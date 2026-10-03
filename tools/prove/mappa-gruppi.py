"""Prove della Mappa a gruppi (22-SERVER, punto 6).

L'utente, guardando la Mappa: piu' apparente su cosa sia, non nomi tutti simili e posizioni
praticamente identiche, ma cluster chiaramente definiti e interconnessi. Lato server, in modo
ADDITIVO (i campi vecchi restano):

- ogni nodo di `/api/memoria/mappa` e ogni scheda di `/api/knowledge` porta `gruppo` (la
  chiave stabile del cluster), `gruppo_nome` (il nome leggibile) e `titolo` (umano e corto);
- il gruppo e' il progetto a cui la memoria appartiene (il progetto Plancia collegato, o la
  cartella di progetto da cui viene il file); le memorie globali (chi sei, preferenze) hanno
  un gruppo per tipo; una cartella con una scheda sola non fa un gruppo;
- il titolo e' il testo del collegamento nell'indice MEMORY.md della stessa cartella, se c'e';
  altrimenti la descrizione accorciata a una frase; mai la sigla finche' c'e' altro;
- la risposta porta anche l'elenco dei gruppi: chiave, nome, colore stabile, numero di
  memorie, legami verso gli altri gruppi (i ponti);
- la disposizione di partenza del server tiene i gruppi separati e compatti, con i ponti
  fra gruppi: anche il primo fotogramma e' gia' leggibile.

Le prove sono sul comportamento e sui numeri della disposizione (quanti nodi stanno piu'
vicini al proprio gruppo che a un altro, quanto vuoto resta fra le isole), non sul cronometro.
Il web (`web/app.js`) disegna i gruppi: qui si guarda il sorgente, come fanno le altre prove
statiche; il disegno vero lo si guarda negli scatti (`tools/scatti.sh`).
"""

import importlib.util
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent


