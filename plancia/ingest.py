"""Raccolta dati: legge il lavoro che è già successo e lo mette in tabella.

Nessuna fonte viene modificata. I transcript di Claude Code, i file di memoria,
le skill e i repo sono di sola lettura: Plancia li osserva e basta.
"""

import glob
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import attribuzione, config, slot, store

# Oltre questa soglia una riga è quasi sempre un tool_result enorme: leggerla
# con json.loads costa più di quello che vale. Se ne ricava il minimo a byte.
MAX_PARSE = 256 * 1024
# Una skill lunga è già una skill sbagliata: sopra i 64 KB si tiene l'inizio.
MAX_SKILL = 64 * 1024
SCRATCH_RE = re.compile(r"^(/private/)?(tmp|var)(/|$)|^/var/folders/")


def log(msg, progress=None):
    if progress:
        progress(msg)


# --------------------------------------------------------------------------
# percorsi
# --------------------------------------------------------------------------

def drive_root():
    hits = sorted(glob.glob(str(config.HOME / "Library/CloudStorage/GoogleDrive-*/Il mio Drive")))
    return hits[0] if hits else None


def expand(path: str) -> str:
    if path.startswith("DRIVE/"):
        root = drive_root()
        return os.path.join(root, path[6:]) if root else ""
    return os.path.normpath(os.path.expanduser(path))


def iso(ts) -> str:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(ts or "")


def to_utc(ts: str) -> str:
    """Tutto in UTC con la Z finale.

    git scrive le date con il fuso locale (+02:00), GitHub con la Z. Se restano
    mescolate, il confronto fra due timestamp fatto come stringa dà l'ordine
    sbagliato e un commit di dieci minuti fa risulta nel futuro.
    """
    ts = (ts or "").strip()
    if not ts:
        return ""
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_frontmatter(text: str):
    """Frontmatter YAML semplice: chiave: valore e un livello di annidamento."""
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            raw = text[3:end]
            body = text[end + 4:].lstrip("\n")
            section = None
            for line in raw.splitlines():
                if not line.strip() or line.strip().startswith("#"):
                    continue
                indented = line.startswith((" ", "\t"))
                key, _, val = line.strip().partition(":")
                key, val = key.strip(), val.strip()
                if len(val) > 1 and val[0] == val[-1] and val[0] in "'\"":
                    val = val[1:-1].replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
                if indented and section:
                    meta.setdefault(section, {})[key] = val
                elif val:
                    meta[key] = val
                    section = None
                else:
                    section = key
    return meta, body


# --------------------------------------------------------------------------
# 1. seed: identità dei progetti
# --------------------------------------------------------------------------

def load_seed() -> dict:
    """La mappa dei progetti dell'utente sta in ~/.plancia/seed.json.

    Quella nel repo è solo un esempio: così il progetto si può pubblicare senza
    portarsi dietro i progetti di chi lo ha scritto.
    """
    for path in (config.USER_SEED, config.SEED_FILE):
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            continue
    return {"projects": [], "method_memories": []}


def sync_seed(conn, progress=None) -> dict:
    seed = load_seed()
    keywords = {}
    for spec in seed.get("projects", []):
        pid = store.upsert_project(
            conn,
            spec["key"],
            spec["name"],
            kind=spec.get("kind", "progetto"),
            auto=0,
            priority=spec.get("priority", 2),
            pinned=spec.get("pinned", 0),
            status=spec.get("status", "attivo"),
        )
        for kind, values in (spec.get("links") or {}).items():
            for value in values:
                store.link_project(conn, pid, kind, expand(value) if kind == "path" else value)
        if spec.get("keywords"):
            keywords[pid] = spec["keywords"]
    conn.commit()
    log(f"progetti di riferimento: {len(seed.get('projects', []))}", progress)
    return keywords


def resolve_path_project(conn, path: str):
    """Il progetto che possiede questo percorso, o il più vicino sopra di esso."""
    if not path:
        return None
    path = os.path.normpath(path)
    rows = conn.execute(
        "SELECT project_id, value FROM project_links WHERE kind='path' "
        "ORDER BY length(value) DESC"
    ).fetchall()
    for row in rows:
        base = row["value"]
        if base and (path == base or path.startswith(base + os.sep)):
            return row["project_id"]
    return None


def infer_project_by_keywords(text: str, keywords: dict):
    if not text:
        return None
    low = text.lower()
    hits = []
    for pid, words in keywords.items():
        score = sum(1 for w in words if w in low)
        if score:
            hits.append((score, pid))
    if not hits:
        return None
    hits.sort(reverse=True)
    if len(hits) > 1 and hits[0][0] == hits[1][0]:
        return None  # ambiguo: meglio nessuna attribuzione che una sbagliata
    return hits[0][1]


# --------------------------------------------------------------------------
# 2. memoria di Claude
# --------------------------------------------------------------------------

def sync_memory(conn, progress=None) -> int:
    seed = load_seed()
    methods = set(seed.get("method_memories", []))
    count = 0
    for md in sorted(config.CLAUDE_PROJECTS.glob("*/memory/*.md")):
        if md.name == "MEMORY.md":
            continue
        try:
            text = md.read_text("utf-8", errors="replace")
        except OSError:
            continue
        meta, body = read_frontmatter(text)
        name = meta.get("name") or md.stem
        mtype = (meta.get("metadata") or {}).get("type", "") if isinstance(meta.get("metadata"), dict) else ""
        # I legami si cercano fuori dal codice. Dentro i backtick le doppie
        # parentesi quadre non sono un rinvio a un'altra memoria: sono sintassi.
        # `[[item]]`, chiave di un file di configurazione citata in una memoria,
        # risultava un legame verso una memoria inesistente, e la diagnosi lo
        # chiamava link rotto per sempre.
        prosa = re.sub(r"```.*?```", " ", body, flags=re.S)
        prosa = re.sub(r"`[^`\n]*`", " ", prosa)
        links = sorted(set(re.findall(r"\[\[([^\]]+)\]\]", prosa)))
        pid_row = store.find_project_by_link(conn, "memory", name)
        pid = pid_row["id"] if pid_row else None
        if pid is None and mtype == "project" and name not in methods:
            pid = store.upsert_project(conn, name, name.replace("-", " ").capitalize(),
                                       kind="progetto")
            store.link_project(conn, pid, "memory", name)
        mtime = iso(md.stat().st_mtime)
        conn.execute(
            "INSERT INTO knowledge(name, path, scope, description, type, body, links, "
            "project_id, updated_at) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET name=excluded.name, description=excluded.description, "
            "type=excluded.type, body=excluded.body, links=excluded.links, "
            "project_id=COALESCE(excluded.project_id, knowledge.project_id), "
            "updated_at=excluded.updated_at",
            (name, str(md), md.parent.parent.name, meta.get("description", ""), mtype,
             body, json.dumps(links), pid, mtime),
        )
        if pid:
            # il riassunto del progetto sono le parole dell'utente, non le mie
            conn.execute(
                "UPDATE projects SET summary=? WHERE id=? AND (summary='' OR summary IS NULL)",
                (meta.get("description", ""), pid),
            )
            store.touch_project(conn, pid, mtime)
        store.add_event(conn, mtime, "memoria", f"memoria aggiornata: {name}",
                        meta.get("description", ""), pid, name, "memory",
                        dedup=f"memoria:{name}:{mtime}")
        count += 1

    # Una memoria cancellata restava nell'archivio per sempre: il giro leggeva
    # i file che ci sono e non guardava mai quelli che non ci sono più. Due
    # righe puntavano a file spariti da una settimana, e continuavano a contare
    # nelle diagnosi e a farsi trovare dalla ricerca. Si toglie solo ciò che
    # stava sotto la cartella dei progetti di Claude, che è l'unica di cui
    # questo giro sa qualcosa.
    radice = str(config.CLAUDE_PROJECTS)
    spariti = [r["path"] for r in conn.execute("SELECT path FROM knowledge")
               if (r["path"] or "").startswith(radice) and not Path(r["path"]).exists()]
    if spariti:
        conn.executemany("DELETE FROM knowledge WHERE path=?", [(p,) for p in spariti])
        log(f"memoria: {len(spariti)} sparite", progress)
    conn.commit()
    log(f"memoria: {count} file", progress)
    return count


