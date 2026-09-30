"""Jarvis: quello che dici a voce diventa una cosa fatta.

Due strade, in quest'ordine. Le frasi che si riconoscono con certezza ("apri i
progetti", "ricordami di chiamare Mario") vengono eseguite qui, in un decimo di
secondo e senza chiamare nessuno. Tutto il resto va a Claude Code in modalità non
interattiva con i tool di Plancia aperti, quindi può davvero aggiungere task,
aggiornare progetti e cercare, non solo rispondere.

Le frasi corte si sbagliano facilmente: se un comando non è chiaro, non si tira a
indovinare, si passa a Claude.
"""

import re

from . import (actions, agente, cantiere, compartimenti_viste, proposte, recap,
               riprendi, risposte, store)

# --------------------------------------------------------------------------
# comandi riconosciuti al volo
# --------------------------------------------------------------------------

VISTE = {
    "oggi": "oggi", "today": "oggi", "hoy": "oggi", "cruscotto": "oggi",
    "riepilogo": "riepilogo", "recap": "riepilogo", "resumen": "riepilogo",
    "progetti": "progetti", "projects": "progetti", "proyectos": "progetti",
    "task": "task", "tasks": "task", "cose da fare": "task", "tareas": "task",
    "social": "social", "post": "social",
    "sessioni": "sessioni", "sessions": "sessioni", "sesiones": "sessioni",
    "agenti": "agenti", "agents": "agenti", "codex": "agenti",
    "conoscenza": "conoscenza", "knowledge": "conoscenza", "memoria": "conoscenza",
    "capacità": "capacita", "capacita": "capacita", "skills": "capacita",
}

MODELLI = {
    # "Non ho capito" detto a una macchina vuol dire ripeti, non spiegami.
    "ripeti": [r"^(?:ripeti|come(?: hai| ha)? detto|non ho (?:capito|sentito)|di nuovo)\b",
               r"^(?:repeat|say (?:that )?again|what did you say|come again)\b",
               r"^(?:repite|repítelo|c[oó]mo dices|otra vez)\b"],
    "velocita": [r"^(?:parla |vai |più |piu )?(più|piu|meno) (piano|lento|lentamente|veloce|svelto|rapido)\b",
                 r"^(?:slow(?:er)? down|speak slower|speed up|faster|slower)\b",
                 r"^(?:m[aá]s (?:despacio|lento|r[aá]pido)|habla m[aá]s (?:despacio|r[aá]pido))\b"],
    "vai": [
        r"^(?:apri|apre|vai (?:a|su|in)|mostra(?:mi)?|portami (?:a|su))\s+(?:la |il |le |i |lo )?(.+?)[.?!]*$",
        r"^(?:open|go to|show me|show)\s+(?:the )?(.+?)[.?!]*$",
        r"^(?:abre|abrir|ve a|mu[eé]strame)\s+(?:la |el |los |las )?(.+?)[.?!]*$",
    ],
    "riepilogo": [
        r"^(?:fammi (?:il|un) |dammi (?:il|un) |leggimi (?:il|un) )?riepilogo\b",
        r"^com'?[eè] andata",
        r"^(?:give me |read me )?(?:the )?(?:daily )?recap\b",
        r"^how did (?:the day|today) go",
        r"^(?:dame |l[eé]eme )?el resumen\b",
    ],
    "fallo": [
        r"^(?:fallo|falla|s[iì](?:,? fallo| grazie)?|procedi|vai|ok(?:,? procedi)?|d'accordo)\b(.*)$",
        r"^(?:do it|yes(?:,? do it)?|go ahead|proceed)\b(.*)$",
        r"^(?:hazlo|s[ií](?:,? hazlo)?|adelante)\b(.*)$",
        r"^(?:la |il )?(prima|primo|seconda|secondo|terza|terzo)\b(.*)$",
    ],
    "eseguilo": [
        r"^(?:esegui(?:lo|la)?|fallo davvero|fallo per davvero|fallo e basta)\b(.*)$",
        r"^(?:actually do it|really do it|execute it)\b(.*)$",
    ],
    "aggiorna": [r"^(?:aggiorna|sincronizza|rileggi)\b", r"^(?:refresh|sync|update)\b",
                 r"^(?:actualiza|sincroniza)\b"],
    # Fermare un lavoro partito è diverso dal far tacere la voce: se uno dice
    # "annulla" mentre un agente sta lavorando, vuole fermare quello.
    "annulla": [r"^(?:annulla|ferma il lavoro|ferma il lancio|interrompi)\b(.*)$",
                r"^(?:cancel|stop the run|abort)\b(.*)$",
                r"^(?:cancela|para el trabajo)\b(.*)$"],
    "ferma": [r"^(?:basta|ferma(?:ti)?|stop|zitto|silenzio|smetti)\b",
              r"^(?:quiet|shut up|be quiet)\b", r"^(?:para|c[aá]llate|silencio)\b"],
    "task_add": [
        r"^(?:ricordami di|ricordami|segna(?:ti)? (?:che|di)?|aggiungi (?:un |il )?task|nuovo task|devo)\s+(.+?)[.?!]*$",
        r"^(?:remind me to|add (?:a )?task|new task|note that)\s+(.+?)[.?!]*$",
        r"^(?:recu[eé]rdame|a[ñn]ade (?:una )?tarea|nueva tarea)\s+(.+?)[.?!]*$",
    ],
    "archivia": [
        r"^(?:archivia|chiudi il progetto|(?:ho )?finito con|metti via)\s+(.+?)[.?!]*$",
        r"^(.+?)\s+(?:è|e) (?:finito|finita|concluso|conclusa|chiuso|chiusa)[.?!]*$",
        r"^(?:archive|close the project|done with)\s+(.+?)[.?!]*$",
        r"^(?:archiva|cierra el proyecto|he terminado con)\s+(.+?)[.?!]*$",
    ],
    "riapri_progetto": [
        r"^(?:riapri|riattiva) (?:il progetto )?(.+?)[.?!]*$",
        r"^(?:reopen|reactivate) (?:the project )?(.+?)[.?!]*$",
    ],
    "task_done": [
        r"^(?:ho fatto|fatto|chiudi (?:il )?task|segna(?:lo)? (?:come )?fatto)\s*(.*?)[.?!]*$",
        r"^(?:done|i did|close (?:the )?task|mark (?:it )?done)\s*(.*?)[.?!]*$",
        r"^(?:hecho|he hecho|cierra la tarea)\s*(.*?)[.?!]*$",
    ],
    # LOTTO-L3-RIPRENDI-UI punto 4: "riprendi il task N" e' diverso da
    # "fallo"/"eseguilo" (che scelgono una PROPOSTA calcolata) - qui il numero
    # e' l'id di un task vero, e la frase decide da sola quale riprendere.
    "riprendi_task": [
        r"^riprendi (?:il )?task\s+(\d+)\b.*$",
        r"^resume task\s+(\d+)\b.*$",
        r"^retoma(?:r)? (?:la )?tarea\s+(\d+)\b.*$",
    ],
}

