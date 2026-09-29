#!/bin/bash
# La prova del Core dell'app Mac: compila mac/Sources/Core con un main di prova
# (mac/Prove/Prova.swift), decodifica tutte le fixture di mac/Prove/fixture con i modelli,
# controlla che i campi mancanti o sbagliati non facciano cadere niente, e fa girare lo
# Store e il Cliente contro un server finto (mac/Prove/server_finto.py) che serve le stesse
# fixture e rifiuta le scritture senza token.
#
#   ./tools/prova-mac.sh
#
# Vive fuori da tools/prova.py apposta: quello gira anche su Linux e Windows, questo
# richiede macOS e Xcode. Sulle altre piattaforme esce 0 dicendo che salta.
set -euo pipefail

if [ "$(uname)" != "Darwin" ] || ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "saltato: serve macOS con Xcode"
  exit 0
fi

RADICE="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
SERVER=""
trap '[ -n "$SERVER" ] && kill "$SERVER" 2>/dev/null || true; rm -rf "$TMP"' EXIT

LIBERO_KB="$(df -k "$TMP" | awk 'NR==2 {print $4}')"
if [ "${LIBERO_KB:-0}" -lt 1048576 ]; then
  echo "Spazio libero insufficiente: $((LIBERO_KB / 1024)) MB, ne servono almeno 1024." >&2
  exit 1
fi

# Lo stesso file per tutti (build.sh e tools/prova-mac.sh); PLANCIA_LUCCHETTO lo sposta.
LUCCHETTO="${PLANCIA_LUCCHETTO:-/tmp/plancia-swiftc-$(id -u).lock}"
mkdir -p "$(dirname "$LUCCHETTO")"

echo "==> compilo il Core"
SORGENTI=()
while IFS= read -r f; do SORGENTI+=("$f"); done < <(find "$RADICE/mac/Sources/Core" -name '*.swift' | sort)
python3 "$RADICE/mac/lucchetto.py" "$LUCCHETTO" xcrun swiftc \
  -swift-version 5 -parse-as-library -Onone \
  -target "$(uname -m)-apple-macosx26.0" \
  -o "$TMP/prova-core" "${SORGENTI[@]}" "$RADICE/mac/Prove/Prova.swift"

echo "==> server finto"
PORTA="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
CASA="$TMP/casa"
mkdir -p "$CASA"
echo "{\"port\": $PORTA, \"lingua\": \"it\"}" > "$CASA/config.json"
echo "token-di-prova" > "$CASA/token"
: > "$TMP/registro"
python3 "$RADICE/mac/Prove/server_finto.py" "$PORTA" "$RADICE/mac/Prove/fixture" "$TMP/registro" "token-di-prova" &
SERVER=$!
for _ in $(seq 1 40); do
  curl -fs -o /dev/null "http://127.0.0.1:$PORTA/api/status" && break
  sleep 0.25
done

echo "==> prova"
falliti=0
PLANCIA_HOME="$CASA" "$TMP/prova-core" "$RADICE/mac/Prove/fixture" "$PORTA" || falliti=1

echo "==> cosa ha visto il server finto"
controlla() {  # controlla <descrizione> <espressione grep>
  if grep -Eq "$2" "$TMP/registro"; then echo "  ok   $1"; else echo "  NO   $1"; falliti=1; fi
}
controlla "PATCH di un task con il token" '^PATCH /api/tasks/3\? token=token-di-prova$'
controlla "POST di un nuovo task con il token e col compartimento non ancora scelto" '^POST /api/tasks\? token=token-di-prova$'
controlla "le letture non portano il token" '^GET /api/lavagna\?[^ ]* token=-$'
controlla "dopo la scelta ogni lettura porta il compartimento" '^GET /api/lavagna\?.*compartimento=Lavoro token=-$'
controlla "dopo la scelta anche le scritture portano il compartimento" '^POST /api/sync\?compartimento=Lavoro token=token-di-prova$'
controlla "la ricerca chiede /api/search con la parola" '^GET /api/search\?.*q=plancia'

if [ "$falliti" -ne 0 ]; then
  echo "FALLITA"
  exit 1
fi
echo "verde"
