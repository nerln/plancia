"""La mappa della memoria: che forma ha il sapere, e dove si sta rovinando.

L'elenco delle memorie c'era già, ed è la cosa meno interessante che si possa
fare con questi dati: dice cosa c'è, non come sta messo. Qui si calcolano le due
cose che un elenco non mostra.

La forma: i `[[link]]` che le memorie si scambiano sono archi veri, e il grafo
che ne esce ha degli assi portanti. `user-profile` ne tiene diciassette: è il
nodo da cui passa tutto, e se una memoria non è legata a niente è quasi sempre
una memoria che non verrà mai riletta.

Lo stato: un archivio che cresce da solo si rovina da solo. Le stesse memorie
scritte due volte in cartelle diverse, i link che puntano a niente, i file
rimasti vuoti. E soprattutto quante memorie il richiamo non potrà mai andare a
prendere, che è la domanda che conta da quando il richiamo esiste.

I nodi sono i fatti, non i file: la stessa memoria in due cartelle è un nodo
solo, e le cartelle diventano una proprietà sua.

I gruppi: un archivio di cento schede con nomi tutti simili è un elenco, non una
mappa. Ogni nodo porta `gruppo` (la chiave stabile del cluster), `gruppo_nome` (il
nome leggibile) e `titolo` (un titolo umano e corto), e la risposta porta l'elenco
dei gruppi con i loro colori e i legami fra uno e l'altro (i ponti). La
disposizione parte già a isole (plancia/disposizione.py): il primo fotogramma è
leggibile senza aspettare nessuna fisica.
"""

import collections
import hashlib
import json
import os
import re
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
            "SELECT name, type, scope, description, links, updated_at, path, project_id, "
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
_CON_ISOLE = set()                      # le impronte in memoria calcolate a isole (con i gruppi)
_IN_CORSO = {}                          # impronta -> Event, un calcolo alla volta per impronta
_PROVVISORIE = {}                       # impronta -> (posizioni, scadenza): il figlio non ha finito in tempo
_VALIDITA_PROVVISORIA = 60.0
_UNO_ALLA_VOLTA = threading.Semaphore(1)
_MEMORIA_MAX = 4
_TEMPO_MAX = 120.0                      # secondi per il processo figlio
# Le sole prove leggono queste due: quante volte si e' calcolato davvero e come.
STATISTICHE = {"calcoli": 0, "figli": 0, "sul_posto": 0, "partenze_calde": 0, "scaduti": 0}


def impronta(nomi: list, archi: list, gruppi: dict = None) -> str:
    """Chi c'e', chi e' legato a chi e (se ci sono) di che gruppo e' ognuno. Cambia solo
    se cambiano le schede, i legami o i gruppi: una descrizione riscritta no."""
    h = hashlib.sha1()
    h.update(("\n".join(sorted(nomi))).encode("utf-8"))
    h.update(b"\0")
    h.update(("\n".join(sorted("%s\t%s" % (a, b) for a, b in archi))).encode("utf-8"))
    if gruppi:
        h.update(b"\0isole2\0")
        h.update(("\n".join(sorted("%s\t%s" % (n, gruppi.get(n, "")) for n in nomi))).encode("utf-8"))
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


def _scrivi_disco(chiave: str, posizioni: dict, isole: bool = False) -> None:
    percorso = _file_cache()
    try:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        tmp = percorso.with_name(percorso.name + ".%d.tmp" % os.getpid())
        tmp.write_text(json.dumps({"impronta": chiave, "posizioni": posizioni, "isole": bool(isole)}),
                       encoding="utf-8")
        os.replace(str(tmp), str(percorso))
    except OSError:
        pass        # la cache e' un'accelerazione: se non si scrive, si ricalcola


def _ricorda(chiave: str, posizioni: dict, isole: bool = False) -> None:
    with _LUCCHETTO:
        _MEMORIA[chiave] = posizioni
        _MEMORIA.move_to_end(chiave)
        if isole:
            _CON_ISOLE.add(chiave)
        while len(_MEMORIA) > _MEMORIA_MAX:
            vecchia, _ = _MEMORIA.popitem(last=False)
            _CON_ISOLE.discard(vecchia)


