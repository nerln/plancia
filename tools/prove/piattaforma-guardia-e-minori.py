"""Prove del quarto giro di U2-UNIVERSALE: la guardia dell'avvio automatico e i minori.

1. GRAVE. `launchctl` lavora nel dominio `gui/<uid>`, che e' quello dell'utente vero
   anche con un'altra HOME: un collaudo con una HOME finta ha fatto `bootout` dei
   servizi veri. Ora l'avvio automatico (`autostart_on/off`, `recap_daily_on/off`,
   `install`, `uninstall`) e ogni `launchctl`, `schtasks` e `systemctl` che passa da
   `piattaforma.esegui` NON partono se la HOME del processo non e' la casa vera
   dell'utente (letta dal sistema, non dall'ambiente), o se `PLANCIA_HOME` sta fuori
   dalla casa vera: i file (plist, unita', `.cmd`) si scrivono nella casa finta e il
   messaggio dice "file scritti, non caricati (HOME di prova)". `PLANCIA_AUTOSTART_FORZA=1`
   forza. Le prove di installazione con un esecutore finto la impostano.
   Le prove qui sotto NON lanciano mai il programma vero: mettono in testa al PATH dei
   programmi finti che registrano gli argomenti, e il processo figlio controlla che
   `launchctl` e gli altri siano quelli finti PRIMA di fare qualunque cosa.
2. Privacy: nessun nome di disco o di volume nel repo (fatta in
   `piattaforma-console-hook.py`); qui la doctor elenca i contenitori in uso.
3. Sul Mac un disco esterno e' un contenitore solo se sta nella chiave `contenitori`
   di config.json: il README lo dice e `plancia doctor` li elenca.
4. Minori: confronto fra cwd e radici senza badare alle maiuscole su Windows, UNC nei
   comandi, niente falso percorso da `sed 's/a:\\/b\\/c/x/'`, `afplay` su mac con gli
   stessi argomenti della base, il controllo di `serve` che non scambia un Plancia
   lento per un altro programma.

Per lanciare da sola: `python3 tools/prove/piattaforma-guardia-e-minori.py`.
"""

import contextlib
import io
import json
import ntpath
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


def _carica_finti():
    """`_finti.py` (materiale di supporto, non una prova) sta accanto a questo file."""
    if "_finti" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_finti", Path(__file__).resolve().parent / "_finti.py")
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["_finti"] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules["_finti"]


_finti = _carica_finti()

PROGRAMMI_FINTI = ("launchctl", "schtasks", "systemctl", "crontab", "osascript", "claude", "codex")


class _Finto:
    """Sostituisce attributi di un oggetto e li rimette (o li toglie, se non c'erano)."""

    _MANCA = object()

    def __init__(self, oggetto, **sostituzioni):
        self.oggetto, self.sostituzioni, self.vecchi = oggetto, sostituzioni, {}

    def __enter__(self):
        for k, v in self.sostituzioni.items():
            self.vecchi[k] = getattr(self.oggetto, k, self._MANCA)
            setattr(self.oggetto, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.vecchi.items():
            if v is self._MANCA:
                delattr(self.oggetto, k)
            else:
                setattr(self.oggetto, k, v)


class _OsWindows:
    """Un `os` con i percorsi di Windows (`ntpath`), il resto e' quello vero."""

    def __init__(self):
        self.path = ntpath
        self.sep = "\\"

    def __getattr__(self, nome):
        return getattr(os, nome)


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


# ==========================================================================
# 1. la guardia: il figlio gira in una HOME finta con programmi finti in testa al PATH
# ==========================================================================

def _figlio_guardia(scenario: str) -> None:
    """Un processo a parte. PRIMA di tutto controlla che `launchctl`, `schtasks`,
    `systemctl` e gli altri siano i programmi finti (se no non fa niente). Poi
    accende e spegne l'avvio automatico e il riepilogo e stampa un JSON."""
    import shutil
    cartella_finti = os.environ["PLANCIA_PROVA_FINTI"]
    for nome in PROGRAMMI_FINTI:
        trovato = shutil.which(nome)
        if not trovato or not str(Path(trovato).resolve()).startswith(str(Path(cartella_finti).resolve())):
            print("RISULTATO:" + json.dumps({"ABORT": "%s non e' quello finto: %s" % (nome, trovato)}))
            return
    casa = Path(os.environ["HOME"])
    (casa / ".claude").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(RADICE))
    from plancia import piattaforma, setup_claude as s

    if scenario == "mac-casa-vera":
        # la HOME del processo E' la casa vera: i comandi devono arrivare (ai finti)
        piattaforma.casa_vera = lambda: str(casa)
    # `pythonw.exe` esiste solo su un Windows vero
    piattaforma.python_senza_finestra = lambda python, esiste=None: python

    def elenco():
        return sorted(p.relative_to(casa).as_posix() for p in casa.rglob("*") if p.is_file()
                      and ".plancia" not in p.relative_to(casa).parts)

    # sulla versione precedente la guardia non c'e': il figlio deve arrivare fino ai
    # comandi (finti) lo stesso, e' li' che la prova diventa rossa
    guardia = getattr(piattaforma, "sistema_toccabile", None)
    out = {"toccabile": list(guardia()) if guardia else None}
    out["on"] = s.autostart_on()
    out["recap_on"] = s.recap_daily_on("08:45")
    out["file_on"] = elenco()
    out["installati"] = [s.autostart_installed(), s.recap_daily_installed(), s.autostart_meccanismo()]
    out["off"] = s.autostart_off()
    out["recap_off"] = s.recap_daily_off()
    out["file_off"] = elenco()
    fuori = []
    for k in ("APPDATA", "XDG_CONFIG_HOME"):
        if os.environ.get(k):
            fuori += [str(p.relative_to(os.environ[k])) for p in Path(os.environ[k]).rglob("*") if p.is_file()]
    out["fuori"] = fuori
    print("RISULTATO:" + json.dumps(out))


