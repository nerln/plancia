"""Prove per plancia/piattaforma.py: Plancia si installa e gira anche su Windows e
Linux, e su macOS non cambia di un byte.

Non c'e' Windows ne' Linux sotto queste prove: si controllano i comandi COSTRUITI
per ognuna delle tre piattaforme (`PLANCIA_PIATTAFORMA` dice quale fingere), mai
eseguiti. Nessuna prova lancia `launchctl`, `schtasks`, `systemctl`,
`osascript`, `claude` o `codex` veri: le prove "di installazione" girano in un
processo figlio (`python tools/prove/piattaforma.py --figlio`) con una casa
finta, dove `subprocess.run`, `subprocess.Popen` e `shutil.which` sono sostituiti
da registratori PRIMA di importare `plancia`. Il figlio non dipende da
`plancia.piattaforma`: gira uguale sulla versione precedente, ed e' cosi' che
queste prove diventano rosse senza la correzione (vedi `_figlio`).

Quello che su macOS deve restare IDENTICO a oggi (argv, plist, settings.json,
~/.claude.json, config.toml di Codex, notifica, voce, appunti, terminale) e'
scritto qui come valori letterali, misurati sulla versione precedente.

Per lanciare da sole: `python3 tools/prove/piattaforma.py`.
"""

import ast
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

PIATTAFORME = ("mac", "windows", "linux")

# Un titolo scritto apposta: le virgolette, la & e le %VAR% che cmd.exe interpreta,
# il punto e virgola che wt.exe legge come separatore di comandi.
TITOLO_OSTILE = 'Fix "R&D" page %PATH% ; echo x'


def _n(testo):
    """Barre dritte: su un host Windows str(Path) le ha rovesciate, e le prove
    dei piani per mac e linux confrontano con percorsi POSIX."""
    return str(testo).replace("\\", "/")


def _nl(argvs):
    """Una lista di argv (o un argv) con le barre dritte."""
    return [_nl(a) if isinstance(a, list) else _n(a) for a in argvs]


def toml_normale(testo):
    """Il testo di un config.toml con le barre rovesciate dei percorsi tornate
    singole: `toml_str` le raddoppia (`\\U` non e' un escape valido), e su un host
    Windows lo fa anche per i percorsi di macOS e Linux, che li' hanno le barre
    rovesciate. La prova le confronta con percorsi scritti a barre dritte."""
    return testo.replace("\\\\", "\\")


def pulisci(v, sostituzioni):
    """Niente di host-dipendente nell'uscita del figlio: percorsi finti e barre
    uguali. Le forme con le barre raddoppiate si sostituiscono per prime."""
    if isinstance(v, str):
        for cosa, con in sostituzioni:
            v = v.replace(cosa.replace("\\", "\\\\"), con)
            v = v.replace(cosa, con)
        return v.replace("\\", "/")
    if isinstance(v, list):
        return [pulisci(x, sostituzioni) for x in v]
    if isinstance(v, dict):
        return {pulisci(k, sostituzioni): pulisci(x, sostituzioni) for k, x in v.items()}
    return v


def cartella_avvio_finta(casa):
    """La cartella Esecuzione automatica di Windows sotto `casa` (APPDATA e' quella
    che il padre ha messo nell'ambiente del figlio)."""
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


# ==========================================================================
# il figlio: gira in una casa finta, con tutto quello che lancia sostituito
# ==========================================================================

def _figlio() -> None:
    piatt = os.environ["PLANCIA_PIATTAFORMA"]
    variante = os.environ["PLANCIA_PROVA_VARIANTE"]
    casa = Path(os.environ["HOME"])
    registro = []
    stato = {"task": False}

    # gli strumenti che "ci sono" sulla macchina finta, per variante
    tutti = ["claude", "wt", "x-terminal-emulator", "wl-copy", "espeak-ng", "paplay",
             "notify-send", "systemctl", "powershell", "spd-say"]
    presenti = {"base": tutti, "avvio-negato": tutti, "senza-strumenti": [],
                "solo-spd-say": ["spd-say"], "esecutore-rotto": tutti,
                "voce-rotta": tutti, "voce-lenta": tutti}[variante]

    class Fine:
        def __init__(self, argv, rc=0):
            self.args, self.returncode, self.stdout, self.stderr = argv, rc, "", ""

    def come_e(k, nome):
        """Un kwarg come si scrive in un json: `stdin=DEVNULL` diventa "devnull",
        i byte degli appunti (UTF-16 con BOM) tornano testo con un'etichetta."""
        v = k.get(nome)
        if v == subprocess.DEVNULL and nome == "stdin":
            return "devnull"
        if isinstance(v, bytes):
            return "UTF16LE-BOM:" + v[2:].decode("utf-16-le") if v[:2] == b"\xff\xfe" else repr(v)
        return v

    def finta_run(argv, *a, **k):
        argv = [str(x) for x in argv] if isinstance(argv, (list, tuple)) else argv
        # la sintesi di una frase (non la riproduzione, non la notifica)
        voce = bool(argv) and (
            (argv[0] in ("espeak-ng", "espeak") and "-w" in argv)
            or (argv[0] in ("powershell", "pwsh") and "SpeechSynthesizer" in argv[-1]))
        registro.append({"run": argv, "input": come_e(k, "input")})
        if k.get("stdin") is not None:
            registro[-1]["stdin"] = come_e(k, "stdin")
        if variante == "esecutore-rotto":
            raise FileNotFoundError(2, "programma di prova che non c'e'")
        if voce and variante == "voce-lenta":
            raise subprocess.TimeoutExpired(argv, k.get("timeout") or 1)
        rc = 1 if (voce and variante == "voce-rotta") else 0
        if argv and argv[0] == "schtasks":
            if "/Create" in argv:
                rc = 1 if variante == "avvio-negato" else 0
                stato["task"] = rc == 0
            elif "/Delete" in argv:
                stato["task"] = False
            elif "/Query" in argv:
                rc = 0 if stato["task"] else 1
        if argv and argv[0] == "systemctl" and "enable" in argv and variante == "avvio-negato":
            rc = 1
        if rc and k.get("check"):
            raise subprocess.CalledProcessError(rc, argv)
        return Fine(argv, rc)

    class FintaPopen:
        def __init__(self, argv, *a, **k):
            registro.append({"popen": [str(x) for x in argv]})
            for nome in ("stdin", "cwd", "creationflags", "start_new_session"):
                if nome in k:
                    registro[-1][nome] = come_e(k, nome)
            self.pid = 1

        def wait(self):
            return 0

        def poll(self):
            return 0

        def terminate(self):
            pass

    subprocess.run = finta_run
    subprocess.Popen = FintaPopen
    import shutil
    shutil.which = lambda n, *a, **k: ("/fake/bin/" + n) if n in presenti else None
    # su Windows os.getuid non c'e' e `_uid()` tornerebbe None: la prova dei
    # comandi di launchd vuole sempre lo stesso utente, ovunque giri
    os.getuid = lambda: 501
    sys.path.insert(0, str(RADICE))
    (casa / ".claude").mkdir(parents=True, exist_ok=True)
    (casa / ".codex").mkdir(parents=True, exist_ok=True)
    (casa / ".codex" / "config.toml").write_text('model = "x"\n')
    (casa / ".claude.json").write_text("{}")

    from plancia import setup_claude as s, codex, voice, jarvis, cli, riprendi, store
    try:
        from plancia import piattaforma
        # `pythonw.exe` esiste solo su un Windows vero: la prova non deve
        # dipendere da dove gira (la scelta si prova a parte, con `esiste` finto)
        piattaforma.python_senza_finestra = lambda python, esiste=None: python
    except ImportError:
        pass

    def snapshot():
        fuori = {}
        for p in sorted(casa.rglob("*")):
            rel = p.relative_to(casa)
            if p.is_symlink():
                fuori[rel.as_posix()] = "-> " + os.readlink(str(p))
            elif p.is_file() and ".plancia" not in rel.parts:
                testo = p.read_bytes().decode("utf-8", errors="replace")
                if p.suffix.lower() != ".cmd":
                    # su un host Windows write_text scrive "\r\n": un plist o
                    # un'unita' systemd non ne hanno bisogno, un .cmd si'
                    testo = testo.replace("\r\n", "\n")
                if p.suffix == ".toml":
                    testo = toml_normale(testo)
                if p.suffix == ".json":
                    # un json si consegna come oggetto: normalizzare le barre nel
                    # testo lo romperebbe (le virgolette si scrivono \")
                    try:
                        testo = json.loads(testo)
                    except ValueError:
                        pass
                fuori[re.sub(r"backup-\d{8}-\d{6}", "backup-TS", rel.as_posix())] = testo
        return fuori

    out = {}

    def passo(nome, f):
        n0 = len(registro)
        try:
            r = f()
        except Exception as e:  # noqa: BLE001
            r = "ECCEZIONE %s: %s" % (type(e).__name__, e)
        out[nome] = {"ritorno": r, "comandi": registro[n0:]}

    passo("install_command", s.install_command)
    passo("install_mcp", s.install_mcp)
    passo("codex_registra", codex.registra_mcp)
    passo("install_hooks", s.install_hooks)
    passo("install_hooks_bis", s.install_hooks)
    passo("agganciati", lambda: [s.hooks_installed(), s.richiamo_installed(), s.mcp_installed()])
    residuo = {"windows": lambda: cartella_avvio_finta(casa) / "plancia.cmd",
               "linux": lambda: casa / ".config" / "autostart" / "plancia.desktop"}.get(piatt)
    if residuo:
        # quello che un giro precedente puo' aver lasciato (il ripiego): con il
        # meccanismo principale attivo, l'avvio automatico non deve partire due volte
        residuo = residuo()
        residuo.parent.mkdir(parents=True, exist_ok=True)
        residuo.write_text("residuo")
    passo("autostart_on", s.autostart_on)
    passo("recap_on", lambda: s.recap_daily_on("08:45", voce=True))
    passo("installati", lambda: [s.autostart_installed(), s.recap_daily_installed()])
    out["FILE_INSTALLATI"] = snapshot()

    os.environ["PLANCIA_AGENTS_JSON"] = str(casa / "vuoto.json")
    (casa / "vuoto.json").write_text("[]")
    (casa / "progetto con spazi").mkdir()

    def apri():
        conn = store.connect()
        store.init_db(conn)
        task = {"session_id": None, "cwd": str(casa / "progetto con spazi"), "agent": "claude",
                "project_id": None, "title": "t", "id": 1, "host": None}
        e = riprendi.apri(task, conn)
        if isinstance(e, dict) and e.get("cwd") and e.get("argv"):
            # la riga e il comando osascript esattamente come li costruiva riprendi.py
            # prima di questo lotto: il riferimento per "su mac non cambia niente"
            riga_base = "cd %s && %s" % (shlex.quote(e["cwd"]), shlex.join(e["argv"]))
            quotata = '"%s"' % riga_base.replace("\\", "\\\\").replace('"', '\\"')
            e["riga_base"] = riga_base
            e["osascript_base"] = ["osascript", "-e",
                                   "tell application \"Terminal\" to do script %s" % quotata]
        return e

    passo("apri", apri)

    def apri_ostile():
        conn = store.connect()
        store.init_db(conn)
        task = {"session_id": None, "cwd": str(casa / "progetto con spazi"), "agent": "claude",
                "project_id": None, "title": TITOLO_OSTILE, "id": 1, "host": None}
        return riprendi.apri(task, conn)

    passo("apri_ostile", apri_ostile)
    os.environ["PLANCIA_TERMINALE"] = "/fake/lanciatore"
    passo("apri_con_lanciatore", apri)
    del os.environ["PLANCIA_TERMINALE"]
    passo("appunti", lambda: jarvis._copia_appunti("riprendi il task 3"))
    os.environ["PLANCIA_CLIPBOARD"] = "/fake/appunti --flag"
    passo("appunti_sostituiti", lambda: jarvis._copia_appunti("ciao"))
    del os.environ["PLANCIA_CLIPBOARD"]
    passo("notifica", lambda: cli.cmd_notifica("Plancia", 'Ciao "mondo" ' + "x" * 300))
    passo("voce_sintesi", lambda: str(voice.sintesi_say("Ciao mondo", "it", casa / "o.wav")))
    passo("voce_riproduci", lambda: voice.riproduci(casa / "o.wav", attendi=True))
    passo("voce_parla", lambda: voice.parla("Ciao mondo", "it", "say", attendi=True))
    passo("voce_parla_senza_attendere", lambda: voice.parla("Ciao mondo", "it", "say", attendi=False))

    def voci():
        voice._voci = None
        return voice.voci_sistema()

    passo("voci_sistema", voci)
    passo("doctor", lambda: s.doctor())

    passo("autostart_off", s.autostart_off)
    passo("recap_off", s.recap_daily_off)
    passo("installati_dopo", lambda: [s.autostart_installed(), s.recap_daily_installed()])
    passo("remove_hooks", s.remove_hooks)
    passo("remove_mcp", s.remove_mcp)
    passo("codex_rimuovi", codex.rimuovi_mcp)
    passo("agganciati_dopo", lambda: [s.hooks_installed(), s.richiamo_installed(), s.mcp_installed()])
    passo("uninstall_all", s.uninstall_all)
    out["FILE_DOPO"] = snapshot()

    # niente di host-dipendente nell'uscita: percorsi finti e barre uguali
    sostituzioni = [(str(casa), "<CASA>"), (str(RADICE), "<RADICE>"),
                    (str(Path(sys.executable)), "<PY>")]
    sys.stdout.write("\n@@FIGLIO@@" + json.dumps(pulisci(out, sostituzioni), ensure_ascii=False))