def _calcola_fuori(nomi: list, archi: list, partenza: dict, gruppi: dict = None) -> tuple:
    """(coordinate, definitive). Le calcola in un processo figlio; sul posto se il
    figlio non riesce a partire. Se il figlio non finisce in tempo (la macchina e'
    sotto un carico enorme) NON si ripiega sul calcolo intero nel server, che
    sarebbe peggio: si danno le posizioni di partenza senza rifinirle
    (`giri=0`, costo lineare), segnate come non definitive: valgono per questa
    risposta e non si scrivono su disco, cosi' la prossima volta si riprova."""
    richiesta = json.dumps({"nomi": nomi, "archi": [list(a) for a in archi],
                            "partenza": partenza, "gruppi": gruppi or {}})
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
            return disposizione_pura.calcola(nomi, archi, partenza, giri=0, gruppi=gruppi), False
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    STATISTICHE["sul_posto"] += 1
    return disposizione_pura.calcola(nomi, archi, partenza, gruppi=gruppi), True


def posizioni(nomi: list, archi: list, gruppi: dict = None) -> dict:
    """{nome: [x, y]} per questi nodi e questi archi, dalla cache se l'impronta
    e' la stessa, altrimenti calcolata (una volta sola anche se le richieste sono
    dieci insieme) a partire dalle posizioni della disposizione precedente.
    Con `gruppi` ({nome: chiave}) la disposizione e' a isole."""
    isole = bool(gruppi) and len(set(gruppi.values())) >= 2
    chiave = impronta(nomi, archi, gruppi if isole else None)
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
                _ricorda(chiave, disco["posizioni"], isole)
                return disco["posizioni"]
            # La partenza: l'ultima disposizione nota (memoria o disco), qualunque
            # impronta avesse. Le schede che c'erano restano dove stavano. A isole
            # si parte solo da una disposizione a isole: una nuvola senza gruppi non
            # dice dove stanno i gruppi.
            partenza = {}
            with _LUCCHETTO:
                for chiave_prec in reversed(_MEMORIA):
                    if not isole or chiave_prec in _CON_ISOLE:
                        partenza = dict(_MEMORIA[chiave_prec])
                        break
            if not partenza and (not isole or disco.get("isole")):
                partenza = disco.get("posizioni", {})
            if partenza:
                STATISTICHE["partenze_calde"] += 1
            with _UNO_ALLA_VOLTA:
                STATISTICHE["calcoli"] += 1
                risultato, definitive = _calcola_fuori(nomi, archi, partenza, gruppi if isole else None)
            if definitive:
                _ricorda(chiave, risultato, isole)
                _scrivi_disco(chiave, risultato, isole)
            else:
                with _LUCCHETTO:
                    _PROVVISORIE.clear()
                    _PROVVISORIE[chiave] = (risultato, time.time() + _VALIDITA_PROVVISORIA)
            return risultato
        finally:
            with _LUCCHETTO:
                _IN_CORSO.pop(chiave, None)
            attesa.set()


def disposizione(nodi: list, archi: list, gruppi: dict = None) -> None:
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
    pos = posizioni(nomi, coppie, gruppi)
    for nodo in nodi:
        xy = pos.get(nodo["nome"], [0.5, 0.5])
        nodo["x"], nodo["y"] = xy[0], xy[1]


# ---------------------------------------------------------------------------
# I gruppi e i titoli
# ---------------------------------------------------------------------------
#
# Il gruppo di una memoria, in quest'ordine:
#
# 1. il progetto Plancia a cui e' collegata esplicitamente (`project_id`), salvo che
#    sia il progetto che la sincronizzazione crea da sola per ogni memoria di tipo
#    `project` (chiave uguale al nome della scheda): quello e' un artefatto, non un
#    raggruppamento;
# 2. se e' una memoria globale dell'utente (chi sei, preferenze): il gruppo del suo
#    tipo, qualunque cartella l'abbia scritta;
# 3. il progetto Plancia che possiede la cartella da cui viene il file (il percorso
#    del progetto, scritto come lo scrive Claude Code: ogni carattere non
#    alfanumerico diventa un trattino);
# 4. la cartella stessa, se ci sono almeno due schede; una cartella con una scheda
#    sola non fa un gruppo e cade nel gruppo del suo tipo.
#
# Un progetto nascosto non da' il nome a un gruppo.

TAVOLOZZA = ["#e07b2a", "#3b6fd0", "#3fa066", "#a35cc2", "#d4546a", "#20a39e",
             "#c9a227", "#6a6bd6", "#a0714a", "#42b0d5", "#8fb339", "#cc5fa8"]
