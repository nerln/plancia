"""Prove per LOTTO-U1-APPWEB: la dashboard si installa come app dal browser
(Chrome, Edge, Safari) e si apre anche con il server spento.

Tre gruppi, tutti con un numero FISSO di prove (regola della casa, vedi
tools/prove-front/memoria.py: il README dichiara un solo numero, e la suite
deve contare lo stesso su ogni macchina, con o senza Chrome):

- statiche, sul sorgente: il manifest (JSON valido, solo campi dello standard,
  icone che esistono alle misure dichiarate, la maskable opaca), index.html che
  lo collega, sw.js (esclude /api/ dalla cache, cancella le cache vecchie, non
  usa skipWaiting), la registrazione in app.js (solo fuori dall'app mac), il
  README;
- HTTP, contro un server vero di prova (senza Chrome): i tipi mime, l'header
  Service-Worker-Allowed, la versione dentro sw.js uguale a quella di
  index.html, ogni indirizzo dell'elenco della shell che risponde 200, le
  icone e niente altro dentro /icone/;
- dinamiche, con Chrome headless via CDP: la pagina registra il worker, a
  server spento una ricarica VERA (Page.reload) mostra la dashboard con le
  card dalla memoria e la pillola "server non raggiungibile", un cambio di
  versione non lascia servita la shell vecchia. Senza Chrome ogni controllo
  si segna comunque, verde, con "(Chrome assente: non verificata)".

Il server di prova gira da una COPIA di plancia/ e web/ in una cartella
temporanea: cosi' la prova del cambio di versione puo' toccare web/app.js
senza mai modificare il repo. Archivio (PLANCIA_HOME) e profilo di Chrome sono
temporanei; sul PATH del server stanno claude e codex finti.

Funzione pubblica `esegui(prova, RADICE)`, come in tools/prove-front/README.md.
"""

import base64
import json
import os
import re
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def _leggi(radice, *parti):
    """Il testo di un file, o "" se manca: su un commit senza il lotto (dove
    manifest e sw.js non esistono) ogni prova deve risultare NO con un motivo,
    non fermare il modulo con un'eccezione e nascondere le dinamiche."""
    try:
        return radice.joinpath(*parti).read_text(encoding="utf-8")
    except OSError:
        return ""


