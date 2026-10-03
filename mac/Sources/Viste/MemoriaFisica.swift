// Memoria, la mappa globale: la fisica.
//
// Solo Foundation, niente SwiftUI e niente thread principale: questo file e' la
// simulazione pura (un valore che avanza di un passo fisso alla volta) e serve alla
// prova in mac/Prove, che la compila da sola. Il motore che la fa girare fuori dal
// thread principale sta in MemoriaMotore.swift, il disegno in MappaDisegno.swift.
//
// Il tempo e' vero: il passo e' di 1/120 s e ogni costante e' "per secondo", cosi' la
// scena si muove allo stesso modo su uno schermo a 60 e a 120 Hz.
//
// Ogni nodo appartiene a un gruppo (un progetto, un tipo di memoria). I gruppi sono
// isole: ognuno ha un'ancora, un punto che si muove come una pallina morbida, e un
// raggio che cresce con il numero di memorie.
//   - dentro un gruppo: repulsione fra i nodi, molle corte per i legami, collisione
//     morbida, e un'attrazione verso l'ancora che e' debole al centro e forte oltre il
//     raggio, cosi' il gruppo resta un disco e non si sfilaccia;
//   - fra i gruppi: le ancore si respingono finche' i dischi non si toccano (con una
//     distanza piccola per chi ha molti ponti), e i ponti (i legami fra gruppi) sono
//     molle lunghe e deboli;
//   - l'ancora segue il centro dei suoi nodi: se si trascina un nodo il gruppo lo segue
//     con un filo di ritardo, in modo elastico.
// Un "calore" (alpha) scende passo dopo passo: sotto la soglia la scena e' ferma e non
// costa piu' niente.
//
// I livelli (1, 2, Tutto) sono un insieme di nodi "voluti". Quelli che entrano nascono
// sul vicino che c'era gia' e si allargano con le molle; quelli che escono vengono
// richiamati sul vicino piu' prossimo mentre svaniscono.
//
// La camera e' una molla smorzata (un filo di rimbalzo), con l'inerzia dopo un pan, un
// rimbalzo morbido ai bordi, e uno zoom che tiene fermo il punto sotto il puntatore.
// Con "Riduci movimento" non rimbalza e non ha inerzia: arriva e basta.

import Foundation

typealias P2 = SIMD2<Float>

// MARK: - la forma del grafo

struct TopologiaGrafo: Sendable {
    let n: Int
    let da: [Int32]
    let a: [Int32]
    let grado: [Int32]
    let vicini: [[Int32]]
    let iniziali: [P2]
    let raggio: [Float]
    /// La carica di ogni nodo: chi ha piu' legami respinge di piu'.
    let carica: [Float]
    /// Il gruppo di ogni nodo (0..<ng) e i nodi di ogni gruppo.
    let ng: Int
    let gruppo: [Int32]
    let membri: [[Int32]]
    /// Per ogni arco, vero se unisce due gruppi diversi (un ponte).
    let ponte: [Bool]
    /// Quanti legami uniscono due gruppi: ng * ng, simmetrica.
    let legami: [Float]
    /// Dove nascono le ancore dei gruppi.
    let centri: [P2]

    /// `archi` senza cappi e senza doppioni; `iniziali` opzionale (una spirale se manca o
    /// se ha la misura sbagliata); `gruppo` opzionale (un gruppo solo se manca);
    /// `centri` opzionale (il baricentro dei nodi iniziali di ogni gruppo).
    init(n: Int, archi: [(Int, Int)], iniziali: [P2]? = nil, gruppo: [Int]? = nil, centri: [P2]? = nil) {
        self.n = max(n, 0)
        var gr = [Int32](repeating: 0, count: max(n, 0))
        var maxG = 0
        if let g = gruppo, g.count == n {
            for i in 0..<n { gr[i] = Int32(max(g[i], 0)); maxG = max(maxG, max(g[i], 0)) }
        }
        let numeroGruppi = n > 0 ? maxG + 1 : 0
        var visti = Set<Int64>()
        var d: [Int32] = [], b: [Int32] = [], pon: [Bool] = []
        var vic = [[Int32]](repeating: [], count: max(n, 0))
        var leg = [Float](repeating: 0, count: numeroGruppi * numeroGruppi)
        for (x, y) in archi where x != y && x >= 0 && y >= 0 && x < n && y < n {
            let k = Int64(min(x, y)) << 32 | Int64(max(x, y))
            if !visti.insert(k).inserted { continue }
            d.append(Int32(x)); b.append(Int32(y))
            vic[x].append(Int32(y)); vic[y].append(Int32(x))
            let gx = Int(gr[x]), gy = Int(gr[y])
            pon.append(gx != gy)
            if gx != gy {
                leg[gx * numeroGruppi + gy] += 1
                leg[gy * numeroGruppi + gx] += 1
            }
        }
        da = d; a = b; vicini = vic; ponte = pon; legami = leg
        grado = vic.map { Int32($0.count) }
        raggio = vic.map { min(4.5 + 1.7 * Float($0.count).squareRoot(), 15) }
        carica = vic.map { 1 + 0.45 * Float($0.count).squareRoot() }
        self.gruppo = gr
        ng = numeroGruppi
        var mem = [[Int32]](repeating: [], count: numeroGruppi)
        for i in 0..<max(n, 0) { mem[Int(gr[i])].append(Int32(i)) }
        membri = mem
        if let i = iniziali, i.count == n, !i.isEmpty {
            self.iniziali = i
        } else {
            // spirale di Fermat: mai due nodi sullo stesso punto, e i primi (i piu'
            // collegati, se chi chiama li ha messi per primi) restano al centro
            self.iniziali = (0..<max(n, 0)).map { i in
                let ang = 2.399963 * Float(i)
                let r = 22 * (Float(i) + 0.5).squareRoot()
                return P2(r * cos(ang), r * sin(ang))
            }
        }
        if let c = centri, c.count == numeroGruppi {
            self.centri = c
        } else {
            self.centri = TopologiaGrafo.centriADisco(membri: mem.map { $0.count })
        }
    }

