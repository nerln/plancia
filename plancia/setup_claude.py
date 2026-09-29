"""Aggancio a Claude Code: server MCP registrato e hook di sessione.

Ogni scrittura in ~/.claude tiene una copia di sicurezza accanto all'originale,
e si può disfare con `plancia uninstall`.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import config, piattaforma

BIN = config.ROOT / "bin"
# I percorsi degli script, nudi. Quello che si scrive davvero in settings.json,
# in ~/.claude.json e nel config.toml di Codex passa da `piattaforma`: su macOS
# e Linux e' proprio questo percorso (lo shebang basta), su Windows diventa
# `"<python>" "<script>"` perche' uno script senza estensione non si esegue.
HOOK_CMD = str(BIN / "plancia-hook")
MCP_CMD = str(BIN / "plancia-mcp")
RICHIAMO_CMD = str(BIN / "plancia-richiamo")
HOOK_EVENTS = ["SessionStart", "SessionEnd"]
RICHIAMO_EVENTS = ["UserPromptSubmit"]

# Gli agganci a Claude Code: eventi, comando, come riconoscerlo in settings.json,
# quanto aspettarlo. Il richiamo ha un timeout corto perché gira a ogni
# messaggio: se un giorno diventa lento, deve arrendersi lui, non far aspettare
# lui.
AGGANCI = [
    (HOOK_EVENTS, HOOK_CMD, "plancia-hook", 5),
    (RICHIAMO_EVENTS, RICHIAMO_CMD, "plancia-richiamo", 3),
]
SKILL_DIR = config.CLAUDE_DIR / "skills" / "plancia"


def backup(path: Path) -> Path:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_suffix(path.suffix + f".plancia-backup-{stamp}")
    shutil.copy2(path, dest)
    return dest


# --------------------------------------------------------------------------
# hook
# --------------------------------------------------------------------------

def _hook_entry(comando: str, timeout: int = 5) -> dict:
    return {"hooks": [{"type": "command", "command": comando, "timeout": timeout}]}


def _e_nostro(comando, basename: str) -> bool:
    """Il comando di un hook e' uno dei nostri? Si guarda come finisce; su
    Windows il comando e' `"<python>" "<script>"` e finisce con una virgoletta,
    e su macOS e Linux, con un percorso che ha spazi, con un apice (`shlex.quote`):
    qui si tolgono (un percorso senza spazi non le ha e non cambia niente)."""
    return (comando or "").rstrip().rstrip('"\'').endswith(basename)


def _senza(entries: list, basename: str) -> list:
    return [e for e in entries
            if not any(_e_nostro(h.get("command"), basename)
                       for h in (e.get("hooks") or []))]


def install_hooks() -> str:
    path = config.CLAUDE_SETTINGS
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception as exc:
            return f"settings.json illeggibile ({exc}): hook non installati"
        backup(path)
    # Su una macchina dove Claude Code non ha ancora scritto niente la cartella
    # non c'è: senza questo, l'installazione moriva con un errore di file non
    # trovato proprio a chi la faceva per la prima volta.
    path.parent.mkdir(parents=True, exist_ok=True)
    hooks = data.setdefault("hooks", {})
    for eventi, comando, basename, timeout in AGGANCI:
        for event in eventi:
            entries = _senza(hooks.setdefault(event, []), basename)
            entries.append(_hook_entry(piattaforma.riga_script(comando), timeout))
            hooks[event] = entries
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    return f"hook installati in {path}"


def remove_hooks() -> str:
    path = config.CLAUDE_SETTINGS
    if not path.exists():
        return "nessun settings.json"
    try:
        data = json.loads(path.read_text("utf-8"))
    except Exception:
        return "settings.json illeggibile"
    backup(path)
    hooks = data.get("hooks", {})
    for eventi, _comando, basename, _timeout in AGGANCI:
        for event in eventi:
            if event in hooks:
                hooks[event] = _senza(hooks[event], basename)
                if not hooks[event]:
                    del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    return "hook rimossi"


def _agganciato(basename: str, eventi) -> bool:
    try:
        data = json.loads(config.CLAUDE_SETTINGS.read_text("utf-8"))
    except Exception:
        return False
    for event in eventi:
        for entry in data.get("hooks", {}).get(event, []):
            for hook in entry.get("hooks", []):
                if _e_nostro(hook.get("command"), basename):
                    return True
    return False


def hooks_installed() -> bool:
    return _agganciato("plancia-hook", HOOK_EVENTS)


def richiamo_installed() -> bool:
    return _agganciato("plancia-richiamo", RICHIAMO_EVENTS)


# --------------------------------------------------------------------------
# MCP
# --------------------------------------------------------------------------

def install_mcp() -> str:
    claude = piattaforma.cerca("claude")
    avvio = piattaforma.argv_script(MCP_CMD)
    if claude:
        piattaforma.esegui([claude, "mcp", "remove", "plancia", "--scope", "user"],
                           capture_output=True, text=True, **piattaforma.opzioni_utf8())
        res = piattaforma.esegui(
            [claude, "mcp", "add", "plancia", "--scope", "user", "--"] + avvio,
            capture_output=True, text=True, **piattaforma.opzioni_utf8())
        if res.returncode == 0:
            return "server MCP registrato con `claude mcp add` (scope utente)"
    # ripiego: scrittura diretta in ~/.claude.json
    path = config.CLAUDE_JSON
    if not path.exists():
        return ("server MCP non registrato: Claude Code non ha ancora scritto "
                "~/.claude.json. Aprilo una volta e poi rilancia `plancia install`")
    backup(path)
    data = json.loads(path.read_text("utf-8"))
    servers = data.setdefault("mcpServers", {})
    if isinstance(servers, list):
        servers = data["mcpServers"] = {}
    servers["plancia"] = {"type": "stdio", "command": avvio[0], "args": avvio[1:], "env": {}}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    return "server MCP registrato in ~/.claude.json"


def remove_mcp() -> str:
    claude = piattaforma.cerca("claude")
    if claude:
        piattaforma.esegui([claude, "mcp", "remove", "plancia", "--scope", "user"],
                           capture_output=True, text=True, **piattaforma.opzioni_utf8())
    path = config.CLAUDE_JSON
    if path.exists():
        try:
            data = json.loads(path.read_text("utf-8"))
            if isinstance(data.get("mcpServers"), dict) and "plancia" in data["mcpServers"]:
                backup(path)
                del data["mcpServers"]["plancia"]
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        except Exception:
            pass
    return "server MCP rimosso"


def mcp_installed() -> bool:
    try:
        data = json.loads(config.CLAUDE_JSON.read_text("utf-8"))
    except Exception:
        return False
    servers = data.get("mcpServers")
    return isinstance(servers, dict) and "plancia" in servers


# --------------------------------------------------------------------------
# skill e comando
# --------------------------------------------------------------------------

SKILL_IT = """---
name: plancia
description: >-
  Consulta e aggiorna Plancia, il centro di controllo del lavoro dell'utente con
  l'IA: progetti, task, post sociali, sessioni passate, memoria. Usala quando
  chiede "a che punto sono", "cosa avevo lasciato", "cosa devo fare oggi",
  "dove l'avevamo fatto", quando apre uno dei propri progetti, quando un lavoro
  finisce e va registrato, e prima di scrivere post sociali. Anche per "aggiorna
  plancia", "segna questo", "apri la dashboard".
