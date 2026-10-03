"""Prove per LOTTO-L3-RIPRENDI-UI-2 (correzioni del critico): due difetti di
`plancia/jarvis.py` che il primo giro del lotto non copriva.

1. Le proposte di tipo "manda" con un `task_id` sono lo stesso "Riprendi" del
   drawer (LOTTO-L3-RIPRENDI-UI punto 2: "le proposte di tipo manda passano
   dallo stesso endpoint"): su un task con sessione chiusa devono forkare
   (`--resume <sid> --fork-session`), non ripartire da zero.
2. La frase vocale di "riprendi il task N" in inglese/spagnolo non deve
   pronunciare il `motivo` in italiano (es. "creato su altra-macchina"): va
   tradotto con la stessa tabella di prefissi che web/app.js usa per `Tmot()`.

Isolamento (mai un `claude`/`codex` vero, mai i dati veri della macchina):
`cantiere.subprocess.Popen` sostituito con un processo finto per il primo
punto; per il secondo basta un task "creato su" un host diverso da quello
vero, che `riprendi.stato()` decide senza toccare il disco né la rete, ma
`PLANCIA_TERMINALE` è comunque impostato su uno script finto perché
la conferma di `riprendi_task` chiama `riprendi.apri()`.

`esegui(prova)` è la firma che `tools/prova.py` scopre da sola in
`tools/prove/*.py`; per lanciare solo questo modulo, il blocco `__main__`
in fondo.
"""

import contextlib
import json
import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent


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
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


def _esegui_frase(jarvis, frase, lang, conn):
    """Una frase detta a Jarvis, portata fino in fondo come fa una persona: la scheda
    che ne esce (se ne esce una) si conferma, e si torna l'esito della conferma. Dal
    22-SERVER niente parte da una frase da solo: lo dice la scheda, lo fa il pulsante."""
    esito = jarvis.esegui(frase, lang, conn=conn)
    proposta = esito.get("proposta")
    if proposta:
        return jarvis.conferma(proposta["id"], lang, conn=conn)
    return esito


@contextlib.contextmanager
def _ambiente(**valori):
    vecchi = {}
    for k, v in valori.items():
        vecchi[k] = os.environ.get(k)
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


class _ProcessoFinto:
    """Sostituisce il processo vero che `subprocess.Popen` avrebbe lanciato
    (mai un `claude`/`codex` vero): stessa forma di quello in
    tools/prove/api-riprendi.py."""
    pid = 999998
    returncode = 0

    class _Stdin:
        def write(self, s):
            pass

        def close(self):
            pass

    def __init__(self):
        self.stdin = self._Stdin()
        self.stdout = iter(())

    def wait(self, timeout=None):
        return 0


_CARTELLA_CLAUDE_FINTO = None


def _script_claude_finto() -> str:
    """Uno script che esce 0 e basta, in una cartella SUA, creata una sola
    volta per processo (mai dentro il `tmp` di un singolo test, che il
    `finally` di `esegui()` rimuove): `claude_bin` resta sostituito per
    tutta la vita del processo di prova, quindi lo script deve sopravvivere
    anche dopo che quel `tmp` è stato rimosso - altrimenti un test
    SUCCESSIVO nello stesso processo che chiamasse `cantiere.avvia()` per
    davvero troverebbe un binario "claude" che punta a un file già
    cancellato (`FileNotFoundError`, misurato per davvero: vedi lo stesso
    difetto e la stessa correzione in `tools/prove/api-riprendi.py`)."""
    global _CARTELLA_CLAUDE_FINTO
    if _CARTELLA_CLAUDE_FINTO is None:
        _CARTELLA_CLAUDE_FINTO = Path(tempfile.mkdtemp(prefix="plancia-prova-claude-finto-jarvis-"))
    return _finti.crea_finto(_CARTELLA_CLAUDE_FINTO, "claude-finto",
                             "import sys\nsys.exit(0)\n")


