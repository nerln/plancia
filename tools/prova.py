#!/usr/bin/env python3
"""Il collaudo: gira tutto su un archivio finto e non tocca il tuo.

    python3 tools/prova.py

Non è una suite di test completa e non pretende di esserlo. È la lista delle
cose che si sono rotte almeno una volta, messe in fila, così prima di una
release si sa in dieci secondi se una di quelle è tornata a rompersi.
"""

import importlib.util
import io
import json
import os
import re
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
        # un controllo che qui non si puo' fare (manca un programma, l'ambiente e'
        # un altro) passa lo stesso, con il perche' scritto accanto
        nota = f"  ({dettaglio})" if str(dettaglio).startswith("saltato") else ""
        print(f"  ok   {nome}{nota}")
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

    def codex_rotto(esito=None, escl=None):
        if esito is not None:
            esito["ok"] = False
        return []

    lavagna.da_codex = codex_rotto
    lavagna.da_claude = lambda esito=None, escl=None: []
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
          _t._etichetta("-private-tmp-claude-501-Users-utente-Library-"
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

    # --------------------------------------------------- progetto dai percorsi
    # La cartella da cui una sessione e' stata aperta quasi non dice niente:
    # queste sono le regole con cui si guarda invece cosa ha toccato.
    from plancia import attribuzione as attr  # noqa: E402
    CASA_FINTA = "/Users/tizio"
    DRIVE_FINTO = CASA_FINTA + "/Library/CloudStorage/GoogleDrive-x/Il mio Drive"
    RADICI = {"/Users/tizio/dev/plancia", "/Users/tizio/dev/paratia",
              DRIVE_FINTO + "/Lavoro/Cowork"}
    GEN = attr.radici_generiche(home=CASA_FINTA, drive=DRIVE_FINTO)

    e = attr.decidi(DRIVE_FINTO, ["/Users/tizio/dev/plancia/a.py"] * 3
                    + ["/Users/tizio/dev/paratia/b.py"], RADICI, GEN)
    prova("da una cartella generica il progetto lo dicono i percorsi",
          e["dir"] == "/Users/tizio/dev/plancia" and e["da"] == "percorsi"
          and e["n"] == 4, str(e))

    e = attr.decidi("/Users/tizio/dev/paratia",
                    ["/Users/tizio/dev/plancia/a.py"] * 2
                    + ["/Users/tizio/dev/paratia/b.py"] * 3, RADICI, GEN)
    prova("una cwd che e' gia' un progetto non si scavalca per due file",
          e["dir"] == "/Users/tizio/dev/paratia" and e["da"] == "cwd", str(e))

    e = attr.decidi("/Users/tizio/dev/paratia",
                    ["/Users/tizio/dev/plancia/a.py"] * 9
                    + ["/Users/tizio/dev/paratia/b.py"], RADICI, GEN)
    prova("con il 90% dei percorsi altrove la cwd si scavalca",
          e["dir"] == "/Users/tizio/dev/plancia" and e["da"] == "percorsi", str(e))

    e = attr.decidi("/Users/tizio/dev/paratia/lab", [], RADICI, GEN)
    prova("una sottocartella conta come il progetto che la contiene",
          e["dir"] == "/Users/tizio/dev/paratia" and e["da"] == "cwd", str(e))

    e = attr.decidi(DRIVE_FINTO, [], RADICI, GEN)
    prova("senza percorsi e senza cartella nota non si inventa niente",
          e["dir"] is None and e["da"] == "nessuno", str(e))

    prova("le chiamate interne di Plancia restano interne",
          attr.decidi(str(config.DATA_DIR), [], RADICI, GEN)["categoria"] == "interna")
    prova("lo scratchpad e le cartelle drift-* restano temporanee",
          attr.decidi("/private/var/folders/j7/x/T/drift-ab12/p", [], RADICI,
                      GEN)["categoria"] == "temporanea"
          and attr.decidi("/private/tmp/claude-501/x/scratchpad", [], RADICI,
                          GEN)["categoria"] == "temporanea")

    # I pareggi si rompono con il primo tocco, non con l'ordine del dizionario
    e = attr.decidi(DRIVE_FINTO, ["/Users/tizio/dev/paratia/b.py",
                                  "/Users/tizio/dev/plancia/a.py"], RADICI, GEN)
    prova("a pari merito vince la cartella toccata per prima",
          e["dir"] == "/Users/tizio/dev/paratia", str(e))

    # Le virgolette: la radice del Drive si chiama «Il mio Drive», con gli spazi
    trovati = attr.percorsi_da_comando(
        'git -C /Users/tizio/dev/plancia status && cat "%s/Lavoro/Cowork/n o t a.md"'
        % DRIVE_FINTO)
    prova("dal comando escono sia il percorso nudo sia quello con gli spazi",
          set(trovati) == {"/Users/tizio/dev/plancia",
                           DRIVE_FINTO + "/Lavoro/Cowork/n o t a.md"}, str(trovati))
    prova("un glob nel comando si accorcia alla sua cartella",
          attr.percorsi_da_comando("ls /Users/tizio/dev/paratia/*.py")
          == ["/Users/tizio/dev/paratia"])
    prova("il numero di riga e la virgola non finiscono nel percorso",
          attr.percorsi_da_comando("sed -n 1p /Users/tizio/dev/plancia/a.py:42,")
          == ["/Users/tizio/dev/plancia/a.py"])
    prova("gli input dei tool danno file_path, path e glob",
          attr.percorsi_da_tool_use({"input": {"file_path": "/Users/tizio/dev/plancia/x.py"}})
          + attr.percorsi_da_tool_use({"input": {"pattern": "/Users/tizio/dev/paratia/**/*.ts"}})
          == ["/Users/tizio/dev/plancia/x.py", "/Users/tizio/dev/paratia"])

    # I conteggi di due sync diversi si sommano, o una sessione lunga finirebbe
    # attribuita in base al solo ultimo pezzo letto
    fusi = attr.fondi({"/Users/tizio/dev/plancia": [3, 0]},
                      {"/Users/tizio/dev/plancia": [2, 0], "/Users/tizio/dev/paratia": [1, 1]})
    prova("i percorsi di due letture si sommano",
          fusi["/Users/tizio/dev/plancia"][0] == 5 and "/Users/tizio/dev/paratia" in fusi,
          str(fusi))

    # le colonne nuove devono esserci ed essere ammesse a NULL, o la Plancia
    # installata dall'altra copia smetterebbe di scrivere su questo database
    colonne = {r["name"]: r for r in conn.execute("PRAGMA table_info(sessions)")}
    prova("le colonne dell'attribuzione ci sono e non sono obbligatorie",
          all(c in colonne and not colonne[c]["notnull"]
              for c in ("dir_dedotta", "dedotto_da", "n_percorsi", "radici_toccate")),
          str(sorted(colonne)))

    # ---------------------------------------------------------- riattribuzione
    # Un giro vero su un transcript finto: deve leggere il file, dedurre la
    # cartella e scriverla in tabella senza creare progetti nuovi.
    finta = CASA / "transcript-finto.jsonl"
    riga = {"type": "assistant", "timestamp": "2026-09-03T10:00:00Z",
            "cwd": str(config.HOME), "message": {"model": "claude-opus-5", "content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": str(RADICE / "plancia" / "ingest.py")}}]}}
    finta.write_text("\n".join(json.dumps(riga) for _ in range(4)), "utf-8")
    radici_vere = sorted({str(RADICE)}, key=len, reverse=True)
    letto = ingest.conta_percorsi(finta, radici_vere)
    prova("conta_percorsi vede i tool_use e li mette sotto la loro radice",
          letto["radici"].get(str(RADICE), [0])[0] == 4, str(letto))

    prima_progetti = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    conn.execute("INSERT INTO sessions(session_id, cwd, file, agent, started_at) "
                 "VALUES('finta-riattr', ?, ?, 'claude', '2026-09-03T10:00:00Z')",
                 (str(config.HOME), str(finta)))
    conn.commit()
    esiti = ingest.riattribuisci(conn)
    dopo = conn.execute("SELECT dir_dedotta, dedotto_da, n_percorsi FROM sessions "
                        "WHERE session_id='finta-riattr'").fetchone()
    prova("la riattribuzione scrive cartella dedotta e prova",
          dopo["dedotto_da"] in ("percorsi", "nessuno") and esiti["lette"] >= 1,
          str(dict(dopo)))
    prova("la riattribuzione non crea progetti nuovi",
          conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == prima_progetti)
    conn.execute("DELETE FROM sessions WHERE session_id='finta-riattr'")
    conn.commit()

    # --------------------------------------------------------- git delle cartelle
    # `git status` dentro il Drive puo' prendere minuti: ogni file tracciato e' un
    # segnaposto che il file provider deve verificare. Misurato il 9 agosto 2026
    # su una cartella da 681 file: due minuti e 51 secondi, contro dieci
    # millisecondi per un repo sul disco, ed erano venti dei quaranta secondi di
    # ogni sync.
    prova("dal ramo con upstream si prende solo il nome",
          ingest._leggi_stato("## main...origin/main [ahead 1]\n M a.py\n?? b.py")
          == ("main", 2))
    prova("e regge un ramo senza upstream",
          ingest._leggi_stato("## feature/x") == ("feature/x", 0))
    prova("e la testa staccata non diventa un ramo vero",
          ingest._leggi_stato("## HEAD (no branch)")[0] == "HEAD (no branch)")
    # Il caso che conta: lo stato non arrivato non deve diventare "pulito".
    prova("lo stato mancante resta ignoto, non zero",
          ingest._leggi_stato(None) == (None, None))
    prima = conn.execute("SELECT COUNT(*) FROM repos WHERE dirty IS NULL").fetchone()[0]
    conn.execute("INSERT INTO repos(name, local_path, branch, dirty) VALUES(?,?,?,?)",
                 ("repo-lento", "/tmp/repo-lento", "main", 7))
    conn.execute(
        "INSERT INTO repos(name, local_path, branch, dirty) VALUES(?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET branch=COALESCE(excluded.branch, repos.branch), "
        "dirty=COALESCE(excluded.dirty, repos.dirty)",
        ("repo-lento", "/tmp/repo-lento", None, None))
    tenuto = conn.execute("SELECT branch, dirty FROM repos WHERE name='repo-lento'").fetchone()
    prova("una cartella troppo lenta tiene i valori di prima",
          tuple(tenuto) == ("main", 7), str(tuple(tenuto)))
    conn.execute("DELETE FROM repos WHERE name='repo-lento'")
    conn.commit()
    prova("e non lascia righe senza stato in giro",
          conn.execute("SELECT COUNT(*) FROM repos WHERE dirty IS NULL").fetchone()[0] == prima)

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

    import socket
    import time

    # Il server non deve fare il DNS inverso all'avvio. `HTTPServer.server_bind`
    # chiama `socket.getfqdn()` con la porta gia' presa e non ancora in ascolto: su
    # un runner macOS di CI ci ha messo decine di secondi, e in quel tempo ogni
    # connessione restava appesa (SYN scartati) fino al timeout. Qui `getfqdn` e' un
    # finto che si segna la chiamata: il server di Plancia non deve toccarlo.
    vero_getfqdn = socket.getfqdn
    chiamate_dns = []
    socket.getfqdn = lambda *a, **k: (chiamate_dns.append(a), "lento.invalid")[1]
    try:
        provvisorio = api._Server(("127.0.0.1", 0), api.Handler)
        legato = provvisorio.server_address[1] > 0
        provvisorio.server_close()
    finally:
        socket.getfqdn = vero_getfqdn
    prova("il server si mette in ascolto senza il DNS inverso (getfqdn)",
          legato and not chiamate_dns, f"getfqdn chiamato {len(chiamate_dns)} volte")

    # Una porta libera scelta dal sistema, non una fissa: su un runner di CI la 7791
    # puo' essere gia' presa, e la prova non deve dipendere da chi c'e' sulla macchina.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.bind(("127.0.0.1", 0))
        porta = sonda.getsockname()[1]
    # Lo stesso finto resta al suo posto mentre parte il server vero di questa
    # prova: la classe senza DNS inverso non basta se serve() non la usa (un
    # merge che rimette ThreadingHTTPServer in serve() lascerebbe verde il
    # controllo qui sopra). Si toglie appena il server risponde.
    chiamate_serve = []
    socket.getfqdn = lambda *a, **k: (chiamate_serve.append(a), "lento.invalid")[1]
    filo = threading.Thread(target=api.serve, kwargs={"port": porta,
                                                      "sync_first": False},
                            daemon=True)
    filo.start()

    # Il server parte in un filo di questo processo e prima di mettersi in ascolto
    # apre l'archivio e riconcilia i lanci: su una macchina carica (un runner macOS
    # di CI) ci mette molto piu' di un secondo e mezzo, e una richiesta arrivata
    # prima resta senza risposta fino al timeout. Si aspetta che risponda davvero,
    # fino a 90 secondi, invece di dormire a occhio. Se non risponde mai, ogni
    # controllo qui sotto segna il suo NO con il perche': nessuno sparisce.
    ultimo_errore = ["il server non ha mai risposto"]
    partenza = time.time()
    while time.time() - partenza < 90:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status",
                                        timeout=5):
                ultimo_errore[0] = ""
                break
        except Exception as errore:        # noqa: BLE001
            ultimo_errore[0] = f"{type(errore).__name__}: {errore}"
            time.sleep(0.25)
    attesa_server = time.time() - partenza
    socket.getfqdn = vero_getfqdn
    prova("serve() mette in ascolto il server senza il DNS inverso (getfqdn)",
          not ultimo_errore[0] and not chiamate_serve,
          f"getfqdn chiamato {len(chiamate_serve)} volte; {ultimo_errore[0]}")
    if ultimo_errore[0]:
        # non ha mai risposto: dove sta ferma la macchina lo dicono le pile dei fili
        import faulthandler
        print(f"   (il server non ha risposto in {attesa_server:.0f} s: {ultimo_errore[0]})")
        faulthandler.dump_traceback(file=sys.stdout, all_threads=True)
    elif attesa_server > 3:
        print(f"   (il server ha risposto dopo {attesa_server:.1f} s)")

    def prendi(percorso):
        """Il JSON di una rotta; se non risponde torna {} e il controllo che la
        legge segna il suo NO (senza sollevare, senza far sparire gli altri)."""
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}{percorso}",
                                        timeout=60) as r:
                return json.loads(r.read())
        except Exception as errore:        # noqa: BLE001
            ultimo_errore[0] = f"{percorso}: {type(errore).__name__}: {errore}"
            return {}

    def perche():
        return ultimo_errore[0]

    o = prendi("/api/overview?lang=en")
    prova("/api/overview risponde", "stats" in o, perche())
    prova("l'overview porta le proposte", isinstance(o.get("proposte"), list), perche())
    prova("l'overview conta la lavagna", "lavagna_aperti" in o.get("stats", {}), perche())
    prova("le proposte seguono la lingua chiesta",
          isinstance(o.get("proposte"), list)
          and not any("Ci mando" in x["testo"] for x in o["proposte"]), perche())
    prova("/api/lavagna risponde", "voci" in prendi("/api/lavagna"), perche())
    prova("/api/runs risponde", isinstance(prendi("/api/runs?limite=3"), list), perche())
    prova("/api/eventi risponde", isinstance(prendi("/api/eventi").get("eventi"), list),
          perche())
    prova("/api/proposte risponde", isinstance(prendi("/api/proposte?lang=it"), list),
          perche())
    # Il 9 agosto questa risposta e' passata da lista a oggetto, e la palette
    # continuava a fare `hits.length` su un oggetto: niente errore, zero
    # risultati per sempre. Il contratto va scritto da qualche parte.
    ric = prendi("/api/search?q=plancia")
    prova("/api/search torna le tre chiavi, non una lista",
          isinstance(ric, dict) and {"turni", "progetti", "schede"} <= set(ric),
          str(type(ric)) + " " + perche())
    # Ogni rotta che una vista chiama, chiamata almeno una volta. Prima ne
    # erano coperte cinque su diciassette: una qualsiasi delle altre poteva
    # rispondere 500 e la vista restare bianca senza che niente lo dicesse.
    # E' la stessa classe di difetto della palette, trovata a mano.
    # `/api/briefing` risponde testo, non JSON: e' il file che l'hook infila
    # in ogni sessione, e va letto come tale.
    ROTTE = [
        ("/api/briefing", "testo"), ("/api/projects", "json"),
        ("/api/tasks", "json"), ("/api/posts", "json"),
        ("/api/sessions?limit=3", "json"), ("/api/events?limit=3", "json"),
        ("/api/knowledge", "json"), ("/api/agents", "json"),
        ("/api/capabilities", "json"), ("/api/status", "json"),
        ("/api/voice/status", "json"), ("/api/recap?solo_cache=1", "json"),
        ("/api/memoria/mappa", "json"), ("/api/memoria/prova?q=swap", "json"),
    ]
    rotti = []
    for rotta, forma in ROTTE:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{porta}{rotta}", timeout=60) as risposta:
                corpo = risposta.read()
                if risposta.status != 200:
                    raise RuntimeError(f"HTTP {risposta.status}")
                if forma == "json":
                    json.loads(corpo)
        except Exception as errore:        # noqa: BLE001
            rotti.append(f"{rotta}: {type(errore).__name__}: {errore}")
    prova("ogni rotta di lettura risponde", not rotti, "; ".join(rotti))

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=60) as r:
            pagina = r.read().decode()
    except Exception as errore:            # noqa: BLE001
        pagina = ""
        ultimo_errore[0] = f"/: {type(errore).__name__}: {errore}"
    prova("la pagina si serve", "<title>" in pagina, perche())

    # Le viste del front chiamano rotte scritte a mano nel JS: se una sparisce
    # dall'API il collaudo qui sopra non se ne accorge, perche' controlla la
    # lista che ho scritto io. Questo confronta le due liste (nessuna richiesta:
    # e' solo lettura dei sorgenti, quindi non dipende dalla rete).
    js = (RADICE / "web" / "app.js").read_text(encoding="utf-8")
    api_py = (RADICE / "plancia" / "api.py").read_text(encoding="utf-8")
    # Le rotte con un id il front le costruisce concatenando: `/api/tasks/`
    # piu' il numero. Della stringa nel JS resta la barra finale, che qui si
    # toglie per confrontarla con la rotta di lista.
    chiamate = {m.split("?")[0].rstrip("/") for m in re.findall(r"/api/[a-z/_]+", js)}
    serve = set(re.findall(r'path == "(/api/[a-z_/]+)"', api_py))
    serve |= {m.rstrip("/") for m in re.findall(r'\^(/api/[a-z_/]+)/', api_py)}
    fantasma = sorted(chiamate - serve - {"/api"})
    prova("il front non chiama rotte che non esistono",
          not fantasma, ", ".join(fantasma))

    # --------------------------------------------------------------- scrittura
    # senza token le scritture devono essere rifiutate
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{porta}/api/tasks",
                                     data=b'{"title":"abusivo"}',
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        urllib.request.urlopen(req, timeout=60)
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
    # La prova va sempre contata, con o senza node: se sparisce quando node
    # manca, il numero totale di prove eseguite cambia da una macchina
    # all'altra (188 senza node, 189 con), il README dichiara un solo numero
    # fisso, e la prova sul README (più sotto) diventa rossa da sola su chi
    # non ha node installato, non per una regressione vera. Il gancio
    # pre-push la bloccherebbe: misurato, `env PATH=/usr/bin:/bin:/usr/sbin:/sbin
    # python3 tools/prova.py` dava "eseguite 188" contro un README a 189.
    if shutil.which("node"):
        esito = subprocess.run(["node", "--check", str(RADICE / "web" / "app.js")],
                               capture_output=True)
        prova("app.js si compila", esito.returncode == 0,
              esito.stderr.decode()[:200])
    else:
        prova("app.js si compila (node assente: non verificato)", True,
              "installa node per verificare davvero")

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

        # La ricerca e' il motivo per cui questo server vale la spesa: se torna
        # solo le schede vuol dire che l'indice sui turni non e' arrivato fin
        # qui, e da dentro una sessione non si vedrebbe la differenza.
        ric = mcp_chiama(server, "tools/call",
                         {"name": "plancia_search", "arguments": {"query": "plancia"}}, 5)
        testo = "".join(c.get("text", "") for c in
                        ric.get("result", {}).get("content", []))
        prova("plancia_search risponde dai turni, non solo dalle schede",
              "nei_turni" in testo, testo[:120])
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
    # L2-SKILL (16/09) ha tolto "plancia_manda" dal testo della skill (i lanci
    # headless spariscono, resta "riprendi" un task): l'elenco atteso segue il
    # testo nuovo invece di quello vecchio. `_sc.SKILL` è diventato `SKILL_IT`
    # perché ora esiste anche `SKILL_EN` (vedi tools/prove/skill.py per le
    # prove sulle due lingue).
    from plancia import setup_claude as _sc  # noqa: E402
    for nome, costante in (("plancia", _sc.SKILL_IT), ("riepilogo", _sc.RIEPILOGO_SKILL)):
        prova(f"la skill {nome} parla delle cose che ci sono",
              all(p in costante for p in (["plancia_task_add", "riprendi", "send_message"]
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

    # ---------------------------------------------------------------- richiamo
    # Il richiamo scrive in contesto senza chiedere niente a nessuno, quindi gli
    # errori che fa non si vedono: si vedono solo le risposte che ne escono. Qui
    # si controlla soprattutto che sappia tacere.
    from plancia import richiamo  # noqa: E402

    QUI = "-Users-tizio-dev-alfa"
    ALTROVE = "-Users-tizio-dev-beta"

    def memoria(nome, tipo, scope, descrizione, corpo):
        # I legami si ricavano dal corpo come fa l'ingest vero: scriverli a mano
        # qui vorrebbe dire provare una cosa diversa da quella che gira.
        prosa = re.sub(r"`[^`\n]*`", " ", re.sub(r"```.*?```", " ", corpo, flags=re.S))
        legami = json.dumps(sorted(set(re.findall(r"\[\[([^\]]+)\]\]", prosa))))
        conn.execute(
            "INSERT OR REPLACE INTO knowledge(name, path, scope, description, type, "
            "body, links, updated_at) VALUES(?,?,?,?,?,?,?,'2026-01-01T00:00:00Z')",
            (nome, f"/finto/{scope}/memory/{nome}.md", scope, descrizione, tipo, corpo,
             legami))

    # I corpi sono lunghi apposta: sotto SOSTANZA_MINIMA il richiamo scarta, e
    # una memoria finta troppo magra farebbe fallire le prove per il motivo
    # sbagliato. E' anche il motivo per cui quella regola esiste.
    LUNGO = (" Questo corpo esiste per avere abbastanza sostanza da superare la"
             " soglia sotto la quale una memoria e' solo un titolo rimasto li'."
             " Serve a provare il richiamo, non a dire qualcosa di vero.")
    memoria("niente-swap", "feedback", ALTROVE,
            "il Mac ha 16 GB e lo swap lo uccide",
            "Il preventivo di memoria va fatto prima di allocare il modello." + LUNGO)
    # la stessa memoria copiata anche nella cartella corrente: e' il caso che
    # sfuggiva, perche' la copia di la' passava il filtro sulla cartella
    memoria("barra-injection", "feedback", ALTROVE,
            "rifiuta i tool dove il contenuto remoto diventa istruzione",
            "Giudica l'architettura, non la pulizia del codice." + LUNGO)
    memoria("barra-injection", "feedback", QUI,
            "rifiuta i tool dove il contenuto remoto diventa istruzione",
            "Giudica l'architettura, non la pulizia del codice." + LUNGO)
    memoria("alfa-stato", "project", ALTROVE,
            "lo stato del progetto alfa",
            "Il prossimo passo di alfa e' la memoria, lo swap e l'injection." + LUNGO)
    # Il titolo rimasto li': deve restare fuori dal richiamo anche se le parole
    # cercate ci stanno tutte dentro. E' il caso che ha fatto nascere la regola.
    memoria("codici-di-prova", "reference", ALTROVE,
            "Codici di verifica del progetto", "Codici di verifica del progetto.")
    conn.commit()
    store.rebuild_search(conn)
    conn.commit()

    r = richiamo.cerca(conn, "quanta memoria serve prima di allocare il modello",
                       escludi_scope=QUI)
    prova("richiama la memoria scritta in un'altra cartella",
          [x["nome"] for x in r] == ["niente-swap"], str([x["nome"] for x in r]))

    r = richiamo.cerca(conn, "quanta memoria serve prima di allocare il modello",
                       escludi_scope=ALTROVE)
    prova("e tace su quella che Claude Code ha già caricato da sé", r == [],
          str([x["nome"] for x in r]))

    r = richiamo.cerca(conn, "il contenuto remoto diventa istruzione nei tool",
                       escludi_scope=QUI)
    prova("una copia in un'altra cartella non la fa tornare", r == [],
          str([x["nome"] for x in r]))

    r = richiamo.cerca(conn, "il prossimo passo del progetto alfa quale sarebbe",
                       escludi_scope=QUI)
    prova("le memorie di progetto restano fuori dal richiamo", r == [],
          str([x["nome"] for x in r]))

    r = richiamo.cerca(conn, "qual e il codice di verifica del progetto",
                       escludi_scope=QUI)
    prova("una memoria che è solo un titolo non richiama, per quanto combaci",
          r == [], str([x["nome"] for x in r]))

    prova("una frase corta non richiama niente",
          richiamo.cerca(conn, "ok grazie") == [])
    prova("una frase che non c'entra non richiama niente",
          richiamo.cerca(conn, "rinomina la funzione e aggiorna i test") == [])

    r = richiamo.cerca(conn, "quanta memoria serve prima di allocare il modello",
                       escludi_scope=QUI, salta={"niente-swap"})
    prova("nella stessa sessione non si ripete", r == [], str([x["nome"] for x in r]))

    richiamo.segna_detto("prova-sessione", ["niente-swap"])
    prova("e il segnaposto della sessione se lo ricorda",
          "niente-swap" in richiamo.gia_detto("prova-sessione"))

    testo = richiamo.blocco([{
        "nome": "niente-swap", "descrizione": "il Mac ha 16 GB", "tipo": "feedback",
        "scope": ALTROVE, "corpo": "x" * 4000, "path": "", "punteggio": 9.0}])
    prova("il blocco in contesto resta corto",
          0 < len(testo) <= richiamo.MAX_CARATTERI, f"{len(testo)} caratteri")
    prova("e dice che è contesto, non istruzioni", "non istruzioni" in testo)

    # Le sigle. Il filtro sulla lunghezza ne buttava via una classe intera:
    # `ram`, `api`, `css`, `gpu`, `mcp` sono corte quanto `per` e `che`, e sono
    # i termini che discriminano di più in quello che scrive.
    termini = richiamo.parole("quanta ram serve per le api css del mio mac")
    prova("le sigle di tre lettere sopravvivono",
          {"ram", "api", "css", "mac"} <= set(termini), str(termini))
    prova("e le parole vuote di tre lettere no",
          not ({"per", "del", "che", "due"} & set(termini)), str(termini))

    # ------------------------------------------------------------------ mappa
    from plancia import mappa as _mappa  # noqa: E402

    m = _mappa.mappa(conn)
    nomi = [n["nome"] for n in m["nodi"]]
    prova("la mappa conta i fatti, non i file",
          len(nomi) == len(set(nomi)), f"{len(nomi)} nodi, {len(set(nomi))} nomi")
    prova("e la memoria in due cartelle resta un nodo solo",
          nomi.count("barra-injection") == 1, str(nomi))

    doppia = next((n for n in m["nodi"] if n["nome"] == "barra-injection"), None)
    prova("che però si ricorda di stare in due posti",
          doppia and len(doppia["cartelle"]) == 2, str(doppia and doppia["cartelle"]))
    prova("e finisce fra le doppie della diagnosi",
          "barra-injection" in [d["nome"] for d in m["diagnosi"]["doppie"]])

    prova("la diagnosi dice quante ne può richiamare il richiamo",
          m["diagnosi"]["richiamabili"] == sum(1 for n in m["nodi"] if n["richiamabile"])
          and m["diagnosi"]["richiamabili"] < m["diagnosi"]["totale"],
          f"{m['diagnosi']['richiamabili']}/{m['diagnosi']['totale']}")

    # Un rinvio dentro i backtick e' sintassi, non un legame: `[[item]]`, che e'
    # la chiave di un file di configurazione citata in una memoria, risultava un
    # link rotto per sempre.
    from plancia import ingest as _ing  # noqa: E402
    import re as _re
    prosa = _re.sub(r"`[^`\n]*`", " ",
                    _re.sub(r"```.*?```", " ", "vedi [[vero]] e la chiave `[[item]]` qui",
                            flags=_re.S))
    prova("i doppi quadri dentro il codice non sono legami",
          _re.findall(r"\[\[([^\]]+)\]\]", prosa) == ["vero"], prosa)

    # Un legame verso un progetto che esiste non e' rotto: e' una memoria che
    # varrebbe la pena scrivere, e chiamarla rotta trasforma un invito in un
    # rimprovero.
    conn.execute("INSERT OR IGNORE INTO projects(key, name) VALUES('molo','molo')")
    memoria("cita-un-progetto", "feedback", ALTROVE, "cita un progetto vero",
            "Segue lo schema di [[molo]] e rinvia anche a [[mai-vista]]." + LUNGO)
    conn.commit()
    m2 = _mappa.mappa(conn)
    prova("un legame verso un progetto vero è una memoria da scrivere",
          "molo" in m2["diagnosi"]["da_scrivere"], str(m2["diagnosi"]["da_scrivere"]))
    prova("e uno verso il nulla resta un link rotto",
          "mai-vista" in [x["verso"] for x in m2["diagnosi"]["rotti"]],
          str(m2["diagnosi"]["rotti"]))

    # Una memoria cancellata dal disco deve sparire dall'archivio al giro dopo.
    fantasma = "/finto/sparita/memory/fantasma.md"
    conn.execute(
        "INSERT OR REPLACE INTO knowledge(name, path, scope, type, body, links, updated_at) "
        "VALUES('fantasma',?,?, 'feedback','x','[]','2026-01-01T00:00:00Z')",
        (str(config.CLAUDE_PROJECTS / "sparita" / "memory" / "fantasma.md"), "sparita"))
    conn.commit()
    _ing.sync_memory(conn)
    resta = conn.execute("SELECT COUNT(*) FROM knowledge WHERE name='fantasma'").fetchone()[0]
    prova("una memoria sparita dal disco esce dall'archivio", resta == 0, str(fantasma))

    p = _mappa.prova(conn, "quanta memoria serve prima di allocare il modello")
    prova("la prova del richiamo dice cosa ha preso",
          [x["nome"] for x in p["presi"]] == ["niente-swap"], str(p["presi"]))
    prova("e mostra anche chi ha perso",
          all(x["nome"] != "niente-swap" for x in p["scartati"]))
    prova("una frase corta la prova la dichiara corta",
          _mappa.prova(conn, "ok")["corta"] is True)

    # ---------------------------------------------------------------- esporta
    # Il file che va sul telefono. La proprietà che conta non è che sia bello:
    # è che non chieda niente a nessuno, perché il motivo per cui esiste è
    # portarsi l'archivio in tasca senza farlo passare da un servizio.
    from plancia import esporta as _esp  # noqa: E402

    fuori = CASA / "memoria.html"
    percorso, peso, quante = _esp.esporta(fuori)
    pagina = fuori.read_text(encoding="utf-8")
    prova("l'esportazione scrive un file solo", fuori.exists() and peso > 500,
          f"{peso} byte")
    prova("e ci mette dentro le memorie", quante > 0, str(quante))

    # Niente che si carichi da fuori: un solo <link>, un font o un'immagine
    # remota vorrebbero dire che aprire l'archivio dice a qualcuno che l'hai
    # aperto. Si guarda il markup, non il testo delle memorie, che di URL ne
    # contiene parecchi in modo legittimo. Da L1-FONT: i tre font vendorizzati
    # entrano come url(data:font/woff2;base64,...) dentro @font-face, quindi
    # uno url( nudo non basta più a distinguere un font incorporato da uno
    # remoto: si guarda dentro le parentesi e si segnala ogni url(...) il cui
    # contenuto, tolti apici e spazi, non comincia con "data:" (case
    # insensitivo: prende anche url(HTTPS://...) e url(//host/x), che un
    # controllo che cerca solo "http" lascerebbe passare).
    senza_dati = re.sub(r"const DATI = .*?;\n", "", pagina, flags=re.S)
    url_remoti = [u for u in re.findall(r"url\(([^)]*)\)", senza_dati)
                  if not u.strip().strip("'\"").lower().startswith("data:")]
    fughe = [s for s in ("<link", "<script src", "<img", "@import",
                         "fetch(", "XMLHttpRequest", "//cdn", "https://")
             if s in senza_dati]
    if url_remoti:
        fughe.append(f"url(...) con http dentro: {url_remoti}")
    prova("il file non carica niente da fuori", not fughe, str(fughe))

    dati_finti = {"memorie": [{"n": "x", "t": "feedback", "d": "</script><b>rotto",
                               "c": "", "q": "qui", "a": "2026-01-01", "r": True}],
                  "progetti": [], "task": [], "quando": "ora"}
    prova("una memoria che contiene un tag di chiusura non chiude lo script",
          "</script><b>rotto" not in _esp.costruisci(dati_finti))

    # ------------------------------------------------------------------- stile
    # la regola di casa: niente em dash nei testi che legge una persona
    fuori = []
    for percorso in [RADICE / "README.md", RADICE / "README.it.md",
                     RADICE / "site" / "index.html"]:
        if percorso.exists() and "—" in percorso.read_text(encoding="utf-8"):
            fuori.append(percorso.name)
    prova("niente em dash nei testi pubblici", not fuori, str(fuori))

    # ---------------------------------------------------------------- scoperta
    # Ogni lotto porta le sue prove in un file sotto tools/prove/, invece di
    # doverle infilare tutte qui dentro: un file solo con un proprietario solo
    # per ondata diventerebbe un collo di bottiglia appena due lotti lavorano
    # in parallelo. Un modulo che comincia con "_" è materiale di supporto
    # (una funzione condivisa, un fixture), non una prova, e va saltato. Un
    # modulo che alza un'eccezione all'importazione o all'esecuzione non deve
    # fermare gli altri: conta come una prova fallita con il nome del file, e
    # si continua.
    cartella_prove = RADICE / "tools" / "prove"
    if cartella_prove.is_dir():
        for percorso in sorted(cartella_prove.glob("*.py")):
            if percorso.stem.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"tools.prove.{percorso.stem}", percorso)
                modulo = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(modulo)
                modulo.esegui(prova)
            except Exception as errore:  # noqa: BLE001 - un lotto non affossa gli altri
                falliti.append(percorso.stem)
                print(f"  NO   {percorso.stem} (errore nel modulo: {errore})")

    # ------------------------------------------------------------------ readme
    # Il README dichiara quante prove gira questa suite, così chi arriva prima
    # di fidarsi legge un numero invece di dover contare. Se diverge dal vero,
    # sta mentendo a chi legge: qualcuno ha aggiunto (o tolto) una prova senza
    # aggiornare la riga. Il +1 nel confronto è questa prova stessa: il numero
    # dichiarato deve contare anche lei, non solo quelle venute prima.
    schema_numero = re.compile(r"(\d+)\s+(?:prove|controlli|checks)\b")
    dichiarati = {}
    for percorso in (RADICE / "README.md", RADICE / "README.it.md"):
        if not percorso.exists():
            continue
        trovato = schema_numero.search(percorso.read_text(encoding="utf-8"))
        if trovato:
            dichiarati[percorso.name] = int(trovato.group(1))
    atteso = passati + len(falliti) + 1
    if not dichiarati:
        prova("il README dichiara quante prove gira la suite", False,
              "cercato 'N prove/controlli/checks' in README.md e README.it.md: non trovato")
    else:
        prova("il numero di prove nel README è quello vero",
              all(n == atteso for n in dichiarati.values()),
              f"dichiarato {dichiarati}, eseguite {atteso}")

    print()
    print(f"{passati} passate, {len(falliti)} fallite")
    if falliti:
        print("fallite: " + ", ".join(falliti))
    shutil.rmtree(CASA, ignore_errors=True)
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(main())