    /// Dove far nascere le ancore quando nessuno lo dice: le isole su una spirale, la piu'
    /// grossa al centro, ognuna nella prima posizione in cui il suo disco non tocca gli altri.
    static func centriADisco(membri: [Int], parametri: ParametriFisica = .standard) -> [P2] {
        let raggi = membri.map { parametri.raggioGruppoPerRadice * Float($0).squareRoot() + parametri.raggioGruppoBase }
        let ordine = membri.indices.sorted { membri[$0] == membri[$1] ? $0 < $1 : membri[$0] > membri[$1] }
        var centri = [P2](repeating: .zero, count: membri.count)
        var messi: [(P2, Float)] = []
        for (posto, k) in ordine.enumerated() {
            var c = P2.zero
            if posto > 0 {
                var t = 0
                while t < 6000 {
                    let ang = 2.399963 * Float(t)
                    let rr = 40 * (Float(t) + 0.5).squareRoot()
                    c = P2(rr * cos(ang), rr * sin(ang))
                    let libero = messi.allSatisfy { m in
                        let d = c - m.0
                        return (d.x * d.x + d.y * d.y).squareRoot() >= m.1 + raggi[k] + parametri.distanzaGruppiBase
                    }
                    if libero { break }
                    t += 1
                }
            }
            messi.append((c, raggi[k]))
            centri[k] = c
        }
        return centri
    }

    /// Chi si raggiunge dal nodo `da` in al massimo `passi` legami (il nodo stesso compreso).
    func raggiungibili(da nodo: Int, passi: Int) -> [Bool] {
        var dentro = [Bool](repeating: false, count: n)
        guard nodo >= 0 && nodo < n else { return dentro }
        dentro[nodo] = true
        var fronte = [nodo]
        var livello = 0
        while livello < passi && !fronte.isEmpty {
            var prossimo: [Int] = []
            for u in fronte {
                for v in vicini[u] where !dentro[Int(v)] {
                    dentro[Int(v)] = true
                    prossimo.append(Int(v))
                }
            }
            fronte = prossimo
            livello += 1
        }
        return dentro
    }
}

// MARK: - i parametri

/// Ogni valore e' per secondo (o per secondo al quadrato): il passo e' di 1/120 s.
struct ParametriFisica: Sendable {
    var passo: Float = 1.0 / 120
    // dentro un gruppo
    var lunghezzaLegame: Float = 36
    var rigidezzaLegame: Float = 26
    var repulsione: Float = 2600
    var raggioRepulsione: Float = 120
    /// la repulsione fra nodi di gruppi diversi, in proporzione: a tenerli lontani ci pensano le ancore
    var repulsioneFraGruppi: Float = 0.35
    var margineCollisione: Float = 4
    var rigidezzaCollisione: Float = 520
    /// attrazione verso l'ancora: al centro e oltre il raggio del gruppo
    var richiamoCentro: Float = 3
    var richiamoOltre: Float = 140
    /// i ponti: lunghezza minima, e quanto sono deboli rispetto ai legami interni
    var rigidezzaPonte: Float = 0.16
    // fra gruppi
    var distanzaMinimaGruppi: Float = 30
    var distanzaGruppiBase: Float = 78
    var respingimentoGruppi: Float = 42
    var attrazionePonti: Float = 5
    var gravitaGruppi: Float = 0.5
    var seguiCentro: Float = 9
    var reazioneAncora: Float = 0.5
    var attritoAncore: Float = 9
    // tutti
    var attrito: Float = 15
    var velocitaMassima: Float = 900
    var raggioGruppoPerRadice: Float = 14.5
    var raggioGruppoBase: Float = 24
    var margineRegione: Float = 20
    /// il calore: la velocita' con cui scende, il minimo sotto cui la scena e' ferma
    var raffreddamento: Float = 1.95
    var alphaMin: Float = 0.0015
    var caloreCambio: Float = 0.75
    var caloreTrascino: Float = 0.30
    /// quanto in fretta nodi e luci arrivano dove devono
    var velocitaPresenza: Float = 10.5
    var velocitaLuce: Float = 14
    var richiamoUscita: Float = 360
    /// "Riduci movimento": la camera e le luci arrivano subito, niente rimbalzo e niente inerzia.
    var ridotto = false

    static let standard = ParametriFisica()
}

// MARK: - la camera

struct CameraSim: Sendable {
    var c: P2 = .zero
    var z: Float = 1
    var tc: P2 = .zero
    var tz: Float = 1
    var vc: P2 = .zero
    var vz: Float = 0
    /// Segue i nodi voluti finche' non la si comanda a mano.
    var segui = true
    var vista = P2(900, 640)
    /// Il punto del mondo che deve restare sotto il puntatore mentre lo zoom si assesta.
    var ancoraMondo: P2?
    var ancoraSchermo: P2 = .zero
    /// La velocita' (unita' del mondo al secondo) con cui la camera continua dopo un pan.
    var inerzia: P2 = .zero
    var panoramica = false

    static let zoomMinimo: Float = 0.05
    static let zoomMassimo: Float = 8
    static let zoomInquadraturaMassimo: Float = 1.7

    var ferma: Bool {
        let d = tc - c
        return abs(d.x) < 0.04 && abs(d.y) < 0.04 && abs(log(tz / z)) < 0.0008
            && abs(vc.x) < 0.01 && abs(vc.y) < 0.01 && abs(vz) < 0.0002
            && abs(inerzia.x) < 0.5 && abs(inerzia.y) < 0.5 && !panoramica
    }

