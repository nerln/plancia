"""Prove per plancia/riprendi.py (i tre stati e i comandi di ripresa) e per i
ritocchi che li accompagnano in cantiere.py, lavagna.py e sessione.py.

Non lancia mai un `claude` o un `codex` vero (regola della sessione): dove
`riprendi.apri()` o `cantiere._comando()` produrrebbero un comando reale, la
prova legge solo l'argv o lo passa a un lanciatore finto
(`PLANCIA_TERMINALE`). Non chiama mai `cantiere.avvia()`: anche con
`attendi=False` fa comunque partire un thread che lancia il processo per
davvero, quindi la traduzione `modo` -> `scrive` si prova sulla funzione
interna `cantiere._scrive_da`, non passando da lì.

Ogni gruppo che legge variabili d'ambiente (`PLANCIA_AGENTS_JSON`,
`PLANCIA_TERMINALE`) o cartelle base (`config.CLAUDE_DIR`, `codex.CODEX_HOME`)
le isola esplicitamente e le rimette uscendo: la sessione che lancia questa
prova è essa stessa una sessione Claude Code reale.

I task e le sessioni che servono a `backfill`/`annulla` vivono in una
connessione SQLite propria (`:memory:`), mai nel database demo che
`tools/prova.py` ha già riempito prima di arrivare qui: anche i task del demo
hanno `session_id` NULL, e contaminerebbero i conteggi.

La firma pubblica è `esegui(prova)` (tools/prova.py:32); per lanciare da
soli, `python3 tools/prove/riprendi.py` (blocco `__main__` in fondo).
"""

import contextlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


