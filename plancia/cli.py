"""Riga di comando di Plancia."""

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime, timedelta, timezone

from . import __version__, actions, briefing, config, store


def cmd_serve(args):
    from . import api
    api.serve(port=args.port, open_browser=args.open, sync_first=not args.no_sync)


def cmd_sync(args):
    from . import ingest
    last = [""]

    def progress(msg):
        if msg != last[0]:
            last[0] = msg
            sys.stderr.write(f"\r\x1b[K{msg}")
            sys.stderr.flush()

    res = ingest.sync(full=args.full, progress=progress, skip_git=args.skip_git,
                      modo=args.modo, ricalcola=args.riattribuisci)
    sys.stderr.write("\r\x1b[K")
    for key, value in res.items():
        print(f"{key}: {value}")


def cmd_mcp(args):
    from . import mcp
    return mcp.main()


def cmd_briefing(args):
    print(briefing.build(project=args.project) if args.project else briefing.write_cache())


def cmd_recap(args):
    from . import recap, voice
    data = recap.build(day=args.day, lang=args.lang, engine=args.engine)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return
    print(data["testo"])
    if args.notify:
        cmd_notifica("Plancia", data["testo"])
    if args.speak or (args.daily and config.load_config().get("riepilogo_voce")):
        info = voice.parla(data["testo"], data["lingua"], args.voce, attendi=not args.background)
        print(f"\n[voce: {info['motore']} · {info['file']}]", file=sys.stderr)


def cmd_notifica(titolo, testo):
    import subprocess
    testo = testo.replace('"', "'")[:220]
    subprocess.run(["osascript", "-e",
                    f'display notification "{testo}" with title "{titolo}"'],
                   capture_output=True, timeout=20)


def cmd_ask(args):
    from . import recap, voice
    domanda = " ".join(args.domanda)
    risposta = recap.answer(domanda, args.lang)
    print(risposta)
    if args.speak:
        voice.parla(risposta, recap.lang_or_default(args.lang), args.voce,
                    attendi=not args.background)


def cmd_jarvis(args):
    from . import jarvis, voice
    frase = " ".join(args.frase)
    esito = jarvis.esegui(frase, args.lang)
    print(f"[{esito['tipo']}] {esito['risposta']}")
    if esito.get("azione"):
        print(f"  azione: {esito['azione']}")
    if args.speak and not esito.get("muto"):
        voice.parla(esito["risposta"], esito.get("lingua", "it"), attendi=True)


def cmd_say(args):
    from . import recap, voice
    testo = " ".join(args.testo)
    info = voice.parla(testo, recap.lang_or_default(args.lang), args.voce, attendi=True)
    print(f"[{info['motore']}] {info['file']}")


def cmd_voice(args):
    from . import voice
    if args.azione == "stato":
        print(json.dumps(voice.stato(), ensure_ascii=False, indent=2))
    elif args.azione == "voci":
        for nome, loc in voice.voci_sistema():
            print(f"{loc}  {nome}")
    elif args.azione == "prova":
        from . import recap
        lang = recap.lang_or_default(args.lang)
        frase = {"it": "Plancia è pronta. Ti leggo il riepilogo quando vuoi.",
                 "en": "Plancia is ready. I can read you the recap whenever you want.",
                 "es": "Plancia está lista. Te leo el resumen cuando quieras."}.get(
                     lang, "Plancia is ready.")
        info = voice.parla(frase, lang, args.voce, attendi=True)
        print(f"[{info['motore']} · {voice.voce_per(lang)}] ok")


def cmd_task(args):
    conn = store.connect()
    store.init_db(conn)
    try:
        if args.azione == "add":
            task = actions.task_add(conn, " ".join(args.testo), project=args.project,
                                    priority=args.priority, due=args.due)
            print(f"#{task['id']} {task['title']}")
        elif args.azione == "done":
            task = actions.task_update(conn, int(args.testo[0]), status="fatto")
            print(f"chiuso #{task['id']} {task['title']}")
        else:
            rows = actions.tasks_list(conn, args.status, args.project, 100)
            if not rows:
                print("nessun task")
            for t in rows:
                mark = {"fatto": "×", "in corso": "»", "bloccato": "!"}.get(t["status"], "·")
                proj = f"  [{t['project']}]" if t["project"] else ""
                due = f"  scade {t['due']}" if t["due"] else ""
                print(f"{mark} #{t['id']:<4} {t['title']}{proj}{due}")
    finally:
        conn.close()


def cmd_lavagna(args):
    from . import lavagna
    conn = store.connect()
    store.init_db(conn)
    try:
        c = lavagna.conteggi(conn)
        print("  " + "   ".join(f"{f}: {d.get('aperti', 0)} aperti" for f, d in c.items()))
        print()
        for v in lavagna.elenco(conn, args.stato, args.fonte, 100):
            prog = f"  [{v['progetto']}]" if v["progetto"] else ""
            print(f"{v['fonte']:<8} {v['stato']:<9} {v['titolo'][:64]}{prog}")
    finally:
        conn.close()