def _lancia_guardia(scenario: str, piatt: str, extra=None) -> dict:
    base = Path(tempfile.mkdtemp(prefix="plancia-guardia-"))
    casa, finti, fuori = base / "casa", base / "finti", base / "fuori"
    for d in (casa, finti, fuori):
        d.mkdir()
    registro = base / "registro.txt"
    registro.write_text("")
    for nome in PROGRAMMI_FINTI:
        # scrive "<nome> <argomenti>" nel registro ed esce 0 (lo stesso su ogni sistema)
        _finti.crea_finto(finti, nome,
                          "import sys\n"
                          f"open({str(registro)!r}, 'a').write("
                          f"' '.join([{nome!r}] + sys.argv[1:]) + '\\n')\n")
    amb = {k: v for k, v in os.environ.items()
           if k not in ("PLANCIA_AUTOSTART_FORZA", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA")}
    amb.update(HOME=str(casa), USERPROFILE=str(casa), PLANCIA_HOME=str(casa / ".plancia"),
               CLAUDE_CONFIG_DIR=str(casa / ".claude"), CODEX_HOME=str(casa / ".codex"),
               PLANCIA_PIATTAFORMA=piatt, PLANCIA_PROVA_FINTI=str(finti),
               PATH=str(finti) + os.pathsep + amb_path())
    if piatt == "windows":
        amb["APPDATA"] = str(fuori / "Roaming")   # fuori dalla casa finta
    if piatt == "linux":
        amb["XDG_CONFIG_HOME"] = str(fuori / "config")
    amb.update(extra or {})
    try:
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--figlio-guardia", scenario],
                             capture_output=True, text=True, env=amb, timeout=180, stdin=subprocess.DEVNULL)
        riga = [r for r in res.stdout.splitlines() if r.startswith("RISULTATO:")]
        dati = json.loads(riga[-1][len("RISULTATO:"):]) if riga else {"ERRORE": (res.stdout + res.stderr)[-800:]}
    except Exception as exc:  # noqa: BLE001
        dati = {"ERRORE": str(exc)}
    dati["registro"] = [r for r in registro.read_text().splitlines() if r.strip()]
    import shutil
    shutil.rmtree(base, ignore_errors=True)
    return dati


def amb_path() -> str:
    return os.environ.get("PATH", "/usr/bin:/bin")


def _di_sistema(righe):
    return [r for r in righe if r.split()[0] in ("launchctl", "schtasks", "systemctl", "crontab")]


def _prove_guardia_figlio(prova):
    d = _lancia_guardia("mac-prova", "mac")
    prova("[guardia mac] il figlio gira, con i programmi finti in testa al PATH", "ERRORE" not in d and "ABORT" not in d,
          str(d)[:600])
    prova("[guardia mac] HOME finta: NESSUN launchctl parte (ne' bootout ne' bootstrap), su on, off, riepilogo e domande",
          _di_sistema(d.get("registro", ["x"])) == [] and d.get("registro") is not None
          and (d.get("toccabile") or [True])[0] is False, str(d)[:600])
    prova("[guardia mac] i messaggi dicono 'file scritti, non caricati (HOME di prova)'",
          d.get("on") == "avvio automatico: file scritti, non caricati (HOME di prova)"
          and d.get("recap_on") == "riepilogo automatico: file scritti, non caricati (HOME di prova)",
          "%s | %s" % (d.get("on"), d.get("recap_on")))
    prova("[guardia mac] i plist si scrivono comunque nella casa finta, e off li toglie (senza scaricare niente)",
          "Library/LaunchAgents/com.plancia.server.plist" in d.get("file_on", [])
          and "Library/LaunchAgents/com.plancia.recap.plist" in d.get("file_on", [])
          and not [f for f in d.get("file_off", []) if f.endswith(".plist")]
          and "non scaricati" in str(d.get("off")) and "HOME di prova" in str(d.get("off"))
          and "non scaricati" in str(d.get("recap_off")), str(d)[:600])
    prova("[guardia mac] autostart_installed e riepilogo installato si leggono dai file, senza chiedere al sistema",
          d.get("installati", [None])[:2] == [True, True] and d.get("installati", [0, 0, ""])[2] == "launchd",
          str(d.get("installati")))

    # Su Windows `CreateProcess` trova un programma solo con l'estensione `.exe`: un
    # `launchctl` finto (`launchctl.cmd`) non partirebbe mai, e su Windows
    # launchctl non esiste. I due scenari che lo lanciano davvero (verso i finti)
    # non si possono fare li'; il ramo che NON lancia niente sta sopra e sotto.
    d = ({} if _finti.WIN else
         _lancia_guardia("mac-forza", "mac", {"PLANCIA_AUTOSTART_FORZA": "1"}))
    reg = [r for r in d.get("registro", [])]
    prova("[guardia mac] con PLANCIA_AUTOSTART_FORZA=1 i comandi partono (verso i finti): bootout e bootstrap "
          "del server e del riepilogo, e poi i bootout di off (il controllo che i finti funzionano)",
          _finti.WIN or "ERRORE" not in d and any(r.startswith("launchctl bootstrap gui/") and "com.plancia.server.plist" in r for r in reg)
          and any(r.startswith("launchctl bootstrap gui/") and "com.plancia.recap.plist" in r for r in reg)
          and sum(1 for r in reg if r.startswith("launchctl bootout")) >= 4
          and d.get("on") == "avvio automatico attivo: la dashboard riparte a ogni accesso",
          "saltato: su Windows launchctl non c'e' e un finto senza .exe non parte" if _finti.WIN
          else str(d)[:600])

    d = {} if _finti.WIN else _lancia_guardia("mac-casa-vera", "mac")
    reg = d.get("registro", [])
    prova("[guardia mac] se la HOME del processo e' la casa vera, i comandi partono senza nessuna variabile",
          _finti.WIN or "ERRORE" not in d and (d.get("toccabile") or [False])[0] is True
          and any("bootstrap" in r for r in reg) and d.get("on") == "avvio automatico attivo: la dashboard riparte a ogni accesso",
          "saltato: su Windows launchctl non c'e' e un finto senza .exe non parte" if _finti.WIN
          else str(d)[:600])

    d = _lancia_guardia("windows-prova", "windows")
    prova("[guardia windows] HOME finta: nessun schtasks; il .cmd di Esecuzione automatica NON finisce fuori dalla casa "
          "finta (APPDATA e' una variabile d'ambiente)",
          "ERRORE" not in d and "ABORT" not in d and _di_sistema(d.get("registro", ["x"])) == []
          and d.get("fuori") == [] and "non caricati (HOME di prova)" in str(d.get("on"))
          and "non caricati (HOME di prova)" in str(d.get("recap_on")), str(d)[:600])

    d = _lancia_guardia("linux-prova", "linux")
    prova("[guardia linux] HOME finta: nessun systemctl; niente scritto fuori dalla casa finta (XDG_CONFIG_HOME "
          "e' una variabile d'ambiente)",
          "ERRORE" not in d and "ABORT" not in d and _di_sistema(d.get("registro", ["x"])) == []
          and d.get("fuori") == [] and "non caricati (HOME di prova)" in str(d.get("on")), str(d)[:600])


def _prove_sistema_toccabile(prova):
    from plancia import piattaforma as pf

    with tempfile.TemporaryDirectory(prefix="plancia-toccabile-") as t:
        vera = Path(t) / "vera"
        finta = Path(t) / "finta"
        fuori = Path(t) / "altrove"
        for d in (vera, finta, fuori, vera / "dati"):
            d.mkdir()
        link = Path(t) / "link"
        try:
            link.symlink_to(vera)
            ha_link = True
        except (OSError, NotImplementedError):
            ha_link = False
        v = lambda: str(vera)  # noqa: E731

        def toccabile(casa=vera, ambiente=None, cv=v):
            return pf.sistema_toccabile(casa, ambiente if ambiente is not None else {}, cv)

        prova("sistema_toccabile: la HOME e' la casa vera -> si'",
              toccabile() == (True, ""), str(toccabile()))
        prova("sistema_toccabile: HOME diversa dalla casa vera -> no, 'HOME di prova'",
              toccabile(finta) == (False, "HOME di prova"), str(toccabile(finta)))
        if ha_link:
            prova("sistema_toccabile: la HOME e' un collegamento alla casa vera (realpath) -> si'",
                  toccabile(link) == (True, ""), str(toccabile(link)))
        prova("sistema_toccabile: PLANCIA_HOME dentro la casa vera -> si'",
              toccabile(ambiente={"PLANCIA_HOME": str(vera / "dati")}) == (True, "")
              and toccabile(ambiente={"PLANCIA_HOME": str(vera)}) == (True, ""))
        prova("sistema_toccabile: PLANCIA_HOME fuori dalla casa vera -> no, anche con la HOME giusta",
              toccabile(ambiente={"PLANCIA_HOME": str(fuori)}) == (False, "HOME di prova"),
              str(toccabile(ambiente={"PLANCIA_HOME": str(fuori)})))
        prova("sistema_toccabile: una cartella che comincia come la casa ma e' un'altra (vera2) -> no",
              toccabile(ambiente={"PLANCIA_HOME": str(vera) + "2"}) == (False, "HOME di prova"))
        prova("sistema_toccabile: PLANCIA_AUTOSTART_FORZA=1 vince su tutto, un altro valore no",
              toccabile(finta, {"PLANCIA_AUTOSTART_FORZA": "1"}) == (True, "")
              and toccabile(finta, {"PLANCIA_AUTOSTART_FORZA": "0"})[0] is False
              and toccabile(finta, {"PLANCIA_AUTOSTART_FORZA": "si"})[0] is False)
        r = toccabile(cv=lambda: None)
        prova("sistema_toccabile: se la casa vera non si legge, nel dubbio no (e lo dice)",
              r[0] is False and "non leggibile" in r[1], str(r))
        r = pf._casa_vera_windows()
        prova("_casa_vera_windows: dove non c'e' Windows torna None senza eccezioni (dove c'e', una cartella)",
              r is None or (os.name == "nt" and isinstance(r, str) and r), str(r))
        prova("casa_vera su POSIX: la casa dell'anagrafe utenti (pwd), non l'ambiente; una cartella che esiste",
              os.name == "nt" or (pf.casa_vera() is not None and os.path.isdir(pf.casa_vera())), str(pf.casa_vera()))
        with _ambiente(HOME=finta):
            if os.name != "nt":
                prova("casa_vera non segue HOME: con HOME finta la casa vera resta quella vera",
                      pf.casa_vera() != str(finta), str(pf.casa_vera()))

    # esegui: i programmi di sistema non partono da una HOME di prova
    lanciati = []

    def finto_run(argv, **k):
        lanciati.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    with _Finto(pf.subprocess, run=finto_run), _Finto(pf, sistema_toccabile=lambda *a, **k: (False, "HOME di prova")):
        esiti = [pf.esegui(a, capture_output=True, text=True) for a in (
            ["launchctl", "bootout", "gui/1/x"], ["/bin/launchctl", "bootstrap", "gui/1", "p"],
            ["schtasks.exe", "/Create"], ["C:\\Windows\\System32\\schtasks.exe", "/Delete"],
            ["systemctl", "--user", "enable", "x"], ["crontab", "-l"])]
        chiamati_dopo = list(lanciati)
        pf.esegui(["git", "status"], capture_output=True, text=True)
    prova("piattaforma.esegui: launchctl, schtasks(.exe, anche col percorso), systemctl e crontab NON partono da una "
          "HOME di prova (esito 127, stderr 'non eseguito')",
          chiamati_dopo == [] and all(e.returncode == 127 and "non eseguito" in e.stderr for e in esiti)
          and lanciati == [["git", "status"]], str((chiamati_dopo, lanciati)))
    lanciati.clear()
    with _Finto(pf.subprocess, run=finto_run), _Finto(pf, sistema_toccabile=lambda *a, **k: (True, "")):
        pf.esegui(["launchctl", "list"], capture_output=True, text=True)
    prova("piattaforma.esegui: dove il sistema e' toccabile il comando parte come prima",
          lanciati == [["launchctl", "list"]], str(lanciati))


# ==========================================================================
# 2. doctor: i contenitori in uso
# ==========================================================================

def _figlio_doctor_contenitori() -> None:
    casa = Path(os.environ["HOME"])
    dati = Path(os.environ["PLANCIA_HOME"])
    dati.mkdir(parents=True, exist_ok=True)
    scenario = os.environ["PLANCIA_PROVA_SCENARIO"]
    if scenario == "con-extra":
        (dati / "config.json").write_text(json.dumps({"contenitori": ["/Volumes/Disco/dev", "~/altro"]}))
    sys.path.insert(0, str(RADICE))
    from plancia import cli, piattaforma as pf, recap, store
    recap.claude_bin = lambda: ""
    conn = store.connect()
    store.init_db(conn)
    conn.close()
    pf.esegui = lambda argv, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="")
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        cli.main(["doctor"])
    print("RISULTATO:" + json.dumps(out.getvalue().splitlines()))


