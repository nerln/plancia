"""La mappa della memoria: che forma ha il sapere, e dove si sta rovinando.

L'elenco delle memorie c'era già, ed è la cosa meno interessante che si possa
fare con questi dati: dice cosa c'è, non come sta messo. Qui si calcolano le due
cose che un elenco non mostra.

La forma: i `[[link]]` che le memorie si scambiano sono archi veri, e il grafo
che ne esce ha degli assi portanti. `user-eugenio` ne tiene diciassette: è il
nodo da cui passa tutto, e se una memoria non è legata a niente è quasi sempre
una memoria che non verrà mai riletta.

Lo stato: un archivio che cresce da solo si rovina da solo. Le stesse memorie
scritte due volte in cartelle diverse, i link che puntano a niente, i file
rimasti vuoti. E soprattutto quante memorie il richiamo non potrà mai andare a
prendere, che è la domanda che conta da quando il richiamo esiste.

I nodi sono i fatti, non i file: la stessa memoria in due cartelle è un nodo
solo, e le cartelle diventano una proprietà sua.
"""

import collections
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config, piattaforma, richiamo
from . import disposizione as disposizione_pura

# «Quasi vuote» vuol dire esattamente quello che il richiamo scarta: la stessa
# soglia, non una simile. Se le due regole divergono, la vista dice che una
# memoria è a posto mentre il richiamo la sta ignorando, ed è il modo più
# rapido di far perdere fiducia a tutt'e due.
CORPO_MINIMO = richiamo.SOSTANZA_MINIMA


def _righe(conn) -> list:
    try:
        return list(conn.execute(
            "SELECT name, type, scope, description, links, updated_at, path, "
            "LENGTH(COALESCE(description,'')) + LENGTH(COALESCE(body,'')) AS peso "
            "FROM knowledge ORDER BY name"))
    except sqlite3.Error:
        return []


# ---------------------------------------------------------------------------
# La disposizione: calcolata una volta, fuori dal server, e ricordata
# ---------------------------------------------------------------------------
#
# Le coordinate dipendono solo da CHI c'e' e da CHI e' legato a chi: nomi e archi.
# Una descrizione riscritta, una scheda toccata, non le spostano. Quindi l'impronta
# (`impronta`) e' quella, e finche' non cambia la disposizione resta quella che si
# e' calcolata: dieci aperture della mappa costano un calcolo, non dieci.
#
# Il calcolo (plancia/disposizione.py) e' pura CPU in Python: nello stesso processo
# del server toglierebbe il fiato alle altre richieste (il GIL le mette in fila
# dietro di lui). Per questo gira in un processo figlio, a priorita' bassa; chi
# chiede la mappa aspetta la risposta, ma il resto del server non se ne accorge.
# Se il figlio non parte, si calcola sul posto: piu' lento, non sbagliato.

_LUCCHETTO = threading.Lock()
_MEMORIA = collections.OrderedDict()    # impronta -> {nome: [x, y]}, le ultime
_IN_CORSO = {}                          # impronta -> Event, un calcolo alla volta per impronta
_PROVVISORIE = {}                       # impronta -> (posizioni, scadenza): il figlio non ha finito in tempo
_VALIDITA_PROVVISORIA = 60.0
_UNO_ALLA_VOLTA = threading.Semaphore(1)
_MEMORIA_MAX = 4
_TEMPO_MAX = 120.0                      # secondi per il processo figlio
# Le sole prove leggono queste due: quante volte si e' calcolato davvero e come.
STATISTICHE = {"calcoli": 0, "figli": 0, "sul_posto": 0, "partenze_calde": 0, "scaduti": 0}


def impronta(nomi: list, archi: list) -> str:
    """Chi c'e' e chi e' legato a chi. Cambia solo se cambiano le schede o i legami."""
    h = hashlib.sha1()
    h.update(("\n".join(sorted(nomi))).encode("utf-8"))
    h.update(b"\0")
    h.update(("\n".join(sorted("%s\t%s" % (a, b) for a, b in archi))).encode("utf-8"))
    return h.hexdigest()


