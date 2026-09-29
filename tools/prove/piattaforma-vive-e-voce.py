"""Prove del secondo giro di U2-UNIVERSALE: tre cose che Windows e Linux rompevano.

1. `os.kill(pid, 0)` su Windows non controlla, TERMINA il processo. Ora tutti i
   controlli "il processo e' vivo" passano da `piattaforma.pid_vivo`, che su Windows
   non chiama mai `os.kill` (ctypes, o `tasklist`) e su macOS e Linux e' ancora
   `os.kill(pid, 0)`. Le prove sostituiscono `os.kill` e l'esecutore: nessun
   processo vero viene toccato.
2. Senza un motore vocale (Linux senza espeak-ng, Windows senza PowerShell) la
   dashboard non deve rompersi: `/api/recap`, `/api/voice/ask`, `/api/voice/speak`
   e `/api/jarvis` rispondono 200 col testo, `voce: null` e una `nota_voce`. Lo
   stesso vale per `say`, `voice prova`, `recap --speak`, `doctor` e per le azioni
   MCP `speak` e `recap --speak`. Queste prove girano in un processo figlio con
   casa, archivio e PATH finti: nessun `claude` o `codex` vero, nessun Voicebox.
3. Riprendi su Windows senza Windows Terminal, `riprendi --apri` che non dice
   "lanciato" se non e' partito niente, `bin/plancia.cmd` che non cade nell'alias
   del Microsoft Store, il commento del workflow, `requires-python`.

Per lanciare da sole: `python3 tools/prove/piattaforma-vive-e-voce.py`.
"""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


@contextlib.contextmanager
def _ambiente(**valori):
    vecchi = {k: os.environ.get(k) for k in valori}
    for k, v in valori.items():
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


