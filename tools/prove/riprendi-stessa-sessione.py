"""Prove per LOTTO 21-RIPRENDI: il lavoro senza testa prosegue NELLA sessione che
il task (o il lancio) aveva salvato, non in una sessione nuova.

Il verdetto di Eugenio (30/09/2026): "i task da proseguire dovrebbero proseguire
sulle stesse sessioni che li hanno salvati da claude code o codex e non da una
nuova sessione creata ad hoc per il task singolo". Prima di questo lotto solo
"Riprendi" nel Terminale lo faceva: "In background" e le proposte
"Rilancia"/"Riprendi" partivano da una sessione nuova o da un fork (un id
nuovo). Qui si provano i tre percorsi (dashboard, MCP, riga di comando) e le
proposte di Jarvis.

Come si prova, senza mai lanciare un agente vero:

- un `claude` e un `codex` FINTI, in una cartella della prova, che registrano
  in un file gli argomenti veri con cui sono stati chiamati, la cartella in cui
  sono partiti e il prompt ricevuto da stdin. Plancia li trova dal
  `config.json` dell'archivio di prova (`claude_bin`, `codex_bin`);
- un archivio di prova a parte (`PLANCIA_HOME`, `HOME`, `CLAUDE_CONFIG_DIR`,
  `CODEX_HOME` in una cartella temporanea): il server, la riga di comando e il
  server MCP sono processi veri lanciati da qui su quell'archivio;
- appunti finti (`PLANCIA_CLIPBOARD`): la prova non tocca mai gli appunti veri.

Casi: sessione chiusa (si riprende con lo stesso id, nella sua cartella, senza
`--fork-session`), viva (non parte niente, si torna il messaggio da incollare;
con `copia` parte una copia), persa (parte una sessione nuova e la risposta lo
dice PRIMA), Codex chiuso (`exec resume <id>`), Codex con il thread tenuto
aperto dall'app (l'errore si riconosce e si dice), un lancio da rilanciare.
"""

import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import shutil
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
PORTA = 7975

_SID_CHIUSA = "sid-chiusa-0001"
_SID_VIVA = "sid-viva-0002"
_SID_PERSA = "sid-persa-0003"
_SID_LAVAGNA = "sid-lavagna-0004"
_SID_RUN = "sid-run-0005"
_SID_MCP = "sid-mcp-0006"
_SID_CLI = "sid-cli-0007"
_SID_JARVIS = "sid-jarvis-0008"
_SID_JARVIS_VIVA = "sid-jarvis-viva-0009"
_SID_CODEX = "0199aaaa-0000-0000-0000-00000000c001"
_SID_CODEX_CONFLITTO = "0199aaaa-0000-0000-0000-00000000c002"

_FINTO_CLAUDE = r'''
import json, os, sys
registro = %(registro)r
argv = sys.argv[1:]
if argv[:1] == ["agents"]:
    with open(registro, "a") as f:
        f.write(json.dumps({"bin": "claude", "argv": argv}) + "\n")
    print("[]")
    sys.exit(0)
stdin = sys.stdin.read() if "-p" in argv else ""
sid = argv[argv.index("--resume") + 1] if "--resume" in argv else None
if "--fork-session" in argv or not sid:
    sid = "nuova-%%d" %% os.getpid()
with open(registro, "a") as f:
    f.write(json.dumps({"bin": "claude", "argv": argv, "cwd": os.getcwd(),
                        "stdin": stdin, "sid": sid}) + "\n")
print(json.dumps({"type": "system", "session_id": sid}))
print(json.dumps({"type": "result", "result": "fatto", "session_id": sid,
                  "usage": {"output_tokens": 1}, "total_cost_usd": 0, "is_error": False}))
'''

_FINTO_CODEX = r'''
import json, os, sys
registro = %(registro)r
modo_file = %(modo)r
argv = sys.argv[1:]
stdin = sys.stdin.read() if argv and argv[-1] == "-" else ""
modo = open(modo_file).read().strip() if os.path.exists(modo_file) else "ok"
with open(registro, "a") as f:
    f.write(json.dumps({"bin": "codex", "argv": argv, "cwd": os.getcwd(),
                        "stdin": stdin, "modo": modo}) + "\n")
if modo == "conflitto":
    sys.stderr.write("Error: thread-store conflict: thread already has an active writer\n")
    sys.exit(1)
sid = argv[argv.index("resume") + 1] if "resume" in argv else "0199aaaa-0000-0000-0000-0000000000ff"
print("session id: " + sid)
print("fatto")
'''

