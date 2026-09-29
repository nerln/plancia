"""Quello che il primo giro completo di GitHub su Windows ha mostrato, e che i
lotti precedenti non potevano vedere dal Mac.

Il collaudo su `windows-latest` (run 36573487970) ha fatto girare `tools/prova.py`
fino in fondo per la prima volta e ha dato una serie di NO. Alcuni erano
aspettative POSIX delle prove (percorsi finti alla POSIX che su Windows si
normalizzano con la barra rovesciata, `HOME` che su Windows non sposta la casa,
uno script di `bin/` lanciato senza interprete: WinError 193). Altri sono
difetti del programma, che qui si provano con le funzioni pure e con
un Windows imitato, senza lanciare niente di vero:

1. l'attribuzione riconosce le cartelle temporanee anche quando il percorso e'
   stato normalizzato da Windows (`\\private\\tmp`);
2. i figli di cui si legge testo (`claude`, `codex`, `git`, `gh`) parlano UTF-8:
   su Windows `text=True` da solo usa cp1252, e un accento arriva come `Ã¨` (o
   una `UnicodeDecodeError` per i byte che cp1252 non ha); `opzioni_utf8` lo
   dice, su macOS e Linux torna `{}`;
3. l'uscita di `plancia` su Windows e' UTF-8 anche rediretta;
4. il padre di un progetto e le radici dei progetti si riconoscono anche con un
   percorso di Windows (rovesci, maiuscole, barra finale);
5. i programmi finti che le prove costruiscono (`_finti.crea_finto`) partono
   davvero su questo sistema, e vi arrivano gli argomenti;
6. (secondo giro, run 36582338633) le cartelle escluse con la lettera di unita': la
   radice di `C:\\` non e' una cartella dentro `\\`, e ogni `cartelle_escluse` risultava
   «inesistente» (config invalida, fail-closed: niente entrava piu' nell'archivio);
   il progetto di una cwd si riconosce anche con il link scritto con altre barre o
   altre maiuscole. Provati con un `os` di Windows imitato su un albero finto.

Per lanciare da sola: `python3 tools/prove/windows-testo.py`.
"""

import ast
import contextlib
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


class _OsNt:
    """Un `os` che si dichiara Windows (`name == "nt"`), il resto e' quello vero."""

    name = "nt"

    def __getattr__(self, nome):
        return getattr(os, nome)


@contextlib.contextmanager
def _windows_imitato(pf, **sostituzioni):
    """`piattaforma` come su un Windows vero: la piattaforma e' Windows e `os.name`
    e' `nt`. `subprocess.run` e' quello che passa `sostituzioni['run']`."""
    vecchie_env = os.environ.get("PLANCIA_PIATTAFORMA")
    os.environ["PLANCIA_PIATTAFORMA"] = "windows"
    vecchio_os, vecchio_run = pf.os, pf.subprocess.run
    pf.os = _OsNt()
    if "run" in sostituzioni:
        pf.subprocess.run = sostituzioni["run"]
    try:
        yield
    finally:
        pf.os, pf.subprocess.run = vecchio_os, vecchio_run
        if vecchie_env is None:
            os.environ.pop("PLANCIA_PIATTAFORMA", None)
        else:
            os.environ["PLANCIA_PIATTAFORMA"] = vecchie_env


class _Flusso:
    """Un finto stdout che si ricorda come e' stato riconfigurato."""

    def __init__(self):
        self.chiamate = []

    def reconfigure(self, **kw):
        self.chiamate.append(kw)


