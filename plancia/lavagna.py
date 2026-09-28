"""La lavagna: tutti i task aperti, di chiunque, in un posto solo.

Ogni agente tiene la sua lista da un'altra parte e con un altro nome. Claude
Code scrive un file JSON per task in `~/.claude/tasks/<sessione>/`. Codex tiene
gli obiettivi in un SQLite, `~/.codex/goals_1.sqlite`. Plancia ha i suoi.

Nessuna di queste liste sa dell'altra, quindi non esiste un posto dove vedere
cosa è aperto. Questo modulo le legge tutte, normalizza gli stati e le mette in
una tabella sola. Le fonti restano di sola lettura: la lavagna è una vista, non
un padrone.
"""

import json
import os
import sqlite3
from pathlib import Path

from . import config, store

TASK_CLAUDE = config.CLAUDE_DIR / "tasks"
GOALS_CODEX = Path(os.environ.get("CODEX_HOME", config.HOME / ".codex")) / "goals_1.sqlite"

# Ogni agente chiama gli stati a modo suo. Qui diventano quattro parole sole.
STATI_CLAUDE = {"pending": "aperto", "in_progress": "in corso",
                "completed": "fatto", "deleted": "sparito"}
STATI_CODEX = {"active": "in corso", "paused": "aperto", "blocked": "bloccato",
               "usage_limited": "bloccato", "budget_limited": "bloccato",
               "complete": "fatto"}
STATI_PLANCIA = {"aperto": "aperto", "in corso": "in corso", "bloccato": "bloccato",
                 "fatto": "fatto", "archiviato": "sparito"}

APERTI = ("aperto", "in corso", "bloccato")


# --------------------------------------------------------------------------
# le tre fonti
# --------------------------------------------------------------------------

def da_claude(esito=None, escl=None) -> list:
    """Un file per task, una cartella per sessione.

    `esito` è un dizionario in cui si segna se la lettura è riuscita. Serve a
    chi cancella: una fonte che non ha risposto non vuol dire che le sue voci
    non esistono più.

    `escl` (l'insieme calcolato da `esclusi.carica()`) salta le cartelle il
    cui nome — l'id della sessione, qui è sempre l'id nudo, senza percorso —
    è fra le sessioni escluse: configurate a mano o scoperte a runtime (una
    sessione aperta in una cartella privata, o spostata lì durante il lavoro:
    vedi plancia/esclusi.py e ingest.sync_sessions). Un todo puo' essere
    rivelatore quanto una trascrizione.
    """
    fuori = []
    if not TASK_CLAUDE.is_dir():
        if esito is not None:
            esito["ok"] = False
        return fuori
    sessioni_escluse = (escl or {}).get("sessioni") or ()
    for cartella in sorted(TASK_CLAUDE.iterdir()):
        if not cartella.is_dir():
            continue
        sessione = cartella.name
        if sessione in sessioni_escluse:
            continue
        for f in sorted(cartella.glob("*.json")):
            try:
                d = json.loads(f.read_text("utf-8"))
            except Exception:
                continue
            titolo = (d.get("subject") or "").strip()
            if not titolo:
                continue
            fuori.append({
                "fonte": "claude",
                "chiave": f"{sessione}:{d.get('id') or f.stem}",
                "titolo": titolo,
                "dettaglio": (d.get("description") or "").strip(),
                "stato": STATI_CLAUDE.get(d.get("status"), "aperto"),
                "stato_origine": d.get("status") or "",
                "agente": "claude",
                "sessione": sessione,
                "aggiornato_at": store.now() if not f.exists() else
                                 _iso(f.stat().st_mtime),
            })
    return fuori


