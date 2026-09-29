"""Schema e accesso al database di Plancia.

Un solo file SQLite in ~/.plancia/plancia.db. Sta fuori da Google Drive di
proposito: un database sincronizzato da Drive si corrompe.
"""

import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone

from . import config

SCHEMA_VERSION = 6

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY,
  key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  kind TEXT DEFAULT 'progetto',
  status TEXT DEFAULT 'attivo',
  priority INTEGER DEFAULT 2,
  pinned INTEGER DEFAULT 0,
  summary TEXT DEFAULT '',
  next_action TEXT DEFAULT '',
  auto INTEGER DEFAULT 1,
  hidden INTEGER DEFAULT 0,
  created_at TEXT,
  updated_at TEXT,
  last_activity TEXT
);

CREATE TABLE IF NOT EXISTS project_links (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  UNIQUE(kind, value)
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  session_id TEXT UNIQUE NOT NULL,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  file TEXT,
  bytes_scanned INTEGER DEFAULT 0,
  file_size INTEGER DEFAULT 0,
  cwd TEXT,
  git_branch TEXT,
  title TEXT,
  first_prompt TEXT,
  started_at TEXT,
  ended_at TEXT,
  n_user INTEGER DEFAULT 0,
  n_assistant INTEGER DEFAULT 0,
  n_tools INTEGER DEFAULT 0,
  models TEXT,
  tools TEXT,
  in_tokens INTEGER DEFAULT 0,
  out_tokens INTEGER DEFAULT 0,
  agent TEXT DEFAULT 'claude',
  scambi INTEGER DEFAULT 0,
  dir_dedotta TEXT,
  dedotto_da TEXT,
  n_percorsi INTEGER DEFAULT 0,
  radici_toccate TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT DEFAULT '',
  status TEXT DEFAULT 'aperto',
  priority INTEGER DEFAULT 2,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  due TEXT,
  tags TEXT DEFAULT '',
  source TEXT DEFAULT 'manuale',
  session_id TEXT,
  agent TEXT DEFAULT '',
  prompt TEXT DEFAULT '',
  cwd TEXT DEFAULT '',
  run_id INTEGER,
  created_at TEXT,
  updated_at TEXT,
  done_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY,
  platform TEXT DEFAULT 'x',
  status TEXT DEFAULT 'bozza',
  text TEXT NOT NULL,
  url TEXT,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  source_ref TEXT DEFAULT '',
  scheduled_for TEXT,
  published_at TEXT,
  metrics TEXT,
  session_id TEXT,
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  description TEXT DEFAULT '',
  visibility TEXT,
  url TEXT,
  pushed_at TEXT,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  local_path TEXT,
  branch TEXT,
  dirty INTEGER DEFAULT 0,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS commits (
  id INTEGER PRIMARY KEY,
  repo TEXT,
  sha TEXT UNIQUE,
  message TEXT,
  date TEXT,
  url TEXT
);
CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(date DESC);

CREATE TABLE IF NOT EXISTS knowledge (
  id INTEGER PRIMARY KEY,
  name TEXT,
  path TEXT UNIQUE,
  scope TEXT,
  description TEXT DEFAULT '',
  type TEXT DEFAULT '',
  body TEXT DEFAULT '',
  links TEXT DEFAULT '[]',
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS capabilities (
  id INTEGER PRIMARY KEY,
  name TEXT,
  kind TEXT,
  description TEXT DEFAULT '',
  path TEXT UNIQUE,
  meta TEXT DEFAULT '{}',
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS agenda (
  id INTEGER PRIMARY KEY,
  fonte TEXT NOT NULL,
  chiave TEXT NOT NULL,
  titolo TEXT NOT NULL,
  dettaglio TEXT DEFAULT '',
  stato TEXT NOT NULL,
  stato_origine TEXT DEFAULT '',
  agente TEXT DEFAULT '',
  sessione TEXT DEFAULT '',
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  creato_at TEXT,
  aggiornato_at TEXT,
  visto_at TEXT,
  UNIQUE(fonte, chiave)
);
CREATE INDEX IF NOT EXISTS idx_agenda_stato ON agenda(stato);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  agente TEXT NOT NULL,
  modo TEXT DEFAULT 'proposta',
  prompt TEXT NOT NULL,
  cwd TEXT,
  stato TEXT DEFAULT 'in coda',
  inizio TEXT,
  fine TEXT,
  pid INTEGER,
  sessione TEXT,
  esito TEXT DEFAULT '',
  log TEXT,
  token INTEGER DEFAULT 0,
  costo REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_stato ON runs(stato);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT,
  detail TEXT DEFAULT '',
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  ref TEXT,
  source TEXT DEFAULT '',
  dedup TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
  kind, ref_id UNINDEXED, title, body, project UNINDEXED, ts UNINDEXED
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "senza-nome"


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE name='search_fts'"
    ).fetchone()
    return row is not None


AGGIUNTE = {
    # su quale cartella ha davvero lavorato la sessione, e come si e' deciso:
    # la cartella da cui e' stata aperta quasi sempre non lo dice
    "sessions": (("agent", "TEXT DEFAULT 'claude'"), ("scambi", "INTEGER DEFAULT 0"),
                 ("dir_dedotta", "TEXT"), ("dedotto_da", "TEXT"),
                 ("n_percorsi", "INTEGER DEFAULT 0"), ("radici_toccate", "TEXT"),
                 # Il thread Codex di partenza (session_meta.session_id): una
                 # ripresa e' un file nuovo con un ALTRO uuid come session_id,
                 # ma il thread resta lo stesso (vedi plancia/codex.py). Senza
                 # questa colonna, escludere un thread dopo che una sua ripresa
                 # e' gia' entrata non da' a `esclusi.purga()` niente a cui
                 # aggrapparsi: sessions non porta il thread da nessun'altra
                 # parte. NULL per le sessioni Claude Code, che non hanno
                 # questo concetto.
                 ("thread", "TEXT")),
    # un task non è solo una nota: può dire a chi tocca, come farlo e dove.
    # "host" dice da quale macchina è nato (Mac o Windows, nel sistema a due
    # assistenti): riprendi.stato() lo confronta con la macchina di adesso per
    # decidere fra viva/chiusa/persa (verdetto §B), e mostra "creato su
    # <host>" come motivo quando la sessione è persa
    "tasks": (("agent", "TEXT DEFAULT ''"), ("prompt", "TEXT DEFAULT ''"),
              ("cwd", "TEXT DEFAULT ''"), ("run_id", "INTEGER"),
              ("host", "TEXT DEFAULT ''"),
              # a mano: il compartimento (vedi plancia/compartimenti_viste.py) a
              # cui una persona ha assegnato l'oggetto dalla dashboard. Vuoto
              # nella quasi totalita' dei casi: il compartimento si ricava dai
              # dati che l'oggetto ha gia' (sessione, cwd, progetto) e questa
              # colonna si SOMMA a quelli, non li sostituisce.
              ("compartimento", "TEXT DEFAULT ''")),
    # un progetto può avere un padre (una piattaforma sotto tanti studi):
    # project_links ha UNIQUE(kind, value) e non regge due figli con lo
    # stesso padre, quindi il padre è una colonna, non un link
    "projects": (("parent_id", "INTEGER"), ("compartimento", "TEXT DEFAULT ''")),
    # da quale conversazione è uscito questo commit
    "commits": (("session_id", "TEXT DEFAULT ''"),),
    # il testo di una skill: è roba che ha scritto lui, e sta in un posto solo
    "capabilities": (("body", "TEXT DEFAULT ''"),),
    # un post senza immagine è l'eccezione, non la regola. L'immagine si decide
    # quando si scrive il post, insieme al testo: al momento di pubblicare non
    # c'è più il contesto per sceglierla, e finiva ripescata a mano ogni volta.
    "posts": (("media", "TEXT DEFAULT ''"), ("compartimento", "TEXT DEFAULT ''")),
    # solo per le note scritte a mano (`plancia_log`, la dashboard) senza un
    # progetto: le altre righe hanno il compartimento dal loro `ref` o progetto
    "events": (("compartimento", "TEXT DEFAULT ''"),),
}


def migrate(conn: sqlite3.Connection) -> None:
    """Colonne aggiunte dopo: SQLite non ha ALTER condizionale."""
    for tabella, colonne in AGGIUNTE.items():
        presenti = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabella})")}
        for colonna, definizione in colonne:
            if colonna not in presenti:
                conn.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {definizione}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    migrate(conn)
    try:
        conn.executescript(FTS_SCHEMA)
    except sqlite3.OperationalError:
        pass  # SQLite senza FTS5: la ricerca ripiega su LIKE
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