def _prove_attribuzione(prova):
    from plancia import attribuzione as a

    prova("temporanea: /private/tmp e /tmp, con la barra di POSIX",
          all(a.TEMPORANEA.search(p) for p in ("/private/tmp/claude-501/x/scratchpad", "/tmp/x",
                                               "/private/var/folders/j7/x/T/drift-ab12/p")))
    prova("temporanea: gli stessi percorsi dopo la normalizzazione di Windows (rovesci)",
          all(a.TEMPORANEA.search(p) for p in ("\\private\\tmp\\claude-501\\x\\scratchpad", "\\tmp\\x",
                                               "\\private\\var\\folders\\j7\\x\\T\\drift-ab12\\p")))
    prova("temporanea: la cartella Temp di Windows, in tutte le grafie",
          all(a.TEMPORANEA.search(p) for p in ("C:\\Users\\x\\AppData\\Local\\Temp\\plancia-prova-1",
                                               "c:/users/x/appdata/local/temp/y")))
    prova("temporanea: un progetto che si chiama 'tmp' o sta sotto 'tmpl' non e' temporaneo",
          not any(a.TEMPORANEA.search(p) for p in ("/Users/x/dev/tmp", "/Users/x/dev/tmp/y", "/tmpl/x",
                                                   "C:\\Users\\x\\dev\\tmp")))
    prova("senza_barra_finale: POSIX e Windows",
          a.senza_barra_finale("/a/b/") == "/a/b" and a.senza_barra_finale("/a/b") == "/a/b"
          and a.senza_barra_finale("C:\\a\\b\\") == "C:\\a\\b"
          and a.senza_barra_finale("C:/a/b/") == "C:/a/b" and a.senza_barra_finale("C:\\") == "C:\\")
    prova("e_dentro: POSIX, sui confini di cartella",
          a.e_dentro("/a/b", "/a/b") and a.e_dentro("/a/b", "/a/b/c") and not a.e_dentro("/a/b", "/a/bar")
          and not a.e_dentro("", "/a") and not a.e_dentro("/a/b/c", "/a/b"))
    prova("e_dentro: Windows, rovesci, barre e maiuscole sono la stessa cartella",
          a.e_dentro("C:\\Users\\x\\Progetto", "c:/users/x/progetto/sub/file.py")
          and a.e_dentro("C:\\Users\\x\\Progetto\\", "C:\\Users\\x\\Progetto")
          and not a.e_dentro("C:\\Users\\x\\Progetto", "C:\\Users\\x\\ProgettoDue"))


def _prove_padre_windows(prova):
    from plancia import riordina, slot, store

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    store.init_db(conn)
    vesuvius = store.upsert_project(conn, "vesuvius", "vesuvius", auto=0, _force=True)
    op6 = store.upsert_project(conn, "op6-causal", "op6-causal", auto=0, _force=True)
    store.link_project(conn, vesuvius, "path", "C:\\Users\\e\\dev\\vesuvius-agosto-2026\\")
    store.link_project(conn, op6, "path", "C:\\Users\\e\\dev\\vesuvius-agosto-2026\\tools\\op6")
    conn.commit()

    r = slot.padre_per_path(conn, "C:\\Users\\e\\dev\\vesuvius-agosto-2026\\src\\main.py")
    prova("Windows: un cwd sotto il percorso di un manuale trova il manuale", r == "vesuvius", str(r))
    r = slot.padre_per_path(conn, "c:/users/e/dev/vesuvius-agosto-2026/src")
    prova("Windows: anche con le barre in avanti e le maiuscole diverse", r == "vesuvius", str(r))
    r = slot.padre_per_path(conn, "C:\\Users\\e\\dev\\vesuvius-agosto-2026\\tools\\op6\\src")
    prova("Windows: il percorso piu' lungo vince", r == "op6-causal", str(r))
    r = slot.padre_per_path(conn, "C:\\Users\\e\\dev\\vesuvius-agosto-2026x\\src")
    prova("Windows: una cartella che comincia allo stesso modo ma e' un'altra non conta", r is None, str(r))
    r = slot.padre_per_path(conn, "D:\\altrove\\vesuvius-agosto-2026\\")
    prova("Windows: il nome della cartella, con la barra finale, trova il manuale per prefisso",
          r == "vesuvius", str(r))
    prova("riordina._dentro: Windows come POSIX",
          riordina._dentro("C:\\a\\b\\", "c:/a/b/c") and not riordina._dentro("C:\\a\\b", "C:\\a\\bc")
          and riordina._dentro("/a/b/", "/a/b/c") and not riordina._dentro("/a/b", "/a/bc"))
    conn.close()


