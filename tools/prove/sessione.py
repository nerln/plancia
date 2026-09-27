"""Prove di plancia/sessione.py: chi ha chiamato il server MCP adesso.

Ogni scenario isola esplicitamente le variabili d'ambiente e le cartelle base
(`config.CLAUDE_DIR`, `codex.CODEX_HOME`/`codex.CONFIG_TOML`) da quelle vere di
questo processo: la sessione che sta eseguendo questa prova è essa stessa una
sessione Claude Code reale, con CLAUDE_CODE_SESSION_ID e CLAUDE_PID veri
nell'ambiente. Senza isolamento le prove leggerebbero (o scriverebbero,
per il test del server MCP) accanto ai file veri di chi le lancia.

La cartella base di Codex ha un'unica fonte, `codex.CODEX_HOME` (vedi
plancia/sessione.py): sessione.py la legge da lì al momento della chiamata,
quindi sovrascrivere `codex.CODEX_HOME` (insieme a `codex.CONFIG_TOML`, che
codex.py calcola una volta sola all'import e non ricalcola da CODEX_HOME)
basta per isolare sia la ricerca del rollout sia `registra_mcp()`.

`esegui(prova)` è la firma che tools/prova.py chiamerà una volta fuso
L0-PROVE; fino ad allora si lancia da soli con
`python3 tools/prove/sessione.py` (blocco `__main__` in fondo).
"""

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


# --------------------------------------------------------------------------
# isolamento: env e cartelle base non toccano niente di vero
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _ambiente(**valori):
    """Imposta (o toglie, con None) le variabili date; le rimette uscendo.

    Per ogni scenario copre esplicitamente anche le chiavi non passate ma
    lette da sessione.py (altrimenti resterebbero quelle vere di questa
    sessione, non quelle del test).
    """
    chiavi = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_PID")
    complete = {k: None for k in chiavi}
    complete.update(valori)
    vecchi = {}
    for k, v in complete.items():
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
def _cartelle_base(config_mod, claude_dir=None):
    """Sposta config.CLAUDE_DIR su una cartella finta.

    È letta a ogni chiamata (non congelata in una chiusura), quindi
    riassegnare l'attributo del modulo basta: non serve un env var letto
    prima dell'import, che nel processo di prova arriverebbe comunque tardi.
    """
    vecchio_claude = config_mod.CLAUDE_DIR
    if claude_dir is not None:
        config_mod.CLAUDE_DIR = Path(claude_dir)
    try:
        yield
    finally:
        config_mod.CLAUDE_DIR = vecchio_claude


@contextlib.contextmanager
def _codex_home_finto(codex_mod, cartella):
    """Sposta codex.CODEX_HOME e codex.CONFIG_TOML su una cartella finta.

    Le due prove nuove per registra_mcp() (in fondo a questo file) e la prova
    del rollout più recente condividono questo helper: un solo punto da
    sovrascrivere invece di uno per ciascuna, perché sessione.py legge
    `codex.CODEX_HOME` e non una copia propria (vedi commento in cima al
    modulo e in plancia/sessione.py).
    """
    vecchio_home = codex_mod.CODEX_HOME
    vecchio_cfg = codex_mod.CONFIG_TOML
    cartella = Path(cartella)
    codex_mod.CODEX_HOME = cartella
    codex_mod.CONFIG_TOML = cartella / "config.toml"
    try:
        yield
    finally:
        codex_mod.CODEX_HOME = vecchio_home
        codex_mod.CONFIG_TOML = vecchio_cfg


def _scrivi_sessione_file(cartella_claude, pid, session_id):
    d = Path(cartella_claude) / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.json" % pid)).write_text(
        json.dumps({"sessionId": session_id}), "utf-8")


