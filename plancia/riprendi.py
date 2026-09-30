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
from datetime import datetime, timezone
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
    """True se `pid` è un processo vivo su questa macchina. Passa da
    `piattaforma.pid_vivo`: su Windows mandare un segnale a un processo lo uccide."""
    return piattaforma.pid_vivo(pid)


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
                             stdin=subprocess.DEVNULL, timeout=25,
                             **piattaforma.opzioni_figlio(), **piattaforma.opzioni_utf8())
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
    """Il `session_id` (str) che un lavoro senza testa può riprendere così
    com'è (`claude -p --resume <id>`, `codex exec resume <id>`), o `None`.

    Solo la sessione **chiusa**: una viva ha già qualcuno davanti, e scrivere
    nello stesso jsonl da due processi la rovina. Prima di LOTTO 21-RIPRENDI
    questa funzione rispondeva anche per la viva e il lancio la **forkava**
    (`--fork-session`): il lavoro finiva in una sessione nuova, mai in quella
    che il task aveva salvato. La decisione completa (riprendi, copia, nuova,
    niente) sta in `piano()`; questa resta per chi chiede solo "c'è
    qualcosa da riprendere senza rischi?".
    """
    return s.get("session_id") if s.get("stato") == "chiusa" else None


def stato(conn, task) -> dict:
    """I tre stati, calcolati per un task (righa di `tasks`, dict-like).

    Torna sempre `{"stato", "motivo", "agent", "session_id", "cwd", "host"}`.
    `conn` non serve oggi (i dati bastano dal task stesso), ma resta nella
    firma perché ogni altra funzione di lettura di Plancia la prende, e un
    domani "viva" potrebbe voler controllare anche `sessions` nel db.
    """
    return _stato_da(_campo(task, "agent", "claude"), _campo(task, "session_id", None),
                     _campo(task, "cwd", ""), _campo(task, "host", ""))


def _stato_da(agent, session_id, cwd="", host_task="") -> dict:
    """Il nucleo di `stato()`, sui quattro dati che servono davvero: chi
    lavora, l'id, la cartella, la macchina. Serve anche a chi ha solo un id di
    sessione (un lancio, una riga della lavagna) e non un task."""
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
    (un comando a cui viene passato, come unico argomento, la riga `cd <cwd> && `
    seguita dal comando già quotato: con `shlex` su macOS e Linux, con
    `list2cmdline` e `cd /d` su Windows); di default apre il terminale del
    sistema (`piattaforma.piano_terminale`): Terminal.app con AppleScript su
    macOS, Windows Terminal o una console nuova su Windows, il primo terminale
    che c'è su Linux. Per "viva" non lancia niente: torna solo il messaggio da
    mettere negli appunti (lo fa la UI).

    Su Windows il testo del task (il titolo, il prompt) non passa mai da una
    riga di `cmd.exe`: `wt.exe` riceve un argomento per ogni pezzo (con il `;`
    scappato) e senza `wt` il comando parte direttamente in una console nuova,
    nella cartella giusta.

    macOS e il lanciatore `PLANCIA_TERMINALE` partono con `stdin=DEVNULL` e lo
    stdout catturato, mai ereditato, e con un `timeout`: `osascript -e 'tell
    application "Terminal" to do script ...'` stampa da solo il riferimento
    della scheda aperta, e ogni altro sottoprocesso di questo modulo (recap,
    ingest, jarvis, cantiere) cattura la sua uscita per lo stesso motivo. Qui
    conta ancora di più perché L3-RIPRENDI-UI chiamerà `apri()` da dentro il
    server MCP (mcp.py), dove lo stdin del processo È il trasporto stdio del
    protocollo JSON-RPC: ereditarlo darebbe al lanciatore un canale che non gli
    appartiene, e una riga sullo stdout non catturata finirebbe nel flusso del
    protocollo. Il `timeout` copre il caso di un `PLANCIA_TERMINALE` (o un
    `osascript` bloccato) che non torna mai: senza, la chiamata resterebbe
    appesa per sempre. Un terminale di Linux o di Windows, invece, resta vivo
    finché la finestra è aperta: parte staccato (`piattaforma.avvia_distaccato`,
    sempre con stdin, stdout e stderr chiusi) e non si aspetta, quindi lì il
    timeout non c'è.
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
    piano = None
    if lanciatore:
        comando_lancio = [lanciatore, riga]
    else:
        piano = piattaforma.piano_terminale(cwd, argv)
        comando_lancio = piano["argv"] if piano else None
    esito = {"stato": s["stato"], "argv": argv, "cwd": cwd, "riga": riga}
    if comando_lancio is None:
        esito["errore"] = ((piano or {}).get("errore")
                           or "nessun terminale trovato: installa uno fra x-terminal-emulator, "
                              "gnome-terminal, konsole o xterm, oppure imposta PLANCIA_TERMINALE")
        esito["lanciato"] = False
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
            piattaforma.avvia_distaccato(comando_lancio, cwd=piano["cwd"],
                                         nuova_console=piano["nuova_console"])
        except OSError as exc:
            esito["errore"] = "non riesco ad aprire il terminale: %s" % exc
            esito["lanciato"] = False
    return esito


