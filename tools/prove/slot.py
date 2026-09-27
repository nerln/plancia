"""Prove per plancia/slot.py: padre di un progetto, albero, prossimi, path.

Ogni gruppo usa un archivio SQLite in memoria a sé (mai il database vero),
ma non un registro eventi a sé: `eventi.jsonl` vive sotto `PLANCIA_HOME`, che
qui è una sola cartella temporanea per l'intera esecuzione del file (vedi
`__main__` sotto). I nomi di batch usati dai gruppi (`g1`, `b1`, `vecchio`...)
sono quindi unici nell'intero file, non solo dentro il gruppo che li usa:
due esecuzioni di `esegui()` nella stessa `PLANCIA_HOME` (es. se in futuro
prova.py la richiama anche lui) riuserebbero gli stessi nomi e `annulla`
troverebbe eventi doppi. La funzione pubblica è `esegui(prova)`, dove
`prova(nome, condizione, dettaglio)` è la stessa forma usata da
tools/prova.py:32, così, quando L0-PROVE scoprirà questa cartella, il
collaudo gira senza modifiche.
"""

import sqlite3


def _conn():
    from plancia import store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    store.init_db(conn)
    return conn


def _progetto(conn, key, name=None, auto=0, **campi):
    from plancia import store
    pid = store.upsert_project(conn, key, name or key, auto=auto, _force=True, **campi)
    conn.commit()
    return pid


def _prova_migrate(prova):
    from plancia import store

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # store.SCHEMA da solo è esattamente "lo schema di prima": le colonne di
    # AGGIUNTE (parent_id incluso) arrivano solo con migrate().
    conn.executescript(store.SCHEMA)
    prima = {r["name"] for r in conn.execute("PRAGMA table_info(projects)")}
    prova("lo schema pre-migrate non ha parent_id", "parent_id" not in prima, str(prima))

    store.migrate(conn)
    dopo_progetti = {r["name"] for r in conn.execute("PRAGMA table_info(projects)")}
    dopo_task = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    prova("migrate aggiunge projects.parent_id", "parent_id" in dopo_progetti, str(dopo_progetti))
    prova("migrate aggiunge tasks.host", "host" in dopo_task, str(dopo_task))

    try:
        store.migrate(conn)
        seconda_ok = True
    except Exception as e:  # noqa: BLE001 - qui l'eccezione è il fallimento da riportare
        seconda_ok = False
        dettaglio = repr(e)
    else:
        dettaglio = ""
    prova("una seconda migrate non fallisce", seconda_ok, dettaglio)


def _prova_set_parent(prova):
    from plancia import slot

    conn = _conn()
    vesuvius = _progetto(conn, "vesuvius", auto=0)
    op6 = _progetto(conn, "op6-causal", auto=0)
    harbour = _progetto(conn, "harbour", auto=0)
    atlas = _progetto(conn, "atlas", auto=1)

    r = slot.set_parent(conn, "harbour", "atlas", "g1")
    prova("padre automatico rifiutato", r["ok"] is False, str(r))

    r = slot.set_parent(conn, "vesuvius", "vesuvius", "g1")
    prova("figlio uguale al padre rifiutato", r["ok"] is False, str(r))

    r = slot.set_parent(conn, "op6-causal", "vesuvius", "g1")
    prova("primo figlio assegnato", r["ok"] is True and r["prima"] is None, str(r))

    r = slot.set_parent(conn, "harbour", "op6-causal", "g1")
    prova("nipote rifiutato (il padre ha già un padre)", r["ok"] is False, str(r))

    r = slot.set_parent(conn, "harbour", "vesuvius", "g1")
    prova("un padre con due figli funziona", r["ok"] is True, str(r))

    figli = conn.execute("SELECT COUNT(*) FROM projects WHERE parent_id=?",
                         (vesuvius,)).fetchone()[0]
    prova("vesuvius risulta padre di due progetti", figli == 2, str(figli))

    # ora il figlio-con-figli: vesuvius ha figli, provo a farlo diventare
    # figlio di harbour -> deve essere rifiutato (diventerebbe nipote lui)
    r = slot.set_parent(conn, "vesuvius", "harbour", "g2")
    prova("un progetto con figli non può diventare figlio", r["ok"] is False, str(r))

    r = slot.set_parent(conn, "chiave-a-caso", "vesuvius", "g3")
    prova("chiave inesistente rifiutata senza eccezione", r["ok"] is False, str(r))

    # 'quasar' non è la chiave di nessun progetto: è una sottostringa di
    # 'quasar-mono', che finora non ha padre. store.get_project la
    # risolverebbe per LIKE '%quasar%'; set_parent deve rifiutarla per
    # intero, senza assegnare un padre a quasar-mono per sbaglio.
    quasar = _progetto(conn, "quasar-mono", auto=0)
    r = slot.set_parent(conn, "quasar", "vesuvius", "g4")
    prova("chiave che è sottostringa di una vera è comunque rifiutata",
          r["ok"] is False, str(r))
    riga = conn.execute("SELECT parent_id FROM projects WHERE id=?", (quasar,)).fetchone()
    prova("quasar-mono non ha preso un padre per sottostringa",
          riga["parent_id"] is None, str(dict(riga)))

    r = slot.set_parent(conn, "harbour", "vesuvius", "a,b")
    prova("batch con virgola rifiutato (eventi.leggi lo spezzerebbe)",
          r["ok"] is False, str(r))

    r = slot.set_parent(conn, "harbour", "vesuvius", "  ")
    prova("batch vuoto o di soli spazi rifiutato", r["ok"] is False, str(r))