def _senza_commenti(js):
    """Toglie i commenti (blocchi e righe) da un pezzo di JavaScript: i
    commenti di sw.js e di app.js NOMINANO skipWaiting e /api/ per spiegare
    perche' non ci sono, e una regex sul testo intero li scambierebbe per
    codice. Va bene solo per i pezzi che non hanno '//' dentro una stringa."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)(^|\s)//[^\n]*", r"\1", js)


# ---------------------------------------------------------------- PNG a mano

def _png_info(percorso):
    """(larghezza, altezza, tipo colore, ha tRNS) di una PNG, solo stdlib."""
    dati = percorso.read_bytes()
    if dati[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, ihdr, trns = 8, None, False
    while pos + 8 <= len(dati):
        lunghezza, tipo = struct.unpack(">I4s", dati[pos:pos + 8])
        corpo = dati[pos + 8:pos + 8 + lunghezza]
        if tipo == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo)
        elif tipo == b"tRNS":
            trns = any(b != 255 for b in corpo) if ihdr and ihdr[4] == 3 else True
        pos += 12 + lunghezza
    if not ihdr:
        return None
    return ihdr[0], ihdr[1], ihdr[4], trns


# ------------------------------------------------------------------ statiche

def _prova_manifest(prova, radice):
    percorso = radice / "web" / "manifest.webmanifest"
    prova("web/manifest.webmanifest esiste", percorso.is_file())
    try:
        m = json.loads(percorso.read_text(encoding="utf-8"))
    except Exception as errore:  # noqa: BLE001
        prova("il manifest è JSON valido", False, str(errore))
        for nome in ("il manifest ha i campi richiesti",
                     "il manifest ha solo campi dello standard Web App Manifest",
                     "il manifest prende i colori dal tema scuro di style.css",
                     "le icone del manifest esistono alle misure dichiarate",
                     "il manifest ha 192 e 512 'any' e una 'maskable'",
                     "la maskable è opaca (niente trasparenza da mascherare)",
                     "le icone del manifest pesano poco (sotto 200 KB in tutto)"):
            prova(nome, False, "manifest illeggibile")
        return
    prova("il manifest è JSON valido", isinstance(m, dict))

    prova("il manifest ha i campi richiesti",
          m.get("name") == "Plancia" and m.get("start_url") == "/#/oggi"
          and m.get("display") == "standalone" and m.get("scope") == "/"
          and bool(m.get("background_color")) and bool(m.get("theme_color")),
          repr({k: m.get(k) for k in ("name", "start_url", "display", "scope")}))

    standard = {"name", "short_name", "description", "lang", "dir", "id",
                "start_url", "scope", "display", "display_override", "orientation",
                "background_color", "theme_color", "icons", "screenshots",
                "shortcuts", "categories", "iarc_rating_id", "related_applications",
                "prefer_related_applications", "protocol_handlers", "file_handlers",
                "share_target", "launch_handler", "edge_side_panel", "scope_extensions",
                "handle_links", "note_taking", "tab_strip"}
    inventati = sorted(set(m) - standard)
    prova("il manifest ha solo campi dello standard Web App Manifest",
          not inventati, str(inventati))

    stile = _leggi(radice, "web", "style.css")
    trovato = re.search(r"--ink-0:\s*(#[0-9a-fA-F]{6})", stile)
    scuro = trovato.group(1).lower() if trovato else None
    prova("il manifest prende i colori dal tema scuro di style.css",
          scuro is not None and m.get("background_color", "").lower() == scuro
          and m.get("theme_color", "").lower() == scuro,
          f"--ink-0={scuro} manifest={m.get('background_color')}/{m.get('theme_color')}")

    icone = m.get("icons") or []
    problemi, peso = [], 0
    for ic in icone:
        src = ic.get("src", "")
        file = radice / "web" / src.lstrip("/")
        if not file.is_file():
            problemi.append(f"{src}: manca")
            continue
        info = _png_info(file)
        dichiarata = ic.get("sizes", "")
        if not info:
            problemi.append(f"{src}: non è una PNG")
        elif f"{info[0]}x{info[1]}" != dichiarata:
            problemi.append(f"{src}: dichiara {dichiarata}, è {info[0]}x{info[1]}")
        if ic.get("type") != "image/png":
            problemi.append(f"{src}: type {ic.get('type')}")
        peso += file.stat().st_size
    prova("le icone del manifest esistono alle misure dichiarate",
          bool(icone) and not problemi, str(problemi))

    any_ = {ic.get("sizes") for ic in icone if ic.get("purpose", "any") == "any"}
    maskable = [ic for ic in icone if "maskable" in ic.get("purpose", "")]
    prova("il manifest ha 192 e 512 'any' e una 'maskable'",
          {"192x192", "512x512"} <= any_ and len(maskable) >= 1,
          f"any={sorted(any_)} maskable={len(maskable)}")

    opache = []
    for ic in maskable:
        info = _png_info(radice / "web" / ic.get("src", "").lstrip("/"))
        # tipo 2 = RGB, 0 = grigi: senza alfa. 3 = palette: opaca se non c'e'
        # un tRNS con valori sotto 255. 4 e 6 hanno il canale alfa.
        if not info or info[2] in (4, 6) or info[3]:
            opache.append(ic.get("src"))
    prova("la maskable è opaca (niente trasparenza da mascherare)",
          bool(maskable) and not opache, str(opache))

    prova("le icone del manifest pesano poco (sotto 200 KB in tutto)",
          0 < peso < 200 * 1024, f"{peso} byte")


def _prova_index(prova, radice):
    indice = _leggi(radice, "web", "index.html")
    prova("index.html collega il manifest",
          bool(re.search(r'<link rel="manifest" href="/manifest\.webmanifest">', indice)))
    scuro = re.search(r'<meta name="theme-color" content="(#[0-9a-fA-F]{6})" '
                      r'media="\(prefers-color-scheme: dark\)">', indice)
    chiaro = re.search(r'<meta name="theme-color" content="(#[0-9a-fA-F]{6})" '
                       r'media="\(prefers-color-scheme: light\)">', indice)
    prova("index.html ha theme-color per il tema scuro e per il chiaro (con media)",
          bool(scuro and chiaro), f"scuro={bool(scuro)} chiaro={bool(chiaro)}")
    stile = _leggi(radice, "web", "style.css")
    ink = re.findall(r"--ink-0:\s*(#[0-9a-fA-F]{6})", stile)
    prova("i due theme-color sono i --ink-0 dei due temi di style.css",
          bool(scuro and chiaro and len(ink) >= 2)
          and scuro.group(1).lower() == ink[0].lower()
          and chiaro.group(1).lower() == ink[1].lower(),
          f"index={scuro and scuro.group(1)}/{chiaro and chiaro.group(1)} css={ink[:2]}")
    touch = re.search(r'<link rel="apple-touch-icon" href="(/icone/[\w.-]+\.png)">', indice)
    prova("index.html ha un apple-touch-icon che esiste su disco",
          bool(touch) and (radice / "web" / touch.group(1).lstrip("/")).is_file())


def _funzione(js, intestazione):
    """Il corpo della funzione che comincia con `intestazione` (graffe
    bilanciate), o None."""
    i = js.find(intestazione)
    if i < 0:
        return None
    a = js.index("{", i)
    livello = 0
    for k in range(a, len(js)):
        if js[k] == "{":
            livello += 1
        elif js[k] == "}":
            livello -= 1
            if livello == 0:
                return js[a:k + 1]
    return None


def _prova_sw(prova, radice):
    grezzo = _leggi(radice, "web", "sw.js")
    codice = _senza_commenti(grezzo)

    prova("sw.js non chiama skipWaiting né clients.claim (il nuovo worker aspetta)",
          bool(codice.strip()) and "skipWaiting" not in codice and "clients.claim" not in codice)

    prova("sw.js prende versione ed elenco dal server (segnaposto), non li scrive a mano",
          "'__PLANCIA_V__'" in codice and "'__PLANCIA_SHELL__'" in codice
          and "PREFISSO + VERSIONE" in codice)

    attiva = _funzione(codice, "addEventListener('activate'") or ""
    prova("all'attivazione sw.js cancella le cache vecchie (stesso prefisso, altra versione)",
          "caches.delete" in attiva and "startsWith(PREFISSO)" in attiva
          and "!== CACHE" in attiva, attiva[:120])

    fetch_ = _funzione(codice, "addEventListener('fetch'") or ""
    prima = fetch_.split("respondWith")[0] if "respondWith" in fetch_ else fetch_
    prova("le chiamate /api/ escono dal worker prima di ogni respondWith (mai in cache)",
          "respondWith" in fetch_ and "'/api/'" in prima and "return" in prima.split("'/api/'")[1][:60],
          prima[:200])
    prova("solo le GET e mai una richiesta con il token passano dal worker",
          "method !== 'GET'" in prima and "X-Plancia-Token" in prima)
    prova("sw.js non mette mai in cache un indirizzo /api/ (nessun put con /api/ nel codice)",
          bool(codice.strip()) and not re.search(r"put\([^)]*api", codice, re.I)
          and codice.count("'/api/'") == 1)

    pagina = _funzione(codice, "async function paginaReteAllaPrima") or ""
    prova("la navigazione va PRIMA in rete e solo se cade si serve la cache",
          "await fetch(" in pagina and "catch" in pagina
          and pagina.index("await fetch(") < pagina.index("caches.open(CACHE).then((c) => c.match"))
    statico = _funzione(codice, "async function staticoCacheAllaPrima") or ""
    prova("le risorse statiche vanno prima in cache, poi in rete",
          "cache.match" in statico and "await fetch(" in statico
          and statico.index("cache.match") < statico.index("await fetch("))
    prova("l'installazione salta la cache http (cache:'reload') e fallisce se manca un file",
          "cache: 'reload'" in codice and "throw new Error" in codice)


def _prova_registrazione(prova, radice):
    app = _leggi(radice, "web", "app.js")
    inizio = app.find("(function registraServiceWorker()")
    prova("app.js ha la funzione che registra il service worker", inizio >= 0)
    codice = _senza_commenti(app[inizio:]) if inizio >= 0 else ""
    prova("la registrazione chiede prima 'serviceWorker' in navigator",
          "'serviceWorker' in navigator" in codice)
    i_mac = codice.find("dataset.app === 'mac'")
    i_reg = codice.find(".register('/sw.js'")
    prova("dentro l'app mac (data-app='mac') non si registra: il controllo viene prima di register()",
          0 <= i_mac < i_reg, f"mac@{i_mac} register@{i_reg}")
    prova("si registra solo da http(s) su localhost, 127.0.0.1 o [::1]",
          "/^https?:$/" in codice and "'localhost'" in codice
          and "'127.0.0.1'" in codice and "'[::1]'" in codice)
    prova("un errore di registrazione è silenzioso: catch + console.warn, niente toast né throw",
          ".catch(" in codice and "console.warn" in codice
          and "toast(" not in codice and "throw" not in codice)
    prova("tutta la registrazione sta dentro un try (nessuna eccezione esce da app.js)",
          re.search(r"registraServiceWorker\(\)\s*\{\s*try\s*\{", codice) is not None
          and codice.rstrip().endswith("})();"))


def _prova_README_ed_export(prova, radice):
    it = _leggi(radice, "README.it.md")
    en = _leggi(radice, "README.md")
    prova("README.it.md dice come installarla da Chrome o Edge (Installa Plancia)",
          "Installa Plancia" in it and "127.0.0.1:7773" in it)
    prova("README.md says how to install it from Chrome or Edge (Install Plancia)",
          "Install Plancia" in en and "127.0.0.1:7773" in en)
    esporta = _leggi(radice, "plancia", "esporta.py")
    prova("l'export offline (esporta.py) è un file solo e non registra nessun service worker",
          "serviceWorker" not in esporta and "sw.js" not in esporta,
          "l'export non usa web/app.js: nessun motivo di toccarlo")


# --------------------------------------------------------------- HTTP e CDP

def _porta_libera(partenza):
    porta = partenza
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
        porta += 1


def _get(porta, percorso, timeout=8):
    """(stato, intestazioni, corpo) di una GET; gli errori HTTP tornano come stato."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{percorso}", timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as errore:
        return errore.code, dict(errore.headers), errore.read()


