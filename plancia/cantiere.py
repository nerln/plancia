"""Il cantiere: un task smette di essere una nota e diventa lavoro fatto.

Prendi una riga della lavagna, scrivi come la vuoi fatta, scegli chi la fa, e
Plancia lancia l'agente giusto nella cartella giusta, ne segue l'avanzamento e
registra cosa è successo.

Due modi, e la differenza è tutta qui:

- **proposta**: l'agente può leggere e cercare, non può scrivere. Ti risponde
  con cosa farebbe. È il modo predefinito, perché lanciare un agente che
  modifica file senza averlo chiesto esplicitamente è un ottimo modo per
  rovinare una giornata.
- **esegui**: l'agente può modificare i file dentro la cartella del progetto.
  Si sceglie una volta per lancio, mai in automatico.

Il lancio vive dentro il processo che lo ha avviato, in un thread daemon. Se
quel processo finisce, il thread muore con lui e il lancio resta appeso finché
`riconcilia()` non lo chiude al riavvio. In pratica funziona perché a lanciare è
il server, che sta su: mandare un lancio da uno script che poi esce vuol dire
buttarlo via, e il 4 agosto 2026 è successo per davvero, tre volte di fila.
Questa riga prima diceva il contrario.
"""

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from . import config, eventi, piattaforma, recap, store

LOG_DIR = config.DATA_DIR / "cantiere"

AGENTI = ("claude", "codex")
# "proposta"/"esegui" restano le due stringhe scritte in runs.modo e lette
# dalla testata del prompt (`TESTATA`, sotto): la scelta vera fra le due,
# però, ora la fa il booleano `scrive` (vedi `_scrive_da`), non più un
# controllo di appartenenza a un elenco di modi validi.

# Cosa può toccare l'agente nei due modi.
TOOL_LETTURA = ["Read", "Glob", "Grep", "WebSearch", "WebFetch",
                # git per intero: con i permessi per singolo sottocomando
                # `git -C ...` non passa e l'agente resta cieco
                "Bash(git:*)", "Bash(ls:*)", "Bash(rg:*)", "Bash(cat:*)",
                "mcp__plancia__plancia_briefing", "mcp__plancia__plancia_search",
                "mcp__plancia__plancia_projects", "mcp__plancia__plancia_memory",
                "mcp__plancia__plancia_sessions", "mcp__plancia__plancia_tasks",
                # I post mancavano da tutte e due le liste, e senza di loro il
                # lato social del cantiere non era raggiungibile: un lancio a cui
                # si chiede una bozza si fermava a chiedere il permesso.
                "mcp__plancia__plancia_posts", "mcp__plancia__plancia_lavagna"]
TOOL_SCRITTURA = TOOL_LETTURA + ["Edit", "Write", "MultiEdit", "NotebookEdit", "Bash",
                                 "mcp__plancia__plancia_task_update",
                                 "mcp__plancia__plancia_log",
                                 "mcp__plancia__plancia_project_update",
                                 "mcp__plancia__plancia_post_add",
                                 "mcp__plancia__plancia_post_update"]


def codex_bin() -> str:
    cfg = config.load_config()
    candidati = [cfg.get("codex_bin"),
                 "/Applications/ChatGPT.app/Contents/Resources/codex",
                 str(config.HOME / ".local/bin/codex"), "/opt/homebrew/bin/codex"]
    for c in candidati:
        if c and os.access(c, os.X_OK):
            return c
    import shutil
    return shutil.which("codex") or ""


# --------------------------------------------------------------------------
# il prompt
# --------------------------------------------------------------------------

TESTATA = {
    "proposta": (
        "Non modificare nessun file. Guarda com'è messa la cosa e rispondi con "
        "cosa faresti: i passi concreti, i file toccati, e i punti dove potresti "
        "sbagliare. Se serve una decisione che non puoi prendere tu, chiedila."),
    "esegui": (
        "Fai il lavoro. Parti da quello che c'è invece di riscrivere, e verifica "
        "che quello che hai cambiato funzioni prima di dire che è fatto."),
}