# --------------------------------------------------------------------------
# 3. capacità: skill, plugin, routine
# --------------------------------------------------------------------------

def sync_capabilities(conn, progress=None) -> int:
    found = 0
    for skill in sorted(config.CLAUDE_SKILLS.glob("*/SKILL.md")):
        # Il testo intero, non solo il nome. Una skill è una cosa che ha scritto
        # lui e che vive in un posto solo: tenerne il testo qui vuol dire poterla
        # cercare con `plancia search` e ritrovarla se sparisce la cartella.
        intero = skill.read_text("utf-8", errors="replace")
        meta, corpo = read_frontmatter(intero[:MAX_SKILL])
        name = meta.get("name") or skill.parent.name
        conn.execute(
            "INSERT INTO capabilities(name, kind, description, path, meta, body, updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET name=excluded.name, "
            "description=excluded.description, body=excluded.body, "
            "updated_at=excluded.updated_at",
            (name, "skill", meta.get("description", "")[:600], str(skill), "{}",
             intero[:MAX_SKILL], iso(skill.stat().st_mtime)),
        )
        row = store.find_project_by_link(conn, "skill", name)
        if row:
            store.touch_project(conn, row["id"], iso(skill.stat().st_mtime))
        found += 1

    for routine in sorted(config.CLAUDE_ROUTINES.glob("*/SKILL.md")):
        meta, body = read_frontmatter(routine.read_text("utf-8", errors="replace")[:4000])
        conn.execute(
            "INSERT INTO capabilities(name, kind, description, path, meta, updated_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET name=excluded.name, "
            "description=excluded.description, updated_at=excluded.updated_at",
            (meta.get("name") or routine.parent.name, "routine",
             meta.get("description", "")[:600], str(routine), "{}",
             iso(routine.stat().st_mtime)),
        )
        found += 1

    installed = config.CLAUDE_PLUGINS / "installed_plugins.json"
    if installed.exists():
        try:
            data = json.loads(installed.read_text("utf-8"))
            for name, entries in (data.get("plugins") or {}).items():
                entry = entries[0] if isinstance(entries, list) and entries else {}
                conn.execute(
                    "INSERT INTO capabilities(name, kind, description, path, meta, updated_at) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                    "description=excluded.description, meta=excluded.meta, "
                    "updated_at=excluded.updated_at",
                    (name, "plugin", f"versione {entry.get('version', '?')}",
                     entry.get("installPath") or f"plugin:{name}", json.dumps(entry),
                     entry.get("lastUpdated", "")),
                )
                found += 1
        except Exception:
            pass
    conn.commit()
    log(f"capacità: {found}", progress)
    return found


# --------------------------------------------------------------------------
# 4. sessioni di Claude Code (incrementale, byte per byte)
# --------------------------------------------------------------------------

