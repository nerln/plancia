// Plancia 2.0 per macOS: il punto d'ingresso. Una finestra SwiftUI con barra laterale,
// le Impostazioni (⌘,) e i menu. Tutto quello che la 1.x faceva oltre alla finestra
// (avvio del server, Jarvis, barra dei menu, plancia://) sta in Sistema/ ed e' collegato
// da DelegatoApp con NSApplicationDelegateAdaptor.

import SwiftUI

@main
struct PlanciaApp: App {
    @NSApplicationDelegateAdaptor(DelegatoApp.self) private var delegato

    @AppStorage(DimensioneTesto.chiave) private var passoTesto = DimensioneTesto.predefinito

    init() { TastiTesto.installa() }

    var body: some Scene {
        Window("Plancia", id: "principale") {
            Radice()
                .environment(Archivio.condiviso)
                .environment(Lingua.condivisa)
                .frame(minWidth: 900 * DimensioneTesto.fattore(passoTesto), minHeight: 560 * DimensioneTesto.fattore(passoTesto))
        }
        .defaultSize(width: 1180, height: 780)
        .commands { Comandi() }

        Settings {
            Impostazioni()
                .environment(Lingua.condivisa)
        }
    }
}
