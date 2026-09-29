"""Prove del terzo giro di U2-UNIVERSALE: la console nuova, le finestre nere, l'hook
e i minori del tester.

1. Windows senza `wt`: la console nuova (`CREATE_NEW_CONSOLE`) non riceve
   stdin/stdout/stderr rediretti, o in CPython il figlio avrebbe `NUL` al posto della
   console e `claude` non leggerebbe i tasti.
2. Sotto `pythonw` (l'avvio automatico) ogni processo che Plancia lancia e non
   mostra porta `CREATE_NO_WINDOW`: git e gh del sync, il `claude` del riepilogo,
   di Jarvis, dell'agente caldo, dei lanci in background, di Riprendi (`agents`),
   la riproduzione, la trascrizione. Su macOS e Linux gli argomenti sono quelli di
   prima. Una prova sul sorgente (ast) impedisce che ne nasca un altro senza.
3. Repo pubblico: `bin/plancia-hook` non contiene piu' nessun indirizzo e nessun
   percorso di una persona. I contenitori li calcola come
   `attribuzione.contenitori_avviso()` (una casa finta con una cartella finta di
   Google Drive), piu' la chiave facoltativa `contenitori` di config.json.
4. Percorsi POSIX: l'hook (`_escluso`, `ancoraggio`), `attribuzione.py` e `turni.py`
   ragionano anche con percorsi di Windows; su macOS niente cambia.
5. L'hook registrato con un percorso con spazi e' quotato (mac e linux); senza
   spazi resta identico.
6. I minori: `esporta --apri`, `ask/jarvis --speak` senza motore, `Ascolta` con la
   `nota_voce`, doctor che nomina il ripiego, un secondo `serve`, il motore vero e
   l'elenco delle voci, Ctrl+K fuori dal Mac.

Per lanciare da sola: `python3 tools/prove/piattaforma-console-hook.py`.
"""

import ast
import contextlib
import io
import json
import ntpath
import os
import posixpath
import re
import sqlite3
import subprocess
import sys
import tempfile
import types
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

NO_WINDOW = 0x08000000


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
    """Sostituisce attributi di un oggetto e li rimette."""

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


def _windows_finto(pf):
    """Su un host che non e' Windows `subprocess` rifiuta `creationflags`: qui si
    finge di esserlo, e `subprocess` e' sostituito da un registratore."""
    return _Finto(pf, _su_windows_vero=lambda piatt=None, nt=None: pf._p(piatt) == "windows")


# --------------------------------------------------------------------------
# 1. la console nuova non ha stdin/stdout/stderr rediretti
# --------------------------------------------------------------------------

def _prove_console_nuova(prova):
    from plancia import piattaforma as pf

    o = pf.opzioni_distacco("windows", "C:\\x", True, nt=True)
    prova("console nuova (Windows senza wt): creationflags CREATE_NEW_CONSOLE, cwd, e NIENTE stdin/stdout/stderr",
          o == {"cwd": "C:\\x", "creationflags": 0x10}, str(o))
    o2 = pf.opzioni_distacco("windows", None, True, nt=True)
    prova("console nuova senza cartella: solo creationflags",
          o2 == {"creationflags": 0x10}, str(o2))
    o3 = pf.opzioni_distacco("windows", None, True, nt=False)
    prova("console nuova su un host che non e' Windows (le prove): nemmeno li' i tre std, e nessun creationflags",
          o3 == {}, str(o3))
    o4 = pf.opzioni_distacco("windows", None, False, nt=True)
    prova("Windows con wt (staccato): i tre std chiusi su NUL come prima, DETACHED | NEW_GROUP",
          o4 == {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                 "stderr": subprocess.DEVNULL, "creationflags": 0x08 | 0x200}, str(o4))
    prova("Linux e macOS: i tre std chiusi e start_new_session, com'era",
          all(pf.opzioni_distacco(p, "/w") == {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                                               "stderr": subprocess.DEVNULL, "cwd": "/w",
                                               "start_new_session": True}
              for p in ("mac", "linux")))

    # fino al Popen: il costruttore riceve davvero quei soli argomenti
    chiamate = []

    class FintaPopen:
        def __init__(self, argv, **k):
            chiamate.append((list(argv), k))

    with _windows_finto(pf), _Finto(subprocess, Popen=FintaPopen):
        pf.avvia_distaccato(["claude", "--resume", "x"], piatt="windows", cwd="C:\\w", nuova_console=True)
        pf.avvia_distaccato(["wt.exe", "-d", "C:\\w", "claude"], piatt="windows")
    k1, k2 = chiamate[0][1], chiamate[1][1]
    prova("Popen della console nuova: nessuno tra stdin, stdout e stderr, CREATE_NEW_CONSOLE",
          not ({"stdin", "stdout", "stderr"} & set(k1)) and k1["creationflags"] == 0x10 and k1["cwd"] == "C:\\w", str(k1))
    prova("Popen di wt.exe: i tre std su DEVNULL come prima",
          k2["stdin"] == k2["stdout"] == k2["stderr"] == subprocess.DEVNULL, str(k2))


# --------------------------------------------------------------------------
# 2. nessuna finestra nera: ogni figlio porta CREATE_NO_WINDOW
# --------------------------------------------------------------------------

class _Fine:
    def __init__(self, out="", rc=0):
        self.stdout, self.stderr, self.returncode = out, "", rc


class _Flusso:
    def write(self, *_a):
        return 0

    def close(self):
        pass

    def __iter__(self):
        return iter(())


class _PopenRegistratore:
    registro = None

    def __init__(self, argv, **k):
        self.registro.append(("Popen", [str(a) for a in argv], k))
        self.stdin, self.stdout = _Flusso(), _Flusso()
        self.pid, self.returncode = 4321, 0

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


def _lanci_di_plancia(registro):
    """Fa partire, uno per uno, tutti i processi che Plancia lancia dal proprio
    codice, con `subprocess` sostituito da un registratore. Torna i nomi."""
    from plancia import agente, cantiere, ingest, jarvis, piattaforma as pf, recap, riprendi, store, voice

    def run_finto(argv, **k):
        registro.append(("run", [str(a) for a in argv], k))
        return _Fine("[]" if "agents" in argv else "")

    _PopenRegistratore.registro = registro
    nomi = []
    with _Finto(subprocess, run=run_finto, Popen=_PopenRegistratore), \
            _Finto(recap, claude_bin=lambda: "/x/claude"), \
            _Finto(voice, voicebox_vivo=lambda *a, **k: False):
        ingest.run(["git", "status"], timeout=7, cwd=str(RADICE))
        nomi.append("ingest.run (git e gh del sync)")
        recap.claude_text("una domanda", timeout=5)
        nomi.append("recap.claude_text (il riepilogo)")
        jarvis.chiedi_a_claude("una frase", "it")
        nomi.append("jarvis.chiedi_a_claude")
        with _ambiente(PLANCIA_AGENTS_JSON=None):
            with _Finto(riprendi, _registro_sessioni_claude=lambda: []):
                riprendi._claude_vivo("sid-x")
        nomi.append("riprendi._claude_vivo (claude agents)")
        ag = agente.Agente("it")
        ag.avvia()
        nomi.append("agente.Agente.avvia (claude stream-json)")
        conn = store.connect()
        store.init_db(conn)
        conn.close()
        cantiere._esegui(987001, "claude", False, "prompt", tempfile.gettempdir(),
                         str(Path(tempfile.gettempdir()) / "plancia-prova-console.log"),
                         "titolo", None, None)
        nomi.append("cantiere._esegui (lanci in background)")
        pf.esegui(["programma", "arg"], capture_output=True)
        nomi.append("piattaforma.esegui")
        with _Finto(pf, comando_riproduzione=lambda p, *a, **k: ["player", str(p)]):
            voice.ferma()
            voice.riproduci("/x/a.wav")
            voice.ferma()
        nomi.append("voice.riproduci")
        with _Finto(voice, AUDIO_DIR=Path(tempfile.gettempdir())):
            voice.trascrivi("/x/a.wav")
        nomi.append("voice.trascrivi (whisper)")
        voice.voicebox_avvia(attesa=0)
        nomi.append("voice.voicebox_avvia")
    return nomi


