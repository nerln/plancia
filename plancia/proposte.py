"""Le proposte: cosa converrebbe fare adesso, e il modo per farlo dire una volta.

Un riepilogo che elenca i fatti e finisce lì ti lascia il lavoro peggiore: capire
cosa farne. Qui i fatti diventano proposte, ognuna con un'azione già pronta, così
"fallo" basta.

Le proposte nascono solo da segnali che stanno nei dati, mai da un modello: un
lancio fallito, un obiettivo di Codex bloccato, modifiche non committate da un
giorno, un post approvato che non è mai uscito, un task aperto dimenticato da
tre settimane su un progetto vivo, una spesa fuori scala. Se il segnale non
c'è, la proposta non c'è: meglio un riepilogo che finisce corto che uno che si
inventa un consiglio.
"""

import json
from datetime import datetime, timedelta, timezone

from . import store

# Quante volte la media giornaliera deve essere superata per gridare.
SOGLIA_FUGA = 2.5


def _ore_fa(ore):
    return (datetime.now(timezone.utc) - timedelta(hours=ore)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _giorni_fa(giorni):
    return _ore_fa(giorni * 24)


T = {
    "it": {
        "lancio_fallito": "Il lancio su {cosa} è fallito. Lo riprovo?",
        "codex_bloccato": "Codex è fermo su {cosa}: {perche}. Ci mando Claude a vedere?",
        "task_fermo": "{cosa} è in corso da {giorni} giorni senza movimento. Lo riprendo?",
        "non_committato": "Su {cosa} ci sono {n} file modificati e non committati da ieri. Vuoi che guardi cosa sono?",
        "post_fermo": "C'è un post approvato e mai uscito su {cosa}. Lo pubblichiamo?",
        "prossimo_passo": "Su {cosa} il prossimo passo è: {passo}. Lo mando a un agente?",
        "spesa": "Oggi hai già generato {n} volte la tua media giornaliera. Ti conviene tenerla d'occhio.",
        "senza_progetto": "Il task {cosa} non è legato a nessun progetto. A quale lo attacco?",
        "task_stagnante": "{cosa} è fermo da {giorni} giorni su {progetto} senza un tocco. Lo archivio o lo riassegno?",
        "chiudi": "Vuoi che ne faccia qualcuna?",
    },
    "en": {
        "lancio_fallito": "The run on {cosa} failed. Shall I try again?",
        "codex_bloccato": "Codex is stuck on {cosa}: {perche}. Want me to send Claude to look?",
        "task_fermo": "{cosa} has been in progress for {giorni} days with no movement. Pick it up?",
        "non_committato": "{cosa} has {n} files changed and uncommitted since yesterday. Want me to look at them?",
        "post_fermo": "There is an approved post on {cosa} that never went out. Publish it?",
        "prossimo_passo": "On {cosa} the next step is: {passo}. Send it to an agent?",
        "spesa": "Today you are already at {n} times your daily average. Worth keeping an eye on.",
        "senza_progetto": "The task {cosa} is not attached to any project. Which one?",
        "task_stagnante": "{cosa} has sat untouched for {giorni} days on {progetto}. Should I archive it or reassign it?",
        "chiudi": "Want me to do any of them?",
    },
    "es": {
        "lancio_fallito": "El lanzamiento sobre {cosa} ha fallado. ¿Lo reintento?",
        "codex_bloccato": "Codex está parado en {cosa}: {perche}. ¿Mando a Claude a mirarlo?",
        "task_fermo": "{cosa} lleva {giorni} días en curso sin moverse. ¿Lo retomo?",
        "non_committato": "En {cosa} hay {n} archivos modificados sin commit desde ayer. ¿Los miro?",
        "post_fermo": "Hay un post aprobado que nunca salió sobre {cosa}. ¿Lo publicamos?",
        "prossimo_passo": "En {cosa} el siguiente paso es: {passo}. ¿Lo mando a un agente?",
        "spesa": "Hoy ya vas por {n} veces tu media diaria. Conviene vigilarlo.",
        "senza_progetto": "La tarea {cosa} no está ligada a ningún proyecto. ¿A cuál?",
        "task_stagnante": "{cosa} lleva {giorni} días sin tocar en {progetto}. ¿Lo archivo o lo reasigno?",
        "chiudi": "¿Quieres que haga alguna?",
    },
}


# Perché Codex si è fermato, detto nella lingua in cui stai parlando.
PERCHE = {
    "it": {"blocked": "bloccato", "usage_limited": "ha finito la quota",
           "budget_limited": "ha finito il budget"},
    "en": {"blocked": "blocked", "usage_limited": "out of quota",
           "budget_limited": "out of budget"},
    "es": {"blocked": "bloqueado", "usage_limited": "sin cuota",
           "budget_limited": "sin presupuesto"},
}


def _t(lang):
    return T.get(lang, T["en"])


def calcola(conn, lang="it", limite=4) -> list:
    """Le proposte del momento, dalla più urgente alla meno."""
    d = _t(lang)
    fuori = []

    def aggiungi(urgenza, chiave, azione, **campi):
        fuori.append({
            "id": f"{chiave}:{campi.get('rif', '')}",
            "testo": d[chiave].format(**campi),
            "motivo": chiave,
            "urgenza": urgenza,
            "azione": azione,
        })

    # 1. un lancio andato male è la cosa più urgente: il lavoro è fermo lì
    for r in conn.execute(
            "SELECT r.id, r.prompt, r.agente, r.modo, r.cwd, t.title FROM runs r "
            "LEFT JOIN tasks t ON t.id=r.task_id WHERE r.stato='fallito' AND r.fine > ? "
            "ORDER BY r.id DESC LIMIT 2", (_giorni_fa(3),)):
        cosa = r["title"] or r["prompt"].splitlines()[0][:60]
        aggiungi(0, "lancio_fallito",
                 {"tipo": "rilancia", "run": r["id"]}, cosa=cosa, rif=r["id"])

    # 2. un obiettivo di Codex bloccato non si sblocca da solo
    for r in conn.execute(
            "SELECT titolo, stato_origine, project_id FROM agenda "
            "WHERE fonte='codex' AND stato='bloccato' LIMIT 2"):
        perche = PERCHE.get(lang, PERCHE["en"]).get(r["stato_origine"], r["stato_origine"])
        aggiungi(1, "codex_bloccato",
                 {"tipo": "manda", "titolo": r["titolo"][:120],
                  "progetto": _chiave(conn, r["project_id"]), "modo": "proposta"},
                 cosa=r["titolo"][:60], perche=perche, rif=r["titolo"][:20])

    # 3. modifiche mai committate: il lavoro c'è ma non è al sicuro
    for r in conn.execute(
            "SELECT r.name, r.dirty, p.key FROM repos r LEFT JOIN projects p ON p.id=r.project_id "
            "WHERE r.dirty > 0 ORDER BY r.dirty DESC LIMIT 1"):
        aggiungi(2, "non_committato",
                 {"tipo": "manda", "titolo": f"Guarda le modifiche non committate in {r['name']} "
                                             f"e dimmi cosa sono", "progetto": r["key"],
                  "modo": "proposta"},
                 cosa=r["name"], n=r["dirty"], rif=r["name"])

    # 4. un post approvato che non esce è lavoro già fatto e sprecato
    for r in conn.execute(
            "SELECT o.id, substr(o.text,1,60) AS t, p.name FROM posts o "
            "LEFT JOIN projects p ON p.id=o.project_id WHERE o.status='approvato' LIMIT 1"):
        aggiungi(3, "post_fermo", {"tipo": "vai", "vista": "social"},
                 cosa=r["name"] or r["t"], rif=r["id"])

    # 5. un task in corso da giorni di solito è un task bloccato che non lo dice
    for r in conn.execute(
            "SELECT id, title, updated_at, project_id FROM tasks "
            "WHERE status='in corso' AND updated_at < ? ORDER BY updated_at LIMIT 1",
            (_giorni_fa(3),)):
        giorni = _quanti_giorni(r["updated_at"])
        aggiungi(4, "task_fermo",
                 {"tipo": "manda", "titolo": r["title"],
                  "progetto": _chiave(conn, r["project_id"]), "task_id": r["id"],
                  "modo": "proposta"},
                 cosa=r["title"][:60], giorni=giorni, rif=r["id"])

    # 6. il prossimo passo dichiarato di un progetto che non si muove
    for r in conn.execute(
            "SELECT key, name, next_action FROM projects WHERE status='attivo' AND hidden=0 "
            "AND next_action <> '' AND (last_activity IS NULL OR last_activity < ?) "
            "ORDER BY priority ASC LIMIT 1", (_giorni_fa(2),)):
        aggiungi(5, "prossimo_passo",
                 {"tipo": "manda", "titolo": r["next_action"], "progetto": r["key"],
                  "modo": "proposta"},
                 cosa=r["name"], passo=r["next_action"][:80], rif=r["key"])

    # 7. la spesa fuori scala: è la lamentela numero uno di chi usa questi agenti
    fuga = _fuga(conn)
    if fuga:
        aggiungi(6, "spesa", {"tipo": "vai", "vista": "archivio"}, n=fuga, rif="spesa")

    # 8. un task aperto che nessuno tocca da settimane, su un progetto ancora
    # vivo, non è "in corso": è dimenticato. Uno per volta (il più vecchio),
    # come task_fermo qui sopra: un elenco che si allunga da solo non è una
    # proposta, è un altro riepilogo. Un task già proposto sopra (controllo 5,
    # "in corso" fermo da 3 giorni) non torna qui: altrimenti lo stesso task
    # genererebbe due proposte opposte ("lo riprendo?" e "lo archivio?").
    # L'urgenza 7 è la più bassa di tutte apposta (è la meno urgente da fare
    # subito): ma proprio per questo il taglio finale a `limite` la
    # scarterebbe sempre non appena ci sono `limite` proposte più urgenti, e
    # un task dimenticato da settimane resterebbe invisibile per sempre. Il
    # posto riservato più sotto la ripesca.
    id_gia_proposti = {p["azione"]["task_id"] for p in fuori
                       if (p.get("azione") or {}).get("task_id") is not None}
    for r in conn.execute(
            "SELECT t.id, t.title, t.updated_at, p.name AS pname, p.key AS pkey "
            "FROM tasks t JOIN projects p ON p.id=t.project_id "
            "WHERE t.status IN ('aperto','in corso') AND p.status='attivo' AND p.hidden=0 "
            "AND t.updated_at < ? ORDER BY t.updated_at ASC",
            (_giorni_fa(21),)):
        if r["id"] in id_gia_proposti:
            continue
        # L'azione è nello stesso formato di task_fermo: "manda" è uno dei
        # tipi che jarvis._esegui_proposta sa eseguire davvero (apre un
        # cantiere che chiede a un agente di archiviare o riassegnare il
        # task). "archivia" non esisteva come tipo gestito da nessuno: la
        # proposta prometteva un effetto che "fallo" non produceva.
        aggiungi(7, "task_stagnante",
                 {"tipo": "manda",
                  "titolo": f"Archivia o riassegna il task #{r['id']} '{r['title'][:80]}' "
                            f"su {r['pname']}",
                  "progetto": r["pkey"], "task_id": r["id"], "modo": "proposta"},
                 cosa=r["title"][:60], giorni=_quanti_giorni(r["updated_at"]),
                 progetto=r["pname"], rif=r["id"])
        break

    fuori.sort(key=lambda p: p["urgenza"])

    # Un posto riservato per task_stagnante (decisione dell'utente, 28/09,
    # voce 8 del DECIDE in docs/CANTIERE-2026-09.md): la sua urgenza 7, la
    # più bassa di tutte, la fa arrivare ultima non appena ci sono `limite`
    # proposte più urgenti, quindi il taglio qui sotto la escluderebbe
    # sempre. Se c'è e non è già tra le prime `limite`, prende il posto
    # dell'ultima (la meno urgente) di quelle prime `limite`: l'ordine delle
    # altre non cambia. Con `limite` >= al numero di proposte non cambia
    # niente (ci sarebbe comunque tra le prime). Con `limite` == 1 il posto
    # riservato non vale: vince sempre la proposta più urgente, altrimenti un
    # limite a una sola proposta perderebbe sempre quella più urgente in
    # favore di questa.
    risultato = fuori[:limite]
    if limite >= 2:
        stagnante = next((p for p in fuori if p["motivo"] == "task_stagnante"), None)
        if stagnante is not None and stagnante["id"] not in {p["id"] for p in risultato}:
            risultato = risultato[:-1] + [stagnante]
    return risultato


def _quanti_giorni(ts) -> int:
    try:
        q = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return max(1, (datetime.now(timezone.utc) - q).days)
    except Exception:
        return 1


def _chiave(conn, project_id):
    if not project_id:
        return None
    r = conn.execute("SELECT key FROM projects WHERE id=?", (project_id,)).fetchone()
    return r["key"] if r else None


def _fuga(conn):
    """Quante volte la media giornaliera stai bruciando oggi.

    Torna None se sei nella norma. Il confronto è sui token generati, che sono
    la cosa che finisce davvero: i limiti si prendono lì.
    """
    oggi = conn.execute(
        f"SELECT COALESCE(SUM(out_tokens),0) FROM sessions s "
        f"WHERE substr(started_at,1,10)=? AND {store.visibile()}",
        (datetime.now().astimezone().strftime("%Y-%m-%d"),)).fetchone()[0]
    media = conn.execute(
        f"SELECT COALESCE(AVG(g),0) FROM (SELECT SUM(out_tokens) g FROM sessions s "
        f"WHERE started_at > ? AND {store.visibile()} GROUP BY substr(started_at,1,10))",
        (_giorni_fa(30),)).fetchone()[0]
    if not media or media < 50000:
        return None
    volte = oggi / media
    return round(volte, 1) if volte >= SOGLIA_FUGA else None


# --------------------------------------------------------------------------
# memoria fra un turno e l'altro
# --------------------------------------------------------------------------

def salva(conn, lista) -> None:
    """Le proposte restano in memoria fino al turno dopo, così "fallo" sa a
    cosa si riferisce."""
    store.set_meta(conn, "proposte", json.dumps(lista, ensure_ascii=False))
    store.set_meta(conn, "proposte_ts", store.now())
    conn.commit()


def ultime(conn) -> list:
    try:
        return json.loads(store.get_meta(conn, "proposte") or "[]")
    except Exception:
        return []


def scegli(conn, quale=None, lang="it"):
    """La proposta a cui si riferisce un "fallo" o un "la seconda"."""
    lista = ultime(conn)
    if not lista:
        # Nessuno le ha ancora chieste in questa sessione: si calcolano adesso,
        # invece di rispondere che non c'è niente da fare quando c'è.
        lista = calcola(conn, lang)
        if lista:
            salva(conn, lista)
    if not lista:
        return None
    if quale is None:
        return lista[0]
    if isinstance(quale, int):
        return lista[quale - 1] if 0 < quale <= len(lista) else None
    testo = str(quale).lower()
    ordinali = {"prima": 1, "primo": 1, "first": 1, "primera": 1,
                "seconda": 2, "secondo": 2, "second": 2, "segunda": 2,
                "terza": 3, "terzo": 3, "third": 3, "tercera": 3,
                # `calcola()` da' fino a 4 proposte e la dashboard ha un
                # pulsante per ciascuna: "la quarta" deve essere riconosciuta
                "quarta": 4, "quarto": 4, "fourth": 4, "cuarta": 4}
    for parola, n in ordinali.items():
        if parola in testo:
            return lista[n - 1] if n <= len(lista) else None
    for p in lista:
        if any(w in p["testo"].lower() for w in testo.split() if len(w) > 4):
            return p
    return lista[0]