def progetto_per_cartella(conn, cwd: str, keywords: dict, testo: str = ""):
    """A quale progetto appartiene una sessione aperta da questa cartella.

    Vale per Claude Code e per Codex: cambia il formato del transcript, non il
    significato di una cartella di lavoro.

    Prima di L1-INGEST, una cwd mai vista diventava sempre una scheda radice:
    122 progetti su una manciata di famiglie reali, perché nessuna
    riorganizzazione dei manuali (`vesuvius`, `op6-causal`, ...) veniva mai
    letta all'ingest. Ora, quando la cwd non risolve un progetto già noto
    (`resolve_path_project`), si cerca un padre con `slot.padre_per_path`
    prima di creare. Da qui scatta solo la regola del prefisso del nome
    della cartella (`vesuvius` trova `vesuvius-op7`): una cwd sotto un path
    già collegato a un manuale è un caso che `resolve_path_project` guarda
    per prima (i suoi link path sono un sovrainsieme esatto di quelli della
    regola 1 di `padre_per_path`), quindi la sessione finisce dentro il
    manuale stesso e non arriva mai qui. La regola per path resta corretta,
    provata in isolamento in `tools/prove/slot.py`, ma attraverso questa
    funzione non scatta mai.

    Tre casi:

    1. La cwd è già coperta da un link path (di un manuale o di una scheda
       nata prima): `resolve_path_project` la trova PRIMA di arrivare qui
       (i suoi link path sono un sovrainsieme esatto di quelli guardati
       dalla regola 1 di `padre_per_path`), quindi la sessione finisce
       dentro quella scheda e questa funzione non crea niente. Non si
       cambia questo comportamento da qui: lo decide `resolve_path_project`.

    2. La cwd non risolve niente e la sua chiave (slug del basename) non
       esiste ancora: nasce una scheda nuova con quella chiave, figlia del
       padre trovato da `slot.padre_per_path` o, in mancanza, di
       `cartelle-viste` (il contenitore delle cartelle senza un manuale che
       le riconosca, creato una sola volta al bisogno).

    3. La cwd non risolve niente ma la chiave esiste già, e appartiene a un
       progetto ESTRANEO: un manuale con lo stesso nome della cartella, o
       una scheda nata da un'altra cartella con lo stesso basename (se
       quella scheda avesse un link path che copre questa cwd, saremmo nel
       caso 1, non qui, quindi arrivare al caso 3 vuol dire che non ce l'ha).
       Legare comunque questa cwd a quella scheda (com'era prima di
       L1-INGEST-B) sporca un progetto che non c'entra niente: da quel
       momento `resolve_path_project` gli attribuirebbe ogni sessione
       futura sotto la cartella incidentale e le sue sottocartelle,
       bypassando anche `cartelle-viste`. Si crea invece una SECONDA
       scheda, con chiave disambiguata `<slug>-2`, `-3`, ... (la prima
       libera), `auto=1`, lo stesso nome (senza suffisso) e lo stesso
       criterio di padre del caso 2: così "una scheda per cwd" resta vero e
       il progetto estraneo non riceve nessun link che non gli appartiene.

    Il padre si assegna solo a una scheda nata in QUESTA chiamata (casi 2 e
    3: sempre una riga appena inserita, mai una riassegnazione). Una scheda
    con `parent_id` già valorizzato (a mano, o da un sync precedente) non
    viene mai toccata (`WHERE ... AND parent_id IS NULL`), e la guardia
    `padre_id != trovato` evita che una scheda diventi padre di se stessa:
    capita quando il suo stesso basename è `cartelle-viste` vista per la
    prima volta, prima che il contenitore esista già come riga propria
    (`_cartella_vista` trova allora la riga appena inserita da questa
    stessa chiamata, che è `trovato`).
    """
    if not cwd:
        return None
    normale = os.path.normpath(cwd)
    if normale == os.path.normpath(str(config.DATA_DIR)):
        # è Plancia che ha chiamato un agente per il riepilogo, non lavoro suo
        return store.upsert_project(conn, "plancia-interno", "Plancia (chiamate interne)",
                                    kind="infra", hidden=1)
    if SCRATCH_RE.match(cwd):
        return store.upsert_project(conn, "temporanee", "Sessioni temporanee",
                                    kind="infra", hidden=1)

    # Certe cartelle non identificano niente. La home e la radice del Drive sono
    # posti da cui si lavora a tutto; Codex invece apre una cartella nuova per
    # ogni conversazione sotto ~/Documents/Codex, col nome preso dalla domanda:
    # sono nomi di chat, non di progetti. In tutti questi casi il progetto si
    # indovina dal testo.
    radici_generiche = {os.path.normpath(str(config.HOME))}
    drive = drive_root()
    if drive:
        radici_generiche.add(os.path.normpath(drive))
    effimere = [os.path.normpath(str(config.HOME / "Documents/Codex"))]
    effimere += [expand(r) for r in config.load_config().get("cartelle_effimere", [])]
    generica = normale in radici_generiche or any(
        normale == e or normale.startswith(e + os.sep) for e in effimere if e)
    if generica:
        trovato = infer_project_by_keywords(testo, keywords)
        return trovato or store.upsert_project(conn, "drive-workspace",
                                               "Senza progetto", kind="infra")

    trovato = resolve_path_project(conn, cwd)
    if trovato is None:
        base = os.path.basename(cwd.rstrip("/")) or cwd
        # La chiave può già appartenere a una scheda esistente (vedi il
        # docstring sopra, caso 3): si controlla PRIMA di scrivere qualsiasi
        # cosa. Se esiste già ma non risolveva la cwd (altrimenti saremmo
        # già tornati sopra, da resolve_path_project), quella scheda è
        # estranea: non le si lega questa cwd, si crea una scheda diversa
        # con chiave disambiguata (L1-INGEST-B).
        chiave = store.slugify(base)
        esisteva = conn.execute(
            "SELECT id FROM projects WHERE key=?", (chiave,)
        ).fetchone()
        if esisteva:
            chiave = _chiave_libera(conn, chiave)
        trovato = store.upsert_project(conn, chiave, base.replace("-", " "),
                                       kind="progetto", auto=1)
        store.link_project(conn, trovato, "path", normale)
        # Il padre si cerca e si scrive sempre qui: `trovato` è appena stato
        # inserito (chiave nuova per costruzione, sia nel caso 2 sia nel
        # caso 3), quindi l'UPDATE sotto non riassegna mai il parent_id di
        # una scheda altrui.
        padre_key = slot.padre_per_path(conn, normale)
        padre_id = _progetto_id(conn, padre_key) if padre_key else _cartella_vista(conn)
        # padre_id != trovato: guardia contro il caso in cui la scheda
        # appena creata SIA _cartella_vista (cwd con basename
        # "cartelle-viste"): senza questo controllo diventerebbe padre
        # di se stessa.
        if padre_id is not None and padre_id != trovato:
            conn.execute(
                "UPDATE projects SET parent_id=?, updated_at=? "
                "WHERE id=? AND parent_id IS NULL",
                (padre_id, store.now(), trovato))
    return trovato


def _chiave_libera(conn, base: str) -> str:
    """La prima chiave libera dopo una collisione: `<base>-2`, poi `-3`, ...

    Il progetto che già ha la chiave `base` (un manuale, o una scheda nata
    da un'altra cartella con lo stesso basename) resta intatto: la cwd
    nuova prende sempre una chiave diversa dalla sua, mai la stessa.
    """
    n = 2
    while conn.execute(
        "SELECT 1 FROM projects WHERE key=?", (f"{base}-{n}",)
    ).fetchone():
        n += 1
    return f"{base}-{n}"


def _progetto_id(conn, key):
    """L'id di un progetto dalla sua chiave esatta, o None se non esiste più
    (caso limite: cancellato fra la lettura di slot.padre_per_path e qui)."""
    riga = conn.execute("SELECT id FROM projects WHERE key=?", (key,)).fetchone()
    return riga["id"] if riga else None


def _cartella_vista(conn) -> int:
    """Il contenitore delle cwd nuove senza nessun manuale che le rivendichi.

    Creato una volta sola: le chiamate successive trovano la riga già
    esistente e ne riusano l'id, senza riscrivere kind/hidden/summary ogni
    volta (che sovrascriverebbe silenziosamente una modifica fatta a mano,
    es. se qualcuno la nasconde in dashboard).
    """
    riga = conn.execute("SELECT id FROM projects WHERE key='cartelle-viste'").fetchone()
    if riga:
        return riga["id"]
    return store.upsert_project(
        conn, "cartelle-viste", "Cartelle viste", kind="infra", auto=0, hidden=0,
        status="attivo",
        summary="Le cartelle di lavoro viste per la prima volta, senza un progetto "
                "manuale a cui appartenere.")