def _prove_nessuna_finestra(prova):
    from plancia import piattaforma as pf

    # Windows (finto): ogni lancio porta il flag
    reg_win = []
    with _ambiente(PLANCIA_PIATTAFORMA="windows"), _windows_finto(pf):
        nomi = _lanci_di_plancia(reg_win)
    per_nome = {}
    for tipo, argv, k in reg_win:
        per_nome.setdefault(argv[0], []).append((tipo, k))
    prova("[windows] i lanci registrati sono tanti quanti i punti del codice (e ognuno e' stato visto)",
          len(reg_win) >= len(nomi) - 1, "%d registrati, %d punti: %s" % (len(reg_win), len(nomi), [r[1][:2] for r in reg_win]))
    senza = [(t, a[:2]) for t, a, k in reg_win
             if k.get("creationflags") != NO_WINDOW]
    prova("[windows] OGNI lancio (git, gh, claude, agenti, lanci in background, riproduzione, whisper, "
          "esegui) porta CREATE_NO_WINDOW", not senza, str(senza))
    quali = sorted({a[0] for t, a, k in reg_win})
    prova("[windows] nei lanci ci sono davvero git, claude, il lanciatore in background, il lettore e whisper",
          all(x in quali for x in ("git", "/x/claude", "player", "whisper-cli")), str(quali))

    # macOS: gli argomenti sono identici a quelli di sempre (nessun creationflags, gli stessi nomi)
    reg_mac = []
    with _ambiente(PLANCIA_PIATTAFORMA="mac"):
        _lanci_di_plancia(reg_mac)
    prova("[mac] nessun lancio porta creationflags",
          not [a[:2] for t, a, k in reg_mac if "creationflags" in k], str(reg_mac))
    attesi_mac = {
        "git": {"capture_output", "text", "timeout", "cwd"},
        "/x/claude": None,   # piu' di un lancio: si guarda sotto
        "player": {"stdout", "stderr"},   # afplay: come nella base 4a89241, senza stdin
        "whisper-cli": {"capture_output", "text", "timeout"},
        "open": {"capture_output", "timeout"},
    }
    ok = True
    dettaglio = []
    for tipo, argv, k in reg_mac:
        atteso = attesi_mac.get(argv[0])
        if atteso is not None and set(k) != atteso:
            ok = False
            dettaglio.append((argv[:2], sorted(k)))
    prova("[mac] gli argomenti dei lanci sono esattamente quelli della base (nessuna chiave in piu' o in meno)",
          ok, str(dettaglio))
    claude_mac = [k for t, a, k in reg_mac if a[0] == "/x/claude"]
    chiavi = sorted(sorted(k) for k in claude_mac)
    prova("[mac] i lanci di claude (riepilogo, Jarvis, agents, agente caldo, background) hanno le chiavi di sempre",
          chiavi == sorted([
              sorted(["capture_output", "text", "timeout", "cwd", "env"]),                       # recap
              sorted(["input", "capture_output", "text", "timeout", "cwd", "env"]),              # jarvis
              sorted(["capture_output", "text", "stdin", "timeout"]),                             # agents
              sorted(["stdin", "stdout", "stderr", "text", "bufsize", "cwd", "env"]),            # agente
              sorted(["stdin", "stdout", "stderr", "text", "bufsize", "cwd", "env"]),            # cantiere
          ]), str(chiavi))

    # sul sorgente: nessun subprocess.run/Popen in plancia/ senza le opzioni di piattaforma
    fuori = []
    for f in sorted((RADICE / "plancia").glob("*.py")):
        if f.name == "piattaforma.py":
            continue
        albero = ast.parse(f.read_text("utf-8"))
        for nodo in ast.walk(albero):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr in ("run", "Popen", "check_output", "call", "check_call")
                    and isinstance(nodo.func.value, ast.Name) and nodo.func.value.id == "subprocess"):
                usa = any(kw.arg is None and isinstance(kw.value, ast.Call)
                          and isinstance(kw.value.func, ast.Attribute)
                          and kw.value.func.attr in ("opzioni_figlio", "opzioni_processo")
                          for kw in nodo.keywords)
                if not usa:
                    fuori.append("%s:%d" % (f.name, nodo.lineno))
    prova("nessun subprocess.run/Popen in plancia/ senza **piattaforma.opzioni_figlio() (o opzioni_processo)",
          not fuori, str(fuori))


def _prove_opzioni_figlio(prova):
    from plancia import piattaforma as pf

    prova("opzioni_figlio: {} su mac, linux e su un host non Windows; creationflags solo su Windows vero",
          pf.opzioni_figlio("mac") == {} and pf.opzioni_figlio("linux") == {}
          and pf.opzioni_figlio("windows", nt=False) == {}
          and pf.opzioni_figlio("windows", nt=True) == {"creationflags": NO_WINDOW})
    prova("opzioni_processo: stdin su NUL fuori da macOS (su macOS niente, come la base), piu' il flag "
          "solo su Windows vero",
          pf.opzioni_processo("mac") == {}
          and pf.opzioni_processo("windows", nt=True) == {"stdin": subprocess.DEVNULL, "creationflags": NO_WINDOW})


# --------------------------------------------------------------------------
# 3. privacy: nessun indirizzo e nessun percorso personale nel codice
# --------------------------------------------------------------------------

_INDIRIZZO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_AMMESSI = ("example.com", "example.org", "noreply@anthropic.com")


