#!/bin/bash
# Gli screenshot dell'app Mac per i README e per il sito, rifatti sempre uguali.
#
#   ./tools/scatti-mac.sh            rifa gli scatti (serve macOS 26, Xcode e l'app costruita)
#
# L'app si fotografa da sola (modalita' --istantanee, vedi mac/Sources/Guscio/Istantanee.swift):
# niente controllo del computer, niente registrazione schermo. Qui si avvia un server di
# prova su un archivio dimostrativo (tools/demo-data.py, nessun dato vero), si lancia l'app
# in inglese, a una finestra fissa (1280x820 punti, 2560x1640 pixel), con la dimensione del
# testo e lo stile fissati sulla riga di comando cosi' le preferenze di chi lancia non
# cambiano niente, e si copiano gli scatti scelti in docs/ (e a 1600 px in site/img/).
# Quelli del web si fanno con tools/scatti.sh.
#
# Serve l'app gia' costruita (./mac/build.sh): non la costruisce, perche' una compilazione
# alla volta e' una scelta di chi lancia. Il pannello Jarvis si fotografa con la prova del
# pannello (mac/Prove/ProvaPannelloJarvis.swift, modo "scene"): quella si compila qui.
#
# Dove scrive (tutte facoltative):
#   PLANCIA_SCATTI_OUT    cartella degli scatti          (default: docs/ del repo)
#   PLANCIA_SCATTI_SITE   cartella delle copie a 1600 px (default: site/img/ del repo;
#                         vuota per non farle)
#   PLANCIA_MAC_LAVORO    cartella di lavoro: archivio finto, PNG grezzi, la prova Jarvis
#                         compilata (default: $TMPDIR/plancia-scatti-mac)
#   PLANCIA_MAC_APP       l'app da fotografare           (default: mac/build/Plancia.app)
#   PLANCIA_DEMO_PORT     la porta del server finto      (default: 7853)
#
# Cosa si fotografa e perche' proprio questo:
#   mac-oggi          Oggi, chiaro: il riepilogo in una riga, un progetto per riga
#   mac-task          Task con l'Inspector: la tabella e il pulsante Riprendi
#   mac-progetti      Progetti raggruppati per area, con il dettaglio del selezionato
#   mac-memoria       la Mappa della memoria, a isole
#   mac-memoria-isola l'isola delle preferenze ingrandita, coi titoli umani
#   mac-ricerca       la Ricerca, con i risultati per tipo
#   mac-legno         lo stile Legno (Oggi)
#   mac-scuro         la Mappa in scuro
#   mac-jarvis        il pannello Jarvis con la scheda di conferma di un agente (scuro: in
#                     chiaro il vetro, senza uno sfondo dietro, rende un grigio fangoso)
set -euo pipefail

RADICE="$(cd "$(dirname "$0")/.." && pwd)"
TMP="${TMPDIR:-/tmp}"; TMP="${TMP%/}"
LAVORO="${PLANCIA_MAC_LAVORO:-$TMP/plancia-scatti-mac}"
APP="${PLANCIA_MAC_APP:-$RADICE/mac/build/Plancia.app}"
PORTA="${PLANCIA_DEMO_PORT:-7853}"
FUORI="${PLANCIA_SCATTI_OUT:-$RADICE/docs}"
SITO="${PLANCIA_SCATTI_SITE-$RADICE/site/img}"

[ "$(uname)" = "Darwin" ] || { echo "serve macOS" >&2; exit 2; }
[ "$PORTA" != "7773" ] || { echo "la porta 7773 e' quella del server vero: scegline un'altra" >&2; exit 2; }
[ -x "$APP/Contents/MacOS/Plancia" ] || { echo "manca l'app costruita ($APP): ./mac/build.sh" >&2; exit 1; }
xcrun --find swiftc >/dev/null 2>&1 || { echo "serve Xcode per la prova del pannello Jarvis" >&2; exit 1; }

# L'archivio vero non si tocca per nessun motivo: la casa finta non puo' essere ~/.plancia.
VERO="$(cd "${HOME:-/}" 2>/dev/null && pwd -P)/.plancia"
mkdir -p "$LAVORO"
if [ "$(cd "$LAVORO" && pwd -P)" = "$VERO" ]; then
  echo "PLANCIA_MAC_LAVORO punta all'archivio vero ($VERO): mi fermo" >&2; exit 2