@contextlib.contextmanager
def _popen_finto_sicuro(cantiere, tmp, atteso, prova, nome):
    """Stesso schema (e stesso motivo) di `_popen_finto_sicuro` in
    `tools/prove/api-riprendi.py`: il critico (L3-RIPRENDI-UI-4) ha trovato
    che il `finally` di questa prova rimetteva `cantiere.subprocess.Popen`
    vero senza controllare se il finto fosse mai stato chiamato, e
    `cantiere.recap.claude_bin()` trova il `claude` reale della macchina se
    quel thread di sfondo arriva al suo Popen in ritardo. Qui `claude_bin`
    resta finto per SEMPRE in questo processo di prova (non costa niente);
    `subprocess.Popen` si ripristina solo se `catturati` arriva ad `atteso`
    entro 5 secondi, con una prova esplicita sul numero. `tmp` non serve più
    allo script finto (ha una cartella sua, vedi `_script_claude_finto`),
    resta come parametro per compatibilità con le chiamate esistenti."""
    cantiere.recap.claude_bin = lambda: _script_claude_finto()

    catturati = []
    vero_popen = cantiere.subprocess.Popen

    def _popen_finto(cmd, **kw):
        catturati.append(cmd)
        return _ProcessoFinto()

    cantiere.subprocess.Popen = _popen_finto
    try:
        yield catturati
    finally:
        for _ in range(50):
            if len(catturati) >= atteso:
                break
            time.sleep(0.1)
        raggiunto = len(catturati) >= atteso
        prova(f"{nome}: il Popen finto è stato chiamato almeno {atteso} volta/e "
              "prima di rimettere quello vero (altrimenti resta finto)",
              raggiunto, f"catturati: {len(catturati)}")
        if raggiunto:
            cantiere.subprocess.Popen = vero_popen