def _prova_annulla(prova):
    from plancia import slot, store

    conn = _conn()
    vesuvius = _progetto(conn, "vesuvius", auto=0)
    delta = _progetto(conn, "delta", auto=0)
    op6 = _progetto(conn, "op6-causal", auto=0)

    r1 = slot.set_parent(conn, "op6-causal", "vesuvius", "b1")
    prova("batch b1: assegnato", r1["ok"] and r1["prima"] is None, str(r1))

    riga = conn.execute("SELECT parent_id FROM projects WHERE id=?", (op6,)).fetchone()
    prova("op6-causal ha vesuvius come padre", riga["parent_id"] == vesuvius, str(dict(riga)))

    r2 = slot.set_parent(conn, "op6-causal", "delta", "b2")
    prova("batch b2: cambiato padre, prima non è None", r2["ok"] and r2["prima"] == vesuvius, str(r2))

    n = slot.annulla(conn, "b2")
    riga = conn.execute("SELECT parent_id FROM projects WHERE id=?", (op6,)).fetchone()
    prova("annulla(b2) rimette il padre precedente (non NULL)",
          n == 1 and riga["parent_id"] == vesuvius, f"n={n} riga={dict(riga)}")

    n = slot.annulla(conn, "b1")
    riga = conn.execute("SELECT parent_id FROM projects WHERE id=?", (op6,)).fetchone()
    prova("annulla(b1) rimette NULL",
          n == 1 and riga["parent_id"] is None, f"n={n} riga={dict(riga)}")

    n = slot.annulla(conn, "batch-mai-esistito")
    prova("annulla su un batch senza eventi torna 0", n == 0, str(n))

    # Un batch più recente ha già cambiato lo stesso progetto: annullare un
    # batch precedente non deve scavalcarlo.
    delta2 = _progetto(conn, "delta2", auto=0)
    r_vecchio = slot.set_parent(conn, "op6-causal", "vesuvius", "vecchio")
    prova("batch 'vecchio': assegnato", r_vecchio["ok"], str(r_vecchio))
    r_nuovo = slot.set_parent(conn, "op6-causal", "delta2", "nuovo")
    prova("batch 'nuovo': riassegnato sopra 'vecchio'", r_nuovo["ok"], str(r_nuovo))

    n = slot.annulla(conn, "vecchio")
    riga = conn.execute("SELECT parent_id FROM projects WHERE id=?", (op6,)).fetchone()
    prova("annulla di un batch superato da uno più recente non lo scavalca",
          n == 0 and riga["parent_id"] == delta2, f"n={n} riga={dict(riga)}")


def _prova_albero(prova):
    from plancia import slot, store

    conn = _conn()
    vesuvius = _progetto(conn, "vesuvius", auto=0)
    op6 = _progetto(conn, "op6-causal", auto=0)
    solitario = _progetto(conn, "solitario", auto=0)
    slot.set_parent(conn, "op6-causal", "vesuvius", "ga")

    ts = store.now()
    conn.execute(
        "INSERT INTO tasks(title, status, project_id, created_at, updated_at) "
        "VALUES('un task aperto', 'aperto', ?, ?, ?)", (op6, ts, ts),
    )
    conn.execute(
        "INSERT INTO tasks(title, status, project_id, created_at, updated_at) "
        "VALUES('un task fatto', 'fatto', ?, ?, ?)", (op6, ts, ts),
    )
    conn.commit()

    alberi = slot.albero(conn)
    chiavi = {n["key"] for n in alberi}
    prova("albero contiene sia il padre sia il progetto senza figli",
          {"vesuvius", "solitario"} <= chiavi, str(chiavi))

    nodo_solitario = next(n for n in alberi if n["key"] == "solitario")
    prova("un progetto senza figli è un nodo con figli=[]",
          nodo_solitario["figli"] == [], str(nodo_solitario))

    nodo_vesuvius = next(n for n in alberi if n["key"] == "vesuvius")
    prova("vesuvius ha un figlio (op6-causal)",
          len(nodo_vesuvius["figli"]) == 1 and nodo_vesuvius["figli"][0]["key"] == "op6-causal",
          str(nodo_vesuvius["figli"]))
    prova("il task aperto del figlio si somma nel padre",
          nodo_vesuvius["task_aperti"] == 1, str(nodo_vesuvius))


