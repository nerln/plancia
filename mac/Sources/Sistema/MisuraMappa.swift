// Il banco dei fotogrammi della mappa della memoria, dentro l'app cosi' chi clona il repo lo
// rifa' e ottiene gli stessi numeri delle note:
//
//   Plancia.app/Contents/MacOS/Plancia --mappa-misura [--mappa-nodi N] [--mappa-fisso]
//
// Apre la VistaMappa vera in una finestra vera da 1100x760 e la fa lavorare: assestamento,
// trascinamento di un nodo, i tre livelli, zoom a passi, pan continuo, poi una scena ferma
// (che non deve disegnare niente). Per ogni fase stampa i fotogrammi (fps, ms di disegno
// medio e massimo, disegni oltre 16,7 ms), il lavoro del thread principale e i passi della
// fisica. I gesti sono simulati via ModelloMappa, non con il mouse.
//
// I dati: N schede sintetiche con legami (di serie 260, seme fisso: due esecuzioni danno lo
// stesso grafo), niente server e niente archivio. Con --mappa-dal-server legge invece la
// memoria del server della casa indicata da $PLANCIA_HOME (sola lettura).

import AppKit
import SwiftUI

@MainActor
enum MisuraMappa {
    static var attiva: Bool { CommandLine.arguments.contains("--mappa-misura") }

    private static let cron = CronometroCiclo()

    private static func valore(_ nome: String) -> String? {
        guard let i = CommandLine.arguments.firstIndex(of: nome), i + 1 < CommandLine.arguments.count else { return nil }
        return CommandLine.arguments[i + 1]
    }

    // MARK: dati sintetici

    /// Un generatore con seme: senza, due esecuzioni non sarebbero confrontabili.
    private struct Seme {
        var s: UInt64
        mutating func prossimo() -> UInt64 {
            s = s &* 6364136223846793005 &+ 1442695040888963407
            return s >> 33
        }
        mutating func fra(_ n: Int) -> Int { Int(prossimo() % UInt64(max(n, 1))) }
    }

    /// N schede di quattro tipi, ognuna con 1-4 legami verso altre (i piu' verso pochi hub,
    /// come in una memoria vera), e qualche scheda senza legami.
    static func schedeSintetiche(_ n: Int) -> [Scheda] {
        var r = Seme(s: 23)
        let tipi = ["user", "feedback", "project", "reference"]
        let hub = max(4, n / 40)
        var righe: [[String: Any]] = []
        for i in 0..<n {
            var legami: [String] = []
            if r.fra(12) != 0 {
                for _ in 0...r.fra(4) {
                    let verso = r.fra(3) == 0 ? r.fra(hub) : r.fra(n)
                    if verso != i { legami.append("scheda-\(verso)") }
                }
            }
            let dati = (try? JSONSerialization.data(withJSONObject: legami)) ?? Data("[]".utf8)
            righe.append(["id": i + 1, "name": "scheda-\(i)", "type": tipi[i % tipi.count],
                          "description": "Scheda sintetica numero \(i)",
                          "updatedAt": "2026-09-\(String(format: "%02d", 1 + i % 28))T10:00:00Z",
                          "links": String(data: dati, encoding: .utf8) ?? "[]"])
        }
        guard let d = try? JSONSerialization.data(withJSONObject: righe),
              let schede = try? JSONDecoder().decode([Scheda].self, from: d) else { return [] }
        return schede
    }

    // MARK: banco

    private static func attendi(_ cond: () -> Bool, _ secondi: Double) async {
        let fine = Date().addingTimeInterval(secondi)
        while Date() < fine && !cond() { try? await Task.sleep(nanoseconds: 20_000_000) }
    }

    private static func riporta(_ nome: String, _ m: ModelloMappa) {
        let (d, fps, medio, max, lenti) = m.misura.riassunto()
        let (passi, pm, pmax) = m.ponte?.misure() ?? (0, 0, 0)
        let busy = cron.msCpu(cron.occupato), mx = cron.msCpu(cron.massimo), lg = cron.lunghi
        cron.azzera()
        let riga = String(format: "  %@ disegni=%4d fps=%5.1f disegno medio=%5.2f max=%6.2f >16.7ms=%d | main busy=%6.0fms max giro=%6.1fms giri lunghi=%d | fisica passi=%d medio=%.3f max=%.3f\n",
                          nome.padding(toLength: 28, withPad: " ", startingAt: 0), d, fps, medio, max, lenti, busy, mx, lg, passi, pm, pmax)
        FileHandle.standardOutput.write(Data(riga.utf8))
    }

