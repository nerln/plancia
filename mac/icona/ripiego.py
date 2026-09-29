#!/usr/bin/env python3
"""Rifa mac/icona/Plancia-1024.png, la PNG di ripiego dell'icona.

Un Mac senza actool 26 o piu' recente non sa compilare il .icon: mac/build.sh
costruisce allora l'iconset da questa PNG (sips e iconutil). E' la resa vera del
.icon, fatta da ictool (il renderer di Icon Composer, dentro Xcode 26 o piu'
recente) con il vetro di sistema, quindi identica per costruzione a quella che
il sistema disegna con il .icon. Non e' un secondo disegno da tenere allineato.

    python3 mac/icona/ripiego.py

Il corpo dell'icona sta in 824 px al centro della tela da 1024, come nelle icone
di macOS, con un'ombra morbida sotto: senza quel margine nel Dock l'icona
verrebbe piu' grande delle altre. Serve Pillow. Si lancia dopo ogni modifica a
Plancia.icon (genera_strati.py) e si committa il risultato.
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageFilter

QUI = os.path.dirname(os.path.abspath(__file__))
ICONA = os.path.join(QUI, "Plancia.icon")
USCITA = os.path.join(QUI, "Plancia-1024.png")
TELA, CORPO = 1024, 824


def trova_ictool():
    """ictool sta in Icon Composer, dentro l'Xcode scelto con xcode-select."""
    sviluppo = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True).stdout.strip()
    contenuti = os.path.dirname(sviluppo)  # .../Xcode.app/Contents
    percorso = os.path.join(contenuti, "Applications", "Icon Composer.app",
                            "Contents", "Executables", "ictool")
    return percorso if os.path.isfile(percorso) else None


def main():
    ictool = trova_ictool()
    if not ictool:
        sys.exit("ictool non trovato: serve Xcode 26 o piu' recente (Icon Composer).")
    with tempfile.TemporaryDirectory() as tmp:
        resa = os.path.join(tmp, "resa.png")
        subprocess.run([ictool, ICONA, "--export-image", "--output-file", resa,
                        "--platform", "macOS", "--rendition", "Default",
                        "--width", str(CORPO), "--height", str(CORPO), "--scale", "1"],
                       check=True, capture_output=True)
        corpo = Image.open(resa).convert("RGBA")
    if corpo.size != (CORPO, CORPO):
        sys.exit("ictool ha reso %s invece di %dx%d" % (corpo.size, CORPO, CORPO))
    margine = (TELA - CORPO) // 2
    tela = Image.new("RGBA", (TELA, TELA), (0, 0, 0, 0))
    # ombra: la sagoma del corpo, spostata in giu', sfocata, al 30 per cento
    alfa = corpo.getchannel("A").point(lambda v: int(v * 0.30))
    ombra = Image.new("RGBA", corpo.size, (0, 0, 0, 0))
    ombra.putalpha(alfa)
    strato = Image.new("RGBA", (TELA, TELA), (0, 0, 0, 0))
    strato.paste(ombra, (margine, margine + 10))
    tela.alpha_composite(strato.filter(ImageFilter.GaussianBlur(12)))
    tela.alpha_composite(corpo, (margine, margine))
    tela.save(USCITA, optimize=True)
    print("scritto", os.path.relpath(USCITA))


if __name__ == "__main__":
    main()
