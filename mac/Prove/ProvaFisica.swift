// La prova della fisica della Mappa della memoria, senza interfaccia: compila da sola
// MemoriaFisica.swift (solo Foundation) insieme a questo file e la fa girare su grafi di
// prova con un seme fisso. La lancia mac/Prove/controlli_sorgenti.py (e quindi
// tools/prova-mac.sh):
//
//   xcrun swiftc -O -parse-as-library MemoriaFisica.swift ProvaFisica.swift -o prova-fisica
//
// Con -D SENZA_GRUPPI costruisce la topologia con la firma vecchia (nessun gruppo), e le
// misure sui gruppi si fanno comunque sugli stessi gruppi pensati dalla prova: serve a
// vedere ROSSA la prova sul codice di prima.
// Con PROVA_FISICA_DUMP=<file> scrive le posizioni finali in JSON, per guardarle.

import Foundation

nonisolated(unsafe) var falliti = 0
nonisolated(unsafe) var passati = 0

func prova(_ nome: String, _ ok: Bool, _ dettaglio: String = "") {
    if ok { passati += 1; print("  ok   \(nome)") }
    else { falliti += 1; print("  NO   \(nome) \(dettaglio)") }
}

/// I parametri della prova: quelli di serie, o quelli cambiati da PROVA_FISICA_PARAMETRI="nome=valore,..."
/// (per cercare a mano i valori buoni senza ricompilare).
nonisolated(unsafe) var PAR = ParametriFisica.standard

func leggiParametri() {
    #if !SENZA_GRUPPI
    guard let t = ProcessInfo.processInfo.environment["PROVA_FISICA_PARAMETRI"] else { return }
    let chiavi: [String: WritableKeyPath<ParametriFisica, Float>] = [
        "lunghezzaLegame": \.lunghezzaLegame, "rigidezzaLegame": \.rigidezzaLegame, "repulsione": \.repulsione,
        "raggioRepulsione": \.raggioRepulsione, "repulsioneFraGruppi": \.repulsioneFraGruppi,
        "margineCollisione": \.margineCollisione, "rigidezzaCollisione": \.rigidezzaCollisione,
        "richiamoCentro": \.richiamoCentro, "richiamoOltre": \.richiamoOltre, "rigidezzaPonte": \.rigidezzaPonte,
        "distanzaMinimaGruppi": \.distanzaMinimaGruppi, "distanzaGruppiBase": \.distanzaGruppiBase,
        "respingimentoGruppi": \.respingimentoGruppi, "attrazionePonti": \.attrazionePonti,
        "gravitaGruppi": \.gravitaGruppi, "seguiCentro": \.seguiCentro, "reazioneAncora": \.reazioneAncora,
        "attritoAncore": \.attritoAncore, "attrito": \.attrito, "raggioGruppoPerRadice": \.raggioGruppoPerRadice,
        "raggioGruppoBase": \.raggioGruppoBase, "raffreddamento": \.raffreddamento, "caloreCambio": \.caloreCambio,
        "caloreTrascino": \.caloreTrascino]
    for coppia in t.split(separator: ",") {
        let kv = coppia.split(separator: "=")
        if kv.count == 2, let k = chiavi[String(kv[0])], let v = Float(kv[1]) { PAR[keyPath: k] = v }
    }
    #endif
}

struct Seme {
    var s: UInt64
    mutating func prossimo() -> UInt64 {
        s = s &* 6364136223846793005 &+ 1442695040888963407
        return s >> 33
    }
    mutating func fra(_ n: Int) -> Int { Int(prossimo() % UInt64(max(n, 1))) }
}

/// Un grafo con gruppi: dentro ogni gruppo un anello e qualche corda, fra i gruppi pochi ponti.
struct GrafoProva {
    var gruppo: [Int] = []
    var archi: [(Int, Int)] = []
    var nomiGruppo: [String] = []
    var n: Int { gruppo.count }

