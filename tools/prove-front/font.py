"""Prove per L1-FONT: le tre famiglie vendorizzate e la scala tipografica.

Statiche, si guarda solo il sorgente (niente browser, niente server): sono le
stesse condizioni scritte in docs/lotti/LOTTO-L1-FONT.md, sotto "Prove rosse
senza". La funzione pubblica è `esegui(prova, radice)`, la stessa forma usata
da tools/prova-front.py (vedi tools/prove-front/README.md).
"""

import re

FOGLI = ("web/style.css", "site/style.css")


def _font_face_families(testo):
    """I nomi di font-family dichiarati dentro un blocco @font-face."""
    nomi = set()
    for blocco in re.findall(r"@font-face\s*\{[^}]*\}", testo, re.S):
        m = re.search(r"font-family:\s*[\"']([^\"';]+)[\"']", blocco)
        if m:
            nomi.add(m.group(1))
    return nomi


def _font_face_urls(testo):
    """Ogni url(...) citato dentro un blocco @font-face, senza le virgolette."""
    urls = []
    for blocco in re.findall(r"@font-face\s*\{[^}]*\}", testo, re.S):
        urls.extend(re.findall(r"url\((['\"]?)([^)'\"]+)\1\)", blocco))
    return [u for _, u in urls]


def _prova_tre_famiglie(prova, radice):
    for foglio in FOGLI:
        testo = (radice / foglio).read_text(encoding="utf-8")
        famiglie = _font_face_families(testo)
        prova(f"{foglio} dichiara tre famiglie in @font-face",
              len(famiglie) == 3, str(sorted(famiglie)))


def _prova_url_esistono(prova, radice):
    for foglio in FOGLI:
        percorso = radice / foglio
        testo = percorso.read_text(encoding="utf-8")
        cartella = percorso.parent
        mancanti = [u for u in _font_face_urls(testo) if not (cartella / u).is_file()]
        prova(f"{foglio}: ogni url(...) di @font-face esiste come file",
              not mancanti, str(mancanti))


def _prova_font_size_solo_variabili(prova, radice):
    # La regola vale su web/style.css: è la dashboard, non il sito (il sito
    # tiene le sue taglie di apertura libere, vedi il commento in cima al
    # file e LOTTO-L1-FONT.md).
    testo = (radice / "web" / "style.css").read_text(encoding="utf-8")
    fuori_scala = re.findall(r"font-size:\s*[0-9][^;]*", testo)
    # calc(var(--t-display) + 4px) contiene una cifra ma non è un valore
    # puntuale fuori scala: è l'unico calc() dichiarato, sopra --t-display.
    fuori_scala = [f for f in fuori_scala if "var(--t-" not in f]
    prova("web/style.css: nessun font-size in px fuori dalle sei variabili",
          not fuori_scala, str(fuori_scala))


def _prova_niente_stack_di_sistema_davanti(prova, radice):
    for foglio in FOGLI:
        testo = (radice / foglio).read_text(encoding="utf-8")
        for nome, cattivo in (("--sans", "-apple-system"), ("--serif", "ui-serif")):
            m = re.search(re.escape(nome) + r":\s*([^;]+);", testo)
            prova(f"{foglio}: {cattivo} non è la prima voce di {nome}",
                  bool(m) and not m.group(1).strip().startswith(cattivo),
                  m.group(1) if m else "variabile non trovata")


def _blocchi(testo):
    """Ogni blocco selettore { dichiarazioni } del foglio (niente @font-face,
    niente @media annidati: qui la CSS è piatta)."""
    return re.findall(r"([^{}]+)\{([^{}]*)\}", testo)


