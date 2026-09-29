"""Il secondo giro su Windows: l'hook di sessione, e i compartimenti spenti.

Il primo giro completo di GitHub su `windows-latest` (run 36582338633) ha dato un NO
che riguarda anche chi non usa i compartimenti (il PC Windows di chi ha scritto
Plancia non li ha): "senza compartimenti il briefing di SessionStart e' quello di
sempre", con l'uscita dell'hook VUOTA.

Da dove veniva il vuoto: dalla prova, non dagli utenti. La prova lanciava
`[python, bin/plancia-hook]` senza `-X utf8`; gli hook che scrive `plancia install`
lo hanno gia' (`piattaforma.riga_script` mette `"<python>" -X utf8 "<script>"`), e con
il flag lo stdio e' UTF-8 e il briefing arriva. Senza il flag, su Windows, con stdin e
stdout in una pipe Python usa cp1252, non UTF-8. Il briefing ha una freccia (U+2192),
che cp1252 non ha: `sys.stdout.write` alzava `UnicodeEncodeError`, l'eccezione finiva
nel `except Exception` che protegge la sessione, e la sessione partiva SENZA briefing, in
silenzio. Sullo stdin lo stesso difetto e' piu' sottile: una cartella con un accento
(`Citta'`, con l'accento) arrivava come `CittÃ ` nella coda delle sessioni. Il difetto
riguarda quindi un hook lanciato a mano o registrato prima di `-X utf8`, non chi ha
installato con `plancia install`. La correzione rende l'hook indipendente dalla tabella
di caratteri: legge e scrive i byte in UTF-8, qualunque sia la tabella. Nessuno dei due
si vede da macOS, dove tutto e' UTF-8. Qui si simula quello che si puo': i sottoprocessi
girano con `PYTHONUTF8=0` e `PYTHONIOENCODING=cp1252` (su Windows vero, senza il flag,
e' quello che succede da solo, e le prove restano vere), e la logica dei percorsi con
`ntpath`.

1. l'hook `bin/plancia-hook`, lanciato senza `-X utf8`: il briefing con la freccia arriva,
   l'accento nella cwd arriva in coda com'era, un BOM su stdin non rompe il JSON; il
   richiamo (`bin/plancia-richiamo`) legge e scrive UTF-8 nello stesso modo; l'intero
   `run()` dell'hook con percorsi di Windows (lettera di unita', barre rovesciate);
2. `piattaforma.stdio_utf8` (il server MCP) fa leggere e scrivere UTF-8 su Windows;
3. i compartimenti e il guardiano su Windows sono spenti, e lo dicono: `attivo()` torna
   None, l'hook manda il briefing di sempre anche con dei compartimenti in config.json, il
   guardiano non nega niente (nemmeno in `bloccante`) e avvisa UNA volta per sessione,
   `plancia guardiano` e `plancia doctor` lo scrivono. Su macOS e Linux non cambia niente;
4. "Windows" lo dice il sistema, mai una variabile. `PLANCIA_PIATTAFORMA` fa fingere una
   piattaforma alle prove di piattaforma (i comandi che Plancia costruisce), ma non spegne
   il guardiano ne' i compartimenti: chi scrive un `settings.json` puo' metterla in `env`,
   e una sessione dentro un compartimento non deve potersi togliere il confine con una riga
   di configurazione. Il guardiano e l'hook decidono da `os.name == "nt"`; la variabile e'
   fra le `env` che il guardiano nega di scrivere. Per provare il ramo di Windows su un
   altro sistema qui si fa credere agli script che `os.name` sia `nt`
   (`tools/prove/_come_windows.py`) e si sostituisce `piattaforma.windows_reale`.

Per lanciare da sola: `python3 tools/prove/windows-hook.py`.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import ntpath
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

FRECCIA = "\u2192"          # la freccia del briefing: cp1252 non ce l'ha
CITTA = "Citt\u00e0"        # un accento, che cp1252 ha ma UTF-8 scrive in due byte


def _env_windows(dati, **extra):
    """L'ambiente di un sottoprocesso come su Windows con lo stdio in una pipe:
    tabella del sistema (cp1252), non UTF-8."""
    env = dict(os.environ)
    env.update({"PLANCIA_HOME": str(dati), "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"})
    for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "PYTHONPATH"):
        env.pop(k, None)
    env.update(extra)
    return env


def _crea_db(percorso, link=()):
    con = sqlite3.connect(str(percorso))
    con.executescript(
        "create table projects(id integer primary key, key text);"
        "create table repos(local_path text, project_id integer);"
        "create table project_links(project_id integer, kind text, value text);")
    con.execute("insert into projects values (1,'proj-uno')")
    for p in link:
        con.execute("insert into project_links values (1,'path',?)", (p,))
    con.commit()
    con.close()


def _hook(dati, payload_byte, env, script="plancia-hook", argomenti=(), come_windows=False):
    """Lancia uno script di `bin/` come si lancia su Windows: l'interprete e lo
    script, senza `-X utf8`, con lo stdin in byte. Torna il processo (byte).

    Con `come_windows` lo script crede che `os.name` sia `nt` (`_come_windows.py`): e' il
    solo modo di provare il ramo di Windows di un altro sistema, perche' gli script non
    guardano piu' la variabile `PLANCIA_PIATTAFORMA` (vedi la sezione 4)."""
    lanciatore = [str(RADICE / "tools" / "prove" / "_come_windows.py")] if come_windows else []
    return subprocess.run([sys.executable] + lanciatore
                          + [str(RADICE / "bin" / script)] + list(argomenti),
                          input=payload_byte, capture_output=True, env=env, timeout=60)