    /// Da un punto dello schermo (origine in alto a sinistra) al mondo, con la camera indicata.
    func mondo(_ s: P2, centro: P2, zoom: Float) -> P2 {
        centro + (s - vista / 2) / zoom
    }

    func schermo(_ w: P2) -> P2 {
        (w - c) * z + vista / 2
    }
}

// MARK: - un'istantanea di quello che si vede

struct FotoScena: Sendable {
    var pos: [P2] = []
    var presenza: [Float] = []
    var voluto: [Bool] = []
    /// 1 = nodo in luce, 0 = nodo da attenuare; conta solo quanto `luce` e' accesa.
    var evidenza: [Float] = []
    var luce: Float = 0
    /// Per ogni gruppo: l'ancora, il baricentro dei nodi che si vedono, il raggio che
    /// contiene i suoi nodi, quanti nodi si vedono e quanto il gruppo e' presente (0...1).
    var ancore: [P2] = []
    var baricentri: [P2] = []
    var raggiGruppo: [Float] = []
    var quantiGruppo: [Int] = []
    var presenzaGruppo: [Float] = []
    var gruppoInLuce: Int?
    /// Lo zoom che inquadra tutto cio' che si vede: serve allo zoom semantico.
    var zoomTutto: Float = 1
    var camera = CameraSim()
    var versione = 0
    var ferma = true

    func schermo(_ w: P2) -> P2 { camera.schermo(w) }
    func mondo(_ s: P2) -> P2 { camera.mondo(s, centro: camera.c, zoom: camera.z) }
}

// MARK: - la simulazione

struct SimulazioneGrafo: Sendable {
    let topo: TopologiaGrafo
    var p: ParametriFisica
    private(set) var pos: [P2]
    private(set) var vel: [P2]
    private(set) var presenza: [Float]
    private(set) var voluto: [Bool]
    private(set) var alpha: Float = 1
    private(set) var alphaTarget: Float = 0
    private(set) var trascinato: Int?
    private var puntoTrascino: P2 = .zero
    private(set) var camera = CameraSim()
    private(set) var passiFatti = 0
    private var attivi: [Int]
    private var uscenti: [Int] = []
    private var ancora: [Int32]
    private var seme: UInt32 = 2463534242
    private var forzaLegame: [Float]
    private var biasLegame: [Float]
    private var acc: [P2]

    // i gruppi
    private(set) var ancoreGruppo: [P2]
    private var velAncora: [P2]
    private var baricentro: [P2]
    private var quanti: [Int]
    private var raggioG: [Float]
    private var raggioVis: [Float]
    private var presenzaG: [Float]

    // la luce (passaggio del mouse, gruppo inquadrato)
    private(set) var nodoInLuce: Int?
    private(set) var gruppoInLuce: Int?
    private var evidenza: [Float]
    private var luce: Float = 0
    private var zoomTutto: Float = 1

    // la griglia della repulsione
    private var bucketDi: [Int32] = []
    private var inizioBucket: [Int32] = []
    private var ordineBucket: [Int32] = []

    // la camera a mano
    private var storiaCentro: [P2] = []
    /// Passi dall'ultimo spostamento col dito: se il gesto finisce senza dirlo (annullato), la
    /// scena si libera da sola dopo un quarto di secondo.
    private var passiDaPan = 0

    init(topologia: TopologiaGrafo, parametri: ParametriFisica = .standard) {
        topo = topologia
        p = parametri
        pos = topologia.iniziali
        vel = [P2](repeating: .zero, count: topologia.n)
        acc = [P2](repeating: .zero, count: topologia.n)
        presenza = [Float](repeating: 1, count: topologia.n)
        voluto = [Bool](repeating: true, count: topologia.n)
        attivi = Array(0..<topologia.n)
        ancora = [Int32](repeating: -1, count: topologia.n)
        evidenza = [Float](repeating: 1, count: topologia.n)
        forzaLegame = []
        biasLegame = []
        for k in topologia.da.indices {
            let x = Int(topologia.da[k]), y = Int(topologia.a[k])
            let gx = Float(topologia.grado[x]), gy = Float(topologia.grado[y])
            forzaLegame.append(1 / max(min(gx, gy), 1))
            biasLegame.append(gx / max(gx + gy, 1))
        }
        let g = topologia.ng
        ancoreGruppo = topologia.centri
        velAncora = [P2](repeating: .zero, count: g)
        baricentro = topologia.centri
        quanti = [Int](repeating: 0, count: g)
        raggioG = [Float](repeating: 0, count: g)
        raggioVis = [Float](repeating: 0, count: g)
        presenzaG = [Float](repeating: 1, count: g)
        statisticheGruppi(subito: true)
    }

    // MARK: stato

    var posizioni: [P2] { pos }
    var presenze: [Float] { presenza }
    var voluti: [Bool] { voluto }
    var luceAccesa: Float { luce }
    var evidenze: [Float] { evidenza }
    var raggi: [Float] { raggioG }

    /// Tutto quello che si muove e' arrivato: niente da calcolare, niente da disegnare.
    var ferma: Bool {
        guard alpha < p.alphaMin, alphaTarget == 0, trascinato == nil, uscenti.isEmpty else { return false }
        for i in 0..<topo.n {
            let t: Float = voluto[i] ? 1 : 0
            if presenza[i] != t { return false }
        }
        guard luceArrivata else { return false }
        return camera.ferma
    }

