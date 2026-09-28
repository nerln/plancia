"""Tutto quello che cambia da un sistema operativo all'altro, in un posto solo.

Il cuore di Plancia e' python e basta e gira ovunque. Quello che lo legge al
Mac sono poche cose di contorno: aprire un Terminale, mettere del testo negli
appunti, dire una frase, mostrare una notifica, far ripartire il server a ogni
accesso, registrare un comando. Ognuna si fa in un modo diverso su macOS,
Windows e Linux, e qui c'e' la ricetta per tutte e tre.

Due livelli, tenuti separati apposta:

- le funzioni che COSTRUISCONO (`comando_terminale`, `comando_appunti`,
  `comando_sintesi`, `comando_notifica`, `piano_server`, ...) sono pure: date
  le stesse entrate tornano lo stesso argv o lo stesso testo di file, non
  toccano il disco e non lanciano niente. Sono quelle che le prove guardano
  su tutte e tre le piattaforme, anche quelle su cui non si sta girando;
- `esegui` e `cerca` sono l'unico punto in cui si lancia un processo o si
  cerca un programma nel PATH. Chi usa questo modulo passa da qui, e le prove
  li sostituiscono: nessuna prova lancia mai `launchctl`, `schtasks`,
  `systemctl`, `osascript`, `claude` o `codex` veri.

`nome()` dice dove si e': "mac", "windows" o "linux", da `sys.platform`,
sovrascrivibile con `PLANCIA_PIATTAFORMA` (un valore che non sia uno dei tre
nomi viene ignorato). Su macOS niente di quello che c'era prima cambia di un
byte: gli argv, i plist e i testi sono quelli di sempre, e le prove lo
confrontano con i valori misurati sulla versione precedente.

Solo libreria standard, python 3.9.
"""

import base64
import ntpath
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

MAC = "mac"
WINDOWS = "windows"
LINUX = "linux"

# Le tre voci di una lingua per ciascun motore che vuole un codice locale.
_CULTURE = {"it": "it-IT", "en": "en-US", "es": "es-ES", "fr": "fr-FR",
            "de": "de-DE", "pt": "pt-BR"}

# I nomi con cui il Task Scheduler di Windows conosce le due attivita'.
TASK_SERVER = "Plancia server"
TASK_RIEPILOGO = "Plancia riepilogo"

LABEL_SERVER = "com.plancia.server"
LABEL_RIEPILOGO = "com.plancia.recap"


def nome() -> str:
    forzata = os.environ.get("PLANCIA_PIATTAFORMA", "").strip().lower()
    if forzata in (MAC, WINDOWS, LINUX):
        return forzata
    p = sys.platform
    if p == "darwin":
        return MAC
    if p.startswith("win") or p in ("cygwin", "msys"):
        return WINDOWS
    return LINUX


def _p(piatt):
    return piatt or nome()


# --------------------------------------------------------------------------
# l'unico punto in cui si lancia qualcosa
# --------------------------------------------------------------------------

def cerca(programma):
    """Il percorso di `programma` nel PATH, o None. Sostituibile dalle prove."""
    return shutil.which(programma)


def esegui(argv, **kwargs):
    """`subprocess.run`. Sostituibile dalle prove."""
    return subprocess.run(argv, **kwargs)


def avvia_distaccato(argv, piatt=None):
    """Lancia `argv` staccato da noi e senza aspettarlo: la finestra di un
    terminale resta aperta finche' la chiude chi la usa. Sostituibile dalle
    prove."""
    veri = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
    if _p(piatt) == WINDOWS:
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        veri["creationflags"] = 0x00000008 | 0x00000200
    else:
        veri["start_new_session"] = True
    return subprocess.Popen(argv, **veri)


def _trova(cerca_fn, candidati):
    """Il primo dei `candidati` (lista di argv) il cui programma c'e' nel PATH."""
    trova = cerca_fn or cerca
    for argv in candidati:
        if trova(argv[0]):
            return list(argv)
    return None


# --------------------------------------------------------------------------
# citare
# --------------------------------------------------------------------------