    static func avvia() {
        Task { await esegui() }
    }

    private static func esegui() async {
        // la finestra principale dell'app non serve e falserebbe la misura
        for _ in 0..<40 {
            if let w = DelegatoApp.corrente?.finestraPrincipale() { w.orderOut(nil); break }
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        let a = Archivio.condiviso
        var dati: DatiMemoria
        if CommandLine.arguments.contains("--mappa-dal-server") {
            await a.carica(.memoria)
            dati = DatiMemoria(schede: a.schede, mappa: a.mappa)
        } else {
            let n = max(8, Int(valore("--mappa-nodi") ?? "260") ?? 260)
            dati = DatiMemoria(schede: schedeSintetiche(n), mappa: nil)
        }
        let legami = dati.vicini.values.reduce(0) { $0 + $1.count } / 2
        FileHandle.standardOutput.write(Data("nodi=\(dati.fatti.count) legami=\(legami)\n".utf8))
        guard dati.fatti.count >= 8 else { FileHandle.standardError.write(Data("memoria troppo piccola\n".utf8)); exit(1) }

        cron.installa()
        let vista = VistaMappa(dati: dati, scelto: nil).environment(a).frame(width: 1100, height: 760)
        let w = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 1100, height: 760),
                         styleMask: [.titled], backing: .buffered, defer: false)
        w.contentView = NSHostingView(rootView: vista)
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        await attendi({ ModelloMappa.attivo?.motore != nil && ModelloMappa.attivo?.pronto == true }, 10)
        guard let m = ModelloMappa.attivo, m.ponte != nil, let hub = m.info?.hub else {
            FileHandle.standardError.write(Data("la mappa non è partita\n".utf8)); exit(1)
        }
        cron.azzera(); m.misura.azzera()
        await attendi({ !m.inMoto }, 20)
        riporta("assestamento iniziale", m)

        m.misura.azzera(); cron.azzera()
        let centro = m.ponte!.foto().pos[hub]
        m.manda(.iniziaTrascino(hub, centro))
        for k in 0..<240 {
            let t = Float(k) / 240 * 2 * .pi * 2
            m.manda(.trascina(centro + P2(cos(t), sin(t)) * 160))
            try? await Task.sleep(nanoseconds: 16_000_000)
        }
        m.manda(.rilascia)
        await attendi({ !m.inMoto }, 20)
        riporta("trascinamento hub+assest.", m)

        let nome = m.info!.nomi[hub]
        for (liv, et) in [(LivelloMappa.uno, "livello 1"), (.due, "livello 2"), (.tutto, "livello Tutto")] {
            m.misura.azzera(); cron.azzera()
            m.allinea(livello: liv, centro: nome, senzaAnimazione: false, zoomScena: false)
            try? await Task.sleep(nanoseconds: 50_000_000)
            await attendi({ !m.inMoto }, 20)
            riporta("transizione " + et, m)
        }

        m.misura.azzera(); cron.azzera()
        for _ in 0..<4 { m.zoomPasso(1.4); try? await Task.sleep(nanoseconds: 250_000_000) }
        for _ in 0..<4 { m.zoomPasso(1 / 1.4); try? await Task.sleep(nanoseconds: 250_000_000) }
        await attendi({ !m.inMoto }, 20)
        riporta("zoom 4 passi e ritorno", m)

        m.misura.azzera(); cron.azzera()
        for k in 0..<180 {
            m.manda(.panora(P2(sin(Float(k) / 20) * 9, cos(Float(k) / 20) * 6)))
            try? await Task.sleep(nanoseconds: 16_000_000)
        }
        await attendi({ !m.inMoto }, 20)
        riporta("pan continuo", m)

        m.manda(.inquadra(subito: false))
        await attendi({ !m.inMoto }, 20)
        try? await Task.sleep(nanoseconds: 300_000_000)
        m.misura.azzera(); cron.azzera()
        try? await Task.sleep(nanoseconds: 1_500_000_000)
        let (d, _, _, _, _) = m.misura.riassunto()
        FileHandle.standardOutput.write(Data("  disegni in 1,5 s a scena ferma: \(d)  (inMoto=\(m.inMoto)) main busy=\(Int(cron.msCpu(cron.occupato)))ms\n".utf8))
        exit(0)
    }
}
