// "Salva una schermata" (menu, plancia://screenshot) e plancia://pdf: il PNG o il PDF
// della finestra principale in ~/.plancia/shots.

import AppKit

extension DelegatoApp {
    private func cartellaScatti() -> URL {
        let dir = Conf.dataDir.appendingPathComponent("shots")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func nomeScatto(_ estensione: String) -> URL {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd-HHmmss"
        return cartellaScatti().appendingPathComponent("plancia-\(f.string(from: Date())).\(estensione)")
    }

    /// Salva la finestra in un PNG. Serve per gli screenshot dei post e per vedere come e'
    /// venuta senza essere davanti al Mac.
    @objc func schermata() {
        guard let window = finestraPrincipale() else {
            apriFinestra()
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.schermata() }
            return
        }
        // Se davanti c'e' un'app a tutto schermo la finestra sta in un altro Spazio: la si
        // porta sullo Spazio corrente per il tempo dello scatto e poi si rimette com'era.
        let comportamento = window.collectionBehavior
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
        attendiVisibile(window, tentativi: 24) {
            if let png = Cattura.png(window) {
                let dest = self.nomeScatto("png")
                try? png.write(to: dest)
                Log.write("schermata salvata: \(dest.path)")
            } else {
                Log.write("schermata fallita")
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                window.collectionBehavior = comportamento
            }
        }
    }

    /// Si aspetta che il sistema dichiari la finestra visibile, non un tempo a caso.
    private func attendiVisibile(_ window: NSWindow, tentativi: Int, poi: @escaping () -> Void) {
        if tentativi <= 0 || window.occlusionState.contains(.visible) {
            return DispatchQueue.main.asyncAfter(deadline: .now() + 0.45, execute: poi)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            self.attendiVisibile(window, tentativi: tentativi - 1, poi: poi)
        }
    }

    func scattaPDF() {
        guard let window = finestraPrincipale(), let dati = Cattura.pdf(window) else {
            return Log.write("pdf fallito")
        }
        let dest = nomeScatto("pdf")
        try? dati.write(to: dest)
        Log.write("pdf salvato: \(dest.path)")
    }
}
