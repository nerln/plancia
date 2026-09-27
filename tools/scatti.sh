#!/bin/bash
# Gli screenshot dei README, rifatti sempre uguali.
#
#   ./tools/scatti.sh
#
# Fino alla 1.0 si facevano a mano, e si vedeva: cambiavano di taglio e di dati a
# ogni giro, e uno mostrava ancora una barra laterale senza la voce Cerca. Qui
# l'archivio e' quello finto (nessun dato vero finisce nel repo), la finestra e'
# sempre la stessa e il fattore di scala e' 2, che e' come sono i quattro file
# gia' nel repo: 2400x1830 (l'oggi ci arriva con un ritaglio, vedi piu' sotto).
set -euo pipefail

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || { echo "serve Google Chrome per gli scatti" >&2; exit 1; }

RADICE="$(cd "$(dirname "$0")/.." && pwd)"
CASA="${PLANCIA_DEMO_HOME:-/tmp/plancia-demo}"
# 7844: porta propria di questo script (non 7799, la porta di default vera),
# cosi' non collide col server di un altro lotto in corso in parallelo sulla
# stessa macchina. E' una porta dello script, non di un lotto: cambia solo se
# collide con qualcos'altro che stai girando tu.
PORTA="${PLANCIA_DEMO_PORT:-7844}"
# I due README puntano agli stessi file, e il primo e' quello inglese: se non si
# forza la lingua l'interfaccia segue quella del sistema e gli scatti cambiano da
# macchina a macchina.
LINGUA="${PLANCIA_DEMO_LANG:-en}"
FUORI="$RADICE/docs"
PROFILO="$(mktemp -d)"
# Lo stesso CLAUDE_CONFIG_DIR finto che demo-data.py stampa (tools/demo-data.py:
# cartella_claude_config()): serve perche' lo stato "chiusa" del task Riprendi
# sia visibile quando L3 aggiungera' il pulsante, invece di dover ricordarselo
# a mano ogni volta che si fanno gli scatti.
CLAUDE_CFG_FINTO="$CASA/claude-config"
# CODEX_HOME finto e vuoto (correzione del critico 18/09): senza questo il
# server, una volta avviato, legge il ~/.codex vero di chi lancia lo script
# (plancia/codex.py, CODEX_HOME dall'ambiente). --no-sync salta solo il sync
# d'avvio: il ticker di plancia.api.serve riparte comunque ogni
# sync_caldo_minuti, e demo-data.py ora scrive quel valore alto in
# config.json apposta, ma un CODEX_HOME finto e' la seconda barriera, non
# l'unica, nel caso lo script giri piu' a lungo del previsto.
CODEX_HOME_FINTO="$CASA/codex-home"
# File vuoto per PLANCIA_AGENTS_JSON: senza un registro sessions/ sotto il
# CLAUDE_CONFIG_DIR finto, riprendi._claude_vivo ripiegherebbe sul binario
# vero `claude agents --json` (timeout 25 s) per capire se una sessione e'
# viva. tools/prove/demo.py usa gia' questa variabile per lo stesso motivo.
AGENTI_FINTI="$CASA/agenti-vuoti.json"

echo "==> archivio dimostrativo in $CASA"
rm -rf "$CASA"
PLANCIA_HOME="$CASA" python3 "$RADICE/tools/demo-data.py" >/dev/null
# Le due cartelle finte si creano dopo il `rm -rf "$CASA"` qui sopra, non
# prima: altrimenti sparirebbero con tutto il resto.
mkdir -p "$CODEX_HOME_FINTO"
echo "[]" > "$AGENTI_FINTI"

echo "==> server su :$PORTA (CLAUDE_CONFIG_DIR=$CLAUDE_CFG_FINTO, CODEX_HOME=$CODEX_HOME_FINTO)"
PLANCIA_HOME="$CASA" CLAUDE_CONFIG_DIR="$CLAUDE_CFG_FINTO" CODEX_HOME="$CODEX_HOME_FINTO" \
  PLANCIA_AGENTS_JSON="$AGENTI_FINTI" \
  python3 -m plancia.cli serve --port "$PORTA" --no-sync \
  >/tmp/plancia-scatti.log 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; rm -rf "$PROFILO"' EXIT