def _prove_doctor_contenitori(prova):
    for scenario in ("con-extra", "senza-extra"):
        casa = Path(tempfile.mkdtemp(prefix="plancia-doc-cont-"))
        amb = {k: v for k, v in os.environ.items() if k not in ("PLANCIA_AUTOSTART_FORZA",)}
        amb.update(HOME=str(casa), USERPROFILE=str(casa), PLANCIA_HOME=str(casa / ".plancia"),
                   CLAUDE_CONFIG_DIR=str(casa / ".claude"), CODEX_HOME=str(casa / ".codex"),
                   PLANCIA_PIATTAFORMA="mac", PLANCIA_PROVA_SCENARIO=scenario)
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--figlio-doctor-contenitori"],
                             capture_output=True, text=True, env=amb, timeout=180, stdin=subprocess.DEVNULL)
        import shutil
        shutil.rmtree(casa, ignore_errors=True)
        riga = [r for r in res.stdout.splitlines() if r.startswith("RISULTATO:")]
        if not riga:
            prova("[%s] il figlio di doctor gira" % scenario, False, (res.stdout + res.stderr)[-1200:])
            continue
        righe = json.loads(riga[-1][len("RISULTATO:"):])
        i = next((n for n, r in enumerate(righe) if "contenitori di progetti" in r), None)
        cont = righe[i:i + 2] if i is not None else []
        if scenario == "con-extra":
            prova("doctor elenca i contenitori in uso (~/dev, ~/Siti, ~/dev/siti) e quelli scritti in config.json",
                  any("~/dev" in r and "~/Siti" in r and "/Volumes/Disco/dev" in r and "~/altro" in r for r in cont)
                  and any(r.strip().startswith("scritti in config.json") and "/Volumes/Disco/dev" in r for r in cont),
                  "\n".join(cont))
        else:
            prova("doctor senza chiave `contenitori`: elenca quelli di Plancia e dice come aggiungerne (disco esterno)",
                  any(r.startswith("ok  contenitori di progetti") and "~/dev" in r for r in cont)
                  and any("nessuno scritto in config.json" in r and "`contenitori`" in r and "disco esterno" in r
                          for r in cont), "\n".join(cont))