def _payload(evento="SessionStart", sid="x", cwd="/tmp", **extra):
    d = {"hook_event_name": evento, "session_id": sid, "cwd": cwd}
    d.update(extra)
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------------------
# 1. l'hook di sessione e il richiamo, con la tabella di caratteri di Windows
# --------------------------------------------------------------------------

def _prove_hook_utf8(prova):
    dati = Path(tempfile.mkdtemp(prefix="plancia-prova-wh-"))
    try:
        (dati / "queue").mkdir()
        (dati / "briefing.md").write_text(
            "# Plancia\n\nprogetto uno %s passo %s fatto\n" % (FRECCIA, CITTA), "utf-8")
        _crea_db(dati / "plancia.db")
        env = _env_windows(dati)

        cwd = "/tmp/" + CITTA
        r = _hook(dati, _payload(cwd=cwd), env)
        try:
            uscita = json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]["additionalContext"]
        except Exception as exc:  # noqa: BLE001
            uscita = "(%s) %r" % (type(exc).__name__, r.stdout[:120])
        prova("hook (stdio cp1252): il briefing con la freccia arriva, in UTF-8",
              FRECCIA in uscita and "passo %s fatto" % CITTA in uscita, uscita[:200])
        prova("hook (stdio cp1252): l'accento della cwd arriva intatto nell'avviso di ancoraggio",
              cwd in uscita, uscita[-200:])
        prova("hook (stdio cp1252): esce zero e non scrive niente su stderr",
              r.returncode == 0 and not r.stderr.strip(), r.stderr.decode("utf-8", "replace")[:200])
        coda = (dati / "queue" / "hooks.jsonl").read_text("utf-8").strip().splitlines()
        rec = json.loads(coda[-1]) if coda else {}
        prova("hook (stdio cp1252): la cwd con l'accento entra in coda com'era, non come mojibake",
              rec.get("cwd") == cwd, str(rec))

        # un BOM su stdin (lo mette PowerShell quando ci si pipa un testo) non rompe il JSON
        r2 = _hook(dati, b"\xef\xbb\xbf" + _payload(sid="bom", cwd="/tmp/bom"), env)
        coda = (dati / "queue" / "hooks.jsonl").read_text("utf-8").strip().splitlines()
        rec2 = json.loads(coda[-1])
        prova("hook: un BOM iniziale su stdin non fa perdere l'evento (sessione e cwd in coda)",
              rec2.get("session_id") == "bom" and rec2.get("cwd") == "/tmp/bom"
              and r2.returncode == 0, str(rec2))

        # un byte che non e' UTF-8 non fa cadere l'hook: la sessione parte lo stesso
        r3 = _hook(dati, b'{"hook_event_name":"SessionStart","session_id":"b\xff","cwd":"/tmp"}', env)
        prova("hook: un byte non UTF-8 su stdin non fa cadere l'hook (esce zero, il briefing c'e')",
              r3.returncode == 0 and FRECCIA in r3.stdout.decode("utf-8", "replace"),
              r3.stdout[:100].decode("utf-8", "replace"))

        # --prova: lo stesso percorso senza mettere niente in coda
        n_prima = len((dati / "queue" / "hooks.jsonl").read_text("utf-8").splitlines())
        r4 = _hook(dati, _payload(cwd=cwd), env, argomenti=["--prova"])
        n_dopo = len((dati / "queue" / "hooks.jsonl").read_text("utf-8").splitlines())
        prova("hook --prova (stdio cp1252): il briefing esce e niente entra in coda",
              FRECCIA in r4.stdout.decode("utf-8", "replace") and n_dopo == n_prima)
    finally:
        _pulisci(dati)


def _carica_richiamo():
    """`bin/plancia-richiamo` come modulo (non ha estensione): le sue funzioni di
    lettura e scrittura, senza lanciarlo."""
    percorso = str(RADICE / "bin" / "plancia-richiamo")
    loader = importlib.machinery.SourceFileLoader("plancia_richiamo_prova", percorso)
    spec = importlib.util.spec_from_loader("plancia_richiamo_prova", loader)
    modulo = importlib.util.module_from_spec(spec)
    loader.exec_module(modulo)
    return modulo