# --------------------------------------------------------------------------
# progetti
# --------------------------------------------------------------------------

def find_project_by_link(conn, kind: str, value: str):
    row = conn.execute(
        "SELECT p.* FROM projects p JOIN project_links l ON l.project_id = p.id "
        "WHERE l.kind=? AND l.value=?",
        (kind, value),
    ).fetchone()
    return row


def get_project(conn, ident):
    """Accetta id numerico, chiave o nome."""
    if ident is None or ident == "":
        return None
    if isinstance(ident, int) or (isinstance(ident, str) and ident.isdigit()):
        row = conn.execute("SELECT * FROM projects WHERE id=?", (int(ident),)).fetchone()
        if row:
            return row
    row = conn.execute("SELECT * FROM projects WHERE key=?", (str(ident),)).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT * FROM projects WHERE lower(name)=lower(?)", (str(ident),)
    ).fetchone()
    if row:
        return row
    riga = conn.execute(
        "SELECT * FROM projects WHERE key LIKE ? OR lower(name) LIKE lower(?) "
        "ORDER BY pinned DESC, last_activity DESC LIMIT 1",
        (f"%{slugify(str(ident))}%", f"%{ident}%"),
    ).fetchone()
    if riga:
        return riga
    # Detto a voce arriva con gli articoli davanti ("il filmato ard"): si
    # cercano le parole una per una invece della frase intera.
    parole = [p for p in re.findall(r"\w{3,}", str(ident).lower())
              if p not in ("il", "lo", "la", "gli", "the", "los", "las", "del", "progetto",
                           "project", "proyecto")]
    if not parole:
        return None
    migliore, punteggio = None, 0
    for r in conn.execute("SELECT * FROM projects").fetchall():
        testo = f"{r['key']} {r['name']}".lower()
        n = sum(1 for p in parole if p in testo)
        if n > punteggio:
            migliore, punteggio = r, n
    return migliore if punteggio else None


