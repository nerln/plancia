#!/bin/bash
# Gli screenshot dei README, rifatti sempre uguali.
#
#   ./tools/scatti.sh              rifa gli scatti (serve Google Chrome)
#   ./tools/scatti.sh --controlla  non scatta: avvia il server sull'archivio finto e
#                                  controlla che ogni vista da fotografare abbia i
#                                  suoi dati (gira anche senza Chrome, e la prova
#                                  tools/prove/scatti.py lo lancia)
#
# Fino alla 1.0 si facevano a mano, e si vedeva: cambiavano di taglio e di dati a
# ogni giro. Qui l'archivio e' quello finto (nessun dato vero finisce nel repo), la
# finestra e' sempre la stessa e il fattore di scala e' 2: 2400x1830 fisici, come i
# file gia' nel repo.
#
# Le viste sono quelle della dashboard di oggi (web/app.js, `views.*`): Oggi, Task
# (`#/lavagna`), Progetti, Memoria (l'elenco e il grafo, `?memoria=grafo`) e la
# ricerca (`#/cerca?q=`). Nessun ritaglio: uno scatto e' la finestra, non un pezzo di
# una pagina piu' alta che si tagliava a un offset misurato una volta a mano.
#
# Dove scrive (tutte facoltative):
#   PLANCIA_SCATTI_OUT    cartella degli scatti          (default: docs/ del repo)
#   PLANCIA_SCATTI_SITE   cartella delle copie a 1600 px (default: site/img/ del repo;
#                         vuota per non farle)
#   PLANCIA_DEMO_HOME     l'archivio finto               (default: $TMPDIR/plancia-demo)
#   PLANCIA_DEMO_PORT     la porta del server finto      (default: 7844)
#   PLANCIA_DEMO_LANG     la lingua della dashboard      (default: en)
set -euo pipefail

CONTROLLA=0
case "${1:-}" in
  "") ;;
  --controlla) CONTROLLA=1 ;;
  *) echo "uso: tools/scatti.sh [--controlla]" >&2; exit 2 ;;
esac

RADICE="$(cd "$(dirname "$0")/.." && pwd)"
TMP="${TMPDIR:-/tmp}"
TMP="${TMP%/}"
CASA="${PLANCIA_DEMO_HOME:-$TMP/plancia-demo}"
# 7844: porta propria di questo script (non 7773, la porta di default vera), cosi'
# non collide con il server vero ne' con quello di un altro lotto in parallelo.
PORTA="${PLANCIA_DEMO_PORT:-7844}"
if [ "$PORTA" = "7773" ]; then echo "la porta 7773 e' quella del server vero: scegline un'altra" >&2; exit 2; fi
# I due README puntano agli stessi file, e il primo e' quello inglese: se non si
# forza la lingua l'interfaccia segue quella del sistema e gli scatti cambiano da
# macchina a macchina.
LINGUA="${PLANCIA_DEMO_LANG:-en}"
FUORI="${PLANCIA_SCATTI_OUT:-$RADICE/docs}"
SITO="${PLANCIA_SCATTI_SITE-$RADICE/site/img}"

# L'archivio vero non si tocca per nessun motivo: la casa finta non puo' essere
# ~/.plancia, in nessuna delle sue forme.
VERO="$(cd "${HOME:-/}" 2>/dev/null && pwd -P)/.plancia"
mkdir -p "$CASA"
if [ "$(cd "$CASA" && pwd -P)" = "$VERO" ]; then
  echo "PLANCIA_DEMO_HOME punta all'archivio vero ($VERO): mi fermo" >&2; exit 2
fi

if [ "$CONTROLLA" = 0 ]; then
  CHROME="${PLANCIA_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
  [ -x "$CHROME" ] || { echo "serve Google Chrome per gli scatti" >&2; exit 1; }
  mkdir -p "$FUORI"
fi

# Lo stesso CLAUDE_CONFIG_DIR finto che demo-data.py stampa: serve perche' lo stato
# "chiusa" del task Riprendi sia visibile senza doverselo ricordare a mano.
CLAUDE_CFG_FINTO="$CASA/claude-config"
# CODEX_HOME finto e vuoto: senza, il server leggerebbe il ~/.codex vero di chi lancia
# lo script. --no-sync salta il sync d'avvio e il ticker, ma la seconda barriera
# resta: un CODEX_HOME finto, e una HOME finta.
CODEX_HOME_FINTO="$CASA/codex-home"
CASA_FINTA="$CASA/home"
# File vuoto per PLANCIA_AGENTS_JSON: senza un registro sessions/ sotto il
# CLAUDE_CONFIG_DIR finto, riprendi._claude_vivo ripiegherebbe sul binario vero
# `claude agents --json` (timeout 25 s) per capire se una sessione e' viva.
AGENTI_FINTI="$CASA/agenti-vuoti.json"