RISPOSTE = {
    "it": {
        "vai": "Apro {vista}.",
        "aggiorna": "Rileggo le fonti.",
        "ferma": "Va bene.",
        "niente_da_ripetere": "Non ho ancora detto niente.",
        "piu_piano": "Vado più piano.",
        "piu_veloce": "Vado più svelto.",
        "niente_da_fermare": "Non c'è niente in corso da fermare.",
        "fermato": "Fermato. Lavori interrotti: {n}.",
        "task_add": "Segnato: {titolo}.",
        "task_done": "Chiuso: {titolo}.",
        "task_non_trovato": "Non trovo un task aperto che assomigli a {titolo}.",
        "archiviato": "Archiviato {nome}. Non lo segnalo più.",
        "riaperto": "{nome} torna attivo.",
        "progetto_non_trovato": "Non trovo un progetto che si chiami {nome}.",
        "niente_proposte": "Non ho niente in sospeso da proporti. Chiedimi il riepilogo.",
        "mandato": "Mando {chi} a vedere: {cosa}. Ti dico com'è andata.",
        "mandato_esegui": "Mando {chi} a farlo davvero: {cosa}.",
        "mandato_stessa": "Riprende la sessione originale.",
        "mandato_nuova": "La sessione originale non c'è più: ne parte una nuova.",
        "sessione_aperta": "La sessione è aperta: da qui non la tocco.",
        "fatto_proposta": "Fatto.",
        "nessun_task": "Non hai task aperti.",
        "non_capito": "Non ho capito.",
        "riprendi_viva": "È aperta, l'ho copiata negli appunti: incollala nella sessione.",
        "riprendi_viva_senza_copia": "È aperta, ma non sono riuscito a copiarla negli appunti.",
        "riprendi_chiusa": "La riprendo.",
        "riprendi_persa": "Non c'è niente da riprendere, parto da capo: {motivo}.",
        "riprendi_non_trovato": "Non trovo il task numero {id}.",
        "riprendi_lancio_errore": "Non sono riuscito a lanciarlo: {errore}.",
        "aggiorna_no_sync": "Il sync è disattivato in questa sessione (--no-sync).",
    },
    "en": {
        "vai": "Opening {vista}.",
        "aggiorna": "Re-reading the sources.",
        "ferma": "All right.",
        "niente_da_ripetere": "I have not said anything yet.",
        "piu_piano": "Slowing down.",
        "piu_veloce": "Speeding up.",
        "niente_da_fermare": "There is nothing running to stop.",
        "fermato": "Stopped. Runs interrupted: {n}.",
        "task_add": "Noted: {titolo}.",
        "task_done": "Closed: {titolo}.",
        "task_non_trovato": "I cannot find an open task like {titolo}.",
        "archiviato": "Archived {nome}. I will stop bringing it up.",
        "riaperto": "{nome} is active again.",
        "progetto_non_trovato": "I cannot find a project called {nome}.",
        "niente_proposte": "Nothing pending to suggest. Ask me for the recap.",
        "mandato": "Sending {chi} to look at: {cosa}. I will tell you how it went.",
        "mandato_esegui": "Sending {chi} to actually do it: {cosa}.",
        "mandato_stessa": "It picks up the original session.",
        "mandato_nuova": "The original session is gone: a new one starts.",
        "sessione_aperta": "The session is open: I will not touch it from here.",
        "fatto_proposta": "Done.",
        "nessun_task": "You have no open tasks.",
        "non_capito": "I did not catch that.",
        "riprendi_viva": "It is open, I copied it to the clipboard: paste it into the session.",
        "riprendi_viva_senza_copia": "It is open, but I could not copy it to the clipboard.",
        "riprendi_chiusa": "Resuming it.",
        "riprendi_persa": "There is nothing to resume, starting from scratch: {motivo}.",
        "riprendi_non_trovato": "I cannot find task number {id}.",
        "riprendi_lancio_errore": "I could not launch it: {errore}.",
        "aggiorna_no_sync": "Sync is disabled for this session (--no-sync).",
    },
    "es": {
        "vai": "Abro {vista}.",
        "aggiorna": "Releo las fuentes.",
        "ferma": "Vale.",
        "niente_da_ripetere": "Todavía no he dicho nada.",
        "piu_piano": "Voy más despacio.",
        "piu_veloce": "Voy más rápido.",
        "niente_da_fermare": "No hay nada en marcha que parar.",
        "fermato": "Parado. Trabajos interrumpidos: {n}.",
        "task_add": "Apuntado: {titolo}.",
        "task_done": "Cerrado: {titolo}.",
        "task_non_trovato": "No encuentro una tarea abierta parecida a {titolo}.",
        "archiviato": "Archivado {nome}. No lo vuelvo a mencionar.",
        "riaperto": "{nome} vuelve a estar activo.",
        "progetto_non_trovato": "No encuentro un proyecto que se llame {nome}.",
        "niente_proposte": "No tengo nada pendiente que proponerte. Pídeme el resumen.",
        "mandato": "Mando a {chi} a mirar: {cosa}. Te digo cómo ha ido.",
        "mandato_esegui": "Mando a {chi} a hacerlo de verdad: {cosa}.",
        "mandato_stessa": "Retoma la sesión original.",
        "mandato_nuova": "La sesión original ya no existe: empieza una nueva.",
        "sessione_aperta": "La sesión está abierta: no la toco desde aquí.",
        "fatto_proposta": "Hecho.",
        "nessun_task": "No tienes tareas abiertas.",
        "non_capito": "No te he entendido.",
        "riprendi_viva": "Está abierta, la he copiado al portapapeles: pégala en la sesión.",
        "riprendi_viva_senza_copia": "Está abierta, pero no he podido copiarla al portapapeles.",
        "riprendi_chiusa": "La retomo.",
        "riprendi_persa": "No hay nada que retomar, empiezo de cero: {motivo}.",
        "riprendi_non_trovato": "No encuentro la tarea número {id}.",
        "riprendi_lancio_errore": "No he podido lanzarlo: {errore}.",
        "aggiorna_no_sync": "La sincronización está desactivada en esta sesión (--no-sync).",
    },
}