def da_codex(esito=None, escl=None) -> list:
    """Gli obiettivi di Codex, letti dal suo SQLite senza toccarlo.

    `escl`: salta gli obiettivi il cui `thread_id` è fra le sessioni escluse
    (l'obiettivo di Codex è la richiesta intera dell'utente: è testo quanto
    o più di un todo di Claude Code).
    """
    if not GOALS_CODEX.exists():
        if esito is not None:
            esito["ok"] = False
        return []
    try:
        conn = sqlite3.connect(f"file:{GOALS_CODEX}?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        righe = conn.execute(
            "SELECT thread_id, goal_id, objective, status, tokens_used, "
            "time_used_seconds, created_at_ms, updated_at_ms FROM thread_goals").fetchall()
        conn.close()
    except Exception:
        # Il database di Codex può essere occupato mentre lui scrive: è un
        # inciampo, non una lista vuota.
        if esito is not None:
            esito["ok"] = False
        return []
    sessioni_escluse = (escl or {}).get("sessioni") or ()
    fuori = []
    for r in righe:
        if r["thread_id"] in sessioni_escluse:
            continue
        obiettivo = (r["objective"] or "").strip()
        if not obiettivo:
            continue
        # L'obiettivo di Codex è la richiesta intera dell'utente: come titolo
        # si prende la prima frase, il resto va nel dettaglio.
        titolo = obiettivo.split(". ")[0][:120].strip()
        fuori.append({
            "fonte": "codex",
            "chiave": r["goal_id"],
            "titolo": titolo,
            "dettaglio": obiettivo[len(titolo):].strip()[:1200],
            "stato": STATI_CODEX.get(r["status"], "aperto"),
            "stato_origine": r["status"] or "",
            "agente": "codex",
            "sessione": r["thread_id"],
            "creato_at": _da_ms(r["created_at_ms"]),
            "aggiornato_at": _da_ms(r["updated_at_ms"]),
            "costo": r["tokens_used"] or 0,
        })
    return fuori


def da_plancia(conn) -> list:
    # `sessione` viene da `tasks.session_id` (L0-SESSIONE, poi il backfill di
    # L2-RIPRENDI per i task più vecchi): prima era sempre "", e riprendi.py
    # non aveva niente da leggere per calcolare lo stato di un task della
    # lavagna, nemmeno per i task che una sessione ce l'hanno per davvero.
    righe = conn.execute(
        "SELECT id, title, body, status, project_id, created_at, updated_at, agent, "
        "session_id FROM tasks").fetchall()
    return [{
        "fonte": "plancia",
        "chiave": str(r["id"]),
        "titolo": r["title"],
        "dettaglio": r["body"] or "",
        "stato": STATI_PLANCIA.get(r["status"], "aperto"),
        "stato_origine": r["status"],
        "agente": r["agent"] or "",
        "sessione": r["session_id"] or "",
        "project_id": r["project_id"],
        "task_id": r["id"],
        "creato_at": r["created_at"],
        "aggiornato_at": r["updated_at"],
    } for r in righe]


def _iso(ts) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _da_ms(ms) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


# --------------------------------------------------------------------------
# la lavagna
# --------------------------------------------------------------------------