def applescript_quote(testo: str) -> str:
    return '"%s"' % testo.replace("\\", "\\\\").replace('"', '\\"')


def _virgolette(testo) -> str:
    return '"%s"' % testo


def _ps_str(testo: str) -> str:
    """Una stringa tra apici singoli per PowerShell (l'apice si raddoppia)."""
    return "'%s'" % str(testo).replace("'", "''")


def toml_str(testo) -> str:
    """Una stringa TOML di base: la barra rovesciata dei percorsi Windows va
    raddoppiata, o `\\U` diventa una sequenza di escape non valida."""
    return '"%s"' % str(testo).replace("\\", "\\\\").replace('"', '\\"')


def _riga_windows(argv) -> str:
    return subprocess.list2cmdline([str(a) for a in argv])


# --------------------------------------------------------------------------
# registrare i comandi di Plancia (MCP, hook)
# --------------------------------------------------------------------------

def argv_script(script, python=None, piatt=None) -> list:
    """L'argv per lanciare uno script di `bin/`.

    Su macOS e Linux lo script si lancia da solo, ha lo shebang. Su Windows
    uno script senza estensione non si esegue: serve l'interprete davanti.
    """
    if _p(piatt) == WINDOWS:
        return [python or sys.executable, str(script)]
    return [str(script)]


def riga_script(script, python=None, piatt=None) -> str:
    """Come `argv_script`, ma come una riga sola (i settings.json degli hook).

    macOS e Linux: il percorso nudo, com'e' sempre stato. Windows:
    `"<python>" "<script>"`, con le virgolette perche' un percorso di Windows
    ha spesso degli spazi.
    """
    if _p(piatt) == WINDOWS:
        return " ".join(_virgolette(a) for a in argv_script(script, python, piatt))
    return str(script)


def percorso_comando(casa, piatt=None, ambiente=None) -> Path:
    """Dove `plancia install` mette il comando `plancia`.

    macOS e Linux: `~/.local/bin/plancia` (un collegamento simbolico).
    Windows: uno shim `plancia.cmd` in una cartella tutta sua sotto
    `%LOCALAPPDATA%`, cosi' non si sporca il resto di quello che c'e' nel PATH.
    """
    casa = Path(casa)
    if _p(piatt) == WINDOWS:
        amb = os.environ if ambiente is None else ambiente
        base = amb.get("LOCALAPPDATA") or str(casa / "AppData" / "Local")
        return Path(base) / "Plancia" / "bin" / "plancia.cmd"
    return casa / ".local" / "bin" / "plancia"


def shim_windows(python, script) -> str:
    """Il contenuto dello shim `plancia.cmd`."""
    return '@echo off\r\n%s %%*\r\n' % " ".join(
        [_virgolette(python), _virgolette(script)])


def nel_path(cartella, path_var, piatt=None) -> bool:
    """`cartella` e' fra le cartelle di `path_var`? Su Windows le maiuscole e la
    barra finale non contano."""
    voci = [v for v in (path_var or "").split(";" if _p(piatt) == WINDOWS else ":")]
    if _p(piatt) == WINDOWS:
        norma = lambda s: s.replace("/", "\\").rstrip("\\").lower()
        return norma(str(cartella)) in [norma(v) for v in voci]
    return str(cartella) in voci


def blocco_mcp_toml(argv_mcp, args_extra) -> str:
    """Il blocco `[mcp_servers.plancia]` per il config.toml di Codex.

    Su macOS e Linux `argv_mcp` e' il solo script e il risultato e' quello di
    sempre; su Windows e' `[python, script]`, e l'interprete resta il
    `command` mentre lo script passa in testa agli `args`.
    """
    comando, resto = argv_mcp[0], list(argv_mcp[1:]) + list(args_extra)
    return ("\n[mcp_servers.plancia]\n"
            "command = %s\n"
            "args = [%s]\n"
            "startup_timeout_sec = 30\n") % (
                toml_str(comando), ", ".join(toml_str(a) for a in resto))