# ==========================================================================
# il padre
# ==========================================================================

_cache = {}


def _figlio_lancia(piatt: str, variante: str = "base") -> dict:
    chiave = (piatt, variante)
    if chiave in _cache:
        return _cache[chiave]
    casa = Path(tempfile.mkdtemp(prefix="plancia-piatt-"))
    amb = {k: v for k, v in os.environ.items()
           if k not in ("PLANCIA_TERMINALE", "PLANCIA_CLIPBOARD", "PLANCIA_AGENTS_JSON",
                        "XDG_CONFIG_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR")}
    amb.update(HOME=str(casa), USERPROFILE=str(casa),
               APPDATA=str(casa / "AppData" / "Roaming"),
               LOCALAPPDATA=str(casa / "AppData" / "Local"),
               CLAUDE_CONFIG_DIR=str(casa / ".claude"), CODEX_HOME=str(casa / ".codex"),
               PLANCIA_HOME=str(casa / ".plancia"), PLANCIA_PIATTAFORMA=piatt,
               PLANCIA_PROVA_VARIANTE=variante)
    try:
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--figlio"],
                             capture_output=True, text=True, env=amb, timeout=180,
                             stdin=subprocess.DEVNULL)
        parti = res.stdout.split("@@FIGLIO@@")
        if len(parti) == 2:
            dati = json.loads(parti[1])
        else:
            dati = {"ERRORE": (res.stderr or res.stdout)[-600:]}
    except Exception as exc:  # noqa: BLE001
        dati = {"ERRORE": str(exc)}
    finally:
        import shutil
        shutil.rmtree(casa, ignore_errors=True)
    _cache[chiave] = dati
    return dati


def _r(dati, passo, campo="ritorno"):
    """Un campo di un passo del figlio, o un segnaposto leggibile se manca."""
    if "ERRORE" in dati:
        return "figlio caduto: " + dati["ERRORE"]
    return dati.get(passo, {}).get(campo)


def _comandi(dati, passo):
    c = _r(dati, passo, "comandi")
    return c if isinstance(c, list) else []


def _run(dati, passo):
    """Gli argv lanciati (run) da un passo, in ordine."""
    return [c["run"] for c in _comandi(dati, passo) if "run" in c]


def _popen(dati, passo):
    return [c["popen"] for c in _comandi(dati, passo) if "popen" in c]


def _file(dati, quale):
    f = dati.get(quale)
    return f if isinstance(f, dict) else {}


def _settings(dati, quale="FILE_INSTALLATI"):
    s = _file(dati, quale).get(".claude/settings.json")
    return s if isinstance(s, dict) else {}


def _comandi_hook(dati):
    """{evento: [comando, ...]} dai settings.json scritti dal figlio."""
    fuori = {}
    for evento, entries in (_settings(dati).get("hooks") or {}).items():
        fuori[evento] = [h.get("command") for e in entries for h in e.get("hooks", [])]
    return fuori


# --------------------------------------------------------------------------
# i valori di macOS, misurati sulla versione precedente
# --------------------------------------------------------------------------

# Il plist del server e del riepilogo, come li scriveva setup_claude.py prima di
# questo lotto (con i segnaposto del figlio al posto dei percorsi di questa macchina).
PLIST_SERVER_MAC = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.plancia.server</string>
  <key>ProgramArguments</key>
  <array><string><PY></string><string><RADICE>/bin/plancia</string><string>serve</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string><CASA>/.plancia/plancia.log</string>
  <key>StandardErrorPath</key><string><CASA>/.plancia/plancia.log</string>
  <key>ProcessType</key><string>Background</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string><CASA>/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
</dict>
</plist>
"""

PLIST_RIEPILOGO_MAC = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.plancia.recap</string>
  <key>ProgramArguments</key>
  <array><string><PY></string><string><RADICE>/bin/plancia</string><string>recap</string>
    <string>--daily</string><string>--notify</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>45</integer></dict>
  <key>StandardOutPath</key><string><CASA>/.plancia/recap.log</string>
  <key>StandardErrorPath</key><string><CASA>/.plancia/recap.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string><CASA>/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
"""

BLOCCO_CODEX_POSIX = ('model = "x"\n\n[mcp_servers.plancia]\n'
                      'command = "<RADICE>/bin/plancia-mcp"\n'
                      'args = ["--agente", "codex"]\n'
                      'startup_timeout_sec = 30\n')


def _applescript_quote_base(testo):
    """La funzione di riprendi.py com'era prima di questo lotto."""
    return '"%s"' % testo.replace("\\", "\\\\").replace('"', '\\"')


def _hook_atteso(comando, timeout):
    return [{"hooks": [{"type": "command", "command": comando, "timeout": timeout}]}]


def _hooks_attesi(hook, richiamo):
    return {"hooks": {"SessionStart": _hook_atteso(hook, 5), "SessionEnd": _hook_atteso(hook, 5),
                      "UserPromptSubmit": _hook_atteso(richiamo, 3)}}


# --------------------------------------------------------------------------
# le prove
# --------------------------------------------------------------------------

def esegui(prova):
    try:
        from plancia import piattaforma as pf
    except ImportError as exc:
        pf = None
        prova("plancia/piattaforma.py esiste", False, str(exc))
    if pf is not None:
        prova("plancia/piattaforma.py esiste", True)

    def gruppo(f, *args):
        """Un gruppo che cade su un'eccezione (una funzione che manca, un valore
        inatteso) e' un rosso con il suo nome, e non ferma gli altri gruppi."""
        try:
            f(prova, *args)
        except Exception as exc:  # noqa: BLE001
            prova("%s: nessuna eccezione" % f.__name__, False, "%s: %s" % (type(exc).__name__, exc))

    if pf is not None:
        gruppo(_prove_nome, pf)
        gruppo(_prove_costruttori_puri, pf)
        gruppo(_prove_windows_con_percorsi_veri, pf)
    gruppo(_prove_installazione)
    gruppo(_prove_ripiego_e_strumenti_assenti)
    gruppo(_prove_quando_il_comando_fallisce)
    gruppo(_prove_il_figlio_su_windows)
    if pf is not None:
        gruppo(_prove_mcp_in_utf8, pf)
        gruppo(_prove_simulazione_windows)
    gruppo(_prove_file_del_lotto)


# --------------------------------------------------------------------------
# nome()
# --------------------------------------------------------------------------

def _con_env(nome, valore, f):
    vecchio = os.environ.get(nome)
    if valore is None:
        os.environ.pop(nome, None)
    else:
        os.environ[nome] = valore
    try:
        return f()
    finally:
        if vecchio is None:
            os.environ.pop(nome, None)
        else:
            os.environ[nome] = vecchio


def _prove_nome(prova, pf):
    for p in PIATTAFORME:
        prova("nome(): PLANCIA_PIATTAFORMA=%s vince" % p,
              _con_env("PLANCIA_PIATTAFORMA", p, pf.nome) == p)
    vera = sys.platform
    esiti = {}
    try:
        for sp in ("darwin", "win32", "cygwin", "linux", "freebsd13"):
            sys.platform = sp
            esiti[sp] = _con_env("PLANCIA_PIATTAFORMA", None, pf.nome)
        sys.platform = "linux"
        esiti["valore_strano"] = _con_env("PLANCIA_PIATTAFORMA", "amiga", pf.nome)
    finally:
        sys.platform = vera
    prova("nome(): da sys.platform, e un valore strano nell'ambiente si ignora",
          esiti == {"darwin": "mac", "win32": "windows", "cygwin": "windows",
                    "linux": "linux", "freebsd13": "linux", "valore_strano": "linux"},
          str(esiti))


# --------------------------------------------------------------------------
# i costruttori, uno per piattaforma
# --------------------------------------------------------------------------

def _ha(*presenti):
    """Un `cerca` finto: trova solo i programmi dati."""
    return lambda programma: ("/fake/" + programma) if programma in presenti else None


