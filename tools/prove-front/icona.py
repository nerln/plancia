"""Prove per ICONA-LEGNO: l'icona e' un telegrafo d'ordini di macchina su tavole di
legno di plancia.

Sono prove statiche sui sorgenti (mac/icona/Plancia.icon, mac/build.sh, le pagine e i
loro CSS); dove c'e' l'attrezzatura (Pillow, ictool, actool, sips e iconutil) misurano
anche la cosa vera, e dove manca la prova resta nell'elenco e passa dicendo che non
era verificabile: il numero di prove non cambia da un Mac all'altro (il README lo
dichiara e tools/prova.py lo controlla). La funzione pubblica e' `esegui(prova, radice)`,
la forma di tools/prova-front.py (vedi tools/prove-front/README.md).

Le prove valgono per QUALUNQUE icona fatta cosi', non per un disegno in particolare.
Cosa deve restare vero, e perche':

- L'icona ha una sorgente vera: un documento di Icon Composer (icon.json) i cui strati
  sono PNG da 1024 con alfa, tutti presenti, senza file orfani in Assets/. Il legno e'
  il fondo e non chiede il vetro; ottone, quadrante e leva si'. Il tema scuro ha due
  strati alternati con hidden-specializations (ictool non legge image-name-specializations:
  provato).
- Gli strati sono procedurali e si rifanno da mac/icona/genera_strati.py (seme fisso),
  non si ritoccano a mano: il generatore scrive gli stessi file che il documento nomina.
- Il ripiego e' una resa: mac/icona/Plancia-1024.png e' quello che ictool disegna dal
  .icon, con il corpo da 824 px al centro della tela da 1024 (come le icone di macOS).
  build.sh, dove actool non compila il .icon, costruisce l'iconset da quella PNG con
  sips e iconutil: stessa icona per costruzione, senza un secondo disegno da tenere
  allineato. Dove c'e' ictool si confronta pixel per pixel col .icon.
- Le chiavi dell'icona nel manifesto sono coerenti con i file prodotti:
  CFBundleIconName solo dove si copia Assets.car, CFBundleIconFile sempre.
- La guardia tra build.sh e actool (la versione maggiore letta con sed) funziona su
  un'uscita vera.
- Il favicon e il marchio accanto al nome (dashboard e sito) sono la resa dell'icona
  in PNG da 64 px, la stessa nei due punti; site/img/icon.png e' RGB 512x512 senza alfa
  e ha i colori dell'icona; il marchio ha abbastanza stacco dal fondo dei due temi.
"""

import base64
import io
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

SORGENTE = "mac/icona/Plancia.icon"
FALLBACK = "mac/icona/Plancia-1024.png"
STRATI_ATTESI = {"legno", "ottone", "quadrante", "leva"}
CON_VETRO = {"ottone", "quadrante", "leva"}
ICONSET_ATTESO = {"icon_16x16.png", "icon_16x16@2x.png", "icon_32x32.png", "icon_32x32@2x.png",
                  "icon_128x128.png", "icon_128x128@2x.png", "icon_256x256.png",
                  "icon_256x256@2x.png", "icon_512x512.png", "icon_512x512@2x.png"}


def _leggi(radice, relativo):
    percorso = radice / relativo
    return percorso.read_text(encoding="utf-8") if percorso.is_file() else ""


def _ihdr(dati):
    """(larghezza, altezza, profondita', tipo colore) dall'intestazione di una PNG."""
    if dati[:8] != b"\x89PNG\r\n\x1a\n" or dati[12:16] != b"IHDR":
        return None
    w, h, prof, tipo = struct.unpack(">IIBB", dati[16:26])
    return w, h, prof, tipo


def _ihdr_file(percorso):
    return _ihdr(percorso.read_bytes()[:26]) if percorso.is_file() else None


def _pillow():
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


