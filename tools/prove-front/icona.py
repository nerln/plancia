"""Prove per ICONA: l'icona minimalista in Liquid Glass (docs/lotti/LOTTO-ICONA.md).

Statiche: si leggono i sorgenti (mac/icona/Plancia.icon, mac/makeicon.swift,
mac/build.sh, i due favicon), niente Xcode, niente build. La funzione
pubblica è `esegui(prova, radice)`, la forma di tools/prova-front.py
(vedi tools/prove-front/README.md).

Cosa deve restare vero, e perché:

- L'icona ha una sorgente vera: un documento di Icon Composer (icon.json e gli
  strati SVG che nomina, tutti presenti), ambra di Plancia come accento, un
  segno solo, senza testo e senza gradienti dentro gli strati (il vetro lo
  mette il sistema, non l'SVG).
- Il ripiego all'icns c'è ed è nell'altro ramo di un `if`: un Mac senza Xcode 26+
  (o con un actool che rifiuta il .icon) deve continuare a produrre un'app con
  icona. Senza questa prova qualcuno può togliere `iconutil` e l'app, su quel
  Mac, resta senza icona senza che niente diventi rosso.
- Le chiavi dell'icona nel manifesto sono coerenti con i file prodotti:
  CFBundleIconName solo dove si copia Assets.car (altrimenti punterebbe a un
  catalogo che non c'è), CFBundleIconFile sempre, e il nome è quello che
  actool (`--app-icon`) e iconutil producono davvero.
- Il segno nel ripiego (makeicon.swift, CoreGraphics) e il segno negli SVG sono
  lo stesso: le coordinate, la rotazione, l'ingrandimento e il bordo devono
  coincidere, o con e senza Xcode 26 l'app avrebbe due icone diverse. Coordinate
  uguali non bastano: conta anche il RIFERIMENTO. La tela da 1024 del .icon
  coincide con il corpo dell'icona (actool la rimpicciolisce nel quadrato da
  824 px), non con l'immagine intera: makeicon.swift deve portare la tavola
  dentro il corpo, con un margine dichiarato una volta sola, o l'ago del
  ripiego esce più grande di 1024/824 (misurato: 0,99 contro 0,80 del lato).
  Un'occhiata statica non misura i pixel: lo fa il confronto delle PNG nel
  rapporto del lotto; qui si tiene ferma la struttura che lo garantisce.
- La guardia tra build.sh e actool (la versione maggiore letta con sed da
  `actool --version`) funziona su un'uscita vera, non solo come testo.
- I due favicon (sito e dashboard) portano lo stesso segno, non la vecchia
  rosa dei venti.
"""

import json
import re
import struct
import subprocess

NOME = "Plancia"
SORGENTE = "mac/icona/Plancia.icon"
AMBRA = "e8934e"


def _leggi(radice, relativo):
    percorso = radice / relativo
    return percorso.read_text(encoding="utf-8") if percorso.is_file() else ""


def _punti_di_percorso(d):
    """I vertici di un percorso SVG assoluto fatto solo di M, L, H, V, Z."""
    pezzi = re.findall(r"[MLHVZ]|-?\d+(?:\.\d+)?", d)
    punti, x, y, i = [], 0.0, 0.0, 0
    while i < len(pezzi):
        c = pezzi[i]
        i += 1
        if c in "ML":
            x, y = float(pezzi[i]), float(pezzi[i + 1])
            i += 2
        elif c == "H":
            x = float(pezzi[i])
            i += 1
        elif c == "V":
            y = float(pezzi[i])
            i += 1
        elif c == "Z":
            continue
        else:
            return []  # un comando che non so leggere: meglio vuoto che sbagliato
        punti.append((x, y))
    return punti