def _prova_mono_senza_600(prova, radice):
    # IBM Plex Mono è vendorizzato solo nei pesi 400 e 500 (vedi i @font-face
    # più sopra in questo stesso file e LICENSE-fonts.txt): un font-weight 600
    # (o una shorthand "font: 600 ...") su un elemento in var(--mono) non
    # sceglie un file diverso, fa sintetizzare al browser un grassetto finto
    # sopra il 500 vero. Oggi (prima della correzione) .num lo viola: rosso.
    for foglio in FOGLI:
        testo = (radice / foglio).read_text(encoding="utf-8")
        violazioni = []
        for selettore, corpo in _blocchi(testo):
            if "var(--mono)" not in corpo:
                continue
            if re.search(r"font-weight:\s*600", corpo) or re.search(r"font:\s*600", corpo):
                violazioni.append(selettore.strip())
        prova(f"{foglio}: nessun blocco con var(--mono) chiede font-weight 600",
              not violazioni, str(violazioni))


def _prova_tag_mono_peso(prova, radice):
    # .tag eredita font-weight:600 dalla regola .tag; senza un 500 esplicito
    # su .tag.mono l'elemento risolverebbe comunque a 600 per cascata, un
    # caso che _prova_mono_senza_600 non vede perché il blocco di .tag.mono
    # da solo non contiene "600". Si controlla qui, esplicitamente.
    testo = (radice / "web" / "style.css").read_text(encoding="utf-8")
    m = re.search(r"\.tag\.mono\s*\{([^}]*)\}", testo)
    prova("web/style.css: .tag.mono dichiara esplicitamente font-weight: 500",
          bool(m) and bool(re.search(r"font-weight:\s*500", m.group(1))),
          m.group(1).strip() if m else "regola .tag.mono non trovata")


def _prova_font_synthesis(prova, radice):
    # Guardia contro la sintesi del grassetto: senza questa riga, un futuro
    # font-weight sopra il peso massimo vendorizzato (o un <b>/<strong> dentro
    # .mono) verrebbe ingrassato artificialmente invece di restare sul volto
    # vero. Oggi (prima della correzione) manca in entrambi i fogli: rosso.
    for foglio in FOGLI:
        testo = (radice / foglio).read_text(encoding="utf-8")
        prova(f"{foglio}: html ha font-synthesis: none",
              bool(re.search(r"\bhtml\b[^{]*\{[^}]*font-synthesis:\s*none", testo)),
              "")


def _prova_unicode_range(prova, radice):
    # Ogni @font-face dei due fogli deve dichiarare un unicode-range: i
    # subset di Google Fonts (latin / latin-ext) non coprono da soli tutto
    # Unicode, e senza questa riga le due facce gemelle si accavallano e la
    # scelta del glifo dipende dal fallback interno di ogni motore invece che
    # da una regola esplicita.
    for foglio in FOGLI:
        testo = (radice / foglio).read_text(encoding="utf-8")
        mancanti = [b for b in re.findall(r"@font-face\s*\{[^}]*\}", testo, re.S)
                    if "unicode-range:" not in b]
        prova(f"{foglio}: ogni @font-face dichiara unicode-range",
              not mancanti, str(len(mancanti)) + " blocchi senza")


def _prova_licenza(prova, radice):
    for percorso in (radice / "web" / "LICENSE-fonts.txt",
                      radice / "site" / "font" / "LICENSE-fonts.txt"):
        esiste = percorso.is_file()
        prova(f"{percorso.relative_to(radice)} esiste", esiste, "")
        if esiste:
            prova(f"{percorso.relative_to(radice)} cita la SIL Open Font License",
                  "SIL Open Font License" in percorso.read_text(encoding="utf-8"), "")


def esegui(prova, radice) -> None:
    _prova_tre_famiglie(prova, radice)
    _prova_url_esistono(prova, radice)
    _prova_font_size_solo_variabili(prova, radice)
    _prova_niente_stack_di_sistema_davanti(prova, radice)
    _prova_mono_senza_600(prova, radice)
    _prova_tag_mono_peso(prova, radice)
    _prova_font_synthesis(prova, radice)
    _prova_unicode_range(prova, radice)
    _prova_licenza(prova, radice)


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