def radici_e_generiche(conn):
    """Le cartelle che valgono come progetto, e quelle che non dicono niente."""
    drive = drive_root()
    radici = attribuzione.radici_note(conn, drive=drive)
    return (sorted(radici, key=len, reverse=True),
            attribuzione.radici_generiche(drive=drive))


def attribuisci(conn, cwd, keywords, testo, conteggi, radici, generiche):
    """Il progetto di una sessione, con scritto come ci si e' arrivati.

    Prima si guarda cosa ha toccato, poi da dove e' stata aperta. Se la cartella
    dedotta non appartiene a nessun progetto si torna alla regola di prima, che
    e' l'unica autorizzata a inventare un progetto nuovo.
    """
    esito = attribuzione.decidi(cwd, attribuzione.percorsi_finti(conteggi),
                                radici, generiche)
    pid = None
    if esito["categoria"] == "progetto" and esito["dir"]:
        pid = resolve_path_project(conn, esito["dir"])
    if pid is None:
        pid = progetto_per_cartella(conn, cwd, keywords, testo)
    return pid, esito


def _bytes_field(raw: bytes, key: bytes, limit: int = 400):
    """Estrae "key":"valore" senza parsare tutta la riga."""
    idx = raw.find(key)
    if idx == -1:
        return None
    start = idx + len(key)
    end = raw.find(b'"', start)
    if end == -1 or end - start > limit:
        return None
    try:
        return raw[start:end].decode("utf-8", "replace")
    except Exception:
        return None


def _is_real_prompt(text: str) -> bool:
    if not text or len(text.strip()) < 3:
        return False
    stripped = text.lstrip()
    if stripped.startswith(("<", "Caveat:", "[Request interrupted", "API Error")):
        return False
    if stripped.startswith("/") and len(stripped.split()) <= 2:
        return False  # comando slash secco, non racconta niente
    return True


def scan_session_file(path: Path, start_offset: int, radici=None) -> dict:
    """Legge solo i byte nuovi del transcript e ne ricava le statistiche.

    `radici` sono le cartelle note, gia' ordinate dalla piu' profonda: se ci
    sono, si conta anche quali di quelle la sessione ha toccato. Costa niente
    perche' i `tool_use` vengono aperti comunque per contare i tool.
    """
    acc = {
        "offset": start_offset, "cwd": None, "branch": None, "title": None,
        "first_prompt": None, "queued_prompt": None, "ts_min": None, "ts_max": None,
        "n_user": 0, "n_assistant": 0, "n_tools": 0, "models": set(),
        "tools": {}, "in_tokens": 0, "out_tokens": 0, "radici": {}, "n_percorsi": 0,
    }
    with open(path, "rb") as fh:
        if start_offset:
            fh.seek(start_offset)
        for raw in fh:
            acc["offset"] += len(raw)
            if len(raw) < 3:
                continue
            # Il tipo va cercato per intero: dentro message.content ci sono altri
            # "type" (text, tool_use, tool_result) che verrebbero prima.
            if b'"type":"assistant"' in raw:
                rtype = "assistant"
            elif b'"type":"user"' in raw:
                rtype = "user"
            elif b'"type":"custom-title"' in raw:
                rtype = "custom-title"
            elif b'"type":"queue-operation"' in raw:
                rtype = "queue-operation"
            else:
                continue  # attachment, snapshot, riassunti: non servono

            if len(raw) > MAX_PARSE:
                # quasi sempre un tool_result enorme: si prende solo il minimo
                if rtype == "assistant":
                    acc["n_assistant"] += 1
                    model = _bytes_field(raw, b'"model":"', 60)
                    if model:
                        acc["models"].add(model)
                continue

            try:
                rec = json.loads(raw)
            except Exception:
                continue

            rtype = rec.get("type")
            if rtype == "custom-title":
                acc["title"] = rec.get("customTitle") or acc["title"]
                continue
            if rtype == "queue-operation":
                if rec.get("operation") == "enqueue" and not acc["queued_prompt"]:
                    text = rec.get("content") or ""
                    if _is_real_prompt(text):
                        acc["queued_prompt"] = text.strip()
                continue

            ts = rec.get("timestamp")
            if ts:
                if acc["ts_min"] is None or ts < acc["ts_min"]:
                    acc["ts_min"] = ts
                if acc["ts_max"] is None or ts > acc["ts_max"]:
                    acc["ts_max"] = ts
            acc["cwd"] = rec.get("cwd") or acc["cwd"]
            acc["branch"] = rec.get("gitBranch") or acc["branch"]

            msg = rec.get("message") or {}
            if rtype == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    # una content list è un tool_result: non è una cosa che ha
                    # scritto lui, e non va contata come scambio
                    acc["n_user"] += 1
                    if not acc["first_prompt"] and _is_real_prompt(content):
                        acc["first_prompt"] = content.strip()
            elif rtype == "assistant":
                acc["n_assistant"] += 1
                if msg.get("model"):
                    acc["models"].add(msg["model"])
                usage = msg.get("usage") or {}
                acc["in_tokens"] += (usage.get("input_tokens") or 0) + \
                    (usage.get("cache_read_input_tokens") or 0) + \
                    (usage.get("cache_creation_input_tokens") or 0)
                acc["out_tokens"] += usage.get("output_tokens") or 0
                for item in msg.get("content") or []:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        acc["n_tools"] += 1
                        name = item.get("name", "?")
                        acc["tools"][name] = acc["tools"].get(name, 0) + 1
                        if radici is not None:
                            _segna(acc, attribuzione.percorsi_da_tool_use(item), radici)
    return acc


def _segna(acc: dict, percorsi, radici) -> None:
    """Somma i percorsi di un tool_use alle radici gia' viste.

    `n_percorsi` conta tutti i percorsi visti, anche quelli fuori dalle radici:
    serve come numero d'ordine, per sapere quale cartella e' stata toccata per
    prima quando due pareggiano.
    """
    for percorso in percorsi:
        radice = attribuzione.radice_di(percorso, radici)
        acc["n_percorsi"] += 1
        if not radice:
            continue
        voce = acc["radici"].get(radice)
        if voce is None:
            acc["radici"][radice] = [1, acc["n_percorsi"]]
        else:
            voce[0] += 1