# --------------------------------------------------------------------------
# il lavoro senza testa: nella sessione di origine, non in una nuova
# --------------------------------------------------------------------------
#
# LOTTO 21-RIPRENDI (verdetto di Eugenio, 30/09/2026): i task e i lanci devono
# proseguire nelle STESSE sessioni di Claude Code o di Codex che li hanno
# salvati, non in una sessione creata apposta per il task. Prima solo "Riprendi"
# nel Terminale lo faceva; "In background", le proposte "Rilancia"/"Riprendi" e
# i lanci del cantiere partivano sempre da una sessione nuova (o da un fork,
# che è comunque un id nuovo e una storia che poi nessuno ritrova).
#
# Le quattro cose che possono succedere, decise qui e in nessun altro posto:
#
# - "riprendi": la sessione è chiusa e la sua trascrizione c'è. Il lavoro
#   continua NELLA stessa sessione (stesso id), nella sua cartella.
# - "copia": la sessione è aperta da qualche parte e si è chiesto
#   esplicitamente una copia. Parte una sessione nuova con la stessa storia
#   (`--fork-session`, `codex exec fork`): quella aperta non riceve niente.
# - "nuova": la sessione è davvero persa (mai registrata, scaduta, di un'altra
#   macchina, senza più la sua cartella). Si riparte da zero col contesto
#   scritto a mano, e l'interfaccia lo dice PRIMA di partire.
# - "niente": la sessione è aperta e non si è chiesta una copia. Non si lancia
#   niente da qui: un secondo processo sullo stesso jsonl la rovinerebbe. Si
#   torna il messaggio da incollare dentro la sessione.

MODI = ("riprendi", "copia", "nuova", "niente")

_AVVISI = {
    "riprendi": "Riprende la sessione originale ({sid}) nella sua cartella: "
                "il lavoro continua lì, non in una sessione nuova.",
    "copia": "La sessione ({sid}) è aperta altrove: parte una COPIA con la stessa "
             "storia, e quella aperta non riceve niente.",
    "nuova": "Non c'è una sessione da riprendere ({motivo}): parte una sessione "
             "NUOVA, con il contesto scritto a mano.",
    "niente": "La sessione ({sid}) è aperta ({motivo}): da qui non la tocco. "
              "Incolla il messaggio direttamente lì.",
}


def _riga_sessione(conn, session_id):
    """La riga di `sessions` per questo id, o None (anche se il db non c'è)."""
    if conn is None or not session_id:
        return None
    try:
        return conn.execute("SELECT cwd, agent FROM sessions WHERE session_id=?",
                            (session_id,)).fetchone()
    except Exception:
        return None


def _rollout_e_nostro(conn, session_id) -> bool:
    """True se l'ultimo tocco al rollout Codex di questa sessione e' di un lancio
    di Plancia gia' finito (e nessuno e' in corso): per Codex "viva" e' solo
    "toccato negli ultimi 10 minuti", e senza questo un secondo lancio subito
    dopo il primo si vedrebbe rifiutare una sessione che ha chiuso lui."""
    rollout = _rollout_per_id(session_id)
    if rollout is None or conn is None:
        return False
    try:
        in_corso = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE sessione=? AND stato IN ('in coda','in corso')",
            (session_id,)).fetchone()[0]
        fine = conn.execute(
            "SELECT MAX(fine) FROM runs WHERE sessione=? AND fine IS NOT NULL",
            (session_id,)).fetchone()[0]
        toccato = rollout.stat().st_mtime
    except Exception:
        return False
    chiuso = _parse_ts(fine)
    if in_corso or chiuso is None:
        return False
    # _parse_ts torna un naive UTC: lo si riporta a un istante
    fine_ts = chiuso.replace(tzinfo=timezone.utc).timestamp()
    return toccato <= fine_ts + 5