def _flussi_cp1252(entrata_byte):
    """Uno stdin e uno stdout come quelli di Windows con una pipe: testo in cp1252
    sopra dei byte (con `.buffer`), non in UTF-8."""
    stdin = io.TextIOWrapper(io.BytesIO(entrata_byte), encoding="cp1252", errors="strict")
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    return stdin, stdout


def _prove_richiamo_utf8(prova):
    rich = _carica_richiamo()
    stdin, stdout = _flussi_cp1252(("{\"prompt\":\"come si fa il risotto a %s\"}" % CITTA)
                                   .encode("utf-8"))
    vecchi = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = stdin, stdout
    letto = "{}"
    try:
        # sul commit di base queste due funzioni non ci sono: la prova cade, non si ferma
        letto = getattr(rich, "_leggi_stdin", lambda: stdin.read())()
        getattr(rich, "_scrivi_stdout", sys.stdout.write)(
            json.dumps({"testo": "freccia %s e %s" % (FRECCIA, CITTA)}, ensure_ascii=False))
        stdout.flush()
    except UnicodeEncodeError as exc:
        stdout.buffer.write(("UnicodeEncodeError: %s" % exc).encode("utf-8"))
    finally:
        sys.stdin, sys.stdout = vecchi
    prova("richiamo (stdio cp1252): il messaggio con l'accento si legge come UTF-8",
          json.loads(letto)["prompt"].endswith(CITTA), letto)
    scritto = stdout.buffer.getvalue().decode("utf-8", "replace")
    prova("richiamo (stdio cp1252): l'uscita con la freccia esce in UTF-8, senza UnicodeEncodeError",
          FRECCIA in scritto and CITTA in scritto, scritto)

    # fino in fondo: il richiamo come processo, con un messaggio con l'accento e la tabella cp1252
    dati = Path(tempfile.mkdtemp(prefix="plancia-prova-wr-"))
    try:
        r = _hook(dati, ("{\"prompt\":\"/comando con %s\",\"cwd\":\"/tmp\"}" % CITTA).encode("utf-8"),
                  _env_windows(dati), script="plancia-richiamo")
        prova("richiamo come processo (stdio cp1252): un messaggio con l'accento non lo fa cadere",
              r.returncode == 0 and not r.stderr.strip(), r.stderr.decode("utf-8", "replace")[:200])
    finally:
        _pulisci(dati)


def _hook_con_ntpath(dati, db, briefing, coda):
    """Il sorgente di `bin/plancia-hook` con i percorsi di Windows (`ntpath`), pronto
    per lanciare `run()`. Le cartelle dei dati restano quelle vere di questo sistema."""
    sorgente = (RADICE / "bin" / "plancia-hook").read_text("utf-8")
    corpo = sorgente.split("\ntry:\n    run()")[0]
    globali = {"__name__": "plancia_hook_windows"}
    vecchia = {k: os.environ.get(k) for k in ("PLANCIA_HOME", "HOME", "USERPROFILE")}
    os.environ.update({"PLANCIA_HOME": str(dati), "HOME": str(dati), "USERPROFILE": str(dati)})
    try:
        exec(compile(corpo, "plancia-hook", "exec"), globali)
    finally:
        for k, v in vecchia.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    class _OsWindows:
        name = "nt"
        path = ntpath

        def __getattr__(self, nome):
            return getattr(os, nome)

    globali["os"] = _OsWindows()
    globali["_P"] = ntpath
    globali.update(DB=str(db), BRIEFING=str(briefing), QUEUE=str(coda),
                   CONFIG=str(Path(dati) / "config.json"))
    return globali