def cmd_manda(args):
    from . import cantiere, riprendi
    # LOTTO-L3-RIPRENDI-UI punto 3: "manda" resta un alias di "riprendi
    # --background" per un rilascio, non sparisce di colpo sotto chi lo ha
    # già in uno script. L'avviso va su stderr, cosi' uno script che legge
    # solo stdout (es. `plancia manda ... | qualcosa`) non lo vede mescolato
    # all'output vero.
    print("«plancia manda» e' un alias di «plancia riprendi --background»: "
          "sparira' in un prossimo rilascio.", file=sys.stderr)
    conn = store.connect()
    store.init_db(conn)
    try:
        sessione = None
        if args.task:
            # Stessa logica del ramo background di cmd_riprendi: se il task
            # ha già una sessione viva o chiusa, il lancio la riprende
            # (--fork-session) invece di ripartire da un prompt scritto da
            # zero. Senza questo, "manda" e "riprendi --background" sullo
            # stesso task avrebbero comportamenti diversi, e non sarebbe più
            # un vero alias.
            task = actions.task_get(conn, args.task)
            if task:
                s = riprendi.stato(conn, task)
                sessione = riprendi.sessione_da_riprendere(s)
        r = cantiere.avvia(conn, " ".join(args.titolo), progetto=args.progetto,
                           istruzioni=args.istruzioni or "", agente=args.agente,
                           modo=args.modo, task_id=args.task, attendi=args.attendi,
                           sessione=sessione)
        print(f"lancio #{r['run']} · {r['agente']} · {r['modo']} · {r['cwd']}")
        if args.attendi:
            d = cantiere.dettaglio(conn, r["run"])
            print(f"\n[{d['stato']}] {d['esito'][:600]}")
        else:
            print("gira in sottofondo: `plancia lanci` per vedere com'è andata")
    finally:
        conn.close()


def cmd_riprendi(args):
    from . import cantiere, riprendi
    conn = store.connect()
    store.init_db(conn)
    try:
        if args.annulla:
            # LOTTO-L3-RITOCCO punto 8: prima si prendeva `Path(args.annulla).stem`
            # (pensato per chi incolla un percorso di log), ma un batch è solo un
            # nome ("backfill-<timestamp>"), non un file: `.stem` su un batch che
            # contenesse un punto lo avrebbe troncato in silenzio, e riscriveva la
            # stessa regola di validità di `riprendi._batch_valido` invece di
            # riusarla. Ora la stringa passa così com'è, e viene rifiutata subito
            # se non è un batch valido (vuoto, o con virgole/spazi: non sarebbe
            # annullabile).
            if not riprendi._batch_valido(args.annulla):
                print(f"batch non valido: {args.annulla!r} (vuoto, o con virgole/spazi)")
                return 1
            n = riprendi.annulla(conn, args.annulla)
            print(f"rimessi: {n}")
            return
        if args.backfill:
            batch = "backfill-" + store.now()
            esito = riprendi.backfill(conn, batch, secco=args.secco)
            print(f"batch {batch}: trovati {esito['trovati']}, non trovati {esito['non_trovati']}"
                  + (" (a secco: non ha scritto niente)" if args.secco else ""))
            return
        if not args.id:
            print("serve un id di task, oppure --backfill o --annulla BATCH")
            return 1
        task = actions.task_get(conn, args.id)
        if not task:
            print(f"task {args.id} inesistente")
            return 1
        s = riprendi.stato(conn, task)
        print(f"#{task['id']} {task['title']}  →  {s['stato']}: {s['motivo']}")
        if args.dove:
            print(f"  cwd: {s.get('cwd') or '(nessuna)'}")
        if args.apri:
            esito = riprendi.apri(task, conn)
            if esito.get("stato") == "viva":
                print(f"  messaggio (da mettere negli appunti a mano): {esito['messaggio']}")
            else:
                print(f"  lanciato: {esito.get('riga', '')}")
                if esito.get("errore"):
                    print(f"  attenzione: {esito['errore']}")
            return
        if args.background:
            sessione = riprendi.sessione_da_riprendere(s)
            esito = cantiere.avvia(
                conn, task.get("title") or "", "", task.get("project_key"),
                args.istruzioni or "", s.get("agent") or task.get("agent") or "claude",
                args.scrive, None, task["id"], sessione=sessione)
            print(f"lancio #{esito['run']} · {esito['agente']} · {esito['modo']} · {esito['cwd']}")
            return
        argv = riprendi.comando(task, s, conn)
        if argv:
            print("  comando: " + " ".join(argv))
        print("  messaggio: " + riprendi.messaggio(task))
    finally:
        conn.close()


def cmd_lanci(args):
    from . import cantiere
    conn = store.connect()
    store.init_db(conn)
    try:
        if args.id:
            d = cantiere.dettaglio(conn, args.id)
            if not d:
                return print("lancio inesistente")
            print(f"#{d['id']} {d['agente']} {d['modo']} {d['stato']}  {d['cwd']}")
            print(f"log: {d['log']}")
            print()
            print(d["esito"] or "(nessun esito)")
            return
        for r in cantiere.elenco(conn, 20):
            durata = ""
            if r["inizio"] and r["fine"]:
                durata = f"  {r['fine'][11:19]}"
            print(f"#{r['id']:<4} {r['agente']:<7} {r['modo']:<9} {r['stato']:<10}"
                  f"{(r['task'] or r['prompt'][:50]).splitlines()[0][:50]}{durata}")
    finally:
        conn.close()