def _prove_readme(prova):
    for nome in ("README.md", "README.it.md"):
        testo = (RADICE / nome).read_text("utf-8")
        prova("%s: dice PLANCIA_AUTOSTART_FORZA e che da una HOME di prova l'avvio automatico scrive i file e non li carica" % nome,
              "PLANCIA_AUTOSTART_FORZA" in testo and "HOME" in testo, "")
        prova("%s: dice che un disco esterno e' un contenitore solo se sta nella chiave `contenitori`, e che doctor li elenca" % nome,
              re.search(r"contenitori.{0,700}doctor|doctor.{0,700}contenitori", testo, re.S) is not None
              and re.search(r"(?i)(external disk|disco esterno)", testo) is not None, "")


# ==========================================================================
# 3. i minori
# ==========================================================================

def _prove_attribuzione_windows_maiuscole(prova):
    from plancia import attribuzione as a

    proj, altro = "C:\\Users\\x\\dev\\proj", "C:\\Users\\x\\dev\\other"
    with _Finto(a, os=_OsWindows()):
        # la cwd e la radice si scrivono con maiuscole diverse: e' la stessa cartella
        e = a.decidi("c:\\users\\x\\dev\\proj", [altro + "\\a.py"] * 3, {proj, altro}, set(), set())
        prova("[windows] decidi: la cwd 'c:\\users\\...' e la radice 'C:\\Users\\...' sono la stessa cartella: "
              "con tutti i percorsi su 'other' (sopra la soglia) vince other, e la cwd e' riconosciuta come "
              "radice nota (il caso del tester, dove invece tornava 'other' anche sotto la soglia: vedi dopo)",
              e["da"] == "percorsi" and a._k(e["dir"]) == a._k(altro), str(e))
        # cwd nota, percorsi misti sotto la soglia: deve vincere la cwd, con qualunque grafia
        e = a.decidi("c:\\users\\x\\dev\\proj",
                     [proj + "\\a.py"] * 3 + [altro + "\\b.py"] * 2, {proj, altro}, set(), set())
        prova("[windows] decidi: cwd con la lettera e le cartelle in minuscolo, percorsi con le maiuscole: "
              "sotto la soglia vince la cwd (proj), non 'other'",
              e["da"] == "cwd" and a._k(e["dir"]) == a._k(proj) and e["dir"] == ntpath.normpath(proj), str(e))
        e = a.decidi("C:\\USERS\\X\\DEV\\PROJ", [altro.lower() + "\\a.py"], {proj, altro}, set(), set())
        prova("[windows] decidi: la cwd tutta maiuscola e' riconosciuta come la radice registrata",
              a._k(e["dir"]) == a._k(altro) or a._k(e["dir"]) == a._k(proj), str(e))
        prova("[windows] radice_di: percorso e radice in grafie diverse; torna la grafia della radice",
              a.radice_di("c:\\USERS\\x\\Dev\\proj\\a.py", [proj]) == proj
              and a.radice_di("C:\\Users\\x\\dev\\proj2\\a.py", [proj]) is None)
        c = a.conta(["c:/users/x/dev/proj/a.py", "C:\\Users\\X\\Dev\\Proj\\b.py"], {proj})
        prova("[windows] conta: due grafie della stessa cartella contano insieme", list(c.values()) == [[2, 0]], str(c))
        prova("[windows] categoria: una cartella interna in un'altra grafia e' 'interna'; 'Temp' senza badare alle maiuscole",
              a.categoria("C:\\Users\\X\\.plancia\\a", {"c:\\users\\x\\.plancia"}) == "interna"
              and a.categoria("C:\\USERS\\X\\APPDATA\\LOCAL\\TEMP\\z") == "temporanea")
        e = a.decidi("C:\\Users\\X\\dev", [proj + "\\a.py"] * 3, {proj}, {"c:\\users\\x\\dev"}, set())
        prova("[windows] decidi: una cartella generica in un'altra grafia resta generica (non e' la cwd di un progetto)",
              e["da"] == "percorsi" and a._k(e["dir"]) == a._k(proj), str(e))

    # POSIX: uscite identiche a quelle misurate sulla base (le grafie diverse RESTANO diverse)
    e1 = a.decidi("/Users/ann/dev/proj", ["/Users/ann/dev/other/a"] * 3, {"/Users/ann/dev/proj", "/Users/ann/dev/other"},
                  set(), set())
    e2 = a.decidi("/Users/ann/dev/proj", ["/Users/ann/dev/proj/a"] * 3 + ["/Users/ann/dev/other/b"] * 2,
                  {"/Users/ann/dev/proj", "/Users/ann/dev/other"}, set(), set())
    e3 = a.decidi("/Users/ann/dev", ["/Users/ann/dev/proj/a"], {"/Users/ann/dev/proj"}, {"/Users/ann/dev"}, set())
    e4 = a.decidi("/Users/ann/DEV/proj", ["/Users/ann/dev/proj/a"], {"/Users/ann/dev/proj"}, set(), set())
    prova("[posix] decidi: le stesse uscite della base (compresa la differenza di maiuscole, che su POSIX conta)",
          e1 == {"dir": "/Users/ann/dev/other", "da": "percorsi", "n": 3, "categoria": "progetto"}
          and e2 == {"dir": "/Users/ann/dev/proj", "da": "cwd", "n": 5, "categoria": "progetto"}
          and e3 == {"dir": "/Users/ann/dev/proj", "da": "percorsi", "n": 1, "categoria": "progetto"}
          and e4 == {"dir": "/Users/ann/dev/proj", "da": "percorsi", "n": 1, "categoria": "progetto"},
          str([e1, e2, e3, e4]))
    prova("[posix] radice_di, conta e categoria: come prima",
          a.radice_di("/Users/ann/dev/proj/a", ["/Users/ann/dev/proj"]) == "/Users/ann/dev/proj"
          and a.radice_di("/users/ann/dev/proj/a", ["/Users/ann/dev/proj"]) is None
          and a.conta(["/a/b/c", "/a/b/d", "/a/x"], {"/a/b", "/a/x"}) == {"/a/b": [2, 0], "/a/x": [1, 2]}
          and a.categoria("/tmp/x") == "temporanea" and a.categoria("/Users/ann/dev/p", set()) == "progetto")