    init(dimensioni: [Int], ponti: Int, seme: UInt64 = 7) {
        var r = Seme(s: seme)
        // i nodi dei gruppi sono mescolati: la spirale iniziale non deve aiutare
        var elenco: [Int] = []
        for (g, d) in dimensioni.enumerated() { for _ in 0..<d { elenco.append(g) } }
        for i in stride(from: elenco.count - 1, to: 0, by: -1) { elenco.swapAt(i, r.fra(i + 1)) }
        gruppo = elenco
        nomiGruppo = dimensioni.indices.map { "gruppo-\($0)" }
        var per: [[Int]] = Array(repeating: [], count: dimensioni.count)
        for (i, g) in elenco.enumerated() { per[g].append(i) }
        for membri in per where membri.count > 1 {
            for k in 0..<membri.count { archi.append((membri[k], membri[(k + 1) % membri.count])) }
            for _ in 0..<(membri.count / 2) {
                let a = membri[r.fra(membri.count)], b = membri[r.fra(membri.count)]
                if a != b { archi.append((a, b)) }
            }
        }
        var fatti = 0
        while fatti < ponti {
            let a = r.fra(elenco.count), b = r.fra(elenco.count)
            if elenco[a] != elenco[b] { archi.append((a, b)); fatti += 1 }
        }
    }

    func topologia(iniziali: [P2]? = nil) -> TopologiaGrafo {
        #if SENZA_GRUPPI
        return TopologiaGrafo(n: n, archi: archi, iniziali: iniziali)
        #else
        return TopologiaGrafo(n: n, archi: archi, iniziali: iniziali, gruppo: gruppo)
        #endif
    }
}

func dist(_ a: P2, _ b: P2) -> Float { let d = a - b; return (d.x * d.x + d.y * d.y).squareRoot() }

struct Misure {
    var separazione: Float = 0      // distanza minima fra due gruppi / somma dei loro raggi
    var coerenza: Float = 0         // quota dei nodi con i tre vicini piu' prossimi nello stesso gruppo
    var rapportoPonti: Float = 0    // lunghezza media dei ponti / dei legami interni
    var sovrapposti: Float = 0      // quota delle coppie di nodi che si toccano
}

func misura(_ g: GrafoProva, _ pos: [P2], raggi: [Float]) -> Misure {
    var m = Misure()
    let ng = (g.gruppo.max() ?? 0) + 1
    var cen = [P2](repeating: .zero, count: ng), cnt = [Float](repeating: 0, count: ng)
    for (i, k) in g.gruppo.enumerated() { cen[k] += pos[i]; cnt[k] += 1 }
    for k in 0..<ng where cnt[k] > 0 { cen[k] /= cnt[k] }
    var rad = [Float](repeating: 0, count: ng)
    for (i, k) in g.gruppo.enumerated() { rad[k] = max(rad[k], dist(pos[i], cen[k]) + raggi[i]) }
    var minimo = Float.infinity
    for a in 0..<ng where cnt[a] > 0 {
        for b in (a + 1)..<max(ng, a + 1) where cnt[b] > 0 {
            minimo = min(minimo, dist(cen[a], cen[b]) / (rad[a] + rad[b]))
        }
    }
    m.separazione = minimo
    var buoni = 0
    for i in 0..<g.n {
        let ordine = (0..<g.n).filter { $0 != i }.sorted { dist(pos[i], pos[$0]) < dist(pos[i], pos[$1]) }
        if ordine.prefix(3).allSatisfy({ g.gruppo[$0] == g.gruppo[i] }) { buoni += 1 }
    }
    m.coerenza = Float(buoni) / Float(g.n)
    var lp: Float = 0, np: Float = 0, li: Float = 0, ni: Float = 0
    for (a, b) in g.archi {
        if g.gruppo[a] == g.gruppo[b] { li += dist(pos[a], pos[b]); ni += 1 } else { lp += dist(pos[a], pos[b]); np += 1 }
    }
    m.rapportoPonti = (lp / max(np, 1)) / max(li / max(ni, 1), 1)
    var tocc = 0, coppie = 0
    for i in 0..<g.n { for j in (i + 1)..<max(g.n, i + 1) {
        coppie += 1
        if dist(pos[i], pos[j]) < raggi[i] + raggi[j] { tocc += 1 }
    } }
    m.sovrapposti = Float(tocc) / Float(max(coppie, 1))
    return m
}

func baricentro(_ g: GrafoProva, _ pos: [P2], gruppo k: Int) -> P2 {
    var s = P2.zero, c: Float = 0
    for (i, kk) in g.gruppo.enumerated() where kk == k { s += pos[i]; c += 1 }
    return c > 0 ? s / c : .zero
}

