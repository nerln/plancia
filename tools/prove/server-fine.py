"""Prove del giro finale del server (22-SERVER): la mappa che regge 1200 nodi, un
solo Jarvis in sola lettura, Riprendi che non cambia modello, il 403 che legge il corpo.

Cosa si dimostra, in ordine:

1. MAPPA. La disposizione della mappa della memoria non cresce piu' col quadrato dei
   nodi (griglia invece di tutte le coppie), e si calcola UNA volta per impronta
   della memoria (nomi e legami, non le descrizioni), fuori dal processo del server
   (un figlio a priorita' bassa), partendo dalle posizioni precedenti. Le prove sono
   sul comportamento e non sul cronometro, che sotto carico mente: quante volte si
   calcola davvero, dove, quanto si sposta chi c'era, quanta CPU paga il processo
   che risponde. I tempi veri stanno nel rapporto del lotto.
2. JARVIS. `jarvis.esegui` (la dashboard web, `plancia jarvis` da terminale) e il
   processo caldo (`agente`) sono lo stesso percorso sicuro del pannello Mac: sola
   lettura, e niente che scriva parte da una frase. Diventa una scheda, e parte con
   `conferma`, da un pulsante o da una risposta scritta a mano davanti a un terminale.
   Il web mostra la scheda con Conferma e Annulla.
3. RIPRENDI. Una sessione dell'utente si riprende col SUO modello: niente `--model`
   in `claude -p --resume` ne' in `codex exec resume`. Il modello del cantiere serve
   solo alle sessioni nuove. Si guardano gli argomenti veri con cui i finti vengono
   lanciati.
4. 403. Un rifiuto per il token legge il corpo della richiesta: la richiesta dopo,
   sulla stessa connessione, non esce sporca (501).

Isolamento: mai un `claude`/`codex` vero (finti che registrano argv), casa propria per
i sottoprocessi, un server su una porta libera, chiuso a fine prova.
"""

import http.client
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

RADICE = Path(__file__).resolve().parent.parent.parent


