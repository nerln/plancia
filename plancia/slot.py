"""Il padre di un progetto: la piattaforma sotto tanti studi.

`project_links` ha `UNIQUE(kind, value)` (store.py:45) e non può dire che due
progetti diversi condividono lo stesso padre: un padre con due figli non ci
stava, se non forzando la chiave. Qui il padre è una colonna
(`projects.parent_id`, aggiunta da `store.AGGIUNTE`), profondità massima 1:
un padre è sempre un progetto manuale (`auto=0`), non ha a sua volta un
padre, e un figlio non può avere figli (altrimenti servirebbe una gerarchia
vera, che qui non serve: vedi LOTTO-L0-SCHEMA.md).

Ogni cambio di padre è reversibile per batch: si scrive `parent_id` e insieme
un evento nel registro (`plancia/eventi.py`), col valore precedente. Il tipo
dell'evento è `padre:<batch>` (non un tipo fisso in `eventi.TIPI`, che è di
un altro file): così `annulla(batch)` legge esattamente e solo gli eventi di
quel batch con `eventi.leggi(tipo=...)`, senza dover scorrere `dati` a mano.

Le chiavi (figlio, padre) si risolvono con un confronto esatto, mai con
`store.get_project`: quella funzione, dopo id/chiave/nome esatti, ripiega su
`LIKE '%chiave%'` e sulle parole del nome (store.py:344-364), pensata per un
comando vocale che arriva impreciso. Qui un refuso o una chiave troncata
deve essere rifiutato, non riassegnato in silenzio a un progetto che
somiglia a quello scritto: L1-RIORDINA applicherà batch letti da un json, e
l'evento deve registrare la chiave chiesta, non quella indovinata.
"""

import os

from . import attribuzione, eventi, store


def _progetto_esatto(conn, ident):
    """Id numerico esatto o chiave esatta. Mai una risoluzione per
    sottostringa (vedi il modulo): un `ident` che non è né un id né una
    chiave che esiste per intero torna None."""
    if ident is None or ident == "":
        return None
    if isinstance(ident, int) or (isinstance(ident, str) and ident.isdigit()):
        riga = conn.execute("SELECT * FROM projects WHERE id=?", (int(ident),)).fetchone()
        if riga:
            return riga
    return conn.execute("SELECT * FROM projects WHERE key=?", (str(ident),)).fetchone()


# Lo stesso elenco di "aperto" che usa actions.tasks_list (aperto, in corso,
# bloccato): un task fatto o archiviato non è "il prossimo passo".
STATI_APERTI = ("aperto", "in corso", "bloccato")

# Lo stesso ORDER BY di actions.tasks_list (actions.py:123-125): copiato
# invece che importato perché importare actions.py trascinerebbe anche
# briefing.py (di un altro lotto) come dipendenza di questo file, non perché
# ci sia un ciclo vero (actions.py non importa slot.py).
_ORDINE_TASK = (
    "CASE t.status WHEN 'in corso' THEN 0 WHEN 'bloccato' THEN 1 "
    "WHEN 'aperto' THEN 2 ELSE 3 END, t.priority ASC, t.due IS NULL, t.due ASC, "
    "t.updated_at DESC"
)


def _batch_non_valido(batch) -> bool:
    """Un batch vuoto o con virgole/spazi non sarebbe annullabile (vedi
    `set_parent`)."""
    return not isinstance(batch, str) or not batch.strip() or "," in batch or \
        any(c.isspace() for c in batch)


def _rifiuto_padre(conn, figlio, padre):
    """Il motivo per cui `padre` non può fare da padre a `figlio`, o None se
    va bene. Le stesse regole per `set_parent` e per `riordina_progetto`."""
    if figlio["id"] == padre["id"]:
        return "il figlio e il padre sono lo stesso progetto"
    if padre["auto"]:
        return f"'{padre['key']}' è un progetto automatico: non può fare da padre"
    if padre["parent_id"]:
        return f"'{padre['key']}' ha già un padre: la profondità massima è 1"
    n_figli = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE parent_id=?", (figlio["id"],)
    ).fetchone()[0]
    if n_figli:
        return f"'{figlio['key']}' ha già dei figli: diventerebbero nipoti del padre"
    return None