class _Finto:
    """Sostituisce un attributo di un modulo e lo rimette."""

    def __init__(self, oggetto, **sostituzioni):
        self.oggetto, self.sostituzioni, self.vecchi = oggetto, sostituzioni, {}

    def __enter__(self):
        for k, v in self.sostituzioni.items():
            self.vecchi[k] = getattr(self.oggetto, k)
            setattr(self.oggetto, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.vecchi.items():
            setattr(self.oggetto, k, v)


# --------------------------------------------------------------------------
# 1. il processo e' vivo? (mai os.kill su Windows)
# --------------------------------------------------------------------------

class _Risultato:
    def __init__(self, out="", rc=0):
        self.stdout, self.returncode = out, rc


def _csv_tasklist(pid):
    return '"python.exe","%d","Console","1","12.345 KB"\r\n' % pid


def _prove_pid_vivo(prova):
    from plancia import cantiere, piattaforma as pf, riprendi

    chiamate_kill = []

    def kill_finto(pid, sig):
        chiamate_kill.append((pid, sig))
        if pid == 111:
            return None
        if pid == 222:
            raise ProcessLookupError()
        if pid == 333:
            raise PermissionError()
        raise OSError()

    comandi = []

    def esegui_finto(uscita, eccezione=None):
        def f(argv, **kw):
            comandi.append((list(argv), kw))
            if eccezione:
                raise eccezione
            return _Risultato(uscita)
        return f

    # macOS e Linux: os.kill(pid, 0), come sempre
    for piatt in ("mac", "linux"):
        del chiamate_kill[:]
        with _Finto(os, kill=kill_finto):
            vivo = pf.pid_vivo(111, piatt)
            morto = pf.pid_vivo(222, piatt)
            altrui = pf.pid_vivo(333, piatt)
            altrui_no = pf.pid_vivo(333, piatt, non_nostro=False)
            altro = pf.pid_vivo(444, piatt)
        prova("[%s] pid_vivo usa os.kill(pid, 0)" % piatt, chiamate_kill[0] == (111, 0),
              str(chiamate_kill))
        prova("[%s] pid_vivo: vivo True, morto False, non nostro True (o False a richiesta), errore False" % piatt,
              (vivo, morto, altrui, altrui_no, altro) == (True, False, True, False, False),
              str((vivo, morto, altrui, altrui_no, altro)))
    with _Finto(os, kill=kill_finto):
        prova("pid_vivo: pid non valido (0, -1, None, 'x') e' False senza toccare niente",
              [pf.pid_vivo(p, "linux") for p in (0, -1, None, "x")] == [False] * 4)

    # Windows: mai os.kill. Prima tasklist (un host non Windows), poi ctypes.
    del chiamate_kill[:]
    del comandi[:]
    with _Finto(os, kill=kill_finto), _Finto(pf, esegui=esegui_finto(_csv_tasklist(4242))):
        vivo = pf.pid_vivo(4242, "windows")
        altro_pid = pf.pid_vivo(4243, "windows")
    prova("[windows] pid_vivo non chiama mai os.kill", chiamate_kill == [], str(chiamate_kill))
    prova("[windows] pid_vivo passa da tasklist con il filtro sul pid",
          comandi and comandi[0][0][:3] == ["tasklist", "/FI", "PID eq 4242"], str(comandi[:1]))
    prova("[windows] tasklist con il pid in elenco: vivo; con un altro pid: no",
          (vivo, altro_pid) == (True, False), str((vivo, altro_pid)))
    with _Finto(os, kill=kill_finto), _Finto(pf, esegui=esegui_finto(
            "INFORMAZIONI: nessuna attivita' in esecuzione corrisponde ai criteri.\r\n")):
        nessuno = pf.pid_vivo(4242, "windows")
    with _Finto(os, kill=kill_finto), _Finto(pf, esegui=esegui_finto("", OSError("no tasklist"))):
        rotto = pf.pid_vivo(4242, "windows")
    prova("[windows] tasklist senza risultati, o che non parte: non vivo, nessuna eccezione",
          (nessuno, rotto) == (False, False))
    del comandi[:]
    with _Finto(os, kill=kill_finto), _Finto(pf, esegui=esegui_finto("")):
        [pf.pid_vivo(p, "windows") for p in (0, -5, None, "abc")]
    prova("[windows] un pid non valido non lancia nemmeno tasklist", comandi == [], str(comandi))

    # Windows su un host Windows: ctypes (kernel32 finto)
    class _K32:
        def __init__(self, handle=1, errore=0, codice=259):
            self.handle, self.errore, self.codice = handle, errore, codice
            self.aperti, self.chiusi = [], []

        def OpenProcess(self, accesso, ereditabile, pid):
            self.aperti.append((accesso, ereditabile, pid))
            return self.handle

        def GetExitCodeProcess(self, handle, ref):
            ref._obj.value = self.codice
            return 1

        def CloseHandle(self, handle):
            self.chiusi.append(handle)
            return 1

    def con_k32(k32):
        return _Finto(pf, _kernel32=lambda: (k32, lambda: k32.errore))

    del chiamate_kill[:]
    with _Finto(os, kill=kill_finto):
        k = _K32(codice=259)
        with con_k32(k):
            v_vivo = pf.pid_vivo(4242, "windows", nt=True)
        k2 = _K32(codice=0)
        with con_k32(k2):
            v_uscito = pf.pid_vivo(4242, "windows", nt=True)
        k3 = _K32(handle=0, errore=5)
        with con_k32(k3):
            v_altrui = pf.pid_vivo(4242, "windows", nt=True)
            v_altrui_no = pf.pid_vivo(4242, "windows", non_nostro=False, nt=True)
        k4 = _K32(handle=0, errore=87)
        with con_k32(k4):
            v_manca = pf.pid_vivo(4242, "windows", nt=True)
    prova("[windows, ctypes] STILL_ACTIVE e' vivo, un codice di uscita no",
          (v_vivo, v_uscito) == (True, False), str((v_vivo, v_uscito)))
    prova("[windows, ctypes] accesso negato: c'e' ma non e' nostro; parametro non valido: non c'e'",
          (v_altrui, v_altrui_no, v_manca) == (True, False, False),
          str((v_altrui, v_altrui_no, v_manca)))
    prova("[windows, ctypes] apre in sola interrogazione e chiude il handle, mai os.kill",
          k.aperti == [(0x1000, 0, 4242)] and k.chiusi == [1] and chiamate_kill == [],
          str((k.aperti, k.chiusi, chiamate_kill)))
    del comandi[:]

    def kernel_che_manca():
        raise OSError("niente kernel32")
    with _Finto(os, kill=kill_finto), _Finto(pf, esegui=esegui_finto(_csv_tasklist(4242)),
                                             _kernel32=kernel_che_manca):
        ripiego = pf.pid_vivo(4242, "windows", nt=True)
    prova("[windows] se ctypes non funziona si ripiega su tasklist", ripiego is True and comandi,
          str((ripiego, comandi)))


def _prove_punti_del_codice(prova):
    """I punti che usavano os.kill(pid, 0): riprendi, cantiere, e nessun altro."""
    from plancia import cantiere, piattaforma as pf, riprendi

    chiamate_kill = []

    def kill_finto(pid, sig):
        chiamate_kill.append((pid, sig))
        if pid == 111:
            return None
        if pid == 222:
            raise ProcessLookupError()
        if pid == 333:
            raise PermissionError()
        raise OSError()

    class _R:
        def __init__(self, out):
            self.stdout, self.returncode = out, 0

    def esegui_finto(uscita):
        return lambda argv, **kw: _R(uscita)

    # i due punti del codice che lo usavano (riprendi e cantiere)
    del chiamate_kill[:]
    with _ambiente(PLANCIA_PIATTAFORMA="windows"), _Finto(os, kill=kill_finto), \
            _Finto(pf, esegui=esegui_finto(_csv_tasklist(4242))):
        r_vivo, r_altro = riprendi._pid_vivo(4242), riprendi._pid_vivo(4243)
        c_vivo, c_altro, c_vuoto = cantiere._vivo(4242), cantiere._vivo(4243), cantiere._vivo(None)
    prova("[windows] riprendi._pid_vivo e cantiere._vivo non chiamano os.kill",
          chiamate_kill == [], str(chiamate_kill))
    prova("[windows] riprendi._pid_vivo e cantiere._vivo dicono la verita' (via tasklist)",
          (r_vivo, r_altro, c_vivo, c_altro, c_vuoto) == (True, False, True, False, False),
          str((r_vivo, r_altro, c_vivo, c_altro, c_vuoto)))
    del chiamate_kill[:]
    with _ambiente(PLANCIA_PIATTAFORMA="mac"), _Finto(os, kill=kill_finto):
        m_vivo, m_morto, m_altrui = riprendi._pid_vivo(111), riprendi._pid_vivo(222), riprendi._pid_vivo(333)
        c_vivo, c_morto, c_altrui = cantiere._vivo(111), cantiere._vivo(222), cantiere._vivo(333)
    prova("[mac] riprendi._pid_vivo e cantiere._vivo restano os.kill(pid, 0), come prima "
          "(un processo di un altro utente: per riprendi c'e', per cantiere no)",
          chiamate_kill[0] == (111, 0)
          and (m_vivo, m_morto, m_altrui) == (True, False, True)
          and (c_vivo, c_morto, c_altrui) == (True, False, False),
          str((chiamate_kill, m_vivo, m_morto, m_altrui, c_vivo, c_morto, c_altrui)))

    # nessun altro os.kill(pid, 0) nel codice
    residui = []
    for f in sorted((RADICE / "plancia").glob("*.py")) + [RADICE / "bin" / n for n in
                                                          ("plancia", "plancia-hook", "plancia-mcp", "plancia-richiamo")]:
        if f.name == "piattaforma.py" or not f.exists():
            continue
        for n, riga in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"os\.kill\([^)]*,\s*0\s*\)", riga):
                residui.append("%s:%d" % (f.name, n))
    prova("nessun os.kill(pid, 0) fuori da piattaforma.py (su Windows uccide)", not residui, str(residui))


