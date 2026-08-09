#!/bin/bash
# Gli screenshot dei README, rifatti sempre uguali.
#
#   ./tools/scatti.sh
#
# Fino alla 1.0 si facevano a mano, e si vedeva: cambiavano di taglio e di dati a
# ogni giro, e uno mostrava ancora una barra laterale senza la voce Cerca. Qui
# l'archivio e' quello finto (nessun dato vero finisce nel repo), la finestra e'
# sempre la stessa e il fattore di scala e' 2, che e' come sono i tre file gia'
# nel repo: 2400x1830.
set -euo pipefail

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || { echo "serve Google Chrome per gli scatti" >&2; exit 1; }

RADICE="$(cd "$(dirname "$0")/.." && pwd)"
CASA="${PLANCIA_DEMO_HOME:-/tmp/plancia-demo}"
PORTA="${PLANCIA_DEMO_PORT:-7799}"
# I due README puntano agli stessi file, e il primo e' quello inglese: se non si
# forza la lingua l'interfaccia segue quella del sistema e gli scatti cambiano da
# macchina a macchina.
LINGUA="${PLANCIA_DEMO_LANG:-en}"
FUORI="$RADICE/docs"
PROFILO="$(mktemp -d)"

echo "==> archivio dimostrativo in $CASA"
rm -rf "$CASA"
PLANCIA_HOME="$CASA" python3 "$RADICE/tools/demo-data.py" >/dev/null

echo "==> server su :$PORTA"
PLANCIA_HOME="$CASA" python3 -m plancia.cli serve --port "$PORTA" --no-sync \
  >/tmp/plancia-scatti.log 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; rm -rf "$PROFILO"' EXIT
for _ in $(seq 1 40); do
  curl -fs -o /dev/null "http://127.0.0.1:$PORTA/" && break
  sleep 0.25
done

scatta() {  # scatta <vista> <file>
  # Un profilo nuovo per ogni scatto, e un tetto di tempo. Con un profilo
  # condiviso il secondo Chrome trovava il lock del primo e restava appeso senza
  # dire niente: lo script si fermava li' con lo scatto di prima gia' fatto, che
  # e' il modo peggiore di fallire.
  local casa; casa="$(mktemp -d)"
  # `#/vista` non ricarica se la pagina e' gia' aperta, ma qui e' un Chrome nuovo
  # ogni volta, quindi l'ancora viene letta all'avvio.
  # `timeout` su macOS non c'e' senza coreutils, quindi il tetto si fa a mano.
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --no-first-run --no-default-browser-check --user-data-dir="$casa" \
    --window-size=1200,915 --force-device-scale-factor=2 \
    --virtual-time-budget=6000 \
    --screenshot="$FUORI/$2" "http://127.0.0.1:$PORTA/?ui=$LINGUA#/$1" >/dev/null 2>&1 &
  # Chrome scrive il file e poi resta in piedi invece di uscire, quindi non si
  # aspetta il processo: si aspetta il file, e appena e' fermo lo si chiude.
  local pid=$! giri=0 dim=0 prima=-1
  rm -f "$FUORI/$2"
  while [ "$giri" -lt 60 ]; do
    sleep 0.5; giri=$((giri + 1))
    kill -0 "$pid" 2>/dev/null || break
    # La redirezione da un file che non c'e' e' un errore della shell, non di
    # `wc`, quindi il file va cercato prima invece di zittire il comando.
    dim=0
    [ -f "$FUORI/$2" ] && dim=$(wc -c < "$FUORI/$2")
    [ "$dim" -gt 0 ] && [ "$dim" -eq "$prima" ] && break
    prima=$dim
  done
  kill -9 "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  rm -rf "$casa"
  [ -s "$FUORI/$2" ] || { echo "    $2 NON fatto" >&2; return 1; }
  echo "    $2"
}

echo "==> scatti"
scatta oggi dashboard.png
scatta lavagna board.png
scatta progetti projects.png
# Con la casella vuota lo scatto della ricerca non mostra niente: la domanda si
# passa nell'indirizzo, che e' la stessa cosa che serve per salvarsi una ricerca.
scatta 'cerca?q=incremental%20rebuild' cerca.png

echo "==> fatto, in docs/"
