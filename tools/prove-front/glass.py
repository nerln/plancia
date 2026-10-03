"""Prove del vetro e del disegno: le superfici della dashboard web (web/style.css,
web/index.html, web/app.js) e i sorgenti dell'app Mac (mac/Sources, SwiftUI dalla 2.0).

Statiche, si guarda solo il sorgente (niente browser, niente server). La
funzione pubblica e' `esegui(prova, radice)`, la stessa forma usata da
tools/prova-front.py (vedi tools/prove-front/README.md).

Storia. Fino alla 2.0 questo file misurava il "vetro" della dashboard (L4-VETRO,
18/09/2026: backdrop-filter e aloni su ogni superficie). L'utente il 29/09 lo ha
bocciato (riquadri appiccicati, fantasmi trasparenti sotto il contenuto) e ha
chiesto una dashboard che somigli alla 2.0 nativa; nella seconda passata (WEB) le
superfici sono piene e il vetro vero lo danno solo i controlli di sistema del Mac.
Le prove che imponevano il vetro sono state tolte perche' dicono il contrario di
quello che si vuole ora; al loro posto ci sono quelle che tengono ferma la
dashboard nuova: superfici piene, niente blur, temi in coppia, contrasti,
colonna di lettura, stato nel sottotitolo e da nessun'altra parte.
"""

import re

FOGLIO = "web/style.css"


def _rimuovi_commenti(testo):
    return re.sub(r"/\*.*?\*/", "", testo, flags=re.S)