func scrivi(_ g: GrafoProva, _ sim: SimulazioneGrafo, _ file: String) {
    var nodi: [[String: Any]] = []
    for i in 0..<g.n { nodi.append(["x": Double(sim.posizioni[i].x), "y": Double(sim.posizioni[i].y), "g": g.gruppo[i], "r": Double(sim.topo.raggio[i])]) }
    let archi = g.archi.map { [$0.0, $0.1] }
    let dati = try? JSONSerialization.data(withJSONObject: ["nodi": nodi, "archi": archi])
    FileManager.default.createFile(atPath: file, contents: dati)
}

@main
struct ProvaFisica {
    static func main() {
        leggiParametri()
        let g = GrafoProva(dimensioni: [22, 16, 12, 10, 8, 8, 6, 5, 3], ponti: 22)
        let topo = g.topologia()
        var sim = SimulazioneGrafo(topologia: topo, parametri: PAR)
        sim.dimensioniVista(900, 640)
        sim.assesta()
        let finale = sim.posizioni
        let m = misura(g, finale, raggi: topo.raggio)
        if let f = ProcessInfo.processInfo.environment["PROVA_FISICA_DUMP"] { scrivi(g, sim, f) }
        print("== gruppi: separazione \(m.separazione), coerenza \(m.coerenza), ponti \(m.rapportoPonti), sovrapposti \(m.sovrapposti)")

        print("== i gruppi sono isole chiare")
        prova("la scena si assesta da sola (ferma)", sim.ferma)
        prova("i dischi dei gruppi non si sovrappongono (separazione >= 0.7)", m.separazione >= 0.7, "\(m.separazione)")
        prova("i vicini piu' prossimi di un nodo sono del suo gruppo (>= 90%)", m.coerenza >= 0.9, "\(m.coerenza)")
        prova("i ponti sono piu' lunghi dei legami interni (>= 1.6 volte)", m.rapportoPonti >= 1.6, "\(m.rapportoPonti)")
        prova("i nodi non si sovrappongono (< 1% delle coppie)", m.sovrapposti < 0.01, "\(m.sovrapposti)")

        #if !SENZA_GRUPPI
        provaTrascino(g)
        provaLuce(g)
        provaCamera(g)
        provaPrestazioni()
        #endif

        print("\(passati) ok, \(falliti) falliti")
        exit(falliti == 0 ? 0 : 1)
    }

    #if !SENZA_GRUPPI
    static func provaTrascino(_ g: GrafoProva) {
        print("== il gruppo segue il nodo trascinato, in modo elastico")
        var sim = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        sim.dimensioniVista(900, 640)
        sim.assesta()
        let prima = sim.posizioni
        // un nodo del gruppo piu' piccolo
        let k = 8
        guard let i = g.gruppo.firstIndex(of: k) else { return prova("c'e' un nodo da trascinare", false) }
        let b0 = baricentro(g, prima, gruppo: k)
        let verso = prima[i] + P2(260, 0)
        sim.iniziaTrascino(i, in: prima[i])
        for s in 0..<240 {
            let t = Float(s + 1) / 240
            sim.trascina(a: prima[i] + (verso - prima[i]) * t)
            sim.passo()
        }
        let durante = sim.posizioni
        let b1 = baricentro(g, durante, gruppo: k)
        let seguito = (b1.x - b0.x) / 260
        prova("durante il trascinamento il gruppo si sposta verso il nodo (>= 25% dello spostamento)", seguito >= 0.25, "\(seguito)")
        prova("il nodo sta sul puntatore", dist(durante[i], verso) < 0.5)
        // gli altri gruppi, i piu' lontani, si muovono poco
        var massimo: Float = 0
        for h in 0..<8 {
            let d = dist(baricentro(g, durante, gruppo: h), baricentro(g, prima, gruppo: h))
            massimo = max(massimo, d)
        }
        prova("gli altri gruppi non vengono trascinati dietro (< 130 unita')", massimo < 130, "\(massimo)")
        sim.rilascia()
        sim.assesta()
        let dopo = sim.posizioni
        let m = misura(g, dopo, raggi: sim.topo.raggio)
        prova("dopo il rilascio la scena si riassesta e i gruppi restano isole", sim.ferma && m.separazione >= 0.65, "\(m.separazione)")
    }