def esegui(prova) -> None:
    from plancia import actions, cantiere, config, jarvis, richiamo, store

    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-jarvis-riprendi-"))
    claude_vuota = tmp / "claude-config"
    claude_vuota.mkdir()
    vecchio_claude_dir = config.CLAUDE_DIR
    config.CLAUDE_DIR = claude_vuota
    host_vero = socket.gethostname()

    lancio = tmp / "lanciato.txt"
    # scrive il suo unico argomento su un file (lo stesso programma su ogni sistema)
    lanciatore = _finti.crea_finto(
        tmp, "finto-terminale",
        "import sys\n"
        f"open({str(lancio)!r}, 'w', encoding='utf-8').write("
        "sys.argv[1] if len(sys.argv) > 1 else '')\n")

    try:
        conn = store.connect()
        store.init_db(conn)

        # --- 1. proposta "manda" su un task chiuso: la STESSA sessione ------
        cwd_chiusa = str(tmp / "cwd-jarvis-chiusa")
        os.makedirs(cwd_chiusa)
        t_chiusa = actions.task_add(conn, "prova jarvis riprendi chiusa",
                                    session_id="sid-jarvis-chiusa", cwd=cwd_chiusa,
                                    agent="claude", host=host_vero)
        cartella_progetto = claude_vuota / "projects" / richiamo.cartella_sessione(cwd_chiusa)
        cartella_progetto.mkdir(parents=True)
        (cartella_progetto / "sid-jarvis-chiusa.jsonl").write_text(
            '{"type":"summary"}\n', "utf-8")

        agents_vuoto = tmp / "agents-vuoto.json"
        agents_vuoto.write_text("[]", "utf-8")

        scelta = {"testo": "fallo", "azione": {
            "tipo": "manda", "titolo": "prova jarvis riprendi chiusa",
            "task_id": t_chiusa["id"], "agente": "claude", "modo": "proposta"}}
        with _popen_finto_sicuro(cantiere, tmp, 1, prova, "proposta 'manda'") as catturati:
            with _ambiente(PLANCIA_AGENTS_JSON=str(agents_vuoto)):
                # 22-SERVER: una proposta non parte da sola. Si prepara la scheda
                # (la stessa che "fallo" prepara da una proposta "manda") e parte
                # con la conferma, l'unica porta.
                scheda = jarvis.proponi(
                    "lancia", {"titolo": scelta["azione"]["titolo"], "agente": "claude",
                               "task_id": t_chiusa["id"], "scrive": False},
                    conn, conn, "it")
                jarvis.conferma(scheda["id"], "it", conn=conn)

        cmd_lanciato = catturati[0] if catturati else []
        prova("una proposta 'manda' con task_id chiuso lancia davvero un comando",
              bool(cmd_lanciato), "nessun Popen chiamato")
        prova("...con --resume sulla sessione DEL TASK (non da zero)",
              "sid-jarvis-chiusa" in cmd_lanciato, str(cmd_lanciato))
        prova("...e SENZA --fork-session (21-RIPRENDI: la stessa sessione, non una copia)",
              "--fork-session" not in cmd_lanciato, str(cmd_lanciato))

        # --- 2. "resume task N"/"retoma la tarea N" in en/es: il motivo va
        # tradotto, non pronunciato in italiano -----------------------------
        t_persa = actions.task_add(conn, "prova jarvis riprendi persa",
                                   session_id="sid-jarvis-persa",
                                   cwd="/tmp/prova-jarvis-riprendi-persa",
                                   agent="claude", host="altra-macchina-jarvis")
        with _ambiente(PLANCIA_TERMINALE=str(lanciatore)):
            r_en = _esegui_frase(jarvis, f"resume task {t_persa['id']}", "en", conn)
            r_es = _esegui_frase(jarvis, f"retoma la tarea {t_persa['id']}", "es", conn)
            r_it = _esegui_frase(jarvis, f"riprendi task {t_persa['id']}", "it", conn)

        prova("en: la voce non pronuncia il motivo in italiano ('creato su')",
              "creato su" not in (r_en.get("risposta") or ""), r_en.get("risposta"))
        prova("en: il motivo tradotto ('created on') compare invece",
              "created on" in (r_en.get("risposta") or ""), r_en.get("risposta"))
        prova("es: la voce non pronuncia il motivo in italiano ('creato su')",
              "creato su" not in (r_es.get("risposta") or ""), r_es.get("risposta"))
        prova("es: il motivo tradotto ('creado en') compare invece",
              "creado en" in (r_es.get("risposta") or ""), r_es.get("risposta"))
        prova("it: il motivo resta in italiano (nessuna traduzione da fare)",
              "creato su" in (r_it.get("risposta") or ""), r_it.get("risposta"))

        # --- LOTTO-L3-RITOCCO punto 7 -------------------------------------
        _prova_copia_appunti_fallita(prova, actions, jarvis, conn, host_vero, lanciatore)
        _prova_copia_appunti_codice_diverso_da_zero(prova, actions, jarvis, conn, host_vero, tmp)
        _prova_lancio_in_errore(prova, actions, jarvis, conn, host_vero, tmp)

        # --- LOTTO-L3-RITOCCO punto 4 (lato Jarvis) -----------------------
        _prova_aggiorna_no_sync(prova, jarvis, conn)
    finally:
        config.CLAUDE_DIR = vecchio_claude_dir
        shutil.rmtree(str(tmp), ignore_errors=True)