# --------------------------------------------------------------------------
# isolamento
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _ambiente(**valori):
    """Imposta (o toglie, con None) le variabili date; le rimette uscendo."""
    chiavi = ("PLANCIA_AGENTS_JSON", "PLANCIA_TERMINALE")
    completo = {k: None for k in chiavi}
    completo.update(valori)
    vecchi = {}
    for k, v in completo.items():
        vecchi[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(v)
    try:
        yield
    finally:
        for k, v in vecchi.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _cartelle_base(config_mod, codex_mod, claude_dir=None, codex_home=None):
    """Sposta `config.CLAUDE_DIR`/`codex.CODEX_HOME`: letti a ogni chiamata
    (mai congelati in una chiusura), quindi riassegnare l'attributo basta."""
    vecchio_claude, vecchio_codex = config_mod.CLAUDE_DIR, codex_mod.CODEX_HOME
    if claude_dir is not None:
        config_mod.CLAUDE_DIR = Path(claude_dir)
    if codex_home is not None:
        codex_mod.CODEX_HOME = Path(codex_home)
    try:
        yield
    finally:
        config_mod.CLAUDE_DIR = vecchio_claude
        codex_mod.CODEX_HOME = vecchio_codex


def _conn():
    from plancia import store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store.init_db(conn)
    return conn


def _task(**campi):
    base = {"id": 1, "title": "sistemare il backfill", "body": "", "session_id": None,
            "agent": "claude", "cwd": "", "host": "", "project_id": None, "prompt": ""}
    base.update(campi)
    return base


# --------------------------------------------------------------------------
# riprendi.stato
# --------------------------------------------------------------------------

def _prova_stato_claude(prova):
    from plancia import riprendi, config, codex

    conn = _conn()

    t = _task(session_id=None)
    s = riprendi.stato(conn, t)
    prova("senza session_id: persa, mai registrata",
          s["stato"] == "persa" and s["motivo"] == "mai registrata", str(s))

    t2 = _task(session_id="qualcosa", host="un-altro-mac")
    s2 = riprendi.stato(conn, t2)
    prova("host diverso da questa macchina: persa, motivo 'creato su <host>'",
          s2["stato"] == "persa" and s2["motivo"] == "creato su un-altro-mac", str(s2))

    with tempfile.TemporaryDirectory() as tmp:
        agenti = Path(tmp) / "agenti.json"
        agenti.write_text(json.dumps([
            {"pid": 4242, "cwd": "/tmp/altrove", "sessionId": "viva-123",
             "name": "altro", "status": "idle"}]), "utf-8")
        t3 = _task(session_id="viva-123", host=socket.gethostname())
        claude_dir_vuota = Path(tmp) / "claude-senza-registro"
        claude_dir_vuota.mkdir()
        with _ambiente(PLANCIA_AGENTS_JSON=str(agenti)):
            with _cartelle_base(config, codex, claude_dir=claude_dir_vuota):
                s3 = riprendi.stato(conn, t3)
        prova("session_id elencato in PLANCIA_AGENTS_JSON: viva",
              s3["stato"] == "viva", str(s3))

    with tempfile.TemporaryDirectory() as tmp:
        from plancia import richiamo
        claude_dir = Path(tmp) / "claude-config"
        cwd_finta = "/Users/prova/dev/qualcosa"
        cartella = claude_dir / "projects" / richiamo.cartella_sessione(cwd_finta)
        cartella.mkdir(parents=True)
        (cartella / "chiusa-456.jsonl").write_text('{"type":"summary"}\n', "utf-8")
        t4 = _task(session_id="chiusa-456", host=socket.gethostname(), cwd=cwd_finta)
        agenti_vuoto = Path(tmp) / "nessuno.json"  # non esiste: lista vuota, non viva
        with _ambiente(PLANCIA_AGENTS_JSON=str(agenti_vuoto)):
            with _cartelle_base(config, codex, claude_dir=claude_dir):
                s4 = riprendi.stato(conn, t4)
        prova("jsonl presente ma non elencata come viva: chiusa",
              s4["stato"] == "chiusa", str(s4))

        argv4 = riprendi.comando(t4, s4)
        prova("chiusa+claude: il comando ha --resume e l'id giusto",
              "--resume" in argv4 and "chiusa-456" in argv4, str(argv4))
        prova("chiusa+claude: l'ultimo argomento è il messaggio di ripresa",
              argv4[-1] == riprendi.messaggio(t4), str(argv4))

    with tempfile.TemporaryDirectory() as tmp:
        claude_dir = Path(tmp) / "claude-config-vuota"
        claude_dir.mkdir()
        t5 = _task(session_id="scaduta-789", host=socket.gethostname())
        agenti_vuoto = Path(tmp) / "nessuno.json"
        with _ambiente(PLANCIA_AGENTS_JSON=str(agenti_vuoto)):
            with _cartelle_base(config, codex, claude_dir=claude_dir):
                s5 = riprendi.stato(conn, t5)
        prova("nessuna trascrizione e non viva: persa, sessione scaduta",
              s5["stato"] == "persa" and s5["motivo"] == "sessione scaduta", str(s5))

    conn.close()


def _prova_stato_row_senza_colonna(prova):
    """`stato()` non deve rompersi su una `sqlite3.Row` che non porta tutte
    le colonne che si aspetta (es. una riga di `agenda`, che non ha `host`):
    una `Row` non ha `.get()`, quindi il vecchio `task["host"]` alzava
    `IndexError` invece di ripiegare sul default."""
    from plancia import riprendi

    conn = _conn()
    conn.execute("CREATE TABLE finta_riga (session_id TEXT, agent TEXT, cwd TEXT)")
    conn.execute("INSERT INTO finta_riga(session_id, agent, cwd) VALUES (NULL, 'claude', '')")
    conn.commit()
    riga = conn.execute("SELECT * FROM finta_riga").fetchone()
    try:
        s = riprendi.stato(conn, riga)
        ok = s.get("stato") == "persa" and s.get("motivo") == "mai registrata"
    except (IndexError, KeyError) as exc:
        ok, s = False, exc
    prova("stato() su una Row senza colonna 'host': niente IndexError, persa come una senza sessione",
          ok, str(s))
    conn.close()


def _prova_stato_codex(prova):
    from plancia import riprendi, config, codex

    conn = _conn()
    rid = "11111111-2222-3333-4444-555555555555"
    with tempfile.TemporaryDirectory() as tmp:
        codex_home = Path(tmp) / "codex-home"
        cartella = codex_home / "sessions" / "2026" / "09" / "16"
        cartella.mkdir(parents=True)
        rollout = cartella / f"rollout-2026-09-16T10-00-00-{rid}.jsonl"
        rollout.write_text('{"type":"session_meta","payload":{"cwd":"/tmp/x"}}\n', "utf-8")
        t = _task(session_id=rid, agent="codex", host=socket.gethostname())

        with _cartelle_base(config, codex, codex_home=codex_home):
            s = riprendi.stato(conn, t)
        prova("codex: rollout appena toccato -> viva",
              s["stato"] == "viva", str(s))

        vecchio = time.time() - 3600  # un'ora fa: oltre i 10 minuti di soglia
        os.utime(rollout, (vecchio, vecchio))
        with _cartelle_base(config, codex, codex_home=codex_home):
            s2 = riprendi.stato(conn, t)
        prova("codex: rollout fermo da un'ora -> chiusa",
              s2["stato"] == "chiusa", str(s2))

        argv2 = riprendi.comando(t, s2)
        prova("chiusa+codex: comando ['codex', 'resume', id] (niente exec)",
              len(argv2) == 3 and argv2[1] == "resume" and argv2[2] == rid, str(argv2))

        rollout.unlink()
        with _cartelle_base(config, codex, codex_home=codex_home):
            s3 = riprendi.stato(conn, t)
        prova("codex: rollout assente -> persa, sessione scaduta",
              s3["stato"] == "persa" and s3["motivo"] == "sessione scaduta", str(s3))
    conn.close()


def _prova_claude_vivo_fonti(prova):
    """Le due fonti di `_claude_vivo` (registro locale, poi `claude agents
    --json`) e il caso in cui nessuna delle due risponde: mai `None` deve
    diventare "chiusa" per finta."""
    from plancia import riprendi, config, codex, recap

    conn = _conn()

    # 1. il registro ha una voce col pid di questo stesso processo (vivo per
    #    definizione): basta lei, non serve consultare la seconda fonte.
    with tempfile.TemporaryDirectory() as tmp:
        claude_dir = Path(tmp) / "claude-registro-vivo"
        sessioni = claude_dir / "sessions"
        sessioni.mkdir(parents=True)
        (sessioni / f"{os.getpid()}.json").write_text(
            json.dumps({"sessionId": "registro-viva-1"}), "utf-8")
        t = _task(session_id="registro-viva-1", host=socket.gethostname())
        with _ambiente():
            with _cartelle_base(config, codex, claude_dir=claude_dir):
                s = riprendi.stato(conn, t)
        prova("registro con pid vivo (questo processo): viva",
              s["stato"] == "viva" and "aperta" in s["motivo"], str(s))

    # 2. il registro ha una voce, ma il pid non esiste più: non viva. Senza
    #    trascrizione da riprendere, il task risulta "persa".
    with tempfile.TemporaryDirectory() as tmp:
        claude_dir = Path(tmp) / "claude-registro-morto"
        sessioni = claude_dir / "sessions"
        sessioni.mkdir(parents=True)
        (sessioni / "999999.json").write_text(
            json.dumps({"sessionId": "registro-morta-1"}), "utf-8")
        t2 = _task(session_id="registro-morta-1", host=socket.gethostname())
        with _ambiente():
            with _cartelle_base(config, codex, claude_dir=claude_dir):
                s2 = riprendi.stato(conn, t2)
        prova("registro con pid morto: non viva (persa, nessuna trascrizione)",
              s2["stato"] == "persa" and s2["motivo"] == "sessione scaduta", str(s2))

    # 3. registro senza voce, e `claude agents --json` (qui un binario finto,
    #    mai il vero) risponde con qualcosa che non è JSON valido: nessuna
    #    fonte ha dato una risposta -> "viva" col motivo onesto, non "chiusa".
    with tempfile.TemporaryDirectory() as tmp:
        claude_dir = Path(tmp) / "claude-senza-registro"
        claude_dir.mkdir()
        finto_bin = Path(tmp) / "claude-rotto"
        finto_bin.write_text("#!/bin/sh\necho non-e-json\n", "utf-8")
        finto_bin.chmod(0o755)
        t3 = _task(session_id="nessuna-fonte", host=socket.gethostname())
        vecchio = recap.claude_bin
        recap.claude_bin = lambda: str(finto_bin)
        try:
            with _ambiente():
                with _cartelle_base(config, codex, claude_dir=claude_dir):
                    s3 = riprendi.stato(conn, t3)
        finally:
            recap.claude_bin = vecchio
        prova("nessuna fonte risponde: viva col motivo onesto (mai 'chiusa' per finta)",
              s3["stato"] == "viva" and "interrogare" in s3["motivo"], str(s3))
        prova("nessuna fonte risponde: comando() resta vuoto (nessun --resume senza fork)",
              riprendi.comando(t3, s3) == [], "")

    conn.close()


def _prova_viva_niente_comando(prova):
    from plancia import riprendi
    t = _task(session_id="viva-xyz", host=socket.gethostname())
    s = {"stato": "viva", "agent": "claude", "session_id": "viva-xyz", "cwd": "/tmp",
         "host": socket.gethostname(), "motivo": "aperta"}
    prova("viva: comando() è vuoto, non lancia niente",
          riprendi.comando(t, s) == [], "")
    prova("viva: messaggio() è quello per gli appunti",
          riprendi.messaggio(t) == f"riprendi il task {t['id']} di Plancia: {t['title']}",
          riprendi.messaggio(t))


def _prova_persa_comando(prova):
    from plancia import riprendi
    t = _task(session_id=None, title="ripartire da capo", body="qualche dettaglio")
    s = riprendi.stato(_conn(), t)
    argv = riprendi.comando(t, s)
    prova("persa: il comando è ['claude', prompt] con dentro il titolo",
          len(argv) == 2 and t["title"] in argv[1], str([argv[0], argv[1][:80] + "…"]))


# --------------------------------------------------------------------------
# apri()
# --------------------------------------------------------------------------

def _prova_apri(prova):
    from plancia import riprendi

    with tempfile.TemporaryDirectory() as tmp:
        # Il "lanciatore finto": uno script di sistema che scrive il suo unico
        # argomento su un file, invece di aprire un Terminale vero.
        lanciatore = Path(tmp) / "finto-terminale.sh"
        uscita = Path(tmp) / "lanciato.txt"
        lanciatore.write_text(
            "#!/bin/sh\nprintf '%s' \"$1\" > " + json.dumps(str(uscita)) + "\n", "utf-8")
        lanciatore.chmod(0o755)

        with tempfile.TemporaryDirectory() as agenti_dir:
            vuoto = Path(agenti_dir) / "nessuno.json"
            t = _task(session_id="chiusa-per-apri", host=socket.gethostname(),
                     cwd=str(Path(tmp)))
            # "chiusa" basta a questa prova (apri() non guarda oltre lo stato:
            # la sessione già usata sopra non ha jsonl, quindi qui si passa
            # uno stato costruito a mano per non doverne ricreare uno).
            s_finta = {"stato": "chiusa", "agent": "claude", "session_id": "chiusa-per-apri",
                      "cwd": str(Path(tmp)), "host": socket.gethostname(), "motivo": ""}
            import plancia.riprendi as rip
            argv_atteso = rip.comando(t, s_finta)

            with _ambiente(PLANCIA_TERMINALE=str(lanciatore), PLANCIA_AGENTS_JSON=str(vuoto)):
                # apri() ricalcola da solo lo stato (non prende s_finta): la
                # sessione non è nè viva nè ha trascrizione, quindi per lei è
                # "persa". Va bene lo stesso: la prova riguarda il lanciatore,
                # non quale stato specifico produce l'argv.
                risultato = riprendi.apri(t)

        contenuto = uscita.read_text("utf-8") if uscita.exists() else ""
        prova("apri(): il lanciatore finto riceve una riga con 'cd'",
              contenuto.startswith("cd "), contenuto)
        prova("apri(): la riga porta anche il comando (claude o l'exe risolto)",
              "claude" in contenuto or (argv_atteso and Path(argv_atteso[0]).name == "claude"),
              contenuto)
        prova("apri(): il risultato riporta lo stato e l'argv usato",
              risultato.get("stato") in ("chiusa", "persa") and risultato.get("argv"),
              str(risultato))

        # Sessione chiusa per davvero (jsonl presente), cosi' la riga contiene
        # anche --resume: è il caso concreto del lotto ("il file contiene cd
        # e --resume").
        from plancia import config, codex, richiamo
        claude_dir = Path(tmp) / "claude-per-apri"
        cwd_reale = str(Path(tmp) / "progetto")
        Path(cwd_reale).mkdir(parents=True, exist_ok=True)
        cartella = claude_dir / "projects" / richiamo.cartella_sessione(cwd_reale)
        cartella.mkdir(parents=True)
        (cartella / "davvero-chiusa.jsonl").write_text("{}\n", "utf-8")
        t2 = _task(id=7, title="riprendere sul serio", session_id="davvero-chiusa",
                  host=socket.gethostname(), cwd=cwd_reale)
        with _ambiente(PLANCIA_TERMINALE=str(lanciatore), PLANCIA_AGENTS_JSON=str(vuoto)):
            with _cartelle_base(config, codex, claude_dir=claude_dir):
                riprendi.apri(t2)
        contenuto2 = uscita.read_text("utf-8")
        prova("apri() su una sessione chiusa: il file scritto contiene cd e --resume",
              "cd " in contenuto2 and "--resume" in contenuto2, contenuto2)


def _prova_apri_stdout_pulito(prova):
    """apri() non deve mai far arrivare l'uscita del lanciatore sullo stdout
    di chi la chiama: dal server MCP quello stdout È il canale JSON-RPC (una
    riga estranea rompe il protocollo). Si verifica lanciando `apri()` in un
    sottoprocesso python vero (non nel processo di questa prova, che ha già
    il suo stdout normale) e catturando SOLO quello: se il lanciatore finto
    scrive `leaked-output` sul proprio stdout e questa riga arriva comunque
    fuori, vuol dire che `apri()` non lo cattura (il difetto di prima:
    `subprocess.run([...], check=False)` senza `stdout=`)."""
    with tempfile.TemporaryDirectory() as tmp:
        lanciatore = Path(tmp) / "finto-terminale-rumoroso.sh"
        lanciatore.write_text("#!/bin/sh\necho leaked-output\n", "utf-8")
        lanciatore.chmod(0o755)

        script = (
            "import sys, os\n"
            "sys.path.insert(0, %r)\n"
            "from plancia import riprendi\n"
            "t = {'id': 1, 'title': 'prova stdout', 'body': '', 'session_id': None,\n"
            "     'agent': 'claude', 'cwd': %r, 'host': 'un-altro-mac',\n"
            "     'project_id': None, 'prompt': ''}\n"
            "riprendi.apri(t)\n"
        ) % (str(RADICE), tmp)

        risultato = subprocess.run(
            [sys.executable, "-c", script],
            env=dict(os.environ, PLANCIA_TERMINALE=str(lanciatore)),
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
        prova("apri(): l'uscita del lanciatore non arriva sullo stdout di chi chiama",
              "leaked-output" not in risultato.stdout, repr(risultato.stdout))


# --------------------------------------------------------------------------
# _comando/_scrive_da di cantiere.py
# --------------------------------------------------------------------------

def _prova_cantiere(prova):
    from plancia import cantiere

    argv = cantiere._comando("claude", True, "/tmp/prova", sessione="sid-riprendi")
    prova("_comando(claude, sessione=...) porta --resume e --fork-session",
          "--resume" in argv and "--fork-session" in argv and "sid-riprendi" in argv, str(argv))
    prova("_comando(claude, sessione=...) tiene comunque i permessi di scrittura",
          all(t in argv for t in cantiere.TOOL_SCRITTURA), str(argv))

    argv_letto = cantiere._comando("claude", False, "/tmp/prova")
    prova("_comando(claude) senza sessione non ha --resume nè --fork-session",
          "--resume" not in argv_letto and "--fork-session" not in argv_letto, str(argv_letto))

    argv_codex = cantiere._comando("codex", False, "/tmp/prova", sessione="sid-codex")
    # `codex exec resume --help` (letto sul binario vero, mai lanciato un
    # agente) non elenca --cd/--sandbox/--color fra le sue opzioni: vanno
    # prima, sul comando padre `exec`; 'resume' e l'id sono le ultime voci,
    # seguite dal prompt '-' (stdin), e nessuna opzione compare dopo 'resume'.
    prova("_comando(codex, sessione=...): 'resume', l'id e '-' sono le ultime tre voci",
          argv_codex[-3:] == ["resume", "sid-codex", "-"], str(argv_codex))
    idx_resume = argv_codex.index("resume")
    prova("_comando(codex, sessione=...): nessuna opzione dopo 'resume'",
          not any(a.startswith("--") for a in argv_codex[idx_resume:]), str(argv_codex))
    prova("_comando(codex, sessione=...): --cd/--sandbox restano su 'exec', prima di 'resume'",
          "--cd" in argv_codex[:idx_resume] and "--sandbox" in argv_codex[:idx_resume],
          str(argv_codex))

    # compatibilità: il vecchio "modo" si traduce nello stesso booleano che
    # userebbe una chiamata nuova con "scrive". Non si chiama mai avvia() qui
    # (lancerebbe un processo vero anche con attendi=False): si prova solo la
    # traduzione, in cantiere._scrive_da.
    prova("_scrive_da(modo='proposta') vecchio stile -> scrive=False",
          cantiere._scrive_da(modo="proposta") is False, "")
    prova("_scrive_da(modo='esegui') vecchio stile -> scrive=True",
          cantiere._scrive_da(modo="esegui") is True, "")
    prova("_scrive_da(scrive='proposta') posizionale vecchio stile -> False",
          cantiere._scrive_da(scrive="proposta") is False, "")
    prova("_scrive_da(scrive=True) stile nuovo -> True",
          cantiere._scrive_da(scrive=True) is True, "")
    prova("_scrive_da senza niente -> False (di default proposta, come prima)",
          cantiere._scrive_da() is False, "")

    # _comando(modo="proposta") vecchio stile: deve restare "come prima"
    # (di lettura, niente acceptEdits) e non concedere la scrittura solo
    # perché la stringa non è vuota (era il difetto: prima una stringa in
    # `scrive` era sempre truthy, quindi 'proposta' -> scrive).
    argv_pos = cantiere._comando("claude", "proposta", "/tmp/prova")
    prova("_comando('claude', 'proposta', cwd) posizionale vecchio stile: niente acceptEdits",
          "--permission-mode" not in argv_pos, str(argv_pos))
    prova("_comando('claude', 'proposta', cwd) posizionale vecchio stile: solo TOOL_LETTURA",
          all(t in argv_pos for t in cantiere.TOOL_LETTURA) and
          not any(t in argv_pos for t in cantiere.TOOL_SCRITTURA
                  if t not in cantiere.TOOL_LETTURA), str(argv_pos))

    argv_kw = cantiere._comando("claude", modo="proposta", cwd="/tmp/prova")
    prova("_comando('claude', modo='proposta', cwd=...) per parola chiave: niente acceptEdits",
          "--permission-mode" not in argv_kw, str(argv_kw))

    argv_esegui = cantiere._comando("claude", modo="esegui", cwd="/tmp/prova")
    prova("_comando('claude', modo='esegui', cwd=...): acceptEdits e TOOL_SCRITTURA",
          "--permission-mode" in argv_esegui and
          all(t in argv_esegui for t in cantiere.TOOL_SCRITTURA), str(argv_esegui))

    # componi_prompt si accorcia quando c'è una sessione
    import sqlite3
    from plancia import store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store.init_db(conn)
    breve = cantiere.componi_prompt(conn, "il mio task", "dettagli lunghi", None,
                                    "fallo con calma", "esegui", "it", 42, "sid-9")
    prova("componi_prompt con sessione: si accorcia (niente TESTATA/CHIUSURA)",
          breve == "riprendi il task 42 di Plancia: il mio task. fallo con calma", breve)
    lungo = cantiere.componi_prompt(conn, "il mio task", "dettagli lunghi", None,
                                    "fallo con calma", "esegui", "it")
    prova("componi_prompt senza sessione: resta il prompt lungo di sempre",
          "## Il lavoro" in lungo and len(lungo) > len(breve), lungo[:60])
    conn.close()


# --------------------------------------------------------------------------
# backfill / annulla
# --------------------------------------------------------------------------

def _prova_backfill(prova):
    from plancia import riprendi, store

    conn = _conn()
    pid = store.upsert_project(conn, "prog-backfill", "Progetto per il backfill", _force=True)
    conn.commit()

    # sessione che copre esattamente il momento in cui il task è stato creato
    # (timestamp con i millisecondi, come li scrive davvero `ingest.py` da
    # `acc['ts_min']`: senza un parser che li legga, questa sessione non si
    # trova mai e la prova sotto è quella che lo dimostra)
    conn.execute(
        "INSERT INTO sessions(session_id, project_id, cwd, agent, started_at, ended_at) "
        "VALUES(?,?,?,?,?,?)",
        ("sess-coperta", pid, "/dev/prog-backfill", "claude",
         "2026-09-10T09:00:00.123Z", "2026-09-10T11:00:00.456Z"))
    # sessione vicina ma non sovrapposta: entro le due ore, per il ripiego
    conn.execute(
        "INSERT INTO sessions(session_id, project_id, cwd, agent, started_at, ended_at) "
        "VALUES(?,?,?,?,?,?)",
        ("sess-vicina", pid, "/dev/prog-backfill", "codex",
         "2026-09-11T08:00:00.789Z", "2026-09-11T08:05:00.012Z"))
    # sessione troppo lontana: non deve mai essere scelta
    conn.execute(
        "INSERT INTO sessions(session_id, project_id, cwd, agent, started_at, ended_at) "
        "VALUES(?,?,?,?,?,?)",
        ("sess-lontana", pid, "/dev/prog-backfill", "claude",
         "2026-01-01T00:00:00.000Z", "2026-01-01T00:05:00.000Z"))

    cur1 = conn.execute(
        "INSERT INTO tasks(title, status, project_id, created_at, updated_at) "
        "VALUES(?,?,?,?,?)",
        ("task dentro la finestra", "aperto", pid, "2026-09-10T10:00:00Z",
         "2026-09-10T10:00:00Z"))
    tid_coperto = cur1.lastrowid
    cur2 = conn.execute(
        "INSERT INTO tasks(title, status, project_id, created_at, updated_at) "
        "VALUES(?,?,?,?,?)",
        ("task vicino ma fuori finestra", "aperto", pid, "2026-09-11T09:30:00Z",
         "2026-09-11T09:30:00Z"))
    tid_vicino = cur2.lastrowid
    cur3 = conn.execute(
        "INSERT INTO tasks(title, status, project_id, created_at, updated_at) "
        "VALUES(?,?,?,?,?)",
        ("task senza niente vicino", "aperto", pid, "2027-01-01T00:00:00Z",
         "2027-01-01T00:00:00Z"))
    tid_orfano = cur3.lastrowid
    conn.commit()

    secco = riprendi.backfill(conn, "prova-secca", secco=True)
    prova("backfill secco: trova 2 associabili, 1 no, e non scrive niente",
          secco == {"ok": True, "trovati": 2, "non_trovati": 1, "secco": True}, str(secco))
    dopo_secco = conn.execute(
        "SELECT session_id FROM tasks WHERE id=?", (tid_coperto,)).fetchone()
    prova("backfill secco non ha scritto session_id",
          dopo_secco["session_id"] is None, str(dict(dopo_secco)))

    esito = riprendi.backfill(conn, "batch-vero")
    prova("backfill vero: stessi conteggi del secco",
          esito == {"ok": True, "trovati": 2, "non_trovati": 1, "secco": False}, str(esito))

    r1 = conn.execute("SELECT session_id, agent, cwd, host FROM tasks WHERE id=?",
                      (tid_coperto,)).fetchone()
    prova("il task dentro la finestra prende la sessione che lo copre",
          r1["session_id"] == "sess-coperta" and r1["agent"] == "claude" and
          r1["host"] == socket.gethostname(), str(dict(r1)))

    r2 = conn.execute("SELECT session_id FROM tasks WHERE id=?", (tid_vicino,)).fetchone()
    prova("il task senza sovrapposizione prende la sessione più vicina entro 2 ore",
          r2["session_id"] == "sess-vicina", str(dict(r2)))

    r3 = conn.execute("SELECT session_id FROM tasks WHERE id=?", (tid_orfano,)).fetchone()
    prova("il task senza niente vicino resta senza sessione",
          r3["session_id"] is None, str(dict(r3)))

    tolti = riprendi.annulla(conn, "batch-vero")
    prova("annulla rimette a NULL i due task toccati dal batch",
          tolti == 2, str(tolti))
    r1b = conn.execute("SELECT session_id, cwd, agent, host FROM tasks WHERE id=?",
                       (tid_coperto,)).fetchone()
    prova("dopo annulla il task torna com'era (session_id NULL)",
          r1b["session_id"] is None and r1b["cwd"] == "" and r1b["agent"] == "" and
          r1b["host"] == "", str(dict(r1b)))

    prova("batch non valido (con una virgola) viene rifiutato",
          riprendi.backfill(conn, "a,b").get("ok") is False, "")
    conn.close()


# --------------------------------------------------------------------------
# lavagna.da_plancia
# --------------------------------------------------------------------------

def _prova_lavagna(prova):
    from plancia import lavagna, store

    conn = _conn()
    pid = store.upsert_project(conn, "prog-lavagna", "Progetto per la lavagna", _force=True)
    conn.commit()
    conn.execute(
        "INSERT INTO tasks(title, status, project_id, agent, session_id, created_at, "
        "updated_at) VALUES(?,?,?,?,?,?,?)",
        ("task con sessione", "aperto", pid, "claude", "sid-lavagna",
         "2026-09-10T10:00:00Z", "2026-09-10T10:00:00Z"))
    conn.execute(
        "INSERT INTO tasks(title, status, project_id, agent, session_id, created_at, "
        "updated_at) VALUES(?,?,?,?,?,?,?)",
        ("task senza sessione", "aperto", pid, "", None,
         "2026-09-10T10:00:00Z", "2026-09-10T10:00:00Z"))
    conn.commit()

    voci = {v["titolo"]: v for v in lavagna.da_plancia(conn)}
    prova("da_plancia porta la sessione quando il task ce l'ha",
          voci["task con sessione"]["sessione"] == "sid-lavagna", str(voci["task con sessione"]))
    prova("da_plancia lascia sessione vuota quando il task non ce l'ha",
          voci["task senza sessione"]["sessione"] == "", str(voci["task senza sessione"]))
    conn.close()


def _prova_lavagna_sync_porta_sessione(prova):
    """`sync()` deve portare la sessione nelle righe di `agenda` che già
    esistono, non solo in quelle create la prima volta: `da_plancia()` la
    riempie sempre, ma senza `sessione=excluded.sessione` nell'`ON CONFLICT`
    un secondo sync su un task che ha appena preso un `session_id` lasciava
    la riga già in agenda con `sessione=''` per sempre."""
    from plancia import lavagna, store

    conn = _conn()
    pid = store.upsert_project(conn, "prog-lavagna-sync", "Progetto per il sync", _force=True)
    conn.commit()
    cur = conn.execute(
        "INSERT INTO tasks(title, status, project_id, agent, session_id, created_at, "
        "updated_at) VALUES(?,?,?,?,?,?,?)",
        ("task da aggiornare", "aperto", pid, "", None,
         "2026-09-10T10:00:00Z", "2026-09-10T10:00:00Z"))
    tid = cur.lastrowid
    conn.commit()

    # da_claude/da_codex leggono le liste vere della macchina: qui non
    # servono (si guarda solo la fonte "plancia"), e sostituirle con una
    # lista vuota evita di toccarle per niente durante la prova.
    vecchio_claude, vecchio_codex = lavagna.da_claude, lavagna.da_codex
    lavagna.da_claude = lambda esito=None: []
    lavagna.da_codex = lambda esito=None: []
    try:
        lavagna.sync(conn)
        prima = lavagna.elenco(conn, stato="tutti")
        voce_prima = next(v for v in prima if v["fonte"] == "plancia" and v["chiave"] == str(tid))
        prova("prima del session_id: la riga in agenda ha sessione vuota",
              voce_prima["sessione"] == "", str(dict(voce_prima)))

        conn.execute("UPDATE tasks SET session_id=? WHERE id=?", ("sid-sync-nuovo", tid))
        conn.commit()
        lavagna.sync(conn)
        dopo = lavagna.elenco(conn, stato="tutti")
        voce_dopo = next(v for v in dopo if v["fonte"] == "plancia" and v["chiave"] == str(tid))
        prova("un secondo sync porta la sessione nuova nella riga già esistente",
              voce_dopo["sessione"] == "sid-sync-nuovo", str(dict(voce_dopo)))
    finally:
        lavagna.da_claude = vecchio_claude
        lavagna.da_codex = vecchio_codex
    conn.close()


# --------------------------------------------------------------------------
# sessione.corrente: cwd cancellata -> ""
# --------------------------------------------------------------------------

def _prova_sessione_cwd_vera(prova):
    from plancia import sessione

    vecchia = os.getcwd()
    cartella = tempfile.mkdtemp(prefix="plancia-prova-riprendi-cwd-")
    os.chdir(cartella)
    try:
        os.rmdir(cartella)  # la cartella sparisce da sotto al processo
        # niente CLAUDE_CODE_SESSION_ID/CLAUDE_PID: si passa comunque dal ramo
        # del ripiego sulla cwd, che è l'unica cosa che questa prova guarda.
        chiavi = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_PID")
        vecchi_env = {k: os.environ.pop(k, None) for k in chiavi}
        try:
            info = sessione.corrente(argv=["plancia-mcp"])
        finally:
            for k, v in vecchi_env.items():
                if v is not None:
                    os.environ[k] = v
        prova("sessione.corrente con cwd cancellata: cwd è '' (non PWD)",
              info["cwd"] == "", str(info))
    finally:
        try:
            os.chdir(vecchia)
        except OSError:
            os.chdir(tempfile.gettempdir())


# --------------------------------------------------------------------------

def esegui(prova) -> None:
    _prova_stato_claude(prova)
    _prova_stato_row_senza_colonna(prova)
    _prova_stato_codex(prova)
    _prova_claude_vivo_fonti(prova)
    _prova_viva_niente_comando(prova)
    _prova_persa_comando(prova)
    _prova_apri(prova)
    _prova_apri_stdout_pulito(prova)
    _prova_cantiere(prova)
    _prova_backfill(prova)
    _prova_lavagna(prova)
    _prova_lavagna_sync_porta_sessione(prova)
    _prova_sessione_cwd_vera(prova)


if __name__ == "__main__":
    import tempfile as _tempfile

    CASA = Path(_tempfile.mkdtemp(prefix="plancia-prova-riprendi-"))
    os.environ["PLANCIA_HOME"] = str(CASA)

    falliti = []
    passati = 0

    def _prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print(f"  ok   {nome}")
        else:
            falliti.append(nome)
            print(f"  NO   {nome} {dettaglio}")

    print(f"archivio di prova: {CASA}\n")
    esegui(_prova)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