    static func provaLuce(_ g: GrafoProva) {
        print("== la luce: il nodo, i suoi vicini e il resto attenuato")
        var sim = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        sim.dimensioniVista(900, 640)
        sim.assesta()
        prova("senza luce nessun nodo e' attenuato (luce 0)", sim.luceAccesa == 0)
        sim.illumina(nodo: 0, gruppo: nil)
        prova("accendere la luce rimette in moto la scena", !sim.ferma)
        sim.assesta()
        let vicini = Set(sim.topo.vicini[0].map { Int($0) })
        var ok = sim.luceAccesa == 1 && sim.evidenze[0] == 1
        var lontano = -1
        for i in 1..<g.n {
            if vicini.contains(i) { ok = ok && sim.evidenze[i] == 1 }
            else { ok = ok && sim.evidenze[i] == 0; lontano = i }
        }
        prova("il nodo e i suoi vicini restano in luce, gli altri si spengono", ok && lontano > 0)
        sim.illumina(nodo: nil, gruppo: 3)
        sim.assesta()
        let tuttiDelGruppo = (0..<g.n).allSatisfy { sim.evidenze[$0] == (g.gruppo[$0] == 3 ? 1 : 0) }
        prova("la luce su un gruppo tiene i suoi nodi e spegne gli altri", tuttiDelGruppo)
        sim.illumina(nodo: nil, gruppo: nil)
        sim.assesta()
        prova("spenta la luce la scena torna ferma", sim.ferma && sim.luceAccesa == 0)
        // con "Riduci movimento" la luce e' subito dove deve
        var r = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        r.imposta(ridotto: true)
        r.illumina(nodo: 0, gruppo: nil)
        prova("con Riduci movimento la luce arriva senza transizione", r.luceAccesa == 1 && r.evidenze[g.n - 1] == (r.topo.vicini[0].contains(Int32(g.n - 1)) ? 1 : 0))
    }