# --------------------------------------------------------------------------
# 3. Windows senza wt, voce mancante, riprendi --apri, plancia.cmd, workflow
# --------------------------------------------------------------------------

def _prove_piccole(prova):
    from plancia import piattaforma as pf

    def cerca_con(*presenti, **percorsi):
        def f(p):
            if p in percorsi:
                return percorsi[p]
            return "/x/" + p if p in presenti else None
        return f

    # voce_mancante
    nulla = cerca_con()
    m_linux = pf.voce_mancante("linux", nulla)
    prova("voce_mancante linux senza niente: dice di installare espeak-ng", bool(m_linux) and "espeak-ng" in m_linux,
          str(m_linux))
    prova("voce_mancante linux con espeak-ng e un lettore audio: c'e'",
          pf.voce_mancante("linux", cerca_con("espeak-ng", "paplay")) is None)
    m_lettore = pf.voce_mancante("linux", cerca_con("espeak-ng"))
    prova("voce_mancante linux con il motore ma senza lettore: lo dice", bool(m_lettore) and "lettore" in m_lettore,
          str(m_lettore))
    prova("voce_mancante linux con solo spd-say: c'e' (dice la frase da solo)",
          pf.voce_mancante("linux", cerca_con("spd-say")) is None)
    m_win = pf.voce_mancante("windows", nulla)
    prova("voce_mancante windows senza PowerShell: lo dice", bool(m_win) and "PowerShell" in m_win, str(m_win))
    prova("voce_mancante windows con PowerShell: c'e'", pf.voce_mancante("windows", cerca_con("powershell")) is None)
    prova("voce_mancante mac: c'e' sempre", pf.voce_mancante("mac", nulla) is None)

    # Windows senza wt: un claude.cmd con un prompt multi-riga non parte da una console
    multiriga = ["claude", "--resume", "sid", "Riprendi da qui.\nSecondo rigo & altro %PATH%"]
    breve = ["claude", "--resume", "sid-chiusa"]
    p_cmd = pf.piano_terminale("C:\\lavoro", multiriga, "windows",
                               cerca_con(claude="C:\\npm\\claude.cmd"))
    prova("[windows senza wt] claude.cmd con un prompt multi-riga: non si lancia e dice che serve Windows Terminal",
          p_cmd is not None and p_cmd["argv"] is None and "Windows Terminal" in p_cmd.get("errore", ""), str(p_cmd))
    p_breve = pf.piano_terminale("C:\\lavoro", breve, "windows", cerca_con(claude="C:\\npm\\claude.cmd"))
    prova("[windows senza wt] claude.cmd con un comando breve (resume di una chiusa): parte",
          p_breve and p_breve["argv"] == ["C:\\npm\\claude.cmd", "--resume", "sid-chiusa"], str(p_breve))
    p_exe = pf.piano_terminale("C:\\lavoro", multiriga, "windows", cerca_con(claude="C:\\bin\\claude.exe"))
    prova("[windows senza wt] claude.exe con un prompt multi-riga: parte, e' un argomento solo",
          p_exe and p_exe["argv"] and p_exe["argv"][-1] == multiriga[-1], str(p_exe))
    p_wt = pf.piano_terminale("C:\\lavoro", multiriga, "windows",
                              cerca_con("wt", claude="C:\\npm\\claude.cmd"))
    prova("[windows con wt] lo stesso prompt passa da wt.exe, un argomento per pezzo",
          p_wt and p_wt["argv"] and p_wt["argv"][0] == "wt.exe", str(p_wt))
    prova("comando_terminale torna None (non un errore) quando il piano rifiuta",
          pf.comando_terminale("C:\\lavoro", multiriga, "windows", cerca_con(claude="C:\\npm\\claude.cmd")) is None)

    # bin/plancia.cmd
    grezzo = (RADICE / "bin" / "plancia.cmd").read_bytes()
    testo = grezzo.decode("utf-8")
    prova("bin/plancia.cmd: tutte le righe finiscono con CRLF", grezzo.count(b"\n") == grezzo.count(b"\r\n"))
    prova("bin/plancia.cmd: prova `py -3` prima di `python`, e verifica che python sia vero con `-c \"import sys\"`",
          "py -3" in testo and testo.count('-c "import sys"') >= 2
          and testo.index("py -3") < testo.index("where python"), testo)
    prova("bin/plancia.cmd: lancia lo script con -X utf8 e mai `python` nudo senza il controllo",
          "-X utf8" in testo and "%PLANCIA_PY% -X utf8" in testo)
    prova("bin/plancia.cmd: senza un Python che funzioni si ferma con un messaggio, non apre lo Store",
          "senzapython" in testo and "winget" in testo)

    # pyproject e workflow
    pyproject = (RADICE / "pyproject.toml").read_text(encoding="utf-8")
    prova("pyproject.toml: requires-python >=3.9 (come README e CI)", 'requires-python = ">=3.9"' in pyproject)
    wf = (RADICE / ".github" / "workflows" / "prova.yml").read_text(encoding="utf-8")
    prova("il commento del workflow non dice che la prova di piattaforma 'non ammette rossi' senza dire che su Windows e' girata davvero",
          "Non ammette rossi su nessun sistema" not in wf and "mai girata su un Windows vero" not in wf
          and "girata al primo giro completo della CI" in wf)