def set_parent(conn, figlio_key, padre_key, batch) -> dict:
    """Assegna un padre a un progetto.

    Rifiuta con un motivo (dict con `ok: False`) invece di sollevare
    un'eccezione: chi chiama da MCP o CLI deve poter mostrare il perché
    all'utente, non un traceback.
    """
    # eventi.leggi(tipo=...) spezza il filtro sulle virgole (eventi.py:131):
    # un batch con la virgola non sarebbe più annullabile per intero, e uno
    # vuoto o fatto di spazi non è distinguibile da "nessun batch".
    if _batch_non_valido(batch):
        return {"ok": False,
                "motivo": "batch non valido: vuoto o con virgole/spazi (non sarebbe annullabile)"}
    figlio = _progetto_esatto(conn, figlio_key)
    if not figlio:
        return {"ok": False, "motivo": f"progetto inesistente: {figlio_key}"}
    padre = _progetto_esatto(conn, padre_key)
    if not padre:
        return {"ok": False, "motivo": f"progetto inesistente: {padre_key}"}
    rifiuto = _rifiuto_padre(conn, figlio, padre)
    if rifiuto:
        return {"ok": False, "motivo": rifiuto}

    prima = figlio["parent_id"]
    dopo = padre["id"]
    conn.execute("UPDATE projects SET parent_id=?, updated_at=? WHERE id=?",
                 (dopo, store.now(), figlio["id"]))
    eventi.scrivi(f"padre:{batch}", f"{figlio['name']} sotto {padre['name']}", figlio["key"],
                  {"batch": batch, "figlio": figlio["key"], "prima": prima, "dopo": dopo})
    conn.commit()
    return {"ok": True, "figlio": figlio["key"], "padre": padre["key"],
            "prima": prima, "dopo": dopo}


# Gli stati che il riordino può scrivere. Sono un sottoinsieme di
# `actions.PROJECT_STATES` (che ha anche "in pausa" e "idea"): un riordino
# decide se un progetto è vivo, chiuso bene o messo da parte, non ne
# mette in pausa uno. Ripetuti qui invece di importare actions.py, che
# trascinerebbe briefing.py (vedi il commento su `_ORDINE_TASK`).
STATI_RIORDINO = ("attivo", "archiviato", "concluso")


def con_nota(sommario, nota) -> str:
    """Il sommario di un progetto con `nota` aggiunta in coda, su una riga a
    parte. Idempotente: se la riga c'è già, torna il sommario com'era (un
    secondo `--applica` dello stesso file non la ripete)."""
    sommario = sommario or ""
    if not nota or nota in sommario.splitlines():
        return sommario
    return f"{sommario}\n{nota}" if sommario else nota


