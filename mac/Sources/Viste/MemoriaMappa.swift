// Memoria, la mappa globale: la vista.
//
// Tutti i fatti come nodi colorati per tipo, raggruppati in isole (un progetto, un tipo di
// memoria): ogni gruppo ha la sua regione morbida nel suo colore e il suo nome, i ponti fra
// i gruppi sono nastri e fasci di curve. Una fisica vera (MemoriaFisica.swift) gira fuori
// dal thread principale (MemoriaMotore.swift), il disegno e' in MappaDisegno.swift, i dati
// dei gruppi in MappaDati.swift e MappaGrafo.swift:
//   - si trascina un nodo e il resto reagisce, il suo gruppo lo segue con un filo di ritardo;
//     si trascina lo sfondo per spostarsi, e la scena continua per inerzia e rimbalza ai bordi;
//   - zoom col pizzico, con la rotella e con i pulsanti, verso il puntatore, con una molla
//     smorzata; dentro la vista anche con + e - (0 inquadra tutto), a passi;
//   - il passaggio del mouse mette in luce il nodo, i suoi vicini e i suoi ponti e attenua il
//     resto; un clic su un gruppo lo inquadra; un doppio clic su un nodo entra a due livelli;
//   - livelli "1", "2" e "Tutto": il fatto scelto e i legami a uno o due passi, oppure tutta
//     la memoria, con una transizione fisica fra l'uno e l'altro;
//   - da lontano si leggono i nomi dei gruppi, avvicinandosi i titoli dei nodi piu'
//     importanti e poi di tutti;
//   - un clic sceglie il fatto (si apre l'Inspector).
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

