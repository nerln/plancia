// La misura della velocita' dell'app: quanto tempo il thread principale resta occupato
// mentre si cambia sezione, si ricarica, si scrive, si cerca e mentre il ciclo di
// sottofondo gira. Il thread principale e' quello che disegna: se sta occupato piu' di
// 16 ms di seguito, un fotogramma salta e l'utente lo vede come uno scatto.
//
//   PLANCIA_HOME=<casa di prova> Plancia.app/Contents/MacOS/Plancia --misura [--misura-out <file>]
//       [--misura-solo sezione|ricarica|scrittura|ricerca|sottofondo] [--misura-ripeti N]
//       [--misura-sezioni task,social] [--misura-giri N]   (solo queste sezioni, N giri: per `sample`)
//   (--misura-ripeti ripete la ricerca N volte: serve a campionarla con `sample`)
//
// Apre la finestra vera, visita le sezioni con la stessa strada dell'utente (le viste
// SwiftUI vere, non un Store isolato) e per ogni passo riporta:
//   occupato  ms di CPU del thread principale spesi nel ciclo degli eventi, dal passo
//             fino a 400 ms dopo che la rete e' tornata quieta (e' il costo vero:
//             decodifica sul principale, assegnazioni, calcoli delle viste, disegno)
//   massimo   il giro piu' lungo del ciclo degli eventi, in CPU (lo scatto peggiore)
//   parete    lo stesso giro in tempo di parete (con la macchina carica e' piu' grande)
//   lunghi    quanti giri hanno superato 16 ms di CPU (fotogrammi persi, a 60 Hz)
//   rete      ms fino a che nessuna richiesta e' piu' in volo
//   richieste e KB scaricati
// Non avvia il server: usa quello che trova sulla porta di $PLANCIA_HOME/config.json.
// Non avvia la barra dei menu, Jarvis o le notifiche.

import AppKit

/// Il cronometro del ciclo degli eventi: un osservatore all'inizio e uno alla fine di ogni
/// giro (dopo il commit di Core Animation), sul thread principale.
///
/// Il tempo si misura due volte: in tempo di CPU del thread principale (quanto lavoro ha
/// fatto davvero, non cambia se la macchina e' sotto pressione) e in tempo di parete (quanto
/// e' passato, che con la macchina carica include le volte in cui il sistema l'ha fermato).
/// I numeri dei rapporti sono di CPU.
final class CronometroCiclo: @unchecked Sendable {
    private var partenza: UInt64 = 0
    private var partenzaCpu: UInt64 = 0
    private var dentro = false
    private(set) var occupato: UInt64 = 0      // CPU, in nanosecondi
    private(set) var massimo: UInt64 = 0       // CPU, il giro piu' lungo
    private(set) var massimoParete: UInt64 = 0 // parete, il giro piu' lungo
    private(set) var lunghi = 0                // giri di CPU oltre 16 ms
    private var osservatori: [CFRunLoopObserver] = []
    private let base: mach_timebase_info_data_t = {
        var b = mach_timebase_info_data_t()
        mach_timebase_info(&b)
        return b
    }()

    func ms(_ t: UInt64) -> Double { Double(t) * Double(base.numer) / Double(base.denom) / 1_000_000 }
    func msCpu(_ t: UInt64) -> Double { Double(t) / 1_000_000 }

    func installa() {
        let inizio = CFRunLoopObserverCreateWithHandler(nil, CFRunLoopActivity.afterWaiting.rawValue, true, Int.min) { [unowned self] _, _ in
            self.partenza = mach_absolute_time()
            self.partenzaCpu = clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID)
            self.dentro = true
        }
        let fine = CFRunLoopObserverCreateWithHandler(nil, CFRunLoopActivity.beforeWaiting.rawValue, true, Int.max) { [unowned self] _, _ in
            guard self.dentro else { return }
            self.dentro = false
            let parete = mach_absolute_time() &- self.partenza
            let cpu = clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID) &- self.partenzaCpu
            self.occupato &+= cpu
            if cpu > self.massimo { self.massimo = cpu }
            if parete > self.massimoParete { self.massimoParete = parete }
            if self.msCpu(cpu) > 16.7 { self.lunghi += 1 }
        }
        for o in [inizio, fine] {
            CFRunLoopAddObserver(CFRunLoopGetMain(), o, .commonModes)
            osservatori.append(o!)
        }
    }

    func azzera() { occupato = 0; massimo = 0; massimoParete = 0; lunghi = 0 }
}