def conta_percorsi(path: Path, radici, offset: int = 0) -> dict:
    """Le radici toccate da un transcript, senza leggerne altro.

    Serve alla riattribuzione, che deve ripassare tutto l'archivio: una riga che
    non nomina un `tool_use` viene scartata dal confronto sui byte, senza passare
    da json. Misurato il 3 settembre 2026 su 470 transcript e 1,7 GB: tre secondi.
    """
    acc = {"radici": {}, "n_percorsi": 0}
    with open(path, "rb") as fh:
        if offset:
            fh.seek(offset)
        for raw in fh:
            # Il confronto e' su `"tool_use"` e non su `"type":"tool_use"`: fra
            # la chiave e il valore ci puo' stare uno spazio, e `"tool_use_id"`
            # non contiene la virgoletta di chiusura, quindi non passa lo stesso.
            if b'"tool_use"' not in raw or len(raw) > MAX_PARSE:
                continue
            try:
                rec = json.loads(raw)
            except Exception:
                continue
            for item in (rec.get("message") or {}).get("content") or []:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    _segna(acc, attribuzione.percorsi_da_tool_use(item), radici)
    return acc


def sync_sessions(conn, keywords, progress=None, full=False) -> int:
    files = sorted(config.CLAUDE_PROJECTS.glob("*/*.jsonl"))
    radici, generiche = radici_e_generiche(conn)
    updated = 0
    for i, path in enumerate(files):
        sid = path.stem
        try:
            size = path.stat().st_size
            mtime = path.stat().st_mtime
        except OSError:
            continue
        row = conn.execute(
            "SELECT id, bytes_scanned, file_size, models, tools, title, first_prompt, "
            "started_at, n_user, n_assistant, n_tools, in_tokens, out_tokens, project_id, "
            "radici_toccate FROM sessions WHERE session_id=?", (sid,)
        ).fetchone()
        offset = 0 if (full or row is None) else (row["bytes_scanned"] or 0)
        if offset > size:
            offset = 0  # file ricreato o troncato: si riparte da capo
        elif row is not None and not full and size <= offset:
            continue
        log(f"sessioni {i + 1}/{len(files)} · {sid[:8]} ({size // 1024} KB)", progress)
        try:
            acc = scan_session_file(path, offset, radici)
        except OSError:
            continue

        # Se si è ripartiti da zero i totali di prima non vanno sommati, o una
        # rilettura completa raddoppia scambi, tool e token.
        old = (lambda col: row[col] if row else 0) if offset else (lambda col: 0)
        keep = (lambda col: row[col] if row else None) if offset else (lambda col: None)

        prev_models = set(store.jloads(row["models"], []) if (row and offset) else [])
        prev_tools = store.jloads(row["tools"], {}) if (row and offset) else {}
        for name, n in acc["tools"].items():
            prev_tools[name] = prev_tools.get(name, 0) + n
        models = sorted(prev_models | acc["models"])
        title = acc["title"] or keep("title")
        first_prompt = keep("first_prompt") or acc["first_prompt"] or acc["queued_prompt"]
        started = keep("started_at") or acc["ts_min"] or iso(mtime)
        ended = acc["ts_max"] or iso(mtime)
        n_user = old("n_user") + acc["n_user"]
        n_assistant = old("n_assistant") + acc["n_assistant"]
        n_tools = old("n_tools") + acc["n_tools"]
        in_tok = old("in_tokens") + acc["in_tokens"]
        out_tok = old("out_tokens") + acc["out_tokens"]
        cwd = acc["cwd"]

        # I conteggi di prima si sommano a quelli dei byte appena letti: il sync
        # incrementale vede solo la coda del transcript, e da sola direbbe che la
        # sessione ha lavorato dove ha lavorato nell'ultima ora.
        vecchie = store.jloads(row["radici_toccate"], {}) if (row and offset) else {}
        conteggi = attribuzione.fondi(vecchie, acc["radici"])

        pid = row["project_id"] if row else None
        esito = {"dir": None, "da": None, "n": 0}
        if cwd:
            pid, esito = attribuisci(conn, cwd, keywords,
                                     f"{title or ''} {first_prompt or ''}",
                                     conteggi, radici, generiche)

        conn.execute(
            "INSERT INTO sessions(session_id, project_id, file, bytes_scanned, file_size, "
            "cwd, git_branch, title, first_prompt, started_at, ended_at, n_user, n_assistant, "
            "n_tools, models, tools, in_tokens, out_tokens, dir_dedotta, dedotto_da, "
            "n_percorsi, radici_toccate, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET project_id=excluded.project_id, "
            "bytes_scanned=excluded.bytes_scanned, file_size=excluded.file_size, "
            "cwd=COALESCE(excluded.cwd, sessions.cwd), git_branch=COALESCE(excluded.git_branch, sessions.git_branch), "
            "title=excluded.title, first_prompt=excluded.first_prompt, ended_at=excluded.ended_at, "
            "n_user=excluded.n_user, n_assistant=excluded.n_assistant, n_tools=excluded.n_tools, "
            "models=excluded.models, tools=excluded.tools, in_tokens=excluded.in_tokens, "
            "out_tokens=excluded.out_tokens, dir_dedotta=excluded.dir_dedotta, "
            "dedotto_da=excluded.dedotto_da, n_percorsi=excluded.n_percorsi, "
            "radici_toccate=excluded.radici_toccate, updated_at=excluded.updated_at",
            (sid, pid, str(path), acc["offset"], size, cwd, acc["branch"], title,
             (first_prompt or "")[:2000], started, ended, n_user, n_assistant, n_tools,
             json.dumps(models), json.dumps(prev_tools), in_tok, out_tok,
             esito["dir"], esito["da"], esito["n"], json.dumps(conteggi), store.now()),
        )
        label = title or (first_prompt or "sessione")[:90]
        store.add_event(conn, started, "sessione", label,
                        f"{n_user} messaggi · {n_tools} tool", pid, sid, "claude",
                        dedup=f"sessione:{sid}")
        store.touch_project(conn, pid, ended)
        updated += 1
        if updated % 5 == 0:
            conn.commit()
    reassign_generic(conn, keywords)
    conn.commit()
    log(f"sessioni aggiornate: {updated}", progress)
    return updated


def reassign_generic(conn, keywords) -> int:
    """Ripassa le sessioni finite nel contenitore generico: le parole chiave
    migliorano nel tempo, e queste devono poter migrare al progetto giusto."""
    row = conn.execute("SELECT id FROM projects WHERE key='drive-workspace'").fetchone()
    if not row:
        return 0
    moved = 0
    for s in conn.execute(
            "SELECT id, title, first_prompt FROM sessions WHERE project_id=?",
            (row["id"],)).fetchall():
        pid = infer_project_by_keywords(f"{s['title'] or ''} {s['first_prompt'] or ''}", keywords)
        if pid and pid != row["id"]:
            conn.execute("UPDATE sessions SET project_id=? WHERE id=?", (pid, s["id"]))
            conn.execute("UPDATE events SET project_id=? WHERE ref=(SELECT session_id FROM sessions WHERE id=?)",
                         (pid, s["id"]))
            moved += 1
    return moved


