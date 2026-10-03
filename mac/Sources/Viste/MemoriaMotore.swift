// Memoria, la mappa globale: il motore.
//
// Fa girare la simulazione (MemoriaFisica.swift) FUORI dal thread principale, a passi
// fissi di 1/120 di secondo, e lascia l'ultima istantanea a chi disegna. Solo Foundation.
//
//   - i comandi (trascina, zoom, cambia livello...) arrivano dal thread principale in una
//     coda protetta da un lucchetto e non aspettano niente: il gesto non si blocca mai;
//   - un `actor` possiede la simulazione e ne consuma la coda a ogni giro;
//   - il giro parte quando arriva un comando e si ferma da solo quando la scena e' ferma:
//     da quel momento non gira nessun Task e nessun timer;
//   - chi disegna legge l'istantanea con `foto()` (una copia, senza aspettare l'actor).

import Foundation

enum ComandoFisica: Sendable {
    case sostituisci(TopologiaGrafo)
    case visibili([Bool], scalda: Bool)
    case iniziaTrascino(Int, P2)
    case trascina(P2)
    case rilascia
    case dimensioni(Float, Float)
    case inquadra(subito: Bool)
    case zoom(Float, ancora: P2?)
    case panora(P2)
    /// Uno spostamento senza gesto da seguire (la rotella e il trackpad): niente inerzia nostra.
    case sposta(P2)
    /// Il dito si stacca dopo un pan: la scena continua per inerzia.
    case rilasciaPanoramica
    case scalda(Float)
    case centra(P2, zoom: Float)
    case centraNodo(Int, zoom: Float)
    /// Mette in luce un nodo con i suoi vicini, o un gruppo, e attenua il resto.
    case illumina(nodo: Int?, gruppo: Int?)
    case inquadraGruppo(Int)
    /// "Riduci movimento": camera e luci arrivano subito.
    case ridotto(Bool)
    /// Porta subito la scena a riposo (le istantanee, le prove).
    case assesta
}

/// Quello che il motore e chi disegna si scambiano. Tutto sotto un lucchetto solo.
final class PonteFisica: @unchecked Sendable {
    private let lucchetto = NSLock()
    private var coda: [ComandoFisica] = []
    private var ultima = FotoScena()
    private var acceso = false
    private var generazione = 0

    // misure (solo per --mappa-misura (Sistema/MisuraMappa.swift) e per le prove)
    private var passiTotali = 0
    private var nsPassi: UInt64 = 0
    private var nsPassoMax: UInt64 = 0

    /// Chiamata (da qualunque thread) quando il giro finisce: `(generazione)`.
    var allaFine: (@Sendable (Int) -> Void)?

    var inMoto: Bool { lucchetto.withLock { acceso } }
    var numeroGenerazione: Int { lucchetto.withLock { generazione } }

    func foto() -> FotoScena { lucchetto.withLock { ultima } }

    /// Accoda un comando. Restituisce la generazione da avviare, se il giro era spento.
    func invia(_ c: ComandoFisica) -> Int? {
        lucchetto.withLock {
            coda.append(c)
            if acceso { return nil }
            acceso = true
            generazione += 1
            return generazione
        }
    }

    func prendiComandi() -> [ComandoFisica] {
        lucchetto.withLock {
            let c = coda
            coda.removeAll(keepingCapacity: true)
            return c
        }
    }

    func pubblica(_ f: FotoScena) { lucchetto.withLock { ultima = f } }

    /// Il giro chiede di spegnersi: riesce solo se nel frattempo non e' arrivato niente.
    func provaSpegni() -> Bool {
        lucchetto.withLock {
            if !coda.isEmpty { return false }
            acceso = false
            return true
        }
    }

    func registraPassi(_ quanti: Int, ns: UInt64) {
        lucchetto.withLock {
            passiTotali += quanti
            nsPassi += ns
            let per = ns / UInt64(max(quanti, 1))
            if per > nsPassoMax { nsPassoMax = per }
        }
    }

    /// (passi, ms medio per passo, ms massimo per passo)
    func misure() -> (passi: Int, medioMs: Double, massimoMs: Double) {
        lucchetto.withLock {
            (passiTotali, passiTotali > 0 ? Double(nsPassi) / Double(passiTotali) / 1e6 : 0,
             Double(nsPassoMax) / 1e6)
        }
    }
}

