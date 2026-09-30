// Memoria, la mappa globale: la vista.
//
// Tutti i fatti come nodi colorati per tipo, i legami come archi, con una fisica vera
// (MemoriaFisica.swift) che gira fuori dal thread principale (MemoriaMotore.swift):
//   - si trascina un nodo e il resto reagisce; si trascina lo sfondo per spostarsi;
//   - zoom col pizzico, con la rotella e con i pulsanti; dentro la vista anche con
//     ⌘+ e ⌘- (⌘0 inquadra tutto), a passi, con la camera che segue con una molla;
//   - livelli "1", "2" e "Tutto": il fatto scelto e i legami a uno o due passi, oppure
//     tutta la memoria, con una transizione fisica fra l'uno e l'altro;
//   - le etichette compaiono secondo lo zoom e l'importanza del nodo;
//   - un clic sceglie il fatto (si apre l'Inspector), un doppio clic entra a due livelli.
//
// Si disegna con un Canvas dentro un TimelineView che gira SOLO mentre qualcosa si muove:
// a scena ferma non c'e' nessun timer e nessun Task.

import SwiftUI
import AppKit

// MARK: - i livelli

enum LivelloMappa: String, CaseIterable, Identifiable {
    case uno, due, tutto
    var id: String { rawValue }

    @MainActor var titolo: String {
        switch self {
        case .uno: return "1"
        case .due: return "2"
        case .tutto: return tr("Tutto", "All")
        }
    }

    var passi: Int? {
        switch self {
        case .uno: return 1
        case .due: return 2
        case .tutto: return nil
        }
    }
}

// MARK: - argomenti per le istantanee e per la misura

/// `--memoria-scena tutto|uno|due|zoom` apre la mappa in quello stato, senza scrivere le
/// preferenze e con la scena gia' a riposo (per le istantanee).
enum ScenaMappa {
    static func argomento(_ nome: String) -> String? {
        let a = CommandLine.arguments
        guard let i = a.firstIndex(of: nome), i + 1 < a.count else { return nil }
        return a[i + 1]
    }

    static var nome: String? {
        guard CommandLine.arguments.contains("--istantanee") else { return nil }
        return argomento("--memoria-scena")
    }

    static var livello: LivelloMappa? {
        switch nome {
        case "uno": return .uno
        case "due": return .due
        case "tutto", "zoom": return .tutto
        default: return nil
        }
    }

    static var zoom: Bool { nome == "zoom" }
}

// MARK: - i dati del grafo, calcolati una volta per ogni forma della memoria

struct InfoGrafo: Sendable {
    let firma: Int
    let nomi: [String]
    let tipi: [TipoMemoria]
    let grado: [Int]
    /// 0...1: 1 e' il nodo piu' collegato. Decide quali etichette si vedono per prime.
    let rango: [Float]
    let archi: [(Int, Int)]
    let indice: [String: Int]
    let vicini: [[Int32]]
    let hub: Int?
    let topologia: TopologiaGrafo

    static func firma(_ dati: DatiMemoria) -> Int {
        var h = Hasher()
        h.combine(dati.fatti.count)
        for f in dati.fatti {
            h.combine(f.nome)
            h.combine(f.tipo.rawValue)
            h.combine(dati.vicini[f.nome]?.count ?? 0)
        }
        return h.finalize()
    }