_SEME = r'''
import json, os, socket, sys, time
sys.path.insert(0, %(radice)r)
from plancia import actions, richiamo, store, config
cfg = json.loads(%(cfg)r)
conn = store.connect(); store.init_db(conn)
host = socket.gethostname()
out = {}

def cartella(nome):
    p = os.path.join(cfg["lavoro"], nome); os.makedirs(p, exist_ok=True); return p

def trascrizione(cwd, sid):
    d = os.path.join(cfg["claude"], "projects", richiamo.cartella_sessione(cwd))
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, sid + ".jsonl"), "w").write('{"type":"summary"}\n')

def rollout(sid, vecchio=True):
    d = os.path.join(cfg["codex"], "sessions", "2026", "09", "01"); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "rollout-2026-09-01T10-00-00-" + sid + ".jsonl")
    open(f, "w").write('{}\n')
    if vecchio:
        t = time.time() - 7200; os.utime(f, (t, t))

def task(titolo, sid, cwd, agente="claude"):
    t = actions.task_add(conn, titolo, session_id=sid, cwd=cwd, agent=agente, host=host)
    return t["id"]

c_chiusa = cartella("chiusa"); trascrizione(c_chiusa, %(sid_chiusa)r)
out["t_chiusa"] = task("prova task chiuso", %(sid_chiusa)r, c_chiusa)

c_viva = cartella("viva"); trascrizione(c_viva, %(sid_viva)r)
os.makedirs(os.path.join(cfg["claude"], "sessions"), exist_ok=True)
open(os.path.join(cfg["claude"], "sessions", str(cfg["pid_vivo"]) + ".json"), "w").write(
    json.dumps({"sessionId": %(sid_viva)r}))
out["t_viva"] = task("prova task vivo", %(sid_viva)r, c_viva)

c_persa = cartella("persa")
out["t_persa"] = task("prova task perso", %(sid_persa)r, c_persa)
out["t_senza"] = task("prova task mai registrato", None, None)

c_mcp = cartella("mcp"); trascrizione(c_mcp, %(sid_mcp)r)
out["t_mcp"] = task("prova task mcp", %(sid_mcp)r, c_mcp)
c_cli = cartella("cli"); trascrizione(c_cli, %(sid_cli)r)
out["t_cli"] = task("prova task cli", %(sid_cli)r, c_cli)
c_jarvis = cartella("jarvis"); trascrizione(c_jarvis, %(sid_jarvis)r)
out["t_jarvis"] = task("prova task jarvis", %(sid_jarvis)r, c_jarvis)
c_jv = cartella("jarvis-viva"); trascrizione(c_jv, %(sid_jarvis_viva)r)
os.makedirs(os.path.join(cfg["claude"], "sessions"), exist_ok=True)
open(os.path.join(cfg["claude"], "sessions", str(cfg["pid_vivo2"]) + ".json"), "w").write(
    json.dumps({"sessionId": %(sid_jarvis_viva)r}))
out["t_jarvis_viva"] = task("prova task jarvis vivo", %(sid_jarvis_viva)r, c_jv)

c_codex = cartella("codex"); rollout(%(sid_codex)r)
out["t_codex"] = task("prova task codex", %(sid_codex)r, c_codex, "codex")
c_cc = cartella("codex-conflitto"); rollout(%(sid_codex_conflitto)r)
out["t_codex_conflitto"] = task("prova task codex occupato", %(sid_codex_conflitto)r, c_cc, "codex")

# una riga della lavagna: sessione nota solo dalla tabella sessions, nessun task
c_lav = cartella("lavagna"); trascrizione(c_lav, %(sid_lavagna)r)
conn.execute("INSERT INTO sessions(session_id, cwd, agent) VALUES(?,?,?)",
             (%(sid_lavagna)r, c_lav, "claude"))

# lanci falliti da rilanciare
c_run = cartella("run"); trascrizione(c_run, %(sid_run)r)
def run(prompt, sessione, task_id, cwd):
    cur = conn.execute("INSERT INTO runs(task_id, agente, modo, prompt, cwd, stato, inizio, sessione, esito) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                       (task_id, "claude", "proposta", prompt, cwd, "fallito", store.now(), sessione, "boom"))
    return cur.lastrowid
out["r_con_sessione"] = run("Lancio con la sua sessione", %(sid_run)r, None, c_run)
out["r_senza"] = run("Lancio senza sessione ne task", None, None, c_run)
out["r_del_task"] = run("Lancio del task chiuso", None, out["t_chiusa"], c_run)
conn.commit()
print(json.dumps(out))
'''


def _carica_finti():
    if "_finti" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_finti", Path(__file__).resolve().parent / "_finti.py")
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["_finti"] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules["_finti"]


_finti = _carica_finti()