def _prove_riprendi_apri_non_lanciato(prova):
    from plancia import actions, cli, piattaforma as pf, recap, riprendi, store

    conn = store.connect()
    store.init_db(conn)
    task = actions.task_add(conn, "prova non lanciato u2", session_id="sid-u2-nolancio",
                            cwd=tempfile.gettempdir(), agent="claude", host="altro-host-u2")
    tid = task["id"]
    conn.close()
    with _ambiente(PLANCIA_PIATTAFORMA="linux", PLANCIA_TERMINALE=None), \
            _Finto(pf, cerca=lambda p: None), _Finto(recap, claude_bin=lambda: "/x/claude"):
        conn = store.connect()
        esito = riprendi.apri(actions.task_get(conn, tid), conn)
        conn.close()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["riprendi", str(tid), "--apri"])
    prova("riprendi.apri senza nessun terminale: errore e lanciato False",
          esito.get("lanciato") is False and "terminale" in (esito.get("errore") or ""), str(esito))
    testo = out.getvalue()
    prova("plancia riprendi --apri senza terminale non scrive 'lanciato:'",
          "lanciato:" not in testo.replace("non lanciato:", ""), testo)
    prova("plancia riprendi --apri senza terminale dice 'non lanciato' e il perche', e torna un codice di errore",
          "non lanciato" in testo and "terminale" in testo and rc == 1, "%r rc=%r" % (testo, rc))

    # Windows senza wt con un claude.cmd e il prompt multi-riga di una task persa: idem
    def cerca_cmd(p):
        return "C:\\npm\\claude.cmd" if p == "claude" else None
    conn = store.connect()
    persa = actions.task_add(conn, "prova persa u2\nsu due righe", session_id="",
                             cwd=tempfile.gettempdir(), agent="claude", host="altro-host-u2")
    conn.close()
    with _ambiente(PLANCIA_PIATTAFORMA="windows", PLANCIA_TERMINALE=None), _Finto(pf, cerca=cerca_cmd), \
            _Finto(recap, claude_bin=lambda: "C:\\npm\\claude.cmd"):
        conn = store.connect()
        e2 = riprendi.apri(actions.task_get(conn, persa["id"]), conn)
        conn.close()
    prova("Riprendi su Windows senza wt, task persa con claude.cmd: non parte niente e dice che serve Windows Terminal",
          e2.get("lanciato") is False and "Windows Terminal" in (e2.get("errore") or ""), str(e2))