def _prove_hook_percorsi_windows(prova):
    """Tutto `run()` con la logica dei percorsi di Windows e le tabelle di cp1252:
    la cwd con la lettera di unita', le barre rovesciate e un accento; il progetto
    registrato con un'altra grafia (barre in avanti, maiuscole diverse)."""
    dati = Path(tempfile.mkdtemp(prefix="plancia-prova-whn-"))
    try:
        (dati / "queue").mkdir()
        (dati / "briefing.md").write_text("# Plancia\n\nvai %s avanti\n" % FRECCIA, "utf-8")
        _crea_db(dati / "plancia.db", ["c:/users/ann/dev/%s/Proj" % CITTA.lower()])
        g = _hook_con_ntpath(dati, dati / "plancia.db", dati / "briefing.md",
                             dati / "queue" / "hooks.jsonl")
        cwd = "C:\\Users\\Ann\\dev\\%s\\Proj\\sub" % CITTA.lower()
        payload = json.dumps({"hook_event_name": "SessionStart", "session_id": "w1",
                              "cwd": cwd}, ensure_ascii=False).encode("utf-8")
        stdin, stdout = _flussi_cp1252(payload)
        vecchi = sys.stdin, sys.stdout, sys.argv
        sys.stdin, sys.stdout, sys.argv = stdin, stdout, ["plancia-hook"]
        try:
            try:
                g["run"]()          # come l'ultima riga dello script: un'eccezione non esce
            except Exception:  # noqa: BLE001
                pass
            stdout.flush()
        finally:
            sys.stdin, sys.stdout, sys.argv = vecchi
        uscita = stdout.buffer.getvalue().decode("utf-8", "replace")
        try:
            testo = json.loads(uscita)["hookSpecificOutput"]["additionalContext"]
        except Exception:  # noqa: BLE001
            testo = uscita
        prova("hook con percorsi di Windows (lettera, barre rovesciate, accento): il briefing con la "
              "freccia esce", FRECCIA in testo, testo[:200])
        prova("hook con percorsi di Windows: la sottocartella e' ancorata al progetto registrato con "
              "un'altra grafia (barre in avanti, maiuscole)",
              "ancorata al progetto `proj-uno`" in testo, testo[-300:])
        coda = (dati / "queue" / "hooks.jsonl").read_text("utf-8").strip().splitlines()
        rec = json.loads(coda[-1]) if coda else {}
        prova("hook con percorsi di Windows: la cwd entra in coda com'era (accento e rovesci)",
              rec.get("cwd") == cwd, str(rec))
        libera = g["ancoraggio"]("C:\\Users\\Ann\\Altro\\Cartella\\")
        legata = g["ancoraggio"](cwd)
        prova("hook con percorsi di Windows: l'avviso scrive il percorso com'e' stato dato (maiuscole e "
              "rovesci), non la forma minuscola che serve ai confronti",
              "(C:\\Users\\Ann\\Altro\\Cartella)" in libera
              and "(c:/users/ann/dev/%s/Proj)" % CITTA.lower() in legata, str((libera, legata)))
    finally:
        _pulisci(dati)


# --------------------------------------------------------------------------
# 2. stdio UTF-8 del server MCP
# --------------------------------------------------------------------------

class _Flusso:
    def __init__(self):
        self.chiamate = []

    def reconfigure(self, **kw):
        self.chiamate.append(kw)


def _prove_stdio_utf8(prova):
    from plancia import piattaforma as pf

    a, b, c = _Flusso(), _Flusso(), _Flusso()
    pf.stdio_utf8(nt=True, flussi=(a, b, c, None))
    voluto = [{"encoding": "utf-8", "errors": "replace"}]
    prova("stdio_utf8 su Windows: stdin, stdout e stderr in UTF-8, un flusso assente (pythonw) non rompe",
          a.chiamate == voluto and b.chiamate == voluto and c.chiamate == voluto,
          str((a.chiamate, b.chiamate, c.chiamate)))
    d = _Flusso()
    pf.stdio_utf8(nt=False, flussi=(d,))
    prova("stdio_utf8 su macOS e Linux: non tocca niente", d.chiamate == [], str(d.chiamate))
    corpo = (RADICE / "plancia" / "mcp.py").read_text("utf-8").split("def main(")[1]
    prova("il server MCP chiama stdio_utf8 prima di leggere da stdin",
          "piattaforma.stdio_utf8()" in corpo.split("for line in sys.stdin")[0])


# --------------------------------------------------------------------------
# 3. compartimenti e guardiano su Windows: spenti
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _piattaforma(nome):
    """`PLANCIA_PIATTAFORMA` impostata (o tolta, con None) per il tempo del blocco. E' la
    variabile con cui le prove di piattaforma FINGONO una piattaforma; non decide niente
    che riguardi la sicurezza (vedi la sezione 4)."""
    vecchia = os.environ.get("PLANCIA_PIATTAFORMA")
    if nome is None:
        os.environ.pop("PLANCIA_PIATTAFORMA", None)
    else:
        os.environ["PLANCIA_PIATTAFORMA"] = nome
    try:
        yield
    finally:
        if vecchia is None:
            os.environ.pop("PLANCIA_PIATTAFORMA", None)
        else:
            os.environ["PLANCIA_PIATTAFORMA"] = vecchia


@contextlib.contextmanager
def _windows_reale(pf, si):
    """`piattaforma.windows_reale` sostituita per il tempo del blocco: `si=True` e' un
    Windows vero (`os.name == "nt"`), `si=False` un sistema POSIX. E' l'unico modo di
    fingere Windows per le decisioni di sicurezza; la variabile non conta."""
    vecchia = getattr(pf, "windows_reale", None)
    pf.windows_reale = lambda: si
    try:
        yield
    finally:
        if vecchia is None:
            del pf.windows_reale      # sul commit di base la funzione non c'e'
        else:
            pf.windows_reale = vecchia