def upsert_project(conn, key: str, name: str, **fields) -> int:
    key = slugify(key)
    row = conn.execute("SELECT * FROM projects WHERE key=?", (key,)).fetchone()
    ts = now()
    if row is None:
        cols = {
            "key": key,
            "name": name,
            "created_at": ts,
            "updated_at": ts,
            "kind": fields.get("kind", "progetto"),
            "status": fields.get("status", "attivo"),
            "priority": fields.get("priority", 2),
            "summary": fields.get("summary", ""),
            "next_action": fields.get("next_action", ""),
            "auto": fields.get("auto", 1),
            "pinned": fields.get("pinned", 0),
            "hidden": fields.get("hidden", 0),
            "last_activity": fields.get("last_activity"),
        }
        placeholders = ", ".join("?" for _ in cols)
        cur = conn.execute(
            f"INSERT INTO projects ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(cols.values()),
        )
        return cur.lastrowid

    pid = row["id"]
    updates, values = [], []
    for col, val in fields.items():
        if col not in row.keys() or val is None:
            continue
        # l'ingest non sovrascrive quello che ha deciso una persona
        if fields.get("_force") is not True and col in ("status", "priority", "pinned"):
            continue
        updates.append(f"{col}=?")
        values.append(val)
    if name and row["auto"] and name != row["name"]:
        updates.append("name=?")
        values.append(name)
    if updates:
        values.extend([ts, pid])
        conn.execute(
            f"UPDATE projects SET {', '.join(updates)}, updated_at=? WHERE id=?", values
        )
    return pid


def link_project(conn, project_id: int, kind: str, value: str) -> None:
    if not value:
        return
    conn.execute(
        "INSERT INTO project_links(project_id, kind, value) VALUES(?,?,?) "
        "ON CONFLICT(kind, value) DO UPDATE SET project_id=excluded.project_id",
        (project_id, kind, value),
    )


def touch_project(conn, project_id: int, ts: str) -> None:
    if not project_id or not ts:
        return
    conn.execute(
        "UPDATE projects SET last_activity = CASE "
        "WHEN last_activity IS NULL OR last_activity < ? THEN ? ELSE last_activity END "
        "WHERE id=?",
        (ts, ts, project_id),
    )


# --------------------------------------------------------------------------
# eventi
# --------------------------------------------------------------------------

def add_event(conn, ts, kind, title, detail="", project_id=None, ref=None,
              source="", dedup=None, compartimento="") -> None:
    dedup = dedup or f"{kind}:{ref or title}:{ts}"
    conn.execute(
        "INSERT INTO events(ts, kind, title, detail, project_id, ref, source, dedup) "
        "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(dedup) DO UPDATE SET "
        "ts=excluded.ts, title=excluded.title, detail=excluded.detail, "
        "project_id=COALESCE(excluded.project_id, events.project_id)",
        (ts, kind, title, detail, project_id, ref, source, dedup),
    )
    if compartimento:
        # il compartimento assegnato a mano (vedi compartimenti_viste.py)
        conn.execute("UPDATE events SET compartimento=? WHERE dedup=?",
                     (compartimento, dedup))


# --------------------------------------------------------------------------
# ricerca
# --------------------------------------------------------------------------