def riattribuisci(conn, progress=None) -> dict:
    """Ricalcola l'attribuzione di tutte le sessioni gia' in archivio.

    Serve quando le radici note cambiano: un progetto nuovo, un repo clonato,
    una cartella spostata. Rilegge i transcript di Claude da capo perche' i
    percorsi toccati non erano stati salvati, ma legge solo i `tool_use`: sui
    470 transcript di questa macchina, 1,7 GB, ci mette tre secondi. Le sessioni
    di Codex passano lo stesso, per la sola regola sulla cartella: quando nasce
    un progetto, anche le loro devono poterci finire dentro.

    Non crea progetti. Se la cartella dedotta non appartiene a nessun progetto
    la sessione resta dov'era, e `dir_dedotta` dice comunque dove ha lavorato:
    e' un'informazione, non una scusa per riempire l'elenco dei progetti.
    """
    radici, generiche = radici_e_generiche(conn)
    righe = conn.execute(
        "SELECT id, session_id, file, cwd, project_id, COALESCE(agent,'claude') AS agente "
        "FROM sessions ORDER BY started_at DESC").fetchall()
    esiti = {"lette": 0, "dedotte": 0, "spostate": 0, "senza_file": 0}
    for i, riga in enumerate(righe):
        if i % 25 == 0:
            log(f"riattribuisco {i + 1}/{len(righe)}", progress)
        # I percorsi toccati si leggono solo dai transcript di Claude: il
        # rollout di Codex ha un altro formato. Per tutte le altre sessioni
        # vale comunque la regola sulla cartella, che dopo un progetto nuovo
        # puo' dare una risposta diversa da quella salvata.
        percorso = Path(riga["file"]) if (riga["file"] and riga["agente"] == "claude") else None
        conteggi = {}
        if percorso and percorso.exists():
            try:
                conteggi = conta_percorsi(percorso, radici)["radici"]
                esiti["lette"] += 1
            except OSError:
                pass
        else:
            esiti["senza_file"] += 1
        esito = attribuzione.decidi(riga["cwd"],
                                    attribuzione.percorsi_finti(conteggi),
                                    radici, generiche)
        pid = riga["project_id"]
        if esito["categoria"] == "progetto" and esito["dir"]:
            trovato = resolve_path_project(conn, esito["dir"])
            if trovato:
                pid = trovato
        if esito["da"] == "percorsi":
            esiti["dedotte"] += 1
        conn.execute(
            "UPDATE sessions SET project_id=?, dir_dedotta=?, dedotto_da=?, "
            "n_percorsi=?, radici_toccate=? WHERE id=?",
            (pid, esito["dir"], esito["da"], esito["n"], json.dumps(conteggi), riga["id"]))
        if pid != riga["project_id"]:
            esiti["spostate"] += 1
            conn.execute("UPDATE events SET project_id=? WHERE ref=? AND kind='sessione'",
                         (pid, riga["session_id"]))
            store.touch_project(conn, pid, store.now())
        if i % 50 == 0:
            conn.commit()
    conn.commit()
    log(f"sessioni riattribuite: {esiti['spostate']} spostate su {len(righe)}", progress)
    return esiti


# --------------------------------------------------------------------------
# 5. repo GitHub e git locale
# --------------------------------------------------------------------------

def run(cmd, timeout=30, cwd=None):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return res.stdout.strip() if res.returncode == 0 else None
    except Exception:
        return None


def sync_repos(conn, progress=None) -> int:
    cfg = config.load_config()
    if not cfg.get("gh_enabled", True):
        return 0
    out = run(["gh", "repo", "list", "--limit", "60", "--json",
               "name,description,visibility,url,pushedAt"], timeout=40)
    if not out:
        log("gh non disponibile: salto i repo", progress)
        return 0
    try:
        repos = json.loads(out)
    except Exception:
        return 0
    owner = run(["gh", "api", "user", "--jq", ".login"], timeout=20) or cfg.get("gh_user", "")
    if owner and owner != cfg.get("gh_user"):
        cfg["gh_user"] = owner
        config.save_config(cfg)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = 0
    for repo in repos:
        name = repo["name"]
        prow = store.find_project_by_link(conn, "repo", name)
        pid = prow["id"] if prow else None
        old = conn.execute("SELECT pushed_at FROM repos WHERE name=?", (name,)).fetchone()
        conn.execute(
            "INSERT INTO repos(name, description, visibility, url, pushed_at, project_id, updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET description=excluded.description, "
            "visibility=excluded.visibility, url=excluded.url, pushed_at=excluded.pushed_at, "
            "project_id=COALESCE(excluded.project_id, repos.project_id), updated_at=excluded.updated_at",
            (name, repo.get("description") or "", repo.get("visibility", ""), repo.get("url", ""),
             to_utc(repo.get("pushedAt", "")), pid, store.now()),
        )
        if pid:
            store.touch_project(conn, pid, to_utc(repo.get("pushedAt", "")))
        # Solo i commit presi da GitHub hanno una url: quelli letti da git in
        # locale sono uno per cartella e non bastano a dire "già scaricato".
        known = conn.execute(
            "SELECT COUNT(*) FROM commits WHERE repo=? AND url<>''", (name,)).fetchone()[0]
        changed = old is None or old["pushed_at"] != to_utc(repo.get("pushedAt", "")) or known == 0
        if owner and changed and (repo.get("pushedAt") or "") > cutoff and fresh < 12:
            fresh += 1
            log(f"commit di {name}", progress)
            data = run(["gh", "api", f"repos/{owner}/{name}/commits?per_page=20"], timeout=30)
            try:
                commits = json.loads(data) if data else []
            except Exception:
                commits = []
            for commit in commits if isinstance(commits, list) else []:
                sha = commit.get("sha")
                info = (commit.get("commit") or {})
                msg = (info.get("message") or "").split("\n")[0]
                date = to_utc(((info.get("author") or {}).get("date")) or "")
                if not sha:
                    continue
                conn.execute(
                    "INSERT INTO commits(repo, sha, message, date, url) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(sha) DO NOTHING",
                    (name, sha, msg, date, commit.get("html_url", "")),
                )
                store.add_event(conn, date, "commit", msg, name, pid, sha, "github",
                                dedup=f"commit:{sha}")
    conn.commit()
    log(f"repo: {len(repos)}", progress)
    return len(repos)


#: Quanto si aspetta `git status` prima di lasciar perdere. Dentro il Drive ogni
#: file tracciato e' un segnaposto che il file provider deve verificare: misurato
#: il 9 agosto 2026 su Voicebox-Fish, 681 file, due minuti e 51 secondi anche
#: saltando gli untracked, contro dieci millisecondi per un repo sul disco. Era
#: da solo i venti secondi di ogni sync.
STATO_TIMEOUT = 4.0
#: Per quanto si ricorda che una cartella e' lenta prima di riprovarci.
STATO_RIPROVA_ORE = 6