class _OsNt:
    """Il modulo `os` per come lo vede uno script su Windows: `name` e' `nt`, il resto
    (l'ambiente, i percorsi, i file) e' quello vero di questo sistema."""
    name = "nt"

    def __getattr__(self, nome):
        return getattr(os, nome)


def _hook_modulo(dati, os_finto=None):
    """Le funzioni di `bin/plancia-hook`, senza lanciare `run()`, con le cartelle dei dati
    in `dati`. Con `os_finto` lo script vede quel modulo al posto di `os`."""
    sorgente = (RADICE / "bin" / "plancia-hook").read_text("utf-8")
    corpo = sorgente.split("\ntry:\n    run()")[0]
    globali = {"__name__": "plancia_hook_prova"}
    vecchia = os.environ.get("PLANCIA_HOME")
    os.environ["PLANCIA_HOME"] = str(dati)
    try:
        exec(compile(corpo, "plancia-hook", "exec"), globali)
    finally:
        if vecchia is None:
            os.environ.pop("PLANCIA_HOME", None)
        else:
            os.environ["PLANCIA_HOME"] = vecchia
    if os_finto is not None:
        globali["os"] = os_finto
    return globali


def _config_compartimenti(dati, w, guardiano="bloccante"):
    (w / "alfa").mkdir(parents=True, exist_ok=True)
    (w / "beta").mkdir(parents=True, exist_ok=True)
    cfg = {"guardiano": guardiano,
           "compartimenti": {"alfa": {"cartelle": [str(w / "alfa")]},
                             "beta": {"cartelle": [str(w / "beta")]},
                             "predefinito": {}}}
    Path(dati, "config.json").write_text(json.dumps(cfg), "utf-8")
    return cfg


def _prove_compartimenti_spenti(prova):
    from plancia import compartimenti_viste as viste, piattaforma as pf

    prova("compartimenti_supportati: no su Windows, si' su macOS e Linux",
          pf.compartimenti_supportati("windows") is False and pf.compartimenti_supportati("mac") is True
          and pf.compartimenti_supportati("linux") is True)
    with _windows_reale(pf, True):
        prova("compartimenti_supportati senza argomento: no su un Windows vero (os.name == nt)",
              pf.compartimenti_supportati() is False)
    with _windows_reale(pf, False):
        prova("...e su un sistema POSIX e' vero", pf.compartimenti_supportati() is True)

    base = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-wc-")))
    try:
        dati, w = base / "dati", base / "w"
        dati.mkdir()
        (dati / "queue").mkdir()
        _config_compartimenti(dati, w)
        with _windows_reale(pf, False):
            sul_posix = viste.attivo(str(dati))
        # le cartelle dei compartimenti sono percorsi POSIX: con quelle di un Windows vero la
        # config non e' valida (e' proprio il motivo per cui su Windows sono spenti)
        prova("attivo() su un sistema POSIX, con dei compartimenti in config: l'ambito c'e'",
              os.name == "nt" or (sul_posix is not None and sorted(sul_posix.nominati) == ["alfa", "beta"]),
              "saltato: cartelle di Windows, i compartimenti ragionano su percorsi POSIX"
              if os.name == "nt" else "")
        for f in dati.glob("compartimenti.e1-*"):
            f.unlink()
        with _windows_reale(pf, True):
            su_win = viste.attivo(str(dati))
        prova("attivo() su Windows, con gli stessi compartimenti in config: None (Plancia mostra tutto)",
              su_win is None, str(su_win))
        prova("attivo() su Windows non scrive nemmeno la copia dell'ultima config valida",
              not list(dati.glob("compartimenti.e1-*")))

        # l'hook, come processo, con `os.name` a `nt`: il briefing di sempre
        (dati / "briefing.md").write_text("# Plancia\n\nBRIEFING-DI-SEMPRE %s\n" % FRECCIA, "utf-8")
        _crea_db(dati / "plancia.db")
        env = _env_windows(dati)
        env.pop("PLANCIA_PIATTAFORMA", None)
        r = _hook(dati, _payload(sid="aaaaaaaa-0000-4000-8000-00000000000a",
                                 cwd=str(w / "alfa")), env, come_windows=True)
        try:
            testo = json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]["additionalContext"]
        except Exception as exc:  # noqa: BLE001
            testo = "(%s) %r" % (type(exc).__name__, r.stdout[:120])
        prova("hook su Windows con dei compartimenti in config: la sessione di alfa riceve il briefing "
              "di sempre, non un silenzio", "BRIEFING-DI-SEMPRE" in testo, testo[:200])
        prova("hook su Windows con dei compartimenti in config: non si scrive nessun briefing per "
              "compartimento", not list(dati.glob("briefing.*.md")))

        # le funzioni dell'hook, con `os` che dice `nt`: non cerca i nominati in config.json
        g = _hook_modulo(dati, _OsNt())
        prova("hook con os.name == nt: _su_windows() e' vero e _config_con_nominati() no, anche con "
              "dei nominati in config.json",
              g["_su_windows"]() is True and g["_config_con_nominati"]() is False)
    finally:
        _pulisci(base)