def _ws_connect(url, timeout=10):
    hostport, path = url[len("ws://"):].split("/", 1)
    host, _, porta = hostport.partition(":")
    sock = socket.create_connection((host, int(porta)), timeout=timeout)
    chiave = base64.b64encode(os.urandom(16)).decode()
    sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
                  f"Connection: Upgrade\r\nSec-WebSocket-Key: {chiave}\r\n"
                  f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
    risposta = b""
    while b"\r\n\r\n" not in risposta:
        pezzo = sock.recv(4096)
        if not pezzo:
            break
        risposta += pezzo
    if b" 101 " not in risposta.split(b"\r\n", 1)[0]:
        raise ConnectionError(f"handshake websocket rifiutato: {risposta[:120]!r}")
    return sock


def _ws_send(sock, testo):
    payload = testo.encode("utf-8")
    testa = bytearray([0x81])
    n = len(payload)
    if n < 126:
        testa.append(0x80 | n)
    elif n < (1 << 16):
        testa += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        testa += bytes([0x80 | 127]) + struct.pack(">Q", n)
    maschera = os.urandom(4)
    testa += maschera
    sock.sendall(bytes(testa) + bytes(b ^ maschera[i % 4] for i, b in enumerate(payload)))


def _esatti(sock, n):
    buf = b""
    while len(buf) < n:
        pezzo = sock.recv(n - len(buf))
        if not pezzo:
            raise ConnectionError("il socket websocket si è chiuso")
        buf += pezzo
    return buf


