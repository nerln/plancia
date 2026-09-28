"""Prove per ICONA: l'icona minimalista in Liquid Glass (docs/lotti/LOTTO-ICONA-2.md).

Statiche: si leggono i sorgenti (mac/icona/Plancia.icon, mac/makeicon.swift,
mac/build.sh, i due favicon), niente Xcode, niente build. L'unica eccezione è
una misura sul disegno del ripiego, che gira solo dove c'è `swift` (macOS con
gli strumenti da riga di comando). La funzione pubblica è `esegui(prova, radice)`,
la forma di tools/prova-front.py (vedi tools/prove-front/README.md).

Le prove valgono per QUALUNQUE segno, non per uno in particolare: il primo giro
disegnava un ago di bussola, il secondo la plancia di una nave, il terzo potrà
essere altro. Il contratto tra i due file che disegnano è questo: gli SVG degli
strati sono fatti di percorsi M, L, Q, Z, un sottopercorso per forma, e
mac/makeicon.swift dichiara le stesse forme come
`let <nome> = Forma(punti: [CGPoint(x: .., y: ..), ...], raggio: ..)`, con la
regola dell'arrotondamento scritta nel suo commento (dal vertice si va verso i
due vicini per `raggio`, al più metà lato, e si gira con una quadratica che ha
il vertice per punto di controllo). Qui si ricalcolano i percorsi da quelle
dichiarazioni e si confrontano coi sottopercorsi degli SVG, in un verso o
nell'altro (un buco ha il verso opposto).

Cosa deve restare vero, e perché:

- L'icona ha una sorgente vera: un documento di Icon Composer (icon.json e gli
  strati SVG che nomina, tutti presenti), ambra di Plancia come accento, un
  segno solo, senza testo e senza gradienti dentro gli strati (il vetro lo
  mette il sistema, non l'SVG), al massimo due strati di vetro.
- Il ripiego all'icns c'è ed è nell'altro ramo di un `if`: un Mac senza Xcode 26+
  (o con un actool che rifiuta il .icon) deve continuare a produrre un'app con
  icona. Senza questa prova qualcuno può togliere `iconutil` e l'app, su quel
  Mac, resta senza icona senza che niente diventi rosso.
- Le chiavi dell'icona nel manifesto sono coerenti con i file prodotti:
  CFBundleIconName solo dove si copia Assets.car (altrimenti punterebbe a un
  catalogo che non c'è), CFBundleIconFile sempre, e il nome è quello che
  actool (`--app-icon`) e iconutil producono davvero.
- Il segno nel ripiego (makeicon.swift, CoreGraphics) e il segno negli SVG sono
  lo stesso: ogni sottopercorso degli SVG è una forma del ripiego, e ogni forma
  del ripiego è negli SVG, con le stesse coordinate e lo stesso arrotondamento,
  o con e senza Xcode 26 l'app avrebbe due icone diverse. Coordinate uguali non
  bastano: conta anche il RIFERIMENTO. La tela da 1024 del .icon coincide con il
  corpo dell'icona (actool la rimpicciolisce nel quadrato da 824 px), non con
  l'immagine intera: makeicon.swift deve portare la tavola dentro il corpo, con
  un margine dichiarato una volta sola, o il segno del ripiego esce più grande
  di 1024/824 (misurato sul primo giro: 0,99 contro 0,80 del lato). Qui lo si
  tiene fermo in due modi: la struttura del sorgente, e (dove c'è swift) la
  misura vera: si disegna il ripiego a 1024 px e il riquadro dei pixel accesi
  deve stare, entro due pixel, dove lo mettono le coordinate degli SVG.
- La guardia tra build.sh e actool (la versione maggiore letta con sed da
  `actool --version`) funziona su un'uscita vera, non solo come testo.
- I due favicon (sito e dashboard) e i due marchi accanto al nome portano lo
  stesso segno degli SVG (gli stessi percorsi, carattere per carattere), non
  una copia disegnata a parte.
"""

import json
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