---

# Plancia

Plancia è l'archivio unico del lavoro dell'utente con l'IA. Sta in `~/dev/plancia`,
i dati in `~/.plancia/plancia.db`, la dashboard su http://127.0.0.1:7773.
Il server MCP espone sei tool diretti (`plancia_search`, `plancia_task_add`,
`plancia_task_update`, `plancia_log`, `plancia_project_update`,
`plancia_post_add`) e un settimo, `plancia`, dietro cui sta tutto il resto:
si chiama con `azione="<nome>"` (`azione="aiuto"` per gli argomenti di
un'azione che non conosci). Se non vedi nessuno di questi tool, il server non
è collegato e lo si registra con `plancia install`.

## All'inizio

Se la conversazione riguarda un progetto dell'utente, chiama `plancia` con
`azione="briefing"` prima di rispondere. Restituisce progetti attivi, task
aperti, post in coda e ultima attività. Costa poco ed evita di chiedere
all'utente cose che sono già scritte.

Se dice "ne avevamo già parlato" o cerchi un lavoro passato, usa `plancia_search`:
indicizza le sessioni di Claude Code, la memoria, i task, i post e i commit.
`plancia` con `azione="sessions"` dà l'elenco con il comando per riprendere la
conversazione.

## Durante

- Lavoro individuato ma non fatto: `plancia_task_add`, che ricorda anche da
  dove è nato. Un task registrato sopravvive alla fine della conversazione,
  una promessa in chat no.
- Decisione presa, strada abbandonata, traguardo raggiunto: `plancia_log`.
- Cambio di stato di un progetto o prossimo passo chiaro:
  `plancia_project_update` con `next_action`. È la prima cosa che leggerà la
  sessione dopo questa.

## Alla fine

Prima di chiudere un lavoro sostanziale: aggiorna `next_action` del progetto e
chiudi i task fatti con `plancia_task_update`. Non serve chiedere il permesso per
scrivere in Plancia: è l'archivio dell'utente, non un'azione verso l'esterno.

## La lavagna

`plancia` con `azione="lavagna"` è la lista unica di quello che è aperto
adesso, di tutti e tre: le liste di task di Claude Code, gli obiettivi di
Codex, i task di Plancia. Usala quando chiede "cosa c'è aperto", "su cosa
siamo fermi", "cosa sta facendo Codex". Gli stati sono riportati agli stessi
cinque: aperto, in corso, bloccato, fatto, sparito.

`azione="lanci"` dice com'è andato un lavoro già partito: esito, token, costo.
`azione="eventi"` legge il registro in append, utile a chi deve reagire a un
lavoro finito.

## Riprendere un task

Ogni task creato con `plancia_task_add` ricorda da dove è nato: la sessione,
la cartella, l'agente e la macchina. Chiudere il terminale non lo perde.

Se ti chiede "riprendi il task N", chiama `plancia` con `azione="riprendi"` e
`id` (il task N): risponde con lo stato, la sessione, la cartella e il comando
per riaprirla. Poi, secondo lo stato:

- **viva**: la sessione è ancora aperta da qualche parte. Consegna il
  messaggio "riprendi il task N di Plancia: <titolo>" alla sessione indicata
  con lo strumento `send_message` dell'app desktop, se lo vedi tra i tuoi
  tool; se non c'è, indica all'utente la cartella e la sessione, con lo
  stesso messaggio da incollare, "riprendi il task N di Plancia: <titolo>", e
  lascia che sia l'utente a riaprirla.
- **chiusa**: di' all'utente il comando da aprire nel Terminale; richiama
  `plancia` con `azione="riprendi", apri=true` solo se l'utente te lo chiede,
  perché apre un Terminale sul Mac dell'utente, un'azione verso l'esterno.
- **persa**: spiega il motivo (cartella sparita, macchina diversa, sessione
  troppo vecchia) e proponi di ripartire da capo invece di inseguirla.

Riprendere vuol dire tornare nella conversazione di prima, non farne partire
una nuova che scrive da sola: qui non si lancia niente in autonomia.
In background resta un'opzione secondaria che sceglie l'utente dalla dashboard,
non un'azione che decidi tu.

## Le proposte

Il riepilogo finisce con le cose che converrebbe fare, calcolate dai segnali nei
dati e mai inventate. Se ti chiede "cosa dovrei fare adesso", `plancia` con
`azione="recap"` le contiene già: non aggiungerne di tue sopra quelle, semmai
spiega perché una è la prima.

## Social

`plancia_post_add` salva una bozza, non pubblica niente. Il campo `source_ref`
deve puntare al lavoro reale che sta dietro al post: sha di un commit, nome di un
repo, id di una sessione. La regola dell'account è che ogni post nasce da qualcosa
che è successo davvero.

**Ogni post nasce con un'immagine propria.** Il campo `media` è il percorso del file
che esce insieme al testo, e si riempie quando si scrive la bozza, non al momento
di pubblicare: dopo non c'è più sotto mano il lavoro da cui è uscita. Un post
senza immagine è l'eccezione e va motivata.

Quando chiudi un lavoro che vale un post, l'immagine di solito ce l'hai già:
uno screenshot già dentro il repo (`docs/img/...`), la dashboard di Plancia,
il sito appena pubblicato. Se serve farne uno nuovo, fallo prima di salvare la
bozza. Due regole imparate pubblicando: sotto i 400 KB, e guardalo prima di
allegarlo, perché uno screenshot porta fuori tutto quello che era sullo schermo.

La scrittura resta della skill `social-media-manager`, la pubblicazione della
skill `x-account`, che chiede approvazione esplicita e sa allegare l'immagine
dagli appunti di sistema. Plancia tiene il conto: `plancia` con
`azione="posts"` per lo stato della pipeline, `azione="post_update"` con
l'url quando un post è davvero online.

## Voce

`plancia` con `azione="recap"` restituisce il riepilogo della giornata scritto
per essere ascoltato. Con `speak=true` lo legge ad alta voce sul Mac dell'utente.
`azione="speak"` legge un testo qualsiasi: usalo solo se lo chiede, e scrivi
per l'orecchio, non per l'occhio.

Le lingue sono it, en, es, fr, de, pt. Se non la specifica, vale quella in
`~/.plancia/config.json`.

## Jarvis

`plancia://jarvis` apre il pannello vocale a mani libere, oppure ⌥Spazio da
qualsiasi app. Ascolta di continuo, capisce dal silenzio quando ha finito di
parlare, esegue e risponde a voce. I comandi che riconosce da solo (aprire una
vista, segnare un task, chiuderlo, rileggere le fonti, il riepilogo) partono
subito; tutto il resto arriva a Claude Code con i tool `plancia_*` aperti, quindi
può agire davvero.

Puoi interromperlo mentre parla: basta ricominciare a parlare, il microfono
resta aperto anche mentre risponde. "Annulla" ferma un lavoro partito, "basta"
chiude il pannello, "ripeti" ridice l'ultima cosa, "più piano" e "più veloce"
cambiano la velocità della voce. Quando un lancio finisce te lo dice a voce anche se nel
frattempo stavi facendo altro.

`plancia jarvis "frase"` fa la stessa cosa da terminale, senza microfono.

Tre strade in ordine: i comandi e le domande sui dati si risolvono in un decimo
di secondo senza chiamare nessun modello; il resto va a un processo Claude tenuto
caldo, circa tre secondi. Il riepilogo è precalcolato, quindi è immediato.

## I due agenti

Plancia legge anche le sessioni di Codex da `~/.codex/sessions` e registra il
proprio server MCP dentro `~/.codex/config.toml`: Codex e Claude vedono lo stesso
archivio e gli stessi tool. La vista Agenti mostra chi ha lavorato su cosa e
quando i due si sono passati il lavoro.

## Comandi

```bash
plancia lavagna          # tutto quello che è aperto, di tutti gli agenti
plancia lanci            # com'è andata
plancia eventi --dopo <id>
plancia recap --speak    # riepilogo letto ad alta voce
plancia jarvis "..."     # un comando vocale scritto
plancia ask "..." --speak
plancia daily on 08:45   # riepilogo automatico ogni mattina
plancia flusso           # da dove arrivano i dati e quanto sono freschi
plancia sync --modo caldo   # solo sessioni e hook, un centesimo di secondo
plancia serve --open     # dashboard
plancia sync             # rilegge sessioni, memoria, repo
plancia briefing         # il briefing su stdout
plancia doctor           # controlla i collegamenti
```
"""


SKILL_EN = """---
name: plancia
description: >-
  Reads and updates Plancia, the control centre for the user's work with AI:
  projects, tasks, social posts, past sessions, memory. Use it when the user
  asks "where was I", "what did I leave off", "what should I do today", "where
  did we do this", when they open one of their projects, when a piece of work
  is finished and needs recording, and before writing social posts. Also for
  "update plancia", "mark this", "open the dashboard".
---

# Plancia

Plancia is the single archive of the user's work with AI. It lives in `~/dev/plancia`,
the data in `~/.plancia/plancia.db`, the dashboard at http://127.0.0.1:7773.
The MCP server exposes six direct tools (`plancia_search`, `plancia_task_add`,
`plancia_task_update`, `plancia_log`, `plancia_project_update`,
`plancia_post_add`) and a seventh, `plancia`, standing in front of everything
else: call it with `azione="<name>"` (`azione="aiuto"` for an action's
arguments). If you do not see any of these tools, the server is not
connected, and you register it with `plancia install`.

## At the start

If the conversation is about one of the user's projects, call `plancia` with
`azione="briefing"` before answering. It returns active projects, open
tasks, queued posts and the latest activity. It costs little and saves
asking the user things that are already written down.

If the user says "we already talked about this" or you are looking for past
work,
use `plancia_search`: it indexes Claude Code sessions, memory, tasks, posts
and commits. `plancia` with `azione="sessions"` gives the list with the
command to resume the conversation.

## During the work

- Work identified but not done: `plancia_task_add`, which also remembers
  where it came from. A recorded task survives the end of the conversation;
  a promise in chat does not.
- A decision made, a path abandoned, a milestone reached: `plancia_log`.
- A project's status changes, or the next step becomes clear:
  `plancia_project_update` with `next_action`. It is the first thing the next
  session will read.

## At the end

Before closing a substantial piece of work: update the project's
`next_action` and close finished tasks with `plancia_task_update`. You do not
need to ask permission to write to Plancia: it is the user's own archive, not
an action toward the outside world.

## The board

`plancia` with `azione="lavagna"` is the single list of everything open right
now, across all three: Claude Code's task lists, Codex's objectives,
Plancia's own tasks. Use it when the user asks "what's open", "what are we
stuck on", "what is Codex doing". States are reported with the same five words:
open, in progress, blocked, done, gone.

`azione="lanci"` says how a run that already started went: outcome, tokens,
cost. `azione="eventi"` reads the append-only log, useful for reacting to a
piece of work that just finished.

## Resuming a task

Every task created with `plancia_task_add` remembers where it came from: the
session, the folder, the agent and the machine. Closing the terminal does not
lose it.

If the user asks "resume task N", call `plancia` with `azione="riprendi"` and `id`
(task N): it answers with the status, the session, the folder and the command
to reopen it. Then, depending on the status:

- **viva** (alive): the session is still open somewhere. Deliver the message
  "riprendi il task N di Plancia: <titolo>" to the indicated session with the
  desktop app's `send_message` tool, if you see it among your tools; if it is
  not there, tell the user the folder and the session and give them the same
  message, "riprendi il task N di Plancia: <titolo>", to paste, and let them
  reopen it.
- **chiusa** (closed): tell the user the command to open in the Terminal; call
  `plancia` again with `azione="riprendi", apri=true` only if the user asks you
  to, because it opens a Terminal on the user's Mac, an action toward the
  outside world.
- **persa** (lost): explain why (folder gone, different machine, session too
  old) and propose starting over instead of chasing it.

Resuming means going back to the earlier conversation, not starting a new one
that writes on its own: nothing gets launched autonomously here. Running it
in background stays a secondary option the user picks from the dashboard, not a
choice you make on your own.

## The proposals

The daily recap ends with the thing that would be worth doing, computed from
signals in the data and never invented. If the user asks "what should I do now",
`plancia` with `azione="recap"` already has it: do not add one of your own on
top, at most explain why one comes first.

## Social

`plancia_post_add` saves a draft, it publishes nothing. The `source_ref`
field must point at the real work behind the post: a commit sha, a repo name,
a session id. The account's rule is that every post comes from something that
really happened.

**Every post is born with its own image.** The `media` field is the path of
the file that goes out with the text, and it is filled in when the draft is
written, not at publish time: by then the work it came from is no longer at
hand. A post with no image is the exception, and it needs a reason.

When you close a piece of work worth a post, you usually already have the
image: a screenshot already in the repo (`docs/img/...`), the Plancia
dashboard, the site that was just published. If a new one is needed, make it
before saving the draft. Two rules learned by publishing: under 400 KB, and
look at it before attaching it, because a screenshot carries out everything
that was on the screen.

Writing stays the job of the `social-media-manager` skill, publishing the job
of the `x-account` skill, which asks for explicit approval and knows how to
attach the image from the system clipboard. Plancia keeps the count:
`plancia` with `azione="posts"` for the pipeline's status,
`azione="post_update"` with the url once a post is really live.

## Voice

`plancia` with `azione="recap"` returns the day's recap written to be
listened to. With `speak=true` it reads it aloud on the user's Mac.
`azione="speak"` reads any text: use it only if the user asks, and write for
the ear, not the eye.

The languages are it, en, es, fr, de, pt. If the user does not specify one, the
one in `~/.plancia/config.json` applies.

## Jarvis

`plancia://jarvis` opens the hands-free voice panel, or ⌥Space from any app.
It listens continuously, tells from the silence when the user has finished
speaking, acts and answers by voice. The commands it recognizes on its own
(opening a view, marking a task, closing it, rereading the sources, the
recap) run right away; everything else reaches Claude Code with the
`plancia_*` tools open, so it can really act.

You can interrupt it while it speaks: just start talking again, the
microphone stays open even while it answers. "Cancel" stops a run that
started, "stop" closes the panel, "repeat" says the last thing again, "slower"
and "faster" change the voice's speed. When a run finishes it tells the user
by voice even if they were doing something else in the meantime.

`plancia jarvis "sentence"` does the same thing from the terminal, without a
microphone.

Three paths, in order: commands and questions about the data are resolved in
a tenth of a second without calling any model; everything else goes to a
Claude process kept warm, about three seconds. The recap is precomputed, so
it is immediate.

## The two agents

Plancia also reads Codex's sessions from `~/.codex/sessions` and registers
its own MCP server inside `~/.codex/config.toml`: Codex and Claude see the
same archive and the same tools. The Agents view shows who worked on what and
when the two handed work to each other.

## Commands

```bash
plancia lavagna          # everything open, across all agents
plancia lanci            # how it went
plancia eventi --dopo <id>
plancia recap --speak    # recap read aloud
plancia jarvis "..."     # a voice command written out
plancia ask "..." --speak
plancia daily on 08:45   # automatic recap every morning
plancia flusso           # where the data comes from and how fresh it is
plancia sync --modo caldo   # sessions and hooks only, a hundredth of a second
plancia serve --open     # dashboard
plancia sync             # rereads sessions, memory, repos
plancia briefing         # the briefing on stdout
plancia doctor           # checks the connections
```
"""


RIEPILOGO_SKILL_IT = """---
name: riepilogo
description: >-
  Racconta all'utente com'è andata la giornata di lavoro con l'IA, con i dati
  veri di Plancia, e se l'utente vuole la legge ad alta voce nella lingua che
  usa.
  Usala per "com'è andata oggi", "riepilogo", "cosa ho fatto", "leggimi il
  riepilogo", "briefing", "recap", "resumen", "what did I get done".
---

# Riepilogo della giornata

Il riepilogo non si inventa e non si ricostruisce a mano: lo produce Plancia dai
dati reali, con `plancia` e `azione="recap"`.

## Come farlo

1. Chiama `plancia` con `azione="recap"`. Senza altri argomenti è la giornata
   di oggi nella lingua dell'utente. `day` accetta AAAA-MM-GG per un giorno passato,
   `lang` cambia lingua.
2. Riporta il testo com'è. È già scritto per essere ascoltato: frasi corte,
   niente elenchi, niente markdown. Non riformattarlo in punti elenco.
3. Se chiede di sentirlo ("leggimelo", "dimmelo", "a voce"), richiama
   `plancia` con `azione="recap", speak=true`, oppure `azione="speak"` se
   vuoi leggere una risposta tua.

Dentro `dati` c'è tutto il dettaglio: sessioni, commit, task chiusi e aperti,
post, progetti fermi. Usalo per rispondere alle domande che fa dopo, senza
rigenerare il riepilogo.

## Il riepilogo finisce con una proposta

Dopo i fatti arriva la cosa che converrebbe fare, e non è un consiglio generico:
nasce da un segnale nei dati. Un lancio fallito, un obiettivo di Codex senza
quota, file non committati da ieri, un post approvato e mai uscito, il prossimo
passo di un progetto fermo.

Se l'utente risponde "fallo", "la seconda", "eseguilo" su una proposta che
riprende un task Plancia, chiama `plancia` con `azione="riprendi"` e l'`id` di
quel task (vedi la skill `plancia`, sezione "Riprendere un task": i tre stati
viva/chiusa/persa), oppure dì all'utente a voce che non sai quale id è. **Non
lanciare niente in autonomia**: il modo predefinito guarda e riferisce, e "In
background" resta al più un'opzione secondaria che sceglie l'utente, non tu.

Se il segnale non c'è, la proposta non c'è, ed è voluto. Non aggiungerne una tua
per riempire il finale.

## Cosa non fare

Non aggiungere risultati che non sono nei dati. Se la giornata è stata vuota, il
riepilogo lo dice in una riga e va bene così: riempirlo di frasi di incoraggiamento
lo rende inutile la volta dopo.

Non leggere ad alta voce senza che lo abbia chiesto. L'audio esce dalle casse
del Mac dell'utente e nella stanza potrebbero esserci altre persone.

Non riscrivere il testo per la voce: ci pensa Plancia, che toglie indirizzi,
percorsi e sha prima di dirlo, perché letti ad alta voce sono una filastrocca.

## Ogni mattina

`plancia daily on 08:45` mette un agente launchd che lo prepara e manda la
notifica. Con `--voce` lo legge anche. `plancia daily off` lo toglie.
L'app Plancia ha la stessa cosa nel menu della barra, e `plancia://recap`
lo lancia da una scorciatoia di sistema.
"""


RIEPILOGO_SKILL_EN = """---
name: riepilogo
description: >-
  Tells the user how their day of work with AI went, from Plancia's real data,
  and reads it aloud in their language if they ask. Use it for "how did today
  go", "recap", "what did I get done", "read me the recap", "briefing",
  "resumen", "riepilogo".
---

# The day's recap

The recap is never invented or pieced together by hand: Plancia produces it
from real data, with `plancia` and `azione="recap"`.

## How to do it

1. Call `plancia` with `azione="recap"`. With no other arguments it is
   today, in the user's language. `day` takes YYYY-MM-DD for a past day, `lang`
   changes the language.
2. Report the text as it is. It is already written to be heard: short
   sentences, no lists, no markdown. Do not reformat it into bullet points.
3. If the user asks to hear it ("read it to me", "say it", "out loud"), call
   `plancia` again with `azione="recap", speak=true`, or `azione="speak"`
   if you want to read back an answer of your own.

Inside `dati` is the whole detail: sessions, commits, tasks closed and open,
posts, stalled projects. Use it to answer whatever the user asks next, without
regenerating the recap.

## The recap ends with a proposal

After the facts comes the thing that would be worth doing, and it is never
generic advice: it comes from a signal in the data. A failed run, a Codex
goal out of quota, files uncommitted since yesterday, an approved post that
never went out, the next step of a stalled project.

If the user answers "do it", "the second one", "run it" on a proposal that
resumes a Plancia task, call `plancia` with `azione="riprendi"` and that task's
`id` (see the `plancia` skill, section "Resuming a task": the three states
alive/closed/lost), or tell the user out loud if you do not know which id it
is. **Never launch anything on your own**: the default mode reads and reports,
and "In background" stays at most a secondary option the user picks, not you.

If there is no signal, there is no proposal, and that is on purpose. Do not
add one of your own to fill the ending.

## What not to do

Do not add results that are not in the data. If the day was empty, the
recap says so in one line and that is fine: filling it with encouraging
phrases makes it useless the next time.

Do not read it aloud without being asked. The audio comes out of the user's
Mac speakers, and the user might not be alone.

Do not rewrite the text for speech: Plancia already does that, stripping
addresses, paths and shas before saying it, because read aloud they sound
like nonsense.

## Every morning

`plancia daily on 08:45` sets up a launchd agent that prepares it and sends
the notification. With `--voce` it reads it too. `plancia daily off` removes
it. The Plancia app has the same thing in its menu bar, and
`plancia://recap` launches it from a system shortcut.
"""


# Come skill_text() per la skill "plancia": stessa scelta di lingua (solo
# l'inglese ha un testo scritto a mano, il resto ripiega sull'italiano),
# cosi' le due skill si comportano allo stesso modo invece che una tradotta e
# l'altra no.
def riepilogo_skill_text(lang: str = "it") -> str:
    return RIEPILOGO_SKILL_EN if lang == "en" else RIEPILOGO_SKILL_IT


# Alias per compatibilita' con chi si aspettava un solo testo (sempre
# italiano, come prima di questo lotto).
RIEPILOGO_SKILL = RIEPILOGO_SKILL_IT


# La skill "plancia" esiste in due lingue scritte a mano (SKILL_IT, SKILL_EN):
# a differenza delle stringhe della dashboard, che passano da T() a runtime,
# questo testo lo legge un agente diverso a ogni sessione, prima ancora che
# Plancia sia connessa, quindi non può scegliere la lingua da un dizionario in
# memoria. skill_text() sceglie in base alla lingua richiesta (o alla
# `lingua` salvata in ~/.plancia/config.json, la stessa chiave che legge tutto
# il resto del programma: recap.py, api.py, voice.py, l'app Mac) e ripiega
# sull'italiano per qualunque lingua diversa da "en", invece di rompere
# l'installazione.
def skill_text(lang: str = "it") -> str:
    testo = SKILL_EN if lang == "en" else SKILL_IT
    # Il testo scritto a mano dice dove sta Plancia sulla macchina di chi l'ha
    # scritto; chi clona altrove (un altro utente, un PC Windows) deve leggere
    # il proprio percorso, non quello.
    return testo.replace("`~/dev/plancia`", f"`{cartella_installata()}`")


def cartella_installata() -> str:
    """La cartella di questo checkout come la scriverebbe una persona: con `~`
    se sta sotto la casa, sempre con le barre in avanti."""
    radice = Path(config.ROOT).resolve()
    try:
        return "~/" + radice.relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return radice.as_posix()


def install_skill(lang: str = None) -> str:
    if lang is None:
        cfg = config.load_config()
        # Stessa normalizzazione di recap.py:24. `locale` è un default morto in
        # config.DEFAULTS che nessun altro punto del programma scrive né legge:
        # resta come ripiego per chi lo avesse scritto a mano, non come chiave
        # primaria.
        lang = (cfg.get("lingua") or cfg.get("locale") or "it").lower()[:2]
    # skill_text() e riepilogo_skill_text() ripiegano entrambe sull'italiano
    # per qualunque lingua diversa da "en": il messaggio deve dire quella
    # scritta davvero, non `lang` cosi' com'e' arrivato, altrimenti un
    # `lang="fr"` stamperebbe "(fr)" per un file che e' in realta' italiano.
    scritta = "en" if lang == "en" else "it"
    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    (SKILL_DIR / "SKILL.md").write_text(skill_text(lang), "utf-8")
    altra = config.CLAUDE_DIR / "skills" / "riepilogo"
    altra.mkdir(parents=True, exist_ok=True)
    (altra / "SKILL.md").write_text(riepilogo_skill_text(lang), "utf-8")
    return f"skill plancia ({scritta}) e riepilogo ({scritta}) scritte in {SKILL_DIR.parent}"


def _scrivi(percorso: Path, testo: str) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    if percorso.suffix.lower() == ".cmd":
        # Un file batch porta gia' i suoi "\r\n" e cmd.exe lo legge nella tabella
        # di caratteri della console (non in utf-8): niente write_text, che su
        # Windows raddoppierebbe il ritorno a capo.
        codifica = "oem" if os.name == "nt" else "utf-8"
        percorso.write_bytes(testo.encode(codifica, errors="replace"))
    else:
        percorso.write_text(testo, "utf-8")


def _lancia(argv):
    """Lancia `argv` (sempre da `piattaforma.esegui`, che le prove sostituiscono).
    Un programma che non c'e' o che si pianta vale come un comando fallito, non
    come un'eccezione: chi chiama decide cosa dire."""
    try:
        return piattaforma.esegui(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


def _toccabile():
    """`(si', perche)`: Plancia puo' caricare servizi e attivita' pianificate del
    sistema? No da una HOME di prova (vedi `piattaforma.sistema_toccabile`)."""
    return piattaforma.sistema_toccabile()


def _dentro_casa(percorso: Path) -> bool:
    """Il file sta sotto la HOME del processo? Una HOME di prova non deve far
    scrivere nemmeno nella cartella Esecuzione automatica o in ~/.config di chi
    non e' lei (APPDATA e XDG_CONFIG_HOME si leggono dall'ambiente)."""
    try:
        casa = Path.home().resolve()
        return casa == Path(percorso).resolve() or casa in Path(percorso).resolve().parents
    except OSError:
        return False


def _scrivi_senza_caricare(piano: dict) -> None:
    """Da una HOME di prova: i file del piano (il plist, l'unita' systemd, il
    `.cmd` di Esecuzione automatica) si scrivono, i comandi non partono."""
    file = piano["file"] or (piano.get("ripiego") or {}).get("file", [])
    for percorso, testo in file:
        if _dentro_casa(percorso):
            _scrivi(percorso, testo)


def _togli_senza_scaricare(piano: dict) -> None:
    for percorso in piano["rimuovi"]:
        if _dentro_casa(percorso) and percorso.exists():
            percorso.unlink()


def _attiva(piano: dict):
    """Scrive i file del piano e lancia i comandi di attivazione. Se l'ultimo
    fallisce e il piano ha un ripiego, toglie quello che aveva scritto e prova il
    ripiego. Se invece funziona, toglie i file che il ripiego avrebbe potuto
    lasciare da un giro precedente. Torna (piano usato, esito dell'ultimo
    comando o None)."""
    for percorso, testo in piano["file"]:
        _scrivi(percorso, testo)
    esito = None
    for argv in piano["attiva"]:
        esito = _lancia(argv)
    if esito is not None and esito.returncode != 0 and piano.get("ripiego"):
        for percorso, _testo in piano["file"]:
            percorso.unlink(missing_ok=True)
        return _attiva(piano["ripiego"])
    if piano.get("ripiego"):
        # Il meccanismo principale ha funzionato: quello di ripiego, lasciato da
        # un giro precedente (il `.cmd` in Esecuzione automatica, il `.desktop`),
        # partirebbe insieme e all'accesso ci sarebbero due server, con il secondo
        # che cade sulla porta occupata.
        for percorso in piano["ripiego"]["rimuovi"]:
            percorso.unlink(missing_ok=True)
    return piano, esito


def _disattiva(piano: dict) -> None:
    """Spegne quello che `_attiva` ha acceso: i comandi, poi i file."""
    for argv in piano["disattiva"]:
        _lancia(argv)
    for percorso in piano["rimuovi"]:
        if percorso.exists():
            percorso.unlink()
    for argv in piano.get("dopo", []):
        _lancia(argv)


def _installato(piano) -> bool:
    if not piano:
        return False
    if any(p.exists() for p in piano["presente"]):
        return True
    if piano["query"]:
        return _lancia(piano["query"]).returncode == 0
    return False


def _uid():
    return os.getuid() if hasattr(os, "getuid") else None


def _errore_di(esito) -> str:
    return ((esito.stderr or esito.stdout or "") if esito is not None else "").strip()[:120]


def install_command() -> str:
    piatt = piattaforma.nome()
    link = piattaforma.percorso_comando(Path.home(), piatt)
    target = link.parent
    target.mkdir(parents=True, exist_ok=True)
    src = BIN / "plancia"
    if piatt == piattaforma.WINDOWS:
        _scrivi(link, piattaforma.shim_windows(sys.executable, src))
    else:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(src)
    on_path = piattaforma.nel_path(target, os.environ.get("PATH", ""), piatt)
    return (f"comando `plancia` in {link}" if on_path
            else f"comando in {link}, aggiungi {target} al PATH")


# --------------------------------------------------------------------------
# avvio automatico
# --------------------------------------------------------------------------

# Le ricette (launchd su macOS, Task Scheduler su Windows, systemd su Linux) sono
# in plancia/piattaforma.py come piani da leggere; qui si applicano. I nomi
# sotto restano per chi li importava.
AGENT_LABEL = piattaforma.LABEL_SERVER
PLIST = piattaforma.PLIST_SERVER


def _piano_server() -> dict:
    # L'interprete va fissato: launchd non ha il PATH della shell e "python3"
    # gli risolve nel 3.9 di Xcode invece che in quello con cui gira il resto.
    return piattaforma.piano_server(sys.executable, BIN / "plancia", config.LOG_FILE,
                                    Path.home(), uid=_uid())


def autostart_on() -> str:
    ok, perche = _toccabile()
    if not ok:
        _scrivi_senza_caricare(_piano_server())
        return f"avvio automatico: file scritti, non caricati ({perche})"
    piano, esito = _attiva(_piano_server())
    if esito is not None and esito.returncode != 0:
        if piattaforma.nome() == piattaforma.MAC:
            return (f"plist scritto in {piano['file'][0][0]}, ma launchctl ha "
                    f"risposto: {_errore_di(esito)}")
        return f"avvio automatico non attivato ({piano['nome']}): {_errore_di(esito)}"
    if piattaforma.nome() == piattaforma.MAC:
        return "avvio automatico attivo: la dashboard riparte a ogni accesso"
    return (f"avvio automatico attivo con {piano['nome']}: "
            "la dashboard riparte a ogni accesso")


def autostart_off() -> str:
    ok, perche = _toccabile()
    if not ok:
        _togli_senza_scaricare(_piano_server())
        return f"avvio automatico: file tolti, non scaricati ({perche})"
    _disattiva(_piano_server())
    return "avvio automatico disattivato"


def autostart_installed() -> bool:
    return _installato(_piano_server())


def autostart_meccanismo() -> str:
    """Il nome del meccanismo che fa ripartire il server DAVVERO ora: quello
    principale del sistema (launchd, Task Scheduler, systemd) se e' lui a esserci,
    altrimenti il ripiego che `_attiva` ha usato (la cartella Esecuzione
    automatica, `~/.config/autostart`). Senza niente installato, il nome di quello
    che si userebbe."""
    piano = _piano_server()
    candidati = []
    while piano:
        candidati.append(piano)
        piano = piano.get("ripiego")
    for c in candidati:
        # un meccanismo con file si riconosce dal suo file; uno senza (il Task
        # Scheduler) chiedendo al sistema
        if c["file"]:
            if any(p.exists() for p, _t in c["file"]):
                return c["nome"]
        elif c["query"] and _lancia(c["query"]).returncode == 0:
            return c["nome"]
    return candidati[0]["nome"]


# --------------------------------------------------------------------------
# riepilogo automatico
# --------------------------------------------------------------------------

RECAP_LABEL = piattaforma.LABEL_RIEPILOGO
RECAP_TEMPLATE = piattaforma.PLIST_RIEPILOGO


def _piano_riepilogo(ora: int = 0, minuto: int = 0):
    return piattaforma.piano_riepilogo(
        sys.executable, BIN / "plancia", ora, minuto, config.DATA_DIR / "recap.log",
        Path.home(), uid=_uid())


def recap_daily_on(ora: str = "08:45", voce: bool = False) -> str:
    try:
        h, m = [int(x) for x in ora.split(":")]
        assert 0 <= h < 24 and 0 <= m < 60
    except Exception:
        return f"ora non valida: {ora}. Serve HH:MM."
    piano = _piano_riepilogo(h, m)
    if piano is None:
        return ("riepilogo automatico non attivato: qui serve systemd --user "
                "(in alternativa metti `plancia recap --daily --notify` in cron)")
    cfg = config.load_config()
    cfg["riepilogo_ora"] = f"{h:02d}:{m:02d}"
    cfg["riepilogo_voce"] = bool(voce)
    config.save_config(cfg)

    ok, perche = _toccabile()
    if not ok:
        _scrivi_senza_caricare(piano)
        return f"riepilogo automatico: file scritti, non caricati ({perche})"
    piano, esito = _attiva(piano)
    if esito is not None and esito.returncode != 0:
        if piattaforma.nome() == piattaforma.MAC:
            return f"plist scritto, launchctl ha risposto: {_errore_di(esito)}"
        return f"riepilogo automatico non attivato ({piano['nome']}): {_errore_di(esito)}"
    return (f"riepilogo automatico alle {h:02d}:{m:02d}"
            + (" con la voce" if voce else " come notifica"))


def recap_daily_off() -> str:
    piano = _piano_riepilogo()
    ok, perche = _toccabile()
    if piano is not None:
        if ok:
            _disattiva(piano)
        else:
            _togli_senza_scaricare(piano)
    cfg = config.load_config()
    cfg.pop("riepilogo_ora", None)
    config.save_config(cfg)
    if not ok:
        return f"riepilogo automatico: file tolti, non scaricati ({perche})"
    return "riepilogo automatico disattivato"


def recap_daily_installed() -> bool:
    return _installato(_piano_riepilogo())


def install_all() -> list:
    if piattaforma.nome() != piattaforma.WINDOWS:
        # su Windows il permesso di esecuzione non esiste: si lancia con python
        for script in ("plancia", "plancia-mcp", "plancia-hook"):
            path = BIN / script
            if path.exists():
                path.chmod(0o755)
    from . import codex
    return [install_command(), install_mcp(), codex.registra_mcp(), install_hooks(),
            install_skill(), autostart_on()]


def uninstall_all() -> list:
    from . import codex
    out = [recap_daily_off(), autostart_off(), remove_hooks(), remove_mcp(),
           codex.rimuovi_mcp()]
    link = piattaforma.percorso_comando(Path.home())
    if link.is_symlink() or (piattaforma.nome() == piattaforma.WINDOWS and link.exists()):
        link.unlink()
        out.append("comando rimosso")
    for d in (SKILL_DIR, config.CLAUDE_DIR / "skills" / "riepilogo"):
        if d.exists():
            shutil.rmtree(d)
    out.append("skill rimosse")
    out.append(f"i dati restano in {config.DATA_DIR}")
    # Le copie di sicurezza restano apposta: se togliendosi di mezzo Plancia
    # avesse rotto qualcosa, sono la strada per tornare indietro. Ma vanno
    # dette, se no restano lì per sempre senza che nessuno sappia cosa sono.
    copie = sorted(config.CLAUDE_DIR.glob("settings.json.plancia-backup-*"))
    if copie:
        out.append(f"copie di sicurezza dei tuoi settings, da buttare quando vuoi: "
                   f"{len(copie)} in {config.CLAUDE_DIR}")
    return out


def _righe_contenitori() -> list:
    """I contenitori in uso: le cartelle che tengono progetti senza essere un
    progetto (una sessione aperta li' dentro riceve l'avviso, e ogni loro
    sottocartella e' un progetto per l'attribuzione). Quelli che Plancia riconosce
    da sola piu' quelli scritti in config.json, alla chiave `contenitori`: un
    disco esterno non e' piu' un contenitore se non sta li'."""
    try:
        from . import attribuzione, ingest
        casa = str(config.HOME)
        tutti = attribuzione.contenitori_avviso(config.HOME, ingest.drive_root())
        extra = attribuzione.contenitori_extra()

        def breve(p):
            return "~" + p[len(casa):] if p == casa or p.startswith(casa + os.sep) else p

        righe = [f"ok  contenitori di progetti: {len(tutti)}  "
                 f"({', '.join(breve(p) for p in tutti)})"]
        if extra:
            righe.append("    scritti in config.json: " + ", ".join(breve(p) for p in extra))
        else:
            righe.append("    nessuno scritto in config.json: un disco esterno o un'altra "
                         "cartella dei progetti si aggiunge alla chiave `contenitori`")
        return righe
    except Exception as exc:
        return [f"no  contenitori di progetti: {exc}"]


def doctor() -> list:
    from . import store
    lines = []
    ok = lambda cond: "ok  " if cond else "no  "
    lines.append(f"{ok(config.DB_PATH.exists())}database {config.DB_PATH}")
    if config.DB_PATH.exists():
        conn = store.connect()
        try:
            for table in ("projects", "sessions", "tasks", "posts", "knowledge", "events"):
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                lines.append(f"    {table}: {n}")
            lines.append(f"    ultimo sync: {store.get_meta(conn, 'last_sync_end', 'mai')}")

            # La lavagna: quante voci per fonte, e se una fonte è muta si vede
            # subito invece di scoprirlo dal fatto che manca roba.
            from . import lavagna as _lav
            per_fonte = _lav.conteggi(conn)
            pezzi = ", ".join(f"{k} {v.get('aperti', 0)}" for k, v in sorted(per_fonte.items()))
            lines.append(f"{ok(any(v.get('aperti') for v in per_fonte.values()))}"
                         f"lavagna: {pezzi or 'vuota'}")
            esiti = {"claude": {"ok": True}, "codex": {"ok": True}}
            _lav.da_claude(esiti["claude"])
            _lav.da_codex(esiti["codex"])
            for fonte, e in esiti.items():
                if not e.get("ok", True):
                    lines.append(f"no  la lavagna non riesce a leggere {fonte}")

            # Lanci appesi: se ce ne sono, la lavagna sta raccontando un lavoro
            # che non sta lavorando.
            from . import cantiere as _cant
            appesi = [r for r in conn.execute(
                "SELECT id, pid FROM runs WHERE stato IN ('in coda','in corso')")
                if not _cant._vivo(r["pid"])]
            lines.append(f"{ok(not appesi)}lanci appesi: {len(appesi)}"
                         + ("  (si chiudono al prossimo giro freddo)" if appesi else ""))

            # Memorie doppie. Nascono da sole: finché la memoria sta in una
            # cartella e basta, la stessa cosa la riscrivi da un'altra parte
            # senza sapere che c'era già. Il richiamo ferma il fenomeno da qui
            # in avanti, ma i doppioni di prima restano lì e vanno uniti a mano.
            doppi = conn.execute(
                "SELECT name, COUNT(DISTINCT scope) AS n FROM knowledge "
                "GROUP BY name HAVING n > 1 ORDER BY n DESC, name").fetchall()
            if doppi:
                elenco = ", ".join(r["name"] for r in doppi[:4])
                if len(doppi) > 4:
                    elenco += f", e altre {len(doppi) - 4}"
                lines.append(f"no  memorie in più cartelle: {len(doppi)}  ({elenco})")
                lines.append("    la skill consolidate-memory le unisce")
            else:
                lines.append("ok  nessuna memoria doppia")
        except Exception as exc:
            lines.append(f"    errore: {exc}")
        finally:
            conn.close()
    lines.append(f"{ok(mcp_installed())}server MCP registrato in ~/.claude.json")
    lines.append(f"{ok(hooks_installed())}hook SessionStart/SessionEnd")
    lines.append(f"{ok(richiamo_installed())}richiamo della memoria (UserPromptSubmit)")
    from . import codex
    cx = codex.stato()
    lines.append(f"{ok(cx['installato'])}Codex trovato ({cx['sessioni']} sessioni)")
    lines.append(f"{ok(cx['mcp'])}server MCP registrato anche in Codex")
    lines.append(f"{ok((SKILL_DIR / 'SKILL.md').exists())}skill plancia")
    lines.append(f"{ok(autostart_installed())}avvio automatico ({autostart_meccanismo()})")
    ora = config.load_config().get("riepilogo_ora")
    lines.append(f"{ok(recap_daily_installed())}riepilogo automatico"
                 + (f" alle {ora}" if ora else "  (`plancia daily on 08:45`)"))
    try:
        from . import voice
        v = voice.stato()
        manca = piattaforma.voce_mancante()
        if manca and not (v["voicebox_vivo"] or voice.pocket_vivo()):
            lines.append(f"no  voce: {manca} (il testo funziona lo stesso, senza la voce)")
        else:
            motore = v["motore"]
            if v.get("motore_sistema"):
                motore = f"{motore} ({v['motore_sistema']})"
            lines.append(f"ok  voce: {motore} · {v['voce_attuale'] or 'voce predefinita del sistema'} · "
                         f"{'Voicebox attivo' if v['voicebox_vivo'] else 'voci di sistema'}")
    except Exception as exc:
        lines.append(f"no  voce: {exc}")
    try:
        from . import eventi as _ev
        st = _ev.stato()
        lines.append(f"{ok(st['eventi'] >= 0)}registro eventi: {st['eventi']} righe, "
                     f"{round(st['byte'] / 1024)} KB, schema {st['schema']}")
    except Exception as exc:
        lines.append(f"no  registro eventi: {exc}")
    from . import recap as _recap
    lines.append(f"{ok(bool(_recap.claude_bin()))}claude per il riepilogo: {_recap.claude_bin() or 'non trovato'}")
    if piattaforma.nome() == piattaforma.MAC:
        app = Path("/Applications/Plancia.app")
        lines.append(f"{ok(app.exists())}app macOS in {app}"
                     + ("" if app.exists() else "  (`./mac/build.sh --install`)"))
    else:
        # l'app nativa esiste solo per macOS: qui la dashboard e' nel browser
        lines.append("ok  app nativa: solo macOS, qui la dashboard si apre nel browser "
                     "(`plancia serve --open`)")
    link = piattaforma.percorso_comando(Path.home())
    lines.append(f"{ok(link.exists())}comando {link}")
    lines.extend(_righe_contenitori())
    port = config.load_config().get("port", config.DEFAULT_PORT)
    import socket
    with socket.socket() as s:
        s.settimeout(0.4)
        alive = s.connect_ex(("127.0.0.1", port)) == 0
    lines.append(f"{ok(alive)}dashboard su http://127.0.0.1:{port}"
                 + ("" if alive else "  (avviala con `plancia serve`)"))
    lines.append(f"    python: {sys.executable}")
    return lines
