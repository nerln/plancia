"""Il briefing: cosa deve sapere una sessione di Claude appena si apre.

Viene scritto su file a ogni sync e a ogni scrittura, così l'hook SessionStart
lo legge in un millisecondo invece di aprire il database.
"""

from datetime import datetime, timedelta, timezone

from . import config, store

PRIORITY = {1: "alta", 2: "media", 3: "bassa"}


def _ago(ts: str) -> str:
    if not ts:
        return "mai"
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    except ValueError:
        return ts[:10]
    delta = datetime.now(timezone.utc) - when
    if delta < timedelta(minutes=90):
        return f"{int(delta.total_seconds() // 60)} min fa"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)} ore fa"
    if delta.days == 1:
        return "ieri"
    if delta.days < 30:
        return f"{delta.days} giorni fa"
    return ts[:10]


def _corto(testo: str, quanti: int) -> str:
    """Taglia a fine parola, non a meta'.

    Il briefing tagliava a carattere fisso e produceva righe che finivano in
    "sectio" e "messa": costavano i token per intero e si leggevano male.
    """
    testo = " ".join((testo or "").split())
    if len(testo) <= quanti:
        return testo
    return testo[:quanti].rsplit(" ", 1)[0] + "…"


def build(conn=None, project=None, limit_projects=6, esteso=True) -> str:
    """Il quadro della situazione.

    `esteso=False` e' quello che entra in ogni sessione di Claude Code e di
    Codex, e li' ogni riga si paga una volta per sessione. Misurato il 9 agosto
    2026: la versione lunga costava ~700 token in ognuna delle 696 sessioni che
    l'hanno ricevuta, cioe' mezzo milione, e la riga piu' cara era un
    `next_action` da 430 caratteri sul paper, presente anche nelle sessioni che
    con il paper non c'entravano niente.

    Quindi la versione corta dice quel che serve a orientarsi e si ferma. Chi ha
    bisogno del resto lo chiede, e lo paga una volta sola.
    """
    if not esteso:
        return _sintesi(conn, project, limit_projects)
    close = False
    if conn is None:
        conn = store.connect()
        store.init_db(conn)
        close = True
    try:
        lines = []
        today = datetime.now().strftime("%d/%m/%Y")
        lines.append(f"# Plancia · {today}")

        where = "WHERE p.status='attivo' AND p.hidden=0"
        params = []
        if project:
            row = store.get_project(conn, project)
            if row:
                where = "WHERE p.id=?"
                params = [row["id"]]
        projects = conn.execute(
            f"SELECT p.*, (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id "
            f"AND t.status IN ('aperto','in corso','bloccato')) AS open_tasks "
            f"FROM projects p {where} "
            f"ORDER BY p.pinned DESC, p.priority ASC, p.last_activity DESC LIMIT ?",
            params + [limit_projects],
        ).fetchall()
        if projects:
            lines.append("\n## Progetti attivi")
            for p in projects:
                bits = [f"ultimo lavoro {_ago(p['last_activity'])}"]
                if p["open_tasks"]:
                    bits.append(f"{p['open_tasks']} task aperti")
                lines.append(f"- **{p['name']}** ({p['key']}) · {', '.join(bits)}")
                if p["next_action"]:
                    lines.append(f"  → prossimo passo: {p['next_action']}")

        tasks = conn.execute(
            "SELECT t.*, p.name AS pname FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
            "WHERE t.status IN ('in corso','aperto','bloccato') "
            "ORDER BY CASE t.status WHEN 'in corso' THEN 0 WHEN 'bloccato' THEN 1 ELSE 2 END, "
            "t.priority ASC, t.due IS NULL, t.due ASC LIMIT 10"
        ).fetchall()
        if tasks:
            lines.append("\n## Task aperti")
            for t in tasks:
                tag = f" [{t['pname']}]" if t["pname"] else ""
                due = f" · scade {t['due']}" if t["due"] else ""
                state = "" if t["status"] == "aperto" else f" ({t['status']})"
                lines.append(f"- #{t['id']} {t['title']}{tag}{state}{due}")

        posts = conn.execute(
            "SELECT id, platform, status, substr(text,1,70) AS text FROM posts "
            "WHERE status IN ('idea','bozza','approvato','programmato') "
            "ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        if posts:
            lines.append("\n## Social in coda")
            for o in posts:
                lines.append(f"- #{o['id']} [{o['platform']}·{o['status']}] {o['text']}…")

        events = conn.execute(
            "SELECT e.ts, e.kind, e.title, p.name AS pname FROM events e "
            "LEFT JOIN projects p ON p.id=e.project_id "
            "WHERE e.kind IN ('sessione','commit','post','task') "
            f"AND {store.visibile('e')} ORDER BY e.ts DESC LIMIT 5"
        ).fetchall()
        if events:
            lines.append("\n## Ultima attività")
            for e in events:
                tag = f" [{e['pname']}]" if e["pname"] else ""
                lines.append(f"- {_ago(e['ts'])} · {e['kind']}: {(e['title'] or '')[:70]}{tag}")

        lines.append(
            "\nPlancia è l'archivio del suo lavoro con l'IA. Usa i tool `plancia_*` "
            "per leggere il contesto, aggiungere task, registrare quello che fai e i post "
            "sociali. Dashboard: http://127.0.0.1:%d" % config.load_config().get("port", 7773)
        )
        return "\n".join(lines)
    finally:
        if close:
            conn.close()


def _sintesi(conn=None, project=None, limit_projects=4) -> str:
    """Il briefing che entra in ogni sessione. Tetti duri su tutto."""
    close = False
    if conn is None:
        conn = store.connect()
        store.init_db(conn)
        close = True
    try:
        righe = [f"# Plancia · {datetime.now().strftime('%d/%m/%Y')}"]

        dove = "WHERE p.status='attivo' AND p.hidden=0"
        params = []
        if project:
            riga = store.get_project(conn, project)
            if riga:
                dove, params = "WHERE p.id=?", [riga["id"]]
        progetti = conn.execute(
            f"SELECT p.name, p.key, p.last_activity, p.next_action, "
            f"(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND "
            f"t.status IN ('aperto','in corso','bloccato')) AS aperti "
            f"FROM projects p {dove} "
            f"ORDER BY p.pinned DESC, p.priority ASC, p.last_activity DESC LIMIT ?",
            # Il tetto lo mette questa funzione, non chi la chiama: e' l'unica
            # ragione per cui esiste.
            params + [min(limit_projects, 4)],
        ).fetchall()
        for p in progetti:
            coda = f", {p['aperti']} task" if p["aperti"] else ""
            righe.append(f"- {p['name']} ({p['key']}) · {_ago(p['last_activity'])}{coda}")
            if p["next_action"]:
                righe.append(f"  → {_corto(p['next_action'], 110)}")

        task = conn.execute(
            "SELECT t.id, t.title, t.due, p.name AS pname FROM tasks t "
            "LEFT JOIN projects p ON p.id=t.project_id "
            "WHERE t.status IN ('in corso','aperto','bloccato') "
            "ORDER BY CASE t.status WHEN 'in corso' THEN 0 WHEN 'bloccato' THEN 1 ELSE 2 END, "
            "t.priority ASC, t.due IS NULL, t.due ASC LIMIT 4"
        ).fetchall()
        aperti = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status IN ('in corso','aperto','bloccato')"
        ).fetchone()[0]
        if task:
            resto = f", altri {aperti - len(task)}" if aperti > len(task) else ""
            righe.append(f"\nTask ({aperti}{resto}):")
            for t in task:
                tag = f" [{t['pname']}]" if t["pname"] else ""
                scade = f" · scade {t['due']}" if t["due"] else ""
                righe.append(f"- #{t['id']} {_corto(t['title'], 62)}{tag}{scade}")

        righe.append("\nIl resto: tool `plancia`, azione=briefing.")
        return "\n".join(righe)
    finally:
        if close:
            conn.close()


def write_cache() -> str:
    """Scrive il file che l'hook di SessionStart infila in ogni sessione.

    Qui va la versione corta, e il motivo e' aritmetico: questo file entra nel
    contesto di ogni sessione di Claude Code e di Codex, quindi ogni riga si paga
    tante volte quante sessioni apri. La versione lunga resta a un tool di
    distanza per chi la vuole davvero.
    """
    text = build(esteso=False)
    config.ensure_dirs()
    config.BRIEFING_FILE.write_text(text, "utf-8")
    return text