def _prove_costruttori_puri(prova, pf):
    argv = ["claude", "--resume", "abc-123"]
    cwd = "/tmp/una cartella"

    # ---- terminale
    prova("terminale mac: lo stesso osascript di sempre",
          pf.comando_terminale(cwd, argv, "mac") == [
              "osascript", "-e",
              'tell application "Terminal" to do script '
              '"cd \'/tmp/una cartella\' && claude --resume abc-123"'],
          str(pf.comando_terminale(cwd, argv, "mac")))
    strano = ["claude", 'dì "ciao" \\ x']
    riga_base = "cd %s && %s" % (shlex.quote(cwd), shlex.join(strano))
    prova("terminale mac: le virgolette e le barre si citano come prima",
          pf.comando_terminale(cwd, strano, "mac")
          == ["osascript", "-e", "tell application \"Terminal\" to do script %s"
              % _applescript_quote_base(riga_base)])
    prova("terminale windows: wt.exe se c'e'",
          pf.comando_terminale(r"C:\Users\Utente\lavoro", argv, "windows", _ha("wt"))
          == ["wt.exe", "-d", r"C:\Users\Utente\lavoro", "claude", "--resume", "abc-123"])
    prova("terminale windows: senza wt, l'argv direttamente (niente cmd.exe), nella cartella, "
          "con una console nuova",
          pf.piano_terminale(r"C:\Users\Utente\lavoro", argv, "windows", _ha())
          == {"argv": ["claude", "--resume", "abc-123"], "cwd": r"C:\Users\Utente\lavoro",
              "nuova_console": True}
          and pf.piano_terminale(r"C:\Users\Utente\lavoro", argv, "windows", _ha("claude"))["argv"][0]
          == "/fake/claude")
    ostile = ["claude", "--resume", "abc", "riprendi il task 3 di Plancia: " + TITOLO_OSTILE]
    senza_wt = pf.piano_terminale(r"C:\x", ostile, "windows", _ha())
    prova("terminale windows senza wt: un titolo con \", &, %PATH% e ; arriva intatto come UN argomento, "
          "e nessun elemento e' cmd, start o /k",
          senza_wt["argv"][3] == ostile[3] and len(senza_wt["argv"]) == 4
          and not {"cmd", "cmd.exe", "start", "/c", "/k"} & set(senza_wt["argv"]),
          str(senza_wt))
    con_wt = pf.comando_terminale(r"C:\x;y", ostile, "windows", _ha("wt"))
    prova("terminale windows con wt: ogni ; e' scappato (\\;) in ogni argomento, cartella compresa, "
          "e il resto del titolo resta com'e'",
          con_wt == ["wt.exe", "-d", "C:\\x\\;y", "claude", "--resume", "abc",
                     "riprendi il task 3 di Plancia: " + TITOLO_OSTILE.replace(";", "\\;")]
          and all(";" not in a.replace("\\;", "") for a in con_wt), str(con_wt))
    prova("il processo del terminale: console nuova (CREATE_NEW_CONSOLE) senza wt, staccato con wt e su "
          "Linux; la cartella solo dove serve; niente creationflags su un host che non e' Windows",
          pf.opzioni_distacco("windows", "C:\\x", True, nt=True)["creationflags"] == 0x10
          and pf.opzioni_distacco("windows", "C:\\x", True, nt=True)["cwd"] == "C:\\x"
          and pf.opzioni_distacco("windows", None, False, nt=True)["creationflags"] == (0x08 | 0x200)
          and "cwd" not in pf.opzioni_distacco("windows", None, False, nt=True)
          and "creationflags" not in pf.opzioni_distacco("windows", None, False, nt=False)
          and pf.opzioni_distacco("linux")["start_new_session"] is True
          and all(pf.opzioni_distacco(p)["stdin"] == subprocess.DEVNULL for p in PIATTAFORME))
    linux = {
        "x-terminal-emulator": ["x-terminal-emulator", "-e", "sh", "-c",
                                "cd '/tmp/una cartella' && claude --resume abc-123"],
        "gnome-terminal": ["gnome-terminal", "--working-directory=/tmp/una cartella", "--",
                           "claude", "--resume", "abc-123"],
        "konsole": ["konsole", "--workdir", "/tmp/una cartella", "-e",
                    "claude", "--resume", "abc-123"],
        "xterm": ["xterm", "-e", "sh", "-c", "cd '/tmp/una cartella' && claude --resume abc-123"],
    }
    for programma, atteso in linux.items():
        prova("terminale linux: %s" % programma,
              pf.comando_terminale(cwd, argv, "linux", _ha(programma)) == atteso,
              str(pf.comando_terminale(cwd, argv, "linux", _ha(programma))))
    prova("terminale linux: l'ordine e' x-terminal-emulator, gnome-terminal, konsole, xterm",
          pf.comando_terminale(cwd, argv, "linux",
                               _ha("xterm", "konsole", "gnome-terminal"))[0] == "gnome-terminal"
          and pf.comando_terminale(cwd, argv, "linux", _ha("xterm", "konsole"))[0] == "konsole")
    prova("terminale linux: nessun terminale vuol dire None",
          pf.comando_terminale(cwd, argv, "linux", _ha()) is None)

    # ---- appunti
    prova("appunti: pbcopy su mac, clip su windows",
          _con_env("PLANCIA_CLIPBOARD", None, lambda: (
              pf.comando_appunti("mac"), pf.comando_appunti("windows")))
          == (["pbcopy"], ["clip"]))
    prova("appunti linux: wl-copy, poi xclip, poi xsel, poi None",
          _con_env("PLANCIA_CLIPBOARD", None, lambda: (
              pf.comando_appunti("linux", _ha("wl-copy", "xclip", "xsel")),
              pf.comando_appunti("linux", _ha("xclip", "xsel")),
              pf.comando_appunti("linux", _ha("xsel")),
              pf.comando_appunti("linux", _ha())))
          == (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-b"], None))
    testo_clip = "perch\u00e9 \u00e8 cos\u00ec \u2192 fatto"
    prova("appunti windows: a `clip` gli accenti arrivano come UTF-16 con BOM, non nella codepage; "
          "altrove e con un lanciatore alternativo il testo com'e'",
          pf.input_appunti(testo_clip, ["clip"], "windows")
          == b"\xff\xfe" + testo_clip.encode("utf-16-le")
          and pf.input_appunti(testo_clip, ["/x/finto"], "windows") == testo_clip
          and pf.input_appunti(testo_clip, ["pbcopy"], "mac") == testo_clip
          and pf.input_appunti(testo_clip, ["wl-copy"], "linux") == testo_clip)
    prova("appunti: PLANCIA_CLIPBOARD vince su tutte e tre",
          all(_con_env("PLANCIA_CLIPBOARD", "/x/finto --f", lambda p=p: pf.comando_appunti(p, _ha("wl-copy")))
              == ["/x/finto", "--f"] for p in PIATTAFORME))

    # ---- voce
    prova("voce mac: lo stesso say di sempre",
          pf.comando_sintesi("Ciao", "it", "Alice", "185", "/tmp/o.wav", "mac")
          == ["say", "-v", "Alice", "-r", "185", "-o", "/tmp/o.wav",
              "--data-format=LEI16@22050", "Ciao"])
    testo = "L'ora e' \"otto\" e un po' di piu', caffe' \u2615 \u00e8 pronto"
    w = pf.comando_sintesi(testo, "it", "", "185", r"C:\Users\Utente\o'k.wav", "windows",
                           _ha("powershell"))
    script = w[-1] if w else ""
    b64 = re.search(r"FromBase64String\('([^']+)'\)", script)
    import base64
    prova("voce windows: PowerShell con System.Speech, testo in base64 (nessuna citazione a mano)",
          bool(w) and w[:6] == ["powershell", "-NoProfile", "-NonInteractive", "-InputFormat", "None",
                                "-Command"]
          and "System.Speech.Synthesis.SpeechSynthesizer" in script and "it-IT" in script
          and bool(b64) and base64.b64decode(b64.group(1)).decode("utf-8") == testo
          and "otto" not in script.replace(b64.group(1), "")
          and "SetOutputToWaveFile('C:\\Users\\Utente\\o''k.wav')" in script
          and "$s.Rate = 1" in script,
          script[:300])
    prova("voce windows: senza PowerShell, None (e la voce lo dice, il resto continua)",
          pf.comando_sintesi("Ciao", "it", "", "185", "o.wav", "windows", _ha()) is None)
    prova("voce windows: scelta della voce per nome, velocita' agli estremi",
          "SelectVoice('Microsoft Elsa')" in pf.comando_sintesi(
              "x", "it", "Microsoft Elsa", "185", "o.wav", "windows", _ha("pwsh"))[-1]
          and "$s.Rate = 10" in pf.comando_sintesi(
              "x", "it", "", "999", "o.wav", "windows", _ha("powershell"))[-1]
          and "$s.Rate = -10" in pf.comando_sintesi(
              "x", "it", "", "10", "o.wav", "windows", _ha("powershell"))[-1])
    prova("voce linux: espeak-ng, poi espeak, poi None",
          pf.comando_sintesi("Ciao", "it", "", "185", "/tmp/o.wav", "linux", _ha("espeak-ng", "espeak"))
          == ["espeak-ng", "-v", "it", "-s", "185", "-w", "/tmp/o.wav", "--", "Ciao"]
          and pf.comando_sintesi("Ciao", "en", "", "185", "/tmp/o.wav", "linux", _ha("espeak"))
          == ["espeak", "-v", "en", "-s", "185", "-w", "/tmp/o.wav", "--", "Ciao"]
          and pf.comando_sintesi("Ciao", "it", "", "185", "/tmp/o.wav", "linux", _ha("spd-say")) is None)
    prova("voce linux: spd-say solo per dire, non per scrivere un file; mai su mac e windows",
          pf.comando_dire("Ciao", "it", True, "linux", _ha("spd-say"))
          == ["spd-say", "-w", "-l", "it", "--", "Ciao"]
          and pf.comando_dire("Ciao", "it", False, "linux", _ha("spd-say"))
          == ["spd-say", "-l", "it", "--", "Ciao"]
          and pf.comando_dire("Ciao", "it", True, "mac", _ha("spd-say")) is None
          and pf.comando_dire("Ciao", "it", True, "linux", _ha()) is None)
    prova("riproduzione: afplay su mac, SoundPlayer su windows (apice raddoppiato)",
          pf.comando_riproduzione("/tmp/o.wav", "mac") == ["afplay", "/tmp/o.wav"]
          and pf.comando_riproduzione(r"C:\t\o'k.wav", "windows", _ha("powershell"))[-1]
          == "(New-Object System.Media.SoundPlayer 'C:\\t\\o''k.wav').PlaySync()"
          and pf.comando_riproduzione("o.wav", "windows", _ha()) is None)
    prova("riproduzione linux: paplay, aplay, pw-play, ffplay, play, poi None",
          [pf.comando_riproduzione("/t/o.wav", "linux", _ha(*p)) for p in
           (("paplay", "aplay"), ("aplay", "pw-play"), ("pw-play", "ffplay"), ("ffplay", "play"),
            ("play",), ())]
          == [["paplay", "/t/o.wav"], ["aplay", "-q", "/t/o.wav"], ["pw-play", "/t/o.wav"],
              ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "/t/o.wav"],
              ["play", "-q", "/t/o.wav"], None])
    prova("linux: un testo che comincia con '-' non diventa un'opzione (espeak, spd-say, notify-send: `--`)",
          all(c[c.index("--") + 1] == "-rm -rf" for c in (
              pf.comando_sintesi("-rm -rf", "it", "", "185", "o.wav", "linux", _ha("espeak-ng")),
              pf.comando_dire("-rm -rf", "it", True, "linux", _ha("spd-say"))))
          and pf.comando_notifica("-t", "-rm -rf", "linux", _ha("notify-send"))
          == ["notify-send", "--", "-t", "-rm -rf"])
    prova("PowerShell: -InputFormat None per Windows PowerShell 5.1 (legge lo stdin rediretto), non per pwsh",
          pf.comando_riproduzione("o.wav", "windows", _ha("powershell"))[:5]
          == ["powershell", "-NoProfile", "-NonInteractive", "-InputFormat", "None"]
          and "-InputFormat" not in pf.comando_riproduzione("o.wav", "windows", _ha("pwsh")))
    prova("processi di contorno: stdin chiuso ovunque, e su Windows CREATE_NO_WINDOW (niente console "
          "nera sotto pythonw); su un host che non e' Windows nessun creationflags",
          pf.opzioni_processo("windows", nt=True) == {"stdin": subprocess.DEVNULL, "creationflags": 0x08000000}
          and pf.opzioni_processo("windows", nt=False) == {"stdin": subprocess.DEVNULL}
          and pf.opzioni_processo("mac") == {"stdin": subprocess.DEVNULL}
          and pf.opzioni_processo("linux", nt=True) == {"stdin": subprocess.DEVNULL})
    prova("voce: la frase di 'manca il motore' dice cosa installare",
          "espeak-ng" in pf.motore_voce_assente("linux")
          and "PowerShell" in pf.motore_voce_assente("windows"))

    # ---- notifica
    prova("notifica mac: lo stesso osascript di sempre",
          pf.comando_notifica("Plancia", "Ciao mondo", "mac")
          == ["osascript", "-e", 'display notification "Ciao mondo" with title "Plancia"'])
    n = pf.comando_notifica("Plancia", "Non c'e' niente", "windows", _ha("powershell"))
    prova("notifica windows: PowerShell senza moduli esterni (NotifyIcon), apici raddoppiati",
          bool(n) and n[0] == "powershell" and "System.Windows.Forms.NotifyIcon" in n[-1]
          and "ShowBalloonTip(10000, 'Plancia', 'Non c''e'' niente'" in n[-1]
          and pf.comando_notifica("P", "t", "windows", _ha()) is None)
    prova("notifica linux: notify-send se c'e', altrimenti None (mai un errore)",
          pf.comando_notifica("Plancia", "Ciao", "linux", _ha("notify-send"))
          == ["notify-send", "--", "Plancia", "Ciao"]
          and pf.comando_notifica("Plancia", "Ciao", "linux", _ha()) is None)

    # ---- registrare i comandi
    script_hook = "/repo/bin/plancia-hook"
    prova("comando registrato: su mac e linux lo script nudo, com'e' sempre stato",
          pf.riga_script(script_hook, "/usr/bin/python3", "mac") == script_hook
          and pf.riga_script(script_hook, "/usr/bin/python3", "linux") == script_hook
          and pf.argv_script(script_hook, "/usr/bin/python3", "mac") == [script_hook]
          and pf.argv_script(script_hook, "/usr/bin/python3", "linux") == [script_hook])
    prova("comando registrato: su windows \"<python>\" -X utf8 \"<script>\" e argv [python, -X, utf8, script] "
          "(stdio in UTF-8: Claude Code e Codex parlano UTF-8, Python su Windows con le pipe usa cp1252)",
          pf.riga_script(r"C:\Users\Nome Cognome\plancia\bin\plancia-hook",
                         r"C:\Program Files\Python312\python.exe", "windows")
          == '"C:\\Program Files\\Python312\\python.exe" -X utf8 "C:\\Users\\Nome Cognome\\plancia\\bin\\plancia-hook"'
          and pf.argv_script(r"C:\p\plancia-mcp", r"C:\Py\python.exe", "windows")
          == [r"C:\Py\python.exe", "-X", "utf8", r"C:\p\plancia-mcp"])
    prova("blocco TOML di Codex: mac e linux come sempre, windows con le barre raddoppiate",
          pf.blocco_mcp_toml(["/repo/bin/plancia-mcp"], ["--agente", "codex"])
          == '\n[mcp_servers.plancia]\ncommand = "/repo/bin/plancia-mcp"\n'
             'args = ["--agente", "codex"]\nstartup_timeout_sec = 30\n'
          and pf.blocco_mcp_toml(pf.argv_script(r"C:\src\bin\plancia-mcp",
                                                r"C:\Program Files\Py\python.exe", "windows"),
                                 ["--agente", "codex"])
          == '\n[mcp_servers.plancia]\ncommand = "C:\\\\Program Files\\\\Py\\\\python.exe"\n'
             'args = ["-X", "utf8", "C:\\\\src\\\\bin\\\\plancia-mcp", "--agente", "codex"]\n'
             'startup_timeout_sec = 30\n')
    prova("comando `plancia`: ~/.local/bin su mac e linux, plancia.cmd sotto LOCALAPPDATA su windows",
          _n(pf.percorso_comando("/home/u", "mac")) == "/home/u/.local/bin/plancia"
          and _n(pf.percorso_comando("/home/u", "linux")) == "/home/u/.local/bin/plancia"
          and pf.percorso_comando("/home/u", "windows", {"LOCALAPPDATA": "/L"}).parts[-3:]
          == ("Plancia", "bin", "plancia.cmd")
          and pf.percorso_comando("/home/u", "windows", {"LOCALAPPDATA": "/L"}).parts[1] == "L"
          and pf.percorso_comando("/home/u", "windows", {}).parts[-5:-2] == ("AppData", "Local", "Plancia"))
    prova("shim windows: @echo off, \"<python>\" -X utf8 \"<script>\" %*, ritorni a capo di Windows",
          pf.shim_windows(r"C:\Py 3\python.exe", r"C:\src\plancia\bin\plancia")
          == '@echo off\r\n"C:\\Py 3\\python.exe" -X utf8 "C:\\src\\plancia\\bin\\plancia" %*\r\n')
    prova("PATH: su windows le maiuscole e la barra finale non contano, su mac e linux si',"
          " no",
          pf.nel_path(r"C:\Users\U\AppData\Local\Plancia\bin",
                      r"C:\Windows;c:\users\u\appdata\local\plancia\bin\;C:\x", "windows")
          and not pf.nel_path("/a/B", "/x:/a/b", "linux") and pf.nel_path("/a/b", "/x:/a/b", "mac"))

    # ---- avvio automatico e riepilogo: i piani
    casa = "/Users/utente"
    py, sc, log = "/usr/bin/python3", "/src/plancia/bin/plancia", "/Users/utente/.plancia/plancia.log"
    m = pf.piano_server(py, sc, log, casa, uid=501, piatt="mac")
    plist_atteso = (PLIST_SERVER_MAC.replace("<PY>", py).replace("<RADICE>", "/src/plancia")
                    .replace("<CASA>", casa))
    prova("avvio mac: stesso plist, stessa etichetta, stessi launchctl di sempre",
          m["file"][0][0] == Path(casa) / "Library/LaunchAgents/com.plancia.server.plist"
          and _n(m["file"][0][1]) == plist_atteso and len(m["file"]) == 1
          and _nl(m["attiva"]) == [["launchctl", "bootout", "gui/501/com.plancia.server"],
                                   ["launchctl", "bootstrap", "gui/501",
                                    casa + "/Library/LaunchAgents/com.plancia.server.plist"]]
          and m["disattiva"] == [["launchctl", "bootout", "gui/501/com.plancia.server"]]
          and m["rimuovi"] == m["presente"] == [Path(casa) / "Library/LaunchAgents/com.plancia.server.plist"],
          str(m["file"][0][1][:120]))
    r = pf.piano_riepilogo(py, sc, 8, 45, "/Users/utente/.plancia/recap.log", casa, uid=501, piatt="mac")
    prova("riepilogo mac: stesso plist, stessi launchctl di sempre",
          _n(r["file"][0][1]) == (PLIST_RIEPILOGO_MAC.replace("<PY>", py).replace("<RADICE>", "/src/plancia")
                                  .replace("<CASA>", casa))
          and _nl(r["attiva"][1]) == ["launchctl", "bootstrap", "gui/501",
                                      casa + "/Library/LaunchAgents/com.plancia.recap.plist"],
          r["file"][0][1][:100])

    wpy, wsc = r"C:\Program Files\Python312\python.exe", r"C:\src\plancia\bin\plancia"
    azione = '"C:\\Program Files\\Python312\\python.exe" -X utf8 "C:\\src\\plancia\\bin\\plancia" serve'
    amb = {"APPDATA": r"C:\Users\U\AppData\Roaming"}
    w = pf.piano_server(wpy, wsc, "log", r"C:\Users\U", piatt="windows", ambiente=amb,
                        esiste=lambda p: False)
    prova("avvio windows: schtasks /Create /SC ONLOGON, con ripiego nella cartella Esecuzione automatica",
          w["attiva"] == [["schtasks", "/Create", "/TN", "Plancia server", "/SC", "ONLOGON",
                           "/TR", azione, "/F"]]
          and w["disattiva"] == [["schtasks", "/Delete", "/TN", "Plancia server", "/F"]]
          and w["query"] == ["schtasks", "/Query", "/TN", "Plancia server"]
          and w["ripiego"]["file"][0][1] == '@echo off\r\nstart "" %s\r\n' % azione
          and w["ripiego"]["file"][0][0].name == "plancia.cmd"
          and str(w["ripiego"]["file"][0][0]).replace("\\", "/").endswith(
              "Microsoft/Windows/Start Menu/Programs/Startup/plancia.cmd"),
          str(w["attiva"]))
    wp = pf.piano_server(wpy, wsc, "log", r"C:\Users\U", piatt="windows", ambiente=amb,
                         esiste=lambda p: p.endswith("pythonw.exe"))
    prova("avvio windows: con pythonw.exe accanto all'interprete lo usa (niente finestra nera)",
          wp["attiva"][0][7].startswith('"C:\\Program Files\\Python312\\pythonw.exe" -X utf8 '),
          wp["attiva"][0][7])
    wr = pf.piano_riepilogo(wpy, wsc, 8, 5, "log", r"C:\Users\U", piatt="windows", esiste=lambda p: False)
    prova("riepilogo windows: schtasks /SC DAILY /ST HH:MM",
          wr["attiva"] == [["schtasks", "/Create", "/TN", "Plancia riepilogo", "/SC", "DAILY", "/ST",
                            "08:05", "/TR",
                            '"C:\\Program Files\\Python312\\python.exe" -X utf8 '
                            '"C:\\src\\plancia\\bin\\plancia" recap --daily --notify', "/F"]]
          and wr["disattiva"] == [["schtasks", "/Delete", "/TN", "Plancia riepilogo", "/F"]])

    casa_l = "/home/utente"
    l = pf.piano_server("/usr/bin/python3", "/src/my plancia/bin/plancia", "/home/utente/.plancia/plancia.log",
                        casa_l, piatt="linux", ambiente={}, cerca_fn=_ha("systemctl"))
    unita = l["file"][0]
    prova("avvio linux: unita' systemd --user, ExecStart con virgolette, enable --now, ripiego .desktop",
          _n(unita[0]) == "/home/utente/.config/systemd/user/plancia.service"
          and 'ExecStart="/usr/bin/python3" "/src/my plancia/bin/plancia" serve\n' in unita[1]
          and "Restart=on-failure" in unita[1] and "WantedBy=default.target" in unita[1]
          and "StandardOutput=append:/home/utente/.plancia/plancia.log" in unita[1]
          and l["attiva"] == [["systemctl", "--user", "daemon-reload"],
                              ["systemctl", "--user", "enable", "--now", "plancia.service"]]
          and l["disattiva"] == [["systemctl", "--user", "disable", "--now", "plancia.service"]]
          and _n(l["ripiego"]["file"][0][0]) == "/home/utente/.config/autostart/plancia.desktop"
          and 'Exec="/usr/bin/python3" "/src/my plancia/bin/plancia" serve' in l["ripiego"]["file"][0][1]
          and set(map(_n, l["rimuovi"])) == {"/home/utente/.config/systemd/user/plancia.service",
                                             "/home/utente/.config/autostart/plancia.desktop"},
          str(l["attiva"]))
    prova("avvio linux: senza systemctl si va diretti al .desktop; XDG_CONFIG_HOME si rispetta",
          pf.piano_server("/p", "/s", "/l", casa_l, piatt="linux", ambiente={}, cerca_fn=_ha())["nome"]
          == "~/.config/autostart"
          and _n(pf.piano_server("/p", "/s", "/l", casa_l, piatt="linux",
                                 ambiente={"XDG_CONFIG_HOME": "/xdg"},
                                 cerca_fn=_ha("systemctl"))["file"][0][0])
          == "/xdg/systemd/user/plancia.service")
    lr = pf.piano_riepilogo("/usr/bin/python3", "/src/plancia/bin/plancia", 8, 45, "/l.log", casa_l,
                            piatt="linux", ambiente={}, cerca_fn=_ha("systemctl"))
    prova("riepilogo linux: un servizio oneshot e un timer OnCalendar alle 08:45",
          [_n(f[0]) for f in lr["file"]] == ["/home/utente/.config/systemd/user/plancia-riepilogo.service",
                                             "/home/utente/.config/systemd/user/plancia-riepilogo.timer"]
          and "Type=oneshot" in lr["file"][0][1] and "recap --daily --notify" in lr["file"][0][1]
          and "OnCalendar=*-*-* 08:45:00" in lr["file"][1][1] and "Persistent=true" in lr["file"][1][1]
          and lr["attiva"][-1] == ["systemctl", "--user", "enable", "--now", "plancia-riepilogo.timer"]
          and pf.piano_riepilogo("/p", "/s", 8, 45, "/l", casa_l, piatt="linux", ambiente={},
                                 cerca_fn=_ha()) is None)
    prova("nomi per le frasi: launchd, Task Scheduler, systemd",
          [pf.nome_avvio(p) for p in PIATTAFORME] == ["launchd", "Task Scheduler", "systemd"])


def _prove_windows_con_percorsi_veri(prova, pf):
    """Il riconoscimento dei nostri hook su un comando di Windows: finisce con una
    virgoletta, e senza questo `remove_hooks` lascerebbe gli hook dov'erano."""
    from plancia import setup_claude as s
    riga = '"C:\\Program Files\\Py\\python.exe" -X utf8 "C:\\src\\plancia\\bin\\plancia-hook"'
    prova("riconosce un hook nostro anche con la virgoletta finale, e non uno altrui",
          s._e_nostro(riga, "plancia-hook") and s._e_nostro("/repo/bin/plancia-hook", "plancia-hook")
          and not s._e_nostro('"C:\\Py\\python.exe" -X utf8 "C:\\altro\\altro-hook"', "plancia-hook")
          and not s._e_nostro(None, "plancia-hook"))
    prova("la scelta di pythonw.exe: solo accanto a python.exe, altrimenti l'interprete",
          pf.python_senza_finestra(r"C:\Py\python.exe", lambda p: p == r"C:\Py\pythonw.exe")
          == r"C:\Py\pythonw.exe"
          and pf.python_senza_finestra(r"C:\Py\python.exe", lambda p: False) == r"C:\Py\python.exe"
          and pf.python_senza_finestra("/usr/bin/python3", lambda p: True) == "/usr/bin/python3")


# --------------------------------------------------------------------------
# l'installazione vera, in una casa finta, una piattaforma alla volta
# --------------------------------------------------------------------------

def _prove_installazione(prova):
    dati = {p: _figlio_lancia(p) for p in PIATTAFORME}
    host_windows = os.name == "nt"

    for p in PIATTAFORME:
        d = dati[p]
        prova("[%s] il figlio d'installazione gira fino in fondo" % p,
              "ERRORE" not in d and all(
                  not str(_r(d, k)).startswith("ECCEZIONE") for k in (
                      "install_mcp", "codex_registra", "install_hooks", "autostart_on",
                      "recap_on", "apri", "appunti", "notifica", "voce_parla", "doctor",
                      "autostart_off", "recap_off", "uninstall_all")),
              d.get("ERRORE") or str([(k, v["ritorno"]) for k, v in d.items()
                                      if isinstance(v, dict)
                                      and str(v.get("ritorno")).startswith("ECCEZIONE")]))

    # ---- hook
    mac_posix = _hooks_attesi("<RADICE>/bin/plancia-hook", "<RADICE>/bin/plancia-richiamo")
    for p in ("mac", "linux"):
        prova("[%s] hook: gli script nudi, IDENTICI a oggi" % p,
              _settings(dati[p]) == mac_posix, json.dumps(_settings(dati[p]))[:300])
    prova("[windows] hook: \"<python>\" -X utf8 \"<script>\" per ogni evento",
          _settings(dati["windows"]) == _hooks_attesi(
              '"<PY>" -X utf8 "<RADICE>/bin/plancia-hook"',
              '"<PY>" -X utf8 "<RADICE>/bin/plancia-richiamo"'),
          json.dumps(_settings(dati["windows"]))[:300])
    for p in PIATTAFORME:
        prova("[%s] hook: installarli due volte non li duplica, e li riconosce" % p,
              (_r(dati[p], "agganciati") or [])[:2] == [True, True]
              and all(len(v) == 1 for v in _comandi_hook(dati[p]).values()),
              str(_r(dati[p], "agganciati")) + str(_comandi_hook(dati[p])))
        prova("[%s] hook: la disinstallazione li toglie tutti" % p,
              _settings(dati[p], "FILE_DOPO").get("hooks") is None
              and _r(dati[p], "agganciati_dopo") == [False, False, False],
              str(_r(dati[p], "agganciati_dopo")))

    # ---- MCP
    for p in ("mac", "linux"):
        prova("[%s] MCP con claude: gli stessi due comandi di sempre" % p,
              _run(dati[p], "install_mcp") == [
                  ["/fake/bin/claude", "mcp", "remove", "plancia", "--scope", "user"],
                  ["/fake/bin/claude", "mcp", "add", "plancia", "--scope", "user", "--",
                   "<RADICE>/bin/plancia-mcp"]], str(_run(dati[p], "install_mcp")))
    prova("[windows] MCP con claude: si registra [python, -X, utf8, script], non lo script nudo",
          _run(dati["windows"], "install_mcp") == [
              ["/fake/bin/claude", "mcp", "remove", "plancia", "--scope", "user"],
              ["/fake/bin/claude", "mcp", "add", "plancia", "--scope", "user", "--", "<PY>",
               "-X", "utf8", "<RADICE>/bin/plancia-mcp"]], str(_run(dati["windows"], "install_mcp")))

    # ---- Codex
    for p in ("mac", "linux"):
        prova("[%s] blocco MCP in Codex: IDENTICO a oggi" % p,
              _file(dati[p], "FILE_INSTALLATI").get(".codex/config.toml") == BLOCCO_CODEX_POSIX,
              repr(_file(dati[p], "FILE_INSTALLATI").get(".codex/config.toml")))
    prova("[windows] blocco MCP in Codex: command = python, args = [-X, utf8, script, --agente, codex]",
          _file(dati["windows"], "FILE_INSTALLATI").get(".codex/config.toml") == (
              'model = "x"\n\n[mcp_servers.plancia]\ncommand = "<PY>"\n'
              'args = ["-X", "utf8", "<RADICE>/bin/plancia-mcp", "--agente", "codex"]\n'
              'startup_timeout_sec = 30\n'),
          repr(_file(dati["windows"], "FILE_INSTALLATI").get(".codex/config.toml")))
    for p in PIATTAFORME:
        prova("[%s] Codex: la disinstallazione toglie il blocco" % p,
              "[mcp_servers.plancia]" not in _file(dati[p], "FILE_DOPO").get(".codex/config.toml", "x"))

    # ---- comando `plancia`
    for p in ("mac", "linux"):
        if host_windows:
            prova("[%s] comando: collegamento in ~/.local/bin (saltata su Windows: il symlink chiede privilegi)"
                  % p, True)
        else:
            prova("[%s] comando: collegamento simbolico ~/.local/bin/plancia -> bin/plancia" % p,
                  _file(dati[p], "FILE_INSTALLATI").get(".local/bin/plancia") == "-> <RADICE>/bin/plancia"
                  and _r(dati[p], "install_command") ==
                  "comando in <CASA>/.local/bin/plancia, aggiungi <CASA>/.local/bin al PATH",
                  str(_r(dati[p], "install_command")))
    prova("[windows] comando: shim plancia.cmd con \"<python>\" -X utf8 \"<script>\" %*",
          _file(dati["windows"], "FILE_INSTALLATI").get("AppData/Local/Plancia/bin/plancia.cmd")
          == '@echo off\r\n"<PY>" -X utf8 "<RADICE>/bin/plancia" %*\r\n'
          and "aggiungi <CASA>/AppData/Local/Plancia/bin al PATH" in str(_r(dati["windows"], "install_command")),
          str(_r(dati["windows"], "install_command")))
    prova("[windows] disinstallazione: lo shim se ne va",
          "AppData/Local/Plancia/bin/plancia.cmd" not in _file(dati["windows"], "FILE_DOPO"))

    # ---- avvio automatico e riepilogo
    prova("[mac] avvio automatico: stessi launchctl, stesso plist, e si toglie tutto",
          _run(dati["mac"], "autostart_on") == [
              ["launchctl", "bootout", "gui/501/com.plancia.server"],
              ["launchctl", "bootstrap", "gui/501", "<CASA>/Library/LaunchAgents/com.plancia.server.plist"]]
          and _file(dati["mac"], "FILE_INSTALLATI").get("Library/LaunchAgents/com.plancia.server.plist")
          == PLIST_SERVER_MAC
          and _run(dati["mac"], "autostart_off") == [["launchctl", "bootout", "gui/501/com.plancia.server"]]
          and _r(dati["mac"], "autostart_on") == "avvio automatico attivo: la dashboard riparte a ogni accesso",
          str(_run(dati["mac"], "autostart_on")))
    prova("[mac] riepilogo giornaliero: stessi launchctl, stesso plist, e si toglie tutto",
          _run(dati["mac"], "recap_on") == [
              ["launchctl", "bootout", "gui/501/com.plancia.recap"],
              ["launchctl", "bootstrap", "gui/501", "<CASA>/Library/LaunchAgents/com.plancia.recap.plist"]]
          and _file(dati["mac"], "FILE_INSTALLATI").get("Library/LaunchAgents/com.plancia.recap.plist")
          == PLIST_RIEPILOGO_MAC
          and _run(dati["mac"], "recap_off") == [["launchctl", "bootout", "gui/501/com.plancia.recap"]]
          and _r(dati["mac"], "recap_on") == "riepilogo automatico alle 08:45 con la voce",
          str(_run(dati["mac"], "recap_on")))
    az_win = '"<PY>" -X utf8 "<RADICE>/bin/plancia" serve'
    prova("[windows] avvio automatico: schtasks /Create /SC ONLOGON, /Delete per toglierlo, niente launchctl",
          _run(dati["windows"], "autostart_on") == [
              ["schtasks", "/Create", "/TN", "Plancia server", "/SC", "ONLOGON", "/TR", az_win, "/F"]]
          and _run(dati["windows"], "autostart_off") == [["schtasks", "/Delete", "/TN", "Plancia server", "/F"]]
          and _r(dati["windows"], "installati")[0] is True
          and _r(dati["windows"], "installati_dopo") == [False, False],
          str(_run(dati["windows"], "autostart_on")))
    prova("[windows] riepilogo giornaliero: schtasks /SC DAILY /ST 08:45, /Delete per toglierlo",
          _run(dati["windows"], "recap_on") == [
              ["schtasks", "/Create", "/TN", "Plancia riepilogo", "/SC", "DAILY", "/ST", "08:45", "/TR",
               '"<PY>" -X utf8 "<RADICE>/bin/plancia" recap --daily --notify', "/F"]]
          and _run(dati["windows"], "recap_off") == [["schtasks", "/Delete", "/TN", "Plancia riepilogo", "/F"]]
          and _r(dati["windows"], "installati") == [True, True],
          str(_run(dati["windows"], "recap_on")))
    unita = "<CASA>/.config/systemd/user/plancia.service"
    prova("[linux] avvio automatico: unita' systemd --user, enable --now, e disable --now per toglierlo",
          _run(dati["linux"], "autostart_on") == [
              ["systemctl", "--user", "daemon-reload"],
              ["systemctl", "--user", "enable", "--now", "plancia.service"]]
          and '.config/systemd/user/plancia.service' in "".join(_file(dati["linux"], "FILE_INSTALLATI"))
          and 'ExecStart="<PY>" "<RADICE>/bin/plancia" serve\n'
          in _file(dati["linux"], "FILE_INSTALLATI").get(".config/systemd/user/plancia.service", "")
          and _run(dati["linux"], "autostart_off") == [
              ["systemctl", "--user", "disable", "--now", "plancia.service"],
              ["systemctl", "--user", "daemon-reload"]]
          and _r(dati["linux"], "installati") == [True, True]
          and _r(dati["linux"], "installati_dopo") == [False, False],
          str(_run(dati["linux"], "autostart_on")))
    prova("[linux] riepilogo giornaliero: timer systemd --user alle 08:45",
          _run(dati["linux"], "recap_on")[-1] == ["systemctl", "--user", "enable", "--now",
                                                  "plancia-riepilogo.timer"]
          and "OnCalendar=*-*-* 08:45:00" in _file(dati["linux"], "FILE_INSTALLATI").get(
              ".config/systemd/user/plancia-riepilogo.timer", ""),
          str(_run(dati["linux"], "recap_on")))
    for p in PIATTAFORME:
        prova("[%s] disinstallazione: non resta nessun file di avvio o di riepilogo" % p,
              not [k for k in _file(dati[p], "FILE_DOPO")
                   if re.search(r"LaunchAgents|systemd|autostart|Startup|\.local/bin|Plancia/bin", k)],
              str(sorted(_file(dati[p], "FILE_DOPO"))))
    def lanciati(p):
        return {c.get("run", c.get("popen"))[0] for k, v in dati[p].items() if isinstance(v, dict)
                for c in v.get("comandi", [])}

    prova("mai un comando di un'altra piattaforma: launchctl, osascript, pbcopy, afplay solo su mac; "
          "schtasks solo su windows; systemctl solo su linux",
          all({"launchctl", "osascript", "pbcopy", "afplay", "say"} <= lanciati(p) if p == "mac" else
              not ({"launchctl", "osascript", "pbcopy", "afplay", "say"} & lanciati(p))
              for p in PIATTAFORME)
          and "schtasks" in lanciati("windows") and "schtasks" not in lanciati("mac")
          and "schtasks" not in lanciati("linux")
          and "systemctl" in lanciati("linux") and "systemctl" not in lanciati("mac")
          and "systemctl" not in lanciati("windows"),
          str({p: sorted(lanciati(p)) for p in PIATTAFORME}))

    prova("[windows] [linux] avvio automatico: con il meccanismo principale attivo (schtasks, systemd) "
          "il .cmd in Esecuzione automatica e il .desktop lasciati da un giro precedente spariscono: "
          "all'accesso non partono due server",
          "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/plancia.cmd"
          not in _file(dati["windows"], "FILE_INSTALLATI")
          and ".config/autostart/plancia.desktop" not in _file(dati["linux"], "FILE_INSTALLATI")
          and _r(dati["windows"], "installati")[0] is True and _r(dati["linux"], "installati")[0] is True,
          str(sorted(_file(dati["windows"], "FILE_INSTALLATI")))
          + str(sorted(_file(dati["linux"], "FILE_INSTALLATI"))))

    # ---- terminale (riprendi.apri)
    mac_apri = dati["mac"].get("apri", {}).get("ritorno") or {}
    prova("[mac] riprendi.apri: lo stesso osascript di sempre (come prima, con `run` e non staccato)",
          isinstance(mac_apri, dict) and bool(mac_apri.get("osascript_base"))
          and _run(dati["mac"], "apri") == [mac_apri["osascript_base"]]
          and mac_apri.get("riga") == mac_apri.get("riga_base")
          and not _popen(dati["mac"], "apri"), str(_run(dati["mac"], "apri"))[:300])
    w_apri = dati["windows"].get("apri", {}).get("ritorno") or {}
    prova("[windows] riprendi.apri: wt.exe -d <cartella> <comando>, staccato",
          isinstance(w_apri, dict) and _popen(dati["windows"], "apri")
          == [["wt.exe", "-d", w_apri.get("cwd")] + list(w_apri.get("argv", []))]
          and not _run(dati["windows"], "apri") and "errore" not in w_apri,
          str(_popen(dati["windows"], "apri"))[:300])
    l_apri = dati["linux"].get("apri", {}).get("ritorno") or {}
    prova("[linux] riprendi.apri: x-terminal-emulator -e sh -c 'cd <cartella> && <comando>', staccato",
          isinstance(l_apri, dict) and _popen(dati["linux"], "apri")
          == [["x-terminal-emulator", "-e", "sh", "-c", l_apri.get("riga_base")]]
          and l_apri.get("riga") == l_apri.get("riga_base") and not _run(dati["linux"], "apri"),
          str(_popen(dati["linux"], "apri"))[:300])
    prova("PLANCIA_TERMINALE vince su tutte e tre: [lanciatore, riga], senza staccarsi",
          all(_run(dati[p], "apri_con_lanciatore") == [[
              "/fake/lanciatore",
              (dati[p].get("apri_con_lanciatore", {}).get("ritorno") or {}).get("riga")]]
              and not _popen(dati[p], "apri_con_lanciatore") for p in PIATTAFORME),
          str([_run(dati[p], "apri_con_lanciatore") for p in PIATTAFORME])[:300])
    prova("la riga da mostrare: `cd` POSIX su mac e linux, `cd /d` con virgolette su windows",
          all((dati[p].get("apri", {}).get("ritorno") or {}).get("riga", "").startswith(inizio)
              for p, inizio in (("mac", "cd "), ("linux", "cd "), ("windows", "cd /d \""))),
          str([(dati[p].get("apri", {}).get("ritorno") or {}).get("riga", "")[:40] for p in PIATTAFORME]))

    # ---- il titolo di un task non passa da cmd.exe, e wt riceve i ; scappati
    o_w = dati["windows"].get("apri_ostile", {}).get("ritorno") or {}
    argv_o = list(o_w.get("argv") or [])
    # l'uscita del figlio ha le barre rovesciate tornate dritte (`_pulisci`): il `\;` e' `/;`
    attesi_wt = ["wt.exe", "-d", o_w.get("cwd")] + [a.replace(";", "/;") for a in argv_o]
    prova("[windows] riprendi.apri con wt e un titolo con \", &, %PATH% e ;: un argomento per pezzo, "
          "ogni ; scappato (\\;), il resto com'e'",
          bool(argv_o) and TITOLO_OSTILE in argv_o[-1] and _popen(dati["windows"], "apri_ostile") == [attesi_wt]
          and not _run(dati["windows"], "apri_ostile"),
          str(_popen(dati["windows"], "apri_ostile"))[:400])
    vuoto_o = _figlio_lancia("windows", "senza-strumenti")
    o_v = vuoto_o.get("apri_ostile", {}).get("ritorno") or {}
    pop_v = _popen(vuoto_o, "apri_ostile")
    prova("[windows] riprendi.apri senza wt: l'argv parte direttamente (mai cmd /c start ... cmd /k), "
          "nella cartella del task, con il titolo intatto in un solo argomento",
          bool(o_v.get("argv")) and len(pop_v) == 1 and pop_v[0] == o_v["argv"]
          and TITOLO_OSTILE in pop_v[0][-1]
          and not {"cmd", "cmd.exe", "start", "/c", "/k"} & set(pop_v[0])
          and [c.get("cwd") for c in _comandi(vuoto_o, "apri_ostile")] == [o_v.get("cwd")],
          str(_comandi(vuoto_o, "apri_ostile"))[:400])

    # ---- appunti
    prova("[mac] appunti: pbcopy con il testo su stdin, come prima",
          _comandi(dati["mac"], "appunti") == [{"run": ["pbcopy"], "input": "riprendi il task 3"}]
          and _r(dati["mac"], "appunti") is True)
    prova("[windows] appunti: clip con il testo su stdin, in UTF-16 con BOM (gli accenti non passano "
          "dalla codepage OEM)",
          _comandi(dati["windows"], "appunti")
          == [{"run": ["clip"], "input": "UTF16LE-BOM:riprendi il task 3"}])
    prova("[linux] appunti: wl-copy con il testo su stdin",
          _comandi(dati["linux"], "appunti") == [{"run": ["wl-copy"], "input": "riprendi il task 3"}])
    prova("PLANCIA_CLIPBOARD vince su tutte e tre",
          all(_comandi(dati[p], "appunti_sostituiti") == [{"run": ["/fake/appunti", "--flag"], "input": "ciao"}]
              for p in PIATTAFORME))

    # ---- notifica
    testo_notifica = "Ciao 'mondo' " + "x" * 207   # le virgolette diventano apici, poi 220 caratteri
    prova("[mac] notifica: lo stesso osascript di sempre, testo tagliato a 220",
          _run(dati["mac"], "notifica") == [["osascript", "-e",
                                             'display notification "%s" with title "Plancia"' % testo_notifica]],
          str(_run(dati["mac"], "notifica"))[:200])
    nw = _run(dati["windows"], "notifica")
    prova("[windows] notifica: PowerShell senza moduli esterni",
          len(nw) == 1 and nw[0][0] == "powershell" and "NotifyIcon" in nw[0][-1]
          and "Ciao ''mondo''" in nw[0][-1], str(nw)[:200])
    prova("[linux] notifica: notify-send (con `--` prima del testo)",
          _run(dati["linux"], "notifica") == [["notify-send", "--", "Plancia", testo_notifica]])

    # ---- voce
    prova("[mac] voce: say e afplay, gli stessi argv di sempre",
          _run(dati["mac"], "voce_sintesi") == [
              ["say", "-v", "?"],
              ["say", "-v", "Alex", "-r", "185", "-o", "<CASA>/o.wav", "--data-format=LEI16@22050",
               "Ciao mondo"]]
          and _popen(dati["mac"], "voce_riproduci") == [["afplay", "<CASA>/o.wav"]]
          and _run(dati["mac"], "voci_sistema") == [["say", "-v", "?"]],
          str(_run(dati["mac"], "voce_sintesi")))
    vw = _run(dati["windows"], "voce_sintesi")
    prova("[windows] voce: PowerShell System.Speech verso un wav, poi SoundPlayer; niente say ne' afplay",
          len(vw) == 1 and vw[0][0] == "powershell" and "SpeechSynthesizer" in vw[0][-1]
          and "SetOutputToWaveFile('<CASA>/o.wav')" in vw[0][-1]
          and len(_popen(dati["windows"], "voce_riproduci")) == 1
          and "SoundPlayer" in _popen(dati["windows"], "voce_riproduci")[0][-1]
          # le voci di sistema ora si elencano anche fuori dal Mac: un PowerShell con
          # GetInstalledVoices (era: nessun comando e l'elenco vuoto)
          and len(_run(dati["windows"], "voci_sistema")) == 1
          and _run(dati["windows"], "voci_sistema")[0][0] == "powershell"
          and "GetInstalledVoices" in _run(dati["windows"], "voci_sistema")[0][-1], str(vw)[:200])
    prova("[linux] voce: espeak-ng verso un wav, poi paplay; niente say ne' afplay",
          _run(dati["linux"], "voce_sintesi") == [
              ["espeak-ng", "-v", "it", "-s", "185", "-w", "<CASA>/o.wav", "--", "Ciao mondo"]]
          and _popen(dati["linux"], "voce_riproduci") == [["paplay", "<CASA>/o.wav"]]
          # `espeak-ng --voices` per l'elenco delle voci (era: nessun comando)
          and _run(dati["linux"], "voci_sistema") == [["espeak-ng", "--voices"]])

    # ---- PowerShell e gli altri processi di contorno non ereditano lo stdin del server MCP
    ps = [c for k, v in dati["windows"].items() if isinstance(v, dict) for c in v.get("comandi", [])
          if (c.get("run") or c.get("popen") or [""])[0] in ("powershell", "pwsh")]
    prova("[windows] ogni PowerShell (voce, riproduzione, notifica) parte con stdin=DEVNULL: quello del "
          "processo e' il canale JSON-RPC di Claude Code, e Windows PowerShell 5.1 lo legge finche' non si chiude",
          len(ps) >= 3 and all(c.get("stdin") == "devnull" for c in ps),
          str([(c.get("run") or c.get("popen"))[0] + ":" + str(c.get("stdin")) for c in ps]))
    def _e_contorno(c):
        a = c.get("run") or c.get("popen") or [""]
        return a[0] in ("afplay", "paplay", "notify-send") or (
            a[0] == "osascript" and "display notification" in " ".join(a))

    contorno = [c for p in ("mac", "linux") for v in dati[p].values() if isinstance(v, dict)
                for c in v.get("comandi", []) if _e_contorno(c)]
    prova("[mac] [linux] la riproduzione e la notifica partono con stdin=DEVNULL anche fuori da Windows",
          len(contorno) >= 3 and all(c.get("stdin") == "devnull" for c in contorno),
          str(contorno)[:300])
    solo_spd = _figlio_lancia("linux", "solo-spd-say")
    prova("[linux] spd-say (in attesa, e staccato) parte con stdin chiuso",
          [c.get("stdin") for c in _comandi(solo_spd, "voce_parla")] == ["devnull"]
          and [c.get("stdin") for c in _comandi(solo_spd, "voce_parla_senza_attendere")] == ["devnull"],
          str(_comandi(solo_spd, "voce_parla"))[:300])

    # ---- doctor
    dm, dw, dl = (" | ".join(map(str, _r(dati[p], "doctor") or [])) for p in ("mac", "windows", "linux"))
    prova("doctor: launchd e l'app macOS su mac; Task Scheduler / systemd e 'dashboard nel browser' altrove",
          "avvio automatico (launchd)" in dm and "app macOS" in dm
          and "avvio automatico (Task Scheduler)" in dw and "launchd" not in dw and "Plancia.app" not in dw
          and "solo macOS" in dw
          and "avvio automatico (systemd)" in dl and "launchd" not in dl and "Plancia.app" not in dl,
          (dm + dw + dl)[:300])


# --------------------------------------------------------------------------
# quando manca qualcosa: la strada di ripiego, e la voce che lo dice
# --------------------------------------------------------------------------

def _prove_ripiego_e_strumenti_assenti(prova):
    negato = {p: _figlio_lancia(p, "avvio-negato") for p in ("windows", "linux")}
    prova("[windows] schtasks negato: ripiego .cmd nella cartella Esecuzione automatica, e off lo toglie",
          '@echo off\r\nstart "" "<PY>" -X utf8 "<RADICE>/bin/plancia" serve\r\n'
          == _file(negato["windows"], "FILE_INSTALLATI").get(
              "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/plancia.cmd")
          and "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/plancia.cmd"
          not in _file(negato["windows"], "FILE_DOPO")
          and _r(negato["windows"], "installati")[0] is True
          and "cartella Esecuzione automatica" in str(_r(negato["windows"], "autostart_on")),
          str(_r(negato["windows"], "autostart_on")))
    prova("[windows] schtasks negato sul riepilogo: lo dice, non finge",
          "non attivato" in str(_r(negato["windows"], "recap_on")), str(_r(negato["windows"], "recap_on")))
    prova("[linux] systemctl enable negato: si toglie l'unita' e si ripiega su ~/.config/autostart, e off lo toglie",
          'Exec="<PY>" "<RADICE>/bin/plancia" serve'
          in _file(negato["linux"], "FILE_INSTALLATI").get(".config/autostart/plancia.desktop", "")
          and ".config/systemd/user/plancia.service" not in _file(negato["linux"], "FILE_INSTALLATI")
          and ".config/autostart/plancia.desktop" not in _file(negato["linux"], "FILE_DOPO"),
          str(sorted(_file(negato["linux"], "FILE_INSTALLATI"))))

    vuoto = {p: _figlio_lancia(p, "senza-strumenti") for p in PIATTAFORME}
    prova("[linux] senza systemd: l'avvio va dritto al .desktop; il riepilogo dice cosa serve (cron)",
          'Exec="<PY>"' in _file(vuoto["linux"], "FILE_INSTALLATI").get(".config/autostart/plancia.desktop", "")
          and not [c for c in _run(vuoto["linux"], "autostart_on")]
          and "systemd --user" in str(_r(vuoto["linux"], "recap_on"))
          and "cron" in str(_r(vuoto["linux"], "recap_on")),
          str(_r(vuoto["linux"], "recap_on")))
    prova("[linux] nessun terminale: riprendi.apri lo dice nell'esito e non lancia niente",
          "nessun terminale" in str((_r(vuoto["linux"], "apri") or {}).get("errore"))
          and not _run(vuoto["linux"], "apri") and not _popen(vuoto["linux"], "apri"),
          str(_r(vuoto["linux"], "apri"))[:200])
    prova("senza uno strumento per gli appunti: False, e nessun comando lanciato (linux); "
          "su windows e mac il comando di sistema c'e' sempre",
          _r(vuoto["linux"], "appunti") is False and not _comandi(vuoto["linux"], "appunti")
          and _comandi(vuoto["windows"], "appunti")
          == [{"run": ["clip"], "input": "UTF16LE-BOM:riprendi il task 3"}]
          and _comandi(vuoto["mac"], "appunti") == [{"run": ["pbcopy"], "input": "riprendi il task 3"}])
    prova("senza notify-send ne' PowerShell la notifica e' silenziosa: nessun comando, nessun errore",
          not _run(vuoto["linux"], "notifica") and not _run(vuoto["windows"], "notifica")
          and not str(_r(vuoto["linux"], "notifica")).startswith("ECCEZIONE")
          and not str(_r(vuoto["windows"], "notifica")).startswith("ECCEZIONE"))
    prova("[linux] senza motore vocale: la sintesi lo dice (NessunMotoreVoce) e parla() non solleva",
          "NessunMotoreVoce" in str(_r(vuoto["linux"], "voce_sintesi"))
          and "espeak-ng" in str(_r(vuoto["linux"], "voce_sintesi"))
          and (_r(vuoto["linux"], "voce_parla") or {}).get("motore") == "nessuno"
          and "espeak-ng" in str((_r(vuoto["linux"], "voce_parla") or {}).get("errore"))
          and (_r(vuoto["linux"], "voce_parla") or {}).get("file") is None
          and not _run(vuoto["linux"], "voce_parla") and not _popen(vuoto["linux"], "voce_parla"),
          str(_r(vuoto["linux"], "voce_parla")))
    prova("[windows] senza PowerShell: stessa cosa, la voce dice che manca il motore",
          "NessunMotoreVoce" in str(_r(vuoto["windows"], "voce_sintesi"))
          and (_r(vuoto["windows"], "voce_parla") or {}).get("motore") == "nessuno",
          str(_r(vuoto["windows"], "voce_parla")))
    prova("[windows] senza PowerShell il resto di Plancia continua (doctor e installazione senza eccezioni)",
          not str(_r(vuoto["windows"], "doctor")).startswith("ECCEZIONE")
          and not str(_r(vuoto["windows"], "install_hooks")).startswith("ECCEZIONE"))
    prova("[mac] senza strumenti in PATH i comandi di sistema sono gli stessi: launchctl, osascript, pbcopy",
          _run(vuoto["mac"], "autostart_on")[0][0] == "launchctl"
          and _run(vuoto["mac"], "notifica")[0][0] == "osascript"
          and _run(vuoto["mac"], "apri")[0][0] == "osascript")

    solo = _figlio_lancia("linux", "solo-spd-say")
    prova("[linux] con solo spd-say: dice la frase (con -w se si aspetta, staccato se no), nessun file",
          _run(solo, "voce_parla") == [["spd-say", "-w", "-l", "it", "--", "Ciao mondo"]]
          and (_r(solo, "voce_parla") or {}).get("motore") == "spd-say"
          and _popen(solo, "voce_parla_senza_attendere") == [["spd-say", "-l", "it", "--", "Ciao mondo"]],
          str(_r(solo, "voce_parla")))


# --------------------------------------------------------------------------
# quando il programma non c'e', esce con un errore o non risponde
# --------------------------------------------------------------------------

def _prove_quando_il_comando_fallisce(prova):
    """Un programma che manca (`FileNotFoundError`), che esce con un errore
    (`CalledProcessError`) o che non risponde (`TimeoutExpired`) non deve
    fermare quello che c'e' intorno, fuori da macOS; su macOS l'errore di `say`
    esce come prima."""
    rotto = {p: _figlio_lancia(p, "esecutore-rotto") for p in PIATTAFORME}
    for p in PIATTAFORME:
        prova("[%s] un esecutore che alza FileNotFoundError: avvio automatico, riepilogo e notifica "
              "non sollevano, l'avvio dice che non e' partito" % p,
              all(not str(_r(rotto[p], k)).startswith("ECCEZIONE")
                  for k in ("autostart_on", "recap_on", "notifica", "autostart_off", "recap_off"))
              and ("launchctl ha risposto" in str(_r(rotto[p], "autostart_on")) if p == "mac"
                   else "avvio automatico" in str(_r(rotto[p], "autostart_on"))),
              str([(k, _r(rotto[p], k)) for k in ("autostart_on", "recap_on", "notifica")])[:400])
    prova("[windows] [linux] senza schtasks o systemctl l'avvio ripiega comunque sul file (.cmd, .desktop)",
          "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/plancia.cmd"
          in _file(rotto["windows"], "FILE_INSTALLATI")
          and ".config/autostart/plancia.desktop" in _file(rotto["linux"], "FILE_INSTALLATI"),
          str(sorted(_file(rotto["windows"], "FILE_INSTALLATI"))))
    prova("[mac] `say` che non c'e': parla() solleva ancora, come prima; fuori da macOS no, "
          "torna motore 'nessuno' con l'errore",
          str(_r(rotto["mac"], "voce_parla")).startswith("ECCEZIONE FileNotFoundError")
          and all((_r(rotto[p], "voce_parla") or {}).get("motore") == "nessuno"
                  and (_r(rotto[p], "voce_parla") or {}).get("file") is None
                  and (_r(rotto[p], "voce_parla") or {}).get("errore")
                  for p in ("windows", "linux")),
          str([_r(rotto[p], "voce_parla") for p in PIATTAFORME])[:400])
    for variante, cosa in (("voce-rotta", "esce con un errore (CalledProcessError)"),
                           ("voce-lenta", "non risponde (TimeoutExpired)")):
        d = {p: _figlio_lancia(p, variante) for p in ("windows", "linux")}
        prova("[windows] [linux] il motore vocale c'e' ma %s: parla() non solleva, torna motore 'nessuno' "
              "con l'errore, e la riproduzione non parte" % cosa,
              all((_r(d[p], "voce_parla") or {}).get("motore") == "nessuno"
                  and "la voce non ha funzionato" in str((_r(d[p], "voce_parla") or {}).get("errore"))
                  and not _popen(d[p], "voce_parla") for p in d),
              str([_r(d[p], "voce_parla") for p in d])[:400])


def _prove_il_figlio_su_windows(prova):
    """Le prove devono dare lo stesso esito su un host Windows: la ripulitura
    dell'uscita del figlio riconosce i percorsi anche con le barre raddoppiate di
    TOML, e `os.getuid` (che su Windows non c'e') non decide niente."""
    sost = [(r"C:\Users\u\casa", "<CASA>"), (r"C:\src\plancia", "<RADICE>"),
            (r"C:\Py 3\python.exe", "<PY>")]
    toml = ('model = "x"\n\n[mcp_servers.plancia]\ncommand = "C:\\\\Py 3\\\\python.exe"\n'
            'args = ["-X", "utf8", "C:\\\\src\\\\plancia\\\\bin\\\\plancia-mcp", "--agente", "codex"]\n'
            'startup_timeout_sec = 30\n')
    prova("l'uscita del figlio su un host Windows: il config.toml di Codex (barre raddoppiate) si riduce "
          "a <PY> e <RADICE>/bin/plancia-mcp come sui sistemi POSIX",
          pulisci(toml_normale(toml), sost)
          == ('model = "x"\n\n[mcp_servers.plancia]\ncommand = "<PY>"\n'
              'args = ["-X", "utf8", "<RADICE>/bin/plancia-mcp", "--agente", "codex"]\n'
              'startup_timeout_sec = 30\n'),
          pulisci(toml_normale(toml), sost))
    prova("l'uscita del figlio: le altre stringhe con percorsi Windows si riducono uguale, anche in liste e dizionari",
          pulisci({"a": [r"C:\Py 3\python.exe -X utf8 C:\src\plancia\bin\plancia"]}, sost)
          == {"a": ["<PY> -X utf8 <RADICE>/bin/plancia"]})
    figlio = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    prova("il figlio fissa os.getuid senza condizioni (su Windows non esiste, e `gui/None` non e' un dominio)",
          "if hasattr(os, \"getuid\"):\n        os.getuid" not in Path(__file__).read_text(encoding="utf-8")
          and any(isinstance(n, ast.Assign) and ast.dump(n.targets[0]).startswith("Attribute(value=Name(id='os'")
                  and getattr(n.targets[0], "attr", "") == "getuid" for n in ast.walk(figlio)))


def _prove_mcp_in_utf8(prova, pf):
    """Il server MCP lanciato con l'argv che Plancia registra su Windows riceve un
    titolo con gli accenti e lo rilegge identico dal db. Su Windows lo stdio con le
    pipe e' in cp1252, non in UTF-8; qui lo si imita con una locale ASCII (LC_ALL=C,
    senza modalita' UTF-8): una simulazione, non Windows, ma il difetto e' lo stesso,
    testo non ASCII che arriva o esce da uno stdio che non e' UTF-8."""
    import sqlite3
    titolo = "perch\u00e9 \u00e8 cos\u00ec \u2192 fatto"
    script = RADICE / "bin" / "plancia-mcp"

    def lancia(argv):
        casa = Path(tempfile.mkdtemp(prefix="plancia-utf8-"))
        amb = {k: v for k, v in os.environ.items() if k not in (
            "PYTHONIOENCODING", "PYTHONUTF8", "LC_ALL", "LANG", "PYTHONCOERCECLOCALE")}
        amb.update(PLANCIA_HOME=str(casa / "dati"), HOME=str(casa), USERPROFILE=str(casa),
                   LC_ALL="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0")
        richiesta = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "plancia_task_add", "arguments": {"title": titolo, "project": "x"}}},
            ensure_ascii=False)
        try:
            res = subprocess.run(argv, input=(richiesta + "\n").encode("utf-8"), capture_output=True,
                                 env=amb, timeout=90)
            try:
                db = sqlite3.connect(str(casa / "dati" / "plancia.db"))
                titoli = [r[0] for r in db.execute("SELECT title FROM tasks")]
                db.close()
            except sqlite3.Error:
                titoli = []
            risposta = res.stdout.decode("utf-8", errors="replace")
            return titoli, risposta
        except Exception as exc:  # noqa: BLE001
            return [], "ERRORE %s" % exc
        finally:
            import shutil
            shutil.rmtree(casa, ignore_errors=True)

    registrato = pf.argv_script(script, sys.executable, "windows")
    titoli, risposta = lancia(registrato)
    prova("MCP lanciato con l'argv registrato su Windows ([python, -X, utf8, script]): il titolo con "
          "accenti e la freccia si rilegge identico dal db, e la risposta arriva",
          registrato[1:3] == ["-X", "utf8"] and titoli == [titolo] and titolo in risposta
          and '"isError": false' in risposta, "%r %s" % (titoli, risposta[:200]))
    titoli0, risposta0 = lancia([sys.executable, str(script)])
    prova("controllo della simulazione: lo stesso server SENZA -X utf8 su uno stdio non-UTF-8 il titolo "
          "non lo rilegge identico (se no la prova sopra non prova niente); da Python 3.15 UTF-8 e' il predefinito",
          sys.version_info >= (3, 15) or titoli0 != [titolo], "%r %s" % (titoli0, risposta0[:200]))