# --------------------------------------------------------------------------
# un Terminale visibile, in una cartella, con un comando
# --------------------------------------------------------------------------

def riga_shell(cwd, argv, piatt=None) -> str:
    """`cd <cwd> && <comando>` come lo scriverebbe la shell del sistema."""
    if _p(piatt) == WINDOWS:
        return "cd /d %s && %s" % (_virgolette(cwd), _riga_windows(argv))
    return "cd %s && %s" % (shlex.quote(cwd), shlex.join(argv))


def comando_terminale(cwd, argv, piatt=None, cerca_fn=None):
    """L'argv che apre una finestra di terminale in `cwd` con `argv` dentro, o
    None se su questo sistema non si trova nessun terminale.

    `PLANCIA_TERMINALE` (un lanciatore alternativo, usato dalle prove) lo
    gestisce chi chiama: qui c'e' solo quello che si fa senza.
    """
    piatt = _p(piatt)
    riga = riga_shell(cwd, argv, piatt)
    if piatt == MAC:
        return ["osascript", "-e",
                "tell application \"Terminal\" to do script %s" % applescript_quote(riga)]
    if piatt == WINDOWS:
        trova = cerca_fn or cerca
        if trova("wt") or trova("wt.exe"):
            return ["wt.exe", "-d", str(cwd)] + [str(a) for a in argv]
        return ["cmd", "/c", "start", "", "/D", str(cwd), "cmd", "/k"] + [str(a) for a in argv]
    scelta = _trova(cerca_fn, [
        ["x-terminal-emulator"], ["gnome-terminal"], ["konsole"], ["xterm"]])
    if scelta is None:
        return None
    if scelta[0] == "x-terminal-emulator":
        return ["x-terminal-emulator", "-e", "sh", "-c", riga]
    if scelta[0] == "gnome-terminal":
        return ["gnome-terminal", "--working-directory=%s" % cwd, "--"] + [str(a) for a in argv]
    if scelta[0] == "konsole":
        return ["konsole", "--workdir", str(cwd), "-e"] + [str(a) for a in argv]
    return ["xterm", "-e", "sh", "-c", riga]


# --------------------------------------------------------------------------
# appunti
# --------------------------------------------------------------------------

def comando_appunti(piatt=None, cerca_fn=None):
    """L'argv che legge da stdin e mette il testo negli appunti, o None.

    `PLANCIA_CLIPBOARD` vince su tutto: e' come le prove evitano di toccare gli
    appunti veri di chi le lancia.
    """
    sostituto = os.environ.get("PLANCIA_CLIPBOARD")
    if sostituto:
        return sostituto.split()
    piatt = _p(piatt)
    if piatt == MAC:
        return ["pbcopy"]
    if piatt == WINDOWS:
        return ["clip"]
    return _trova(cerca_fn, [["wl-copy"], ["xclip", "-selection", "clipboard"],
                             ["xsel", "-b"]])


# --------------------------------------------------------------------------
# voce
# --------------------------------------------------------------------------

def _powershell(cerca_fn=None):
    trova = cerca_fn or cerca
    for exe in ("powershell", "pwsh"):
        if trova(exe):
            return exe
    return None


def _ps_comando(exe, script) -> list:
    return [exe, "-NoProfile", "-NonInteractive", "-Command", script]


def voce_sistema_presente(piatt=None) -> bool:
    """Le voci di sistema si elencano con `say -v ?`: solo su macOS."""
    return _p(piatt) == MAC