def _leggi_stato(out):
    """Ramo e numero di file modificati da `git status --porcelain --branch`.

    La prima riga e' `## main...origin/main [ahead 1]`, oppure `## main` senza
    upstream, oppure `## HEAD (no branch)` a testa staccata. Le altre sono i
    file. Torna (None, None) se lo stato non e' arrivato, e chi scrive deve
    distinguerlo da "nessun file modificato".
    """
    if out is None:
        return None, None
    righe = out.splitlines()
    ramo = None
    if righe and righe[0].startswith("##"):
        ramo = righe[0][2:].strip().split("...")[0].strip()
        righe = righe[1:]
    return ramo, len(righe)


def _git_stato(percorso: str, chiedi_stato: bool):
    """Ultimo commit, ramo e file modificati di una cartella git.

    Due processi invece di tre: `status --branch` porta anche il ramo, quindi la
    chiamata a `branch --show-current` non serve.

    Torna `ramo` e `sporchi` a None quando lo stato non e' stato chiesto o non e'
    arrivato in tempo: chi scrive nel database deve tenere il valore di prima
    invece di scrivere zero, o una cartella lenta risulterebbe pulita.
    """
    head = run(["git", "-C", percorso, "log", "-1", "--format=%H\x1f%cI\x1f%s"], timeout=8)
    ramo = sporchi = None
    if chiedi_stato:
        ramo, sporchi = _leggi_stato(run(
            ["git", "-C", percorso, "status", "--porcelain", "--branch"],
            timeout=STATO_TIMEOUT))
    return head, ramo, sporchi


def sync_local_git(conn, progress=None) -> int:
    cfg = config.load_config()
    roots = [expand(r) for r in cfg.get("code_roots", [])]
    drive = drive_root()
    if drive:
        roots.append(drive)

    cartelle = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            if (entry.is_dir() and not entry.name.startswith(".")
                    and os.path.isdir(os.path.join(entry.path, ".git"))):
                cartelle.append((entry.name, entry.path))

    limite = (datetime.now(timezone.utc)
              - timedelta(hours=STATO_RIPROVA_ORE)).strftime("%Y-%m-%dT%H:%M:%SZ")
    chiedi = {}
    for nome, percorso in cartelle:
        visto = store.get_meta(conn, f"git_lento:{percorso}") or ""
        chiedi[percorso] = visto < limite

    # I processi git aspettano il disco, non la CPU: in parallelo il giro dura
    # quanto la cartella piu' lenta invece della somma di tutte.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        esiti = list(pool.map(
            lambda c: _git_stato(c[1], chiedi[c[1]]), cartelle))

    lenti = 0
    for (nome, percorso), (head, ramo, sporchi) in zip(cartelle, esiti):
        if chiedi[percorso] and sporchi is None:
            store.set_meta(conn, f"git_lento:{percorso}", store.now())
            lenti += 1
        elif sporchi is not None:
            store.set_meta(conn, f"git_lento:{percorso}", "")

        pid = resolve_path_project(conn, percorso)
        if pid is None:
            pid = store.upsert_project(conn, nome, nome.replace("-", " "), kind="progetto")
            store.link_project(conn, pid, "path", percorso)
        conn.execute(
            "INSERT INTO repos(name, local_path, branch, dirty, project_id, updated_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET local_path=excluded.local_path, "
            "branch=COALESCE(excluded.branch, repos.branch), "
            "dirty=COALESCE(excluded.dirty, repos.dirty), "
            "project_id=COALESCE(repos.project_id, excluded.project_id)",
            (nome, percorso, ramo, sporchi, pid, store.now()),
        )
        if head:
            sha, date, msg = (head.split("\x1f") + ["", "", ""])[:3]
            date = to_utc(date)
            conn.execute(
                "INSERT INTO commits(repo, sha, message, date, url) VALUES(?,?,?,?,?) "
                "ON CONFLICT(sha) DO NOTHING", (nome, sha, msg, date, ""))
            store.touch_project(conn, pid, date)
    conn.commit()
    if lenti:
        log(f"cartelle troppo lente per lo stato: {lenti}", progress)
    log(f"cartelle git locali: {len(cartelle)}", progress)
    return len(cartelle)


# --------------------------------------------------------------------------
# 6. coda degli hook (sessioni aperte in tempo reale)
# --------------------------------------------------------------------------

def drain_queue(conn, progress=None) -> int:
    path = config.QUEUE_FILE
    if not path.exists():
        return 0
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
        path.write_text("", "utf-8")
    except OSError:
        return 0
    n = 0
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ts = rec.get("ts") or store.now()
        event = rec.get("event", "hook")
        cwd = rec.get("cwd") or ""
        sid = rec.get("session_id") or ""
        pid = resolve_path_project(conn, cwd) if cwd else None
        titles = {"SessionStart": "sessione aperta", "SessionEnd": "sessione chiusa"}
        store.add_event(conn, ts, "hook", titles.get(event, event),
                        os.path.basename(cwd.rstrip("/")), pid, sid, "hook",
                        dedup=f"hook:{event}:{sid}:{ts}")
        if event == "SessionStart":
            store.set_meta(conn, "live_session", sid)
            store.set_meta(conn, "live_since", ts)
        n += 1
    conn.commit()
    log(f"eventi hook: {n}", progress)
    return n


# --------------------------------------------------------------------------
# orchestrazione
# --------------------------------------------------------------------------

# Stessa soglia con cui un progetto verrebbe segnalato come fermo: invece di
# dire che una cartella di passaggio è ferma, la si archivia.
GIORNI_PRIMA_DI_ARCHIVIARE = 14