# Chi sei e preferenze viaggiano da una cartella all'altra: il loro gruppo e' il tipo.
GLOBALI = ("user", "feedback")
NOMI_TIPO = {"user": "Chi sei", "feedback": "Preferenze", "reference": "Riferimenti",
             "project": "Altri progetti"}
CARTELLA_MINIMA = 2
TITOLO_MAX = 70


def colore_gruppo(chiave: str, occupati=()) -> str:
    """Il colore di un gruppo: dalla sua chiave, sempre lo stesso. Se in una stessa mappa
    due gruppi cadono sullo stesso, il secondo (in ordine di chiave) prende il primo
    libero: restano tutti distinti finche' i gruppi sono meno dei colori."""
    n = len(TAVOLOZZA)
    i = int.from_bytes(hashlib.sha1(chiave.encode("utf-8")).digest()[:4], "big") % n
    for passo in range(n):
        c = TAVOLOZZA[(i + passo) % n]
        if c not in occupati:
            return c
    return TAVOLOZZA[i]


def _codifica(percorso: str) -> str:
    """Come Claude Code scrive una cartella di progetto nel nome della cartella delle sue memorie."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.normpath(percorso))


def _umano(testo: str) -> str:
    t = re.sub(r"[-_]+", " ", testo or "").strip()
    return (t[:1].upper() + t[1:]) if t else ""


# Pezzi di percorso che non dicono niente su che progetto sia: "dev-plancia" e' "Plancia".
_GENERICI = {"users", "user", "home", "dev", "code", "projects", "project", "src", "github",
             "repos", "repo", "documents", "desktop", "work", "workspace"}


def _nome_cartella(scope: str) -> str:
    pezzi = [p for p in richiamo._dove(scope).split("-") if p]
    while len(pezzi) > 1 and pezzi[0].lower() in _GENERICI:
        pezzi.pop(0)
    return _umano(" ".join(pezzi)) or "Altrove"


def _taglia(testo: str, massimo: int) -> str:
    if len(testo) <= massimo:
        return testo
    taglio = testo[:massimo - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (taglio or testo[:massimo - 1]) + "…"


def titolo_da_descrizione(testo: str, massimo: int = TITOLO_MAX) -> str:
    """La prima frase della descrizione, accorciata: un titolo, non un riassunto."""
    t = " ".join((testo or "").split())
    if not t:
        return ""
    t = re.split(r"(?<=[.!?])\s|;|\s[\u2014\u2013]\s|\s-\s", t, maxsplit=1)[0].strip().rstrip(".;:,")
    return _taglia(t[:1].upper() + t[1:], massimo)


_INDICI = {}        # percorso di MEMORY.md -> (mtime, dimensione, {file: titolo})
_LEGAME_INDICE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _indice(cartella: str) -> dict:
    """I titoli scritti nell'indice MEMORY.md di una cartella di memorie: il testo di
    ogni collegamento, per nome di file. Si rilegge solo se il file e' cambiato."""
    percorso = os.path.join(cartella, "MEMORY.md")
    try:
        st = os.stat(percorso)
    except OSError:
        _INDICI.pop(percorso, None)
        return {}
    firma = (st.st_mtime_ns, st.st_size)
    trovato = _INDICI.get(percorso)
    if trovato and trovato[0] == firma:
        return trovato[1]
    titoli = {}
    try:
        with open(percorso, encoding="utf-8", errors="replace") as f:
            for riga in f:
                for testo, bersaglio in _LEGAME_INDICE.findall(riga):
                    nome_file = os.path.basename(bersaglio.split("#", 1)[0])
                    testo = " ".join(testo.split())
                    if nome_file.endswith(".md") and testo and nome_file not in titoli:
                        titoli[nome_file] = testo
    except OSError:
        return {}
    if len(_INDICI) > 400:
        _INDICI.clear()
    _INDICI[percorso] = (firma, titoli)
    return titoli


def titolo_di(percorso: str, descrizione: str, nome: str) -> str:
    """Il titolo di una memoria: il testo del suo collegamento nell'indice MEMORY.md
    della stessa cartella; se manca, la descrizione accorciata a una frase; se manca
    anche quella, il nome reso leggibile. Mai la sigla finche' c'e' altro."""
    if percorso:
        titolo = _indice(os.path.dirname(percorso)).get(os.path.basename(percorso))
        if titolo:
            return _taglia(titolo, TITOLO_MAX + 20)
    return titolo_da_descrizione(descrizione) or _umano(nome) or nome


