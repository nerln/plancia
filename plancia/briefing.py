"""Il briefing: cosa deve sapere una sessione di Claude appena si apre.

Viene scritto su file a ogni sync e a ogni scrittura, così l'hook SessionStart
lo legge in un millisecondo invece di aprire il database.
"""

import os
import re
from datetime import datetime, timedelta, timezone

from . import config, slot, store

PRIORITY = {1: "alta", 2: "media", 3: "bassa"}


def _ago(ts: str) -> str:
    if not ts:
        return "mai"
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    except ValueError:
        return ts[:10]
    delta = datetime.now(timezone.utc) - when
    if delta < timedelta(minutes=90):
        return f"{int(delta.total_seconds() // 60)} min fa"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)} ore fa"
    if delta.days == 1:
        return "ieri"
    if delta.days < 30:
        return f"{delta.days} giorni fa"
    return ts[:10]


def _corto(testo: str, quanti: int) -> str:
    """Taglia a fine parola, non a meta'.

    Il briefing tagliava a carattere fisso e produceva righe che finivano in
    "sectio" e "messa": costavano i token per intero e si leggevano male.
    """
    testo = " ".join((testo or "").split())
    if len(testo) <= quanti:
        return testo
    return testo[:quanti].rsplit(" ", 1)[0] + "…"


