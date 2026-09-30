#!/bin/bash
# La prova del pannello Jarvis dell'app Mac, senza microfono e senza altoparlanti.
#
#   ./tools/prova-jarvis-mac.sh [cartella dove tenere i PNG]
#
# Compila i file Jarvis*.swift con mac/Prove/ProvaPannelloJarvis.swift, avvia un server di
# prova con un `claude` finto (tools/prove/_claude_finto_jarvis.py) su un archivio
# dimostrativo, e fa girare il pannello in modo prova (PLANCIA_JARVIS_PROVA=1):
#   - una scena fissa per ogni stato (riposo, ascolto, pensa, risponde, scheda di conferma,
#     scheda di un agente che scrive, scheda di una sessione, senza voce, server spento,
#     risposta lunga), in chiaro e in scuro, fotografate con il vetro vero;
#   - il ciclo vero contro il server di prova: il testo scorre, una proposta diventa una
#     scheda, "si" non conferma, il pulsante conferma una volta sola, Esc butta la scheda e
#     ferma il server, chiudere il pannello butta la scheda, il microfono finto si accende
#     solo dal pulsante e si spegne da solo;
#   - il server spento: il pannello lo dice e non resta appeso.
# Poi guarda cosa e' rimasto nell'archivio (solo i task confermati col pulsante) e cosa ha visto il
# modello finto (i tool di scrittura negati).
#
# Isolamento: PLANCIA_HOME, HOME, CLAUDE_CONFIG_DIR e CODEX_HOME sono cartelle di questo
# script, mai quelle vere; launchctl, osascript, claude e gli altri sono programmi finti
# inerti in testa al PATH. Non tocca la porta vera ne' Voicebox. Vive fuori da
# tools/prova.py perche' richiede macOS e Xcode; altrove esce 0 dicendo che salta.
set -euo pipefail

if [ "$(uname)" != "Darwin" ] || ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "saltato: serve macOS con Xcode"
  exit 0
fi

RADICE="$(cd "$(dirname "$0")/.." && pwd)"
BASE_TMP="${PLANCIA_PROVA_TMP:-${TMPDIR:-/tmp}}"
TMP="$(mktemp -d "$BASE_TMP/plancia-prova-jarvis.XXXXXX")"
PNG="${1:-$TMP/png}"
SERVER=""
POCKET=""
pulisci() {
  [ -n "$SERVER" ] && kill "$SERVER" 2>/dev/null || true
  [ -n "$POCKET" ] && { kill "$POCKET" 2>/dev/null || true; wait "$POCKET" 2>/dev/null || true; }
  rm -rf "$TMP"
}
trap pulisci EXIT

LIBERO_KB="$(df -k "$TMP" | awk 'NR==2 {print $4}')"
if [ "${LIBERO_KB:-0}" -lt 1048576 ]; then
  echo "Spazio libero insufficiente: $((LIBERO_KB / 1024)) MB, ne servono almeno 1024." >&2
  exit 1
fi

# ---- l'ambiente: tutto in una cartella nostra, e i programmi finti davanti a tutto
export PLANCIA_HOME="$TMP/casa"
export HOME="$TMP/home"
export CLAUDE_CONFIG_DIR="$TMP/claude-cfg"
export CODEX_HOME="$TMP/codex-home"
export TMPDIR="$TMP/tmp"
export PLANCIA_AGENTS_JSON="$TMP/agenti-vuoti.json"
export FINTO_LOG="$TMP/claude-finto.log"
mkdir -p "$PLANCIA_HOME" "$HOME" "$CLAUDE_CONFIG_DIR" "$CODEX_HOME" "$TMPDIR" "$TMP/finti" "$PNG"
echo "[]" > "$PLANCIA_AGENTS_JSON"
for n in launchctl osascript schtasks systemctl crontab codex say; do
  printf '#!/bin/sh\nexit 0\n' > "$TMP/finti/$n"
  chmod +x "$TMP/finti/$n"
done
printf '#!/bin/sh\nexec /usr/bin/python3 "%s/tools/prove/_claude_finto_jarvis.py" "$@"\n' "$RADICE" > "$TMP/finti/claude"
chmod +x "$TMP/finti/claude"
export PLANCIA_TERMINALE="$TMP/finti/osascript"
export PATH="$TMP/finti:/usr/bin:/bin:/usr/sbin:/sbin"

# Lo stesso lucchetto di build.sh e tools/prova-mac.sh: una compilazione alla volta.
LUCCHETTO="${PLANCIA_LUCCHETTO:-/tmp/plancia-swiftc-$(id -u).lock}"
mkdir -p "$(dirname "$LUCCHETTO")"

echo "==> compilo il pannello"
SORGENTI=()
while IFS= read -r f; do SORGENTI+=("$f"); done < <(find "$RADICE/mac/Sources/Core" -name '*.swift' | sort)
SORGENTI+=("$RADICE/mac/Sources/Sistema/Conf.swift" "$RADICE/mac/Sources/Sistema/Cattura.swift")
while IFS= read -r f; do SORGENTI+=("$f"); done < <(ls "$RADICE"/mac/Sources/Sistema/[Jj]arvis*.swift | sort)
SORGENTI+=("$RADICE/mac/Prove/ProvaPannelloJarvis.swift")
python3 "$RADICE/mac/lucchetto.py" "$LUCCHETTO" xcrun swiftc \
  -swift-version 5 -parse-as-library -Onone \
  -target "$(uname -m)-apple-macosx26.0" \
  -o "$TMP/prova-jarvis" "${SORGENTI[@]}" 2>&1 | grep -E "error" || true