    init(dati: DatiMemoria) {
        let fatti = dati.fatti
        let n = fatti.count
        nomi = fatti.map { $0.nome }
        tipi = fatti.map { $0.tipo }
        var ind: [String: Int] = [:]
        for (i, nome) in nomi.enumerated() { ind[nome] = i }
        indice = ind
        var lista: [(Int, Int)] = []
        for (i, nome) in nomi.enumerated() {
            for v in dati.vicini[nome] ?? [] {
                if let j = ind[v], j > i { lista.append((i, j)) }
            }
        }
        archi = lista
        var vic = [[Int32]](repeating: [], count: n)
        for (a, b) in lista { vic[a].append(Int32(b)); vic[b].append(Int32(a)) }
        vicini = vic
        let gr = vic.map { $0.count }
        grado = gr
        let nm = nomi
        let ordine = (0..<n).sorted { (gr[$0], nm[$1]) > (gr[$1], nm[$0]) }
        var r = [Float](repeating: 0, count: n)
        for (pos, i) in ordine.enumerated() { r[i] = 1 - Float(pos) / Float(max(n, 1)) }
        rango = r
        hub = ordine.first
        firma = InfoGrafo.firma(dati)

        // si parte dalla forma che ha gia' calcolato il server, portata alla scala della
        // simulazione; chi non ce l'ha va su una spirale
        let scala = 62 * Float(max(n, 1)).squareRoot()
        var iniziali: [P2] = []
        for (i, f) in fatti.enumerated() {
            if let x = f.x, let y = f.y {
                iniziali.append(P2(Float(x) - 0.5, Float(y) - 0.5) * scala)
            } else {
                let ang = 2.399963 * Float(i)
                let raggio = 22 * (Float(i) + 0.5).squareRoot()
                iniziali.append(P2(raggio * cos(ang), raggio * sin(ang)))
            }
        }
        topologia = TopologiaGrafo(n: n, archi: lista, iniziali: iniziali)
    }
}

// MARK: - la misura dei fotogrammi

/// Quanto dura un disegno e quanti se ne fanno: per la prova, non per l'utente.
final class MisuraDisegno: @unchecked Sendable {
    private let lucchetto = NSLock()
    private var disegni = 0
    private var totale = 0.0
    private var massimo = 0.0
    private var primo = 0.0
    private var ultimo = 0.0
    private var lenti = 0

    func azzera() {
        lucchetto.withLock { disegni = 0; totale = 0; massimo = 0; primo = 0; ultimo = 0; lenti = 0 }
    }

    func registra(durata: Double, adesso: Double) {
        lucchetto.withLock {
            if disegni == 0 { primo = adesso }
            disegni += 1
            totale += durata
            massimo = max(massimo, durata)
            if durata > 0.0167 { lenti += 1 }
            ultimo = adesso
        }
    }

    /// (disegni, fps, ms medio, ms massimo, disegni oltre 16,7 ms)
    func riassunto() -> (Int, Double, Double, Double, Int) {
        lucchetto.withLock {
            let secondi = max(ultimo - primo, 0.001)
            let fps = disegni > 1 ? Double(disegni - 1) / secondi : 0
            return (disegni, fps, disegni > 0 ? totale / Double(disegni) * 1000 : 0, massimo * 1000, lenti)
        }
    }
}

// MARK: - il modello della mappa (sul thread principale, ma senza dati per fotogramma)

@MainActor @Observable
final class ModelloMappa {
    /// Il modello della mappa aperta adesso: serve solo alla prova dei fotogrammi.
    @ObservationIgnored nonisolated(unsafe) static weak var attivo: ModelloMappa?

    private(set) var info: InfoGrafo?
    private(set) var inMoto = false
    private(set) var hover: Int?

    @ObservationIgnored private(set) var motore: MotoreFisica?
    @ObservationIgnored private var ultimiVisibili: [Bool]?
    private(set) var dimensioni: CGSize = .zero
    @ObservationIgnored private var inizializzato = false
    @ObservationIgnored let misura = MisuraDisegno()
    @ObservationIgnored var alFine: (() -> Void)?

    init() { Self.attivo = self }

    var pronto: Bool { dimensioni.width > 8 && dimensioni.height > 8 }
    var ponte: PonteFisica? { motore?.ponte }

    // MARK: dati

    /// Nuova forma della memoria: si tengono le posizioni di chi c'era gia'.
    func imposta(info nuova: InfoGrafo) {
        var topo = nuova.topologia
        if let vecchio = info, let m = motore {
            let foto = m.ponte.foto()
            var iniz = nuova.topologia.iniziali
            for (j, nome) in nuova.nomi.enumerated() {
                if let i = vecchio.indice[nome], i < foto.pos.count { iniz[j] = foto.pos[i] }
            }
            topo = TopologiaGrafo(n: nuova.nomi.count, archi: nuova.archi, iniziali: iniz)
            manda(.sostituisci(topo))
            ultimiVisibili = nil
        } else {
            let m = MotoreFisica(topologia: topo)
            m.ponte.allaFine = { [weak self] _ in
                Task { @MainActor in self?.fine() }
            }
            motore = m
            ultimiVisibili = nil
            inizializzato = false
        }
        info = nuova
    }