def _prova_prossimi(prova):
    from plancia import slot, store

    conn = _conn()
    con_scadenza = _progetto(conn, "con-scadenza", auto=0, status="attivo")
    recente = _progetto(conn, "toccato-ieri", auto=0, status="attivo",
                        next_action="fai qualcosa")
    vecchio = _progetto(conn, "toccato-una-settimana-fa", auto=0, status="attivo",
                        next_action="fai qualcos'altro")
    vuoto = _progetto(conn, "senza-niente", auto=0, status="attivo")

    ts = store.now()
    conn.execute(
        "INSERT INTO tasks(title, status, due, project_id, created_at, updated_at) "
        "VALUES('con scadenza', 'aperto', '2026-01-01', ?, ?, ?)", (con_scadenza, ts, ts),
    )
    conn.execute("UPDATE projects SET last_activity='2026-09-15T09:00:00Z' WHERE id=?",
                 (recente,))
    conn.execute("UPDATE projects SET last_activity='2026-09-09T09:00:00Z' WHERE id=?",
                 (vecchio,))
    conn.commit()

    righe = slot.prossimi(conn)
    ordine = [r["key"] for r in righe]
    prova("chi ha scadenza viene prima di chi non ce l'ha",
          ordine.index("con-scadenza") < ordine.index("toccato-ieri"), str(ordine))
    prova("a parità, chi è stato toccato più di recente viene prima",
          ordine.index("toccato-ieri") < ordine.index("toccato-una-settimana-fa"), str(ordine))
    prova("chi non ha niente va in fondo", ordine[-1] == "senza-niente", str(ordine))

    riga_scadenza = next(r for r in righe if r["key"] == "con-scadenza")
    prova("la fonte è il task quando c'è un task aperto",
          riga_scadenza["fonte"] == "task" and riga_scadenza["scadenza"] == "2026-01-01",
          str(riga_scadenza))
    riga_vuoto = next(r for r in righe if r["key"] == "senza-niente")
    prova("un progetto senza task e senza next_action ha fonte 'vuoto'",
          riga_vuoto["fonte"] == "vuoto", str(riga_vuoto))


def _prova_padre_per_path(prova):
    from plancia import slot, store

    conn = _conn()
    prova("nessun manuale: None", slot.padre_per_path(conn, "/qualunque/cosa") is None, "")

    vesuvius = _progetto(conn, "vesuvius", auto=0)
    op6 = _progetto(conn, "op6-causal", auto=0)
    store.link_project(conn, vesuvius, "path", "/Users/e/dev/vesuvius-agosto-2026")
    store.link_project(conn, op6, "path", "/Users/e/dev/vesuvius-agosto-2026/tools/op6")
    conn.commit()

    r = slot.padre_per_path(conn, "/Users/e/dev/vesuvius-agosto-2026/src/main.py")
    prova("cwd sotto il path di un manuale trova il manuale", r == "vesuvius", str(r))

    r = slot.padre_per_path(conn, "/altrove/vesuvius-agosto-2026")
    prova("nome cartella 'vesuvius-agosto-2026' trova 'vesuvius' per prefisso col trattino",
          r == "vesuvius", str(r))

    r = slot.padre_per_path(conn, "/altrove/vesuviusx")
    prova("nome cartella 'vesuviusx' (senza trattino) non trova nulla", r is None, str(r))

    r = slot.padre_per_path(conn, "/Users/e/dev/vesuvius-agosto-2026/tools/op6/src")
    prova("il path più lungo vince: op6-causal batte vesuvius sul proprio sottoalbero",
          r == "op6-causal", str(r))

    # Ora op6-causal diventa figlio di vesuvius (profondità 1): il manuale
    # che vince per prefisso più lungo è ancora op6-causal, ma non è più una
    # radice. padre_per_path deve risalire a vesuvius, mai proporre un
    # figlio come padre (altrimenti L1-INGEST creerebbe un nipote).
    r_set = slot.set_parent(conn, "op6-causal", "vesuvius", "gp")
    prova("setup: op6-causal messo sotto vesuvius", r_set["ok"], str(r_set))
    r = slot.padre_per_path(conn, "/Users/e/dev/vesuvius-agosto-2026/tools/op6/src")
    prova("un manuale che è già figlio non viene proposto come padre: risale alla radice",
          r == "vesuvius", str(r))


def esegui(prova) -> None:
    _prova_migrate(prova)
    _prova_set_parent(prova)
    _prova_annulla(prova)
    _prova_albero(prova)
    _prova_prossimi(prova)
    _prova_padre_per_path(prova)


if __name__ == "__main__":
    import os
    import sys
    import tempfile
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-slot-"))
    os.environ["PLANCIA_HOME"] = str(CASA)

    falliti = []
    passati = 0

    def prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print(f"  ok   {nome}")
        else:
            falliti.append(nome)
            print(f"  NO   {nome} {dettaglio}")

    print(f"archivio di prova: {CASA}\n")
    esegui(prova)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