def _guardiano(dati, sid, env, comando="cat /etc/passwd", come_windows=False):
    payload = json.dumps({"hook_event_name": "PreToolUse", "session_id": sid,
                          "tool_name": "Bash", "tool_input": {"command": comando},
                          "cwd": "/tmp"}).encode("utf-8")
    return _hook(dati, payload, env, script="plancia-guardiano", come_windows=come_windows)


def _nega(r) -> bool:
    """Il guardiano ha negato lo strumento (`permissionDecision` a `deny`)."""
    try:
        u = json.loads(r.stdout.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return (u.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"


def _prove_guardiano_windows(prova):
    base = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-wg-")))
    try:
        dati, w = base / "dati", base / "w"
        dati.mkdir()
        _config_compartimenti(dati, w, guardiano="bloccante")
        env = _env_windows(dati)
        env.pop("PLANCIA_PIATTAFORMA", None)
        sid1, sid2 = "aaaaaaaa-0000-4000-8000-00000000000a", "bbbbbbbb-0000-4000-8000-00000000000b"
        cmd_vietato = "rm -rf %s" % (w / "beta" / "x")

        r1 = _guardiano(dati, sid1, env, cmd_vietato, come_windows=True)
        try:
            u1 = json.loads(r1.stdout.decode("utf-8"))
        except Exception:  # noqa: BLE001
            u1 = {}
        prova("guardiano su Windows (anche in `bloccante`): esce zero e non nega niente",
              r1.returncode == 0 and "hookSpecificOutput" not in u1
              and "permissionDecision" not in r1.stdout.decode("utf-8", "replace"),
              r1.stdout.decode("utf-8", "replace")[:200])
        prova("guardiano su Windows: la prima volta di una sessione avvisa (systemMessage) che non e' "
              "supportato su Windows",
              "non supportato su Windows" in u1.get("systemMessage", ""), str(u1))
        r1b = _guardiano(dati, sid1, env, cmd_vietato, come_windows=True)
        prova("guardiano su Windows: la stessa sessione non e' avvisata una seconda volta",
              r1b.returncode == 0 and not r1b.stdout.strip(), r1b.stdout.decode("utf-8", "replace")[:200])
        r2 = _guardiano(dati, sid2, env, cmd_vietato, come_windows=True)
        prova("guardiano su Windows: un'altra sessione e' avvisata a sua volta",
              "non supportato su Windows" in r2.stdout.decode("utf-8", "replace"))
        prova("guardiano su Windows: non scrive nel registro dei negati ne' carica il pacchetto "
              "(niente guardiano.log)", not (dati / "guardiano.log").exists())
        prova("guardiano su Windows: un file per sessione, in guardiano-windows/",
              sorted(p.name for p in (dati / "guardiano-windows").iterdir()) == [sid1, sid2])
        r3 = _hook(dati, b"non e' json", env, script="plancia-guardiano", come_windows=True)
        prova("guardiano su Windows: uno stdin che non e' JSON non lo fa cadere (esce zero)",
              r3.returncode == 0 and not r3.stderr.strip(), r3.stderr.decode("utf-8", "replace")[:200])

        # gli stessi dati su un sistema POSIX: il guardiano c'e' ancora, nega, e non stampa
        # l'avviso di Windows (su un Windows vero il guardiano POSIX non si lancia)
        (w / "beta").mkdir(exist_ok=True)
        if os.name == "nt":
            r4 = None
        else:
            r4 = _guardiano(dati, sid1, env, cmd_vietato)
        prova("guardiano su Linux/macOS: la stessa configurazione non stampa l'avviso di Windows",
              r4 is None or "non supportato su Windows" not in r4.stdout.decode("utf-8", "replace"),
              "saltato: cartelle di Windows" if r4 is None else r4.stdout.decode("utf-8", "replace")[:200])
    finally:
        _pulisci(base)


def _prove_avvisi(prova):
    """`plancia guardiano` e `plancia doctor` dicono che su Windows e' spento."""
    from plancia import cli, config, piattaforma as pf, setup_claude

    class _Args:
        registro = None

    def _stampa(f, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = f(*a)
        return rc, buf.getvalue()

    with _windows_reale(pf, True):
        rc, out = _stampa(cli.cmd_guardiano, _Args())
    prova("plancia guardiano su Windows: dice che non e' supportato ed esce zero",
          rc == 0 and "non sono supportati su Windows" in out, out[:200])

    vera = config.load_config
    try:
        for nome, cfg, atteso in (
                ("compartimenti nominati", {"compartimenti": {"alfa": {"cartelle": []}}}, True),
                ("guardiano acceso", {"guardiano": "solo-registro"}, True),
                ("solo la voce predefinito e guardiano spento",
                 {"compartimenti": {"predefinito": {}}, "guardiano": "spento"}, False),
                ("config senza niente", {}, False)):
            config.load_config = lambda cfg=cfg: dict(cfg)
            with _windows_reale(pf, True):
                righe = setup_claude._righe_compartimenti_windows()
            prova("doctor su Windows, config con %s: %s" % (
                nome, "una riga che dice che sono spenti" if atteso else "nessuna riga"),
                  bool(righe) == atteso and (not atteso or "non sono supportati su Windows" in righe[0]),
                  str(righe))
        config.load_config = lambda: {"compartimenti": {"alfa": {"cartelle": []}}, "guardiano": "bloccante"}
        with _windows_reale(pf, False):
            righe = setup_claude._righe_compartimenti_windows()
        prova("doctor su macOS, con dei compartimenti in config: nessuna riga in piu'", righe == [], str(righe))
    finally:
        config.load_config = vera
    prova("doctor() aggiunge le righe dei compartimenti spenti",
          "_righe_compartimenti_windows()" in (RADICE / "plancia" / "setup_claude.py")
          .read_text("utf-8").split("def doctor(")[1])


# --------------------------------------------------------------------------
# 4. "Windows" lo dice il sistema, non una variabile
# --------------------------------------------------------------------------

def _prove_la_variabile_non_decide(prova):
    """`PLANCIA_PIATTAFORMA` non spegne il guardiano ne' i compartimenti. Chi puo' scrivere
    un `settings.json` puo' metterla in `env`: se bastasse a far credere a Plancia di essere
    su Windows, una sessione dentro un compartimento si toglierebbe il confine con una riga.
    Il valore che si prova e' quello OPPOSTO al sistema vero ("windows" su macOS e Linux,
    "linux" su un Windows vero): in tutti e due i casi il risultato deve restare quello del
    sistema."""
    from plancia import compartimenti as C, compartimenti_viste as viste, piattaforma as pf

    windows_vero = os.name == "nt"
    opposto = "linux" if windows_vero else "windows"

    esiti = []
    for valore in ("windows", "linux", "mac", "amiga", None):
        with _piattaforma(valore):
            esiti.append(pf.compartimenti_supportati())
    prova("compartimenti_supportati(): PLANCIA_PIATTAFORMA non la cambia, con nessun valore",
          all(e is (not windows_vero) for e in esiti), str(esiti))
    with _piattaforma("windows"):
        prova("la variabile fa ancora fingere la piattaforma alle prove di piattaforma "
              "(piattaforma.nome())", pf.nome() == "windows")

    prova("la variabile e' fra le env che il guardiano nega di scrivere in un settings.json",
          "PLANCIA_PIATTAFORMA" in C._ENV_PERICOLOSE)
    prova("_env_pericolose la segnala, e non segnala una env innocua",
          list(C._env_pericolose(json.dumps({"env": {"PLANCIA_PIATTAFORMA": "windows"}}))) == ["PLANCIA_PIATTAFORMA"]
          and C._env_pericolose(json.dumps({"env": {"PYTHONIOENCODING": "utf-8"}})) == {})

    base = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-wv-")))
    try:
        dati, w = base / "dati", base / "w"
        dati.mkdir()
        (dati / "queue").mkdir()
        _config_compartimenti(dati, w, guardiano="bloccante")

        with _piattaforma(opposto):
            ambito = viste.attivo(str(dati))
        if windows_vero:
            atteso = ambito is None
        else:
            atteso = ambito is not None and sorted(ambito.nominati) == ["alfa", "beta"]
        prova("attivo() con PLANCIA_PIATTAFORMA=%s: i compartimenti restano quelli del sistema "
              "(%s)" % (opposto, "spenti" if windows_vero else "accesi"), atteso, str(ambito))

        g = _hook_modulo(dati)
        with _piattaforma(opposto):
            windows_hook = g["_su_windows"]()
            nominati = g["_config_con_nominati"]()
        prova("hook con PLANCIA_PIATTAFORMA=%s: _su_windows() dice il sistema vero" % opposto,
              windows_hook is windows_vero, str(windows_hook))
        prova("hook con PLANCIA_PIATTAFORMA=%s: i compartimenti nominati in config.json %s" % (
            opposto, "restano ignorati" if windows_vero else "si cercano ancora"),
              nominati is (not windows_vero), str(nominati))
        with _piattaforma("linux"):
            g_nt = _hook_modulo(dati, _OsNt())
            spento = g_nt["_su_windows"]() is True and g_nt["_config_con_nominati"]() is False
        prova("hook con os.name == nt e PLANCIA_PIATTAFORMA=linux: resta Windows (la variabile non "
              "riaccende niente)", spento)

        # l'hook come processo: la sessione va a cercare i compartimenti (attivo() lascia la copia
        # dell'ultima config valida), oppure su Windows no
        (dati / "briefing.md").write_text("# Plancia\n\nBRIEFING-DI-SEMPRE %s\n" % FRECCIA, "utf-8")
        _crea_db(dati / "plancia.db")
        for f in dati.glob("compartimenti.e1-*"):
            f.unlink()
        env = _env_windows(dati, PLANCIA_PIATTAFORMA=opposto)
        _hook(dati, _payload(sid="aaaaaaaa-0000-4000-8000-00000000000a", cwd=str(w / "alfa")), env)
        cerca = bool(list(dati.glob("compartimenti.e1-*")))
        prova("hook come processo con PLANCIA_PIATTAFORMA=%s: %s" % (
            opposto, "non guarda i compartimenti" if windows_vero else "guarda ancora i compartimenti"),
              cerca is (not windows_vero), str(sorted(p.name for p in dati.iterdir())))

        # il guardiano come processo: sul sistema vero nega ancora (POSIX) o resta spento (Windows)
        sid1 = "aaaaaaaa-0000-4000-8000-00000000000a"
        cmd_vietato = "rm -rf %s" % (w / "beta" / "x")
        r = _guardiano(dati, sid1, env, cmd_vietato)
        avvisa = "non supportato su Windows" in r.stdout.decode("utf-8", "replace")
        if windows_vero:
            prova("guardiano con PLANCIA_PIATTAFORMA=%s su Windows: resta spento e lo dice" % opposto,
                  avvisa and not _nega(r), r.stdout.decode("utf-8", "replace")[:200])
            # gemella della seconda prova del ramo POSIX: stesso numero di controlli ovunque
            prova("guardiano con PLANCIA_PIATTAFORMA=%s su Windows: non scrive il registro dei "
                  "negati (spento, non nega niente)" % opposto,
                  not (dati / "guardiano.log").exists() or "negato" not in
                  (dati / "guardiano.log").read_text("utf-8", "replace"),
                  str(sorted(p.name for p in dati.iterdir())))
        else:
            prova("guardiano con PLANCIA_PIATTAFORMA=%s su macOS/Linux: nega ancora (bloccante), "
                  "non spento" % opposto,
                  _nega(r) and not avvisa, r.stdout.decode("utf-8", "replace")[:300]
                  + " | " + r.stderr.decode("utf-8", "replace")[:200])
            prova("guardiano con PLANCIA_PIATTAFORMA=%s su macOS/Linux: scrive il registro dei "
                  "negati e non il file dell'avviso di Windows" % opposto,
                  (dati / "guardiano.log").exists() and not (dati / "guardiano-windows").exists(),
                  str(sorted(p.name for p in dati.iterdir())))
        # e con os.name == nt la variabile non lo riaccende
        env_l = _env_windows(dati, PLANCIA_PIATTAFORMA="linux")
        r = _guardiano(dati, "bbbbbbbb-0000-4000-8000-00000000000b", env_l, cmd_vietato,
                       come_windows=True)
        prova("guardiano con os.name == nt e PLANCIA_PIATTAFORMA=linux: resta spento e lo dice",
              "non supportato su Windows" in r.stdout.decode("utf-8", "replace") and not _nega(r),
              r.stdout.decode("utf-8", "replace")[:200])
    finally:
        _pulisci(base)


def _pulisci(percorso):
    import shutil
    shutil.rmtree(percorso, ignore_errors=True)


def esegui(prova):
    _prove_hook_utf8(prova)
    _prove_richiamo_utf8(prova)
    _prove_hook_percorsi_windows(prova)
    _prove_stdio_utf8(prova)
    _prove_compartimenti_spenti(prova)
    _prove_guardiano_windows(prova)
    _prove_avvisi(prova)
    _prove_la_variabile_non_decide(prova)


if __name__ == "__main__":
    passate = fallite = 0

    def _prova(nome, esito, dettaglio=""):
        global passate, fallite
        if esito:
            passate += 1
            print(f"  ok   {nome}")
        else:
            fallite += 1
            print(f"  NO   {nome} {dettaglio}")

    os.environ.setdefault("PLANCIA_HOME", tempfile.mkdtemp(prefix="plancia-prova-wh-casa-"))
    esegui(_prova)
    print(f"\n{passate} passate, {fallite} fallite")
    sys.exit(1 if fallite else 0)