    func impostaDimensioni(_ s: CGSize) {
        guard s.width > 8, s.height > 8 else { return }
        let cambiata = abs(s.width - dimensioni.width) > 0.5 || abs(s.height - dimensioni.height) > 0.5
        dimensioni = s
        if cambiata && inizializzato {
            manda(.dimensioni(Float(s.width), Float(s.height)))
        }
    }

    func impostaHover(_ i: Int?) {
        // nelle istantanee il puntatore vero e' dove capita: non deve cambiare la scena
        if ScenaMappa.nome != nil { return }
        if hover != i { hover = i }
    }

    // MARK: comandi

    func manda(_ c: ComandoFisica) {
        guard let m = motore else { return }
        if !inMoto { inMoto = true }
        m.invia(c)
    }

    private func fine() {
        let vivo = motore?.ponte.inMoto ?? false
        if inMoto != vivo { inMoto = vivo }
        if !vivo { alFine?() }
    }

    /// Mette d'accordo il motore con quello che l'utente ha scelto: quali nodi si vedono e
    /// dove guarda la camera.
    func allinea(livello: LivelloMappa, centro: String?, senzaAnimazione: Bool, zoomScena: Bool) {
        guard let info = info, motore != nil, pronto else { return }
        let n = info.nomi.count
        var voluti = [Bool](repeating: true, count: n)
        var nodoCentro: Int?
        if let passi = livello.passi {
            if let c = centro, let i = info.indice[c] {
                voluti = info.topologia.raggiungibili(da: i, passi: passi)
                nodoCentro = i
            } else if let h = info.hub {
                voluti = info.topologia.raggiungibili(da: h, passi: passi)
                nodoCentro = h
            }
        }
        if !inizializzato {
            inizializzato = true
            manda(.dimensioni(Float(dimensioni.width), Float(dimensioni.height)))
            manda(.visibili(voluti, scalda: false))
            manda(.inquadra(subito: true))
            ultimiVisibili = voluti
            if senzaAnimazione { manda(.assesta) }
        } else if voluti != ultimiVisibili {
            ultimiVisibili = voluti
            manda(.visibili(voluti, scalda: true))
            if senzaAnimazione { manda(.assesta) }
        }
        if zoomScena, let h = centro.flatMap({ info.indice[$0] }) ?? nodoCentro ?? info.hub {
            manda(.assesta)
            manda(.centraNodo(h, zoom: 2.4))
            manda(.assesta)
        }
    }

    func inquadra() {
        manda(.inquadra(subito: false))
    }

    func zoomPasso(_ fattore: Float, ancora: CGPoint? = nil) {
        manda(.zoom(fattore, ancora: ancora.map { P2(Float($0.x), Float($0.y)) }))
    }

    // MARK: il nodo sotto un punto

    /// Il nodo piu' vicino al punto (coordinate della vista), se ce n'e' uno a portata di clic.
    func nodo(in p: CGPoint, foto: FotoScena, centro: Int?) -> Int? {
        guard let info = info, foto.pos.count == info.nomi.count else { return nil }
        var migliore: (Int, CGFloat)?
        for i in 0..<info.nomi.count where foto.presenza[i] > 0.5 && foto.voluto[i] {
            let s = foto.schermo(foto.pos[i])
            let r = DisegnoMappa.raggioSchermo(info.topologia.raggio[i] * (i == centro ? 1.35 : 1), foto.camera.z)
            let d = hypot(CGFloat(s.x) - p.x, CGFloat(s.y) - p.y)
            if d <= r + 5, migliore == nil || d < migliore!.1 { migliore = (i, d) }
        }
        return migliore?.0
    }
}

// MARK: - il disegno

struct StatoDisegno {
    var scelto: Int?
    var hover: Int?
    var livello: LivelloMappa
    /// Il nodo in evidenza e i suoi vicini.
    var evidenziati: Set<Int>
    var centro: Int?
}