NOME = "Plancia"
SORGENTE = "mac/icona/Plancia.icon"
AMBRA = "e8934e"


def _leggi(radice, relativo):
    percorso = radice / relativo
    return percorso.read_text(encoding="utf-8") if percorso.is_file() else ""


def _sottopercorsi(d):
    """Un percorso SVG fatto solo di M, L, Q, Z, come lista di sottopercorsi:
    ognuno è una lista di (comando, numeri). Un comando che non so leggere dà
    lista vuota: meglio niente che sbagliato."""
    arità = {"M": 2, "L": 2, "Q": 4, "Z": 0}
    pezzi = re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?", d)
    fuori, corrente, i = [], None, 0
    while i < len(pezzi):
        c = pezzi[i]
        i += 1
        if c not in arità:
            return []
        n = arità[c]
        if i + n > len(pezzi):
            return []
        try:
            numeri = tuple(float(x) for x in pezzi[i:i + n])
        except ValueError:
            return []
        i += n
        if c == "M":
            corrente = []
            fuori.append(corrente)
        if corrente is None:
            return []
        corrente.append((c, numeri))
    return fuori


def _arrotonda(punti, raggio, inverso=False):
    """La regola di makeicon.swift (e degli SVG): dal vertice verso i due vicini
    per `raggio` (al più metà lato), poi una quadratica col vertice per controllo."""
    if inverso:
        punti = punti[::-1]

    def verso(da, a):
        dx, dy = a[0] - da[0], a[1] - da[1]
        lunghezza = math.hypot(dx, dy)
        t = min(raggio, lunghezza / 2) / lunghezza
        return (da[0] + dx * t, da[1] + dy * t)

    n = len(punti)
    fuori = []
    for i in range(n):
        prima, qui, dopo = punti[i - 1], punti[i], punti[(i + 1) % n]
        entra, esce = verso(qui, prima), verso(qui, dopo)
        fuori.append(("M" if i == 0 else "L", entra))
        fuori.append(("Q", qui + esce))
    fuori.append(("Z", ()))
    return fuori


def _uguali(a, b, tolleranza=0.06):
    """Due sottopercorsi con gli stessi comandi e numeri entro la tolleranza
    (gli SVG hanno un decimale)."""
    if len(a) != len(b):
        return False
    for (ca, na), (cb, nb) in zip(a, b):
        if ca != cb or len(na) != len(nb):
            return False
        if any(abs(x - y) > tolleranza for x, y in zip(na, nb)):
            return False
    return True


def _forme_dallo_swift(swift):
    """{nome: (punti, raggio)} di ogni `let <nome> = Forma(punti: [...], raggio: r)`."""
    fuori = {}
    for m in re.finditer(r"let\s+(\w+)\s*=\s*Forma\(punti:\s*\[(.*?)\],\s*raggio:\s*([\d.]+)\s*\)",
                         swift, re.S):
        punti = [(float(a), float(b)) for a, b in
                 re.findall(r"CGPoint\(x:\s*(-?[\d.]+),\s*y:\s*(-?[\d.]+)\)", m.group(2))]
        fuori[m.group(1)] = (punti, float(m.group(3)))
    return fuori


def _area_con_segno(sp):
    """Formula dei lacci sui punti del sottopercorso (vertici e controlli): conta solo il
    segno, cioè il verso in cui gira."""
    pts = []
    for c, n in sp:
        for i in range(0, len(n), 2):
            pts.append((n[i], n[i + 1]))
    return sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts))) / 2


def _dentro(a, b):
    """Il riquadro del sottopercorso `a` sta dentro quello di `b`."""
    ra, rb = _riquadro([a]), _riquadro([b])
    return bool(ra and rb) and ra != rb and ra[0] >= rb[0] and ra[1] >= rb[1] \
        and ra[2] <= rb[2] and ra[3] <= rb[3]