def riordina_progetto(conn, figlio_key, batch, padre_key=None, stato=None, nota=None) -> dict:
    """Cambia in un colpo solo padre, stato e nota (`summary`) di un progetto,
    con UN evento `padre:<batch>` che porta i valori di prima e di dopo di
    ognuno: `annulla(batch)` disfa così tutto insieme, campo per campo.

    Tutto o niente: se il padre viene rifiutato, lo stato non cambia. Un
    valore uguale a quello che c'è già non conta come cambiamento; se nessun
    campo cambia non si scrive nessun evento (`cambiato: False`).
    """
    if _batch_non_valido(batch):
        return {"ok": False,
                "motivo": "batch non valido: vuoto o con virgole/spazi (non sarebbe annullabile)"}
    figlio = _progetto_esatto(conn, figlio_key)
    if not figlio:
        return {"ok": False, "motivo": f"progetto inesistente: {figlio_key}"}
    if stato and stato not in STATI_RIORDINO:
        return {"ok": False,
                "motivo": f"stato non valido: '{stato}'. Ammessi: {', '.join(STATI_RIORDINO)}"}
    parent_prima = figlio["parent_id"]
    parent_dopo = parent_prima
    padre = None
    if padre_key:
        padre = _progetto_esatto(conn, padre_key)
        if not padre:
            return {"ok": False, "motivo": f"progetto inesistente: {padre_key}"}
        rifiuto = _rifiuto_padre(conn, figlio, padre)
        if rifiuto:
            return {"ok": False, "motivo": rifiuto}
        parent_dopo = padre["id"]
    stato_prima = figlio["status"]
    stato_dopo = stato or stato_prima
    nota_prima = figlio["summary"] or ""
    nota_dopo = con_nota(nota_prima, nota) if nota else nota_prima

    if (parent_dopo, stato_dopo, nota_dopo) == (parent_prima, stato_prima, nota_prima):
        return {"ok": True, "cambiato": False, "figlio": figlio["key"],
                "padre": padre["key"] if padre else None}

    conn.execute(
        "UPDATE projects SET parent_id=?, status=?, summary=?, updated_at=? WHERE id=?",
        (parent_dopo, stato_dopo, nota_dopo, store.now(), figlio["id"]))
    cosa = []
    if parent_dopo != parent_prima:
        cosa.append(f"sotto {padre['name']}")
    if stato_dopo != stato_prima:
        cosa.append(f"stato {stato_dopo}")
    if nota_dopo != nota_prima:
        cosa.append("nota")
    eventi.scrivi(f"padre:{batch}", f"{figlio['name']}: {', '.join(cosa)}", figlio["key"],
                  {"batch": batch, "figlio": figlio["key"],
                   "prima": parent_prima, "dopo": parent_dopo,
                   "stato_prima": stato_prima, "stato_dopo": stato_dopo,
                   "nota_prima": nota_prima, "nota_dopo": nota_dopo})
    conn.commit()
    return {"ok": True, "cambiato": True, "figlio": figlio["key"],
            "padre": padre["key"] if padre else None,
            "prima": parent_prima, "dopo": parent_dopo,
            "stato_prima": stato_prima, "stato_dopo": stato_dopo}


def annulla(conn, batch) -> int:
    """Rimette i valori di prima per ogni evento del batch, in ordine
    inverso rispetto a come sono stati scritti. Torna quanti progetti ha
    toccato.

    Campo per campo, e solo se il campo è ancora quello lasciato da questo
    batch: se dopo `set_parent(op6, vesuvius, 'vecchio')` arriva
    `set_parent(op6, delta, 'nuovo')`, `annulla('vecchio')` non deve
    scavalcare 'nuovo' riportando op6 a vesuvius. Si confronta il valore
    attuale (`parent_id`, `status`, `summary`) con il `dopo` registrato in
    quell'evento: solo se combaciano è sicuro rimettere `prima`. Lo stesso
    vale per lo stato e per la nota di `riordina_progetto`: uno stato
    cambiato a mano o da un altro batch dopo di questo non viene toccato,
    anche se il padre invece torna com'era. Gli eventi di prima di
    `riordina_progetto` non portano stato né nota: per loro si rimette solo
    il padre, come sempre.
    """
    righe = eventi.leggi(tipo=f"padre:{batch}", limite=100000)
    ripristinati = 0
    ts = store.now()
    for riga in reversed(righe):
        dati = riga.get("dati") or {}
        figlio_key = dati.get("figlio")
        if not figlio_key:
            continue
        figlio = _progetto_esatto(conn, figlio_key)
        if not figlio:
            continue
        rimesso = {}
        # Un campo che l'evento non ha cambiato (prima == dopo) non conta
        # come "rimesso": uno stato cambiato senza toccare il padre non deve
        # far dire che è tornato anche il padre.
        if figlio["parent_id"] == dati.get("dopo") and dati.get("prima") != dati.get("dopo"):
            rimesso["parent_id"] = dati.get("prima")
        if ("stato_dopo" in dati and figlio["status"] == dati["stato_dopo"]
                and dati.get("stato_prima") != dati["stato_dopo"]):
            rimesso["status"] = dati.get("stato_prima")
        if ("nota_dopo" in dati and (figlio["summary"] or "") == dati["nota_dopo"]
                and dati.get("nota_prima") != dati["nota_dopo"]):
            rimesso["summary"] = dati.get("nota_prima") or ""
        if not rimesso:
            continue
        colonne = ", ".join(f"{c}=?" for c in rimesso)
        conn.execute(f"UPDATE projects SET {colonne}, updated_at=? WHERE id=?",
                     (*rimesso.values(), ts, figlio["id"]))
        ripristinati += 1
    conn.commit()
    return ripristinati