def build(conn=None, project=None, limit_projects=6, esteso=True) -> str:
    """Il quadro della situazione.

    `esteso=False` e' quello che entra in ogni sessione di Claude Code e di
    Codex, e li' ogni riga si paga una volta per sessione. Misurato il 9 agosto
    2026: la versione lunga costava ~700 token in ognuna delle 696 sessioni che
    l'hanno ricevuta, cioe' mezzo milione, e la riga piu' cara era un
    `next_action` da 430 caratteri sul paper, presente anche nelle sessioni che
    con il paper non c'entravano niente.

    Quindi la versione corta dice quel che serve a orientarsi e si ferma. Chi ha
    bisogno del resto lo chiede, e lo paga una volta sola.
    """
    if not esteso:
        return _sintesi(conn, project, limit_projects)
    close = False
    if conn is None:
        conn = store.connect()
        store.init_db(conn)
        close = True
    try:
        lines = []
        today = datetime.now().strftime("%d/%m/%Y")
        lines.append(f"# Plancia · {today}")

        where = "WHERE p.status='attivo' AND p.hidden=0"
        params = []
        if project:
            row = store.get_project(conn, project)
            if row:
                where = "WHERE p.id=?"
                params = [row["id"]]
        projects = conn.execute(
            f"SELECT p.*, (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id "
            f"AND t.status IN ('aperto','in corso','bloccato')) AS open_tasks "
            f"FROM projects p {where} "
            f"ORDER BY p.pinned DESC, p.priority ASC, p.last_activity DESC LIMIT ?",
            params + [limit_projects],
        ).fetchall()
        if projects:
            lines.append("\n## Progetti attivi")
            for p in projects:
                bits = [f"ultimo lavoro {_ago(p['last_activity'])}"]
                if p["open_tasks"]:
                    bits.append(f"{p['open_tasks']} task aperti")
                lines.append(f"- **{p['name']}** ({p['key']}) · {', '.join(bits)}")
                if p["next_action"]:
                    lines.append(f"  → prossimo passo: {p['next_action']}")

        tasks = conn.execute(
            "SELECT t.*, p.name AS pname FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
            "WHERE t.status IN ('in corso','aperto','bloccato') "
            "ORDER BY CASE t.status WHEN 'in corso' THEN 0 WHEN 'bloccato' THEN 1 ELSE 2 END, "
            "t.priority ASC, t.due IS NULL, t.due ASC LIMIT 10"
        ).fetchall()
        if tasks:
            lines.append("\n## Task aperti")
            for t in tasks:
                tag = f" [{t['pname']}]" if t["pname"] else ""
                due = f" · scade {t['due']}" if t["due"] else ""
                state = "" if t["status"] == "aperto" else f" ({t['status']})"
                lines.append(f"- #{t['id']} {t['title']}{tag}{state}{due}")

        posts = conn.execute(
            "SELECT id, platform, status, substr(text,1,70) AS text FROM posts "
            "WHERE status IN ('idea','bozza','approvato','programmato') "
            "ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        if posts:
            lines.append("\n## Social in coda")
            for o in posts:
                lines.append(f"- #{o['id']} [{o['platform']}·{o['status']}] {o['text']}…")

        events = conn.execute(
            "SELECT e.ts, e.kind, e.title, p.name AS pname FROM events e "
            "LEFT JOIN projects p ON p.id=e.project_id "
            "WHERE e.kind IN ('sessione','commit','post','task') "
            f"AND {store.visibile('e')} ORDER BY e.ts DESC LIMIT 5"
        ).fetchall()
        if events:
            lines.append("\n## Ultima attività")
            for e in events:
                tag = f" [{e['pname']}]" if e["pname"] else ""
                lines.append(f"- {_ago(e['ts'])} · {e['kind']}: {(e['title'] or '')[:70]}{tag}")

        lines.append(
            "\nPlancia è l'archivio del suo lavoro con l'IA. Usa i tool `plancia_*` "
            "per leggere il contesto, aggiungere task, registrare quello che fai e i post "
            "sociali. Dashboard: http://127.0.0.1:%d" % config.load_config().get("port", 7773)
        )
        return "\n".join(lines)
    finally:
        if close:
            conn.close()


def _blocco_prossimi(conn, chiave_filtro=None, tetto=7, max_nomi_altri=5) -> list:
    """Le righe del blocco "Prossimi": slot.prossimi() raggruppato per area
    (il progetto padre), con un tetto fisso sulle righe di dettaglio.

    Il tetto si applica PRIMA di raggruppare, non durante: slot.prossimi()
    torna le righe già nell'ordine del verdetto (scadenza se c'è, poi ultima
    attività), e le prime `tetto` di quell'ordine sono le uniche mostrate come
    dettaglio, qualunque area appartengano. Raggruppare durante il giro (come
    faceva prima) spende il tetto sul primo gruppo incontrato: un'area con
    tante righe vicine in cima alla lista mangerebbe da sola tutte le righe
    disponibili, lasciando fuori scadenze più urgenti di altre aree comparse
    dopo.

    Un progetto che è padre di altre righe (la sua chiave compare come area
    di qualcun altro) va nel gruppo con il proprio nome, non in "Senza area":
    altrimenti ogni area con un padre attivo comparirebbe due volte, come
    intestazione e come progetto senza area, e la sua riga mangerebbe una
    delle `tetto` disponibili per niente.

    La riga del padre stesso (un suo task, o il suo next_action) non ripete
    il nome: l'intestazione ce l'ha già, quindi si stampa "- → cosa" invece
    di "- Nome: cosa" (altrimenti il nome dell'area comparirebbe due volte
    nello stesso blocco, una come intestazione e una come suo "progetto
    figlio"). Se il padre non ha niente da dire (fonte "vuoto" in
    slot.prossimi) la riga si omette del tutto. E se il padre finisce fuori
    dal tetto, non compare mai nella coda "altri N" della propria area: non
    è "un altro progetto" rispetto alla sua stessa intestazione, quindi non
    conta né nel numero né nell'elenco dei nomi.

    Chi resta fuori dal tetto non sparisce: la sua area si chiude con una
    riga "altri N" che nomina solo i primi `max_nomi_altri` progetti (il
    resto solo contato) - il conteggio è quello che serve per capire che c'è
    altro, l'elenco completo di nomi è a un tool di distanza e non vale il
    suo peso in caratteri qui dentro.

    Il gruppo si identifica per CHIAVE di progetto, non per nome: due padri
    con lo stesso nome (capita, non è vietato dallo schema) restano due
    gruppi distinti invece di fondersi in uno solo con la riga sbagliata
    sotto l'altro. Il nome per la stampa si guarda solo alla fine, con
    `_nome_gruppo`.
    """
    righe_prossimi = slot.prossimi(conn)
    if chiave_filtro:
        righe_prossimi = [r for r in righe_prossimi if r["key"] == chiave_filtro]
    if not righe_prossimi:
        return []

    chiavi_area = {r["area"] for r in righe_prossimi if r["area"]}
    nomi_area = {}
    if chiavi_area:
        segnaposto = ",".join("?" for _ in chiavi_area)
        for r in conn.execute(
                f"SELECT key, name FROM projects WHERE key IN ({segnaposto})",
                list(chiavi_area)):
            nomi_area[r["key"]] = r["name"]

    # Chiave interna per il gruppo "senza area": una chiave di progetto non
    # può mai valere questo oggetto, quindi non si confonde mai con un'area
    # vera (anche una chiamata "senza-area" da un padre reale).
    SENZA_AREA = object()

    def _gruppo_di(r):
        if r["area"]:
            return r["area"]
        if r["key"] in chiavi_area:
            # E' esso stesso il padre di almeno una riga: la sua intestazione
            # esiste già, la riga va lì sotto invece che in "Senza area".
            return r["key"]
        return SENZA_AREA

    def _nome_gruppo(g):
        if g is SENZA_AREA:
            return "Senza area"
        return nomi_area.get(g, g)

    mostra = righe_prossimi[:tetto]
    fuori_tetto = righe_prossimi[tetto:]

    # L'ordine delle aree è la prima comparsa nell'intera lista (mostra +
    # fuori tetto), non solo in quella mostrata: un'area finita tutta fuori
    # tetto ha comunque la sua intestazione e la sua riga "altri N", nel
    # punto in cui sarebbe comparsa se il tetto non ci fosse.
    ordine, dettaglio, avanzo = [], {}, {}
    for r in righe_prossimi:
        g = _gruppo_di(r)
        if g not in dettaglio:
            dettaglio[g], avanzo[g] = [], []
            ordine.append(g)
    for r in mostra:
        dettaglio[_gruppo_di(r)].append(r)
    for r in fuori_tetto:
        if r["key"] in chiavi_area:
            # Il padre stesso, fuori dal tetto: la sua intestazione esiste
            # già (o esisterà per via dei suoi figli), quindi non è "un
            # altro" da contare o nominare nella coda della propria area.
            continue
        avanzo[_gruppo_di(r)].append(r)
    # "Senza area" resta sempre in fondo, qualunque sia stato il primo
    # progetto incontrato senza padre.
    if SENZA_AREA in ordine:
        ordine.remove(SENZA_AREA)
        ordine.append(SENZA_AREA)

    # Quando "Senza area" è l'unico gruppo (oggi il caso comune: nessun
    # progetto ha ancora un padre), l'intestazione non distingue niente da
    # niente altro sullo schermo: si omette invece di aprire con una riga che
    # non serve a nessuno.
    un_solo_gruppo_senza_area = ordine == [SENZA_AREA]

    def _cosa_riga(r):
        """Il testo della riga, senza ripetere il nome del progetto quando
        `cosa` inizia già con quel nome (un titolo di task scritto come
        "Nome: descrizione" produceva "- Nome: Nome: descrizione")."""
        grezzo = r["cosa"] or ""
        prefisso = f"{r['name']}: "
        if grezzo.startswith(prefisso):
            grezzo = grezzo[len(prefisso):]
        return _corto(grezzo, 70) if grezzo else ""

    righe = ["\nProssimi:"]
    for gruppo in ordine:
        nome_area = _nome_gruppo(gruppo)
        dettagli = dettaglio[gruppo]
        rimasti = avanzo[gruppo]
        if not dettagli:
            # Nessuna riga di dettaglio per questa area (il tetto è finito
            # prima che toccasse a lei): un'intestazione più una riga "altri
            # N" per niente sarebbero due righe spese per zero informazione
            # in più. Si comprime in una riga sola.
            if not rimasti:
                continue
            if un_solo_gruppo_senza_area:
                continue  # non può capitare (l'unico gruppo è "mostra" per intero), ma per sicurezza
            nomi = [x["name"] for x in rimasti[:max_nomi_altri]]
            oltre = len(rimasti) - len(nomi)
            elenco = ", ".join(nomi) + (f" e altri {oltre}" if oltre else "")
            righe.append(f"\n{nome_area}: altri {len(rimasti)}: {elenco}")
            continue
        if not un_solo_gruppo_senza_area:
            righe.append(f"\n{nome_area}:")
        for r in dettagli:
            cosa = _cosa_riga(r)
            if r["key"] in chiavi_area:
                # E' il padre della sezione: l'intestazione ha già il nome,
                # non lo si ripete. Senza niente da dire (cosa vuota) la
                # riga non aggiunge nulla e si salta.
                if cosa:
                    righe.append(f"- → {cosa}")
            else:
                righe.append(f"- {r['name']}: {cosa}" if cosa else f"- {r['name']}")
        if rimasti:
            nomi = [x["name"] for x in rimasti[:max_nomi_altri]]
            oltre = len(rimasti) - len(nomi)
            elenco = ", ".join(nomi) + (f" e altri {oltre}" if oltre else "")
            righe.append(f"- altri {len(rimasti)}: {elenco}")
    return righe


def _sintesi(conn=None, project=None, limit_projects=4) -> str:
    """Il briefing che entra in ogni sessione.

    Tetto duro sulle righe di dettaglio del blocco "Prossimi" (7) e sui nomi
    per esteso dentro ogni "altri N" (`max_nomi_altri`, oggi 5): quello che
    fa restare il file corto anche quando un'area ha decine di progetti.
    Un'area che il tetto lascia interamente fuori si comprime in una riga
    sola ("Nome: altri N: ..."), invece di intestazione più riga a parte.
    Il numero di intestazioni di area NON ha un tetto proprio, però - oggi
    non si vede perché nessun progetto ha ancora un padre e tutto collassa
    in un solo gruppo senza intestazione, ma con molte aree attive il blocco
    cresce comunque di almeno una riga per area: se dovesse contare, il
    tetto va aggiunto lì.
    """
    close = False
    if conn is None:
        conn = store.connect()
        store.init_db(conn)
        close = True
    try:
        righe = [f"# Plancia · {datetime.now().strftime('%d/%m/%Y')}"]

        # Non più l'elenco piatto dei progetti attivi: la stessa
        # informazione (nome, prossimo passo) arriva più densa dal blocco
        # "Prossimi" qui sotto, raggruppata per area. limit_projects resta
        # nella firma per compatibilità con build(), ma non pilota più
        # niente: il tetto del blocco prossimi è fisso (vedi _blocco_prossimi).
        chiave_filtro = None
        if project:
            riga_progetto = store.get_project(conn, project)
            if riga_progetto:
                chiave_filtro = riga_progetto["key"]
        righe.extend(_blocco_prossimi(conn, chiave_filtro))

        task = conn.execute(
            "SELECT t.id, t.title, t.due, p.name AS pname FROM tasks t "
            "LEFT JOIN projects p ON p.id=t.project_id "
            "WHERE t.status IN ('in corso','aperto','bloccato') "
            "ORDER BY CASE t.status WHEN 'in corso' THEN 0 WHEN 'bloccato' THEN 1 ELSE 2 END, "
            "t.priority ASC, t.due IS NULL, t.due ASC LIMIT 4"
        ).fetchall()
        aperti = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status IN ('in corso','aperto','bloccato')"
        ).fetchone()[0]
        if task:
            resto = f", altri {aperti - len(task)}" if aperti > len(task) else ""
            righe.append(f"\nTask ({aperti}{resto}):")
            for t in task:
                tag = f" [{t['pname']}]" if t["pname"] else ""
                scade = f" · scade {t['due']}" if t["due"] else ""
                righe.append(f"- #{t['id']} {_corto(t['title'], 62)}{tag}{scade}")

        righe.append("\nIl resto: tool `plancia`, azione=briefing.")
        return "\n".join(righe)
    finally:
        if close:
            conn.close()