def _prove_utf8(prova):
    from plancia import piattaforma as pf

    prova("opzioni_utf8: {} su macOS, Linux e su un host che non e' Windows davvero",
          pf.opzioni_utf8("mac") == {} and pf.opzioni_utf8("linux") == {}
          and pf.opzioni_utf8("windows", nt=False) == {})
    prova("opzioni_utf8: su Windows vero UTF-8, con i byte sbagliati che non fanno cadere la lettura",
          pf.opzioni_utf8("windows", nt=True) == {"encoding": "utf-8", "errors": "replace"})

    # `esegui` con text=True su Windows: l'uscita di schtasks e simili e' nella tabella OEM
    chiamate = []

    def run_finto(argv, **kw):
        chiamate.append((argv, kw))
        return subprocess.CompletedProcess(argv, 0, "", "")

    with _windows_imitato(pf, run=run_finto):
        pf.esegui(["programma", "a"], capture_output=True, text=True)
        pf.esegui(["programma", "b"], capture_output=True)
        pf.esegui(["programma", "c"], capture_output=True, text=True, encoding="utf-8")
    kw_testo, kw_byte, kw_utf8 = chiamate[0][1], chiamate[1][1], chiamate[2][1]
    prova("esegui su Windows: con text=True i byte che la tabella non ha diventano un segnaposto",
          kw_testo.get("errors") == "replace" and "encoding" not in kw_testo, str(kw_testo))
    prova("esegui su Windows: senza text=True (byte) non si tocca niente",
          "errors" not in kw_byte and "encoding" not in kw_byte, str(kw_byte))
    prova("esegui su Windows: chi ha gia' scelto la sua codifica la tiene",
          kw_utf8.get("encoding") == "utf-8", str(kw_utf8))

    chiamate.clear()
    vero = os.environ.get("PLANCIA_PIATTAFORMA")
    os.environ["PLANCIA_PIATTAFORMA"] = "mac"
    vecchio_run = pf.subprocess.run
    pf.subprocess.run = run_finto
    try:
        pf.esegui(["programma", "a"], capture_output=True, text=True)
    finally:
        pf.subprocess.run = vecchio_run
        if vero is None:
            os.environ.pop("PLANCIA_PIATTAFORMA", None)
        else:
            os.environ["PLANCIA_PIATTAFORMA"] = vero
    prova("esegui su macOS: nessuna opzione in piu' rispetto a prima",
          set(chiamate[0][1]) == {"capture_output", "text"}, str(chiamate[0][1]))

    # sul sorgente: chi legge TESTO da claude, codex, git o gh lo dice in UTF-8
    senza = []
    for f in sorted((RADICE / "plancia").glob("*.py")):
        if f.name == "piattaforma.py":
            continue
        albero = ast.parse(f.read_text("utf-8"))
        for nodo in ast.walk(albero):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr in ("run", "Popen")
                    and isinstance(nodo.func.value, ast.Name) and nodo.func.value.id == "subprocess"):
                testo = any(kw.arg in ("text", "universal_newlines")
                            and isinstance(kw.value, ast.Constant) and kw.value.value is True
                            for kw in nodo.keywords)
                dice = any(kw.arg is None and isinstance(kw.value, ast.Call)
                           and isinstance(kw.value.func, ast.Attribute)
                           and kw.value.func.attr == "opzioni_utf8" for kw in nodo.keywords)
                if testo and not dice:
                    senza.append("%s:%d" % (f.name, nodo.lineno))
    prova("ogni subprocess.run/Popen in plancia/ con text=True porta **piattaforma.opzioni_utf8()",
          not senza, str(senza))

    # l'uscita di `plancia`
    vero = _Flusso()
    pf.uscita_utf8(nt=True, flussi=(vero, None))
    prova("uscita_utf8 su Windows: stdout e stderr scrivono UTF-8, e un flusso assente (pythonw) non rompe",
          vero.chiamate == [{"encoding": "utf-8", "errors": "replace"}], str(vero.chiamate))
    altro = _Flusso()
    pf.uscita_utf8(nt=False, flussi=(altro,))
    prova("uscita_utf8 su macOS e Linux: non tocca niente", altro.chiamate == [], str(altro.chiamate))
    prova("cli.main chiama uscita_utf8 prima di leggere gli argomenti",
          "piattaforma.uscita_utf8()" in (RADICE / "plancia" / "cli.py").read_text("utf-8")
          .split("def main(")[1].split("build_parser()")[0])


def _prove_porta_occupata(prova):
    """Una seconda copia del server sulla stessa porta non si aggancia (su Windows,
    con `SO_REUSEADDR`, si agganciava)."""
    from plancia import api

    prova("il server: SO_REUSEADDR acceso solo dove serve (non su Windows)",
          api._Server.allow_reuse_address == (os.name != "nt"), str(api._Server.allow_reuse_address))
    primo = api._Server(("127.0.0.1", 0), api.Handler)
    porta = primo.server_address[1]
    try:
        try:
            secondo = api._Server(("127.0.0.1", porta), api.Handler)
            secondo.server_close()
            errore = ""
        except OSError as exc:
            errore = type(exc).__name__
        prova("un secondo server sulla stessa porta occupata non parte (errore di porta occupata)",
              bool(errore), "si e' agganciato lo stesso")
    finally:
        primo.server_close()