def _ws_recv(sock):
    b0, b1 = _esatti(sock, 2)
    lunghezza = b1 & 0x7F
    if lunghezza == 126:
        lunghezza = struct.unpack(">H", _esatti(sock, 2))[0]
    elif lunghezza == 127:
        lunghezza = struct.unpack(">Q", _esatti(sock, 8))[0]
    maschera = _esatti(sock, 4) if b1 & 0x80 else None
    payload = _esatti(sock, lunghezza) if lunghezza else b""
    if maschera:
        payload = bytes(b ^ maschera[i % 4] for i, b in enumerate(payload))
    if b0 & 0x0F == 0x8:
        raise ConnectionError("il target ha chiuso la connessione CDP")
    return payload.decode("utf-8", "replace")


class _Pagina:
    """Una scheda di Chrome pilotata via CDP, con un contatore di id suo."""

    def __init__(self, porta_cdp):
        self.porta_cdp = porta_cdp
        # about:blank e poi Page.navigate: un '#' nell'indirizzo verrebbe letto
        # come fragment della richiesta HTTP a /json/new e sparirebbe.
        richiesta = urllib.request.Request(
            f"http://127.0.0.1:{porta_cdp}/json/new?about:blank", method="PUT")
        with urllib.request.urlopen(richiesta, timeout=10) as r:
            info = json.load(r)
        self.id = info["id"]
        self.sock = _ws_connect(info["webSocketDebuggerUrl"])
        self.n = 0

    def cdp(self, metodo, parametri=None, timeout=15):
        self.n += 1
        mio = self.n
        _ws_send(self.sock, json.dumps({"id": mio, "method": metodo, "params": parametri or {}}))
        scadenza = time.time() + timeout
        while time.time() < scadenza:
            msg = json.loads(_ws_recv(self.sock))
            if msg.get("id") == mio:
                return msg
        raise TimeoutError(f"CDP {metodo} senza risposta entro {timeout}s")

    def valuta(self, espressione, await_promise=False):
        try:
            r = self.cdp("Runtime.evaluate", {"expression": espressione,
                                              "returnByValue": True,
                                              "awaitPromise": await_promise})
        except (ConnectionError, TimeoutError, socket.timeout, OSError) as errore:
            return {"errore_cdp": f"{type(errore).__name__}: {errore}"}
        risultato = (r.get("result") or {}).get("result") or {}
        if "value" in risultato:
            return risultato["value"]
        return {"errore_cdp": json.dumps(r)[:200]}

    def attendi(self, espressione, condizione, timeout=12, await_promise=True):
        """Ripete `espressione` finche' `condizione(valore)` e' vera. Torna
        l'ultimo valore (vero o no): chi chiama controlla di nuovo."""
        # Le attese sono sondaggi: tornano appena la condizione e' vera, quindi un
        # timeout largo non costa niente a chi passa. Sono triplicate perche' un
        # runner di CI carico (o un Mac con la macchina occupata) impiega molto piu'
        # di uno da sviluppo a chiudere una pagina e attivare un worker.
        scadenza = time.time() + timeout * 3
        valore = None
        while time.time() < scadenza:
            valore = self.valuta(espressione, await_promise)
            try:
                if condizione(valore):
                    return valore
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.3)
        return valore

    def chiudi(self):
        try:
            self.sock.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.porta_cdp}/json/close/{self.id}",
                                   timeout=5).read()
        except Exception:  # noqa: BLE001
            pass


_JS_SW = """(async function(){try{
  var r = await navigator.serviceWorker.getRegistration();
  if(!r) return {registrato:false, controller: !!navigator.serviceWorker.controller};
  return {registrato:true, scope:r.scope,
    attivo: r.active ? r.active.state : null,
    attesa: r.waiting ? r.waiting.state : null,
    installazione: r.installing ? r.installing.state : null,
    controller: navigator.serviceWorker.controller ? navigator.serviceWorker.controller.state : null};
}catch(e){return {errore:String(e)}}})()"""

_JS_CACHE = """(async function(){try{
  var out = {}; var nomi = await caches.keys();
  for (var n of nomi){ var c = await caches.open(n); var k = await c.keys();
    out[n] = k.map(function(x){ var u = new URL(x.url); return u.pathname + u.search; }); }
  return out;
}catch(e){return {errore:String(e)}}})()"""

_JS_PAGINA = """(function(){try{
  var v = document.getElementById('view'), s = document.getElementById('spia-memoria');
  var a = document.querySelector('script[src*="app.js"]');
  return {href: location.href, view: !!v,
    card: v ? v.querySelectorAll('[data-chiave]').length : 0,
    spia: s ? s.textContent : null,
    scriptApp: a ? a.src : null,
    marcatore: (typeof window.__versioneProva === 'undefined') ? null : window.__versioneProva,
    controllato: !!(navigator.serviceWorker && navigator.serviceWorker.controller),
    preReload: typeof window.__preReload};
}catch(e){return {errore:String(e)}}})()"""

_JS_API_SPENTA = """(async function(){try{
  var r = await fetch('/api/status');
  return {ok: r.ok, stato: r.status};
}catch(e){return {caduta:true, errore:String(e)}}})()"""

_JS_MAC = """(function(){
  function metti(){ var e = document.documentElement; if (e) { e.dataset.app = 'mac'; return true; } return false; }
  if (!metti())
    new MutationObserver(function(){ if (metti()) this.disconnect(); }).observe(document, {childList: true});
})();"""

