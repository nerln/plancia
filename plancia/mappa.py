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
import math
import os
import sqlite3

from . import richiamo

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


def _seme(nome: str) -> float:
    """Un numero fisso ricavato dal nome. Serve a partire sempre dallo stesso
    punto: una mappa che si ridispone a ogni apertura non si impara mai."""
    h = hashlib.sha1(nome.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / 0xFFFFFFFF


def disposizione(nodi: list, archi: list, giri: int = 260) -> None:
    """Mette le coordinate dentro i nodi, in un quadrato da 0 a 1.

    Molle sugli archi e repulsione fra tutti, il metodo di sempre. Quello che
    conta qui non è l'eleganza del layout ma che sia lo stesso ogni volta: le
    posizioni di partenza escono dal nome, non dal caso, e non c'è animazione.
    Si calcola qui e non nel browser perché il browser lo rifarebbe a ogni
    apertura, leggermente diverso.

    Stabile a parità di dati, non stabile in assoluto: un legame nuovo verso un
    nodo molto collegato sposta anche i vicini, e la mappa di domani non sarà
    sovrapponibile a quella di oggi. Vale per riaprirla dieci volte in un
    pomeriggio, non per impararla a memoria una volta per sempre.
    """
    if not nodi:
        return
    n = len(nodi)
    indice = {x["nome"]: i for i, x in enumerate(nodi)}
    # Partenza su una spirale: i nodi non nascono mai sovrapposti, e chi ha più
    # legami parte più al centro, dove poi resterà.
    px, py = [], []
    for i, nodo in enumerate(nodi):
        ang = 2.399963 * i + _seme(nodo["nome"]) * 0.6
        raggio = 0.08 + 0.42 * math.sqrt((i + 0.5) / n)
        px.append(0.5 + raggio * math.cos(ang))
        py.append(0.5 + raggio * math.sin(ang))

    legami = [(indice[a["da"]], indice[a["a"]]) for a in archi
              if a["da"] in indice and a["a"] in indice]
    k = math.sqrt(1.0 / n)          # distanza di riposo fra due nodi
    passo = 0.1
    for giro in range(giri):
        fx = [0.0] * n
        fy = [0.0] * n
        for i in range(n):
            for j in range(i + 1, n):
                dx, dy = px[i] - px[j], py[i] - py[j]
                d2 = dx * dx + dy * dy
                if d2 < 1e-9:
                    dx, dy, d2 = (i - j) * 1e-4, (j - i) * 1e-4, 2e-8
                forza = (k * k) / d2
                fx[i] += dx * forza; fy[i] += dy * forza
                fx[j] -= dx * forza; fy[j] -= dy * forza
        for a, b in legami:
            dx, dy = px[a] - px[b], py[a] - py[b]
            d = math.hypot(dx, dy) or 1e-6
            forza = (d * d) / k / d
            fx[a] -= dx * forza; fy[a] -= dy * forza
            fx[b] += dx * forza; fy[b] += dy * forza
        # Il passo si raffredda: prima si sistema la forma grossa, poi si limano
        # le sovrapposizioni senza più stravolgere niente.
        limite = passo * (1.0 - giro / giri) + 0.002
        for i in range(n):
            d = math.hypot(fx[i], fy[i]) or 1e-9
            px[i] += fx[i] / d * min(d, limite)
            py[i] += fy[i] / d * min(d, limite)
            px[i] = min(0.99, max(0.01, px[i]))
            py[i] = min(0.99, max(0.01, py[i]))

    minx, maxx = min(px), max(px)
    miny, maxy = min(py), max(py)
    larghezza = (maxx - minx) or 1.0
    altezza = (maxy - miny) or 1.0
    for i, nodo in enumerate(nodi):
        nodo["x"] = round(0.03 + 0.94 * (px[i] - minx) / larghezza, 4)
        nodo["y"] = round(0.03 + 0.94 * (py[i] - miny) / altezza, 4)


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
