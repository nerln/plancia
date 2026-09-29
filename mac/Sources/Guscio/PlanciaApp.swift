// Plancia 2.0 per macOS: il punto d'ingresso. Una finestra SwiftUI con barra laterale,
// le Impostazioni (⌘,) e i menu. Tutto quello che la 1.x faceva oltre alla finestra
// (avvio del server, Jarvis, barra dei menu, plancia://) sta in Sistema/ ed e' collegato
// da DelegatoApp con NSApplicationDelegateAdaptor.

import SwiftUI

@main
struct PlanciaApp: App {
    @NSApplicationDelegateAdaptor(DelegatoApp.self) private var delegato

    var body: some Scene {
        Window("Plancia", id: "principale") {
            Radice()
                .environment(Archivio.condiviso)
                .environment(Lingua.condivisa)
                .frame(minWidth: 900, minHeight: 560)
        }
        .defaultSize(width: 1180, height: 780)
        .commands { Comandi() }

        Settings {
            Impostazioni()
                .environment(Lingua.condivisa)
        }
    }
}
