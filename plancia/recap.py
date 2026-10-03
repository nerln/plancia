"""Il riepilogo giornaliero: cosa è successo oggi, detto come lo diresti a voce.

Due strade per il testo. Quella a modelli è deterministica, non costa niente e
funziona sempre. Quella con Claude prende gli stessi dati e li racconta meglio.
Se la seconda non risponde entro il tempo previsto, si usa la prima.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

from . import config, piattaforma, proposte, store
from .voce_testo import per_voce

SOSTANZA = ("AND ((SELECT COUNT(*) FROM sessions s WHERE s.project_id=p.id) >= 3 OR p.id IN (SELECT project_id FROM project_links WHERE kind IN ('repo','memory')))")

LANGS = ["it", "en", "es", "fr", "de", "pt"]
DEFAULT_LANG = "it"


def lang_or_default(lang=None) -> str:
    lang = (lang or config.load_config().get("lingua") or DEFAULT_LANG).lower()[:2]
    return lang if lang in LANGS else DEFAULT_LANG


# --------------------------------------------------------------------------
# raccolta dati
# --------------------------------------------------------------------------

def _bounds(day: str = None):
    """Estremi UTC della giornata locale: il database è in UTC, la giornata no."""
    local = datetime.now().astimezone()
    if day:
        base = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=local.tzinfo)
    else:
        base = local
    start = base.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (start.astimezone(timezone.utc).strftime(fmt),
            end.astimezone(timezone.utc).strftime(fmt),
            start.strftime("%Y-%m-%d"))


def collect(conn, day: str = None) -> dict:
    start, end, label = _bounds(day)
    prev_start = (datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ") - timedelta(days=1)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = lambda sql, p=(): [dict(r) for r in conn.execute(sql, p).fetchall()]
    one = lambda sql, p=(): conn.execute(sql, p).fetchone()[0]

    sessioni = rows(
        "SELECT s.session_id, s.title, substr(s.first_prompt,1,240) AS prompt, "
        "s.started_at, s.n_user, s.n_tools, s.out_tokens, p.name AS progetto, p.key AS chiave, "
        "par.name AS area "
        "FROM sessions s LEFT JOIN projects p ON p.id=s.project_id "
        "LEFT JOIN projects par ON par.id = p.parent_id "
        f"WHERE s.started_at >= ? AND s.started_at < ? AND {store.visibile()} "
        "ORDER BY s.out_tokens DESC",
        (start, end))
    commit = rows(
        "SELECT repo, message, date FROM commits WHERE date >= ? AND date < ? "
        "ORDER BY date DESC", (start, end))
    task_chiusi = rows(
        "SELECT t.id, t.title, p.name AS progetto FROM tasks t "
        "LEFT JOIN projects p ON p.id=t.project_id "
        "WHERE t.done_at >= ? AND t.done_at < ?", (start, end))
    task_creati = rows(
        "SELECT t.id, t.title, p.name AS progetto FROM tasks t "
        "LEFT JOIN projects p ON p.id=t.project_id "
        "WHERE t.created_at >= ? AND t.created_at < ? AND t.status <> 'fatto'", (start, end))
    task_aperti = rows(
        "SELECT t.id, t.title, t.priority, t.due, p.name AS progetto, par.name AS area "
        "FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
        "LEFT JOIN projects par ON par.id = p.parent_id "
        "WHERE t.status IN ('aperto','in corso','bloccato') "
        "ORDER BY t.priority ASC, t.due IS NULL, t.due ASC LIMIT 8")
    scaduti = [t for t in task_aperti if t["due"] and t["due"] < label]
    # L'elenco ha un tetto di otto righe: i numeri detti a voce sono su tutti i task aperti, non sulle otto
    tot_aperti = rows("SELECT COUNT(*) AS n FROM tasks WHERE status IN ('aperto','in corso','bloccato')")
    tot_scaduti = rows("SELECT COUNT(*) AS n FROM tasks WHERE status IN ('aperto','in corso','bloccato') "
                       "AND due IS NOT NULL AND due <> '' AND due < ?", (label,))
    n_aperti = tot_aperti[0]["n"] if tot_aperti else len(task_aperti)
    n_scaduti = tot_scaduti[0]["n"] if tot_scaduti else len(scaduti)
    post_pubblicati = rows(
        "SELECT id, platform, substr(text,1,120) AS text, url FROM posts "
        "WHERE published_at >= ? AND published_at < ?", (start, end))
    post_coda = rows(
        "SELECT id, platform, status, substr(text,1,120) AS text FROM posts "
        "WHERE status IN ('idea','bozza','approvato','programmato') LIMIT 5")
    prossimi = rows(
        "SELECT p.name, p.key, p.next_action, p.last_activity, par.name AS area "
        "FROM projects p LEFT JOIN projects par ON par.id = p.parent_id "
        "WHERE p.status='attivo' AND p.hidden=0 AND p.next_action <> '' "
        "ORDER BY p.priority ASC, p.last_activity DESC LIMIT 5")
    fermi = rows(
        "SELECT p.name, p.key, p.last_activity, par.name AS area FROM projects p "
        "LEFT JOIN projects par ON par.id = p.parent_id "
        "WHERE p.status='attivo' "
        "AND p.hidden=0 AND p.last_activity IS NOT NULL AND p.last_activity < ? "
        + SOSTANZA + " ORDER BY p.last_activity ASC LIMIT 3",
        ((datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ"),))

    per_progetto = {}
    for s in sessioni:
        key = s["progetto"] or "senza progetto"
        voce = per_progetto.setdefault(key, {"progetto": key, "area": s.get("area"),
                                             "sessioni": 0, "token": 0, "titoli": []})
        voce["sessioni"] += 1
        voce["token"] += s["out_tokens"] or 0
        if s["title"]:
            voce["titoli"].append(s["title"])
    for c in commit:
        row = conn.execute(
            "SELECT p.name, par.name AS area FROM repos r JOIN projects p ON p.id=r.project_id "
            "LEFT JOIN projects par ON par.id = p.parent_id WHERE r.name=?",
            (c["repo"],)).fetchone()
        key = row["name"] if row else c["repo"]
        voce = per_progetto.setdefault(
            key, {"progetto": key, "area": (row["area"] if row else None),
                  "sessioni": 0, "token": 0, "titoli": []})
        voce.setdefault("commit", 0)
        voce["commit"] = voce.get("commit", 0) + 1

    return {
        "giorno": label,
        "sessioni": sessioni,
        "sessioni_ieri": one(f"SELECT COUNT(*) FROM sessions s WHERE started_at >= ? "
                             f"AND started_at < ? AND {store.visibile()}", (prev_start, start)),
        "commit": commit,
        "per_progetto": sorted(per_progetto.values(),
                               key=lambda v: (-v["token"], -v["sessioni"])),
        "task_chiusi": task_chiusi,
        "task_creati": task_creati,
        "task_aperti": task_aperti,
        "task_scaduti": scaduti,
        "task_aperti_totale": n_aperti,
        "task_scaduti_totale": n_scaduti,
        "post_pubblicati": post_pubblicati,
        "post_coda": post_coda,
        "prossimi_passi": prossimi,
        "progetti_fermi": fermi,
        "token_giorno": sum(s["out_tokens"] or 0 for s in sessioni),
    }


# --------------------------------------------------------------------------
# testo a modelli, senza modello linguistico
# --------------------------------------------------------------------------

P = {
    "it": {
        "apertura_vuota": "Oggi non risulta ancora niente. Nessuna sessione, nessun commit.",
        "apertura": "{n_sess} e {n_commit} oggi.",
        "sessione": "una sessione", "sessioni": "{n} sessioni",
        "commit_1": "un commit", "commit_n": "{n} commit", "commit_0": "nessun commit",
        "su_progetti": "Hai lavorato su {elenco}.",
        "piu_lungo": "La più lunga è stata {titolo}.",
        "confronto_su": "Ieri erano {n}, quindi oggi hai spinto di più.",
        "confronto_giu": "Ieri erano {n}.",
        "task_chiusi": "Hai chiuso {n}: {elenco}.",
        "task_uno": "un task", "task_n": "{n} task",
        "task_aperti": "Restano aperti {n} task, il primo è {titolo}.",
        "task_aperti_1": "Resta un task aperto: {titolo}.",
        "scaduti": "Attenzione, {n} in ritardo.",
        "post": "Sul fronte social, {n} pubblicati e {q} in coda.",
        "prossimi": "Per domani: {elenco}.",
        "fermi": "Fermo da un po': {elenco}.",
        "chiusura": "Vuoi che approfondisca qualcosa?",
        "buongiorno": "Buongiorno.", "buonasera": "Buonasera.", "buonpomeriggio": "Buon pomeriggio.",
        "e": " e ",
    },
    "en": {
        "apertura_vuota": "Nothing logged today yet. No sessions, no commits.",
        "apertura": "{n_sess} and {n_commit} today.",
        "sessione": "one session", "sessioni": "{n} sessions",
        "commit_1": "one commit", "commit_n": "{n} commits", "commit_0": "no commits",
        "su_progetti": "You worked on {elenco}.",
        "piu_lungo": "The longest one was {titolo}.",
        "confronto_su": "Yesterday it was {n}, so today you pushed harder.",
        "confronto_giu": "Yesterday it was {n}.",
        "task_chiusi": "You closed {n}: {elenco}.",
        "task_uno": "one task", "task_n": "{n} tasks",
        "task_aperti": "{n} tasks are still open, first up is {titolo}.",
        "task_aperti_1": "One task is still open: {titolo}.",
        "scaduti": "Careful, {n} are overdue.",
        "post": "On social, {n} published and {q} in the queue.",
        "prossimi": "For tomorrow: {elenco}.",
        "fermi": "Untouched for a while: {elenco}.",
        "chiusura": "Want me to dig into any of it?",
        "buongiorno": "Good morning.", "buonasera": "Good evening.", "buonpomeriggio": "Good afternoon.",
        "e": " and ",
    },
    "es": {
        "apertura_vuota": "Hoy todavía no hay nada. Ninguna sesión, ningún commit.",
        "apertura": "{n_sess} y {n_commit} hoy.",
        "sessione": "una sesión", "sessioni": "{n} sesiones",
        "commit_1": "un commit", "commit_n": "{n} commits", "commit_0": "ningún commit",
        "su_progetti": "Has trabajado en {elenco}.",
        "piu_lungo": "La más larga fue {titolo}.",
        "confronto_su": "Ayer fueron {n}, así que hoy has ido más fuerte.",
        "confronto_giu": "Ayer fueron {n}.",
        "task_chiusi": "Has cerrado {n}: {elenco}.",
        "task_uno": "una tarea", "task_n": "{n} tareas",
        "task_aperti": "Quedan {n} tareas abiertas, la primera es {titolo}.",
        "task_aperti_1": "Queda una tarea abierta: {titolo}.",
        "scaduti": "Ojo, {n} van con retraso.",
        "post": "En social, {n} publicados y {q} en cola.",
        "prossimi": "Para mañana: {elenco}.",
        "fermi": "Parado desde hace tiempo: {elenco}.",
        "chiusura": "¿Quieres que entre en detalle en algo?",
        "buongiorno": "Buenos días.", "buonasera": "Buenas noches.", "buonpomeriggio": "Buenas tardes.",
        "e": " y ",
    },
}
P["fr"] = P["en"]
P["de"] = P["en"]
P["pt"] = P["es"]


def _prima_frase(testo: str, massimo: int = 130) -> str:
    """Il prossimo passo detto a voce: una frase, non un paragrafo.

    Un `next_action` può essere lungo quanto vuole, ed è giusto che lo sia:
    dentro ci sta il ragionamento. Ma letto ad alta voce in mezzo al riepilogo
    diventa un muro, e chi ascolta perde il filo di tutto il resto.
    """
    testo = " ".join((testo or "").split())
    if len(testo) <= massimo:
        return testo
    taglio = testo[:massimo]
    for segno in (". ", "; ", ": ", ", "):
        i = taglio.rfind(segno)
        if i > massimo // 3:
            return taglio[:i].rstrip(" ,;:")
    return taglio.rsplit(" ", 1)[0]


def _con_area(nome: str, area) -> str:
    """"<progetto> (<area>)" quando c'è un'area, il nome da solo altrimenti.

    Una funzione sola per il testo a modelli e per quello che finisce nel
    JSON mandato a Claude (`_compact`): l'area compare nello stesso formato
    in entrambe le strade, non solo in quella che si legge per prima.
    """
    return f"{nome} ({area})" if area else nome


def _elenco(items, lang) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + P[lang]["e"] + items[-1]


def _saluto(lang) -> str:
    ora = datetime.now().hour
    key = "buongiorno" if ora < 13 else ("buonpomeriggio" if ora < 19 else "buonasera")
    return P[lang][key]


def render_template(dati: dict, lang: str) -> str:
    t = P[lang]
    frasi = [_saluto(lang)]
    n_sess, n_commit = len(dati["sessioni"]), len(dati["commit"])

    if not n_sess and not n_commit:
        frasi.append(t["apertura_vuota"])
    else:
        sess = t["sessione"] if n_sess == 1 else t["sessioni"].format(n=n_sess)
        com = (t["commit_0"] if n_commit == 0 else
               t["commit_1"] if n_commit == 1 else t["commit_n"].format(n=n_commit))
        frasi.append(t["apertura"].format(n_sess=sess, n_commit=com).capitalize())
        nomi = [_con_area(v["progetto"], v.get("area")) for v in dati["per_progetto"][:3]]
        if nomi:
            frasi.append(t["su_progetti"].format(elenco=_elenco(nomi, lang)))
        if dati["sessioni"] and dati["sessioni"][0].get("title"):
            frasi.append(t["piu_lungo"].format(titolo=dati["sessioni"][0]["title"]))
        ieri = dati["sessioni_ieri"]
        if ieri:
            frasi.append((t["confronto_su"] if n_sess > ieri else t["confronto_giu"]).format(n=ieri))

    if dati["task_chiusi"]:
        n = len(dati["task_chiusi"])
        quanti = t["task_uno"] if n == 1 else t["task_n"].format(n=n)
        frasi.append(t["task_chiusi"].format(
            n=quanti, elenco=_elenco([x["title"] for x in dati["task_chiusi"][:3]], lang)))
    if dati["task_aperti"]:
        n = dati.get("task_aperti_totale") or len(dati["task_aperti"])
        chiave = "task_aperti_1" if n == 1 else "task_aperti"
        frasi.append(t[chiave].format(n=n, titolo=dati["task_aperti"][0]["title"]))
    if dati["task_scaduti"]:
        frasi.append(t["scaduti"].format(n=dati.get("task_scaduti_totale") or len(dati["task_scaduti"])))
    if dati["post_pubblicati"] or dati["post_coda"]:
        frasi.append(t["post"].format(n=len(dati["post_pubblicati"]), q=len(dati["post_coda"])))
    if dati["prossimi_passi"]:
        frasi.append(t["prossimi"].format(elenco=_elenco(
            [f"{_con_area(p['name'], p.get('area'))}, {_prima_frase(p['next_action'])}"
             for p in dati["prossimi_passi"][:2]], lang)))
    if dati["progetti_fermi"]:
        frasi.append(t["fermi"].format(elenco=_elenco(
            [_con_area(p["name"], p.get("area")) for p in dati["progetti_fermi"]], lang)))
    prop = dati.get("proposte") or []
    frasi.append(prop[0]["testo"] if prop else t["chiusura"])
    return " ".join(f for f in frasi if f)


# --------------------------------------------------------------------------
# testo raccontato da Claude
# --------------------------------------------------------------------------

NOMI_LINGUA = {"it": "italiano", "en": "English", "es": "español", "fr": "français",
               "de": "Deutsch", "pt": "português"}

PROMPT = """Sei l'assistente vocale personale di chi legge. Ricevi i dati reali della
giornata di lavoro con l'IA dell'utente, in JSON.