def attribuisci_commit(conn, progress=None) -> int:
    """Da quale conversazione è uscito ogni commit.

    Un commit non dice mai da dove viene. Ma se alle 14:32 hai committato su un
    repo, e fra le 14:05 e le 14:40 c'era aperta una sessione su quel progetto,
    è quasi sempre quella. Si accetta anche mezz'ora dopo la fine: si committa
    quando la sessione è già finita, non mentre parla.

    Non è una prova, è un indizio, e serve a una cosa sola: poter risalire dal
    commit alla conversazione che l'ha prodotto senza cercare a mano.
    """
    fatti = 0
    finestra = ("AND started_at <= ? AND datetime(COALESCE(NULLIF(ended_at,''), started_at), "
                "'+30 minutes') >= datetime(?) ORDER BY started_at DESC LIMIT 1")
    for c in conn.execute(
            "SELECT c.rowid AS rid, c.date, r.project_id, r.local_path, r.name FROM commits c "
            "JOIN repos r ON r.name = c.repo "
            "WHERE COALESCE(c.session_id,'') = '' "
            "ORDER BY c.date DESC LIMIT 400").fetchall():
        riga = None
        if c["project_id"]:
            riga = conn.execute(
                "SELECT session_id FROM sessions WHERE project_id = ? " + finestra,
                (c["project_id"], c["date"], c["date"])).fetchone()
        # Seconda strada: la cartella. Un progetto può non essere legato al repo,
        # ma se la sessione girava dentro quella cartella il commit è suo.
        if not riga and c["local_path"]:
            riga = conn.execute(
                "SELECT session_id FROM sessions WHERE cwd LIKE ? " + finestra,
                (c["local_path"].rstrip("/") + "%", c["date"], c["date"])).fetchone()
        if riga:
            conn.execute("UPDATE commits SET session_id=? WHERE rowid=?",
                         (riga["session_id"], c["rid"]))
            fatti += 1
    if fatti:
        conn.commit()
        if progress:
            progress(f"commit legati a una sessione: {fatti}")
    return fatti


def cura_progetti(conn, progress=None) -> int:
    """Un progetto nato da una cartella dove hai lavorato una volta tre
    settimane fa non è un progetto attivo: è un ricordo.

    Senza questa regola l'elenco si riempie di cartelle di passaggio e il
    riepilogo continua a segnalare come "fermo" qualcosa che è solo finito.
    Si tocca solo quello che ha creato l'ingest da solo (auto=1) e che non ha
    né un repo né un file di memoria: quelli li hai dichiarati tu.
    """
    limite = (datetime.now(timezone.utc) - timedelta(days=GIORNI_PRIMA_DI_ARCHIVIARE)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "UPDATE projects SET status='archiviato', updated_at=? "
        "WHERE auto=1 AND hidden=0 AND status='attivo' "
        "AND (last_activity IS NULL OR last_activity < ?) "
        "AND id NOT IN (SELECT project_id FROM project_links WHERE kind IN ('repo','memory')) "
        "AND (SELECT COUNT(*) FROM sessions s WHERE s.project_id=projects.id) <= 2",
        (store.now(), limite))
    if cur.rowcount:
        log(f"progetti archiviati: {cur.rowcount}", progress)
    conn.commit()
    return cur.rowcount


def sync(full=False, progress=None, skip_git=False, modo="tutto",
         ricalcola=False) -> dict:
    """Le fonti, lette in due giri diversi.

    Caldo: la coda degli hook e la coda nuova dei transcript. Sono pochi byte,
    costa meno di un secondo e tiene aggiornato quello che stai facendo adesso.

    Freddo: memoria, skill, repo, git, archiviazione dei progetti e indice di
    ricerca. Cambiano poche volte al giorno e costano qualche secondo.

    Prima erano un giro solo, e per sapere se avevi appena aperto una sessione
    si pagava anche la lettura di venti repo.
    """
    conn = store.connect()
    store.init_db(conn)
    inizio = store.now()
    result = {}
    caldo = modo in ("tutto", "caldo")
    freddo = modo in ("tutto", "freddo")

    keywords = sync_seed(conn, progress) if freddo else raccogli_keywords(conn)

    if caldo:
        result["hook"] = drain_queue(conn, progress)
        result["sessioni"] = sync_sessions(conn, keywords, progress, full=full)
        from . import codex, lavagna
        result["codex"] = codex.sync(conn, keywords, progress, full=full)
        result["lavagna"] = lavagna.sync(conn, progress)

    # Dopo il giro caldo, cosi' ricalcola anche le sessioni appena arrivate, e
    # fuori dai due giri perche' non e' una fonte: e' una rilettura di quello
    # che c'e' gia'.
    if ricalcola:
        result["riattribuite"] = riattribuisci(conn, progress)

    if freddo:
        result["memoria"] = sync_memory(conn, progress)
        result["capacita"] = sync_capabilities(conn, progress)
        if not skip_git:
            result["repo"] = sync_repos(conn, progress)
            result["git_locali"] = sync_local_git(conn, progress)
        result["archiviati"] = cura_progetti(conn, progress)
        result["commit_attribuiti"] = attribuisci_commit(conn, progress)
        # Un lancio può morire anche senza che il server si fermi: se il
        # processo non c'è più, la riga non deve restare "in corso" fino al
        # prossimo riavvio.
        try:
            from . import cantiere
            fermi = cantiere.riconcilia(conn)
            if fermi and progress:
                progress(f"lanci appesi chiusi: {fermi}")
            result["lanci_chiusi"] = fermi
        except Exception:
            pass
        log("indice di ricerca", progress)
        store.rebuild_search(conn)

    # L'indice sui turni: e' incrementale, un file gia' visto e non cambiato
    # costa una stat. Il primo giro su 1283 transcript ha preso 3,8 secondi.
    # Sta fuori dal blocco freddo perche' e' la cosa che rende la ricerca utile,
    # e va aggiornata anche nei sync leggeri.
    try:
        from . import turni
        # `full` e' il parametro che chiede di rileggere tutto: prima qui c'era
        # un confronto con la stringa "full", che `modo` non vale mai (tutto,
        # caldo, freddo), quindi la rilettura completa non partiva nemmeno con
        # `plancia sync --full`.
        esito = turni.indicizza(conn, completo=full)
        result["turni_indicizzati"] = esito["turni"]
    except Exception as exc:  # un indice mancato non deve far fallire il sync
        result["turni_errore"] = f"{type(exc).__name__}: {exc}"

    store.set_meta(conn, "last_sync", inizio)
    store.set_meta(conn, "last_sync_end", store.now())
    store.set_meta(conn, f"last_sync_{modo}", store.now())
    conn.commit()
    conn.close()
    from . import briefing
    briefing.write_cache()
    if freddo:
        # il riepilogo si prepara qui, in un filo a parte: quando lo chiedi
        # dev'esserci già
        import threading
        from . import recap as _recap
        threading.Thread(target=lambda: _recap.prepara(), daemon=True).start()
    return result


def raccogli_keywords(conn) -> dict:
    """Le parole chiave dal seed, senza riscrivere i progetti.

    Il giro caldo ha bisogno di indovinare il progetto di una sessione, ma non
    di rifare l'anagrafe.
    """
    seed = load_seed()
    fuori = {}
    for spec in seed.get("projects", []):
        if not spec.get("keywords"):
            continue
        riga = conn.execute("SELECT id FROM projects WHERE key=?",
                            (store.slugify(spec["key"]),)).fetchone()
        if riga:
            fuori[riga["id"]] = spec["keywords"]
    return fuori