@MainActor
enum Misura {
    static var attiva: Bool { CommandLine.arguments.contains("--misura") }

    private static let cron = CronometroCiclo()

    struct Riga {
        var scenario: String
        var voce: String
        var occupato = 0.0
        var massimo = 0.0
        var parete = 0.0
        var lunghi = 0
        var rete = 0.0
        var richieste = 0
        var kb = 0
    }

    private static var righe: [Riga] = []

    private static func valore(_ nome: String) -> String? {
        guard let i = CommandLine.arguments.firstIndex(of: nome), i + 1 < CommandLine.arguments.count else { return nil }
        return CommandLine.arguments[i + 1]
    }

    private static func ora() -> Double { Double(DispatchTime.now().uptimeNanoseconds) / 1_000_000 }

    // MARK: attesa

    /// Aspetta che non ci sia piu' nulla in volo ne' in caricamento. Torna i ms di rete.
    private static func quiete(minimo: Double = 250) async -> Double {
        let a = Archivio.condiviso
        let t0 = ora()
        var calme = 0
        while ora() - t0 < 60_000 {
            try? await Task.sleep(nanoseconds: 30_000_000)
            let ferma = Cliente.contatori.inVolo == 0 && !a.inCaricamento && !a.ricercaInCorso
            calme = ferma ? calme + 1 : 0
            if ora() - t0 >= minimo && calme >= 3 { break }
        }
        return ora() - t0
    }

    /// Un passo misurato. `assestamento` lascia il tempo alle viste di finire di disegnare.
    private static func passo(_ scenario: String, _ voce: String, assestamento: UInt64 = 400_000_000,
                              _ azione: () async -> Void) async -> Riga {
        cron.azzera()
        let r0 = Cliente.contatori.richieste, b0 = Cliente.contatori.byte
        await azione()
        let rete = await quiete()
        try? await Task.sleep(nanoseconds: assestamento)
        var r = Riga(scenario: scenario, voce: voce)
        r.occupato = cron.msCpu(cron.occupato)
        r.massimo = cron.msCpu(cron.massimo)
        r.parete = cron.ms(cron.massimoParete)
        r.lunghi = cron.lunghi
        r.rete = rete
        r.richieste = Cliente.contatori.richieste - r0
        r.kb = (Cliente.contatori.byte - b0) / 1024
        righe.append(r)
        return r
    }

    // MARK: scenari

    static func avvia() {
        cron.installa()
        Task { await esegui() }
    }