def _prove_percorsi_comando(prova):
    from plancia import attribuzione as a

    unc = r"\\server\share\dev\p\a.py"
    prova("percorsi_da_comando: un UNC nudo dentro un comando (`type \\\\server\\share\\...`) e' un percorso",
          a.percorsi_da_comando("type " + unc) == [unc], str(a.percorsi_da_comando("type " + unc)))
    prova("percorsi_da_comando: un UNC tra virgolette, con gli spazi",
          a.percorsi_da_comando('dir "\\\\server\\share\\my dir\\a.py"') == ["\\\\server\\share\\my dir\\a.py"],
          str(a.percorsi_da_comando('dir "\\\\server\\share\\my dir\\a.py"')))
    prova("percorsi_da_comando: UNC e lettera insieme, e il vecchio caso di file_path UNC",
          a.percorsi_da_comando("copy C:\\Users\\x\\dev\\p\\a " + unc)
          == [unc, "C:\\Users\\x\\dev\\p\\a"] or a.percorsi_da_comando("copy C:\\Users\\x\\dev\\p\\a " + unc)
          == ["C:\\Users\\x\\dev\\p\\a", unc], str(a.percorsi_da_comando("copy C:\\Users\\x\\dev\\p\\a " + unc)))
    prova("percorsi_da_comando: un doppio rovescio della shell (`printf 'a\\\\nb'`, `\\\\n`) non e' un UNC",
          a.percorsi_da_comando("printf 'a\\\\nb' && echo \\\\n") == []
          and a.percorsi_da_comando("echo \\\\ /Users/x/dev/p/a") == ["/Users/x/dev/p/a"])
    prova("percorsi_da_comando: `sed 's/a:\\/b\\/c\\/d/x/'` non da' nessun falso percorso (la lettera con i due punti "
          "in mezzo a un'espressione non e' un disco)",
          a.percorsi_da_comando("sed 's/a:\\/b\\/c\\/d/x/' /Users/x/dev/p/a") == ["/Users/x/dev/p/a"]
          and a.percorsi_da_comando("sed -i 's/x:\\\\y\\\\z\\\\w/q/' f") == [],
          str(a.percorsi_da_comando("sed 's/a:\\/b\\/c\\/d/x/' /Users/x/dev/p/a")))
    casi = {
        "cd /d C:\\Users\\x\\dev\\p": ["C:\\Users\\x\\dev\\p"],
        "run --path=C:\\Users\\x\\dev\\p": ["C:\\Users\\x\\dev\\p"],
        "(C:\\Users\\x\\dev\\p)": ["C:\\Users\\x\\dev\\p"],
        "type \"C:\\Users\\x\\dev\\p\" | more": ["C:\\Users\\x\\dev\\p"],
        "git -C 'C:/Users/x/dev/p' status": ["C:/Users/x/dev/p"],
        "C:\\Users\\x\\dev\\p\\run.bat": ["C:\\Users\\x\\dev\\p\\run.bat"],
        "echo hi;C:\\Users\\x\\dev\\p\\a": ["C:\\Users\\x\\dev\\p\\a"],
        "echo https://a.b/c s:/x C:/Users/zz /tmp/foo": [],
    }
    fuori = {k: a.percorsi_da_comando(k) for k in casi}
    prova("percorsi_da_comando: i percorsi di Windows che aprono un token (inizio, spazio, virgoletta, parentesi, `=`, `;`) "
          "si riconoscono ancora tutti", fuori == casi, str({k: v for k, v in fuori.items() if v != casi[k]}))
    prova("percorsi_da_tool_use: file_path UNC e glob UNC, come prima",
          a.percorsi_da_tool_use({"input": {"file_path": unc}}) == [unc]
          and a.percorsi_da_tool_use({"input": {"command": "type " + unc}}) == [unc])


