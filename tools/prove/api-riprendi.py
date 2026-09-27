"""Prove per LOTTO-L3-RIPRENDI-UI, lato server: il pulsante Riprendi visto da
`plancia/api.py` (le tre rotte `/api/riprendi/...`) e dal dispatcher MCP
(`plancia/mcp.py`, azione `riprendi`). Più il difetto minore di L1-RIORDINA
che il lotto chiude di striscio (`plancia riordina --mostra` su un file
inesistente).

Isolamento (regola della sessione: mai toccare i dati veri di chi lancia
questa prova, mai un `claude`/`codex` vero):

- il server HTTP di prova gira su una porta propria, nello stesso processo
  (un thread, come fa già `tools/prova.py` per le sue prove HTTP): questo è
  quello che permette di isolare `config.CLAUDE_DIR` riassegnando l'attributo
  del modulo (letto a ogni chiamata da `plancia/riprendi.py`, mai congelato
  in una chiusura) e di vederlo anche dal thread del server, che vive nello
  stesso processo.
- `PLANCIA_AGENTS_JSON` sostituisce `claude agents --json` (mai lanciato);
  `PLANCIA_TERMINALE` sostituisce `osascript`/Terminal.app con uno script che
  scrive il suo unico argomento su un file, invece di aprire un Terminale.
- il lancio in sottofondo di `cantiere.avvia()` passa comunque da
  `subprocess.Popen`: qui si sostituisce quel riferimento con un processo
  finto (mai un `claude` vero), stessa idea del lanciatore finto sopra.

`esegui(prova)` è la firma che `tools/prova.py` scopre da sola in
`tools/prove/*.py` (vedi `tools/prove/README.md`); per lanciare solo questo
modulo, il blocco `__main__` in fondo.
"""

import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

PORTA = 7793


@contextlib.contextmanager
def _ambiente(**valori):
    """Imposta (o toglie, con None) le variabili date; le rimette uscendo."""
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