Scrivi il briefing che leggerai all'utente ad alta voce, in {lingua}, massimo {parole} parole.

Regole:
- si ascolta, non si legge: niente elenchi puntati, niente titoli, niente markdown,
  niente trattini lunghi, niente sigle o percorsi di file letti a voce
- parla di quello che è successo davvero, non aggiungere niente che non sia nei dati
- concreto: nomi dei progetti, cosa è cambiato, cosa resta aperto
- se non è successo quasi niente, dillo in una riga e non riempire
- in `cosa_converrebbe_fare` ci sono le proposte già calcolate dai dati: chiudi
  con la prima, detta con parole tue, e falla diventare una domanda secca a cui
  si possa rispondere "fallo". Se l'elenco è vuoto, chiudi con la cosa più
  sensata da riprendere

Dati:
{dati}"""

DOMANDA = """Sei l'assistente personale di chi ti parla. Rispondi in {lingua}, a voce,
massimo {parole} parole. Niente markdown, niente elenchi, niente trattini lunghi.
Rispondi solo con quello che risulta dai dati; se il dato non c'è, dillo.

Contesto del lavoro dell'utente:
{contesto}

Domanda: {domanda}"""


def claude_bin() -> str:
    """Il comando `claude`.

    Sotto launchd il PATH non è quello della shell, quindi cercarlo solo con
    which non basta: senza questo il riepilogo ripiega sempre sul testo a
    modelli e non si capisce perché.
    """
    cfg = config.load_config()
    candidati = [cfg.get("claude_bin"), shutil.which("claude"),
                 str(config.HOME / ".local/bin/claude"),
                 "/usr/local/bin/claude", "/opt/homebrew/bin/claude",
                 str(config.HOME / ".claude/local/claude")]
    for c in candidati:
        if c and os.access(c, os.X_OK):
            return c
    return ""


def claude_text(prompt: str, timeout: int = 120) -> str:
    """Una domanda secca a Claude Code in modalità non interattiva.

    Su macOS e Linux il prompt è un argomento (`claude -p --model <m> <prompt>`), come
    sempre. Su Windows va nello stdin (`piattaforma.prompt_da_stdin`): un `claude.cmd` di
    npm passa da cmd.exe, che taglia l'argomento alla prima riga a capo (e può interpretare
    `%` e, con delle virgolette nel testo, anche `&` e `|`); il riepilogo e la risposta a
    voce sono prompt su più righe."""
    cfg = config.load_config()
    exe = claude_bin()
    if not exe:
        return ""
    da_stdin = piattaforma.prompt_da_stdin()
    cmd = [exe, "-p"] if da_stdin else [exe, "-p", prompt]
    model = cfg.get("modello_voce") or "sonnet"
    if model:
        cmd[2:2] = ["--model", model]
    env = dict(os.environ)
    env.setdefault("CLAUDE_CODE_DISABLE_TERMINAL_TITLE", "1")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                             cwd=str(config.DATA_DIR), env=env,
                             **({"input": prompt} if da_stdin else {}),
                             **piattaforma.opzioni_figlio(), **piattaforma.opzioni_utf8())
    except Exception:
        return ""
    if res.returncode != 0:
        return ""
    return (res.stdout or "").strip()


def _compact(dati: dict) -> dict:
    """Solo quello che serve a raccontare, niente id e niente rumore.

    I nomi di progetto qui dentro portano già l'area quando c'è
    ("<progetto> (<area>)"), con `_con_area`: è la stessa stringa che finisce
    nel testo a modelli, così il formato non dipende dal fatto che Claude
    segua un'istruzione per nominarla allo stesso modo.
    """
    return {
        "giorno": dati["giorno"],
        "sessioni_oggi": len(dati["sessioni"]),
        "sessioni_ieri": dati["sessioni_ieri"],
        "token_generati": dati["token_giorno"],
        "lavoro_per_progetto": [
            {k: v for k, v in p.items() if k not in ("titoli", "area", "progetto")}
            | {"progetto": _con_area(p["progetto"], p.get("area")), "titoli": p["titoli"][:3]}
            for p in dati["per_progetto"][:5]],
        "commit": [{"repo": c["repo"], "messaggio": c["message"]} for c in dati["commit"][:8]],
        "task_chiusi": [t["title"] for t in dati["task_chiusi"]],
        "task_creati": [t["title"] for t in dati["task_creati"]],
        "task_aperti": [{"titolo": t["title"], "progetto": _con_area(t["progetto"], t.get("area")),
                         "scadenza": t["due"]}
                        for t in dati["task_aperti"][:6]],
        "task_in_ritardo": [t["title"] for t in dati["task_scaduti"]],
        "post_pubblicati": [p["text"] for p in dati["post_pubblicati"]],
        "post_in_coda": len(dati["post_coda"]),
        "prossimi_passi": [{"progetto": _con_area(p["name"], p.get("area")),
                            "passo": _prima_frase(p["next_action"], 200)}
                           for p in dati["prossimi_passi"]],
        "progetti_fermi": [_con_area(p["name"], p.get("area")) for p in dati["progetti_fermi"]],
        "cosa_converrebbe_fare": [p["testo"] for p in dati.get("proposte", [])],
    }


def impronta(conn, giorno: str) -> str:
    """Una firma corta di com'è messa la giornata.

    Se non è cambiata, il riepilogo di prima vale ancora e non serve
    rigenerarlo: sono otto secondi e una chiamata a un modello risparmiati ogni
    volta che lo richiedi.
    """
    r = conn.execute(
        "SELECT (SELECT COUNT(*) FROM sessions WHERE substr(started_at,1,10)=?) "
        "|| '-' || (SELECT COUNT(*) FROM commits WHERE substr(date,1,10)=?) "
        "|| '-' || (SELECT COALESCE(MAX(updated_at),'') FROM tasks) "
        "|| '-' || (SELECT COUNT(*) FROM tasks WHERE status IN ('aperto','in corso','bloccato')) "
        "|| '-' || (SELECT COALESCE(MAX(updated_at),'') FROM posts)",
        (giorno, giorno)).fetchone()[0]
    return str(r)


def solo_cache(conn, lang=None) -> dict:
    """Il riepilogo già pronto, o niente. Non genera: serve a dipingere subito
    la pagina senza aspettare un modello."""
    lang = lang_or_default(lang)
    giorno = _bounds()[2]
    firma = impronta(conn, giorno)
    fresco = store.get_meta(conn, "recap_impronta") == f"{firma}|{lang}|{giorno}"
    testo = store.get_meta(conn, "recap_testo")
    # In cache ci sta un riepilogo solo. Se è di un'altra lingua non lo si
    # mostra: leggere l'italiano dentro un'interfaccia inglese confonde più di
    # quanto aiuti aspettare.
    if testo and store.get_meta(conn, "recap_lingua", lang) != lang:
        testo, fresco = None, False
    # Anche quando la giornata è cambiata si restituisce l'ultimo testo: meglio
    # un riepilogo di venti minuti fa, subito, che un riquadro vuoto per dieci
    # secondi. Chi chiama lo aggiorna in sottofondo.
    return {"giorno": giorno, "lingua": lang, "testo": testo if testo else None,
            "fonte": store.get_meta(conn, "recap_fonte", "cache"),
            "fresco": bool(fresco and testo), "da_cache": True}


def prepara(lang=None, min_minuti=20) -> bool:
    """Rigenera il riepilogo se è vecchio o se la giornata è cambiata.

    Si chiama alla fine del giro freddo: così quando lo chiedi, a voce o a
    schermo, c'è già e non aspetti otto secondi.
    """
    from datetime import datetime as _dt
    conn = store.connect()
    store.init_db(conn)
    try:
        lang = lang_or_default(lang)
        pronto = solo_cache(conn, lang)
        if pronto["testo"]:
            return False
        ultimo = store.get_meta(conn, "recap_ts")
        if ultimo:
            try:
                scarto = (_dt.now(timezone.utc) - _dt.strptime(
                    ultimo, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds()
                if scarto < min_minuti * 60:
                    return False
            except ValueError:
                pass
        build(conn, lang=lang, cache=False)
        store.set_meta(conn, "recap_ts", store.now())
        conn.commit()
        return True
    finally:
        conn.close()


def build(conn=None, day=None, lang=None, engine=None, parole=140, cache=True) -> dict:
    close = False
    if conn is None:
        conn = store.connect()
        store.init_db(conn)
        close = True
    try:
        lang = lang_or_default(lang)
        dati = collect(conn, day)
        firma = impronta(conn, dati["giorno"])
        if cache and store.get_meta(conn, "recap_impronta") == f"{firma}|{lang}|{dati['giorno']}":
            testo = store.get_meta(conn, "recap_testo")
            if testo:
                return {"giorno": dati["giorno"], "lingua": lang,
                        "fonte": store.get_meta(conn, "recap_fonte", "cache"),
                        "testo": testo, "dati": dati, "da_cache": True}
        prop = proposte.calcola(conn, lang)
        proposte.salva(conn, prop)
        dati["proposte"] = prop
        engine = engine or config.load_config().get("motore_riepilogo", "claude")
        testo, fonte = "", "modello"
        if engine == "claude":
            testo = claude_text(PROMPT.format(
                lingua=NOMI_LINGUA[lang], parole=parole,
                dati=json.dumps(_compact(dati), ensure_ascii=False, indent=1)))
            if testo:
                fonte = "claude"
        if not testo:
            testo = render_template(dati, lang)
        # Il riepilogo nasce per essere ascoltato, quindi si ripulisce alla
        # fonte e non solo sulla strada della voce: il prossimo passo di un
        # progetto può contenere un indirizzo, e letto ad alta voce diventa una
        # filastrocca.
        testo = per_voce(testo, lang)
        store.set_meta(conn, "recap_impronta", f"{firma}|{lang}|{dati['giorno']}")
        store.set_meta(conn, "recap_testo", testo)
        store.set_meta(conn, "recap_lingua", lang)
        store.set_meta(conn, "recap_fonte", fonte)
        conn.commit()
        return {"giorno": dati["giorno"], "lingua": lang, "fonte": fonte,
                "testo": testo, "dati": dati, "da_cache": False}
    finally:
        if close:
            conn.close()


def answer(question: str, lang=None, conn=None, parole=110, schede=None) -> str:
    """Una domanda sul proprio lavoro, con il contesto di Plancia già allegato.

    `schede` (opzionale) è una funzione `domanda -> lista di schede` che prende il
    posto della ricerca sull'indice FTS. Le viste temporanee di una connessione
    separata per compartimento non coprono le tabelle virtuali, quindi chi
    risponde da dentro un compartimento passa qui la ricerca filtrata
    (`compartimenti_viste.cerca_schede`); senza, si cerca su tutto come sempre."""
    from . import briefing
    close = False
    if conn is None:
        conn = store.connect()
        store.init_db(conn)
        close = True
    try:
        lang = lang_or_default(lang)
        pezzi = [briefing.build(conn)]
        hits = schede(question) if schede else store.search(conn, question, 8)
        if hits:
            pezzi.append("Risultati di ricerca sull'archivio dell'utente:\n" +
                         json.dumps(hits, ensure_ascii=False)[:2500])
        dati = collect(conn)
        pezzi.append("Dati di oggi:\n" +
                     json.dumps(_compact(dati), ensure_ascii=False)[:2500])
        risposta = claude_text(DOMANDA.format(
            lingua=NOMI_LINGUA[lang], parole=parole,
            contesto="\n\n".join(pezzi), domanda=question), timeout=150)
        return risposta or {
            "it": "Non sono riuscito a rispondere adesso.",
            "en": "I could not get an answer right now.",
            "es": "No he podido responder ahora.",
        }.get(lang, "No answer.")
    finally:
        if close:
            conn.close()
