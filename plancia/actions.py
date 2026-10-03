"""Le scritture. Un solo posto per API HTTP e server MCP, così le due strade
non divergono mai.
"""

import json

from . import briefing, eventi, lavagna, store

TASK_STATES = ["aperto", "in corso", "bloccato", "fatto", "archiviato"]
POST_STATES = ["idea", "bozza", "approvato", "programmato", "pubblicato", "scartato"]
PROJECT_STATES = ["attivo", "in pausa", "concluso", "idea", "archiviato"]


class BadInput(ValueError):
    pass


def _chiave(conn, project_id):
    """La chiave del progetto, che è quello che serve a chi legge da fuori."""
    if not project_id:
        return None
    r = conn.execute("SELECT key FROM projects WHERE id=?", (project_id,)).fetchone()
    return r["key"] if r else None


def _project_id(conn, ident):
    if ident in (None, "", 0):
        return None
    row = store.get_project(conn, ident)
    return row["id"] if row else None


def _after_write(conn):
    conn.commit()
    try:
        briefing.write_cache()
    except Exception:
        pass


# --------------------------------------------------------------------------
# task
# --------------------------------------------------------------------------

def task_add(conn, title, body="", project=None, priority=2, due=None, tags="",
             source="manuale", session_id=None, cwd=None, agent=None, host=None,
             compartimento="") -> dict:
    title = (title or "").strip()
    if not title:
        raise BadInput("il titolo del task non può essere vuoto")
    pid = _project_id(conn, project)
    ts = store.now()
    # cwd e agent sono nello schema da prima di questo lotto (store.py, colonne
    # aggiunte via AGGIUNTE["tasks"]) ma nessun chiamante le scriveva mai: sono
    # morte nel codice, vive nel dato (docs/RICOGNIZIONE-dati-mcp-hook.md,
    # punto 1). host la aggiunge L0-SCHEMA: si scrive solo se la colonna esiste
    # già, così questo file non si rompe finché quel lotto non è fuso.
    colonne = ["title", "body", "status", "priority", "project_id", "due", "tags",
               "source", "session_id", "created_at", "updated_at"]
    valori = [title, body or "", "aperto", int(priority or 2), pid, due, tags or "",
              source, session_id, ts, ts]
    if cwd is not None:
        colonne.append("cwd")
        valori.append(cwd)
    if agent is not None:
        colonne.append("agent")
        valori.append(agent)
    if host is not None and any(r["name"] == "host" for r in
                                conn.execute("PRAGMA table_info(tasks)")):
        colonne.append("host")
        valori.append(host)
    if compartimento:
        # assegnato a mano (dashboard, o un agente di un compartimento nominato):
        # si somma alla sessione e al progetto, vedi compartimenti_viste.py
        colonne.append("compartimento")
        valori.append(compartimento)
    segnaposto = ",".join("?" for _ in colonne)
    cur = conn.execute(
        "INSERT INTO tasks(%s) VALUES(%s)" % (",".join(colonne), segnaposto), valori)
    tid = cur.lastrowid
    store.add_event(conn, ts, "task", f"task creato: {title}", body[:200], pid,
                    f"task:{tid}", source, dedup=f"task-new:{tid}")
    eventi.scrivi("task.creato", title, _chiave(conn, pid), {"id": tid, "fonte": source})
    lavagna.aggiorna_plancia(conn, tid)
    _after_write(conn)
    return task_get(conn, tid)


def task_get(conn, tid) -> dict:
    row = conn.execute(
        "SELECT t.*, p.name AS project, p.key AS project_key FROM tasks t "
        "LEFT JOIN projects p ON p.id=t.project_id WHERE t.id=?", (tid,)
    ).fetchone()
    return dict(row) if row else None