class _Mondo:
    """L'archivio di prova, i programmi finti e i processi veri che lo usano."""

    def __init__(self, base: Path):
        self.base = base
        self.home = base / "plancia-home"
        self.casa = base / "casa"
        self.claude = base / "claude"
        self.codex = base / "codex"
        self.lavoro = base / "lavoro"
        self.finti = base / "finti"
        self.registro = self.finti / "registro.jsonl"
        self.modo_codex = self.finti / "modo-codex.txt"
        self.clipboard = self.finti / "appunti.txt"
        for d in (self.home, self.casa, self.claude, self.codex, self.lavoro, self.finti):
            d.mkdir(parents=True, exist_ok=True)
        claude = _finti.crea_finto(
            self.finti, "claude-finto",
            _FINTO_CLAUDE % {"registro": str(self.registro)})
        codex = _finti.crea_finto(
            self.finti, "codex-finto",
            _FINTO_CODEX % {"registro": str(self.registro), "modo": str(self.modo_codex)})
        (self.home / "config.json").write_text(
            json.dumps({"claude_bin": claude, "codex_bin": codex}), "utf-8")
        self.clip = _finti.crea_finto(
            self.finti, "appunti-finti",
            "import sys\nopen(%r, 'w').write(sys.stdin.read())\n" % str(self.clipboard))
        self.server = None
        self.token = ""
        self.ids = {}

    def env(self):
        e = dict(os.environ)
        _finti.casa_finta(e, self.casa)
        e.update({"PLANCIA_HOME": str(self.home), "CLAUDE_CONFIG_DIR": str(self.claude),
                  "CODEX_HOME": str(self.codex), "PLANCIA_CLIPBOARD": self.clip})
        e.pop("PLANCIA_AGENTS_JSON", None)
        e.pop("PLANCIA_TERMINALE", None)
        e["PATH"] = _finti.path_con(self.finti)
        return _finti.variabili_di_sistema(e)

    def python(self, codice: str, timeout=60) -> str:
        r = subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True,
                           env=self.env(), timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-800:])
        return r.stdout

    def semina(self):
        cfg = {"lavoro": str(self.lavoro), "claude": str(self.claude),
               "codex": str(self.codex), "pid_vivo": os.getpid(),
               "pid_vivo2": os.getppid()}
        codice = _SEME % {
            "radice": str(RADICE), "cfg": json.dumps(cfg),
            "sid_chiusa": _SID_CHIUSA, "sid_viva": _SID_VIVA, "sid_persa": _SID_PERSA,
            "sid_lavagna": _SID_LAVAGNA, "sid_run": _SID_RUN, "sid_mcp": _SID_MCP,
            "sid_cli": _SID_CLI, "sid_jarvis": _SID_JARVIS,
            "sid_jarvis_viva": _SID_JARVIS_VIVA, "sid_codex": _SID_CODEX,
            "sid_codex_conflitto": _SID_CODEX_CONFLITTO}
        self.ids = json.loads(self.python(codice).strip().splitlines()[-1])
        self.token = self.python(
            "import sys; sys.path.insert(0, %r)\nfrom plancia import config\n"
            "print(config.get_token())" % str(RADICE)).strip()

    def avvia_server(self):
        self.server = subprocess.Popen(
            [sys.executable, str(RADICE / "bin" / "plancia"), "serve", "--port", str(PORTA),
             "--no-sync"],
            env=self.env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL)
        for _ in range(80):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/status" % PORTA, timeout=2).read()
                return True
            except Exception:
                time.sleep(0.25)
        return False

    def ferma(self):
        if self.server:
            self.server.terminate()
            try:
                self.server.wait(timeout=10)
            except Exception:
                self.server.kill()

    def http(self, percorso, metodo="GET", corpo=None):
        dati = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (PORTA, percorso), data=dati, method=metodo,
            headers={"Content-Type": "application/json", "X-Plancia-Token": self.token})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            # un errore HTTP e' una risposta come un'altra per la prova: la
            # condizione che la guarda dira' NO, senza far cadere il resto
            try:
                corpo = json.loads(exc.read())
            except ValueError:
                corpo = {}
            return dict(corpo, _http=exc.code)

    # --- il registro dei programmi finti ---------------------------------
    def chiamate(self):
        if not self.registro.exists():
            return []
        righe = [json.loads(r) for r in self.registro.read_text("utf-8").splitlines() if r.strip()]
        # `claude agents --json` (per sapere se una sessione e' aperta) non e' un lavoro
        return [r for r in righe if r.get("argv", [None])[:1] != ["agents"]]

    def dopo(self, n_prima, atteso=1, secondi=15):
        """Le chiamate arrivate dopo la n-esima; aspetta che siano `atteso`."""
        fine = time.time() + secondi
        while time.time() < fine:
            nuove = self.chiamate()[n_prima:]
            if len(nuove) >= atteso:
                return nuove
            time.sleep(0.1)
        return self.chiamate()[n_prima:]

    def lancio_finito(self, run_id, secondi=20):
        fine = time.time() + secondi
        d = {}
        while time.time() < fine:
            d = self.http("/api/runs/%d" % run_id)
            if d.get("stato") not in ("in coda", "in corso"):
                return d
            time.sleep(0.2)
        return d