_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


def umanizza_schede(conn, trovate: list) -> list:
    """Le schede della ricerca con la memoria scritta come la scrive la Mappa: `title` e' il titolo
    umano (non la sigla del file), `nome` e' la sigla (serve per aprirla), e nelle anteprime i
    [[collegamenti]] diventano il titolo della memoria a cui puntano. Le altre schede non cambiano."""
    if not trovate:
        return trovate
    marche = "\u00ab\u00bb"
    nomi = set()
    for h in trovate:
        if h.get("kind") == "memoria":
            nomi.add(h.get("title") or "")
        for m in _WIKILINK.findall(h.get("snip") or ""):
            nomi.add(m.strip(marche).replace("\u00ab", "").replace("\u00bb", ""))
    nomi.discard("")
    titoli = {}
    if nomi:
        try:
            righe = conn.execute(
                "SELECT name, description, path, updated_at FROM knowledge WHERE name IN (%s)"
                % ",".join("?" * len(nomi)), list(nomi)).fetchall()
        except sqlite3.Error:
            righe = []
        for nome, r in _ultime([{"name": x["name"], "description": x["description"], "path": x["path"],
                                 "updated_at": x["updated_at"]} for x in righe]).items():
            titoli[nome] = titolo_di(r["path"] or "", r["description"] or "", nome)

    def titolo(nome: str) -> str:
        return titoli.get(nome) or _umano(nome) or nome

    def sostituisci(m):
        dentro = m.group(1)
        evidenziato = "\u00ab" in dentro
        nome = dentro.replace("\u00ab", "").replace("\u00bb", "").strip()
        t = titolo(nome)
        return "\u00ab" + t + "\u00bb" if evidenziato else t

    fuori = []
    for h in trovate:
        h = dict(h)
        if h.get("kind") == "memoria":
            h["nome"] = h.get("title") or ""
            h["title"] = titolo(h["nome"])
        if h.get("snip"):
            h["snip"] = _WIKILINK.sub(sostituisci, h["snip"])
        fuori.append(h)
    return fuori


def _contesto(conn) -> dict:
    """I progetti Plancia (per id) e le loro cartelle, scritte come Claude Code le scrive."""
    progetti = {}
    try:
        for r in conn.execute("SELECT id, key, name, hidden, auto FROM projects"):
            progetti[r["id"]] = {"key": r["key"], "name": r["name"],
                                 "nascosto": bool(r["hidden"]), "auto": bool(r["auto"])}
    except sqlite3.Error:
        try:
            for r in conn.execute("SELECT id, key, name FROM projects"):
                progetti[r["id"]] = {"key": r["key"], "name": r["name"], "nascosto": False, "auto": False}
        except sqlite3.Error:
            pass
    cartelle = {}
    try:
        for r in conn.execute("SELECT project_id, value FROM project_links WHERE kind='path' ORDER BY id"):
            if r["value"]:
                cartelle.setdefault(_codifica(r["value"]), r["project_id"])
    except sqlite3.Error:
        pass
    return {"progetti": progetti, "cartelle": cartelle}


def _gruppo_tipo(tipo: str) -> tuple:
    t = tipo if tipo in NOMI_TIPO else "altro"
    return ("tipo:" + t, NOMI_TIPO.get(t, "Altro"), "tipo")


def _gruppo_provvisorio(nome: str, tipo: str, scope: str, project_id, ctx: dict) -> tuple:
    p = ctx["progetti"].get(project_id) if project_id else None
    if p and not p["nascosto"] and not (p["auto"] and p["key"] == nome):
        return (p["key"], p["name"], "progetto")
    if tipo in GLOBALI:
        return _gruppo_tipo(tipo)
    p = ctx["progetti"].get(ctx["cartelle"].get(scope or ""))
    if p and not p["nascosto"]:
        return (p["key"], p["name"], "progetto")
    return ("cartella:" + (scope or ""), _nome_cartella(scope or ""), "cartella")


def _ultime(righe: list) -> dict:
    """Una riga per nome: la piu' aggiornata (a parita', la prima), come i nodi."""
    scelte = {}
    for r in righe:
        vecchia = scelte.get(r["name"])
        if vecchia is None or (r["updated_at"] or "") > (vecchia["updated_at"] or ""):
            scelte[r["name"]] = r
    return scelte