actor MotoreFisica {
    nonisolated let ponte = PonteFisica()
    private var sim: SimulazioneGrafo
    private var versione = 0
    /// Il passo fisso, in nanosecondi (1/120 s: uno schermo a 120 Hz vede una posizione nuova a
    /// ogni fotogramma, uno a 60 Hz ne salta uno su due senza che il moto cambi).
    private let passoNs: UInt64 = 8_333_333

    init(topologia: TopologiaGrafo, parametri: ParametriFisica = .standard) {
        sim = SimulazioneGrafo(topologia: topologia, parametri: parametri)
        versione = 0
        ponte.pubblica(sim.foto(versione: 0))
    }

    /// Manda un comando dal thread principale (o da qualunque altro) senza aspettare.
    nonisolated func invia(_ c: ComandoFisica) {
        if let g = ponte.invia(c) {
            Task.detached(priority: .userInitiated) { [self] in await self.corri(generazione: g) }
        }
    }

    private func applica(_ c: ComandoFisica) {
        switch c {
        case .sostituisci(let t):
            let camera = sim.camera
            sim = SimulazioneGrafo(topologia: t, parametri: sim.p)
            sim.adotta(camera: camera)
        case .visibili(let v, let calore): sim.imposta(visibili: v, scalda: calore)
        case .iniziaTrascino(let i, let p): sim.iniziaTrascino(i, in: p)
        case .trascina(let p): sim.trascina(a: p)
        case .rilascia: sim.rilascia()
        case .dimensioni(let w, let h): sim.dimensioniVista(w, h)
        case .inquadra(let subito): sim.inquadra(subito: subito)
        case .zoom(let f, let a): sim.zoom(fattore: f, ancoraSchermo: a)
        case .panora(let d): sim.panora(schermo: d)
        case .sposta(let d): sim.panora(schermo: d, dito: false)
        case .rilasciaPanoramica: sim.rilasciaPanoramica()
        case .illumina(let n, let g): sim.illumina(nodo: n, gruppo: g)
        case .inquadraGruppo(let g): sim.inquadra(gruppo: g)
        case .ridotto(let r): sim.imposta(ridotto: r)
        case .scalda(let v): sim.scalda(v)
        case .centra(let p, let z): sim.centra(su: p, zoom: z)
        case .centraNodo(let i, let z):
            if i >= 0 && i < sim.posizioni.count { sim.centra(su: sim.posizioni[i], zoom: z) }
        case .assesta: sim.assesta()
        }
    }

    private func corri(generazione: Int) async {
        var ultimo = DispatchTime.now().uptimeNanoseconds
        var accumulo: UInt64 = 0
        var primo = true
        // dopo l'ultimo movimento il giro resta acceso ancora un attimo: un gesto continuo
        // (un pan, una rotella) manda un comando ogni pochi millisecondi e non deve
        // spegnere e riaccendere tutto a ogni comando
        let graziaNs: UInt64 = 150_000_000
        var ultimaAttivita = ultimo
        while true {
            let comandi = ponte.prendiComandi()
            for c in comandi { applica(c) }

            let ora = DispatchTime.now().uptimeNanoseconds
            accumulo += min(ora &- ultimo, 100_000_000)
            ultimo = ora
            if primo { accumulo = max(accumulo, passoNs); primo = false }
            if !comandi.isEmpty { ultimaAttivita = ora }

            var fatti = 0
            let inizio = DispatchTime.now().uptimeNanoseconds
            while accumulo >= passoNs && fatti < 12 {
                sim.passo()
                accumulo -= passoNs
                fatti += 1
            }
            if fatti > 0 || !comandi.isEmpty {
                versione += 1
                ponte.pubblica(sim.foto(versione: versione))
                if fatti > 0 {
                    ponte.registraPassi(fatti, ns: DispatchTime.now().uptimeNanoseconds &- inizio)
                }
            }

            if !sim.ferma { ultimaAttivita = ora }
            if sim.ferma && comandi.isEmpty && ora &- ultimaAttivita > graziaNs && ponte.provaSpegni() { break }

            let attesa = accumulo >= passoNs ? 0 : passoNs - accumulo
            try? await Task.sleep(nanoseconds: max(attesa, 1_000_000))
        }
        ponte.allaFine?(generazione)
    }
}
