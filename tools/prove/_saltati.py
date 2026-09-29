"""Materiale di supporto per le prove che su Windows non si fanno: non e' una prova.

Comincia con `_`, quindi `tools/prova.py` non lo scopre. Un modulo lo importa cosi':

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _saltati

Il guardiano (`tools/prove/guardiano.py`) e i compartimenti
(`tools/prove/compartimenti-plancia.py`) ragionano su percorsi POSIX e su Windows
sono spenti (`plancia/piattaforma.compartimenti_supportati`). Le loro prove non si
lanciano li': ognuna si segna come passata con il motivo scritto accanto ("saltato:
non supportato su Windows"), CONTROLLO PER CONTROLLO, cosi' il conteggio delle prove
resta identico su ogni sistema (il README dichiara un numero solo, e
`tools/prova.py` lo confronta con quello vero).

Il conteggio non si puo' dedurre da Windows: i controlli si scrivono uno per uno
dentro funzioni lunghe, con dei cicli e dei nomi composti a runtime. Lo si misura su
macOS e Linux, dove le prove girano davvero, e sta in `saltati-windows.json`
(`{modulo: totale}`). Su macOS e Linux ogni modulo, in fondo, confronta i controlli
eseguiti con quel numero, e cade se non tornano: chi aggiunge o toglie un controllo
deve aggiornare il file, e l'errore dice come:

    PLANCIA_RIGENERA_SALTATI=1 python3 tools/prova.py

riscrive `saltati-windows.json` con i numeri veri (e poi si rilancia, senza la
variabile, per vedere che tornano).

Il modulo che ha una parte che su Windows si fa davvero (i compartimenti: la parte
"senza compartimenti" gira anche li') segna come saltati solo i controlli che restano
dopo quella parte: `salta_il_resto` ne emette esattamente quanti servono a fare il
totale, qualunque sia il numero di quelli fatti.
"""

import json
import os
from pathlib import Path

#: Si gira su Windows davvero.
WIN = os.name == "nt"

MOTIVO = "saltato: non supportato su Windows"

ELENCO = Path(__file__).resolve().parent / "saltati-windows.json"


def _leggi() -> dict:
    try:
        letto = json.loads(ELENCO.read_text("utf-8"))
        return letto if isinstance(letto, dict) else {}
    except (OSError, ValueError):
        return {}


class Contatore:
    """Avvolge `prova`: passa tutto avanti e si ricorda quanti controlli sono stati
    scritti. Un modulo lo mette al posto di `prova` nella sua `esegui`."""

    def __init__(self, prova):
        self.prova = prova
        self.fatti = 0

    def __call__(self, nome, condizione, dettaglio=""):
        self.fatti += 1
        return self.prova(nome, condizione, dettaglio)


def salta_il_resto(modulo, contatore) -> None:
    """Su Windows: segna come saltati i controlli del `modulo` che restano, tanti
    quanti ne servono a fare il totale misurato. Da chiamare nel punto in cui la parte
    che si fa anche su Windows e' finita (o all'inizio, se non ce n'e')."""
    totale = _leggi().get(modulo)
    if not isinstance(totale, int):
        # senza il numero misurato non si puo' tenere il conteggio: un NO chiaro, non un
        # silenzio (il file sta nel repo, quindi e' un guasto del repo)
        contatore.prova("%s: il numero dei controlli saltati su Windows e' in saltati-windows.json"
                        % modulo, False, "manca la voce %r in %s" % (modulo, ELENCO.name))
        return
    for i in range(contatore.fatti, totale):
        contatore.prova("%s: controllo %d di %d" % (modulo, i + 1, totale), True, MOTIVO)
    contatore.fatti = max(contatore.fatti, totale)


def chiudi(modulo, contatore, prova) -> None:
    """In fondo alla `esegui` di un modulo. Su macOS e Linux confronta i controlli
    eseguiti con il numero misurato (o, con `PLANCIA_RIGENERA_SALTATI=1`, lo riscrive);
    su Windows non c'e' niente da confrontare. In tutti e due i casi e' un controllo
    solo, cosi' il conteggio delle prove e' lo stesso."""
    nome = "%s: i controlli saltati su Windows sono tanti quanti quelli eseguiti altrove" % modulo
    if WIN:
        prova(nome, True, MOTIVO.replace("non supportato su Windows",
                                        "il numero si verifica su macOS e Linux"))
        return
    # il controllo di verifica non fa parte del totale (e' quello che lo verifica)
    misurati = contatore.fatti
    if os.environ.get("PLANCIA_RIGENERA_SALTATI") == "1":
        letto = _leggi()
        letto[modulo] = misurati
        ELENCO.write_text(json.dumps(letto, indent=2, sort_keys=True) + "\n", "utf-8")
        prova(nome, True, "riscritto: %d" % misurati)
        return
    voluto = _leggi().get(modulo)
    prova(nome, voluto == misurati,
          "eseguiti %d, in %s %r: rilancia con PLANCIA_RIGENERA_SALTATI=1 python3 tools/prova.py"
          % (misurati, ELENCO.name, voluto))
