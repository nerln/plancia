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
- `esegui`, `avvia_distaccato` e `cerca` sono il punto in cui si lancia un
  processo o si cerca un programma nel PATH per tutto quello che cambia da
  sistema a sistema. Chi usa questo modulo passa da qui, e le prove li
  sostituiscono: nessuna prova lancia mai `launchctl`, `schtasks`, `systemctl`,
  `osascript`, `claude` o `codex` veri. Ogni altro `subprocess` di `plancia/`
  (git e gh del sync, il `claude` del riepilogo, di Jarvis, dell'agente caldo e
  dei lanci in background, la riproduzione, la trascrizione) passa comunque da
  `opzioni_figlio()`: su Windows aggiunge `CREATE_NO_WINDOW`, perche' il server
  parte con `pythonw` e senza il flag ogni figlio aprirebbe una finestra nera;
  su macOS e Linux torna `{}` e la chiamata resta identica. Restano senza il
  flag solo i lanci in una console visibile (Riprendi, `opzioni_distacco`).

`nome()` dice dove si e': "mac", "windows" o "linux", da `sys.platform`,
sovrascrivibile con `PLANCIA_PIATTAFORMA` (un valore che non sia uno dei tre
nomi viene ignorato). La variabile serve alle prove, per far costruire i comandi
di un'altra piattaforma, e a nient'altro: NON decide niente che riguardi la
sicurezza. Chi puo' scrivere un `settings.json` puo' metterla in `env`, e se
bastasse a far credere a Plancia di essere su Windows, una sessione si toglierebbe
da sola il guardiano e i compartimenti. Quelle decisioni (`compartimenti_supportati`,
e gli script `bin/plancia-guardiano` e `bin/plancia-hook`) passano da
`windows_reale()`, cioe' da `os.name == "nt"`. Su macOS niente di quello che c'era
prima cambia di un byte: gli argv, i plist e i testi sono quelli di sempre, e le
prove lo confrontano con i valori misurati sulla versione precedente.