[ -x "$TMP/prova-jarvis" ] || { echo "compilazione fallita"; exit 1; }

echo "==> archivio dimostrativo e server di prova"
python3 "$RADICE/tools/demo-data.py" >/dev/null
libera() { python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'; }
PORTA="$(libera)"
PORTA_POCKET="$(libera)"
# Un Pocket-TTS finto (tools/prove/_pocket_finto.py) su una porta libera: la sintesi vera passa dal
# server, il suono no. Voicebox punta a una porta chiusa: la prova non tocca mai quelli veri.
export PLANCIA_POCKET_LOG="$TMP/pocket.log"
: > "$PLANCIA_POCKET_LOG"
python3 "$RADICE/tools/prove/_pocket_finto.py" "$PORTA_POCKET" "$PLANCIA_POCKET_LOG" &
POCKET=$!
python3 - "$PLANCIA_HOME/config.json" "$PORTA" "$TMP/finti/claude" "$PORTA_POCKET" <<'PY'
import json, os, sys
p, porta, claude, pocket = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
c = json.load(open(p)) if os.path.exists(p) else {}
c["port"] = porta
c["claude_bin"] = claude
c["pocket_url"] = "http://127.0.0.1:%d" % pocket
c["voicebox_url"] = "http://127.0.0.1:9"
json.dump(c, open(p, "w"))
PY
(cd "$RADICE" && exec python3 -m plancia.cli serve --port "$PORTA" --no-sync) >"$TMP/server.log" 2>&1 &
SERVER=$!
for _ in $(seq 1 60); do
  curl -fs -o /dev/null "http://127.0.0.1:$PORTA/api/status" && break
  sleep 0.25
done
curl -fs -o /dev/null "http://127.0.0.1:$PORTA/api/status" || { echo "il server di prova non parte"; cat "$TMP/server.log"; exit 1; }
# il token nasce alla prima pagina servita, non all'avvio: senza, la prima richiesta del pannello
# verrebbe rifiutata (come succede a una casa nuova prima che si apra la dashboard)
curl -fs -o /dev/null "http://127.0.0.1:$PORTA/"
[ -s "$PLANCIA_HOME/token" ] || { echo "il server non ha scritto il token"; exit 1; }

export PLANCIA_JARVIS_PROVA=1
falliti=0
for aspetto in chiaro scuro; do
  echo "==> pannello, aspetto $aspetto"
  "$TMP/prova-jarvis" "$PNG" "$aspetto" tutto || falliti=1
done

echo "==> con il server spento"
kill "$SERVER" 2>/dev/null || true
wait "$SERVER" 2>/dev/null || true
SERVER=""
"$TMP/prova-jarvis" "$PNG" chiaro spento || falliti=1

echo "==> cosa e' rimasto"
# il server e' spento: si legge il database direttamente, sola lettura
python3 - "$PLANCIA_HOME/plancia.db" "$FINTO_LOG" <<'PY' || falliti=1
import json, sqlite3, sys
db = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
titoli = [r[0] for r in db.execute("SELECT title FROM tasks")]
esito = 0
def controlla(nome, ok):
    global esito
    print(("  ok   " if ok else "  NO   ") + nome)
    if not ok:
        esito = 1
# il pannello gira due volte (chiaro e scuro) e ogni giro preme Conferma una volta sola
controlla("il task confermato col pulsante c'e', una volta per giro (due)",
          titoli.count("Task dalla prova Jarvis") == 2)
controlla("quello buttato con Esc non c'e'", "Da buttare con Esc" not in titoli)
controlla("quello buttato chiudendo il pannello non c'e'", "Da buttare chiudendo" not in titoli)
controlla("quello nato dalla voce e lasciato senza conferma non c'e'",
          not any("mario" in t.lower() for t in titoli))
righe = open(sys.argv[2], encoding="utf-8").read().splitlines()
argv = [json.loads(r[5:]) for r in righe if r.startswith("ARGV ")]
scritture = ["mcp__plancia__plancia_task_add", "mcp__plancia__plancia_task_update",
             "mcp__plancia__plancia_project_update", "mcp__plancia__plancia_manda"]
def sicuro(a):
    if "--disallowedTools" not in a or "--allowedTools" not in a:
        return False
    i, j = a.index("--disallowedTools"), a.index("--allowedTools")
    negati = a[i + 1:j] if i < j else a[i + 1:]
    ammessi = a[j + 1:i] if j < i else a[j + 1:]
    return all(t in negati for t in scritture) and not any(t in ammessi for t in scritture)
controlla("il modello e' partito in sola lettura (tool di scrittura negati)",
          bool(argv) and all(sicuro(a) for a in argv))
sys.exit(esito)
PY

if [ "$falliti" -ne 0 ]; then
  echo "FALLITA"
  exit 1
fi
echo "verde (PNG in $PNG)"