_CONTROLLI_HTTP = [
    "server: /manifest.webmanifest risponde 200 come application/manifest+json ed è JSON",
    "server: /sw.js risponde come JavaScript con Service-Worker-Allowed: / e senza segnaposto",
    "server: la versione dentro /sw.js è lo stesso ?v= che index.html mette su app.js e style.css",
    "server: ogni indirizzo dell'elenco della shell in /sw.js risponde 200 (l'installazione non cade)",
    "server: /icone/ serve PNG e nient'altro (né .py, né '..', né un'altra cartella)",
    "server: /api/ e /audio/ non stanno nell'elenco della shell",
]

_CONTROLLI_DINAMICI = [
    "dinamica: Chrome headless risponde su /json/version",
    "dinamica: dentro l'app mac (data-app='mac') la pagina NON registra nessun service worker",
    "dinamica: fuori dall'app mac la pagina registra il service worker, con scope /, e si attiva",
    "dinamica: all'attivazione la shell è tutta in cache (ogni indirizzo dell'elenco)",
    "dinamica: dopo aver usato la dashboard sotto il worker nessuna chiamata /api/ è finita in cache",
    "dinamica: a server spento una ricarica vera (Page.reload) apre la dashboard, "
    "non la pagina d'errore del browser",
    "dinamica: a server spento le card ci sono (dalla memoria) e la pillola dice "
    "server non raggiungibile",
    "dinamica: a server spento /api/ fallisce davvero, anche se online era riuscita (il worker non risponde al posto del server)",
    "dinamica: dopo un cambio di versione la pagina servita è la NUOVA, anche sotto il worker vecchio",
    "dinamica: il worker nuovo si installa ma aspetta (niente skipWaiting): la pagina "
    "aperta resta sotto il vecchio",
    "dinamica: a server spento, dopo il cambio di versione, la ricarica mostra la shell NUOVA "
    "e non la vecchia",
    "dinamica: chiusa la pagina il worker nuovo si attiva e cancella la cache della versione vecchia",
    "dinamica: col worker nuovo attivo, a server spento la ricarica mostra ancora la shell nuova "
    "(la sua cache è completa)",
]