def _con(argv, chiave):
    """Il valore che segue `chiave` in `argv`, o None."""
    return argv[argv.index(chiave) + 1] if chiave in argv and argv.index(chiave) + 1 < len(argv) else None


def _percorsi_uguali(a, b):
    return os.path.realpath(a or "") == os.path.realpath(b or "")


def esegui(prova) -> None:
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-stessa-sessione-"))
    mondo = _Mondo(base)
    try:
        try:
            mondo.semina()
        except Exception as exc:
            prova("l'archivio di prova si semina", False, str(exc))
            return
        if not mondo.avvia_server():
            prova("il server di prova parte", False, "nessuna risposta su /api/status")
            return
        try:
            _dashboard(prova, mondo)
            _codex(prova, mondo)
            _rilancio(prova, mondo)
            _mcp(prova, mondo)
            _cli(prova, mondo)
            _jarvis(prova, mondo)
        finally:
            mondo.ferma()
    finally:
        shutil.rmtree(str(base), ignore_errors=True)


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------

def _dashboard(prova, m):
    ids = m.ids

    # --- chiusa: la STESSA sessione, nella sua cartella, senza fork --------
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_chiusa"], "POST", {"background": True})
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("dashboard, sessione chiusa: parte un claude senza testa", bool(c), str(r))
    prova("...riprende la sessione del task (--resume <id>)",
          _con(argv, "--resume") == _SID_CHIUSA, str(argv))
    prova("...SENZA --fork-session: e' la stessa sessione, non una copia",
          "--fork-session" not in argv, str(argv))
    prova("...in modalita' senza testa (-p)", "-p" in argv, str(argv))
    prova("...nella cartella in cui la sessione era nata",
          _percorsi_uguali((c[0] if c else {}).get("cwd"), str(m.lavoro / "chiusa")),
          str(c[0] if c else None))
    prova("...il messaggio dice di riprendere il task", "riprendi il task" in
          (c[0] if c else {}).get("stdin", ""), str(c[0] if c else None))
    prova("...la risposta dice che ha ripreso la sessione originale (piano.modo)",
          (r.get("piano") or {}).get("modo") == "riprendi" and r.get("continua") == "riprendi"
          and r.get("lanciato") is True, str(r))
    fine = m.lancio_finito(r["run"]) if r.get("run") else {}
    prova("...il lancio porta l'id della sessione originale (runs.sessione)",
          fine.get("sessione") == _SID_CHIUSA, str(fine)[:300])

    # --- viva: niente da lanciare, il messaggio da incollare --------------
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_viva"], "POST", {"background": True})
    time.sleep(1.0)
    prova("dashboard, sessione viva: NON parte nessun claude",
          len(m.chiamate()) == n, str(m.chiamate()[n:]))
    prova("...la risposta dice lanciato=false, piano 'niente' e porta il messaggio da incollare",
          r.get("lanciato") is False and (r.get("piano") or {}).get("modo") == "niente"
          and str(ids["t_viva"]) in (r.get("messaggio") or ""), str(r))

    # --- viva + copia esplicita: parte una copia, dichiarata --------------
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_viva"], "POST", {"background": True, "copia": True})
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("dashboard, sessione viva con copia=true: parte una COPIA (--fork-session)",
          _con(argv, "--resume") == _SID_VIVA and "--fork-session" in argv, str(argv))
    prova("...e la risposta la chiama copia", (r.get("piano") or {}).get("modo") == "copia", str(r))

    # --- persa: nuova, e la risposta lo dice ------------------------------
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_persa"], "POST", {"background": True})
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("dashboard, sessione persa: parte una sessione NUOVA (niente --resume)",
          bool(c) and "--resume" not in argv, str(argv))
    prova("...e la risposta lo dice (piano.modo nuova, avviso con la parola NUOVA)",
          (r.get("piano") or {}).get("modo") == "nuova" and "NUOVA" in (r.get("piano") or {}).get("avviso", ""),
          str(r.get("piano")))

    # --- l'anteprima dice cosa succederebbe, senza lanciare ---------------
    n = len(m.chiamate())
    a = m.http("/api/riprendi/%d" % ids["t_chiusa"], "POST", {"anteprima": True})
    g = m.http("/api/riprendi/%d" % ids["t_persa"])
    time.sleep(0.5)
    prova("dashboard, anteprima: non parte niente e torna il piano",
          len(m.chiamate()) == n and (a.get("piano") or {}).get("modo") == "riprendi", str(a))
    prova("dashboard, GET /api/riprendi/<id> porta il piano per lo stato persa",
          (g.get("piano") or {}).get("modo") == "nuova", str(g))

    # --- una riga della lavagna (solo l'id della sessione, nessun task) ---
    n = len(m.chiamate())
    r = m.http("/api/cantiere", "POST", {"titolo": "prova lavagna", "sessione": _SID_LAVAGNA})
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("POST /api/cantiere con la sola 'sessione' chiusa la riprende (stesso id, niente fork)",
          _con(argv, "--resume") == _SID_LAVAGNA and "--fork-session" not in argv, str(argv))
    prova("...nella cartella che la tabella sessions ricorda",
          _percorsi_uguali((c[0] if c else {}).get("cwd"), str(m.lavoro / "lavagna")),
          str(c[0] if c else None))
    n = len(m.chiamate())
    a = m.http("/api/cantiere", "POST", {"titolo": "x", "sessione": _SID_LAVAGNA, "anteprima": True})
    time.sleep(0.4)
    prova("POST /api/cantiere con anteprima=true non lancia e dice 'riprendi'",
          len(m.chiamate()) == n and (a.get("piano") or {}).get("modo") == "riprendi", str(a))
    n = len(m.chiamate())
    r = m.http("/api/cantiere", "POST", {"titolo": "prova senza sessione"})
    c = m.dopo(n)
    prova("POST /api/cantiere senza sessione resta un lancio nuovo, senza --resume",
          bool(c) and "--resume" not in c[0].get("argv", []), str(c))

    # --- un task senza sessione mai registrata: nuova, detto ---------------
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_senza"], "POST", {"background": True})
    c = m.dopo(n)
    prova("dashboard, task mai registrato: sessione nuova dichiarata",
          bool(c) and (r.get("piano") or {}).get("modo") == "nuova", str(r.get("piano")))


