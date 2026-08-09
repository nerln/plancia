"""Riga di comando di Plancia."""

import argparse
import json
import sys
import webbrowser

from . import actions, briefing, config, store


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
                      modo=args.modo)
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
    from . import cantiere
    conn = store.connect()
    store.init_db(conn)
    try:
        r = cantiere.avvia(conn, " ".join(args.titolo), progetto=args.progetto,
                           istruzioni=args.istruzioni or "", agente=args.agente,
                           modo=args.modo, task_id=args.task, attendi=args.attendi)
        print(f"lancio #{r['run']} · {r['agente']} · {r['modo']} · {r['cwd']}")
        if args.attendi:
            d = cantiere.dettaglio(conn, r["run"])
            print(f"\n[{d['stato']}] {d['esito'][:600]}")
        else:
            print("gira in sottofondo: `plancia lanci` per vedere com'è andata")
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


def cmd_doctor(args):
    from . import setup_claude
    for line in setup_claude.doctor():
        print(line)


def cmd_open(args):
    port = config.load_config().get("port", config.DEFAULT_PORT)
    webbrowser.open(f"http://127.0.0.1:{port}")


def cmd_config(args):
    cfg = config.load_config()
    if args.chiave:
        value = args.valore
        if value is not None:
            try:
                value = json.loads(value)
            except Exception:
                pass
            cfg[args.chiave] = value
            config.save_config(cfg)
        print(f"{args.chiave} = {cfg.get(args.chiave)}")
    else:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))


def build_parser():
    p = argparse.ArgumentParser(prog="plancia", description="Centro di controllo del lavoro con l'IA")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="avvia la dashboard locale")
    s.add_argument("--port", type=int)
    s.add_argument("--open", action="store_true", help="apre il browser")
    s.add_argument("--no-sync", action="store_true", help="non aggiornare all'avvio")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("sync", help="rilegge sessioni, memoria, repo")
    s.add_argument("--full", action="store_true", help="rilegge i transcript da capo")
    s.add_argument("--skip-git", action="store_true", help="salta GitHub e git locale")
    s.add_argument("--modo", choices=["tutto", "caldo", "freddo"], default="tutto",
                   help="caldo: solo sessioni e hook. freddo: memoria, repo, indice")
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

    s = sub.add_parser("projects", help="elenco progetti")
    s.set_defaults(func=cmd_projects)

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
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