def _dizionario(lang):
    return RISPOSTE.get(lang, RISPOSTE["en"])


# I 9 prefissi di `motivo` che `plancia/riprendi.py` produce in italiano fisso
# (vedi `stato()` lì): la dashboard li traduce con `Tmot()` in web/app.js, ma
# quella tabella conosce solo l'inglese. Qui serve anche lo spagnolo perché
# Jarvis può rispondere in tre lingue, e senza questa traduzione la voce
# inglese/spagnola pronunciava parole italiane in mezzo alla frase (bug
# trovato dal critico dell'ondata L3-RIPRENDI-UI-2).
MOTIVI_PREFISSI = [
    ("mai registrata", "never recorded", "nunca registrada"),
    ("sessione scaduta", "session expired", "sesión caducada"),
    ("aperta in un'altra sessione", "open in another session", "abierta en otra sesión"),
    ("aperta in ", "open in ", "abierta en "),
    ("creato su ", "created on ", "creado en "),
    ("non sono riuscito a interrogare le sessioni aperte",
     "could not check open sessions", "no he podido consultar las sesiones abiertas"),
    ("il rollout è stato modificato negli ultimi 10 minuti",
     "the rollout was touched in the last 10 minutes",
     "el rollout se modificó en los últimos 10 minutos"),
    ("la trascrizione c'è, ma il rollout è fermo da più di 10 minuti",
     "the transcript exists, but the rollout has been idle for over 10 minutes",
     "la transcripción existe, pero el rollout lleva parado más de 10 minutos"),
    ("la trascrizione c'è, ma la sessione non risulta più aperta",
     "the transcript exists, but the session no longer looks open",
     "la transcripción existe, pero la sesión ya no parece abierta"),
]

