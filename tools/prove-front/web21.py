"""Prove della dashboard web nella seconda passata di Plancia 2.0 (WEB).

La dashboard per Windows, Linux e il browser segue il disegno dell'app Mac 2.0:
font di sistema, barra laterale senza logo, Impostazioni in un menu, stato nel
sottotitolo, Oggi a colonna di lettura, Task come tabella con dettaglio,
Memoria con elenco e grafo a fisica, ricerca con ambiti e risultati immediati.

Due parti. Le statiche guardano il sorgente. Le dinamiche aprono la pagina per
davvero: un server di prova con l'archivio dimostrativo (PLANCIA_HOME in una
cartella temporanea, mai quello vero, claude e codex finti in testa al PATH) e
Chrome headless pilotato via CDP. Senza Chrome le dinamiche passano dicendo che
non sono state verificate, e il numero di prove resta lo stesso su ogni macchina
(stessa regola di memoria.py).
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

_spec = importlib.util.spec_from_file_location(
    "prove_front_memoria_helper", os.path.join(os.path.dirname(__file__), "memoria.py"))
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)



def _ambiente_chrome():
    import pwd
    return dict(os.environ, HOME=pwd.getpwuid(os.getuid()).pw_dir)


def _leggi(radice, *parti):
    return (radice.joinpath(*parti)).read_text(encoding="utf-8")


# ------------------------------------------------------------------ statiche
def _statiche(prova, radice):
    js = _leggi(radice, "web", "app.js")
    indice = _leggi(radice, "web", "index.html")

    prova("nessuno script esterno: la dashboard e il grafo sono JS puro (nessun <script src=http...>)",
          not re.search(r'<script[^>]+src="https?://', indice)
          and not re.search(r"\bd3\b|cytoscape|vis-network|sigma\.js|force-graph", js), "")
    grafo = js[js.index("function montaGrafo("):js.index("function distruggiGrafo(")]
    prova("il grafo disegna su un canvas e non su una libreria", "getContext('2d')" in grafo and "createElement('canvas')" in grafo, "")
    prova("il grafo ha una fisica: repulsione, molle sui legami, gravita' per tipo e calore che cala",
          all(x in grafo for x in ("function passo()", "alpha", "archi", "centro[")), "")
    prova("il grafo si trascina, si sposta e si ingrandisce (pointerdown, pointermove, wheel, pinch)",
          all(x in grafo for x in ("'pointerdown'", "'pointermove'", "'wheel'", "pinch")), "")
    prova("il grafo ha i livelli (1, 2, tutto) attorno al nodo scelto e l'adatta",
          all(x in grafo for x in ("setLivello", "ricalcolaVisibili", "adatta(")), "")
    prova("il grafo rispetta prefers-reduced-motion e ridisegna col tema",
          "prefers-reduced-motion" in grafo and "'plancia-tema'" in grafo, "")
    prova("il grafo parte sempre uguale (posizioni iniziali da un generatore seminato dal nome, niente Math.random per i nodi)",
          "seme(n.id)" in grafo, "")

    ric = js[js.index("const AMBITI"):js.index("(function collegaRicerca()")]
    prova("la ricerca ha cinque ambiti: Tutto, Task, Progetti, Sessioni, Memoria",
          re.findall(r"\['(\w+)', '\w+'\]", ric[:ric.index("const GRUPPI_RIC")]) == ["tutto", "task", "progetti", "sessioni", "memoria"], "")
    prova("la ricerca filtra subito in locale e poi chiede al server con 200 ms di calma",
          "filtraLocale(" in ric and "}, 200);" in ric, "")
    prova("la ricerca annulla la richiesta di prima (AbortController) e non fa saltare la lista (unisci)",
          "new AbortController()" in ric and "ric.ctl.abort()" in ric and "function unisci()" in ric, "")
    prova("Escape svuota la ricerca e riporta la vista", "ev.key === 'Escape'" in js and "chiudiRicerca(true)" in js, "")
    prova("/ e Cmd/Ctrl+K portano al campo di ricerca", "ev.key === '/'" in js and "toLowerCase() === 'k'" in js, "")

    prova("i vecchi indirizzi portano dove il contenuto e' finito (task, conoscenza, sessioni, agenti, capacita)",
          all(x in js for x in ("task: 'lavagna'", "conoscenza: 'memoria'", "sessioni: 'archivio'",
                                "agenti: 'archivio'", "capacita: 'archivio'")), "")
    prova("la dimensione del testo ha cinque gradini e si ricorda (plancia-scala)",
          "const SCALE = [0.85, 1, 1.15, 1.3, 1.5]" in js and "plancia-scala" in js, "")
    prova("la selezione di una riga non ridisegna la vista: cambia il dettaglio e l'indirizzo (replaceState)",
          "history.replaceState" in js and "async function seleziona(" in js, "")
    prova("tabella dei task: cerchio di stato, titolo, progetto, scadenza, fonte",
          all(x in js for x in ('class="tabella"', "cerchioTask(", "c-stato", "T('Scadenza')", "T('Fonte')")), "")
    prova("Memoria: l'elenco e' per tipo con i conteggi e 'Da sistemare' in fondo",
          "TIPI_MEM.map" in js and "T('Da sistemare')" in js, "")
    prova("Social e Progetti hanno il dettaglio a destra (DETTAGLI.social, DETTAGLI.progetti)",
          "DETTAGLI.social = async" in js and "DETTAGLI.progetti = async" in js, "")
    prova("non restano vortice, palette, spia in pillola ne' sync-dot nel JS",
          not re.search(r"function vortice|openPalette|spia-memoria|sync-dot|btn-theme|btn-lang", js), "")


# ------------------------------------------------------------------ dinamiche
_CONTROLLI = [
    "dinamica: Chrome headless risponde su /json/version",
    "dinamica: la barra laterale ha sei voci e nessun logo ne' wordmark",
    "dinamica: font di sistema, e nessun font web caricato",
    "dinamica: nessun errore JavaScript girando le sei viste",
    "dinamica: nessuna vista allarga la pagina in orizzontale, a 1280 e a 390 px",
    "dinamica: 'aggiornato alle' compare una volta sola per vista, nel sottotitolo",
    "dinamica: Oggi e' una colonna che non si allarga (stessa larghezza a 1280 e a 1800 px, al massimo 720)",
    "dinamica: Task e' una tabella e scegliere una riga cambia il dettaglio senza ridisegnare la vista",
    "dinamica: Memoria: il grafo ha un canvas dipinto e tanti nodi quanti sono i fatti",
    "dinamica: trascinare un nodo lo muove (la fisica lo segue)",
    "dinamica: il livello 1 tiene solo il nodo scelto e i suoi vicini, 'Tutto' li rimette",
    "dinamica: la rotella ingrandisce il grafo",
    "dinamica: la ricerca mostra i risultati subito, per ambito, e Escape riporta la vista",
    "dinamica: il menu Impostazioni: tema scuro, lingua inglese e testo piu' grande cambiano la pagina",
    "dinamica: nessun claude/codex vero e' partito per colpa di questa prova",
]

_JS_ERRORI = "Number(document.documentElement.dataset.errori || 0)"


def _attendi(sock, id_, espr, ok, timeout=12, await_promise=False):
    scadenza = time.time() + timeout
    ultimo = None
    while time.time() < scadenza:
        try:
            ultimo = _m._valuta(sock, id_, espr, await_promise)
        except (ConnectionError, TimeoutError):
            ultimo = None
        if ok(ultimo):
            return ultimo
        time.sleep(0.25)
    return ultimo


def _dinamica(radice):
    ris = {}
    casa = tempfile.mkdtemp(prefix="plancia-prova-web21-")
    cartelle = {k: os.path.join(casa, k) for k in ("claude-config", "codex-home", "chrome-profile", "bin-finti")}
    for c in cartelle.values():
        os.makedirs(c, exist_ok=True)
    agenti = os.path.join(casa, "agenti-vuoti.json")
    open(agenti, "w").write("[]")
    segnali = []
    for nome in ("claude", "codex"):
        seg = os.path.join(casa, "segnale-" + nome)
        segnali.append(seg)
        p = os.path.join(cartelle["bin-finti"], nome)
        open(p, "w").write("#!/bin/sh\ntouch '%s'\nexit 0\n" % seg)
        os.chmod(p, 0o755)
    for nome in ("terminale", "clipboard"):
        p = os.path.join(casa, nome + "-finto.sh")
        open(p, "w").write("#!/bin/sh\nexit 0\n")
        os.chmod(p, 0o755)
    amb = dict(os.environ)
    amb.update({
        "PLANCIA_HOME": casa, "CLAUDE_CONFIG_DIR": cartelle["claude-config"], "CODEX_HOME": cartelle["codex-home"],
        "PLANCIA_AGENTS_JSON": agenti, "PLANCIA_TERMINALE": os.path.join(casa, "terminale-finto.sh"),
        "PLANCIA_CLIPBOARD": os.path.join(casa, "clipboard-finto.sh"),
        "PATH": cartelle["bin-finti"] + os.pathsep + amb.get("PATH", ""),
        "PYTHONPATH": str(radice) + (os.pathsep + amb["PYTHONPATH"] if amb.get("PYTHONPATH") else ""),
    })
    server = chrome = sock = None
    try:
        subprocess.run([sys.executable, str(radice / "tools" / "demo-data.py")], env=amb, check=True,
                       capture_output=True, text=True)
        # qualche memoria in piu', con legami, perche' il grafo abbia qualcosa da muovere
        import sqlite3
        db = sqlite3.connect(os.path.join(casa, "plancia.db"))
        nomi = [("nota-%02d" % i, ["feedback", "user", "reference", "project"][i % 4]) for i in range(16)]
        for i, (n, t) in enumerate(nomi):
            legami = [nomi[(i + 1) % 16][0], nomi[(i + 5) % 16][0]]
            db.execute("INSERT INTO knowledge(name,path,scope,description,type,body,links,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                       (n, "/demo/x/%s.md" % n, "demo", "Una nota di prova numero %d" % i, t,
                        "# %s\nCorpo della nota. " % n + " ".join("[[%s]]" % x for x in legami) + " " + "testo " * 20,
                        json.dumps(legami), "2026-09-%02dT09:00:00Z" % (10 + i)))
        db.commit()
        db.close()
        porta = _m._porta_libera(int(os.environ.get("PLANCIA_WEB21_PORT", 7962)))
        server = subprocess.Popen([sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta), "--no-sync"],
                                  env=amb, cwd=str(radice), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            ris[_CONTROLLI[0]] = (False, "il server di prova non e' partito")
            return ris
        porta_cdp = _m._porta_libera(int(os.environ.get("PLANCIA_WEB21_CDP_PORT", 9591)))
        chrome = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                                   "--no-default-browser-check", f"--remote-debugging-port={porta_cdp}",
                                   f"--user-data-dir={cartelle['chrome-profile']}", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_ambiente_chrome())
        pronto = False
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{porta_cdp}/json/version", timeout=1)
                pronto = True
                break
            except Exception:
                time.sleep(0.25)
        ris[_CONTROLLI[0]] = (pronto, "")
        if not pronto:
            return ris
        sock = _m._apri_pagina_cdp(porta_cdp)
        sock.settimeout(30)
        n = [100]

        def cdp(metodo, par=None):
            n[0] += 1
            return _m._cdp(sock, n[0], metodo, par, timeout=30)

        def val(espr, aw=False):
            n[0] += 1
            return _m._valuta(sock, n[0], espr, aw)

        def apri(hash_, w=1280, h=820, lingua="it"):
            cdp("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 600})
            cdp("Page.navigate", {"url": f"http://127.0.0.1:{porta}/?ui={lingua}{hash_}"})
            time.sleep(0.6)

        def vista_pronta(v):
            return bool(v) and v.get("ok")

        JS_PRONTA = ("(function(){var v=document.getElementById('view');"
                     "return {ok: !!v && v.children.length > 0 && !/carico/.test(v.innerText.slice(0,40)) "
                     "&& (!!v.querySelector('.lettura,[data-lista],.scheda-pagina,.guida,.vuoto,.md') ), "
                     "sel: !!document.querySelector('#dettaglio') ? (document.querySelector('#dettaglio').innerText.length>0) : true};})()")

        viste = ["#/oggi", "#/lavagna", "#/progetti", "#/social", "#/memoria", "#/archivio"]

        # ---- barra laterale, font
        apri("#/oggi")
        _attendi(sock, 200, JS_PRONTA, vista_pronta)
        rail = val("""(function(){var r=document.querySelector('.rail');
          return {voci: [].map.call(r.querySelectorAll('nav a'), function(a){return a.textContent.trim().replace(/[0-9]+$/,'').trim();}),
                  immagini: r.querySelectorAll('img').length, testo: r.innerText.replace(/\\s+/g,' ').trim()};})()""") or {}
        ris[_CONTROLLI[1]] = (rail.get("immagini") == 0 and len(rail.get("voci", [])) == 6
                              and "Plancia" not in rail.get("testo", ""), repr(rail))
        font = val("""(function(){return {famiglia: getComputedStyle(document.body).fontFamily,
                        caricati: document.fonts ? document.fonts.size : -1};})()""") or {}
        ris[_CONTROLLI[2]] = (font.get("famiglia", "").startswith("-apple-system") and font.get("caricati") == 0, repr(font))

        # ---- le sei viste: errori, overflow, 'aggiornato'
        errori_tot, overflow, aggiornato = [], [], []
        for larghezza in (1280, 390):
            for v in viste:
                apri(v, larghezza)
                _attendi(sock, 201, JS_PRONTA, vista_pronta)
                time.sleep(0.5)
                r = val("""(function(){var t=document.body.innerText;
                  return {sw: document.documentElement.scrollWidth, iw: window.innerWidth,
                    agg: (t.match(/aggiornato alle/gi)||[]).length, sub: document.getElementById('tb-sub').textContent,
                    err: %s};})()""" % _JS_ERRORI) or {}
                if r.get("sw", 0) > r.get("iw", 0) + 1:
                    overflow.append(f"{v}@{larghezza}: {r.get('sw')}>{r.get('iw')}")
                if larghezza == 1280 and r.get("agg") != 1:
                    aggiornato.append(f"{v}: {r.get('agg')} {r.get('sub')!r}")
                if r.get("err"):
                    errori_tot.append(f"{v}@{larghezza}")
        ris[_CONTROLLI[3]] = (not errori_tot, str(errori_tot))
        ris[_CONTROLLI[4]] = (not overflow, str(overflow))
        ris[_CONTROLLI[5]] = (not aggiornato, str(aggiornato))

        # ---- Oggi: la colonna non si allarga
        larg = []
        for w in (1280, 1800):
            apri("#/oggi", w, 900)
            _attendi(sock, 202, JS_PRONTA, vista_pronta)
            larg.append(val("Math.round(document.querySelector('.lettura').getBoundingClientRect().width)"))
        ris[_CONTROLLI[6]] = (larg[0] == larg[1] and larg[0] is not None and larg[0] <= 720, str(larg))

        # ---- Task: tabella e dettaglio
        apri("#/lavagna")
        _attendi(sock, 203, JS_PRONTA, vista_pronta)
        time.sleep(0.8)
        t = val("""(async function(){
          var righe = document.querySelectorAll('table.tabella tbody tr[data-sel]');
          if (righe.length < 2) return {righe: righe.length};
          var vista = document.getElementById('view').firstElementChild;
          var prima = document.querySelector('#dettaglio h2').textContent;
          righe[1].click();
          await new Promise(function(r){ setTimeout(r, 400); });
          var dopo = document.querySelector('#dettaglio h2').textContent;
          return {righe: righe.length, prima: prima, dopo: dopo,
                  stessaVista: vista === document.getElementById('view').firstElementChild,
                  titolo: righe[1].querySelector('.c-tit').textContent,
                  sel: document.querySelectorAll('tr.sel').length,
                  hash: location.hash};
        })()""", True) or {}
        ris[_CONTROLLI[7]] = (t.get("righe", 0) > 2 and t.get("dopo") == t.get("titolo") and t.get("prima") != t.get("dopo")
                              and t.get("stessaVista") is True and t.get("sel") == 1 and "/lavagna/" in t.get("hash", ""),
                              repr(t))

        # ---- Memoria: il grafo
        apri("#/memoria")
        _attendi(sock, 204, JS_PRONTA, vista_pronta)
        time.sleep(0.5)
        val("document.querySelector('[data-filter=\"memoria.modo\"][data-value=\"grafo\"]').click()")
        g = _attendi(sock, 205, """(function(){var c=document.querySelector('#grafo-box canvas');
            if(!c||typeof state==='undefined'||!state.grafo) return null;
            var x=c.getContext('2d').getImageData(0,0,c.width,c.height).data, k=0;
            for (var i=3;i<x.length;i+=4*7) if (x[i]>0) k++;
            return {pixel:k, nodi: state.grafo.nodi.length, fatti: state.mappa.nodi.length, w:c.width, h:c.height};})()""",
                     lambda v: bool(v) and v.get("pixel", 0) > 50, timeout=10)
        ris[_CONTROLLI[8]] = (bool(g) and g.get("pixel", 0) > 50 and g.get("nodi") == g.get("fatti") and g.get("nodi", 0) >= 10, repr(g))

        d = val("""(async function(){
          var G = state.grafo, c = document.querySelector('#grafo-box canvas');
          var id = G.nodi[3].id, p = G.posizione(id), r = c.getBoundingClientRect();
          var n = G.nodi[3], x0 = n.x, y0 = n.y;
          function ev(t, x, y){ c.dispatchEvent(new PointerEvent(t, {pointerId: 7, clientX: r.left + x, clientY: r.top + y, bubbles: true, isPrimary: true})); }
          ev('pointerdown', p[0], p[1]);
          ev('pointermove', p[0] + 20, p[1] + 5);
          ev('pointermove', p[0] + 90, p[1] + 40);
          await new Promise(function(r){ setTimeout(r, 200); });
          var durante = {x: n.x, y: n.y, fisso: n.fisso};
          ev('pointerup', p[0] + 90, p[1] + 40);
          return {id: id, x0: x0, y0: y0, durante: durante, spostamento: Math.hypot(durante.x - x0, durante.y - y0)};
        })()""", True) or {}
        ris[_CONTROLLI[9]] = (d.get("spostamento", 0) > 20 and (d.get("durante") or {}).get("fisso") is True, repr(d))

        lv = val("""(async function(){
          var G = state.grafo, tutti = G.nodi.length;
          var id = state.sel.memoria; G.seleziona(id);
          document.querySelector('[data-act="grafo-livello"][data-v="1"]').click();
          await new Promise(function(r){ setTimeout(r, 300); });
          var uno = G.nodi.filter(function(n){return n.visT > 0;}).length;
          document.querySelector('[data-act="grafo-livello"][data-v="0"]').click();
          await new Promise(function(r){ setTimeout(r, 300); });
          var tuttiDi = G.nodi.filter(function(n){return n.visT > 0;}).length;
          return {tutti: tutti, uno: uno, dopo: tuttiDi, sel: id};
        })()""", True) or {}
        ris[_CONTROLLI[10]] = (0 < lv.get("uno", 0) < lv.get("tutti", 0) and lv.get("dopo") == lv.get("tutti"), repr(lv))

        z = val("""(async function(){
          var G = state.grafo, c = document.querySelector('#grafo-box canvas'), r = c.getBoundingClientRect();
          var k0 = G.ingrandimento();
          c.dispatchEvent(new WheelEvent('wheel', {deltaY: -300, clientX: r.left + r.width/2, clientY: r.top + r.height/2, bubbles: true, cancelable: true}));
          await new Promise(function(r){ setTimeout(r, 200); });
          return {k0: k0, k1: G.ingrandimento()};
        })()""", True) or {}
        ris[_CONTROLLI[11]] = (z.get("k1", 0) > z.get("k0", 1) * 1.1, repr(z))

        # ---- Ricerca
        apri("#/oggi")
        _attendi(sock, 206, JS_PRONTA, vista_pronta)
        time.sleep(0.5)
        val("document.getElementById('cerca-q').focus()")
        time.sleep(1.2)  # l'indice locale si carica al primo fuoco
        rr = val("""(async function(){
          var q = document.getElementById('cerca-q');
          q.value = 'lumen'; q.dispatchEvent(new Event('input', {bubbles: true}));
          await new Promise(function(r){ setTimeout(r, 120); });
          var subito = document.querySelectorAll('.risultato').length;
          var gruppi = [].map.call(document.querySelectorAll('.risultati h2'), function(h){return h.textContent;});
          document.querySelector('[data-act="ambito"][data-v="progetti"]').click();
          var soloProgetti = [].map.call(document.querySelectorAll('.risultati h2'), function(h){return h.textContent;});
          await new Promise(function(r){ setTimeout(r, 900); });
          q.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
          await new Promise(function(r){ setTimeout(r, 400); });
          return {subito: subito, gruppi: gruppi, soloProgetti: soloProgetti, valore: q.value,
                  tornata: !!document.querySelector('.lettura') && !document.querySelector('.risultati')};
        })()""", True) or {}
        ris[_CONTROLLI[12]] = (rr.get("subito", 0) > 0 and "Task" in rr.get("gruppi", []) and rr.get("soloProgetti") == ["Progetti"]
                               and rr.get("valore") == "" and rr.get("tornata") is True, repr(rr))

        # ---- Impostazioni
        apri("#/oggi")
        _attendi(sock, 207, JS_PRONTA, vista_pronta)
        s = val("""(async function(){
          localStorage.clear();
          var px0 = parseFloat(getComputedStyle(document.documentElement).fontSize);
          document.getElementById('btn-imp').click();
          var aperto = !document.getElementById('menu-imp').hidden;
          document.querySelector('[data-tema="dark"]').click();
          var scuro = document.documentElement.dataset.resolved;
          var fondo = getComputedStyle(document.body).backgroundColor;
          document.querySelector('[data-scala="1"]').click();
          var px1 = parseFloat(getComputedStyle(document.documentElement).fontSize);
          document.querySelector('[data-lingua="en"]').click();
          await new Promise(function(r){ setTimeout(r, 1200); });
          return {aperto: aperto, scuro: scuro, fondo: fondo, px0: px0, px1: px1,
                  titolo: document.getElementById('tb-titolo').textContent, lang: document.documentElement.lang};
        })()""", True) or {}
        ris[_CONTROLLI[13]] = (s.get("aperto") is True and s.get("scuro") == "dark" and s.get("fondo") != "rgb(255, 255, 255)"
                               and s.get("px1", 0) > s.get("px0", 99) and s.get("titolo") == "Today" and s.get("lang") == "en", repr(s))
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass
        if chrome:
            chrome.kill()
            chrome.wait(timeout=10)
        if server:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
        rimasti = [p for p in segnali if os.path.exists(p)]
        shutil.rmtree(casa, ignore_errors=True)
        ris[_CONTROLLI[14]] = (not rimasti, repr(rimasti))
    return ris


def _prova_dinamica(prova, radice):
    if not os.path.exists(CHROME):
        for nome in _CONTROLLI:
            prova(f"{nome} (Chrome assente: non verificata)", True, "installa Chrome per verificare davvero")
        return
    try:
        ris = _dinamica(radice)
    except Exception as errore:  # noqa: BLE001 - non deve far perdere il conteggio fisso
        ris = {"_eccezione": f"{type(errore).__name__}: {errore}"}
    ecc = ris.pop("_eccezione", None)
    for nome in _CONTROLLI:
        ok, dettaglio = ris.get(nome, (False, ecc or "non raggiunta: una fase precedente ha interrotto la sequenza"))
        prova(nome, ok, dettaglio)


def esegui(prova, radice):
    _statiche(prova, radice)
    _prova_dinamica(prova, radice)