def piano(conn, agente, session_id, cwd="", host="", copia=False) -> dict:
    """Cosa succede a un lavoro senza testa che parte da questa sessione.

    Torna sempre `{"modo", "stato", "motivo", "agent", "origine", "sessione",
    "cwd", "avviso"}`. `modo` è uno di `MODI`; `origine` è la sessione a cui il
    lavoro faceva capo (anche quando si riparte da una nuova), `sessione` è
    quella che il comando riprende davvero (vuota per "nuova" e "niente");
    `avviso` è la frase da mostrare PRIMA di lanciare.

    `cwd` e `agente` mancanti si leggono dalla riga di `sessions`: una riga
    della lavagna o un lancio portano solo l'id. `copia=True` chiede una copia
    invece di riprendere l'originale (utile soprattutto se è aperta).
    """
    agente = agente or "claude"
    cwd = cwd or ""
    riga = _riga_sessione(conn, session_id)
    if riga is not None:
        cwd = cwd or (riga["cwd"] or "")
        if riga["agent"] in ("claude", "codex"):
            agente = riga["agent"]
    s = _stato_da(agente, session_id, cwd, host)
    if s["stato"] == "viva" and agente == "codex" and _rollout_e_nostro(conn, session_id):
        # il rollout e' stato toccato da poco, ma dal lancio di Plancia che e'
        # appena finito su questa stessa sessione: nessuno la tiene aperta
        s = dict(s, stato="chiusa",
                 motivo="il rollout è stato toccato da un lancio di Plancia appena finito")
    sid = (session_id or "")[:8]
    stato_s = s["stato"]

    if stato_s == "persa":
        modo = "nuova"
        motivo = s["motivo"]
    elif stato_s == "viva" and not copia:
        modo = "niente"
        motivo = s["motivo"]
    else:
        modo = "copia" if copia else "riprendi"
        motivo = s["motivo"]
        # Riprendere o copiare vuole la cartella in cui la sessione è nata:
        # senza, l'agente non ritrova la sua trascrizione.
        if not cwd or not os.path.isdir(cwd):
            modo = "nuova"
            motivo = "la cartella della sessione non c'è più" if cwd else \
                "della sessione non si sa la cartella"
    return {"modo": modo, "stato": stato_s, "motivo": motivo, "agent": agente,
            "origine": session_id or None,
            "sessione": session_id if modo in ("riprendi", "copia") else None,
            "cwd": cwd,
            "avviso": _AVVISI[modo].format(sid=sid, motivo=motivo)}