# L3-RIPRENDI-UI-4 (obbligatoria del critico): `riprendi.apri()` scrive
# `esito["errore"]` in italiano fisso ("il lanciatore non ha risposto entro
# %ss"), e `riprendi_lancio_errore` lo incollava intatto dentro una frase
# inglese/spagnola ("I could not launch it: il lanciatore non ha risposto
# entro 0.3s."): stesso difetto che _tmot()/MOTIVI_PREFISSI chiudono per
# `motivo`, qui per `errore`. `plancia/riprendi.py` non è file di proprietà
# di questo lotto (solo un helper nuovo, vedi punto 10): la stringa resta
# quella, si traduce qui con lo stesso schema a prefisso.
ERRORI_PREFISSI = [
    ("il lanciatore non ha risposto entro ",
     "the launcher did not respond within ",
     "el lanzador no respondió en "),
]


def _terr(errore: str, lang: str) -> str:
    """Traduce `esito['errore']` (italiano fisso da riprendi.apri) per la voce."""
    if lang not in ("en", "es") or not errore:
        return errore or ""
    idx = 1 if lang == "en" else 2
    for prefissi in ERRORI_PREFISSI:
        it, trad = prefissi[0], prefissi[idx]
        if errore == it:
            return trad
        if errore.startswith(it):
            return trad + errore[len(it):]
    return errore


def _tmot(motivo: str, lang: str) -> str:
    """Traduce il `motivo` (italiano fisso da riprendi.stato) per la voce.

    Stessa idea di `Tmot()` in web/app.js, ma con anche lo spagnolo perché
    Jarvis risponde in tre lingue mentre la dashboard ne mostra solo due.
    """
    if lang not in ("en", "es") or not motivo:
        return motivo or ""
    idx = 1 if lang == "en" else 2
    for prefissi in MOTIVI_PREFISSI:
        it, trad = prefissi[0], prefissi[idx]
        if motivo == it:
            return trad
        if motivo.startswith(it):
            return trad + motivo[len(it):]
    return motivo