def _prove_simulazione_windows(prova):
    """Le prove pure girano anche con `Path` di Windows (`PureWindowsPath`, barre
    rovesciate) e senza `os.getuid`: e' quello che vede un host Windows, dove la CI
    le lancia e non ammette rossi. Si fa in un processo a parte, perche' il
    cambio di `Path` vale per tutto quello che si importa dopo."""
    try:
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--simula-windows"],
                             capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL,
                             env={k: v for k, v in os.environ.items() if k != "PLANCIA_PIATTAFORMA"})
        fine = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
        rossi = [r for r in res.stdout.splitlines() if r.startswith("  NO ")]
        ok = res.returncode == 0 and fine.endswith(" 0 fallite")
        dettaglio = "\n".join(rossi[:6]) or (res.stderr[-400:] if not ok else "")
    except Exception as exc:  # noqa: BLE001
        ok, dettaglio = False, str(exc)
    prova("simulazione Windows: le prove dei costruttori passano con Path di Windows e senza os.getuid",
          ok, dettaglio)


# --------------------------------------------------------------------------
# i file del lotto: CI, README, shim, privacy, python 3.9
# --------------------------------------------------------------------------

def _leggi(rel):
    """Il testo di un file del repo, o "" se non c'e' (una prova rossa, non un'eccezione)."""
    try:
        return (RADICE / rel).read_text(encoding="utf-8")
    except OSError:
        return ""