CHIUSURA = (
    "Alla fine scrivi due righe soltanto, in {lingua}, che dicano cosa hai fatto "
    "davvero e cosa resta aperto. Niente elenchi, niente markdown: quelle due "
    "righe vengono lette ad alta voce.")


# Nella sessione ripresa il permesso di scrivere lo decide `_comando`, ma
# l'agente non lo sa: una riga breve gli dice che è una proposta.
SOLA_LETTURA = ("Solo lettura: non modificare nessun file. Dimmi cosa faresti e "
                "cosa potrebbe andare storto.")


def componi_prompt(conn, titolo, dettaglio="", progetto=None, istruzioni="",
                   modo="proposta", lingua="it", task_id=None, sessione=None,
                   prompt_pronto=None) -> str:
    """Il prompt di un lancio. `prompt_pronto`, se dato, è il testo intero (senza
    sessione) o il messaggio di ripresa (con sessione): niente altro si compone."""
    if prompt_pronto and not sessione:
        return prompt_pronto
    if sessione:
        # La sessione ripresa (`--resume`/`exec resume`, vedi _comando) ha già
        # tutto il contesto del progetto: rifarglielo da capo (titolo,
        # summary, cartelle, memoria...) è lavoro sprecato e rischia pure di
        # contraddire quello che la conversazione sa già. Il task_id serve
        # solo a farsi riconoscere ("il task N di Plancia"), non a
        # ricomporre altro: senza task_id la frase diventa più generica.
        if prompt_pronto:
            pezzi = [prompt_pronto]
        else:
            pezzi = [f"riprendi il task {task_id} di Plancia: {titolo}."] if task_id else \
                [f"riprendi da Plancia: {titolo}."]
        if istruzioni:
            pezzi.append(istruzioni)
        if modo != "esegui":
            pezzi.append(SOLA_LETTURA)
        return " ".join(pezzi)

    pezzi = [TESTATA.get(modo, TESTATA["proposta"]), "", f"## Il lavoro\n{titolo}"]
    if dettaglio:
        pezzi.append(dettaglio)
    if istruzioni:
        pezzi.append(f"\n## Come lo voglio fatto\n{istruzioni}")

    if progetto:
        riga = store.get_project(conn, progetto)
        if riga:
            contesto = [f"\n## Il progetto\n{riga['name']}"]
            if riga["summary"]:
                contesto.append(riga["summary"])
            if riga["next_action"]:
                contesto.append(f"Prossimo passo dichiarato: {riga['next_action']}")
            percorsi = [r["value"] for r in conn.execute(
                "SELECT value FROM project_links WHERE project_id=? AND kind='path'",
                (riga["id"],))]
            if percorsi:
                contesto.append("Cartelle: " + ", ".join(percorsi))
            memorie = [r["name"] for r in conn.execute(
                "SELECT name FROM knowledge WHERE project_id=? LIMIT 3", (riga["id"],))]
            if memorie:
                contesto.append("Memoria di riferimento: " + ", ".join(memorie) +
                                ". Leggila con plancia_memory prima di partire.")
            pezzi.append("\n".join(contesto))

    pezzi.append("\n" + CHIUSURA.format(lingua=recap.NOMI_LINGUA.get(lingua, "English")))
    return "\n".join(pezzi)


def cartella_per(conn, progetto=None) -> str:
    """Dove far lavorare l'agente.

    Un progetto può avere più cartelle collegate. Si sceglie quella che è un
    repository git, perché è lì che sta il codice; la cartella dei dati di
    Plancia si scarta sempre. Sbagliare qui non è un dettaglio: Claude Code non
    legge fuori dalla cartella in cui parte, quindi l'agente resterebbe cieco.
    """
    dati = os.path.normpath(str(config.DATA_DIR))
    if progetto:
        riga = store.get_project(conn, progetto)
        if riga:
            candidati = [r["value"] for r in conn.execute(
                "SELECT value FROM project_links WHERE project_id=? AND kind='path'",
                (riga["id"],))]
            r = conn.execute("SELECT local_path FROM repos WHERE project_id=? "
                             "AND local_path IS NOT NULL", (riga["id"],)).fetchone()
            if r:
                candidati.append(r["local_path"])
            buoni = [c for c in candidati
                     if c and os.path.isdir(c) and os.path.normpath(c) != dati]
            for c in buoni:
                if os.path.isdir(os.path.join(c, ".git")):
                    return c
            if buoni:
                return buoni[0]
    return str(config.HOME)