def _copia_appunti(testo: str) -> bool:
    """Metti `testo` negli appunti di sistema (stato "viva" di "riprendi il
    task N", LOTTO-L3-RIPRENDI-UI punto 4): la sessione è già aperta da
    qualche parte, non c'è niente da lanciare, ma il messaggio da incollarci
    dentro deve arrivare da qualche parte diversa dalla voce.

    `PLANCIA_CLIPBOARD`, quando c'è, sostituisce il comando di sistema: stessa
    idea di `PLANCIA_TERMINALE` in `riprendi.apri` (le prove non toccano mai gli
    appunti veri di chi le lancia). Il comando di sistema lo sceglie
    `piattaforma.comando_appunti`: `pbcopy` su macOS, `clip` su Windows,
    `wl-copy`, `xclip` o `xsel` su Linux. Silenzioso se fallisce (nessun
    comando per gli appunti, o in CI): chi ha chiesto "riprendi" ha comunque
    la risposta parlata, che dice il motivo a prescindere dagli appunti.
    """
    from . import piattaforma
    comando = piattaforma.comando_appunti()
    if not comando:
        return False
    try:
        # Consigliata del critico (L3-RIPRENDI-UI-4): `subprocess.run` senza
        # `check` tornava True anche quando il comando usciva con un codice
        # diverso da zero (pbcopy fallito, o lo script finto di una prova che
        # esce 1) - il punto 7 del lotto era soddisfatto alla lettera (la
        # voce non mente MAI se `_copia_appunti` torna False), non nello
        # spirito (qui tornava sempre True). Ora conta il codice di uscita.
        dati = piattaforma.input_appunti(testo, comando)
        res = piattaforma.esegui(comando, input=dati, text=isinstance(dati, str),
                                 capture_output=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False


def riconosci(testo: str):
    """(comando, argomento) se la frase è chiara, altrimenti (None, None)."""
    t = " ".join(testo.lower().strip().split())
    if not t:
        return None, None
    for comando, modelli in MODELLI.items():
        for m in modelli:
            trovato = re.match(m, t)
            if trovato:
                arg = trovato.group(1).strip() if trovato.groups() else ""
                return comando, arg
    return None, None


def _vista(arg: str):
    arg = (arg or "").strip().lower().rstrip("?.!")
    if arg in VISTE:
        return VISTE[arg]
    for chiave, vista in VISTE.items():
        if chiave in arg:
            return vista
    return None


# --------------------------------------------------------------------------
# la strada lunga: Claude con i tool aperti
# --------------------------------------------------------------------------

TOOL_CONSENTITI = [
    "mcp__plancia__plancia_briefing", "mcp__plancia__plancia_search",
    "mcp__plancia__plancia_projects", "mcp__plancia__plancia_project_update",
    "mcp__plancia__plancia_tasks", "mcp__plancia__plancia_task_add",
    "mcp__plancia__plancia_task_update", "mcp__plancia__plancia_posts",
    "mcp__plancia__plancia_post_add", "mcp__plancia__plancia_post_update",
    "mcp__plancia__plancia_sessions", "mcp__plancia__plancia_memory",
    "mcp__plancia__plancia_log", "mcp__plancia__plancia_recap",
]

PROMPT = """Sei l'assistente vocale di chi ti parla. Ti arriva una frase detta a voce,
trascritta, quindi può avere errori di trascrizione: interpretala con buon senso.

Hai i tool `plancia_*` sull'archivio di lavoro dell'utente: progetti, task, post,
sessioni passate di Claude Code e Codex, memoria. Usali davvero. Se ti chiede di
segnare, aggiornare o chiudere qualcosa, fallo e basta: è l'archivio
dell'utente, non serve chiedere il permesso. Se ti chiede un'informazione,
guardala nei tool invece di tirare a indovinare.

Rispondi in {lingua}, massimo {parole} parole, scritte per essere ascoltate:
niente elenchi, niente markdown, niente trattini lunghi, niente percorsi di file
o sigle lette a voce. Una o due frasi. Se hai fatto qualcosa, dillo in modo
diretto e corto.

Frase: {frase}"""


def chiedi_a_claude(frase: str, lang: str, parole=55) -> str:
    exe = recap.claude_bin()
    if not exe:
        return ""
    import os
    import subprocess
    from . import config, piattaforma
    prompt = PROMPT.format(lingua=recap.NOMI_LINGUA.get(lang, "English"),
                           parole=parole, frase=frase)
    cmd = [exe, "-p", "--model", config.load_config().get("modello_voce", "sonnet"),
           "--allowedTools"] + TOOL_CONSENTITI
    try:
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                             timeout=180, cwd=str(config.DATA_DIR), env=dict(os.environ),
                             **piattaforma.opzioni_figlio(), **piattaforma.opzioni_utf8())
    except Exception:
        return ""
    return (res.stdout or "").strip() if res.returncode == 0 else ""


def _risposta_lancio(esito, d, cosa, chi, con_task, esegui) -> dict:
    """La frase e l'azione per un lancio di proposta (LOTTO 21-RIPRENDI): dice
    a voce se riprende la sessione originale, se ne parte una nuova o se non
    parte niente perche' la sessione e' aperta."""
    piano = esito.get("piano") or {}
    if not esito.get("lanciato"):
        # sessione aperta, nessuna copia chiesta: niente da lanciare, e il
        # messaggio (se c'e' un task) va negli appunti, come "riprendi il task"
        if esito.get("messaggio"):
            copiato = _copia_appunti(esito["messaggio"])
            chiave = "riprendi_viva" if copiato else "riprendi_viva_senza_copia"
        else:
            chiave = "sessione_aperta"
        return {"tipo": "riprendi", "risposta": d[chiave],
                "azione": {"tipo": "vai", "vista": "task"}}
    chiave = "mandato_esegui" if esegui else "mandato"
    frase = d[chiave].format(chi=chi, cosa=cosa)
    if piano.get("modo") == "riprendi":
        frase += " " + d["mandato_stessa"]
    elif piano.get("modo") == "nuova" and (con_task or piano.get("origine")):
        frase += " " + d["mandato_nuova"]
    return {"tipo": "cantiere", "risposta": frase,
            "azione": {"tipo": "vai", "vista": "oggi"}, "run": esito["run"]}