def _scrivi_rollout(cartella_codex, uuid, cwd, quando):
    """Un rollout finto con mtime impostato esplicitamente (per l'ordine)."""
    d = Path(cartella_codex) / "sessions" / "2026" / "09" / "16"
    d.mkdir(parents=True, exist_ok=True)
    riga = json.dumps({"type": "session_meta",
                       "payload": {"id": uuid, "cwd": cwd}})
    path = d / ("rollout-2026-09-16T10-00-00-%s.jsonl" % uuid)
    path.write_text(riga + "\n", "utf-8")
    os.utime(str(path), (quando, quando))


# --------------------------------------------------------------------------
# esegui
# --------------------------------------------------------------------------

def esegui(prova) -> None:
    from plancia import actions, codex, config, sessione, store

    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-sessione-"))
    try:
        vuota = tmp / "claude-vuota"
        vuota.mkdir()

        # 1. CLAUDE_CODE_SESSION_ID nell'ambiente, nessun file di sessione.
        with _ambiente(CLAUDE_CODE_SESSION_ID="xyz-1"):
            with _cartelle_base(config, claude_dir=vuota):
                r = sessione.corrente(argv=["bin/plancia-mcp"])
        prova("corrente() legge CLAUDE_CODE_SESSION_ID dall'ambiente",
              r["session_id"] == "xyz-1" and r["origine"] == "env" and r["agent"] == "claude",
              str(r))

        # 2. Come sopra, ma dentro un subagente: l'id è comunque quello del padre.
        with _ambiente(CLAUDE_CODE_SESSION_ID="xyz-1", CLAUDE_CODE_CHILD_SESSION="1"):
            with _cartelle_base(config, claude_dir=vuota):
                r = sessione.corrente(argv=["bin/plancia-mcp"])
        prova("un subagente porta comunque l'id del padre",
              r["session_id"] == "xyz-1" and r["origine"] == "env",
              str(r))

        # 3. Variabile assente: si ripiega su os.getppid() contro il file finto.
        cartella3 = tmp / "claude-3"
        cartella3.mkdir()
        ppid = os.getppid()
        _scrivi_sessione_file(cartella3, ppid, "dal-file")
        with _ambiente():
            with _cartelle_base(config, claude_dir=cartella3):
                r = sessione.corrente(argv=["bin/plancia-mcp"])
        prova("senza la variabile, il file di sessione del genitore vince",
              r["session_id"] == "dal-file" and r["origine"] == "file",
              str(r))

        # 3b (oltre il minimo richiesto). CLAUDE_PID diverge dalla variabile:
        # vince il file, come dice il testo del lotto ("se diverso, vince il
        # file e lo annoti in origine").
        cartella3b = tmp / "claude-3b"
        cartella3b.mkdir()
        _scrivi_sessione_file(cartella3b, "424242", "il-file-vince")
        with _ambiente(CLAUDE_CODE_SESSION_ID="dalla-variabile", CLAUDE_PID="424242"):
            with _cartelle_base(config, claude_dir=cartella3b):
                r = sessione.corrente(argv=["bin/plancia-mcp"])
        prova("CLAUDE_PID diverso dalla variabile: vince il file",
              r["session_id"] == "il-file-vince" and r["origine"] == "file",
              str(r))

        # 3c (correzione del critico). CLAUDE_PID assente (come su ogni
        # processo plancia-mcp vivo misurato il 16/09/2026: la variabile non
        # arriva mai al server), variabile presente ma il file del PPID vero
        # dice un'altra sessione: deve vincere il file, non l'ambiente.
        # Rossa con la versione di HEAD, che senza CLAUDE_PID nell'ambiente
        # non consultava affatto il file quando la variabile era presente.
        cartella3c = tmp / "claude-3c"
        cartella3c.mkdir()
        _scrivi_sessione_file(cartella3c, os.getppid(), "nuova")
        with _ambiente(CLAUDE_CODE_SESSION_ID="vecchia"):
            with _cartelle_base(config, claude_dir=cartella3c):
                r = sessione.corrente(argv=["bin/plancia-mcp"])
        prova("senza CLAUDE_PID nell'ambiente, vince comunque il file del ppid",
              r["session_id"] == "nuova" and r["origine"] == "file",
              str(r))

        # 4. Codex: argv con --agente codex, rollout più recente nella cwd.
        # Oltre al minimo richiesto dal lotto: un rollout più vecchio nella
        # stessa cwd e uno più nuovo in un'altra cwd, per dimostrare che il
        # confronto guarda sia la cwd sia la recenza, non uno dei due soli
        # (con un solo rollout, come nella prima versione di questa prova,
        # "più recente" e "nella cwd" non sono davvero esercitati).
        cartella_codex = tmp / "codex-4"
        cartella_cwd = tmp / "cwd-codex"
        cartella_cwd.mkdir()
        cartella_altra_cwd = tmp / "cwd-codex-altra"
        cartella_altra_cwd.mkdir()
        originale = os.getcwd()
        os.chdir(str(cartella_cwd))
        try:
            vera_cwd = os.getcwd()
            ora = time.time()
            uuid_vecchio = "00000000-0000-4000-8000-000000000000"
            uuid_giusto = "11111111-2222-4333-8444-555555555555"
            uuid_altra_cwd = "22222222-3333-4444-9555-666666666666"
            _scrivi_rollout(cartella_codex, uuid_vecchio, vera_cwd, ora - 3600)
            _scrivi_rollout(cartella_codex, uuid_giusto, vera_cwd, ora - 60)
            _scrivi_rollout(cartella_codex, uuid_altra_cwd, str(cartella_altra_cwd), ora)
            with _ambiente():
                with _codex_home_finto(codex, cartella_codex):
                    r = sessione.corrente(argv=["bin/plancia-mcp", "--agente", "codex"])
        finally:
            os.chdir(originale)
        prova("argv --agente codex prende il rollout più recente nella cwd giusta",
              r["agent"] == "codex" and r["session_id"] == uuid_giusto,
              str(r))

        # 5. task_add scrive cwd e agent (e host, se la colonna c'è già).
        # In un try: se questo salta con un'eccezione (successo con actions.py
        # riportato alla base, che non accetta ancora cwd/agent/host — vedi
        # TypeError misurato dal critico), le prove 6-9 devono girare comunque
        # invece di morire tutte insieme con lo stesso ImportError/TypeError.
        try:
            conn = store.connect()
            store.init_db(conn)
            riga = actions.task_add(conn, "prova sessione L0-SESSIONE", session_id="s",
                                    cwd="/c", agent="claude", host="h")
            tid = riga["id"]
            letto = conn.execute(
                "SELECT session_id, cwd, agent FROM tasks WHERE id=?", (tid,)).fetchone()
            ok5 = (letto["session_id"] == "s" and letto["cwd"] == "/c"
                   and letto["agent"] == "claude")
            dettaglio5 = str(dict(letto))
            conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
            conn.commit()
            conn.close()
        except Exception as exc:
            ok5, dettaglio5 = False, "eccezione: %r" % (exc,)
        prova("task_add scrive session_id, cwd e agent", ok5, dettaglio5)

        # 6-7. Il server MCP vero, come sottoprocesso.
        _prova_mcp(prova, tmp)

        # 8-9. registra_mcp(): scrive il blocco, e lo aggiorna se c'è già
        # senza il flag (correzione del critico: prima usciva con "già
        # presente" e lasciava il comando registrato senza --agente codex).
        _prova_registra_mcp(prova, codex, tmp)
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def _prova_mcp(prova, tmp) -> None:
    casa_mcp = tmp / "plancia-home-mcp"
    claude_vuota = tmp / "claude-vuota-mcp"
    casa_mcp.mkdir()
    claude_vuota.mkdir()

    env = dict(os.environ)
    env["PLANCIA_HOME"] = str(casa_mcp)
    env["CLAUDE_CONFIG_DIR"] = str(claude_vuota)
    env["CLAUDE_CODE_SESSION_ID"] = "xyz-2"
    env.pop("CLAUDE_PID", None)
    env.pop("CLAUDE_CODE_CHILD_SESSION", None)

    richieste = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-06-18"}}) + "\n" +
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                   "params": {"name": "plancia_task_add",
                              "arguments": {"title": "prova L0-SESSIONE via MCP"}}}) + "\n"
    )
    # Un'unica prova per "il server risponde" e "il task porta i campi
    # giusti": la prima parte da sola passa anche senza la patch (misurato
    # riportando solo mcp.py alla base: 7 verdi, 1 rossa), quindi non conta
    # come prova a sé — è solo la premessa per leggere il db.
    esito = None
    try:
        proc = subprocess.run(
            [sys.executable, str(RADICE / "bin" / "plancia-mcp")],
            input=richieste, capture_output=True, text=True, env=env, timeout=30)
        risposte = [json.loads(r) for r in proc.stdout.splitlines() if r.strip()]
        chiamata = next((r for r in risposte if r.get("id") == 2), None)
        esito = {"stderr": proc.stderr[-2000:], "risposte": risposte}
        ok_chiamata = bool(chiamata) and not chiamata["result"]["isError"]
        if ok_chiamata:
            conn2 = __import__("sqlite3").connect(str(casa_mcp / "plancia.db"))
            conn2.row_factory = __import__("sqlite3").Row
            riga = conn2.execute(
                "SELECT session_id, cwd, agent FROM tasks ORDER BY id DESC LIMIT 1").fetchone()
            conn2.close()
            ok = (bool(riga) and riga["session_id"] == "xyz-2" and riga["agent"] == "claude"
                  and bool(riga["cwd"]))
            dettaglio = str(dict(riga)) if riga else "nessuna riga"
        else:
            ok, dettaglio = False, str(esito)
    except Exception as exc:
        ok, dettaglio = False, "eccezione: %r" % (exc,)
    prova("il task creato via MCP porta session_id, cwd e agent dal server",
          ok, dettaglio)

    # 7. Resilienza: la cartella in cui il server è partito viene cancellata
    # mentre il processo resta vivo (scenario reale su questa macchina: le
    # copie in ~/dev/plancia-copie/<lotto> si cancellano a fine lotto con la
    # sessione ancora aperta lì). Rossa con la versione di HEAD di mcp.py:
    # sessione.corrente() solleva FileNotFoundError da os.getcwd(), call_tool
    # risponde "Errore interno" e il task non viene scritto affatto.
    cartella_viva = tmp / "cwd-cancellata"
    cartella_viva.mkdir()
    env2 = dict(env)
    env2["CLAUDE_CODE_SESSION_ID"] = "xyz-3"
    richiesta_init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2025-06-18"}}) + "\n"
    richiesta_add = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                "params": {"name": "plancia_task_add",
                                           "arguments": {"title": "prova cwd cancellata"}}}) + "\n"
    ok7, dettaglio7 = False, ""
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(RADICE / "bin" / "plancia-mcp")],
            cwd=str(cartella_viva), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env2, bufsize=1)
        proc.stdin.write(richiesta_init)
        proc.stdin.flush()
        riga_init = proc.stdout.readline()
        shutil.rmtree(str(cartella_viva), ignore_errors=True)
        proc.stdin.write(richiesta_add)
        proc.stdin.flush()
        riga_add = proc.stdout.readline()
        risposta = json.loads(riga_add) if riga_add.strip() else None
        ok_chiamata7 = bool(risposta) and not risposta["result"]["isError"]
        if ok_chiamata7:
            conn3 = __import__("sqlite3").connect(str(casa_mcp / "plancia.db"))
            conn3.row_factory = __import__("sqlite3").Row
            riga3 = conn3.execute(
                "SELECT session_id, cwd FROM tasks WHERE session_id='xyz-3' "
                "ORDER BY id DESC LIMIT 1").fetchone()
            conn3.close()
            ok7 = bool(riga3) and riga3["session_id"] == "xyz-3"
            dettaglio7 = str(dict(riga3)) if riga3 else "nessuna riga con session_id=xyz-3"
        else:
            dettaglio7 = "init=%r add=%r" % (riga_init, riga_add)
    except Exception as exc:
        dettaglio7 = "eccezione: %r" % (exc,)
    finally:
        if proc is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
    prova("cwd cancellata durante la sessione: il task si scrive comunque",
          ok7, dettaglio7)