Solo libreria standard, python 3.9.
"""

import base64
import csv
import ntpath
import os
import re
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


def windows_reale() -> bool:
    """Si sta girando su Windows davvero (`os.name == "nt"`)?

    E' l'unica risposta che vale per una decisione di sicurezza, e non guarda
    `PLANCIA_PIATTAFORMA`: quella variabile la scrive chiunque possa scrivere un
    `settings.json`, e le prove di piattaforma la usano per fingere. La stessa regola
    vive in `bin/plancia-guardiano` e `bin/plancia-hook`, che non importano il
    pacchetto. Su Cygwin e MSYS `os.name` e' `posix`, i percorsi sono POSIX e i
    compartimenti funzionano: per loro e' falso. Le prove la sostituiscono per provare
    il ramo di Windows su un altro sistema."""
    return os.name == "nt"


def compartimenti_supportati(piatt=None) -> bool:
    """I compartimenti e il guardiano funzionano su questa piattaforma?

    No su Windows. Le regole di appartenenza (`plancia/compartimenti.py`) ragionano
    su percorsi POSIX: la cartella di un compartimento, lo specchio delle memorie in
    `<claude>/projects/<percorso con i trattini>`, i comandi di shell che il guardiano
    legge (`cd`, `cat`, `rm`, le redirezioni). Su Windows, con le lettere di unita' e
    la barra rovesciata, non danno un risultato di cui ci si possa fidare, e un
    confine di privacy che sbaglia in silenzio e' peggio di uno spento e dichiarato.
    Quindi su Windows sono spenti: `compartimenti_viste.attivo()` torna None (Plancia
    mostra tutto a tutti, com'e' senza compartimenti), il guardiano esce subito senza
    negare niente e lo dice una volta per sessione, `plancia doctor` lo scrive se
    config.json ne ha. Su macOS e Linux e' sempre vero: non cambia niente.

    Senza argomento la risposta viene dal sistema vero (`windows_reale`), mai da
    `PLANCIA_PIATTAFORMA`: la variabile non spegne i compartimenti. Con `piatt`
    esplicito (le prove) si chiede cosa vale per quella piattaforma."""
    if piatt is None:
        return not windows_reale()
    return piatt != WINDOWS


#: Cosa si dice a chi ha compartimenti o guardiano in config.json su Windows.
NOTA_COMPARTIMENTI_WINDOWS = (
    "compartimenti e guardiano non sono supportati su Windows (ragionano su percorsi "
    "POSIX): qui sono spenti, il guardiano non nega niente e Plancia mostra tutto a "
    "tutte le sessioni")


# --------------------------------------------------------------------------
# l'unico punto in cui si lancia qualcosa
# --------------------------------------------------------------------------

def cerca(programma):
    """Il percorso di `programma` nel PATH, o None. Sostituibile dalle prove."""
    return shutil.which(programma)


# Windows: CREATE_NO_WINDOW, DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP,
# CREATE_NEW_CONSOLE (i valori di subprocess, scritti qui perche' su un altro
# sistema la libreria non li ha).
_NO_WINDOW = 0x08000000
_DETACHED = 0x00000008
_NEW_GROUP = 0x00000200
_NEW_CONSOLE = 0x00000010


def _su_windows_vero(piatt=None, nt=None) -> bool:
    """La piattaforma e' Windows E si sta girando su Windows davvero: su un altro
    sistema `subprocess` rifiuta `creationflags`, anche quando le prove fingono."""
    return _p(piatt) == WINDOWS and (os.name == "nt" if nt is None else nt)


def opzioni_figlio(piatt=None, nt=None) -> dict:
    """Le opzioni di `subprocess` comuni a OGNI processo che Plancia lancia e non
    mostra: su Windows `CREATE_NO_WINDOW`, perche' il server gira con `pythonw`
    (nessuna console) e un programma console avviato da un processo senza console
    apre una finestra nera per ogni `git`, `gh` o `claude`. Su macOS e Linux torna
    `{}`: la chiamata resta identica a quella di sempre.

    Unica eccezione voluta, un terminale visibile per l'utente (Riprendi):
    passa da `opzioni_distacco`, che sceglie da sola le sue opzioni. Chi lancia
    un processo dentro `plancia/` lo fa con `**opzioni_figlio()` (o da
    `esegui`)."""
    if _su_windows_vero(piatt, nt):
        return {"creationflags": _NO_WINDOW}
    return {}


def prompt_da_stdin(piatt=None) -> bool:
    """Il prompt di `claude -p` si scrive nello stdin invece di passarlo come argomento?

    Su Windows si'. `claude` installato con npm e' uno shim `claude.cmd`, e per lanciare
    un `.cmd` Python passa da cmd.exe: un argomento con una riga a capo viene tagliato
    alla prima (il riepilogo e la risposta a voce allegano dati su piu' righe, e al
    modello arrivava la sola prima riga), i caratteri speciali di cmd.exe (`%`, e con delle
    virgolette nel testo anche `&`, `|`, `^`) dentro un titolo di task o un messaggio di
    commit possono essere interpretati, e la riga ha un tetto di 8191 caratteri. Lo stdin
    non passa da nessuna analisi della riga di comando. `claude -p` senza un prompt fra gli argomenti lo legge da stdin (l'aiuto:
    `--input-format` e' `text` di default, "useful for pipes"; e' gia' la strada di Jarvis
    e del cantiere). Su macOS e Linux resta l'argomento, com'e' sempre stato: l'argv non
    cambia di un byte."""
    return _p(piatt) == WINDOWS


def opzioni_utf8(piatt=None, nt=None) -> dict:
    """Le opzioni di `subprocess` per un processo di cui si legge o si scrive TESTO
    (`text=True`) e che parla UTF-8: `claude`, `codex`, `git`, `gh`.

    Su Windows `text=True` da solo usa la tabella di caratteri del sistema
    (cp1252): un accento di `claude -p` arriverebbe come `Ã¨`, e un byte che quella
    tabella non ha (0x81, 0x8D, 0x8F, 0x90, 0x9D) farebbe cadere la lettura con
    `UnicodeDecodeError`. Il prompt scritto nello stdin di un lancio, allo stesso
    modo, non passerebbe con un carattere fuori tabella. Si dice UTF-8 (i byte
    sbagliati diventano un segnaposto invece di un'eccezione). Va sempre insieme a
    `text=True`: `encoding` da solo accende la modalita' testo, e chi passa byte
    (gli appunti, la riproduzione) non lo usa. Su macOS e Linux torna `{}`: la
    chiamata resta identica a quella di sempre."""
    if _su_windows_vero(piatt, nt):
        return {"encoding": "utf-8", "errors": "replace"}
    return {}


def uscita_utf8(nt=None, flussi=None) -> None:
    """Su Windows fa scrivere UTF-8 a `plancia` sul suo stdout e stderr.

    `python bin/plancia ...` lanciato direttamente (senza lo shim `plancia.cmd`, che
    aggiunge `-X utf8`) scrive nella tabella di caratteri del sistema quando
    l'uscita e' rediretta: un accento arriva a Claude Code, che legge UTF-8, come
    `Ã¨`, e un carattere fuori tabella (una freccia) e' una `UnicodeEncodeError`
    che interrompe il comando a meta'. Con la console vera niente cambia. Sotto
    `pythonw` (nessuna console) i flussi non ci sono e non si tocca niente. Su macOS
    e Linux non fa nulla."""
    if not (os.name == "nt" if nt is None else nt):
        return
    for flusso in (flussi if flussi is not None else (sys.stdout, sys.stderr)):
        try:
            flusso.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def stdio_utf8(nt=None, flussi=None) -> None:
    """Su Windows fa leggere e scrivere UTF-8 allo stdin e allo stdout di un
    processo che parla JSON con Claude Code o Codex (il server MCP).

    L'installazione lo lancia gia' con `-X utf8` (vedi `argv_script`); questo copre chi
    lo lancia a mano o da una configurazione scritta prima: con lo stdin in una pipe
    Python su Windows usa cp1252, e un titolo con gli accenti finiva nel db come
    mojibake. Un flusso assente (pythonw) o senza `reconfigure` non si tocca. Su macOS
    e Linux non fa nulla."""
    if not (os.name == "nt" if nt is None else nt):
        return
    for flusso in (flussi if flussi is not None
                   else (sys.stdin, sys.stdout, sys.stderr)):
        try:
            flusso.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def opzioni_processo(piatt=None, nt=None) -> dict:
    """Le opzioni di `subprocess` per un processo di contorno (PowerShell per la
    voce, la notifica, la riproduzione): senza stdin, che sarebbe quello del
    processo che ci ha lanciato (per il server MCP e' il canale JSON-RPC, e
    Windows PowerShell lo legge finche' non si chiude), e su Windows senza la
    console nera che il server, girando con pythonw, aprirebbe a ogni chiamata."""
    # Su macOS `afplay` parte come e' sempre partito (stdout e stderr chiusi, lo
    # stdin ereditato): niente cambia di un byte. Lo stdin chiuso serve a
    # PowerShell su Windows e ai lettori di Linux.
    opzioni = {} if _p(piatt) == MAC else {"stdin": subprocess.DEVNULL}
    opzioni.update(opzioni_figlio(piatt, nt))
    return opzioni


# --------------------------------------------------------------------------
# la guardia dell'avvio automatico
# --------------------------------------------------------------------------

#: I programmi che cambiano lo stato del sistema dell'utente vero: caricano o
#: scaricano servizi, attivita' pianificate, unita' systemd. Da un ambiente finto
#: (una HOME di prova) non devono mai partire: `launchctl` lavora nel dominio
#: `gui/<uid>`, che e' quello dell'utente vero anche con un'altra HOME, e uno
#: `bootout` di prova ferma i servizi veri (successo davvero, in un collaudo).
PROGRAMMI_DI_SISTEMA = ("launchctl", "schtasks", "systemctl", "crontab")

#: Per forzare l'esecuzione anche con una HOME diversa da quella vera (un
#: contenitore, una macchina di prova dove i comandi sono finti): `1`. Le prove
#: che sostituiscono l'esecutore la impostano; chi non ha sostituito niente non
#: deve impostarla mai.
VARIABILE_FORZA = "PLANCIA_AUTOSTART_FORZA"

#: Come si scrive il perche' quando i comandi non partono.
NON_CARICATO = "HOME di prova"


def _casa_vera_windows():
    """La cartella del profilo dell'utente che esegue il processo, chiesta al
    sistema con il token del processo (`GetUserProfileDirectoryW`), NON a
    `USERPROFILE`: quella e' una variabile d'ambiente e un ambiente finto la
    cambia, come `os.path.expanduser`. None se non si riesce."""
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        userenv = ctypes.WinDLL("userenv", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                            ctypes.POINTER(wintypes.HANDLE)]
        advapi.OpenProcessToken.restype = wintypes.BOOL
        userenv.GetUserProfileDirectoryW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD)]
        userenv.GetUserProfileDirectoryW.restype = wintypes.BOOL
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            return None
        try:
            lunghezza = wintypes.DWORD(0)
            # la prima chiamata, senza buffer, fallisce e dice quanto serve
            userenv.GetUserProfileDirectoryW(token, None, ctypes.byref(lunghezza))
            buf = ctypes.create_unicode_buffer(max(lunghezza.value, 1))
            if not userenv.GetUserProfileDirectoryW(token, buf, ctypes.byref(lunghezza)):
                return None
            return buf.value or None
        finally:
            kernel.CloseHandle(token)
    except Exception:
        return None


def casa_vera():
    """La casa dell'utente che esegue il processo, letta dal sistema e non
    dall'ambiente: su POSIX dall'anagrafe degli utenti (`pwd`), su Windows dal
    token del processo. Un ambiente finto (HOME, USERPROFILE) non la cambia.
    None se non si riesce a leggerla."""
    if os.name == "nt":
        return _casa_vera_windows()
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_dir or None
    except Exception:
        return None


def _confronto(percorso) -> str:
    return os.path.normcase(os.path.realpath(os.path.expanduser(str(percorso))))


def sistema_toccabile(casa=None, ambiente=None, casa_vera_fn=None):
    """`(True, "")` se Plancia puo' cambiare il sistema dell'utente (caricare
    servizi, attivita' pianificate, unita' systemd), `(False, perche)` se sta
    girando in un ambiente finto.

    Falso se la HOME del processo (`Path.home()`) non e' la casa vera dell'utente,
    o se `PLANCIA_HOME` punta fuori dalla casa vera, o se la casa vera non si
    riesce a leggere (nel dubbio non si tocca niente). `PLANCIA_AUTOSTART_FORZA=1`
    vince su tutto."""
    env = os.environ if ambiente is None else ambiente
    if str(env.get(VARIABILE_FORZA, "")).strip() == "1":
        return True, ""
    vera = (casa_vera_fn or casa_vera)()
    if not vera:
        return False, "casa dell'utente non leggibile"
    try:
        qui = casa if casa is not None else Path.home()
        vera_n = _confronto(vera)
        if _confronto(qui) != vera_n:
            return False, NON_CARICATO
        dati = str(env.get("PLANCIA_HOME", "")).strip()
        if dati:
            d = _confronto(dati)
            if d != vera_n and not d.startswith(vera_n.rstrip(os.sep) + os.sep):
                return False, NON_CARICATO
    except Exception:
        return False, "casa dell'utente non leggibile"
    return True, ""


def _programma(argv) -> str:
    if not argv:
        return ""
    nome_ = os.path.basename(str(argv[0]).replace("\\", "/")).lower()
    return nome_[:-4] if nome_.endswith(".exe") else nome_


def esegui(argv, **kwargs):
    """`subprocess.run`, senza finestra nera su Windows. Sostituibile dalle prove.

    I programmi che cambiano il sistema dell'utente (`PROGRAMMI_DI_SISTEMA`) non
    partono da una HOME di prova (`sistema_toccabile`): tornano un esito fallito,
    `127`, senza lanciare niente."""
    if _programma(argv) in PROGRAMMI_DI_SISTEMA:
        ok, perche = sistema_toccabile()
        if not ok:
            testo = bool(kwargs.get("text") or kwargs.get("universal_newlines"))
            return subprocess.CompletedProcess(
                argv, 127, "" if testo else b"", "non eseguito: " + perche)
    for nome, valore in opzioni_figlio().items():
        kwargs.setdefault(nome, valore)
    if (kwargs.get("text") or kwargs.get("universal_newlines")) and _su_windows_vero():
        # l'uscita di `schtasks`, `tasklist` e simili e' nella tabella OEM della
        # console, non in quella ANSI di Python: un byte che la seconda non ha
        # (una `i` accentata in italiano e' 0x8D) e' una `UnicodeDecodeError`, e
        # di quel testo interessa solo il messaggio d'errore
        kwargs.setdefault("errors", "replace")
    return subprocess.run(argv, **kwargs)


def opzioni_distacco(piatt=None, cwd=None, nuova_console=False, nt=None) -> dict:
    """Le opzioni con cui `avvia_distaccato` lancia il processo. Con
    `nuova_console` (Windows, il terminale quando manca `wt`) il processo ha una
    console sua e visibile: `DETACHED_PROCESS` e `CREATE_NEW_CONSOLE` non stanno
    insieme, e stdin, stdout e stderr NON si passano. In CPython su Windows basta
    una sola maniglia rediretta perche' si imposti `STARTF_USESTDHANDLES`: il
    figlio riceverebbe `NUL` al posto della console nuova e non potrebbe leggere
    i tasti (claude uscirebbe subito). Senza redirezioni la console e' la sua."""
    if nuova_console and _p(piatt) == WINDOWS:
        opzioni = {}
    else:
        opzioni = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    if cwd is not None:
        opzioni["cwd"] = str(cwd)
    if _p(piatt) == WINDOWS:
        if _su_windows_vero(piatt, nt):
            opzioni["creationflags"] = (_NEW_CONSOLE if nuova_console
                                        else _DETACHED | _NEW_GROUP)
    else:
        opzioni["start_new_session"] = True
    return opzioni


def avvia_distaccato(argv, piatt=None, cwd=None, nuova_console=False):
    """Lancia `argv` staccato da noi e senza aspettarlo: la finestra di un
    terminale resta aperta finche' la chiude chi la usa. Sostituibile dalle
    prove."""
    return subprocess.Popen(argv, **opzioni_distacco(piatt, cwd, nuova_console))


# --------------------------------------------------------------------------
# "questo processo e' vivo?"
# --------------------------------------------------------------------------

# Windows: PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE, ERROR_ACCESS_DENIED.
_QUERY_LIMITED = 0x1000
_STILL_ACTIVE = 259
_ACCESSO_NEGATO = 5


def _kernel32():
    """`(kernel32, get_last_error)` con i tipi dichiarati. Solo su Windows, dove
    `ctypes.WinDLL` esiste; le prove lo sostituiscono con uno finto."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k32.GetExitCodeProcess.restype = ctypes.c_int
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.restype = ctypes.c_int
    return k32, ctypes.get_last_error


def _pid_vivo_ctypes(pid, non_nostro=True) -> bool:
    """Windows: si APRE il processo in sola interrogazione e si legge il codice di
    uscita (`STILL_ACTIVE` se gira ancora). Non si manda nessun segnale: su
    Windows `os.kill(pid, 0)` non controlla, TERMINA il processo."""
    import ctypes
    k32, ultimo_errore = _kernel32()
    handle = k32.OpenProcess(_QUERY_LIMITED, 0, pid)
    if not handle:
        # accesso negato: il processo c'e', semplicemente non e' nostro; ogni
        # altro errore (parametro non valido) vuol dire che non c'e'
        return bool(non_nostro) if ultimo_errore() == _ACCESSO_NEGATO else False
    try:
        codice = ctypes.c_uint32(0)
        if not k32.GetExitCodeProcess(handle, ctypes.byref(codice)):
            return False
        return codice.value == _STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def _pid_vivo_tasklist(pid) -> bool:
    """Il ripiego di Windows: `tasklist /FI "PID eq N"`. Passa da `esegui`, che le
    prove sostituiscono."""
    try:
        res = esegui(["tasklist", "/FI", "PID eq %d" % pid, "/NH", "/FO", "CSV"],
                     capture_output=True, text=True, timeout=15,
                     stdin=subprocess.DEVNULL)
    except Exception:
        return False
    for campi in csv.reader((res.stdout or "").splitlines()):
        # "immagine.exe","1234","Console","1","12.345 KB"
        if len(campi) > 1 and campi[1].strip() == str(pid):
            return True
    return False


def pid_vivo(pid, piatt=None, non_nostro=True, nt=None) -> bool:
    """True se `pid` e' un processo vivo su questa macchina. L'unico punto in cui
    Plancia lo controlla: chi ha bisogno di saperlo passa da qui.

    macOS e Linux: `os.kill(pid, 0)`, che non manda niente e dice solo se il
    processo esiste (un processo di un altro utente c'e', ma non e' nostro: vale
    `non_nostro`). Windows: MAI `os.kill`, perche' li' ogni segnale che non sia
    Ctrl+C o Ctrl+Break chiama TerminateProcess e UCCIDE il processo che si voleva
    solo controllare. Si usa `ctypes` (OpenProcess e GetExitCodeProcess) e,
    dove `ctypes` non e' disponibile o fallisce, `tasklist`.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if _p(piatt) == WINDOWS:
        su_nt = os.name == "nt" if nt is None else nt
        if su_nt:
            try:
                return _pid_vivo_ctypes(pid, non_nostro)
            except Exception:
                pass
        return _pid_vivo_tasklist(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return bool(non_nostro)
    except OSError:
        return False
    return True


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


# L'interprete di Windows in modalita' UTF-8, per tutto quello che parla con
# Claude Code o Codex attraverso pipe (vedi `argv_script`).
UTF8_WINDOWS = ["-X", "utf8"]


# I caratteri che una shell POSIX interpreta dentro un percorso: solo per questi
# `riga_script` mette le virgolette. Gli accenti e `~`, `+`, `=`, `%` non servono.
_CARATTERI_SHELL = re.compile(r"[\s'\"\\$`&|;<>()*?\[\]{}!#]")


def _riga_python(python, script, *argomenti) -> str:
    """`"<python>" -X utf8 "<script>" <argomenti>` come riga per cmd.exe, per il
    Task Scheduler e per un hook."""
    return " ".join([_virgolette(python)] + UTF8_WINDOWS + [_virgolette(script)]
                    + list(argomenti))


def _riga_windows(argv) -> str:
    return subprocess.list2cmdline([str(a) for a in argv])


# --------------------------------------------------------------------------
# registrare i comandi di Plancia (MCP, hook)
# --------------------------------------------------------------------------

def argv_script(script, python=None, piatt=None) -> list:
    """L'argv per lanciare uno script di `bin/`.

    Su macOS e Linux lo script si lancia da solo, ha lo shebang. Su Windows
    uno script senza estensione non si esegue: serve l'interprete davanti, e in
    modalita' UTF-8 (`-X utf8`). Quando stdin e stdout sono pipe, come nel server
    MCP e negli hook, Python su Windows usa la codepage ANSI (cp1252), non UTF-8:
    Claude Code e Codex parlano UTF-8, e un titolo con gli accenti arriverebbe
    nel db come mojibake, mentre una freccia nel briefing farebbe cadere la
    risposta con un UnicodeEncodeError.
    """
    if _p(piatt) == WINDOWS:
        return [python or sys.executable] + UTF8_WINDOWS + [str(script)]
    return [str(script)]


def riga_script(script, python=None, piatt=None) -> str:
    """Come `argv_script`, ma come una riga sola (i settings.json degli hook).

    macOS e Linux: il percorso nudo, com'e' sempre stato, SE non ha niente che la
    shell interpreti (uno spazio, un apice, una parentesi, `&`, `$`...): le
    installazioni esistenti restano identiche. Con uno spazio o un carattere della
    shell il percorso e' quotato (`shlex.quote`), o `sh -c` lo spezzerebbe e
    l'hook non partirebbe (codice 127). Windows: `"<python>" -X utf8 "<script>"`,
    con le virgolette perche' un percorso di Windows ha spesso degli spazi.
    """
    if _p(piatt) == WINDOWS:
        return _riga_python(python or sys.executable, script)
    percorso = str(script)
    return shlex.quote(percorso) if _CARATTERI_SHELL.search(percorso) else percorso


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
    return '@echo off\r\n%s %%*\r\n' % _riga_python(python, script)


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


def _arg_wt(argomento) -> str:
    """Un argomento per `wt.exe`: il punto e virgola e' il separatore di comandi
    di Windows Terminal anche dentro un argomento, e va scritto `\\;`."""
    return str(argomento).replace(";", "\\;")


_CARATTERI_CMD = "\r\n&|<>^%\""


def _passa_da_cmd(comando) -> bool:
    """Il programma e' uno script `.cmd`/`.bat` (quindi passa da cmd.exe) e un
    argomento contiene qualcosa che cmd.exe non sa ricevere in sicurezza."""
    if not comando or not str(comando[0]).lower().endswith((".cmd", ".bat")):
        return False
    return any(c in str(a) for a in comando[1:] for c in _CARATTERI_CMD)


def piano_terminale(cwd, argv, piatt=None, cerca_fn=None):
    """Come aprire una finestra di terminale in `cwd` con `argv` dentro: un
    dizionario `{"argv", "cwd", "nuova_console"}`, o None se su questo sistema non
    si trova nessun terminale. Su Windows senza `wt` e con un `claude.cmd` che
    dovrebbe ricevere un testo pericoloso per cmd.exe torna lo stesso dizionario
    con `argv` a None e un `errore` che dice di installare Windows Terminal.

    `cwd` e' la cartella in cui deve partire il processo lanciato (solo Windows
    senza `wt`, dove non c'e' un terminale che sappia scegliere la cartella) e
    `nuova_console` dice di dargli una console visibile sua. Su Windows il testo
    libero, che sia il titolo di un task o un prompt, non passa MAI da una riga
    interpretata da `cmd.exe`: senza `wt` si lancia `argv` direttamente
    (`CreateProcess`, che non interpreta `&`, `%` o le virgolette), con `wt` ogni
    argomento e' un argomento e il `;` si scappa.

    `PLANCIA_TERMINALE` (un lanciatore alternativo, usato dalle prove) lo
    gestisce chi chiama: qui c'e' solo quello che si fa senza.
    """
    piatt = _p(piatt)
    riga = riga_shell(cwd, argv, piatt)

    def piano(comando, cartella=None, console=False):
        return {"argv": comando, "cwd": cartella, "nuova_console": console}

    if piatt == MAC:
        return piano(["osascript", "-e",
                      "tell application \"Terminal\" to do script %s" % applescript_quote(riga)])
    if piatt == WINDOWS:
        trova = cerca_fn or cerca
        if trova("wt") or trova("wt.exe"):
            return piano(["wt.exe", "-d", _arg_wt(cwd)] + [_arg_wt(a) for a in argv])
        # Il primo elemento, se si trova, con il percorso intero: `claude` e' spesso
        # un `claude.cmd`, e CreateProcess non aggiunge da solo l'estensione.
        comando = [str(a) for a in argv]
        trovato = trova(comando[0]) if comando else None
        if trovato:
            comando[0] = str(trovato)
        if _passa_da_cmd(comando):
            # `claude` installato con npm e' un `claude.cmd`: CreateProcess lo
            # esegue attraverso cmd.exe, che spezza un argomento con un ritorno a
            # capo e interpreta `&`, `%` e le virgolette. Il prompt di un task
            # "persa" e' multi-riga: senza Windows Terminal (che passa ogni
            # argomento cosi' com'e') non si lancia, e lo si dice.
            return {"argv": None, "cwd": None, "nuova_console": False,
                    "errore": ("serve Windows Terminal (wt.exe) per questo comando: "
                               "claude e' un .cmd e il testo del task ha ritorni a capo "
                               "o caratteri che cmd.exe interpreta. Installa Windows "
                               "Terminal (winget install Microsoft.WindowsTerminal) "
                               "oppure lancia il task in background dalla dashboard")}
        return piano(comando, str(cwd), True)
    scelta = _trova(cerca_fn, [
        ["x-terminal-emulator"], ["gnome-terminal"], ["konsole"], ["xterm"]])
    if scelta is None:
        return None
    if scelta[0] == "x-terminal-emulator":
        return piano(["x-terminal-emulator", "-e", "sh", "-c", riga])
    if scelta[0] == "gnome-terminal":
        return piano(["gnome-terminal", "--working-directory=%s" % cwd, "--"]
                     + [str(a) for a in argv])
    if scelta[0] == "konsole":
        return piano(["konsole", "--workdir", str(cwd), "-e"] + [str(a) for a in argv])
    return piano(["xterm", "-e", "sh", "-c", riga])


def comando_terminale(cwd, argv, piatt=None, cerca_fn=None):
    """L'argv di `piano_terminale`, o None."""
    p = piano_terminale(cwd, argv, piatt, cerca_fn)
    return p["argv"] if p else None


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


def input_appunti(testo, comando, piatt=None):
    """Quello che si scrive nello stdin di `comando` (l'argv di `comando_appunti`).

    `clip` di Windows legge lo stdin nella codepage OEM della console, e un testo
    con gli accenti uscirebbe sbagliato: gli si manda UTF-16 con la sua
    intestazione (BOM), che riconosce. Sono byte, quindi chi lancia non deve
    usare `text=True`. Un lanciatore alternativo (`PLANCIA_CLIPBOARD`) e ogni
    altro sistema ricevono il testo com'e'.
    """
    if _p(piatt) == WINDOWS and list(comando) == ["clip"]:
        return ("\ufeff" + testo).encode("utf-16-le")
    return testo


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
    """L'argv di un comando PowerShell. Windows PowerShell 5.1 con lo stdin
    rediretto lo legge e non esce finche' non si chiude: chi lancia gli passa
    `stdin=DEVNULL` (`opzioni_processo`) e qui `-InputFormat None` lo dice anche
    a lui. `pwsh` non ha quel difetto e non conosce il valore `None`."""
    ins = ["-InputFormat", "None"] if exe == "powershell" else []
    return [exe, "-NoProfile", "-NonInteractive"] + ins + ["-Command", script]


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
            # `--`: un testo che comincia con `-` non deve diventare un'opzione
            return [motore, "-v", lang, "-s", str(wpm), "-w", str(out), "--", testo]
    return None


def comando_dire(testo, lang, attendi=True, piatt=None, cerca_fn=None):
    """L'argv che dice `testo` ad alta voce senza passare da un file (solo Linux,
    con `spd-say`), o None. Serve quando manca un motore che sappia scrivere un
    wav ma c'e' Speech Dispatcher. Con `attendi` il comando torna a frase finita."""
    if _p(piatt) == LINUX and (cerca_fn or cerca)("spd-say"):
        return ["spd-say"] + (["-w"] if attendi else []) + ["-l", lang, "--", testo]
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


def voce_mancante(piatt=None, cerca_fn=None):
    """None se su questa macchina si puo' dire una frase ad alta voce, altrimenti
    la frase che spiega cosa manca e cosa installare. E' la verita' che dicono
    `doctor`, `say` e `voice prova`: non basta che ci sia un elenco di voci.

    Si puo' parlare con un motore che scrive un file piu' un lettore audio, oppure
    con `spd-say` (Linux), che dice la frase da solo. Su macOS `say` e `afplay`
    ci sono sempre."""
    piatt = _p(piatt)
    if piatt == MAC:
        return None
    if comando_dire("x", "it", True, piatt, cerca_fn):
        return None
    if comando_sintesi("x", "it", "", 185, "x.wav", piatt, cerca_fn) is None:
        return motore_voce_assente(piatt)
    if comando_riproduzione("x.wav", piatt, cerca_fn) is None:
        return ("nessun lettore audio: installa paplay, aplay o ffplay "
                "per sentire la voce")
    return None


def nome_motore_voce(argv, piatt=None) -> str:
    """Il nome vero del motore che ha detto o scritto la frase (`argv` e' quello di
    `comando_sintesi`): `say` su macOS, `System.Speech` su Windows (PowerShell e'
    solo il modo di arrivarci), `espeak-ng` o `espeak` su Linux."""
    piatt = _p(piatt)
    if piatt == MAC:
        return "say"
    if piatt == WINDOWS:
        return "System.Speech"
    return os.path.basename(str(argv[0])) if argv else "sistema"


def motore_sistema(piatt=None, cerca_fn=None):
    """Il nome del motore di sistema che c'e' su questa macchina, o None."""
    argv = comando_sintesi("x", "it", "", 185, "x.wav", piatt, cerca_fn)
    return nome_motore_voce(argv, piatt) if argv else None


def comando_elenco_voci(piatt=None, cerca_fn=None):
    """L'argv che elenca le voci installate, o None: `say -v ?` su macOS, le voci
    di System.Speech su Windows, `espeak-ng --voices` su Linux."""
    piatt = _p(piatt)
    if piatt == MAC:
        return ["say", "-v", "?"]
    if piatt == WINDOWS:
        exe = _powershell(cerca_fn)
        if exe is None:
            return None
        return _ps_comando(exe, "; ".join([
            "Add-Type -AssemblyName System.Speech",
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
            "$s.GetInstalledVoices() | ForEach-Object "
            "{ $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }",
            "$s.Dispose()"]))
    for motore in ("espeak-ng", "espeak"):
        if (cerca_fn or cerca)(motore):
            return [motore, "--voices"]
    return None


def voci_da_elenco(testo, piatt=None) -> list:
    """`[(nome, "it_IT")]` dall'uscita di `comando_elenco_voci` (solo Windows e
    Linux: quella di macOS la legge `voice.voci_sistema`)."""
    fuori = []
    for riga in (testo or "").splitlines():
        riga = riga.strip()
        if _p(piatt) == WINDOWS:
            nome, _, cultura = riga.partition("|")
            if nome.strip() and cultura.strip():
                fuori.append((nome.strip(), cultura.strip().replace("-", "_")))
            continue
        # espeak: "Pty Language Age/Gender VoiceName File Other"
        campi = riga.split()
        if len(campi) < 4 or not campi[0].isdigit():
            continue
        lingua, _, regione = campi[1].partition("-")
        fuori.append((campi[3], "%s_%s" % (lingua, (regione or lingua).upper())))
    return fuori


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
# mostrare un file all'utente
# --------------------------------------------------------------------------

def comando_apri(percorso, piatt=None, cerca_fn=None):
    """L'argv che mostra `percorso` all'utente, o None: macOS lo rivela nel
    Finder (`open -R`, com'e' sempre stato), Linux lo apre con `xdg-open`.
    Windows non ha un argv: si apre con `os.startfile` (vedi `apri_file`)."""
    piatt = _p(piatt)
    if piatt == MAC:
        return ["open", "-R", str(percorso)]
    if piatt == LINUX and (cerca_fn or cerca)("xdg-open"):
        return ["xdg-open", str(percorso)]
    return None


def _startfile(percorso):
    """`os.startfile`, che c'e' solo su Windows. Sostituibile dalle prove."""
    if not hasattr(os, "startfile"):
        raise OSError("os.startfile non c'e' su questo sistema")
    os.startfile(str(percorso))


def apri_file(percorso, piatt=None, cerca_fn=None):
    """Mostra `percorso` con il lanciatore del sistema. Torna `(True, "")` o
    `(False, perche')`: non solleva mai, chi l'ha chiesto ha comunque il file."""
    piatt = _p(piatt)
    try:
        if piatt == WINDOWS:
            _startfile(percorso)
            return True, ""
        argv = comando_apri(percorso, piatt, cerca_fn)
        if argv is None:
            return False, ("manca xdg-open: apri il file a mano" if piatt == LINUX
                           else "non so come aprire un file su questo sistema")
        esegui(argv, capture_output=True, timeout=15, stdin=subprocess.DEVNULL)
        return True, ""
    except Exception as exc:
        return False, str(exc) or type(exc).__name__


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
        return ["notify-send", "--", titolo, testo]
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
        azione = _riga_python(senza, script, "serve")
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
        azione = _riga_python(senza, script, "recap", "--daily", "--notify")
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