def comando_sintesi(testo, lang, voce, velocita, out, piatt=None, cerca_fn=None):
    """L'argv che scrive in `out` (un wav) il `testo` detto dalla voce di sistema,
    o None se su questa macchina non c'e' un motore.

    `velocita` e' in parole al minuto, come la vuole `say`. Windows usa il
    sintetizzatore che c'e' gia' (System.Speech, via PowerShell), Linux
    `espeak-ng` o `espeak`. `spd-say` non sa scrivere un file, quindi si usa
    solo per dire una frase e basta (`comando_dire`).
    """
    piatt = _p(piatt)
    try:
        wpm = int(velocita)
    except (TypeError, ValueError):
        wpm = 185
    if piatt == MAC:
        return ["say", "-v", voce, "-r", str(velocita), "-o", str(out),
                "--data-format=LEI16@22050", testo]
    if piatt == WINDOWS:
        exe = _powershell(cerca_fn)
        if exe is None:
            return None
        b64 = base64.b64encode(testo.encode("utf-8")).decode("ascii")
        rate = max(-10, min(10, int(round((wpm - 170) / 15.0))))
        passi = [
            "$ErrorActionPreference = 'Stop'",
            "Add-Type -AssemblyName System.Speech",
            "$t = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String(%s))"
            % _ps_str(b64),
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
            "try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet, "
            "[System.Speech.Synthesis.VoiceAge]::NotSet, 0, "
            "[System.Globalization.CultureInfo]%s) } catch {}" % _ps_str(_CULTURE.get(lang, "en-US")),
        ]
        if voce:
            passi.append("try { $s.SelectVoice(%s) } catch {}" % _ps_str(voce))
        passi += ["$s.Rate = %d" % rate,
                  "$s.SetOutputToWaveFile(%s)" % _ps_str(out),
                  "$s.Speak($t)",
                  "$s.Dispose()"]
        return _ps_comando(exe, "; ".join(passi))
    for motore in ("espeak-ng", "espeak"):
        if (cerca_fn or cerca)(motore):
            return [motore, "-v", lang, "-s", str(wpm), "-w", str(out), testo]
    return None


def comando_dire(testo, lang, attendi=True, piatt=None, cerca_fn=None):
    """L'argv che dice `testo` ad alta voce senza passare da un file (solo Linux,
    con `spd-say`), o None. Serve quando manca un motore che sappia scrivere un
    wav ma c'e' Speech Dispatcher. Con `attendi` il comando torna a frase finita."""
    if _p(piatt) == LINUX and (cerca_fn or cerca)("spd-say"):
        return ["spd-say"] + (["-w"] if attendi else []) + ["-l", lang, testo]
    return None


def comando_riproduzione(percorso, piatt=None, cerca_fn=None):
    """L'argv che riproduce un file audio, o None se non c'e' un lettore."""
    piatt = _p(piatt)
    if piatt == MAC:
        return ["afplay", str(percorso)]
    if piatt == WINDOWS:
        exe = _powershell(cerca_fn)
        if exe is None:
            return None
        return _ps_comando(
            exe, "(New-Object System.Media.SoundPlayer %s).PlaySync()" % _ps_str(percorso))
    scelta = _trova(cerca_fn, [["paplay"], ["aplay", "-q"], ["pw-play"],
                               ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
                               ["play", "-q"]])
    return scelta + [str(percorso)] if scelta else None


def motore_voce_assente(piatt=None) -> str:
    """La frase che dice, chiaro, perche' non si sente niente e cosa fare."""
    piatt = _p(piatt)
    if piatt == WINDOWS:
        return "nessun motore vocale: serve PowerShell con System.Speech"
    if piatt == LINUX:
        return ("nessun motore vocale di sistema: installa espeak-ng "
                "(o espeak) e un lettore audio come paplay o aplay")
    return "nessun motore vocale di sistema"


# --------------------------------------------------------------------------
# notifica
# --------------------------------------------------------------------------

def comando_notifica(titolo, testo, piatt=None, cerca_fn=None):
    """L'argv che mostra una notifica di sistema, o None se non si puo' (su
    Windows e Linux niente notifica e' meglio di un errore)."""
    piatt = _p(piatt)
    if piatt == MAC:
        return ["osascript", "-e",
                f'display notification "{testo}" with title "{titolo}"']
    if piatt == WINDOWS:
        exe = _powershell(cerca_fn)
        if exe is None:
            return None
        passi = [
            "Add-Type -AssemblyName System.Windows.Forms",
            "Add-Type -AssemblyName System.Drawing",
            "$n = New-Object System.Windows.Forms.NotifyIcon",
            "$n.Icon = [System.Drawing.SystemIcons]::Information",
            "$n.Visible = $true",
            "$n.ShowBalloonTip(10000, %s, %s, [System.Windows.Forms.ToolTipIcon]::Info)"
            % (_ps_str(titolo), _ps_str(testo)),
            "Start-Sleep -Seconds 6",
            "$n.Dispose()",
        ]
        return _ps_comando(exe, "; ".join(passi))
    if (cerca_fn or cerca)("notify-send"):
        return ["notify-send", titolo, testo]
    return None