echo "==> archivio dimostrativo in $CASA"
# `rm -rf` su un percorso dato da fuori: solo se e' vuoto o e' gia' un archivio
# finto di questo script (ha il suo plancia.db). Altrimenti e' una cartella di
# qualcun altro.
if [ -n "$(ls -A "$CASA" 2>/dev/null)" ] && [ ! -f "$CASA/plancia.db" ]; then
  echo "$CASA non e' vuota e non e' un archivio finto: non la cancello" >&2; exit 2
fi
rm -rf "$CASA"
mkdir -p "$CASA"
PLANCIA_HOME="$CASA" python3 "$RADICE/tools/demo-data.py" >/dev/null
# Le cartelle finte si creano dopo il `rm -rf "$CASA"` qui sopra, non prima:
# altrimenti sparirebbero con tutto il resto.
mkdir -p "$CODEX_HOME_FINTO" "$CASA_FINTA"
echo "[]" > "$AGENTI_FINTI"

echo "==> server su :$PORTA"
PLANCIA_HOME="$CASA" CLAUDE_CONFIG_DIR="$CLAUDE_CFG_FINTO" CODEX_HOME="$CODEX_HOME_FINTO" \
  HOME="$CASA_FINTA" PLANCIA_AGENTS_JSON="$AGENTI_FINTI" PYTHONPATH="$RADICE" \
  python3 "$RADICE/bin/plancia" serve --port "$PORTA" --no-sync \
  >"$CASA/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; wait $SERVER 2>/dev/null || true' EXIT
pronto=0
for _ in $(seq 1 60); do
  if curl -fs -o /dev/null "http://127.0.0.1:$PORTA/api/overview"; then pronto=1; break; fi
  kill -0 $SERVER 2>/dev/null || break
  sleep 0.25
done
[ "$pronto" = 1 ] || { echo "il server non e' partito (vedi $CASA/server.log)" >&2; exit 1; }

# ---------------------------------------------------------------- il controllo
# Senza Chrome: ogni vista da fotografare deve avere i dati che la fanno bella.
# Un archivio finto che torna vuoto darebbe cinque screenshot con "nessuna memoria".
if [ "$CONTROLLA" = 1 ]; then
  ok=1
  leggi() { curl -fs "http://127.0.0.1:$PORTA$1"; }
  numero() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
  # la vista Memoria e il suo grafo: una cinquantina di schede, con legami veri e
  # qualche orfana (un archivio senza legami e' una nuvola di pallini)
  m="$(leggi /api/memoria/mappa)"
  schede="$(echo "$m" | numero "len(d['nodi'])")"
  archi="$(echo "$m" | numero "len(d['archi'])")"
  orfane="$(echo "$m" | numero "len(d['diagnosi']['orfane'])")"
  tipi="$(echo "$m" | numero "len({n['tipo'] for n in d['nodi']})")"
  posti="$(echo "$m" | numero "sum(1 for n in d['nodi'] if 0 <= n.get('x', -1) <= 1 and 0 <= n.get('y', -1) <= 1)")"
  echo "    memoria: $schede schede, $archi legami, $orfane orfane, $tipi tipi, $posti con posizione"
  [ "$schede" -ge 40 ] && [ "$schede" -le 70 ] || { echo "    NO: servono 40-70 schede" >&2; ok=0; }
  [ "$archi" -ge "$schede" ] || { echo "    NO: servono piu' legami che schede" >&2; ok=0; }
  [ "$orfane" -ge 1 ] && [ "$orfane" -lt $((schede / 3)) ] || { echo "    NO: servono alcune orfane, non troppe" >&2; ok=0; }
  [ "$tipi" -ge 4 ] || { echo "    NO: servono i quattro tipi" >&2; ok=0; }
  [ "$posti" = "$schede" ] || { echo "    NO: ogni scheda deve avere le sue coordinate" >&2; ok=0; }
  # le altre viste
  for coppia in "Oggi:/api/overview:d['stats']['progetti_attivi']" \
                "Task:/api/tasks:len(d)" \
                "Progetti:/api/projects:len(d)" \
                "Ricerca:/api/search?q=incremental%20rebuild:len(d) if isinstance(d, list) else len(d.get('risultati', d))"; do
    nome="${coppia%%:*}"; resto="${coppia#*:}"; url="${resto%%:*}"; espr="${resto#*:}"
    n="$(leggi "$url" | numero "$espr" 2>/dev/null || echo 0)"
    echo "    $nome: $n"
    [ "${n:-0}" -ge 1 ] || { echo "    NO: la vista $nome non ha dati" >&2; ok=0; }
  done
  [ "$ok" = 1 ] || exit 1
  echo "==> controllo passato"
  exit 0