# --------------------------------------------------------------------------
# codex
# --------------------------------------------------------------------------

def _codex(prova, m):
    ids = m.ids
    m.modo_codex.write_text("ok", "utf-8")
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_codex"], "POST", {"background": True})
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("codex chiuso: parte `codex exec ... resume <id> -` (la stessa sessione)",
          argv[:1] == ["exec"] and argv[-3:] == ["resume", _SID_CODEX, "-"], str(argv))
    prova("...nessun `fork` e nessuna opzione dopo `resume`",
          "fork" not in argv and not any(a.startswith("--") for a in argv[argv.index("resume"):]),
          str(argv) if "resume" in argv else "nessun resume")
    prova("...nella cartella della sessione (--cd)",
          _percorsi_uguali(_con(argv, "--cd"), str(m.lavoro / "codex")), str(argv))
    prova("...il messaggio arriva da stdin", "riprendi il task" in (c[0] if c else {}).get("stdin", ""),
          str(c[0] if c else None))
    fine = m.lancio_finito(r["run"]) if r.get("run") else {}
    prova("...il lancio riuscito porta l'id della sessione di codex",
          fine.get("stato") == "riuscito" and fine.get("sessione") == _SID_CODEX, str(fine)[:300])

    # Codex tocca il rollout mentre lavora: subito dopo il lancio, il rollout e'
    # "toccato da meno di 10 minuti", ma la sessione l'ha appena chiusa Plancia
    # stessa, non un'app: un secondo lancio deve poterla riprendere lo stesso.
    rollout = next((m.codex / "sessions").glob("*/*/*/rollout-*-%s.jsonl" % _SID_CODEX))
    adesso = time.time() - 2
    os.utime(str(rollout), (adesso, adesso))
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_codex"], "POST", {"background": True})
    c = m.dopo(n)
    prova("codex: un secondo lancio subito dopo il primo riprende la stessa sessione "
          "(il rollout toccato e' il nostro, non di un'app)",
          bool(c) and (r.get("piano") or {}).get("modo") == "riprendi", str(r.get("piano")))
    m.lancio_finito(r["run"]) if r.get("run") else None
    # invece un rollout toccato ADESSO, senza un lancio nostro che lo spieghi, e' una viva
    rollout2 = next((m.codex / "sessions").glob("*/*/*/rollout-*-%s.jsonl" % _SID_CODEX_CONFLITTO))
    os.utime(str(rollout2), (time.time(), time.time()))
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_codex_conflitto"], "POST", {"background": True})
    time.sleep(0.8)
    prova("codex: un rollout toccato adesso e non da un lancio nostro e' una sessione viva, non parte niente",
          len(m.chiamate()) == n and (r.get("piano") or {}).get("modo") == "niente", str(r.get("piano")))
    old_t = time.time() - 7200
    os.utime(str(rollout2), (old_t, old_t))

    # il thread e' tenuto aperto dall'app: l'errore si riconosce e si dice
    m.modo_codex.write_text("conflitto", "utf-8")
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_codex_conflitto"], "POST", {"background": True})
    m.dopo(n)
    fine = m.lancio_finito(r["run"]) if r.get("run") else {}
    prova("codex con il thread aperto nell'app: il lancio e' 'bloccato', non un 'fallito' muto",
          fine.get("stato") == "bloccato", str(fine)[:300])
    prova("...e l'esito spiega che la sessione e' tenuta aperta dall'app",
          "aperta" in (fine.get("esito") or "") and "Codex" in (fine.get("esito") or ""),
          str(fine.get("esito")))
    stato_task = m.python(
        "import sys; sys.path.insert(0, %r)\nfrom plancia import store\n"
        "c = store.connect()\nprint(c.execute('SELECT status FROM tasks WHERE id=?', (%d,)).fetchone()[0])"
        % (str(RADICE), ids["t_codex_conflitto"])).strip()
    prova("...e il task resta 'aperto' (la sessione era occupata, il task non e' cambiato)",
          stato_task == "aperto", stato_task)
    m.modo_codex.write_text("ok", "utf-8")


