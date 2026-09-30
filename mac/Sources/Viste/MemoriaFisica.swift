// Memoria, la mappa globale: la fisica.
//
// Solo Foundation, niente SwiftUI e niente thread principale: questo file e' la
// simulazione pura (un valore che avanza di un passo fisso alla volta) e serve alla
// prova in mac/Prove, che la compila da sola. Il motore che la fa girare fuori dal
// thread principale sta in MemoriaMotore.swift, il disegno in MemoriaMappa.swift.
//
// Le forze sono quelle classiche di un grafo a molle:
//   - repulsione fra i nodi (a corto raggio, con un tetto), piu' forte per i nodi molto
//     collegati, cosi' gli hub si fanno spazio;
//   - una molla per ogni legame, che tira meno sull'hub e piu' sulla foglia;
//   - gravita' verso il centro, piu' forte per i nodi senza legami, che altrimenti
//     andrebbero alla deriva;
//   - una collisione morbida fra i cerchi, perche' non si sovrappongano;
//   - lo smorzamento, e un "calore" (alpha) che scende passo dopo passo: quando e'
//     sotto la soglia la simulazione e' ferma e non costa piu' niente.
// Un nodo che si trascina viene tenuto sul puntatore, e riscalda la simulazione finche'
// non lo si rilascia.
//
// I livelli (1, 2, Tutto) sono un insieme di nodi "voluti". Quelli che entrano nascono
// sul vicino che c'era gia' e si allargano con le molle; quelli che escono vengono
// richiamati sul vicino piu' prossimo mentre svaniscono. La camera e' una molla
// smorzata anche lei: inquadra i nodi voluti finche' non si comanda a mano.

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

    /// `archi` senza cappi e senza doppioni; `iniziali` opzionale (una spirale se manca o
    /// se ha la misura sbagliata).
    init(n: Int, archi: [(Int, Int)], iniziali: [P2]? = nil) {
        self.n = max(n, 0)
        var visti = Set<Int64>()
        var d: [Int32] = [], b: [Int32] = []
        var vic = [[Int32]](repeating: [], count: max(n, 0))
        for (x, y) in archi where x != y && x >= 0 && y >= 0 && x < n && y < n {
            let k = Int64(min(x, y)) << 32 | Int64(max(x, y))
            if !visti.insert(k).inserted { continue }
            d.append(Int32(x)); b.append(Int32(y))
            vic[x].append(Int32(y)); vic[y].append(Int32(x))
        }
        da = d; a = b; vicini = vic
        grado = vic.map { Int32($0.count) }
        raggio = vic.map { min(4.5 + 1.7 * Float($0.count).squareRoot(), 15) }
        carica = vic.map { 1 + 0.45 * Float($0.count).squareRoot() }
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

struct ParametriFisica: Sendable {
    var lunghezzaLegame: Float = 50
    var rigidezzaLegame: Float = 0.6
    var repulsione: Float = 70
    var raggioRepulsione: Float = 380
    var gravita: Float = 0.04
    var gravitaOrfani: Float = 0.11
    var attrito: Float = 0.42
    var alphaMin: Float = 0.0015
    var decadimento: Float = 0.032
    var margineCollisione: Float = 4
    var rigidezzaCollisione: Float = 0.6
    var richiamoUscita: Float = 0.10
    var velocitaMassima: Float = 30
    /// quanto scalda (alpha) un cambio di livello e un trascinamento
    var caloreCambio: Float = 0.75
    var caloreTrascino: Float = 0.30

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

    static let zoomMinimo: Float = 0.05
    static let zoomMassimo: Float = 8
    static let zoomInquadraturaMassimo: Float = 1.7

    var ferma: Bool {
        let d = tc - c
        return abs(d.x) < 0.04 && abs(d.y) < 0.04 && abs(log(tz / z)) < 0.0008
            && abs(vc.x) < 0.01 && abs(vc.y) < 0.01 && abs(vz) < 0.0002
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

    init(topologia: TopologiaGrafo, parametri: ParametriFisica = .standard) {
        topo = topologia
        p = parametri
        pos = topologia.iniziali
        vel = [P2](repeating: .zero, count: topologia.n)
        presenza = [Float](repeating: 1, count: topologia.n)
        voluto = [Bool](repeating: true, count: topologia.n)
        attivi = Array(0..<topologia.n)
        ancora = [Int32](repeating: -1, count: topologia.n)
        forzaLegame = []
        biasLegame = []
        for k in topologia.da.indices {
            let x = Int(topologia.da[k]), y = Int(topologia.a[k])
            let gx = Float(topologia.grado[x]), gy = Float(topologia.grado[y])
            forzaLegame.append(1 / max(min(gx, gy), 1))
            biasLegame.append(gx / max(gx + gy, 1))
        }
    }

    // MARK: stato

    var posizioni: [P2] { pos }
    var presenze: [Float] { presenza }
    var voluti: [Bool] { voluto }

    /// Tutto quello che si muove e' arrivato: niente da calcolare, niente da disegnare.
    var ferma: Bool {
        guard alpha < p.alphaMin, alphaTarget == 0, trascinato == nil, uscenti.isEmpty else { return false }
        for i in 0..<topo.n {
            let t: Float = voluto[i] ? 1 : 0
            if presenza[i] != t { return false }
        }
        return camera.ferma
    }

    func foto(versione: Int) -> FotoScena {
        FotoScena(pos: pos, presenza: presenza, voluto: voluto, camera: camera,
                  versione: versione, ferma: ferma)
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
        if scalda { alpha = max(alpha, p.caloreCambio) }
        camera.segui = true
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

    // MARK: camera

    mutating func dimensioniVista(_ w: Float, _ h: Float) {
        guard w > 8, h > 8 else { return }
        camera.vista = P2(w, h)
    }

    /// Prende la camera di una simulazione precedente (cambiano i dati, la vista resta).
    mutating func adotta(camera vecchia: CameraSim) {
        camera = vecchia
        camera.segui = true
    }

    /// Torna a seguire i nodi voluti.
    mutating func inquadra(subito: Bool = false) {
        camera.segui = true
        let (c, z) = inquadratura()
        camera.tc = c; camera.tz = z
        if subito { camera.c = c; camera.z = z; camera.vc = .zero; camera.vz = 0 }
    }

    /// Centro e zoom che mostrano tutti i nodi voluti.
    func inquadratura() -> (P2, Float) {
        var minP = P2(repeating: .infinity), maxP = P2(repeating: -.infinity)
        var qualcuno = false
        for i in attivi {
            let r = P2(repeating: topo.raggio[i] + 6)
            minP = pointwiseMin(minP, pos[i] - r)
            maxP = pointwiseMax(maxP, pos[i] + r)
            qualcuno = true
        }
        guard qualcuno else { return (.zero, 1) }
        let dim = maxP - minP
        // spazio per le etichette ai lati
        let margine = P2(110, 64)
        let libero = pointwiseMax(camera.vista - margine * 2, P2(80, 80))
        let z = min(libero.x / max(dim.x, 40), libero.y / max(dim.y, 40))
        return ((minP + maxP) / 2,
                min(max(z, CameraSim.zoomMinimo), CameraSim.zoomInquadraturaMassimo))
    }

    /// Porta la camera su un punto del mondo, a un dato zoom (smette di seguire).
    mutating func centra(su punto: P2, zoom z: Float) {
        camera.segui = false
        camera.tc = punto
        camera.tz = min(max(z, CameraSim.zoomMinimo), CameraSim.zoomMassimo)
    }

    /// Fa avanzare la simulazione fino a fermarla (per le istantanee e per le prove).
    mutating func assesta(massimo: Int = 2000) {
        var k = 0
        while !ferma && k < massimo { passo(); k += 1 }
    }

    /// Un passo di zoom, tenendo fermo il punto `ancoraSchermo` (o il centro della vista).
    mutating func zoom(fattore: Float, ancoraSchermo: P2? = nil) {
        camera.segui = false
        let s = ancoraSchermo ?? camera.vista / 2
        let w = camera.mondo(s, centro: camera.tc, zoom: camera.tz)
        let nz = min(max(camera.tz * fattore, CameraSim.zoomMinimo), CameraSim.zoomMassimo)
        camera.tz = nz
        camera.tc = w - (s - camera.vista / 2) / nz
    }

    /// Sposta la vista di `delta` punti-schermo (la scena segue il dito).
    mutating func panora(schermo delta: P2) {
        camera.segui = false
        camera.c -= delta / camera.z
        camera.tc -= delta / camera.z
        camera.vc = .zero
    }

    // MARK: un passo (1/60 s)

    mutating func passo() {
        passiFatti += 1
        let n = topo.n
        guard n > 0 else { return }

        alpha += (alphaTarget - alpha) * p.decadimento

        // la presenza cala o cresce verso il voluto
        var qualcunoUscente = false
        for i in 0..<n {
            let t: Float = voluto[i] ? 1 : 0
            let d = t - presenza[i]
            if d == 0 { continue }
            if abs(d) < 0.012 { presenza[i] = t } else { presenza[i] += d * 0.16 }
            if !voluto[i] && presenza[i] > 0 { qualcunoUscente = true }
        }
        if !qualcunoUscente { uscenti.removeAll(keepingCapacity: true) }

        let calda = alpha >= p.alphaMin || alphaTarget > 0 || trascinato != nil
        if calda { forze() }

        // i nodi che escono tornano verso il vicino piu' prossimo
        for i in uscenti where presenza[i] > 0 {
            let an = Int(ancora[i])
            if an >= 0 && an != i {
                vel[i] += (pos[an] - pos[i]) * p.richiamoUscita
            }
            vel[i] *= (1 - p.attrito)
            pos[i] += vel[i]
        }
        uscenti.removeAll { presenza[$0] == 0 }

        if calda {
            for i in attivi {
                if let t = trascinato, t == i { continue }
                var v = vel[i] * (1 - p.attrito)
                let m = (v.x * v.x + v.y * v.y).squareRoot()
                if m > p.velocitaMassima { v *= p.velocitaMassima / m }
                vel[i] = v
                pos[i] += v
            }
        } else {
            for i in attivi { vel[i] = .zero }
        }
        if let t = trascinato {
            pos[t] = puntoTrascino
            vel[t] = .zero
        }

        passoCamera()
    }

    private mutating func forze() {
        let m = attivi.count
        let a = alpha
        let r2max = p.raggioRepulsione * p.raggioRepulsione
        // in un vicinato piccolo i nodi non devono stare lontani come in tutta la mappa
        let scala = min(max((Float(m) / 150).squareRoot(), 0.45), 1)
        let kRep = p.repulsione * a * scala
        let margine = p.margineCollisione
        let kColl = p.rigidezzaCollisione

        // repulsione e collisione, a coppie
        if m > 1 {
            for x in 0..<m {
                let i = attivi[x]
                let pi = pos[i]
                let qi = topo.carica[i]
                let ri = topo.raggio[i]
                var acc = P2.zero
                for y in (x + 1)..<m {
                    let j = attivi[y]
                    var d = pi - pos[j]
                    var d2 = d.x * d.x + d.y * d.y
                    if d2 > r2max { continue }
                    if d2 < 0.01 {
                        d = P2(casuale(), casuale()) * 0.5
                        d2 = d.x * d.x + d.y * d.y + 0.01
                    }
                    let w = kRep / max(d2, 40)
                    let fi = d * (w * topo.carica[j])
                    acc += fi
                    vel[j] -= d * (w * qi)
                    let rr = ri + topo.raggio[j] + margine
                    if d2 < rr * rr {
                        let dist = d2.squareRoot()
                        let spinta = (rr - dist) / dist * kColl * 0.5
                        acc += d * spinta
                        vel[j] -= d * spinta
                    }
                }
                vel[i] += acc
            }
        }

        // le molle dei legami
        let L = p.lunghezzaLegame, k = p.rigidezzaLegame * a
        for e in topo.da.indices {
            let s = Int(topo.da[e]), t = Int(topo.a[e])
            guard voluto[s], voluto[t] else { continue }
            var d = pos[t] + vel[t] - pos[s] - vel[s]
            var l = (d.x * d.x + d.y * d.y).squareRoot()
            if l < 0.001 { d = P2(casuale(), casuale()); l = 0.5 }
            let f = (l - L) / l * k * forzaLegame[e]
            d *= f
            let b = biasLegame[e]
            vel[t] -= d * b
            vel[s] += d * (1 - b)
        }

        // gravita' verso il centro
        for i in attivi {
            let g = topo.grado[i] == 0 ? p.gravitaOrfani : p.gravita
            vel[i] -= pos[i] * (g * a)
        }
    }

    private mutating func passoCamera() {
        if camera.segui {
            let (c, z) = inquadratura()
            camera.tc = c
            camera.tz = z
        }
        // molla smorzata, appena sotto lo smorzamento critico: si assesta con un filo di rimbalzo
        let k: Float = 0.055, smorza: Float = 0.80
        camera.vc = (camera.vc + (camera.tc - camera.c) * k) * smorza
        camera.c += camera.vc
        let lz = log(camera.z), tlz = log(camera.tz)
        camera.vz = (camera.vz + (tlz - lz) * k) * smorza
        camera.z = exp(lz + camera.vz)
        if camera.ferma {
            camera.c = camera.tc; camera.z = camera.tz
            camera.vc = .zero; camera.vz = 0
        }
    }
}