def _trova_ictool():
    """ictool sta in Icon Composer, dentro l'Xcode scelto con xcode-select."""
    if sys.platform != "darwin":
        return None
    try:
        sviluppo = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True,
                                  timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not sviluppo:
        return None
    ictool = Path(sviluppo).parent / "Applications" / "Icon Composer.app" / "Contents" / "Executables" / "ictool"
    return ictool if ictool.is_file() else None


def _png_da_pagina(pagina, schema):
    """I byte della PNG in base64 che `schema` (con un gruppo) trova nella pagina."""
    m = re.search(schema, pagina)
    if not m:
        return None
    try:
        return base64.b64decode(m.group(1), validate=True)
    except ValueError:
        return None


def _senza_commenti(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _blocco_css(css, apertura):
    """Il testo tra le graffe del primo blocco CSS che comincia con `apertura`
    (`:root`, `html[data-resolved="light"] {`), commenti tolti. Vuoto se non c'è."""
    css = _senza_commenti(css)
    i = css.find(apertura)
    if i < 0:
        return ""
    inizio = css.find("{", i)
    if inizio < 0:
        return ""
    livello = 0
    for j in range(inizio, len(css)):
        if css[j] == "{":
            livello += 1
        elif css[j] == "}":
            livello -= 1
            if livello == 0:
                return css[inizio + 1:j]
    return ""


def _colore_variabile(blocco, nome):
    """L'esadecimale (senza #, minuscolo) di `--<nome>: #rrggbb;` dentro un blocco."""
    m = re.search(r"--%s\s*:\s*#([0-9a-fA-F]{6})\s*;" % re.escape(nome), blocco)
    return m.group(1).lower() if m else None


def _luminanza(esadecimale):
    def canale(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(esadecimale[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * canale(r) + 0.7152 * canale(g) + 0.0722 * canale(b)


def _contrasto(a, b):
    """Rapporto di contrasto WCAG fra due colori esadecimali."""
    chiaro, scuro = sorted((_luminanza(a), _luminanza(b)), reverse=True)
    return (chiaro + 0.05) / (scuro + 0.05)


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


def esegui(prova, radice):
    def salta(nome, motivo, cond=True):
        prova(f"{nome} [non verificabile qui: {motivo}]", cond)

    Image = _pillow()
    ictool = _trova_ictool()
    sorgente = radice / SORGENTE

    # ------------------------------------------------------------ il documento
    documento = None
    if (sorgente / "icon.json").is_file():
        try:
            documento = json.loads((sorgente / "icon.json").read_text(encoding="utf-8"))
        except ValueError:
            documento = None
    prova("l'icona ha una sorgente: mac/icona/Plancia.icon/icon.json è un JSON valido",
          isinstance(documento, dict))
    prova("lo sfondo è un colore dichiarato (fill), che il legno copre", bool(documento) and "fill" in documento)
    prova("il documento dichiara le piattaforme quadrate (supported-platforms.squares)",
          bool(documento) and "squares" in documento.get("supported-platforms", {}))

    gruppi = documento.get("groups", []) if documento else []
    strati = [(gi, s) for gi, g in enumerate(gruppi) for s in g.get("layers", [])]
    nomi = {s.get("name", "") for _, s in strati}
    base_nomi = {n.replace("_scuro", "") for n in nomi}
    prova("gli strati sono legno, ottone, quadrante e leva (ognuno anche con la sua variante scura, dove serve)",
          base_nomi == STRATI_ATTESI, str(sorted(nomi)))

    immagini = [s.get("image-name", "") for _, s in strati]
    mancanti = [i for i in immagini if not i.endswith(".png") or not (sorgente / "Assets" / i).is_file()]
    prova("ogni strato nomina una PNG che esiste in Assets/", bool(strati) and not mancanti, str(mancanti))
    presenti = {p.name for p in (sorgente / "Assets").glob("*")} if (sorgente / "Assets").is_dir() else set()
    orfani = sorted(presenti - set(immagini))
    prova("in Assets/ non resta niente che nessuno strato nomina (né gli SVG del giro prima)",
          bool(presenti) and not orfani, str(orfani))
    misure = {i: _ihdr_file(sorgente / "Assets" / i) for i in immagini if i}
    prova("ogni strato è una PNG da 1024x1024, 8 bit, con canale alfa (RGBA)",
          bool(misure) and all(m is not None and m[:2] == (1024, 1024) and m[2] == 8 and m[3] == 6
                               for m in misure.values()), str(misure))
    prova("il ripiego di prima non c'è più: niente mac/makeicon.swift",
          not (radice / "mac" / "makeicon.swift").exists())

    def strato(nome):
        return next((s for _, s in strati if s.get("name") == nome), {})

    ultimo = gruppi[-1].get("layers", []) if gruppi else []
    prova("il legno è il gruppo più in basso e non chiede il vetro (è il fondo, opaco)",
          bool(ultimo) and {s.get("name", "").replace("_scuro", "") for s in ultimo} == {"legno"}
          and not any(s.get("glass") for s in ultimo))
    prova("ottone, quadrante e leva chiedono il vetro di sistema (glass) in ogni loro variante",
          all(strato(n).get("glass") is True for n in CON_VETRO)
          and all(s.get("glass") is True for _, s in strati if s.get("name", "").replace("_scuro", "") in CON_VETRO))

    # Il tema scuro: per ogni strato con una variante "_scuro" c'e' la coppia giusta.
    # La voce senza appearance va per prima (misurato: con la sola voce dark resta
    # nascosto anche nel Dark) e image-name-specializations non c'e' (ictool la ignora).
    coppie_ok = True
    dettagli = []
    for base in ("legno", "quadrante"):
        chiaro, scuro = strato(base), strato(base + "_scuro")
        ok = (chiaro.get("hidden-specializations") == [{"appearance": "dark", "value": True}]
              and scuro.get("hidden-specializations") == [{"value": True}, {"appearance": "dark", "value": False}]
              and (sorgente / "Assets" / str(scuro.get("image-name"))).is_file()
              and scuro.get("image-name") != chiaro.get("image-name"))
        coppie_ok = coppie_ok and ok
        dettagli.append(base)
    prova("il tema scuro di legno e quadrante sono due strati alternati con hidden-specializations "
          "(la voce senza appearance per prima)", coppie_ok, ",".join(dettagli))
    prova("nessuno strato usa image-name-specializations (ictool la ignora nel Dark)",
          bool(strati) and not any("image-name-specializations" in s for _, s in strati))

    # ------------------------------------------------------------ il generatore
    gen = _leggi(radice, "mac/icona/genera_strati.py")
    prova("genera_strati.py esiste e dice come rigenerare (python3 mac/icona/genera_strati.py)",
          "python3 mac/icona/genera_strati.py" in gen and "Plancia.icon" in gen)
    scritti = set(re.findall(r'"(\w+\.png)"', gen))
    prova("il generatore scrive gli stessi PNG che il documento nomina (ne' uno di piu' ne' uno di meno)",
          bool(scritti) and scritti == set(immagini), f"generatore={sorted(scritti)} documento={sorted(set(immagini))}")
    prova("il rumore del generatore ha un seme fisso (rigenerando si ottengono gli stessi pixel)",
          re.search(r"default_rng\(\s*\d+\s*\)", gen) is not None)
    prova("ripiego.py e pagine.py esistono e dicono come si lanciano",
          "python3 mac/icona/ripiego.py" in _leggi(radice, "mac/icona/ripiego.py")
          and "python3 mac/icona/pagine.py" in _leggi(radice, "mac/icona/pagine.py"))

    # ------------------------------------------------------------ actool compila il .icon
    maggiore = 0
    if shutil.which("xcrun") and sys.platform == "darwin":
        try:
            v = subprocess.run(["xcrun", "actool", "--version"], capture_output=True, text=True, timeout=60).stdout
            m_v = re.search(r"<string>(\d+)\.[\d.]*</string>", v)
            maggiore = int(m_v.group(1)) if m_v else 0
        except (OSError, subprocess.SubprocessError):
            maggiore = 0
    if maggiore >= 26:
        tmp = tempfile.mkdtemp(prefix="plancia-actool-")
        try:
            giro = subprocess.run(
                ["xcrun", "actool", str(sorgente), "--compile", tmp, "--platform", "macosx",
                 "--target-device", "mac", "--minimum-deployment-target", "13.0",
                 "--app-icon", "Plancia", "--include-all-app-icons",
                 "--enable-on-demand-resources", "NO", "--development-region", "en",
                 "--output-partial-info-plist", tmp + "/parziale.plist"],
                capture_output=True, text=True, timeout=180)
            compilato = (giro.returncode == 0 and (Path(tmp) / "Assets.car").is_file()
                         and (Path(tmp) / "Plancia.icns").is_file())
        except (OSError, subprocess.SubprocessError):
            compilato = False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        prova("actool compila il .icon in Assets.car e Plancia.icns", compilato)
    else:
        salta("actool compila il .icon in Assets.car e Plancia.icns", "serve actool 26 o piu' recente")

    # ------------------------------------------------------------ build.sh
    build = _leggi(radice, "mac/build.sh")
    pos_actool = build.find("xcrun actool")
    pos_else = build.find("\nelse\n", pos_actool) if pos_actool >= 0 else -1
    pos_png = build.find("mac/icona/Plancia-1024.png", pos_else) if pos_else >= 0 else -1
    pos_sips = build.find("sips -z", pos_else) if pos_else >= 0 else -1
    pos_iconutil = build.find("iconutil -c icns", pos_else) if pos_else >= 0 else -1
    pos_fi = build.find("\nfi\n", pos_iconutil) if pos_iconutil >= 0 else -1
    prova("build.sh compila il .icon con actool",
          pos_actool >= 0 and "--app-icon Plancia" in build and "mac/icona/Plancia.icon" in build)
    prova("build.sh prova il .icon solo con actool 26 o più recente",
          bool(re.search(r"ACTOOL_MAGGIORE[^\n]*-ge\s+26", build)))
    prova("build.sh ha il ripiego: l'altro ramo dell'if prende Plancia-1024.png, la riduce con sips "
          "e la trasforma in icns con iconutil",
          0 <= pos_actool < pos_else < pos_png < pos_sips < pos_iconutil < pos_fi)
    prova("build.sh non disegna più a mano: nessun riferimento a makeicon né a swift per l'icona",
          bool(build) and "makeicon" not in build and "swift mac/" not in build
          and not re.search(r"xcrun swift\s+\"?\$ROOT/mac/makeicon", build))
    prova("guardia di non regressione: il ripiego produce Plancia.icns dentro Resources",
          re.search(r'iconutil -c icns[^\n]*Resources/Plancia\.icns', build) is not None)
    coppie = re.search(r"for coppia in ((?:[\w@]+:[\w@]+\s*\\?\s*)+);\s*do", build)
    elenco = re.findall(r"(\d+):([\w@]+)", coppie.group(1)) if coppie else []
    nomi_iconset = {f"icon_{nome}.png" for _, nome in elenco}
    prova("il ripiego costruisce le dieci misure dell'iconset (16, 32, 128, 256, 512, ciascuna e @2x)",
          nomi_iconset == ICONSET_ATTESO, str(sorted(nomi_iconset ^ ICONSET_ATTESO)))
    doppi_ok = bool(elenco)
    for px, nome in elenco:
        m = re.fullmatch(r"(\d+)x\d+(@2x)?", nome)
        base = int(m.group(1)) if m else -1
        doppi_ok = doppi_ok and int(px) == base * (2 if m and m.group(2) else 1)
    prova("ogni misura dell'iconset ha i pixel giusti (la @2x è il doppio della base)", doppi_ok, str(elenco))

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
          sorgente.is_dir() and "--app-icon Plancia " in build and "Plancia.icns" in ramo_actool)
    manifesto = build[build.find('echo "· manifesto"'):]
    prova("guardia di non regressione: il manifesto scrive $ICONA, la variabile che i due rami riempiono",
          "$ICONA" in manifesto)

    m_sed = re.search(r"sed -n '([^'\n]*<string>[^'\n]*)'", build)
    letto = _sed(m_sed.group(1), ACTOOL_VERSION_CAMPIONE) if m_sed else None
    prova("la versione di actool letta da build.sh su un'uscita vera dà 27, non vuoto",
          letto == "27", f"letto={letto!r}")
    prova("...e su un'uscita senza versione dà vuoto (nessun Liquid Glass per errore)",
          m_sed is not None and _sed(m_sed.group(1), "<plist><dict></dict></plist>\n") == "", "")

    # ------------------------------------------------------------ la PNG di ripiego
    png_ripiego = radice / FALLBACK
    testa = _ihdr_file(png_ripiego)
    prova("Plancia-1024.png esiste ed è una PNG RGBA da 1024x1024",
          testa is not None and testa[:2] == (1024, 1024) and testa[2] == 8 and testa[3] == 6, str(testa))

    if Image is not None and testa is not None:
        img = Image.open(png_ripiego).convert("RGBA")
        alfa = img.getchannel("A")
        corpo = alfa.point(lambda v: 255 if v > 200 else 0).getbbox()
        prova("il corpo dell'icona è largo 824 px (±4) e sta al centro della tela (come le icone di macOS)",
              corpo is not None and abs((corpo[2] - corpo[0]) - 824) <= 4 and abs((corpo[3] - corpo[1]) - 824) <= 4
              and abs((corpo[0] + corpo[2]) / 2 - 512) <= 3 and abs((corpo[1] + corpo[3]) / 2 - 512) <= 3,
              f"riquadro opaco={corpo}")
        prova("gli angoli della tela sono trasparenti e il centro è opaco",
              alfa.getpixel((0, 0)) == 0 and alfa.getpixel((1023, 1023)) == 0 and alfa.getpixel((512, 512)) == 255)
        # a 16 px l'icona deve avere corpo (non svanire): il centro non e' vuoto e non e' un colore piatto
        piccola = img.resize((16, 16), Image.LANCZOS)
        colori = {piccola.getpixel((x, y))[:3] for x in range(4, 12) for y in range(4, 12)}
        prova("a 16 px il centro ha più di un colore (ghiera, settori e legno non si impastano in una macchia)",
              len(colori) >= 6, f"colori distinti nel centro={len(colori)}")
    else:
        for nome in ("il corpo dell'icona è largo 824 px (±4) e sta al centro della tela",
                     "gli angoli della tela sono trasparenti e il centro è opaco",
                     "a 16 px il centro ha più di un colore"):
            salta(nome, "manca Pillow" if Image is None else "manca la PNG", cond=testa is not None)

    if Image is not None and ictool and testa is not None:
        tmp = tempfile.mkdtemp(prefix="plancia-resa-")
        try:
            fuori = Path(tmp) / "resa.png"
            giro = subprocess.run([str(ictool), str(sorgente), "--export-image", "--output-file", str(fuori),
                                   "--platform", "macOS", "--rendition", "Default",
                                   "--width", "824", "--height", "824", "--scale", "1"],
                                  capture_output=True, text=True, timeout=180)
            resa = Image.open(fuori).convert("RGBA") if fuori.is_file() and giro.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            resa = None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if resa is not None and resa.size == (824, 824):
            ritaglio = Image.open(png_ripiego).convert("RGBA").crop((100, 100, 924, 924))
            r_px, p_px, a_px = resa.load(), ritaglio.load(), resa.getchannel("A").load()
            tot = fuori_soglia = 0
            somma = 0
            for y in range(0, 824, 3):
                for x in range(0, 824, 3):
                    if a_px[x, y] == 255:
                        d = max(abs(r_px[x, y][c] - p_px[x, y][c]) for c in range(3))
                        tot += 1
                        somma += d
                        fuori_soglia += d > 10
            media = somma / tot if tot else 999
            prova("la PNG di ripiego è la resa di ictool del .icon: media della differenza sotto 2 livelli, "
                  "quasi nessun pixel oltre 10 (il .icon è cambiato e la PNG no?)",
                  tot > 1000 and media < 2 and fuori_soglia / max(tot, 1) < 0.01,
                  f"pixel={tot} media={media:.2f} oltre10={fuori_soglia}")
        else:
            prova("la PNG di ripiego è la resa di ictool del .icon", False, "ictool non ha reso il .icon a 824 px")
    else:
        salta("la PNG di ripiego è la resa di ictool del .icon",
              "manca ictool (Xcode 26 o piu' recente)" if not ictool else "manca Pillow")

    # L'iconset vero: gli stessi passi di build.sh sulla PNG committata
    if sys.platform == "darwin" and shutil.which("sips") and shutil.which("iconutil") and elenco and testa is not None:
        tmp = Path(tempfile.mkdtemp(prefix="plancia-iconset-"))
        try:
            iconset = tmp / "Plancia.iconset"
            iconset.mkdir()
            ok = True
            for px, nome in elenco:
                r = subprocess.run(["sips", "-z", px, px, str(png_ripiego), "--out", str(iconset / f"icon_{nome}.png")],
                                   capture_output=True, timeout=60)
                ok = ok and r.returncode == 0
            r = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(tmp / "Plancia.icns")],
                               capture_output=True, timeout=60)
            ok = ok and r.returncode == 0 and (tmp / "Plancia.icns").is_file() and (tmp / "Plancia.icns").stat().st_size > 10000
        except (OSError, subprocess.SubprocessError):
            ok = False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        prova("gli stessi passi del ripiego (sips e iconutil) sulla PNG committata danno un icns", ok)
    else:
        salta("gli stessi passi del ripiego (sips e iconutil) sulla PNG committata danno un icns", "manca sips o iconutil")

    # ------------------------------------------------------------ favicon e marchio
    payload_favicon = {}
    for relativo, classe, foglio, tema_chiaro in (("web/index.html", "brand-mark", "web/style.css", True),
                                                  ("site/index.html", "bussola", "site/style.css", False)):
        pagina = _leggi(radice, relativo)
        fav = _png_da_pagina(pagina, r'<link rel="icon" href="data:image/png;base64,([A-Za-z0-9+/=]+)">')
        testa_fav = _ihdr(fav[:26]) if fav else None
        prova(f"{relativo}: il favicon è una PNG da 64x64 in data URI (la resa dell'icona)",
              testa_fav is not None and testa_fav[:2] == (64, 64) and testa_fav[3] == 6, str(testa_fav))
        marchio = re.search(r'<img class="%s" src="data:image/png;base64,([A-Za-z0-9+/=]+)"([^>]*)>' % classe, pagina)
        mb = base64.b64decode(marchio.group(1)) if marchio else None
        prova(f"{relativo}: il marchio accanto al nome (.{classe}) è un <img> con la stessa PNG del favicon",
              fav is not None and mb == fav and ' alt=""' in marchio.group(2)
              and re.search(r'width="\d+"', marchio.group(2)) is not None
              and re.search(r'height="\d+"', marchio.group(2)) is not None)
        prova(f"{relativo}: non restano SVG del segno di prima (né favicon svg né <svg> del marchio)",
              "data:image/svg" not in pagina and not re.search(r'<svg[^>]*class="%s"' % classe, pagina))
        payload_favicon[relativo] = fav

        stile = _senza_commenti(_leggi(radice, foglio))
        m_css = re.search(r"(?<![\w-])\.%s\s*\{([^}]*)\}" % classe, stile)
        dim = re.search(r"width:\s*(\d+)px;\s*height:\s*(\d+)px", m_css.group(1)) if m_css else None
        prova(f"{foglio}: .{classe} ha larghezza e altezza fisse, uguali, e nessuna regola per pezzi SVG",
              dim is not None and dim.group(1) == dim.group(2)
              and not re.search(r"\.(?:scafo|vetri)\b", stile)
              and "--marchio-" not in stile and "--crema" not in stile,
              str(dim.groups() if dim else None))

        # stacco dal fondo: il bordo del riquadro (media dei pixel del perimetro, opachi)
        # deve avere contrasto almeno 1,4 con lo sfondo del tema, o il marchio si perde.
        if Image is not None and fav:
            im = Image.open(io.BytesIO(fav)).convert("RGBA")
            bordo = [im.getpixel((x, y)) for x in range(64) for y in range(64)
                     if (x in (4, 59) or y in (4, 59)) and 4 <= x <= 59 and 4 <= y <= 59]
            bordo = [p for p in bordo if p[3] > 200]
            medio = "".join("%02x" % round(sum(p[c] for p in bordo) / len(bordo)) for c in range(3)) if bordo else None
            fondi = [_colore_variabile(_blocco_css(_leggi(radice, foglio), ":root"), "ink-0")]
            if tema_chiaro:
                fondi.append(_colore_variabile(_blocco_css(_leggi(radice, foglio), 'html[data-resolved="light"] {'), "ink-0"))
            contrasti = [round(_contrasto(medio, f), 2) if medio and f else None for f in fondi]
            prova(f"{relativo}: il marchio stacca dal fondo di ogni tema (contrasto del bordo almeno 1,4)",
                  all(c is not None and c >= 1.4 for c in contrasti), f"bordo={medio} contrasti={contrasti}")
        else:
            salta(f"{relativo}: il marchio stacca dal fondo di ogni tema", "manca Pillow", cond=bool(fav))

    prova("dashboard e sito usano la stessa PNG per il favicon",
          payload_favicon.get("web/index.html") is not None
          and payload_favicon.get("web/index.html") == payload_favicon.get("site/index.html"))

    sito = _leggi(radice, "site/index.html")
    prova("site/index.html: l'apple-touch-icon punta a img/icon.png",
          '<link rel="apple-touch-icon" href="img/icon.png">' in sito)
    testa_ic = _ihdr_file(radice / "site" / "img" / "icon.png")
    prova("site/img/icon.png è 512x512, RGB a 8 bit, senza canale alfa",
          testa_ic is not None and testa_ic[:2] == (512, 512) and testa_ic[2] == 8 and testa_ic[3] == 2, str(testa_ic))
    fav = payload_favicon.get("site/index.html")
    if Image is not None and fav and testa_ic is not None:
        grande = Image.open(radice / "site" / "img" / "icon.png").convert("RGB")
        piccolo = Image.open(io.BytesIO(fav)).convert("RGBA")

        def media(im, riquadro):
            reg = im.crop(riquadro).convert("RGB").resize((1, 1), Image.BOX)
            return reg.getpixel((0, 0))
        a = media(grande, (128, 128, 384, 384))
        b = media(piccolo, (16, 16, 48, 48))
        diff = max(abs(x - y) for x, y in zip(a, b))
        prova("site/img/icon.png ha i colori dell'icona: il centro combacia col favicon (differenza sotto 14)",
              diff < 14, f"icon.png={a} favicon={b}")
        angoli = [grande.getpixel(p) for p in ((0, 0), (511, 0), (0, 511), (511, 511))]
        prova("site/img/icon.png ha gli angoli pieni di legno (non un colore piatto, non nero)",
              all(sum(c) > 90 for c in angoli) and len(set(angoli)) > 1, str(angoli))
    else:
        salta("site/img/icon.png ha i colori dell'icona", "manca Pillow", cond=testa_ic is not None)
        salta("site/img/icon.png ha gli angoli pieni di legno", "manca Pillow", cond=testa_ic is not None)