def _ambiente(radice, casa, copia):
    claude_cfg = os.path.join(casa, "claude-config")
    codex_home = os.path.join(casa, "codex-home")
    bin_finti = os.path.join(casa, "bin-finti")
    for cartella in (claude_cfg, codex_home, bin_finti):
        os.makedirs(cartella, exist_ok=True)
    agenti = os.path.join(casa, "agenti-vuoti.json")
    with open(agenti, "w", encoding="utf-8") as f:
        f.write("[]")
    finto = os.path.join(casa, "finto.sh")
    with open(finto, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(finto, 0o755)
    segnali = []
    # Ogni comando che potrebbe toccare qualcosa di vero e' finto, sul PATH del
    # server: nemmeno un server di prova deve poter fermare o lanciare niente
    # della macchina (il 29/09 una HOME finta non bastava per launchctl).
    for nome in ("claude", "codex", "launchctl", "osascript", "schtasks", "systemctl", "crontab"):
        segnale = os.path.join(casa, "segnale-" + nome)
        segnali.append(segnale)
        percorso = os.path.join(bin_finti, nome)
        with open(percorso, "w", encoding="utf-8") as f:
            f.write(f"#!/bin/sh\ntouch {shlex.quote(segnale)}\nexit 0\n")
        os.chmod(percorso, 0o755)
    amb = dict(os.environ)
    amb.update({
        "PLANCIA_HOME": os.path.join(casa, "home"),
        "CLAUDE_CONFIG_DIR": claude_cfg,
        "CODEX_HOME": codex_home,
        "PLANCIA_AGENTS_JSON": agenti,
        "PLANCIA_TERMINALE": finto,
        "PLANCIA_CLIPBOARD": finto,
        "PATH": bin_finti + os.pathsep + amb.get("PATH", ""),
        "PYTHONPATH": str(copia),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return amb, segnali


def _avvia_server(copia, porta, amb):
    server = subprocess.Popen(
        [sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta), "--no-sync"],
        env=amb, cwd=str(copia), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(60):
        if server.poll() is not None:
            break
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=1).read()
            return server, None
        except Exception:  # noqa: BLE001
            time.sleep(0.25)
    uscita = ""
    try:
        server.kill()
        uscita = server.stdout.read()[-300:] if server.stdout else ""
    except Exception:  # noqa: BLE001
        pass
    return None, "il server di prova non è partito: " + uscita


def _ferma(server):
    if not server:
        return
    server.terminate()
    try:
        server.wait(timeout=8)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=8)


def _shell_da_sw(testo_sw):
    trovato = re.search(r"SHELL = JSON\.parse\('(\[.*?\])'\)", testo_sw)
    return json.loads(trovato.group(1)) if trovato else None


def _prove_http(porta, risultati):
    """Le sei prove HTTP contro il server v1. Torna la lista della shell."""
    st, testa, corpo = _get(porta, "/manifest.webmanifest")
    try:
        json.loads(corpo.decode("utf-8"))
        valido = True
    except Exception:  # noqa: BLE001
        valido = False
    risultati[_CONTROLLI_HTTP[0]] = (
        st == 200 and testa.get("Content-Type", "").startswith("application/manifest+json") and valido,
        f"{st} {testa.get('Content-Type')}")

    st, testa, corpo = _get(porta, "/sw.js")
    testo_sw = corpo.decode("utf-8", "replace")
    risultati[_CONTROLLI_HTTP[1]] = (
        st == 200 and "javascript" in testa.get("Content-Type", "")
        and testa.get("Service-Worker-Allowed") == "/" and "__PLANCIA_" not in testo_sw,
        f"{st} {testa.get('Content-Type')} SWA={testa.get('Service-Worker-Allowed')}")
    shell = _shell_da_sw(testo_sw)

    _, _, indice = _get(porta, "/")
    indice = indice.decode("utf-8", "replace")
    v_indice = set(re.findall(r"/(?:style\.css|app\.js|moto\.css)\?v=(\d+)", indice))
    v_sw = re.search(r"VERSIONE = '(\d+)'", testo_sw)
    risultati[_CONTROLLI_HTTP[2]] = (
        len(v_indice) == 1 and bool(v_sw) and v_sw.group(1) in v_indice,
        f"index={sorted(v_indice)} sw={v_sw and v_sw.group(1)}")

    cattivi = []
    for url in shell or []:
        s, _, c = _get(porta, url)
        if s != 200 or not c:
            cattivi.append(f"{url}: {s}")
    risultati[_CONTROLLI_HTTP[3]] = (
        bool(shell) and "/" in shell and any(u.startswith("/app.js?v=") for u in shell)
        and any(u.endswith(".woff2") for u in shell) and any(u.startswith("/icone/") for u in shell)
        and not cattivi, str(cattivi[:4]) or f"{len(shell or [])} indirizzi")

    s1, t1, c1 = _get(porta, "/icone/icon-192.png")
    ok = s1 == 200 and t1.get("Content-Type") == "image/png" and c1[:8] == b"\x89PNG\r\n\x1a\n"
    for cattivo in ("/icone/genera_icone.py", "/icone/", "/icone/../app.js", "/icone/%2e%2e/app.js",
                    "/icone/sub/icon-192.png", "/icone/nonesiste.png"):
        s, _, _c = _get(porta, cattivo)
        ok = ok and s == 404
    risultati[_CONTROLLI_HTTP[4]] = (ok, f"{s1} {t1.get('Content-Type')}")

    risultati[_CONTROLLI_HTTP[5]] = (
        bool(shell) and not any("/api/" in u or "/audio/" in u for u in shell), str(shell)[:120])
    return shell


def _dinamica(radice, chrome):
    """Tutto il giro vero. Torna {nome: (ok, dettaglio)} per HTTP e dinamica."""
    risultati = {}
    casa = tempfile.mkdtemp(prefix="plancia-prova-appweb-")
    copia = os.path.join(casa, "copia")
    profilo = os.path.join(casa, "chrome-profile")
    os.makedirs(profilo)
    for cartella in ("plancia", "web"):
        shutil.copytree(radice / cartella, os.path.join(copia, cartella),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    amb, segnali = _ambiente(radice, casa, copia)
    server = chrome_proc = None
    pagine = []
    try:
        amb_demo = dict(amb, PYTHONPATH=str(radice))
        subprocess.run([sys.executable, str(radice / "tools" / "demo-data.py")],
                       env=amb_demo, check=True, capture_output=True, text=True)
        porta = _porta_libera(int(os.environ.get("PLANCIA_APPWEB_PORT", 7961)))
        server, errore = _avvia_server(copia, porta, amb)
        if errore:
            for nome in _CONTROLLI_HTTP + _CONTROLLI_DINAMICI:
                risultati[nome] = (False, errore)
            return risultati
        shell = _prove_http(porta, risultati)

        if chrome is None:
            return risultati

        porta_cdp = _porta_libera(int(os.environ.get("PLANCIA_APPWEB_CDP_PORT", 9581)))
        chrome_proc = subprocess.Popen([
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--no-default-browser-check",
            f"--remote-debugging-port={porta_cdp}", f"--user-data-dir={profilo}",
            "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pronto = False
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{porta_cdp}/json/version", timeout=1).read()
                pronto = True
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        risultati[_CONTROLLI_DINAMICI[0]] = (pronto, "")
        if not pronto:
            return risultati

        origine = f"http://127.0.0.1:{porta}"
        url_vista = f"{origine}/?ui=it#/progetti"

        # 1) dentro l'app mac: la pagina parte, ma NON registra. Il marcatore
        # data-app='mac' e' messo come fa main.swift (a inizio documento); se
        # non attecchisse, la prova sarebbe verde per il motivo sbagliato,
        # quindi si legge anche il marcatore.
        mac = _Pagina(porta_cdp)
        pagine.append(mac)
        mac.cdp("Page.enable")  # senza, addScriptToEvaluateOnNewDocument non si applica
        mac.cdp("Page.addScriptToEvaluateOnNewDocument", {"source": _JS_MAC})
        mac.cdp("Page.navigate", {"url": url_vista})
        mac.attendi(_JS_PAGINA, lambda v: v.get("view") and v.get("card", 0) > 0)
        time.sleep(3.0)  # la registrazione partirebbe a 'load': si lascia il tempo
        stato = mac.valuta("""(async function(){try{
            var r = await navigator.serviceWorker.getRegistrations();
            return {app: document.documentElement.dataset.app, registrazioni: r.length,
                    vista: document.getElementById('view').children.length};
        }catch(e){return {errore:String(e)}}})()""", True)
        risultati[_CONTROLLI_DINAMICI[1]] = (
            stato.get("app") == "mac" and stato.get("registrazioni") == 0 and stato.get("vista", 0) > 0,
            repr(stato))
        mac.chiudi()
        pagine.remove(mac)

        # 2) fuori dall'app mac
        p = _Pagina(porta_cdp)
        pagine.append(p)
        p.cdp("Page.navigate", {"url": url_vista})
        sw = p.attendi(_JS_SW, lambda v: v.get("attivo") == "activated", timeout=20)
        risultati[_CONTROLLI_DINAMICI[2]] = (
            bool(sw.get("registrato")) and sw.get("scope") == origine + "/"
            and sw.get("attivo") == "activated", repr(sw))

        cache = p.valuta(_JS_CACHE, True)
        nomi_v1 = [n for n in cache if n.startswith("plancia-shell-")] if isinstance(cache, dict) else []
        chiavi = set(cache[nomi_v1[0]]) if len(nomi_v1) == 1 else set()
        mancanti = sorted(set(shell or []) - chiavi)
        risultati[_CONTROLLI_DINAMICI[3]] = (
            len(nomi_v1) == 1 and bool(shell) and not mancanti, f"{nomi_v1} mancano {mancanti[:4]}")

        # la dashboard in uso: la memoria di Progetti deve esistere prima di
        # spegnere il server (e' quello che il F5 a server spento ridisegna)
        p.attendi("""(function(){try{return Object.keys(localStorage).some(function(k){
            return k.indexOf('plancia-memoria')===0 && k.indexOf(':progetti:')>=0;});}catch(e){return false}})()""",
                  lambda v: v is True, timeout=15, await_promise=False)
        # Una ricarica ONLINE: ora la pagina e' sotto il worker (al primo
        # caricamento non lo era ancora) e le sue chiamate /api/ passano
        # davvero da li'. Senza questo passo "nessuna /api/ in cache" e "a
        # server spento /api/ cade" sarebbero veri anche con un worker che le
        # cattura, perche' nessuna chiamata gli sarebbe mai arrivata.
        p.valuta("window.__preReload = true")
        p.cdp("Page.reload", {"ignoreCache": False})
        p.attendi(_JS_PAGINA, lambda v: v.get("preReload") != "boolean")
        p.attendi(_JS_PAGINA, lambda v: v.get("card", 0) > 0 and v.get("controllato") is True, timeout=15)
        api_online = p.valuta(_JS_API_SPENTA, True)
        cache = p.valuta(_JS_CACHE, True)
        api_in_cache = [u for urls in cache.values() for u in urls if "/api/" in u] \
            if isinstance(cache, dict) and "errore" not in cache else ["non leggibile"]
        risultati[_CONTROLLI_DINAMICI[4]] = (
            not api_in_cache and len(nomi_v1) == 1 and api_online.get("ok") is True,
            f"{api_in_cache[:3]} cache={nomi_v1} api online={api_online}")

        # 3) server spento, F5 vero
        _ferma(server)
        server = None
        p.valuta("window.__preReload = true")
        p.cdp("Page.reload", {"ignoreCache": True})
        p.attendi(_JS_PAGINA, lambda v: v.get("preReload") != "boolean")
        dopo = p.attendi(_JS_PAGINA,
                         lambda v: v.get("view") and v.get("card", 0) > 0
                         and ("raggiungibile" in (v.get("spia") or "") or "unreachable" in (v.get("spia") or "")),
                         timeout=15)
        risultati[_CONTROLLI_DINAMICI[5]] = (
            bool(dopo.get("view")) and str(dopo.get("href", "")).startswith(origine)
            and dopo.get("controllato") is True, repr(dopo)[:300])
        risultati[_CONTROLLI_DINAMICI[6]] = (
            dopo.get("card", 0) > 0 and ("raggiungibile" in (dopo.get("spia") or "")
                                         or "unreachable" in (dopo.get("spia") or "")),
            f"card={dopo.get('card')} spia={dopo.get('spia')!r}")
        api = p.valuta(_JS_API_SPENTA, True)
        risultati[_CONTROLLI_DINAMICI[7]] = (
            bool(api.get("caduta")) and dopo.get("controllato") is True
            and api_online.get("ok") is True, f"offline={api!r} online={api_online!r}")

        # 4) cambio di versione: si tocca web/app.js della COPIA (mai del repo)
        # con un marcatore e una data nel futuro, e si riavvia sulla stessa
        # porta (stessa origine, quindi stesso worker registrato)
        percorso_app = os.path.join(copia, "web", "app.js")
        with open(percorso_app, "a", encoding="utf-8") as f:
            f.write("\nwindow.__versioneProva = 2;\n")
        futuro = time.time() + 120
        os.utime(percorso_app, (futuro, futuro))
        server, errore = _avvia_server(copia, porta, amb)
        if errore:
            for nome in _CONTROLLI_DINAMICI[8:]:
                risultati[nome] = (False, errore)
            return risultati
        _, _, indice2 = _get(porta, "/")
        v2 = re.search(r"/app\.js\?v=(\d+)", indice2.decode("utf-8", "replace"))
        v2 = v2.group(1) if v2 else "?"
        p.valuta("window.__preReload = true")
        p.cdp("Page.reload", {"ignoreCache": False})
        p.attendi(_JS_PAGINA, lambda v: v.get("preReload") != "boolean")
        nuova = p.attendi(_JS_PAGINA, lambda v: v.get("marcatore") == 2 and v.get("card", 0) > 0, timeout=15)
        risultati[_CONTROLLI_DINAMICI[8]] = (
            nuova.get("marcatore") == 2 and f"?v={v2}" in str(nuova.get("scriptApp"))
            and nuova.get("controllato") is True,
            f"v2={v2} {repr(nuova)[:220]}")

        sw2 = p.attendi(_JS_SW, lambda v: v.get("attesa") == "installed", timeout=20)
        cache2 = p.valuta(_JS_CACHE, True)
        nomi2 = sorted(cache2) if isinstance(cache2, dict) else []
        risultati[_CONTROLLI_DINAMICI[9]] = (
            sw2.get("attesa") == "installed" and sw2.get("attivo") == "activated"
            and sw2.get("controller") == "activated" and len(nomi2) == 2,
            f"{repr(sw2)} cache={nomi2}")

        _ferma(server)
        server = None
        p.valuta("window.__preReload = true")
        p.cdp("Page.reload", {"ignoreCache": True})
        p.attendi(_JS_PAGINA, lambda v: v.get("preReload") != "boolean")
        offline2 = p.attendi(_JS_PAGINA, lambda v: v.get("marcatore") == 2 and v.get("card", 0) > 0, timeout=15)
        risultati[_CONTROLLI_DINAMICI[10]] = (
            offline2.get("marcatore") == 2 and f"?v={v2}" in str(offline2.get("scriptApp"))
            and offline2.get("card", 0) > 0, repr(offline2)[:300])

        # 5) chiusa la pagina non resta nessun cliente del worker vecchio:
        # quello nuovo si attiva e cancella la sua cache. Si riapre offline.
        p.chiudi()
        pagine.remove(p)
        time.sleep(1.0)
        q = _Pagina(porta_cdp)
        pagine.append(q)
        q.cdp("Page.navigate", {"url": url_vista})
        q.attendi(_JS_PAGINA, lambda v: v.get("view") and v.get("card", 0) > 0, timeout=15)
        cache3 = q.attendi(_JS_CACHE, lambda v: isinstance(v, dict) and len(v) == 1, timeout=20)
        nomi3 = sorted(cache3) if isinstance(cache3, dict) else []
        risultati[_CONTROLLI_DINAMICI[11]] = (
            len(nomi3) == 1 and nomi3[0].endswith("-" + v2), f"v2={v2} cache={nomi3}")
        q.valuta("window.__preReload = true")
        q.cdp("Page.reload", {"ignoreCache": True})
        q.attendi(_JS_PAGINA, lambda v: v.get("preReload") != "boolean")
        offline3 = q.attendi(_JS_PAGINA, lambda v: v.get("marcatore") == 2 and v.get("card", 0) > 0, timeout=15)
        risultati[_CONTROLLI_DINAMICI[12]] = (
            offline3.get("marcatore") == 2 and offline3.get("card", 0) > 0
            and offline3.get("controllato") is True, repr(offline3)[:300])
    finally:
        for pagina in pagine:
            pagina.chiudi()
        if chrome_proc:
            chrome_proc.kill()
            chrome_proc.wait(timeout=10)
        _ferma(server)
        toccati = [os.path.basename(s) for s in segnali if os.path.exists(s)]
        shutil.rmtree(casa, ignore_errors=True)
        if toccati:
            risultati["_segnali"] = ", ".join(toccati)
    return risultati


def _prova_server_e_chrome(prova, radice):
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    con_chrome = os.path.exists(chrome)
    try:
        risultati = _dinamica(radice, chrome if con_chrome else None)
    except Exception as errore:  # noqa: BLE001 - il conteggio non deve cambiare mai
        risultati = {"_eccezione": f"{type(errore).__name__}: {errore}"}
    eccezione = risultati.pop("_eccezione", None)
    segnali = risultati.pop("_segnali", None)
    for nome in _CONTROLLI_HTTP:
        ok, dettaglio = risultati.get(nome, (False, eccezione or "non raggiunta"))
        prova(nome, ok, dettaglio)
    for nome in _CONTROLLI_DINAMICI:
        if not con_chrome:
            prova(f"{nome} (Chrome assente: non verificata)", True,
                  "installa Chrome per verificare davvero")
            continue
        ok, dettaglio = risultati.get(
            nome, (False, eccezione or "non raggiunta: una fase precedente ha interrotto la sequenza"))
        prova(nome, ok, dettaglio)
    prova("la prova non ha lanciato nessun launchctl/claude/codex/osascript vero (finti sul PATH)",
          not segnali, str(segnali))


def esegui(prova, radice):
    _prova_manifest(prova, radice)
    _prova_index(prova, radice)
    _prova_sw(prova, radice)
    _prova_registrazione(prova, radice)
    _prova_README_ed_export(prova, radice)
    try:
        _prova_server_e_chrome(prova, radice)
    except Exception as errore:  # noqa: BLE001
        prova("appweb (server e Chrome): completato senza eccezioni", False,
              f"{type(errore).__name__}: {errore}")


if __name__ == "__main__":
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    falliti = []
    passati = 0

    def _prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print(f"  ok   {nome}")
        else:
            falliti.append(nome)
            print(f"  NO   {nome} {dettaglio}")

    esegui(_prova, RADICE)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