# --------------------------------------------------------------------------
# l'esecuzione
# --------------------------------------------------------------------------

def _comando(agente: str, scrive=False, cwd: str = "", sessione=None, modo=None,
             copia=False) -> list:
    """L'argv del lancio. `scrive` sceglie i permessi (letto sotto);
    `sessione`, se data, riprende QUELLA conversazione, con lo stesso id
    (`claude -p --resume <id>`, `codex exec resume <id>`): è il punto del
    LOTTO 21-RIPRENDI, il lavoro continua nella sessione che il task aveva
    salvato. Con `copia=True` invece ne parte una copia (`--fork-session`,
    `codex exec fork <id>`) che ha la stessa storia ma un id nuovo: si usa
    solo quando la sessione è aperta altrove e si è chiesto di proseguire lo
    stesso. Prima di questo lotto il fork era l'unica strada, anche per una
    sessione chiusa.
    `modo`/`scrive` stringa: vedi `_scrive_da`, chiamata qui per prima cosa
    così anche chi passa ancora `_comando(agente, "proposta", cwd)` alla
    vecchia maniera (posizionale, nello slot che oggi si chiama `scrive`)
    ottiene il booleano giusto invece di un `bool("proposta")` sempre vero.
    """
    scrive = _scrive_da(modo, scrive)
    if agente == "codex":
        exe = codex_bin()
        if not exe:
            raise RuntimeError("Codex non è installato")
        sandbox = "workspace-write" if scrive else "read-only"
        # Letto `codex exec resume --help` (mai lanciato un agente vero, solo
        # --help) con /Applications/ChatGPT.app/Contents/Resources/codex,
        # codex-cli 0.154.0-alpha.6.2: il sottocomando `resume` NON elenca
        # `--cd`/`--sandbox`/`--color` fra le sue opzioni (ha solo
        # --skip-git-repo-check, -c, --last, --all, -m, --json...), quindi
        # vanno prima di lui, sul comando padre `exec`. Verificato che
        # `codex exec --cd /tmp --sandbox read-only --skip-git-repo-check
        # --color never resume <id> --help` viene accettato dal parser
        # (l'ordine opposto, con le opzioni dopo `resume`, dà "error:
        # unexpected argument --cd found"); non verificato dal vivo se una
        # sessione ripresa onora davvero il `--sandbox` del padre (nessun
        # agente lanciato per controllarlo). L'id resta posizionale; il
        # prompt in coda è '-', perché l'help di `exec resume` dice che con
        # '-' il prompt si legge da stdin, ed `_esegui` scrive il messaggio
        # su stdin invece che come argomento (vedi sotto).
        base = [exe, "exec", "--cd", cwd, "--sandbox", sandbox,
                "--skip-git-repo-check", "--color", "never"]
        if sessione:
            # `codex exec fork <id> -` esiste (letto con --help, mai lanciato):
            # stessa forma di `resume`, prompt da stdin.
            base += ["fork" if copia else "resume", sessione, "-"]
        return base
    exe = recap.claude_bin()
    if not exe:
        raise RuntimeError("Claude Code non è installato")
    cfg = config.load_config()
    # Una conversazione dell'utente si riprende col SUO modello: `--model` la
    # cambierebbe a meta' (l'utente la aveva aperta con Opus, e il lavoro
    # ripartirebbe con Sonnet senza dirglielo). Il modello del cantiere serve
    # solo alle sessioni nuove, che un modello lo devono scegliere.
    cmd = [exe, "-p"]
    if not sessione:
        cmd += ["--model", cfg.get("modello_cantiere", "sonnet")]
    cmd += ["--output-format", "stream-json", "--verbose"]
    if sessione:
        # Senza `--fork-session` claude riprende la sessione con lo stesso id
        # (letto in `claude --help`: "--fork-session: When resuming, create a
        # new session ID instead of reusing the original"). Il chiamante
        # (`riprendi.lancia`) ha già controllato che la sessione non sia
        # aperta: due processi sullo stesso jsonl la rovinerebbero, ed è per
        # questo che una viva si copia (`copia=True`) o non si tocca.
        cmd += ["--resume", sessione]
        if copia:
            cmd += ["--fork-session"]
    if scrive:
        cmd += ["--permission-mode", "acceptEdits", "--allowedTools"] + TOOL_SCRITTURA
    else:
        cmd += ["--allowedTools"] + TOOL_LETTURA
    return cmd