    private var luceArrivata: Bool {
        let tl: Float = (nodoInLuce != nil || gruppoInLuce != nil) ? 1 : 0
        if luce != tl { return false }
        if tl == 0 { return true }
        for i in 0..<topo.n where evidenza[i] != bersaglioLuce(i) { return false }
        return true
    }

    func foto(versione: Int) -> FotoScena {
        FotoScena(pos: pos, presenza: presenza, voluto: voluto, evidenza: evidenza, luce: luce,
                  ancore: ancoreGruppo, baricentri: baricentro, raggiGruppo: raggioVis,
                  quantiGruppo: quanti, presenzaGruppo: presenzaG, gruppoInLuce: gruppoInLuce,
                  zoomTutto: zoomTutto, camera: camera, versione: versione, ferma: ferma)
    }

    private mutating func casuale() -> Float {
        seme ^= seme << 13; seme ^= seme >> 17; seme ^= seme << 5
        return Float(seme % 20_000) / 10_000 - 1   // -1 ... 1
    }

    // MARK: comandi

    /// Cambia l'insieme dei nodi che si vedono. `scalda` rimette in moto la simulazione.
    mutating func imposta(visibili nuovi: [Bool], scalda: Bool = true) {
        guard nuovi.count == topo.n else { return }
        let prima = voluto
        let presenzaPrima = presenza
        voluto = nuovi
        attivi = (0..<topo.n).filter { voluto[$0] }
        // chi entra: se dormiva, nasce sul vicino che c'era gia'
        for i in 0..<topo.n where voluto[i] && !prima[i] && presenza[i] < 0.02 {
            var base: P2?
            for v in topo.vicini[i] where prima[Int(v)] && presenzaPrima[Int(v)] > 0.3 {
                base = pos[Int(v)]; break
            }
            if let b = base {
                pos[i] = b + P2(casuale(), casuale()) * 10
                vel[i] = .zero
            }
        }
        // chi esce: verso il vicino voluto piu' prossimo (ricerca a partire dai voluti)
        ancora = [Int32](repeating: -1, count: topo.n)
        var fronte: [Int] = []
        var visto = voluto
        for i in attivi { ancora[i] = Int32(i); fronte.append(i) }
        while !fronte.isEmpty {
            var prossimo: [Int] = []
            for u in fronte {
                for v in topo.vicini[u] where !visto[Int(v)] {
                    visto[Int(v)] = true
                    ancora[Int(v)] = ancora[u]
                    prossimo.append(Int(v))
                }
            }
            fronte = prossimo
        }
        uscenti = (0..<topo.n).filter { !voluto[$0] && presenza[$0] > 0 }
        // un gruppo che torna a vedersi riparte dal baricentro dei suoi nodi
        statisticheGruppi(subito: false)
        if scalda { alpha = max(alpha, p.caloreCambio) }
        camera.segui = true
        camera.ancoraMondo = nil
    }

    mutating func scalda(_ valore: Float) { alpha = max(alpha, valore) }

    mutating func iniziaTrascino(_ i: Int, in punto: P2) {
        guard i >= 0, i < topo.n, voluto[i] else { return }
        trascinato = i
        puntoTrascino = punto
        camera.segui = false      // mentre si trascina la camera non rincorre il nodo
        alphaTarget = p.caloreTrascino
        alpha = max(alpha, p.caloreTrascino)
    }

    mutating func trascina(a punto: P2) {
        guard trascinato != nil else { return }
        puntoTrascino = punto
    }

    mutating func rilascia() {
        trascinato = nil
        alphaTarget = 0
    }

    mutating func imposta(ridotto: Bool) {
        p.ridotto = ridotto
        if ridotto { camera.inerzia = .zero }
    }

    // MARK: la luce

    /// Mette in luce un nodo (e i suoi vicini) oppure un gruppo; niente, per spegnerla.
    mutating func illumina(nodo: Int?, gruppo: Int?) {
        let n = (nodo.map { $0 >= 0 && $0 < topo.n } ?? false) ? nodo : nil
        let g = (gruppo.map { $0 >= 0 && $0 < topo.ng } ?? false) ? gruppo : nil
        nodoInLuce = n
        gruppoInLuce = g
        if p.ridotto {
            luce = (n != nil || g != nil) ? 1 : 0
            for i in 0..<topo.n { evidenza[i] = bersaglioLuce(i) }
        }
    }

    private func bersaglioLuce(_ i: Int) -> Float {
        if let f = nodoInLuce {
            if i == f { return 1 }
            return topo.vicini[f].contains(Int32(i)) ? 1 : 0
        }
        if let g = gruppoInLuce { return Int(topo.gruppo[i]) == g ? 1 : 0 }
        return 1
    }

    // MARK: camera

    mutating func dimensioniVista(_ w: Float, _ h: Float) {
        guard w > 8, h > 8 else { return }
        camera.vista = P2(w, h)
    }

    /// Prende la camera di una simulazione precedente (cambiano i dati, la vista resta).
    mutating func adotta(camera vecchia: CameraSim) {
        camera = vecchia
        camera.segui = true
        camera.ancoraMondo = nil
    }

    /// Torna a seguire i nodi voluti.
    mutating func inquadra(subito: Bool = false) {
        camera.segui = true
        camera.ancoraMondo = nil
        camera.inerzia = .zero
        gruppoInLuce = nil
        let (c, z) = inquadratura()
        camera.tc = c; camera.tz = z
        if subito || p.ridotto { camera.c = c; camera.z = z; camera.vc = .zero; camera.vz = 0 }
    }

    /// Centro e zoom che mostrano tutti i nodi voluti.
    func inquadratura() -> (P2, Float) {
        var minP = P2(repeating: .infinity), maxP = P2(repeating: -.infinity)
        var qualcuno = false
        for i in attivi {
            let r = P2(repeating: topo.raggio[i] + 6 + p.margineRegione * 0.6)
            minP = pointwiseMin(minP, pos[i] - r)
            maxP = pointwiseMax(maxP, pos[i] + r)
            qualcuno = true
        }
        guard qualcuno else { return (.zero, 1) }
        return adatta(minP, maxP, margine: P2(70, 52))
    }