def cmd_eventi(args):
    from . import eventi
    for e in eventi.leggi(args.dopo, args.tipo, args.limite):
        # Il progetto e l'agente sono la metà del valore di un evento: senza,
        # chi legge deve andare a cercarsi da solo di cosa si parlava.
        coda = " · ".join(x for x in (e.get("progetto"),
                                      (e.get("dati") or {}).get("agente")) if x)
        print(f"{e['ts'][:19]}  {e['tipo']:<22} {e['titolo'][:46]:<46}  "
              f"{coda:<24}  {e['id']}")


def cmd_riordina(args):
    from pathlib import Path
    from . import riordina
    conn = store.connect()
    store.init_db(conn)
    try:
        if args.proponi:
            percorso, righe = riordina.proponi(conn, dove=args.dove)
            conteggi = {}
            for r in righe:
                conteggi[r["regola"]] = conteggi.get(r["regola"], 0) + 1
            print(f"scritto: {percorso}")
            for regola in ("path", "repo", "prefisso"):
                if conteggi.get(regola):
                    print(f"  {regola}: {conteggi[regola]}")
            print(f"  nessuna: {conteggi.get('nessuna', 0)}")
        elif args.mostra:
            try:
                righe = riordina.carica(args.mostra)
            except FileNotFoundError:
                print(f"file non trovato: {args.mostra}")
                # Difetto minore segnalato dal tester di L1-RIORDINA: usciva
                # con 0 (successo) anche quando il file non c'era. `main()`
                # fa `args.func(args) or 0`: senza un valore vero qui, None
                # diventa 0 e uno script che controlla l'uscita non si accorge
                # che il comando non ha fatto niente.
                return 1
            print(riordina.tabella(righe) if righe else "nessuna riga")
        elif args.applica:
            try:
                esito = riordina.applica(conn, args.applica,
                                         resto_in_cartelle_viste=args.resto_in_cartelle_viste)
            except FileNotFoundError:
                print(f"file non trovato: {args.applica}")
                return 1
            print(f"applicate: {esito['applicate']}  rifiutate: {esito['rifiutate']}")
            for r in esito["dettagli_rifiutate"]:
                print(f"  rifiutata {r['chiave']} -> {r['padre']}: {r['motivo']}")
        elif args.annulla:
            # Accetta sia il nome del batch (mappa4) sia il percorso del file
            # (mappa4.json, o l'intero percorso di --dove): lo stem è quello
            # che --applica ha usato come batch, ma è più naturale ripassare
            # d'istinto lo stesso file o nome che si è appena visto.
            n = riordina.annulla(conn, Path(args.annulla).stem)
            print(f"rimesse: {n}")
    finally:
        conn.close()


def cmd_projects(args):
    conn = store.connect()
    store.init_db(conn)
    try:
        rows = conn.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id "
            "AND t.status IN ('aperto','in corso','bloccato')) AS task_aperti "
            "FROM projects p WHERE hidden=0 ORDER BY pinned DESC, priority, last_activity DESC"
        ).fetchall()
        for p in rows:
            print(f"{p['status'][:8]:<9} {p['key']:<22} {p['name'][:38]:<39} "
                  f"{p['task_aperti'] or '':<3} {(p['last_activity'] or '')[:10]}")
    finally:
        conn.close()


def cmd_sessioni(args):
    """Il catalogo delle sessioni, raggruppato per il progetto vero.

    Il progetto e' quello su cui la sessione ha lavorato, che non e' sempre
    quello della cartella da cui e' stata aperta: la tilde in fondo alla riga
    segna le sessioni attribuite guardando i percorsi che hanno toccato.
    """
    conn = store.connect()
    store.init_db(conn)
    try:
        sql = ("SELECT s.session_id, s.started_at, COALESCE(s.agent,'claude') AS agente, "
               "s.n_user, s.first_prompt, s.title, s.dedotto_da, s.dir_dedotta, "
               "COALESCE(p.name, 'Senza progetto') AS progetto "
               "FROM sessions s LEFT JOIN projects p ON p.id=s.project_id WHERE 1=1")
        params = []
        if not args.tutte:
            sql += " AND " + store.visibile("s")
        if args.progetto:
            riga = store.get_project(conn, args.progetto)
            if riga is None:
                return print(f"nessun progetto che assomigli a «{args.progetto}»")
            sql += " AND s.project_id=?"
            params.append(riga["id"])
        if args.giorni:
            limite = (datetime.now(timezone.utc) - timedelta(days=args.giorni)
                      ).strftime("%Y-%m-%dT%H:%M:%SZ")
            sql += " AND s.started_at > ?"
            params.append(limite)
        righe = conn.execute(sql + " ORDER BY s.started_at DESC", params).fetchall()
        if not righe:
            return print("nessuna sessione")

        gruppi = {}
        for r in righe:
            gruppi.setdefault(r["progetto"], []).append(r)
        dedotte = 0
        for progetto, elenco in sorted(
                gruppi.items(), key=lambda kv: kv[1][0]["started_at"] or "", reverse=True):
            print(f"\n{progetto}  ({len(elenco)})")
            for r in elenco:
                testo = " ".join((r["title"] or r["first_prompt"] or "").split())
                if len(testo) > 70:
                    testo = testo[:69] + "…"
                marchio = ""
                if r["dedotto_da"] == "percorsi":
                    marchio, dedotte = " ~", dedotte + 1
                print(f"  {(r['started_at'] or '')[:10]}  {r['agente']:<7} "
                      f"{r['session_id'][:8]}  {r['n_user'] or 0:>4}  "
                      f"{testo:<70}{marchio}".rstrip())
        print(f"\n{len(righe)} sessioni"
              + (f", {dedotte} col progetto dedotto dai percorsi (~)" if dedotte else ""))
        if not args.tutte:
            print("le chiamate interne e le sessioni temporanee sono fuori: --tutte le mostra")
    finally:
        conn.close()


