"""Prove per L5-STAGNANTE: il posto riservato di task_stagnante nel taglio
finale di proposte.calcola() (decisione dell'utente del 28/09, voce 8 del
DECIDE in docs/CANTIERE-2026-09.md).

Stessa disciplina di tools/prove/briefing-aree.py: un archivio SQLite in
memoria per prova, mai il database vero. Vedi tools/prove/README.md per
come questo file viene scoperto.
"""

import sqlite3
from datetime import datetime, timedelta, timezone


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


def _giorni_fa(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ore_fa(n):
    return (datetime.now(timezone.utc) - timedelta(hours=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _task(conn, project_id, title, status="aperto", updated_at=None):
    from plancia import store
    ts = store.now()
    conn.execute(
        "INSERT INTO tasks(title, status, project_id, created_at, updated_at) "
        "VALUES(?,?,?,?,?)",
        (title, status, project_id, ts, updated_at or ts),
    )
    conn.commit()


def _cinque_urgenti(conn, pid):
    """Una proposta per ciascuno dei controlli 1-5 di proposte.calcola,
    tutte più urgenti di task_stagnante (urgenza 0-4 contro 7), tutte sullo
    stesso progetto attivo."""
    from plancia import store

    # 1. lancio_fallito (urgenza 0)
    conn.execute(
        "INSERT INTO runs(agente, modo, prompt, cwd, stato, inizio, fine) "
        "VALUES('claude','proposta','lancio di prova','~/dev/x','fallito',?,?)",
        (_ore_fa(2), _ore_fa(1)))

    # 2. codex_bloccato (urgenza 1)
    conn.execute(
        "INSERT INTO agenda(fonte, chiave, titolo, stato, stato_origine, project_id, "
        "creato_at, aggiornato_at) "
        "VALUES('codex','c1','obiettivo bloccato','bloccato','blocked',?,?,?)",
        (pid, store.now(), store.now()))

    # 3. non_committato (urgenza 2)
    conn.execute(
        "INSERT INTO repos(name, dirty, project_id, updated_at) VALUES('repo-x',3,?,?)",
        (pid, store.now()))

    # 4. post_fermo (urgenza 3)
    conn.execute(
        "INSERT INTO posts(platform, status, text, project_id, created_at, updated_at) "
        "VALUES('x','approvato','un post pronto',?,?,?)",
        (pid, store.now(), store.now()))

    # 5. task_fermo (urgenza 4): "in corso" da 4 giorni, non da 30, così non
    # tocca anche il controllo 8 (che vuole 21 giorni) e non si confonde con
    # il task stagnante vero.
    _task(conn, pid, "task in corso da giorni", status="in corso", updated_at=_giorni_fa(4))
    conn.commit()


def _prova_posto_riservato(prova):
    """Con le cinque proposte più urgenti (controlli 1-5) più un task aperto
    non toccato da 30 giorni su un progetto attivo (controllo 8):
    calcola(limite=4) contiene task_stagnante al posto dell'ultima delle
    prime quattro, le altre tre restano le tre più urgenti nello stesso
    ordine; calcola(limite=1) non lo contiene (il posto riservato non vale
    sotto limite 2); senza le cinque proposte più urgenti c'è comunque."""
    from plancia import proposte

    conn = _conn()
    pid = _progetto(conn, "attivo-urgenti", name="AttivoUrgenti", auto=0)
    _cinque_urgenti(conn, pid)
    pid_stagnante = _progetto(conn, "attivo-stagnante", name="AttivoStagnante", auto=0)
    _task(conn, pid_stagnante, "task dimenticato", status="aperto", updated_at=_giorni_fa(30))

    lista4 = proposte.calcola(conn, limite=4)
    motivi4 = [p["motivo"] for p in lista4]
    prova("con limite=4 e cinque proposte più urgenti, task_stagnante c'è",
          "task_stagnante" in motivi4, str(motivi4))
    prova("con limite=4 sono esattamente quattro proposte",
          len(lista4) == 4, str(motivi4))
    prova("con limite=4 le prime tre sono le tre più urgenti, nello stesso ordine",
          motivi4[:3] == ["lancio_fallito", "codex_bloccato", "non_committato"], str(motivi4))
    prova("con limite=4 il posto riservato sta al posto dell'ultima delle prime quattro",
          motivi4[3] == "task_stagnante", str(motivi4))

    lista1 = proposte.calcola(conn, limite=1)
    prova("con limite=1 il posto riservato non vale: task_stagnante non c'è",
          not any(p["motivo"] == "task_stagnante" for p in lista1), str(lista1))
    prova("con limite=1 vince comunque la proposta più urgente",
          len(lista1) == 1 and lista1[0]["motivo"] == "lancio_fallito", str(lista1))

    conn_solo = _conn()
    pid_solo = _progetto(conn_solo, "solo-stagnante", name="SoloStagnante", auto=0)
    _task(conn_solo, pid_solo, "task dimenticato solo", status="aperto", updated_at=_giorni_fa(30))
    lista_solo = proposte.calcola(conn_solo, limite=4)
    prova("senza le cinque proposte più urgenti, task_stagnante c'è comunque",
          any(p["motivo"] == "task_stagnante" for p in lista_solo), str(lista_solo))


def esegui(prova) -> None:
    _prova_posto_riservato(prova)


if __name__ == "__main__":
    import os
    import sys
    import tempfile
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-proposte-stagnante-"))
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
