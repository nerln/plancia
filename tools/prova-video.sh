#!/bin/bash
# Il collaudo a video: tools/prova.py gira senza browser, tools/prova-front.py
# guarda solo il sorgente con delle regex. Nessuno dei due apre davvero la
# pagina, quindi nessuno dei due vede un redesign che passa la CI e arriva
# rotto a video (un errore JavaScript, una vista che il router non riempie
# più). Qui si apre per davvero, in Chrome headless, e si guarda cosa il DOM
# dice di sé stesso dopo il caricamento.
#
#   bash tools/prova-video.sh
#
# Le viste provate sono tutti gli indirizzi "#/qualcosa" che si trovano in
# web/index.html (menu laterale, link "Guida" nel piede, link "Briefing" in
# alto): non scritte qui a mano, così questo file resta vero anche quando il
# menu cambia. Si parte dalla porta 7831 e si sale finché non se ne trova una
# libera, per non litigare con altri lotti in corso in parallelo.
#
# NOTA IMPORTANTE (letta rompendo il router apposta, vedi il rapporto del
# lotto L0-PROVE-2): route(), in web/app.js, scrive SEMPRE qualcosa dentro
# #view prima di sapere se la vista ha funzionato: un placeholder "carico…"
# subito, e se la funzione della vista alza un'eccezione la inghiotte in un
# try/catch e scrive "errore: ..." al suo posto. Quindi #view non è MAI vuoto
# dopo che app.js è partito, e "il contenuto è vuoto" da solo non vede niente:
# una vista che il router ha smesso di riempire ha comunque del testo dentro,
# è solo il segnaposto. Per questo leggi_dom, oltre a VUOTO/PIENO, riconosce
# il caso "l'unico figlio di #view è un <div class=empty> il cui testo
# comincia con carico/loading o errore/error" e lo dichiara rosso: un
# div.empty legittimo in mezzo ad altro contenuto resta verde. La lingua
# dell'indirizzo è fissata a "it" (?ui=it, come fa scatti.sh con ?ui=$LINGUA)
# così il testo del segnaposto non dipende dal locale della macchina che
# lancia lo script.
set -euo pipefail

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || { echo "serve Google Chrome per il collaudo a video" >&2; exit 1; }

RADICE="$(cd "$(dirname "$0")/.." && pwd)"
CASA="${PLANCIA_VIDEO_HOME:-/tmp/plancia-prova-video-$$}"
LOG="${PLANCIA_VIDEO_LOG:-/tmp/plancia-prova-video-$$.log}"

# Una cartella qualunque passata in PLANCIA_VIDEO_HOME finisce cancellata con
# rm -rf due volte (qui sotto e nel trap): si accetta solo se il nome dice
# chiaramente che è nostra, per non poter mai colpire una cartella vera.
case "$CASA" in
  *plancia-prova-video*) ;;
  *) echo "PLANCIA_VIDEO_HOME non contiene 'plancia-prova-video', non la tocco: $CASA" >&2
     exit 1 ;;
esac

pulisci() {
  local esito=$?
  [ -n "${SERVER:-}" ] && kill "$SERVER" 2>/dev/null || true
  [ -n "${SERVER:-}" ] && wait "$SERVER" 2>/dev/null || true
  rm -rf "$CASA"
  exit "$esito"
}
trap pulisci EXIT

echo "==> archivio di prova in $CASA"
rm -rf "$CASA"
PLANCIA_HOME="$CASA" python3 "$RADICE/tools/demo-data.py" >/dev/null

# la prima porta libera da 7831 (o da PLANCIA_VIDEO_PORT) in su
PORTA="${PLANCIA_VIDEO_PORT:-7831}"
while python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sys.exit(0 if s.connect_ex(('127.0.0.1', $PORTA)) == 0 else 1)
"; do
  PORTA=$((PORTA + 1))
done

echo "==> server su :$PORTA"
# PYTHONPATH invece di un cd: lo script deve girare uguale anche lanciato da
# un'altra cartella (`cd /tmp && bash .../tools/prova-video.sh`), e senza
# questo "python3 -m plancia.cli" non trova il modulo (ModuleNotFoundError nel
# log) mentre il resto dello script continua e scambia il server morto per
# ogni vista rotta.
PLANCIA_HOME="$CASA" PYTHONPATH="$RADICE${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m plancia.cli serve --port "$PORTA" --no-sync >"$LOG" 2>&1 &
SERVER=$!
ATTIVO=0
for _ in $(seq 1 40); do
  curl -fs -o /dev/null "http://127.0.0.1:$PORTA/" && { ATTIVO=1; break; }
  sleep 0.25
done
if [ "$ATTIVO" -ne 1 ] || ! kill -0 "$SERVER" 2>/dev/null; then
  echo "il server non è partito, vedi $LOG:" >&2
  cat "$LOG" >&2
  exit 1
fi

# Ogni indirizzo "#/qualcosa" che compare in web/index.html: il menu laterale,
# ma anche "Guida" (-> #/benvenuto) e "Briefing" (-> #/briefing), che sono
# raggiungibili dall'interfaccia senza stare nel <nav>. Se web/app.js definisce
# anche una vista "guida" vera e propria (oggi non esiste), si aggiunge pure.
VISTE="$(python3 - "$RADICE/web/index.html" "$RADICE/web/app.js" <<'PY'
import re
import sys

indice = open(sys.argv[1], encoding="utf-8").read()
viste = list(dict.fromkeys(re.findall(r'href="#/(\w+)"', indice)))