def _file_cache() -> Path:
    return config.DATA_DIR / "cache" / "mappa-disposizione.json"


def _leggi_disco() -> dict:
    try:
        dati = json.loads(_file_cache().read_text(encoding="utf-8"))
        if isinstance(dati, dict) and isinstance(dati.get("posizioni"), dict):
            return dati
    except (OSError, ValueError):
        pass
    return {}


def _scrivi_disco(chiave: str, posizioni: dict) -> None:
    percorso = _file_cache()
    try:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        tmp = percorso.with_name(percorso.name + ".%d.tmp" % os.getpid())
        tmp.write_text(json.dumps({"impronta": chiave, "posizioni": posizioni}),
                       encoding="utf-8")
        os.replace(str(tmp), str(percorso))
    except OSError:
        pass        # la cache e' un'accelerazione: se non si scrive, si ricalcola


def _ricorda(chiave: str, posizioni: dict) -> None:
    with _LUCCHETTO:
        _MEMORIA[chiave] = posizioni
        _MEMORIA.move_to_end(chiave)
        while len(_MEMORIA) > _MEMORIA_MAX:
            _MEMORIA.popitem(last=False)


def _calcola_fuori(nomi: list, archi: list, partenza: dict) -> tuple:
    """(coordinate, definitive). Le calcola in un processo figlio; sul posto se il
    figlio non riesce a partire. Se il figlio non finisce in tempo (la macchina e'
    sotto un carico enorme) NON si ripiega sul calcolo intero nel server, che
    sarebbe peggio: si danno le posizioni di partenza senza rifinirle
    (`giri=0`, costo lineare), segnate come non definitive: valgono per questa
    risposta e non si scrivono su disco, cosi' la prossima volta si riprova."""
    richiesta = json.dumps({"nomi": nomi, "archi": [list(a) for a in archi],
                            "partenza": partenza})
    if sys.executable:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(config.ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        try:
            fatto = subprocess.run(
                [sys.executable, "-m", "plancia.disposizione"], input=richiesta,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                timeout=_TEMPO_MAX, cwd=str(config.ROOT), env=env,
                **piattaforma.opzioni_figlio(), **piattaforma.opzioni_utf8())
            if fatto.returncode == 0:
                risultato = json.loads(fatto.stdout)
                if isinstance(risultato, dict) and set(risultato) == set(nomi):
                    STATISTICHE["figli"] += 1
                    return risultato, True
        except subprocess.TimeoutExpired:
            STATISTICHE["scaduti"] += 1
            return disposizione_pura.calcola(nomi, archi, partenza, giri=0), False
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    STATISTICHE["sul_posto"] += 1
    return disposizione_pura.calcola(nomi, archi, partenza), True


def posizioni(nomi: list, archi: list) -> dict:
    """{nome: [x, y]} per questi nodi e questi archi, dalla cache se l'impronta
    e' la stessa, altrimenti calcolata (una volta sola anche se le richieste sono
    dieci insieme) a partire dalle posizioni della disposizione precedente."""
    chiave = impronta(nomi, archi)
    while True:
        with _LUCCHETTO:
            trovata = _MEMORIA.get(chiave)
            if trovata is not None:
                _MEMORIA.move_to_end(chiave)
                return trovata
            provvisoria = _PROVVISORIE.get(chiave)
            if provvisoria is not None and provvisoria[1] > time.time():
                return provvisoria[0]
            attesa = _IN_CORSO.get(chiave)
            if attesa is None:
                attesa = _IN_CORSO[chiave] = threading.Event()
                mio = True
            else:
                mio = False
        if not mio:
            attesa.wait(_TEMPO_MAX * 2)
            continue    # o e' in memoria adesso, o chi calcolava e' caduto e tocca a noi
        try:
            # Anche su disco, per non rifare da zero a ogni riavvio del server.
            disco = _leggi_disco()
            if disco.get("impronta") == chiave and set(disco["posizioni"]) == set(nomi):
                _ricorda(chiave, disco["posizioni"])
                return disco["posizioni"]
            # La partenza: l'ultima disposizione nota (memoria o disco), qualunque
            # impronta avesse. Le schede che c'erano restano dove stavano.
            partenza = {}
            with _LUCCHETTO:
                if _MEMORIA:
                    partenza = dict(next(reversed(_MEMORIA.values())))
            if not partenza:
                partenza = disco.get("posizioni", {})
            if partenza:
                STATISTICHE["partenze_calde"] += 1
            with _UNO_ALLA_VOLTA:
                STATISTICHE["calcoli"] += 1
                risultato, definitive = _calcola_fuori(nomi, archi, partenza)
            if definitive:
                _ricorda(chiave, risultato)
                _scrivi_disco(chiave, risultato)
            else:
                with _LUCCHETTO:
                    _PROVVISORIE.clear()
                    _PROVVISORIE[chiave] = (risultato, time.time() + _VALIDITA_PROVVISORIA)
            return risultato
        finally:
            with _LUCCHETTO:
                _IN_CORSO.pop(chiave, None)
            attesa.set()


def disposizione(nodi: list, archi: list) -> None:
    """Mette le coordinate dentro i nodi, in un quadrato da 0 a 1.

    Stabile a parita' di dati, non stabile in assoluto: un legame nuovo verso un
    nodo molto collegato sposta anche i vicini (poco: si riparte dalle posizioni di
    prima), e la mappa di domani non sara' sovrapponibile a quella di oggi. Vale
    per riaprirla dieci volte in un pomeriggio, non per impararla a memoria una
    volta per sempre.
    """
    if not nodi:
        return
    nomi = [x["nome"] for x in nodi]
    coppie = [(a["da"], a["a"]) for a in archi]
    pos = posizioni(nomi, coppie)
    for nodo in nodi:
        xy = pos.get(nodo["nome"], [0.5, 0.5])
        nodo["x"], nodo["y"] = xy[0], xy[1]


def mappa(conn) -> dict:
    """Nodi, archi e diagnosi, già pronti da disegnare."""
    righe = _righe(conn)
    if not righe:
        return {"nodi": [], "archi": [], "diagnosi": {
            "totale": 0, "richiamabili": 0, "doppie": [], "orfane": [],
            "rotti": [], "da_scrivere": [], "vuote": [], "cartelle": []}}

    # Un nodo per nome. Delle copie si tiene la più aggiornata e si ricorda in
    # quante cartelle vive, che è il segnale del doppione.
    nodi = {}
    cartelle = collections.defaultdict(set)
    veri = collections.defaultdict(set)
    for r in righe:
        nome = r["name"]
        cartelle[nome].add(r["scope"] or "")
        # Il file vero dietro il percorso. Deduplicare con un link è la sua
        # regola, e dopo averlo fatto le due copie sono lo stesso file: se la
        # diagnosi continuasse a chiamarle doppie, chiederebbe di riparare una
        # cosa già riparata, che è il modo più rapido di farsi ignorare.
        try:
            veri[nome].add(os.path.realpath(r["path"]))
        except OSError:
            veri[nome].add(r["path"])
        vecchio = nodi.get(nome)
        if vecchio is None or (r["updated_at"] or "") > (vecchio["aggiornata"] or ""):
            nodi[nome] = {
                "nome": nome,
                "tipo": r["type"] or "altro",
                "descrizione": (r["description"] or "").strip(),
                "aggiornata": r["updated_at"] or "",
                "peso": r["peso"] or 0,
                "path": r["path"] or "",
                "grado": 0,
            }

    archi, rotti = set(), []
    for r in righe:
        try:
            usciti = json.loads(r["links"] or "[]")
        except (TypeError, ValueError):
            usciti = []
        for verso in usciti:
            if verso == r["name"]:
                continue
            if verso in nodi:
                archi.add(tuple(sorted((r["name"], verso))))
            else:
                rotti.append({"da": r["name"], "verso": verso})

    for a, b in archi:
        nodi[a]["grado"] += 1
        nodi[b]["grado"] += 1

    for nome, n in nodi.items():
        n["cartelle"] = sorted(c for c in cartelle[nome] if c)
        n["dove"] = [richiamo._dove(c) for c in n["cartelle"]]
        # La domanda che conta: il richiamo potrà mai andare a prenderla? Le
        # memorie di progetto no, ed è giusto così, ma va detto invece che
        # lasciato intuire. E nemmeno quelle troppo magre, che il richiamo
        # scarta: contarle qui vorrebbe dire promettere una cosa che non
        # succede, e la mappa perderebbe l'unica affermazione che fa.
        n["richiamabile"] = (n["tipo"] in richiamo.TIPI_TRASVERSALI
                             and n["peso"] >= richiamo.SOSTANZA_MINIMA)

    # Un legame verso una memoria che non c'è non è per forza un errore. Se
    # punta a un progetto che esiste davvero, è un promemoria: quella memoria
    # vale la pena scriverla, e chiamarla «rotta» trasformerebbe un invito in
    # un rimprovero. Rotto è solo ciò che non corrisponde a niente.
    progetti = set()
    try:
        for r in conn.execute("SELECT key, name FROM projects"):
            progetti.add((r["key"] or "").lower())
            progetti.add((r["name"] or "").lower())
    except sqlite3.Error:
        pass
    da_scrivere, davvero_rotti = [], []
    for x in rotti:
        (da_scrivere if x["verso"].lower() in progetti else davvero_rotti).append(x)
    rotti = davvero_rotti

    ordinati = sorted(nodi.values(), key=lambda n: (-n["grado"], n["nome"]))
    doppie = [{"nome": n["nome"], "cartelle": n["dove"]}
              for n in ordinati if len(veri[n["nome"]]) > 1]
    orfane = [n["nome"] for n in ordinati if n["grado"] == 0]
    vuote = [n["nome"] for n in ordinati if n["peso"] < CORPO_MINIMO]

    conteggio = collections.Counter()
    for n in ordinati:
        for d in n["dove"]:
            conteggio[d] += 1

    lista_archi = [{"da": a, "a": b} for a, b in sorted(archi)]
    disposizione(ordinati, lista_archi)

    return {
        "nodi": ordinati,
        "archi": lista_archi,
        "diagnosi": {
            "totale": len(ordinati),
            "richiamabili": sum(1 for n in ordinati if n["richiamabile"]),
            "doppie": doppie,
            "orfane": orfane,
            "rotti": rotti,
            "da_scrivere": sorted({x["verso"] for x in da_scrivere}),
            "vuote": vuote,
            "cartelle": [{"nome": k, "quante": v} for k, v in conteggio.most_common()],
        },
    }


def prova(conn, frase: str) -> dict:
    """Cosa direbbe il richiamo su questa frase, e cosa ha scartato.

    È il modo di guardare il richiamo da fuori mentre lavora. Senza, l'unico
    modo di accorgersi che una memoria è scritta male è notare che Claude non se
    ne ricorda mai, e non è una cosa che si nota.
    """
    termini = richiamo.parole(frase)
    if len(termini) < 2:
        return {"termini": termini, "corta": True, "presi": [], "scartati": []}
    # Senza azzerare anche lo stacco si vedrebbero solo i vincitori, e la
    # domanda qui è proprio quali memorie erano in gara e hanno perso.
    tutti = richiamo.cerca(conn, frase, soglia=0.0, limite=8, stacco=0.0)
    presi = richiamo.cerca(conn, frase)
    nomi = {p["nome"] for p in presi}
    magro = lambda x: {k: x[k] for k in ("nome", "tipo", "descrizione", "punteggio")}  # noqa: E731
    return {
        "termini": termini,
        "corta": False,
        "soglia": richiamo.SOGLIA,
        "presi": [magro(x) for x in presi],
        "scartati": [magro(x) for x in tutti if x["nome"] not in nomi],
    }
