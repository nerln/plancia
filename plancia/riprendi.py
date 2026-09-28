"""I tre stati di un task e come tornarci dentro (verdetto 16/09/2026, §B).

Un task nato da `plancia_task_add` porta `session_id`, `cwd`, `agent`, `host`
(L0-SESSIONE, L0-SCHEMA). Questo modulo li legge e decide una cosa sola: cosa
succede quando Eugenio preme "Riprendi".

Tre stati, mai di più, perché sono le uniche tre cose che possono essere vere
di una sessione:

- **viva**: la sessione compare ancora fra quelle aperte, sulla stessa
  macchina. Non c'è niente da lanciare: il messaggio va portato a mano (o con
  `send_message`) dentro una conversazione che sta già girando.
- **chiusa**: la sessione non è più aperta, ma la sua trascrizione esiste.
  Si riprende con `--resume` (Claude) o `resume` (Codex), nella stessa
  cartella in cui era partita.
- **persa**: non c'è niente a cui tornare (mai registrata, sessione scaduta,
  o nata su un'altra macchina). Si riparte da zero, col contesto scritto a
  mano nel prompt.

Per Claude Code, "viva" si legge in due passi (`_claude_vivo`, sotto):
prima il registro istantaneo che l'app scrive per ogni sessione interattiva
(`CLAUDE_DIR/sessions/<pid>.json`), poi, solo se lì non c'è niente, il comando
reale `claude agents --json`. Le prove non lanciano mai quest'ultimo (vedi le
regole della sessione): la variabile `PLANCIA_AGENTS_JSON`, quando c'è,
sostituisce il secondo passo con un file nello stesso formato (lista di
oggetti con almeno `sessionId`). Quando nessuna delle due fonti riesce a dare
una risposta (il registro non ha voce, e il comando fallisce o va in
timeout), lo stato torna "viva" con un motivo che lo dice onestamente: mai
"chiusa" per un buco nella misura, perché offrirebbe `--resume` senza
`--fork-session` su una sessione magari ancora aperta. Per Codex non esiste
un equivalente scriptabile (debito dichiarato dal consiglio, punto 14):
l'unico segnale a disposizione è che il file di rollout sia stato toccato di
recente, quindi "viva" per Codex vuol dire "il rollout è stato modificato
negli ultimi 10 minuti", non "la sessione è aperta da qualche parte": è
un'euristica, e lo dice nel motivo.
"""

import json
import os
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import cantiere, codex, config, eventi, piattaforma, recap, richiamo, store

# Quanto vecchio può essere l'ultimo tocco a un rollout Codex perché lo si
# consideri ancora "viva": non è un segnale diretto (non c'è modo scriptabile
# di sapere se un processo Codex interattivo è aperto), ma un rollout toccato
# da più di dieci minuti quasi certamente non ha nessuno davanti.
_CODEX_VIVA_SECONDI = 600

# La stessa finestra usata da backfill() per associare un task a una sessione
# quando non c'è sovrapposizione temporale: due ore prima o dopo la sessione
# più vicina sullo stesso progetto (il verdetto la chiama "la più vicina
# entro 2 ore", senza dare un numero diverso da assumere).
_BACKFILL_FINESTRA_SECONDI = 2 * 3600

def _parse_ts(s):
    """Legge un timestamp ISO-8601 con o senza millisecondi, sempre con 'Z'.

    Stesso schema già in uso in `ingest.to_utc` e `briefing.py`:
    `datetime.fromisoformat` non digerisce da solo il suffisso 'Z' (non lo
    accetta come offset prima di Python 3.11), quindi si sostituisce con
    '+00:00' prima di passarglielo; regge sia '...T10:00:00Z' (i timestamp
    scritti a mano nelle prove) sia '...T10:00:00.924Z' (quello che
    `ingest.py` scrive per davvero in `sessions.started_at/ended_at`, presi
    da `acc['ts_min']` del jsonl). Prima qui c'era uno `strptime` con un
    formato fisso senza frazione: su una copia del db vero, 1151 `started_at`
    su 1152 tornavano `None`, e il ripiego "la più vicina entro 2 ore" di
    `_sessione_per_backfill` non trovava mai niente per nessuno di loro.
    Il risultato è naive (senza tzinfo): il confronto in
    `_sessione_per_backfill` è fra timestamp tutti nella stessa convenzione
    (UTC), quindi togliere il tzinfo invece di tenerlo evita di dover
    rendere aware anche l'altro lato del confronto.
    """
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------
# stato
# --------------------------------------------------------------------------