def _prove_file_del_lotto(prova):
    yml = _leggi(".github/workflows/prova.yml")
    struttura = None
    try:
        import yaml
        struttura = yaml.safe_load(yml)
    except Exception:  # noqa: BLE001 - senza pyyaml si guarda il testo
        struttura = None
    if struttura:
        job = struttura.get("jobs", {}).get("prova", {})
        matrice = job.get("strategy", {}).get("matrix", {})
        ok_matrice = (matrice.get("os") == ["ubuntu-latest", "windows-latest", "macos-latest"]
                      and matrice.get("python") == ["3.9", "3.12"]
                      and job.get("strategy", {}).get("fail-fast") is False
                      and "matrix.os" in str(job.get("runs-on")))
    else:
        ok_matrice = bool(re.search(r"os:\s*\[ubuntu-latest,\s*windows-latest,\s*macos-latest\]", yml)
                          and re.search(r"python:\s*\['3\.9',\s*'3\.12'\]", yml))
    prova("CI: matrice os [ubuntu, windows, macos] x python [3.9, 3.12], senza fail-fast", ok_matrice)
    if struttura:
        passi = struttura.get("jobs", {}).get("prova", {}).get("steps", [])
        non_bloccano = [s for s in passi if s.get("continue-on-error")]
        piatt_passi = [s for s in passi if "piattaforma.py" in str(s.get("run"))]
        ok_ci = (
            # la prova di piattaforma gira su tutti e tre e non ammette rossi
            len(piatt_passi) == 2 and not any(s.get("continue-on-error") for s in piatt_passi)
            and {s["run"] for s in piatt_passi} == {"python3 tools/prove/piattaforma.py",
                                                    "python tools/prove/piattaforma.py"}
            # su windows `python`, mai `python3`
            and all("python3" not in s["run"] for s in passi
                    if "Windows" in str(s.get("name")) and "run" in s)
            # quello che non blocca e' solo la suite e il front, e solo su windows
            and sorted(s["run"] for s in non_bloccano) == ["python tools/prova-front.py",
                                                           "python tools/prova.py"]
            and all(s.get("if") == "runner.os == 'Windows'" for s in non_bloccano))
    else:
        ok_ci = ("python tools/prove/piattaforma.py" in yml and "python3 tools/prove/piattaforma.py" in yml
                 and yml.count("continue-on-error: true") == 2)
    prova("CI: su windows si lancia `python`; la prova di piattaforma non ammette rossi, "
          "la suite intera e il front su windows non bloccano", ok_ci)
    prova("CI: perche' non bloccano lo scrive (prove SOLO POSIX da portare)",
          "SOLO POSIX" in yml and "shebang" in yml)

    for nome, titolo in (("README.md", "## Windows and Linux"), ("README.it.md", "## Windows e Linux")):
        testo = _leggi(nome)
        sezione = testo.split(titolo, 1)[1].split("\n## ", 1)[0] if titolo in testo else ""
        prova("%s: sezione '%s' con i comandi esatti" % (nome, titolo.lstrip("# ")),
              "git clone https://github.com/nerln/plancia.git" in sezione
              and "python bin/plancia install" in sezione
              and "python bin/plancia serve --open" in sezione
              and "plancia.cmd" in sezione and "macOS" in sezione,
              sezione[:200])
        prova("%s: la sezione non usa em dash e non nomina percorsi di nessuna macchina" % nome,
              "\u2014" not in sezione and "/Users/" not in sezione)

    cmd = _leggi("bin/plancia.cmd")
    prova("bin/plancia.cmd: lancia bin/plancia con python (o py -3) e ne passa gli argomenti",
          '"%~dp0plancia" %*' in cmd and "py -3" in cmd and cmd.lstrip().startswith("@echo off"))

    # il repo e' pubblico: niente nomi veri ne' percorsi di questa macchina nei file del lotto
    nuovi = ("plancia/piattaforma.py", "tools/prove/piattaforma.py", "bin/plancia.cmd",
             ".github/workflows/prova.yml")
    vecchi = ("plancia/setup_claude.py", "plancia/codex.py", "plancia/voice.py",
              "plancia/riprendi.py", "plancia/jarvis.py", "plancia/cli.py")
    trovati = []
    for rel in nuovi + vecchi:
        testo = _leggi(rel).lower()
        # il percorso di questa macchina non deve stare in nessuno; i nomi veri
        # nei file scritti da zero (nei vecchi c'e' gia' quel che c'e')
        proibiti = [str(Path.home())] + (["ner" + "elli", "eugen" + "io"] if rel in nuovi else [])
        trovati += [rel for p in proibiti if p.lower() in testo and rel not in trovati]
    prova("privacy: nessun nome vero ne' percorso di questa macchina nei file del lotto",
          not trovati, str(trovati))

    # python 3.9: la grammatica, e niente dei metodi piu' recenti
    guai = []
    for rel in ("plancia/piattaforma.py", "plancia/setup_claude.py", "plancia/codex.py",
                "plancia/voice.py", "plancia/riprendi.py", "plancia/jarvis.py", "plancia/cli.py",
                "tools/prove/piattaforma.py"):
        testo = _leggi(rel)
        try:
            albero = ast.parse(testo, feature_version=(3, 9))
        except SyntaxError as exc:
            guai.append("%s: %s" % (rel, exc))
            continue
        # (str.removeprefix e removesuffix ci sono dalla 3.9: non sono un guaio)
        if re.search(r"\bmatch\s+\w+:\s*$", testo, re.M):
            guai.append(rel + ": match")
        for nodo in ast.walk(albero):
            for ann in (getattr(nodo, "annotation", None), getattr(nodo, "returns", None)):
                if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
                    guai.append(rel + ": annotazione X | Y")
    prova("python 3.9: grammatica ammessa, niente match o annotazioni X | Y", not guai, str(guai))