class _RegistratoreProcessi:
    def __init__(self):
        self.lanci = []
        reg = self

        class Finto:
            pid = 4242

            def __init__(self, argv, **k):
                reg.lanci.append((list(argv), k))

            def poll(self):
                return 0

            def wait(self, *a, **k):
                return 0

            def terminate(self):
                pass

        self.classe = Finto


def _prove_afplay(prova):
    import subprocess as sp
    from plancia import voice

    for piatt, atteso in (("mac", {"stdout", "stderr"}), ("linux", {"stdout", "stderr", "stdin"}),
                          ("windows", {"stdout", "stderr", "stdin"})):
        reg = _RegistratoreProcessi()
        from plancia import piattaforma as _pf
        # dove il lettore e' installato (su Windows PowerShell): la prova guarda gli argomenti
        with _ambiente(PLANCIA_PIATTAFORMA=piatt), _Finto(sp, Popen=reg.classe), \
                _Finto(_pf, cerca=lambda programma: "/x/" + programma):
            try:
                voice.riproduci("/tmp/o.wav")
            except Exception as exc:  # noqa: BLE001
                reg.lanci.append((["ECCEZIONE", str(exc)], {}))
            voice._riproduzione = None
        argv, k = reg.lanci[0] if reg.lanci else (None, {})
        if piatt == "mac":
            prova("[mac] afplay parte con gli stessi argomenti della base: stdout e stderr su DEVNULL, NIENTE stdin "
                  "(e nessun creationflags)",
                  argv == ["afplay", "/tmp/o.wav"] and set(k) == atteso
                  and k["stdout"] == sp.DEVNULL and k["stderr"] == sp.DEVNULL, str((argv, k)))
        else:
            prova("[%s] il lettore parte con lo stdin chiuso (serve a PowerShell e ai lettori di Linux)" % piatt,
                  argv is not None and argv[0] != "afplay" and atteso <= set(k) and k["stdin"] == sp.DEVNULL,
                  str((argv, k)))


