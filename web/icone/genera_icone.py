#!/usr/bin/env python3
"""Rifa le PNG del manifest (web/icone/*.png) dall'icona del telegrafo.

    python3 web/icone/genera_icone.py

Non e' un secondo disegno: le fonti sono quelle di mac/icona (vedi
genera_strati.py e ripiego.py), lette da li'.

- icon-192.png, icon-512.png ("any"): la resa vera dell'icona,
  mac/icona/Plancia-1024.png (lo squircle con il suo vetro), ritagliata di
  poco intorno al corpo cosi' nella barra delle applicazioni di Windows e di
  Linux non galleggia in un mare di trasparenza. Restano trasparenti agli
  angoli, come vuole "any".
- maskable-512.png ("maskable"): una PNG OPACA a tutta tela. Il sistema la
  ritaglia da se' (cerchio, squircle, goccia) e la spec vuole il soggetto
  dentro la zona sicura, il cerchio di raggio 40 per cento del lato, cioe'
  l'80 per cento del diametro. Qui non si mette lo squircle dentro un
  quadrato (il bordo di vetro finirebbe sotto la maschera o, peggio, dentro
  come una cornice): si compongono gli strati di Plancia.icon, il legno a
  tutta tela sotto, e sopra quadrante, ottone e leva rimpiccioliti quanto
  basta perche' il punto piu' lontano (il pomolo della leva, a 475 px dal
  centro su 1024) stia dentro 400 px. Il vetro di sistema non c'e': solo
  un'ombra morbida sotto ottone e leva, al posto di quella che disegna il
  sistema.
- apple-touch-icon.png (180): la stessa composizione, opaca (iOS riempie di
  nero la trasparenza e arrotonda da se').

Le PNG sono quantizzate a 256 colori (Pillow, niente pngquant): il legno
regge bene la palette, e senza quantizzare un 512 pesa il triplo. Serve
Pillow. Deterministico: gli stessi pixel a ogni rilancio.
"""
import os
import sys

from PIL import Image, ImageFilter

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(os.path.dirname(QUI))
STRATI = os.path.join(RADICE, "mac", "icona", "Plancia.icon", "Assets")
RESA = os.path.join(RADICE, "mac", "icona", "Plancia-1024.png")

TELA = 1024
# raggio massimo del soggetto (la leva) misurato sugli strati: 475.6 px
RAGGIO_LEVA = 476.0
# zona sicura della spec: cerchio di raggio 0.4 * lato. Si tiene 4 px sotto.
RAGGIO_SICURO = 0.4 * TELA - 4.0
SCALA_SOGGETTO = RAGGIO_SICURO / RAGGIO_LEVA


def quantizza(im):
    """256 colori. Con l'alfa serve FASTOCTREE (l'unico metodo di Pillow che
    la tratta); senza alfa MEDIANCUT con dither, che sul legno rende meglio."""
    if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 255:
        return im.quantize(colors=256, method=Image.Quantize.FASTOCTREE,
                           dither=Image.Dither.NONE)
    return im.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                                      dither=Image.Dither.FLOYDSTEINBERG)


def salva(im, nome):
    percorso = os.path.join(QUI, nome)
    quantizza(im).save(percorso, optimize=True)
    print("%-22s %4dx%-4d %6.1f KB" % (nome, im.width, im.height,
                                       os.path.getsize(percorso) / 1024))


def compone_maskable():
    """Legno a tutta tela + soggetto (quadrante, ottone, leva) ridotto."""
    def strato(nome):
        return Image.open(os.path.join(STRATI, nome + ".png")).convert("RGBA")

    soggetto = Image.alpha_composite(strato("quadrante"), strato("ottone"))
    soggetto = Image.alpha_composite(soggetto, strato("leva"))
    lato = round(TELA * SCALA_SOGGETTO)
    piccolo = soggetto.resize((lato, lato), Image.LANCZOS)
    tela_soggetto = Image.new("RGBA", (TELA, TELA), (0, 0, 0, 0))
    margine = (TELA - lato) // 2
    tela_soggetto.paste(piccolo, (margine, margine))

    # ombra morbida sotto ottone e leva, in luogo di quella di sistema
    alfa = tela_soggetto.getchannel("A").point(lambda v: int(v * 0.45))
    ombra = Image.new("RGBA", (TELA, TELA), (0, 0, 0, 0))
    ombra.putalpha(alfa)
    spostata = Image.new("RGBA", (TELA, TELA), (0, 0, 0, 0))
    spostata.paste(ombra, (0, 9))
    spostata = spostata.filter(ImageFilter.GaussianBlur(11))

    fondo = strato("legno")  # opaco su tutta la tela
    out = Image.alpha_composite(fondo, spostata)
    out = Image.alpha_composite(out, tela_soggetto)
    return out.convert("RGB")


def main():
    for percorso in (RESA, STRATI):
        if not os.path.exists(percorso):
            sys.exit("manca %s: si lancia dalla radice del repo, con mac/icona presente" % percorso)

    resa = Image.open(RESA).convert("RGBA")
    # il corpo sta in 824 px al centro (margine 100): si tengono 60 px di
    # margine, quanto basta all'ombra
    ritaglio = resa.crop((60, 60, TELA - 60, TELA - 60))
    salva(ritaglio.resize((192, 192), Image.LANCZOS), "icon-192.png")
    salva(ritaglio.resize((512, 512), Image.LANCZOS), "icon-512.png")

    maskable = compone_maskable()
    salva(maskable.resize((512, 512), Image.LANCZOS), "maskable-512.png")
    salva(maskable.resize((180, 180), Image.LANCZOS), "apple-touch-icon.png")


if __name__ == "__main__":
    main()