def _colora(frammento: str, tinta: bool) -> str:
    """I marcatori di FTS5 diventano grassetto, o spariscono se non c'è un tty."""
    frammento = " ".join((frammento or "").split())
    if not tinta:
        return frammento.replace("«", "").replace("»", "")
    return frammento.replace("«", "\033[1;33m").replace("»", "\033[0m")


def cmd_search(args):
    """Cerca nei turni prima che nelle schede, e stampa dove riaprire.

    Il percorso e la riga escono nel formato `file:riga` di proposito: si
    incollano in un editor e si apre il punto esatto, che è la differenza fra
    una ricerca e un riassunto.
    """
    from . import turni
    conn = store.connect()
    store.init_db(conn)
    tinta = sys.stdout.isatty()
    q = " ".join(args.query)
    try:
        trovati = turni.cerca(conn, q, limit=args.limit, progetto=args.project)
        for t in trovati:
            chi = "tu" if t["ruolo"] == "user" else "claude"
            testa = f"{chi:<7} {t['progetto'] or '-'}"
            if tinta:
                testa = f"\033[2m{testa}\033[0m"
            print(testa)
            print(f"        {_colora(t['frammento'], tinta)}")
            dove = f"{t['percorso']}:{t['riga']}"
            print(f"        \033[2m{dove}\033[0m" if tinta else f"        {dove}")
            print()

        if args.project and not trovati:
            noti = ", ".join(p["progetto"] for p in turni.progetti(conn)[:8])
            print(f"nessun turno in «{args.project}». Etichette note: {noti}")
            return

        # Le schede (task, commit, memorie) non sanno del filtro progetto, e
        # stamparle lo stesso farebbe sembrare che il filtro non abbia funzionato.
        if args.project:
            return
        schede = store.search(conn, q, 5)
        if schede:
            if trovati:
                print("nelle schede:")
            for hit in schede:
                print(f"{hit['kind']:<10} {(hit['title'] or '')[:70]}")
                if hit.get("snip"):
                    print(f"           {_colora(hit['snip'], tinta)[:100]}")
        elif not trovati:
            print("nessun risultato")
    finally:
        conn.close()


def cmd_ricorda(args):
    """Mostra cosa il richiamo direbbe a Claude su questa frase, e perché.

    Serve a fidarsi. Il richiamo scrive nel contesto senza chiedere il permesso
    e senza farsi vedere: se non c'è un modo di guardarlo da fuori, l'unico modo
    di accorgersi che sbaglia è insospettirsi delle risposte, che è tardi.
    """
    from . import richiamo
    conn = richiamo.apri_ro()
    if conn is None:
        print("archivio non ancora creato: lancia `plancia sync`")
        return
    tinta = sys.stdout.isatty()
    testo = " ".join(args.testo)
    try:
        if args.tutto:
            trovati = richiamo.cerca(conn, testo, soglia=0.0, limite=12,
                                     tipi=None if args.progetti else richiamo.TIPI_TRASVERSALI)
        else:
            trovati = richiamo.cerca(conn, testo, escludi_scope=richiamo.cartella_sessione(os.getcwd()),
                                     tipi=None if args.progetti else richiamo.TIPI_TRASVERSALI)
    finally:
        conn.close()

    termini = richiamo.parole(testo)
    if len(termini) < 2:
        print("frase troppo corta o troppo comune: il richiamo tace")
        return
    if tinta:
        print(f"\033[2mcercate: {' '.join(termini)}\033[0m")
    else:
        print(f"cercate: {' '.join(termini)}")

    if not trovati:
        print(f"\nniente sopra la soglia ({richiamo.SOGLIA}): il richiamo tace.")
        print("`--tutto` mostra anche quello che ha scartato.")
        return

    print()
    for t in trovati:
        segno = "→" if t["punteggio"] >= richiamo.SOGLIA else " "
        testa = f"{segno} {t['punteggio']:6.2f}  {t['nome']}"
        print(f"\033[1m{testa}\033[0m" if tinta else testa)
        riga = f"         {t['tipo']} · scritta in {richiamo._dove(t['scope'])}"
        print(f"\033[2m{riga}\033[0m" if tinta else riga)
        if t["descrizione"]:
            print(f"         {t['descrizione'][:100]}")
    if not args.tutto:
        print(f"\n{len(trovati)} in contesto. `--tutto` mostra anche gli scartati.")


