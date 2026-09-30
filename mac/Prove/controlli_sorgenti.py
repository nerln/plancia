#!/usr/bin/env python3
"""Controlli statici sui sorgenti dell'app Mac, per i difetti che non si vedono da un test
di Core: si guardano nel codice. Si lancia con la radice del repo:

    python3 mac/Prove/controlli_sorgenti.py <radice>

Stampa "  ok   ..." e "  NO   ..." per controllo ed esce con 1 se uno e' rosso. Python 3
stdlib, funziona anche senza Xcode."""

import glob
import os
import re
import sys

radice = sys.argv[1] if len(sys.argv) > 1 else "."
sorgenti = sorted(glob.glob(os.path.join(radice, "mac", "Sources", "**", "*.swift"), recursive=True))
esito = 0


def controlla(nome, ok, dettaglio=""):
    global esito
    print(("  ok   " if ok else "  NO   ") + nome + ((" " + dettaglio) if dettaglio and not ok else ""))
    if not ok:
        esito = 1


def leggi(rel):
    with open(os.path.join(radice, "mac", "Sources", rel), encoding="utf-8") as f:
        return f.read()


# 1. gli accenti veri nelle stringhe: e', puo', piu', gia', Accessibilita' e simili sono
#    apostrofi al posto delle lettere accentate (il resto dell'app ha gli accenti)
PAROLE = r"(?:e|E|puo|piu|gia|cosi|perche|Accessibilita|verra|sara|fara|dara|potra|attivita|velocita|qualita)"
brutte = []
for f in sorgenti:
    for n, riga in enumerate(open(f, encoding="utf-8"), 1):
        if riga.strip().startswith("//") or '"' not in riga:
            continue
        pezzi = riga.split('"')
        for i in range(1, len(pezzi), 2):          # solo dentro le virgolette
            if re.search(r"(?<![A-Za-zÀ-ÿ])" + PAROLE + r"'(?![A-Za-zÀ-ÿ])", pezzi[i]):
                brutte.append("%s:%d" % (os.path.relpath(f, radice), n))
controlla("nessun apostrofo al posto di un accento nelle stringhe (e', puo', Accessibilita')",
          not brutte, ", ".join(brutte[:6]))

# 2. la dimensione del testo e' di ⌘+ ⌘- ⌘0 ovunque sia il puntatore: la mappa della memoria
#    non deve prendersi quei tasti
mappa = leggi("Viste/MemoriaMappa.swift")
monitor = mappa[mappa.index("addLocalMonitorForEvents"):]
monitor = monitor[:monitor.index("return nil\n            }") + 20]
controlla("la mappa lascia passare ogni tasto con ⌘, ⌥ o ⌃ (sono comandi di menu)",
          "[.command, .option, .control]" in monitor and "flag.contains(.command)" not in monitor)
controlla("la mappa non zooma con i tasti mentre si scrive in un campo di testo", "firstResponder is NSText" in monitor)
controlla("nessun altro punto usa il puntatore sulla mappa per rubare ⌘+", "puntatoreSopra" not in leggi("Tema/DimensioneTesto.swift"))

# 3. la legenda e i controlli della mappa stanno in una barra sotto, non sopra i nodi
controlla("la legenda della mappa non e' piu' sovrapposta ai nodi",
          "overlay(alignment: .bottomLeading) { legenda" not in mappa and "private func barra(" in mappa)
controlla("le etichette non lasciano piu' un vuoto fisso dove stava la legenda", "size.height - 150" not in mappa)

# 4. le colonne delle tabelle non superano lo spazio accanto all'Inspector a 125% (1024 pt
#    di layout, meno la barra laterale e l'Inspector: ~500)
for rel in ("Viste/Task.swift", "Viste/Archivio.swift"):
    testo = leggi(rel)
    blocchi = re.split(r"\bTable\(", testo)[1:]
    for k, b in enumerate(blocchi, 1):
        b = b.split("alternatingRowBackgrounds")[0]
        minimi = [int(m) for m in re.findall(r"\.width\(min: (\d+)", b)] + [int(m) for m in re.findall(r"\.width\((\d+)\)", b)]
        # ogni colonna ha ~12 pt di margine suo: minimi + margini devono stare in ~500 pt
        totale = sum(minimi) + 12 * len(minimi)
        controlla("%s, tabella %d: minimi + margini delle colonne (%d) stanno accanto all'Inspector a 125%%"
                  % (rel.split("/")[-1], k, totale), totale <= 500)

# 5. i collegamenti nel Legno sono d'ottone: nessun buttonStyle(.link) fuori dal modificatore
fuori = []
for f in sorgenti:
    if f.endswith("Tema/Stile.swift"):
        continue
    if ".buttonStyle(.link)" in open(f, encoding="utf-8").read():
        fuori.append(os.path.relpath(f, radice))
controlla("nessun collegamento blu di sistema fuori dal modificatore .collegamento()", not fuori, ", ".join(fuori))

# 6. Jarvis non avvia piu' nessuna app di voce: la voce neurale e' un servizio a parte (Kokoro)
controlla("Jarvis non apre Voicebox ne' nessun'altra app di voce",
          not os.path.exists(os.path.join(radice, "mac", "Sources", "Sistema", "JarvisVoicebox.swift"))
          and "avviaVoicebox" not in leggi("Sistema/JarvisModello.swift")
          and "Voicebox.avvia" not in leggi("Sistema/JarvisModello.swift")
          and "openApplication" not in "".join(open(f, encoding="utf-8").read() for f in sorgenti if "Jarvis" in f))

# 7. il banco dei fotogrammi della mappa e' nel repo
controlla("il banco dei fotogrammi della mappa e' nell'app (--mappa-misura)",
          "--mappa-misura" in leggi("Sistema/MisuraMappa.swift") and "MisuraMappa" in leggi("Sistema/Delegato.swift"))

# 8. il cambio di sezione non ricostruisce la barra degli strumenti ne' l'Inspector: ce n'e' uno
#    solo, in Guscio, con gli stessi elementi in ogni sezione (misurato: un .toolbar o un
#    .inspector per vista costavano 30-60 e 10-25 ms a ogni cambio)
def fuori_guscio(cerca):
    trovati = []
    for f in sorgenti:
        rel = os.path.relpath(f, radice)
        if "/Guscio/" in rel:
            continue
        for n, riga in enumerate(open(f, encoding="utf-8"), 1):
            if riga.strip().startswith("//"):
                continue
            if re.search(cerca, riga):
                trovati.append("%s:%d" % (rel, n))
    return trovati

t = fuori_guscio(r"\.toolbar\s*[({]")
controlla("nessuna vista ha una barra degli strumenti sua: c'e' solo quella della finestra (Guscio)", not t, ", ".join(t[:6]))
i = fuori_guscio(r"\.inspector\s*\(")
controlla("nessuna vista ha un Inspector suo: c'e' solo quello della finestra (Guscio/Ispettore.swift)", not i, ", ".join(i[:6]))

# 9. nessun interruttore di esperimento dimenticato
resti = [os.path.relpath(f, radice) for f in sorgenti if re.search(r"\bSper\.|PLANCIA_SP\b", open(f, encoding="utf-8").read())]
controlla("nessun interruttore di esperimento (Sper, PLANCIA_SP) nei sorgenti", not resti, ", ".join(resti))

sys.exit(esito)