enum DisegnoMappa {
    /// Il raggio a schermo cresce meno dello zoom: da lontano i nodi restano visibili, da
    /// vicino non diventano dischi enormi.
    static func raggioSchermo(_ r: Float, _ zoom: Float) -> CGFloat {
        CGFloat(max(r * pow(zoom, 0.6), 2.4))
    }

    private static func cerchio(_ c: CGPoint, _ r: CGFloat) -> Path {
        Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r))
    }

    static func disegna(_ ctx: inout GraphicsContext, _ size: CGSize, foto: FotoScena,
                        info: InfoGrafo, stato: StatoDisegno) {
        let n = info.nomi.count
        guard n > 0, foto.pos.count == n, foto.presenza.count == n else { return }
        let zoom = foto.camera.z
        var punti = [CGPoint](repeating: .zero, count: n)
        for i in 0..<n {
            let s = foto.camera.schermo(foto.pos[i])
            punti[i] = CGPoint(x: CGFloat(s.x), y: CGFloat(s.y))
        }
        let area = CGRect(origin: .zero, size: size).insetBy(dx: -60, dy: -60)
        let focus = stato.hover ?? stato.scelto
        let sfuma = focus != nil && (stato.livello == .tutto || stato.hover != nil)
        let pochi = stato.livello != .tutto

        // i legami: tutti insieme, salvo quelli che stanno entrando o uscendo
        var normali = Path(), evidenza = Path()
        var incerti: [(Int, Int, Double)] = []
        for (a, b) in info.archi {
            let pa = foto.presenza[a], pb = foto.presenza[b]
            if pa <= 0 || pb <= 0 { continue }
            let p1 = punti[a], p2 = punti[b]
            if !area.contains(p1) && !area.contains(p2) { continue }
            if pa < 1 || pb < 1 || !foto.voluto[a] || !foto.voluto[b] {
                incerti.append((a, b, Double(min(pa, pb))))
                continue
            }
            if let f = focus, a == f || b == f {
                evidenza.move(to: p1); evidenza.addLine(to: p2)
            } else {
                normali.move(to: p1); normali.addLine(to: p2)
            }
        }
        let opacitaBase: Double = sfuma ? 0.07 : (pochi ? 0.28 : 0.16)
        ctx.stroke(normali, with: .color(.primary.opacity(opacitaBase)), lineWidth: pochi ? 1.2 : 0.8)
        for (a, b, p) in incerti {
            var t = Path()
            t.move(to: punti[a]); t.addLine(to: punti[b])
            ctx.stroke(t, with: .color(.primary.opacity(opacitaBase * p)), lineWidth: 0.8)
        }
        ctx.stroke(evidenza, with: .color(.accentColor.opacity(0.8)), lineWidth: 1.6)

        // i nodi: prima quelli sfumati, poi gli evidenziati, in cima il centro
        var ordine: [Int] = []
        ordine.reserveCapacity(n)
        for i in 0..<n where foto.presenza[i] > 0.01 && area.contains(punti[i]) { ordine.append(i) }
        func peso(_ i: Int) -> Int {
            if i == focus { return 3 }
            if i == stato.centro { return 2 }
            return stato.evidenziati.contains(i) ? 1 : 0
        }
        ordine.sort { peso($0) < peso($1) }
        for i in ordine {
            let p = foto.presenza[i]
            let e = stato.evidenziati.contains(i)
            let spento = sfuma && !e
            let grande = (i == stato.centro) ? 1.35 : 1.0
            let r = raggioSchermo(info.topologia.raggio[i] * Float(grande), zoom)
                * CGFloat(p) + (i == stato.hover ? 2 : 0)
            let c = cerchio(punti[i], r)
            ctx.fill(c, with: .color(info.tipi[i].colore.opacity(Double(p) * (spento ? 0.3 : 1))))
            if zoom > 0.45 {
                ctx.stroke(c, with: .style(.background), lineWidth: 1.2)
            }
            if i == stato.scelto || i == stato.centro && pochi {
                ctx.stroke(cerchio(punti[i], r + 3.5), with: .color(.accentColor), lineWidth: 2)
            }
        }

        etichette(&ctx, size, foto: foto, info: info, stato: stato, punti: punti, focus: focus, area: area)
    }

    private static func etichette(_ ctx: inout GraphicsContext, _ size: CGSize, foto: FotoScena,
                                  info: InfoGrafo, stato: StatoDisegno, punti: [CGPoint],
                                  focus: Int?, area: CGRect) {
        let n = info.nomi.count
        let zoom = foto.camera.z
        let pochi = stato.livello != .tutto
        // chi ha diritto a un'etichetta, in ordine di importanza
        var candidati: [(Int, Float)] = []
        for i in 0..<n where foto.presenza[i] > 0.6 && foto.voluto[i] && area.contains(punti[i]) {
            var pr = info.rango[i]
            if i == focus { pr += 4 } else if i == stato.centro { pr += 3 } else if stato.evidenziati.contains(i) { pr += 2 }
            candidati.append((i, pr))
        }
        candidati.sort { $0.1 > $1.1 }

        var occupati: [CGRect] = []
        var messe = 0
        let visibile = CGRect(origin: .zero, size: size)
        for (i, pr) in candidati {
            if messe >= 90 { break }
            let importante = pr >= 1.5 || (pochi && candidati.count <= 60)
            // le etichette compaiono con lo zoom: prima i nodi piu' collegati
            let soglia: Float = importante ? 0.3 : 0.35 + 1.45 * (1 - info.rango[i])
            let alfa = min(max((zoom - soglia) / 0.18, 0), 1)
            if alfa <= 0.02 { continue }

            let evidente = i == focus || i == stato.centro
            var t = Text(accorcia(info.nomi[i], 30))
            t = evidente ? t.font(.callout.weight(.semibold)) : t.font(.caption)
            let ris = ctx.resolve(t.foregroundStyle(.primary))
            let misura = ris.measure(in: CGSize(width: 320, height: 40))
            let r = raggioSchermo(info.topologia.raggio[i] * (i == stato.centro ? 1.35 : 1), zoom)
            var rect = CGRect(x: punti[i].x + r + 4, y: punti[i].y - misura.height / 2 - 1,
                              width: misura.width + 8, height: misura.height + 2)
            if rect.maxX > visibile.maxX - 4 {
                rect.origin.x = punti[i].x - r - 4 - rect.width
            }
            let ingombro = rect.insetBy(dx: -2, dy: -1)
            if !evidente && occupati.contains(where: { $0.intersects(ingombro) }) { continue }
            occupati.append(ingombro)
            messe += 1

            var strato = ctx
            strato.opacity = Double(alfa) * ((focus != nil && !stato.evidenziati.contains(i) && stato.livello == .tutto) ? 0.35 : 1)
            let targhetta = Path(roundedRect: rect, cornerRadius: 5)
            strato.fill(targhetta, with: .style(.background.opacity(0.82)))
            strato.draw(ris, at: CGPoint(x: rect.minX + 4, y: rect.midY), anchor: .leading)
        }
    }
}