def _triangoli_dagli_svg(radice, strati):
    """{nome dello strato: vertici} letti dai file SVG."""
    fuori = {}
    for strato in strati:
        svg = _leggi(radice, f"{SORGENTE}/Assets/{strato['image-name']}")
        d = re.search(r'<path[^>]*\sd="([^"]+)"', svg)
        fuori[strato["name"]] = _punti_di_percorso(d.group(1)) if d else []
    return fuori


def _punti_dallo_swift(swift, nome):
    """I CGPoint di `let <nome>: [CGPoint] = [...]` in makeicon.swift."""
    m = re.search(r"let\s+%s\s*:\s*\[CGPoint\]\s*=\s*\[(.*?)\]\s*\n" % nome, swift, re.S)
    if not m:
        return []
    return [(float(a), float(b)) for a, b in
            re.findall(r"CGPoint\(x:\s*(-?[\d.]+),\s*y:\s*(-?[\d.]+)\)", m.group(1))]


def _numero_swift(swift, nome):
    m = re.search(r"let\s+%s\s*:\s*CGFloat\s*=\s*([\d.]+)" % nome, swift)
    return float(m.group(1)) if m else None


# Un'uscita vera di `xcrun actool --version` (Xcode 27, letta il 29/09/2026).
ACTOOL_VERSION_CAMPIONE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>com.apple.actool.version</key>
\t<dict>
\t\t<key>bundle-version</key>
\t\t<string>25098</string>
\t\t<key>short-bundle-version</key>
\t\t<string>27.0</string>
\t</dict>
</dict>
</plist>
"""


def _sed(script, testo):
    """`sed -n <script> | head -1` su un testo, come fa build.sh."""
    try:
        fuori = subprocess.run(["sed", "-n", script], input=testo, capture_output=True,
                               text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return fuori.splitlines()[0] if fuori.strip() else ""


def _corpo_funzione(swift, nome):
    """Il testo di `func <nome>(...) {...}` in makeicon.swift, fino alla graffa che la chiude."""
    m = re.search(r"func\s+%s\s*\(" % re.escape(nome), swift)
    if not m:
        return ""
    inizio = swift.find("{", m.end())
    if inizio < 0:
        return ""
    livello = 0
    for i in range(inizio, len(swift)):
        if swift[i] == "{":
            livello += 1
        elif swift[i] == "}":
            livello -= 1
            if livello == 0:
                return swift[inizio:i + 1]
    return ""


def _dimensioni_png(percorso):
    """(larghezza, altezza) dall'intestazione di un PNG, senza librerie."""
    if not percorso.is_file():
        return None
    testa = percorso.read_bytes()[:24]
    if testa[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", testa[16:24])


def esegui(prova, radice):
    # ------------------------------------------------------------ la sorgente
    percorso_json = radice / SORGENTE / "icon.json"
    documento = None
    if percorso_json.is_file():
        try:
            documento = json.loads(percorso_json.read_text(encoding="utf-8"))
        except ValueError:
            documento = None
    prova("l'icona ha una sorgente: mac/icona/Plancia.icon/icon.json è un JSON valido",
          isinstance(documento, dict))

    strati = []
    if documento:
        for gruppo in documento.get("groups", []):
            strati.extend(gruppo.get("layers", []))
    prova("il documento ha almeno uno strato di primo piano", len(strati) >= 1)

    mancanti = [s.get("image-name") for s in strati
                if not (radice / SORGENTE / "Assets" / str(s.get("image-name"))).is_file()]
    prova("ogni strato nomina un file che esiste in Assets/", bool(strati) and not mancanti,
          str(mancanti))

    prova("lo sfondo è un colore dichiarato (fill), non un file",
          bool(documento) and "fill" in documento)

    svg_testo = {s["name"]: _leggi(radice, f"{SORGENTE}/Assets/{s['image-name']}")
                 for s in strati if "name" in s and "image-name" in s}
    tutti = "\n".join(svg_testo.values()).lower()
    prova("l'ambra di Plancia (#e8934e) è l'accento degli strati", AMBRA in tutti)
    prova("niente testo dentro il segno (un segno solo, leggibile a 16 px)",
          bool(tutti) and "<text" not in tutti)
    prova("niente gradienti dentro gli strati: il vetro lo applica il sistema",
          bool(tutti) and "gradient" not in tutti)
    prova("il segno è fatto di pochi tratti: al massimo due forme in tutto",
          bool(tutti) and len(re.findall(r"<(?:path|circle|rect|polygon|ellipse|line)\b", tutti)) <= 2)
    prova("gli strati chiedono il vetro (glass) e il documento lo dichiara per le piattaforme quadrate",
          bool(strati) and all(s.get("glass") is True for s in strati)
          and "squares" in documento.get("supported-platforms", {}))

    # ------------------------------------------------------------ il ripiego
    build = _leggi(radice, "mac/build.sh")
    pos_actool = build.find("xcrun actool")
    pos_else = build.find("\nelse\n", pos_actool) if pos_actool >= 0 else -1
    pos_iconutil = build.find("iconutil -c icns", pos_else) if pos_else >= 0 else -1
    pos_makeicon = build.find("mac/makeicon.swift", pos_else) if pos_else >= 0 else -1
    pos_fi = build.find("\nfi\n", pos_iconutil) if pos_iconutil >= 0 else -1

    prova("build.sh compila il .icon con actool",
          pos_actool >= 0 and "--app-icon Plancia" in build and "mac/icona/Plancia.icon" in build)
    prova("build.sh prova il .icon solo con actool 26 o più recente",
          bool(re.search(r"ACTOOL_MAGGIORE[^\n]*-ge\s+26", build)))
    prova("build.sh ha il ripiego all'icns: l'altro ramo dell'if disegna con makeicon.swift e usa iconutil",
          0 <= pos_actool < pos_else < pos_makeicon < pos_iconutil < pos_fi)
    prova("guardia di non regressione: il ripiego produce Plancia.icns dentro Resources",
          "iconutil -c icns" in build
          and re.search(r'iconutil -c icns[^\n]*Resources/Plancia\.icns', build) is not None)

    # ------------------------------------------------------------ il manifesto
    ramo_actool = build[pos_actool:pos_else] if 0 <= pos_actool < pos_else else ""
    ramo_ripiego = build[pos_else:pos_fi] if 0 <= pos_else < pos_fi else ""
    chiave_file = "<key>CFBundleIconFile</key><string>Plancia</string>"
    chiave_nome = "<key>CFBundleIconName</key><string>Plancia</string>"
    prova("nel ramo actool il manifesto ha CFBundleIconFile e CFBundleIconName, entrambi 'Plancia'",
          chiave_file in ramo_actool and chiave_nome in ramo_actool)
    prova("il ramo actool copia Assets.car e Plancia.icns nel bundle: CFBundleIconName ha il suo catalogo",
          bool(re.search(r"cp\s+[^\n]*Assets\.car[^\n]*Plancia\.icns[^\n]*Resources", ramo_actool)))
    prova("nel ripiego il manifesto ha CFBundleIconFile ma NON CFBundleIconName (non c'è Assets.car)",
          chiave_file in ramo_ripiego and "CFBundleIconName" not in ramo_ripiego)
    prova("il nome dell'icona è lo stesso ovunque: Plancia.icon, --app-icon Plancia, Plancia.icns",
          (radice / SORGENTE).is_dir() and "--app-icon Plancia " in build
          and "Plancia.icns" in ramo_actool)
    manifesto = build[build.find('echo "· manifesto"'):]
    prova("guardia di non regressione: il manifesto scrive $ICONA, la variabile che i due rami riempiono",
          "$ICONA" in manifesto)

    # ------------------------------------------------------------ swift == svg
    swift = _leggi(radice, "mac/makeicon.swift")
    prova("mac/makeicon.swift esiste ed è il ripiego che disegna l'ago",
          "CGContext" in swift and "let nord" in swift and "let sud" in swift)

    dagli_svg = _triangoli_dagli_svg(radice, strati)
    for nome in ("nord", "sud"):
        dallo_swift = _punti_dallo_swift(swift, nome)
        prova(f"il triangolo '{nome}' ha le stesse coordinate nello SVG e in makeicon.swift",
              len(dallo_swift) == 3 and dagli_svg.get(nome) == dallo_swift,
              f"svg={dagli_svg.get(nome)} swift={dallo_swift}")

    posizioni = [s.get("position", {}).get("scale") for s in strati]
    prova("l'ingrandimento è lo stesso nel .icon (position.scale) e in makeicon.swift",
          bool(posizioni) and len(set(posizioni)) == 1
          and _numero_swift(swift, "ingrandimento") == float(posizioni[0]),
          f"icon={posizioni} swift={_numero_swift(swift, 'ingrandimento')}")

    trasformazioni = set()
    for testo in svg_testo.values():
        trasformazioni.update(re.findall(r"rotate\((-?[\d.]+)\s+512\s+512\)", testo))
    m_rot = re.search(r"let\s+rotazione\s*:\s*CGFloat\s*=\s*([\d.]+)\s*\*", swift)
    prova("la rotazione (rotate di SVG, in gradi) è la stessa in tutti gli strati e in makeicon.swift",
          len(trasformazioni) == 1 and m_rot is not None
          and float(next(iter(trasformazioni))) == float(m_rot.group(1)),
          f"svg={trasformazioni} swift={m_rot.group(1) if m_rot else None}")

    bordi = set()
    for testo in svg_testo.values():
        bordi.update(re.findall(r'stroke-width="([\d.]+)"', testo))
    prova("il bordo che arrotonda gli spigoli (stroke-width) è lo stesso negli SVG e in makeicon.swift",
          len(bordi) == 1 and _numero_swift(swift, "bordoSpigoli") == float(next(iter(bordi))),
          f"svg={bordi} swift={_numero_swift(swift, 'bordoSpigoli')}")

    # Il riferimento: la tavola sta nel corpo dell'icona, non nell'immagine intera.
    m_marg = re.search(r"let\s+margineCorpo\s*:\s*CGFloat\s*=\s*([\d.]+)", swift)
    prova("makeicon.swift dichiara il margine del corpo una volta sola (margineCorpo = 0,098)",
          m_marg is not None and float(m_marg.group(1)) == 0.098
          and len(re.findall(r"let\s+margineCorpo\b", swift)) == 1
          and len(re.findall(r"0\.098", swift)) == 1,
          f"margineCorpo={m_marg.group(1) if m_marg else None}")
    corpo_scala = _corpo_funzione(swift, "scalaTavola")
    corpo_punto = _corpo_funzione(swift, "punto")
    corpo_meta = _corpo_funzione(swift, "metà")
    prova("scalaTavola() porta la tavola nel corpo: (lato meno i due margini) diviso la tavola",
          "margineCorpo" in corpo_scala and "tavola" in corpo_scala and "lato" in corpo_scala,
          corpo_scala)
    prova("punto() somma il margine e usa scalaTavola: la tavola sta dentro il corpo, non sull'immagine",
          "margineCorpo" in corpo_punto and "scalaTavola(lato)" in corpo_punto
          and re.search(r"margine\s*\+", corpo_punto) is not None
          and not re.search(r"\blato\s*/\s*tavola\b", corpo_punto), corpo_punto)
    prova("metà() porta lo spessore del bordo con la stessa scala della tavola (scalaTavola), non con lato/tavola",
          "scalaTavola(lato)" in corpo_meta and not re.search(r"\blato\s*/\s*tavola\b", corpo_meta),
          corpo_meta)
    prova("il corpo dell'icona (quadrato arrotondato in disegna) usa lo stesso margineCorpo della tavola",
          re.search(r"let\s+margine\s*=\s*s\s*\*\s*margineCorpo", swift) is not None)

    # La guardia tra build.sh e actool, eseguita su un'uscita vera di
    # `actool --version` (Xcode 27: bundle-version 25098, short 27.0): deve dare
    # 27, non vuoto. Se la regex smette di combaciare, il Liquid Glass sparisce
    # in silenzio e il resto resta verde.
    m_sed = re.search(r"sed -n '([^'\n]*<string>[^'\n]*)'", build)
    campione = ACTOOL_VERSION_CAMPIONE
    letto = _sed(m_sed.group(1), campione) if m_sed else None
    prova("la versione di actool letta da build.sh su un'uscita vera dà 27, non vuoto",
          letto == "27", f"letto={letto!r}")
    prova("...e su un'uscita senza versione dà vuoto (nessun Liquid Glass per errore)",
          m_sed is not None and _sed(m_sed.group(1), "<plist><dict></dict></plist>\n") == "",
          "")

    # ------------------------------------------------------------ favicon
    for relativo in ("site/index.html", "web/index.html"):
        pagina = _leggi(radice, relativo)
        m = re.search(r'<link rel="icon" href="data:image/svg\+xml,([^"]*)">', pagina)
        svg = m.group(1) if m else ""
        prova(f"{relativo}: il favicon è l'ago (ambra e crema, ruotato di 40 gradi)",
              bool(svg) and "%23e8934e" in svg and "rotate(40 512 512)" in svg)
        prova(f"{relativo}: il favicon non è più la vecchia rosa dei venti (cerchio e quattro tacche)",
              bool(svg) and "<circle" not in svg)
        m_sc = re.search(r"scale\(([\d.]+)\) translate\(-512 -512\) rotate\(40 512 512\)", svg)
        prova(f"{relativo}: il favicon ha lo stesso ingrandimento del .icon (position.scale)",
              m_sc is not None and bool(posizioni) and float(m_sc.group(1)) == float(posizioni[0]),
              f"favicon={m_sc.group(1) if m_sc else None} icon={posizioni}")

    # Il marchio dentro le pagine (accanto al nome) è lo stesso segno del favicon:
    # se resta la vecchia rosa dei venti, l'icona nel Dock e il marchio nella
    # finestra sembrano di due prodotti diversi.
    for relativo, classe in (("web/index.html", "brand-mark"), ("site/index.html", "bussola")):
        m = re.search(r'<svg[^>]*class="%s"[^>]*>(.*?)</svg>' % classe, _leggi(radice, relativo), re.S)
        corpo = m.group(1) if m else ""
        prova(f"{relativo}: il marchio accanto al nome (.{classe}) è l'ago, non la rosa dei venti",
              bool(corpo) and "rotate(40 512 512)" in corpo and "<circle" not in corpo)
        prova(f"{relativo}: la metà sud del marchio si attenua una volta sola (opacity, senza stroke-opacity)",
              bool(corpo) and "opacity" in corpo and "stroke-opacity" not in corpo)

    misure = _dimensioni_png(radice / "site" / "img" / "icon.png")
    prova("site/img/icon.png è un PNG quadrato di almeno 180 px (per apple-touch-icon)",
          misure is not None and misure[0] == misure[1] and misure[0] >= 180, str(misure))
    # iOS riempie di nero la trasparenza di un apple-touch-icon e arrotonda da sé:
    # serve un quadrato pieno, senza canale alfa (colour type 2 = RGB, 0 = grigio).
    png = radice / "site" / "img" / "icon.png"
    tipo_colore = png.read_bytes()[25] if png.is_file() and len(png.read_bytes()) > 25 else None
    prova("site/img/icon.png è un quadrato pieno, senza canale alfa (apple-touch-icon: iOS riempie di nero la trasparenza)",
          tipo_colore in (0, 2), f"colour type={tipo_colore}")
    prova("site/index.html usa site/img/icon.png come apple-touch-icon",
          'rel="apple-touch-icon" href="img/icon.png"' in _leggi(radice, "site/index.html"))
