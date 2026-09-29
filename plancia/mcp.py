"""Server MCP di Plancia: il canale con cui Claude Code legge e scrive nell'hub.

JSON-RPC 2.0 su stdio, scritto a mano sulla libreria standard. Nessun pacchetto
da installare significa che non si rompe quando cambia una dipendenza.

Regola inviolabile: su stdout esce solo JSON-RPC. Ogni diagnostica va su stderr.
"""

import json
import sys
import traceback

from . import (actions, briefing, cantiere, compartimenti_viste as viste, config,
               eventi, lavagna, piattaforma, recap, sessione, store, turni, voice)

PROTOCOL = "2025-06-18"
SUPPORTED = {"2024-11-05", "2025-03-26", "2025-06-18"}
# La versione la dice il pacchetto: tenerne una copia qui vuol dire tenerne una
# copia sbagliata.
try:
    from . import __version__ as VERSION
except Exception:
    VERSION = "0"


def err(msg: str) -> None:
    print(f"[plancia-mcp] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# definizione dei tool
# --------------------------------------------------------------------------

def _s(desc, **props):
    return {"type": "object", "properties": props, "additionalProperties": False,
            "description": desc}


STR = {"type": "string"}
INT = {"type": "integer"}

_TUTTI = [
    {
        "name": "plancia_briefing",
        "description": (
            "Read first in any session about the user's own work. Returns the current "
            "state of that AI work: active projects, open tasks, queued social posts, "
            "recent activity. Optionally scoped to one project."),
        "inputSchema": _s("", project={**STR, "description": "project key or name (optional)"}),
    },
    {
        "name": "plancia_search",
        "description": (
            "Search what was actually said in past sessions, verbatim, plus tasks, "
            "memory notes, posts and commits. Every hit carries the file and the line "
            "it came from, so it can be reopened rather than paraphrased. Use it "
            "before asking 'did we already do X?' and before redoing something."),
        "inputSchema": _s("", query=STR, limit=INT),
    },
    {
        "name": "plancia_projects",
        "description": "List the projects with status, priority, last activity and open task counts.",
        "inputSchema": _s("", status=STR, include_hidden={"type": "boolean"}),
    },
    {
        "name": "plancia_project_update",
        "description": (
            "Update a project: status (attivo/in pausa/concluso/idea), next_action, "
            "summary, priority (1 high, 3 low), pinned. Set next_action whenever you "
            "finish a chunk of work so the next session knows where to pick up."),
        "inputSchema": _s("", project=STR, status=STR, next_action=STR, summary=STR,
                          priority=INT, pinned=INT),
    },
    {
        "name": "plancia_tasks",
        "description": "List tasks. status: aperti (default), tutti, or one of aperto/in corso/bloccato/fatto/archiviato.",
        "inputSchema": _s("", status=STR, project=STR, limit=INT),
    },
    {
        "name": "plancia_task_add",
        "description": (
            "Record a task. Use it whenever work is identified but not done in this "
            "session, so it survives the end of the conversation."),
        "inputSchema": _s("", title=STR, project=STR, priority=INT, due=STR, body=STR),
    },
    {
        "name": "plancia_task_update",
        "description": "Change a task: status, priority, title, body, due date, project.",
        "inputSchema": _s("", id=INT, status=STR, priority=INT, title=STR, body=STR,
                          due=STR, project=STR),
    },
    {
        "name": "plancia_posts",
        "description": "List social posts and their state in the pipeline (idea, bozza, approvato, programmato, pubblicato).",
        "inputSchema": _s("", status=STR, platform=STR),
    },
    {
        "name": "plancia_post_add",
        "description": (
            "Save a social post draft. source_ref must point at the real work behind it "
            "(a commit sha, a repo name, a session id): the account only posts about "
            "things that actually happened. Saving a draft is not publishing. "
            "media is the path to the image that goes out with the post: pick it now, "
            "while you still know what the work looked like. A post without an image "
            "is the exception."),
        "inputSchema": _s("", text=STR, platform=STR, status=STR, project=STR,
                          source_ref=STR, url=STR, scheduled_for=STR, media=STR),
    },
    {
        "name": "plancia_post_update",
        "description": (
            "Update a post: status, url once published, metrics, text, media. Mark "
            "'pubblicato' only after it is actually live, and pass the url."),
        "inputSchema": _s("", id=INT, status=STR, url=STR, text=STR, metrics=STR,
                          scheduled_for=STR, media=STR),
    },
    {
        "name": "plancia_sessions",
        "description": "Past Claude Code sessions with project, date, size and the opening prompt. Use to find where something was done.",
        "inputSchema": _s("", project=STR, query=STR, limit=INT),
    },
    {
        "name": "plancia_memory",
        "description": "Read the memory notes Plancia indexed (Claude's own memory files). Pass name for the full text, or query to search.",
        "inputSchema": _s("", name=STR, query=STR),
    },
    {
        "name": "plancia_log",
        "description": (
            "Record something that happened, so it shows up in the timeline: a decision, "
            "a milestone, a deploy, a dead end. kind: nota, decisione, milestone, problema."),
        "inputSchema": _s("", title=STR, kind=STR, detail=STR, project=STR, ref=STR),
    },
    {
        "name": "plancia_recap",
        "description": (
            "The spoken daily recap of the user's work: sessions, commits, tasks closed "
            "and open, posts, what to pick up next. Use it when the user asks how the "
            "day went, what they got done, or for a briefing. Pass speak=true to read "
            "it aloud on the user's Mac. lang: it, en, es, fr, de, pt."),
        "inputSchema": _s("", lang=STR, day={**STR, "description": "YYYY-MM-DD, default today"},
                          speak={"type": "boolean"}),
    },
    {
        "name": "plancia_speak",
        "description": (
            "Read a text out loud on the user's Mac, in the language given. Use only "
            "when the user asks to hear something. Keep it short and written to be "
            "listened to: no lists, no markdown, no file paths."),
        "inputSchema": _s("", text=STR, lang=STR),
    },
    {
        "name": "plancia_lavagna",
        "description": (
            "The unified board: every open task across Claude Code, Codex and Plancia "
            "itself, with its source, state and project. Use it to answer 'what is "
            "open' without guessing, and before proposing new work."),
        "inputSchema": _s("", stato=STR, fonte=STR, limite=INT),
    },
    {
        "name": "plancia_manda",
        "description": (
            "Dispatch a piece of work to an agent. modo='proposta' (default) lets it "
            "read and plan but never write; modo='esegui' lets it modify files in the "
            "project folder. Only use 'esegui' when the user asked for the work to be "
            "actually done. Returns immediately with a run id; check it with "
            "plancia_lanci."),
        "inputSchema": _s("", titolo=STR, dettaglio=STR, progetto=STR, istruzioni=STR,
                          agente={**STR, "description": "claude or codex"},
                          modo={**STR, "description": "proposta or esegui"},
                          task_id=INT),
    },
    {
        "name": "plancia_lanci",
        "description": "The runs dispatched to agents, newest first, with state and outcome.",
        "inputSchema": _s("", id=INT, limite=INT),
    },
    {
        "name": "plancia_eventi",
        "description": (
            "The append-only event log other tools can consume: work started and "
            "finished, tasks closed, posts published. Pass 'dopo' with the id of the "
            "last event you saw to get only what is new. Use it to find what shipped "
            "since last time, for example before writing a post."),
        "inputSchema": _s("", dopo=STR, tipo=STR, limite=INT),
    },
    {
        "name": "plancia_sync",
        "description": "Re-scan sessions, memory, repos. Fast when incremental; pass full=true to rebuild from scratch.",
        "inputSchema": _s("", full={"type": "boolean"}, skip_git={"type": "boolean"}),
    },
    {
        "name": "plancia_riprendi",
        "description": (
            "Resume a Plancia task from where its own session left off (viva/chiusa/"
            "persa: still open, closed with a transcript, or nothing to resume), or "
            "just check that state. id is required. apri=true launches the resume "
            "command in a visible terminal, or reports the clipboard message when the "
            "session is still open (viva). background=true dispatches it in the "
            "background instead, forking the existing session when there is one "
            "(scrive=true lets it modify files, istruzioni adds instructions). Without "
            "apri or background it only reports the state, the ready command and the "
            "message, without launching anything."),
        "inputSchema": _s("", id=INT, apri={"type": "boolean"}, background={"type": "boolean"},
                          scrive={"type": "boolean"}, istruzioni=STR),
    },
]


# --------------------------------------------------------------------------
# cosa viene esposto, e perche' solo questo
#
# Gli schemi dei tool stanno nel contesto di OGNI sessione, sempre, che vengano
# usati o no. Misurato il 9 agosto 2026: i venti tool pesavano 2170 token a
# sessione, e le sessioni che li hanno davvero caricati sono 696, cioe quelle
# dal 2 agosto, giorno del primo commit di questo file. Fanno 1,5 milioni di
# token per 158 chiamate in tutto. E quattro di loro (speak, sync, lavagna,
# eventi) non erano stati chiamati mai, nemmeno una volta.
#
# Quindi restano di prima classe i cinque che portano l'uso vero, piu' search,
# che e' la ragione per cui l'archivio esiste: senza, 427 sessioni e 41 memorie
# non servono a niente. Tutto il resto continua a funzionare identico, ma dietro
# un tool solo, e paga un solo schema invece di quindici.
# --------------------------------------------------------------------------

PRIMI = ("plancia_search", "plancia_task_add", "plancia_task_update",
         "plancia_log", "plancia_project_update", "plancia_post_add")

#: nome dell'azione -> definizione completa, per chi chiede aiuto al dispatcher
CODA = {t["name"].removeprefix("plancia_"): t for t in _TUTTI if t["name"] not in PRIMI}


#: Un indizio per azione, corto quanto basta a sceglierla. Il manuale completo
#: costa quindici schemi, ed e' esattamente la spesa che questo tool evita:
#: chi ha bisogno degli argomenti chiede azione='aiuto' e li paga una volta sola.
INDIZI = {
    "briefing": "state of the user's work now",
    "projects": "list projects",
    "tasks": "list tasks",
    "posts": "list social drafts",
    "post_update": "change a post, mark it published",
    "sessions": "past sessions, where something was done",
    "memory": "the memory notes",
    "recap": "spoken daily recap",
    "speak": "read text aloud",
    "lavagna": "open tasks across Claude, Codex and Plancia",
    "manda": "dispatch work to an agent",
    "lanci": "state of dispatched runs",
    "eventi": "append-only event log, what shipped since",
    "sync": "re-scan sessions, memory, repos",
    "riprendi": "resume a task's own session, or check its state",
}

TOOLS = [t for t in _TUTTI if t["name"] in PRIMI] + [{
    "name": "plancia",
    "description": (
        "The rest of the archive, behind one tool: pass azione plus that action's "
        "own arguments, or azione='aiuto' with di='<action>' for its arguments.\n"
        + " | ".join(f"{n}: {h}" for n, h in INDIZI.items())),
    "inputSchema": {
        "type": "object",
        "properties": {"azione": {"type": "string", "enum": sorted(CODA) + ["aiuto"]}},
        "required": ["azione"],
        # Gli argomenti veri sono quelli dell'azione scelta, e stanno in CODA.
        # Ripeterli qui vorrebbe dire ripagare i quindici schemi che questo
        # tool esiste per non pagare.
        "additionalProperties": True,
    },
}]


# --------------------------------------------------------------------------
# esecuzione
# --------------------------------------------------------------------------

def _fmt(data) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# Le azioni che scrivono qualcosa di persistente. `plancia_riprendi` scrive
# solo quando `background=True` (dispatcha un lancio): senza, riporta solo lo
# stato, ed è un'azione di lettura come le altre.
_SCRITTURE = {"plancia_task_add", "plancia_task_update", "plancia_post_add",
              "plancia_post_update", "plancia_log", "plancia_project_update",
              "plancia_manda"}


def _sessione_bloccata(conn):
    """Il motivo per cui la sessione che sta chiamando ADESSO non può
    scrivere, o `None` se può.

    Il server MCP di una sessione aperta in un contenitore e poi SPOSTATA con
    `change_directory` (o un tool equivalente) può avere ancora la cwd di
    PARTENZA: `sessione.corrente()` legge `os.getcwd()` del PROCESSO server,
    fissata al suo avvio, non la cwd "logica" della conversazione che lo
    ospita. Il solo controllo sulla cwd di adesso non basterebbe in quel
    caso: si controlla anche il session_id contro gli id scoperti dall'ultimo
    `plancia sync` (una sessione aperta altrove, ma il cui contenuto rivela
    poi una cartella privata, viene scoperta da `ingest.sync_sessions` e
    ricordata — vedi `esclusi.carica(conn=...)`), così anche una sessione il
    cui server non ha mai visto la cwd giusta risulta comunque bloccata, con
    un giro di ritardo rispetto all'ultimo sync.
    """
    try:
        s = sessione.corrente()
    except Exception:
        return None
    from . import esclusi as _esclusi
    escl = _esclusi.carica(conn=conn)
    if not _esclusi.configurato(escl):
        return None
    if _esclusi.sessione_esclusa(s.get("session_id"), s.get("cwd"), escl):
        return ("questa sessione lavora su una cartella o un id privati "
                "(esclusi da Plancia): niente scritture da qui.")
    return None


def _progetto_scrivibile(conn, lettura, ombra, ident, esiste=False, chiave=False):
    """Il progetto da usare in una scrittura, senza uscire dal compartimento
    (la regola e' `compartimenti_viste.progetto_scrivibile`, la stessa del
    comando da terminale e della dashboard)."""
    return viste.progetto_scrivibile(conn, lettura, ombra, ident, esiste=esiste,
                                     chiave=chiave)


def _oggetto_scrivibile(conn, lettura, ombra, leggi, chiave, nome):
    """Rifiuta di toccare un task o un post che la sessione non vede (la regola
    e' `compartimenti_viste.oggetto_scrivibile`)."""
    viste.oggetto_scrivibile(conn, lettura, ombra, leggi, chiave, nome)


def call_tool(name: str, args: dict) -> str:
    # Il dispatcher: `plancia` con un'azione diventa il tool di prima che aveva
    # quel nome, e da li' in giu' non cambia niente. Tenere una catena sola vuol
    # dire che i due modi di chiamare non possono divergere.
    if name == "plancia":
        args = dict(args)
        azione = str(args.pop("azione", "")).strip()
        if azione == "aiuto":
            quale = str(args.get("di") or args.get("azione_richiesta") or "").strip()
            if quale in CODA:
                return _fmt({"azione": quale, "argomenti": CODA[quale]["inputSchema"],
                             "descrizione": CODA[quale]["description"]})
            return _fmt({"azioni": {n: CODA[n]["description"] for n in sorted(CODA)}})
        if azione not in CODA:
            return (f"azione sconosciuta: {azione!r}. "
                    f"Quelle valide sono: {', '.join(sorted(CODA))}")
        name = f"plancia_{azione}"

    conn = store.connect()
    store.init_db(conn)
    # Compartimenti (plancia/compartimenti_viste.py): se in config ce ne sono di
    # nominati, questo server sa di che compartimento e' la sessione che lo ha
    # lanciato (`sessione.corrente()`: l'id e la cwd di partenza; l'id si
    # confronta anche con la cartella in cui e' stata aperta, trovando il suo
    # transcript). Le LETTURE passano da `lettura`, una seconda connessione con
    # le viste temporanee che nascondono gli altri compartimenti; le SCRITTURE
    # da `conn`, dopo aver controllato a mano di che compartimento e' l'oggetto
    # (una vista non si scrive). Senza compartimenti `lettura` e `conn` sono la
    # stessa connessione e non cambia niente. Se la separazione non riesce
    # (un'eccezione) la chiamata fallisce: niente lettura senza filtro.
    lettura, ombra, visore = conn, None, None
    try:
        ambito = viste.attivo()
        if ambito is not None:
            try:
                s_ = sessione.corrente()
            except Exception:
                s_ = {}
            visore = viste.visore_mcp(ambito, s_)
            lettura = store.connect()
            ombra = viste.applica(lettura, ambito, visore)
    except Exception:
        err(traceback.format_exc())
        conn.close()
        raise actions.BadInput("compartimenti: non riesco a stabilire da che "
                               "compartimento sei, niente da qui.")
    # cosa mettere nella colonna `compartimento` di quello che si scrive: il
    # nominato dice sempre il suo (vale anche se la sessione non e' nota)
    tag_comp = visore if visore not in (None, viste.PREDEFINITO, viste.INCERTO) else ""
    try:
        if ombra is not None and visore == viste.INCERTO:
            raise actions.BadInput(
                "questa sessione ha segnali di piu' compartimenti: Plancia non "
                "mostra niente (e non scrive) finche' non e' chiaro di quale sia.")
        scrive_ora = name in _SCRITTURE or (
            name == "plancia_riprendi" and bool(args.get("background")))
        if scrive_ora:
            motivo = _sessione_bloccata(conn)
            if motivo:
                raise actions.BadInput(motivo)

        if name == "plancia_briefing":
            return briefing.build(lettura, args.get("project"))

        if name == "plancia_search":
            q = args.get("query", "")
            limite = int(args.get("limit") or 25)
            # Prima i turni, perche' e' li' che sta quello che si vuole
            # ritrovare: fino al 9 agosto 2026 questa ricerca vedeva solo il
            # primo prompt di ogni sessione, lo 0,08% del materiale, ed e' il
            # motivo per cui e' stata chiamata cinque volte in tutto.
            if ombra is not None:
                # l'indice FTS non si filtra con una vista: il filtro sta dentro la query, prima del taglio per rango
                dai_turni, gruppi = viste.cerca_turni(
                    lettura, ombra, q, min(limite, 12), args.get("project"))
                schede = viste.cerca_schede(lettura, ombra, q, limite)
            else:
                dai_turni = turni.cerca(conn, q, limit=min(limite, 12),
                                        progetto=args.get("project"))
                schede = store.search(conn, q, limite)
                gruppi = None
            if not dai_turni and not schede:
                return "nessun risultato"
            esito = {"nei_turni": dai_turni, "nelle_schede": schede}
            # Il conteggio per progetto sta su tutto l'indice: dice quanto resta
            # fuori dai dodici mostrati, e da dove, cosi si puo' richiamare con
            # `project` invece di andare a tentoni.
            if gruppi is None:
                gruppi = turni.raggruppa(conn, q) if dai_turni else []
            if len(gruppi) > 1:
                esito["altrove"] = {g["progetto"]: g["turni"] for g in gruppi}
            return _fmt(esito)

        if name == "plancia_projects":
            sql = ("SELECT p.id, p.key, p.name, p.kind, p.status, p.priority, p.pinned, "
                   "p.summary, p.next_action, p.last_activity, "
                   "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND "
                   "t.status IN ('aperto','in corso','bloccato')) AS task_aperti, "
                   "(SELECT COUNT(*) FROM sessions s WHERE s.project_id=p.id) AS sessioni "
                   "FROM projects p WHERE 1=1")
            params = []
            if not args.get("include_hidden"):
                sql += " AND p.hidden=0"
            if args.get("status"):
                sql += " AND p.status=?"
                params.append(args["status"])
            sql += " ORDER BY p.pinned DESC, p.priority ASC, p.last_activity DESC"
            return _fmt([dict(r) for r in lettura.execute(sql, params).fetchall()])

        if name == "plancia_project_update":
            return _fmt(actions.project_update(
                conn, _progetto_scrivibile(conn, lettura, ombra, args.get("project"),
                                           esiste=True),
                status=args.get("status"), next_action=args.get("next_action"),
                summary=args.get("summary"), priority=args.get("priority"),
                pinned=args.get("pinned")))

        if name == "plancia_tasks":
            return _fmt(actions.tasks_list(lettura, args.get("status"), args.get("project"),
                                           int(args.get("limit") or 50)))

        if name == "plancia_task_add":
            # Chi ha chiamato adesso: L0-SESSIONE, cosi' "Riprendi" (ondata 2)
            # ha una sessione a cui tornare invece di un task orfano
            # (docs/CONSIGLIO-2026-09-16-verdetto.md, "La prima cosa da fare").
            # Cintura di sicurezza: corrente() legge os.getcwd(), che solleva
            # se la cartella in cui il server e' partito e' stata cancellata
            # nel frattempo (scenario reale: copie di lotto in
            # ~/dev/plancia-copie/<lotto> cancellate a fine lotto con la
            # sessione ancora viva). Senza questo try il task non viene
            # scritto affatto: meglio scriverlo con i campi vuoti.
            try:
                s = sessione.corrente()
            except Exception:
                err(traceback.format_exc())
                s = {}
            if s.get("origine") == "nessuna":
                # Non e' un errore (il task si scrive comunque, con i campi
                # che ci sono), ma vale la pena saperlo: soprattutto per
                # agent="codex", dove nessun server lanciato da Codex era
                # vivo al momento di questo lotto per misurare se la cwd del
                # server coincide con quella del rollout (e' un'inferenza,
                # non una misura: vedi plancia/sessione.py).
                err("sessione.corrente() non ha trovato niente: agent=%r cwd=%r" %
                    (s.get("agent"), s.get("cwd")))
            return _fmt(actions.task_add(
                conn, args.get("title"), args.get("body", ""),
                _progetto_scrivibile(conn, lettura, ombra, args.get("project")),
                args.get("priority", 2), args.get("due"), source="claude",
                session_id=s.get("session_id"), cwd=s.get("cwd"), agent=s.get("agent"),
                host=s.get("host"), compartimento=tag_comp))

        if name == "plancia_task_update":
            _oggetto_scrivibile(conn, lettura, ombra, actions.task_get,
                                int(args.get("id")), "il task")
            return _fmt(actions.task_update(
                conn, int(args.get("id")), status=args.get("status"),
                priority=args.get("priority"), title=args.get("title"),
                body=args.get("body"), due=args.get("due"),
                # "" svuota il progetto del task: `_progetto_scrivibile` lo
                # trasformerebbe in None ("non toccare"), quindi passa cosi' com'e'
                project=(args.get("project") if args.get("project") in (None, "")
                         else _progetto_scrivibile(conn, lettura, ombra,
                                                   args.get("project")))))

        if name == "plancia_posts":
            return _fmt(actions.posts_list(lettura, args.get("status"), args.get("platform")))

        if name == "plancia_post_add":
            try:
                sid_post = sessione.corrente().get("session_id")
            except Exception:
                sid_post = None
            return _fmt(actions.post_add(
                conn, args.get("text"), args.get("platform", "x"),
                args.get("status", "bozza"),
                _progetto_scrivibile(conn, lettura, ombra, args.get("project")),
                args.get("url"), args.get("source_ref", ""), args.get("scheduled_for"),
                session_id=sid_post if ombra is not None else None,
                media=args.get("media", ""), compartimento=tag_comp))

        if name == "plancia_post_update":
            _oggetto_scrivibile(conn, lettura, ombra, actions.post_get,
                                int(args.get("id")), "il post")
            return _fmt(actions.post_update(
                conn, int(args.get("id")), status=args.get("status"), url=args.get("url"),
                text=args.get("text"), metrics=args.get("metrics"),
                scheduled_for=args.get("scheduled_for"), media=args.get("media")))

        if name == "plancia_sessions":
            sql = ("SELECT s.session_id, s.title, substr(s.first_prompt,1,220) AS prompt, "
                   "s.started_at, s.ended_at, s.n_user, s.n_tools, s.cwd, s.models, "
                   "p.name AS progetto FROM sessions s LEFT JOIN projects p ON p.id=s.project_id "
                   "WHERE 1=1")
            params = []
            if args.get("project"):
                row = store.get_project(lettura, args["project"])
                sql += " AND s.project_id=?"
                params.append(row["id"] if row else -1)
            if args.get("query"):
                sql += " AND (s.first_prompt LIKE ? OR s.title LIKE ?)"
                params += [f"%{args['query']}%"] * 2
            sql += " ORDER BY s.started_at DESC LIMIT ?"
            params.append(int(args.get("limit") or 20))
            return _fmt([dict(r) for r in lettura.execute(sql, params).fetchall()])

        if name == "plancia_memory":
            if args.get("name"):
                row = lettura.execute(
                    "SELECT name, description, type, body, updated_at FROM knowledge "
                    "WHERE name=? OR name LIKE ?", (args["name"], f"%{args['name']}%")
                ).fetchone()
                return _fmt(dict(row)) if row else "nessuna memoria con questo nome"
            like = f"%{args.get('query', '')}%"
            rows = lettura.execute(
                "SELECT name, description, type, updated_at FROM knowledge "
                "WHERE name LIKE ? OR description LIKE ? OR body LIKE ? "
                "ORDER BY updated_at DESC LIMIT 40", (like, like, like)).fetchall()
            return _fmt([dict(r) for r in rows])

        if name == "plancia_log":
            return _fmt(actions.log_event(
                conn, args.get("title"), args.get("kind", "nota"), args.get("detail", ""),
                _progetto_scrivibile(conn, lettura, ombra, args.get("project")),
                args.get("ref"), compartimento=tag_comp))

        if name == "plancia_recap":
            data = recap.build(lettura, args.get("day"), args.get("lang"))
            if args.get("speak"):
                info = voice.parla(data["testo"], data["lingua"], attendi=False)
                if info["motore"] == "nessuno":
                    # il testo arriva lo stesso: la voce non c'e', e si dice perche'
                    data["voce"] = None
                    data["nota_voce"] = info.get("errore") or "nessun motore vocale"
                else:
                    data["voce"] = info["motore"]
            data.pop("dati", None)
            return _fmt(data)

        if name == "plancia_speak":
            testo = (args.get("text") or "").strip()
            if not testo:
                raise actions.BadInput("serve un testo")
            info = voice.parla(testo, recap.lang_or_default(args.get("lang")), attendi=False)
            if info["motore"] == "nessuno":
                # nessun motore ha parlato: dirlo, o l'agente racconta di aver letto
                return _fmt({"letto": False, "motore": None, "lingua": info["lingua"],
                             "motivo": info.get("errore") or "nessun motore vocale"})
            return _fmt({"letto": True, "motore": info["motore"], "lingua": info["lingua"]})

        if name == "plancia_lavagna":
            return _fmt({"voci": lavagna.elenco(lettura, args.get("stato", "aperti"),
                                                args.get("fonte"),
                                                int(args.get("limite") or 60)),
                         "conteggi": lavagna.conteggi(lettura)})

        if name == "plancia_manda":
            titolo = (args.get("titolo") or "").strip()
            if not titolo:
                raise actions.BadInput("serve un titolo")
            progetto = args.get("progetto")
            if ombra is not None:
                if args.get("task_id") is not None:
                    _oggetto_scrivibile(conn, lettura, ombra, actions.task_get,
                                        int(args["task_id"]), "il task")
                # la chiave, non l'id: e' quella che finisce nel registro degli eventi
                progetto = _progetto_scrivibile(conn, lettura, ombra, progetto, chiave=True)
                if progetto is None and visore != viste.PREDEFINITO:
                    # senza un progetto l'agente partirebbe in una cartella
                    # qualunque, che non e' detto sia del tuo compartimento
                    raise actions.BadInput(
                        "da un compartimento nominato plancia_manda vuole un "
                        "progetto del compartimento (progetto=...).")
            return _fmt(cantiere.avvia(
                conn, titolo, args.get("dettaglio", ""), progetto,
                args.get("istruzioni", ""), args.get("agente", "claude"),
                args.get("modo", "proposta"), None, args.get("task_id"),
                compartimento=tag_comp))

        if name == "plancia_lanci":
            if args.get("id"):
                return _fmt(cantiere.dettaglio(lettura, int(args["id"])))
            return _fmt(cantiere.elenco(lettura, int(args.get("limite") or 10)))

        if name == "plancia_eventi":
            limite = int(args.get("limite") or 50)
            if ombra is None:
                return _fmt(eventi.leggi(args.get("dopo"), args.get("tipo"), limite))
            # il registro e' un file solo, di tutti: il filtro sta dentro la
            # lettura, prima del taglio agli ultimi `limite`
            return _fmt(ombra.leggi_eventi(args.get("dopo"), args.get("tipo"), limite))

        if name == "plancia_sync":
            from . import ingest
            conn.close()
            res = ingest.sync(full=bool(args.get("full")),
                              skip_git=bool(args.get("skip_git")))
            return _fmt(res)

        if name == "plancia_riprendi":
            tid = args.get("id")
            if tid is None:
                raise actions.BadInput("serve id")
            if ombra is not None:
                _oggetto_scrivibile(conn, lettura, ombra, actions.task_get,
                                    int(tid), "il task")
            task = actions.task_get(lettura, int(tid))
            if not task:
                raise actions.BadInput(f"task {tid} inesistente")
            from . import riprendi as _riprendi
            s = _riprendi.stato(lettura, task)
            if args.get("apri"):
                return _fmt(_riprendi.apri(task, conn))
            if args.get("background"):
                # Stessa logica del ramo background di api.py e cmd_riprendi:
                # fork della sessione quando c'e' (viva o chiusa), altrimenti
                # cantiere.avvia() scrive da solo un prompt da zero (persa).
                # Nome locale `sessione_fork`, non `sessione`: il modulo
                # `sessione` (plancia/sessione.py) e' importato in cima a
                # questo file e usato piu' sopra, in plancia_task_add
                # (`sessione.corrente()`) - una variabile locale chiamata
                # come lui lo ombreggia per l'INTERA funzione `call_tool`
                # (regola di scoping di Python: un'assegnazione in un punto
                # qualsiasi del corpo rende il nome locale ovunque nel
                # corpo), e task_add falliva con UnboundLocalError perche'
                # leggeva quel nome prima che questo ramo lo assegnasse mai.
                sessione_fork = _riprendi.sessione_da_riprendere(s)
                return _fmt(cantiere.avvia(
                    conn, task.get("title") or "", "", task.get("project_key"),
                    args.get("istruzioni", ""), s.get("agent") or task.get("agent") or "claude",
                    bool(args.get("scrive")), None, task["id"], sessione=sessione_fork,
                    compartimento=tag_comp))
            argv = _riprendi.comando(task, s, lettura)
            return _fmt({"stato": s.get("stato"), "motivo": s.get("motivo"),
                        "sessione": s.get("session_id"), "cwd": s.get("cwd"),
                        "comando": argv, "messaggio": _riprendi.messaggio(task)})

        raise actions.BadInput(f"tool sconosciuto: {name}")
    finally:
        if lettura is not conn:
            viste.chiudi(lettura, ombra)
            try:
                lettura.close()
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# ciclo JSON-RPC
# --------------------------------------------------------------------------

def respond(rid, result=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(req: dict) -> None:
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if rid is None:  # notifica: nessuna risposta
        return

    if method == "initialize":
        asked = params.get("protocolVersion")
        respond(rid, {
            "protocolVersion": asked if asked in SUPPORTED else PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "plancia", "version": VERSION},
            "instructions": (
                "Plancia is the user's control centre for their AI work. Call "
                "plancia_briefing at the start of a session about their projects, and "
                "record tasks, decisions and social posts as they happen."),
        })
    elif method == "ping":
        respond(rid, {})
    elif method == "tools/list":
        respond(rid, {"tools": TOOLS})
    elif method == "resources/list":
        respond(rid, {"resources": []})
    elif method == "resources/templates/list":
        respond(rid, {"resourceTemplates": []})
    elif method == "prompts/list":
        respond(rid, {"prompts": []})
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            text = call_tool(name, args)
            respond(rid, {"content": [{"type": "text", "text": text}], "isError": False})
        except actions.BadInput as exc:
            respond(rid, {"content": [{"type": "text", "text": f"Errore: {exc}"}],
                          "isError": True})
        except Exception as exc:
            err(traceback.format_exc())
            respond(rid, {"content": [{"type": "text", "text": f"Errore interno: {exc}"}],
                          "isError": True})
    else:
        respond(rid, error={"code": -32601, "message": f"metodo non gestito: {method}"})


def main() -> int:
    piattaforma.stdio_utf8()
    config.ensure_dirs()
    conn = store.connect()
    store.init_db(conn)
    conn.close()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        try:
            if isinstance(req, list):
                for item in req:
                    handle(item)
            else:
                handle(req)
        except Exception:
            err(traceback.format_exc())
    return 0


if __name__ == "__main__":
    sys.exit(main())