def _riquadro(sottopercorsi):
    """(xmin, ymin, xmax, ymax) esatto di segmenti dritti e quadratiche: agli
    estremi si aggiunge il punto in cui la quadratica smette di salire."""
    xs, ys = [], []
    for sp in sottopercorsi:
        corrente = None
        for c, n in sp:
            if c in ("M", "L"):
                corrente = n
                xs.append(n[0])
                ys.append(n[1])
            elif c == "Q" and corrente is not None:
                p0, p1, p2 = corrente, n[0:2], n[2:4]
                for asse, lista in ((0, xs), (1, ys)):
                    lista.append(p2[asse])
                    den = p0[asse] - 2 * p1[asse] + p2[asse]
                    if den:
                        t = (p0[asse] - p1[asse]) / den
                        if 0 < t < 1:
                            lista.append((1 - t) ** 2 * p0[asse] + 2 * t * (1 - t) * p1[asse]
                                         + t * t * p2[asse])
                corrente = p2
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _leggi_png(percorso):
    """(larghezza, altezza, righe di RGBA) di un PNG a 8 bit non interlacciato,
    con la sola stdlib. None se non è un PNG che so leggere."""
    dati = percorso.read_bytes()
    if dati[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, ihdr, idat = 8, None, b""
    while pos + 8 <= len(dati):
        lung, tipo = struct.unpack(">I4s", dati[pos:pos + 8])
        corpo = dati[pos + 8:pos + 8 + lung]
        pos += 12 + lung
        if tipo == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo)
        elif tipo == b"IDAT":
            idat += corpo
        elif tipo == b"IEND":
            break
    if not ihdr:
        return None
    w, h, profondità, colore, _, _, interlaccio = ihdr
    canali = {2: 3, 6: 4}.get(colore)
    if profondità != 8 or interlaccio or not canali:
        return None
    grezzo = zlib.decompress(idat)
    riga, fuori, prec = w * canali, [], bytearray(w * canali)
    for y in range(h):
        base = y * (riga + 1)
        filtro, cur = grezzo[base], bytearray(grezzo[base + 1:base + 1 + riga])
        for i in range(riga):
            a = cur[i - canali] if i >= canali else 0
            b = prec[i]
            c = prec[i - canali] if i >= canali else 0
            if filtro == 1:
                cur[i] = (cur[i] + a) & 255
            elif filtro == 2:
                cur[i] = (cur[i] + b) & 255
            elif filtro == 3:
                cur[i] = (cur[i] + (a + b) // 2) & 255
            elif filtro == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur[i] = (cur[i] + pr) & 255
        fuori.append(bytes(cur))
        prec = cur
    return w, h, [(canali, r) for r in fuori]


def _riquadro_acceso(png, da, a):
    """Il riquadro (x0, y0, x1, y1) dei pixel opachi e chiari (luminanza > 110) dentro
    la finestra [da, a) della PNG, in frazione del lato: fuori resta il bordo del corpo."""
    w, h, righe = png
    x0f, x1f = int(w * da), int(w * a)
    y0f, y1f = int(h * da), int(h * a)
    trovati = [None, None, None, None]
    for y in range(y0f, y1f):
        canali, r = righe[y]
        for x in range(x0f, x1f):
            px = r[x * canali:x * canali + canali]
            opaco = canali == 3 or px[3] > 200
            if opaco and 0.3 * px[0] + 0.59 * px[1] + 0.11 * px[2] > 110:
                trovati[0] = x if trovati[0] is None else min(trovati[0], x)
                trovati[1] = y if trovati[1] is None else min(trovati[1], y)
                trovati[2] = x if trovati[2] is None else max(trovati[2], x)
                trovati[3] = y if trovati[3] is None else max(trovati[3], y)
    return tuple(trovati) if trovati[0] is not None else None


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
    prova("il segno è fatto di pochi tratti: al massimo due strati, un solo percorso ciascuno",
          bool(tutti) and len(strati) <= 2
          and len(re.findall(r"<(?:path|circle|rect|polygon|ellipse|line)\b", tutti)) <= 2)
    prova("gli strati non usano trasformazioni né bordi: le forme sono già disegnate al loro posto "
          "(le coordinate di makeicon.swift sono quelle dell'SVG, senza rotazioni nascoste)",
          bool(tutti) and "transform" not in tutti and "stroke" not in tutti)
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
    prova("mac/makeicon.swift esiste ed è il ripiego che disegna il segno con CoreGraphics",
          "CGContext" in swift and "struct Forma" in swift)

    forme = _forme_dallo_swift(swift)
    prova("makeicon.swift dichiara le forme del segno (let <nome> = Forma(punti:, raggio:))",
          len(forme) >= 1 and all(len(p) >= 3 for p, _ in forme.values()), str(sorted(forme)))
    prova("ogni forma dichiarata è anche usata nel disegno (nome dichiarato e poi richiamato)",
          bool(forme) and all(len(re.findall(r"\b%s\b" % re.escape(n), swift)) >= 2 for n in forme))

    dagli_svg = {}
    for strato in strati:
        d = re.search(r'<path[^>]*\sd="([^"]+)"', svg_testo.get(strato.get("name"), ""))
        dagli_svg[strato.get("name")] = _sottopercorsi(d.group(1)) if d else []
    tutti_sp = [(nome, sp) for nome, sps in dagli_svg.items() for sp in sps]
    prova("gli SVG sono percorsi M, L, Q, Z che il confronto sa leggere",
          bool(tutti_sp) and all(dagli_svg.values()), str({n: len(v) for n, v in dagli_svg.items()}))

    # La forma del segno (terzo giro): una sagoma sola, leggera. Due misure sugli
    # SVG, che valgono per qualunque segno futuro con lo stesso spirito.
    #  - Pochi pezzi: in ogni strato, le forme piene (quelle che non sono un buco
    #    dentro un'altra) sono al più due, cioè uno scafo e UNA casa del ponte. Il
    #    secondo giro ne aveva tre (scafo, casa, ponte) e si leggeva pesante, a
    #    gradini, da clip-art.
    #  - Slanciato: il riquadro del segno intero è basso e lungo, altezza al più il
    #    48 per cento della larghezza (il secondo giro era al 53: tozzo).
    piene = {n: sum(1 for i, sp in enumerate(sps)
                    if not any(i != j and _dentro(sp, altro) for j, altro in enumerate(sps)))
             for n, sps in dagli_svg.items()}
    prova("il segno ha pochi pezzi: in ogni strato al più due forme piene (scafo e una casa sola, niente gradini)",
          bool(piene) and max(piene.values()) <= 2, str(piene))
    riquadro_segno = _riquadro([sp for _, sp in tutti_sp])
    slancio = ((riquadro_segno[3] - riquadro_segno[1]) / (riquadro_segno[2] - riquadro_segno[0])
               if riquadro_segno else None)
    prova("il segno è slanciato: il suo riquadro è alto al più il 48 per cento della larghezza (non tozzo)",
          slancio is not None and slancio <= 0.48,
          f"altezza/larghezza={None if slancio is None else round(slancio, 3)}")

    ricalcolate = {n: (_arrotonda(p, r), _arrotonda(p, r, inverso=True)) for n, (p, r) in forme.items()}
    non_trovati = [nome for nome, sp in tutti_sp
                   if not any(_uguali(sp, avanti) or _uguali(sp, indietro)
                              for avanti, indietro in ricalcolate.values())]
    prova("ogni sottopercorso degli SVG è una forma di makeicon.swift, stesse coordinate e stesso arrotondamento",
          bool(tutti_sp) and bool(forme) and not non_trovati, f"senza corrispondenza negli strati: {non_trovati}")
    inutilizzate = [n for n, (avanti, indietro) in ricalcolate.items()
                    if not any(_uguali(sp, avanti) or _uguali(sp, indietro) for _, sp in tutti_sp)]
    prova("ogni forma di makeicon.swift è in uno SVG (il ripiego non disegna cose che il .icon non ha)",
          bool(forme) and bool(tutti_sp) and not inutilizzate, f"solo nel ripiego: {inutilizzate}")

    # Un buco (un sottopercorso dentro un altro dello stesso strato, come i vetri nella
    # nave) deve girare al contrario: con lo stesso verso la regola non-zero lo riempie
    # e la finestra sparisce (Icon Composer e CoreGraphics leggono entrambi non-zero).
    buchi_storti = []
    for nome, sps in dagli_svg.items():
        for i, dentro in enumerate(sps):
            for j, fuori_sp in enumerate(sps):
                if i != j and _dentro(dentro, fuori_sp) and \
                        _area_con_segno(dentro) * _area_con_segno(fuori_sp) > 0:
                    buchi_storti.append(f"{nome}#{i}")
    prova("i buchi degli SVG girano al contrario della forma che li contiene (altrimenti si riempiono)",
          bool(tutti_sp) and not buchi_storti, str(buchi_storti))

    posizioni = [s.get("position", {}).get("scale") for s in strati]
    prova("l'ingrandimento è lo stesso nel .icon (position.scale) e in makeicon.swift",
          bool(posizioni) and len(set(posizioni)) == 1
          and _numero_swift(swift, "ingrandimento") == float(posizioni[0]),
          f"icon={posizioni} swift={_numero_swift(swift, 'ingrandimento')}")

    # Il riferimento: la tavola sta nel corpo dell'icona, non nell'immagine intera.
    m_marg = re.search(r"let\s+margineCorpo\s*:\s*CGFloat\s*=\s*([\d.]+)", swift)
    prova("makeicon.swift dichiara il margine del corpo una volta sola (margineCorpo = 0,098)",
          m_marg is not None and float(m_marg.group(1)) == 0.098
          and len(re.findall(r"let\s+margineCorpo\b", swift)) == 1
          and len(re.findall(r"0\.098", swift)) == 1,
          f"margineCorpo={m_marg.group(1) if m_marg else None}")
    corpo_scala = _corpo_funzione(swift, "scalaTavola")
    corpo_punto = _corpo_funzione(swift, "punto")
    corpo_arrotondata = _corpo_funzione(swift, "arrotondata")
    prova("scalaTavola() porta la tavola nel corpo: (lato meno i due margini) diviso la tavola",
          "margineCorpo" in corpo_scala and "tavola" in corpo_scala and "lato" in corpo_scala,
          corpo_scala)
    prova("punto() somma il margine e usa scalaTavola: la tavola sta dentro il corpo, non sull'immagine",
          "margineCorpo" in corpo_punto and "scalaTavola(lato)" in corpo_punto
          and re.search(r"margine\s*\+", corpo_punto) is not None
          and not re.search(r"\blato\s*/\s*tavola\b", corpo_punto), corpo_punto)
    prova("arrotondata() porta il raggio degli spigoli con la stessa scala della tavola (scalaTavola), non con lato/tavola",
          "scalaTavola(lato)" in corpo_arrotondata and "punto(" in corpo_arrotondata
          and not re.search(r"\blato\s*/\s*tavola\b", corpo_arrotondata),
          corpo_arrotondata)
    prova("il corpo dell'icona (quadrato arrotondato in disegna) usa lo stesso margineCorpo della tavola",
          re.search(r"let\s+margine\s*=\s*s\s*\*\s*margineCorpo", swift) is not None)

    # La misura vera, dove c'è swift: si disegna il ripiego a 1024 px e il riquadro
    # dei pixel accesi (crema e ambra, dentro il corpo) deve stare dove lo mettono
    # le coordinate degli SVG, cioè margine + coordinata x scala. Se il ripiego
    # disegnasse sull'immagine intera invece che sul corpo, il segno uscirebbe più
    # grande del 24 per cento e questa misura si sposterebbe di decine di pixel.
    atteso = _riquadro([sp for _, sp in tutti_sp])
    if (sys.platform == "darwin" and shutil.which("xcrun") and atteso and forme
            and (radice / "mac" / "makeicon.swift").is_file()):
        tmp = tempfile.mkdtemp(prefix="plancia-icona-")
        try:
            giro = subprocess.run(["xcrun", "swift", str(radice / "mac" / "makeicon.swift"), tmp],
                                  capture_output=True, text=True, timeout=180)
            png = _leggi_png(Path(tmp) / "icon_512x512@2x.png") \
                if giro.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            png = None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if png:
            lato = png[0]
            m_marg2 = float(m_marg.group(1)) if m_marg else 0.098
            scala = (lato - 2 * lato * m_marg2) / 1024
            previsto = (lato * m_marg2 + atteso[0] * scala, lato * m_marg2 + atteso[1] * scala,
                        lato * m_marg2 + atteso[2] * scala, lato * m_marg2 + atteso[3] * scala)
            misurato = _riquadro_acceso(png, 0.15, 0.85)
            prova("misurato sul disegno: il riquadro del segno del ripiego (1024 px) sta dove lo mettono "
                  "gli SVG, entro 2 px",
                  misurato is not None
                  and all(abs(a - b) <= 2 for a, b in zip(misurato, previsto)),
                  f"misurato={misurato} previsto={tuple(round(v, 1) for v in previsto)}")
        else:
            prova("il ripiego si disegna a 1024 px (swift makeicon.swift dà una PNG leggibile)", False,
                  "makeicon.swift non ha prodotto icon_512x512@2x.png")

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
    # Il segno delle pagine è quello degli SVG, carattere per carattere: i percorsi
    # `d` degli strati compaiono uguali nel favicon e nel marchio. Una copia
    # ridisegnata a mano (o rimasta al segno di prima) li fa divergere in silenzio.
    percorsi_svg = {}
    for strato in strati:
        d = re.search(r'<path[^>]*\sd="([^"]+)"', svg_testo.get(strato.get("name"), ""))
        if d:
            percorsi_svg[strato["name"]] = d.group(1)
    for relativo in ("site/index.html", "web/index.html"):
        pagina = _leggi(radice, relativo)
        m = re.search(r'<link rel="icon" href="data:image/svg\+xml,([^"]*)">', pagina)
        svg = m.group(1) if m else ""
        prova(f"{relativo}: il favicon porta i percorsi degli SVG dell'icona, tutti e senza differenze",
              bool(svg) and bool(percorsi_svg) and all(d in svg for d in percorsi_svg.values()))
        prova(f"{relativo}: il favicon ha l'ambra e nessun residuo del segno del primo giro "
              "(niente rotate, niente cerchio della rosa dei venti)",
              bool(svg) and "%23e8934e" in svg and "rotate(" not in svg and "<circle" not in svg)
        # la tavola da 1024 va in 32: scale(.03125); se c'è un ingrandimento in più
        # dev'essere quello del .icon (position.scale)
        m_sc = re.search(r"translate\(512 512\) scale\(([\d.]+)\)", svg)
        ingrandito = float(m_sc.group(1)) if m_sc else 1.0
        prova(f"{relativo}: il favicon ha lo stesso ingrandimento del .icon (position.scale)",
              "scale(.03125)" in svg and bool(posizioni) and ingrandito == float(posizioni[0]),
              f"favicon={ingrandito} icon={posizioni}")

    # Il marchio dentro le pagine (accanto al nome) è lo stesso segno del favicon:
    # se resta un segno diverso, l'icona nel Dock e il marchio nella finestra
    # sembrano di due prodotti diversi.
    for relativo, classe in (("web/index.html", "brand-mark"), ("site/index.html", "bussola")):
        m = re.search(r'<svg[^>]*class="%s"[^>]*>(.*?)</svg>' % classe, _leggi(radice, relativo), re.S)
        corpo = m.group(1) if m else ""
        prova(f"{relativo}: il marchio accanto al nome (.{classe}) porta i percorsi degli SVG dell'icona",
              bool(corpo) and bool(percorsi_svg) and all(d in corpo for d in percorsi_svg.values())
              and "rotate(" not in corpo and "<circle" not in corpo)
        prova(f"{relativo}: il marchio attenua una parte una volta sola (opacity, senza stroke-opacity)",
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