def lancia(conn, titolo, dettaglio="", progetto=None, istruzioni="", agente="claude",
           scrive=False, cwd=None, task_id=None, lingua="it", sessione=None, task=None,
           copia=False, anteprima=False, compartimento="", attendi=False, modo=None,
           prompt_pronto=None, lett=None) -> dict:
    """L'unica porta per un lavoro senza testa che ha (forse) una sessione.

    Dashboard, MCP, riga di comando e Jarvis passano tutti da qui: decidono
    qui, con `piano()`, se il lavoro riprende la sessione di origine, ne fa una
    copia, riparte da una nuova o non parte affatto.

    La sessione di origine è `sessione` se data, altrimenti quella del task
    (`task` già letto, oppure `task_id`). Con `anteprima=True` non parte niente:
    torna solo il piano, così l'interfaccia lo dice prima. Con "niente" (sessione
    aperta, nessuna copia chiesta) neppure parte: torna `lanciato=False`, il piano
    e, se c'è un task, il messaggio da incollare nella sessione.

    Altrimenti torna quello di `cantiere.avvia()` più `lanciato=True`, `piano` e
    `continua` (il modo scelto). `lett` è la connessione da cui leggere task e
    sessioni (le viste dei compartimenti); la scrittura va sempre su `conn`.
    """
    lett = lett or conn
    if task is None and task_id is not None:
        from . import actions
        task = actions.task_get(lett, int(task_id))
    # la cartella data insieme a una sessione esplicita e' quella della sessione
    origine, cwd_origine, host = sessione, (cwd or "") if sessione else "", ""
    if not origine and task:
        origine = _campo(task, "session_id", None)
        cwd_origine = _campo(task, "cwd", "")
        host = _campo(task, "host", "")
    agente_origine = (_campo(task, "agent", "") or agente) if task else agente
    p = piano(lett, agente_origine, origine, cwd_origine, host, copia)

    if anteprima:
        return {"lanciato": False, "anteprima": True, "piano": p}
    if p["modo"] == "niente":
        fuori = {"lanciato": False, "piano": p, "stato": p["stato"], "motivo": p["motivo"]}
        if task:
            fuori["messaggio"] = messaggio(task)
        return fuori

    riprende = p["modo"] in ("riprendi", "copia")
    esito = cantiere.avvia(
        conn, titolo, dettaglio=dettaglio, progetto=progetto, istruzioni=istruzioni,
        agente=p["agent"] if riprende else agente, scrive=scrive,
        cwd=p["cwd"] if riprende else cwd,
        task_id=task_id if task_id is not None else (task["id"] if task else None),
        lingua=lingua, attendi=attendi, sessione=p["sessione"], modo=modo,
        compartimento=compartimento, copia=(p["modo"] == "copia"),
        prompt_pronto=prompt_pronto)
    esito["lanciato"] = True
    esito["piano"] = p
    esito["continua"] = p["modo"]
    return esito


def rilancia_run(conn, run_id, scrive=None, lingua="it", anteprima=False,
                 compartimento="", copia=False, lett=None, attendi=False):
    """Rilancia un lancio del cantiere: riprende la conversazione in cui era
    girato (`runs.sessione`) se è ancora riprendibile, altrimenti quella del suo
    task, altrimenti riparte con lo stesso prompt. `None` se il lancio non c'è.

    `scrive=None` tiene il modo del lancio originale; `True`/`False` lo forzano.
    `lett` è la connessione da cui leggere il lancio e il task (le viste dei
    compartimenti); la scrittura va sempre su `conn`.
    """
    lett = lett or conn
    r = lett.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not r:
        return None
    from . import actions
    task = actions.task_get(lett, r["task_id"]) if r["task_id"] else None
    originale_scrive = (r["modo"] == "esegui")
    scrive_ora = originale_scrive if scrive is None else bool(scrive)

    origine, cwd_origine, host = r["sessione"], r["cwd"] or "", ""
    if not origine and task:
        origine = _campo(task, "session_id", None)
        cwd_origine = _campo(task, "cwd", "") or cwd_origine
        host = _campo(task, "host", "")
    p = piano(lett, r["agente"], origine, cwd_origine, host, copia)

    if anteprima:
        return {"lanciato": False, "anteprima": True, "piano": p}
    if p["modo"] == "niente":
        fuori = {"lanciato": False, "piano": p, "stato": p["stato"], "motivo": p["motivo"]}
        if task:
            fuori["messaggio"] = messaggio(task)
        return fuori

    riprende = p["modo"] in ("riprendi", "copia")
    if riprende:
        esito_prec = (r["esito"] or "").strip().replace("\n", " ")[:300]
        testo = (f"Il lancio n. {r['id']} si era chiuso come «{r['stato']}»"
                 + (f": {esito_prec}" if esito_prec else "")
                 + ". Riprendi da dove eri arrivato e portalo a termine.")
        verbatim = testo
    elif scrive_ora == originale_scrive:
        # stesso modo: il prompt di prima com'era, non il suo inizio dentro un
        # prompt nuovo
        verbatim = r["prompt"]
    else:
        verbatim = None
    titolo = (r["prompt"] or "")[:200]
    esito = cantiere.avvia(
        conn, titolo, agente=p["agent"] if riprende else r["agente"], scrive=scrive_ora,
        cwd=p["cwd"] if riprende else r["cwd"], task_id=r["task_id"], lingua=lingua,
        attendi=attendi, sessione=p["sessione"], compartimento=compartimento,
        copia=(p["modo"] == "copia"), prompt_pronto=verbatim)
    esito["lanciato"] = True
    esito["piano"] = p
    esito["continua"] = p["modo"]
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