def write_cache() -> str:
    """Scrive il file che l'hook di SessionStart infila in ogni sessione.

    Qui va la versione corta, e il motivo e' aritmetico: questo file entra nel
    contesto di ogni sessione di Claude Code e di Codex, quindi ogni riga si paga
    tante volte quante sessioni apri. La versione lunga resta a un tool di
    distanza per chi la vuole davvero.

    Con dei compartimenti nominati in config.json (vedi
    plancia/compartimenti_viste.py) il file e' uno PER compartimento: la sessione
    di un nominato riceve solo il suo (`briefing.<nome>.md`), quella del
    predefinito solo il proprio (`briefing.predefinito.md`, che e' anche
    `briefing.md` per chi lo legge da fuori). L'hook sceglie il file dal
    compartimento della sessione e, con i compartimenti attivi, non legge mai il
    `briefing.md` non separato che un sync di prima poteva aver lasciato. Senza
    compartimenti e' un file solo, com'e' sempre stato. Se i compartimenti ci
    sono ma non si riesce a separare, non si scrive niente: meglio un briefing
    vecchio che uno che mescola.
    """
    from . import compartimenti_viste as viste
    config.ensure_dirs()
    ambito = viste.attivo()
    if ambito is None:
        text = build(esteso=False)
        config.BRIEFING_FILE.write_text(text, "utf-8")
        _togli_briefing_altrui(viste, [])
        return text
    conn = store.connect()
    try:
        appart = viste.Appartenenze(conn, ambito)
    finally:
        conn.close()
    testi = {}
    for nome in viste.elenco(ambito):
        conn = store.connect()
        try:
            o = viste.applica(conn, ambito, nome, appart=appart)
            testi[nome] = build(conn, esteso=False)
        finally:
            conn.close()
    for nome, testo in testi.items():
        with open(viste.file_briefing(str(config.DATA_DIR), nome), "w",
                  encoding="utf-8") as fh:
            fh.write(testo)
    _togli_briefing_altrui(viste, [n for n in testi])
    config.BRIEFING_FILE.write_text(testi[viste.PREDEFINITO], "utf-8")
    return testi[viste.PREDEFINITO]