# --------------------------------------------------------------------------
# avvio automatico e riepilogo giornaliero
# --------------------------------------------------------------------------
#
# Ogni `piano_*` e' un dizionario, mai un'azione:
#   nome      come si chiama il meccanismo ("launchd", "Task Scheduler", ...)
#   file      [(percorso, testo)] da scrivere prima di tutto
#   attiva    [argv] da lanciare in ordine; l'esito dell'ultimo e' quello che conta
#   ripiego   un altro piano da usare se `attiva` fallisce (o None)
#   disattiva [argv] da lanciare per spegnere (l'esito non conta)
#   rimuovi   [percorso] da cancellare, ci siano o no
#   dopo      [argv] (facoltativo) da lanciare dopo aver cancellato i file
#   presente  [percorso] la cui esistenza dice "e' installato"
#   query     argv il cui codice 0 dice "e' installato" (o None)
# `esegui` di setup_claude li applica: qui non si tocca niente.

PLIST_SERVER = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{python}</string><string>{cmd}</string><string>serve</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
  <key>ProcessType</key><string>Background</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>{path}</string></dict>
</dict>
</plist>
"""

PLIST_RIEPILOGO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{python}</string><string>{cmd}</string><string>recap</string>
    <string>--daily</string><string>--notify</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>{ora}</integer><key>Minute</key><integer>{minuto}</integer></dict>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>{path}</string></dict>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
"""


def cartella_launchagents(casa) -> Path:
    return Path(casa) / "Library" / "LaunchAgents"


def cartella_avvio_windows(ambiente=None, casa=None) -> Path:
    """`%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup`."""
    amb = os.environ if ambiente is None else ambiente
    base = amb.get("APPDATA") or str(Path(casa or Path.home()) / "AppData" / "Roaming")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def cartella_systemd(casa, ambiente=None) -> Path:
    amb = os.environ if ambiente is None else ambiente
    base = amb.get("XDG_CONFIG_HOME") or str(Path(casa) / ".config")
    return Path(base) / "systemd" / "user"


def cartella_autostart_linux(casa, ambiente=None) -> Path:
    amb = os.environ if ambiente is None else ambiente
    base = amb.get("XDG_CONFIG_HOME") or str(Path(casa) / ".config")
    return Path(base) / "autostart"


def python_senza_finestra(python, esiste=None) -> str:
    """Su Windows `pythonw.exe` (se sta accanto all'interprete) non apre una
    finestra nera: e' quello che serve per un server che deve stare in fondo."""
    esiste = esiste or os.path.exists
    python = str(python)
    # un percorso di Windows si spezza con ntpath anche quando a guardarlo e'
    # una macchina che non e' Windows (le prove lo fanno)
    modulo = ntpath if ("\\" in python or python[1:2] == ":") else os.path
    cartella, nome_exe = modulo.split(python)
    candidato = modulo.join(cartella, "pythonw.exe") if cartella else "pythonw.exe"
    if nome_exe.lower() in ("python.exe", "python") and esiste(candidato):
        return candidato
    return python