def _leggi_claude(riga: str, acc: dict):
    """Estrae dallo stream quello che serve: sessione, esito, token, permessi negati."""
    try:
        d = json.loads(riga)
    except Exception:
        return
    if d.get("session_id") and not acc.get("sessione"):
        acc["sessione"] = d["session_id"]
    if d.get("type") == "result":
        acc["esito"] = (d.get("result") or "").strip()
        acc["token"] = ((d.get("usage") or {}).get("output_tokens") or 0)
        acc["costo"] = d.get("total_cost_usd") or 0
        acc["errore"] = bool(d.get("is_error"))
        # Una sessione che si ferma a chiedere un permesso esce con zero e senza
        # errore: per il sistema operativo è andata bene, e il lavoro non c'è.
        acc["negati"] = sorted({
            (p or {}).get("tool_name", "")
            for p in (d.get("permission_denials") or [])
            if (p or {}).get("tool_name")
        })


# Codex, quando l'app ChatGPT/Codex Desktop tiene aperto il thread, rifiuta
# `exec resume` con un errore di questo tipo (nota vera di questa macchina).
_CONFLITTO_CODEX = ("thread-store conflict", "already has an active writer")
_ID_SESSIONE_CODEX = re.compile(r"session id:\s*([0-9a-fA-F][0-9a-fA-F-]{30,})")


def _leggi_codex(riga: str, acc: dict):
    """Dallo stream di testo di Codex: l'id della sessione (la riga
    `session id: ...` dell'intestazione) e il conflitto col thread aperto."""
    if not acc.get("sessione"):
        m = _ID_SESSIONE_CODEX.search(riga)
        if m:
            acc["sessione"] = m.group(1)
    bassa = riga.lower()
    if any(k in bassa for k in _CONFLITTO_CODEX):
        acc["conflitto"] = True


TESTO_CONFLITTO = (
    "Codex non può riprendere questa sessione da qui: l'app ChatGPT/Codex la tiene "
    "aperta. Chiudi quel thread e riprova, oppure chiedi una copia o una sessione nuova.")


def _scrive_da(modo=None, scrive=False) -> bool:
    """Il booleano vero dietro `modo` ("proposta"/"esegui") o `scrive`.

    Funzione a parte (invece di stare dentro `avvia`) perché è l'unico pezzo
    di questa traduzione che si può provare senza lanciare un agente vero:
    `avvia()` in fondo fa partire un processo reale anche con `attendi=False`
    (il thread parte comunque), quindi le prove passano di qui, non da lì.

    - `modo` dato (non None) vince sempre: è la firma con cui chiama ancora
      `plancia_manda` in mcp.py (uno dei "sei tool primi", non toccato da
      LOTTO-L3-RITOCCO), per parola chiave o per posizione (nello slot dove
      prima stava `modo`, che ora si chiama `scrive`: una stringa lì dentro è
      quindi il segno di una chiamata vecchio stile, non un errore). Da
      LOTTO-L3-RITOCCO (punto 13), /api/cantiere (api.py) e
      `jarvis._esegui_proposta` passano `scrive` (bool) come tutto il resto:
      questo alias resta solo per chi non è stato ancora toccato.
    - senza `modo`, una stringa in `scrive` viene letta allo stesso modo (lo
      stesso slot posizionale di `plancia_manda`, che passa "proposta"/
      "esegui" senza usare la parola chiave `modo=`).
    - altrimenti `scrive` è già il booleano che dice.
    """
    if modo is not None:
        return modo == "esegui"
    if isinstance(scrive, str):
        return scrive == "esegui"
    return bool(scrive)