    private func adatta(_ minP: P2, _ maxP: P2, margine: P2, massimo: Float = CameraSim.zoomInquadraturaMassimo) -> (P2, Float) {
        let dim = maxP - minP
        let libero = pointwiseMax(camera.vista - margine * 2, P2(80, 80))
        let z = min(libero.x / max(dim.x, 40), libero.y / max(dim.y, 40))
        return ((minP + maxP) / 2,
                min(max(z, CameraSim.zoomMinimo), massimo))
    }

    /// Porta la camera su un punto del mondo, a un dato zoom (smette di seguire).
    mutating func centra(su punto: P2, zoom z: Float) {
        camera.segui = false
        camera.ancoraMondo = nil
        camera.inerzia = .zero
        camera.tc = punto
        camera.tz = min(max(z, CameraSim.zoomMinimo), CameraSim.zoomMassimo)
        if p.ridotto { camera.c = camera.tc; camera.z = camera.tz; camera.vc = .zero; camera.vz = 0 }
    }

    /// Inquadra un gruppo (quello che si vede dei suoi nodi) e lo mette in luce.
    mutating func inquadra(gruppo g: Int) {
        guard g >= 0, g < topo.ng else { return }
        var minP = P2(repeating: .infinity), maxP = P2(repeating: -.infinity)
        var qualcuno = false
        for i in topo.membri[g] where voluto[Int(i)] {
            let r = P2(repeating: topo.raggio[Int(i)] + 8 + p.margineRegione)
            minP = pointwiseMin(minP, pos[Int(i)] - r)
            maxP = pointwiseMax(maxP, pos[Int(i)] + r)
            qualcuno = true
        }
        guard qualcuno else { return }
        let (c, z) = adatta(minP, maxP, margine: P2(90, 70), massimo: 3.2)
        gruppoInLuce = g
        nodoInLuce = nil
        centra(su: c, zoom: z)
        if p.ridotto { for i in 0..<topo.n { evidenza[i] = bersaglioLuce(i) }; luce = 1 }
    }

    /// Fa avanzare la simulazione fino a fermarla (per le istantanee e per le prove).
    mutating func assesta(massimo: Int = 4000) {
        var k = 0
        while !ferma && k < massimo { passo(); k += 1 }
    }

    /// Un passo di zoom, tenendo fermo il punto `ancoraSchermo` (o il centro della vista).
    mutating func zoom(fattore: Float, ancoraSchermo: P2? = nil) {
        camera.segui = false
        camera.inerzia = .zero
        let s = ancoraSchermo ?? camera.vista / 2
        // il punto del mondo che adesso sta sotto il puntatore: e' quello che deve restarci
        let w = camera.ancoraMondo != nil && camera.ancoraSchermo == s
            ? camera.ancoraMondo!
            : camera.mondo(s, centro: camera.c, zoom: camera.z)
        let nz = min(max(camera.tz * fattore, CameraSim.zoomMinimo), CameraSim.zoomMassimo)
        camera.tz = nz
        camera.tc = w - (s - camera.vista / 2) / nz
        camera.ancoraMondo = w
        camera.ancoraSchermo = s
        if p.ridotto {
            camera.z = nz; camera.c = camera.tc; camera.vc = .zero; camera.vz = 0
            camera.ancoraMondo = nil
        }
    }

    /// Sposta la vista di `delta` punti-schermo (la scena segue il dito).
    mutating func panora(schermo delta: P2, dito: Bool = true) {
        camera.segui = false
        camera.ancoraMondo = nil
        camera.inerzia = .zero
        // col trackpad (senza dito sulla mappa) l'inerzia la da' gia' il sistema
        camera.panoramica = dito
        passiDaPan = 0
        // oltre i bordi la scena oppone resistenza
        var d = delta / camera.z
        let fuori = camera.c - dentroLimiti(camera.c)
        if fuori != .zero && (d.x * fuori.x > 0 || d.y * fuori.y > 0) {
            let f = 1 / (1 + (abs(fuori.x) + abs(fuori.y)) * camera.z / 90)
            d *= f
        }
        camera.c -= d
        camera.tc = camera.c
        camera.vc = .zero
    }

    /// Il dito si stacca: la scena continua per inerzia, con la velocita' degli ultimi istanti.
    mutating func rilasciaPanoramica() {
        guard camera.panoramica else { return }
        camera.panoramica = false
        camera.tc = camera.c
        guard !p.ridotto, storiaCentro.count >= 4 else { storiaCentro.removeAll(); return }
        let durata = Float(storiaCentro.count - 1) * p.passo
        var v = (storiaCentro[storiaCentro.count - 1] - storiaCentro[0]) / max(durata, 0.01)
        let veloce = (v.x * v.x + v.y * v.y).squareRoot() * camera.z
        if veloce < 60 { v = .zero }
        if veloce > 4500 { v *= 4500 / veloce }
        camera.inerzia = v
        storiaCentro.removeAll()
    }

    /// Il rettangolo dentro cui la camera puo' stare: il contenuto, piu' mezza vista.
    private func limiti() -> (P2, P2)? {
        var minP = P2(repeating: .infinity), maxP = P2(repeating: -.infinity)
        var qualcuno = false
        for i in attivi {
            minP = pointwiseMin(minP, pos[i]); maxP = pointwiseMax(maxP, pos[i]); qualcuno = true
        }
        guard qualcuno else { return nil }
        let mezza = camera.vista / (2 * camera.z) * 0.55
        return (minP - mezza, maxP + mezza)
    }