// MARK: - lo stato di un gesto (fuori da SwiftUI: cambiarlo non ridisegna niente)

private final class StatoGesto {
    enum Fase { case nodo(Int, scostamento: P2), sfondo }
    var fase: Fase?
    var mosso = false
    var trascinando = false
    var ultimaTraslazione = CGSize.zero
    var ultimaMagnificazione: CGFloat = 1
    var ultimoClic: (nodo: Int, quando: TimeInterval)?

    func azzera() {
        fase = nil; mosso = false; trascinando = false; ultimaTraslazione = .zero
    }
}

// MARK: - rotella, trackpad e tastiera dentro la vista

/// Una NSView trasparente che ascolta la rotella e i tasti + - 0 (senza ⌘) solo quando il
/// puntatore e' sopra la mappa e non si sta scrivendo in un campo. ⌘+ ⌘- ⌘0 non si toccano mai:
/// sono della dimensione del testo, ovunque sia il puntatore, come dicono le voci del menu Vista.
struct AscoltoInput: NSViewRepresentable {
    var rotella: (_ punto: CGPoint, _ dx: CGFloat, _ dy: CGFloat, _ precisa: Bool, _ zoom: Bool) -> Void
    var tasto: (_ zoom: Int) -> Void     // +1 avanti, -1 indietro, 0 inquadra