def task_update(conn, tid, **fields) -> dict:
    current = task_get(conn, tid)
    if not current:
        raise BadInput(f"task {tid} inesistente")
    updates, values = [], []
    if "status" in fields and fields["status"]:
        status = fields["status"].strip().lower()
        if status not in TASK_STATES:
            raise BadInput(f"stato non valido: {status}. Ammessi: {', '.join(TASK_STATES)}")
        updates.append("status=?")
        values.append(status)
        updates.append("done_at=?")
        values.append(store.now() if status == "fatto" else None)
    for col in ("title", "body", "due", "tags"):
        if fields.get(col) is not None:
            updates.append(f"{col}=?")
            values.append(fields[col])
    if fields.get("priority") is not None:
        updates.append("priority=?")
        values.append(int(fields["priority"]))
    if "project" in fields and fields["project"] is not None:
        updates.append("project_id=?")
        values.append(_project_id(conn, fields["project"]))
    if not updates:
        return current
    ts = store.now()
    values.extend([ts, tid])
    conn.execute(f"UPDATE tasks SET {', '.join(updates)}, updated_at=? WHERE id=?", values)
    row = task_get(conn, tid)
    if fields.get("status") == "fatto":
        store.add_event(conn, ts, "task", f"task chiuso: {row['title']}", "",
                        row["project_id"], f"task:{tid}", "plancia", dedup=f"task-done:{tid}")
        eventi.scrivi("task.chiuso", row["title"], _chiave(conn, row["project_id"]),
                      {"id": tid})
    lavagna.aggiorna_plancia(conn, tid)
    _after_write(conn)
    return row


def tasks_list(conn, status=None, project=None, limit=50) -> list:
    sql = ("SELECT t.*, p.name AS project, p.key AS project_key FROM tasks t "
           "LEFT JOIN projects p ON p.id=t.project_id WHERE 1=1")
    params = []
    if status == "aperti" or status is None:
        sql += " AND t.status IN ('aperto','in corso','bloccato')"
    elif status != "tutti":
        sql += " AND t.status=?"
        params.append(status)
    if project:
        sql += " AND t.project_id=?"
        params.append(_project_id(conn, project))
    sql += (" ORDER BY CASE t.status WHEN 'in corso' THEN 0 WHEN 'bloccato' THEN 1 "
            "WHEN 'aperto' THEN 2 ELSE 3 END, t.priority ASC, t.due IS NULL, t.due ASC, "
            "t.updated_at DESC LIMIT ?")
    params.append(int(limit))
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# --------------------------------------------------------------------------
# post
# --------------------------------------------------------------------------

def post_add(conn, text, platform="x", status="bozza", project=None, url=None,
             source_ref="", scheduled_for=None, session_id=None, media="",
             compartimento="") -> dict:
    text = (text or "").strip()
    if not text:
        raise BadInput("il testo del post non può essere vuoto")
    status = (status or "bozza").lower()
    if status not in POST_STATES:
        raise BadInput(f"stato non valido: {status}. Ammessi: {', '.join(POST_STATES)}")
    ts = store.now()
    pid = _project_id(conn, project)
    cur = conn.execute(
        "INSERT INTO posts(platform, status, text, url, project_id, source_ref, "
        "scheduled_for, published_at, session_id, media, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (platform, status, text, url, pid, source_ref or "", scheduled_for,
         ts if status == "pubblicato" else None, session_id, media or "", ts, ts),
    )
    oid = cur.lastrowid
    if compartimento:
        conn.execute("UPDATE posts SET compartimento=? WHERE id=?", (compartimento, oid))
    store.add_event(conn, ts, "post", f"post {status}: {text[:60]}", platform, pid,
                    f"post:{oid}", "plancia", dedup=f"post-new:{oid}")
    _after_write(conn)
    return post_get(conn, oid)


def post_get(conn, oid) -> dict:
    row = conn.execute(
        "SELECT o.*, p.name AS project, p.key AS project_key FROM posts o "
        "LEFT JOIN projects p ON p.id=o.project_id WHERE o.id=?", (oid,)
    ).fetchone()
    return dict(row) if row else None