    private func dentroLimiti(_ c: P2) -> P2 {
        guard let (lo, hi) = limiti() else { return c }
        return pointwiseMin(pointwiseMax(c, lo), hi)
    }

    // MARK: un passo (1/120 s)

    mutating func passo() {
        passiFatti += 1
        let n = topo.n
        let dt = p.passo
        guard n > 0 else { return }

        alpha += (alphaTarget - alpha) * (1 - exp(-p.raffreddamento * dt))

        // la presenza cala o cresce verso il voluto
        var qualcunoUscente = false
        let kp = p.ridotto ? 1 : 1 - exp(-p.velocitaPresenza * dt)
        for i in 0..<n {
            let t: Float = voluto[i] ? 1 : 0
            let d = t - presenza[i]
            if d == 0 { continue }
            if abs(d) < 0.012 { presenza[i] = t } else { presenza[i] += d * kp }
            if !voluto[i] && presenza[i] > 0 { qualcunoUscente = true }
        }
        if !qualcunoUscente { uscenti.removeAll(keepingCapacity: true) }

        passoLuce(dt)
        statisticheGruppi(subito: false)

        let calda = alpha >= p.alphaMin || alphaTarget > 0 || trascinato != nil
        if calda { forze(dt) }

        // i nodi che escono tornano verso il vicino piu' prossimo
        let smorzaU = exp(-30 * dt)
        for i in uscenti where presenza[i] > 0 {
            let an = Int(ancora[i])
            if an >= 0 && an != i {
                vel[i] += (pos[an] - pos[i]) * (p.richiamoUscita * dt)
            }
            vel[i] *= smorzaU
            pos[i] += vel[i] * dt
        }
        uscenti.removeAll { presenza[$0] == 0 }

        if calda {
            let smorza = exp(-p.attrito * dt)
            for i in attivi {
                if let t = trascinato, t == i { continue }
                var v = (vel[i] + acc[i] * dt) * smorza
                let m = (v.x * v.x + v.y * v.y).squareRoot()
                if m > p.velocitaMassima { v *= p.velocitaMassima / m }
                vel[i] = v
                pos[i] += v * dt
            }
            let smorzaG = exp(-p.attritoAncore * dt)
            for g in 0..<topo.ng where quanti[g] > 0 {
                velAncora[g] = (velAncora[g] + accAncora[g] * dt) * smorzaG
                ancoreGruppo[g] += velAncora[g] * dt
            }
        } else {
            for i in attivi { vel[i] = .zero }
            for g in 0..<topo.ng { velAncora[g] = .zero }
        }
        if let t = trascinato {
            pos[t] = puntoTrascino
            vel[t] = .zero
        }

        passoCamera(dt)
    }

    private var accAncora: [P2] = []

    private mutating func passoLuce(_ dt: Float) {
        let accesa = nodoInLuce != nil || gruppoInLuce != nil
        let k = p.ridotto ? 1 : 1 - exp(-p.velocitaLuce * dt)
        let tl: Float = accesa ? 1 : 0
        if luce != tl {
            let d = tl - luce
            luce = abs(d) < 0.01 ? tl : luce + d * k
        }
        if accesa {
            for i in 0..<topo.n {
                let t = bersaglioLuce(i)
                if evidenza[i] != t {
                    let d = t - evidenza[i]
                    evidenza[i] = abs(d) < 0.01 ? t : evidenza[i] + d * k
                }
            }
        }
    }

    /// Baricentro, raggio e quanti nodi si vedono, per ogni gruppo.
    private mutating func statisticheGruppi(subito: Bool) {
        let g = topo.ng
        guard g > 0 else { return }
        for k in 0..<g {
            var s = P2.zero
            var c = 0
            var pres: Float = 0
            for i in topo.membri[k] {
                let ii = Int(i)
                pres = max(pres, presenza[ii])
                if voluto[ii] { s += pos[ii]; c += 1 }
            }
            let prima = quanti[k]
            quanti[k] = c
            presenzaG[k] = pres
            if c > 0 { baricentro[k] = s / Float(c) }
            // un gruppo che riappare parte dal baricentro dei suoi nodi
            if c > 0 && prima == 0 && !subito { ancoreGruppo[k] = baricentro[k]; velAncora[k] = .zero }
            let voluta = c > 0 ? p.raggioGruppoPerRadice * Float(c).squareRoot() + p.raggioGruppoBase : 0
            if subito || p.ridotto || raggioG[k] == 0 {
                raggioG[k] = voluta
            } else {
                raggioG[k] += (voluta - raggioG[k]) * (1 - exp(-6 * p.passo))
            }
            // il raggio che contiene davvero i nodi, per il disegno e per il clic
            var r: Float = 0
            if c > 0 {
                for i in topo.membri[k] where voluto[Int(i)] {
                    let d = pos[Int(i)] - baricentro[k]
                    r = max(r, (d.x * d.x + d.y * d.y).squareRoot() + topo.raggio[Int(i)])
                }
            }
            raggioVis[k] = r + p.margineRegione
        }
        if subito { zoomTutto = inquadratura().1 }
    }

    // MARK: le forze

