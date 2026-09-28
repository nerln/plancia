"""Le sessioni di Codex, lette come quelle di Claude Code.

Codex scrive un file per sessione in ~/.codex/sessions/AAAA/MM/GG/rollout-*.jsonl
e tiene i titoli in session_index.jsonl. Il formato è diverso da quello di Claude
ma dice le stesse cose: da dove hai lavorato, cosa hai chiesto, quanto è costato.

Una volta dentro la stessa tabella, i due agenti stanno sulla stessa cronologia e
si possono confrontare.
"""

import json
import os
import re
from pathlib import Path

from . import config, esclusi, store

CODEX_HOME = Path(os.environ.get("CODEX_HOME", config.HOME / ".codex"))
SESSIONI = CODEX_HOME / "sessions"
INDICE = CODEX_HOME / "session_index.jsonl"
CONFIG_TOML = CODEX_HOME / "config.toml"

MAX_PARSE = 256 * 1024
UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")


def titoli() -> dict:
    """id → nome del thread, come lo vedi nell'app di Codex."""
    fuori = {}
    try:
        for riga in INDICE.read_text("utf-8", errors="replace").splitlines():
            try:
                d = json.loads(riga)
            except Exception:
                continue
            if d.get("id") and d.get("thread_name"):
                fuori[d["id"]] = d["thread_name"]
    except OSError:
        pass
    return fuori


def leggi(path: Path, offset: int) -> dict:
    acc = {"offset": offset, "cwd": None, "id": None, "titolo": None, "prompt": None,
           "ts_min": None, "ts_max": None, "n_user": 0, "n_assistant": 0, "n_tools": 0,
           "out_tokens": 0, "in_tokens": 0, "modelli": set(), "scambi": 0,
           "thread": None}
    with open(path, "rb") as fh:
        if offset:
            fh.seek(offset)
        for raw in fh:
            acc["offset"] += len(raw)
            if len(raw) < 3:
                continue
            # I payload grossi sono output di tool: non servono per contare
            grande = len(raw) > MAX_PARSE
            if grande and b'"type":"response_item"' in raw[:120]:
                acc["n_tools"] += 1
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue

            ts = d.get("timestamp")
            if ts:
                if acc["ts_min"] is None or ts < acc["ts_min"]:
                    acc["ts_min"] = ts
                if acc["ts_max"] is None or ts > acc["ts_max"]:
                    acc["ts_max"] = ts

            tipo = d.get("type")
            p = d.get("payload") or {}

            if tipo == "session_meta":
                acc["id"] = acc["id"] or p.get("id") or p.get("session_id")
                # Un thread può essere ripreso più volte: ogni ripresa è un file
                # nuovo, ma il titolo nell'indice sta sul thread di partenza.
                acc["thread"] = acc["thread"] or p.get("session_id")
                acc["cwd"] = acc["cwd"] or p.get("cwd")
            elif tipo == "turn_context":
                acc["cwd"] = acc["cwd"] or p.get("cwd")
                if p.get("model"):
                    acc["modelli"].add(p["model"])
            elif tipo == "inter_agent_communication_metadata":
                acc["scambi"] += 1
            elif tipo == "event_msg":
                pt = p.get("type")
                if pt == "user_message":
                    testo = (p.get("message") or "").strip()
                    if testo and not testo.startswith("<"):
                        acc["n_user"] += 1
                        if not acc["prompt"]:
                            acc["prompt"] = testo
                elif pt == "agent_message":
                    acc["n_assistant"] += 1
                elif pt == "token_count":
                    uso = (p.get("info") or {}).get("total_token_usage") or {}
                    acc["out_tokens"] = max(acc["out_tokens"], uso.get("output_tokens") or 0)
                    acc["in_tokens"] = max(acc["in_tokens"], uso.get("input_tokens") or 0)
                elif pt == "thread_settings_applied":
                    modello = (p.get("thread_settings") or {}).get("model")
                    if modello:
                        acc["modelli"].add(modello)
            elif tipo == "response_item" and p.get("type") in ("function_call", "custom_tool_call"):
                acc["n_tools"] += 1
    return acc