    static func provaCamera(_ g: GrafoProva) {
        print("== la camera: zoom sul puntatore, inerzia, rimbalzo, gruppo inquadrato")
        var sim = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        sim.dimensioniVista(900, 640)
        sim.assesta()
        // zoom verso un punto: il punto del mondo sotto il puntatore resta sotto il puntatore
        let puntatore = P2(700, 150)
        let sotto = sim.camera.mondo(puntatore, centro: sim.camera.c, zoom: sim.camera.z)
        sim.zoom(fattore: 2.2, ancoraSchermo: puntatore)
        var scarto: Float = 0
        for _ in 0..<400 {
            sim.passo()
            let s = sim.camera.schermo(sotto)
            scarto = max(scarto, dist(s, puntatore))
        }
        prova("durante lo zoom il punto sotto il puntatore non si sposta (< 1 punto)", scarto < 1, "\(scarto)")
        prova("lo zoom arriva", abs(sim.camera.z / sim.camera.tz - 1) < 0.01)

        // inerzia: dopo il rilascio la camera continua e poi si ferma
        sim.assesta()
        let c0 = sim.camera.c
        for _ in 0..<30 { sim.panora(schermo: P2(-14, 0)); sim.passo() }
        let c1 = sim.camera.c
        sim.rilasciaPanoramica()
        for _ in 0..<12 { sim.passo() }
        let c2 = sim.camera.c
        prova("durante il pan la camera segue il dito", c1.x > c0.x)
        prova("dopo il rilascio la camera continua per inerzia", c2.x > c1.x + 1, "\(c2.x - c1.x)")
        sim.assesta()
        prova("l'inerzia si esaurisce e la camera e' ferma", sim.camera.ferma)

        // un gesto che finisce senza dirlo (annullato) non lascia la scena accesa per sempre
        var abbandonata = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        abbandonata.dimensioniVista(900, 640)
        abbandonata.assesta()
        for _ in 0..<10 { abbandonata.panora(schermo: P2(-6, 0)); abbandonata.passo() }
        abbandonata.assesta()
        prova("un pan mai rilasciato si libera da solo e la scena torna ferma", abbandonata.ferma)

        // con Riduci movimento niente inerzia: il pan si ferma dove si lascia
        var r = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        r.dimensioniVista(900, 640)
        r.imposta(ridotto: true)
        r.assesta()
        for _ in 0..<30 { r.panora(schermo: P2(-14, 0)); r.passo() }
        let r1 = r.camera.c
        r.rilasciaPanoramica()
        for _ in 0..<12 { r.passo() }
        prova("con Riduci movimento il pan non ha inerzia", abs(r.camera.c.x - r1.x) < 0.01)

        // oltre i bordi: la camera ci va, e poi torna dentro
        var b = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        b.dimensioniVista(900, 640)
        b.assesta()
        b.zoom(fattore: 3)
        b.assesta()
        for _ in 0..<80 { b.panora(schermo: P2(60, 0)); b.passo() }
        let fuori = b.camera.c
        b.rilasciaPanoramica()
        b.assesta()
        prova("oltre i bordi la camera torna dentro (rimbalzo morbido)", b.camera.c.x != fuori.x && b.camera.ferma)

        // inquadra un gruppo
        var q = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        q.dimensioniVista(900, 640)
        q.assesta()
        q.inquadra(gruppo: 4)
        q.assesta()
        let centro = baricentro(g, q.posizioni, gruppo: 4)
        let s = q.camera.schermo(centro)
        prova("inquadrare un gruppo lo porta al centro della vista", dist(s, P2(450, 320)) < 40, "\(s)")
        var tuttiDentro = true
        for (i, k) in g.gruppo.enumerated() where k == 4 {
            let p = q.camera.schermo(q.posizioni[i])
            if p.x < 0 || p.y < 0 || p.x > 900 || p.y > 640 { tuttiDentro = false }
        }
        prova("e tutti i suoi nodi stanno nella vista", tuttiDentro)
        prova("lo zoom del gruppo e' maggiore di quello di tutta la mappa", q.camera.z > q.foto(versione: 0).zoomTutto * 1.2)
        prova("un gruppo piccolo si inquadra piu' da vicino del massimo di 'inquadra tutto' (1,7)", q.camera.z > 1.7, "\(q.camera.z)")
        q.inquadra()
        q.assesta()
        prova("inquadrare tutto spegne la luce sul gruppo", q.luceAccesa == 0 && q.gruppoInLuce == nil)
    }

    static func provaPrestazioni() {
        print("== il costo di un passo (un passo di fisica dura 1/120 s = 8,3 ms)")
        for (nome, dimensioni) in [("300 nodi", [75, 75, 75, 75]), ("1200 nodi", Array(repeating: 100, count: 12))] {
            let g = GrafoProva(dimensioni: dimensioni, ponti: dimensioni.reduce(0, +) / 8)
            var sim = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
            sim.dimensioniVista(900, 640)
            for _ in 0..<60 { sim.passo() }
            var massimo: Double = 0, totale: Double = 0
            let passi = 120
            for _ in 0..<passi {
                // tempo di CPU del processo, non di orologio: con la macchina carica l'orologio misura gli altri
                let t0 = clock_gettime_nsec_np(CLOCK_PROCESS_CPUTIME_ID)
                sim.passo()
                let ms = Double(clock_gettime_nsec_np(CLOCK_PROCESS_CPUTIME_ID) - t0) / 1e6
                totale += ms; massimo = max(massimo, ms)
            }
            let medio = totale / Double(passi)
            print("     \(nome): passo medio \(String(format: "%.3f", medio)) ms, massimo \(String(format: "%.3f", massimo)) ms")
            // un passo di fisica dura 8,3 ms: il costo medio deve starci con ampio margine
            let limite = nome == "300 nodi" ? 2.0 : 8.3
            prova("\(nome): un passo costa in media meno di \(limite) ms", medio < limite, "\(medio) ms")
            let ferma = sim
            _ = ferma
        }
        // 300 nodi a scena ferma: il passo non fa niente di pesante
        let g = GrafoProva(dimensioni: [75, 75, 75, 75], ponti: 38)
        var sim = SimulazioneGrafo(topologia: g.topologia(), parametri: PAR)
        sim.dimensioniVista(900, 640)
        sim.assesta()
        prova("300 nodi si assestano e la scena e' ferma", sim.ferma)
    }
    #endif
}