    private mutating func forze(_ dt: Float) {
        let m = attivi.count
        let a = alpha
        for i in attivi { acc[i] = .zero }
        if accAncora.count != topo.ng { accAncora = [P2](repeating: .zero, count: topo.ng) }
        for g in 0..<topo.ng { accAncora[g] = .zero }

        // in un vicinato piccolo i nodi non devono stare lontani come in tutta la mappa
        let scala = min(max((Float(m) / 150).squareRoot(), 0.5), 1)
        let kRep = p.repulsione * a * scala
        let rc = p.raggioRepulsione
        let rc2 = rc * rc
        let margine = p.margineCollisione
        let kColl = p.rigidezzaCollisione
        let fra = p.repulsioneFraGruppi

        // repulsione e collisione, con una griglia: ogni nodo guarda solo le celle accanto
        if m > 1 {
            costruisciGriglia(cella: rc)
            let mask = inizioBucket.count - 2   // la tabella ha dim + 1 posti, dim e' una potenza di due
            var vicineCelle = [Int](repeating: 0, count: 9)
            for x in 0..<m {
                let i = attivi[x]
                let pi = pos[i]
                let qi = topo.carica[i]
                let ri = topo.raggio[i]
                let gi = topo.gruppo[i]
                let cx = Int((pi.x / rc).rounded(.down)), cy = Int((pi.y / rc).rounded(.down))
                var nc = 0
                for ox in -1...1 {
                    for oy in -1...1 {
                        let b = bucket(cx + ox, cy + oy, mask)
                        var nuovo = true
                        for k in 0..<nc where vicineCelle[k] == b { nuovo = false; break }
                        if nuovo { vicineCelle[nc] = b; nc += 1 }
                    }
                }
                for k in 0..<nc {
                    let b = vicineCelle[k]
                    let da = Int(inizioBucket[b]), a1 = Int(inizioBucket[b + 1])
                    var y = da
                    while y < a1 {
                        let j = Int(ordineBucket[y])
                        y += 1
                        if j <= i { continue }
                        var d = pi - pos[j]
                        var d2 = d.x * d.x + d.y * d.y
                        let stessoGruppo = topo.gruppo[j] == gi
                        let rr = ri + topo.raggio[j] + margine
                        if d2 > rc2 && d2 > rr * rr { continue }
                        if d2 < 0.01 {
                            d = P2(casuale(), casuale()) * 0.5
                            d2 = d.x * d.x + d.y * d.y + 0.01
                        }
                        if d2 < rc2 {
                            let sfuma = 1 - d2 / rc2
                            let w = kRep * sfuma * (stessoGruppo ? 1 : fra) / max(d2, 40)
                            acc[i] += d * (w * topo.carica[j])
                            acc[j] -= d * (w * qi)
                        }
                        if d2 < rr * rr {
                            let dist = d2.squareRoot()
                            let spinta = (rr - dist) / dist * kColl * 0.5
                            acc[i] += d * spinta
                            acc[j] -= d * spinta
                        }
                    }
                }
            }
        }

        // le molle dei legami: corte dentro un gruppo, lunghe e deboli sui ponti
        let L = p.lunghezzaLegame, k = p.rigidezzaLegame * a
        for e in topo.da.indices {
            let s = Int(topo.da[e]), t = Int(topo.a[e])
            guard voluto[s], voluto[t] else { continue }
            var d = pos[t] + vel[t] * dt - pos[s] - vel[s] * dt
            var l = (d.x * d.x + d.y * d.y).squareRoot()
            if l < 0.001 { d = P2(casuale(), casuale()); l = 0.5 }
            var lunghezza = L
            var rigidezza = k * forzaLegame[e]
            if topo.ponte[e] {
                let gs = Int(topo.gruppo[s]), gt = Int(topo.gruppo[t])
                lunghezza = distanzaGruppi(gs, gt) * 0.8 + 6
                rigidezza = k * p.rigidezzaPonte * min(forzaLegame[e] * 2, 1)
            }
            let f = (l - lunghezza) / l * rigidezza
            d *= f
            let b = biasLegame[e]
            acc[t] -= d * b
            acc[s] += d * (1 - b)
        }

        // dentro il gruppo: verso l'ancora, appena al centro e forte oltre il raggio
        for i in attivi {
            let g = Int(topo.gruppo[i])
            let d = ancoreGruppo[g] - pos[i]
            let dist = (d.x * d.x + d.y * d.y).squareRoot()
            let R = max(raggioG[g], 20)
            let fuori = max(0, dist - R * 0.7) / R
            // il richiamo al centro si raffredda col resto; il confine del disco no: e' un vincolo
            let kk = p.richiamoCentro * a + p.richiamoOltre * fuori * fuori
            var f = d * kk
            // un nodo lontanissimo (dopo un cambio di gruppi) non deve far schizzare niente
            let f2 = f.x * f.x + f.y * f.y
            if f2 > 36_000_000 { f *= 6000 / f2.squareRoot() }
            acc[i] += f
            // la reazione: l'ancora si fa tirare dai suoi nodi, in proporzione al peso del gruppo
            accAncora[g] -= f * (p.reazioneAncora / Float(max(quanti[g], 1)))
        }

        // fra i gruppi
        fraGruppi(a)
    }

    /// La distanza a cui due ancore vogliono stare: i dischi si toccano, meno se hanno molti ponti.
    private func distanzaGruppi(_ x: Int, _ y: Int) -> Float {
        let ponti = topo.legami[x * topo.ng + y]
        let vuoto = max(p.distanzaMinimaGruppi, p.distanzaGruppiBase - 14 * ponti.squareRoot())
        return raggioG[x] + raggioG[y] + vuoto
    }