def _indirizzi_veri():
    trovati = []
    for cartella in ("bin", "plancia"):
        for f in sorted((RADICE / cartella).rglob("*")):
            if not f.is_file() or f.suffix in (".pyc", ".png", ".jpg", ".wav", ".icns"):
                continue
            try:
                testo = f.read_text("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for n, riga in enumerate(testo.splitlines(), 1):
                for m in _INDIRIZZO.finditer(riga):
                    if not any(a in m.group(0) for a in _AMMESSI):
                        trovati.append("%s/%s:%d %s" % (cartella, f.name, n, m.group(0)))
    return trovati


def _carica_hook(env_home=None, env_data=None, os_finto=None):
    """Il sorgente di `bin/plancia-hook` senza l'ultima riga che lo esegue e chiama
    `sys.exit`: torna il dizionario dei suoi nomi."""
    sorgente = (RADICE / "bin" / "plancia-hook").read_text("utf-8")
    corpo = sorgente.split("\ntry:\n    run()")[0]
    globali = {"__name__": "plancia_hook_prova"}
    with _ambiente(HOME=env_home, USERPROFILE=env_home, PLANCIA_HOME=env_data):
        exec(compile(corpo, "plancia-hook", "exec"), globali)
    if os_finto is not None:
        # il sorgente fa `import os`: si sostituisce dopo, cosi' le sue funzioni
        # ragionano con i percorsi di Windows
        globali["os"] = os_finto
        globali["_P"] = os_finto.path
    return globali


def _lista_hook(g, casa):
    """I contenitori dell'hook: la funzione di adesso, o la costante della base."""
    if "_contenitori" in g:
        return g["_contenitori"](str(casa))
    return [os.path.normpath(c) for c in g["CONTENITORI"]]


def _lista_attribuzione(casa, drive):
    from plancia import attribuzione
    if hasattr(attribuzione, "contenitori_avviso"):
        return attribuzione.contenitori_avviso(home=casa, drive=drive)
    return attribuzione.contenitori(home=casa, drive=drive)


def _prove_privacy_e_contenitori(prova):
    from plancia import attribuzione, config

    veri = _indirizzi_veri()
    prova("in bin/ e plancia/ nessun indirizzo con un dominio vero (esclusi example.com, example.org, "
          "noreply@anthropic.com)", not veri, str(veri))
    hook = (RADICE / "bin" / "plancia-hook").read_text("utf-8")
    prova("bin/plancia-hook non ha nessun percorso scritto a mano di una macchina "
          "(/Users/nome, /Volumes/disco, GoogleDrive-<indirizzo>)",
          not re.search(r"/Users/[A-Za-z]|/Volumes/[A-Za-z]|GoogleDrive-[A-Za-z0-9.]*@", hook), "")
    # nessun nome di disco o di volume di nessuna macchina, in nessun file del
    # repo (le prove comprese): i soli nomi ammessi sono segnaposto. Contano i
    # file che git traccia: gli appunti privati esclusi da .git/info/exclude
    # stanno nella cartella ma non vanno mai nel repo pubblico. Senza git (un
    # archivio scaricato) si guarda tutto l'albero.
    try:
        tracciati = subprocess.run(["git", "-C", str(RADICE), "ls-files", "-z"],
                                   capture_output=True, check=True).stdout.decode("utf-8")
        candidati = [RADICE / p for p in tracciati.split("\0") if p]
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        candidati = []
        for cartella, sotto, file in os.walk(str(RADICE)):
            sotto[:] = [d for d in sotto if d not in (".git", "__pycache__", "node_modules", "vendor")]
            candidati.extend(Path(cartella) / nome for nome in file)
    nomi_di_volume = set()
    for percorso in candidati:
        nome = percorso.name
        if nome.endswith((".py", ".md", ".js", ".html", ".css", ".yml", ".sh", ".swift", ".cmd")) \
                or nome.startswith("plancia"):
            try:
                testo = percorso.read_text("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            nomi_di_volume.update(re.findall(r"/Volumes/([A-Za-z0-9._-]+)", testo))
    prova("nessun nome di disco o di volume scritto nel repo (solo i segnaposto Disco e disco)",
          nomi_di_volume <= {"Disco", "disco"}, str(sorted(nomi_di_volume)))

    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-casa-"))
    drive = casa / "Library" / "CloudStorage" / "GoogleDrive-utente@example.com" / "Il mio Drive"
    drive.mkdir(parents=True)
    dati = Path(tempfile.mkdtemp(prefix="plancia-prova-dati-"))
    (dati / "config.json").write_text(json.dumps({"contenitori": [str(casa / "altro"), "~/extra", 7, "", None]}))
    g = _carica_hook(str(casa), str(dati))
    with _ambiente(HOME=casa, USERPROFILE=casa):
        da_hook = _lista_hook(g, casa)
        with _Finto(config, CONFIG_FILE=dati / "config.json"):
            da_attr = _lista_attribuzione(casa, drive)
    prova("hook e attribuzione danno la STESSA lista di contenitori su una casa finta con un Drive finto "
          "e la chiave contenitori di config.json",
          da_hook == da_attr and len(da_hook) == 8, "%s\n%s" % (da_hook, da_attr))
    prova("la lista ha la radice del Drive, ~/dev, ~/Siti, ~/dev/siti, Lavoro, Personale e le due extra "
          "(le voci non-stringa o vuote sono ignorate, ~ si espande)",
          da_hook == [str(drive), str(casa / "dev"), str(casa / "Siti"), str(casa / "dev" / "siti"),
                      str(drive / "Lavoro"), str(drive / "Personale"),
                      str(casa / "altro"), str(casa / "extra")], str(da_hook))

    # senza Drive e senza config: solo le cartelle sotto casa, ancora uguali
    casa2 = Path(tempfile.mkdtemp(prefix="plancia-prova-casa2-"))
    dati2 = Path(tempfile.mkdtemp(prefix="plancia-prova-dati2-"))
    g2 = _carica_hook(str(casa2), str(dati2))
    with _Finto(config, CONFIG_FILE=dati2 / "config.json"), _ambiente(HOME=casa2, USERPROFILE=casa2):
        prova("senza Drive ne' config: hook e attribuzione danno ancora la stessa lista (dev, Siti, dev/siti)",
              _lista_hook(g2, casa2) == _lista_attribuzione(casa2, None)
              == [str(casa2 / "dev"), str(casa2 / "Siti"), str(casa2 / "dev" / "siti")])
    # una chiave scritta male non rompe niente
    (dati2 / "config.json").write_text('{"contenitori": "una stringa"}')
    with _Finto(config, CONFIG_FILE=dati2 / "config.json"), _ambiente(HOME=casa2, USERPROFILE=casa2):
        prova("config.json con `contenitori` che non e' una lista: come non averla, in tutti e due",
              _lista_hook(g2, casa2) == _lista_attribuzione(casa2, None)
              == [str(casa2 / "dev"), str(casa2 / "Siti"), str(casa2 / "dev" / "siti")])
    (dati2 / "config.json").write_text("non json")
    with _Finto(config, CONFIG_FILE=dati2 / "config.json"), _ambiente(HOME=casa2, USERPROFILE=casa2):
        prova("config.json rotto: idem, nessuna eccezione",
              _lista_hook(g2, casa2) == _lista_attribuzione(casa2, None)
              == [str(casa2 / "dev"), str(casa2 / "Siti"), str(casa2 / "dev" / "siti")])

    prova("config: la chiave contenitori esiste, vuota, fra i default",
          config.DEFAULTS.get("contenitori") == [])


# --------------------------------------------------------------------------
# 4. percorsi: hook, attribuzione, turni
# --------------------------------------------------------------------------

class _OsWindows:
    """Un `os` con i percorsi di Windows (`ntpath`), il resto e' quello vero."""

    def __init__(self):
        self.path = ntpath

    def __getattr__(self, nome):
        return getattr(os, nome)


class _OsPosix:
    """Un `os` con i percorsi di POSIX (`posixpath`), il resto e' quello vero: cosi'
    una regola che ragiona su stringhe POSIX si prova uguale su ogni sistema."""

    def __init__(self):
        self.path = posixpath

    def __getattr__(self, nome):
        return getattr(os, nome)


def _crea_db(percorso, righe_repo, link=()):
    con = sqlite3.connect(str(percorso))
    con.executescript(
        "create table projects(id integer primary key, key text);"
        "create table repos(local_path text, project_id integer);"
        "create table project_links(project_id integer, kind text, value text);")
    con.execute("insert into projects values (1,'proj-uno'),(2,'proj-due')")
    for p, i in righe_repo:
        con.execute("insert into repos values (?,?)", (p, i))
    for p, i in link:
        con.execute("insert into project_links values (?,?,?)", (i, "path", p))
    con.commit()
    con.close()


def _prove_hook_percorsi(prova):
    casa = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-hcasa-")))
    dati = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-hdati-")))
    (casa / "dev" / "proj").mkdir(parents=True)
    (casa / "privato" / "x").mkdir(parents=True)
    _crea_db(dati / "plancia.db", [(str(casa / "dev" / "proj"), 1), (str(casa / "dev") + "/", 2)])
    g = _carica_hook(str(casa), str(dati))

    # POSIX: gli stessi risultati della base (misurati sulla base 6aa7ba8)
    cartelle = [str(casa / "privato")]
    # con cartelle vere di questo sistema: su Windows non sono percorsi POSIX (la stessa regola,
    # su stringhe POSIX, e' provata piu' sotto con posixpath)
    prova("[posix] _escluso: uguale a prima (uguale, sotto, fuori, slash finale, id esplicito, vuoto)",
          os.name == "nt" or ([g["_escluso"](c, "", cartelle, set()) for c in
           (str(casa / "privato"), str(casa / "privato" / "x"), str(casa / "privato") + "/",
            str(casa / "dev"), "", None)] == [True, True, True, False, False, False]
          and g["_escluso"]("/altrove", "sid", cartelle, {"sid"}) is True),
          "saltato: cartelle vere di Windows, la regola POSIX e' provata con posixpath" if os.name == "nt" else "")
    with _ambiente(HOME=casa, USERPROFILE=casa):
        ancore = {
            "progetto": g["ancoraggio"](str(casa / "dev" / "proj")),
            "sotto": g["ancoraggio"](str(casa / "dev" / "proj" / "sub") + "/"),
            "contenitore": g["ancoraggio"](str(casa / "dev")),
            "sconosciuta": g["ancoraggio"](str(casa / "altro")),
        }
    prova("[posix] ancoraggio: progetto e sottocartella ancorati (anche con lo slash finale), ~/dev e' un "
          "contenitore, una cartella ignota lo dice",
          "ancorata al progetto `proj-uno`" in ancore["progetto"]
          and "ancorata al progetto `proj-uno`" in ancore["sotto"]
          and "cartella contenitore" in ancore["contenitore"] and "proj-uno" in ancore["contenitore"]
          and "non risulta legata a nessun progetto" in ancore["sconosciuta"], str(ancore))

    # Windows (ntpath): barre, maiuscole, unita
    gw = _carica_hook(str(casa), str(dati), os_finto=_OsWindows())
    gw["DB"] = str(dati / "plancia.db")
    gw["CONFIG"] = str(dati / "config.json")
    prova("[windows] _escluso: una cartella esclusa esclude le sue sottocartelle, con / o \\ e maiuscole diverse",
          gw["_escluso"]("C:\\Users\\Ann\\Privato\\x", "", ["c:\\users\\ann\\privato"], set())
          and gw["_escluso"]("c:/users/ann/PRIVATO", "", ["c:\\users\\ann\\privato"], set())
          and not gw["_escluso"]("C:\\Users\\Ann\\Privato2", "", ["c:\\users\\ann\\privato"], set()))
    _crea_db(dati / "plancia-w.db", [("C:\\Users\\Ann\\dev\\Proj", 1), ("D:/lavoro/", 2)])
    gw["DB"] = str(dati / "plancia-w.db")
    a1 = gw["ancoraggio"]("C:\\Users\\Ann\\dev\\Proj\\sub")
    a2 = gw["ancoraggio"]("c:/users/ann/dev/proj")
    a3 = gw["ancoraggio"]("D:\\lavoro\\x\\y")
    a4 = gw["ancoraggio"]("E:\\altro")
    prova("[windows] ancoraggio: una sottocartella di un progetto registrato e' ancorata (senza l'invito a "
          "creare una scheda doppia), anche con barre e maiuscole diverse, su un'altra unita'",
          "ancorata al progetto `proj-uno`" in a1 and "ancorata al progetto `proj-uno`" in a2
          and "ancorata al progetto `proj-due`" in a3
          and "non risulta legata a nessun progetto" in a4, str((a1, a2, a3, a4)))
    # un contenitore, anche con barre e maiuscole diverse (sulla base i contenitori sono una
    # costante, in questa versione una funzione: si sostituisce quella che c'e')
    if "_contenitori" in gw:
        gw["_contenitori"] = lambda casa=None: ["C:\\Users\\Ann\\dev"]
    else:
        gw["CONTENITORI"] = ["C:\\Users\\Ann\\dev"]
    a5 = gw["ancoraggio"]("c:/users/ann/dev/")
    prova("[windows] un contenitore riconosciuto anche con barre e maiuscole diverse",
          "cartella contenitore" in a5, a5)


def _prove_hook_helper_windows(prova):
    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-hh-"))
    gw = _carica_hook(str(casa), str(casa), os_finto=_OsWindows())
    prova("[windows] _norma: una sola forma di separatore, maiuscole uguali, niente separatore finale, "
          "la radice dell'unita' resta",
          gw["_norma"]("C:/Users/Ann/Dev/") == "c:\\users\\ann\\dev"
          and gw["_norma"]("C:\\") == "c:\\" and gw["_senza_fine"]("C:\\") == "C:\\"
          and gw["_senza_fine"]("C:\\Users\\") == "C:\\Users")
    prova("[windows] _dentro: la sottocartella e' dentro, 'C:\\dev2' non e' dentro 'C:\\dev', la radice contiene tutto",
          gw["_dentro"](gw["_norma"]("C:/Dev/proj/sub"), gw["_norma"]("c:\\dev\\proj"))
          and not gw["_dentro"](gw["_norma"]("C:\\dev2"), gw["_norma"]("C:\\dev"))
          and gw["_dentro"]("c:\\x", gw["_norma"]("C:\\")))
    g = _carica_hook(str(casa), str(casa), os_finto=_OsPosix())
    prova("[posix] _norma e _senza_fine: solo lo slash finale, la radice resta '/', niente normpath",
          g["_norma"]("/a/b/") == "/a/b" and g["_norma"]("/") == "/" and g["_norma"]("/a//b") == "/a//b"
          and g["_dentro"]("/a/b/c", "/a/b") and not g["_dentro"]("/a/bc", "/a/b") and g["_dentro"]("/x", "/"))


def _prove_attribuzione_e_turni(prova):
    from plancia import attribuzione as a, turni

    # POSIX: identico alla base (uscite misurate su 6aa7ba8)
    comandi = [
        "cd \"/Users/ann/Il mio Drive/Lavoro\" && ls /Users/ann/dev/x/file.py:42 /Volumes/Disco/dev/y/*.py",
        "git -C /Users/ann/dev/proj status; cat '/Users/ann/dev/with space/a.txt'",
        "echo https://a.b/c s:/x C:/Users/zz /tmp/foo",
        "ls /Users/ann",
        "",
        "rm -rf /Users/ann/dev/q/",
    ]
    attesi = [["/Users/ann/Il mio Drive/Lavoro", "/Users/ann/dev/x/file.py", "/Volumes/Disco/dev/y"],
              ["/Users/ann/dev/with space/a.txt", "/Users/ann/dev/proj"], [], [], [], ["/Users/ann/dev/q"]]
    prova("[posix] percorsi_da_comando: le stesse uscite della base",
          [a.percorsi_da_comando(c) for c in comandi] == attesi, str([a.percorsi_da_comando(c) for c in comandi]))
    blocchi = [{"input": {"file_path": "/Users/ann/dev/x/f.py"}}, {"input": {"path": "relativo/x"}},
               {"input": {"pattern": "/Users/ann/dev/x/**/*.py"}}, {"input": {"glob": "/Users/ann/*"}},
               {"input": {"command": "ls /Users/ann/dev/z/ && cat /Users/ann/dev/z/a"}},
               {"input": {"file_path": "/Users/ann/dev/x/", "notebook_path": "/Users/ann/n.ipynb"}},
               {"input": "x"}]
    attesi_b = [["/Users/ann/dev/x/f.py"], [], ["/Users/ann/dev/x"], ["/Users/ann"],
                ["/Users/ann/dev/z", "/Users/ann/dev/z/a"], ["/Users/ann/dev/x", "/Users/ann/n.ipynb"], []]
    prova("[posix] percorsi_da_tool_use: le stesse uscite della base",
          [a.percorsi_da_tool_use(b) for b in blocchi] == attesi_b, str([a.percorsi_da_tool_use(b) for b in blocchi]))
    prova("[posix] base_di_glob, categoria e _pulisci: come prima",
          [a.base_di_glob(v) for v in ("/a/b/*.py", "/a/b/c.py", "/a/b/", "/a/b/{x,y}/z")] == ["/a/b"] * 4
          and [a.categoria(c, None) for c in ("/tmp/x", "/private/var/folders/a", "/Users/ann/dev/drift-abc/x",
                                              "/Users/ann/dev/p", "/TMP/x", "")]
          == ["temporanea", "temporanea", "temporanea", "progetto", "progetto", "progetto"]
          and [a._pulisci(v) for v in ("/a/b/,", "/a/b//", "/", "a")] == ["/a/b", "/a/b", "/", "a"])

    # Windows
    prova("[windows] un file_path con la lettera dell'unita' (barre rovesciate o dritte) e' accettato",
          a.percorsi_da_tool_use({"input": {"file_path": "C:\\Users\\ann\\dev\\x\\f.py"}}) == ["C:\\Users\\ann\\dev\\x\\f.py"]
          and a.percorsi_da_tool_use({"input": {"path": "D:/lavoro/x/f.py"}}) == ["D:/lavoro/x/f.py"]
          and a.percorsi_da_tool_use({"input": {"path": "\\\\server\\share\\x\\f.py"}}) == ["\\\\server\\share\\x\\f.py"])
    prova("[windows] un glob con backslash torna alla cartella sopra il primo carattere speciale",
          a.percorsi_da_tool_use({"input": {"pattern": "D:\\dev\\x\\**\\*.py"}}) == ["D:\\dev\\x"]
          and a.base_di_glob("C:\\a\\b\\c.py") == "C:\\a\\b")
    prova("[windows] percorsi_da_comando: percorsi con virgolette (e spazi) e nudi, dritti o rovesci; "
          "https:// non e' un disco; C:\\Users\\ann da solo non e' un progetto",
          a.percorsi_da_comando('cd "C:\\Users\\Ann Lee\\Il Progetto" && ls C:/Users/ann/dev/x/file.py https://a.b/c')
          == ["C:\\Users\\Ann Lee\\Il Progetto", "C:/Users/ann/dev/x/file.py"]
          and a.percorsi_da_comando("dir C:\\Users\\ann") == []
          and a.percorsi_da_comando("dir C:\\Users\\ann\\dev\\p\\") == ["C:\\Users\\ann\\dev\\p"])
    prova("[windows] le cartelle temporanee di Windows sono `temporanea`",
          a.categoria("C:\\Users\\ann\\AppData\\Local\\Temp\\x") == "temporanea"
          and a.categoria("c:/users/ann/appdata/local/temp") == "temporanea"
          and a.categoria("C:\\Users\\ann\\dev\\drift-abc\\x") == "temporanea"
          and a.categoria("C:\\Users\\ann\\dev\\proj") == "progetto")

    # turni.CASA: la home scritta come Claude Code (ricalcolata con la home di Windows)
    import importlib

    def casa_con(home):
        with _Finto(turni.Path, home=classmethod(lambda cls: home)):
            importlib.reload(turni)
            return turni.CASA
    try:
        casa_windows = casa_con("C:\\Users\\Ana Maria")
        casa_mac = casa_con("/Users/utente")
    finally:
        importlib.reload(turni)
    prova("[turni] CASA con la home di Windows e' la codifica di Claude Code: C:\\Users\\Ana Maria -> C--Users-Ana-Maria",
          casa_windows == "C--Users-Ana-Maria", casa_windows)
    prova("[turni] CASA su macOS: /Users/utente -> -Users-utente, come prima (replace slash)",
          casa_mac == "-Users-utente" == "/Users/utente".replace("/", "-"), casa_mac)
    prova("[turni] CASA di questa macchina = codifica della home (esclusi._codifica)",
          turni.CASA == turni.esclusi._codifica(str(Path.home())))
    with _Finto(turni, CASA="C--Users-x"):
        etichetta = turni._etichetta("C--Users-x-dev-progetto")
    prova("[turni] _etichetta su un nome di Claude Code di Windows: 'C--Users-x-dev-progetto' e' 'progetto'",
          etichetta == "progetto", etichetta)


# --------------------------------------------------------------------------
# 5. l'hook registrato con un percorso con spazi
# --------------------------------------------------------------------------

def _prove_hook_quotato(prova):
    from plancia import piattaforma as pf, setup_claude as sc
    import shlex

    senza = "/home/utente/plancia/bin/plancia-hook"
    con = "/home/utente/albero con spazi/plancia/bin/plancia-hook"
    accento = "/Users/José/plancia/bin/plancia-hook"
    prova("riga_script mac/linux senza spazi: il percorso nudo, IDENTICO a prima (anche con accenti, +, =, @)",
          all(pf.riga_script(p, piatt=x) == p for x in ("mac", "linux")
              for p in (senza, accento, "/a/b+c=d@e/bin/plancia-hook")))
    q = pf.riga_script(con, piatt="linux")
    prova("riga_script linux con spazi: quotato con shlex.quote, e sh -c lo rilegge come UN argomento",
          q == shlex.quote(con) and shlex.split(q) == [con], q)
    prova("riga_script mac con spazi, apice o parentesi: quotato",
          pf.riga_script(con, piatt="mac") == shlex.quote(con)
          and shlex.split(pf.riga_script("/a/b (1)/it's/hook", piatt="mac")) == ["/a/b (1)/it's/hook"])
    prova("riga_script windows: invariata, python tra virgolette",
          pf.riga_script("C:\\p q\\bin\\plancia-hook", "C:\\Py\\python.exe", "windows")
          == '"C:\\Py\\python.exe" -X utf8 "C:\\p q\\bin\\plancia-hook"')
    prova("_e_nostro riconosce anche il comando che finisce con un apice (percorso quotato)",
          sc._e_nostro(q, "plancia-hook") and sc._e_nostro(senza, "plancia-hook")
          and not sc._e_nostro("'/x/altro'", "plancia-hook"))

    # fino a settings.json: con spazi un comando quotato, senza spazi quello di sempre, e una seconda
    # install non lascia doppioni (ne' rimuove quello di un altro)
    for etichetta, script_dir, atteso_quotato in (("senza spazi", "albero", False), ("con spazi", "albero con spazi", True)):
        casa = Path(tempfile.mkdtemp(prefix="plancia-prova-cfg-"))
        cfg = casa / "claude"
        cfg.mkdir()
        (cfg / "settings.json").write_text(json.dumps({"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": "/altro/hook", "timeout": 9}]}]}}))
        radice = casa / script_dir
        (radice / "bin").mkdir(parents=True)
        with _ambiente(PLANCIA_PIATTAFORMA="linux"), \
                _Finto(sc, BIN=radice / "bin"), \
                _Finto(sc.config, CLAUDE_SETTINGS=cfg / "settings.json", CLAUDE_DIR=cfg), \
                _Finto(sc, HOOK_CMD=str(radice / "bin" / "plancia-hook"),
                       RICHIAMO_CMD=str(radice / "bin" / "plancia-richiamo"),
                       AGGANCI=[(sc.HOOK_EVENTS, str(radice / "bin" / "plancia-hook"), "plancia-hook", 5),
                                (sc.RICHIAMO_EVENTS, str(radice / "bin" / "plancia-richiamo"), "plancia-richiamo", 3)]):
            sc.install_hooks()
            sc.install_hooks()
            dati = json.loads((cfg / "settings.json").read_text())
            comandi = [h["command"] for e in dati["hooks"]["SessionStart"] for h in e["hooks"]]
            ancora = sc.hooks_installed()
            sc.remove_hooks()
            dopo = json.loads((cfg / "settings.json").read_text())
            restano = [h["command"] for e in dopo.get("hooks", {}).get("SessionStart", []) for h in e["hooks"]]
        nostro = str(radice / "bin" / "plancia-hook")
        atteso = shlex.quote(nostro) if atteso_quotato else nostro
        # su Windows il percorso ha delle barre rovesciate, che una shell POSIX interpreta: anche
        # "senza spazi" e' quotato (la piattaforma qui e' finta, Linux), e il "nudo di sempre" non
        # esiste: e' un controllo che si fa solo dove i percorsi sono POSIX
        nudo_impossibile = os.name == "nt" and not atteso_quotato
        prova("install_hooks (%s): il comando e' %s, una sola volta dopo due install, e quello di un altro resta"
              % (etichetta, "quotato" if atteso_quotato else "il percorso nudo di sempre"),
              nudo_impossibile or (atteso in comandi and comandi.count(atteso) == 1
                                   and "/altro/hook" in comandi and ancora),
              "saltato: un percorso di Windows ha delle barre rovesciate, la shell POSIX le quota"
              if nudo_impossibile else str(comandi))
        prova("remove_hooks (%s): toglie il nostro (anche quotato) e lascia quello di un altro" % etichetta,
              restano == ["/altro/hook"], str(restano))


