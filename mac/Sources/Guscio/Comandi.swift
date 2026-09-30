// I menu. Vista: le sezioni con ⌘1 ... ⌘6, Aggiorna ⌘R, il compartimento. Voce: Jarvis e
// il riepilogo. Aiuto: la guida. Le voci che la 1.x aveva restano, nei posti di macOS.

import SwiftUI

struct Comandi: Commands {
    @Environment(\.openWindow) private var openWindow
    private let archivio = Archivio.condiviso
    @AppStorage(DimensioneTesto.chiave) private var passoTesto = DimensioneTesto.predefinito

    /// La finestra principale, se e' stata chiusa, si riapre da qui.
    private func registraApertura() {
        let apri = openWindow
        DelegatoApp.apriFinestraSwiftUI = { apri(id: "principale") }
    }

    var body: some Commands {
        let _ = registraApertura()

        CommandGroup(before: .sidebar) {
            ForEach(Sezione.allCases) { s in
                Button(s.titolo) { archivio.vai(s) }
                    .keyboardShortcut(KeyEquivalent(Character(String(s.numero))), modifiers: .command)
            }
            Divider()
            Button(tr("Aggiorna", "Refresh")) { Task { await archivio.aggiorna() } }
                .keyboardShortcut("r", modifiers: .command)
            Button(tr("Aggiorna i dati dalle fonti", "Sync from sources")) {
                DelegatoApp.corrente?.sincronizza()
            }
            .keyboardShortcut("u", modifiers: .command)
            if archivio.compartimenti.attivi {
                Menu(tr("Compartimento", "Compartment")) {
                    ForEach(archivio.compartimenti.elenco ?? [], id: \.self) { nome in
                        Button(nome) { archivio.compartimento = nome }
                    }
                }
            }
            Divider()
            Button(tr("Apri nel browser", "Open in browser")) { DelegatoApp.corrente?.apriNelBrowser() }
            Divider()
        }

        // Dimensione del testo: ⌘+ ingrandisce, ⌘- riduce, ⌘0 torna alla dimensione reale.
        // ⌘= (il tasto piu' senza Maiuscole sulle tastiere americane) lo prende TastiTesto.
        CommandGroup(after: .toolbar) {
            Button(tr("Ingrandisci il testo", "Make Text Bigger")) { passoTesto = DimensioneTesto.limita(passoTesto + 1) }
                .keyboardShortcut("+", modifiers: .command)
                .disabled(passoTesto >= DimensioneTesto.passi.count - 1)
            Button(tr("Riduci il testo", "Make Text Smaller")) { passoTesto = DimensioneTesto.limita(passoTesto - 1) }
                .keyboardShortcut("-", modifiers: .command)
                .disabled(passoTesto <= 0)
            Button(tr("Dimensione reale del testo", "Actual Text Size")) { passoTesto = DimensioneTesto.predefinito }
                .keyboardShortcut("0", modifiers: .command)
            Divider()
        }

        CommandMenu(tr("Voce", "Voice")) {
            Button("Jarvis") { DelegatoApp.corrente?.apriJarvis() }
                .keyboardShortcut("j", modifiers: .command)
            Button(tr("Riepilogo vocale", "Spoken recap")) { DelegatoApp.corrente?.riepilogoVocale() }
                .keyboardShortcut("r", modifiers: [.command, .option])
            Button(tr("Chiedi a Plancia", "Ask Plancia")) { DelegatoApp.corrente?.apriVoce() }
                .keyboardShortcut("d", modifiers: .command)
            Divider()
            Button(tr("Attiva la voce…", "Turn on voice…")) { DelegatoApp.corrente?.chiediPermessi() }
        }

        CommandGroup(replacing: .help) {
            Button(tr("Guida di Plancia", "Plancia Help")) {
                if let u = URL(string: "https://github.com/nerln/plancia#readme") { NSWorkspace.shared.open(u) }
            }
        }
    }
}