class _ServerLento(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    ritardo = 2.6
    nome = "Plancia/1.0"

    def do_GET(self):
        time.sleep(self.ritardo)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def version_string(self):
        return self.nome

    def log_message(self, *a):
        pass


def _porta_libera():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _prove_serve_lento(prova):
    from plancia import cli

    prova("il controllo della porta di serve aspetta piu' di 2 secondi (un Plancia sotto carico)",
          (getattr(cli, "_ATTESA_STATO", 0) or 0) >= 5, str(getattr(cli, "_ATTESA_STATO", None)))

    # un Plancia che risponde dopo 2,6 secondi e' ancora Plancia (con 2 secondi di attesa era "altro")
    porta = _porta_libera()
    srv = HTTPServer(("127.0.0.1", porta), _ServerLento)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        chi = cli._chi_ascolta(porta)
    finally:
        srv.shutdown()
        srv.server_close()
    prova("un Plancia che risponde dopo 2,6 secondi (macchina sotto carico) e' riconosciuto come Plancia, non 'altro'",
          chi == "plancia", str(chi))

    # una porta aperta che non risponde: "muto", non "un altro programma"
    muto = socket.socket()
    muto.bind(("127.0.0.1", 0))
    muto.listen(5)
    pm = muto.getsockname()[1]
    try:
        with _Finto(cli, _ATTESA_STATO=1):
            chi = cli._chi_ascolta(pm)
            args = types.SimpleNamespace(port=pm, open=False, no_sync=True)
            err = io.StringIO()
            from plancia import api

            def _no(*a, **k):
                raise AssertionError("api.serve non deve partire")
            with _Finto(api, serve=_no), contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = cli.cmd_serve(args)
    finally:
        muto.close()
    prova("una porta aperta che non risponde in tempo e' 'muto'; `serve` dice 'forse da Plancia che non risponde' "
          "(non 'un altro programma'), rc 1, e non avvia niente",
          chi == "muto" and rc == 1 and "forse da Plancia che non risponde" in err.getvalue()
          and "un altro programma" not in err.getvalue(), "%s %s %r" % (chi, rc, err.getvalue()))

    # un altro programma che risponde in fretta (non e' Plancia): resta "un altro programma"
    porta = _porta_libera()
    with _Finto(_ServerLento, ritardo=0, nome="Altro/2"):
        srv = HTTPServer(("127.0.0.1", porta), _ServerLento)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            chi = cli._chi_ascolta(porta)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = cli._porta_occupata(porta, chi)
        finally:
            srv.shutdown()
            srv.server_close()
    prova("un altro programma che risponde: 'altro' e il messaggio di prima (non e' Plancia), rc 1",
          chi == "altro" and rc == 1 and "un altro programma (non e' Plancia)" in err.getvalue(),
          "%s %s %r" % (chi, rc, err.getvalue()))
    prova("porta libera: None", cli._chi_ascolta(_porta_libera()) is None)


def _prove_contenitori_come_la_base(prova):
    """Su macOS le liste sono quelle della base 4a89241 (`attribuzione.contenitori` e
    `radici_generiche`), meno il disco scritto a mano, che ora sta nella chiave
    `contenitori` di config.json: con la chiave, e' di nuovo contenitore e generico e le
    sue sottocartelle sono radici di progetto (il caso trovato dal tester)."""
    from plancia import attribuzione as a, config

    with tempfile.TemporaryDirectory(prefix="plancia-cont-base-") as t:
        casa = Path(t) / "casa"
        drive = Path(t) / "drive"
        disco = Path(t) / "disco" / "dev"
        dati = Path(t) / "dati"
        for d in (casa, drive, dati, disco / "uno", disco / "due", casa / "dev" / "p"):
            d.mkdir(parents=True)
        with _Finto(config, CONFIG_FILE=dati / "config.json", DATA_DIR=dati):
            atteso_cont = [str(casa / "dev"), str(casa / "Siti"), str(casa / "dev" / "siti"),
                           str(drive / "Lavoro"), str(drive / "Personale")]
            atteso_gen = {str(casa), str(casa / "dev"), str(casa / "Siti"), str(casa / "dev" / "siti"),
                          str(casa / "Documents" / "Codex"), str(dati), str(drive),
                          str(drive / "Lavoro"), str(drive / "Personale")}
            prova("[mac] senza la chiave: contenitori() e radici_generiche() sono la lista della base (senza il disco a mano)",
                  a.contenitori(str(casa), str(drive)) == atteso_cont
                  and a.radici_generiche(str(casa), str(drive)) == atteso_gen,
                  str((a.contenitori(str(casa), str(drive)), sorted(a.radici_generiche(str(casa), str(drive))))))
            prova("[mac] contenitori_avviso() = la radice del Drive + contenitori(): la stessa regola dell'hook",
                  a.contenitori_avviso(str(casa), str(drive)) == [str(drive)] + atteso_cont)
            (dati / "config.json").write_text(json.dumps({"contenitori": [str(disco)]}))
            note = a.radici_note(None, str(casa), str(drive))
            prova("[mac] con il disco nella chiave `contenitori`: e' contenitore e generico, e le sue sottocartelle "
                  "sono radici di progetto (come prima con il disco scritto a mano)",
                  str(disco) in a.contenitori(str(casa), str(drive))
                  and str(disco) in a.radici_generiche(str(casa), str(drive))
                  and {str(disco / "uno"), str(disco / "due")} <= note and str(disco) not in note
                  and str(casa / "dev" / "p") in note, str(sorted(note)))
            (dati / "config.json").write_text("{}")
            note = a.radici_note(None, str(casa), str(drive))
            prova("[mac] senza la chiave il disco non e' un contenitore: nessuna radice di progetto li' sotto "
                  "(e' quello che il README e `plancia doctor` dicono)",
                  not any(str(disco.parent) in r for r in note), str(sorted(note)))


def _prove_attribuzione_commento(prova):
    testo = (RADICE / "plancia" / "attribuzione.py").read_text("utf-8")
    i = testo.index("#: Le cartelle sotto cui ogni sottocartella")
    resto = testo[i:].split("\n", 2)[1]
    prova("attribuzione.py: il commento 'Le cartelle sotto cui...' sta sopra contenitori(), non sopra contenitori_extra()",
          resto.startswith("def contenitori(home=None, drive=None)"), resto)


# --------------------------------------------------------------------------

def esegui(prova):
    def gruppo(f):
        try:
            f(prova)
        except Exception as exc:  # noqa: BLE001
            import traceback
            prova("%s: nessuna eccezione" % f.__name__, False,
                  "%s: %s %s" % (type(exc).__name__, exc, traceback.format_exc()[-800:]))

    gruppo(_prove_guardia_figlio)
    gruppo(_prove_sistema_toccabile)
    gruppo(_prove_doctor_contenitori)
    gruppo(_prove_readme)
    gruppo(_prove_attribuzione_windows_maiuscole)
    gruppo(_prove_percorsi_comando)
    gruppo(_prove_afplay)
    gruppo(_prove_serve_lento)
    gruppo(_prove_contenitori_come_la_base)
    gruppo(_prove_attribuzione_commento)


if __name__ == "__main__":
    if "--figlio-guardia" in sys.argv:
        _figlio_guardia(sys.argv[sys.argv.index("--figlio-guardia") + 1])
        sys.exit(0)
    if "--figlio-doctor-contenitori" in sys.argv:
        _figlio_doctor_contenitori()
        sys.exit(0)
    if "PLANCIA_HOME" not in os.environ:
        os.environ["PLANCIA_HOME"] = tempfile.mkdtemp(prefix="plancia-prova-guardia-")
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