# --------------------------------------------------------------------------
# 2. senza un motore vocale (processo figlio con tutto finto)
# --------------------------------------------------------------------------

def _figlio_voce(piatt: str) -> None:
    """Gira in un processo a parte: casa, archivio, PATH finti e `claude` sostituito.
    Stampa un JSON con quello che ha visto."""
    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-voce-casa-"))
    vuoto = casa / "path-vuoto"
    vuoto.mkdir()
    for k in ("HOME", "USERPROFILE"):
        os.environ[k] = str(casa)
    os.environ["PLANCIA_HOME"] = str(casa / "plancia")
    os.environ["CLAUDE_CONFIG_DIR"] = str(casa / "claude")
    os.environ["CODEX_HOME"] = str(casa / "codex")
    os.environ["PATH"] = str(vuoto)
    os.environ["PLANCIA_PIATTAFORMA"] = piatt
    for k in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
        os.environ.pop(k, None)
    sys.path.insert(0, str(RADICE))

    import threading
    import urllib.error
    import urllib.request

    from plancia import agente, api, cli, config, mcp, recap, setup_claude, store, voice

    # mai un claude vero, mai un Voicebox vero
    recap.claude_bin = lambda: ""
    recap.claude_text = lambda *a, **k: "Questo e' il testo del riepilogo di prova."
    agente.chiedi = lambda *a, **k: "Risposta di Jarvis di prova."
    voice.voicebox_vivo = lambda *a, **k: False
    voice.pocket_vivo = lambda *a, **k: False

    conn = store.connect()
    store.init_db(conn)
    store.migrate(conn)
    conn.close()

    httpd = api._Server(("127.0.0.1", 0), api.Handler)
    porta = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def http(percorso, corpo=None, metodo="POST"):
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (porta, percorso),
            data=json.dumps(corpo).encode("utf-8") if corpo is not None else None, method=metodo,
            headers={"Content-Type": "application/json", "X-Plancia-Token": config.get_token()})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return [r.status, json.loads(r.read())]
        except urllib.error.HTTPError as e:
            try:
                return [e.code, json.loads(e.read())]
            except Exception:
                return [e.code, None]

    visto = {"http": {
        "recap": http("/api/recap", {"lang": "it", "voce": True}),
        "ask": http("/api/voice/ask", {"domanda": "come va", "lang": "it", "voce": True}),
        "speak": http("/api/voice/speak", {"testo": "ciao a tutti", "lang": "it"}),
        "speak_riproduci": http("/api/voice/speak", {"testo": "ciao a tutti", "lang": "it",
                                                     "riproduci": True}),
        "jarvis": http("/api/jarvis", {"testo": "come sta andando", "lang": "it", "voce": True}),
        "recap_senza_voce": http("/api/recap", {"lang": "it", "voce": False}),
    }}
    httpd.shutdown()

    def cli_(argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return {"rc": rc, "out": out.getvalue(), "err": err.getvalue()}

    visto["cli"] = {"say": cli_(["say", "ciao"]), "prova": cli_(["voice", "prova"]),
                    "recap": cli_(["recap", "--speak"])}

    doc = io.StringIO()
    with contextlib.redirect_stdout(doc), contextlib.redirect_stderr(io.StringIO()):
        try:
            cli.main(["doctor"])
        except SystemExit:
            pass
    visto["doctor_voce"] = [r for r in doc.getvalue().splitlines()
                            if re.match(r"^(ok|no)\s+voce:", r)]

    visto["mcp"] = {
        "speak": json.loads(mcp.call_tool("plancia_speak", {"text": "ciao a tutti"})),
        "recap": json.loads(mcp.call_tool("plancia_recap", {"speak": True})),
    }
    print("RISULTATO:" + json.dumps(visto))


def _prove_voce_senza_motore(prova):
    for piatt in ("linux", "windows"):
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--figlio-voce", piatt],
                             capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        riga = [r for r in res.stdout.splitlines() if r.startswith("RISULTATO:")]
        if not riga:
            prova("[%s senza motore vocale] il figlio gira" % piatt, False,
                  (res.stdout + res.stderr)[-1500:])
            continue
        v = json.loads(riga[-1][len("RISULTATO:"):])
        h = v["http"]

        def corpo(nome):
            return h[nome][1] or {}

        for nome in ("recap", "ask", "speak", "jarvis"):
            prova("[%s senza motore vocale] /api %s: 200, non 500" % (piatt, nome),
                  h[nome][0] == 200, str(h[nome]))
        prova("[%s senza motore vocale] /api/recap: il testo c'e', voce null, nota_voce dice che manca il motore, "
              "nessun file audio" % piatt,
              bool(corpo("recap").get("testo")) and corpo("recap").get("voce", 1) is None
              and "motore vocale" in (corpo("recap").get("nota_voce") or "")
              and not corpo("recap").get("url") and not corpo("recap").get("file"), str(h["recap"]))
        prova("[%s senza motore vocale] /api/voice/ask: la risposta c'e', voce null, nota_voce" % piatt,
              bool(corpo("ask").get("risposta")) and corpo("ask").get("voce", 1) is None
              and "motore vocale" in (corpo("ask").get("nota_voce") or "")
              and not corpo("ask").get("url"), str(h["ask"]))
        prova("[%s senza motore vocale] /api/voice/speak: 200 con voce null e nota_voce (e senza url)" % piatt,
              corpo("speak").get("voce", 1) is None and "motore vocale" in (corpo("speak").get("nota_voce") or "")
              and not corpo("speak").get("url"), str(h["speak"]))
        prova("[%s senza motore vocale] /api/voice/speak con riproduci: 200, non 500" % piatt,
              h["speak_riproduci"][0] == 200, str(h["speak_riproduci"]))
        prova("[%s senza motore vocale] /api/jarvis: la risposta c'e', voce null, nota_voce, motore null" % piatt,
              bool(corpo("jarvis").get("risposta")) and corpo("jarvis").get("voce", 1) is None
              and "motore vocale" in (corpo("jarvis").get("nota_voce") or "")
              and corpo("jarvis").get("motore", 1) is None, str(h["jarvis"]))
        prova("[%s senza motore vocale] /api/recap con voce false: nessun campo di voce, solo il testo" % piatt,
              h["recap_senza_voce"][0] == 200 and "nota_voce" not in corpo("recap_senza_voce"),
              str(h["recap_senza_voce"]))
        # la dashboard (app.js, non toccato): recap -> `d.motore || null` e `d.url || null`,
        # chiedi -> `if (res.url) suona(res.url)`; senza url ne' motore non si rompe niente
        c = v["cli"]
        prova("[%s senza motore vocale] plancia say: dice che non c'e' un motore e cosa installare, "
              "non '[nessuno] None'" % piatt,
              c["say"]["rc"] == 1 and "nessun motore vocale" in c["say"]["err"]
              and "None" not in c["say"]["out"] + c["say"]["err"] and "[nessuno]" not in c["say"]["out"],
              str(c["say"]))
        prova("[%s senza motore vocale] plancia voice prova: dice che la prova non e' riuscita, non 'ok'" % piatt,
              c["prova"]["rc"] == 1 and "nessun motore vocale" in c["prova"]["err"]
              and "ok" not in c["prova"]["out"], str(c["prova"]))
        prova("[%s senza motore vocale] plancia recap --speak: il testo esce, e la voce e' 'non disponibile' col perche'"
              % piatt,
              "riepilogo di prova" in c["recap"]["out"] and "voce non disponibile" in c["recap"]["err"]
              and "nessun motore vocale" in c["recap"]["err"] and "None" not in c["recap"]["err"],
              str(c["recap"]))
        prova("[%s senza motore vocale] plancia doctor: la voce e' 'no', col perche', non 'ok'" % piatt,
              len(v["doctor_voce"]) >= 1 and all(r.startswith("no") for r in v["doctor_voce"][:1])
              and "motore vocale" in v["doctor_voce"][0], str(v["doctor_voce"]))
        m = v["mcp"]
        prova("[%s senza motore vocale] MCP speak: letto false con il motivo" % piatt,
              m["speak"].get("letto") is False and "motore vocale" in (m["speak"].get("motivo") or ""),
              str(m["speak"]))
        prova("[%s senza motore vocale] MCP recap con speak: il testo c'e', voce null e nota_voce" % piatt,
              bool(m["recap"].get("testo")) and m["recap"].get("voce", 1) is None
              and "motore vocale" in (m["recap"].get("nota_voce") or ""), str(m["recap"]))


def _prove_voce_su_mac_identica(prova):
    """Sul Mac niente cambia: con un motore (finto) i campi sono quelli di prima e
    le stringhe della CLI sono le stesse."""
    from plancia import cli, piattaforma as pf, voice

    con_voce = {"file": "/x/a.wav", "motore": "say", "lingua": "it"}
    with _ambiente(PLANCIA_PIATTAFORMA="mac"), _Finto(voice, parla=lambda *a, **k: con_voce,
                                                     voce_per=lambda lang: "Alice"):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            r1 = cli.main(["say", "ciao"])
            r2 = cli.main(["voice", "prova"])
    prova("[mac] plancia say con la voce: '[say] /x/a.wav', codice 0",
          out.getvalue().startswith("[say] /x/a.wav\n") and not r1, out.getvalue())
    prova("[mac] plancia voice prova con la voce: '[say · Alice] ok', codice 0",
          "[say · Alice] ok\n" in out.getvalue() and not r2 and err.getvalue() == "", out.getvalue() + err.getvalue())
    prova("[mac] voce_mancante e' None e doctor non la segnala", pf.voce_mancante("mac") is None)


# --------------------------------------------------------------------------

def esegui(prova):
    def gruppo(f):
        try:
            f(prova)
        except Exception as exc:  # noqa: BLE001
            import traceback
            prova("%s: nessuna eccezione" % f.__name__, False,
                  "%s: %s %s" % (type(exc).__name__, exc, traceback.format_exc()[-600:]))

    gruppo(_prove_punti_del_codice)
    gruppo(_prove_pid_vivo)
    gruppo(_prove_piccole)
    gruppo(_prove_riprendi_apri_non_lanciato)
    gruppo(_prove_voce_senza_motore)
    gruppo(_prove_voce_su_mac_identica)


if __name__ == "__main__":
    if "--figlio-voce" in sys.argv:
        _figlio_voce(sys.argv[sys.argv.index("--figlio-voce") + 1])
        sys.exit(0)
    if "PLANCIA_HOME" not in os.environ:
        os.environ["PLANCIA_HOME"] = tempfile.mkdtemp(prefix="plancia-prova-vive-")
    _passate, _fallite = [0], []

    def _prova(nome, cond, dettaglio=""):
        if cond:
            _passate[0] += 1
            print("  ok   %s" % nome)
        else:
            _fallite.append(nome)
            print("  NO   %s %s" % (nome, dettaglio))

    esegui(_prova)
    print("\n%d passate, %d fallite" % (_passate[0], len(_fallite)))
    sys.exit(1 if _fallite else 0)
