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
  coincidere, o con e senza Xcode 26 l'app avrebbe due icone diverse.
- I due favicon (sito e dashboard) portano lo stesso segno, non la vecchia
  rosa dei venti.
"""

import json
import re
import struct

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
    prova("il ripiego produce Plancia.icns dentro Resources",
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
    prova("il manifesto scrive $ICONA, la variabile che i due rami riempiono",
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

    # ------------------------------------------------------------ favicon
    for relativo in ("site/index.html", "web/index.html"):
        pagina = _leggi(radice, relativo)
        m = re.search(r'<link rel="icon" href="data:image/svg\+xml,([^"]*)">', pagina)
        svg = m.group(1) if m else ""
        prova(f"{relativo}: il favicon è l'ago (ambra e crema, ruotato di 40 gradi)",
              bool(svg) and "%23e8934e" in svg and "rotate(40 512 512)" in svg)
        prova(f"{relativo}: il favicon non è più la vecchia rosa dei venti (cerchio e quattro tacche)",
              bool(svg) and "<circle" not in svg)

    # Il marchio dentro le pagine (accanto al nome) è lo stesso segno del favicon:
    # se resta la vecchia rosa dei venti, l'icona nel Dock e il marchio nella
    # finestra sembrano di due prodotti diversi.
    for relativo, classe in (("web/index.html", "brand-mark"), ("site/index.html", "bussola")):
        m = re.search(r'<svg[^>]*class="%s"[^>]*>(.*?)</svg>' % classe, _leggi(radice, relativo), re.S)
        corpo = m.group(1) if m else ""
        prova(f"{relativo}: il marchio accanto al nome (.{classe}) è l'ago, non la rosa dei venti",
              bool(corpo) and "rotate(40 512 512)" in corpo and "<circle" not in corpo)

    misure = _dimensioni_png(radice / "site" / "img" / "icon.png")
    prova("site/img/icon.png è un PNG quadrato di almeno 180 px (per apple-touch-icon)",
          misure is not None and misure[0] == misure[1] and misure[0] >= 180, str(misure))
    prova("site/index.html usa site/img/icon.png come apple-touch-icon",
          'rel="apple-touch-icon" href="img/icon.png"' in _leggi(radice, "site/index.html"))
