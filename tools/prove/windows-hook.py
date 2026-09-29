"""Il secondo giro su Windows: l'hook di sessione, e i compartimenti spenti.

Il primo giro completo di GitHub su `windows-latest` (run 36582338633) ha dato un NO
che riguarda anche chi non usa i compartimenti (il PC Windows di chi ha scritto
Plancia non li ha): "senza compartimenti il briefing di SessionStart e' quello di
sempre", con l'uscita dell'hook VUOTA.

La causa e' la tabella di caratteri. Su Windows uno script lanciato come
`[python, bin/plancia-hook]` con stdin e stdout in una pipe legge e scrive in cp1252,
non in UTF-8. Il briefing ha una freccia (U+2192), che cp1252 non ha:
`sys.stdout.write` alzava `UnicodeEncodeError`, l'eccezione finiva nel `except Exception`
che protegge la sessione, e la sessione partiva SENZA briefing, in silenzio. Sullo stdin lo stesso difetto e' piu' sottile: una cartella con un accento
(`Citta'`, con l'accento) arrivava come `CittÃ ` nella coda delle sessioni. Nessuno dei due
si vede da macOS, dove tutto e' UTF-8. Qui si simula quello che si puo': i sottoprocessi
girano con `PYTHONUTF8=0` e `PYTHONIOENCODING=cp1252` (su Windows vero e' quello che
succede da solo, e le prove restano vere), e la logica dei percorsi con `ntpath`.

1. l'hook `bin/plancia-hook`, lanciato come su Windows (senza `-X utf8`): il briefing
   con la freccia arriva, l'accento nella cwd arriva in coda com'era, un BOM su stdin non
   rompe il JSON; il richiamo (`bin/plancia-richiamo`) legge e scrive UTF-8 nello stesso modo;
   l'intero `run()` dell'hook con percorsi di Windows (lettera di unita', barre rovesciate);
2. `piattaforma.stdio_utf8` (il server MCP) fa leggere e scrivere UTF-8 su Windows;
3. i compartimenti e il guardiano su Windows sono spenti, e lo dicono: `attivo()` torna
   None, l'hook manda il briefing di sempre anche con dei compartimenti in config.json, il
   guardiano non nega niente (nemmeno in `bloccante`) e avvisa UNA volta per sessione,
   `plancia guardiano` e `plancia doctor` lo scrivono. Su macOS e Linux non cambia niente.

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


def _hook(dati, payload_byte, env, script="plancia-hook", argomenti=()):
    """Lancia uno script di `bin/` come si lancia su Windows: l'interprete e lo
    script, senza `-X utf8`, con lo stdin in byte. Torna il processo (byte)."""
    return subprocess.run([sys.executable, str(RADICE / "bin" / script)] + list(argomenti),
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
    with _piattaforma("windows"):
        prova("compartimenti_supportati senza argomento segue la piattaforma (PLANCIA_PIATTAFORMA=windows)",
              pf.compartimenti_supportati() is False)
    with _piattaforma("linux"):
        prova("...e su Linux e' vero", pf.compartimenti_supportati() is True)

    base = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-wc-")))
    try:
        dati, w = base / "dati", base / "w"
        dati.mkdir()
        (dati / "queue").mkdir()
        _config_compartimenti(dati, w)
        with _piattaforma("linux"):
            sul_posix = viste.attivo(str(dati))
        # le cartelle dei compartimenti sono percorsi POSIX: con quelle di un Windows vero la
        # config non e' valida (e' proprio il motivo per cui su Windows sono spenti)
        prova("attivo() su un sistema POSIX, con dei compartimenti in config: l'ambito c'e'",
              os.name == "nt" or (sul_posix is not None and sorted(sul_posix.nominati) == ["alfa", "beta"]),
              "saltato: cartelle di Windows, i compartimenti ragionano su percorsi POSIX"
              if os.name == "nt" else "")
        for f in dati.glob("compartimenti.e1-*"):
            f.unlink()
        with _piattaforma("windows"):
            su_win = viste.attivo(str(dati))
        prova("attivo() su Windows, con gli stessi compartimenti in config: None (Plancia mostra tutto)",
              su_win is None, str(su_win))
        prova("attivo() su Windows non scrive nemmeno la copia dell'ultima config valida",
              not list(dati.glob("compartimenti.e1-*")))

        # l'hook, come processo, con la piattaforma dichiarata Windows: il briefing di sempre
        (dati / "briefing.md").write_text("# Plancia\n\nBRIEFING-DI-SEMPRE %s\n" % FRECCIA, "utf-8")
        _crea_db(dati / "plancia.db")
        env = _env_windows(dati, PLANCIA_PIATTAFORMA="windows")
        r = _hook(dati, _payload(sid="aaaaaaaa-0000-4000-8000-00000000000a",
                                 cwd=str(w / "alfa")), env)
        try:
            testo = json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]["additionalContext"]
        except Exception as exc:  # noqa: BLE001
            testo = "(%s) %r" % (type(exc).__name__, r.stdout[:120])
        prova("hook su Windows con dei compartimenti in config: la sessione di alfa riceve il briefing "
              "di sempre, non un silenzio", "BRIEFING-DI-SEMPRE" in testo, testo[:200])
        prova("hook su Windows con dei compartimenti in config: non si scrive nessun briefing per "
              "compartimento", not list(dati.glob("briefing.*.md")))
    finally:
        _pulisci(base)


def _guardiano(dati, sid, env, comando="cat /etc/passwd"):
    payload = json.dumps({"hook_event_name": "PreToolUse", "session_id": sid,
                          "tool_name": "Bash", "tool_input": {"command": comando},
                          "cwd": "/tmp"}).encode("utf-8")
    return _hook(dati, payload, env, script="plancia-guardiano")


def _prove_guardiano_windows(prova):
    base = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-wg-")))
    try:
        dati, w = base / "dati", base / "w"
        dati.mkdir()
        _config_compartimenti(dati, w, guardiano="bloccante")
        env = _env_windows(dati, PLANCIA_PIATTAFORMA="windows")
        sid1, sid2 = "aaaaaaaa-0000-4000-8000-00000000000a", "bbbbbbbb-0000-4000-8000-00000000000b"
        cmd_vietato = "rm -rf %s" % (w / "beta" / "x")

        r1 = _guardiano(dati, sid1, env, cmd_vietato)
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
        r1b = _guardiano(dati, sid1, env, cmd_vietato)
        prova("guardiano su Windows: la stessa sessione non e' avvisata una seconda volta",
              r1b.returncode == 0 and not r1b.stdout.strip(), r1b.stdout.decode("utf-8", "replace")[:200])
        r2 = _guardiano(dati, sid2, env, cmd_vietato)
        prova("guardiano su Windows: un'altra sessione e' avvisata a sua volta",
              "non supportato su Windows" in r2.stdout.decode("utf-8", "replace"))
        prova("guardiano su Windows: non scrive nel registro dei negati ne' carica il pacchetto "
              "(niente guardiano.log)", not (dati / "guardiano.log").exists())
        prova("guardiano su Windows: un file per sessione, in guardiano-windows/",
              sorted(p.name for p in (dati / "guardiano-windows").iterdir()) == [sid1, sid2])
        r3 = _hook(dati, b"non e' json", env, script="plancia-guardiano")
        prova("guardiano su Windows: uno stdin che non e' JSON non lo fa cadere (esce zero)",
              r3.returncode == 0 and not r3.stderr.strip(), r3.stderr.decode("utf-8", "replace")[:200])

        # gli stessi dati su un sistema POSIX: il guardiano c'e' ancora e non stampa l'avviso di
        # Windows (su un Windows vero il guardiano POSIX con cartelle di Windows non si lancia)
        env_posix = _env_windows(dati, PLANCIA_PIATTAFORMA="linux")
        (w / "beta").mkdir(exist_ok=True)
        if os.name == "nt":
            r4 = None
        else:
            r4 = _guardiano(dati, sid1, env_posix, cmd_vietato)
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

    with _piattaforma("windows"):
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
            with _piattaforma("windows"):
                righe = setup_claude._righe_compartimenti_windows()
            prova("doctor su Windows, config con %s: %s" % (
                nome, "una riga che dice che sono spenti" if atteso else "nessuna riga"),
                  bool(righe) == atteso and (not atteso or "non sono supportati su Windows" in righe[0]),
                  str(righe))
        config.load_config = lambda: {"compartimenti": {"alfa": {"cartelle": []}}, "guardiano": "bloccante"}
        with _piattaforma("mac"):
            righe = setup_claude._righe_compartimenti_windows()
        prova("doctor su macOS, con dei compartimenti in config: nessuna riga in piu'", righe == [], str(righe))
    finally:
        config.load_config = vera
    prova("doctor() aggiunge le righe dei compartimenti spenti",
          "_righe_compartimenti_windows()" in (RADICE / "plancia" / "setup_claude.py")
          .read_text("utf-8").split("def doctor(")[1])


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