def cmd_esporta(args):
    """Scrive il cervello in un file solo, da consegnare a mano al telefono.

    Non manda niente da nessuna parte: fa un file e ti dice dov'è. Il passaggio
    al telefono lo fai tu, con AirDrop o dal Wi-Fi di casa, e in tutt'e due i
    casi il file non tocca internet.
    """
    from pathlib import Path
    from . import esporta as _esp
    dove = Path(args.dove).expanduser() if args.dove else (
        config.DATA_DIR / "memoria.html")
    percorso, peso, quante = _esp.esporta(dove)
    print(f"{quante} memorie · {peso / 1024:.0f} KB")
    print(percorso)
    print("\nsul telefono: AirDrop questo file, poi aprilo e «Aggiungi a schermata Home».")
    print("vive lì e non chiede niente alla rete. per aggiornarlo, rifallo e rimandalo.")
    if args.apri:
        import subprocess
        subprocess.run(["open", "-R", str(percorso)], check=False)


def cmd_init(args):
    from . import init_seed, ingest
    progetti = init_seed.raccogli()
    for p in sorted(progetti.values(), key=lambda x: x["key"]):
        pezzi = ", ".join(f"{k}: {len(v)}" for k, v in p["links"].items())
        print(f"  {p['key']:<28} {pezzi}")
    print(init_seed.scrivi(progetti, forza=args.force))
    if not args.no_sync:
        print("rileggo le fonti…")
        res = ingest.sync()
        print(", ".join(f"{k} {v}" for k, v in res.items()))


def cmd_install(args):
    from . import setup_claude
    for line in setup_claude.install_all():
        print("·", line)
    print("\nOra: `plancia sync` e poi `plancia serve --open`.")
    print("Le sessioni di Claude Code già aperte vanno riavviate per vedere i tool plancia_*.")


def cmd_uninstall(args):
    from . import setup_claude
    for line in setup_claude.uninstall_all():
        print("·", line)


def cmd_autostart(args):
    from . import setup_claude
    print(setup_claude.autostart_on() if args.stato == "on" else setup_claude.autostart_off())


def cmd_daily(args):
    from . import setup_claude
    if args.stato == "off":
        print(setup_claude.recap_daily_off())
        return
    print(setup_claude.recap_daily_on(args.ora, voce=args.voce))


def cmd_flusso(args):
    """Da dove arrivano i dati, quanto sono freschi e quanto costa aggiornarli."""
    from . import codex, ingest
    conn = store.connect()
    store.init_db(conn)
    try:
        drive = ingest.drive_root()
        fonti = [
            ("sessioni Claude", str(config.CLAUDE_PROJECTS / "*/*.jsonl"), "caldo",
             conn.execute("SELECT COUNT(*) FROM sessions WHERE agent='claude'").fetchone()[0]),
            ("sessioni Codex", str(codex.SESSIONI), "caldo",
             conn.execute("SELECT COUNT(*) FROM sessions WHERE agent='codex'").fetchone()[0]),
            ("coda degli hook", str(config.QUEUE_FILE), "caldo",
             conn.execute("SELECT COUNT(*) FROM events WHERE source='hook'").fetchone()[0]),
            ("memoria", str(config.CLAUDE_PROJECTS / "*/memory"), "freddo",
             conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]),
            ("skill e plugin", str(config.CLAUDE_SKILLS), "freddo",
             conn.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0]),
            ("GitHub", "gh repo list", "freddo",
             conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0]),
            ("git locale", ", ".join(config.load_config().get("code_roots", [])) +
             (f", {drive}" if drive else ""), "freddo",
             conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]),
        ]
        print("FONTE                DOVE                                     GIRO     RIGHE")
        for nome, dove, giro, n in fonti:
            print(f"{nome:<20} {dove[-40:]:<40} {giro:<8} {n:>6}")
        print()
        print("  fonti → sync → SQLite → briefing.md, riepilogo, API, voce")
        print()
        for chiave, etichetta in (("last_sync_caldo", "ultimo giro caldo"),
                                  ("last_sync_freddo", "ultimo giro freddo")):
            print(f"  {etichetta}: {store.get_meta(conn, chiave, 'mai')}")
        print(f"  riepilogo in cache: {'sì' if store.get_meta(conn, 'recap_testo') else 'no'}")
        from . import agente
        print(f"  processo Claude caldo: {agente.stato() or 'nessuno'}")
    finally:
        conn.close()


def cmd_esclusi(args):
    from . import esclusi
    cfg = config.load_config_verificata()
    if not cfg.get("esclusi_ok", True):
        print(f"config.json non valido: {cfg.get('esclusi_errore')}")
        print("fail-closed: nessun conteggio, nessuna pulizia — i dati non sono affidabili "
              "finché il file non torna a leggersi e a validare.")
        return
    cartelle = cfg.get("cartelle_escluse") or []
    sessioni = cfg.get("sessioni_escluse") or []
    print("cartelle escluse:")
    for c in cartelle:
        print(f"  {c}")
    if not cartelle:
        print("  (nessuna)")
    print("sessioni escluse:")
    for s in sessioni:
        print(f"  {s}")
    if not sessioni:
        print("  (nessuna)")

    conn = store.connect()
    store.init_db(conn)
    try:
        escl = esclusi.carica(cfg, conn=conn)
        conteggi = esclusi.conta(conn, escl) if args.prova else esclusi.purga(conn, escl)
    finally:
        conn.close()
    etichetta = "righe che la pulizia toglierebbe" if args.prova else "righe tolte"
    print(f"{etichetta}:")
    if not conteggi:
        print("  (niente da fare: nessuna cartella o sessione esclusa)")
    for chiave, n in conteggi.items():
        print(f"  {chiave}: {n}")