def _prova_copia_appunti_fallita(prova, actions, jarvis, conn, host_vero, lanciatore) -> None:
    """LOTTO-L3-RITOCCO punto 7: se `_copia_appunti` torna False (nessun
    `pbcopy`, o qui il PLANCIA_CLIPBOARD finto che non esiste), "riprendi il
    task N" su una sessione viva non deve dire "l'ho copiato negli appunti"
    - prima lo diceva comunque, ignorando il valore tornato.
    """
    t_viva = actions.task_add(conn, "prova jarvis riprendi viva senza copia",
                              session_id="sid-jarvis-viva-nocopia",
                              cwd="/tmp/prova-jarvis-viva-nocopia",
                              agent="claude", host=host_vero)
    agents_json = Path(lanciatore).parent / "agents-viva-nocopia.json"
    agents_json.write_text(json.dumps([{"sessionId": "sid-jarvis-viva-nocopia"}]), "utf-8")
    clipboard_rotto = Path(lanciatore).parent / "clipboard-che-non-esiste-xyz"

    # La frase di successo ("l'ho copiata/copiato negli appunti") non deve
    # comparire: la risposta corretta parla comunque di appunti, ma per dire
    # che NON ci è riuscita (jarvis.RISPOSTE["riprendi_viva_senza_copia"]).
    frase_successo = {"it": "l'ho copiata negli appunti", "en": "i copied it to the clipboard",
                      "es": "la he copiado al portapapeles"}
    with _ambiente(PLANCIA_AGENTS_JSON=str(agents_json), PLANCIA_CLIPBOARD=str(clipboard_rotto)):
        for lang, frase in (("it", "riprendi task"), ("en", "resume task"), ("es", "retoma la tarea")):
            r = _esegui_frase(jarvis, f"{frase} {t_viva['id']}", lang, conn)
            risposta = (r.get("risposta") or "").lower()
            prova(f"{lang}: 'copia negli appunti' fallita non dice di essere riuscita a copiare",
                  frase_successo[lang] not in risposta, r.get("risposta"))
            prova(f"{lang}: ...ma dice comunque che la sessione è aperta",
                  bool(risposta), r.get("risposta"))


def _prova_copia_appunti_codice_diverso_da_zero(prova, actions, jarvis, conn, host_vero, tmp) -> None:
    """Consigliata del critico (L3-RIPRENDI-UI-4): `_copia_appunti` usava
    `subprocess.run` senza `check`, quindi tornava True anche quando il
    comando USCIVA (uno pbcopy vero, o qui uno script finto) con un codice
    diverso da zero - un comando che esiste ed è eseguibile, a differenza
    della prova sopra (PLANCIA_CLIPBOARD su un percorso che non esiste).
    Verificato: prima di questa correzione, con questo script (`exit 1`),
    Jarvis diceva ancora "l'ho copiata negli appunti"."""
    t_viva = actions.task_add(conn, "prova jarvis riprendi viva, clipboard che fallisce",
                              session_id="sid-jarvis-viva-exit1",
                              cwd="/tmp/prova-jarvis-viva-exit1",
                              agent="claude", host=host_vero)
    agents_json = tmp / "agents-viva-exit1.json"
    agents_json.write_text(json.dumps([{"sessionId": "sid-jarvis-viva-exit1"}]), "utf-8")
    clipboard_fallisce = _finti.crea_finto(
        tmp, "clipboard-exit1", "import sys\nsys.stdin.read()\nsys.exit(1)\n")

    with _ambiente(PLANCIA_AGENTS_JSON=str(agents_json), PLANCIA_CLIPBOARD=str(clipboard_fallisce)):
        r = _esegui_frase(jarvis, f"riprendi task {t_viva['id']}", "it", conn)
    risposta = (r.get("risposta") or "").lower()
    prova("uno script PLANCIA_CLIPBOARD che esiste ma esce con codice 1 non fa dire "
          "'l'ho copiata negli appunti' (il codice di uscita conta, non solo l'eccezione)",
          "l'ho copiata negli appunti" not in risposta, r.get("risposta"))