def post_update(conn, oid, **fields) -> dict:
    current = post_get(conn, oid)
    if not current:
        raise BadInput(f"post {oid} inesistente")
    updates, values = [], []
    if fields.get("status"):
        status = fields["status"].lower()
        if status not in POST_STATES:
            raise BadInput(f"stato non valido: {status}. Ammessi: {', '.join(POST_STATES)}")
        updates.append("status=?")
        values.append(status)
        if status == "pubblicato":
            updates.append("published_at=?")
            values.append(fields.get("published_at") or store.now())
    for col in ("text", "url", "source_ref", "scheduled_for", "platform", "media"):
        if fields.get(col) is not None:
            updates.append(f"{col}=?")
            values.append(fields[col])
    if fields.get("metrics") is not None:
        updates.append("metrics=?")
        values.append(json.dumps(fields["metrics"]) if not isinstance(fields["metrics"], str)
                      else fields["metrics"])
    if "project" in fields and fields["project"] is not None:
        updates.append("project_id=?")
        values.append(_project_id(conn, fields["project"]))
    if not updates:
        return current
    ts = store.now()
    values.extend([ts, oid])
    conn.execute(f"UPDATE posts SET {', '.join(updates)}, updated_at=? WHERE id=?", values)
    row = post_get(conn, oid)
    if fields.get("status") == "pubblicato":
        store.add_event(conn, ts, "post", f"pubblicato su {row['platform']}: {row['text'][:60]}",
                        row["url"] or "", row["project_id"], f"post:{oid}", "plancia",
                        dedup=f"post-pub:{oid}")
        eventi.scrivi("post.pubblicato", row["text"][:120], _chiave(conn, row["project_id"]),
                      {"id": oid, "piattaforma": row["platform"], "url": row["url"]})
    _after_write(conn)
    return row


def posts_list(conn, status=None, platform=None, limit=100) -> list:
    sql = ("SELECT o.*, p.name AS project, p.key AS project_key FROM posts o "
           "LEFT JOIN projects p ON p.id=o.project_id WHERE 1=1")
    params = []
    if status and status != "tutti":
        sql += " AND o.status=?"
        params.append(status)
    if platform:
        sql += " AND o.platform=?"
        params.append(platform)
    sql += " ORDER BY o.updated_at DESC LIMIT ?"
    params.append(int(limit))
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# --------------------------------------------------------------------------
# progetti ed eventi
# --------------------------------------------------------------------------

def project_update(conn, ident, **fields) -> dict:
    row = store.get_project(conn, ident)
    if not row:
        raise BadInput(f"progetto '{ident}' inesistente")
    updates, values = [], []
    if fields.get("status"):
        if fields["status"] not in PROJECT_STATES:
            raise BadInput(f"stato non valido. Ammessi: {', '.join(PROJECT_STATES)}")
        updates.append("status=?")
        values.append(fields["status"])
    for col in ("summary", "next_action", "name", "kind"):
        if fields.get(col) is not None:
            updates.append(f"{col}=?")
            values.append(fields[col])
    for col in ("priority", "pinned", "hidden"):
        if fields.get(col) is not None:
            updates.append(f"{col}=?")
            values.append(int(fields[col]))
    if not updates:
        return dict(row)
    values.extend([store.now(), row["id"]])
    conn.execute(f"UPDATE projects SET {', '.join(updates)}, updated_at=? WHERE id=?", values)
    if fields.get("status") == "archiviato":
        eventi.scrivi("progetto.archiviato", row["name"], row["key"], {})
    elif fields.get("next_action"):
        eventi.scrivi("progetto.aggiornato", row["name"], row["key"],
                      {"prossimo_passo": fields["next_action"]})
    _after_write(conn)
    return dict(conn.execute("SELECT * FROM projects WHERE id=?", (row["id"],)).fetchone())


def project_create(conn, name, key=None, kind="progetto", summary="", priority=2,
                   compartimento="") -> dict:
    if not (name or "").strip():
        raise BadInput("serve un nome")
    pid = store.upsert_project(conn, key or name, name.strip(), kind=kind,
                               summary=summary, priority=priority, auto=0, _force=True)
    if compartimento:
        conn.execute("UPDATE projects SET compartimento=? WHERE id=?", (compartimento, pid))
    _after_write(conn)
    return dict(conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())


def log_event(conn, title, kind="nota", detail="", project=None, ref=None,
              source="claude", compartimento="") -> dict:
    if not (title or "").strip():
        raise BadInput("serve un titolo")
    ts = store.now()
    pid = _project_id(conn, project)
    store.add_event(conn, ts, kind, title.strip(), detail or "", pid, ref, source,
                    dedup=f"{source}:{kind}:{title[:60]}:{ts}", compartimento=compartimento)
    if pid:
        store.touch_project(conn, pid, ts)
    _after_write(conn)
    return {"ts": ts, "kind": kind, "title": title, "project_id": pid}