def avvia(conn, titolo, dettaglio="", progetto=None, istruzioni="", agente="claude",
          scrive=False, cwd=None, task_id=None, lingua="it", attendi=False,
          sessione=None, modo=None, compartimento="", copia=False,
          prompt_pronto=None) -> dict:
    """Mette in coda un lancio e lo fa partire. Torna subito con l'id.

    `sessione` è la conversazione da RIPRENDERE con lo stesso id, non da forkare
    (LOTTO 21-RIPRENDI); `copia=True` ne fa invece una copia con id nuovo.
    Chi decide se è lecito riprenderla (chiusa? viva? persa?) è
    `riprendi.lancia()`, che è la porta da usare: questa funzione si fida.
    `prompt_pronto` è il prompt intero (senza sessione) o il messaggio di
    ripresa (con sessione), scritto da chi chiama.

    `compartimento` (vuoto per il predefinito) e' il nome del compartimento
    nominato da cui parte il lancio (la sua vista, la sua sessione): finisce in
    `runs.compartimento` e il lancio compare in quella vista e in nessun'altra,
    anche se parte da una cartella che non dice di chi e' (vedi
    compartimenti_viste.py).

    `scrive` (bool) ha preso il posto di `modo` ("proposta"/"esegui") come
    unico interruttore per i permessi: sceglie fra `TOOL_LETTURA` e
    `TOOL_SCRITTURA` in `_comando`. `modo` resta come alias di compatibilità
    per chi lo passa ancora (`plancia_manda` in mcp.py, uno dei "sei tool
    primi": vedi `_scrive_da`). api.py e jarvis.py sono passati a `scrive` con
    LOTTO-L3-RITOCCO (punto 13). Il valore stringa ("esegui"/"proposta")
    resta comunque quello scritto in `runs.modo` e usato per la testata del
    prompt: non è sparito, è solo derivato da `scrive` invece che essere la
    fonte di verità.
    """
    agente = agente if agente in AGENTI else "claude"
    scrive = _scrive_da(modo, scrive)
    modo = "esegui" if scrive else "proposta"

    cwd = cwd or cartella_per(conn, progetto)
    prompt = componi_prompt(conn, titolo, dettaglio, progetto, istruzioni, modo, lingua,
                            task_id, sessione, prompt_pronto)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cur = conn.execute(
        "INSERT INTO runs(task_id, agente, modo, prompt, cwd, stato, inizio) "
        "VALUES(?,?,?,?,?,'in coda',?)",
        (task_id, agente, modo, prompt, cwd, store.now()))
    run_id = cur.lastrowid
    if compartimento:
        conn.execute("UPDATE runs SET compartimento=? WHERE id=?", (compartimento, run_id))
    log = LOG_DIR / f"run-{run_id}.log"
    conn.execute("UPDATE runs SET log=? WHERE id=?", (str(log), run_id))
    if sessione and not copia:
        # riprende la STESSA conversazione: l'id lo si sa già, prima ancora
        # che l'agente risponda (una copia ne avrà uno suo, letto dallo stream)
        conn.execute("UPDATE runs SET sessione=? WHERE id=?", (sessione, run_id))
    if task_id:
        conn.execute("UPDATE tasks SET status='in corso', agent=?, run_id=?, updated_at=? "
                     "WHERE id=?", (agente, run_id, store.now(), task_id))
    conn.commit()

    eventi.scrivi("lavoro.avviato", titolo=titolo, progetto=progetto,
                  dati={"run": run_id, "agente": agente, "modo": modo, "cwd": cwd,
                        "sessione": sessione,
                        "continua": ("copia" if copia else "riprendi") if sessione else "nuova"})

    if attendi:
        _esegui(run_id, agente, scrive, prompt, cwd, str(log), titolo, progetto, task_id,
               sessione, copia)
    else:
        threading.Thread(target=_esegui, daemon=True,
                         args=(run_id, agente, scrive, prompt, cwd, str(log), titolo,
                               progetto, task_id, sessione, copia)).start()
    return {"run": run_id, "agente": agente, "modo": modo, "cwd": cwd, "log": str(log),
            "sessione": sessione or None,
            "continua": ("copia" if copia else "riprendi") if sessione else "nuova"}