def _percorso_unix_avvio(casa) -> str:
    return ":".join([str(Path(casa) / ".local/bin"), "/opt/homebrew/bin",
                     "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])


def _percorso_unix_riepilogo(casa) -> str:
    return ":".join([str(Path(casa) / ".local/bin"), "/opt/homebrew/bin",
                     "/usr/local/bin", "/usr/bin", "/bin"])


def _systemd_exec(python, script, *argomenti) -> str:
    """ExecStart di un'unita': i percorsi tra virgolette, il `%` raddoppiato."""
    pezzi = [_virgolette(python), _virgolette(script)] + list(argomenti)
    return " ".join(pezzi).replace("%", "%%")


def piano_server(python, script, log, casa, uid=None, piatt=None, ambiente=None,
                 cerca_fn=None, esiste=None) -> dict:
    """Come far ripartire la dashboard a ogni accesso."""
    piatt = _p(piatt)
    casa = Path(casa)
    if piatt == MAC:
        plist = cartella_launchagents(casa) / (LABEL_SERVER + ".plist")
        dominio = "gui/%s/%s" % (uid, LABEL_SERVER)
        return {
            "nome": "launchd",
            "file": [(plist, PLIST_SERVER.format(
                label=LABEL_SERVER, python=python, cmd=str(script),
                path=_percorso_unix_avvio(casa), log=str(log)))],
            "attiva": [["launchctl", "bootout", dominio],
                       ["launchctl", "bootstrap", "gui/%s" % uid, str(plist)]],
            "ripiego": None,
            "disattiva": [["launchctl", "bootout", dominio]],
            "rimuovi": [plist], "presente": [plist], "query": None,
        }
    if piatt == WINDOWS:
        senza = python_senza_finestra(python, esiste)
        azione = "%s %s serve" % (_virgolette(senza), _virgolette(script))
        avvio = cartella_avvio_windows(ambiente, casa) / "plancia.cmd"
        return {
            "nome": "Task Scheduler",
            "file": [],
            "attiva": [["schtasks", "/Create", "/TN", TASK_SERVER, "/SC", "ONLOGON",
                        "/TR", azione, "/F"]],
            # senza privilegi ONLOGON puo' essere negato: la cartella Esecuzione
            # automatica non chiede niente a nessuno
            "ripiego": {
                "nome": "cartella Esecuzione automatica",
                "file": [(avvio, '@echo off\r\nstart "" %s\r\n' % azione)],
                "attiva": [], "ripiego": None, "disattiva": [],
                "rimuovi": [avvio], "presente": [avvio], "query": None,
            },
            "disattiva": [["schtasks", "/Delete", "/TN", TASK_SERVER, "/F"]],
            "rimuovi": [avvio], "presente": [avvio],
            "query": ["schtasks", "/Query", "/TN", TASK_SERVER],
        }
    systemd = cartella_systemd(casa, ambiente)
    unita = systemd / "plancia.service"
    desktop = cartella_autostart_linux(casa, ambiente) / "plancia.desktop"
    contenuto_unita = (
        "[Unit]\nDescription=Plancia, la dashboard del lavoro con l'IA\n\n"
        "[Service]\nExecStart=%s\nRestart=on-failure\n"
        "Environment=PATH=%s\nStandardOutput=append:%s\nStandardError=append:%s\n\n"
        "[Install]\nWantedBy=default.target\n" % (
            _systemd_exec(python, script, "serve"),
            "%s:/usr/local/bin:/usr/bin:/bin" % (casa / ".local/bin"), log, log))
    contenuto_desktop = (
        "[Desktop Entry]\nType=Application\nName=Plancia\n"
        "Comment=La dashboard di Plancia\nExec=%s %s serve\n"
        "X-GNOME-Autostart-enabled=true\n" % (_virgolette(python), _virgolette(script)))
    ripiego = {
        "nome": "~/.config/autostart", "file": [(desktop, contenuto_desktop)],
        "attiva": [], "ripiego": None, "disattiva": [],
        "rimuovi": [desktop], "presente": [desktop], "query": None,
    }
    if not (cerca_fn or cerca)("systemctl"):
        return ripiego
    return {
        "nome": "systemd",
        "file": [(unita, contenuto_unita)],
        "attiva": [["systemctl", "--user", "daemon-reload"],
                   ["systemctl", "--user", "enable", "--now", "plancia.service"]],
        "ripiego": ripiego,
        "disattiva": [["systemctl", "--user", "disable", "--now", "plancia.service"]],
        "rimuovi": [unita, desktop], "presente": [unita, desktop], "query": None,
        "dopo": [["systemctl", "--user", "daemon-reload"]],
    }


def piano_riepilogo(python, script, ora, minuto, log, casa, uid=None, piatt=None,
                    ambiente=None, cerca_fn=None, esiste=None):
    """Come far girare il riepilogo ogni giorno all'ora data. None se su questo
    sistema non c'e' modo di farlo senza strumenti che Plancia non pretende."""
    piatt = _p(piatt)
    casa = Path(casa)
    if piatt == MAC:
        plist = cartella_launchagents(casa) / (LABEL_RIEPILOGO + ".plist")
        dominio = "gui/%s/%s" % (uid, LABEL_RIEPILOGO)
        return {
            "nome": "launchd",
            "file": [(plist, PLIST_RIEPILOGO.format(
                label=LABEL_RIEPILOGO, python=python, cmd=str(script), ora=ora,
                minuto=minuto, log=str(log), path=_percorso_unix_riepilogo(casa)))],
            "attiva": [["launchctl", "bootout", dominio],
                       ["launchctl", "bootstrap", "gui/%s" % uid, str(plist)]],
            "ripiego": None,
            "disattiva": [["launchctl", "bootout", dominio]],
            "rimuovi": [plist], "presente": [plist], "query": None,
        }
    if piatt == WINDOWS:
        senza = python_senza_finestra(python, esiste)
        azione = "%s %s recap --daily --notify" % (_virgolette(senza), _virgolette(script))
        return {
            "nome": "Task Scheduler",
            "file": [],
            "attiva": [["schtasks", "/Create", "/TN", TASK_RIEPILOGO, "/SC", "DAILY",
                        "/ST", "%02d:%02d" % (ora, minuto), "/TR", azione, "/F"]],
            "ripiego": None,
            "disattiva": [["schtasks", "/Delete", "/TN", TASK_RIEPILOGO, "/F"]],
            "rimuovi": [], "presente": [],
            "query": ["schtasks", "/Query", "/TN", TASK_RIEPILOGO],
        }
    if not (cerca_fn or cerca)("systemctl"):
        return None
    systemd = cartella_systemd(casa, ambiente)
    servizio = systemd / "plancia-riepilogo.service"
    timer = systemd / "plancia-riepilogo.timer"
    contenuto_servizio = (
        "[Unit]\nDescription=Il riepilogo giornaliero di Plancia\n\n"
        "[Service]\nType=oneshot\nExecStart=%s\n"
        "Environment=PATH=%s\nStandardOutput=append:%s\nStandardError=append:%s\n" % (
            _systemd_exec(python, script, "recap", "--daily", "--notify"),
            "%s:/usr/local/bin:/usr/bin:/bin" % (casa / ".local/bin"), log, log))
    contenuto_timer = (
        "[Unit]\nDescription=Il riepilogo giornaliero di Plancia, ogni giorno alle %02d:%02d\n\n"
        "[Timer]\nOnCalendar=*-*-* %02d:%02d:00\nPersistent=true\n\n"
        "[Install]\nWantedBy=timers.target\n" % (ora, minuto, ora, minuto))
    return {
        "nome": "systemd",
        "file": [(servizio, contenuto_servizio), (timer, contenuto_timer)],
        "attiva": [["systemctl", "--user", "daemon-reload"],
                   ["systemctl", "--user", "enable", "--now", "plancia-riepilogo.timer"]],
        "ripiego": None,
        "disattiva": [["systemctl", "--user", "disable", "--now", "plancia-riepilogo.timer"]],
        "rimuovi": [timer, servizio], "presente": [timer], "query": None,
        "dopo": [["systemctl", "--user", "daemon-reload"]],
    }


def nome_avvio(piatt=None) -> str:
    """Il nome, per le frasi, del meccanismo che fa ripartire il server."""
    return {MAC: "launchd", WINDOWS: "Task Scheduler"}.get(_p(piatt), "systemd")