app = open(sys.argv[2], encoding="utf-8").read()
if "guida" not in viste and re.search(r"views\.guida\s*=", app):
    viste.append("guida")

print(" ".join(viste))
PY
)"

# Legge il DOM scaricato da Chrome: quanti errori JS ha contato index.html
# (data-errori sull'elemento <html>: la sua assenza è rossa quanto un errore
# vero, non un "0" per omissione), se il contenitore che ogni vista riempie
# (<div id="view">) ha scritto qualcosa dentro, ed è rimasto fermo sul
# segnaposto del router (vedi la nota in cima al file). I tag privi di
# chiusura (<input>, <br>, <img>...) non contano per la profondità: Chrome li
# serializza senza tag di chiusura, e senza questa esclusione il lettore
# resterebbe "dentro" #view ben oltre la sua chiusura vera (la vista memoria,
# per dire, ha già un <input> dentro #view).
leggi_dom() {
  python3 - "$1" <<'PY'
import sys
from html.parser import HTMLParser

VUOTI = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "param", "source", "track", "wbr"}
SEGNAPOSTO = ("carico", "loading", "errore", "error")


class Lettore(HTMLParser):
    def __init__(self):
        super().__init__()
        self.errori = None
        self.dentro = False
        self.profondita = 0
        self.testo = ""
        self.figli = []  # (tag, classe) dei figli diretti di #view

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "html" and "data-errori" in d:
            self.errori = d["data-errori"] or "0"
        if not self.dentro and d.get("id") == "view":
            self.dentro = True
            self.profondita = 0
            return
        if self.dentro:
            if self.profondita == 0:
                self.figli.append((tag, d.get("class", "")))
            if tag not in VUOTI:
                self.profondita += 1

    def handle_endtag(self, tag):
        if not self.dentro:
            return
        if self.profondita == 0:
            self.dentro = False
        elif tag not in VUOTI:
            self.profondita -= 1

    def handle_data(self, data):
        if self.dentro:
            self.testo += data


lettore = Lettore()
lettore.feed(open(sys.argv[1], encoding="utf-8", errors="replace").read())

testo = lettore.testo.strip()
fermo = ""
if len(lettore.figli) == 1:
    tag, classe = lettore.figli[0]
    if tag == "div" and "empty" in classe.split() and testo.lower().startswith(SEGNAPOSTO):
        fermo = testo

print(lettore.errori if lettore.errori is not None else "ASSENTE")
print("VUOTO" if not testo else "PIENO")
print(fermo)
PY
}

# Chrome scrive il dump e poi resta in piedi invece di uscire (stesso
# comportamento descritto in tools/scatti.sh): non si aspetta il processo, si
# aspetta che il file smetta di crescere, poi si chiude a forza. Trenta
# secondi di tetto (60 giri da 0.5s), lo stesso di scatti.sh: nove secondi si
# sono visti scadere a freddo, col primo Chrome della sessione ancora a 0 byte
# dopo cinque.
scarica_dom() {  # scarica_dom <vista> <file-di-uscita>
  local profilo; profilo="$(mktemp -d)"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --use-mock-keychain --disable-features=MacAppCodeSignClone \
    --no-first-run --no-default-browser-check --user-data-dir="$profilo" \
    --virtual-time-budget=4000 --dump-dom \
    "http://127.0.0.1:$PORTA/?ui=it#/$1" >"$2" 2>/dev/null &
  local pid=$! giri=0 dim=0 prima=-1
  while [ "$giri" -lt 60 ]; do
    sleep 0.5; giri=$((giri + 1))
    kill -0 "$pid" 2>/dev/null || break
    dim=0
    [ -f "$2" ] && dim=$(wc -c <"$2")
    [ "$dim" -gt 0 ] && [ "$dim" -eq "$prima" ] && break
    prima=$dim
  done
  kill -9 "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  rm -rf "$profilo"
}

echo "==> viste: $VISTE"
ROSSO=0
for VISTA in $VISTE; do
  DOM="$(mktemp)"
  scarica_dom "$VISTA" "$DOM"

  if [ ! -s "$DOM" ]; then
    echo "    $VISTA NO (Chrome non ha scritto il DOM entro il tempo massimo)" >&2
    ROSSO=1
    rm -f "$DOM"
    continue
  fi

  LETTURA="$(leggi_dom "$DOM")"
  ERRORI="$(echo "$LETTURA" | sed -n '1p')"
  CORPO="$(echo "$LETTURA" | sed -n '2p')"
  FERMO="$(echo "$LETTURA" | sed -n '3p')"
  rm -f "$DOM"

  if [ "$ERRORI" = "ASSENTE" ]; then
    echo "    $VISTA NO (il contatore degli errori non c'è nel DOM)" >&2
    ROSSO=1
  elif [ "$ERRORI" -gt 0 ] 2>/dev/null; then
    echo "    $VISTA NO (errori javascript: $ERRORI)" >&2
    ROSSO=1
  elif [ -n "$FERMO" ]; then
    echo "    $VISTA NO (la vista si è fermata su: $FERMO)" >&2
    ROSSO=1
  elif [ "$CORPO" != "PIENO" ]; then
    echo "    $VISTA NO (la vista non ha riempito #view)" >&2
    ROSSO=1
  else
    echo "    $VISTA ok"
  fi
done

if [ "$ROSSO" -ne 0 ]; then
  echo "collaudo a video: rosso" >&2
  exit 1
fi
echo "collaudo a video: verde, tutte le viste hanno riempito il contenuto senza errori"