def _simula_windows() -> int:
    """`--simula-windows`: le prove pure con `Path` di Windows e senza `os.getuid`."""
    import pathlib
    pathlib.Path = pathlib.PureWindowsPath
    globals()["Path"] = pathlib.PureWindowsPath
    if hasattr(os, "getuid"):
        del os.getuid
    from plancia import piattaforma as pf
    assert pf.Path is pathlib.PureWindowsPath
    passate, fallite = [0], []

    def prova(nome, cond, dettaglio=""):
        if cond:
            passate[0] += 1
        else:
            fallite.append(nome)
            print("  NO   %s %s" % (nome, dettaglio))

    _prove_nome(prova, pf)
    _prove_costruttori_puri(prova, pf)
    print("\n%d passate, %d fallite" % (passate[0], len(fallite)))
    return 1 if fallite else 0


if __name__ == "__main__":
    if "--figlio" in sys.argv:
        _figlio()
        sys.exit(0)
    if "--simula-windows" in sys.argv:
        sys.exit(_simula_windows())
    # da soli: l'archivio vero non si tocca, si lavora in uno finto
    if "PLANCIA_HOME" not in os.environ:
        os.environ["PLANCIA_HOME"] = tempfile.mkdtemp(prefix="plancia-prova-piatt-")
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