def _esegui(run_id, agente, scrive, prompt, cwd, log, titolo, progetto, task_id,
           sessione=None, copia=False):
    conn = store.connect()
    store.init_db(conn)
    acc = {"sessione": None, "esito": "", "token": 0, "costo": 0, "errore": False,
           "negati": []}
    inizio = time.time()
    try:
        cmd = _comando(agente, scrive, cwd, sessione, copia=copia)
    except RuntimeError as exc:
        _chiudi(conn, run_id, "fallito", str(exc), acc, titolo, progetto, task_id, scrive)
        conn.close()
        return

    conn.execute("UPDATE runs SET stato='in corso' WHERE id=?", (run_id,))
    conn.commit()
    try:
        with open(log, "w", encoding="utf-8") as fh:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1,
                                    cwd=cwd, env=dict(os.environ),
                                    **piattaforma.opzioni_figlio(),
                                    **piattaforma.opzioni_utf8())
            conn.execute("UPDATE runs SET pid=? WHERE id=?", (proc.pid, run_id))
            conn.commit()
            proc.stdin.write(prompt)
            proc.stdin.close()
            ultime = []
            for riga in proc.stdout:
                fh.write(riga)
                if agente == "claude":
                    _leggi_claude(riga, acc)
                else:
                    # Codex scrive testo: l'esito è la coda dell'output
                    _leggi_codex(riga, acc)
                    ultime.append(riga.rstrip())
                    if len(ultime) > 40:
                        ultime.pop(0)
            proc.wait(timeout=3600)
            if agente == "codex" and not acc["esito"]:
                acc["esito"] = "\n".join(ultime[-12:]).strip()
            if agente == "codex" and acc.get("conflitto"):
                # Il thread è aperto nell'app: non è un guasto, è una sessione
                # occupata. Lo si dice com'è invece di lasciare "fallito" muto.
                stato = "bloccato"
                acc["esito"] = TESTO_CONFLITTO
            elif proc.returncode != 0 or acc["errore"]:
                stato = "fallito"
            elif acc.get("negati"):
                # Uscita pulita, lavoro non fatto: l'agente ha chiesto un
                # permesso e si è fermato. Chiamarlo riuscito faceva chiudere
                # il task come "fatto" senza che nessuno avesse fatto niente.
                stato = "bloccato"
                mancanti = ", ".join(acc["negati"])
                acc["esito"] = (
                    f"Si è fermato perché non ha il permesso di usare: {mancanti}. "
                    f"{acc.get('esito') or ''}"
                ).strip()
            else:
                stato = "riuscito"
    except Exception as exc:
        stato, acc["esito"] = "fallito", f"{type(exc).__name__}: {exc}"

    acc["durata"] = round(time.time() - inizio)
    _chiudi(conn, run_id, stato, acc["esito"], acc, titolo, progetto, task_id, scrive)
    conn.close()