def rebuild_search(conn) -> None:
    if not has_fts(conn):
        return
    conn.execute("DELETE FROM search_fts")
    rows = conn.execute(
        "SELECT t.id, t.title, t.body, t.updated_at, p.name AS pname "
        "FROM tasks t LEFT JOIN projects p ON p.id=t.project_id"
    ).fetchall()
    conn.executemany(
        "INSERT INTO search_fts(kind, ref_id, title, body, project, ts) VALUES('task',?,?,?,?,?)",
        [(r["id"], r["title"], r["body"] or "", r["pname"] or "", r["updated_at"] or "") for r in rows],
    )
    rows = conn.execute(
        "SELECT k.id, k.name, k.description, k.body, k.updated_at, p.name AS pname "
        "FROM knowledge k LEFT JOIN projects p ON p.id=k.project_id"
    ).fetchall()
    conn.executemany(
        "INSERT INTO search_fts(kind, ref_id, title, body, project, ts) VALUES('memoria',?,?,?,?,?)",
        [(r["id"], r["name"], (r["description"] or "") + "\n" + (r["body"] or "")[:6000],
          r["pname"] or "", r["updated_at"] or "") for r in rows],
    )
    # Le skill sono testo che ha scritto lui: se non stanno nell'indice, "dove
    # l'avevo scritto che non si usano gli em dash" non trova niente.
    rows = conn.execute(
        "SELECT id, name, description, body, updated_at FROM capabilities "
        "WHERE kind IN ('skill','routine')").fetchall()
    conn.executemany(
        "INSERT INTO search_fts(kind, ref_id, title, body, project, ts) VALUES('capacita',?,?,?,?,?)",
        [(r["id"], r["name"], (r["description"] or "") + "\n" + (r["body"] or "")[:8000],
          "", r["updated_at"] or "") for r in rows],
    )
    rows = conn.execute(
        "SELECT s.id, s.title, s.first_prompt, s.started_at, p.name AS pname "
        "FROM sessions s LEFT JOIN projects p ON p.id=s.project_id"
    ).fetchall()
    conn.executemany(
        "INSERT INTO search_fts(kind, ref_id, title, body, project, ts) VALUES('sessione',?,?,?,?,?)",
        [(r["id"], r["title"] or "", r["first_prompt"] or "", r["pname"] or "",
          r["started_at"] or "") for r in rows],
    )
    rows = conn.execute(
        "SELECT o.id, o.text, o.status, o.created_at, p.name AS pname "
        "FROM posts o LEFT JOIN projects p ON p.id=o.project_id"
    ).fetchall()
    conn.executemany(
        "INSERT INTO search_fts(kind, ref_id, title, body, project, ts) VALUES('post',?,?,?,?,?)",
        [(r["id"], (r["text"] or "")[:80], r["text"] or "", r["pname"] or "",
          r["created_at"] or "") for r in rows],
    )
    rows = conn.execute("SELECT id, repo, sha, message, date FROM commits").fetchall()
    conn.executemany(
        "INSERT INTO search_fts(kind, ref_id, title, body, project, ts) VALUES('commit',?,?,?,?,?)",
        [(r["id"], r["message"] or "", f"{r['repo']} {r['sha'][:8] if r['sha'] else ''}",
          r["repo"] or "", r["date"] or "") for r in rows],
    )


def _fts_query(q: str) -> str:
    """Le virgolette e gli operatori FTS nell'input rompono il match: li tolgo."""
    terms = re.findall(r"[\w']+", q, flags=re.UNICODE)
    if not terms:
        return ""
    return " AND ".join(f'"{t}"*' for t in terms)


def search(conn, q: str, limit: int = 30):
    q = (q or "").strip()
    if not q:
        return []
    if has_fts(conn):
        expr = _fts_query(q)
        if expr:
            try:
                rows = conn.execute(
                    "SELECT kind, ref_id, title, project, ts, "
                    "snippet(search_fts, 3, '«', '»', '…', 14) AS snip "
                    "FROM search_fts WHERE search_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (expr, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
    like = f"%{q}%"
    rows = conn.execute(
        "SELECT 'task' AS kind, id AS ref_id, title, '' AS project, updated_at AS ts, "
        "substr(body,1,160) AS snip FROM tasks WHERE title LIKE ? OR body LIKE ? LIMIT ?",
        (like, like, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def visibile(alias: str = "s") -> str:
    """Esclude quello che appartiene a un progetto nascosto.

    Le chiamate che Plancia fa a `claude -p` per il riepilogo aprono a loro
    volta una sessione di Claude Code. Senza questo filtro il lavoro vero
    finisce sommerso dalle chiamate dell'app a se stessa.
    """
    return (f"({alias}.project_id IS NULL OR {alias}.project_id NOT IN "
            f"(SELECT id FROM projects WHERE hidden=1))")


def row_to_dict(row) -> dict:
    return dict(row) if row is not None else None


def rows_to_dicts(rows) -> list:
    return [dict(r) for r in rows]


def jloads(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