def _prova_registra_mcp(prova, codex, tmp) -> None:
    # 8. Nessun blocco: registra_mcp() lo scrive con il flag.
    cartella8 = tmp / "codex-8"
    with _codex_home_finto(codex, cartella8):
        cartella8.mkdir()
        codex.CONFIG_TOML.write_text("# config di Codex, senza plancia\n", "utf-8")
        msg8 = codex.registra_mcp()
        testo8 = codex.CONFIG_TOML.read_text("utf-8")
    prova("registra_mcp() scrive il blocco con --agente codex quando manca",
          "[mcp_servers.plancia]" in testo8 and '"--agente", "codex"' in testo8,
          "%s | %r" % (msg8, testo8))

    # 9. Blocco già presente ma con args = [] (come sul config.toml vero
    # misurato il 16/09/2026, scritto prima che il lotto aggiungesse il
    # flag): registra_mcp() lo aggiorna, il resto del file resta identico,
    # e mcp_registrato() continua a dire True. Rossa con HEAD: prima di
    # questa correzione, registra_mcp() usciva con "già presente" al primo
    # `if "[mcp_servers.plancia]" in testo` e non toccava niente.
    cartella9 = tmp / "codex-9"
    blocco_vecchio = (
        "# altre righe di config.toml, scritte da Codex, non toccarle\n"
        "[qualcosa_altro]\n"
        "x = 1\n"
        "\n"
        "[mcp_servers.plancia]\n"
        "command = \"/vecchio/comando/senza/flag\"\n"
        "args = []\n"
        "startup_timeout_sec = 30\n"
    )
    with _codex_home_finto(codex, cartella9):
        cartella9.mkdir()
        codex.CONFIG_TOML.write_text(blocco_vecchio, "utf-8")
        msg9 = codex.registra_mcp()
        testo9 = codex.CONFIG_TOML.read_text("utf-8")
        registrato9 = codex.mcp_registrato()
    resto_intatto = ("# altre righe di config.toml, scritte da Codex, non toccarle" in testo9
                     and "[qualcosa_altro]" in testo9 and "x = 1" in testo9)
    ha_flag9 = '"--agente", "codex"' in testo9
    prova("registra_mcp() aggiorna un blocco vecchio senza il flag",
          ha_flag9 and registrato9 and resto_intatto and "args = []" not in testo9,
          "%s | resto_intatto=%s | %r" % (msg9, resto_intatto, testo9))


# --------------------------------------------------------------------------
# lancio da soli, finché prova.py non scopre tools/prove/ (L0-PROVE)
# --------------------------------------------------------------------------

if __name__ == "__main__":
    _casa = tempfile.mkdtemp(prefix="plancia-prova-sessione-main-")
    os.environ["PLANCIA_HOME"] = _casa

    falliti = []
    passati = 0

    def prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print("  ok   %s" % nome)
        else:
            falliti.append(nome)
            print("  NO   %s %s" % (nome, dettaglio))

    try:
        esegui(prova)
    finally:
        shutil.rmtree(_casa, ignore_errors=True)

    print("\n%d passate, %d fallite" % (passati, len(falliti)))
    if falliti:
        print("fallite: " + ", ".join(falliti))
    sys.exit(1 if falliti else 0)