def _esegui_proposta(conn, scelta, d, lang, forza_esecuzione=False, lett=None,
                     tag="") -> dict:
    """Trasforma una proposta in un fatto.

    Con i compartimenti (vedi compartimenti_viste.py) `lett` e' la connessione
    con le viste (da cui si legge il lancio o il task a cui la proposta punta) e
    `tag` il compartimento a cui appartiene il lancio che ne esce.

    Il modo resta quello scritto nella proposta, cioè proposta, a meno che tu
    non abbia detto esplicitamente di eseguire. Una frase come "fallo" non deve
    mai finire per modificare file da sola.
    """
    lett = lett or conn
    a = scelta.get("azione") or {}
    tipo = a.get("tipo")

    if tipo == "vai":
        return {"tipo": "vai", "risposta": d["vai"].format(vista=a.get("vista", "")),
                "azione": {"tipo": "vai", "vista": a.get("vista", "oggi")}}

    if tipo == "rilancia":
        # LOTTO 21-RIPRENDI: un lancio fallito si rilancia NELLA conversazione
        # in cui era girato (o in quella del suo task), non in una nuova
        esito = riprendi.rilancia_run(
            conn, a.get("run"), scrive=(True if forza_esecuzione else None),
            lingua=lang, compartimento=tag, lett=lett)
        if esito is None:
            return {"tipo": "proposta", "risposta": d["niente_proposte"]}
        r = lett.execute("SELECT agente FROM runs WHERE id=?", (a.get("run"),)).fetchone()
        return _risposta_lancio(esito, d, scelta["testo"][:60],
                                r["agente"] if r else "claude", False, forza_esecuzione)

    if tipo == "manda":
        modo = "esegui" if forza_esecuzione else a.get("modo", "proposta")
        agente_scelto = a.get("agente", "claude")
        # Le proposte di tipo "manda" con un task_id sono lo stesso "Riprendi"
        # del drawer (LOTTO-L3-RIPRENDI-UI punto 2: "le proposte di tipo manda
        # passano dallo stesso endpoint"): `riprendi.lancia` guarda la sessione
        # del task e decide (chiusa = la stessa sessione, viva = niente da
        # lanciare, persa = nuova), come api.py, cli.py e mcp.py.
        tid = a.get("task_id")
        task = actions.task_get(lett, tid) if tid else None
        if task and task.get("agent"):
            agente_scelto = task["agent"]
        esito = riprendi.lancia(
            conn, a.get("titolo", scelta["testo"])[:200],
            progetto=a.get("progetto"), agente=agente_scelto,
            scrive=(modo == "esegui"), task_id=tid, task=task, lingua=lang,
            sessione=a.get("sessione") or None, compartimento=tag, lett=lett)
        return _risposta_lancio(esito, d, a.get("titolo", "")[:70], agente_scelto,
                                bool(tid), modo == "esegui")

    return {"tipo": "proposta", "risposta": d["fatto_proposta"]}


# --------------------------------------------------------------------------
# ingresso unico
# --------------------------------------------------------------------------

def esegui(testo: str, lang=None, conn=None, vista=None) -> dict:
    """Esegue una frase. Con `vista` (una `compartimenti_viste.Vista`: la
    dashboard nel suo compartimento, il comando da terminale di una sessione)
    si legge solo da lei, si scrive solo su oggetti che vede e quello che parte
    e' del suo compartimento; senza compartimenti la vista e' la connessione di
    sempre. `conn` resta per chi la passa gia' (le prove)."""
    esito = _esegui(testo, lang, conn, vista)
    # L'ultima cosa detta si tiene da parte qui e non nella rotta HTTP: da
    # terminale, dall'app e da MCP "ripeti" deve rispondere alla stessa cosa.
    # Con i compartimenti sta nella `meta` della vista: ognuno ripete la sua.
    try:
        if esito.get("risposta") and not esito.get("ripetuta"):
            c = vista.lettura if vista is not None else (conn or store.connect())
            store.set_meta(c, "ultima_risposta", esito["risposta"])
            c.commit()
            if vista is None and conn is None:
                c.close()
    except Exception:
        pass
    return esito