def _prova_lancio_in_errore(prova, actions, jarvis, conn, host_vero, tmp) -> None:
    """LOTTO-L3-RITOCCO punto 7: se `apri()` torna `errore` (lanciatore in
    timeout), la voce di "riprendi il task N" (chiusa/persa) lo dice invece
    di rispondere come se il lancio fosse partito.

    L3-RIPRENDI-UI-4 (obbligatoria del critico): prima questa prova girava
    solo in italiano. `esito['errore']` (plancia/riprendi.py) è italiano
    fisso ("il lanciatore non ha risposto entro..."), e in en/es finiva
    incollato intatto dentro una frase altrimenti tradotta - la voce
    pronunciava parole italiane in mezzo all'inglese/spagnolo, lo stesso
    difetto già chiuso per `motivo` (vedi `_tmot`/MOTIVI_PREFISSI). Qui si
    controlla, per ciascuna lingua, che la risposta NON contenga più la
    parola italiana "lanciatore"."""
    from plancia import riprendi

    lanciatore_lento = _finti.crea_finto(tmp, "terminale-lento",
                                         "import time\ntime.sleep(5)\n")

    prefissi_attesi = {
        "it": "non sono riuscito a lanciarlo",
        "en": "i could not launch it",
        "es": "no he podido lanzarlo",
    }
    for lang in ("it", "en", "es"):
        t_persa = actions.task_add(
            conn, f"prova jarvis riprendi lancio in errore ({lang})",
            session_id=f"sid-jarvis-lancio-errore-{lang}",
            cwd=f"/tmp/prova-jarvis-lancio-errore-{lang}",
            agent="claude", host="altra-macchina-jarvis-errore")

        vecchio_timeout = riprendi._APRI_TIMEOUT_SECONDI
        riprendi._APRI_TIMEOUT_SECONDI = 0.3
        try:
            with _ambiente(PLANCIA_TERMINALE=str(lanciatore_lento)):
                r = _esegui_frase(jarvis, f"riprendi task {t_persa['id']}", lang, conn)
        finally:
            riprendi._APRI_TIMEOUT_SECONDI = vecchio_timeout
        risposta = (r.get("risposta") or "")
        prova(f"{lang}: la voce dice che non è riuscita a lanciarlo quando il "
              "terminale va in timeout",
              prefissi_attesi[lang] in risposta.lower(), risposta)
        if lang != "it":
            prova(f"{lang}: la risposta non pronuncia più la parola italiana "
                  "'lanciatore' in mezzo alla frase",
                  "lanciatore" not in risposta.lower(), risposta)


def _prova_aggiorna_no_sync(prova, jarvis, conn) -> None:
    """LOTTO-L3-RITOCCO punto 4 (lato voce): con `_NO_SYNC_ATTIVO` (impostato
    da `plancia/api.py:serve` quando il processo è partito con --no-sync)
    "aggiorna"/"sync"/"refresh" non deve più dire "rileggo le fonti", una
    promessa vuota quando nessun sync può partire per tutta la vita del
    processo. Import locale (non in testa al file, mai chiamato altrove in
    questo modulo di prova) solo per riassegnare l'attributo a runtime: non è
    una modifica di plancia/api.py, è la stessa tecnica di
    riprendi._APRI_TIMEOUT_SECONDI qui sopra."""
    from plancia import api as _api

    vecchio = getattr(_api, "_NO_SYNC_ATTIVO", False)
    try:
        _api._NO_SYNC_ATTIVO = True
        r = _esegui_frase(jarvis, "aggiorna", "it", conn)
        prova("con _NO_SYNC_ATTIVO, la voce dice che il sync è disattivato, non 'rileggo le fonti'",
              "disattivat" in (r.get("risposta") or "").lower(), r.get("risposta"))

        _api._NO_SYNC_ATTIVO = False
        r2 = _esegui_frase(jarvis, "aggiorna", "it", conn)
        prova("senza _NO_SYNC_ATTIVO, la voce torna a dire 'rileggo le fonti'",
              (r2.get("risposta") or "") == "Rileggo le fonti.", r2.get("risposta"))
    finally:
        _api._NO_SYNC_ATTIVO = vecchio


if __name__ == "__main__":
    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-jarvis-riprendi-home-"))
    os.environ["PLANCIA_HOME"] = str(CASA)

    falliti = []
    passati = 0

    def _prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print(f"  ok   {nome}")
        else:
            falliti.append(nome)
            print(f"  NO   {nome} {dettaglio}")

    print(f"archivio di prova: {CASA}\n")
    try:
        esegui(_prova)
    finally:
        shutil.rmtree(str(CASA), ignore_errors=True)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