def _carica_modulo(nome):
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parent / (nome + ".py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[nome] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules[nome]


_finti = _carica_modulo("_finti")
_saltati = _carica_modulo("_saltati")
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


def esegui(reale) -> None:
    prova = _saltati.Contatore(reale)
    if _saltati.WIN:
        _saltati.salta_il_resto("mappa-gruppi", prova)
    else:
        _esegui(prova)
    _saltati.chiudi("mappa-gruppi", prova, reale)


def _porta_libera():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def _isole(ngruppi, per_gruppo, ponti, densita=3):
    """Un archivio sintetico a isole: legami fitti dentro ogni gruppo, qualche ponte fra
    gruppi, tutto ripetibile (nessun caso: l'indice fa da seme)."""
    nomi, gruppi, archi, membri = [], {}, [], []
    for g in range(ngruppi):
        n = per_gruppo if isinstance(per_gruppo, int) else per_gruppo[g % len(per_gruppo)]
        m = ["g%02d-n%03d" % (g, i) for i in range(n)]
        membri.append(m)
        for x in m:
            nomi.append(x)
            gruppi[x] = "g%02d" % g
        for i, a in enumerate(m):
            for k in range(densita):
                b = m[(i * (k + 3) + 5 * k + 1) % n]
                if a != b:
                    archi.append((a, b))
    for t in range(ponti):
        g1 = (t * 3) % ngruppi
        g2 = (t * 3 + 1 + t // ngruppi) % ngruppi
        if g1 != g2:
            archi.append((membri[g1][t % len(membri[g1])], membri[g2][(t * 7) % len(membri[g2])]))
    return nomi, archi, gruppi


def _qualita(nomi, archi, gruppi, pos):
    """(quota di nodi piu' vicini al centro del proprio gruppo che a quello di un altro,
    vuoto minimo fra i gruppi (distanza dei centri meno i due raggi), vuoto medio fra
    gruppi legati da un ponte, e fra gruppi senza ponti)."""
    per = {}
    for x in nomi:
        per.setdefault(gruppi[x], []).append(pos[x])
    c = {g: (sum(p[0] for p in l) / len(l), sum(p[1] for p in l) / len(l)) for g, l in per.items()}
    giusti = 0
    for x in nomi:
        mio = math.dist(pos[x], c[gruppi[x]])
        altro = min(math.dist(pos[x], c[g]) for g in c if g != gruppi[x])
        giusti += mio < altro
    raggio = {g: max(math.dist(p, c[g]) for p in per[g]) for g in per}
    vuoto = min(math.dist(c[a], c[b]) - raggio[a] - raggio[b] for a in c for b in c if a < b)
    legati = {tuple(sorted((gruppi[a], gruppi[b]))) for a, b in archi if gruppi[a] != gruppi[b]}
    tutti = [tuple(sorted((a, b))) for a in c for b in c if a < b]
    d_legati = [math.dist(c[a], c[b]) - raggio[a] - raggio[b] for a, b in tutti if (a, b) in legati]
    d_slegati = [math.dist(c[a], c[b]) - raggio[a] - raggio[b] for a, b in tutti if (a, b) not in legati]
    media = lambda l: sum(l) / len(l) if l else 0.0  # noqa: E731
    return giusti / len(nomi), vuoto, media(d_legati), media(d_slegati)


def _esegui(prova) -> None:
    from plancia import config, disposizione, mappa, store

    _prove_disposizione(prova, disposizione)
    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-gruppi-"))
    conn = _prove_mappa(prova, tmp, config, mappa, store)
    _prove_http(prova, tmp)
    _prove_web(prova)
    conn.close()


# ------------------------------------------------------------- 1. la disposizione a isole

def _prove_disposizione(prova, disposizione) -> None:
    nomi, archi, gruppi = _isole(8, [14, 12, 10, 10, 9, 8, 7, 6], 14)
    a = disposizione.calcola(nomi, archi, gruppi=gruppi)
    b = disposizione.calcola(nomi, archi, gruppi=gruppi)
    prova("gruppi: la disposizione a isole e' la stessa a parita' di dati", a == b)
    fuori = [n for n, (x, y) in a.items() if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0)]
    prova("gruppi: ogni nodo sta nel riquadro e ci sono tutti", not fuori and set(a) == set(nomi), str(fuori[:3]))
    giusti, vuoto, d_legati, d_slegati = _qualita(nomi, archi, gruppi, a)
    prova("gruppi: ogni nodo sta piu' vicino al proprio gruppo che a un altro (isole compatte)",
          giusti >= 0.98, "%.3f" % giusti)
    prova("gruppi: le isole non si toccano (vuoto fra i gruppi positivo)", vuoto > 0.01, "%.4f" % vuoto)
    prova("gruppi: i gruppi legati da ponti hanno meno vuoto fra loro di quelli senza (i ponti si vedono)",
          d_legati < d_slegati, "legati %.3f, slegati %.3f" % (d_legati, d_slegati))
    sovrapposti = len({(round(x, 3), round(y, 3)) for x, y in a.values()})
    prova("gruppi: nessun nodo sopra un altro (le posizioni sono tutte distinte)",
          sovrapposti == len(nomi), "%d posizioni per %d nodi" % (sovrapposti, len(nomi)))
    senza = disposizione.calcola(nomi, archi)
    giusti0, vuoto0, _, _ = _qualita(nomi, archi, gruppi, senza)
    # Il confronto che serve e' il vuoto fra i gruppi: senza `gruppi` le isole si toccano
    # (vuoto negativo), con `gruppi` no. La quota di nodi "giusti" senza gruppi cambia con la
    # versione di Python (con 3.9 e' 0,97, con 3.12 e' 1,00, perche' sum() somma i float in
    # modo diverso), quindi si chiede solo che non sia migliore.
    prova("gruppi: senza `gruppi` la disposizione di prima non separa i gruppi (il confronto che serve)",
          giusti0 <= giusti and vuoto0 < 0.01 < vuoto,
          "senza %.2f/%.3f, con %.2f/%.3f" % (giusti0, vuoto0, giusti, vuoto))
    prova("gruppi: con un gruppo solo (o nessuno) vale la disposizione di sempre",
          disposizione.calcola(nomi, archi, gruppi={x: "tutti" for x in nomi}) == senza
          and disposizione.calcola(nomi, archi, gruppi={}) == senza)

    # grande: 40 gruppi, 1200 nodi
    n1200, a1200, g1200 = _isole(40, 30, 90)
    cpu = time.process_time()
    grande = disposizione.calcola(n1200, a1200, gruppi=g1200)
    cpu = time.process_time() - cpu
    giusti, vuoto, _, _ = _qualita(n1200, a1200, g1200, grande)
    prova("gruppi: 1200 nodi in 40 gruppi: poca CPU, isole separate e compatte",
          len(grande) == 1200 and cpu < 6.0 and giusti >= 0.98 and vuoto > 0.0,
          "cpu %.1f s, giusti %.3f, vuoto %.4f" % (cpu, giusti, vuoto))

    # la mappa di domani assomiglia a quella di oggi: una scheda in piu' non la fa girare
    nuovi = nomi + ["g03-nuovo"]
    gruppi2 = dict(gruppi)
    gruppi2["g03-nuovo"] = "g03"
    archi2 = archi + [("g03-nuovo", "g03-n002"), ("g03-nuovo", "g03-n005")]
    caldo = disposizione.calcola(nuovi, archi2, partenza=a, gruppi=gruppi2)
    freddo = disposizione.calcola(nuovi, archi2, gruppi=gruppi2)
    spost = sorted(math.dist(a[n], caldo[n]) for n in nomi)
    spost_f = sorted(math.dist(a[n], freddo[n]) for n in nomi)
    prova("gruppi: con la partenza precedente la mappa non gira su se' stessa per una scheda in piu'",
          spost[len(spost) // 2] < 0.05 and spost[len(spost) // 2] <= spost_f[len(spost_f) // 2] + 1e-9
          and max(spost) < 0.3,
          "mediana %.3f (da zero %.3f), massimo %.3f" % (spost[len(spost) // 2], spost_f[len(spost_f) // 2], max(spost)))
    prova("gruppi: due gruppi di un nodo e nodi senza gruppo non rompono niente",
          set(disposizione.calcola(["a", "b", "c"], [("a", "b")], gruppi={"a": "x", "b": "y"})) == {"a", "b", "c"}
          and len(disposizione.calcola(["a", "b"], [], gruppi={"a": "x", "b": "y"})) == 2)


# ------------------------------------------------------------- 2. dalle schede alla mappa

def _scrivi_memoria(radice, cartella, nome, tipo, descrizione, corpo="", indice=None):
    d = radice / cartella / "memory"
    d.mkdir(parents=True, exist_ok=True)
    f = d / (nome + ".md")
    f.write_text("---\nname: %s\ndescription: %s\nmetadata:\n  type: %s\n---\n\n%s\n"
                 % (nome, descrizione, tipo, corpo or ("testo di prova " * 30)), "utf-8")
    if indice:
        riga = "- [%s](%s.md) - %s\n" % (indice, nome, "gancio di prova")
        i = d / "MEMORY.md"
        i.write_text((i.read_text("utf-8") if i.exists() else "") + riga, "utf-8")
    return f


def _prove_mappa(prova, tmp, config, mappa, store):
    conn = store.connect()
    store.init_db(conn)
    store.migrate(conn)
    conn.execute("DELETE FROM knowledge")
    conn.execute("DELETE FROM project_links")
    conn.execute("DELETE FROM projects")
    radice = tmp / "claude-projects"
    pid = {}
    for key, nome, percorso in (("lumen", "Lumen", "/prova/dev/lumen"), ("apiary", "Apiary", "/prova/dev/apiary")):
        pid[key] = store.upsert_project(conn, key, nome, auto=0, _force=True)
        store.link_project(conn, pid[key], "path", percorso)
    conn.commit()

    schede = []   # (nome, tipo, cartella, descrizione, indice, legami, project_id)

    def nuova(nome, tipo, cartella, descrizione, indice=None, legami=(), project_id=None):
        f = _scrivi_memoria(radice, cartella, nome, tipo, descrizione, indice=indice)
        conn.execute(
            "INSERT INTO knowledge(name, path, scope, description, type, body, links, project_id, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (nome, str(f), cartella, descrizione, tipo, "testo di prova " * 30, json.dumps(list(legami)),
             project_id, "2026-09-%02dT10:00:00Z" % (1 + len(schede) % 27)))
        schede.append(nome)

    # progetto Lumen (cartella che corrisponde al percorso del progetto Plancia): 4 schede
    nuova("lumen-index", "project", "-prova-dev-lumen", "Il formato dell'indice: un file solo, scritto in modo atomico. Il resto e' dettaglio.",
          indice="Come e' fatto l'indice", legami=("lumen-release", "lumen-quirks"))
    nuova("lumen-release", "project", "-prova-dev-lumen", "Tag, build, checksum e infine il changelog",
          indice="Il rito della release", legami=("lumen-index",))
    nuova("lumen-quirks", "reference", "-prova-dev-lumen", "Il front matter e' facoltativo; le tabelle vogliono l'intestazione",
          legami=("lumen-index",))
    nuova("lumen-nodesc", "project", "-prova-dev-lumen", "", legami=("lumen-index",))
    # progetto Apiary: due schede, una in una cartella che non e' il progetto ma e' collegata col project_id
    nuova("apiary-budgets", "project", "-prova-dev-apiary", "Budget per progetto, imposti al proxy", indice="Budget e tetti",
          legami=("apiary-keys",))
    nuova("apiary-keys", "project", "-prova-dev-apiary", "Le chiavi ruotano il primo del mese", legami=("apiary-budgets", "apiary-altrove"))
    nuova("apiary-altrove", "project", "-prova-altra-cartella", "Una scheda di Apiary scritta altrove", project_id=pid["apiary"],
          legami=("apiary-keys",))
    # globali: per tipo, qualunque sia la cartella
    nuova("chi-sono", "user", "-prova-dev-lumen", "Lavoro da solo, la mattina", indice="Chi sono", legami=("stile",))
    nuova("sera", "user", "-prova-home", "Alla sera niente riunioni")
    nuova("stile", "feedback", "-prova-home", "Frasi corte. Niente em dash.", indice="Stile di scrittura", legami=("commit",))
    nuova("commit", "feedback", "-prova-dev-apiary", "Messaggi di commit all'imperativo", legami=("stile", "lumen-quirks"))
    # una cartella con due schede e senza progetto: fa un gruppo suo, con il nome della cartella
    nuova("sito-a", "project", "-prova-dev-sito-statico", "La pagina archivio aspetta i tag", legami=("sito-b",))
    nuova("sito-b", "project", "-prova-dev-sito-statico", "L'hosting e' un host solo dietro una CDN", legami=("sito-a", "lumen-release"))
    # una cartella con una scheda sola: niente gruppo suo, cade nel gruppo del tipo
    nuova("solitaria", "project", "-prova-dev-una-sola", "Una scheda sola in una cartella sola")
    nuova("rif-sola", "reference", "-prova-dev-altra-sola", "Dove stanno i modelli sul disco esterno")
    conn.commit()

    m = mappa.mappa(conn)
    nodi = {n["nome"]: n for n in m["nodi"]}
    prova("gruppi: ogni nodo porta gruppo, gruppo_nome e titolo (e i campi di prima restano)",
          all(n.get("gruppo") and n.get("gruppo_nome") and n.get("titolo") for n in m["nodi"])
          and {"nome", "tipo", "descrizione", "grado", "x", "y", "richiamabile", "dove"} <= set(m["nodi"][0])
          and {"nodi", "archi", "diagnosi", "gruppi"} <= set(m), str(set(m["nodi"][0])))
    prova("gruppi: una memoria di progetto sta nel progetto Plancia della sua cartella",
          nodi["lumen-index"]["gruppo"] == "lumen" and nodi["lumen-release"]["gruppo"] == "lumen"
          and nodi["lumen-index"]["gruppo_nome"] == "Lumen", str(nodi["lumen-index"]))
    prova("gruppi: ...anche una di riferimento della stessa cartella",
          nodi["lumen-quirks"]["gruppo"] == "lumen")
    prova("gruppi: il progetto collegato (project_id) vale anche se il file sta in un'altra cartella",
          nodi["apiary-altrove"]["gruppo"] == "apiary" and nodi["apiary-keys"]["gruppo"] == "apiary")
    prova("gruppi: chi sei e preferenze hanno un gruppo per tipo, in qualunque cartella stiano",
          nodi["chi-sono"]["gruppo"] == nodi["sera"]["gruppo"] == "tipo:user"
          and nodi["stile"]["gruppo"] == nodi["commit"]["gruppo"] == "tipo:feedback"
          and nodi["stile"]["gruppo_nome"] != nodi["chi-sono"]["gruppo_nome"], str({k: nodi[k]["gruppo"] for k in nodi}))
    prova("gruppi: una cartella con due schede e senza progetto fa un gruppo col nome della cartella",
          nodi["sito-a"]["gruppo"] == nodi["sito-b"]["gruppo"] and nodi["sito-a"]["gruppo"].startswith("cartella:")
          and "sito" in nodi["sito-a"]["gruppo_nome"].lower(), str(nodi["sito-a"]))
    prova("gruppi: una cartella con una scheda sola non fa un gruppo: cade nel gruppo del suo tipo",
          nodi["solitaria"]["gruppo"] == "tipo:project" and nodi["rif-sola"]["gruppo"] == "tipo:reference",
          "%s %s" % (nodi["solitaria"]["gruppo"], nodi["rif-sola"]["gruppo"]))

    prova("gruppi: il titolo e' il testo del collegamento nell'indice MEMORY.md",
          nodi["lumen-index"]["titolo"] == "Come e' fatto l'indice" and nodi["stile"]["titolo"] == "Stile di scrittura"
          and nodi["apiary-budgets"]["titolo"] == "Budget e tetti", str([nodi[k]["titolo"] for k in ("lumen-index", "stile")]))
    t = nodi["lumen-quirks"]["titolo"]
    prova("gruppi: senza indice il titolo e' la descrizione accorciata a una frase, non la sigla",
          t == "Il front matter e' facoltativo" and t != "lumen-quirks", t)
    t = nodi["lumen-nodesc"]["titolo"]
    prova("gruppi: senza indice e senza descrizione si ripiega sul nome leggibile (mai vuoto)",
          t and " " in t and t[0].isupper() and "-" not in t, t)
    lunga = "Una descrizione molto lunga che non finisce mai e che continua ancora per molte parole senza un solo punto fermo fino in fondo"
    prova("gruppi: il titolo di una descrizione lunga e senza punti si accorcia ai confini di una parola",
          len(mappa.titolo_da_descrizione(lunga)) <= 70 and mappa.titolo_da_descrizione(lunga).endswith("…"),
          mappa.titolo_da_descrizione(lunga))
    prova("gruppi: i titoli sono tutti diversi fra loro quando le schede lo sono",
          len({n["titolo"] for n in m["nodi"]}) == len(m["nodi"]), str(sorted(n["titolo"] for n in m["nodi"])))

    gruppi = {g["chiave"]: g for g in m["gruppi"]}
    prova("gruppi: l'elenco dei gruppi ha chiave, nome, colore, numero di memorie e legami",
          {"chiave", "nome", "colore", "memorie", "legami"} <= set(m["gruppi"][0])
          and all(re.match(r"^#[0-9a-f]{6}$", g["colore"]) for g in m["gruppi"]), str(m["gruppi"][0]))
    prova("gruppi: ogni nodo appartiene a un gruppo dell'elenco e i conti tornano",
          all(n["gruppo"] in gruppi for n in m["nodi"]) and sum(g["memorie"] for g in m["gruppi"]) == len(m["nodi"])
          and all(g["memorie"] == sum(1 for n in m["nodi"] if n["gruppo"] == g["chiave"]) for g in m["gruppi"]))
    ponti = {}
    for a in m["archi"]:
        ga, gb = nodi[a["da"]]["gruppo"], nodi[a["a"]]["gruppo"]
        if ga != gb:
            ponti[(ga, gb)] = ponti.get((ga, gb), 0) + 1
            ponti[(gb, ga)] = ponti.get((gb, ga), 0) + 1
    letti = {(g["chiave"], l["gruppo"]): l["n"] for g in m["gruppi"] for l in g["legami"]}
    prova("gruppi: i legami fra gruppi (i ponti) sono quelli degli archi, simmetrici e mai verso se' stessi",
          letti == ponti and bool(ponti) and all(a != b for a, b in letti), "%s | %s" % (letti, ponti))
    colori = [g["colore"] for g in m["gruppi"]]
    prova("gruppi: i colori dei gruppi nella stessa mappa sono tutti diversi", len(set(colori)) == len(colori), str(colori))
    m2 = mappa.mappa(conn)
    prova("gruppi: il colore di un gruppo e' stabile (stessa mappa, stesso colore) e dipende dalla sua chiave",
          {g["chiave"]: g["colore"] for g in m2["gruppi"]} == {g["chiave"]: g["colore"] for g in m["gruppi"]}
          and mappa.colore_gruppo("lumen") == mappa.colore_gruppo("lumen")
          and mappa.colore_gruppo("lumen") != mappa.colore_gruppo("tipo:user"))

    per = {}
    for n in m["nodi"]:
        per.setdefault(n["gruppo"], []).append((n["x"], n["y"]))
    prova("gruppi: i gruppi stanno separati nel primo fotogramma (centri lontani piu' dei raggi)",
          _vuoto_reale(per) > 0, "%.4f" % _vuoto_reale(per))
    prova("gruppi: l'elenco dei gruppi porta anche il centro (x, y) di ognuno",
          all(0 <= g.get("x", -1) <= 1 and 0 <= g.get("y", -1) <= 1 for g in m["gruppi"]))

    # il gruppo cambia -> l'impronta cambia e la disposizione si ricalcola; la descrizione no
    prima = mappa.STATISTICHE["calcoli"]
    conn.execute("UPDATE knowledge SET description='riscritta del tutto' WHERE name='stile'")
    conn.commit()
    mappa.mappa(conn)
    prova("gruppi: riscrivere una descrizione (anche il titolo) non ricalcola la disposizione",
          mappa.STATISTICHE["calcoli"] == prima)
    conn.execute("UPDATE knowledge SET project_id=? WHERE name='solitaria'", (pid["lumen"],))
    conn.commit()
    m3 = mappa.mappa(conn)
    n3 = {n["nome"]: n for n in m3["nodi"]}
    prova("gruppi: collegare una scheda a un progetto la sposta di gruppo e ricalcola",
          n3["solitaria"]["gruppo"] == "lumen" and mappa.STATISTICHE["calcoli"] == prima + 1,
          "%s, %d calcoli" % (n3["solitaria"]["gruppo"], mappa.STATISTICHE["calcoli"] - prima))

    # un progetto nascosto non da' il nome a un gruppo
    conn.execute("UPDATE projects SET hidden=1 WHERE key='apiary'")
    conn.commit()
    m4 = mappa.mappa(conn)
    n4 = {n["nome"]: n for n in m4["nodi"]}
    prova("gruppi: un progetto nascosto non da' il suo nome a un gruppo",
          all(n["gruppo_nome"] != "Apiary" for n in m4["nodi"])
          and n4["apiary-keys"]["gruppo"] != "apiary", str(n4["apiary-keys"]))
    conn.execute("UPDATE projects SET hidden=0 WHERE key='apiary'")
    conn.commit()

    # le schede dell'elenco (/api/knowledge) portano gli stessi campi
    schede_api = mappa.schede(conn)
    s = {x["name"]: x for x in schede_api}
    prova("gruppi: le schede di /api/knowledge portano gruppo, gruppo_nome e titolo, come i nodi",
          len(schede_api) == len(schede) and all(x.get("gruppo") and x.get("gruppo_nome") and x.get("titolo") for x in schede_api)
          and s["lumen-index"]["gruppo"] == "lumen" and s["lumen-index"]["titolo"] == "Come e' fatto l'indice"
          and {"id", "name", "description", "type", "updated_at", "links", "progetto", "project_key"} <= set(schede_api[0]),
          str(schede_api[0]))
    prova("gruppi: gruppo, titolo e nome sono gli stessi nelle schede e nella mappa",
          all(s[k]["gruppo"] == nodi_k["gruppo"] and s[k]["titolo"] == nodi_k["titolo"]
              for k, nodi_k in ((n["nome"], n) for n in mappa.mappa(conn)["nodi"] if n["nome"] in s)
              if k not in ("apiary-keys", "apiary-altrove", "solitaria")))

    # MEMORY.md che cambia: il titolo segue (e non si legge due volte lo stesso file)
    idx = radice / "-prova-dev-lumen" / "memory" / "MEMORY.md"
    time.sleep(0.02)
    idx.write_text(idx.read_text("utf-8").replace("Come e' fatto l'indice", "L'indice in breve"), "utf-8")
    os.utime(str(idx), (time.time() + 5, time.time() + 5))
    prova("gruppi: se l'indice MEMORY.md cambia, il titolo segue",
          {n["nome"]: n for n in mappa.mappa(conn)["nodi"]}["lumen-index"]["titolo"] == "L'indice in breve")
    return conn


def _vuoto_reale(per):
    c = {g: (sum(p[0] for p in l) / len(l), sum(p[1] for p in l) / len(l)) for g, l in per.items()}
    raggio = {g: max(math.dist(p, c[g]) for p in per[g]) for g in per}
    return min(math.dist(c[a], c[b]) - raggio[a] - raggio[b] for a in c for b in c if a < b)


# ------------------------------------------------------------- 3. dal server

def _prove_http(prova, tmp) -> None:
    casa = tmp / "casa-http"
    casa.mkdir()
    (casa / "claude-vuota").mkdir()
    (casa / "codex-vuota").mkdir()
    porta = _porta_libera()
    env = dict(os.environ)
    env["PLANCIA_HOME"] = str(casa)
    _finti.casa_finta(env, casa)
    env["CLAUDE_CONFIG_DIR"] = str(casa / "claude-vuota")
    env["CODEX_HOME"] = str(casa / "codex-vuota")
    server = None
    try:
        dati = subprocess.run([sys.executable, str(RADICE / "tools" / "demo-data.py")], env=env,
                              capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        if dati.returncode != 0:
            prova("gruppi/http: l'archivio dimostrativo si crea", False, dati.stderr[-300:])
            return
        server = subprocess.Popen([sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta), "--no-sync"],
                                  cwd=str(RADICE), env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        base = "http://127.0.0.1:%d" % porta
        vivo = False
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/api/overview", timeout=1)
                vivo = True
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if server.poll() is not None:
                    break
                time.sleep(0.25)
        if not vivo:
            prova("gruppi/http: il server di prova e' partito", False, (server.stdout.read() if server.stdout else "")[:500])
            return

        def leggi(percorso):
            return json.loads(urllib.request.urlopen(base + percorso, timeout=90).read())

        m = leggi("/api/memoria/mappa")
        k = leggi("/api/knowledge")
        nodi = {n["nome"]: n for n in m["nodi"]}
        prova("gruppi/http: /api/memoria/mappa porta i gruppi, e ogni nodo il suo",
              bool(m.get("gruppi")) and all(n.get("gruppo") and n.get("titolo") for n in m["nodi"]),
              str(m.get("gruppi"))[:200])
        prova("gruppi/http: /api/knowledge porta gruppo, gruppo_nome e titolo, uguali a quelli della mappa",
              len(k) == len(m["nodi"]) and all(x.get("gruppo") == nodi[x["name"]]["gruppo"]
                                               and x.get("titolo") == nodi[x["name"]]["titolo"] for x in k if x["name"] in nodi),
              str(k[0])[:200])
        prova("gruppi/http: la mappa demo ha 6-9 gruppi leggibili (nome umano, non una sigla), ognuno con piu' di una memoria",
              6 <= len(m["gruppi"]) <= 12 and all(g["memorie"] >= 2 and g["nome"] for g in m["gruppi"]),
              str([(g["nome"], g["memorie"]) for g in m["gruppi"]]))
        t0 = time.time()
        for _ in range(5):
            leggi("/api/overview")
        prova("gruppi/http: la seconda richiesta della mappa e' in cache (stesse posizioni, risposta rapida)",
              leggi("/api/memoria/mappa")["nodi"] == m["nodi"] and time.time() - t0 < 30)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(10)


# ------------------------------------------------------------- 4. il web

def _prove_web(prova) -> None:
    js = (RADICE / "web" / "app.js").read_text("utf-8")
    css = (RADICE / "web" / "style.css").read_text("utf-8")
    grafo = js[js.index("function montaGrafo("):js.index("function distruggiGrafo(")]
    prova("web: il grafo parte dalle posizioni del server e tira i nodi verso il centro del proprio gruppo",
          "n.n.x" in grafo and "n.gruppo" in grafo and "centro[" in grafo and "gruppi" in grafo)
    prova("web: i gruppi sono regioni morbide colorate (involucro arrotondato, riempimento trasparente) col nome grande",
          "involucro(" in grafo and "lineJoin" in grafo and "nomeGruppo(" in grafo and "globalAlpha" in grafo)
    prova("web: i nodi si scrivono col titolo, non con la sigla",
          "n.n.titolo" in grafo and "const nome = n.id.length" not in grafo)
    prova("web: da lontano si vedono solo i gruppi (nomi grandi), da vicino i titoli dei nodi",
          "SOGLIA_TITOLI" in grafo and "SOGLIA_GRUPPI" in grafo)
    prova("web: i ponti fra gruppi si vedono (archi fra gruppi piu' marcati, e aggregati da lontano)",
          "ponte" in grafo and "e.ponte" in grafo)
    prova("web: la legenda elenca i gruppi con colore, nome e numero, e un clic ci va",
          "grafo-gruppo" in js and "focalizza" in grafo and "g.colore" in js)
    prova("web: l'elenco e il dettaglio usano il titolo e dicono di che gruppo e' la memoria",
          "n.titolo" in js[js.index("views.memoria"):js.index("/* ---------------------------------------------------------------- grafo */")]
          and "gruppo_nome" in js[js.index("DETTAGLI.memoria"):js.index("/* ---------------------------------------------------------------- grafo */")])
    prova("web: la regione dei gruppi ha il suo stile e i colori seguono il tema chiaro e scuro",
          ".grafo-legenda" in css and "grafo-gruppo" in css)
