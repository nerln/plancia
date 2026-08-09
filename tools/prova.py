#!/usr/bin/env python3
"""Il collaudo: gira tutto su un archivio finto e non tocca il tuo.

    python3 tools/prova.py

Non è una suite di test completa e non pretende di esserlo. È la lista delle
cose che si sono rotte almeno una volta, messe in fila, così prima di una
release si sa in dieci secondi se una di quelle è tornata a rompersi.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-"))
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


def main():
    print(f"archivio di prova: {CASA}\n")

    from plancia import (config, eventi, lavagna, proposte, recap,  # noqa: E402
                         store)

    # ---------------------------------------------------------------- schema
    conn = store.connect()
    store.init_db(conn)
    store.migrate(conn)
    tabelle = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    prova("le tabelle ci sono tutte",
          {"projects", "sessions", "tasks", "posts", "agenda", "runs",
           "events", "knowledge"} <= tabelle,
          str(sorted(tabelle)))

    # migrate deve poter girare due volte di fila senza lamentarsi
    store.migrate(conn)
    colonne = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    prova("migrate è ripetibile e aggiunge le colonne nuove",
          {"agent", "prompt", "cwd", "run_id"} <= colonne, str(sorted(colonne)))

    # ------------------------------------------------------------ dati finti
    subprocess.run([sys.executable, str(RADICE / "tools" / "demo-data.py")],
                   check=True, capture_output=True, env=os.environ)
    conn = store.connect()
    n_prog = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    prova("i dati dimostrativi entrano", n_prog >= 7, f"progetti: {n_prog}")

    # ---------------------------------------------------------------- lavagna
    conteggi = lavagna.conteggi(conn)
    prova("la lavagna vede tutte e tre le fonti",
          {"claude", "codex", "plancia"} <= set(conteggi), str(conteggi))
    voci = lavagna.elenco(conn, "aperti")
    prova("le voci aperte hanno stato e fonte",
          bool(voci) and all(v.get("stato") and v.get("fonte") for v in voci))

    # in modalità dimostrativa non deve andare a leggere la macchina vera
    prova("la lavagna dimostrativa non tocca le fonti vere",
          lavagna.sync(conn) == 0)

    # una fonte che non risponde non deve far sparire le sue voci: si simula
    # facendo fallire la lettura di Codex e controllando che restino lì
    prima = conn.execute("SELECT COUNT(*) FROM agenda WHERE fonte='codex'").fetchone()[0]
    store.set_meta(conn, "demo", "0")
    conn.commit()
    vero_codex, vero_claude = lavagna.da_codex, lavagna.da_claude

    def codex_rotto(esito=None):
        if esito is not None:
            esito["ok"] = False
        return []

    lavagna.da_codex = codex_rotto
    lavagna.da_claude = lambda esito=None: []
    lavagna.sync(conn)
    lavagna.da_codex, lavagna.da_claude = vero_codex, vero_claude
    dopo = conn.execute("SELECT COUNT(*) FROM agenda WHERE fonte='codex'").fetchone()[0]
    store.set_meta(conn, "demo", "1")
    conn.commit()
    prova("una fonte muta non cancella le sue voci", dopo == prima,
          f"prima {prima}, dopo {dopo}")

    # --------------------------------------------------------------- proposte
    for lingua in ("it", "en", "es"):
        p = proposte.calcola(conn, lingua)
        prova(f"le proposte escono in {lingua}", bool(p))
        testo = " ".join(x["testo"] for x in p)
        if lingua == "en":
            prova("le proposte in inglese non hanno pezzi in italiano",
                  "quota" not in testo or "ha finito" not in testo, testo[:80])
        prova(f"ogni proposta in {lingua} ha un'azione",
              all(x.get("azione", {}).get("tipo") for x in p))

    # l'ordine è per urgenza: un lancio fallito prima di una spesa alta
    p = proposte.calcola(conn, "it")
    prova("le proposte sono ordinate per urgenza",
          [x["urgenza"] for x in p] == sorted(x["urgenza"] for x in p))

    proposte.salva(conn, p)
    prova("«la seconda» sceglie la seconda",
          proposte.scegli(conn, "la seconda") == p[1] if len(p) > 1 else True)
    prova("«fallo» sceglie la prima", proposte.scegli(conn) == p[0])
    # Se nessuno le ha ancora chieste, "fallo" non deve dire che non c'è niente
    store.set_meta(conn, "proposte", "")
    conn.commit()
    prova("«fallo» funziona anche a memoria vuota",
          (proposte.scegli(conn, None, "it") or {}).get("testo") == p[0]["testo"])

    # --------------------------------------------------------------- riepilogo
    dati = recap.collect(conn)
    prova("il riepilogo raccoglie la giornata", "sessioni" in dati)
    for lingua in ("it", "en", "es", "fr", "de", "pt"):
        testo = recap.render_template(dati, lingua)
        prova(f"il riepilogo a modelli parla {lingua}",
              len(testo) > 40 and "None" not in testo, testo[:60])

    r = recap.build(conn, lang="en", engine="template", cache=True)
    prova("il riepilogo in cache torna fresco",
          recap.solo_cache(conn, "en").get("fresco") is True)
    prova("il riepilogo in cache non torna in un'altra lingua",
          recap.solo_cache(conn, "it").get("testo") is None,
          "la cache tiene una lingua sola")

    # -------------------------------------------------------- indice dei turni
    # Fino al 9 agosto 2026 la ricerca vedeva il solo primo prompt di ogni
    # sessione: 0,80 MB su 979 di transcript, cioe' lo 0,08%, ed e' il motivo per
    # cui era stata chiamata cinque volte in tutto.
    from plancia import turni as _t  # noqa: E402
    _t.prepara(conn)
    finto = Path(tempfile.mkdtemp()) / "progetto-x"
    finto.mkdir(parents=True)
    (finto / "sessione1.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"type": "assistant", "timestamp": "2026-08-09T10:00:00Z",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "Il pavimento di riproducibilita' misurato con inkfloor "
                                      "sta al 92,8 per cento e la soglia regge."}]}},
        {"type": "user", "timestamp": "2026-08-09T10:01:00Z",
         "message": {"role": "user", "content": "ok"}},
        {"type": "assistant", "timestamp": "2026-08-09T10:02:00Z",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "Ho trovato che il denominatore del blending era a uno "
                                      "invece che gaussiano, con attenuazione del 27 per cento."}]}},
    ]), encoding="utf-8")

    esito = _t.indicizza(conn, completo=True, radice=finto.parent)
    prova("l'indice legge i turni dai transcript", esito["turni"] == 2, str(esito))
    prova("e scarta i turni troppo corti per essere cercati",
          esito["turni"] == 2, "il turno 'ok' non deve entrare")
    prova("ritrova una frase detta a meta' sessione",
          bool(_t.cerca(conn, "denominatore blending")))
    prova("e dice da quale riga di quale file viene",
          all(r["riga"] > 0 and r["percorso"].endswith(".jsonl")
              for r in _t.cerca(conn, "inkfloor")))
    prova("il frammento e' verbatim, non un riassunto",
          "92,8" in (_t.cerca(conn, "pavimento riproducibilita")[0]["frammento"] or ""))
    # FTS5 mette AND fra le parole: tre parole che non stanno mai insieme nello
    # stesso turno davano zero risultati, ed e' il caso che si incontra subito.
    prova("tre parole sparse trovano lo stesso",
          bool(_t.cerca(conn, "inkfloor blending soglia")))
    prova("una domanda scritta con gli operatori resta com'e'",
          _t._domanda('"frase esatta"') == '"frase esatta"')
    secondo = _t.indicizza(conn, radice=finto.parent)
    prova("il secondo giro salta i file gia' visti",
          secondo["file_saltati"] == 1 and secondo["turni"] == 0, str(secondo))

    # Ogni sottoagente si porta dietro la sua copia del prompt, quindi lo stesso
    # testo sta in piu' file: senza deduplica la prima pagina e' fatta di
    # doppioni, ed e' quello che si vedeva al primo giro nel browser.
    (finto / "sessione2.jsonl").write_text((finto / "sessione1.jsonl").read_text(),
                                           encoding="utf-8")
    _t.indicizza(conn, radice=finto.parent)
    doppi = _t.cerca(conn, "denominatore blending", limit=10)
    prova("lo stesso testo in due file torna una volta sola",
          len(doppi) == 1, f"{len(doppi)} risultati")

    # I transcript dei sottoagenti stanno in subagents/workflows/<id>/, e la
    # cartella che li contiene e' l'id del workflow: senza risalire alla prima
    # cartella sotto la radice l'etichetta era un identificativo a caso.
    sotto = finto / "subagents" / "workflows" / "wf_abc123"
    sotto.mkdir(parents=True)
    (sotto / "agent-1.jsonl").write_text((finto / "sessione1.jsonl").read_text(),
                                         encoding="utf-8")
    _t.indicizza(conn, completo=True, radice=finto.parent)
    prova("un turno di sottoagente prende l'etichetta del progetto, non del workflow",
          all("wf_" not in (r["progetto"] or "")
              for r in _t.cerca(conn, "inkfloor", limit=10)))

    # La cartella dice poco: il 94 per cento dei turni sta sotto il Drive perche'
    # e' da li' che si lavora. Il nome buono lo sa gia' l'ingest, sessione per
    # sessione, e si prende con una giuntura.
    conn.execute("INSERT INTO projects(key, name, kind, status) VALUES(?,?,?,?)",
                 ("provaproj", "Progetto Vero", "codice", "attivo"))
    pid = conn.execute("SELECT id FROM projects WHERE key='provaproj'").fetchone()[0]
    conn.execute("INSERT INTO sessions(session_id, project_id, file) VALUES(?,?,?)",
                 ("sessione1", pid, "x"))
    conn.commit()
    prova("il progetto vero vince sulla cartella",
          any(r["progetto"] == "Progetto Vero"
              for r in _t.cerca(conn, "inkfloor", limit=10)))
    # Va chiesto col filtro: la deduplica tiene un risultato solo per testo, e
    # quello sopravvissuto e' gia' quello col progetto vero.
    dalla_cartella = _t.cerca(conn, "inkfloor", limit=10, progetto="progetto x")
    prova("e le sessioni che l'ingest non ha visto tengono la cartella",
          bool(dalla_cartella)
          and all(r["progetto"] == "progetto x" for r in dalla_cartella),
          f"{len(dalla_cartella)} risultati")
    gruppi = {g["progetto"]: g["turni"] for g in _t.raggruppa(conn, "inkfloor")}
    prova("il conteggio per progetto copre tutto l'indice, non la pagina",
          gruppi.get("Progetto Vero") == 1 and gruppi.get("progetto x") == 2, str(gruppi))
    prova("e il filtro sul progetto usa lo stesso nome",
          len(_t.cerca(conn, "inkfloor", limit=10, progetto="Progetto Vero")) == 1)
    prova("una scratchpad sotto /private/tmp non diventa lavoro vero",
          _t._etichetta("-private-tmp-claude-501-Users-eugenionerelli-Library-"
                        "CloudStorage-GoogleDrive-x-Il-mio-Drive-abc-scratchpad") == "tmp")
    prova("e un worktree di Claude resta il suo progetto",
          _t._etichetta(_t.CASA + "-dev-scriba--claude-worktrees-stoic-mayer") == "scriba")
    shutil.rmtree(finto.parent, ignore_errors=True)

    # -------------------------------------------------------------- briefing
    # Il file che l'hook infila in ogni sessione: ogni riga si paga una volta
    # per sessione. La versione lunga resta, ma a un tool di distanza.
    from plancia import briefing as _b  # noqa: E402
    corto = _b.build(conn, esteso=False)
    lungo = _b.build(conn)
    prova("il briefing corto e' molto piu' corto di quello esteso",
          len(corto) < len(lungo) * 0.55, f"{len(corto)} contro {len(lungo)}")
    prova("e sta sotto il tetto di token",
          len(corto) // 4 <= 320, f"~{len(corto)//4} token, tetto 320")
    prova("l'hook riceve la versione corta, non quella lunga",
          _b.write_cache() == _b.build(esteso=False))
    prova("il taglio non spezza le parole a meta'",
          not any(r.rstrip("…").endswith((" ", "-")) for r in corto.splitlines()))

    # ------------------------------------------------------------------ lanci
    from plancia import cantiere  # noqa: E402
    conn.execute("INSERT INTO runs(agente, modo, prompt, cwd, stato, inizio, pid) "
                 "VALUES('claude','proposta','appeso','/tmp','in corso',?,999999)",
                 (store.now(),))
    conn.commit()
    prova("un lancio appeso viene chiuso al riavvio", cantiere.riconcilia(conn) >= 1)
    prova("e non resta in corso",
          conn.execute("SELECT COUNT(*) FROM runs WHERE stato='in corso' "
                       "AND prompt='appeso'").fetchone()[0] == 0)

    conn.execute("INSERT INTO runs(agente, modo, prompt, cwd, stato, inizio) "
                 "VALUES('claude','proposta','senza pid','/tmp','in coda',?)", (store.now(),))
    conn.commit()
    rid = conn.execute("SELECT id FROM runs WHERE prompt='senza pid'").fetchone()[0]
    prova("si annulla anche un lancio senza processo", cantiere.annulla(conn, rid) is True)

    # I post mancavano da tutte e due le liste: chiedere una bozza a un lancio
    # voleva dire farlo fermare a chiedere un permesso.
    prova("un lancio può leggere i post",
          "mcp__plancia__plancia_posts" in cantiere.TOOL_LETTURA)
    prova("e in esecuzione può scriverne una bozza",
          "mcp__plancia__plancia_post_add" in cantiere.TOOL_SCRITTURA
          and "mcp__plancia__plancia_post_update" in cantiere.TOOL_SCRITTURA)
    prova("ma in proposta no, perché proporre non è scrivere",
          "mcp__plancia__plancia_post_add" not in cantiere.TOOL_LETTURA)

    # Una sessione che si ferma a chiedere un permesso esce con zero e senza
    # errore. Contarla come riuscita faceva chiudere il task come "fatto" senza
    # che nessuno avesse fatto niente: è già successo, il 4 agosto 2026.
    acc = {"sessione": None, "esito": "", "token": 0, "costo": 0, "errore": False,
           "negati": []}
    cantiere._leggi_claude(json.dumps({
        "type": "result", "result": "Serve la tua approvazione.", "is_error": False,
        "usage": {"output_tokens": 10}, "total_cost_usd": 0.1,
        "permission_denials": [{"tool_name": "mcp__plancia__plancia_post_add"},
                               {"tool_name": "mcp__plancia__plancia_post_add"}],
    }), acc)
    prova("i permessi negati si leggono dallo stream",
          acc["negati"] == ["mcp__plancia__plancia_post_add"], str(acc["negati"]))
    prova("e un'uscita pulita senza errori non basta a dire riuscito",
          bool(acc["negati"]) and not acc["errore"])

    conn.execute("INSERT INTO tasks(title, status, created_at, updated_at) "
                 "VALUES('task di un lancio bloccato','in corso',?,?)",
                 (store.now(), store.now()))
    conn.commit()
    tid = conn.execute("SELECT id FROM tasks WHERE title='task di un lancio bloccato'"
                       ).fetchone()[0]
    conn.execute("INSERT INTO runs(task_id, agente, modo, prompt, cwd, stato, inizio) "
                 "VALUES(?,'claude','esegui','bloccato','/tmp','in corso',?)",
                 (tid, store.now()))
    conn.commit()
    brid = conn.execute("SELECT id FROM runs WHERE prompt='bloccato'").fetchone()[0]
    cantiere._chiudi(conn, brid, "bloccato", "niente permessi", acc,
                     "prova", None, tid, "esegui")
    prova("un lancio bloccato non chiude il task come fatto",
          conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0]
          == "bloccato",
          conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0])

    # ------------------------------------------------------------ comandi voce
    from plancia import jarvis as _j  # noqa: E402
    coppie = [("vai più veloce", "velocita"), ("parla più piano", "velocita"),
              ("vai su progetti", "vai"), ("apri la lavagna", "vai"),
              ("ripeti", "ripeti"), ("non ho capito", "ripeti"),
              ("basta", "ferma"), ("annulla", "annulla"),
              ("slow down", "velocita"), ("say that again", "ripeti")]
    sbagliate = [f"{f} -> {_j.riconosci(f)[0]}" for f, atteso in coppie
                 if _j.riconosci(f)[0] != atteso]
    prova("i comandi vocali non si rubano la frase", not sbagliate, str(sbagliate))

    # ------------------------------------------------------- testo per la voce
    from plancia.voce_testo import per_voce  # noqa: E402
    prova("gli indirizzi non si leggono lettera per lettera",
          "GitHub" in per_voce("pubblicato su github.com/tizio/repo, poi si vede", "it")
          and "github.com" not in per_voce("pubblicato su github.com/tizio/repo", "it"))
    prova("di un percorso resta l'ultimo pezzo",
          per_voce("sta in ~/.plancia/eventi.jsonl", "it") == "sta in eventi.jsonl")
    prova("gli sha non si dicono",
          "4f1a2c9e8b7d" not in per_voce("il commit 4f1a2c9e8b7d6543 è a posto", "it"))
    prova("la punteggiatura della frase resta",
          per_voce("vedi github.com/a/b, poi torna", "it").endswith("poi torna")
          and "," in per_voce("vedi github.com/a/b, poi torna", "it"))
    prova("l'em dash non arriva alla voce",
          "—" not in per_voce("una cosa — e poi un'altra", "it"))
    _lungo = ("Prima frase corta. Poi tutto un ragionamento che va avanti per righe "
              "e righe senza fermarsi mai davvero, come succede quando uno scrive di getto")
    _corto = recap._prima_frase(_lungo)
    prova("un prossimo passo lunghissimo si accorcia",
          len(_corto) <= 130 and len(_corto) < len(_lungo), f"{len(_corto)} caratteri")
    prova("e non si taglia in mezzo a una parola",
          _lungo.startswith(_corto) and not _corto.endswith(" "), _corto[-24:])
    prova("un prossimo passo corto resta intero",
          recap._prima_frase("annunciarlo su X") == "annunciarlo su X")
    prova("le date con le barre non diventano numeri",
          per_voce("la riunione è il 12/08/2026 alle nove", "it")
          == "la riunione è il 12/08/2026 alle nove")
    prova("ripeti risponde uguale da qualsiasi porta",
          _j.esegui("quanti progetti attivi ho", "it", conn)["risposta"]
          == _j.esegui("ripeti", "it", conn)["risposta"])
    prova("una frase normale non viene toccata",
          per_voce("Oggi tre sessioni e due commit, niente di strano.", "it")
          == "Oggi tre sessioni e due commit, niente di strano.")

    # --------------------------------------------------- risposte senza modello
    from plancia import risposte  # noqa: E402
    domande = {
        "it": ["quanti task aperti ho", "cosa c'è aperto sulla lavagna",
               "come sono andati i lanci", "quanto ho speso oggi",
               "cosa ho fatto oggi", "come va con codex"],
        "en": ["how many open tasks do i have", "what is open on the board",
               "how did the runs go", "how much did i spend today",
               "what did i do today", "how is codex doing"],
        "es": ["cuántas tareas abiertas tengo", "qué hay abierto en la pizarra",
               "cómo han ido los lanzamientos", "cuánto he gastado hoy"],
    }
    for lingua, elenco_domande in domande.items():
        mancanti = [d for d in elenco_domande if not risposte.prova(conn, d, lingua)]
        prova(f"le domande sui dati rispondono in {lingua} senza modello",
              not mancanti, str(mancanti))

    # una domanda che i dati non sanno deve passare al modello, non inventare
    prova("una domanda che i dati non sanno passa oltre",
          risposte.prova(conn, "scrivimi una poesia sul mare", "it") is None)

    # ------------------------------------------------------ commit e sessioni
    from plancia import ingest  # noqa: E402
    n = ingest.attribuisci_commit(conn)
    prova("l'attribuzione dei commit gira", isinstance(n, int))
    sbagliati = conn.execute(
        "SELECT COUNT(*) FROM commits c JOIN repos r ON r.name=c.repo "
        "JOIN sessions s ON s.session_id=c.session_id "
        "WHERE COALESCE(c.session_id,'')<>'' AND r.project_id IS NOT NULL "
        "AND s.project_id IS NOT NULL AND s.project_id <> r.project_id").fetchone()[0]
    prova("nessun commit finisce nella sessione di un altro progetto",
          sbagliati == 0, f"sbagliati: {sbagliati}")

    # ---------------------------------------------------------------- eventi
    e = eventi.scrivi("lavoro.completato", "prova", progetto="lumen",
                      dati={"agente": "claude"})
    letti = eventi.leggi(limite=5)
    prova("l'evento si scrive e si rilegge",
          bool(letti) and letti[-1]["id"] == e["id"])
    prova("il segnalibro non torna indietro", eventi.leggi(dopo=e["id"]) == [])
    prova("lo schema è dichiarato", e["schema"] == "plancia.evento/1")

    # con il registro grande si legge dal fondo, non tutto: il pannello vocale
    # lo chiede ogni sei secondi
    for i in range(4000):
        eventi.scrivi("task.creato", f"riempimento {i}")
    import time as _t
    _t0 = _t.perf_counter()
    ultimi = eventi.leggi(limite=5)
    quanto = (_t.perf_counter() - _t0) * 1000
    prova("un registro grande si legge in fretta", quanto < 60, f"{quanto:.0f} ms")
    prova("e torna comunque gli ultimi", len(ultimi) == 5)
    prova("il segnalibro dell'ultimo non torna niente",
          eventi.leggi(dopo=ultimi[-1]["id"]) == [])

    # ------------------------------------------------------------------- HTTP
    from plancia import api  # noqa: E402
    import threading

    porta = 7791
    filo = threading.Thread(target=api.serve, kwargs={"port": porta,
                                                      "sync_first": False},
                            daemon=True)
    filo.start()
    import time
    time.sleep(1.5)

    def prendi(percorso):
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{percorso}",
                                    timeout=10) as r:
            return json.loads(r.read())

    try:
        o = prendi("/api/overview?lang=en")
        prova("/api/overview risponde", "stats" in o)
        prova("l'overview porta le proposte", isinstance(o.get("proposte"), list))
        prova("l'overview conta la lavagna", "lavagna_aperti" in o["stats"])
        prova("le proposte seguono la lingua chiesta",
              not any("Ci mando" in x["testo"] for x in o["proposte"]))
        prova("/api/lavagna risponde", "voci" in prendi("/api/lavagna"))
        prova("/api/runs risponde", isinstance(prendi("/api/runs?limite=3"), list))
        prova("/api/eventi risponde", isinstance(prendi("/api/eventi").get("eventi"), list))
        prova("/api/proposte risponde", isinstance(prendi("/api/proposte?lang=it"), list))
        # Il 9 agosto questa risposta e' passata da lista a oggetto, e la palette
        # continuava a fare `hits.length` su un oggetto: niente errore, zero
        # risultati per sempre. Il contratto va scritto da qualche parte.
        ric = prendi("/api/search?q=plancia")
        prova("/api/search torna le tre chiavi, non una lista",
              isinstance(ric, dict) and {"turni", "progetti", "schede"} <= set(ric),
              str(type(ric)))
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=10) as r:
            pagina = r.read().decode()
        prova("la pagina si serve", "<title>" in pagina)
    except Exception as errore:            # noqa: BLE001
        prova("il server HTTP risponde", False, str(errore))

    # --------------------------------------------------------------- scrittura
    # senza token le scritture devono essere rifiutate
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{porta}/api/tasks",
                                     data=b'{"title":"abusivo"}',
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        urllib.request.urlopen(req, timeout=10)
        prova("le scritture senza token sono rifiutate", False, "è passata")
    except urllib.error.HTTPError as errore:
        prova("le scritture senza token sono rifiutate", errore.code in (401, 403),
              str(errore.code))
    except Exception as errore:            # noqa: BLE001
        prova("le scritture senza token sono rifiutate", False, str(errore))

    # ------------------------------------------------------------------ front
    app_js = (RADICE / "web" / "app.js").read_text(encoding="utf-8")
    prova("app.js non legge il riepilogo prima di averlo",
          app_js.index("const d = r.data;") > app_js.index("solo_cache=1"))
    # L'altra meta' del contratto qui sopra: chi chiama /api/search deve aprire
    # l'oggetto. Due punti di chiamata, la vista Cerca e la palette, e uno dei
    # due era rimasto indietro.
    chiamate = app_js.count("'/api/search?q='")
    prova("ogni chiamata a /api/search apre l'oggetto",
          chiamate == 2 and app_js.count("d.turni || []") == 2, f"{chiamate} chiamate")
    if shutil.which("node"):
        esito = subprocess.run(["node", "--check", str(RADICE / "web" / "app.js")],
                               capture_output=True)
        prova("app.js si compila", esito.returncode == 0,
              esito.stderr.decode()[:200])

    # -------------------------------------------------------- installazione
    # Si prova su una casa finta: e' la strada che fa chi arriva dal repo, e
    # finora non la controllava nessuno. Fuori restano i due LaunchAgent, che
    # parlano con il launchd vero dell'utente e non si simulano.
    casa = Path(tempfile.mkdtemp(prefix="plancia-casa-"))
    codice = (
        "import sys; sys.path.insert(0, %r)\n"
        "from plancia import setup_claude as s, codex\n"
        "print(s.install_command()); print(s.install_mcp()); print(codex.registra_mcp())\n"
        "print(s.install_hooks()); print(s.install_skill())\n" % str(RADICE))
    ambiente = dict(os.environ, HOME=str(casa), PLANCIA_HOME=str(casa / ".plancia"))
    esito = subprocess.run([sys.executable, "-c", codice], capture_output=True, env=ambiente)
    prova("l'installazione da zero non si rompe", esito.returncode == 0,
          esito.stderr.decode()[-200:])
    prova("scrive le due skill",
          (casa / ".claude/skills/plancia/SKILL.md").exists()
          and (casa / ".claude/skills/riepilogo/SKILL.md").exists())
    prova("mette gli hook", (casa / ".claude/settings.json").exists())
    prova("mette il comando", (casa / ".local/bin/plancia").exists())
    prova("non tocca la casa vera", not (Path.home() / ".plancia-finta").exists())

    # e disinstallandosi deve andarsene davvero, lasciando i file dell'utente
    codice_via = (
        "import sys, json, shutil, pathlib; sys.path.insert(0, %r)\n"
        "from plancia import setup_claude as s\n"
        "s.remove_hooks(); s.remove_mcp()\n"
        "casa = pathlib.Path.home()\n"
        "l = casa / '.local/bin/plancia'\n"
        "l.unlink() if l.is_symlink() else None\n"
        "[shutil.rmtree(d) for d in (s.SKILL_DIR, casa / '.claude/skills/riepilogo') if d.exists()]\n"
        # su una macchina senza Claude Code il file non esiste mai: non averlo
        # e non avere il nostro server dentro sono la stessa cosa
        "leggi = lambda p: json.loads(p.read_text()) if p.exists() else {}\n"
        "j = leggi(casa / '.claude.json')\n"
        "st = leggi(casa / '.claude/settings.json')\n"
        "print(list((j.get('mcpServers') or {}).keys()), list((st.get('hooks') or {}).keys()))\n"
        % str(RADICE))
    via = subprocess.run([sys.executable, "-c", codice_via], capture_output=True, env=ambiente)
    prova("la disinstallazione non si rompe", via.returncode == 0,
          via.stderr.decode()[-200:])
    prova("toglie il server MCP e gli hook", via.stdout.decode().strip() == "[] []",
          via.stdout.decode().strip())
    prova("porta via le skill", not (casa / ".claude/skills/plancia").exists())
    prova("lascia al suo posto la configurazione tua",
          (casa / ".claude/settings.json").exists())

    shutil.rmtree(casa, ignore_errors=True)

    # ------------------------------------------------------------------ voce
    from plancia import voice as _v  # noqa: E402
    import time as _t2
    _v._ultimo_no = 0.0
    _t0 = _t2.perf_counter()
    _v.voicebox_vivo()                 # questa bussa davvero
    primo = (_t2.perf_counter() - _t0) * 1000
    # La chiamata a memoria si misura tre volte e si tiene la piu' veloce: una
    # soglia secca in millisecondi faceva fallire il collaudo quando la macchina
    # era sotto carico, e un collaudo che fallisce a caso smette di dire
    # qualcosa. Il confronto e' anche relativo al primo giro, che sotto carico
    # rallenta insieme al secondo.
    tempi = []
    for _ in range(3):
        _t0 = _t2.perf_counter()
        _v.voicebox_vivo()
        tempi.append((_t2.perf_counter() - _t0) * 1000)
    secondo = min(tempi)
    prova("un Voicebox che non risponde non si richiede a ogni frase",
          secondo < 5 or secondo < primo / 2, f"{primo:.1f} ms poi {secondo:.1f} ms")
    _v._ultimo_no = 0.0

    prova("il testo per la voce passa dalla sintesi",
          "per_voce" in io.open(RADICE / "plancia" / "voice.py", encoding="utf-8").read())

    # ----------------------------------------------------------------- MCP
    # E' la porta da cui entrano Claude e Codex: se non si apre, in ogni
    # sessione i tool plancia_* spariscono senza dire niente.
    def mcp_chiama(proc, metodo, params=None, id_=1):
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": id_, "method": metodo,
                                     "params": params or {}}) + "\n")
        proc.stdin.flush()
        riga = proc.stdout.readline()
        return json.loads(riga) if riga.strip() else {}

    server = subprocess.Popen([str(RADICE / "bin" / "plancia-mcp")], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, bufsize=1, env=os.environ)
    try:
        avvio = mcp_chiama(server, "initialize", {"protocolVersion": "2024-11-05",
                                                  "capabilities": {}, "clientInfo":
                                                  {"name": "prova", "version": "1"}})
        prova("il server MCP si presenta",
              avvio.get("result", {}).get("serverInfo", {}).get("name") == "plancia")
        elenco_tool = [t["name"] for t in
                       mcp_chiama(server, "tools/list", {}, 2).get("result", {}).get("tools", [])]
        # La superficie esposta e' piccola apposta: gli schemi stanno nel
        # contesto di ogni sessione, usati o no. Misurato il 9 agosto 2026 su
        # 1269 sessioni vere, i venti tool costavano 2,75 milioni di token per
        # 158 chiamate, e quattro non erano stati chiamati mai.
        from plancia import mcp as _m  # noqa: E402
        prova("la superficie esposta resta piccola",
              len(elenco_tool) <= 8, f"{len(elenco_tool)} tool")
        prova("e il dispatcher c'e'", "plancia" in elenco_tool)
        prova("ogni azione della coda ha il suo indizio",
              not (set(_m.CODA) - set(_m.INDIZI)),
              str(set(_m.CODA) - set(_m.INDIZI)))
        prova("nessun indizio punta a un'azione che non esiste",
              not (set(_m.INDIZI) - set(_m.CODA)),
              str(set(_m.INDIZI) - set(_m.CODA)))
        prova("niente e' sparito: primi piu coda fanno il totale di prima",
              len(_m.PRIMI) + len(_m.CODA) == len(_m._TUTTI))

        # La guardia vera: se qualcuno riaggiunge tool di prima classe, questo
        # collaudo diventa rosso prima che la spesa torni dov'era.
        peso = len(json.dumps(_m.TOOLS)) // 4
        prova("gli schemi stanno sotto il tetto di token",
              peso <= 1200, f"~{peso} token, tetto 1200")

        risposta = mcp_chiama(server, "tools/call",
                              {"name": "plancia", "arguments": {"azione": "lavagna"}}, 3)
        prova("il dispatcher raggiunge un'azione della coda",
              bool(risposta.get("result", {}).get("content")))
        vecchio = mcp_chiama(server, "tools/call",
                             {"name": "plancia_lavagna", "arguments": {}}, 4)
        prova("e i nomi vecchi rispondono ancora, per i client gia' avviati",
              bool(vecchio.get("result", {}).get("content")))
    finally:
        server.terminate()

    # ---------------------------------------------------------------- hook
    coda = casa_hook = Path(tempfile.mkdtemp(prefix="plancia-hook-"))
    amb = dict(os.environ, PLANCIA_HOME=str(casa_hook))
    entrata = b'{"hook_event_name":"SessionStart","session_id":"x","cwd":"/tmp"}'
    r = subprocess.run([str(RADICE / "bin" / "plancia-hook"), "--prova"],
                       input=entrata, capture_output=True, env=amb)
    prova("l'hook di prova non mette niente in coda",
          not (casa_hook / "queue" / "hooks.jsonl").exists()
          or not (casa_hook / "queue" / "hooks.jsonl").read_text().strip())
    prova("l'hook esce sempre con zero", r.returncode == 0)
    subprocess.run([str(RADICE / "bin" / "plancia-hook")], input=entrata,
                   capture_output=True, env=amb)
    prova("senza --prova la sessione finisce in coda",
          (casa_hook / "queue" / "hooks.jsonl").read_text().strip().count("SessionStart") == 1)
    shutil.rmtree(casa_hook, ignore_errors=True)

    # ------------------------------------------------------- skill in archivio
    conn.execute("INSERT INTO capabilities(name, kind, description, path, meta, body, "
                 "updated_at) VALUES('finta','skill','una skill di prova','/finta/SKILL.md',"
                 "'{}','dentro c e scritto sciacquapanni', ?)", (store.now(),))
    conn.commit()
    store.rebuild_search(conn)
    trovata = list(conn.execute(
        "SELECT kind, title FROM search_fts WHERE search_fts MATCH 'sciacquapanni'"))
    prova("il testo di una skill si ritrova cercando",
          any(r["kind"] == "capacita" for r in trovata), str([dict(r) for r in trovata]))

    # ------------------------------------------------------------------- skill
    from plancia import setup_claude as _sc  # noqa: E402
    for nome, costante in (("plancia", _sc.SKILL), ("riepilogo", _sc.RIEPILOGO_SKILL)):
        prova(f"la skill {nome} parla delle cose che ci sono",
              all(p in costante for p in (["plancia_lavagna", "plancia_manda", "proposta"]
                                          if nome == "plancia" else ["proposta", "fallo"])),
              "la skill nel repo è più vecchia del programma")
        prova(f"la skill {nome} ha il suo frontmatter",
              costante.lstrip().startswith("---") and "description:" in costante)

    # -------------------------------------------------------------------- front
    esito = subprocess.run([sys.executable, str(RADICE / "tools" / "prova-front.py")],
                           capture_output=True)
    fuori = esito.stdout.decode()
    for riga in fuori.splitlines():
        if riga.strip().startswith(("ok ", "NO ")):
            prova(riga.split(None, 1)[1].strip(), riga.strip().startswith("ok"))

    # ------------------------------------------------------------------- stile
    # la regola di casa: niente em dash nei testi che legge una persona
    fuori = []
    for percorso in [RADICE / "README.md", RADICE / "README.it.md",
                     RADICE / "site" / "index.html"]:
        if percorso.exists() and "—" in percorso.read_text(encoding="utf-8"):
            fuori.append(percorso.name)
    prova("niente em dash nei testi pubblici", not fuori, str(fuori))

    print()
    print(f"{passati} passate, {len(falliti)} fallite")
    if falliti:
        print("fallite: " + ", ".join(falliti))
    shutil.rmtree(CASA, ignore_errors=True)
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(main())