def _totali(conn, ids) -> dict:
    """Sessioni, eventi e task aperti per un insieme di project_id, con lo
    stesso filtro hidden che usa il resto dell'app (store.visibile)."""
    if not ids:
        return {"sessioni": 0, "eventi": 0, "task_aperti": 0}
    segnaposto = ",".join("?" for _ in ids)
    sessioni = conn.execute(
        f"SELECT COUNT(*) FROM sessions s WHERE s.project_id IN ({segnaposto}) "
        f"AND {store.visibile('s')}",
        list(ids),
    ).fetchone()[0]
    n_eventi = conn.execute(
        f"SELECT COUNT(*) FROM events e WHERE e.project_id IN ({segnaposto}) "
        f"AND {store.visibile('e')}",
        list(ids),
    ).fetchone()[0]
    segnaposto_stati = ",".join("?" for _ in STATI_APERTI)
    task_aperti = conn.execute(
        f"SELECT COUNT(*) FROM tasks t WHERE t.project_id IN ({segnaposto}) "
        f"AND t.status IN ({segnaposto_stati}) AND {store.visibile('t')}",
        list(ids) + list(STATI_APERTI),
    ).fetchone()[0]
    return {"sessioni": sessioni, "eventi": n_eventi, "task_aperti": task_aperti}


def albero(conn) -> list:
    """I padri (progetti senza parent_id, non nascosti) con i loro figli, e
    per ciascun nodo i totali sommati sul proprio sottoalbero. Un progetto
    senza figli resta un nodo con `figli: []`, non sparisce."""
    padri = conn.execute(
        "SELECT * FROM projects WHERE parent_id IS NULL AND hidden=0 ORDER BY name"
    ).fetchall()
    alberi = []
    for padre in padri:
        righe_figli = conn.execute(
            "SELECT * FROM projects WHERE parent_id=? AND hidden=0 ORDER BY name",
            (padre["id"],),
        ).fetchall()
        figli = []
        for f in righe_figli:
            nodo = dict(f)
            nodo.update(_totali(conn, [f["id"]]))
            figli.append(nodo)
        nodo_padre = dict(padre)
        nodo_padre["figli"] = figli
        nodo_padre.update(_totali(conn, [padre["id"]] + [f["id"] for f in righe_figli]))
        alberi.append(nodo_padre)
    return alberi