fi
# `rm -rf` su un percorso dato da fuori: solo se e' vuoto o e' gia' una cartella di questo script.
if [ -n "$(ls -A "$LAVORO" 2>/dev/null)" ] && [ ! -f "$LAVORO/.scatti-mac" ]; then
  echo "$LAVORO non e' vuota e non e' una cartella di questo script: non la cancello" >&2; exit 2
fi
rm -rf "$LAVORO"
mkdir -p "$LAVORO/casa" "$LAVORO/home" "$LAVORO/claude-cfg" "$LAVORO/codex-home" "$LAVORO/tmp" \
         "$LAVORO/finti" "$LAVORO/png"
: > "$LAVORO/.scatti-mac"
mkdir -p "$FUORI"

# L'ambiente: tutto in cartelle nostre, e i programmi che toccherebbero la macchina finti.
export PLANCIA_HOME="$LAVORO/casa"
export HOME="$LAVORO/home"
export CLAUDE_CONFIG_DIR="$LAVORO/claude-cfg"
export CODEX_HOME="$LAVORO/codex-home"
export TMPDIR="$LAVORO/tmp"
echo "[]" > "$LAVORO/agenti-vuoti.json"
export PLANCIA_AGENTS_JSON="$LAVORO/agenti-vuoti.json"
for n in launchctl osascript schtasks systemctl crontab claude codex say afplay; do
  printf '#!/bin/sh\nexit 0\n' > "$LAVORO/finti/$n"; chmod +x "$LAVORO/finti/$n"
done
export PATH="$LAVORO/finti:/usr/bin:/bin:/usr/sbin:/sbin"

# Un solo processo pesante alla volta, e non su una macchina gia' in affanno.
aspetta_carico() {
  for _ in $(seq 1 60); do
    c="$(sysctl -n vm.loadavg | awk '{print int($2)}')"
    [ "${c:-0}" -lt 40 ] && return 0
    sleep 5
  done
  echo "    (la macchina e' carica, vado avanti lo stesso)"
}

echo "==> archivio dimostrativo in $LAVORO/casa"
python3 "$RADICE/tools/demo-data.py" >/dev/null
# l'app legge la porta da config.json
python3 - "$PLANCIA_HOME/config.json" "$PORTA" <<'PY'
import json, os, sys
p, porta = sys.argv[1], int(sys.argv[2])
c = json.load(open(p)) if os.path.exists(p) else {}
c["port"] = porta
json.dump(c, open(p, "w"), indent=2)
PY

echo "==> server su :$PORTA"
CLAUDE_CONFIG_DIR="$PLANCIA_HOME/claude-config" PYTHONPATH="$RADICE" \
  python3 "$RADICE/bin/plancia" serve --port "$PORTA" --no-sync >"$LAVORO/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; wait $SERVER 2>/dev/null || true' EXIT
pronto=0
for _ in $(seq 1 60); do
  if curl -fs -o /dev/null "http://127.0.0.1:$PORTA/api/overview"; then pronto=1; break; fi
  kill -0 $SERVER 2>/dev/null || break
  sleep 0.25
done
[ "$pronto" = 1 ] || { echo "il server non e' partito (vedi $LAVORO/server.log)" >&2; exit 1; }
curl -fs -o /dev/null "http://127.0.0.1:$PORTA/"

# Un giro dell'app: scatta <cartella> <aspetto> <stile> <scena della mappa> [parola cercata]
scatta() {
  local dest="$LAVORO/png/$1" aspetto="$2" stile="$3" scena="$4" parola="${5:-rollback}"
  mkdir -p "$dest"
  aspetta_carico
  "$APP/Contents/MacOS/Plancia" --istantanee "$dest" --aspetto "$aspetto" --lingua en \
    --parola "$parola" --stile "$stile" --testo 3 --memoria-scena "$scena" \
    >"$dest/log.txt" 2>&1 &
  local pid=$! giri=0
  # tetto di tempo: l'app esce da sola dopo l'ultimo scatto
  while kill -0 $pid 2>/dev/null && [ $giri -lt 150 ]; do sleep 2; giri=$((giri + 1)); done
  if kill -0 $pid 2>/dev/null; then kill $pid 2>/dev/null || true; echo "    l'app non e' uscita: l'ho chiusa" >&2; fi
  wait $pid 2>/dev/null || true
  grep -q "raggiungibile: true" "$dest/log.txt" || { echo "    giro $1 fallito (vedi $dest/log.txt)" >&2; exit 1; }
  echo "    $1"
}

