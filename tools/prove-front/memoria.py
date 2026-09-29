"""Prove per LOTTO-L4-MEMORIA, lato front: statiche sul sorgente (niente
browser: quello lo fa `tools/prova-video.sh`) più una dinamica, con Chrome
headless via CDP. Il numero di prove dinamiche è FISSO (vedi
_CONTROLLI_DINAMICI): se manca Chrome o una porta libera sopra 9560 ogni
prova di quell'elenco si segna comunque, verde, con "(Chrome assente: non
verificata)" - mai saltata, perché il conteggio deve essere lo stesso su ogni
macchina (README.md/README.it.md dichiarano un solo numero, il pre-push lo
confronta: la regola è la stessa già in tools/prova.py per node assente).

Quello che si controlla (vedi LOTTO-L4-MEMORIA.md, "Prove rosse senza", e le
correzioni obbligatorie del critico sul lotto):
- la chiave di memoria (`plancia-memoria-v1`) con versione e tetto in byte;
- route() non scrive più "carico…" quando c'è memoria della vista (si legge
  il ramo if(memoria)/else nel sorgente, non un numero di riga: un domani
  che cambia la forma di route() rende NO questa prova con un motivo, non un
  falso verde);
- le quattro chiavi T() it/en della spia;
- web/moto.css esiste, ha le sue @keyframes e il suo
  @media (prefers-reduced-motion: reduce), non usa opacity dentro le
  keyframes né backdrop-filter né --surface (colori di superficie e vetro
  sono di L4-VETRO, in web/style.css, non di questo lotto);
- web/index.html collega /moto.css con lo stesso `?v=` di style.css;
- le card/righe che il vortice deve seguire portano data-chiave;
- l'addendum del coordinatore (26/09): applyTheme avvisa il nativo
  (`window.webkit?.messageHandlers?.tema?.postMessage`), protetto da `?.`;
- dinamica: la memoria di /#progetti sopravvive a un server spento (rosso
  sul commit base: senza la memoria, a server spento la vista era
  "errore: …");
- dinamica (banchi su vortice() vero, correzioni del critico): la transizione
  di .card viene neutralizzata mentre si scrive la posizione di partenza (e
  riattivata solo al rAF successivo), un figlio [data-chiave] non riceve un
  transform proprio quando il suo antenato [data-chiave] si sposta, e un
  elemento con rect nullo (un [hidden] che diventa visibile) entra con
  .vortice-entra invece di volare da (0,0);
- dinamica: la spia usa l'ora dei dati (state.overviewQuando), non l'ora del
  disegno, quando la vista riusa la cassa senza fare una nuova richiesta;
- dinamica: un click su una card a server spento mostra il toast d'errore e
  non fa sparire le card.

Funzione pubblica `esegui(prova, RADICE)`, stessa forma di
tools/prove-front/riprendi.py (vedi tools/prove-front/README.md).
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
    return (radice.joinpath(*parti)).read_text(encoding="utf-8")


# ------------------------------------------------------------------ statiche

def _prova_memoria_chiave(prova, sorgente):
    prova("app.js dichiara la chiave versionata 'plancia-memoria-v1'",
          "plancia-memoria-v1" in sorgente)
    prova("app.js dichiara un tetto in byte per la voce di memoria (400 * 1024)",
          bool(re.search(r"400\s*\*\s*1024", sorgente)))
    prova("esiste una funzione per leggere la memoria e una per salvarla",
          "function memoriaSalva" in sorgente and "function memoriaLeggi" in sorgente)
    prova("la vista 'cerca' con una query non si salva",
          bool(re.search(r"vista\s*===\s*'cerca'[^\n]*\.q", sorgente)))


def _prova_route_niente_carico_con_memoria(prova, sorgente):
    m = re.search(r"async function route\(\)\s*{", sorgente)
    prova("route() esiste in app.js", bool(m))
    if not m:
        return
    # Il corpo di route(): dall'apertura di route() alla chiusura di livello
    # 0 della sua funzione (si contano le parentesi graffe, non un numero di
    # riga fisso: la nota in cima al lotto chiede di cercare il testo).
    inizio = m.end() - 1  # la '{' di apertura
    profondita = 0
    fine = None
    for i, c in enumerate(sorgente[inizio:], start=inizio):
        if c == "{":
            profondita += 1
        elif c == "}":
            profondita -= 1
            if profondita == 0:
                fine = i + 1
                break
    prova("route() ha una chiusura leggibile (graffe bilanciate)", fine is not None)
    if fine is None:
        return
    corpo = sorgente[inizio:fine]

    m_if = re.search(r"if\s*\(memoria\)\s*{(.*?)}\s*else\s*{(.*?)}", corpo, re.S)
    prova("route() ha un ramo 'if (memoria)' prima del fetch, con un else", bool(m_if))
    if not m_if:
        return
    ramo_memoria, ramo_altrimenti = m_if.group(1), m_if.group(2)
    prova("il ramo SENZA memoria (prima apertura) scrive ancora 'carico…'",
          "carico" in ramo_altrimenti)
    prova("il ramo CON memoria non scrive 'carico…' (la vista non è mai vuota)",
          "carico" not in ramo_memoria)
    prova("il ramo con memoria marca #view con data-memoria",
          "dataset.memoria" in ramo_memoria)

    # Il resto di route() (dopo il ramo qui sopra): il fetch che segue deve
    # poter fallire senza scrivere "errore: " quando c'era memoria - si
    # guarda il resto del corpo, non il ramo di apertura.
    resto = corpo[m_if.end():]
    m_catch = re.search(r"catch\s*\([^)]*\)\s*{(.*?)}\s*$", resto, re.S)
    prova("route() ha un catch dopo il fetch", bool(m_catch))
    if m_catch:
        corpo_catch = m_catch.group(1)
        m_if2 = re.search(r"if\s*\(memoria\)\s*{(.*?)}\s*else\s*{(.*?)}", corpo_catch, re.S)
        prova("nel catch, il ramo CON memoria non scrive 'errore: ' al posto della vista",
              bool(m_if2) and "T('errore" not in m_if2.group(1))
        prova("nel catch, il ramo SENZA memoria scrive ancora 'errore: ' (comportamento di prima)",
              bool(m_if2) and "T('errore" in m_if2.group(2))


def _prova_spia_testi(prova, sorgente):
    for chiave in ("spia_titolo", "spia_aggiornato", "spia_memoria", "spia_aggiorno"):
        prova(f"la chiave della spia '{chiave}' esiste in EN", f"'{chiave}':" in sorgente)
    # IT_TESTI: stesse chiavi, un'occorrenza in più di quella già contata in EN
    # (le chiavi 'spia_*' non compaiono da nessun'altra parte nel file).
    for chiave in ("spia_titolo", "spia_aggiornato", "spia_memoria", "spia_aggiorno"):
        prova(f"la chiave della spia '{chiave}' esiste anche in IT_TESTI (due occorrenze totali)",
              sorgente.count(f"'{chiave}':") >= 2)


def _blocchi_keyframes(css):
    """Ogni @keyframes per intero, corpo compreso: una @media che contenga
    'opacity' fuori da una keyframe (il caso di reduced-motion, che spegne
    l'animazione, non la disegna) non deve far scattare il divieto."""
    blocchi = []
    for m in re.finditer(r"@keyframes[^{]*\{", css):
        profondita = 0
        inizio = m.end() - 1
        for i, c in enumerate(css[inizio:], start=inizio):
            if c == "{":
                profondita += 1
            elif c == "}":
                profondita -= 1
                if profondita == 0:
                    blocchi.append(css[inizio:i + 1])
                    break
    return blocchi


def _prova_moto_css(prova, radice):
    percorso = radice / "web" / "moto.css"
    prova("web/moto.css esiste", percorso.exists())
    if not percorso.exists():
        return
    moto = percorso.read_text(encoding="utf-8")
    prova("moto.css contiene @keyframes per il vortice", "@keyframes vortice" in moto)
    prova("moto.css ha un @media (prefers-reduced-motion: reduce)",
          "prefers-reduced-motion: reduce" in moto)
    blocchi = _blocchi_keyframes(moto)
    prova("moto.css ha almeno una @keyframes da controllare", bool(blocchi))
    prova("nessuna @keyframes del vortice usa opacity (solo transform, mai opacity)",
          not any("opacity" in b for b in blocchi))
    prova("moto.css non usa backdrop-filter (niente vetro: è di L4-VETRO)",
          "backdrop-filter" not in moto)
    prova("moto.css non fa riferimento a --surface (niente colori di superficie)",
          "--surface" not in moto)


def _prova_index_link_moto(prova, radice):
    indice = _leggi(radice, "web", "index.html")
    prova('index.html collega /moto.css?v=__PLANCIA_V__ (stessa forma di style.css)',
          '<link rel="stylesheet" href="/moto.css?v=__PLANCIA_V__">' in indice)


def _prova_data_chiave(prova, sorgente):
    prova("projectCard (griglia e figli nell'albero) porta data-chiave",
          'data-chiave="${esc(p.key)}"' in sorgente)
    prova("alberoPadre (la card del padre nell'albero) porta data-chiave",
          'data-chiave="${esc(padre.key)}"' in sorgente)
    prova("rigaProssimo (le righe del pannello Prossimi) porta data-chiave",
          "data-chiave=\"${esc(areaKey)}:${esc(r.key)}\"" in sorgente)
    prova("la card del kanban (views.social) porta data-chiave",
          'class="kcard" data-chiave="${p.id}"' in sorgente)


def _prova_addendum_tema(prova, sorgente):
    m = re.search(r"function applyTheme\(mode\)\s*{", sorgente)
    prova("applyTheme(mode) esiste in app.js", bool(m))
    if not m:
        return
    inizio = m.end() - 1
    profondita = 0
    fine = None
    for i, c in enumerate(sorgente[inizio:], start=inizio):
        if c == "{":
            profondita += 1
        elif c == "}":
            profondita -= 1
            if profondita == 0:
                fine = i + 1
                break
    corpo = sorgente[inizio:fine] if fine else ""
    prova("applyTheme avvisa il nativo con window.webkit?.messageHandlers?.tema?.postMessage",
          "window.webkit?.messageHandlers?.tema?.postMessage(resolved)" in corpo)
    prova("la chiamata è protetta da ?. su ogni passo (webkit, messageHandlers, tema)",
          bool(re.search(r"window\.webkit\?\.\s*messageHandlers\?\.\s*tema\?\.\s*postMessage",
                          corpo)))


# ------------------------------------------------------------------ dinamica

def _porta_libera(partenza):
    porta = partenza
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
        porta += 1


def _ws_connect(url, timeout=10):
    assert url.startswith("ws://"), url
    hostport, path = url[len("ws://"):].split("/", 1)
    path = "/" + path
    host, _, porta = hostport.partition(":")
    porta = int(porta) if porta else 80
    sock = socket.create_connection((host, porta), timeout=timeout)
    chiave = base64.b64encode(os.urandom(16)).decode()
    richiesta = (
        f"GET {path} HTTP/1.1\r\nHost: {host}:{porta}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {chiave}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(richiesta.encode())
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
    intestazione = bytearray([0x81])
    lunghezza = len(payload)
    if lunghezza < 126:
        intestazione.append(0x80 | lunghezza)
    elif lunghezza < (1 << 16):
        intestazione.append(0x80 | 126)
        intestazione += struct.pack(">H", lunghezza)
    else:
        intestazione.append(0x80 | 127)
        intestazione += struct.pack(">Q", lunghezza)
    maschera = os.urandom(4)
    intestazione += maschera
    mascherato = bytes(b ^ maschera[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(intestazione) + mascherato)


def _recv_esatti(sock, n):
    buf = b""
    while len(buf) < n:
        pezzo = sock.recv(n - len(buf))
        if not pezzo:
            raise ConnectionError("il socket websocket si è chiuso")
        buf += pezzo
    return buf


def _ws_recv(sock):
    b0, b1 = _recv_esatti(sock, 2)
    opcode = b0 & 0x0F
    mascherato = bool(b1 & 0x80)
    lunghezza = b1 & 0x7F
    if lunghezza == 126:
        lunghezza = struct.unpack(">H", _recv_esatti(sock, 2))[0]
    elif lunghezza == 127:
        lunghezza = struct.unpack(">Q", _recv_esatti(sock, 8))[0]
    maschera = _recv_esatti(sock, 4) if mascherato else None
    payload = _recv_esatti(sock, lunghezza) if lunghezza else b""
    if maschera:
        payload = bytes(b ^ maschera[i % 4] for i, b in enumerate(payload))
    if opcode == 0x8:
        raise ConnectionError("il target ha chiuso la connessione CDP")
    return payload.decode("utf-8", "replace")


def _cdp(sock, id_, metodo, parametri=None, timeout=15):
    """Una chiamata CDP sincrona: manda, e scarta ogni messaggio (eventi
    compresi) finché non arriva la risposta con lo stesso id."""
    _ws_send(sock, json.dumps({"id": id_, "method": metodo, "params": parametri or {}}))
    scadenza = time.time() + timeout
    while time.time() < scadenza:
        try:
            msg = json.loads(_ws_recv(sock))
        except (ConnectionError, socket.timeout):
            raise
        if msg.get("id") == id_:
            return msg
    raise TimeoutError(f"CDP {metodo} senza risposta entro {timeout}s")


def _valuta(sock, id_, espressione, await_promise=False):
    r = _cdp(sock, id_, "Runtime.evaluate",
             {"expression": espressione, "returnByValue": True, "awaitPromise": await_promise})
    risultato = (r.get("result") or {}).get("result") or {}
    if "value" in risultato:
        return risultato["value"]
    if risultato.get("subtype") == "null" or risultato.get("type") == "undefined":
        return None
    return risultato


def _apri_pagina_cdp(porta_cdp):
    # about:blank, non l'indirizzo vero: un '#' nell'indirizzo vero (ogni
    # vista di Plancia ne ha uno, #/progetti) verrebbe letto come il
    # fragment di QUESTA richiesta HTTP e sparirebbe prima di raggiungere
    # Chrome. L'indirizzo vero si carica dopo, con Page.navigate via CDP
    # (i parametri lì sono JSON, non una query string: nessun problema).
    richiesta = urllib.request.Request(
        f"http://127.0.0.1:{porta_cdp}/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(richiesta, timeout=10) as r:
        info = json.load(r)
    return _ws_connect(info["webSocketDebuggerUrl"])


# Elenco FISSO dei controlli dinamici, nell'ordine in cui li produce
# _dinamica_vera(). Il numero di prove eseguite deve essere lo stesso su ogni
# macchina (regola della casa, tools/prova.py:674-680, il caso di node):
# senza Chrome (il collaudo CI gira su ubuntu-latest, dove
# /Applications/Google Chrome.app non esiste) o senza una porta libera, ogni
# nome qui sotto viene emesso comunque, verde, con "(Chrome assente: non
# verificata)" - mai saltato, mai contato in un numero diverso. Con Chrome,
# se una fase a monte fallisce (il server non parte, Chrome non risponde...)
# i controlli successivi che non sono stati raggiunti si segnano NO con
# quel motivo, non spariscono: il totale resta lo stesso identico elenco.
_CONTROLLI_DINAMICI = [
    "dinamica: Chrome headless risponde su /json/version",
    "dinamica: dopo aprire #/progetti, la memoria della vista esiste in "
    "localStorage ed è html vero (contiene data-chiave)",
    "dinamica (banco vortice): l'elemento spostato parte SUBITO dalla "
    "posizione vecchia (transform inverso, transition:none) - non da un "
    "salto immediato alla posizione nuova",
    "dinamica (banco vortice): al rAF successivo l'animazione parte per "
    "davvero (transform tornato vuoto, transizione di 420ms, .vortice-muove)",
    "dinamica (banco vortice, annidati): un figlio [data-chiave] dentro un "
    "padre [data-chiave] che si sposta NON riceve un transform proprio (lo "
    "porta il padre, altrimenti raddoppierebbe lo spostamento)",
    "dinamica (banco vortice, rect nulli): una riga che passa da [hidden] a "
    "visibile entra con .vortice-entra, non un transform dall'angolo (0,0)",
    "dinamica: la spia usa l'ora dei DATI (state.overviewQuando) quando "
    "la vista non ha fatto nessuna richiesta di rete, non l'ora del disegno",
    "dinamica: a server spento, #view NON è tornato a 'carico…'",
    "dinamica: a server spento, #view NON mostra 'errore: '",
    "dinamica: a server spento, #view mostra ancora le card (memoria intatta)",
    "dinamica: la spia dice che il server non è raggiungibile",
    "dinamica: #view porta ancora data-memoria (resta la vista di memoria, non fresca)",
    "dinamica: a server spento, un click su una card mostra il toast d'errore "
    "(classe bad) e NON fa sparire le card da #view",
    "dinamica: un F5 vero col server spento mostra #view (era il limite noto: "
    "la shell ora la tiene il service worker di U1-APPWEB, web/sw.js)",
    "dinamica: nessun claude/codex vero è partito per colpa di questa prova "
    "(script finti nel PATH, nessun segnale scritto)",
]

# I tre banchi di prova (bug del critico su vortice()) sono script JS a se
# stanti: creano un contenitore fuori dal flusso normale della pagina,
# scrivono l'html "vecchio", chiamano la funzione vortice() VERA (quella
# caricata dalla pagina, con web/moto.css e web/style.css veri) e leggono lo
# stato subito dopo. Deterministici: non dipendono dal server, dal DB demo
# né dal timing dell'animazione - solo dal comportamento di vortice() stesso.
_BANCO_TRANSIZIONE_JS = """(function(){
  var host = document.createElement('div');
  document.body.appendChild(host);
  host.innerHTML = '<div class="card" data-chiave="__banco_b1">uno</div>'
    + '<div class="card" data-chiave="__banco_b2">due</div>';
  void host.offsetHeight;
  var htmlNuovo = '<div class="card" data-chiave="__banco_b2">due</div>'
    + '<div class="card" data-chiave="__banco_b1">uno</div>';
  vortice(host, htmlNuovo);
  var b1 = host.querySelector('[data-chiave="__banco_b1"]');
  var subito = {transform: b1.style.transform, transition: b1.style.transition,
                classe: b1.className};
  var risultato = {subito: subito};
  window.__bancoHost = host; window.__bancoB1 = b1;
  return risultato;
})()"""

_BANCO_TRANSIZIONE_DOPO_RAF_JS = """(function(){
  return new Promise(function(resolve){
    requestAnimationFrame(function(){
      requestAnimationFrame(function(){
        var b1 = window.__bancoB1;
        var dopo = {transform: b1.style.transform, transition: b1.style.transition,
                    classe: b1.className};
        window.__bancoHost.remove();
        delete window.__bancoHost; delete window.__bancoB1;
        resolve(dopo);
      });
    });
  });
})()"""

_BANCO_ANNIDATI_JS = """(function(){
  var host = document.createElement('div');
  document.body.appendChild(host);
  host.innerHTML =
    '<div class="albero-padre card" data-chiave="__banco_p1">'
      + '<div class="albero-figlio card" data-chiave="__banco_f1">figlio</div>'
    + '</div>'
    + '<div class="albero-padre card" data-chiave="__banco_p2">altro</div>';
  void host.offsetHeight;
  var htmlNuovo =
    '<div class="albero-padre card" data-chiave="__banco_p2">altro</div>'
    + '<div class="albero-padre card" data-chiave="__banco_p1">'
      + '<div class="albero-figlio card" data-chiave="__banco_f1">figlio</div>'
    + '</div>';
  vortice(host, htmlNuovo);
  var padre = host.querySelector('[data-chiave="__banco_p1"]');
  var figlio = host.querySelector('[data-chiave="__banco_f1"]');
  var out = {padreTransform: padre.style.transform, figlioTransform: figlio.style.transform};
  host.remove();
  return out;
})()"""

_BANCO_RECT_NULLO_JS = """(function(){
  var host = document.createElement('div');
  document.body.appendChild(host);
  host.innerHTML = '<div class="prossimi-riga" data-chiave="__banco_r0">visibile</div>'
    + '<div class="prossimi-riga" data-chiave="__banco_r1" hidden>nascosta</div>';
  void host.offsetHeight;
  var htmlNuovo = '<div class="prossimi-riga" data-chiave="__banco_r0">visibile</div>'
    + '<div class="prossimi-riga" data-chiave="__banco_r1">ora visibile</div>';
  vortice(host, htmlNuovo);
  var riga = host.querySelector('[data-chiave="__banco_r1"]');
  var out = {classe: riga.className, transform: riga.style.transform};
  host.remove();
  return out;
})()"""


def _dinamica_vera(radice, chrome):
    """Fa girare per davvero tutta la dinamica e torna un dict
    {nome_prova: (ok, dettaglio)}. Chi chiama pesca da qui con il nome
    esatto in _CONTROLLI_DINAMICI: quello che manca (una fase a monte non
    raggiunta) diventa NO con un motivo, mai un buco nel conteggio."""
    risultati = {}
    casa = tempfile.mkdtemp(prefix="plancia-prova-memoria-")
    claude_cfg = os.path.join(casa, "claude-config")
    codex_home = os.path.join(casa, "codex-home")
    profilo_chrome = os.path.join(casa, "chrome-profile")
    agenti_json = os.path.join(casa, "agenti-vuoti.json")
    terminale_finto = os.path.join(casa, "terminale-finto.sh")
    clipboard_finto = os.path.join(casa, "clipboard-finto.sh")
    bin_finti = os.path.join(casa, "bin-finti")
    for cartella in (claude_cfg, codex_home, profilo_chrome, bin_finti):
        os.makedirs(cartella, exist_ok=True)
    with open(agenti_json, "w", encoding="utf-8") as f:
        f.write("[]")
    for finto in (terminale_finto, clipboard_finto):
        with open(finto, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(finto, 0o755)

    # Sostituto del pgrep globale (correzione del critico): un pgrep -x
    # claude/codex guarda TUTTI i processi della macchina, e su quella di
    # Eugenio girano sessioni claude vere in parallelo a questa prova - una
    # che parte o finisce nei ~15s della dinamica fa sembrare rosso un
    # pre-push senza che questa prova abbia fatto niente di male. Al posto
    # del pgrep: due eseguibili finti chiamati proprio "claude" e "codex",
    # messi in testa al PATH del server di prova. Se QUALCOSA nel codice che
    # gira sotto questa prova provasse a lanciare l'agente vero, troverebbe
    # questi al posto del vero claude/codex sul PATH ed eseguirebbe questi -
    # che si limitano a scrivere un file-segnale e uscire. Il controllo
    # finale guarda se quei due file esistono, non l'elenco dei processi di
    # tutta la macchina.
    segnale_claude = os.path.join(casa, "segnale-claude")
    segnale_codex = os.path.join(casa, "segnale-codex")
    for nome, segnale in (("claude", segnale_claude), ("codex", segnale_codex)):
        percorso = os.path.join(bin_finti, nome)
        with open(percorso, "w", encoding="utf-8") as f:
            f.write(f"#!/bin/sh\ntouch {shlex.quote(segnale)}\nexit 0\n")
        os.chmod(percorso, 0o755)

    ambiente = dict(os.environ)
    ambiente.update({
        "PLANCIA_HOME": casa,
        "CLAUDE_CONFIG_DIR": claude_cfg,
        "CODEX_HOME": codex_home,
        "PLANCIA_AGENTS_JSON": agenti_json,
        "PLANCIA_TERMINALE": terminale_finto,
        "PLANCIA_CLIPBOARD": clipboard_finto,
        "PATH": bin_finti + os.pathsep + ambiente.get("PATH", ""),
        "PYTHONPATH": str(radice) + (os.pathsep + ambiente["PYTHONPATH"]
                                      if ambiente.get("PYTHONPATH") else ""),
    })

    server = None
    chrome_proc = None
    sock = None
    try:
        subprocess.run([sys.executable, str(radice / "tools" / "demo-data.py")],
                        env=ambiente, check=True, capture_output=True, text=True)

        porta_http = _porta_libera(int(os.environ.get("PLANCIA_MEMORIA_PORT", 7873)))
        server = subprocess.Popen(
            [sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta_http), "--no-sync"],
            env=ambiente, cwd=str(radice),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        attivo = False
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{porta_http}/", timeout=1)
                attivo = True
                break
            except Exception:
                time.sleep(0.25)
        if not attivo:
            uscita = server.stdout.read() if server.stdout else ""
            risultati["dinamica: Chrome headless risponde su /json/version"] = (
                False, "il server di prova non è partito: " + uscita[-300:])
            return risultati

        porta_cdp = _porta_libera(int(os.environ.get("PLANCIA_MEMORIA_CDP_PORT", 9561)))
        chrome_proc = subprocess.Popen([
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--no-default-browser-check",
            f"--remote-debugging-port={porta_cdp}", f"--user-data-dir={profilo_chrome}",
            "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        cdp_pronto = False
        for _ in range(30):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{porta_cdp}/json/version", timeout=1)
                cdp_pronto = True
                break
            except Exception:
                time.sleep(0.25)
        risultati["dinamica: Chrome headless risponde su /json/version"] = (cdp_pronto, "")
        if not cdp_pronto:
            return risultati

        url_vista = f"http://127.0.0.1:{porta_http}/?ui=it#/progetti"
        sock = _apri_pagina_cdp(porta_cdp)
        _cdp(sock, 1, "Page.navigate", {"url": url_vista})
        time.sleep(1.0)  # il primo giro (fetch vero, non da memoria) impiega un pelo di più

        chiave_memoria = None
        for _ in range(40):
            try:
                chiave_memoria = _valuta(
                    sock, 1,
                    "(function(){try{"
                    "var k=Object.keys(localStorage).find("
                    "function(x){return x.indexOf('plancia-memoria')===0 "
                    "&& x.indexOf(':progetti:')>=0;});"
                    "return k?localStorage.getItem(k):null;"
                    "}catch(e){return 'ERRORE:'+e;}})()")
            except (ConnectionError, TimeoutError):
                chiave_memoria = None
            if chiave_memoria and "data-chiave" in chiave_memoria:
                break
            time.sleep(0.3)

        html_memoria = ""
        if chiave_memoria:
            try:
                html_memoria = json.loads(chiave_memoria).get("html", "")
            except (json.JSONDecodeError, AttributeError):
                html_memoria = ""
        risultati["dinamica: dopo aprire #/progetti, la memoria della vista esiste in "
                  "localStorage ed è html vero (contiene data-chiave)"] = (
            "data-chiave" in html_memoria, str(chiave_memoria)[:160])

        # I tre banchi (correzioni del critico su vortice()): non dipendono
        # dal server né dai dati demo, solo dalla pagina già caricata (con
        # web/moto.css e web/style.css veri).
        try:
            banco1 = _valuta(sock, 20, _BANCO_TRANSIZIONE_JS)
            subito = (banco1 or {}).get("subito") or {}
            risultati["dinamica (banco vortice): l'elemento spostato parte SUBITO dalla "
                      "posizione vecchia (transform inverso, transition:none) - non da un "
                      "salto immediato alla posizione nuova"] = (
                bool(subito.get("transform")) and subito.get("transition") == "none",
                repr(subito))

            banco1_dopo = _valuta(sock, 21, _BANCO_TRANSIZIONE_DOPO_RAF_JS, await_promise=True)
            banco1_dopo = banco1_dopo or {}
            risultati["dinamica (banco vortice): al rAF successivo l'animazione parte per "
                      "davvero (transform tornato vuoto, transizione di 420ms, "
                      ".vortice-muove)"] = (
                banco1_dopo.get("transform") == ""
                and "420ms" in (banco1_dopo.get("transition") or "")
                and "vortice-muove" in (banco1_dopo.get("classe") or ""),
                repr(banco1_dopo))
        except (ConnectionError, TimeoutError) as errore:
            dettaglio = f"{type(errore).__name__}: {errore}"
            risultati.setdefault("dinamica (banco vortice): l'elemento spostato parte SUBITO dalla "
                                  "posizione vecchia (transform inverso, transition:none) - non da un "
                                  "salto immediato alla posizione nuova", (False, dettaglio))
            risultati.setdefault("dinamica (banco vortice): al rAF successivo l'animazione parte per "
                                  "davvero (transform tornato vuoto, transizione di 420ms, "
                                  ".vortice-muove)", (False, dettaglio))

        try:
            banco2 = _valuta(sock, 22, _BANCO_ANNIDATI_JS) or {}
            risultati["dinamica (banco vortice, annidati): un figlio [data-chiave] dentro un "
                      "padre [data-chiave] che si sposta NON riceve un transform proprio (lo "
                      "porta il padre, altrimenti raddoppierebbe lo spostamento)"] = (
                bool(banco2.get("padreTransform")) and banco2.get("figlioTransform") == "",
                repr(banco2))
        except (ConnectionError, TimeoutError) as errore:
            risultati["dinamica (banco vortice, annidati): un figlio [data-chiave] dentro un "
                      "padre [data-chiave] che si sposta NON riceve un transform proprio (lo "
                      "porta il padre, altrimenti raddoppierebbe lo spostamento)"] = (
                False, f"{type(errore).__name__}: {errore}")

        try:
            banco3 = _valuta(sock, 23, _BANCO_RECT_NULLO_JS) or {}
            risultati["dinamica (banco vortice, rect nulli): una riga che passa da [hidden] a "
                      "visibile entra con .vortice-entra, non un transform dall'angolo (0,0)"] = (
                "vortice-entra" in (banco3.get("classe") or "") and banco3.get("transform") == "",
                repr(banco3))
        except (ConnectionError, TimeoutError) as errore:
            risultati["dinamica (banco vortice, rect nulli): una riga che passa da [hidden] a "
                      "visibile entra con .vortice-entra, non un transform dall'angolo (0,0)"] = (
                False, f"{type(errore).__name__}: {errore}")

        # L'ora si formatta con LOC(), la stessa lingua dell'interfaccia che
        # scrive la spia (oraCorta in app.js), non con la lingua del browser: su
        # un runner con il formato a 12 ore `undefined` da "07:40 AM" mentre la
        # pagina scrive "07:40", e la prova confrontava due formati diversi.
        # La spia (punto 4, correzione del critico): con il server ANCORA
        # vivo e state.overview già in cassa (il giro sopra l'ha popolata),
        # si forza state.overviewQuando nel passato e si richiama route()
        # senza toccare state.overview - niente fetch parte (la vista lo
        # riusa dalla cassa), quindi la pillola deve dire l'ora FORZATA, non
        # "adesso". Sul commit senza la correzione, route() chiamava sempre
        # spiaAggiorna('fresco') senza un secondo argomento: oraCorta(undefined)
        # torna sempre new Date(), quindi questa prova è rossa lì per
        # costruzione, non per un caso limite di timing.
        try:
            r = _valuta(sock, 24, """(async function(){
              if (!state.overview) return {saltato:true};
              var passato = new Date(Date.now() - 5*60000);
              state.overviewQuando = passato;
              var atteso = passato.toLocaleTimeString(LOC(),{hour:'2-digit',minute:'2-digit'});
              var adesso = new Date().toLocaleTimeString(LOC(),{hour:'2-digit',minute:'2-digit'});
              await route();
              var s = document.getElementById('spia-memoria');
              return {saltato:false, testo: s?s.textContent:null, atteso: atteso, adesso: adesso};
            })()""", await_promise=True) or {}
            ok = (not r.get("saltato")) and r.get("atteso") and r.get("atteso") in (r.get("testo") or "") \
                and (r.get("adesso") not in (r.get("testo") or "") or r.get("adesso") == r.get("atteso"))
            risultati["dinamica: la spia usa l'ora dei DATI (state.overviewQuando) quando "
                      "la vista non ha fatto nessuna richiesta di rete, non l'ora del disegno"] = (
                bool(ok), repr(r))
        except (ConnectionError, TimeoutError) as errore:
            risultati["dinamica: la spia usa l'ora dei DATI (state.overviewQuando) quando "
                      "la vista non ha fatto nessuna richiesta di rete, non l'ora del disegno"] = (
                False, f"{type(errore).__name__}: {errore}")

        # Il server si spegne (kill vero: SIGTERM sul processo di prova, mai
        # un claude/codex reale, che con gli eseguibili finti sul PATH non
        # potrebbe partire comunque - vedi il controllo finale più sotto).
        server.terminate()
        try:
            server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=8)
        server = None

        # state.overview = null prima di route(): views.progetti (come
        # views.oggi) riusa state.overview se c'è già, invece di rifare la
        # richiesta - esattamente quello che fa ogni azione vera dopo un
        # cambiamento (punto 5 del lotto: "state.overview = null; await
        # route()"). Senza azzerarlo qui, route() non richiamerebbe mai
        # l'API e la prova non testerebbe niente: sembrerebbe verde perché
        # non ha mai provato a controllare il server spento.
        _cdp(sock, 3, "Runtime.evaluate",
             {"expression": "state.overview = null, route()",
              "awaitPromise": True, "returnByValue": True})

        stato = _valuta(
            sock, 5,
            "(function(){var v=document.getElementById('view');"
            "var s=document.getElementById('spia-memoria');"
            "return {html:(v?v.innerHTML.slice(0,4000):''), "
            "memoria:(v?v.getAttribute('data-memoria'):null), "
            "spia:(s?s.textContent:null)};})()") or {}

        html_dopo = stato.get("html") or ""
        spia_dopo = stato.get("spia") or ""
        risultati["dinamica: a server spento, #view NON è tornato a 'carico…'"] = (
            not html_dopo.lower().startswith("carico") and "carico…" not in html_dopo[:80], "")
        risultati["dinamica: a server spento, #view NON mostra 'errore: '"] = (
            "errore:" not in html_dopo.lower(), "")
        risultati["dinamica: a server spento, #view mostra ancora le card (memoria intatta)"] = (
            "data-chiave" in html_dopo, html_dopo[:200])
        risultati["dinamica: la spia dice che il server non è raggiungibile"] = (
            "raggiungibile" in spia_dopo or "unreachable" in spia_dopo, repr(spia_dopo))
        risultati["dinamica: #view porta ancora data-memoria (resta la vista di memoria, non fresca)"] = (
            stato.get("memoria") == "1", "")

        # Correzione del critico (punto 2, "mai vuota"): un click su una card
        # mentre il server è spento deve mostrare il toast d'errore e basta -
        # non restare muto. openProject()/openMemory() sono async e prima
        # non avevano .catch: la promessa rifiutata (fetch fallito) non la
        # gestiva nessuno.
        try:
            click = _valuta(sock, 25, """(function(){
              var el = document.querySelector('#view [data-project]');
              if (!el) return {trovato:false};
              el.click();
              return {trovato:true};
            })()""") or {}
            time.sleep(0.4)
            dopo_click = _valuta(sock, 26, """(function(){
              var t = document.getElementById('toast');
              var v = document.getElementById('view');
              return {toastHidden: t?t.hidden:null, toastClasse: t?t.className:null,
                      viewHaCard: v ? !!v.querySelector('[data-project]') : false};
            })()""") or {}
            ok = click.get("trovato") and dopo_click.get("toastHidden") is False \
                and "bad" in (dopo_click.get("toastClasse") or "") and dopo_click.get("viewHaCard")
            risultati["dinamica: a server spento, un click su una card mostra il toast d'errore "
                      "(classe bad) e NON fa sparire le card da #view"] = (
                bool(ok), repr({"click": click, "dopo": dopo_click}))
        except (ConnectionError, TimeoutError) as errore:
            risultati["dinamica: a server spento, un click su una card mostra il toast d'errore "
                      "(classe bad) e NON fa sparire le card da #view"] = (
                False, f"{type(errore).__name__}: {errore}")

        # Un F5 vero (Page.reload) col server spento. Era il limite noto di
        # questo lotto: il document stesso non era in cache (Cache-Control:
        # no-store su ogni risposta), quindi il reload dava la pagina
        # d'errore del browser e questa prova affermava che #view NON c'era.
        # LOTTO-U1-APPWEB l'ha chiuso: web/sw.js tiene la shell, e la pagina
        # (registrata al primo caricamento, piu' di dieci secondi fa) si apre
        # anche a server spento. La prova ora afferma il contrario, e resta
        # nell'elenco fisso con lo stesso posto; il dettaglio del service
        # worker (versioni, cache, /api/ mai in cache) e' in prove-front/
        # appweb.py. window.__preReload esiste solo nel document corrente:
        # sparisce da solo quando ne arriva uno nuovo, e la sua assenza e'
        # come si vede che il reload e' successo.
        _valuta(sock, 6, "window.__preReload = true")
        _cdp(sock, 7, "Page.reload", {"ignoreCache": True})
        marcatore_sparito, vista_dopo_reload = False, None
        scadenza = time.time() + 10
        while time.time() < scadenza:
            try:
                marcatore = _valuta(sock, 8, "typeof window.__preReload")
            except (ConnectionError, TimeoutError):
                marcatore = "boolean"
            if marcatore != "boolean":
                marcatore_sparito = True
                for _ in range(20):
                    try:
                        vista_dopo_reload = _valuta(
                            sock, 9, "document.getElementById('view') ? 'presente' : null")
                    except (ConnectionError, TimeoutError):
                        vista_dopo_reload = None
                    if vista_dopo_reload == "presente":
                        break
                    time.sleep(0.3)
                break
            time.sleep(0.3)
        risultati["dinamica: un F5 vero col server spento mostra #view (era il limite noto: "
                  "la shell ora la tiene il service worker di U1-APPWEB, web/sw.js)"] = (
            marcatore_sparito and vista_dopo_reload == "presente", repr(vista_dopo_reload))
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass
        if chrome_proc:
            chrome_proc.kill()
            chrome_proc.wait(timeout=10)
        if server:
            server.kill()
            try:
                server.wait(timeout=10)
            except Exception:
                pass
        segnali_rimasti = [p for p in (segnale_claude, segnale_codex) if os.path.exists(p)]
        shutil.rmtree(casa, ignore_errors=True)
        risultati["dinamica: nessun claude/codex vero è partito per colpa di questa prova "
                  "(script finti nel PATH, nessun segnale scritto)"] = (
            not segnali_rimasti, repr(segnali_rimasti))

    return risultati


def _prova_dinamica(prova, radice):
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    porta_libera = False
    if os.path.exists(chrome):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                porta_libera = s.connect_ex(("127.0.0.1", 9561)) != 0
        except OSError:
            porta_libera = False

    if not os.path.exists(chrome) or not porta_libera:
        motivo = ("Google Chrome non è installato in questo percorso" if not os.path.exists(chrome)
                   else "nessuna porta libera sopra 9560 per il CDP")
        for nome in _CONTROLLI_DINAMICI:
            prova(f"{nome} (Chrome assente: non verificata)", True,
                  f"installa Chrome per verificare davvero: {motivo}")
        return

    try:
        risultati = _dinamica_vera(radice, chrome)
    except Exception as errore:  # non deve mai far perdere il conteggio fisso
        risultati = {}
        risultati["_eccezione"] = f"{type(errore).__name__}: {errore}"

    eccezione = risultati.pop("_eccezione", None)
    for nome in _CONTROLLI_DINAMICI:
        ok, dettaglio = risultati.get(
            nome, (False, eccezione or "non raggiunta: una fase precedente ha interrotto la sequenza"))
        prova(nome, ok, dettaglio)


def esegui(prova, radice):
    sorgente = _leggi(radice, "web", "app.js")

    _prova_memoria_chiave(prova, sorgente)
    _prova_route_niente_carico_con_memoria(prova, sorgente)
    _prova_spia_testi(prova, sorgente)
    _prova_moto_css(prova, radice)
    _prova_index_link_moto(prova, radice)
    _prova_data_chiave(prova, sorgente)
    _prova_addendum_tema(prova, sorgente)

    try:
        _prova_dinamica(prova, radice)
    except Exception as errore:  # la dinamica è "se riesci": non affossa le statiche
        prova("dinamica (CDP): completata senza eccezioni", False, f"{type(errore).__name__}: {errore}")


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