def sync(conn, progress=None, escl=None) -> int:
    """Rilegge le tre liste e le riscrive nella lavagna.

    Le voci che una fonte non riporta più vengono tolte: se hai cancellato un
    task in Claude Code non deve restare qui a fare finta di esistere.

    `escl`, se non dato, si calcola da sé (`esclusi.carica(conn=conn)`): chi
    chiama da `ingest.sync()` passa invece quello già calcolato una volta per
    tutto il giro (che include anche gli id scoperti a runtime nello STESSO
    giro, per esempio da `sync_sessions` un momento prima).
    """
    # Un archivio dimostrativo non deve andare a leggere le liste vere della
    # macchina: serve a far vedere l'interfaccia, non il lavoro di chi guarda.
    if store.get_meta(conn, "demo") == "1":
        return 0

    from . import esclusi as _esclusi, ingest
    escl = escl if escl is not None else _esclusi.carica(conn=conn)
    esiti = {"claude": {"ok": True}, "codex": {"ok": True}, "plancia": {"ok": True}}
    voci = (da_claude(esiti["claude"], escl) + da_codex(esiti["codex"], escl)
            + da_plancia(conn))

    # dove possibile la voce eredita il progetto della sessione che l'ha creata
    per_sessione = {r["session_id"]: r["project_id"] for r in conn.execute(
        "SELECT session_id, project_id FROM sessions WHERE project_id IS NOT NULL")}

    viste = set()
    for v in voci:
        if v.get("project_id") is None and v.get("sessione"):
            v["project_id"] = per_sessione.get(v["sessione"])
        viste.add((v["fonte"], v["chiave"]))
        conn.execute(
            "INSERT INTO agenda(fonte, chiave, titolo, dettaglio, stato, stato_origine, "
            "agente, sessione, project_id, task_id, creato_at, aggiornato_at, visto_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(fonte, chiave) DO UPDATE SET titolo=excluded.titolo, "
            "dettaglio=excluded.dettaglio, stato=excluded.stato, "
            "stato_origine=excluded.stato_origine, agente=excluded.agente, "
            "sessione=excluded.sessione, "
            "project_id=COALESCE(excluded.project_id, agenda.project_id), "
            "task_id=COALESCE(excluded.task_id, agenda.task_id), "
            "aggiornato_at=excluded.aggiornato_at, visto_at=excluded.visto_at",
            (v["fonte"], v["chiave"], v["titolo"], v.get("dettaglio", ""), v["stato"],
             v.get("stato_origine", ""), v.get("agente", ""), v.get("sessione", ""),
             v.get("project_id"), v.get("task_id"), v.get("creato_at") or store.now(),
             v.get("aggiornato_at") or store.now(), store.now()))

    presenti = conn.execute("SELECT fonte, chiave FROM agenda").fetchall()
    tolte = 0
    for r in presenti:
        # Se la fonte non ha risposto non si tocca niente di suo: cancellare le
        # voci di Codex perché il suo database era occupato per un secondo vuol
        # dire far sparire dalla lavagna lavoro che c'è.
        if not esiti.get(r["fonte"], {"ok": True}).get("ok", True):
            continue
        if (r["fonte"], r["chiave"]) not in viste:
            conn.execute("DELETE FROM agenda WHERE fonte=? AND chiave=?",
                         (r["fonte"], r["chiave"]))
            tolte += 1
    conn.commit()
    ingest.log(f"lavagna: {len(voci)} voci, {tolte} sparite", progress)
    return len(voci)


def elenco(conn, stato="aperti", fonte=None, limite=200) -> list:
    sql = ("SELECT a.*, p.name AS progetto, p.key AS progetto_chiave "
           "FROM agenda a LEFT JOIN projects p ON p.id=a.project_id WHERE 1=1")
    params = []
    if stato == "aperti":
        sql += f" AND a.stato IN ({','.join('?' * len(APERTI))})"
        params += list(APERTI)
    elif stato and stato != "tutti":
        sql += " AND a.stato=?"
        params.append(stato)
    if fonte:
        sql += " AND a.fonte=?"
        params.append(fonte)
    sql += (" ORDER BY CASE a.stato WHEN 'in corso' THEN 0 WHEN 'bloccato' THEN 1 "
            "WHEN 'aperto' THEN 2 ELSE 3 END, a.aggiornato_at DESC LIMIT ?")
    params.append(int(limite))
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def conteggi(conn) -> dict:
    fuori = {}
    for r in conn.execute(
            "SELECT fonte, stato, COUNT(*) n FROM agenda GROUP BY fonte, stato"):
        fuori.setdefault(r["fonte"], {})[r["stato"]] = r["n"]
    for fonte in ("plancia", "claude", "codex"):
        d = fuori.setdefault(fonte, {})
        d["aperti"] = sum(d.get(s, 0) for s in APERTI)
    return fuori