def _prove_finti(prova):
    """I programmi finti delle prove partono davvero su questo sistema."""
    with tempfile.TemporaryDirectory(prefix="plancia-prova-finti-") as t:
        uscita = Path(t) / "uscita.txt"
        finto = _finti.crea_finto(
            t, "finto",
            "import sys\n"
            f"open({str(uscita)!r}, 'w', encoding='utf-8').write('|'.join(sys.argv[1:]))\n"
            "sys.exit(3)\n")
        esito = subprocess.run([finto, "un argomento con spazi", "due"], capture_output=True)
        letto = uscita.read_text("utf-8") if uscita.exists() else ""
        prova("un programma finto (crea_finto) parte da solo su questo sistema, con i suoi argomenti",
              letto == "un argomento con spazi|due", repr(letto))
        prova("...e il suo codice di uscita arriva a chi lo ha lanciato", esito.returncode == 3,
              str(esito.returncode))
        prova("...e sta in PATH con il suo nome (shutil.which lo trova)",
              _finti.crea_finto(t, "finto-nel-path", "pass\n") and
              __import__("shutil").which("finto-nel-path", path=t) is not None)

    casa = Path(tempfile.gettempdir()) / "casa-finta"
    env = _finti.casa_finta({}, casa)
    prova("casa_finta: HOME sempre, e su Windows anche USERPROFILE e le cartelle dati",
          env["HOME"] == str(casa)
          and (not _finti.WIN or (env["USERPROFILE"] == str(casa)
                                  and env["LOCALAPPDATA"].startswith(str(casa)))), str(env))
    prova("path_con: la cartella data e' la prima del PATH",
          _finti.path_con("/x/finti").split(os.pathsep)[0] == "/x/finti")


class _PathNt:
    """`ntpath` con le sole funzioni che toccano il disco sostituite da un albero
    finto: `realpath` normalizza soltanto, `isdir` guarda l'albero."""

    def __init__(self, sistema):
        self._s = sistema

    def __getattr__(self, nome):
        return getattr(ntpath, nome)

    def realpath(self, p):
        return ntpath.normpath(p)

    def isdir(self, p):
        return self._s.cerca(p) is not None


class _EntrataFinta:
    def __init__(self, name):
        self.name = name


class _OsNtFinto:
    """Un `os` che si comporta da Windows su un albero di cartelle finto
    (`{"C:\\": {"Users": {"Ann": {"Privato": {}}}}}`), il resto e' quello vero."""

    sep = "\\"
    name = "nt"

    def __init__(self, albero):
        self.albero = albero
        self.path = _PathNt(self)

    def cerca(self, p):
        unita, resto = ntpath.splitdrive(p)
        nodo = None
        for chiave, valore in self.albero.items():
            if ntpath.normcase(chiave.rstrip("\\")) == ntpath.normcase(unita):
                nodo = valore
        if nodo is None:
            return None
        for pezzo in [x for x in resto.replace("/", "\\").split("\\") if x]:
            trovato = next((v for k, v in nodo.items() if k.lower() == pezzo.lower()), None)
            if trovato is None:
                return None
            nodo = trovato
        return nodo

    def scandir(self, p):
        nodo = self.cerca(p)
        if nodo is None:
            raise FileNotFoundError(p)
        return [_EntrataFinta(k) for k in nodo]

    def __getattr__(self, nome):
        return getattr(os, nome)