#: i nomi che `compartimenti_viste.file_briefing` puo' produrre (nome ridotto a
#: caratteri sicuri, piu' un pezzo di hash se e' cambiato): un file con un altro
#: nome, messo li' da chi usa la cartella, non e' nostro e non si tocca
_RX_FILE_BRIEFING = re.compile(r"^briefing\.[A-Za-z0-9_-]{1,40}(-[0-9a-f]{6})?\.md$")


def _togli_briefing_altrui(viste, nomi) -> None:
    """Toglie i `briefing.<nome>.md` di compartimenti che non ci sono piu'
    (config cambiata, compartimenti spenti): un file vecchio con dentro il
    lavoro di un compartimento non deve restare li' a farsi leggere.

    Solo i file che questo modulo sa scrivere (`_RX_FILE_BRIEFING`), e senza
    compartimenti (`nomi` vuoto) solo se i compartimenti ci sono stati (la copia
    dell'ultima config valida esiste): chi non ha mai usato la funzione non vede
    una `unlink` in piu' e un suo file con quel nome resta dov'e'."""
    tengo = {os.path.basename(viste.file_briefing(str(config.DATA_DIR), n)) for n in nomi}
    try:
        if not nomi and not os.path.exists(viste._copia_percorso(str(config.DATA_DIR))):
            return
        for f in config.DATA_DIR.glob("briefing.*.md"):
            if f.name not in tengo and _RX_FILE_BRIEFING.match(f.name):
                f.unlink()
    except OSError:
        pass