def _luminanza_relativa(hex_colore):
    """Luminanza relativa WCAG (0..1) di un colore #rrggbb."""
    hex_colore = hex_colore.lstrip("#")
    componenti = (int(hex_colore[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def linearizza(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearizza(c) for c in componenti)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrasto(a, b):
    la, lb = _luminanza_relativa(a), _luminanza_relativa(b)
    chiaro, scuro = max(la, lb), min(la, lb)
    return (chiaro + 0.05) / (scuro + 0.05)


def _blocco(css, apertura):
    """Il corpo del primo blocco che comincia con `apertura` (senza annidamenti)."""
    i = css.find(apertura)
    if i < 0:
        return None
    j = css.index("{", i)
    k = css.index("}", j)
    return css[j + 1:k]


def _var(corpo, nome):
    m = re.search(r"(?<![\w-])" + re.escape(nome) + r":\s*([^;]+);", corpo or "")
    return m.group(1).strip() if m else None


def _regola(css, selettore):
    """Le dichiarazioni della prima regola che ha ESATTAMENTE questo selettore."""
    m = re.search(r"(?:^|\})\s*" + re.escape(selettore) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else None


def _prova_dashboard(prova, radice):
    css_grezzo = (radice / FOGLIO).read_text(encoding="utf-8")
    css = _rimuovi_commenti(css_grezzo)
    indice = (radice / "web" / "index.html").read_text(encoding="utf-8")
    js = (radice / "web" / "app.js").read_text(encoding="utf-8")

    # ---- superfici piene, niente vetro finto
    prova(f"{FOGLIO}: nessun backdrop-filter (le superfici sono piene, niente vetro finto)",
          "backdrop-filter" not in css, "")
    prova(f"{FOGLIO}: nessun gradiente o alone dietro il contenuto (niente radial-gradient, niente body::before)",
          "radial-gradient" not in css and "body::before" not in css, "")
    prova(f"{FOGLIO}: nessun mix di colore trasparente (color-mix) come sfondo",
          "color-mix" not in css, "")
    body = _regola(css, "body") or ""
    prova(f"{FOGLIO}: body ha un fondo pieno (var(--bg)) e #view pure",
          "background: var(--bg)" in body and "background: var(--bg)" in (_regola(css, "#view") or ""), body[:120])
    piene = {
        ".rail": "var(--side)", ".topbar": "var(--bg)", ".md-view > .dettaglio": "var(--bg-2)",
        ".drawer-panel": "var(--bg)", ".menu-imp": "var(--bg)", ".gruppo": "var(--bg-2)",
        ".panel-body": "var(--bg-2)",
    }
    for sel, atteso in piene.items():
        r = _regola(css, sel) or ""
        prova(f"{FOGLIO}: {sel} ha uno sfondo pieno ({atteso})",
              f"background: {atteso}" in r and "rgba" not in r.split("background:")[-1].split(";")[0], r[:120])

    # ---- temi in coppia
    chiaro = _blocco(css, ":root {") or ""
    scuro = _blocco(css, ':root[data-resolved="dark"]') or ""
    media = css[css.index("@media (prefers-color-scheme: dark)"):] if "@media (prefers-color-scheme: dark)" in css else ""
    media = media[media.index("{", media.index(":root:not")) + 1: media.index("}", media.index(":root:not"))] if ":root:not" in media else ""
    colori = ["--bg", "--bg-2", "--side", "--text", "--text-2", "--text-3", "--line", "--accent",
              "--accent-fill", "--danger", "--warn", "--ok", "--t-feedback", "--t-user", "--t-reference", "--t-project"]
    manca_scuro = [c for c in colori if _var(scuro, c) is None]
    manca_media = [c for c in colori if _var(media, c) is None]
    prova(f"{FOGLIO}: il tema scuro ridichiara tutti i colori (:root[data-resolved=\"dark\"])",
          not manca_scuro, str(manca_scuro))
    prova(f"{FOGLIO}: il tema di sistema scuro (@media prefers-color-scheme) ridichiara gli stessi colori",
          not manca_media, str(manca_media))
    prova(f"{FOGLIO}: i valori del tema scuro sono gli stessi nel blocco data-resolved e nel @media",
          all(_var(scuro, c) == _var(media, c) for c in colori),
          str([c for c in colori if _var(scuro, c) != _var(media, c)]))

    # ---- contrasti (WCAG AA: 4,5 per il testo)
    for nome, blocco in (("chiaro", chiaro), ("scuro", scuro)):
        bg = _var(blocco, "--bg")
        bg2 = _var(scuro, "--bg-2") if nome == "scuro" else _var(chiaro, "--bg-2")
        for var in ("--text", "--text-2", "--text-3", "--danger", "--warn", "--ok", "--accent"):
            v = _var(blocco, var)
            ok = bool(bg and v and v.startswith("#") and _contrasto(v, bg) >= 4.5)
            prova(f"{FOGLIO}: tema {nome}: {var} su --bg ha contrasto almeno 4,5",
                  ok, f"{v} su {bg}" + (f" = {_contrasto(v, bg):.2f}" if v and v.startswith('#') and bg else ""))
        for var in ("--text-2", "--text-3"):
            v = _var(blocco, var)
            ok = bool(bg2 and v and _contrasto(v, bg2) >= 4.5)
            prova(f"{FOGLIO}: tema {nome}: {var} sul grigio dei gruppi (--bg-2) ha contrasto almeno 4,5",
                  ok, f"{v} su {bg2}" + (f" = {_contrasto(v, bg2):.2f}" if v and bg2 else ""))
        acc, testo_acc = _var(blocco, "--accent-fill"), _var(chiaro, "--accent-text")
        prova(f"{FOGLIO}: tema {nome}: il testo bianco sulla voce scelta della barra laterale ha contrasto almeno 4,5",
              bool(acc and testo_acc and _contrasto(testo_acc, acc) >= 4.5),
              f"{testo_acc} su {acc}")

    # ---- niente colori scritti a mano fuori dai blocchi dei temi
    fuori = css
    for apertura in (":root {", ':root[data-resolved="dark"]', ":root:not"):
        i = fuori.find(apertura)
        if i >= 0:
            j = fuori.index("{", i)
            k = fuori.index("}", j)
            fuori = fuori[:i] + fuori[k + 1:]
    esadecimali = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", fuori)) - {"#fff", "#ffffff"})
    prova(f"{FOGLIO}: nessun colore esadecimale fuori dai blocchi dei temi (solo il bianco delle spunte)",
          not esadecimali, str(esadecimali))

    # ---- la struttura
    lett = _regola(css, ".lettura") or ""
    prova(f"{FOGLIO}: Oggi e' una colonna di lettura centrata che non si allarga (max-width 720px, margin auto)",
          "max-width: 720px" in lett and "margin: 0 auto" in lett, lett[:100])
    prova(f"{FOGLIO}: la voce scelta della barra laterale e' piena di colore d'accento",
          "background: var(--accent-fill)" in (_regola(css, ".rail nav a.on") or ""), "")
    prova(f"{FOGLIO}: la barra laterale si sposta in basso sugli schermi stretti (@media max-width 860px)",
          "@media (max-width: 860px)" in css and ".rail { order: 2;" in css, "")
    prova(f"{FOGLIO}: c'e' un blocco per prefers-reduced-motion", "prefers-reduced-motion" in css, "")
    prova(f"{FOGLIO}: il fuoco da tastiera si vede (:focus-visible)", ":focus-visible" in css, "")
    prova(f"{FOGLIO}: elenco e dettaglio: la colonna del dettaglio ha una larghezza sola (--detail-w)",
          "grid-template-columns: minmax(0, 1fr) var(--detail-w)" in css, "")

    # ---- index.html: la testata e le impostazioni
    prova("web/index.html: la barra laterale ha le sei voci e nessun'altra (Oggi, Task, Progetti, Social, Memoria, Archivio)",
          re.findall(r'<a href="#/(\w+)" data-view', indice) == ["oggi", "lavagna", "progetti", "social", "memoria", "archivio"],
          str(re.findall(r'<a href="#/(\w+)" data-view', indice)))
    prova("web/index.html: nessun pulsante Tema/IT/Guida in giro: stanno nel menu Impostazioni",
          'id="btn-theme"' not in indice and 'id="btn-lang"' not in indice
          and 'id="menu-imp"' in indice and 'data-tema="light"' in indice and 'data-lingua="en"' in indice
          and 'href="#/benvenuto"' in indice, "")
    menu = indice[indice.index('id="menu-imp"'):indice.index('id="drawer"')]
    prova("web/index.html: la Guida e il Briefing sono voci del menu Impostazioni",
          'href="#/benvenuto"' in menu and 'href="#/briefing"' in menu, "")
    testata = indice[indice.index('<header class="topbar">'):indice.index("</header>")]
    prova("web/index.html: la testata ha titolo e sottotitolo (#tb-titolo, #tb-sub) e il campo di ricerca",
          'id="tb-titolo"' in testata and 'id="tb-sub"' in testata and 'id="cerca-q"' in testata, "")
    prova("web/index.html: 'aggiornato alle' non e' scritto da nessuna parte nella pagina (lo scrive solo il sottotitolo)",
          "aggiornato" not in indice and "sync-line" not in indice and "sync-text" not in indice, "")

    # ---- app.js: lo stato sta nel sottotitolo e da nessun'altra parte
    scritture = re.findall(r"spia_aggiornato|T\('aggiornato", js)
    prova("web/app.js: il testo 'aggiornato alle' esce da spiaAggiorna e da nessun'altra funzione",
          scritture.count("spia_aggiornato") == 3 and "T('aggiornato" not in js,
          str(scritture))  # 3 = dizionario EN, dizionario IT, spiaAggiorna
    corpo_spia = js[js.index("function spiaAggiorna("):js.index("/* ---------------------------------------------------------------- selezione")]
    prova("web/app.js: spiaAggiorna scrive nel sottotitolo (#tb-sub)", "$('#tb-sub')" in corpo_spia, "")
    oggi = js[js.index("views.oggi = async"):js.index("function rigaProposta")]
    prova("web/app.js: Oggi non ha piu' bento, nastro, agenti ne' 'aggiornato': solo riepilogo, prossimi, proposte, domanda",
          "bento" not in oggi and "nastro(" not in oggi and "ago(d.ultimo_sync)" not in oggi
          and 'class="lettura"' in oggi and "panelloProssimi(" in oggi and "proposte.map(rigaProposta)" in oggi, "")
    prova("web/app.js: nessuna palette a comparsa (#palette): la ricerca e' il campo in alto",
          "#palette" not in js and "openPalette" not in js, "")


def _prova_swift(prova, radice):
    """L'app Mac 2.0 e' SwiftUI nativa (LOTTO-MAC2): niente WKWebView, niente materiale
    fatto a mano, niente colori o font fissi. Il vetro lo danno i controlli di sistema
    (NavigationSplitView, toolbar, Inspector, fogli). Le prove del 1.x che leggevano
    main.swift (NSGlassEffectView dietro una WKWebView, il messaggio `tema` dalla pagina)
    non hanno piu' niente da provare: la finestra non contiene piu' una pagina web.
    Queste guardano i sorgenti; il giudizio sul vetro resta a chi apre l'app."""
    base = radice / "mac" / "Sources"
    file_swift = sorted(base.rglob("*.swift"))
    # le chiavi sono percorsi relativi scritti SEMPRE con la barra dritta: su Windows
    # `str(Path)` userebbe la rovescia, e ogni confronto qui sotto ("Sistema/...",
    # "Guscio/PlanciaApp.swift") non troverebbe niente
    testi = {f.relative_to(base).as_posix(): f.read_text(encoding="utf-8") for f in file_swift}
    prova("mac/Sources: ci sono i sorgenti nelle quattro cartelle (Core, Guscio, Sistema, Viste)",
          all(any(k.startswith(c + "/") for k in testi) for c in ("Core", "Guscio", "Sistema", "Viste")),
          str(sorted({k.split("/")[0] for k in testi})))
    nomi = [f.name for f in file_swift]
    prova("mac/Sources: nessun nome di file si ripete fra cartelle (swiftc lo rifiuta)",
          len(nomi) == len(set(nomi)), str({n for n in nomi if nomi.count(n) > 1}))
    prova("mac/Sources: non c'e' piu' main.swift (il punto d'ingresso e' @main SwiftUI)",
          not (base / "main.swift").exists())

    def senza_commenti(t):
        t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        return re.sub(r"(?m)//.*$", "", t)

    codice = {k: senza_commenti(v) for k, v in testi.items()}
    nativi = {k: v for k, v in codice.items() if not k.startswith("Sistema/")}

    prova("nessun sorgente usa WKWebView o WebKit: la dashboard non e' il contenuto",
          not any("WKWebView" in v or "import WebKit" in v for v in codice.values()))
    app = codice.get("Guscio/PlanciaApp.swift", "")
    prova("Guscio/PlanciaApp.swift: @main SwiftUI con NSApplicationDelegateAdaptor",
          "@main" in app and "NSApplicationDelegateAdaptor" in app and "Settings" in app)
    prova("@main compare una volta sola", sum(v.count("@main") for v in codice.values()) == 1)
    radice_swift = codice.get("Guscio/Radice.swift", "")
    prova("Radice: NavigationSplitView con barra laterale di sistema (.listStyle(.sidebar))",
          "NavigationSplitView" in radice_swift and ".listStyle(.sidebar)" in radice_swift)
    prova("Radice: campo di ricerca di sistema con gli ambiti e stato nel sottotitolo",
          ".searchable(" in radice_swift and ".searchScopes(" in radice_swift
          and ".navigationSubtitle(" in radice_swift)
    prova("Radice: niente logo ne' wordmark nella barra laterale (nessuna Image(\"...\") di risorsa)",
          not re.search(r'Image\("', radice_swift) and "Fraunces" not in radice_swift)
    prova("Impostazioni: lingua e aspetto in una scena Settings, nessun pulsante Tema",
          "Lingua" in codice.get("Guscio/Impostazioni.swift", "")
          and "Aspetto" in codice.get("Guscio/Impostazioni.swift", "")
          and not re.search(r'Button\([^)]*"Tema"', radice_swift))
    prova("Comandi: le sezioni con ⌘1...⌘6 e Aggiorna con ⌘R",
          "keyboardShortcut(KeyEquivalent(Character(String(s.numero)))" in codice.get("Guscio/Comandi.swift", "")
          and 'keyboardShortcut("r", modifiers: .command)' in codice.get("Guscio/Comandi.swift", ""))
    prova("Istantanee: la modalita' --istantanee esiste e non parte nel server",
          "--istantanee" in codice.get("Guscio/Istantanee.swift", ""))

    # regole di design (LOTTO-MAC2, Regole di design)
    fuori = []
    for k, v in nativi.items():
        # la tavolozza dello stile Legno (Tema/Tavolozza.swift) e' l'unico posto dove i colori
        # possono essere fissi: sono il mogano e l'ottone, non hanno un colore semantico
        if k != "Tema/Tavolozza.swift" and re.search(r"Color\(\s*(red|hue|white|\.sRGB)|NSColor\(\s*(red|calibrated|srgb|white)|#[0-9a-fA-F]{6}\b", v):
            fuori.append(k + ": colore fisso")
        if re.search(r"\.font\(\s*\.system\(\s*size:", v):
            fuori.append(k + ": font a dimensione fissa")
        if ".glassEffect(" in v or re.search(r"\.(ultraThin|thin|regular|thick|ultraThick)Material", v):
            fuori.append(k + ": materiale fatto a mano")
        if re.search(r"\.blur\(", v):
            fuori.append(k + ": blur")
        if re.search(r"Font\.custom|\.custom\(", v):
            fuori.append(k + ": font non di sistema")
    prova("Core, Guscio e Viste: solo colori semantici, font di sistema e stili semantici, "
          "nessun materiale ne' blur fatto a mano", not fuori, "; ".join(fuori))
    prova("Core non dipende da AppKit ne' da SwiftUI (si compila da solo, vedi tools/prova-mac.sh)",
          not any(re.search(r"import (AppKit|SwiftUI|Cocoa)", v)
                  for k, v in codice.items() if k.startswith("Core/")))

    # quello che la 1.x sapeva fare e non si e' perso
    sistema = "\n".join(v for k, v in codice.items() if k.startswith("Sistema/"))
    for frammento, cosa in (
            ("func ensureRunning", "avvio del server se non c'e'"),
            ("func stopIfOurs", "l'uscita ferma solo il server avviato dall'app"),
            ("NSStatusBar.system.statusItem", "la voce nella barra dei menu"),
            ("kAEGetURL", "gli indirizzi plancia://"),
            ("applicationShouldHandleReopen", "la riapertura dal Dock"),
            ("final class JarvisPanel", "Jarvis"),
            ("UNUserNotificationCenter", "le notifiche"),
            ("app.log", "il registro")):
        prova(f"Sistema/: {cosa} c'e' ancora", frammento in sistema)
    build = (radice / "mac" / "build.sh").read_text(encoding="utf-8")
    prova("mac/build.sh: target macOS 26 e LSMinimumSystemVersion 26.0, niente macosx13",
          "macosx26.0" in build and "<key>LSMinimumSystemVersion</key><string>26.0</string>" in build
          and "macosx13" not in build)
    prova("mac/build.sh: compila tutti i sorgenti di mac/Sources con -parse-as-library, dietro un lucchetto",
          "-parse-as-library" in build and "find \"$ROOT/mac/Sources\"" in build and "lucchetto.py" in build)
    prova("mac/build.sh: si ferma se lo spazio libero e' sotto 1 GB", "1048576" in build)


def esegui(prova, radice) -> None:
    _prova_dashboard(prova, radice)
    _prova_swift(prova, radice)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

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

    esegui(prova, RADICE)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