def _chiudi(conn, run_id, stato, esito, acc, titolo, progetto, task_id, scrive):
    # `sessione=COALESCE(?, sessione)`: un lancio che RIPRENDE una sessione ne
    # scrive l'id in `avvia()`, prima ancora di partire. Se lo stream non porta
    # nessun session_id (il lancio fallisce subito, o Codex e' occupato) `acc`
    # non ha niente da dire, e sovrascrivere con NULL faceva perdere la sessione
    # proprio a chi ne aveva piu' bisogno: "Rilancia" ripartiva da una nuova.
    conn.execute(
        "UPDATE runs SET stato=?, fine=?, esito=?, sessione=COALESCE(?, sessione), "
        "token=?, costo=? WHERE id=?",
        (stato, store.now(), (esito or "")[:4000], acc.get("sessione"),
         acc.get("token") or 0, acc.get("costo") or 0, run_id))
    modo = "esegui" if scrive else "proposta"
    if task_id:
        # Solo l'esecuzione vera chiude il task: una proposta lo lascia aperto,
        # perché proporre non è fare. E un lancio bloccato resta bloccato anche
        # sul task, altrimenti sparisce dalla lavagna come se fosse a posto.
        if stato == "bloccato" and acc.get("conflitto"):
            # la sessione era occupata, il task non è cambiato: resta com'era
            nuovo = "aperto"
        elif stato == "bloccato":
            nuovo = "bloccato"
        elif stato == "riuscito" and scrive:
            nuovo = "fatto"
        else:
            nuovo = "aperto"
        conn.execute("UPDATE tasks SET status=?, updated_at=?, done_at=? WHERE id=?",
                     (nuovo, store.now(), store.now() if nuovo == "fatto" else None, task_id))
    conn.commit()
    eventi.scrivi("lavoro.completato" if stato == "riuscito" else "lavoro.fallito",
                  titolo=titolo, progetto=progetto,
                  dati={"run": run_id, "modo": modo, "esito": (esito or "")[:1200],
                        "durata_s": acc.get("durata"), "token": acc.get("token"),
                        "sessione": acc.get("sessione")})
    try:
        from . import briefing
        briefing.write_cache()
    except Exception:
        pass


# --------------------------------------------------------------------------
# lettura
# --------------------------------------------------------------------------

def _vivo(pid) -> bool:
    """Il processo del lancio c'è ancora? Per `piattaforma.pid_vivo`: su Windows
    mandare un segnale non controlla, uccide. Un processo di un altro utente non
    è il nostro lancio (il pid è stato riusato): non conta come vivo."""
    if not pid:
        return False
    return piattaforma.pid_vivo(pid, non_nostro=False)


def riconcilia(conn) -> int:
    """I lanci rimasti appesi quando il server si è fermato.

    Il lavoro gira in un thread del server: se il server riparte, il thread non
    c'è più ma la riga resta "in corso" per sempre, e da lì in poi la lavagna e
    le proposte parlano di un lavoro che non sta lavorando.
    """
    fermi = 0
    for r in conn.execute(
            "SELECT id, pid, inizio FROM runs WHERE stato IN ('in coda','in corso')").fetchall():
        if _vivo(r["pid"]):
            continue
        conn.execute("UPDATE runs SET stato='interrotto', fine=?, "
                     "esito=COALESCE(NULLIF(esito,''), ?) WHERE id=?",
                     (store.now(), "il lavoro si è fermato quando si è fermato Plancia", r["id"]))
        fermi += 1
    if fermi:
        conn.commit()
    return fermi


def elenco(conn, limite=20) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT r.*, t.title AS task FROM runs r LEFT JOIN tasks t ON t.id=r.task_id "
        "ORDER BY r.id DESC LIMIT ?", (limite,)).fetchall()]


def dettaglio(conn, run_id) -> dict:
    r = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["coda"] = Path(d["log"]).read_text("utf-8", errors="replace")[-4000:]
    except Exception:
        d["coda"] = ""
    return d


def in_corso(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM runs WHERE stato IN "
                        "('in coda','in corso')").fetchone()[0]


def annulla(conn, run_id) -> bool:
    r = conn.execute("SELECT pid, stato FROM runs WHERE id=?", (run_id,)).fetchone()
    if not r or r["stato"] not in ("in coda", "in corso"):
        return False
    # Un lancio senza pid è uno che non è mai partito davvero, o il cui thread è
    # morto con il server. Va chiuso lo stesso: prima diceva di averlo annullato
    # e lo lasciava in coda per sempre.
    if r["pid"]:
        try:
            os.kill(r["pid"], 15)
        except Exception:
            pass
    conn.execute("UPDATE runs SET stato='annullato', fine=? WHERE id=?",
                 (store.now(), run_id))
    conn.commit()
    return True