def cmd_guardiano(args):
    """Il registro e lo stato del guardiano dei compartimenti (sola lettura:
    non scrive config.json ne' il registro)."""
    dati = str(config.DATA_DIR)
    try:
        from . import compartimenti
    except Exception as exc:  # noqa: BLE001 - il modulo non si importa: lo diciamo
        # Lo stesso guasto che spegne l'hook (`guardiano-non-parte`): il registro si
        # legge a mano, senza il modulo, e si mostrano le righe di quel guasto.
        print(f"ATTENZIONE: plancia/compartimenti.py non si importa "
              f"({type(exc).__name__}: {exc}): il guardiano non parte, i "
              "compartimenti non sono protetti")
        righe = []
        try:
            with open(os.path.join(dati, "guardiano.log"), "r", encoding="utf-8") as f:
                for linea in f:
                    try:
                        d = json.loads(linea)
                    except ValueError:
                        continue
                    if isinstance(d, dict) and d.get("esito") == "guardiano-non-parte":
                        righe.append(d)
        except OSError:
            pass
        for d in righe[-3:]:
            print("  %s  %s" % (str(d.get("ts", "?")).replace("T", " ").rstrip("Z"),
                                d.get("motivo") or ""))
        return 1
    if args.registro is not None:
        righe = compartimenti.leggi_registro(dati, args.registro)
        if not righe:
            print("(registro vuoto)")
        for r in righe:
            print("%s  %-14s  [%s] %s  %s  %s" % (
                str(r.get("ts", "?")).replace("T", " ").rstrip("Z"),
                r.get("esito", "?"), r.get("compartimento") or "-",
                r.get("strumento") or "-", r.get("bersaglio") or "-",
                r.get("motivo") or ""))
        return
    st = compartimenti.stato(dati)
    print(f"modalita: {st['modo']}")
    if st["non_parte"]["righe"]:
        u = st["non_parte"]["ultima"] or {}
        print("ATTENZIONE: il guardiano NON PARTE (%d volte nelle ultime 24 ore, "
              "ultima %s: %s): non protegge nessuna sessione finche' non si ripara"
              % (st["non_parte"]["righe"],
                 str(u.get("ts", "?")).replace("T", " ").rstrip("Z"),
                 u.get("motivo") or ""))
    if st["config"] == "rotta":
        print(f"{st['errore']}: "
              + ("uso l'ultima config valida" if st["usa_copia"]
                 else "nessuna copia valida, solo-registro per tutti"))
    print("compartimenti:")
    if not st["compartimenti"]:
        print("  (nessuno)")
    for c in st["compartimenti"]:
        if c["nome"] == "predefinito":
            print(f"  predefinito: {c['divieti']} divieti, {c['comandi_vietati']} "
                  f"comandi vietati, manifesto {'si' if c['manifesto'] else 'no'}")
        else:
            print(f"  {c['nome']}: {c['cartelle']} cartelle, {c['sessioni']} sessioni, "
                  f"{c['drive_ids']} id Drive")
    r = st["registro_24h"]
    print(f"registro, ultime 24 ore: {r['negato'] + r['avrebbe-negato'] + r['altro']} righe "
          f"({r['negato']} negate, {r['avrebbe-negato']} avrebbe-negato, {r['altro']} note)")


def cmd_doctor(args):
    from . import setup_claude
    for line in setup_claude.doctor():
        print(line)


def cmd_open(args):
    port = config.load_config().get("port", config.DEFAULT_PORT)
    webbrowser.open(f"http://127.0.0.1:{port}")


def cmd_config(args):
    if args.chiave and args.valore is not None:
        # un config.json che esiste e non si legge non si riscrive: load_config()
        # tornerebbe i default e la scrittura cancellerebbe guardiano,
        # compartimenti ed esclusioni (vedi config.save_config)
        errore = config.config_illeggibile()
        if errore:
            print(f"config: {errore}: non scrivo niente, riparalo a mano",
                  file=sys.stderr)
            return 2
    cfg = config.load_config()
    if args.chiave:
        value = args.valore
        if value is not None:
            try:
                value = json.loads(value)
            except Exception:
                pass
            if args.chiave == "guardiano":
                # Un valore fuori dai tre modi si degrada in silenzio (il
                # guardiano lo tratta come config rotta): meglio rifiutarlo qui.
                from .compartimenti import MODI
                modo = value.strip().lower() if isinstance(value, str) else None
                if modo not in MODI:
                    print("guardiano: valore non valido %r: i modi sono %s"
                          % (args.valore, ", ".join(MODI)), file=sys.stderr)
                    return 2
                value = modo
            cfg[args.chiave] = value
            config.save_config(cfg)
        print(f"{args.chiave} = {cfg.get(args.chiave)}")
    else:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))


