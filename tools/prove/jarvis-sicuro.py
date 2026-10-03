"""Prove del pannello Jarvis dell'app Mac (percorso sicuro di `plancia/jarvis.py`
e voce a frasi di `plancia/voice.py`).

Cosa si dimostra, in ordine di importanza:

1. Il modello che risponde al pannello e' in SOLA LETTURA: ogni tool di scrittura
   dell'MCP e' negato per nome (non solo assente dall'elenco dei permessi), e
   nessuno di quelli ammessi scrive. Si legge dagli argomenti con cui il `claude`
   finto viene lanciato e si confronta con `mcp._SCRITTURE`.
2. Niente che scriva o avvii un agente parte da una frase: ne' dalle frasi
   riconosciute ("segna", "ho fatto", "archivia", "fallo"), ne' da una riga
   @@PROPOSTA del modello. Diventa una scheda, e l'archivio non cambia finche'
   `conferma` non viene chiamata. Una proposta si consuma una volta, scade, e vale
   solo nel compartimento in cui e' nata. "si" a voce non conferma.
3. Il testo scorre e la voce parte a frasi: i pezzi arrivano prima della fine, le
   frasi complete escono mentre il resto arriva, la riga della proposta non arriva
   mai a occhi o voce, nemmeno spezzata fra due pezzi.
4. Si ferma: `ferma_tutto` interrompe il turno e chiude il processo.
5. Lo stesso, via HTTP (NDJSON) con un server vero: la conferma senza token e'
   rifiutata.
6. La voce neurale non ripiega MAI su `say`: senza Pocket ne' Voicebox solleva
   `NessunaVoceNeurale`, e l'app usa le voci avanzate di sistema.

Isolamento (mai un `claude`/`codex` vero, mai i dati veri): `recap.claude_bin`
sostituito con uno script finto che parla lo stesso stream-json; Pocket e Voicebox
sostituiti (le sonde di rete non partono); il server HTTP gira in un sottoprocesso
con casa, HOME e CLAUDE_CONFIG_DIR propri.

`esegui(prova)` e' la firma che `tools/prova.py` scopre da sola.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

RADICE = Path(__file__).resolve().parent.parent.parent


def _carica_finti():
    if "_finti" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_finti", Path(__file__).resolve().parent / "_finti.py")
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["_finti"] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules["_finti"]


def _carica_saltati():
    """`_saltati.py` (materiale di supporto, non una prova) sta accanto a questo file."""
    if "_saltati" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_saltati", Path(__file__).resolve().parent / "_saltati.py")
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["_saltati"] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules["_saltati"]


_finti = _carica_finti()
_saltati = _carica_saltati()
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


# Il `claude` finto: stessa forma dello stream-json vero (--include-partial-messages),
# pezzi da 5 caratteri cosi' la riga @@PROPOSTA si spezza in mezzo alla marca.
CLAUDE_FINTO = (Path(__file__).resolve().parent / "_claude_finto_jarvis.py").read_text("utf-8")


def _porta_libera():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def _eventi(gen):
    return list(gen)


def _finale(eventi):
    return eventi[-1]["esito"] if eventi and eventi[-1].get("t") == "fine" else None


def esegui(reale) -> None:
    """Su Windows il modulo non si fa: il `claude` finto passerebbe da cmd.exe, che taglia gli
    argomenti a capo, e il pannello e' comunque solo dell'app Mac. I controlli si segnano
    saltati uno per uno (vedi `_saltati.py`), cosi' il conteggio e' lo stesso ovunque."""
    prova = _saltati.Contatore(reale)
    if _saltati.WIN:
        _saltati.salta_il_resto("jarvis-sicuro", prova)
    else:
        _esegui(prova)
    _saltati.chiudi("jarvis-sicuro", prova, reale)


def _esegui(prova) -> None:
    from plancia import actions, cantiere, config, jarvis, recap, store, voice
    from plancia import mcp

    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-jarvis-sicuro-"))
    finto = _finti.crea_finto(tmp / "bin", "claude-finto-sicuro", CLAUDE_FINTO)
    log = tmp / "claude-finto.log"
    os.environ["FINTO_LOG"] = str(log)
    vero_bin = recap.claude_bin
    recap.claude_bin = lambda: finto
    vero_avvia = cantiere.avvia
    lanci = []

    def avvia_finto(conn, titolo, *a, **kw):
        lanci.append((titolo, kw))
        return {"run": 4242}

    cantiere.avvia = avvia_finto
    vero_pocket, vero_vb, vero_say = voice.pocket_vivo, voice.voicebox_vivo, voice.sintesi_say
    vero_pocket_no, vero_vb_no = voice._pocket_no, voice._ultimo_no
    voice.pocket_vivo = lambda timeout=1.0: False
    voice.voicebox_vivo = lambda timeout=1.5: False

    try:
        conn = store.connect()
        store.init_db(conn)
        store.upsert_project(conn, "jv-sicuro", "Jarvis Sicuro", kind="prova", priority=2, pinned=0,
                             summary="progetto di prova")
        # Un progetto vicino per parole a "non-esiste": una proposta del modello
        # con una chiave inesistente non deve agganciarsi a questo per somiglianza
        # (su un archivio vero e' successo con un progetto con "non" nel nome).
        store.upsert_project(conn, "note-non-nostre", "Note non nostre", kind="prova",
                             priority=2, pinned=0, summary="progetto vicino per parole")
        conn.commit()
        n_task = lambda: conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        n_prog_att = lambda: conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status='attivo'").fetchone()[0]
        t_aperto = actions.task_add(conn, "Preparare la scheda di Jarvis", project="jv-sicuro")
        conn.commit()

        # ---------------------------------------------------------------- 1. sola lettura
        scritture = {"mcp__plancia__" + n for n in mcp._SCRITTURE}
        prova("ogni tool di scrittura dell'MCP e' negato a Jarvis",
              scritture <= set(jarvis.TOOL_NEGATI),
              str(sorted(scritture - set(jarvis.TOOL_NEGATI))))
        prova("nessun tool ammesso a Jarvis scrive",
              not (set(jarvis.TOOL_LETTURA) & scritture)
              and not (set(jarvis.TOOL_LETTURA) & set(jarvis.TOOL_NEGATI)),
              str(set(jarvis.TOOL_LETTURA) & (scritture | set(jarvis.TOOL_NEGATI))))
        prova("Bash, Write, Edit e la rete di Claude Code sono negati",
              {"Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"}
              <= set(jarvis.TOOL_NEGATI))
        prova("il tool che riepiloga e parla dal server non e' ammesso (`speak`)",
              "mcp__plancia__plancia_recap" in jarvis.TOOL_NEGATI
              and "mcp__plancia__plancia_speak" in jarvis.TOOL_NEGATI)

        # ---------------------------------------------------------------- 3. il testo scorre
        prima = n_task()
        ev = _eventi(jarvis.flusso("spiegami cosa bolle in pentola", "it", conn=conn))
        tipi = [e["t"] for e in ev]
        prova("il flusso comincia con lo stato e finisce con l'esito",
              tipi[0] == "stato" and tipi[-1] == "fine", str(tipi[:3]) + str(tipi[-2:]))
        pezzi = [e["d"] for e in ev if e["t"] == "testo"]
        prova("il testo arriva a pezzi, non tutto insieme", len(pezzi) >= 3, str(len(pezzi)))
        esito = _finale(ev) or {}
        prova("i pezzi messi insieme sono la risposta",
              "".join(pezzi).strip() == esito.get("risposta"), "".join(pezzi))
        frasi = [e for e in ev if e["t"] == "frase"]
        prova("le frasi complete escono una a una, ripulite per la voce",
              [f["d"] for f in frasi] ==
              ["Hai tre task aperti.", "Il primo scade domani. Il resto puo' aspettare."],
              str([f["d"] for f in frasi]))
        prova("la prima frase esce PRIMA che il testo sia finito",
              tipi.index("frase") < len(tipi) - 1 - tipi[::-1].index("testo"), str(tipi))
        prova("il pannello non scrive niente per una domanda", n_task() == prima)

        righe = log.read_text("utf-8").splitlines()
        argv = json.loads(next(r for r in righe if r.startswith("ARGV "))[5:])
        prova("il modello parte con i pezzi parziali e in sola lettura",
              "--include-partial-messages" in argv and "--disallowedTools" in argv
              and "--allowedTools" in argv, str(argv[:12]))
        if "--disallowedTools" in argv and "--allowedTools" in argv:
            i_no, i_si = argv.index("--disallowedTools"), argv.index("--allowedTools")
            negati = argv[i_no + 1:i_si] if i_no < i_si else argv[i_no + 1:]
            ammessi = argv[i_si + 1:i_no] if i_si < i_no else argv[i_si + 1:]
            prova("negli argomenti: i tool di scrittura sono nei negati e non negli ammessi",
                  scritture <= set(negati) and not (scritture & set(ammessi)),
                  "negati=%s ammessi=%s" % (negati, ammessi))

        # ---------------------------------------------------------------- 2. proposte
        def proposta_da_modello(json_riga):
            e = _eventi(jarvis.flusso("proponi: " + json_riga, "it", conn=conn))
            return e, _finale(e)

        e1, es1 = proposta_da_modello(json.dumps(
            {"azione": "task_add", "titolo": "Comprare il toner", "progetto": "jv-sicuro"}))
        testo_visto = "".join(x["d"] for x in e1 if x["t"] == "testo")
        parlato = " ".join(x["dire"] for x in e1 if x["t"] == "frase")
        prova("la riga @@PROPOSTA non arriva mai a occhi ne' voce, nemmeno spezzata",
              "@@" not in testo_visto and "PROPOSTA" not in testo_visto
              and "@@" not in parlato and "toner" not in testo_visto and "{" not in parlato,
              testo_visto + " | " + parlato)
        p1 = (es1 or {}).get("proposta") or {}
        prova("una proposta del modello diventa una scheda coi dati veri",
              p1.get("azione") == "task_add" and p1.get("id") and p1.get("rischio") == "scrive"
              and any(r["v"] == "Comprare il toner" for r in p1.get("righe", []))
              and any(r["v"] == "Jarvis Sicuro" for r in p1.get("righe", [])), str(p1))
        prova("...e l'archivio non cambia finche' non si conferma", n_task() == prima)

        c = jarvis.conferma(p1["id"], "it", conn=conn)
        prova("la conferma esegue, una volta",
              c.get("eseguita") and n_task() == prima + 1, str(c)[:200])
        creato = conn.execute("SELECT source FROM tasks WHERE title=?",
                              ("Comprare il toner",)).fetchone()
        prova("il task confermato porta la fonte jarvis", creato and creato[0] == "jarvis")
        c2 = jarvis.conferma(p1["id"], "it", conn=conn)
        prova("la seconda conferma della stessa scheda non fa niente",
              not c2.get("eseguita") and n_task() == prima + 1)

        # scheda scartata: progetto inesistente, azione sconosciuta, agente sconosciuto
        for nome, riga in [
            ("un progetto che non esiste",
             {"azione": "task_add", "titolo": "Fantasma", "progetto": "non-esiste"}),
            ("un'azione che non e' nell'elenco",
             {"azione": "esegui_comando", "cmd": "rm -rf /"}),
            ("un agente che non e' claude o codex",
             {"azione": "lancia", "titolo": "Fa qualcosa", "agente": "bash"}),
            ("un task che non esiste", {"azione": "task_done", "task_id": 987654}),
            ("uno stato di progetto non ammesso",
             {"azione": "progetto_stato", "progetto": "jv-sicuro", "stato": "cancellato"}),
        ]:
            _, es = proposta_da_modello(json.dumps(riga))
            prova("una proposta con %s si scarta senza scheda" % nome,
                  es is not None and "proposta" not in es and es.get("proposta_scartata"),
                  str(es)[:200])
        prova("...e non ha toccato niente", n_task() == prima + 1 and not lanci)

        # lanciare un agente: la scheda dice cosa, dove e in che modo; parte solo alla conferma
        _, es = proposta_da_modello(json.dumps(
            {"azione": "lancia", "titolo": "Rifare i test", "agente": "claude",
             "progetto": "jv-sicuro", "scrive": True, "task_id": t_aperto["id"]}))
        p = (es or {}).get("proposta") or {}
        chiavi = {r["k"] for r in p.get("righe", [])}
        prova("la scheda di un agente che scrive lo dice, con agente, modo, cartella e sessione",
              p.get("rischio") == "lancia_scrive" and {"Agente", "Modo", "Cartella", "Sessione"} <= chiavi
              and "modificare file" in " ".join(r["v"] for r in p["righe"]), str(p))
        prova("...e non parte niente prima del pulsante", not lanci)
        c = jarvis.conferma(p["id"], "it", conn=conn)
        prova("alla conferma parte un solo agente, in scrittura",
              len(lanci) == 1 and lanci[0][1].get("scrive") is True and c.get("eseguita"),
              str(lanci))
        lanci.clear()
        _, es_cwd = proposta_da_modello(json.dumps(
            {"azione": "lancia", "titolo": "Fa qualcosa", "agente": "claude", "cwd": "/etc/passwd-finto"}))
        p_cwd = (es_cwd or {}).get("proposta") or {}
        prova("la cartella non la sceglie il modello: un cwd nella riga @@PROPOSTA viene ignorato",
              "/etc/passwd-finto" not in json.dumps(p_cwd), str(p_cwd)[:200])
        jarvis.rifiuta(p_cwd.get("id", ""), "")

        # proseguire un task: riparte dalla sessione che lo ha salvato (la stessa, senza fork), non da una nuova
        from plancia import richiamo
        claude_vuota = tmp / "claude-config"
        (claude_vuota / "projects").mkdir(parents=True)
        agenti_vuoto = tmp / "agents-vuoto.json"
        agenti_vuoto.write_text("[]", "utf-8")
        vecchio_dir, vecchio_agenti = config.CLAUDE_DIR, os.environ.get("PLANCIA_AGENTS_JSON")
        config.CLAUDE_DIR = claude_vuota
        os.environ["PLANCIA_AGENTS_JSON"] = str(agenti_vuoto)
        try:
            # la cartella deve esistere: senza, riprendi.piano() riparte da una sessione nuova
            cwd_dir = tmp / "sessione-cwd"
            cwd_dir.mkdir(parents=True, exist_ok=True)
            cwd_c = str(cwd_dir)
            t_ses = actions.task_add(conn, "Task con sessione salvata", project="jv-sicuro",
                                     session_id="sid-jv-sicuro", cwd=cwd_c, agent="claude",
                                     host=socket.gethostname())
            conn.commit()
            cart = claude_vuota / "projects" / richiamo.cartella_sessione(cwd_c)
            cart.mkdir(parents=True)
            (cart / "sid-jv-sicuro.jsonl").write_text('{"type":"summary"}\n', "utf-8")
            _, es = proposta_da_modello(json.dumps(
                {"azione": "lancia", "titolo": "Prosegui il task", "agente": "claude",
                 "task_id": t_ses["id"]}))
            p_ses = (es or {}).get("proposta") or {}
            prova("proseguire un task: la scheda dice che riparte dalla sessione che lo ha salvato",
                  any("riparte dalla sessione" in r["v"] for r in p_ses.get("righe", [])), str(p_ses)[:200])
            prova("...e prima del pulsante non parte niente", not lanci)
            jarvis.conferma(p_ses["id"], "it", conn=conn)
            kw = lanci[-1][1] if lanci else {}
            prova("...e alla conferma l'agente riprende quella sessione, non ne apre una nuova",
                  kw.get("sessione") == "sid-jv-sicuro" and kw.get("task_id") == t_ses["id"], str(kw)[:200])

            # sessione APERTA: la scheda lo dice, e alla conferma non parte niente (un secondo
            # processo sullo stesso jsonl lo rovinerebbe); il messaggio va negli appunti
            lanci.clear()
            agenti_vivo = tmp / "agents-vivo.json"
            agenti_vivo.write_text(json.dumps([{"sessionId": "sid-jv-viva"}]), "utf-8")
            os.environ["PLANCIA_AGENTS_JSON"] = str(agenti_vivo)
            t_viva = actions.task_add(conn, "Task con sessione aperta", project="jv-sicuro",
                                      session_id="sid-jv-viva", cwd=cwd_c, agent="claude",
                                      host=socket.gethostname())
            conn.commit()
            _, es_v = proposta_da_modello(json.dumps(
                {"azione": "lancia", "titolo": "Prosegui il task aperto", "agente": "claude",
                 "task_id": t_viva["id"]}))
            p_viva = (es_v or {}).get("proposta") or {}
            prova("proseguire un task con la sessione aperta: la scheda dice che e' aperta",
                  any("aperta" in r["v"] for r in p_viva.get("righe", [])), str(p_viva)[:200])
            copiati = []
            vecchia_copia = jarvis._copia_appunti
            jarvis._copia_appunti = lambda t: copiati.append(t) or True
            try:
                jarvis.conferma(p_viva["id"], "it", conn=conn)
            finally:
                jarvis._copia_appunti = vecchia_copia
            prova("...e alla conferma non parte nessun agente, il messaggio va negli appunti",
                  not lanci and len(copiati) == 1, f"{lanci} {copiati}")
        finally:
            config.CLAUDE_DIR = vecchio_dir
            if vecchio_agenti is None:
                os.environ.pop("PLANCIA_AGENTS_JSON", None)
            else:
                os.environ["PLANCIA_AGENTS_JSON"] = vecchio_agenti
            lanci.clear()

        # scadenza, rifiuto, "si" a voce
        _, es = proposta_da_modello(json.dumps({"azione": "task_done", "task_id": t_aperto["id"]}))
        p = es["proposta"]
        ev_si = _eventi(jarvis.flusso("sì", "it", conn=conn))
        es_si = _finale(ev_si) or {}
        prova("dire si a voce con una scheda aperta non conferma: rimanda al pulsante",
              es_si.get("tipo") == "attende" and "pulsante" in es_si.get("risposta", "")
              and conn.execute("SELECT status FROM tasks WHERE id=?",
                               (t_aperto["id"],)).fetchone()[0] != "fatto")
        ev_fl = _eventi(jarvis.flusso("fallo", "it", conn=conn))
        prova("anche 'fallo' a voce rimanda al pulsante",
              (_finale(ev_fl) or {}).get("tipo") == "attende" and jarvis.proposta_viva(""))
        jarvis._PENDENTI[p["id"]]["scade"] = time.time() - 1
        c = jarvis.conferma(p["id"], "it", conn=conn)
        prova("una proposta scaduta non si esegue", not c.get("eseguita")
              and conn.execute("SELECT status FROM tasks WHERE id=?",
                               (t_aperto["id"],)).fetchone()[0] != "fatto", str(c))
        _, es = proposta_da_modello(json.dumps({"azione": "task_done", "task_id": t_aperto["id"]}))
        r = jarvis.rifiuta(es["proposta"]["id"], "")
        prova("rifiutare toglie la scheda", r.get("rifiutata")
              and not jarvis.conferma(es["proposta"]["id"], "it", conn=conn).get("eseguita"))

        # compartimento: la scheda vale solo dove e' nata
        _, es = proposta_da_modello(json.dumps({"azione": "task_done", "task_id": t_aperto["id"]}))
        altra_vista = SimpleNamespace(visore="altro", conn=conn, lettura=conn, tag="altro",
                                      oggetto=lambda *a, **k: None,
                                      progetto=lambda *a, **k: None)
        prova("la scheda di un compartimento non si conferma da un altro",
              not jarvis.conferma(es["proposta"]["id"], "it", vista=altra_vista).get("eseguita"))
        prova("...e resta valida dove e' nata",
              jarvis.conferma(es["proposta"]["id"], "it", conn=conn).get("eseguita"))

        # frasi riconosciute: mai un fatto, sempre una scheda
        antes = (n_task(), n_prog_att())
        e = _finale(_eventi(jarvis.flusso("ricordami di chiamare Mario", "it", conn=conn))) or {}
        prova("'ricordami di...' prepara la scheda e non scrive",
              e.get("tipo") == "proposta" and e["proposta"]["azione"] == "task_add"
              and n_task() == antes[0], str(e)[:160])
        prova("...e il titolo resta com'e' stato detto (maiuscole comprese)",
              any(r["v"] == "chiamare Mario" for r in e["proposta"]["righe"]), str(e["proposta"]["righe"]))
        t2 = actions.task_add(conn, "Sistemare la lavagna del progetto", project="jv-sicuro")
        conn.commit()
        antes = (n_task(), n_prog_att())
        e = _finale(_eventi(jarvis.flusso("ho fatto sistemare la lavagna", "it", conn=conn))) or {}
        prova("'ho fatto...' prepara la scheda e non chiude il task",
              e.get("tipo") == "proposta" and e["proposta"]["azione"] == "task_done"
              and conn.execute("SELECT status FROM tasks WHERE id=?",
                               (t2["id"],)).fetchone()[0] == "aperto", str(e)[:160])
        e = _finale(_eventi(jarvis.flusso("archivia jv-sicuro", "it", conn=conn))) or {}
        prova("'archivia...' prepara la scheda e non archivia",
              e.get("tipo") == "proposta" and e["proposta"]["azione"] == "progetto_stato"
              and n_prog_att() == antes[1], str(e)[:160])
        jarvis.rifiuta(e["proposta"]["id"], "")
        e = _finale(_eventi(jarvis.flusso("annulla", "it", conn=conn))) or {}
        prova("'annulla' senza lavori in corso lo dice, senza scheda", "proposta" not in e, str(e)[:120])
        e = _finale(_eventi(jarvis.flusso("eseguilo", "it", conn=conn))) or {}
        prova("'eseguilo' non avvia niente da solo", not lanci, str(lanci))
        e = _finale(_eventi(jarvis.flusso("apri task", "it", conn=conn))) or {}
        prova("aprire una vista e' immediato e non chiede conferma",
              e.get("tipo") == "vai" and e.get("azione", {}).get("vista") == "task" and "proposta" not in e)
        e = _finale(_eventi(jarvis.flusso("basta", "it", conn=conn))) or {}
        prova("'basta' ferma e tace", e.get("tipo") == "ferma" and e.get("muto"))
        e = _finale(_eventi(jarvis.flusso("più piano", "it", conn=conn))) or {}
        prova("'piu piano' cambia solo la velocita", e.get("azione", {}).get("tipo") == "velocita")

        # ---------------------------------------------------------------- 4. si ferma
        def in_altro_thread():
            raccolti.extend(jarvis.flusso("una cosa lento lento", "it", conn=store.connect()))

        raccolti = []
        t = threading.Thread(target=in_altro_thread, daemon=True)
        t.start()
        for _ in range(60):
            if any(x for x in log.read_text("utf-8").splitlines() if x.startswith("TURNO una cosa lento")):
                break
            time.sleep(0.1)
        time.sleep(0.8)
        t0 = time.time()
        jarvis.ferma_tutto()
        t.join(6)
        prova("Esc ferma la risposta in corso, e in fretta",
              not t.is_alive() and time.time() - t0 < 3, "%.1fs" % (time.time() - t0))
        prova("...e il flusso lo dice", raccolti and raccolti[-1].get("esito", {}).get("tipo") == "interrotto",
              str(raccolti[-1:] if raccolti else raccolti))
        pid = int([r for r in log.read_text("utf-8").splitlines() if r.startswith("PID ")][-1][4:])
        for _ in range(30):
            try:
                os.kill(pid, 0)
            except OSError:
                pid = None
                break
            time.sleep(0.1)
        prova("...e il processo del modello e' chiuso", pid is None)
        # un turno dopo un'interruzione riparte pulito
        ev = _eventi(jarvis.flusso("raccontami una storia sul mare", "it", conn=conn))
        prova("dopo un'interruzione la domanda successiva funziona",
              (_finale(ev) or {}).get("tipo") == "claude" and "tre task" in (_finale(ev) or {}).get("risposta", ""))

        # ---------------------------------------------------------------- 6. la voce
        f = voice.Frasi()
        uscite = []
        for ch in "Ok. Fatto! Il valore e' 3.5 e vedi github.com/x. Poi finisce senza punto":
            uscite += f.nutri(ch)
        uscite += f.chiudi()
        prova("le frasi non si spezzano su 3.5 ne' su github.com, e le brevi si uniscono",
              uscite == ["Ok. Fatto!", "Il valore e' 3.5 e vedi github.com/x.",
                         "Poi finisce senza punto"], str(uscite))
        f = voice.Frasi()
        lunga = f.nutri("parola " * 60)
        prova("una frase che non finisce mai si taglia comunque, senza spezzare parole",
              lunga and all(len(x) <= 205 and not x.endswith("paro") for x in lunga), str(lunga)[:120])
        f = voice.Frasi()
        prova("la prima frase esce appena c'e', anche corta", f.nutri("Va bene. Poi ") == ["Va bene."])
        prova("una riga vuota di solo percorso non produce una frase da dire",
              voice.frasi_da_dire("~/.plancia/eventi.jsonl", "it") in ([], ["eventi.jsonl"]))

        def say_vietato(*a, **k):
            raise AssertionError("la voce neurale non deve mai ripiegare su say")

        voice.sintesi_say = say_vietato
        try:
            voice.sintesi("Ciao, sono Jarvis.", "it", "neurale", cache=False)
            errore = None
        except voice.NessunaVoceNeurale as exc:
            errore = exc
        except Exception as exc:  # noqa: BLE001
            errore = AssertionError("eccezione sbagliata: %r" % (exc,))
        prova("senza Pocket ne' Voicebox la voce neurale solleva NessunaVoceNeurale e non usa say",
              isinstance(errore, voice.NessunaVoceNeurale), repr(errore))
        prova("NessunaVoceNeurale e' un NessunMotoreVoce (il server la riporta senza errore 500)",
              issubclass(voice.NessunaVoceNeurale, voice.NessunMotoreVoce))
        # con un Pocket finto vero (un processo che parla HTTP), non solo sostituito a mano
        porta_pocket = _porta_libera()
        registro_pocket = tmp / "pocket.log"
        pocket = subprocess.Popen(
            [sys.executable, str(RADICE / "tools" / "prove" / "_pocket_finto.py"),
             str(porta_pocket), str(registro_pocket)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        vere_url = (voice._url_pocket, voice._url_voicebox)
        voice._url_pocket = lambda: "http://127.0.0.1:%d" % porta_pocket
        voice._url_voicebox = lambda: "http://127.0.0.1:9"
        voice.pocket_vivo, voice.voicebox_vivo = vero_pocket, vero_vb
        try:
            for _ in range(40):
                voice._pocket_no = 0.0
                if voice.pocket_vivo():
                    break
                time.sleep(0.15)
            info = voice.sintesi("Prima frase di prova.", "it", "neurale", cache=False)
            prova("col Pocket finto (HTTP vero) la voce neurale produce un WAV",
                  info.get("motore") == "pocket" and Path(info["file"]).stat().st_size > 2048, str(info))
            prova("...e voce_neurale() dice pocket", voice.voce_neurale() == "pocket")
            try:
                voice.sintesi("Questa e' guasto.", "it", "neurale", cache=False)
                errore = None
            except voice.NessunaVoceNeurale as exc:
                errore = exc
            prova("se Pocket rifiuta la frase la voce neurale non ripiega su say",
                  isinstance(errore, voice.NessunaVoceNeurale), repr(errore))
        finally:
            pocket.terminate()
            voice._url_pocket, voice._url_voicebox = vere_url
            voice.pocket_vivo = lambda timeout=1.0: False
            voice.voicebox_vivo = lambda timeout=1.5: False
        voice.pocket_vivo = lambda timeout=1.0: True
        vero_pocket_sint = voice.sintesi_pocket
        voice.sintesi_pocket = lambda testo, out, voce_wav=None, timeout=60: (
            out.write_bytes(b"RIFF" + b"\0" * 4096) or out)
        try:
            info = voice.sintesi("Ciao, sono Jarvis.", "it", "neurale", cache=False)
            prova("con Pocket acceso la voce neurale lo usa", info.get("motore") == "pocket", str(info))
        finally:
            voice.sintesi_pocket = vero_pocket_sint
            voice.pocket_vivo = lambda timeout=1.0: False

        # ---------------------------------------------------------------- 5. HTTP
        _prova_http(prova, tmp, finto)
    finally:
        try:
            jarvis.spegni()
        except Exception:
            pass
        recap.claude_bin = vero_bin
        cantiere.avvia = vero_avvia
        voice.pocket_vivo, voice.voicebox_vivo, voice.sintesi_say = vero_pocket, vero_vb, vero_say
        voice._pocket_no, voice._ultimo_no = vero_pocket_no, vero_vb_no
        os.environ.pop("FINTO_LOG", None)


def _prova_http(prova, tmp, finto) -> None:
    casa = tmp / "casa-http"
    casa.mkdir()
    (casa / "claude-vuota").mkdir()
    (casa / "codex-vuota").mkdir()
    porta = _porta_libera()
    env = dict(os.environ)
    env["PLANCIA_HOME"] = str(casa)
    _finti.casa_finta(env, casa)
    env["CLAUDE_CONFIG_DIR"] = str(casa / "claude-vuota")
    env["CODEX_HOME"] = str(casa / "codex-vuota")
    env["FINTO_LOG"] = str(tmp / "claude-http.log")
    env["PATH"] = _finti.path_con(tmp / "bin")
    server = None
    try:
        dati = subprocess.run([sys.executable, str(RADICE / "tools" / "demo-data.py")],
                              env=env, capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL)
        if dati.returncode != 0:
            prova("l'archivio dimostrativo per la prova HTTP si crea", False, dati.stderr[-300:])
            return
        # dopo i dati dimostrativi, che riscrivono la configurazione
        conf = json.loads((casa / "config.json").read_text("utf-8")) \
            if (casa / "config.json").exists() else {}
        conf["claude_bin"] = finto
        # nemmeno una sonda verso le porte vere di Pocket e Voicebox: due porte chiuse
        conf["pocket_url"] = "http://127.0.0.1:9"
        conf["voicebox_url"] = "http://127.0.0.1:9"
        (casa / "config.json").write_text(json.dumps(conf), "utf-8")
        server = subprocess.Popen(
            [sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta), "--no-sync"],
            cwd=str(RADICE), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        base = "http://127.0.0.1:%d" % porta
        vivo = False
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/", timeout=0.5)
                vivo = True
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if server.poll() is not None:
                    break
                time.sleep(0.25)
        if not vivo:
            prova("il server di prova (HTTP) e' partito", False,
                  (server.stdout.read() if server.stdout else "")[:600])
            return
        token = (casa / "token").read_text("utf-8").strip()

        def chiama(percorso, corpo, con_token=True):
            richiesta = urllib.request.Request(
                base + percorso, data=json.dumps(corpo).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json",
                         **({"X-Plancia-Token": token} if con_token else {})})
            return urllib.request.urlopen(richiesta, timeout=60)

        try:
            chiama("/api/jarvis/conferma", {"id": "x"}, con_token=False)
            codice = 200
        except urllib.error.HTTPError as exc:
            codice = exc.code
        prova("la conferma senza token e' rifiutata", codice == 403, str(codice))
        try:
            chiama("/api/jarvis/capisci", {"testo": "spiegami cosa bolle in pentola"}, con_token=False)
            codice = 200
        except urllib.error.HTTPError as exc:
            codice = exc.code
        prova("nemmeno il flusso si apre senza token", codice == 403, str(codice))

        r = chiama("/api/jarvis/capisci", {"testo": "spiegami cosa bolle in pentola", "lang": "it"})
        tipo = r.headers.get("Content-Type", "")
        righe = [json.loads(x) for x in r.read().decode("utf-8").splitlines() if x.strip()]
        prova("...con la risposta del modello finto (non il ripiego)",
              "Hai tre task" in righe[-1].get("esito", {}).get("risposta", ""),
              str(righe[-1])[:200])
        prova("/api/jarvis/capisci risponde a righe NDJSON, testo poi fine",
              "ndjson" in tipo and righe and righe[0]["t"] == "stato" and righe[-1]["t"] == "fine"
              and any(x["t"] == "testo" for x in righe) and any(x["t"] == "frase" for x in righe),
              tipo + " " + str([x["t"] for x in righe][:6]))

        r = chiama("/api/jarvis/capisci", {"testo": "proponi: " + json.dumps(
            {"azione": "task_add", "titolo": "Task da HTTP"}), "lang": "it"})
        righe = [json.loads(x) for x in r.read().decode("utf-8").splitlines() if x.strip()]
        es = righe[-1].get("esito", {})
        pid = (es.get("proposta") or {}).get("id")
        prova("via HTTP una proposta del modello arriva come scheda", bool(pid), str(es)[:200])
        d = json.loads(chiama("/api/jarvis/conferma", {"id": pid, "lang": "it"}).read())
        prova("via HTTP la conferma con token esegue", d.get("eseguita") is True, str(d)[:200])
        d2 = json.loads(chiama("/api/jarvis/conferma", {"id": pid, "lang": "it"}).read())
        prova("via HTTP la seconda conferma non esegue", d2.get("eseguita") is False, str(d2)[:200])
        d = json.loads(chiama("/api/jarvis/voce", {}).read())
        prova("/api/jarvis/voce dice se c'e' una voce neurale, senza lanciare niente",
              "neurale" in d, str(d))
        d = json.loads(chiama("/api/jarvis/ferma", {}).read())
        prova("/api/jarvis/ferma risponde", d.get("fermato") is True)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    # a mano: una casa di prova SUA, prima di importare plancia
    _casa = tempfile.mkdtemp(prefix="plancia-prova-jarvis-sicuro-casa-")
    os.environ["PLANCIA_HOME"] = _casa
    sys.path.insert(0, str(RADICE))
    _falliti = []

    def _prova(nome, cond, dettaglio=""):
        print(("  ok   " if cond else "  NO   ") + nome + ("" if cond else "  " + str(dettaglio)))
        if not cond:
            _falliti.append(nome)

    esegui(_prova)
    print("\n%s" % ("FALLITE: %d" % len(_falliti) if _falliti else "tutte verdi"))
    sys.exit(1 if _falliti else 0)