def _http(percorso, metodo="GET", corpo=None):
    from plancia import config
    dati = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORTA}{percorso}", data=dati, method=metodo,
        headers={"Content-Type": "application/json", "X-Plancia-Token": config.get_token()})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class _ProcessoFinto:
    """Sostituisce il processo vero che `subprocess.Popen` avrebbe lanciato
    (mai un `claude`/`codex` vero, regola della sessione): stdin/stdout
    minimi perché `cantiere._esegui` ci scrive e ci legge davvero."""
    pid = 999999
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
    volta per processo (mai dentro il `tmp` di un singolo test): `claude_bin`
    resta sostituito per tutta la vita del processo di prova (vedi
    `_popen_finto_sicuro`), quindi lo script deve sopravvivere anche dopo che
    il `tmp` del test che l'ha creato è stato rimosso nel suo `finally` -
    altrimenti un test SUCCESSIVO nello stesso processo (`tools/prova.py` ne
    esegue tanti uno via l'altro) che chiamasse `cantiere.avvia()` per
    davvero (senza patchare Popen) troverebbe un binario "claude" che punta a
    un file già cancellato: `FileNotFoundError`, non un fake che esce 0.
    Misurato per davvero: `tools/prove/riprendi.py`, eseguito dopo
    `tools/prove/jarvis-riprendi.py` nello stesso processo di
    `tools/prova.py`, falliva così prima di questa correzione."""
    global _CARTELLA_CLAUDE_FINTO
    if _CARTELLA_CLAUDE_FINTO is None:
        _CARTELLA_CLAUDE_FINTO = Path(tempfile.mkdtemp(prefix="plancia-prova-claude-finto-"))
    script = _CARTELLA_CLAUDE_FINTO / "claude-finto.sh"
    if not script.exists():
        script.write_text("#!/bin/sh\nexit 0\n", "utf-8")
        script.chmod(0o755)
    return str(script)


@contextlib.contextmanager
def _popen_finto_sicuro(cantiere, tmp, atteso, prova, nome):
    """Isola OGNI lancio di `cantiere.avvia()` per la durata del blocco -
    MAI un `claude`/`codex` vero (regola assoluta della sessione).

    Trovato dal critico (L3-RIPRENDI-UI-4): la versione precedente
    sostituiva solo `cantiere.subprocess.Popen`, e il `finally` rimetteva
    quello vero SENZA controllare se il finto fosse mai stato chiamato.
    `cantiere.avvia()` lancia `_esegui` in un thread di sfondo: su una
    macchina carica (o con sqlite bloccato da un altro lotto in
    parallelo), quel thread può essere ancora dentro `store.connect()`/
    `init_db` quando il blocco `with` esce - il Popen vero viene rimesso
    a posto, il thread arriva al suo `subprocess.Popen(...)` DOPO,
    `recap.claude_bin()` trova il `claude` reale (~/.local/bin/claude o il
    PATH), e parte un `claude -p` vero, magari con `--permission-mode
    acceptEdits` (scrive=True), nella cartella della copia.

    Qui `cantiere.recap.claude_bin` viene sostituito con uno script finto
    che esce 0 e NON viene MAI ripristinato in questo processo di prova:
    non costa niente, e protegge anche un thread che arrivasse al suo
    Popen ben oltre la finestra d'attesa qui sotto. `subprocess.Popen`
    (che serve a CATTURARE l'argv per le prove sul comando) si ripristina
    invece solo se `catturati` arriva a `atteso` elementi entro 5 secondi:
    altrimenti resta finto, con una prova esplicita che lo dice (un fake
    che resta è meglio di un claude vero). `tmp` non serve più allo script
    finto (vedi `_script_claude_finto`: ha una cartella sua, indipendente da
    quella del singolo test), resta come parametro per compatibilità con le
    chiamate esistenti."""
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
        # se non raggiunto: subprocess.Popen resta il finto per il resto del
        # processo di prova. claude_bin resta finto in ogni caso (sopra).


def esegui(prova) -> None:
    from plancia import actions, api as _api, cantiere, config, richiamo, store

    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-api-riprendi-"))
    claude_vuota = tmp / "claude-config"
    claude_vuota.mkdir()

    vecchio_claude_dir = config.CLAUDE_DIR
    config.CLAUDE_DIR = claude_vuota
    host_vero = socket.gethostname()

    try:
        filo = threading.Thread(
            target=_api.serve, kwargs={"port": PORTA, "sync_first": False}, daemon=True)
        filo.start()
        time.sleep(1.2)

        conn = store.connect()
        store.init_db(conn)

        # --- i tre task del demo, uno per stato (come dice il lotto: -----
        # PLANCIA_AGENTS_JSON per 'viva', un jsonl finto per 'chiusa', un
        # host diverso per 'persa') -----------------------------------
        t_viva = actions.task_add(conn, "prova riprendi viva", session_id="sid-viva",
                                  cwd="/tmp/prova-riprendi-viva", agent="claude",
                                  host=host_vero)
        agents_json = tmp / "agents.json"
        agents_json.write_text(json.dumps([{"sessionId": "sid-viva"}]), "utf-8")

        cwd_chiusa = "/tmp/prova-riprendi-chiusa"
        t_chiusa = actions.task_add(conn, "prova riprendi chiusa", session_id="sid-chiusa",
                                    cwd=cwd_chiusa, agent="claude", host=host_vero)
        cartella_progetto = claude_vuota / "projects" / richiamo.cartella_sessione(cwd_chiusa)
        cartella_progetto.mkdir(parents=True)
        (cartella_progetto / "sid-chiusa.jsonl").write_text('{"type":"summary"}\n', "utf-8")

        t_persa = actions.task_add(conn, "prova riprendi persa", session_id="sid-persa",
                                   cwd="/tmp/prova-riprendi-persa", agent="claude",
                                   host="altra-macchina-mai-vista")

        with _ambiente(PLANCIA_AGENTS_JSON=str(agents_json)):
            d_viva = _http(f"/api/riprendi/{t_viva['id']}")
            d_chiusa = _http(f"/api/riprendi/{t_chiusa['id']}")
            d_persa = _http(f"/api/riprendi/{t_persa['id']}")

        prova("GET /api/riprendi di un task appena registrato viva risponde stato='viva'",
              d_viva.get("riprendi", {}).get("stato") == "viva", str(d_viva))
        prova("GET /api/riprendi di un task con la trascrizione, non viva: chiusa",
              d_chiusa.get("riprendi", {}).get("stato") == "chiusa", str(d_chiusa))
        prova("GET /api/riprendi di un task nato su un'altra macchina: persa",
              d_persa.get("riprendi", {}).get("stato") == "persa", str(d_persa))
        prova("il motivo della persa nomina l'altra macchina",
              "altra-macchina-mai-vista" in (d_persa.get("riprendi", {}).get("motivo") or ""),
              str(d_persa))
        prova("la risposta porta anche il messaggio da mettere negli appunti",
              str(t_persa["id"]) in (d_persa.get("messaggio") or ""), str(d_persa))

        # --- POST apri su 'persa': comando pronto, niente --resume -----
        lancio = tmp / "lanciato.txt"
        lanciatore = tmp / "finto-terminale.sh"
        lanciatore.write_text(
            "#!/bin/sh\nprintf '%s' \"$1\" > " + json.dumps(str(lancio)) + "\n", "utf-8")
        lanciatore.chmod(0o755)
        with _ambiente(PLANCIA_TERMINALE=str(lanciatore)):
            _http(f"/api/riprendi/{t_persa['id']}", "POST", {"apri": True})
        contenuto = lancio.read_text("utf-8") if lancio.exists() else ""
        prova("POST apri su un task persa lancia davvero qualcosa",
              bool(contenuto), "il lanciatore finto non ha scritto niente")
        prova("...e l'argv lanciato non contiene --resume (persa riparte da zero)",
              "--resume" not in contenuto, contenuto[:200])

        # --- POST background: fork della sessione quando c'è ------------
        # PLANCIA_AGENTS_JSON qui non serve a costruire lo stato (quello lo
        # fa già il jsonl finto: senza il file di sessione, `_claude_vivo`
        # cadrebbe sul secondo passo e lancerebbe `claude agents --json` per
        # davvero, proprio il binario che questa prova non deve mai
        # toccare): un file con una lista che non contiene 'sid-chiusa'
        # rende quel passo deterministico e senza sottoprocessi veri.
        agents_vuoto = tmp / "agents-vuoto.json"
        agents_vuoto.write_text("[]", "utf-8")

        with _popen_finto_sicuro(cantiere, tmp, 1, prova, "POST background") as catturati:
            with _ambiente(PLANCIA_AGENTS_JSON=str(agents_vuoto)):
                _http(f"/api/riprendi/{t_chiusa['id']}", "POST",
                     {"background": True, "istruzioni": "controlla e basta"})

        cmd_lanciato = catturati[0] if catturati else []
        prova("POST background fa davvero lanciare un comando a cantiere",
              bool(cmd_lanciato), "nessun Popen chiamato entro 5 secondi")
        prova("...con --fork-session, perché il task ha già una sessione da riprendere",
              "--fork-session" in cmd_lanciato, str(cmd_lanciato))
        prova("...e con --resume sulla sessione DEL TASK, non su una nuova",
              "sid-chiusa" in cmd_lanciato, str(cmd_lanciato))

        # --- MCP: l'azione 'riprendi' del dispatcher --------------------
        _prova_mcp(prova, claude_vuota, t_persa["id"])

        # --- LOTTO-L3-RITOCCO punto 12: GET e POST su un id inesistente --
        # rispondono con lo stesso codice e lo stesso corpo (prima la POST
        # alzava actions.BadInput, tradotto in 400, non 404 come la GET).
        _prova_404_coerente(prova)

        # --- LOTTO-L3-RITOCCO punto 11: il lanciatore in timeout ---------
        # (`riprendi.apri()` mette `errore` nella risposta): POST apri deve
        # farlo arrivare fino al corpo JSON, cosi' il front (non provato qui,
        # e' tools/prove-front/riprendi.py) puo' dirlo nel toast.
        _prova_apri_errore_timeout(prova, t_persa["id"])

        # --- LOTTO-L3-RITOCCO punto 13: /api/cantiere prende 'scrive' -----
        # (bool) e non piu' 'modo' (stringa): lo si vede dal 'modo' scritto
        # su runs, che cantiere.avvia deriva da 'scrive'.
        _prova_cantiere_scrive_bool(prova, cantiere, tmp)
        _prova_cantiere_sessione_forka(prova, cantiere, tmp)
    finally:
        config.CLAUDE_DIR = vecchio_claude_dir
        shutil.rmtree(str(tmp), ignore_errors=True)

    # --- CLI: difetto minore di L1-RIORDINA chiuso di striscio ----------
    _prova_riordina_exit(prova)

    # --- CLI: LOTTO-L3-RITOCCO punto 8 -----------------------------------
    _prova_annulla_batch(prova)


def _prova_mcp(prova, claude_vuota, task_id) -> None:
    """`plancia_riprendi` dietro il dispatcher `plancia`, via `bin/plancia-mcp`
    su stdin: stesso schema di `tools/prove/sessione.py`."""
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(claude_vuota)
    richieste = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-06-18"}}) + "\n" +
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                   "params": {"name": "plancia",
                              "arguments": {"azione": "riprendi", "id": task_id}}}) + "\n"
    )
    ok, dettaglio = False, ""
    try:
        proc = subprocess.run(
            [sys.executable, str(RADICE / "bin" / "plancia-mcp")],
            input=richieste, capture_output=True, text=True, env=env, timeout=30)
        risposte = [json.loads(r) for r in proc.stdout.splitlines() if r.strip()]
        chiamata = next((r for r in risposte if r.get("id") == 2), None)
        testo = "".join(c.get("text", "") for c in
                        (chiamata or {}).get("result", {}).get("content", []))
        ok = (bool(chiamata) and not chiamata["result"]["isError"]
              and '"stato": "persa"' in testo)
        dettaglio = testo[:300] if testo else proc.stderr[-500:]
    except Exception as exc:
        dettaglio = "eccezione: %r" % (exc,)
    prova("l'azione MCP 'riprendi' risponde per un task del demo (stato persa)",
          ok, dettaglio)


def _prova_404_coerente(prova) -> None:
    """LOTTO-L3-RITOCCO punto 12: un id che non esiste in `tasks` risponde con
    lo stesso codice HTTP e lo stesso corpo JSON sia in GET sia in POST."""
    import urllib.request as _u
    from plancia import config

    def _con_codice(percorso, metodo, corpo=None):
        dati = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = _u.Request(f"http://127.0.0.1:{PORTA}{percorso}", data=dati, method=metodo,
                         headers={"Content-Type": "application/json",
                                  "X-Plancia-Token": config.get_token()})
        try:
            with _u.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except _u.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    codice_get, corpo_get = _con_codice("/api/riprendi/999999999", "GET")
    codice_post, corpo_post = _con_codice("/api/riprendi/999999999", "POST", {"apri": True})
    prova("GET /api/riprendi/<inesistente> risponde 404", codice_get == 404,
          f"codice={codice_get} corpo={corpo_get}")
    prova("POST /api/riprendi/<inesistente> risponde LO STESSO codice 404 (non 400)",
          codice_post == 404, f"codice={codice_post} corpo={corpo_post}")
    prova("...e lo stesso corpo della GET",
          corpo_get == corpo_post, f"GET={corpo_get} POST={corpo_post}")


def _prova_apri_errore_timeout(prova, task_id) -> None:
    """LOTTO-L3-RITOCCO punto 11: se il lanciatore (PLANCIA_TERMINALE) non
    risponde in tempo, `riprendi.apri()` mette `errore` nella risposta invece
    di far finta che il lancio sia partito - qui si verifica che POST
    /api/riprendi/<id> {"apri": true} lo faccia arrivare fino al JSON.
    `riprendi._APRI_TIMEOUT_SECONDI` (letto a runtime, non congelato in una
    chiusura) si abbassa per la durata della prova, cosi' non si aspettano i
    15 secondi veri: e' un attributo di modulo riassegnato a runtime, non una
    modifica del file (plancia/riprendi.py resta quello del lotto)."""
    from plancia import riprendi

    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-apri-timeout-"))
    lanciatore_lento = tmp / "terminale-lento.sh"
    lanciatore_lento.write_text("#!/bin/sh\nsleep 5\n", "utf-8")
    lanciatore_lento.chmod(0o755)

    vecchio_timeout = riprendi._APRI_TIMEOUT_SECONDI
    riprendi._APRI_TIMEOUT_SECONDI = 0.3
    try:
        with _ambiente(PLANCIA_TERMINALE=str(lanciatore_lento)):
            r = _http(f"/api/riprendi/{task_id}", "POST", {"apri": True})
    finally:
        riprendi._APRI_TIMEOUT_SECONDI = vecchio_timeout
        shutil.rmtree(str(tmp), ignore_errors=True)
    prova("POST apri con un lanciatore che non risponde in tempo porta 'errore' nel JSON",
          bool(r.get("errore")), str(r))


def _prova_cantiere_scrive_bool(prova, cantiere, tmp) -> None:
    """LOTTO-L3-RITOCCO punto 13: /api/cantiere prende 'scrive' (bool) invece
    di 'modo' (stringa "proposta"/"esegui") - si vede dal 'modo' che
    cantiere.avvia deriva e scrive su runs (bool True -> "esegui").

    L3-RIPRENDI-UI-4: due lanci in sottofondo per due thread diversi - vedi
    `_popen_finto_sicuro` per il perché non basta un `finally` che rimette
    il Popen vero senza guardare quanti ne sono arrivati."""
    with _popen_finto_sicuro(cantiere, tmp, 2, prova, "POST /api/cantiere"):
        r_scrive = _http("/api/cantiere", "POST",
                         {"titolo": "prova scrive bool", "scrive": True})
        r_sola_lettura = _http("/api/cantiere", "POST",
                              {"titolo": "prova scrive bool, sola lettura", "scrive": False})
    prova("POST /api/cantiere con scrive=true fa un lancio in modo 'esegui'",
          r_scrive.get("modo") == "esegui", str(r_scrive))
    prova("POST /api/cantiere con scrive=false (o assente) resta in modo 'proposta'",
          r_sola_lettura.get("modo") == "proposta", str(r_sola_lettura))


def _prova_cantiere_sessione_forka(prova, cantiere, tmp) -> None:
    """L3-RIPRENDI-UI-4 (obbligatoria del critico, "occhi di Eugenio"): il
    modulo "In background" senza un task_id (righe della lavagna venute da
    Claude/Codex, che una sessione la hanno già, plancia/lavagna.py) partiva
    sempre da zero - /api/cantiere non inoltrava mai `sessione` a
    `cantiere.avvia()`, che però la accetta già (--resume --fork-session).
    Qui si controlla il contratto HTTP: con `sessione` nel corpo, l'argv
    lanciato porta --resume <sessione> --fork-session; senza, non li porta."""
    with _popen_finto_sicuro(cantiere, tmp, 1, prova, "POST /api/cantiere (con sessione)") as cat_con:
        _http("/api/cantiere", "POST",
             {"titolo": "prova cantiere sessione", "sessione": "sid-da-riprendere"})
    cmd_con = cat_con[0] if cat_con else []
    prova("POST /api/cantiere con 'sessione' nel corpo fa un lancio con --resume/--fork-session",
          "--resume" in cmd_con and "sid-da-riprendere" in cmd_con and "--fork-session" in cmd_con,
          str(cmd_con))

    with _popen_finto_sicuro(cantiere, tmp, 1, prova, "POST /api/cantiere (senza sessione)") as cat_senza:
        _http("/api/cantiere", "POST", {"titolo": "prova cantiere senza sessione"})
    cmd_senza = cat_senza[0] if cat_senza else []
    prova("...e senza 'sessione' nel corpo, l'argv resta senza --resume/--fork-session",
          "--resume" not in cmd_senza and "--fork-session" not in cmd_senza, str(cmd_senza))


def _prova_annulla_batch(prova) -> None:
    """LOTTO-L3-RITOCCO punto 8: 'plancia riprendi --annulla BATCH' passava
    da `Path(BATCH).stem` prima di chiamare `riprendi.annulla()`. `.stem`
    tronca dopo l'ULTIMO punto: un batch con un punto dentro (per esempio uno
    costruito a mano, o un futuro formato di `store.now()` con i
    millisecondi) perdeva la coda, e `annulla()` cercava eventi sotto un nome
    che non esisteva, dicendo "rimessi: 0" anche quando c'era davvero
    qualcosa da rimettere.

    Nota onesta (consigliata del critico, L3-RIPRENDI-UI-4): `store.now()`
    (plancia/store.py) è `"%Y-%m-%dT%H:%M:%SZ"`, SENZA punto - un batch vero
    ("backfill-" + store.now()) non ha mai avuto questo problema. Il batch
    col punto qui sotto è un caso costruito apposta per dimostrare il
    difetto di `.stem` in generale, non quello che `riprendi.backfill`
    produce oggi. La correzione (la stringa passa intatta, e viene rifiutata
    subito - codice 1, niente ValueError - se non è un batch valido per
    `riprendi._batch_valido`) resta comunque giusta e vale per qualunque
    batch, con o senza punto."""
    from plancia import actions, eventi, store

    # --- batch non valido: rifiutato con codice 1, su una casa a parte ----
    # (non deve toccare niente, quindi non serve condividerla col resto).
    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-annulla-"))
    try:
        env_isolato = dict(os.environ, PLANCIA_HOME=str(tmp))
        esito_bad = subprocess.run(
            [sys.executable, str(RADICE / "bin" / "plancia"), "riprendi",
             "--annulla", "batch,con,virgole"],
            capture_output=True, text=True, env=env_isolato, timeout=20)
        prova("'plancia riprendi --annulla' con un batch non valido esce con codice 1",
              esito_bad.returncode == 1, f"returncode={esito_bad.returncode} stdout={esito_bad.stdout!r}")
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)

    # --- batch vero, col punto dei millisecondi: nessuna troncatura -------
    # Stessa PLANCIA_HOME/db di tutto il resto di questo file (quella che
    # `__main__`/tools/prova.py hanno già fissato in config.DATA_DIR/DB_PATH
    # all'inizio del processo): il sottoprocesso qui sotto deve leggere
    # l'evento scritto qui sopra, quindi la sua PLANCIA_HOME dev'essere
    # esattamente quella corrente, non una nuova - una cartella nuova
    # darebbe sempre "rimessi: 0", a prescindere dal difetto.
    batch = "backfill-2026-09-26T10-00-00.500"
    conn = store.connect()
    store.init_db(conn)
    t = actions.task_add(conn, "prova annulla batch col punto")
    conn.execute("UPDATE tasks SET session_id=? WHERE id=?", ("sid-annulla-punto", t["id"]))
    conn.commit()
    eventi.scrivi(f"attribuzione:{batch}", f"task {t['id']} attribuito", None,
                  {"batch": batch, "task_id": t["id"], "sessione": "sid-annulla-punto",
                   "prima": {"session_id": None, "cwd": None, "agent": None, "host": None}})
    conn.close()

    env_condiviso = dict(os.environ, PLANCIA_HOME=os.environ.get("PLANCIA_HOME", ""))
    esito_ok = subprocess.run(
        [sys.executable, str(RADICE / "bin" / "plancia"), "riprendi", "--annulla", batch],
        capture_output=True, text=True, env=env_condiviso, timeout=20)
    prova("...con un batch valido (col punto dei millisecondi) esce con codice 0",
          esito_ok.returncode == 0, f"returncode={esito_ok.returncode} stdout={esito_ok.stdout!r}")
    prova("...e rimette davvero l'attribuzione (il nome non è stato troncato a un .stem)",
          "rimessi: 1" in esito_ok.stdout, esito_ok.stdout)


def _prova_riordina_exit(prova) -> None:
    """Difetto minore segnalato dal tester di L1-RIORDINA (LOTTO §2, punto
    3): `plancia riordina --mostra`/`--applica` su un file inesistente
    stampava l'errore ma usciva con lo stesso codice di un successo."""
    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-riordina-exit-"))
    env = dict(os.environ, PLANCIA_HOME=str(tmp))
    try:
        esito_mostra = subprocess.run(
            [sys.executable, str(RADICE / "bin" / "plancia"), "riordina",
             "--mostra", "/inesistente"],
            capture_output=True, text=True, env=env, timeout=20)
        esito_applica = subprocess.run(
            [sys.executable, str(RADICE / "bin" / "plancia"), "riordina",
             "--applica", "/inesistente"],
            capture_output=True, text=True, env=env, timeout=20)
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)
    prova("'plancia riordina --mostra' su un file inesistente esce con codice 1",
          esito_mostra.returncode == 1,
          f"returncode={esito_mostra.returncode} stdout={esito_mostra.stdout!r}")
    prova("'plancia riordina --applica' su un file inesistente esce con codice 1",
          esito_applica.returncode == 1,
          f"returncode={esito_applica.returncode} stdout={esito_applica.stdout!r}")


if __name__ == "__main__":
    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-api-riprendi-home-"))
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