def prossimi(conn, limite=None) -> list:
    """Una riga per progetto attivo non nascosto: cosa fare dopo e da dove
    viene (un task aperto, il next_action, o niente)."""
    progetti = conn.execute(
        "SELECT * FROM projects WHERE status='attivo' AND hidden=0"
    ).fetchall()
    segnaposto_stati = ",".join("?" for _ in STATI_APERTI)
    righe = []
    for p in progetti:
        area = None
        if p["parent_id"]:
            riga_padre = conn.execute(
                "SELECT key FROM projects WHERE id=?", (p["parent_id"],)
            ).fetchone()
            area = riga_padre["key"] if riga_padre else None
        task = conn.execute(
            f"SELECT id, title, due FROM tasks t WHERE t.project_id=? "
            f"AND t.status IN ({segnaposto_stati}) ORDER BY {_ORDINE_TASK} LIMIT 1",
            (p["id"],) + STATI_APERTI,
        ).fetchone()
        if task:
            # task["due"] può essere '' (mai NULL, di default): normalizzato
            # a None, altrimenti scadenza='' verrebbe fuori da questa
            # funzione come "ha una scadenza" per chi non guarda anche se il
            # sort qui sotto la tratta già correttamente come falsy.
            cosa, fonte, task_id, scadenza = task["title"], "task", task["id"], task["due"] or None
        elif p["next_action"]:
            cosa, fonte, task_id, scadenza = p["next_action"], "next_action", None, None
        else:
            cosa, fonte, task_id, scadenza = "", "vuoto", None, None
        righe.append({
            "key": p["key"], "name": p["name"], "area": area, "cosa": cosa,
            "fonte": fonte, "task_id": task_id, "scadenza": scadenza,
            "ultima_attivita": p["last_activity"],
        })
    # Sort stabile, dal criterio meno importante al più importante: l'ultimo
    # sort è quello che decide per primo.
    righe.sort(key=lambda r: r["ultima_attivita"] or "", reverse=True)
    righe.sort(key=lambda r: r["scadenza"] or "￿")
    righe.sort(key=lambda r: 0 if r["scadenza"] else 1)
    righe.sort(key=lambda r: 1 if r["fonte"] == "vuoto" else 0)
    if limite:
        righe = righe[:limite]
    return righe


def _prefisso_path(valore: str, cwd: str) -> bool:
    """valore è prefisso di cwd sui confini di cartella (non su una
    sottostringa qualunque: '/a/bar' non è sotto '/a/b')."""
    return attribuzione.e_dentro(valore, cwd)


def padre_per_path(conn, cwd):
    """La radice (auto=0, senza padre) a cui appartiene `cwd`, o None.

    Per L1-INGEST: la scheda nuova nasce già con questo come parent_id,
    senza passare da `set_parent`. Deve quindi essere sempre un progetto di
    profondità 0 (una radice), mai un suo figlio: altrimenti la scheda
    nuova nascerebbe nipote, profondità 2, che `albero()` non mostra mai
    (non è una radice e non è figlio di una radice).

    Due regole indipendenti, entrambe su un progetto manuale (auto=0):
    1. un `project_links` di kind `path` che è prefisso di cwd. Non `repo`:
       quel kind tiene il nome del repository GitHub, non un percorso
       (ingest.py:755, init_seed.py:48); il link col path di un repo locale
       è comunque un link `path` (ingest.py:892), quindi `path` da solo
       basta;
    2. la chiave, seguita da un trattino, è prefisso del nome della
       cartella (`vesuvius` trova `vesuvius-agosto-2026`, non `vesuviusx`).

    Se più manuali combaciano (da una regola o dall'altra), vince quello con
    il prefisso più lungo (path e nome sono metri diversi: qui si sceglie
    di confrontarli comunque, il che dà la precedenza al link più specifico
    quando i due tipi di match convivono sullo stesso cwd). Se il manuale
    che vince ha già un padre (è il figlio di una radice, es. `op6-causal`
    sotto `vesuvius`), si risale alla radice: mai un figlio.
    """
    if not cwd:
        return None
    cwd = attribuzione.senza_barra_finale(str(cwd))
    cartella = attribuzione.nome_cartella(cwd)
    manuali = conn.execute("SELECT * FROM projects WHERE auto=0").fetchall()
    migliore, punteggio = None, -1
    for m in manuali:
        link_rows = conn.execute(
            "SELECT value FROM project_links WHERE project_id=? AND kind='path'",
            (m["id"],),
        ).fetchall()
        for l in link_rows:
            valore = attribuzione.senza_barra_finale(l["value"] or "")
            if valore and _prefisso_path(valore, cwd) and len(valore) > punteggio:
                migliore, punteggio = m, len(valore)
        if cartella.startswith(m["key"] + "-") and len(m["key"]) > punteggio:
            migliore, punteggio = m, len(m["key"])
    if migliore is None:
        return None
    if migliore["parent_id"]:
        radice = conn.execute(
            "SELECT key FROM projects WHERE id=?", (migliore["parent_id"],)
        ).fetchone()
        return radice["key"] if radice else None
    return migliore["key"]
