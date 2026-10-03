#!/usr/bin/env python3
"""Prova del tema Legno: contrasto WCAG AA della tavolozza e peso della texture.

    python3 mac/Sources/Tema/prova_tema.py

Legge i colori da Tavolozza.swift (le righe `static let nome: UInt32 = 0x...`), la texture
da TexturaLegno.swift, e controlla:
  - ogni coppia testo/sfondo del tema (chiaro e scuro) arriva a 4.5:1 (testo normale) o
    3:1 (dove e' scritto: testo grande o simbolo);
  - il testo crema sul legno con il velo scuro, sui pixel piu' chiari della texture;
  - la texture pesa poco (sotto 100 KB in base64 in tutto);
  - i passi della dimensione del testo sono in ordine crescente e uno vale 100%.
Esce con 0 se tutto e' verde, 1 altrimenti. Serve Pillow e numpy (come genera_textura.py).
"""
import base64, io, os, re, sys

QUI = os.path.dirname(os.path.abspath(__file__))


def leggi(nome):
    with open(os.path.join(QUI, nome), encoding="utf-8") as f:
        return f.read()


def colori():
    t = leggi("Tavolozza.swift")
    c = {m.group(1): int(m.group(2), 16) for m in re.finditer(r"static let (\w+): UInt32 = (0x[0-9A-Fa-f]+)", t)}
    v = {m.group(1): float(m.group(2)) for m in re.finditer(r"static let (\w+): Double = ([0-9.]+)", t)}
    return c, v


def lum(v):
    def ch(x):
        x /= 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def lum_rgb(r, g, b):
    return lum((int(r) << 16) | (int(g) << 8) | int(b))


def rapporto(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def rapporto_l(la, lb):
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def main():
    falliti = 0

    def controlla(descrizione, valore, minimo):
        nonlocal falliti
        ok = valore >= minimo
        falliti += 0 if ok else 1
        print(("  ok   " if ok else "  NO   ") + "%-64s %5.2f (minimo %.1f)" % (descrizione, valore, minimo))

    try:
        c, v = colori()
    except FileNotFoundError as e:
        print("  NO   manca", e.filename)
        return 1
    print("==> contrasto della tavolozza")
    coppie = [
        ("inchiostro su carta, chiaro", "inchiostroChiaro", "cartaChiaro", 7.0),
        ("inchiostro su carta, scuro", "inchiostroScuro", "cartaScuro", 7.0),
        ("inchiostro tenue su carta, chiaro", "inchiostroTenueChiaro", "cartaChiaro", 4.5),
        ("inchiostro tenue su carta, scuro", "inchiostroTenueScuro", "cartaScuro", 4.5),
        ("ottone (testo, tinta) su carta, chiaro", "ottoneTestoChiaro", "cartaChiaro", 4.5),
        ("ottone (testo, tinta) su carta, scuro", "ottoneTestoScuro", "cartaScuro", 4.5),
        ("inchiostro su ottone pieno (riga scelta, alto)", "inchiostroSuOttone", "ottonePienoAlto", 4.5),
        ("inchiostro su ottone pieno (riga scelta, medio)", "inchiostroSuOttone", "ottonePieno", 4.5),
        ("inchiostro su ottone pieno (riga scelta, basso)", "inchiostroSuOttone", "ottonePienoBasso", 4.5),
        ("crema su inchiostro (conteggio sulla riga scelta)", "crema", "inchiostroSuOttone", 4.5),
    ]
    for d, a, b, m in coppie:
        if a not in c or b not in c:
            print("  NO   colore mancante per:", d)
            falliti += 1
            continue
        controlla(d, rapporto(c[a], c[b]), m)
    # bianco su ottone della tinta (i pulsanti prominenti del sistema hanno il testo bianco)
    if "ottoneTestoChiaro" in c:
        controlla("bianco su tinta ottone, chiaro (pulsanti prominenti)", rapporto(0xFFFFFF, c["ottoneTestoChiaro"]), 4.5)

    print("==> testo sul legno (velo scuro sopra la texture)")
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        print("  NO   servono Pillow e numpy")
        return 1
    t = leggi("TexturaLegno.swift")
    blocchi = {}
    for nome in ("chiaro", "scuro"):
        m = re.search(r"static let %s: String =\s*((?:\"[A-Za-z0-9+/=]*\"\s*\+?\s*)+)" % nome, t)
        if not m:
            print("  NO   texture", nome, "non trovata")
            return 1
        blocchi[nome] = "".join(re.findall(r"\"([A-Za-z0-9+/=]*)\"", m.group(1)))
    peso = sum(len(b) for b in blocchi.values())
    print("  texture: %d KB in base64" % (peso // 1024))
    controlla("texture sotto i 100 KB (100 meno i KB)", 100 - peso / 1024.0 + 1.0, 1.0)
    for nome, veloNome, tono in (("chiaro", "veloChiaro", "chiaro"), ("scuro", "veloScuro", "scuro")):
        im = Image.open(io.BytesIO(base64.b64decode(blocchi[nome]))).convert("RGB")
        a = np.asarray(im, dtype=np.float32) * (1.0 - v[veloNome])
        # luminanza relativa dei pixel dopo il velo; si guarda il 99.5 percentile
        lin = np.where(a / 255 <= 0.03928, a / 255 / 12.92, ((a / 255 + 0.055) / 1.055) ** 2.4)
        L = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
        p = float(np.percentile(L, 99.5))
        controlla("crema sul legno %s (99.5 percentile piu' chiaro)" % tono, rapporto_l(lum(c["crema"]), p), 4.5)
        controlla("crema tenue sul legno %s (99.5 percentile)" % tono, rapporto_l(lum(c["cremaTenue"]), p), 4.5)
        controlla("ottone inciso sul legno %s (99.5 percentile)" % tono, rapporto_l(lum(c["ottoneIncisione"]), p), 4.5)
        controlla("inchiostro sull'ottone, come selezione sul legno %s" % tono,
                  rapporto(c["inchiostroSuOttone"], c["ottonePieno"]), 4.5)

    print("==> passi della dimensione del testo")
    d = leggi("DimensioneTesto.swift")
    m = re.search(r"let scala: \[Int\] = \[([0-9, ]+)\]", d)
    scala = [int(x) for x in m.group(1).split(",")] if m else []
    m2 = re.search(r"static let predefinito = (\d+)", d)
    pred = int(m2.group(1)) if m2 else -1
    ok = bool(scala) and scala == sorted(set(scala)) and 0 <= pred < len(scala) and scala[pred] == 100
    falliti += 0 if ok else 1
    print(("  ok   " if ok else "  NO   ") + "passi crescenti %s, il predefinito (%d) e' 100%%" % (scala, pred))
    ok = bool(scala) and scala[0] <= 85 and scala[-1] >= 125
    falliti += 0 if ok else 1
    print(("  ok   " if ok else "  NO   ") + "l'intervallo va da <= 85% a >= 125%")

    print("verde" if falliti == 0 else "FALLITA (%d)" % falliti)
    return 0 if falliti == 0 else 1


sys.exit(main())
