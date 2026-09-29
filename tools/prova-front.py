#!/usr/bin/env python3
"""Il collaudo del front, senza aprire un browser.

    python3 tools/prova-front.py

Qui non si apre nessun browser: si guarda solo il sorgente, con delle regex, e
si cercano le due cose che si sono rotte davvero: una stringa italiana che
nessuno ha tradotto e che quindi compare in mezzo all'inglese, e una vista che
nessuno può raggiungere. La pagina aperta per davvero, con un server acceso e
Chrome headless (`--virtual-time-budget`, per far passare i timer che
altrimenti andrebbero avanti da soli), è tools/prova-video.sh: quello vede un
errore JavaScript o una vista rimasta sul segnaposto del router, che qui,
essendo solo testo, restano invisibili.
"""

import importlib.util
import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
APP = RADICE / "web" / "app.js"
INDEX = RADICE / "web" / "index.html"

# Se una stringa ha una di queste dentro, è italiana e in inglese non ci sta.
ITALIANE = re.compile(
    r"(?:\b(?:il|lo|la|gli|le|un|una|che|per|con|non|del|della|dei|delle|"
    r"sono|hai|nessun|nessuna|ancora|oggi|ieri|adesso|questa|questo)\b|[àèéìòù])",
    re.IGNORECASE)

falliti = []
passati = 0


def prova(nome, condizione, dettaglio=""):
    global passati
    if condizione:
        passati += 1
        # un controllo che qui non si puo' fare (manca un programma, l'ambiente e'
        # un altro) passa lo stesso, con il perche' scritto accanto
        nota = f"  ({dettaglio})" if str(dettaglio).startswith("saltato") else ""
        print(f"  ok   {nome}{nota}")
    else:
        falliti.append(nome)
        print(f"  NO   {nome} {dettaglio}")


def main():
    sorgente = APP.read_text(encoding="utf-8")
    indice = INDEX.read_text(encoding="utf-8")

    # il dizionario inglese: tutte le chiavi che sa tradurre
    inizio = sorgente.index("const EN = {")
    fine = sorgente.index("\n};", inizio)
    dizionario = sorgente[inizio:fine]
    chiavi = set(re.findall(r"'((?:[^'\\]|\\.)*)'\s*:", dizionario))
    chiavi |= set(re.findall(r'"((?:[^"\\]|\\.)*)"\s*:', dizionario))

    # tutte le stringhe passate a T(), che è quello che l'utente legge
    usate = set(re.findall(r"T\('((?:[^'\\]|\\.)*)'\)", sorgente))
    usate |= set(re.findall(r'T\("((?:[^"\\]|\\.)*)"\)', sorgente))
    prova("il front chiama T su qualcosa", len(usate) > 40, f"trovate {len(usate)}")

    orfane = sorted(s for s in usate if s not in chiavi and ITALIANE.search(s))
    prova("nessuna frase italiana senza traduzione", not orfane,
          f"{len(orfane)}: {orfane[:6]}")

    # le viste dichiarate e quelle raggiungibili dal menu
    viste = set(re.findall(r"views\.(\w+)\s*=", sorgente))
    prova("le viste ci sono tutte",
          {"oggi", "lavagna", "progetti", "social", "archivio", "benvenuto"} <= viste,
          str(sorted(viste)))

    nel_menu = set(re.findall(r'href="#/(\w+)"', indice))
    orfane_viste = sorted(v for v in viste
                          if v not in nel_menu and v not in ("benvenuto", "cerca"))
    prova("ogni vista si raggiunge dal menu", not orfane_viste, str(orfane_viste))

    # i data-act usati nel markup devono avere un pezzo di codice che li ascolta
    azioni = set(re.findall(r"data-act=\"(\w[\w-]*)\"", sorgente))
    ascoltate = set(re.findall(r"name === '([\w-]+)'", sorgente))
    sorde = sorted(a for a in azioni if a not in ascoltate)
    prova("ogni bottone ha qualcuno che lo ascolta", not sorde, str(sorde))

    prova("niente template letterali dentro le stringhe tradotte",
          not [s for s in usate if "${" in s])

    # la mappa della memoria
    prova("la vista memoria c'è ed è nel menu",
          "memoria" in viste and "memoria" in nel_menu)

    # I nodi si cliccano perché portano data-memory, che è lo stesso aggancio
    # dell'elenco in Archivio: se sparisce, la mappa diventa un disegno.
    prova("i nodi della mappa aprono la memoria",
          'data-memory="${esc(n.nome)}"' in sorgente)

    # Il tetto all'altezza della mappa non è estetico: senza, la prova del
    # richiamo finisce sotto la piega e non la usa piu' nessuno.
    stile = (RADICE / "web" / "style.css").read_text(encoding="utf-8")
    prova("la mappa ha un tetto in altezza", "max-height: 54vh" in stile)

    # Le classi dei tipi devono esistere nel foglio di stile, altrimenti i nodi
    # escono tutti dello stesso colore e la mappa non dice piu' niente.
    senza_colore = [t for t in ("feedback", "user", "reference", "project")
                    if f".mnodo.{t}" not in stile]
    prova("ogni tipo di memoria ha il suo colore", not senza_colore, str(senza_colore))

    # ---------------------------------------------------------------- scoperta
    # Stessa idea di tools/prova.py: ogni lotto porta le sue prove statiche sul
    # front in un file sotto tools/prove-front/, un modulo per lotto invece di
    # un file unico con un proprietario alla volta. "_" salta, un errore nel
    # modulo conta come fallito con il nome del file e non ferma gli altri.
    cartella_prove = RADICE / "tools" / "prove-front"
    if cartella_prove.is_dir():
        for percorso in sorted(cartella_prove.glob("*.py")):
            if percorso.stem.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"tools.prove_front.{percorso.stem}", percorso)
                modulo = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(modulo)
                modulo.esegui(prova, RADICE)
            except Exception as errore:  # noqa: BLE001 - un lotto non affossa gli altri
                falliti.append(percorso.stem)
                print(f"  NO   {percorso.stem} (errore nel modulo: {errore})")

    print()
    print(f"{passati} passate, {len(falliti)} fallite")
    if falliti:
        print("fallite: " + ", ".join(falliti))
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(main())