def _esegui(testo: str, lang=None, conn=None, vista=None) -> dict:
    lang = recap.lang_or_default(lang)
    d = _dizionario(lang)
    chiudi = False
    if vista is not None:
        conn = vista.conn
        if vista.incerta:
            return {"tipo": "claude", "risposta": d["non_capito"], "via": "compartimento"}
    elif conn is None:
        conn = store.connect()
        store.init_db(conn)
        chiudi = True
    # `lett`: da dove si LEGGE (le viste del compartimento, se ci sono); `conn`:
    # dove si scrive, solo dopo aver visto che l'oggetto e' leggibile da `lett`
    lett = vista.lettura if vista is not None else conn
    tag = vista.tag if vista is not None else ""
    try:
        comando, arg = riconosci(testo)

        if comando == "ripeti":
            ultima = store.get_meta(lett, "ultima_risposta") or ""
            if not ultima:
                return {"tipo": "ripeti", "risposta": d["niente_da_ripetere"], "via": "comando"}
            # Si rimanda lo stesso testo: chi non ha sentito vuole quello, non
            # una riformulazione che lo confonde ancora di più.
            return {"tipo": "ripeti", "risposta": ultima, "via": "comando", "ripetuta": True}

        if comando == "velocita":
            giu = bool(re.search(r"piano|lent|slow|despacio", testo, re.I))
            passo = -0.06 if giu else 0.06
            return {"tipo": "velocita",
                    "risposta": d["piu_piano"] if giu else d["piu_veloce"],
                    "azione": {"tipo": "velocita", "passo": passo}, "via": "comando"}

        if comando == "annulla":
            from . import cantiere
            attivi = [r for r in cantiere.elenco(lett, limite=5)
                      if r["stato"] in ("in coda", "in corso")]
            if not attivi:
                return {"tipo": "annulla", "risposta": d["niente_da_fermare"], "via": "comando"}
            for r in attivi:
                cantiere.annulla(conn, r["id"])
            return {"tipo": "annulla",
                    "risposta": d["fermato"].format(n=len(attivi)), "via": "comando"}

        if comando == "ferma":
            return {"tipo": "ferma", "risposta": d["ferma"], "azione": {"tipo": "ferma"},
                    "muto": True}

        if comando == "vai":
            vista = _vista(arg)
            if vista:
                return {"tipo": "vai", "risposta": d["vai"].format(vista=arg),
                        "azione": {"tipo": "vai", "vista": vista}}
            # "apri" seguito da altro non è una vista: probabilmente è un progetto
            riga = store.get_project(lett, arg)
            if riga:
                return {"tipo": "vai", "risposta": d["vai"].format(vista=riga["name"]),
                        "azione": {"tipo": "progetto", "chiave": riga["key"]}}

        if comando == "riprendi_task" and arg:
            from . import riprendi as _riprendi
            try:
                tid = int(arg)
            except ValueError:
                tid = None
            task = actions.task_get(lett, tid) if tid is not None else None
            if not task:
                return {"tipo": "riprendi", "risposta": d["riprendi_non_trovato"].format(id=arg)}
            s = _riprendi.stato(lett, task)
            if s["stato"] == "viva":
                # LOTTO-L3-RITOCCO punto 7: prima si diceva sempre "l'ho
                # copiato negli appunti", anche quando `_copia_appunti`
                # tornava False (nessun `pbcopy`, o il finto sostituto della
                # prova assente/rotto): la voce mentiva su una cosa che non
                # era successa.
                copiato = _copia_appunti(_riprendi.messaggio(task))
                chiave = "riprendi_viva" if copiato else "riprendi_viva_senza_copia"
                return {"tipo": "riprendi", "risposta": d[chiave],
                        "azione": {"tipo": "vai", "vista": "task"}}
            # chiusa o persa: in entrambi i casi c'è qualcosa da lanciare
            # (apri() lo sa già distinguere, vedi plancia/riprendi.py). Se il
            # lanciatore va in timeout (`apri()` lo segnala in `errore`), la
            # voce lo dice invece di rispondere come se fosse partito.
            esito = _riprendi.apri(task, conn)
            if esito.get("errore"):
                return {"tipo": "riprendi",
                        "risposta": d["riprendi_lancio_errore"].format(
                            errore=_terr(esito["errore"], lang)),
                        "azione": {"tipo": "vai", "vista": "task"}}
            chiave = "riprendi_chiusa" if s["stato"] == "chiusa" else "riprendi_persa"
            return {"tipo": "riprendi",
                    "risposta": d[chiave].format(motivo=_tmot(s["motivo"], lang)),
                    "azione": {"tipo": "vai", "vista": "task"}}

        if comando in ("fallo", "eseguilo"):
            scelta = proposte.scegli(lett, arg or None, lang)
            if not scelta:
                return {"tipo": "proposta", "risposta": d["niente_proposte"]}
            return _esegui_proposta(conn, scelta, d, lang,
                                    forza_esecuzione=(comando == "eseguilo"),
                                    lett=lett, tag=tag)

        if comando in ("archivia", "riapri_progetto") and arg:
            riga = store.get_project(lett, arg)
            if not riga:
                return {"tipo": "progetto",
                        "risposta": d["progetto_non_trovato"].format(nome=arg)}
            nuovo = "archiviato" if comando == "archivia" else "attivo"
            actions.project_update(conn, riga["key"], status=nuovo)
            chiave = "archiviato" if nuovo == "archiviato" else "riaperto"
            return {"tipo": "progetto", "risposta": d[chiave].format(nome=riga["name"]),
                    "azione": {"tipo": "vai", "vista": "progetti"}}

        if comando == "aggiorna":
            # LOTTO-L3-RITOCCO punto 4: con `plancia serve --no-sync` nessun
            # sync parte da solo (vedi api.py:serve), quindi "rileggo le
            # fonti" sarebbe una promessa vuota. Import locale di `api`
            # (invece che in testa al file) perché `api.py` importa già
            # `jarvis`: un import in cima creerebbe un ciclo.
            from . import api as _api
            if getattr(_api, "_NO_SYNC_ATTIVO", False):
                return {"tipo": "aggiorna", "risposta": d["aggiorna_no_sync"],
                        "azione": {"tipo": "aggiorna", "avviato": False}}
            return {"tipo": "aggiorna", "risposta": d["aggiorna"],
                    "azione": {"tipo": "aggiorna"}}

        if comando == "riepilogo":
            dati = recap.build(lett, lang=lang)
            return {"tipo": "riepilogo", "risposta": dati["testo"],
                    "azione": {"tipo": "vai", "vista": "riepilogo"}, "lungo": True}

        if comando == "task_add" and arg and len(arg) > 2:
            task = actions.task_add(conn, arg[:200], source="jarvis", compartimento=tag)
            return {"tipo": "task", "risposta": d["task_add"].format(titolo=task["title"]),
                    "azione": {"tipo": "vai", "vista": "task"}}

        if comando == "task_done":
            aperti = actions.tasks_list(lett, "aperti", limit=30)
            if not aperti:
                return {"tipo": "task", "risposta": d["nessun_task"]}
            scelto = None
            if arg:
                parole = [p for p in re.findall(r"\w{4,}", arg.lower())]
                migliore, punteggio = None, 0
                for t in aperti:
                    titolo = t["title"].lower()
                    n = sum(1 for p in parole if p in titolo)
                    if n > punteggio:
                        migliore, punteggio = t, n
                scelto = migliore
            else:
                scelto = aperti[0]
            if not scelto:
                return {"tipo": "task",
                        "risposta": d["task_non_trovato"].format(titolo=arg)}
            actions.task_update(conn, scelto["id"], status="fatto")
            return {"tipo": "task", "risposta": d["task_done"].format(titolo=scelto["title"]),
                    "azione": {"tipo": "vai", "vista": "task"}}

        # Prima di scomodare un modello: la domanda è una di quelle che i dati
        # sanno già? Costa zero e risponde in un decimo di secondo.
        locale = risposte.prova(lett, testo, lang)
        if locale:
            return {"tipo": "dati", "risposta": locale}

        if vista is not None and vista.nominato:
            # Il modello con i tool `plancia_*` (il processo caldo, o quello a
            # freddo) parte da una cartella di Plancia e vedrebbe il compartimento
            # del predefinito, e il processo caldo tiene il filo del discorso fra
            # una frase e l'altra: da un compartimento nominato si risponde
            # invece con i soli dati della sua vista nel prompt, senza tool e
            # senza memoria di chi ha parlato prima.
            risposta = recap.answer(
                testo, lang, lett,
                schede=lambda q: compartimenti_viste.cerca_schede(lett, vista.ombra, q, 8))
            return {"tipo": "claude", "risposta": risposta or d["non_capito"]}
        risposta = agente.chiedi(testo, lang)
        if not risposta:
            # il processo caldo non è partito: si ripiega su quello a freddo
            risposta = chiedi_a_claude(testo, lang)
        return {"tipo": "claude", "risposta": risposta or d["non_capito"]}
    finally:
        if chiudi:
            conn.close()
