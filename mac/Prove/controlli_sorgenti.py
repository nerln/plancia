#!/usr/bin/env python3
"""Controlli statici sui sorgenti dell'app Mac, per i difetti che non si vedono da un test
di Core: si guardano nel codice. Si lancia con la radice del repo:

    python3 mac/Prove/controlli_sorgenti.py <radice>

Stampa "  ok   ..." e "  NO   ..." per controllo ed esce con 1 se uno e' rosso. Python 3
stdlib, funziona anche senza Xcode."""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

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

# 10. l'Inspector nasce nello stato giusto a ogni sezione: se la colonna fosse la stessa, chi lascia
#     una sezione con l'Inspector aperto la chiuderebbe con l'animazione di AppKit (misurato con
#     sample: NSSplitViewController _collapse:splitViewItem:animated:, 700-1700 milioni di
#     istruzioni a ogni cambio con l'archivio grande)
controlla("l'Inspector della finestra ha l'identita' della sezione (.id dopo .inspector) in Guscio/Ispettore.swift",
          re.search(r"\.inspector\(isPresented:.*?\n\s*\}\s*\n\s*\.id\(", leggi("Guscio/Ispettore.swift"), re.S) is not None)

# 10b. l'Inspector sta sul contenuto vero: su una vista vuota in uno sfondo (Color.clear a
#      dimensione zero) la colonna si apre ma il contenuto non si restringe e ci finisce sotto
#      (visto nelle istantanee di Task, Social e Archivio)
controlla("l'Inspector non e' appeso a una vista vuota (Color.clear) ma al contenuto",
          "Color.clear" not in leggi("Guscio/Ispettore.swift"))

# 11. i commenti citano i banchi di misura che esistono
citazioni = []
for f in sorgenti:
    testo = open(f, encoding="utf-8").read()
    for sbagliata in ("--memoria-misura", "Core/Misura.swift"):
        if sbagliata in testo:
            citazioni.append("%s cita %s" % (os.path.relpath(f, radice), sbagliata))
controlla("nessun commento cita un banco di misura che non esiste (--memoria-misura, Core/Misura.swift)",
          not citazioni, ", ".join(citazioni))

# 12. la Mappa della memoria: gruppi, nomi umani, zoom semantico, 120 Hz, Riduci movimento
motore = leggi("Viste/MemoriaMotore.swift")
disegno = leggi("Viste/MappaDisegno.swift")
vista = leggi("Viste/MemoriaMappa.swift")
controlla("la fisica gira a passi di 1/120 s (uno schermo a 120 Hz vede una posizione nuova a ogni fotogramma)",
          "8_333_333" in motore and "16_666_667" not in motore)
controlla("i nodi portano il titolo umano corto, mai la sigla del file",
          "info.etichette[" in disegno and "info.titoli[" in disegno and not re.search(r"Text\((accorcia\()?info\.nomi", disegno))
controlla("le regioni dei gruppi e i loro nomi si disegnano nel colore stabile del gruppo",
          "info.gruppi[g].colore" in disegno and "func involucro(" in disegno and "func nomiGruppi(" in disegno)
controlla("lo zoom e' semantico: relativo all'inquadratura che mostra tutto (zoomTutto)",
          "foto.zoomTutto" in disegno and "rho" in disegno)
controlla("Riduci movimento arriva alla fisica (camera e luci senza molla, niente inerzia)",
          "accessibilityReduceMotion" in vista and "impostaRiduciMovimento" in vista and ".ridotto(" in vista)
controlla("un clic su un gruppo lo inquadra e c'e' un pulsante per gruppo nella barra",
          ".inquadraGruppo(" in vista and "func scegliGruppo(" in vista and "private func gruppi(" in vista)
controlla("il passaggio del mouse mette in luce il nodo, i vicini e i ponti con una transizione della fisica",
          ".illumina(" in vista and "illumina(" in motore and "luce" in disegno)

# 13. la fisica della Mappa (gruppi a isole, luce, camera, costo del passo): MemoriaFisica.swift
#     si compila da sola con mac/Prove/ProvaFisica.swift, che la prova su grafi con un seme fisso
def prova_fisica():
    if sys.platform != "darwin" or shutil.which("xcrun") is None:
        print("  --   fisica della mappa: saltata, serve macOS con Xcode")
        return True
    lucchetto = os.environ.get("PLANCIA_LUCCHETTO", "/tmp/plancia-swiftc-%d.lock" % os.getuid())
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "prova-fisica")
        comp = subprocess.run(
            [sys.executable, os.path.join(radice, "mac", "lucchetto.py"), lucchetto, "xcrun", "swiftc",
             "-swift-version", "5", "-O", "-parse-as-library", "-target", os.uname().machine + "-apple-macosx26.0",
             os.path.join(radice, "mac", "Sources", "Viste", "MemoriaFisica.swift"),
             os.path.join(radice, "mac", "Prove", "ProvaFisica.swift"), "-o", exe],
            capture_output=True, text=True)
        if comp.returncode != 0:
            print("  NO   la prova della fisica non compila")
            print("\n".join((comp.stdout + comp.stderr).splitlines()[-12:]))
            return False
        run = subprocess.run([exe], capture_output=True, text=True)
        print(run.stdout.rstrip())
        return run.returncode == 0

print("==> la fisica della mappa: gruppi a isole, luce, camera, costo del passo")
if not prova_fisica():
    esito = 1

sys.exit(esito)