fi

scatta() {  # scatta <vista> <file> [query-string, es. "&memoria=grafo"]
  # Un profilo nuovo per ogni scatto, e un tetto di tempo. Con un profilo condiviso
  # il secondo Chrome trovava il lock del primo e restava appeso senza dire niente:
  # lo script si fermava li' con lo scatto di prima gia' fatto, che e' il modo
  # peggiore di fallire.
  local casa; casa="$(mktemp -d)"
  local extra="${3:-}"
  # `#/vista` non ricarica se la pagina e' gia' aperta, ma qui e' un Chrome nuovo
  # ogni volta, quindi l'ancora viene letta all'avvio.
  # `--use-mock-keychain` e `--disable-features=MacAppCodeSignClone`: senza il primo
  # Chrome cerca il portachiavi di login (e da un sandbox non lo trova), senza il
  # secondo lascia una copia dell'app in /private/var a ogni avvio ucciso.
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --use-mock-keychain --disable-features=MacAppCodeSignClone \
    --no-first-run --no-default-browser-check --user-data-dir="$casa" \
    --window-size=1200,915 --force-device-scale-factor=2 \
    --virtual-time-budget=8000 \
    --screenshot="$FUORI/$2" "http://127.0.0.1:$PORTA/?ui=$LINGUA${extra}#/$1" >/dev/null 2>&1 &
  # Chrome scrive il file e poi resta in piedi invece di uscire, quindi non si
  # aspetta il processo: si aspetta il file, e appena e' fermo lo si chiude.
  local pid=$! giri=0 dim=0 prima=-1
  rm -f "$FUORI/$2"
  while [ "$giri" -lt 60 ]; do
    sleep 0.5; giri=$((giri + 1))
    kill -0 "$pid" 2>/dev/null || break
    # La redirezione da un file che non c'e' e' un errore della shell, non di `wc`,
    # quindi il file va cercato prima invece di zittire il comando.
    dim=0
    [ -f "$FUORI/$2" ] && dim=$(wc -c < "$FUORI/$2")
    [ "$dim" -gt 0 ] && [ "$dim" -eq "$prima" ] && break
    prima=$dim
  done
  kill -9 "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  rm -rf "$casa"
  [ -s "$FUORI/$2" ] || { echo "    $2 NON fatto" >&2; return 1; }
  # sempre 2400x1830: la finestra e' 1200x915 a scala 2
  local d; d="$(sips -g pixelWidth -g pixelHeight "$FUORI/$2" | tail -2 | awk '{print $2}' | paste -sd x -)"
  [ "$d" = "2400x1830" ] || { echo "    $2 e' $d, non 2400x1830" >&2; return 1; }
  echo "    $2"
}

echo "==> scatti in $FUORI"
scatta oggi dashboard.png
scatta lavagna board.png
scatta progetti projects.png
scatta memoria memoria.png
scatta memoria grafo.png "&memoria=grafo"
# Con la casella vuota lo scatto della ricerca non mostra niente: la domanda si passa
# nell'indirizzo, che e' la stessa cosa che serve per salvarsi una ricerca.
scatta 'cerca?q=incremental%20rebuild' cerca.png

# Il sito usa le stesse immagini a meta' risoluzione. Farlo qui e non a mano e' il
# motivo per cui le sue erano rimaste indietro di una settimana.
if [ -n "$SITO" ]; then
  echo "==> copie per il sito, a 1600 px, in $SITO"
  mkdir -p "$SITO"
  for coppia in dashboard.png:today.png board.png:board.png projects.png:projects.png \
                memoria.png:memoria.png grafo.png:grafo.png cerca.png:cerca.png; do
    da="${coppia%%:*}"; a="${coppia##*:}"
    sips -Z 1600 "$FUORI/$da" --out "$SITO/$a" >/dev/null
    echo "    $a"
  done
fi

echo "==> fatto"