def sync(conn, keywords, progress=None, full=False, escl=None) -> int:
    from . import ingest  # evita l'import circolare
    escl = escl if escl is not None else esclusi.carica()
    if not SESSIONI.is_dir():
        return 0
    nomi = titoli()
    files = sorted(SESSIONI.glob("*/*/*/rollout-*.jsonl"))
    aggiornate = 0
    for i, path in enumerate(files):
        try:
            size = path.stat().st_size
            mtime = path.stat().st_mtime
        except OSError:
            continue
        # Il nome è rollout-<data con trattini>-<uuid>: la data ha i trattini
        # anche lei, quindi l'id si prende dal fondo con una regex, non con split.
        m = UUID_RE.search(path.stem)
        if not m:
            continue
        sid = m.group(1)
        # Per id: si salta subito, senza nemmeno leggere il file. Il rollout
        # di Codex non ha la cwd nel nome (a differenza delle trascrizioni di
        # Claude Code, dove la cartella di progetto e' gia' nel percorso):
        # quella si scopre solo leggendo le prime righe, piu' sotto.
        if escl["sessioni"] and sid in escl["sessioni"]:
            continue
        row = conn.execute(
            "SELECT id, bytes_scanned, n_user, n_assistant, n_tools, in_tokens, out_tokens, "
            "scambi, title, first_prompt, started_at, project_id, models "
            "FROM sessions WHERE session_id=?", (sid,)).fetchone()
        offset = 0 if (full or row is None) else (row["bytes_scanned"] or 0)
        if offset > size:
            offset = 0
        elif row is not None and not full and size <= offset:
            continue
        ingest.log(f"codex {i + 1}/{len(files)} · {sid[:8]}", progress)
        try:
            acc = leggi(path, offset)
        except OSError:
            continue

        vecchio = (lambda c: row[c] if row else 0) if offset else (lambda c: 0)
        tieni = (lambda c: row[c] if row else None) if offset else (lambda c: None)
        titolo = (nomi.get(acc["thread"] or "") or nomi.get(acc["id"] or "")
                  or nomi.get(sid) or tieni("title"))
        prompt = tieni("first_prompt") or acc["prompt"]
        inizio = tieni("started_at") or acc["ts_min"] or ingest.iso(mtime)
        fine = acc["ts_max"] or ingest.iso(mtime)
        cwd = acc["cwd"]

        # Per cwd: si scopre solo ora, dopo aver letto le prime righe del
        # rollout. Se una sessione già in archivio (`row` non None) è ripresa
        # da un offset avanzato in un giro in cui la cwd non ricompare più
        # (già letta in un giro precedente), questo controllo non la vede: la
        # riga vecchia resta un giro in più, e la toglie `esclusi.purga()`,
        # che legge la cwd salvata invece di quella di questo solo giro.
        if cwd and esclusi.percorso_escluso(cwd, escl):
            continue

        pid = row["project_id"] if row else None
        if cwd:
            pid = ingest.progetto_per_cartella(conn, cwd, keywords,
                                               f"{titolo or ''} {prompt or ''}")

        modelli = sorted(set(store.jloads(row["models"], []) if (row and offset) else []) |
                         acc["modelli"])
        conn.execute(
            "INSERT INTO sessions(session_id, project_id, file, bytes_scanned, file_size, "
            "cwd, title, first_prompt, started_at, ended_at, n_user, n_assistant, n_tools, "
            "models, tools, in_tokens, out_tokens, agent, scambi, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'{}',?,?,'codex',?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET project_id=excluded.project_id, "
            "bytes_scanned=excluded.bytes_scanned, file_size=excluded.file_size, "
            "cwd=COALESCE(excluded.cwd, sessions.cwd), title=excluded.title, "
            "first_prompt=excluded.first_prompt, ended_at=excluded.ended_at, "
            "n_user=excluded.n_user, n_assistant=excluded.n_assistant, "
            "n_tools=excluded.n_tools, models=excluded.models, in_tokens=excluded.in_tokens, "
            "out_tokens=excluded.out_tokens, agent='codex', scambi=excluded.scambi, "
            "updated_at=excluded.updated_at",
            (sid, pid, str(path), acc["offset"], size, cwd, titolo,
             (prompt or "")[:2000], inizio, fine,
             vecchio("n_user") + acc["n_user"], vecchio("n_assistant") + acc["n_assistant"],
             vecchio("n_tools") + acc["n_tools"], json.dumps(modelli),
             vecchio("in_tokens") + acc["in_tokens"], vecchio("out_tokens") + acc["out_tokens"],
             vecchio("scambi") + acc["scambi"], store.now()))

        etichetta = titolo or (prompt or "sessione Codex")[:90]
        store.add_event(conn, inizio, "sessione", etichetta,
                        f"{acc['n_user']} messaggi · {acc['n_tools']} tool", pid, sid,
                        "codex", dedup=f"sessione:{sid}")
        if acc["scambi"]:
            store.add_event(conn, fine, "scambio",
                            f"Codex e Claude si sono parlati in {etichetta[:60]}",
                            f"{acc['scambi']} messaggi fra agenti", pid, sid, "codex",
                            dedup=f"scambio:{sid}")
        store.touch_project(conn, pid, fine)
        aggiornate += 1
        if aggiornate % 10 == 0:
            conn.commit()
    conn.commit()
    ingest.log(f"sessioni Codex: {aggiornate}", progress)
    return aggiornate


