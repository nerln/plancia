#!/usr/bin/env python3
"""Rifa Tema/TexturaLegno.swift: la texture del tema Legno, presa dagli strati dell'icona.

    python3 mac/Sources/Tema/genera_textura.py

Prende le due tavole piene dello strato legno di mac/icona/Plancia.icon (quella in alto e
quella in basso, dove non c'e' il buco per il quadrante), le riduce a meta', le rende
ripetibili in orizzontale (dissolvenza con se stesse spostate di meta' larghezza) e
ne impila tre con il calafataggio nero in mezzo. Il risultato e' una piastrella di
512x384 pixel (256x192 punti), in JPEG, una per il chiaro e una per lo scuro, scritta
come testo base64 dentro un file Swift: niente risorse, niente file grandi.

Serve Python 3 con numpy e Pillow, come genera_strati.py. Il rumore e' a seme fisso.
"""
import base64, io, os, sys
import numpy as np
from PIL import Image

QUI = os.path.dirname(os.path.abspath(__file__))
ICONA = os.path.join(QUI, "..", "..", "icona", "Plancia.icon", "Assets")
LARG, ALT_TAVOLA, SPESSORE_COMMESSO = 512, 128, 5


def rendi_ripetibile(a):
    """Dissolvenza con se stessa spostata di meta': i due bordi coincidono."""
    w = a.shape[1]
    x = np.arange(w, dtype=np.float32)
    peso = (1.0 - np.abs(2.0 * x / w - 1.0))[None, :, None]
    return a * peso + np.roll(a, w // 2, axis=1) * (1.0 - peso)


def tavola(img, y0, y1, sposta, capovolgi):
    banda = img.crop((0, y0, 1024, y1)).convert("RGB").resize((LARG, ALT_TAVOLA - SPESSORE_COMMESSO), Image.LANCZOS)
    a = np.asarray(banda, dtype=np.float32)
    a = np.roll(rendi_ripetibile(a), sposta, axis=1)
    if capovolgi:
        a = a[::-1, :, :]
    # il commesso: nero, con un filo piu' chiaro sotto (il bordo della tavola)
    commesso = np.zeros((SPESSORE_COMMESSO, LARG, 3), dtype=np.float32)
    commesso[:] = (14, 8, 5)
    commesso[-1] = a[0] * 0.75
    return np.concatenate([commesso, a], axis=0)


def piastrella(nome):
    img = Image.open(os.path.join(ICONA, nome)).convert("RGBA")
    parti = [tavola(img, 0, 134, 0, False), tavola(img, 902, 1024, 173, False), tavola(img, 4, 130, 311, True)]
    a = np.concatenate(parti, axis=0)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def base64_jpeg(im):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82, optimize=True, subsampling=0)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def righe(testo, n=100):
    return "\n".join('        "' + testo[i:i + n] + '"' for i in range(0, len(testo), n))


def main():
    chiaro = piastrella("legno.png")
    scuro = piastrella("legno_dark.png")
    assert chiaro.size == (LARG, 3 * ALT_TAVOLA)
    out = os.path.join(QUI, "TexturaLegno.swift")
    b1, b2 = base64_jpeg(chiaro), base64_jpeg(scuro)
    with open(out, "w") as f:
        f.write("""// GENERATO da genera_textura.py, non si modifica a mano. La texture del tema Legno:
// tre tavole di mogano con il calafataggio, dagli strati dell'icona, in una piastrella
// ripetibile di 512x384 pixel (256x192 punti), chiara e scura.

enum TexturaLegno {
    static let chiaro: String =
""" + righe(b1).replace('"\n        "', '" +\n        "') + """

    static let scuro: String =
""" + righe(b2).replace('"\n        "', '" +\n        "') + """

    static let larghezza = 256.0
    static let altezza = 192.0
}
""")
    print("scritto", out, len(b1) // 1024, "KB +", len(b2) // 1024, "KB (base64)")
    if len(sys.argv) > 1:
        chiaro.save(os.path.join(sys.argv[1], "piastrella-chiara.png"))
        scuro.save(os.path.join(sys.argv[1], "piastrella-scura.png"))


main()