def _prove_esclusi_windows(prova):
    from plancia import config, esclusi

    albero = {"C:\\": {"Users": {"Ann": {"Privato": {"Sotto": {}}, "Progetti": {}, ".plancia": {}}}}}
    finto = _OsNtFinto(albero)
    vecchi = esclusi.os
    esclusi.os = finto
    try:
        vera = esclusi._grafia_vera("C:/users/ann/PRIVATO")
        prova("esclusi._grafia_vera su Windows: la lettera di unita' non e' una cartella dentro la radice; "
              "torna la grafia vera di ogni pezzo",
              vera == "C:\\Users\\Ann\\Privato", str(vera))
        prova("esclusi._grafia_vera su Windows: una cartella che non esiste da' None",
              esclusi._grafia_vera("C:\\Users\\Ann\\Non-c-e") is None
              and esclusi._grafia_vera("D:\\Users") is None)
        prova("esclusi._senza_fine: la radice dell'unita' resta `C:\\`, una cartella perde la barra finale",
              esclusi._senza_fine("C:\\") == "C:\\" and esclusi._senza_fine("C:\\Users\\") == "C:\\Users"
              and esclusi._senza_fine("C:\\Users") == "C:\\Users")

        home = "C:\\Users\\Ann"
        vecchie = config.HOME, config.CLAUDE_DIR, config.DATA_DIR
        config.HOME, config.CLAUDE_DIR, config.DATA_DIR = home, home + "\\.claude", home + "\\.plancia"
        try:
            ok, err, cartelle, _ = esclusi.valida({"cartelle_escluse": ["C:/users/ann/privato"]})
            prova("esclusi.valida su Windows: una cartella esclusa esistente e' valida, nella grafia vera",
                  ok and cartelle == ["C:\\Users\\Ann\\Privato"], str((ok, err, cartelle)))
            ok2, err2, *_ = esclusi.valida({"cartelle_escluse": ["C:\\Users\\Ann\\Non-c-e"]})
            prova("esclusi.valida su Windows: una cartella che non esiste e' ancora «inesistente»",
                  not ok2 and "inesistente" in (err2 or ""), str(err2))
            ok3, err3, *_ = esclusi.valida({"cartelle_escluse": ["C:\\"]})
            prova("esclusi.valida su Windows: la radice dell'unita' non si esclude",
                  not ok3, str(err3))
            ok4, err4, *_ = esclusi.valida({"cartelle_escluse": ["C:\\Users"]})
            prova("esclusi.valida su Windows: una cartella che contiene la casa e' troppo ampia",
                  not ok4 and "troppo ampia" in (err4 or ""), str(err4))
        finally:
            config.HOME, config.CLAUDE_DIR, config.DATA_DIR = vecchie

        esc = {"cartelle": ["C:\\Users\\Ann\\Privato"], "codifiche": ["C--Users-Ann-Privato"], "sessioni": set()}
        prova("esclusi.percorso_escluso su Windows: la cartella, le sue sottocartelle, con barre e maiuscole "
              "diverse; non una cartella che comincia allo stesso modo",
              esclusi.percorso_escluso("c:/USERS/ann/privato", esc)
              and esclusi.percorso_escluso("C:\\Users\\Ann\\Privato\\Sotto\\a.py", esc)
              and not esclusi.percorso_escluso("C:\\Users\\Ann\\Privato2", esc)
              and not esclusi.percorso_escluso("C:\\Users\\Ann", esc))
        prova("esclusi.progetto_escluso su Windows: il nome codificato della cartella non distingue le maiuscole",
              esclusi.progetto_escluso("c--users-ann-privato", esc)
              and esclusi.progetto_escluso("C--Users-Ann-Privato-sotto", esc)
              and not esclusi.progetto_escluso("C--Users-Ann-Privato2", esc))
    finally:
        esclusi.os = vecchi

    # macOS e Linux: la radice e' `/`, `_senza_fine` e `_sotto` sono quelli di sempre
    prova("esclusi su POSIX: la radice resta `/`, una cartella perde la barra finale, `_sotto` sui confini",
          esclusi._senza_fine("/") == "/" and esclusi._senza_fine("/a/b/") == "/a/b"
          and esclusi._sotto("/a/b/c", "/a/b") and not esclusi._sotto("/a/bc", "/a/b")
          and not esclusi._sotto("/a/b", "/a/b") and esclusi._uguale("/a/b", "/a/b")
          and not esclusi._uguale("/a/B", "/a/b") if os.name != "nt" else True,
          "saltato: percorsi POSIX" if os.name == "nt" else "")


def _prove_resolve_path_windows(prova):
    """Un link `path` scritto a mano (barre in avanti, altre maiuscole) e la cwd che
    arriva normalizzata da Windows sono la stessa cartella."""
    from plancia import ingest, store

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    store.init_db(conn)
    pid = store.upsert_project(conn, "proj-w", "proj-w", auto=0, _force=True)
    store.link_project(conn, pid, "path", "C:/Dev/Proj")
    conn.commit()
    trovato = [ingest.resolve_path_project(conn, p) for p in (
        "c:\\dev\\proj", "C:\\DEV\\Proj\\src\\a.py", "C:/dev/proj/sub", "C:\\dev\\proj2", "D:\\dev\\proj")]
    conn.close()
    prova("ingest.resolve_path_project: il link scritto con le barre in avanti e altre maiuscole trova la cwd "
          "di Windows (e non una cartella che comincia allo stesso modo, ne' un'altra unita')",
          trovato == [pid, pid, pid, None, None], str(trovato))


def esegui(prova):
    _prove_esclusi_windows(prova)
    _prove_resolve_path_windows(prova)
    _prove_attribuzione(prova)
    _prove_padre_windows(prova)
    _prove_utf8(prova)
    _prove_porta_occupata(prova)
    _prove_finti(prova)


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

    os.environ.setdefault("PLANCIA_HOME", tempfile.mkdtemp(prefix="plancia-prova-wt-"))
    esegui(_prova)
    print(f"\n{passate} passate, {fallite} fallite")
    sys.exit(1 if fallite else 0)
