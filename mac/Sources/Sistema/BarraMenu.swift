// La voce nella barra dei menu: le stesse azioni della 1.x.

import AppKit

extension DelegatoApp {
    func costruisciMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "location.north.circle",
                                   accessibilityDescription: "Plancia")
            button.image?.isTemplate = true
        }
        let menu = NSMenu()
        menu.addItem(voceMenu("Jarvis  ⌥Spazio", #selector(apriJarvis), "j"))
        menu.addItem(voceMenu("Riepilogo vocale", #selector(riepilogoVocale), "r"))
        menu.addItem(voceMenu("Chiedi a Plancia", #selector(apriVoce), "d"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(voceMenu("Apri Plancia", #selector(apriFinestra), "o"))
        menu.addItem(voceMenu("Apri nel browser", #selector(apriNelBrowser), "b"))
        menu.addItem(voceMenu("Aggiorna i dati", #selector(sincronizza), "u"))
        menu.addItem(voceMenu("Salva una schermata", #selector(schermata), "s"))
        // Compare solo finche' serve: una voce di menu che non serve piu' e' rumore.
        if !AscoltoContinuo.stato.micro || !AscoltoContinuo.stato.voce {
            menu.addItem(NSMenuItem.separator())
            menu.addItem(voceMenu("Attiva la voce…", #selector(chiediPermessi), ""))
        }
        menu.addItem(NSMenuItem.separator())
        menu.addItem(voceMenu("Esci da Plancia", #selector(esci), "q"))
        statusItem.menu = menu
    }

    private func voceMenu(_ titolo: String, _ sel: Selector, _ tasto: String) -> NSMenuItem {
        let item = NSMenuItem(title: titolo, action: sel, keyEquivalent: tasto)
        item.target = self
        return item
    }

    @objc func apriVoce() { voce.apri() }
    @objc func apriJarvis() { jarvis.apri() }
    @objc func riepilogoVocale() { voce.apriEriepiloga() }

    /// La dashboard web resta come ripiego: la stessa che serve al browser.
    @objc func apriNelBrowser() {
        if let u = URL(string: Conf.base) { NSWorkspace.shared.open(u) }
    }

    /// Chiede al server di rileggere le fonti e poi rilegge quello che l'app mostra.
    @objc func sincronizza() {
        Task { @MainActor in
            await Archivio.condiviso.sincronizza()
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            await Archivio.condiviso.aggiorna()
        }
    }
}