echo "==> giri dell'app"
scatta chiaro chiaro sistema tutto
scatta isola chiaro sistema gruppo
scatta legno chiaro legno tutto
scatta scuro scuro sistema tutto

echo "==> pannello Jarvis"
aspetta_carico
SORG=()
while IFS= read -r f; do SORG+=("$f"); done < <(find "$RADICE/mac/Sources/Core" -name '*.swift' | sort)
SORG+=("$RADICE/mac/Sources/Viste/MemoriaDati.swift" "$RADICE/mac/Sources/Sistema/Conf.swift" \
       "$RADICE/mac/Sources/Sistema/Cattura.swift")
while IFS= read -r f; do SORG+=("$f"); done < <(ls "$RADICE"/mac/Sources/Sistema/[Jj]arvis*.swift | sort)
SORG+=("$RADICE/mac/Prove/ProvaPannelloJarvis.swift")
LUCCHETTO="${PLANCIA_LUCCHETTO:-/tmp/plancia-swiftc-$(id -u).lock}"
python3 "$RADICE/mac/lucchetto.py" "$LUCCHETTO" xcrun swiftc -swift-version 5 -parse-as-library -Onone \
  -target "$(uname -m)-apple-macosx26.0" -o "$LAVORO/prova-jarvis" "${SORG[@]}" 2>&1 | grep -E "error" || true
[ -x "$LAVORO/prova-jarvis" ] || { echo "compilazione della prova Jarvis fallita" >&2; exit 1; }
mkdir -p "$LAVORO/png/jarvis"
PLANCIA_JARVIS_PROVA=1 PLANCIA_JARVIS_PROVA_SENZA_ETICHETTA=1 PLANCIA_PROVA_LINGUA=en \
  "$LAVORO/prova-jarvis" "$LAVORO/png/jarvis" scuro scene >"$LAVORO/png/jarvis/log.txt" 2>&1 &
pid=$!; giri=0
while kill -0 $pid 2>/dev/null && [ $giri -lt 60 ]; do sleep 2; giri=$((giri + 1)); done
kill -0 $pid 2>/dev/null && { kill $pid 2>/dev/null || true; }
wait $pid 2>/dev/null || true
[ -s "$LAVORO/png/jarvis/jarvis-schedaAgente-scuro.png" ] || { echo "manca la scena Jarvis" >&2; exit 1; }

# metti <cartella dei grezzi> <file grezzo> <nome finale>: copia in docs/, e a 1600 px nel sito
# quelli che il sito mostra (la larghezza si riduce solo se supera 1600: il pannello Jarvis no).
metti() {
  local da="$LAVORO/png/$1/$2" a="$3"
  [ -s "$da" ] || { echo "    manca $da" >&2; exit 1; }
  cp "$da" "$FUORI/$a"
  local d; d="$(sips -g pixelWidth -g pixelHeight "$FUORI/$a" | tail -2 | awk '{print $2}' | paste -sd x -)"
  echo "    $a ($d)"
  if [ -n "$SITO" ] && [ "${4:-}" = "sito" ]; then
    mkdir -p "$SITO"
    local w="${d%x*}"
    if [ "$w" -gt 1600 ]; then sips --resampleWidth 1600 "$FUORI/$a" --out "$SITO/$a" >/dev/null
    else cp "$FUORI/$a" "$SITO/$a"; fi
  fi
}

echo "==> scatti in $FUORI"
metti chiaro oggi-chiaro.png mac-oggi.png sito
metti chiaro task-dettaglio-chiaro.png mac-task.png sito
metti chiaro progetti-dettaglio-chiaro.png mac-progetti.png sito
metti chiaro memoria-chiaro.png mac-memoria.png sito
metti isola memoria-dettaglio-chiaro.png mac-memoria-isola.png
metti chiaro ricerca-chiaro.png mac-ricerca.png sito
metti legno oggi-chiaro.png mac-legno.png sito
metti scuro memoria-scuro.png mac-scuro.png
metti jarvis jarvis-schedaAgente-scuro.png mac-jarvis.png sito

echo "==> fatto"