# --------------------------------------------------------------------------
# 6. i minori del tester: un processo figlio con tutto finto
# --------------------------------------------------------------------------

def _figlio_minori(piatt: str) -> None:
    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-minori-casa-"))
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
    from http.server import ThreadingHTTPServer

    from plancia import api, cli, config, piattaforma as pf, recap, setup_claude as sc, store, voice, jarvis

    recap.claude_bin = lambda: ""
    recap.answer = lambda *a, **k: "Risposta di prova."
    jarvis.esegui = lambda frase, lang=None, conn=None, vista=None: {"tipo": "risposta", "risposta": "Jarvis di prova.",
                                                         "lingua": "it"}
    voice.voicebox_vivo = lambda *a, **k: False
    voice.pocket_vivo = lambda *a, **k: False
    conn = store.connect()
    store.init_db(conn)
    store.migrate(conn)
    conn.close()

    def cli_(argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = cli.main(argv)
            except SystemExit as exc:
                rc = exc.code
            except Exception as exc:  # un traceback e' il difetto che si cerca
                rc = "ECCEZIONE %s: %s" % (type(exc).__name__, exc)
        return {"rc": rc, "out": out.getvalue(), "err": err.getvalue()}

    visto = {}

    # esporta --apri: nessun traceback, con o senza il lanciatore
    aperti = []
    memoria = casa / "memoria.html"
    # senza un lanciatore (nessun xdg-open, e os.startfile che su un host non Windows non c'e')
    pf.esegui = lambda argv, **k: aperti.append(list(argv)) or types.SimpleNamespace(returncode=0, stdout="", stderr="")

    def _senza_startfile(percorso):
        # come su un host che non e' Windows: e su Windows vero non si apre davvero il file
        raise OSError("os.startfile non c'e' su questo sistema")

    pf._startfile = _senza_startfile
    visto["esporta_senza"] = cli_(["esporta", "--dove", str(memoria), "--apri"])
    visto["aperti_senza"] = list(aperti)
    del aperti[:]
    startfile = []
    pf._startfile = lambda p: startfile.append(str(p))
    pf.cerca = lambda p: "/x/" + p if p == "xdg-open" else None
    visto["esporta_con"] = cli_(["esporta", "--dove", str(memoria), "--apri"])
    visto["aperti"] = aperti
    visto["startfile"] = startfile

    # ask/jarvis --speak senza motore
    visto["ask"] = cli_(["ask", "come", "va", "--speak"])
    visto["jarvis"] = cli_(["jarvis", "come", "sto", "andando", "--speak"])
    # /api/voice/status
    visto["stato"] = voice.stato()
    print("RISULTATO:" + json.dumps(visto, default=str))


def _prove_minori_cli(prova):
    for piatt in ("linux", "windows"):
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--figlio-minori", piatt],
                             capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        riga = [r for r in res.stdout.splitlines() if r.startswith("RISULTATO:")]
        if not riga:
            prova("[%s] il figlio dei minori gira" % piatt, False, (res.stdout + res.stderr)[-1500:])
            continue
        v = json.loads(riga[-1][len("RISULTATO:"):])
        s = v["esporta_senza"]
        prova("[%s] esporta --apri senza un lanciatore: nessun traceback, il file c'e', lo dice su stderr, rc 0" % piatt,
              s["rc"] == 0 and "ECCEZIONE" not in str(s["rc"]) and "non sono riuscito ad aprirlo" in s["err"]
              and "memoria.html" in s["out"] and not v["aperti_senza"], str(s))
        c = v["esporta_con"]
        if piatt == "linux":
            prova("[linux] esporta --apri con xdg-open: lancia `xdg-open <file>`, mai `open`",
                  c["rc"] == 0 and any(a[:1] == ["xdg-open"] for a in v["aperti"])
                  and not any(a[:1] == ["open"] for a in v["aperti"]), str(v["aperti"]))
        else:
            prova("[windows] esporta --apri: os.startfile sul file, mai `open`",
                  c["rc"] == 0 and any(str(p).endswith("memoria.html") for p in v["startfile"])
                  and not any(a[:1] == ["open"] for a in v["aperti"]), str((c, v["startfile"], v["aperti"])))
        for nome in ("ask", "jarvis"):
            r = v[nome]
            prova("[%s senza motore] plancia %s --speak: la risposta esce e la voce e' 'non disponibile' col perche'"
                  % (piatt, nome),
                  r["rc"] == 0 and "di prova" in r["out"] and "voce non disponibile" in r["err"]
                  and "motore vocale" in r["err"] and "None" not in r["err"], str(r))
        st = v["stato"]
        prova("[%s senza motore] /api/voice/status: motore_sistema null e nota_voci che dice cosa manca" % piatt,
              st.get("motore_sistema") is None and "motore vocale" in (st.get("nota_voci") or "")
              and st["voci_sistema"] == 0, str(st))


def _prove_voce_motore_e_voci(prova):
    from plancia import piattaforma as pf, voice

    def cerca_con(*presenti):
        return lambda p: "/x/" + p if p in presenti else None

    # voci_sistema fuori da macOS: l'elenco dal motore, e stato() con motore e voci
    def esegui_finto(argv, **k):
        return types.SimpleNamespace(returncode=0, stdout="Microsoft Elsa Desktop|it-IT\r\nMicrosoft David Desktop|en-US\r\n",
                                     stderr="")
    with _ambiente(PLANCIA_PIATTAFORMA="windows"), _Finto(pf, cerca=cerca_con("powershell"), esegui=esegui_finto), \
            _Finto(voice, _voci=None, voicebox_vivo=lambda *a, **k: False):
        voci = voice.voci_sistema()
        st = voice.stato()
    prova("[windows] con il motore che risponde: l'elenco delle voci non e' vuoto, lingue it/en, il motore e' System.Speech",
          voci == [("Microsoft Elsa Desktop", "it_IT"), ("Microsoft David Desktop", "en_US")]
          and st["voci_sistema"] == 2 and st["lingue_disponibili"] == ["en", "it"]
          and st.get("motore_sistema") == "System.Speech" and st.get("nota_voci", 1) is None, str(st))

    def esegui_vuoto(argv, **k):
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    with _ambiente(PLANCIA_PIATTAFORMA="linux"), _Finto(pf, cerca=cerca_con("espeak-ng"), esegui=esegui_vuoto), \
            _Finto(voice, _voci=None, voicebox_vivo=lambda *a, **k: False):
        st2 = voice.stato()
    prova("[linux] motore che c'e' ma senza elenco: motore espeak-ng e una nota_voci che dice perche'",
          st2.get("motore_sistema") == "espeak-ng" and st2["voci_sistema"] == 0
          and "espeak-ng" in (st2.get("nota_voci") or "") and "predefinita" in (st2.get("nota_voci") or ""), str(st2))

    # sintesi(): il motore riportato e' quello vero
    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-audio-"))

    def sintesi_finta(testo, lang, out):
        Path(out).write_bytes(b"x" * 4096)
        return out
    for piatt, presenti, atteso in (("windows", ("powershell",), "System.Speech"),
                                    ("linux", ("espeak-ng",), "espeak-ng"), ("mac", (), "say")):
        with _ambiente(PLANCIA_PIATTAFORMA=piatt), _Finto(pf, cerca=cerca_con(*presenti)), \
                _Finto(voice, AUDIO_DIR=tmp, sintesi_say=sintesi_finta, voicebox_vivo=lambda *a, **k: False,
                       pocket_vivo=lambda *a, **k: False):
            info = voice.sintesi("una frase di prova per %s" % piatt, "it", "auto", cache=False)
        prova("[%s] sintesi(): il motore riportato e' %r, non sempre 'say'" % (piatt, atteso),
              info["motore"] == atteso, str(info))

    # mac: `voci_sistema` e `stato` restano quelli di prima (stesse chiavi, `say -v ?`)
    chiamate = []

    def esegui_say(argv, **k):
        chiamate.append((list(argv), sorted(k)))
        return types.SimpleNamespace(returncode=0, stdout="Alice              it_IT    # Ciao\n", stderr="")
    with _ambiente(PLANCIA_PIATTAFORMA="mac"), _Finto(pf, esegui=esegui_say), \
            _Finto(voice, _voci=None, voicebox_vivo=lambda *a, **k: False):
        voci_mac = voice.voci_sistema()
        st_mac = voice.stato()
    prova("[mac] voci_sistema: `say -v ?` con gli stessi argomenti di prima; stato() senza le chiavi nuove",
          chiamate == [(["say", "-v", "?"], ["capture_output", "text", "timeout"])]
          and voci_mac == [("Alice", "it_IT")]
          and "motore_sistema" not in st_mac and "nota_voci" not in st_mac and st_mac["voci_sistema"] == 1,
          str((chiamate, voci_mac, st_mac)))

    # le funzioni pure
    prova("motore_sistema: il nome vero (say, System.Speech, espeak-ng, espeak) o None",
          pf.motore_sistema("mac") == "say"
          and pf.motore_sistema("windows", cerca_con("powershell")) == "System.Speech"
          and pf.motore_sistema("linux", cerca_con("espeak-ng")) == "espeak-ng"
          and pf.motore_sistema("linux", cerca_con("espeak")) == "espeak"
          and pf.motore_sistema("linux", cerca_con()) is None
          and pf.motore_sistema("windows", cerca_con()) is None)
    win = pf.comando_elenco_voci("windows", cerca_con("powershell"))
    prova("comando_elenco_voci: `say -v ?` su mac (com'era), System.Speech su Windows, espeak --voices su Linux",
          pf.comando_elenco_voci("mac") == ["say", "-v", "?"]
          and win[0] == "powershell" and "GetInstalledVoices" in win[-1]
          and pf.comando_elenco_voci("linux", cerca_con("espeak-ng")) == ["espeak-ng", "--voices"]
          and pf.comando_elenco_voci("linux", cerca_con()) is None)
    prova("voci_da_elenco: Windows (nome|cultura) e espeak (tabella) danno (nome, it_IT)",
          pf.voci_da_elenco("Microsoft Elsa Desktop|it-IT\r\nMicrosoft Zira Desktop|en-US\r\n\r\n", "windows")
          == [("Microsoft Elsa Desktop", "it_IT"), ("Microsoft Zira Desktop", "en_US")]
          and pf.voci_da_elenco(
              "Pty Language       Age/Gender VoiceName          File                 Other Languages\n"
              " 5  it              --/M      Italian            roa/it\n"
              " 5  en-us           --/M      English_(America)  en-us   (en 3)\n", "linux")
          == [("Italian", "it_IT"), ("English_(America)", "en_US")])


def _figlio_doctor(scenario: str) -> None:
    """Un processo a parte, casa e PATH finti: `autostart_on` con un meccanismo
    che fallisce, poi la riga di `plancia doctor`. Stampa un JSON."""
    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-doc-casa-"))
    vuoto = casa / "path-vuoto"
    vuoto.mkdir()
    piatt = scenario.split("-")[0]
    # `pf.esegui` e' sostituito qui sotto da un finto: nessun comando parte. La
    # guardia dell'avvio automatico (HOME di prova) lascerebbe pero' i comandi
    # fuori dal finto, e la prova vuole vederli.
    os.environ["PLANCIA_AUTOSTART_FORZA"] = "1"
    for k in ("HOME", "USERPROFILE"):
        os.environ[k] = str(casa)
    os.environ["PLANCIA_HOME"] = str(casa / "plancia")
    os.environ["CLAUDE_CONFIG_DIR"] = str(casa / "claude")
    os.environ["CODEX_HOME"] = str(casa / "codex")
    os.environ["PATH"] = str(vuoto)
    os.environ["PLANCIA_PIATTAFORMA"] = piatt
    for k in ("LOCALAPPDATA", "XDG_CONFIG_HOME"):
        os.environ.pop(k, None)
    (casa / "AppData" / "Roaming").mkdir(parents=True)
    os.environ["APPDATA"] = str(casa / "AppData" / "Roaming")
    sys.path.insert(0, str(RADICE))

    from plancia import cli, piattaforma as pf, recap, setup_claude as sc, store

    recap.claude_bin = lambda: ""
    conn = store.connect()
    store.init_db(conn)
    conn.close()
    stato = {"task": False}

    def esegui_finto(argv, **k):
        rc = 0
        if argv[0] == "schtasks":
            if "/Create" in argv:
                rc = 1  # un utente non amministratore: ONLOGON negato
            elif "/Query" in argv:
                rc = 0 if stato["task"] else 1
        return types.SimpleNamespace(returncode=rc, stdout="", stderr="Access is denied" if rc else "")
    pf.esegui = esegui_finto
    if scenario == "linux-senza-systemctl":
        pf.cerca = lambda p: None
    elif scenario == "linux-systemd":
        pf.cerca = lambda p: "/x/systemctl" if p == "systemctl" else None
    else:
        pf.cerca = lambda p: None
    if scenario == "windows-task":
        # il task c'e' davvero: schtasks /Create riesce
        def esegui_ok(argv, **k):
            if argv[0] == "schtasks" and "/Create" in argv:
                stato["task"] = True
            return types.SimpleNamespace(returncode=0 if argv[0] != "schtasks" or "/Query" not in argv or stato["task"] else 1,
                                         stdout="", stderr="")
        pf.esegui = esegui_ok
    messaggio = sc.autostart_on() if piatt != "mac" else ""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        cli.main(["doctor"])
    riga = [r for r in out.getvalue().splitlines() if "avvio automatico" in r]
    print("RISULTATO:" + json.dumps({"messaggio": messaggio, "doctor": riga}))


def _prove_doctor_ripiego(prova):
    attesi = {
        "windows-negato": ("cartella Esecuzione automatica", "cartella Esecuzione automatica"),
        "windows-task": ("Task Scheduler", "Task Scheduler"),
        "linux-senza-systemctl": ("~/.config/autostart", "~/.config/autostart"),
        "linux-systemd": ("systemd", "systemd"),
        "mac": ("", "launchd"),
    }
    for scenario, (in_messaggio, in_doctor) in attesi.items():
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--figlio-doctor", scenario],
                             capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        riga = [r for r in res.stdout.splitlines() if r.startswith("RISULTATO:")]
        if not riga:
            prova("[%s] il figlio di doctor gira" % scenario, False, (res.stdout + res.stderr)[-1500:])
            continue
        v = json.loads(riga[-1][len("RISULTATO:"):])
        doctor = " ".join(v["doctor"])
        prova("[%s] doctor nomina il meccanismo davvero usato (%s)" % (scenario, in_doctor),
              ("(%s)" % in_doctor) in doctor and len(v["doctor"]) == 1, str(v))
        if in_messaggio:
            prova("[%s] il messaggio di install nomina lo stesso meccanismo" % scenario,
                  in_messaggio in v["messaggio"], str(v))


def _prove_serve_doppio(prova):
    import http.server
    import socket
    import threading

    from plancia import cli

    # un server di Plancia finto: l'intestazione Server lo dice
    class HandlerPlancia(http.server.BaseHTTPRequestHandler):
        server_version = "Plancia/1.0"

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    class HandlerAltro(HandlerPlancia):
        server_version = "Altro/2.0"

    def avvia(handler):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, srv.server_address[1]

    aperti = []

    partiti = []

    def serve_finto(**k):
        partiti.append(k)

    from plancia import api
    srv, porta = avvia(HandlerPlancia)
    try:
        with _Finto(api, serve=serve_finto), _Finto(cli.webbrowser, open=lambda u: aperti.append(u)):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = cli.main(["serve", "--port", str(porta), "--open", "--no-sync"])
    finally:
        srv.shutdown()
    prova("un secondo `serve` mentre gira Plancia: 'gia' in ascolto', rc 0, nessun traceback, e --open apre "
          "il browser su quello",
          rc == 0 and "gia' in ascolto" in out.getvalue() and aperti == ["http://127.0.0.1:%d" % porta]
          and not partiti, "%r %r %r %r" % (rc, out.getvalue(), aperti, partiti))
    # il server vero (api.Handler): si riconosce dall'intestazione Server, senza token
    from plancia import store
    conn = store.connect()
    store.init_db(conn)
    conn.close()
    srv_vero, porta_vera = avvia(api.Handler)
    try:
        riconosciuto = cli._chi_ascolta(porta_vera)
    finally:
        srv_vero.shutdown()
        srv_vero.server_close()
    prova("_chi_ascolta riconosce il server vero di Plancia (api.Handler) e una porta libera",
          riconosciuto == "plancia" and cli._chi_ascolta(porta_vera) is None, str(riconosciuto))
    srv, porta = avvia(HandlerAltro)
    try:
        with _Finto(api, serve=serve_finto):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc2 = cli.main(["serve", "--port", str(porta), "--no-sync"])
    finally:
        srv.shutdown()
    prova("porta occupata da un altro programma: lo dice e rc 1, senza traceback",
          rc2 == 1 and "occupata da un altro programma" in err.getvalue() and not partiti,
          "%r %r %r" % (rc2, err.getvalue(), partiti))

    # la porta si occupa fra il controllo e il bind: EADDRINUSE dell'api diventa il messaggio
    import errno

    def serve_occupato(**k):
        raise OSError(errno.EADDRINUSE, "Address already in use")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        libera = s.getsockname()[1]
    with _Finto(api, serve=serve_occupato):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc3 = cli.main(["serve", "--port", str(libera), "--no-sync"])
    prova("EADDRINUSE durante l'avvio: messaggio e rc 1, non un traceback",
          rc3 == 1 and "occupata" in err.getvalue(), "%r %r" % (rc3, err.getvalue()))
    # porta libera: api.serve parte come sempre, con gli argomenti di sempre
    visti = []
    with _Finto(api, serve=lambda **k: visti.append(k)):
        cli.main(["serve", "--port", str(libera), "--open", "--no-sync"])
    prova("porta libera: api.serve riceve port, open_browser e sync_first come prima",
          visti == [{"port": libera, "open_browser": True, "sync_first": False}], str(visti))


def _prove_app_js(prova):
    js = (RADICE / "web" / "app.js").read_text("utf-8")
    prova("app.js: il riepilogo tiene la nota_voce del server e 'Ascolta' la passa a suona()",
          "r.notaVoce = d.nota_voce || null" in js
          and "suona(state.recap && state.recap.audio, state.recap && state.recap.notaVoce)" in js)
    prova("app.js: si legge senza errori di sintassi (node --check, se c'e' node)",
          _node_check(RADICE / "web" / "app.js"))

    # il comportamento, eseguendo i due pezzi di app.js in node con un DOM finto
    m_suona = re.search(r"function suona\(url[^)]*\) \{.*?\n\}\n", js, re.S)
    m_hint = re.search(r"\(function suggerimentoScorciatoia\(\) \{.*?\n\}\)\(\);", js, re.S)
    nome_ascolta = ("app.js: 'Ascolta' senza audio e con una nota_voce mostra QUELLA (rossa, piu' a lungo); "
                    "senza nota il vecchio 'audio non pronto'")
    nome_hint = ("app.js: il suggerimento di ricerca e' Ctrl+K su Windows e Linux (anche da userAgentData), "
                 "Cmd+K su Mac e iPhone")
    if not shutil_which("node"):
        # gli stessi due controlli di chi ha node, dichiarati saltati: il conteggio
        # non cambia da una macchina all'altra
        for nome in (nome_ascolta, nome_hint):
            prova(nome, True, "saltato: node non e' installato su questa macchina")
        return
    copione = """
const vm = require('vm');
const fonti = JSON.parse(process.env.PLANCIA_FONTI);
function esegui(codice, extra) {
  const cx = Object.assign({ console }, extra);
  vm.createContext(cx);
  vm.runInContext(codice, cx);
  return cx;
}
const fuori = {};
// Ascolta senza audio: con e senza nota
{
  const toasts = [];
  const cx = esegui((fonti.suona || 'function suona() {}') + '\\nthis.suona = suona;',
    { $: () => ({}), toast: (m, bad, ms) => toasts.push([m, !!bad, ms || null]), T: (x) => x,
      aggiornaBottoneVoce() {} });
  cx.suona(null, "nessun motore vocale di sistema: installa espeak-ng");
  cx.suona(null);
  fuori.toasts = toasts;
}
// il suggerimento: Mac, Windows, Linux, iPhone
fuori.hint = {};
for (const [nome, nav] of Object.entries({
  mac: { platform: 'MacIntel', userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)' },
  win: { platform: 'Win32', userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' },
  linux: { platform: 'Linux x86_64', userAgent: 'Mozilla/5.0 (X11; Linux x86_64)' },
  chd: { userAgentData: { platform: 'Windows' }, platform: '', userAgent: '' },
  ios: { platform: 'iPhone', userAgent: 'iPhone' },
})) {
  const kbd = { textContent: '\\u2318K' };
  if (fonti.hint) esegui(fonti.hint, { navigator: nav, $: (sel) => (sel === '#btn-search kbd' ? kbd : null) });
  fuori.hint[nome] = kbd.textContent;
}
console.log(JSON.stringify(fuori));
"""
    fonti = {"suona": m_suona.group(0) if m_suona else None, "hint": m_hint.group(0) if m_hint else None}
    r = subprocess.run(["node", "-e", copione], capture_output=True, text=True, timeout=60,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, env=dict(os.environ, PLANCIA_FONTI=json.dumps(fonti)))
    try:
        v = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        prova("app.js in node: gira", False, (r.stdout + r.stderr)[-800:])
        return
    t = v["toasts"]
    prova(nome_ascolta,
          len(t) == 2 and "espeak-ng" in t[0][0] and t[0][1] is True and (t[0][2] or 0) > 2600
          and t[1][0] == "audio non pronto" and t[1][1] is True, str(t))
    h = v["hint"]
    prova(nome_hint,
          h == {"mac": "\u2318K", "win": "Ctrl+K", "linux": "Ctrl+K", "chd": "Ctrl+K", "ios": "\u2318K"}, str(h))


def shutil_which(nome):
    import shutil
    return shutil.which(nome)


def _node_check(percorso):
    try:
        r = subprocess.run(["node", "--check", str(percorso)], capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return True
    return r.returncode == 0


# --------------------------------------------------------------------------

def esegui(prova):
    def gruppo(f):
        try:
            f(prova)
        except Exception as exc:  # noqa: BLE001
            import traceback
            prova("%s: nessuna eccezione" % f.__name__, False,
                  "%s: %s %s" % (type(exc).__name__, exc, traceback.format_exc()[-800:]))

    gruppo(_prove_console_nuova)
    gruppo(_prove_nessuna_finestra)
    gruppo(_prove_opzioni_figlio)
    gruppo(_prove_privacy_e_contenitori)
    gruppo(_prove_hook_percorsi)
    gruppo(_prove_hook_helper_windows)
    gruppo(_prove_attribuzione_e_turni)
    gruppo(_prove_hook_quotato)
    gruppo(_prove_minori_cli)
    gruppo(_prove_voce_motore_e_voci)
    gruppo(_prove_doctor_ripiego)
    gruppo(_prove_serve_doppio)
    gruppo(_prove_app_js)


if __name__ == "__main__":
    if "--figlio-doctor" in sys.argv:
        _figlio_doctor(sys.argv[sys.argv.index("--figlio-doctor") + 1])
        sys.exit(0)
    if "--figlio-minori" in sys.argv:
        _figlio_minori(sys.argv[sys.argv.index("--figlio-minori") + 1])
        sys.exit(0)
    if "PLANCIA_HOME" not in os.environ:
        os.environ["PLANCIA_HOME"] = tempfile.mkdtemp(prefix="plancia-prova-console-")
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