# --------------------------------------------------------------------------
# registrazione del server MCP dentro Codex
# --------------------------------------------------------------------------

BLOCCO = """
[mcp_servers.plancia]
command = "{cmd}"
args = ["--agente", "codex"]
startup_timeout_sec = 30
"""
# --agente codex e' il segnale con cui il server, lanciato da qui, sa di
# essere dentro Codex e non dentro Claude Code: lo legge plancia/sessione.py
# da sys.argv per scegliere come cercare la sessione (rollout piu' recente
# nella cwd, invece di CLAUDE_CODE_SESSION_ID). bin/plancia-mcp non lo
# consuma per altro, quindi non c'e' conflitto.


def mcp_registrato() -> bool:
    try:
        return "[mcp_servers.plancia]" in CONFIG_TOML.read_text("utf-8")
    except OSError:
        return False


def _sezione_plancia(testo: str) -> str:
    """Il testo del blocco [mcp_servers.plancia] dentro `testo`, o "" se assente."""
    i = testo.find("[mcp_servers.plancia]")
    if i < 0:
        return ""
    j = testo.find("\n[", i + 1)
    return testo[i:j] if j >= 0 else testo[i:]


def _blocco_ha_flag(testo: str) -> bool:
    """True se il blocco già scritto porta --agente codex negli args."""
    sezione = _sezione_plancia(testo)
    return "--agente" in sezione and "codex" in sezione


def _togli_blocco_plancia(testo: str) -> str:
    """`testo` senza il blocco [mcp_servers.plancia], se c'è (righe, non stringhe:
    stessa logica usata da `rimuovi_mcp()`, fattorizzata qui perché ora serve
    anche a `registra_mcp()` per riscrivere un blocco vecchio)."""
    righe = testo.splitlines(True)
    fuori, salta = [], False
    for riga in righe:
        if riga.strip() == "[mcp_servers.plancia]":
            salta = True
            continue
        if salta:
            if riga.startswith("[") or (riga.strip() == "" and fuori and fuori[-1].strip() == ""):
                salta = False
            else:
                continue
        fuori.append(riga)
    return "".join(fuori)


def registra_mcp() -> str:
    """Aggiunge il server a config.toml, o lo aggiorna se manca il flag.

    Il file lo scrive Codex, quindi si appende un blocco e basta: riscriverlo
    con una libreria TOML perderebbe commenti e ordine.

    Misurato il 16/09/2026 su questa macchina: ~/.codex/config.toml aveva già
    un blocco [mcp_servers.plancia] con `args = []` (registrato prima che
    questo lotto aggiungesse il flag --agente codex). Uscire silenziosamente
    con "già presente" in quel caso — come faceva questa funzione prima della
    correzione — lascia il comando reale senza il flag per sempre: a
    differenza di `install_mcp()` per Claude Code (che fa remove+add a ogni
    installazione), niente altro qui aggiorna un blocco già scritto. Quindi:
    blocco assente → lo si scrive; blocco presente senza il flag → lo si
    toglie e si riscrive con il flag (con backup, come per una scrittura
    nuova); blocco presente con il flag → niente da fare.
    """
    if not CONFIG_TOML.exists():
        return f"Codex non è configurato ({CONFIG_TOML} non esiste)"
    testo = CONFIG_TOML.read_text("utf-8")
    from . import setup_claude
    if "[mcp_servers.plancia]" in testo:
        if _blocco_ha_flag(testo):
            return "server MCP già presente in Codex"
        setup_claude.backup(CONFIG_TOML)
        testo = _togli_blocco_plancia(testo)
        if not testo.endswith("\n"):
            testo += "\n"
        CONFIG_TOML.write_text(testo + BLOCCO.format(cmd=setup_claude.MCP_CMD), "utf-8")
        return "server MCP aggiornato in Codex (flag --agente codex)"
    setup_claude.backup(CONFIG_TOML)
    if not testo.endswith("\n"):
        testo += "\n"
    CONFIG_TOML.write_text(testo + BLOCCO.format(cmd=setup_claude.MCP_CMD), "utf-8")
    return f"server MCP registrato in {CONFIG_TOML}"


def rimuovi_mcp() -> str:
    if not CONFIG_TOML.exists():
        return "niente da togliere da Codex"
    testo = CONFIG_TOML.read_text("utf-8")
    CONFIG_TOML.write_text(_togli_blocco_plancia(testo), "utf-8")
    return "server MCP tolto da Codex"


def stato() -> dict:
    return {
        "installato": CODEX_HOME.is_dir(),
        "sessioni": len(list(SESSIONI.glob("*/*/*/rollout-*.jsonl"))) if SESSIONI.is_dir() else 0,
        "mcp": mcp_registrato(),
        "config": str(CONFIG_TOML),
    }