def _pid_vivo(pid) -> bool:
    """True se `pid` è un processo vivo su questa macchina."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # il processo c'è, semplicemente non è nostro
    except OSError:
        return False
    return True


def _registro_sessioni_claude() -> list:
    """`[(pid, sessionId), ...]` dal registro che l'app scrive per ogni
    sessione interattiva: `CLAUDE_DIR/sessions/<pid>.json` (lo stesso file
    che legge `sessione._file_session_id`). Istantaneo, senza sottoprocesso:
    torna sempre una lista, vuota se la cartella non c'è o non contiene
    niente di leggibile, mai un'eccezione — è la prima fonte di `_claude_vivo`
    e deve essere quella su cui si può sempre contare.
    """
    cartella = config.CLAUDE_DIR / "sessions"
    if not cartella.is_dir():
        return []
    trovati = []
    for f in cartella.glob("*.json"):
        try:
            dati = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(dati, dict) and dati.get("sessionId"):
            trovati.append((f.stem, dati["sessionId"]))
    return trovati


def _claude_vivo(session_id):
    """True/False quando si è potuto stabilire con certezza se la sessione è
    aperta; `None` quando nessuna delle due fonti ha dato una risposta (mai
    un falso "chiusa" per un buco nella misura: lo gestisce `stato()`).

    Due fonti, in quest'ordine:

    1. Il registro locale (`_registro_sessioni_claude`, sopra): istantaneo, e
       misurato il 16/09/2026 che le sue voci vive combaciano 5/5 con
       `claude agents --json` su questa macchina (stesso sessionId, stesso
       stato). Una voce col session_id giusto decide da sola, viva o morta
       che sia il pid registrato: non si scomoda la seconda fonte.
    2. `claude agents --json`, solo quando la prima non ha trovato niente:
       con `stdin=subprocess.DEVNULL` (altrimenti il sottoprocesso eredita lo
       stdin di chi chiama — nel server MCP è il canale JSON-RPC, vedi
       `apri()`) e `timeout=25`, non 5: misurato su questa macchina, sotto il
       carico normale di più lotti in fan-out, che il comando reale impiega
       anche 19 secondi, e con un timeout di 5 la maggioranza dei lanci
       cadeva nell'`except` e faceva dire "chiusa" a sessioni aperte.

    `PLANCIA_AGENTS_JSON`, quando c'è, sostituisce solo la seconda fonte (le
    prove non lanciano mai il binario vero, regola della sessione): un file
    assente o illeggibile conta come "nessuna sessione trovata" (False), non
    come fonte fallita (None), perché è un sostituto deliberato e
    deterministico messo lì apposta dalla prova, non un sottoprocesso che può
    impallarsi per davvero.
    """
    if not session_id:
        return False

    for pid, sid in _registro_sessioni_claude():
        if sid == session_id:
            return _pid_vivo(pid)

    percorso = os.environ.get("PLANCIA_AGENTS_JSON")
    if percorso:
        try:
            dati = json.loads(Path(percorso).read_text("utf-8"))
        except (OSError, ValueError):
            dati = []
        lista = dati if isinstance(dati, list) else []
        return any((r or {}).get("sessionId") == session_id for r in lista)

    exe = recap.claude_bin()
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "agents", "--json"], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=25)
        dati = json.loads(out.stdout or "[]")
    except Exception:
        return None
    lista = dati if isinstance(dati, list) else []
    return any((r or {}).get("sessionId") == session_id for r in lista)


def _rollout_per_id(session_id):
    """Il file di rollout Codex il cui nome finisce per `session_id`, o None.

    Stesso schema di cartelle di `sessione._rollout_piu_recente`
    (`CODEX_HOME/sessions/AAAA/MM/GG/rollout-<data>-<uuid>.jsonl`), ma qui si
    cerca per id esatto invece che per cwd: il session_id del task è già
    quell'uuid (lavagna.py:113, dove `sessione = thread_id`).
    """
    if not session_id:
        return None
    cartella = codex.CODEX_HOME / "sessions"
    if not cartella.is_dir():
        return None
    trovati = list(cartella.glob(f"*/*/*/rollout-*-{session_id}.jsonl"))
    return trovati[0] if trovati else None


def _trascrizione_claude(cwd, session_id):
    """Dove Claude Code tiene la trascrizione di questa sessione, o None se
    non si può nemmeno calcolare il percorso (cwd o session_id mancanti).

    `None`, non `Path("")`: `Path("")` normalizza a `Path(".")`, che esiste
    sempre (è la cartella corrente) e avrebbe fatto risultare "chiusa" ogni
    sessione senza cwd invece di lasciarla cadere su "persa".

    La cartella si calcola con `richiamo.cartella_sessione` (stesso codice
    che usa Plancia altrove per lo stesso scopo, misurato sul campo in
    docs/RICOGNIZIONE-cantiere-dispatch.md): niente da riscrivere qui.
    """
    cartella = richiamo.cartella_sessione(cwd)
    if not cartella or not session_id:
        return None
    return config.CLAUDE_DIR / "projects" / cartella / f"{session_id}.jsonl"


def _campo(task, nome, default=""):
    """Legge `task[nome]`, che `task` sia un dict (`plancia_task_add`, le
    prove) o una `sqlite3.Row` (una riga letta dal db, es. `agenda`): una
    `Row` non ha `.get()`, e una colonna che quella riga non porta (`host`
    letto da una riga di `agenda`, che non lo ha) alzerebbe `IndexError`
    invece di tornare il default, quindi si intercetta anche quello."""
    try:
        valore = task.get(nome) if hasattr(task, "get") else task[nome]
    except (IndexError, KeyError):
        return default
    return valore if valore else default


def sessione_da_riprendere(s):
    """Il `session_id` (str) da forkare quando si lancia in background, o `None`.

    `s` è il dict che torna `stato()` (o un suo sottoinsieme con almeno
    `session_id`/`stato`): "viva" o "chiusa" hanno una sessione vera a cui
    attaccarsi (`--fork-session`/`exec resume`, vedi `cantiere._comando`),
    "persa" no (`cantiere.avvia()` scrive da sola un prompt da zero).

    LOTTO-L3-RITOCCO punto 10: prima questa riga (`s["session_id"] if
    s["stato"] in ("viva", "chiusa") else None`, o `s.get(...)` a seconda del
    chiamante) era copiata uguale in api.py, cli.py (due volte), mcp.py e
    jarvis.py: un domani in cui uno solo dei cinque avesse aggiunto un quarto
    stato, o cambiato la coppia "viva"/"chiusa", sarebbe rimasto disallineato
    dagli altri quattro senza che niente lo segnalasse.
    """
    return s.get("session_id") if s.get("stato") in ("viva", "chiusa") else None


def stato(conn, task) -> dict:
    """I tre stati, calcolati per un task (righa di `tasks`, dict-like).

    Torna sempre `{"stato", "motivo", "agent", "session_id", "cwd", "host"}`.
    `conn` non serve oggi (i dati bastano dal task stesso), ma resta nella
    firma perché ogni altra funzione di lettura di Plancia la prende, e un
    domani "viva" potrebbe voler controllare anche `sessions` nel db.
    """
    session_id = _campo(task, "session_id", None)
    agent = _campo(task, "agent", "claude")
    cwd = _campo(task, "cwd", "")
    host_task = _campo(task, "host", "")
    host_ora = socket.gethostname()

    base = {"agent": agent, "session_id": session_id, "cwd": cwd,
            "host": host_task or host_ora}

    if not session_id:
        return dict(base, stato="persa", motivo="mai registrata")

    # Un task nato su un'altra macchina non ha niente da riprendere qui: il
    # jsonl/rollout non esiste su questo disco, e "viva" non avrebbe senso
    # nemmeno se per assurdo l'id combaciasse con qualcosa di locale.
    if host_task and host_task != host_ora:
        return dict(base, stato="persa", motivo=f"creato su {host_task}")

    if agent == "codex":
        rollout = _rollout_per_id(session_id)
        if rollout is None:
            return dict(base, stato="persa", motivo="sessione scaduta")
        eta = 0
        try:
            eta = time.time() - rollout.stat().st_mtime
        except OSError:
            pass
        if eta <= _CODEX_VIVA_SECONDI:
            return dict(base, stato="viva",
                        motivo="il rollout è stato modificato negli ultimi 10 minuti")
        return dict(base, stato="chiusa",
                    motivo="la trascrizione c'è, ma il rollout è fermo da più di 10 minuti")

    # claude
    vivo = _claude_vivo(session_id)
    if vivo is None:
        # Nessuna delle due fonti ha risposto (registro senza voce e
        # `claude agents --json` fallito o scaduto): dire "chiusa" qui
        # sarebbe il punto cieco peggiore possibile, perché porterebbe
        # `comando()` a fare `--resume` senza `--fork-session` su una
        # sessione magari ancora apertissima (due processi sullo stesso
        # jsonl). "Viva" non lancia niente (`comando()` torna `[]`): è la
        # sola risposta prudente quando non si sa, anche se il motivo lo
        # dice onestamente invece di far finta di aver visto la sessione.
        return dict(base, stato="viva",
                    motivo="non sono riuscito a interrogare le sessioni aperte")
    if vivo:
        return dict(base, stato="viva",
                    motivo=(f"aperta in {cwd}" if cwd else "aperta in un'altra sessione"))
    trascrizione = _trascrizione_claude(cwd, session_id)
    if trascrizione and trascrizione.exists():
        return dict(base, stato="chiusa",
                    motivo="la trascrizione c'è, ma la sessione non risulta più aperta")
    return dict(base, stato="persa", motivo="sessione scaduta")


# --------------------------------------------------------------------------
# messaggio e comando
# --------------------------------------------------------------------------

def messaggio(task) -> str:
    """"riprendi il task N di Plancia: <titolo>": lo stesso testo va sia nel
    prompt di `--resume` (stato chiuso) sia negli appunti (stato vivo,
    lo scrive la UI: qui c'è solo il testo)."""
    tid = _campo(task, "id", "")
    titolo = _campo(task, "title") or _campo(task, "titolo")
    return f"riprendi il task {tid} di Plancia: {titolo}"


def comando(task, stato_calcolato, conn=None) -> list:
    """L'argv da lanciare per questo task, secondo lo stato già calcolato.

    Vuoto per "viva" (non c'è niente da lanciare: vedi `messaggio`). Per
    "persa" serve il db per il contesto del progetto
    (`cantiere.componi_prompt`): se chi chiama ne ha già una aperta (`apri()`
    ce l'ha) la passa in `conn`, opzionale, così non se ne apre una seconda
    per niente; altrimenti ne apre una propria solo per la durata della
    chiamata, senza `init_db` — che scrive `meta.schema_version` e fa
    `commit()`, quindi non è vero che "nessuna scrittura avviene qui" come
    diceva una versione precedente di questa docstring. Un percorso che
    legge solo il progetto per comporre un prompt non deve reinizializzare
    lo schema: se il db non esiste ancora, non ci sono task da riprendere.
    """
    esito = stato_calcolato.get("stato")
    agente = stato_calcolato.get("agent") or _campo(task, "agent", "claude")
    session_id = stato_calcolato.get("session_id") or _campo(task, "session_id", None)

    if esito == "viva":
        return []

    if esito == "chiusa":
        if agente == "codex":
            exe = cantiere.codex_bin() or "codex"
            return [exe, "resume", session_id]
        exe = recap.claude_bin() or "claude"
        return [exe, "--resume", session_id, messaggio(task)]

    # persa: si riparte da zero, con tutto il contesto scritto a mano.
    propria = conn is None
    if propria:
        conn = store.connect()
    try:
        prompt = cantiere.componi_prompt(
            conn, _campo(task, "title"), _campo(task, "body"),
            _campo(task, "project_id", None), _campo(task, "prompt"))
    finally:
        if propria:
            conn.close()
    exe = recap.claude_bin() or "claude"
    return [exe, prompt]


# La ricetta per aprire un terminale sta in piattaforma.py, una per sistema.
_applescript_quote = piattaforma.applescript_quote


_APRI_TIMEOUT_SECONDI = 15


def apri(task, conn=None) -> dict:
    """Lancia il comando di ripresa in un Terminale visibile.

    Non è un run di `cantiere`: non scrive in `runs`, non passa da
    `riconcilia()`. Il lanciatore è sostituibile con `PLANCIA_TERMINALE`
    (un comando a cui viene passato, come unico argomento, `cd <cwd> && `
    seguito dalla riga già quotata con `shlex.join`); di default apre il
    terminale del sistema (`piattaforma.comando_terminale`): Terminal.app con
    AppleScript su macOS, Windows Terminal o `cmd` su Windows, il primo
    terminale che c'è su Linux. Per "viva" non lancia niente: torna solo
    il messaggio da mettere negli appunti (lo fa la UI).

    Il lanciatore (`osascript` o `PLANCIA_TERMINALE`) parte con
    `stdin=DEVNULL` e lo stdout catturato, mai ereditato: `osascript -e
    'tell application "Terminal" to do script ...'` stampa da solo il
    riferimento della scheda aperta, e ogni altro sottoprocesso di questo
    modulo (recap, ingest, jarvis, cantiere) cattura la sua uscita per lo
    stesso motivo. Qui conta ancora di più perché L3-RIPRENDI-UI chiamerà
    `apri()` da dentro il server MCP (mcp.py), dove lo stdin del processo È
    il trasporto stdio del protocollo JSON-RPC: ereditarlo darebbe al
    lanciatore un canale che non gli appartiene, e una riga sullo stdout non
    catturata finirebbe nel flusso del protocollo. `timeout` copre il caso
    di un `PLANCIA_TERMINALE` (o un `osascript` bloccato) che non torna mai:
    senza, la chiamata resterebbe appesa per sempre.
    """
    proprio = conn is None
    if proprio:
        conn = store.connect()
        store.init_db(conn)
    try:
        s = stato(conn, task)
        if s["stato"] == "viva":
            return {"stato": "viva", "motivo": s["motivo"], "messaggio": messaggio(task)}
        argv = comando(task, s, conn)
        cwd = _campo(task, "cwd")
        if s["stato"] == "persa" or not cwd or not os.path.isdir(cwd):
            cwd = cantiere.cartella_per(conn, _campo(task, "project_id", None))
    finally:
        if proprio:
            conn.close()

    riga = piattaforma.riga_shell(cwd, argv)
    lanciatore = os.environ.get("PLANCIA_TERMINALE")
    if lanciatore:
        comando_lancio = [lanciatore, riga]
    else:
        comando_lancio = piattaforma.comando_terminale(cwd, argv)
    esito = {"stato": s["stato"], "argv": argv, "cwd": cwd, "riga": riga}
    if comando_lancio is None:
        esito["errore"] = ("nessun terminale trovato: installa uno fra x-terminal-emulator, "
                           "gnome-terminal, konsole o xterm, oppure imposta PLANCIA_TERMINALE")
        return esito
    if lanciatore or piattaforma.nome() == piattaforma.MAC:
        # `osascript` (o il lanciatore finto delle prove) torna subito: qui si
        # aspetta il suo esito, con un tetto.
        try:
            piattaforma.esegui(comando_lancio, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               text=True, check=False, timeout=_APRI_TIMEOUT_SECONDI)
        except subprocess.TimeoutExpired:
            esito["errore"] = "il lanciatore non ha risposto entro %ss" % _APRI_TIMEOUT_SECONDI
    else:
        # Un terminale di Linux (xterm, x-terminal-emulator) resta in primo piano
        # finche' la finestra e' aperta: aspettarlo, con un tetto, lo ucciderebbe
        # allo scadere. Si stacca e non si aspetta.
        try:
            piattaforma.avvia_distaccato(comando_lancio)
        except OSError as exc:
            esito["errore"] = "non riesco ad aprire il terminale: %s" % exc
    return esito


# --------------------------------------------------------------------------
# backfill
# --------------------------------------------------------------------------

def _batch_valido(batch) -> bool:
    # Stessa regola di plancia/slot.py (L0-SCHEMA): eventi.leggi(tipo=...)
    # spezza il filtro sulle virgole, e un batch vuoto o fatto di spazi non è
    # distinguibile da "nessun batch" quando si prova ad annullarlo.
    return isinstance(batch, str) and bool(batch.strip()) and "," not in batch \
        and not any(c.isspace() for c in batch)


def _sessione_per_backfill(conn, project_id, created_at):
    """La sessione dello stesso progetto viva al momento `created_at`, o la
    più vicina entro due ore quando nessuna sessione lo copre davvero."""
    if project_id is None:
        return None
    riga = conn.execute(
        "SELECT session_id, cwd, agent FROM sessions WHERE project_id=? "
        "AND started_at IS NOT NULL AND started_at<=? "
        "AND (ended_at IS NULL OR ended_at>=?) "
        "ORDER BY started_at DESC LIMIT 1",
        (project_id, created_at, created_at)).fetchone()
    if riga:
        return riga

    creato = _parse_ts(created_at)
    if creato is None:
        return None
    migliore = None
    for r in conn.execute(
            "SELECT session_id, cwd, agent, started_at FROM sessions "
            "WHERE project_id=? AND started_at IS NOT NULL", (project_id,)):
        inizio = _parse_ts(r["started_at"])
        if inizio is None:
            continue
        diff = abs((creato - inizio).total_seconds())
        if diff <= _BACKFILL_FINESTRA_SECONDI and (migliore is None or diff < migliore[0]):
            migliore = (diff, r)
    return migliore[1] if migliore else None


def backfill(conn, batch, secco=False) -> dict:
    """Associa ogni task senza `session_id` alla sessione più plausibile.

    Senza questo, ogni task scritto prima di L0-SESSIONE non riprende mai
    niente (i tre stati collassano tutti su "persa: mai registrata"). Scrive
    anche un evento per riga toccata, cosi' `annulla(batch)` può disfare
    esattamente e solo questo lotto di attribuzioni. `secco=True` conta e
    basta: non scrive né tasks né eventi.
    """
    if not _batch_valido(batch):
        return {"ok": False,
                "motivo": "batch non valido: vuoto o con virgole/spazi (non sarebbe annullabile)"}

    host_ora = socket.gethostname()
    trovati, non_trovati = 0, 0
    righe = conn.execute(
        "SELECT id, project_id, created_at FROM tasks WHERE session_id IS NULL").fetchall()
    for r in righe:
        sessione = _sessione_per_backfill(conn, r["project_id"], r["created_at"])
        if not sessione:
            non_trovati += 1
            continue
        trovati += 1
        if secco:
            continue
        conn.execute(
            "UPDATE tasks SET session_id=?, cwd=?, agent=?, host=?, updated_at=? WHERE id=?",
            (sessione["session_id"], sessione["cwd"] or "", sessione["agent"] or "claude",
             host_ora, store.now(), r["id"]))
        eventi.scrivi(f"attribuzione:{batch}",
                      f"task {r['id']} attribuito alla sessione {sessione['session_id']}",
                      None,
                      {"batch": batch, "task_id": r["id"], "sessione": sessione["session_id"],
                       "prima": {"session_id": None, "cwd": None, "agent": None, "host": None}})
    if not secco:
        conn.commit()
    return {"ok": True, "trovati": trovati, "non_trovati": non_trovati, "secco": bool(secco)}


def annulla(conn, batch) -> int:
    """Rimette NULL/vuoto dove `backfill(batch)` aveva scritto.

    Salta le righe che un batch più recente ha già cambiato (stesso motivo di
    `slot.annulla`): si confronta il `session_id` attuale del task con quello
    che questo batch gli aveva scritto, e si tocca solo se combaciano ancora.
    """
    righe = eventi.leggi(tipo=f"attribuzione:{batch}", limite=100000)
    ripristinati = 0
    ts = store.now()
    for riga in reversed(righe):
        dati = riga.get("dati") or {}
        tid = dati.get("task_id")
        if tid is None:
            continue
        r = conn.execute("SELECT session_id FROM tasks WHERE id=?", (tid,)).fetchone()
        if not r or r["session_id"] != dati.get("sessione"):
            continue
        conn.execute(
            "UPDATE tasks SET session_id=NULL, cwd='', agent='', host='', updated_at=? "
            "WHERE id=?", (ts, tid))
        ripristinati += 1
    conn.commit()
    return ripristinati