    func makeNSView(context: Context) -> VistaAscolto {
        let v = VistaAscolto()
        v.rotella = rotella
        v.tasto = tasto
        return v
    }

    func updateNSView(_ v: VistaAscolto, context: Context) {
        v.rotella = rotella
        v.tasto = tasto
    }

    static func dismantleNSView(_ v: VistaAscolto, coordinator: ()) { v.rimuovi() }

    final class VistaAscolto: NSView {
        var rotella: ((CGPoint, CGFloat, CGFloat, Bool, Bool) -> Void)?
        var tasto: ((Int) -> Void)?
        private var monitor: Any?

        override var isFlipped: Bool { true }
        override func hitTest(_ punto: NSPoint) -> NSView? { nil }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            rimuovi()
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .keyDown]) { [weak self] e in
                guard let self = self, let w = self.window, e.window === w else { return e }
                if e.type == .scrollWheel {
                    let p = self.convert(e.locationInWindow, from: nil)
                    guard self.bounds.contains(p) else { return e }
                    let comando = e.modifierFlags.contains(.command) || e.modifierFlags.contains(.control)
                    self.rotella?(p, e.scrollingDeltaX, e.scrollingDeltaY, e.hasPreciseScrollingDeltas, comando)
                    return nil
                }
                // tasti: senza ⌘, ⌥ e ⌃ (quelli sono dei comandi di menu), col puntatore sulla
                // mappa e mentre non si scrive in un campo di testo
                let flag = e.modifierFlags.intersection(.deviceIndependentFlagsMask)
                guard flag.intersection([.command, .option, .control]).isEmpty else { return e }
                if w.firstResponder is NSText { return e }
                let p = self.convert(w.mouseLocationOutsideOfEventStream, from: nil)
                guard self.bounds.contains(p) else { return e }
                switch e.characters ?? "" {
                case "+", "=": self.tasto?(1)
                case "-", "_": self.tasto?(-1)
                case "0": self.tasto?(0)
                default: return e
                }
                return nil
            }
        }

        func rimuovi() {
            if let m = monitor { NSEvent.removeMonitor(m) }
            monitor = nil
        }

        deinit { if let m = monitor { NSEvent.removeMonitor(m) } }
    }
}

// MARK: - la vista

struct VistaMappa: View {
    let dati: DatiMemoria
    let scelto: String?

    @Environment(Archivio.self) private var archivio
    @Environment(\.accessibilityReduceMotion) private var riduciMovimento
    @AppStorage("memoriaLivello") private var livelloGuardato = LivelloMappa.tutto.rawValue

    @State private var modello = ModelloMappa()
    @State private var gesto = StatoGesto()

    private var livello: LivelloMappa {
        ScenaMappa.livello ?? LivelloMappa(rawValue: livelloGuardato) ?? .tutto
    }

    private struct Chiave: Hashable {
        var firma: Int
        var livello: LivelloMappa
        var scelto: String?
        var pronto: Bool
        var ridotto: Bool
    }

    var body: some View {
        let firma = InfoGrafo.firma(dati)
        let chiave = Chiave(firma: firma, livello: livello, scelto: scelto,
                            pronto: modello.pronto, ridotto: riduciMovimento)
        VStack(spacing: 0) {
            Group {
                if let info = modello.info, let ponte = modello.ponte {
                    superficie(info: info, ponte: ponte)
                } else {
                    ProgressView().controlSize(.small)
                }
            }
            // la mappa e' solo lo spazio sopra la barra: i nodi non ci finiscono mai sotto
            .onGeometryChange(for: CGSize.self, of: { $0.size }) { modello.impostaDimensioni($0) }
            if let info = modello.info {
                Divider()
                barra(info)
            }
        }
        .task(id: chiave) { allinea(firma: firma) }
    }

