#!/usr/bin/env python3
"""Porta l'icona nelle pagine: favicon, marchio accanto al nome, apple-touch-icon.

Parte dalla resa di ictool del .icon (stessa che finisce nel Dock), quindi le
pagine mostrano l'icona vera e non un disegno a parte.

    python3 mac/icona/pagine.py

Cosa riscrive:
  - site/img/icon.png: apple-touch-icon del sito, 512x512 RGB senza canale alfa.
    La resa di ictool ha gli angoli trasparenti: il fondo va riempito, e qui si usa
    lo strato del legno (mac/icona/Plancia.icon/Assets/legno.png), a tutto riquadro,
    cosi' i quattro angoli hanno lo stesso legno e non un colore piatto.
  - la PNG da 64 px (base64) del favicon e del marchio, dentro web/index.html e
    site/index.html: si sostituisce il contenuto dei data:image/png;base64 gia'
    presenti, riconosciuti da <link rel="icon"> e dalle classi brand-mark e bussola.

Serve Pillow e Xcode 26 o piu' recente (ictool). Si lancia dopo ogni modifica al
segno, insieme a ripiego.py, e si committa il risultato.
"""
import base64
import io
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(os.path.dirname(QUI))
ICONA = os.path.join(QUI, "Plancia.icon")


def trova_ictool():
    sviluppo = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True).stdout.strip()
    percorso = os.path.join(os.path.dirname(sviluppo), "Applications", "Icon Composer.app",
                            "Contents", "Executables", "ictool")
    return percorso if os.path.isfile(percorso) else None


def rendi(ictool, piattaforma, lato, tmp):
    fuori = os.path.join(tmp, "%s-%d.png" % (piattaforma, lato))
    subprocess.run([ictool, ICONA, "--export-image", "--output-file", fuori,
                    "--platform", piattaforma, "--rendition", "Default",
                    "--width", str(lato), "--height", str(lato), "--scale", "1"],
                   check=True, capture_output=True)
    return Image.open(fuori).convert("RGBA")


def png_base64(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def sostituisci(percorso, schemi, b64):
    """Cambia il payload base64 nei punti che `schemi` riconosce; ritorna quanti."""
    testo = open(percorso, encoding="utf-8").read()
    totale = 0
    for schema in schemi:
        testo, n = re.subn(schema, lambda m: m.group(1) + b64 + m.group(2), testo)
        totale += n
    open(percorso, "w", encoding="utf-8").write(testo)
    return totale


def main():
    ictool = trova_ictool()
    if not ictool:
        sys.exit("ictool non trovato: serve Xcode 26 o piu' recente (Icon Composer).")
    with tempfile.TemporaryDirectory() as tmp:
        # apple-touch-icon: resa a tutto riquadro sopra il legno, ridotta, senza alfa
        grande = rendi(ictool, "iOS", 1024, tmp)
        legno = Image.open(os.path.join(ICONA, "Assets", "legno.png")).convert("RGBA")
        fondo = legno.copy()
        fondo.alpha_composite(grande)
        fondo.convert("RGB").resize((512, 512), Image.LANCZOS).save(
            os.path.join(RADICE, "site", "img", "icon.png"), optimize=True)
        print("scritto site/img/icon.png")
        # favicon e marchio: la resa nativa a 64 px, con gli angoli trasparenti
        b64 = png_base64(rendi(ictool, "macOS", 64, tmp))
    da_fare = {
        "web/index.html": [r'(<link rel="icon" href="data:image/png;base64,)[A-Za-z0-9+/=]+(">)',
                           r'(<img class="brand-mark" src="data:image/png;base64,)[A-Za-z0-9+/=]+(")'],
        "site/index.html": [r'(<link rel="icon" href="data:image/png;base64,)[A-Za-z0-9+/=]+(">)',
                            r'(<img class="bussola" src="data:image/png;base64,)[A-Za-z0-9+/=]+(")'],
    }
    for relativo, schemi in da_fare.items():
        n = sostituisci(os.path.join(RADICE, relativo), schemi, b64)
        print("%s: %d punti aggiornati" % (relativo, n))


if __name__ == "__main__":
    main()