    private static func esegui() async {
        var finestra: NSWindow?
        for _ in 0..<80 {
            if let w = DelegatoApp.corrente?.finestraPrincipale(), w.isVisible { finestra = w; break }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        guard let w = finestra else { FileHandle.standardError.write(Data("la finestra non è comparsa\n".utf8)); exit(1) }
        w.setContentSize(NSSize(width: 1280, height: 820))
        w.setFrameTopLeftPoint(NSPoint(x: 60, y: (NSScreen.main?.visibleFrame.maxY ?? 900) - 40))
        w.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)

        // come nell'app vera: il ciclo parte all'avvio (qui con un intervallo lungo, cosi' non
        // cade in mezzo a un passo), e si lascia il tempo di finire quello che fa da solo
        let a = Archivio.condiviso
        a.avvia(ogniSecondi: 3600)
        a.vai(.oggi)
        _ = await quiete(minimo: 7000)
        let solo = valore("--misura-solo")
        func vuole(_ scenario: String) -> Bool { solo == nil || solo == scenario }

        // 1. cambio di sezione: tre giri, il primo a freddo (nessun dato in memoria)
        var ordine: [Sezione] = [.task, .progetti, .social, .memoria, .archivio, .oggi]
        // --misura-sezioni task,social: solo queste, nell'ordine dato (per campionarne una con `sample`)
        if let elenco = valore("--misura-sezioni") {
            let scelte = elenco.split(separator: ",").compactMap { Sezione.da(nome: String($0)) }
            if !scelte.isEmpty { ordine = scelte }
        }
        let giri = max(1, Int(valore("--misura-giri") ?? "3") ?? 3)
        for giro in (vuole("sezione") ? Array(1...giri) : []) {
            for s in ordine {
                _ = await passo("sezione", "\(s.rawValue) giro \(giro)") { a.vai(s) }
            }
        }

        // 2. ricarica a mano (⌘R) della sezione aperta
        for s in (vuole("ricarica") ? ordine : []) {
            a.vai(s)
            _ = await quiete(minimo: 800)
            for n in 1...3 {
                _ = await passo("ricarica", "\(s.rawValue) \(n)") { await a.aggiorna() }
            }
        }

        // 3. scrittura: un task cambia stato e la sezione si rilegge
        a.vai(.task)
        _ = await quiete(minimo: 800)
        if vuole("scrittura"), let id = a.compiti.first?.id {
            let iniziale = a.compiti.first?.status ?? "in corso"
            let altro = iniziale == "bloccato" ? "in corso" : "bloccato"
            for (n, stato) in [altro, iniziale, altro, iniziale].enumerated() {
                _ = await passo("scrittura", "task \(n + 1) -> \(stato)") { _ = await a.imposta(task: id, stato: stato) }
            }
        }

        // 4. ricerca: cinque tasti, uno ogni 90 ms
        a.vai(.oggi)
        _ = await quiete(minimo: 800)
        let ripetizioni = vuole("ricerca") ? max(1, Int(valore("--misura-ripeti") ?? "1") ?? 1) : 0
        for n in Array(stride(from: 1, through: ripetizioni, by: 1)) {
            _ = await passo("ricerca", n == 1 ? "indice" : "indice \(n)", assestamento: 600_000_000) {
                a.ricercaAperta = true
                for parola in ["i", "in", "ind", "indi", "indic", "indice"] {
                    a.ricerca = parola
                    try? await Task.sleep(nanoseconds: 90_000_000)
                }
            }
            a.azzeraRicerca()
            _ = await quiete(minimo: 500)
        }

        // 5. sottofondo: il passo che il ciclo di 30 s fa da solo, quattro volte per sezione
        for s in (vuole("sottofondo") ? [Sezione.task, .archivio, .memoria, .oggi] : []) {
            a.vai(s)
            _ = await quiete(minimo: 800)
            for n in 1...4 {
                // il ciclo vero passa ogni 30 s: la sezione non e' "appena caricata"
                try? await Task.sleep(nanoseconds: 3_400_000_000)
                _ = await passo("sottofondo", "\(s.rawValue) \(n)") { await a.passoDiSottofondo() }
            }
        }

        stampa()
        exit(0)
    }

    // MARK: uscita

    private static func f(_ x: Double, _ w: Int = 8) -> String {
        let s = String(format: "%.1f", x)
        return String(repeating: " ", count: max(0, w - s.count)) + s
    }

    private static func stampa() {
        var out = ""
        out += "scenario   voce                      occupato   massimo   parete  lunghi      rete  richieste       KB\n"
        for r in righe {
            let voce = r.voce.padding(toLength: 24, withPad: " ", startingAt: 0)
            out += "\(r.scenario.padding(toLength: 10, withPad: " ", startingAt: 0)) \(voce) \(f(r.occupato, 10)) \(f(r.massimo, 9)) \(f(r.parete, 8)) \(String(format: "%7d", r.lunghi)) \(f(r.rete, 9)) \(String(format: "%10d", r.richieste)) \(String(format: "%8d", r.kb))\n"
        }
        // sintesi per scenario: somma dell'occupato, massimo dei massimi
        out += "\nsintesi (somma dell'occupato, massimo dei massimi, somma dei giri lunghi, somma delle richieste)\n"
        var visti: [String] = []
        for r in righe where !visti.contains(r.scenario) { visti.append(r.scenario) }
        for sc in visti {
            let v = righe.filter { $0.scenario == sc }
            out += "\(sc.padding(toLength: 10, withPad: " ", startingAt: 0)) occupato \(f(v.reduce(0) { $0 + $1.occupato }, 9)) ms   massimo \(f(v.map(\.massimo).max() ?? 0, 7)) ms   lunghi \(v.reduce(0) { $0 + $1.lunghi })   richieste \(v.reduce(0) { $0 + $1.richieste })   KB \(v.reduce(0) { $0 + $1.kb })\n"
        }
        FileHandle.standardOutput.write(Data(out.utf8))
        if let file = valore("--misura-out") {
            let json: [[String: Any]] = righe.map {
                ["scenario": $0.scenario, "voce": $0.voce, "occupato_ms": $0.occupato, "massimo_ms": $0.massimo, "parete_ms": $0.parete,
                 "lunghi": $0.lunghi, "rete_ms": $0.rete, "richieste": $0.richieste, "kb": $0.kb]
            }
            if let d = try? JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys]) {
                try? d.write(to: URL(fileURLWithPath: file))
            }
        }
    }
}