    private func allinea(firma: Int) {
        if modello.info?.firma != firma { modello.imposta(info: InfoGrafo(dati: dati)) }
        guard let info = modello.info else { return }
        // a uno o due livelli serve un fatto al centro: se non c'e', il piu' collegato
        if livello != .tutto && scelto == nil, let h = info.hub {
            archivio.memoriaScelta = info.nomi[h]
            return
        }
        modello.allinea(livello: livello, centro: scelto,
                        senzaAnimazione: riduciMovimento || ScenaMappa.nome != nil,
                        zoomScena: ScenaMappa.zoom)
    }

    private var livelloBinding: Binding<LivelloMappa> {
        Binding(get: { livello }, set: { nuovo in
            guard ScenaMappa.livello == nil else { return }
            livelloGuardato = nuovo.rawValue
        })
    }

    // MARK: superficie

    private func superficie(info: InfoGrafo, ponte: PonteFisica) -> some View {
        let centro = livello == .tutto ? nil : scelto.flatMap { info.indice[$0] }
        let indiceScelto = scelto.flatMap { info.indice[$0] }
        let focus = modello.hover ?? indiceScelto
        var evid = Set<Int>()
        if let f = focus {
            evid.insert(f)
            for v in info.vicini[f] { evid.insert(Int(v)) }
        }
        let stato = StatoDisegno(scelto: indiceScelto, hover: modello.hover, livello: livello,
                                 evidenziati: evid, centro: centro)
        let misura = modello.misura
        let inMoto = modello.inMoto

        return TimelineView(.animation(minimumInterval: nil, paused: !inMoto)) { tl in
            Canvas(rendersAsynchronously: false) { ctx, size in
                let t0 = CACurrentMediaTime()
                _ = tl.date
                DisegnoMappa.disegna(&ctx, size, foto: ponte.foto(), info: info, stato: stato)
                misura.registra(durata: CACurrentMediaTime() - t0, adesso: t0)
            }
        }
        .contentShape(Rectangle())
        .gesture(trascinamento(info: info, ponte: ponte, centro: centro))
        .simultaneousGesture(pizzico)
        .onContinuousHover { fase in
            switch fase {
            case .active(let p):
                let i = modello.nodo(in: p, foto: ponte.foto(), centro: centro)
                modello.impostaHover(i)
            case .ended:
                modello.impostaHover(nil)
            }
        }
        .pointerStyle(modello.hover != nil ? .link : .default)
        .background(AscoltoInput(rotella: { punto, dx, dy, precisa, zoom in
            if !precisa || zoom {
                let f = precisa ? exp(Float(dy) * 0.012) : pow(1.12, Float(max(min(dy, 6), -6)))
                modello.zoomPasso(f, ancora: punto)
            } else {
                modello.manda(.panora(P2(Float(dx), Float(dy))))
            }
        }, tasto: { verso in
            if verso == 0 { modello.inquadra() } else { modello.zoomPasso(verso > 0 ? 1.4 : 1 / 1.4) }
        }))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(tr("Mappa della memoria, \(info.nomi.count) fatti",
                               "Memory map, \(info.nomi.count) facts"))
        .accessibilityChildren {
            ForEach(Array((0..<info.nomi.count).sorted { info.rango[$0] > info.rango[$1] }.prefix(40)), id: \.self) { i in
                Button(info.nomi[i]) { archivio.memoriaScelta = info.nomi[i] }
            }
        }
    }

    // MARK: gesti