def _assegna(conn, scelte: dict) -> dict:
    """{nome: {"gruppo", "gruppo_nome", "titolo"}} per le schede scelte."""
    ctx = _contesto(conn)
    prov = {nome: _gruppo_provvisorio(nome, r["type"] or "", r["scope"] or "", r["project_id"], ctx)
            for nome, r in scelte.items()}
    in_cartella = collections.Counter(g[0] for g in prov.values() if g[2] == "cartella")
    fuori = {}
    for nome, r in scelte.items():
        chiave, nome_gruppo, genere = prov[nome]
        if genere == "cartella" and in_cartella[chiave] < CARTELLA_MINIMA:
            chiave, nome_gruppo, genere = _gruppo_tipo(r["type"] or "")
        fuori[nome] = {"gruppo": chiave, "gruppo_nome": nome_gruppo,
                       "titolo": titolo_di(r["path"] or "", r["description"] or "", nome)}
    return fuori


def _elenco_gruppi(nodi: list, archi: list) -> list:
    """I gruppi presenti: chiave, nome, colore stabile, quante memorie, i ponti verso
    gli altri gruppi (quanti legami li uniscono) e il centro dove stanno sulla mappa."""
    per = collections.OrderedDict()
    for n in nodi:
        g = per.setdefault(n["gruppo"], {"chiave": n["gruppo"], "nome": n["gruppo_nome"], "memorie": 0,
                                         "xs": [], "ys": []})
        g["memorie"] += 1
        g["xs"].append(n["x"])
        g["ys"].append(n["y"])
    di = {n["nome"]: n["gruppo"] for n in nodi}
    ponti = collections.defaultdict(collections.Counter)
    for a in archi:
        ga, gb = di.get(a["da"]), di.get(a["a"])
        if ga and gb and ga != gb:
            ponti[ga][gb] += 1
            ponti[gb][ga] += 1
    occupati = set()
    colori = {}
    for chiave in sorted(per):
        colori[chiave] = colore_gruppo(chiave, occupati)
        occupati.add(colori[chiave])
    risultato = []
    for chiave, g in per.items():
        risultato.append({
            "chiave": chiave, "nome": g["nome"], "colore": colori[chiave], "memorie": g["memorie"],
            "legami": [{"gruppo": altro, "n": n} for altro, n in
                       sorted(ponti[chiave].items(), key=lambda t: (-t[1], t[0]))],
            "x": round(sum(g["xs"]) / len(g["xs"]), 4), "y": round(sum(g["ys"]) / len(g["ys"]), 4),
        })
    risultato.sort(key=lambda g: (-g["memorie"], g["nome"].lower(), g["chiave"]))
    return risultato


def schede(conn) -> list:
    """L'elenco delle schede di `/api/knowledge`: una per riga dell'archivio, con in piu'
    gruppo, gruppo_nome e titolo, gli stessi dei nodi della mappa."""
    righe = _righe(conn)
    gruppi = _assegna(conn, _ultime(righe))
    risultato = []
    for r in conn.execute(
            "SELECT k.id, k.name, k.description, k.type, k.updated_at, k.links, "
            "p.name AS progetto, p.key AS project_key FROM knowledge k "
            "LEFT JOIN projects p ON p.id=k.project_id ORDER BY k.updated_at DESC").fetchall():
        d = dict(r)
        d.update(gruppi.get(d["name"]) or {"gruppo": "tipo:altro", "gruppo_nome": "Altro",
                                           "titolo": _umano(d["name"] or "")})
        risultato.append(d)
    return risultato


def mappa(conn) -> dict:
    """Nodi, archi e diagnosi, già pronti da disegnare."""
    righe = _righe(conn)
    if not righe:
        return {"nodi": [], "archi": [], "diagnosi": {
            "totale": 0, "richiamabili": 0, "doppie": [], "orfane": [],
            "rotti": [], "da_scrivere": [], "vuote": [], "cartelle": []}, "gruppi": []}

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
    assegnati = _assegna(conn, _ultime(righe))
    for n in ordinati:
        n.update(assegnati[n["nome"]])
    disposizione(ordinati, lista_archi, {n["nome"]: n["gruppo"] for n in ordinati})

    return {
        "nodi": ordinati,
        "archi": lista_archi,
        "gruppi": _elenco_gruppi(ordinati, lista_archi),
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