def build_parser():
    p = argparse.ArgumentParser(prog="plancia", description="Centro di controllo del lavoro con l'IA")
    p.add_argument("--version", action="version", version=f"plancia {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="avvia la dashboard locale")
    s.add_argument("--port", type=int)
    s.add_argument("--open", action="store_true", help="apre il browser")
    s.add_argument("--no-sync", action="store_true",
                   help="nessun sync automatico, né all'avvio né periodico")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("sync", help="rilegge sessioni, memoria, repo")
    s.add_argument("--full", action="store_true", help="rilegge i transcript da capo")
    s.add_argument("--skip-git", action="store_true", help="salta GitHub e git locale")
    s.add_argument("--modo", choices=["tutto", "caldo", "freddo"], default="tutto",
                   help="caldo: solo sessioni e hook. freddo: memoria, repo, indice")
    s.add_argument("--riattribuisci", action="store_true",
                   help="ricalcola il progetto di tutte le sessioni dai percorsi toccati")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("mcp", help="server MCP su stdio (lo lancia Claude Code)")
    s.set_defaults(func=cmd_mcp)

    s = sub.add_parser("briefing", help="stampa il briefing")
    s.add_argument("--project")
    s.set_defaults(func=cmd_briefing)

    s = sub.add_parser("task", help="task da terminale")
    s.add_argument("azione", nargs="?", default="list", choices=["list", "add", "done"])
    s.add_argument("testo", nargs="*")
    s.add_argument("--project")
    s.add_argument("--priority", type=int, default=2)
    s.add_argument("--due")
    s.add_argument("--status", default="aperti")
    s.set_defaults(func=cmd_task)

    s = sub.add_parser("recap", help="riepilogo della giornata, anche a voce")
    s.add_argument("--lang")
    s.add_argument("--day", help="AAAA-MM-GG, default oggi")
    s.add_argument("--engine", choices=["claude", "template"])
    s.add_argument("--speak", action="store_true", help="leggilo ad alta voce")
    s.add_argument("--notify", action="store_true", help="mandalo come notifica")
    s.add_argument("--daily", action="store_true", help="modalità automatica")
    s.add_argument("--voce", choices=["auto", "voicebox", "say"])
    s.add_argument("--background", action="store_true", help="non aspettare la fine")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_recap)

    s = sub.add_parser("ask", help="domanda sul tuo lavoro, risposta da Claude")
    s.add_argument("domanda", nargs="+")
    s.add_argument("--lang")
    s.add_argument("--speak", action="store_true")
    s.add_argument("--voce", choices=["auto", "voicebox", "say"])
    s.add_argument("--background", action="store_true")
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("jarvis", help="esegui un comando vocale scritto")
    s.add_argument("frase", nargs="+")
    s.add_argument("--lang")
    s.add_argument("--speak", action="store_true")
    s.set_defaults(func=cmd_jarvis)

    s = sub.add_parser("say", help="leggi una frase con la voce configurata")
    s.add_argument("testo", nargs="+")
    s.add_argument("--lang")
    s.add_argument("--voce", choices=["auto", "voicebox", "say"])
    s.set_defaults(func=cmd_say)

    s = sub.add_parser("voice", help="stato della voce, elenco voci, prova")
    s.add_argument("azione", nargs="?", default="stato", choices=["stato", "voci", "prova"])
    s.add_argument("--lang")
    s.add_argument("--voce", choices=["auto", "voicebox", "say"])
    s.set_defaults(func=cmd_voice)

    s = sub.add_parser("riordina", help="propone, applica e annulla la mappa dei padri")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--proponi", action="store_true", help="calcola la mappa e la scrive in un file")
    g.add_argument("--mostra", metavar="FILE", help="stampa in tabella la mappa di un file")
    g.add_argument("--applica", metavar="FILE", help="assegna i padri della mappa di un file")
    g.add_argument("--annulla", metavar="BATCH", help="rimette il padre di prima di un'applicazione")
    s.add_argument("--dove", help="dove scrivere il JSON di --proponi "
                                  "(default ~/.plancia/riordino/<data>.json)")
    s.add_argument("--resto-in-cartelle-viste", action="store_true",
                   help="con --applica: chi non ha un padre proposto finisce sotto "
                        "'cartelle-viste' invece di restare com'era")
    s.set_defaults(func=cmd_riordina)

    s = sub.add_parser("projects", help="elenco progetti")
    s.set_defaults(func=cmd_projects)

    s = sub.add_parser("sessioni", help="il catalogo delle sessioni, per progetto")
    s.add_argument("--progetto", help="solo quelle di un progetto")
    s.add_argument("--giorni", type=int, help="solo le ultime N giornate")
    s.add_argument("--tutte", action="store_true",
                   help="anche le chiamate interne e le sessioni temporanee")
    s.set_defaults(func=cmd_sessioni)

    s = sub.add_parser("lavagna", help="tutti i task aperti, di tutti gli agenti")
    s.add_argument("--stato", default="aperti")
    s.add_argument("--fonte", choices=["plancia", "claude", "codex"])
    s.set_defaults(func=cmd_lavagna)

    s = sub.add_parser("manda", help="manda un lavoro a un agente")
    s.add_argument("titolo", nargs="+")
    s.add_argument("--progetto")
    s.add_argument("--istruzioni", help="come lo vuoi fatto")
    s.add_argument("--agente", choices=["claude", "codex"], default="claude")
    s.add_argument("--modo", choices=["proposta", "esegui"], default="proposta")
    s.add_argument("--task", type=int, help="id del task di Plancia da chiudere")
    s.add_argument("--attendi", action="store_true")
    s.set_defaults(func=cmd_manda)

    s = sub.add_parser("riprendi", help="riprende un task nei suoi tre stati "
                                        "(viva/chiusa/persa), o attribuisce sessioni vecchie")
    s.add_argument("id", nargs="?", type=int, help="id del task di Plancia")
    s.add_argument("--dove", action="store_true", help="mostra anche la cartella")
    s.add_argument("--apri", action="store_true",
                   help="lancia la ripresa in un Terminale visibile")
    s.add_argument("--background", action="store_true",
                   help="manda in sottofondo, come 'manda' ma sulla sessione del task")
    s.add_argument("--scrive", action="store_true",
                   help="con --background, puo' modificare i file del progetto")
    s.add_argument("--istruzioni", help="con --background, come lo vuoi fatto")
    s.add_argument("--backfill", action="store_true",
                   help="attribuisce una sessione ai task che non ne hanno una")
    s.add_argument("--secco", action="store_true",
                   help="con --backfill, conta senza scrivere niente")
    s.add_argument("--annulla", help="nome del batch di --backfill da disfare")
    s.set_defaults(func=cmd_riprendi)

    s = sub.add_parser("lanci", help="i lavori mandati agli agenti")
    s.add_argument("id", nargs="?", type=int)
    s.set_defaults(func=cmd_lanci)

    s = sub.add_parser("eventi", help="il registro degli eventi")
    s.add_argument("--dopo")
    s.add_argument("--tipo")
    s.add_argument("--limite", type=int, default=30)
    s.set_defaults(func=cmd_eventi)

    # `cerca` è l'alias italiano, come il resto dei comandi; `search` resta
    # perché sta negli script e negli alias già scritti.
    for nome in ("cerca", "search"):
        s = sub.add_parser(nome, help="cerca in quello che è stato detto")
        s.add_argument("query", nargs="+")
        s.add_argument("--limit", type=int, default=10)
        s.add_argument("--project", help="restringe a un progetto")
        s.set_defaults(func=cmd_search)

    s = sub.add_parser("ricorda", help="cosa richiamerebbe la memoria su questa frase")
    s.add_argument("testo", nargs="+")
    s.add_argument("--tutto", action="store_true",
                   help="mostra anche quello che resta sotto la soglia")
    s.add_argument("--progetti", action="store_true",
                   help="include anche le memorie di progetto, di solito escluse")
    s.set_defaults(func=cmd_ricorda)

    s = sub.add_parser("esporta", help="il cervello in un file solo, per il telefono")
    s.add_argument("--dove", help="dove scriverlo (predefinito ~/.plancia/memoria.html)")
    s.add_argument("--apri", action="store_true", help="mostra il file nel Finder")
    s.set_defaults(func=cmd_esporta)

    s = sub.add_parser("init", help="costruisce la mappa dei progetti dai tuoi dati")
    s.add_argument("--force", action="store_true", help="riscrive il seed esistente")
    s.add_argument("--no-sync", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("install", help="collega MCP, hook, skill e comando")
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("uninstall", help="scollega tutto (i dati restano)")
    s.set_defaults(func=cmd_uninstall)

    s = sub.add_parser("autostart", help="avvia la dashboard a ogni accesso")
    s.add_argument("stato", choices=["on", "off"])
    s.set_defaults(func=cmd_autostart)

    s = sub.add_parser("daily", help="riepilogo automatico ogni giorno")
    s.add_argument("stato", choices=["on", "off"])
    s.add_argument("ora", nargs="?", default="08:45", help="HH:MM, default 08:45")
    s.add_argument("--voce", action="store_true", help="leggilo anche ad alta voce")
    s.set_defaults(func=cmd_daily)

    s = sub.add_parser("flusso", help="da dove arrivano i dati e quanto sono freschi")
    s.set_defaults(func=cmd_flusso)

    s = sub.add_parser("esclusi", help="cartelle e sessioni private: elenco e pulizia")
    s.add_argument("--prova", action="store_true", help="conta senza toccare l'archivio")
    s.set_defaults(func=cmd_esclusi)

    s = sub.add_parser("guardiano", help="il guardiano dei compartimenti: stato e registro")
    s.add_argument("--registro", nargs="?", const=20, type=int, metavar="N",
                   help="le ultime N decisioni non ammesse (default 20)")
    s.add_argument("--stato", action="store_true",
                   help="modalita', compartimenti e righe recenti (il default)")
    s.set_defaults(func=cmd_guardiano)

    s = sub.add_parser("doctor", help="controlla lo stato")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("open", help="apre la dashboard nel browser")
    s.set_defaults(func=cmd_open)

    s = sub.add_parser("config", help="legge o scrive la configurazione")
    s.add_argument("chiave", nargs="?")
    s.add_argument("valore", nargs="?")
    s.set_defaults(func=cmd_config)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    config.ensure_dirs()
    try:
        return args.func(args) or 0
    except config.ConfigIlleggibile as exc:
        print(f"config: {exc}: non scrivo niente, riparalo a mano", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
