// Voicebox: la voce neurale di Jarvis vive in un'app a parte, e se e' spenta Jarvis resta
// muto (nessuna voce di sistema di qualita' su molti Mac). Qui si sa se c'e', se gira, e la si
// avvia, nascosta e senza rubare il primo piano, quando apri il pannello e non risponde.
//
// Mai in prova: JarvisProva.attivo e PLANCIA_SENZA_AVVIO_APP tengono ferme le prove, che non
// devono aprire app vere. Mai con un indirizzo di Voicebox scelto da te in config.json
// (voicebox_url fuori da questo Mac): li' l'app non e' nostra da aprire.

import AppKit

@MainActor
enum Voicebox {
    static let percorso = "/Applications/Voicebox.app"

    static var installato: Bool { FileManager.default.fileExists(atPath: percorso) }

    static var inEsecuzione: Bool {
        NSWorkspace.shared.runningApplications.contains { $0.bundleURL?.path == percorso }
    }

    /// Per le prove: al posto dell'apertura vera. Se c'e', si puo' avviare anche in modo prova.
    static var finto: (() async -> Bool)?
    /// Ogni quanto si guarda se il server vede la voce neurale, e quante volte.
    static var intervallo: TimeInterval = 3
    static var tentativi = 28

    /// Si puo' provare ad avviarlo: c'e', non siamo in prova, l'indirizzo e' quello locale.
    static var puoAvviare: Bool {
        if finto != nil { return true }
        if JarvisProva.attivo { return false }
        if ProcessInfo.processInfo.environment["PLANCIA_SENZA_AVVIO_APP"] != nil { return false }
        if let u = Casa.config["voicebox_url"] as? String, !u.isEmpty,
           !u.contains("127.0.0.1"), !u.contains("localhost") { return false }
        return installato
    }

    /// Lo apre nascosto, senza attivarlo. Vero se e' gia' aperto o se il sistema ha accettato.
    static func avvia() async -> Bool {
        if let f = finto { return await f() }
        if inEsecuzione { return true }
        let conf = NSWorkspace.OpenConfiguration()
        conf.activates = false
        conf.hides = true
        conf.addsToRecentItems = false
        do {
            _ = try await NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: percorso), configuration: conf)
            Log.write("jarvis: Voicebox avviato (nascosto)")
            return true
        } catch {
            Log.write("jarvis: Voicebox non si avvia: \(error.localizedDescription)")
            return false
        }
    }
}