    private mutating func fraGruppi(_ a: Float) {
        let g = topo.ng
        guard g > 0 else { return }
        for x in 0..<g where quanti[x] > 0 {
            // l'ancora segue il baricentro: se un nodo si trascina, il gruppo lo segue
            accAncora[x] += (baricentro[x] - ancoreGruppo[x]) * (p.seguiCentro * a)
            accAncora[x] -= ancoreGruppo[x] * (p.gravitaGruppi * a)
            guard x + 1 < g else { continue }
            for y in (x + 1)..<g where quanti[y] > 0 {
                var d = ancoreGruppo[y] - ancoreGruppo[x]
                var dist = (d.x * d.x + d.y * d.y).squareRoot()
                if dist < 0.01 { d = P2(casuale(), casuale()); dist = 0.8 }
                let voluta = distanzaGruppi(x, y)
                let ponti = topo.legami[x * g + y]
                var forza: Float = 0
                if dist < voluta {
                    forza = -(voluta - dist) * p.respingimentoGruppi * a
                } else if ponti > 0 {
                    forza = (dist - voluta) * p.attrazionePonti * min(ponti, 6) / 6 * a
                }
                if forza == 0 { continue }
                let dir = d / dist
                // il gruppo piu' grosso si sposta meno
                let mx = Float(quanti[x]).squareRoot(), my = Float(quanti[y]).squareRoot()
                accAncora[x] += dir * (forza * my / (mx + my) * 2)
                accAncora[y] -= dir * (forza * mx / (mx + my) * 2)
            }
        }
    }

    // MARK: la griglia

    private func bucket(_ cx: Int, _ cy: Int, _ mask: Int) -> Int {
        let h = (UInt32(truncatingIfNeeded: cx) &* 73856093) ^ (UInt32(truncatingIfNeeded: cy) &* 19349663)
        return Int(h) & mask
    }

    /// Mette i nodi che si vedono in celle di lato `cella` (con una tabella di dimensione
    /// fissa: due celle che finiscono nello stesso posto danno solo qualche confronto in piu').
    private mutating func costruisciGriglia(cella: Float) {
        let m = attivi.count
        var dim = 64
        while dim < m * 2 { dim <<= 1 }
        if inizioBucket.count != dim + 1 {
            inizioBucket = [Int32](repeating: 0, count: dim + 1)
        } else {
            for i in 0..<inizioBucket.count { inizioBucket[i] = 0 }
        }
        if bucketDi.count != topo.n { bucketDi = [Int32](repeating: 0, count: topo.n) }
        if ordineBucket.count != m { ordineBucket = [Int32](repeating: 0, count: m) }
        let mask = dim - 1
        for i in attivi {
            let cx = Int((pos[i].x / cella).rounded(.down)), cy = Int((pos[i].y / cella).rounded(.down))
            let b = bucket(cx, cy, mask)
            bucketDi[i] = Int32(b)
            inizioBucket[b + 1] += 1
        }
        for b in 0..<dim { inizioBucket[b + 1] += inizioBucket[b] }
        var riempimento = [Int32](repeating: 0, count: dim)
        for i in attivi {
            let b = Int(bucketDi[i])
            ordineBucket[Int(inizioBucket[b] + riempimento[b])] = Int32(i)
            riempimento[b] += 1
        }
    }

    // MARK: la camera

    private mutating func passoCamera(_ dt: Float) {
        let (cTutto, zTutto) = inquadratura()
        zoomTutto = zTutto
        if camera.segui {
            camera.tc = cTutto
            camera.tz = zTutto
        }
        if p.ridotto {
            camera.c = camera.tc; camera.z = camera.tz
            camera.vc = .zero; camera.vz = 0; camera.inerzia = .zero
            if let am = camera.ancoraMondo { camera.c = am - (camera.ancoraSchermo - camera.vista / 2) / camera.z }
            camera.ancoraMondo = nil
            camera.panoramica = false
            return
        }
        if camera.panoramica {
            storiaCentro.append(camera.c)
            if storiaCentro.count > 12 { storiaCentro.removeFirst() }
            passiDaPan += 1
            if passiDaPan <= 30 { return }
            rilasciaPanoramica()
        }
        // l'inerzia dopo un pan: la scena continua e rallenta
        let inerte = abs(camera.inerzia.x) >= 0.5 || abs(camera.inerzia.y) >= 0.5
        if inerte {
            camera.c += camera.inerzia * dt
            camera.inerzia *= exp(-3.4 * dt)
            camera.tc = camera.c
            camera.vc = .zero
        }
        // oltre i bordi la camera torna con una molla morbida (il rimbalzo)
        if !camera.segui && camera.ancoraMondo == nil {
            let dentro = dentroLimiti(camera.c)
            if dentro != camera.c {
                camera.tc = dentro
                if inerte { camera.inerzia *= exp(-5 * dt) }
            } else if inerte {
                camera.tc = camera.c
            }
        }
        // molla smorzata, appena sotto lo smorzamento critico: si assesta con un filo di rimbalzo
        let w: Float = 13, zeta: Float = 0.86
        if !(inerte && camera.tc == camera.c) {
            camera.vc += ((camera.tc - camera.c) * (w * w) - camera.vc * (2 * zeta * w)) * dt
            camera.c += camera.vc * dt
        }
        let lz = log(camera.z), tlz = log(camera.tz)
        camera.vz += ((tlz - lz) * (w * w) - camera.vz * (2 * zeta * w)) * dt
        camera.z = exp(lz + camera.vz * dt)
        // durante lo zoom il punto sotto il puntatore non si sposta
        if let am = camera.ancoraMondo {
            camera.c = am - (camera.ancoraSchermo - camera.vista / 2) / camera.z
            camera.tc = am - (camera.ancoraSchermo - camera.vista / 2) / camera.tz
            camera.vc = .zero
            if abs(log(camera.tz / camera.z)) < 0.0008 && abs(camera.vz) < 0.01 {
                camera.z = camera.tz; camera.c = camera.tc; camera.vz = 0
                camera.ancoraMondo = nil
            }
        }
        if camera.ferma {
            camera.c = camera.tc; camera.z = camera.tz
            camera.vc = .zero; camera.vz = 0; camera.inerzia = .zero
        }
    }
}