def _carica_modulo(nome):
    if nome not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parent / (nome + ".py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[nome] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules[nome]


_finti = _carica_modulo("_finti")
_saltati = _carica_modulo("_saltati")
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

CLAUDE_FINTO_JARVIS = (Path(__file__).resolve().parent / "_claude_finto_jarvis.py").read_text("utf-8")

# Un `claude` finto per Riprendi: registra gli argomenti veri e risponde come lo stream vero.
CLAUDE_FINTO_ARGV = r'''
import json, os, sys
registro = os.environ["FINTO_ARGV"]
argv = sys.argv[1:]
stdin = sys.stdin.read() if "-p" in argv else ""
sid = argv[argv.index("--resume") + 1] if "--resume" in argv else "nuova-%d" % os.getpid()
with open(registro, "a") as f:
    f.write(json.dumps({"bin": "claude", "argv": argv}) + "\n")
print(json.dumps({"type": "system", "session_id": sid}))
print(json.dumps({"type": "result", "result": "fatto", "session_id": sid,
                  "usage": {"output_tokens": 1}, "total_cost_usd": 0, "is_error": False}))
'''

CODEX_FINTO_ARGV = r'''
import json, os, sys
registro = os.environ["FINTO_ARGV"]
argv = sys.argv[1:]
if argv and argv[-1] == "-":
    sys.stdin.read()
with open(registro, "a") as f:
    f.write(json.dumps({"bin": "codex", "argv": argv}) + "\n")
print("session id: 0199aaaa-0000-0000-0000-0000000000ff")
print("fatto")
'''


def _porta_libera():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def _registro(percorso):
    try:
        return [json.loads(r) for r in Path(percorso).read_text("utf-8").splitlines() if r.strip()]
    except OSError:
        return []


def _archivio(n, legami_per_nodo=3, prefisso="nodo"):
    """n nomi e degli archi ripetibili (senza caso): ogni nodo lega ai suoi vicini d'indice."""
    nomi = ["%s-%04d" % (prefisso, i) for i in range(n)]
    archi = []
    for i in range(n):
        for k in range(1, legami_per_nodo + 1):
            j = (i * (k + 2) + 7 * k) % n
            if j != i:
                archi.append((nomi[i], nomi[j]))
    return nomi, archi


def esegui(reale) -> None:
    """Su Windows il modulo non si fa (finti in shell, `nice`): i controlli si segnano
    saltati uno per uno, cosi' il conteggio e' lo stesso ovunque."""
    prova = _saltati.Contatore(reale)
    if _saltati.WIN:
        _saltati.salta_il_resto("server-fine", prova)
    else:
        _esegui(prova)
    _saltati.chiudi("server-fine", prova, reale)


def _esegui(prova) -> None:
    from plancia import actions, cantiere, config, disposizione, jarvis, mappa, mcp, recap, store
    from plancia import agente

    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-server-fine-"))
    _mappa(prova, tmp, config, disposizione, mappa, store)
    _jarvis(prova, tmp, actions, agente, config, jarvis, mcp, recap, store)
    _riprendi(prova, tmp, cantiere, config, recap, store)
    _http(prova, tmp)


# ------------------------------------------------------------------------ 1. mappa

def _mappa(prova, tmp, config, disposizione, mappa, store) -> None:
    # --- la disposizione pura
    nomi, archi = _archivio(300)
    a = disposizione.calcola(nomi, archi)
    b = disposizione.calcola(nomi, archi)
    prova("mappa: la disposizione e' la stessa a parita' di dati", a == b)
    fuori = [n for n, (x, y) in a.items() if not (0.03 <= x <= 0.97 and 0.03 <= y <= 0.97)]
    prova("mappa: ogni nodo sta nel riquadro da 0.03 a 0.97", not fuori and set(a) == set(nomi), str(fuori[:3]))
    sovrapposti = len({(round(x, 3), round(y, 3)) for x, y in a.values()})
    prova("mappa: i nodi non si sovrappongono (quasi tutte le posizioni sono distinte)",
          sovrapposti >= 0.97 * len(nomi), "%d posizioni per %d nodi" % (sovrapposti, len(nomi)))
    prova("mappa: nessun nodo, uno solo, due nodi senza legami",
          disposizione.calcola([], []) == {} and disposizione.calcola(["a"], []) == {"a": [0.5, 0.5]}
          and len(disposizione.calcola(["a", "b"], [])) == 2)
    prova("mappa: un legame verso un nome che non c'e' non rompe niente",
          set(disposizione.calcola(["a", "b", "c"], [("a", "b"), ("a", "zzz"), ("c", "c")])) == {"a", "b", "c"})

    # 1200 nodi: il lavoro che la versione a tutte le coppie faceva in 73 s di CPU (misurato)
    # deve stare in una frazione, e lo si misura in CPU, che non dipende dal carico
    n1200, a1200 = _archivio(1200)
    cpu = time.process_time()
    grandi = disposizione.calcola(n1200, a1200)
    cpu = time.process_time() - cpu
    prova("mappa: 1200 nodi e 3500 legami: meno di 20 secondi di CPU (prima 73)",
          len(grandi) == 1200 and cpu < 20.0, "%.1f s" % cpu)
    prova("mappa: le iterazioni calano col numero dei nodi, con un minimo",
          disposizione.giri_per(100, False) >= disposizione.giri_per(1200, False) >= disposizione.GIRI_MIN
          and disposizione.giri_per(50, True) == disposizione.GIRI_CALDI)

    # --- la partenza dalle posizioni di prima: chi c'era resta dov'era
    nuovi = nomi + ["nodo-nuovo"]
    caldo = disposizione.calcola(nuovi, archi + [("nodo-nuovo", nomi[5]), ("nodo-nuovo", nomi[9])], partenza=a)
    import math
    spostamento = sorted(math.dist(a[n], caldo[n]) for n in nomi)
    mediano = spostamento[len(spostamento) // 2]
    freddo = disposizione.calcola(nuovi, archi + [("nodo-nuovo", nomi[5]), ("nodo-nuovo", nomi[9])])
    spostamento_freddo = sorted(math.dist(a[n], freddo[n]) for n in nomi)
    prova("mappa: con la partenza precedente le schede che c'erano si spostano poco",
          mediano < 0.06 and mediano < spostamento_freddo[len(spostamento_freddo) // 2],
          "mediana calda %.3f, fredda %.3f" % (mediano, spostamento_freddo[len(spostamento_freddo) // 2]))
    vicino = math.dist(caldo["nodo-nuovo"], caldo[nomi[5]]) < 0.25
    prova("mappa: la scheda nuova nasce accanto ai suoi vicini", vicino)

    # --- la cache: una volta per impronta
    mappa._MEMORIA.clear()
    cache = mappa._file_cache()
    if cache.exists():
        cache.unlink()
    mappa.STATISTICHE.update({"calcoli": 0, "figli": 0, "sul_posto": 0, "partenze_calde": 0})
    nomi2, archi2 = _archivio(120, prefisso="cache")
    p1 = mappa.posizioni(nomi2, archi2)
    p2 = mappa.posizioni(list(reversed(nomi2)), list(reversed(archi2)))
    prova("mappa: la stessa memoria, nell'ordine che si vuole, si calcola una volta sola",
          mappa.STATISTICHE["calcoli"] == 1 and p1 == p2, str(mappa.STATISTICHE))
    prova("mappa: il calcolo e' andato al processo figlio, non al server",
          mappa.STATISTICHE["figli"] == 1 and mappa.STATISTICHE["sul_posto"] == 0, str(mappa.STATISTICHE))
    prova("mappa: la cache e' anche su disco (un riavvio non ricalcola)",
          cache.exists() and json.loads(cache.read_text("utf-8"))["impronta"] == mappa.impronta(nomi2, archi2))
    mappa._MEMORIA.clear()
    p3 = mappa.posizioni(nomi2, archi2)
    prova("mappa: dopo un riavvio (memoria vuota) si legge dal disco senza calcolare",
          mappa.STATISTICHE["calcoli"] == 1 and p3 == p1, str(mappa.STATISTICHE))
    prova("mappa: l'impronta non cambia con l'ordine e cambia con un legame",
          mappa.impronta(nomi2, archi2) == mappa.impronta(list(reversed(nomi2)), archi2)
          and mappa.impronta(nomi2, archi2) != mappa.impronta(nomi2, archi2 + [(nomi2[0], nomi2[1])]))
    p4 = mappa.posizioni(nomi2 + ["cache-nuova"], archi2 + [("cache-nuova", nomi2[3])])
    prova("mappa: una scheda nuova ricalcola, ma partendo dalle posizioni di prima",
          mappa.STATISTICHE["calcoli"] == 2 and mappa.STATISTICHE["partenze_calde"] >= 1
          and "cache-nuova" in p4, str(mappa.STATISTICHE))

    # dieci richieste insieme: un calcolo solo
    mappa._MEMORIA.clear()
    if cache.exists():
        cache.unlink()
    n5, a5 = _archivio(200, prefisso="insieme")
    prima = mappa.STATISTICHE["calcoli"]
    ris = []
    fili = [threading.Thread(target=lambda: ris.append(mappa.posizioni(n5, a5))) for _ in range(8)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(120)
    prova("mappa: otto richieste insieme, un calcolo solo e la stessa risposta a tutte",
          mappa.STATISTICHE["calcoli"] == prima + 1 and len(ris) == 8 and all(r == ris[0] for r in ris),
          "%d calcoli, %d risposte" % (mappa.STATISTICHE["calcoli"] - prima, len(ris)))

    # il figlio che non finisce in tempo (macchina sotto un carico enorme): il server NON
    # ripiega sul calcolo intero (sarebbe peggio), da' la partenza senza rifinirla, e non
    # la scrive come definitiva
    mappa._MEMORIA.clear()
    mappa._PROVVISORIE.clear()
    if cache.exists():
        cache.unlink()
    n7, a7 = _archivio(150, prefisso="scaduto")
    vero_tempo, scaduti, calcoli = mappa._TEMPO_MAX, mappa.STATISTICHE["scaduti"], mappa.STATISTICHE["calcoli"]
    mappa._TEMPO_MAX = 0.001
    try:
        p7 = mappa.posizioni(n7, a7)
        p8 = mappa.posizioni(n7, a7)
    finally:
        mappa._TEMPO_MAX = vero_tempo
    prova("mappa: se il figlio non finisce in tempo si danno lo stesso le posizioni di tutti",
          set(p7) == set(n7) and mappa.STATISTICHE["scaduti"] == scaduti + 1
          and mappa.STATISTICHE["sul_posto"] == 0, str(mappa.STATISTICHE))
    prova("mappa: ...ma non come definitive (ne' su disco ne' nella memoria), e per un minuto non si riprova",
          not cache.exists() and mappa.impronta(n7, a7) not in mappa._MEMORIA
          and p8 == p7 and mappa.STATISTICHE["calcoli"] == calcoli + 1, str(mappa.STATISTICHE))
    mappa._PROVVISORIE.clear()

    # il processo che risponde non paga il calcolo: la CPU sua e' una frazione del tempo
    mappa._MEMORIA.clear()
    if cache.exists():
        cache.unlink()
    n6, a6 = _archivio(600, prefisso="fuori")
    cpu, parete = time.process_time(), time.time()
    mappa.posizioni(n6, a6)
    cpu, parete = time.process_time() - cpu, time.time() - parete
    prova("mappa: durante il calcolo la CPU del server e' una frazione del tempo (lo fa il figlio)",
          cpu < 0.35 * parete + 0.2, "cpu %.2f s su %.2f s" % (cpu, parete))

    # --- dalla scheda alla mappa vera: il formato non cambia e la descrizione non ricalcola
    conn = store.connect()
    store.init_db(conn)
    for i in range(14):
        nome = "prova-server-%02d" % i
        vicini = ["prova-server-%02d" % ((i * 3 + 1) % 14), "prova-server-%02d" % ((i + 5) % 14)]
        conn.execute(
            "INSERT OR REPLACE INTO knowledge(name, path, scope, description, type, body, links, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (nome, "/prova/%s.md" % nome, "prova-server", "scheda %d" % i, ("user", "feedback", "project", "reference")[i % 4],
             "corpo " * 60, json.dumps([v for v in vicini if v != nome]), "2026-09-01T00:00:00Z"))
    conn.commit()
    prima = mappa.STATISTICHE["calcoli"]
    m1 = mappa.mappa(conn)
    gia = mappa.STATISTICHE["calcoli"]
    conn.execute("UPDATE knowledge SET description='riscritta', body='altro corpo ' WHERE scope='prova-server'")
    conn.commit()
    m2 = mappa.mappa(conn)
    prova("mappa: la risposta ha lo stesso formato di sempre (nodi con x e y, archi, diagnosi)",
          set(m1) == {"nodi", "archi", "diagnosi", "gruppi"}
          and all(0 <= n["x"] <= 1 and 0 <= n["y"] <= 1 for n in m1["nodi"])
          and {"nome", "tipo", "grado"} <= set(m1["nodi"][0]) and {"da", "a"} == set(m1["archi"][0]))
    prova("mappa: riscrivere le descrizioni non ricalcola la disposizione",
          mappa.STATISTICHE["calcoli"] == gia and gia >= prima
          and {n["nome"]: (n["x"], n["y"]) for n in m1["nodi"]} == {n["nome"]: (n["x"], n["y"]) for n in m2["nodi"]})
    conn.execute("DELETE FROM knowledge WHERE scope='prova-server'")
    conn.commit()
    conn.close()


# ------------------------------------------------------------------------ 2. jarvis

def _jarvis(prova, tmp, actions, agente, config, jarvis, mcp, recap, store) -> None:
    from plancia import voice
    log = tmp / "claude-jarvis.log"
    finto = _finti.crea_finto(tmp / "bin-jarvis", "claude-finto-server", CLAUDE_FINTO_JARVIS)
    os.environ["FINTO_LOG"] = str(log)
    vero_bin = recap.claude_bin
    recap.claude_bin = lambda: finto
    from plancia import cantiere
    vero_avvia = cantiere.avvia
    lanci = []
    cantiere.avvia = lambda conn, titolo, *a, **kw: (lanci.append(titolo) or {"run": 4243})
    vero_pocket, vero_vb = voice.pocket_vivo, voice.voicebox_vivo
    voice.pocket_vivo = lambda timeout=1.0: False
    voice.voicebox_vivo = lambda timeout=1.5: False
    try:
        conn = store.connect()
        store.init_db(conn)
        n_task = lambda: conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]  # noqa: E731
        scritture = {"mcp__plancia__" + n for n in mcp._SCRITTURE}

        prova("jarvis: il processo caldo dell'agente e' quello in sola lettura di Jarvis",
              agente.Agente is jarvis.SessioneLettura and agente.TOOL is jarvis.TOOL_LETTURA)
        prova("jarvis: nessun tool di scrittura fra quelli del processo caldo",
              not (set(agente.TOOL) & scritture), str(set(agente.TOOL) & scritture))
        sorgente = (RADICE / "plancia" / "agente.py").read_text("utf-8") + (RADICE / "plancia" / "jarvis.py").read_text("utf-8")
        prova("jarvis: nel codice non c'e' piu' il permesso di scrivere senza chiedere",
              "non serve chiedere il permesso" not in sorgente and "plancia_task_add\",\n" not in
              (RADICE / "plancia" / "agente.py").read_text("utf-8"))
        prova("jarvis: non esistono piu' due percorsi (niente `_esegui_proposta`, niente TOOL_CONSENTITI)",
              not hasattr(jarvis, "_esegui_proposta") and not hasattr(jarvis, "TOOL_CONSENTITI"))

        # --- esegui: la frase riconosciuta e' una scheda, non un fatto
        prima = n_task()
        e = jarvis.esegui("ricordami di comprare il toner", "it", conn=conn)
        prova("jarvis.esegui: 'ricordami di...' torna una scheda e non scrive",
              e.get("tipo") == "proposta" and e.get("proposta", {}).get("azione") == "task_add"
              and n_task() == prima, str(e)[:200])
        prova("jarvis.esegui: la scheda ha il titolo, le righe e l'avviso",
              bool(e["proposta"].get("titolo")) and e["proposta"].get("righe") and "id" in e["proposta"], str(e["proposta"])[:200])
        c = jarvis.conferma(e["proposta"]["id"], "it", conn=conn)
        prova("jarvis.conferma: solo adesso il task c'e'", c.get("eseguita") is True and n_task() == prima + 1, str(c)[:200])
        prova("jarvis.conferma: una seconda volta non scrive di nuovo",
              not jarvis.conferma(e["proposta"]["id"], "it", conn=conn).get("eseguita") and n_task() == prima + 1)

        t = actions.task_add(conn, "Sistemare la lavagna di prova", source="prova")
        conn.commit()
        e = jarvis.esegui("ho fatto sistemare la lavagna", "it", conn=conn)
        stato = conn.execute("SELECT status FROM tasks WHERE id=?", (t["id"],)).fetchone()[0]
        prova("jarvis.esegui: 'ho fatto...' non chiude il task da solo",
              e.get("tipo") == "proposta" and stato == "aperto", str(e)[:160] + " " + stato)
        r = jarvis.rifiuta(e["proposta"]["id"], "")
        prova("jarvis.rifiuta: la scheda buttata non si conferma piu'",
              not jarvis.conferma(e["proposta"]["id"], "it", conn=conn).get("eseguita")
              and conn.execute("SELECT status FROM tasks WHERE id=?", (t["id"],)).fetchone()[0] == "aperto", str(r)[:120])

        e = jarvis.esegui("apri task", "it", conn=conn)
        prova("jarvis.esegui: aprire una vista e' immediato e senza scheda",
              e.get("tipo") == "vai" and "proposta" not in e)

        # una frase per il modello: lo scrive il finto, con la riga @@PROPOSTA
        prima = n_task()
        e = jarvis.esegui("proponi: " + json.dumps({"azione": "task_add", "titolo": "Task dal modello"}), "it", conn=conn)
        prova("jarvis.esegui: una proposta del modello e' una scheda e basta",
              bool((e.get("proposta") or {}).get("id")) and n_task() == prima and "@@PROPOSTA" not in e.get("risposta", ""), str(e)[:200])
        jarvis.rifiuta(e["proposta"]["id"], "")
        e = jarvis.esegui("una cosa qualunque da spiegare", "it", conn=conn)
        prova("jarvis.esegui: una domanda torna la risposta del modello, senza scheda",
              "Hai tre task" in e.get("risposta", "") and "proposta" not in e, str(e)[:160])
        prova("jarvis.esegui: 'eseguilo' e 'fallo' non avviano agenti", not lanci, str(lanci))

        # --- agente.chiedi (il processo caldo di prima): in sola lettura, la proposta tolta
        risposta = agente.chiedi("proponi: " + json.dumps({"azione": "task_add", "titolo": "X"}), "it")
        prova("agente.chiedi: la riga della proposta non arriva a chi legge", "@@PROPOSTA" not in risposta, risposta)
        prova("agente.chiedi: una domanda ha la sua risposta e non scrive",
              "Hai tre task" in agente.chiedi("che cosa ho da fare", "it") and n_task() == prima)
        righe = log.read_text("utf-8").splitlines()
        argvs = [json.loads(r[5:]) for r in righe if r.startswith("ARGV ")]
        buoni = [a for a in argvs if "--disallowedTools" in a]
        prova("agente.chiedi: ogni processo lanciato ha i tool di scrittura negati per nome",
              bool(argvs) and len(buoni) == len(argvs) and all(
                  scritture <= set(a[a.index("--disallowedTools") + 1:]) - {"--allowedTools"} or
                  scritture <= set(a[a.index("--disallowedTools") + 1:a.index("--allowedTools")])
                  for a in buoni), str(argvs)[:200])
        s = agente.stato()
        prova("agente.stato: dice quanti processi caldi ci sono, per lingua", "it" in s and s["it"]["vivo"], str(s))
        agente.spegni()
        prova("agente.spegni: chiude il processo caldo", not agente.stato().get("it", {"vivo": False})["vivo"])

        # --- il terminale: `plancia jarvis` senza un terminale vero non conferma mai
        casa = tmp / "casa-cli"
        casa.mkdir()
        env = dict(os.environ)
        env["PLANCIA_HOME"] = str(casa)
        _finti.casa_finta(env, casa)
        env["CLAUDE_CONFIG_DIR"] = str(casa / "claude")
        env["CODEX_HOME"] = str(casa / "codex")
        env["PATH"] = _finti.path_con(tmp / "bin-jarvis")
        env["FINTO_LOG"] = str(tmp / "claude-cli.log")
        (casa / "config.json").write_text(json.dumps({"claude_bin": finto}), "utf-8")

        def cli(*args, ingresso=None):
            return subprocess.run([sys.executable, str(RADICE / "bin" / "plancia"), *args],
                                  env=env, cwd=str(RADICE), input=ingresso, capture_output=True, text=True,
                                  timeout=120)

        def n_task_cli():
            db = casa / "plancia.db"
            if not db.exists():
                return 0
            import sqlite3
            c2 = sqlite3.connect(str(db))
            try:
                return c2.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            except sqlite3.Error:
                return 0
            finally:
                c2.close()

        cli("jarvis", "apri", "task")            # crea l'archivio
        prima = n_task_cli()
        r = cli("jarvis", "ricordami", "di", "spegnere", "il", "forno", ingresso="s\n")
        prova("terminale: `plancia jarvis` mostra la scheda, e con 's' nello stdin (niente terminale) non conferma",
              r.returncode == 0 and "spegnere il forno" in r.stdout and "non eseguito" in r.stdout
              and n_task_cli() == prima, (r.stdout + r.stderr)[-300:])
        jarvis_sorgente = (RADICE / "plancia" / "cli.py").read_text("utf-8")
        prova("terminale: la conferma a tastiera chiede solo a un terminale vero (isatty)",
              "isatty()" in jarvis_sorgente and "_conferma_a_tastiera" in jarvis_sorgente)

        # --- il web: la scheda con Conferma e Annulla
        app = (RADICE / "web" / "app.js").read_text("utf-8")
        css = (RADICE / "web" / "style.css").read_text("utf-8")
        prova("web: schedaJarvis mostra Conferma e Annulla e chiama conferma/rifiuta",
              "function schedaJarvis" in app and "data-j=\"conferma\"" in app and "data-j=\"annulla\"" in app
              and "/api/jarvis/conferma" in app and "/api/jarvis/rifiuta" in app)
        prova("web: il pulsante Rilancia passa dalla scheda, non da un fatto",
              "if (r.proposta)" in app and "await schedaJarvis(r.proposta" in app)
        prova("web: Esc e un clic fuori buttano la scheda, il focus parte su Annulla",
              "ev.key === 'Escape'" in app and "[data-j=\"annulla\"]').focus()" in app)
        prova("web: la scheda ha il suo stile", ".jscheda" in css and ".jscheda-az" in css)
    finally:
        try:
            jarvis.spegni()
        except Exception:
            pass
        recap.claude_bin = vero_bin
        cantiere.avvia = vero_avvia
        voice.pocket_vivo, voice.voicebox_vivo = vero_pocket, vero_vb
        os.environ.pop("FINTO_LOG", None)


# ------------------------------------------------------------------------ 3. riprendi

def _riprendi(prova, tmp, cantiere, config, recap, store) -> None:
    registro = tmp / "argv.jsonl"
    finto_c = _finti.crea_finto(tmp / "bin-riprendi", "claude-argv", CLAUDE_FINTO_ARGV)
    finto_x = _finti.crea_finto(tmp / "bin-riprendi", "codex-argv", CODEX_FINTO_ARGV)
    os.environ["FINTO_ARGV"] = str(registro)
    # Altri lotti della stessa suite lasciano `recap.claude_bin` sostituito (un lambda
    # che torna "" o un finto loro): qui serve il finto che registra argv, qualunque
    # cosa sia rimasta in giro.
    vero_claude_bin = recap.claude_bin
    recap.claude_bin = lambda: finto_c
    cfg_vecchia = config.load_config()
    cfg = dict(cfg_vecchia)
    cfg["claude_bin"] = finto_c
    cfg["codex_bin"] = finto_x
    cfg["modello_cantiere"] = "sonnet"
    config.save_config(cfg)
    cwd = tmp / "lavoro"
    cwd.mkdir(exist_ok=True)
    try:
        conn = store.connect()
        store.init_db(conn)

        def lancia(agente, sessione=None, copia=False):
            registro.write_text("") if not registro.exists() else None
            prima = len(_registro(registro))
            cantiere.avvia(conn, "prova modello", agente=agente, cwd=str(cwd), sessione=sessione,
                           copia=copia, attendi=True, lingua="it")
            righe = _registro(registro)[prima:]
            return righe[-1]["argv"] if righe else None

        nuova = lancia("claude")
        prova("riprendi: una sessione NUOVA parte col modello del cantiere",
              nuova is not None and "--model" in nuova and nuova[nuova.index("--model") + 1] == "sonnet", str(nuova))
        ripresa = lancia("claude", sessione="sid-utente-0001")
        prova("riprendi: `claude -p --resume <id>` NON passa --model (resta quello della conversazione)",
              ripresa is not None and "--resume" in ripresa and ripresa[ripresa.index("--resume") + 1] == "sid-utente-0001"
              and "--model" not in ripresa and "-m" not in ripresa, str(ripresa))
        copia = lancia("claude", sessione="sid-utente-0002", copia=True)
        prova("riprendi: nemmeno la copia (`--fork-session`) cambia il modello",
              copia is not None and "--fork-session" in copia and "--model" not in copia, str(copia))
        prova("riprendi: la ripresa tiene i permessi di sempre (sola lettura: tool di lettura, niente acceptEdits)",
              ripresa is not None and "--allowedTools" in ripresa and "acceptEdits" not in ripresa, str(ripresa))
        scrive = None
        registro_prima = len(_registro(registro))
        cantiere.avvia(conn, "prova modello scrive", agente="claude", cwd=str(cwd), sessione="sid-utente-0003",
                       scrive=True, attendi=True, lingua="it")
        nuovi = _registro(registro)[registro_prima:]
        scrive = nuovi[-1]["argv"] if nuovi else None
        prova("riprendi: una ripresa in scrittura ha i suoi permessi e ancora nessun --model",
              scrive is not None and "acceptEdits" in scrive and "--model" not in scrive, str(scrive))

        cfg["modello_cantiere"] = "opus"
        config.save_config(cfg)
        nuova2 = lancia("claude")
        prova("riprendi: il modello del cantiere e' quello della configurazione, per le sessioni nuove",
              nuova2 is not None and nuova2[nuova2.index("--model") + 1] == "opus", str(nuova2))

        codex = lancia("codex", sessione="0199aaaa-0000-0000-0000-00000000c0de")
        prova("riprendi: `codex exec resume <id>` non passa --model",
              codex is not None and "resume" in codex and "--model" not in codex and "-m" not in codex, str(codex))
        codex_nuovo = lancia("codex")
        prova("riprendi: nemmeno una sessione codex nuova sceglie un modello da sola",
              codex_nuovo is not None and "exec" in codex_nuovo and "--model" not in codex_nuovo, str(codex_nuovo))

        # --- le strade che riprendono passano tutte da cantiere._comando
        sorgente = (RADICE / "plancia" / "cantiere.py").read_text("utf-8")
        prova("riprendi: nel cantiere il modello si mette in un posto solo, e solo senza sessione",
              sorgente.count('"--model"') == 1 and "if not sessione:" in sorgente)
        conn.close()
    finally:
        recap.claude_bin = vero_claude_bin
        config.save_config(cfg_vecchia)
        os.environ.pop("FINTO_ARGV", None)


# ------------------------------------------------------------------------ 4. http

def _http(prova, tmp) -> None:
    casa = tmp / "casa-http"
    casa.mkdir()
    (casa / "claude-vuota").mkdir()
    (casa / "codex-vuota").mkdir()
    finto = _finti.crea_finto(tmp / "bin-jarvis", "claude-finto-server", CLAUDE_FINTO_JARVIS)
    porta = _porta_libera()
    env = dict(os.environ)
    env["PLANCIA_HOME"] = str(casa)
    _finti.casa_finta(env, casa)
    env["CLAUDE_CONFIG_DIR"] = str(casa / "claude-vuota")
    env["CODEX_HOME"] = str(casa / "codex-vuota")
    env["FINTO_LOG"] = str(tmp / "claude-http.log")
    env["PATH"] = _finti.path_con(tmp / "bin-jarvis")
    server = None
    try:
        dati = subprocess.run([sys.executable, str(RADICE / "tools" / "demo-data.py")], env=env,
                              capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        if dati.returncode != 0:
            prova("http: l'archivio dimostrativo si crea", False, dati.stderr[-300:])
            return
        conf = json.loads((casa / "config.json").read_text("utf-8")) if (casa / "config.json").exists() else {}
        conf["claude_bin"] = finto
        conf["pocket_url"] = "http://127.0.0.1:9"
        conf["voicebox_url"] = "http://127.0.0.1:9"
        (casa / "config.json").write_text(json.dumps(conf), "utf-8")
        server = subprocess.Popen([sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta), "--no-sync"],
                                  cwd=str(RADICE), env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        base = "http://127.0.0.1:%d" % porta
        vivo = False
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/api/overview", timeout=1)
                vivo = True
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if server.poll() is not None:
                    break
                time.sleep(0.25)
        if not vivo:
            prova("http: il server di prova e' partito", False, (server.stdout.read() if server.stdout else "")[:500])
            return
        # Il token nasce alla prima richiesta che lo controlla: un rifiuto lo crea.
        try:
            urllib.request.urlopen(urllib.request.Request(
                base + "/api/jarvis/rifiuta", data=b"{}", method="POST",
                headers={"Content-Type": "application/json"}), timeout=20)
        except urllib.error.HTTPError:
            pass
        token = (casa / "token").read_text("utf-8").strip()

        def post(percorso, corpo):
            r = urllib.request.Request(base + percorso, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                       headers={"Content-Type": "application/json", "X-Plancia-Token": token})
            return json.loads(urllib.request.urlopen(r, timeout=120).read())

        def leggi(percorso):
            return json.loads(urllib.request.urlopen(base + percorso, timeout=60).read())

        # --- /api/jarvis: una scheda, mai un fatto
        n0 = len(leggi("/api/tasks"))
        r = post("/api/jarvis", {"testo": "ricordami di annaffiare le piante", "lang": "it", "voce": False})
        prova("http: /api/jarvis con una frase che scrive torna la scheda e non scrive",
              r.get("tipo") == "proposta" and (r.get("proposta") or {}).get("id") and len(leggi("/api/tasks")) == n0,
              str(r)[:200])
        r2 = post("/api/jarvis/conferma", {"id": r["proposta"]["id"], "lang": "it"})
        prova("http: /api/jarvis/conferma (col token) esegue, e il task compare",
              r2.get("eseguita") is True and len(leggi("/api/tasks")) == n0 + 1, str(r2)[:200])
        r = post("/api/jarvis", {"testo": "ricordami di buttare l'umido", "lang": "it", "voce": False})
        r3 = post("/api/jarvis/rifiuta", {"id": r["proposta"]["id"], "lang": "it"})
        r4 = post("/api/jarvis/conferma", {"id": r["proposta"]["id"], "lang": "it"})
        prova("http: /api/jarvis/rifiuta butta la scheda, e dopo non si conferma",
              not r4.get("eseguita") and len(leggi("/api/tasks")) == n0 + 1, str(r3)[:80] + str(r4)[:120])
        r = post("/api/jarvis", {"testo": "proponi: " + json.dumps({"azione": "task_add", "titolo": "Dal modello"}),
                                 "lang": "it", "voce": False})
        prova("http: una proposta del modello, dalla dashboard, e' una scheda e non un task",
              (r.get("proposta") or {}).get("id") and len(leggi("/api/tasks")) == n0 + 1, str(r)[:200])
        try:
            urllib.request.urlopen(urllib.request.Request(
                base + "/api/jarvis/conferma", data=b'{"id": "x"}', method="POST",
                headers={"Content-Type": "application/json"}), timeout=20)
            codice = 200
        except urllib.error.HTTPError as exc:
            codice = exc.code
        prova("http: la conferma senza token e' rifiutata", codice == 403, str(codice))
        log = Path(env["FINTO_LOG"]).read_text("utf-8") if Path(env["FINTO_LOG"]).exists() else ""
        argvs = [json.loads(r[5:]) for r in log.splitlines() if r.startswith("ARGV ")]
        prova("http: il modello lanciato dalla dashboard ha i tool di scrittura negati",
              bool(argvs) and all("--disallowedTools" in a and "mcp__plancia__plancia_task_add" in a for a in argvs),
              str(argvs)[:200])

        # --- il 403 legge il corpo: la richiesta dopo, sulla stessa connessione, esce pulita
        corpo = json.dumps({"testo": "x" * 3000}).encode("utf-8")
        for percorso in ("/api/jarvis", "/api/tasks", "/api/jarvis/conferma"):
            conn = http.client.HTTPConnection("127.0.0.1", porta, timeout=20)
            try:
                conn.request("POST", percorso, body=corpo, headers={"Content-Type": "application/json"})
                a = conn.getresponse()
                a.read()
                primo = a.status
                conn.request("GET", "/api/overview")
                b = conn.getresponse()
                b.read()
                secondo = b.status
            except (http.client.HTTPException, OSError) as exc:
                primo, secondo = 0, str(exc)
            finally:
                conn.close()
            prova("403: POST %s senza token e poi un GET sulla stessa connessione: 403 poi 200" % percorso,
                  primo == 403 and secondo == 200, "%s poi %s" % (primo, secondo))
        # un corpo enorme non si legge: la connessione si chiude, ma la risposta e' un 403 pulito
        conn = http.client.HTTPConnection("127.0.0.1", porta, timeout=20)
        try:
            conn.putrequest("POST", "/api/tasks")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(50 * 1024 * 1024))
            conn.endheaders()
            a = conn.getresponse()
            a.read()
            grande = (a.status, (a.getheader("Connection") or "").lower())
        except (http.client.HTTPException, OSError) as exc:
            grande = (0, str(exc))
        finally:
            conn.close()
        prova("403: un corpo da 50 MB non si legge: 403 e connessione chiusa", grande == (403, "close"), str(grande))
        prova("403: con un token giusto le scritture funzionano ancora sulla stessa connessione",
              len(post("/api/jarvis/conferma", {"id": "inesistente"})) >= 1)

        # --- la mappa via HTTP: la seconda richiesta e' quella in cache, e non blocca il resto
        m1 = leggi("/api/memoria/mappa")
        t0 = time.time()
        m2 = leggi("/api/memoria/mappa")
        caldo = time.time() - t0
        prova("http: /api/memoria/mappa: nodi con posizione, legami, e la seconda richiesta e' identica",
              len(m1["nodi"]) >= 40 and len(m1["archi"]) >= len(m1["nodi"]) // 2
              and all("x" in n and "y" in n for n in m1["nodi"]) and m1 == m2, "%d nodi" % len(m1["nodi"]))
        prova("http: la mappa in cache risponde subito (meno di un secondo anche sotto carico)", caldo < 1.0, "%.2f s" % caldo)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    _casa = tempfile.mkdtemp(prefix="plancia-prova-server-fine-casa-")
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