    private func trascinamento(info: InfoGrafo, ponte: PonteFisica, centro: Int?) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { v in
                let foto = ponte.foto()
                if gesto.fase == nil {
                    if let i = modello.nodo(in: v.startLocation, foto: foto, centro: centro) {
                        let m = foto.mondo(P2(Float(v.startLocation.x), Float(v.startLocation.y)))
                        gesto.fase = .nodo(i, scostamento: foto.pos[i] - m)
                    } else {
                        gesto.fase = .sfondo
                    }
                }
                if hypot(v.translation.width, v.translation.height) > 3 { gesto.mosso = true }
                guard gesto.mosso, let fase = gesto.fase else { return }
                switch fase {
                case .nodo(let i, let scostamento):
                    if !gesto.trascinando {
                        gesto.trascinando = true
                        modello.manda(.iniziaTrascino(i, foto.pos[i]))
                    }
                    let m = foto.mondo(P2(Float(v.location.x), Float(v.location.y)))
                    modello.manda(.trascina(m + scostamento))
                case .sfondo:
                    let dx = v.translation.width - gesto.ultimaTraslazione.width
                    let dy = v.translation.height - gesto.ultimaTraslazione.height
                    gesto.ultimaTraslazione = v.translation
                    modello.manda(.panora(P2(Float(dx), Float(dy))))
                }
            }
            .onEnded { _ in
                defer { gesto.azzera() }
                guard let fase = gesto.fase else { return }
                switch fase {
                case .nodo(let i, _):
                    if gesto.trascinando {
                        modello.manda(.rilascia)
                    } else {
                        clic(su: i, info: info)
                    }
                case .sfondo:
                    if !gesto.mosso, livello == .tutto { archivio.memoriaScelta = nil }
                }
            }
    }

    private func clic(su i: Int, info: InfoGrafo) {
        let adesso = ProcessInfo.processInfo.systemUptime
        let doppio = gesto.ultimoClic.map { $0.nodo == i && adesso - $0.quando < 0.4 } ?? false
        gesto.ultimoClic = doppio ? nil : (i, adesso)
        archivio.memoriaScelta = info.nomi[i]
        if doppio && livello != .due && ScenaMappa.livello == nil { livelloGuardato = LivelloMappa.due.rawValue }
    }

    private var pizzico: some Gesture {
        MagnifyGesture()
            .onChanged { v in
                let f = v.magnification / gesto.ultimaMagnificazione
                gesto.ultimaMagnificazione = v.magnification
                let d = modello.dimensioni
                let ancora = CGPoint(x: v.startAnchor.x * d.width, y: v.startAnchor.y * d.height)
                modello.zoomPasso(Float(f), ancora: ancora)
            }
            .onEnded { _ in gesto.ultimaMagnificazione = 1 }
    }

    // MARK: pezzi sopra il disegno

    /// La barra sotto la mappa: a sinistra cosa vogliono dire i colori, a destra il livello e lo
    /// zoom. Se la larghezza non basta i due gruppi vanno uno sopra l'altro.
    private func barra(_ info: InfoGrafo) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 16) {
                legenda(info)
                Spacer(minLength: 12)
                controlli
            }
            VStack(alignment: .leading, spacing: 8) {
                legenda(info)
                controlli
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private func legenda(_ info: InfoGrafo) -> some View {
        let presenti = TipoMemoria.allCases.filter { t in info.tipi.contains(t) }
        return HStack(spacing: 12) {
            ForEach(presenti, id: \.self) { t in
                Label {
                    Text(t.titolo)
                } icon: {
                    Image(systemName: "circle.fill").foregroundStyle(t.colore)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Text(tr("\(info.nomi.count) fatti, \(info.archi.count) legami",
                    "\(info.nomi.count) facts, \(info.archi.count) links"))
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .fixedSize()
        .allowsHitTesting(false)
    }

    // Il livello e lo zoom: controlli di sistema, nella barra sotto la mappa.
    private var controlli: some View {
        HStack(spacing: 10) {
            Picker(tr("Livello", "Level"), selection: livelloBinding) {
                ForEach(LivelloMappa.allCases) { Text($0.titolo).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .fixedSize()
            .help(tr("Il fatto scelto e i legami a uno o due passi, oppure tutta la memoria",
                     "The chosen fact and its links one or two steps away, or all of memory"))

            Button { modello.zoomPasso(1 / 1.4) } label: {
                Label(tr("Riduci", "Zoom out"), systemImage: "minus.magnifyingglass")
            }
            .help(tr("Riduci (-)", "Zoom out (-)"))
            Button { modello.zoomPasso(1.4) } label: {
                Label(tr("Ingrandisci", "Zoom in"), systemImage: "plus.magnifyingglass")
            }
            .help(tr("Ingrandisci (+)", "Zoom in (+)"))
            Button { modello.inquadra() } label: {
                Label(tr("Inquadra tutto", "Fit all"), systemImage: "viewfinder")
            }
            .help(tr("Inquadra tutto (0)", "Fit all (0)"))
        }
        .labelStyle(.iconOnly)
        .buttonStyle(.bordered)
        .fixedSize()
    }
}