# --------------------------------------------------------------------------
# rilancio di un lancio
# --------------------------------------------------------------------------

def _rilancio(prova, m):
    ids = m.ids
    n = len(m.chiamate())
    r = m.http("/api/cantiere", "POST", {"run": ids["r_con_sessione"]})
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("rilancio di un lancio che ha la sua sessione: la riprende (stesso id, niente fork)",
          _con(argv, "--resume") == _SID_RUN and "--fork-session" not in argv, str(argv))
    prova("...nella cartella del lancio", _percorsi_uguali((c[0] if c else {}).get("cwd"),
                                                          str(m.lavoro / "run")), str(c[0] if c else None))
    prova("...il messaggio racconta com'era finito il lancio",
          "Il lancio n. %d" % ids["r_con_sessione"] in (c[0] if c else {}).get("stdin", "")
          and "boom" in (c[0] if c else {}).get("stdin", ""), str(c[0] if c else None))

    n = len(m.chiamate())
    r = m.http("/api/cantiere", "POST", {"run": ids["r_del_task"]})
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("rilancio di un lancio senza sessione ma col task: riprende la sessione DEL TASK",
          _con(argv, "--resume") == _SID_CHIUSA, str(argv))

    n = len(m.chiamate())
    r = m.http("/api/cantiere", "POST", {"run": ids["r_senza"]})
    c = m.dopo(n)
    prova("rilancio di un lancio senza sessione ne task: riparte con lo stesso prompt, nuova, e lo dice",
          bool(c) and "--resume" not in c[0].get("argv", [])
          and (r.get("piano") or {}).get("modo") == "nuova"
          and "Lancio senza sessione ne task" in c[0].get("stdin", ""), str(r.get("piano")))
    a = m.http("/api/cantiere", "POST", {"run": ids["r_con_sessione"], "anteprima": True})
    prova("anteprima del rilancio: solo il piano", a.get("anteprima") is True
          and (a.get("piano") or {}).get("modo") == "riprendi", str(a))


# --------------------------------------------------------------------------
# MCP
# --------------------------------------------------------------------------

