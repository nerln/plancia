// Il backend, tenuto vivo: se il server non risponde, l'app lo avvia; all'uscita
// ferma soltanto quello che ha avviato lei.

import Foundation

// MARK: - il backend, tenuto vivo

final class Backend {
    private var process: Process?
    private(set) var avviatoDaNoi = false

    func ensureRunning(_ done: @escaping (Bool) -> Void) {
        API.alive { up in
            if up { return done(true) }
            guard let exe = Conf.executable else { return done(false) }
            let p = Process()
            p.executableURL = URL(fileURLWithPath: exe)
            p.arguments = ["serve"]
            p.standardOutput = FileHandle.nullDevice
            p.standardError = FileHandle.nullDevice
            do { try p.run() } catch { return done(false) }
            self.process = p
            self.avviatoDaNoi = true
            self.attendi(tentativi: 25, done: done)
        }
    }

    private func attendi(tentativi: Int, done: @escaping (Bool) -> Void) {
        if tentativi <= 0 { return done(false) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            API.alive { up in
                if up { done(true) } else { self.attendi(tentativi: tentativi - 1, done: done) }
            }
        }
    }

    func stopIfOurs() {
        // Se il backend gira per conto suo (launchd) non è compito nostro spegnerlo.
        if avviatoDaNoi, let p = process, p.isRunning { p.terminate() }
    }
}
