"""Prove per L1-BRIEFING: briefing, proposte e recap che leggono aree e
prossimi.

Stessa disciplina di tools/prove/slot.py: un archivio SQLite in memoria per
gruppo (mai il database vero), così una prova non lascia residui per la
prossima. Vedi tools/prove/README.md per come questo file viene scoperto.
"""

import sqlite3
from datetime import datetime, timedelta, timezone


def _conn():
    from plancia import store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    store.init_db(conn)
    return conn


def _progetto(conn, key, name=None, auto=0, **campi):
    from plancia import store
    pid = store.upsert_project(conn, key, name or key, auto=auto, _force=True, **campi)
    conn.commit()
    return pid


def _giorni_fa(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _task(conn, project_id, title, status="aperto", updated_at=None):
    from plancia import store
    ts = store.now()
    conn.execute(
        "INSERT INTO tasks(title, status, project_id, created_at, updated_at) "
        "VALUES(?,?,?,?,?)",
        (title, status, project_id, ts, updated_at or ts),
    )
    conn.commit()


def _sezioni(testo):
    """Spezza il testo del briefing in {nome_sezione: [righe di dettaglio]},
    per poter controllare cosa sta sotto quale intestazione."""
    sezioni, corrente = {}, None
    for riga in testo.splitlines():
        s = riga.strip()
        if s and s.endswith(":") and not s.startswith("-"):
            corrente = s[:-1]
            sezioni.setdefault(corrente, [])
        elif corrente is not None and s.startswith("- "):
            sezioni[corrente].append(s)
    return sezioni


def _nomi_dettaglio(testo):
    """I nomi dei progetti mostrati come righe di dettaglio nel blocco
    "Prossimi", nell'ordine in cui compaiono nel testo.

    Una riga normale porta il nome per esteso ("- Nome: cosa" o "- Nome").
    La riga del padre della sezione corrente non lo ripete ("- → cosa"):
    conta comunque come una riga di dettaglio per quel nome, che è quello
    della sezione in cui si trova (l'intestazione)."""
    nomi, sezione = [], None
    for riga in testo.splitlines():
        s = riga.strip()
        if s and s.endswith(":") and not s.startswith("-"):
            sezione = s[:-1]
        elif s.startswith("- altri "):
            continue
        elif s.startswith("- → "):
            nomi.append(sezione)
        elif s.startswith("- "):
            nomi.append(s[2:].split(":", 1)[0])
    return nomi


def _prova_briefing_aree(prova):
    """Il blocco 'Prossimi' del briefing corto: intestazioni per area,
    tetto di 7 righe di dettaglio in tutto (esattamente le prime 7 di
    slot.prossimi(), non le prime incontrate per area), un gruppo 'Senza
    area' per chi non ha un padre, e i padri attivi che non ci finiscono
    dentro anche loro."""
    from plancia import briefing, slot

    conn = _conn()
    # il padre è attivo (status di default): sul db vero le aree sono
    # progetti manuali attivi (per esempio i worktree di un repo), non
    # progetti conclusi. Se il padre finisse fuori da slot.prossimi() la
    # prova non vedrebbe il difetto che l'ha messo sotto "Senza area".
    ricerca = _progetto(conn, "ricerca", name="Ricerca", auto=0)
    vr = _progetto(conn, "vr-lab", name="VR Lab", auto=0)
    ai = _progetto(conn, "ai-bridge", name="AI Bridge", auto=0)
    slot.set_parent(conn, "vr-lab", "ricerca", "g1")
    slot.set_parent(conn, "ai-bridge", "ricerca", "g2")
    solitario = _progetto(conn, "solitario", name="Solitario", auto=0)

    # sei progetti in più nella stessa area, così il tetto di 7 righe totali
    # e il gruppo "altri N" si vedono davvero (l'area arriva a 9 candidati
    # contando il padre)
    extra_ids = []
    for i in range(6):
        pid = _progetto(conn, f"extra-{i}", name=f"Extra {i}", auto=0)
        slot.set_parent(conn, f"extra-{i}", "ricerca", f"gx{i}")
        extra_ids.append(pid)
    for pid, passo in [(ricerca, "passo ricerca"), (vr, "passo vr"), (ai, "passo ai"),
                       (solitario, "passo solo")] + \
            [(pid, f"passo {i}") for i, pid in enumerate(extra_ids)]:
        conn.execute("UPDATE projects SET next_action=? WHERE id=?", (passo, pid))
    conn.commit()

    testo = briefing.build(conn, esteso=False)
    prova("il briefing contiene l'intestazione dell'area", "Ricerca:" in testo, testo)
    prova("il briefing contiene il gruppo senza area", "Senza area:" in testo, testo)

    righe = testo.splitlines()
    nomi_dettaglio_ordine = _nomi_dettaglio(testo)
    prova("esattamente 7 righe di dettaglio nel blocco prossimi (il tetto)",
          len(nomi_dettaglio_ordine) == 7, f"{len(nomi_dettaglio_ordine)}: {nomi_dettaglio_ordine}")

    # Le righe mostrate sono ESATTAMENTE le prime 7 di slot.prossimi(): non
    # importa in che ordine il raggruppamento per area le stampa (un'area
    # tiene insieme le sue righe), ma l'insieme dei progetti in vista deve
    # coincidere con l'insieme dei primi 7 del verdetto, non con "i primi 7
    # dell'area incontrata per prima". Ricerca è il padre: la sua riga di
    # dettaglio è "- → cosa" (senza il nome), ma conta comunque come "Ricerca"
    # perché sta nella sezione "Ricerca:".
    attesi = sorted(r["name"] for r in slot.prossimi(conn)[:7])
    nomi_dettaglio = sorted(nomi_dettaglio_ordine)
    prova("le righe di dettaglio sono ESATTAMENTE le prime 7 di slot.prossimi()",
          nomi_dettaglio == attesi, f"{nomi_dettaglio} vs {attesi}")

    prova("il padre (Ricerca) non ripete il proprio nome nella sua riga di dettaglio",
          "- → passo ricerca" in righe and "- Ricerca: passo ricerca" not in righe, testo)
    prova("il nome del padre compare una volta sola in tutto il blocco (l'intestazione)",
          testo.count("Ricerca") == 1, testo)

    prova("c'è una riga 'altri N' per l'area con più progetti di quanti ne stiano nel tetto",
          any(r.startswith("- altri ") for r in righe), testo)

    sezioni = _sezioni(testo)
    prova("il padre attivo (Ricerca) non compare sotto 'Senza area'",
          not any("Ricerca" in r for r in sezioni.get("Senza area", [])),
          str(sezioni.get("Senza area")))
    prova("Solitario (senza padre) compare sotto 'Senza area', non sotto 'Ricerca'",
          any("Solitario" in r for r in sezioni.get("Senza area", [])),
          str(sezioni.get("Senza area")))

    # la riga "altri N" con più di max_nomi_altri progetti tronca i nomi
    # elencati e passa a "e altri M": non deve mai stampare tutti i 77 nomi
    # di un'area enorme come farebbe sul db vero.
    riga_altri = next(r for r in righe if r.startswith("- altri "))
    prova("la riga 'altri N' non elenca più di 5 nomi per esteso",
          riga_altri.count(",") <= 4, riga_altri)


def _prova_padre_non_duplicato(prova):
    """Aggiunta LOTTO 16/09 (#2): un padre con un next_action o un task
    proprio non deve comparire due volte (intestazione + riga "Nome: cosa"
    sotto se stesso), e se finisce fuori dal tetto di 7 non deve mai contare
    come "un altro" nella coda "altri N" della propria area."""
    from plancia import briefing, slot

    # caso 1: il padre è dentro al tetto (pochi progetti, next_action forte)
    conn = _conn()
    padre = _progetto(conn, "area-1", name="Area1", auto=0)
    f1 = _progetto(conn, "figlio-1", name="Figlio1", auto=0)
    f2 = _progetto(conn, "figlio-2", name="Figlio2", auto=0)
    slot.set_parent(conn, "figlio-1", "area-1", "gp1")
    slot.set_parent(conn, "figlio-2", "area-1", "gp2")
    for pid, passo in [(padre, "passo padre"), (f1, "passo 1"), (f2, "passo 2")]:
        conn.execute("UPDATE projects SET next_action=? WHERE id=?", (passo, pid))
    conn.commit()
    testo = briefing.build(conn, esteso=False)
    prova("il nome del padre compare una volta sola nel blocco (l'intestazione)",
          testo.count("Area1") == 1, testo)
    prova("la riga del padre usa il segno al posto del nome",
          "- → passo padre" in testo, testo)

    # caso 2: il padre finisce fuori dal tetto di 7 (nessun next_action
    # proprio, quindi in coda per fonte "vuoto" in slot.prossimi) e non deve
    # comparire nella riga "altri N" della sua stessa area.
    conn2 = _conn()
    _progetto(conn2, "area-2", name="Area2", auto=0)
    for i in range(8):
        pid = _progetto(conn2, f"f2-{i}", name=f"Figlio {i}", auto=0)
        slot.set_parent(conn2, f"f2-{i}", "area-2", f"gp{i}")
        conn2.execute("UPDATE projects SET next_action=? WHERE id=?", (f"passo {i}", pid))
    conn2.commit()
    testo2 = briefing.build(conn2, esteso=False)
    riga_altri2 = next(r for r in testo2.splitlines() if r.startswith("- altri "))
    prova("il padre fuori dal tetto non compare nella riga 'altri N' della sua area",
          "Area2" not in riga_altri2, riga_altri2)


def _prova_altri_tanti_nomi(prova):
    """Con molti più progetti fuori tetto di quanti se ne possano nominare,
    la riga 'altri N' resta corta: il conteggio è esatto, i nomi si fermano
    a un tetto fisso invece di elencarli tutti (misurato sul db vero:
    1588 caratteri per una sola riga con 77 nomi)."""
    from plancia import briefing, slot

    conn = _conn()
    for i in range(20):
        pid = _progetto(conn, f"tanti-{i}", name=f"Progetto Tanti {i}", auto=0)
        conn.execute("UPDATE projects SET next_action=? WHERE id=?", (f"passo {i}", pid))
    conn.commit()

    testo = briefing.build(conn, esteso=False)
    righe = testo.splitlines()
    riga_altri = next(r for r in righe if r.startswith("- altri "))
    prova("'altri N' con 20 progetti fuori tetto dichiara il conteggio esatto",
          riga_altri.startswith("- altri 13:"), riga_altri)
    prova("ma nomina al più 5 progetti, il resto solo contato",
          "e altri 8" in riga_altri, riga_altri)
    prova("la riga 'altri N' resta corta anche con molti progetti fuori tetto",
          len(riga_altri) < 200, f"{len(riga_altri)} caratteri: {riga_altri}")


def _prova_area_comprimibile(prova):
    """Consigliata dal critico (16/09): un'area che il tetto lascia
    interamente fuori (0 righe di dettaglio, solo "altri N") non deve
    costare un'intestazione vuota più una riga a parte: si comprime in
    "Nome: altri N: ..." su una riga sola."""
    from plancia import briefing, slot

    conn = _conn()
    piccola = _progetto(conn, "piccola", name="Piccola", auto=0)
    _task(conn, piccola, "il più urgente", status="aperto")
    conn.execute("UPDATE tasks SET due=? WHERE project_id=?",
                 (datetime.now(timezone.utc).strftime("%Y-%m-%d"), piccola))
    _progetto(conn, "grande", name="Grande", auto=0)
    for i in range(3):
        pid = _progetto(conn, f"grande-f{i}", name=f"GrandeFiglio{i}", auto=0)
        slot.set_parent(conn, f"grande-f{i}", "grande", f"gg{i}")
        conn.execute("UPDATE projects SET next_action=? WHERE id=?", (f"passo {i}", pid))
    conn.commit()

    # tetto=1: solo la riga più urgente (Piccola, con scadenza) entra nel
    # dettaglio; l'intera area Grande (padre + 3 figli, nessuno con
    # scadenza) finisce fuori tetto.
    righe = briefing._blocco_prossimi(conn, tetto=1)
    testo = "\n".join(righe)
    prova("l'area interamente fuori tetto compare come intestazione+altri sulla stessa riga",
          any(r.startswith("\nGrande: altri 3:") for r in righe), testo)
    prova("non c'è una riga 'Grande:' separata (nessuna intestazione vuota sprecata)",
          "\nGrande:" not in righe, testo)


def _prova_gruppi_per_chiave_non_nome(prova):
    """Consigliata dal critico (16/09): il gruppo si identifica per chiave di
    progetto, non per nome. Due padri con lo stesso nome restano due
    intestazioni distinte invece di fondersi in un solo gruppo."""
    from plancia import briefing, slot

    conn = _conn()
    _progetto(conn, "area-x", name="Duplicato", auto=0)
    _progetto(conn, "area-y", name="Duplicato", auto=0)
    fx = _progetto(conn, "figlio-x", name="FiglioX", auto=0)
    fy = _progetto(conn, "figlio-y", name="FiglioY", auto=0)
    slot.set_parent(conn, "figlio-x", "area-x", "gpx")
    slot.set_parent(conn, "figlio-y", "area-y", "gpy")
    for pid, passo in [(fx, "passo x"), (fy, "passo y")]:
        conn.execute("UPDATE projects SET next_action=? WHERE id=?", (passo, pid))
    conn.commit()

    testo = briefing.build(conn, esteso=False)
    prova("due padri omonimi restano due intestazioni distinte, non una sola fusa",
          testo.count("Duplicato:") == 2, testo)
    prova("il figlio dell'area-x compare", "- FiglioX: passo x" in testo, testo)
    prova("il figlio dell'area-y compare", "- FiglioY: passo y" in testo, testo)


def _prova_niente_prefisso_duplicato(prova):
    """Cosmetico segnalato dal critico (16/09): quando il titolo del task
    inizia già col nome del progetto ("Harbour: rollback..."), la riga non
    deve ripetere il nome ("- Harbour: Harbour: rollback...")."""
    from plancia import briefing

    conn = _conn()
    p = _progetto(conn, "harbour", name="Harbour", auto=0)
    _task(conn, p, "Harbour: rollback still leaves the old release dir")
    conn.commit()

    testo = briefing.build(conn, esteso=False)
    prova("niente prefisso duplicato quando il titolo ripete già il nome",
          "Harbour: Harbour:" not in testo, testo)
    prova("la riga mostra comunque il testo del task, senza il prefisso ripetuto",
          "- Harbour: rollback still leaves the old release dir" in testo, testo)


def _prova_proposta_task_stagnante(prova):
    """L'ottavo controllo di proposte.calcola: un task fermo da 21 giorni
    su un progetto attivo e non nascosto, uno alla volta, il più vecchio."""
    from plancia import proposte

    conn = _conn()
    attivo = _progetto(conn, "attivo", name="Attivo", auto=0)
    _task(conn, attivo, "vecchio davvero", updated_at=_giorni_fa(22))
    lista = proposte.calcola(conn, limite=20)
    prova("un task fermo da 22 giorni genera la proposta",
          any(p["motivo"] == "task_stagnante" for p in lista), str(lista))

    conn2 = _conn()
    attivo2 = _progetto(conn2, "attivo2", name="Attivo2", auto=0)
    _task(conn2, attivo2, "recente", updated_at=_giorni_fa(20))
    lista2 = proposte.calcola(conn2, limite=20)
    prova("un task fermo da 20 giorni non genera la proposta",
          not any(p["motivo"] == "task_stagnante" for p in lista2), str(lista2))

    conn3 = _conn()
    attivo3 = _progetto(conn3, "attivo3", name="Attivo3", auto=0)
    _task(conn3, attivo3, "il più vecchio", updated_at=_giorni_fa(40))
    _task(conn3, attivo3, "il meno vecchio", updated_at=_giorni_fa(25))
    stagnanti3 = [p for p in proposte.calcola(conn3, limite=20) if p["motivo"] == "task_stagnante"]
    prova("con due task fermi ne esce una sola", len(stagnanti3) == 1, str(stagnanti3))
    if stagnanti3:
        prova("ed è la più vecchia",
              "più vecchio" in stagnanti3[0]["testo"], str(stagnanti3))

    # progetto nascosto: niente proposta anche con un task fermo da mesi
    conn4 = _conn()
    nascosto = _progetto(conn4, "nascosto", name="Nascosto", auto=0, hidden=1)
    _task(conn4, nascosto, "sepolto", updated_at=_giorni_fa(99))
    lista4 = proposte.calcola(conn4, limite=20)
    prova("un task su un progetto nascosto non genera la proposta",
          not any(p["motivo"] == "task_stagnante" for p in lista4), str(lista4))

    # progetto non attivo (in pausa): stessa cosa
    conn5 = _conn()
    in_pausa = _progetto(conn5, "in-pausa", name="In pausa", auto=0, status="in pausa")
    _task(conn5, in_pausa, "fermo apposta", updated_at=_giorni_fa(99))
    lista5 = proposte.calcola(conn5, limite=20)
    prova("un task su un progetto non attivo non genera la proposta",
          not any(p["motivo"] == "task_stagnante" for p in lista5), str(lista5))


def _prova_azione_task_stagnante_eseguibile(prova):
    """L'azione della proposta task_stagnante deve essere uno dei tipi che
    jarvis._esegui_proposta sa davvero eseguire (vai/rilancia/manda): non un
    tipo nuovo ('archivia') che nessuno gestisce e che jarvis.esegui('fallo')
    risponderebbe con un generico 'Fatto.' senza fare niente.

    Il tipo 'manda' fa davvero partire un agente (cantiere.avvia apre un
    processo `claude`/`codex`): qui si sostituisce con un segnaposto, così la
    prova controlla che la proposta arrivi al ramo giusto di jarvis senza
    lanciare un agente vero dentro la suite.
    """
    from plancia import jarvis, proposte

    TIPI_ESEGUITI = {"vai", "rilancia", "manda"}

    conn = _conn()
    attivo = _progetto(conn, "stagnante-jarvis", name="StagnanteJarvis", auto=0)
    _task(conn, attivo, "task da archiviare", updated_at=_giorni_fa(30))
    lista = [p for p in proposte.calcola(conn, limite=20) if p["motivo"] == "task_stagnante"]
    prova("la proposta task_stagnante esiste per verificarne l'azione", len(lista) == 1, str(lista))
    if not lista:
        return
    azione = lista[0].get("azione") or {}
    prova("l'azione della proposta task_stagnante è di un tipo che jarvis esegue",
          azione.get("tipo") in TIPI_ESEGUITI, str(azione))

    proposte.salva(conn, lista)
    chiamate = []
    originale = jarvis.cantiere.avvia
    jarvis.cantiere.avvia = lambda conn, titolo, **kw: (
        chiamate.append((titolo, kw)) or {"run": 999})
    try:
        esito = jarvis.esegui("fallo", lang="it", conn=conn)
    finally:
        jarvis.cantiere.avvia = originale
    prova("jarvis.esegui('fallo') su task_stagnante non torna la risposta generica 'Fatto.'",
          esito.get("risposta") != "Fatto.", str(esito))
    prova("jarvis.esegui('fallo') su task_stagnante manda davvero un agente (cantiere.avvia)",
          len(chiamate) == 1, str(chiamate))


def _prova_recap_area(prova):
    """Il recap cita l'area del progetto quando c'è, sia nel testo a
    modelli (render_template) sia in quello che finisce nel JSON per Claude
    (_compact): '<progetto> (<area>)'."""
    from plancia import recap

    dati_con_area = {
        "per_progetto": [{"progetto": "VR Lab", "area": "Ricerca", "sessioni": 2,
                          "token": 100, "titoli": ["una sessione"]}],
        "sessioni": [{"title": "una sessione", "out_tokens": 100}],
        "sessioni_ieri": 0,
        "commit": [],
        "task_chiusi": [], "task_aperti": [], "task_scaduti": [],
        "post_pubblicati": [], "post_coda": [],
        "prossimi_passi": [{"name": "VR Lab", "area": "Ricerca", "next_action": "fai qualcosa"}],
        "progetti_fermi": [{"name": "AI Bridge", "area": "Ricerca", "last_activity": "2026-01-01"}],
        "proposte": [],
    }
    testo_it = recap.render_template(dati_con_area, "it")
    prova("il recap (scritto) cita l'area di un progetto lavorato",
          "VR Lab (Ricerca)" in testo_it, testo_it)
    prova("il recap (scritto) cita l'area anche per i progetti fermi",
          "AI Bridge (Ricerca)" in testo_it, testo_it)

    compatto = recap._compact({**dati_con_area, "giorno": "2026-09-16",
                               "sessioni_ieri": 0, "token_giorno": 100,
                               "task_chiusi": [], "task_creati": [], "task_aperti": [],
                               "task_scaduti": [], "post_pubblicati": [], "post_coda": []})
    prova("il recap (per Claude, 'parlato') cita l'area nel lavoro per progetto",
          compatto["lavoro_per_progetto"][0]["progetto"] == "VR Lab (Ricerca)", str(compatto))
    prova("il recap (per Claude) cita l'area nei prossimi passi",
          compatto["prossimi_passi"][0]["progetto"] == "VR Lab (Ricerca)", str(compatto))
    prova("il recap (per Claude) cita l'area nei progetti fermi",
          compatto["progetti_fermi"] == ["AI Bridge (Ricerca)"], str(compatto))

    dati_senza_area = {**dati_con_area,
                       "per_progetto": [{"progetto": "Solitario", "area": None, "sessioni": 1,
                                        "token": 10, "titoli": []}],
                       "prossimi_passi": [], "progetti_fermi": []}
    testo_senza = recap.render_template(dati_senza_area, "it")
    prova("senza area non compaiono parentesi accanto al nome", "(" not in testo_senza, testo_senza)


def _prova_recap_collect_area(prova):
    """recap.collect() porta davvero l'area dalle JOIN nuove su un database
    vero (non un dict scritto a mano che salta collect() del tutto): un
    padre impostato con slot.set_parent, e recap.build(engine='template')
    che deve nominarlo nel testo prodotto."""
    from plancia import recap, slot

    conn = _conn()
    _progetto(conn, "harbour", name="Harbour", auto=0)
    figlio = _progetto(conn, "lumen", name="Lumen", auto=0)
    slot.set_parent(conn, "lumen", "harbour", "gk1")
    conn.execute("UPDATE projects SET next_action=? WHERE id=?", ("fai qualcosa", figlio))
    conn.commit()

    for lang in ("it", "en"):
        esito = recap.build(conn, lang=lang, engine="template", cache=False)
        prova(f"recap.build (engine=template, {lang}) porta l'area dal collect() vero",
              "Lumen (Harbour)" in esito["testo"], esito["testo"])

    # senza padre: nessuna area, quindi nessuna parentesi per quel progetto
    conn2 = _conn()
    solo = _progetto(conn2, "solo", name="Solo", auto=0)
    conn2.execute("UPDATE projects SET next_action=? WHERE id=?", ("fai altro", solo))
    conn2.commit()
    esito2 = recap.build(conn2, lang="it", engine="template", cache=False)
    prova("recap.build senza padre non aggiunge parentesi al progetto",
          "Solo (" not in esito2["testo"], esito2["testo"])


def _prova_niente_em_dash(prova):
    """La regola di casa sui testi pubblici, guardata sui testi PRODOTTI
    (non sui dizionari sorgente, già puliti prima di questo lotto): il
    briefing corto, il recap a modelli in it/en, e le proposte formattate
    nelle tre lingue che questo lotto tocca."""
    from plancia import briefing, proposte, recap

    conn = _conn()
    p1 = _progetto(conn, "em-uno", name="Progetto Uno", auto=0)
    conn.execute("UPDATE projects SET next_action=? WHERE id=?", ("passo uno", p1))
    _task(conn, p1, "task vecchio e fermo", updated_at=_giorni_fa(30))
    conn.commit()

    testo_briefing = briefing.build(conn, esteso=False)
    prova("niente em dash nel briefing corto prodotto", "—" not in testo_briefing, testo_briefing)

    dati = recap.collect(conn)
    for lang in ("it", "en"):
        testo_recap = recap.render_template(dati, lang)
        prova(f"niente em dash nel recap a modelli prodotto ({lang})",
              "—" not in testo_recap, testo_recap)

    for lang in ("it", "en", "es"):
        lista = proposte.calcola(conn, lang=lang, limite=20)
        con_em_dash = [p["testo"] for p in lista if "—" in p["testo"]]
        prova(f"niente em dash nelle proposte formattate prodotte ({lang})",
              not con_em_dash, str(con_em_dash))


def esegui(prova) -> None:
    _prova_briefing_aree(prova)
    _prova_padre_non_duplicato(prova)
    _prova_altri_tanti_nomi(prova)
    _prova_area_comprimibile(prova)
    _prova_gruppi_per_chiave_non_nome(prova)
    _prova_niente_prefisso_duplicato(prova)
    _prova_proposta_task_stagnante(prova)
    _prova_azione_task_stagnante_eseguibile(prova)
    _prova_recap_area(prova)
    _prova_recap_collect_area(prova)
    _prova_niente_em_dash(prova)


if __name__ == "__main__":
    import os
    import sys
    import tempfile
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-briefing-aree-"))
    os.environ["PLANCIA_HOME"] = str(CASA)

    falliti = []
    passati = 0

    def prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print(f"  ok   {nome}")
        else:
            falliti.append(nome)
            print(f"  NO   {nome} {dettaglio}")

    print(f"archivio di prova: {CASA}\n")
    esegui(prova)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
