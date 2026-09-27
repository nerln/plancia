"""Prove per LOTTO-L4-SITO: sito, versione e workflow di pubblicazione.

Guarda solo file di testo (site/index.html, i tre file di versione,
.github/workflows/pages.yml), niente archivio: non serve una `PLANCIA_HOME`
diversa da quella che `tools/prova.py` fissa già per tutta la suite.

L'em dash nei testi pubblici e il numero di prove dichiarato dal README sono
già controllati da `tools/prova.py` stesso (vedi il blocco "stile" e
"readme"): non li si ripete qui.
"""

import re
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent

IMG_SRC = re.compile(r'<img\s[^>]*\bsrc="([^"]+)"')


def sezione(nome):
    """Il corpo della sezione marcata `<!-- nome -->`, fino al prossimo
    commento di sezione. Le sezioni di LOTTO-L4-SITO usano tutte la stessa
    forma di commento (una riga di trattini e il nome in mezzo)."""
    return re.compile(r"<!--[- ]*" + re.escape(nome) + r"[- ]*-->(.*?)(?=<!--[- ]*\w)", re.S)


def esegui(prova):
    indice = RADICE / "site" / "index.html"
    testo = indice.read_text(encoding="utf-8") if indice.exists() else ""
    prova("site/index.html esiste", bool(testo))
    if not testo:
        return

    # ------------------------------------------------------- immagini citate
    riferite = IMG_SRC.findall(testo)
    prova("il sito cita almeno un'immagine", bool(riferite))
    mancanti = []
    for src in riferite:
        if src.startswith(("http:", "https:", "data:")):
            continue
        if not (RADICE / "site" / src).exists():
            mancanti.append(src)
    prova("ogni <img src> di site/index.html esiste in site/img",
          not mancanti, str(mancanti))

    # ---------------------------------------- la sezione riepilogo, l'immagine
    trovata = sezione("riepilogo").search(testo)
    prova("la sezione riepilogo si trova (marcata dal commento HTML)",
          trovata is not None)
    if trovata:
        corpo = trovata.group(1)
        prova("la sezione riepilogo non cita più l'immagine projects",
              "img/projects.png" not in corpo, corpo[:200])
        prova("la sezione riepilogo non cita l'immagine di Prossimi (today.png)",
              "img/today.png" not in corpo, corpo[:200])
        prova("la sezione riepilogo cita davvero l'immagine del riepilogo (recap.png)",
              "img/recap.png" in corpo, corpo[:200])

    # --------------------------------------- le sezioni Prossimi e Riprendi
    # LOTTO-L4-SITO punto 1: al posto della vecchia "lavagna" (che vendeva il
    # lancio) vanno una sezione Prossimi (con lo screenshot del pannello, gia'
    # in img/today.png) e una sezione Riprendi (con img/board.png, la vista
    # "Tutti i task"). Rosso sulla base, dove nessuna delle due esisteva.
    trovata_prossimi = sezione("prossimi").search(testo)
    prova("la sezione Prossimi si trova (marcata dal commento HTML)",
          trovata_prossimi is not None)
    if trovata_prossimi:
        corpo = trovata_prossimi.group(1)
        prova("la sezione Prossimi cita l'immagine del pannello Prossimi (today.png)",
              "img/today.png" in corpo, corpo[:200])

    trovata_riprendi = sezione("riprendi").search(testo)
    prova("la sezione Riprendi si trova (marcata dal commento HTML)",
          trovata_riprendi is not None)
    if trovata_riprendi:
        corpo = trovata_riprendi.group(1)
        prova("la sezione Riprendi cita l'immagine di Tutti i task (board.png)",
              "img/board.png" in corpo, corpo[:200])

    # -------------------------------------------------------------- gergo
    prova("\"20 tool\" non compare nel sito (sono 7 schemi dietro un dispatcher)",
          "20 tool" not in testo and "20 strumenti" not in testo
          and "twenty tools" not in testo.lower())
    prova("\"lavagna\" non compare piu' nel sito (rinominata Tutti i task/All tasks)",
          "lavagna" not in testo.lower())

    # Il lancio headless (LOTTO-L4-SITO punto 1) resta citato una volta sola
    # per lingua, come "In background"/"In the background": non piu' la
    # funzione centrale del sito, un'opzione secondaria dietro Riprendi.
    prova("\"In background\" compare esattamente una volta (it)",
          testo.count("In background") == 1, testo.count("In background"))
    prova("\"In the background\" compare esattamente una volta (en)",
          testo.count("In the background") == 1, testo.count("In the background"))

    # ----------------------------------------------------------- le versioni
    # Niente `tomllib` (Python 3.11+): questo lotto gira su 3.9, quindi la
    # riga `version = "..."` si legge con una regex invece che con un parser
    # TOML vero, che qui sarebbe una dipendenza in più per un file di tre righe.
    versioni = {}
    pyproject = RADICE / "pyproject.toml"
    if pyproject.exists():
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
        versioni["pyproject.toml"] = m.group(1) if m else None

    init_py = RADICE / "plancia" / "__init__.py"
    if init_py.exists():
        m = re.search(r'__version__\s*=\s*"([^"]+)"', init_py.read_text(encoding="utf-8"))
        versioni["plancia/__init__.py"] = m.group(1) if m else None

    build_sh = RADICE / "mac" / "build.sh"
    if build_sh.exists():
        m = re.search(r'^VERSIONE="([^"]+)"', build_sh.read_text(encoding="utf-8"), re.M)
        versioni["mac/build.sh"] = m.group(1) if m else None

    prova("le tre versioni si leggono tutte", all(versioni.values()), str(versioni))
    prova("le tre versioni coincidono", len(set(versioni.values())) == 1, str(versioni))

    # La versione attesa non e' scritta qui a mano (si fisserebbe a 1.1.0 e
    # bloccherebbe il primo rilascio successivo, vedi la critica del 26/09):
    # si legge dalla prima voce "## X.Y.Z" di docs/NOVITA.md, che e' la fonte
    # vera del numero corrente (piu'-recente-in-cima).
    novita = RADICE / "docs" / "NOVITA.md"
    attesa = None
    if novita.exists():
        m = re.search(r"(?m)^##\s+(\d+\.\d+\.\d+)\b", novita.read_text(encoding="utf-8"))
        attesa = m.group(1) if m else None
    prova("docs/NOVITA.md dichiara una versione corrente (prima voce '## X.Y.Z')",
          attesa is not None)
    if attesa:
        prova(f"le tre versioni sono quella dichiarata da NOVITA.md ({attesa})",
              set(versioni.values()) == {attesa}, str(versioni))

    # ------------------------------------------------------------- pages.yml
    pages = RADICE / ".github" / "workflows" / "pages.yml"
    if pages.exists():
        testo_pages = pages.read_text(encoding="utf-8")
        # Solo il blocco `push:` non deve avere `branches` (niente deploy a
        # ogni push su main): un futuro `pull_request: branches: [...]`
        # legittimo altrove nel file non deve far fallire questa prova.
        blocco_push = re.search(r"(?m)^\s*push:\s*\n((?:^\s{4,}.*\n?)*)", testo_pages)
        prova("pages.yml ha un blocco 'push'", blocco_push is not None, testo_pages)
        if blocco_push:
            prova("pages.yml non ha 'branches' sotto push (niente deploy a ogni push su main)",
                  "branches" not in blocco_push.group(1), blocco_push.group(1))
        prova("pages.yml parte su workflow_dispatch",
              "workflow_dispatch" in testo_pages)
        prova("pages.yml parte sui tag v*",
              re.search(r"tags:\s*\[?\s*['\"]v\*", testo_pages) is not None)
    else:
        prova("pages.yml esiste", False)

    # ------------------------------------------------- la scala del hero
    # LOTTO-L5-RIFINITURA punto 2: il commento in cima a site/style.css dice
    # che .apertura h1, .apertura .sotto e .patto li stanno sulla scala
    # --t-* (via --t-hero/--t-lead per le prime due, --t-lg per la terza) e
    # non hanno più nessun font-size scritto a mano. Rossa sulla base, dove
    # nessuna prova lo controllava e una regressione a clamp()/px sarebbe
    # passata inosservata.
    foglio_sito = RADICE / "site" / "style.css"
    testo_sito = foglio_sito.read_text(encoding="utf-8") if foglio_sito.exists() else ""
    prova("site/style.css esiste", bool(testo_sito))
    if testo_sito:
        for selettore, nome in (
            (r"\.apertura h1", ".apertura h1"),
            (r"\.apertura \.sotto", ".apertura .sotto"),
            (r"\.patto li", ".patto li"),
        ):
            m = re.search(selettore + r"\s*\{([^}]*)\}", testo_sito)
            prova(f"site/style.css: la regola {nome} si trova", m is not None)
            if not m:
                continue
            corpo = m.group(1)
            fs = re.search(r"font-size:\s*([^;]+);", corpo)
            prova(f"site/style.css: {nome} ha un font-size", fs is not None, corpo.strip())
            if fs:
                valore = fs.group(1).strip()
                prova(f"site/style.css: {nome} usa var(--t-...) per font-size, "
                      "non un clamp() o una taglia scritta a mano",
                      valore.startswith("var(--t-"), valore)