def _mcp_chiama(m, chiamate, atteso_dopo=None):
    """Parla col server MCP vero (bin/plancia-mcp) su stdin/stdout. Lo tiene
    aperto finche' i programmi finti non hanno registrato quanto atteso: un
    lancio vive in un thread del processo, e il processo non deve finire prima."""
    proc = subprocess.Popen([sys.executable, str(RADICE / "bin" / "plancia-mcp")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=m.env())
    n = len(m.chiamate())
    richieste = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18"}}]
    for i, (nome, args) in enumerate(chiamate, start=2):
        richieste.append({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                          "params": {"name": nome, "arguments": args}})
    proc.stdin.write("".join(json.dumps(r) + "\n" for r in richieste))
    proc.stdin.flush()
    if atteso_dopo:
        m.dopo(n, atteso_dopo)
    else:
        time.sleep(1.5)
    try:
        proc.stdin.close()
        out = proc.stdout.read()
        proc.wait(timeout=20)
    except Exception:
        proc.kill()
        out = ""
    risposte = {}
    for riga in out.splitlines():
        try:
            d = json.loads(riga)
        except ValueError:
            continue
        testo = "".join(c.get("text", "") for c in (d.get("result") or {}).get("content", []))
        risposte[d.get("id")] = testo
    return risposte, n


def _mcp(prova, m):
    ids = m.ids
    risp, n = _mcp_chiama(m, [
        ("plancia", {"azione": "riprendi", "id": ids["t_mcp"], "background": True}),
    ], atteso_dopo=1)
    c = m.chiamate()[n:]
    argv = (c[0] if c else {}).get("argv", [])
    prova("MCP plancia_riprendi background, sessione chiusa: riprende la stessa sessione",
          _con(argv, "--resume") == _SID_MCP and "--fork-session" not in argv, str(argv) + str(risp)[:200])
    prova("...nella cartella della sessione", _percorsi_uguali((c[0] if c else {}).get("cwd"),
                                                             str(m.lavoro / "mcp")), str(c[0] if c else None))
    prova("...la risposta dice 'riprendi'", '"continua": "riprendi"' in risp.get(2, ""), risp.get(2, "")[:300])

    risp, n = _mcp_chiama(m, [
        ("plancia", {"azione": "riprendi", "id": ids["t_viva"], "background": True}),
    ])
    prova("MCP plancia_riprendi background, sessione viva: non parte niente",
          len(m.chiamate()) == n, str(m.chiamate()[n:]))
    prova("...e la risposta lo dice ('niente') con il messaggio da incollare",
          '"lanciato": false' in risp.get(2, "") and '"modo": "niente"' in risp.get(2, ""),
          risp.get(2, "")[:300])

    risp, n = _mcp_chiama(m, [
        ("plancia", {"azione": "riprendi", "id": ids["t_persa"]}),
    ])
    prova("MCP plancia_riprendi senza background mostra il piano (nuova) e non lancia",
          len(m.chiamate()) == n and '"modo": "nuova"' in risp.get(2, ""), risp.get(2, "")[:300])

    risp, n = _mcp_chiama(m, [
        ("plancia", {"azione": "manda", "titolo": "prova manda mcp", "task_id": ids["t_mcp"]}),
    ], atteso_dopo=1)
    c = m.chiamate()[n:]
    argv = (c[0] if c else {}).get("argv", [])
    prova("MCP plancia_manda con task_id riprende la sessione del task (non ne apre una nuova)",
          _con(argv, "--resume") == _SID_MCP and "--fork-session" not in argv, str(argv) + str(risp)[:200])


# --------------------------------------------------------------------------
# riga di comando
# --------------------------------------------------------------------------

def _cli_esegui(m, args, timeout=60):
    return subprocess.run([sys.executable, str(RADICE / "bin" / "plancia")] + args,
                          capture_output=True, text=True, env=m.env(), timeout=timeout)


def _cli(prova, m):
    ids = m.ids
    n = len(m.chiamate())
    r = _cli_esegui(m, ["riprendi", str(ids["t_cli"]), "--background"])
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("CLI riprendi --background, sessione chiusa: riprende la stessa sessione",
          _con(argv, "--resume") == _SID_CLI and "--fork-session" not in argv,
          str(argv) + r.stdout[-200:] + r.stderr[-200:])
    prova("...nella cartella della sessione", _percorsi_uguali((c[0] if c else {}).get("cwd"),
                                                             str(m.lavoro / "cli")), str(c[0] if c else None))

    n = len(m.chiamate())
    r = _cli_esegui(m, ["riprendi", str(ids["t_viva"]), "--background"])
    time.sleep(0.8)
    prova("CLI riprendi --background, sessione viva: non parte niente, esce con 1 e dice cosa fare",
          len(m.chiamate()) == n and r.returncode == 1 and "aperta" in r.stdout
          and "--copia" in r.stdout, r.stdout[-300:])

    n = len(m.chiamate())
    r = _cli_esegui(m, ["riprendi", str(ids["t_persa"])])
    prova("CLI riprendi ID (senza background) scrive prima cosa farebbe: sessione NUOVA",
          "NUOVA" in r.stdout and len(m.chiamate()) == n, r.stdout[-300:])

    n = len(m.chiamate())
    r = _cli_esegui(m, ["manda", "prova manda cli", "--task", str(ids["t_cli"]), "--attendi"])
    c = m.chiamate()[n:]
    argv = (c[0] if c else {}).get("argv", [])
    prova("CLI manda --task riprende la sessione del task (--attendi, stessa cosa di riprendi)",
          _con(argv, "--resume") == _SID_CLI and "--fork-session" not in argv,
          str(argv) + r.stdout[-200:] + r.stderr[-200:])
    prova("...e lo scrive", "riprende la sessione originale" in r.stdout.lower(), r.stdout[-300:])

    n = len(m.chiamate())
    r = _cli_esegui(m, ["riprendi", str(ids["t_viva"]), "--background", "--copia"])
    c = m.dopo(n)
    argv = (c[0] if c else {}).get("argv", [])
    prova("CLI riprendi --background --copia su una viva: parte la copia (--fork-session)",
          _con(argv, "--resume") == _SID_VIVA and "--fork-session" in argv, str(argv) + r.stdout[-200:])


# --------------------------------------------------------------------------
# le proposte di Jarvis
# --------------------------------------------------------------------------

_DRIVER_JARVIS = r'''
import json, os, sys, time
sys.path.insert(0, %(radice)r)
from plancia import jarvis, store
conn = store.connect(); store.init_db(conn)
scelta = json.loads(%(scelta)r)
# 22-SERVER: una proposta non parte da sola. Si prepara la scheda (quella che "fallo"
# e "rilancia" preparano) e parte con la conferma, l'unica porta.
a = scelta["azione"]
if a["tipo"] == "rilancia":
    scheda = jarvis.proponi("rilancia", {"run": a["run"]}, conn, conn, "it")
else:
    scheda = jarvis.proponi("lancia", {
        "titolo": a["titolo"], "agente": a.get("agente", "claude"),
        "progetto": a.get("progetto"), "scrive": a.get("modo") == "esegui",
        "task_id": a.get("task_id")}, conn, conn, "it")
esito = jarvis.conferma(scheda["id"], "it", conn=conn)
registro = %(registro)r
atteso = %(atteso)d
partenza = %(partenza)d
fine = time.time() + 15
while time.time() < fine and atteso:
    righe = [r for r in open(registro).read().splitlines() if r.strip()] if os.path.exists(registro) else []
    if len([r for r in righe if '"agents"' not in r and json.loads(r).get("argv", [None])[:1] != ["agents"]]) >= partenza + atteso:
        break
    time.sleep(0.1)
print(json.dumps(esito))
'''


def _jarvis_proposta(m, scelta, atteso):
    partenza = len(m.chiamate())
    out = m.python(_DRIVER_JARVIS % {
        "radice": str(RADICE), "scelta": json.dumps(scelta), "registro": str(m.registro),
        "atteso": atteso, "partenza": partenza}, timeout=60)
    return json.loads(out.strip().splitlines()[-1]), m.chiamate()[partenza:]


def _jarvis(prova, m):
    ids = m.ids

    # "manda" con task_id: la stessa sessione del task
    esito, c = _jarvis_proposta(m, {"testo": "fallo", "azione": {
        "tipo": "manda", "titolo": "prova task jarvis", "task_id": ids["t_jarvis"],
        "agente": "claude", "modo": "proposta"}}, 1)
    argv = (c[0] if c else {}).get("argv", [])
    prova("proposta 'manda' con task chiuso: riprende la sessione del task, stesso id",
          _con(argv, "--resume") == _SID_JARVIS and "--fork-session" not in argv, str(argv) + str(esito))
    prova("...nella sua cartella", _percorsi_uguali((c[0] if c else {}).get("cwd"),
                                                  str(m.lavoro / "jarvis")), str(c[0] if c else None))
    prova("...e la voce lo dice", "sessione originale" in (esito.get("risposta") or ""), str(esito))

    # "manda" con task vivo: niente da lanciare, messaggio negli appunti
    m.clipboard.write_text("", "utf-8")
    esito, c = _jarvis_proposta(m, {"testo": "fallo", "azione": {
        "tipo": "manda", "titolo": "prova task jarvis vivo", "task_id": ids["t_jarvis_viva"],
        "agente": "claude", "modo": "proposta"}}, 0)
    prova("proposta 'manda' con task vivo: non lancia niente",
          not c, str(c))
    prova("...il messaggio da incollare va negli appunti e la voce lo dice",
          str(ids["t_jarvis_viva"]) in m.clipboard.read_text("utf-8")
          and "appunti" in (esito.get("risposta") or ""), str(esito))

    # "rilancia": nella conversazione del lancio
    esito, c = _jarvis_proposta(m, {"testo": "rilancia", "azione": {
        "tipo": "rilancia", "run": ids["r_con_sessione"]}}, 1)
    argv = (c[0] if c else {}).get("argv", [])
    prova("proposta 'rilancia': riprende la conversazione del lancio (stesso id, niente fork)",
          _con(argv, "--resume") == _SID_RUN and "--fork-session" not in argv, str(argv) + str(esito))

    # "manda" senza task su una persa: nuova
    esito, c = _jarvis_proposta(m, {"testo": "fallo", "azione": {
        "tipo": "manda", "titolo": "prova task perso jarvis", "task_id": ids["t_persa"],
        "agente": "claude", "modo": "proposta"}}, 1)
    prova("proposta 'manda' con task perso: parte nuova e la voce lo dice",
          bool(c) and "--resume" not in c[0].get("argv", []) and "nuova" in (esito.get("risposta") or ""),
          str(esito))