/// `--memoria-scena tutto|uno|due|zoom|gruppo|hover` apre la mappa in quello stato, senza
/// scrivere le preferenze e con la scena gia' a riposo (per le istantanee):
///   tutto  tutta la memoria da lontano     gruppo  il gruppo piu' grosso inquadrato
///   uno    il fatto piu' collegato, 1 passo   hover  il passaggio del mouse sul nodo piu' collegato
///   due    lo stesso, a 2 passi               zoom   il nodo piu' collegato da vicino
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
        case "tutto", "zoom", "gruppo", "hover": return .tutto
        default: return nil
        }
    }

    static var zoom: Bool { nome == "zoom" }
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
    private(set) var hoverGruppo: Int?
    private(set) var gruppoScelto: Int?

    @ObservationIgnored private(set) var motore: MotoreFisica?
    @ObservationIgnored private var ultimiVisibili: [Bool]?
    private(set) var dimensioni: CGSize = .zero
    @ObservationIgnored private var inizializzato = false
    @ObservationIgnored let misura = MisuraDisegno()
    @ObservationIgnored var alFine: (() -> Void)?
    @ObservationIgnored private var nodoSceltoLuce: Int?
    @ObservationIgnored private var ultimaLuce: (Int?, Int?)?
    @ObservationIgnored private var ridotto = false

    init() { Self.attivo = self }

    /// La mappa parte quando la vista ha una misura vera: al primo giro del layout e' di pochi
    /// punti (16 x 16), e inquadrare tutto o un gruppo con quella misura darebbe uno zoom sbagliato.
    var pronto: Bool { dimensioni.width > 120 && dimensioni.height > 120 }
    var ponte: PonteFisica? { motore?.ponte }

    // MARK: dati

    /// Nuova forma della memoria: si tengono le posizioni di chi c'era gia' e nel suo gruppo.
    func imposta(info nuova: InfoGrafo) {
        var topo = nuova.topologia
        if let vecchio = info, let m = motore {
            let foto = m.ponte.foto()
            var iniz = nuova.topologia.iniziali
            for (j, nome) in nuova.nomi.enumerated() {
                if let i = vecchio.indice[nome], i < foto.pos.count,
                   vecchio.gruppi[vecchio.gruppo[i]].chiave == nuova.gruppi[nuova.gruppo[j]].chiave {
                    iniz[j] = foto.pos[i]
                }
            }
            topo = TopologiaGrafo(n: nuova.nomi.count, archi: nuova.archi, iniziali: iniz,
                                  gruppo: nuova.gruppo, centri: nuova.topologia.centri)
            manda(.sostituisci(topo))
            ultimiVisibili = nil
            ultimaLuce = nil
            if let g = gruppoScelto, g >= nuova.gruppi.count { gruppoScelto = nil }
        } else {
            let m = MotoreFisica(topologia: topo)
            m.ponte.allaFine = { [weak self] _ in
                Task { @MainActor in self?.fine() }
            }
            motore = m
            ultimiVisibili = nil
            ultimaLuce = nil
            inizializzato = false
        }
        info = nuova
        diag("info n=\(nuova.nomi.count) gruppi=\(nuova.gruppi.count) dalServer=\(nuova.dalServer)")
    }

    /// Una riga sul log delle istantanee (solo con --memoria-scena): cosa ha fatto la mappa.
    private func diag(_ testo: String) {
        guard ScenaMappa.nome != nil else { return }
        FileHandle.standardOutput.write(Data(("mappa: " + testo + "\n").utf8))
    }

    func impostaDimensioni(_ s: CGSize) {
        guard s.width > 8, s.height > 8 else { return }
        let cambiata = abs(s.width - dimensioni.width) > 0.5 || abs(s.height - dimensioni.height) > 0.5
        dimensioni = s
        if cambiata && inizializzato {
            manda(.dimensioni(Float(s.width), Float(s.height)))
        }
    }

    func impostaRiduciMovimento(_ r: Bool) {
        guard r != ridotto else { return }
        ridotto = r
        manda(.ridotto(r))
    }

    // MARK: la luce: passaggio del mouse, gruppo scelto

    func impostaHover(_ i: Int?, gruppo: Int? = nil) {
        // nelle istantanee il puntatore vero e' dove capita: non deve cambiare la scena
        if ScenaMappa.nome != nil { return }
        forzaHover(i, gruppo: gruppo)
    }

    func forzaHover(_ i: Int?, gruppo: Int? = nil) {
        let g = i == nil ? gruppo : nil
        if hover != i { hover = i }
        if hoverGruppo != g { hoverGruppo = g }
        inviaLuce()
    }

    /// Chi e' in luce: il nodo sotto il puntatore, altrimenti il gruppo sotto il puntatore o
    /// quello scelto, altrimenti il fatto scelto (solo a "Tutto": a uno e due livelli si vede gia' lui).
    private func inviaLuce() {
        guard motore != nil else { return }
        let nodo = hover ?? (hoverGruppo == nil && gruppoScelto == nil ? nodoSceltoLuce : nil)
        let gruppo = hover == nil ? (hoverGruppo ?? gruppoScelto) : gruppoScelto
        if let u = ultimaLuce, u.0 == nodo, u.1 == gruppo { return }
        ultimaLuce = (nodo, gruppo)
        manda(.illumina(nodo: nodo, gruppo: gruppo))
    }

    /// Scegliere un gruppo lo inquadra e lascia in luce solo lui; `nil` toglie la scelta.
    func scegliGruppo(_ g: Int?) {
        gruppoScelto = g
        if let g = g { manda(.inquadraGruppo(g)) }
        inviaLuce()
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
        nodoSceltoLuce = livello == .tutto ? centro.flatMap { info.indice[$0] } : nil
        if !inizializzato {
            inizializzato = true
            manda(.ridotto(ridotto))
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
        inviaLuce()
        if zoomScena, let h = centro.flatMap({ info.indice[$0] }) ?? nodoCentro ?? info.hub {
            manda(.assesta)
            manda(.centraNodo(h, zoom: 2.4))
            manda(.assesta)
        }
    }

    /// Le scene delle istantanee che non sono solo un livello: un gruppo inquadrato, il mouse su un nodo.
    func scena(_ nome: String?) {
        guard nome != nil, let info = info, motore != nil, pronto else { return }
        switch nome {
        case "gruppo":
            manda(.assesta)
            scegliGruppo(0)
            manda(.assesta)
        case "hover":
            if let h = info.hub { forzaHover(h); manda(.assesta) }
        default:
            break
        }
        diag("scena \(nome ?? "-")")
        Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 800_000_000)
            guard let f = self?.ponte?.foto() else { return }
            self?.diag("gruppo0 baricentro=\(f.baricentri.first ?? .zero) raggio=\(f.raggiGruppo.first ?? 0) quanti=\(f.quantiGruppo.first ?? 0) inLuce=\(String(describing: f.gruppoInLuce)) c=\(f.camera.c) tc=\(f.camera.tc)")
            self?.diag("camera z=\(f.camera.z) tz=\(f.camera.tz) zoomTutto=\(f.zoomTutto) vista=\(f.camera.vista) segui=\(f.camera.segui) ferma=\(f.ferma)")
        }
    }

    func inquadra() {
        gruppoScelto = nil
        manda(.inquadra(subito: false))
        inviaLuce()
    }

    func zoomPasso(_ fattore: Float, ancora: CGPoint? = nil) {
        manda(.zoom(fattore, ancora: ancora.map { P2(Float($0.x), Float($0.y)) }))
    }

    // MARK: il nodo o il gruppo sotto un punto

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

    /// Il gruppo la cui isola contiene il punto (il piu' centrato, se ce n'e' piu' d'uno).
    func gruppo(in p: CGPoint, foto: FotoScena) -> Int? {
        guard let info = info, foto.baricentri.count == info.gruppi.count else { return nil }
        var migliore: (Int, CGFloat)?
        for g in 0..<info.gruppi.count where foto.quantiGruppo[g] > 0 && foto.presenzaGruppo[g] > 0.5 {
            let c = foto.schermo(foto.baricentri[g])
            let r = CGFloat(foto.raggiGruppo[g] * foto.camera.z) + 8
            let d = hypot(CGFloat(c.x) - p.x, CGFloat(c.y) - p.y) / max(r, 1)
            if d <= 1, migliore == nil || d < migliore!.1 { migliore = (g, d) }
        }
        return migliore?.0
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
    @Environment(\.colorScheme) private var schema
    @Environment(\.legno) private var legno
    @AppStorage("memoriaLivello") private var livelloGuardato = LivelloMappa.tutto.rawValue

    @State private var modello = ModelloMappa()
    @State private var gesto = StatoGesto()
    /// I gruppi come li dice il server, e se si e' gia' provato a chiederli (o e' passato
    /// il tempo che si aspetta: la mappa non resta vuota per un server lento).
    @State private var serverGruppi: MappaGruppi?
    @State private var improntaServer = 0
    @State private var gruppiPronti = false

    private var livello: LivelloMappa {
        ScenaMappa.livello ?? LivelloMappa(rawValue: livelloGuardato) ?? .tutto
    }

    private struct Chiave: Hashable {
        var firma: Int
        var livello: LivelloMappa
        var scelto: String?
        var pronto: Bool
        var ridotto: Bool
        var gruppiPronti: Bool
    }

    private struct ChiaveGruppi: Hashable {
        var firma: Int
        var compartimento: String?
    }

    var body: some View {
        let firmaDati = InfoGrafo.firma(dati)
        let firma = InfoGrafo.firma(firmaDati, improntaServer: improntaServer)
        let chiave = Chiave(firma: firma, livello: livello, scelto: scelto,
                            pronto: modello.pronto, ridotto: riduciMovimento, gruppiPronti: gruppiPronti)
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
        .task(id: ChiaveGruppi(firma: firmaDati, compartimento: archivio.compartimento)) { await caricaGruppi() }
        .task(id: chiave) { allinea(firma: firma) }
    }

    /// Chiede i gruppi al server; se non arrivano in mezzo secondo parte lo stesso coi gruppi
    /// ricavati dalle schede, e quando arrivano la mappa si riorganizza da sola.
    private func caricaGruppi() async {
        let attesa = Task {
            if (try? await Task.sleep(nanoseconds: 600_000_000)) != nil { gruppiPronti = true }
        }
        let m = await CaricaGruppi.carica(compartimento: archivio.compartimento)
        attesa.cancel()
        let nuova = m?.impronta ?? 0
        if nuova != improntaServer { serverGruppi = m; improntaServer = nuova }
        gruppiPronti = true
    }

    private func allinea(firma: Int) {
        guard gruppiPronti else { return }
        modello.impostaRiduciMovimento(riduciMovimento)
        if modello.info?.firma != firma { modello.imposta(info: InfoGrafo(dati: dati, server: serverGruppi)) }
        guard let info = modello.info else { return }
        // a uno o due livelli serve un fatto al centro: se non c'e', il piu' collegato
        if livello != .tutto && scelto == nil, let h = info.hub {
            archivio.memoriaScelta = info.nomi[h]
            return
        }
        modello.allinea(livello: livello, centro: scelto,
                        senzaAnimazione: riduciMovimento || ScenaMappa.nome != nil,
                        zoomScena: ScenaMappa.zoom)
        modello.scena(ScenaMappa.nome)
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
        let stato = StatoDisegno(scelto: indiceScelto, hover: modello.hover, livello: livello, centro: centro,
                                 gruppoScelto: modello.gruppoScelto, scuro: schema == .dark, legno: legno != nil,
                                 inglese: Lingua.condivisa.codice != "it")
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
                let foto = ponte.foto()
                if let i = modello.nodo(in: p, foto: foto, centro: centro) {
                    modello.impostaHover(i)
                } else {
                    modello.impostaHover(nil, gruppo: modello.gruppo(in: p, foto: foto))
                }
            case .ended:
                modello.impostaHover(nil)
            }
        }
        .pointerStyle(modello.hover != nil || modello.hoverGruppo != nil ? .link : .default)
        .background(AscoltoInput(rotella: { punto, dx, dy, precisa, zoom in
            // nelle istantanee il puntatore e la tastiera veri non devono cambiare la scena
            guard ScenaMappa.nome == nil else { return }
            if !precisa || zoom {
                let f = precisa ? exp(Float(dy) * 0.012) : pow(1.12, Float(max(min(dy, 6), -6)))
                modello.zoomPasso(f, ancora: punto)
            } else {
                modello.manda(.sposta(P2(Float(dx), Float(dy))))
            }
        }, tasto: { verso in
            guard ScenaMappa.nome == nil else { return }
            if verso == 0 { modello.inquadra() } else { modello.zoomPasso(verso > 0 ? 1.4 : 1 / 1.4) }
        }))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(tr("Mappa della memoria, \(info.nomi.count) fatti in \(info.gruppi.count) gruppi",
                               "Memory map, \(info.nomi.count) facts in \(info.gruppi.count) groups"))
        .accessibilityChildren {
            ForEach(Array((0..<info.nomi.count).sorted { info.rango[$0] > info.rango[$1] }.prefix(40)), id: \.self) { i in
                Button(info.titoli[i]) { archivio.memoriaScelta = info.nomi[i] }
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
            .onEnded { v in
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
                    if gesto.mosso {
                        modello.manda(.rilasciaPanoramica)
                    } else {
                        clicSfondo(in: v.location, ponte: ponte)
                    }
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

    /// Un clic sul vuoto: dentro un'isola inquadra il gruppo (di nuovo, lo lascia), fuori toglie la scelta.
    private func clicSfondo(in p: CGPoint, ponte: PonteFisica) {
        if let g = modello.gruppo(in: p, foto: ponte.foto()) {
            modello.scegliGruppo(modello.gruppoScelto == g ? nil : g)
        } else {
            if modello.gruppoScelto != nil { modello.scegliGruppo(nil) }
            if livello == .tutto { archivio.memoriaScelta = nil }
        }
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

    // MARK: pezzi sotto il disegno

    /// La barra sotto la mappa: i gruppi (un clic li inquadra), cosa vogliono dire i colori, a
    /// destra il livello e lo zoom. Se la larghezza non basta i due gruppi vanno uno sopra l'altro,
    /// e se non basta nemmeno cosi' la legenda perde la frase in fondo. L'ultima scelta deve
    /// stare in poco. Misurato: la larghezza ideale della barra (piu' di 800 punti) faceva da
    /// larghezza preferita di tutta la colonna, e a 125% o con la finestra stretta spingeva
    /// l'Inspector fuori dalla finestra (e, con la finestra sotto i 1100 punti, mandava AppKit in
    /// un giro di vincoli che chiudeva l'app).
    private func barra(_ info: InfoGrafo) -> some View {
        VStack(spacing: 6) {
            gruppi(info)
                .frame(maxWidth: .infinity, alignment: .leading)
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
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .leading, spacing: 8) {
                    legenda(info, frase: false)
                    controlli
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            // La larghezza ideale di ViewThatFits e' quella della prima scelta (oltre 800 punti):
            // la colonna la prendeva per preferita e spingeva l'Inspector fuori dalla finestra.
            .frame(minWidth: 0, idealWidth: 300, maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    /// Un pulsante per gruppo: il colore dell'isola, il nome, quante memorie. Porta la camera li'.
    private func gruppi(_ info: InfoGrafo) -> some View {
        FlussoChip(righeMassime: 2, spazio: 6) {
            ForEach(Array(info.gruppi.enumerated()), id: \.offset) { g, gi in
                let scelto = modello.gruppoScelto == g
                Button { modello.scegliGruppo(scelto ? nil : g) } label: {
                    HStack(spacing: 5) {
                        Circle().fill(ColoreGruppo.colore(gi.colore)).frame(width: 8, height: 8)
                        Text(gi.nomeVisto(inglese: Lingua.condivisa.codice != "it")).font(.caption)
                        Text("\(gi.membri.count)").font(.caption).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(scelto ? ColoreGruppo.colore(gi.colore).opacity(0.22) : Color.clear, in: Capsule())
                    .overlay(Capsule().strokeBorder(ColoreGruppo.colore(gi.colore).opacity(scelto ? 0.8 : 0.35), lineWidth: 1))
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(tr("Gruppo \(gi.nomeVisto(inglese: Lingua.condivisa.codice != "it")), \(gi.membri.count) memorie",
                                       "Group \(gi.nomeVisto(inglese: Lingua.condivisa.codice != "it")), \(gi.membri.count) memories"))
                .help(tr("Inquadra il gruppo", "Frame the group"))
            }
        }
        .clipped()

    }

    private func legenda(_ info: InfoGrafo, frase: Bool = true) -> some View {
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
            if frase {
                Text(tr("il colore è il tipo, l'area è il gruppo", "colour is the type, the area is the group"))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
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


/// Dispone i chip dei gruppi a righe, andando a capo dove la larghezza finisce, per al piu'
/// `righeMassime` righe: i chip che non ci stanno si nascondono (fuori dal ritaglio) invece di
/// uscire dal bordo senza segno di scorrimento, com'era con la riga che scorreva. I piu' grandi
/// sono i primi (l'ordine e' quello dei gruppi); gli altri si raggiungono dalla mappa.
struct FlussoChip: Layout {
    let righeMassime: Int
    let spazio: CGFloat

    private struct Disposizione { var posti: [CGPoint]; var dimensioni: CGSize }

    private func dispone(_ larghezza: CGFloat, _ sub: Subviews) -> Disposizione {
        var posti: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, riga = 0, altezzaRiga: CGFloat = 0, piuLarga: CGFloat = 0
        for v in sub {
            let d = v.sizeThatFits(.unspecified)
            if x > 0, x + d.width > larghezza { riga += 1; x = 0; y += altezzaRiga + spazio; altezzaRiga = 0 }
            if riga >= righeMassime { posti.append(CGPoint(x: -100_000, y: 0)); continue }
            posti.append(CGPoint(x: x, y: y))
            x += d.width + spazio
            altezzaRiga = max(altezzaRiga, d.height)
            piuLarga = max(piuLarga, x - spazio)
        }
        return Disposizione(posti: posti, dimensioni: CGSize(width: piuLarga, height: y + altezzaRiga))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let d = dispone(proposal.width ?? 300, subviews).dimensioni
        return CGSize(width: min(d.width, proposal.width ?? d.width), height: d.height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let d = dispone(bounds.width, subviews)
        for (v, p) in zip(subviews, d.posti) {
            v.place(at: CGPoint(x: bounds.minX + p.x, y: bounds.minY + p.y), anchor: .topLeading, proposal: .unspecified)
        }
    }
}