for _ in $(seq 1 40); do
  curl -fs -o /dev/null "http://127.0.0.1:$PORTA/" && break
  sleep 0.25
done

scatta() {  # scatta <vista> <file> [altezza-finestra-css]
  # Un profilo nuovo per ogni scatto, e un tetto di tempo. Con un profilo
  # condiviso il secondo Chrome trovava il lock del primo e restava appeso senza
  # dire niente: lo script si fermava li' con lo scatto di prima gia' fatto, che
  # e' il modo peggiore di fallire.
  local casa; casa="$(mktemp -d)"
  # Altezza di finestra in px CSS: 915 di norma (2400x1830 fisici a scala 2,
  # come i quattro file nel repo), piu' alta solo per "oggi" (vedi sotto),
  # dove il pannello Prossimi sta sotto la piega a 915.
  local altezza="${3:-915}"
  # `#/vista` non ricarica se la pagina e' gia' aperta, ma qui e' un Chrome nuovo
  # ogni volta, quindi l'ancora viene letta all'avvio.
  # `timeout` su macOS non c'e' senza coreutils, quindi il tetto si fa a mano.
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --no-first-run --no-default-browser-check --user-data-dir="$casa" \
    --window-size=1200,"$altezza" --force-device-scale-factor=2 \
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
# "oggi" a finestra alta (correzione del critico 18/09: il punto 3 del lotto,
# "Oggi con Prossimi", non era fotografato): a 915 px CSS il pannello
# Prossimi (web/app.js, griglia data-in="4", sotto recap + due bento + le
# proposte) sta sotto la piega, e Chrome --screenshot cattura solo la
# viewport, non la pagina intera. Si scatta a 2600 px CSS (5200 fisici, la
# pagina intera del demo ci sta) e si ritaglia la fascia 2400x1830 che
# contiene il pannello. L'offset e' stato misurato a mano una volta sui dati
# di questo demo (deterministico: stessi dati, stesso motore di riepilogo a
# template) ed e' stabile finche' non cambiano demo-data.py o il CSS della
# pagina; se uno dei due cambia e uno scatto risulta tagliato a meta' del
# pannello, va rimisurato.
scatta oggi dashboard.png 2600
sips --cropOffset 2260 0 --cropToHeightWidth 1830 2400 "$FUORI/dashboard.png" >/dev/null
dim="$(sips -g pixelWidth -g pixelHeight "$FUORI/dashboard.png" | tail -2 | awk '{print $2}' | paste -sd x -)"
[ "$dim" = "2400x1830" ] || { echo "    dashboard.png ritagliato a $dim, non 2400x1830" >&2; exit 1; }
echo "    dashboard.png (ritagliato su Prossimi)"
scatta lavagna board.png
scatta progetti projects.png
# Con la casella vuota lo scatto della ricerca non mostra niente: la domanda si
# passa nell'indirizzo, che e' la stessa cosa che serve per salvarsi una ricerca.
scatta 'cerca?q=incremental%20rebuild' cerca.png

# Il sito usa le stesse immagini a meta' risoluzione. Farlo qui e non a mano e' il
# motivo per cui le sue erano rimaste indietro di una settimana e senza la voce
# Cerca nella barra laterale.
echo "==> copie per il sito, a 1600 px"
mkdir -p "$RADICE/site/img"
for coppia in dashboard.png:today.png board.png:board.png projects.png:projects.png cerca.png:cerca.png; do
  da="${coppia%%:*}"; a="${coppia##*:}"
  sips -Z 1600 "$FUORI/$da" --out "$RADICE/site/img/$a" >/dev/null
  echo "    site/img/$a"
done

echo "==> fatto, in docs/ e in site/img/"
