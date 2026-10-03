// Mappa della memoria: i dati del grafo, calcolati una volta per ogni forma della memoria.
//
// Nodi, legami, gruppi (con il loro colore e i ponti), titoli corti, rango di ogni nodo
// e la topologia per la fisica con le posizioni di partenza. Niente SwiftUI per frame.

import Foundation
import SwiftUI

struct GruppoInfo: Sendable {
    let chiave: String
    let nome: String
    /// 0xRRGGBB
    let colore: UInt32
    let membri: [Int]
    /// Gli altri gruppi a cui e' legato, con quanti legami (i ponti).
    let ponti: [(Int, Int)]
}

extension GruppoInfo {
    /// Il nome da mostrare: i gruppi di tipo (chi sei, preferenze...) arrivano dal server in
    /// italiano, come nel web si traducono qui; quelli di progetto restano come il server li dice.
    func nomeVisto(inglese: Bool) -> String {
        switch chiave {
        case "tipo:user": return inglese ? "About you" : "Chi sei"
        case "tipo:feedback": return inglese ? "Preferences" : "Preferenze"
        case "tipo:reference": return inglese ? "References" : "Riferimenti"
        case "tipo:project": return inglese ? "Other projects" : "Altri progetti"
        case "tipo:altro": return inglese ? "Other" : "Altro"
        default: return nome
        }
    }
}

struct InfoGrafo: Sendable {
    let firma: Int
    let nomi: [String]
    /// Il titolo umano di ogni nodo (quello che si legge sulla mappa) e la sua versione corta.
    let titoli: [String]
    let etichette: [String]
    let tipi: [TipoMemoria]
    let grado: [Int]
    /// 0...1: 1 e' il nodo piu' collegato. Decide quali etichette si vedono per prime.
    let rango: [Float]
    /// 0...1 dentro il gruppo: 0 e' il piu' collegato del suo gruppo.
    let rangoNelGruppo: [Float]
    let gruppo: [Int]
    let gruppi: [GruppoInfo]
    let archi: [(Int, Int)]
    let indice: [String: Int]
    let vicini: [[Int32]]
    let hub: Int?
    let topologia: TopologiaGrafo
    /// Vero se i gruppi vengono dal server (con la sua disposizione a isole).
    let dalServer: Bool

    /// La forma della memoria: i nomi, i tipi, i progetti e quanti legami ha ognuno.
    static func firma(_ dati: DatiMemoria) -> Int {
        var h = Hasher()
        h.combine(dati.fatti.count)
        for f in dati.fatti {
            h.combine(f.nome)
            h.combine(f.tipo.rawValue)
            h.combine(f.progettoChiave)
            h.combine(dati.vicini[f.nome]?.count ?? 0)
        }
        return h.finalize()
    }

    /// La forma insieme ai gruppi del server (`improntaServer`, 0 se non ci sono).
    static func firma(_ base: Int, improntaServer: Int) -> Int {
        var h = Hasher()
        h.combine(base)
        h.combine(improntaServer)
        return h.finalize()
    }

    @MainActor
    init(dati: DatiMemoria, server: MappaGruppi? = nil) {
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
        firma = InfoGrafo.firma(InfoGrafo.firma(dati), improntaServer: server?.impronta ?? 0)

        // --- i gruppi: dal server se corrispondono, altrimenti dalla scheda stessa
        var perNome: [String: NodoGruppo] = [:]
        for x in server?.nodi ?? [] { if let k = x.nome { perNome[k] = x } }
        let trovati = nomi.filter { perNome[$0]?.gruppo != nil }.count
        let usaServer = server != nil && n > 0 && Double(trovati) / Double(n) >= 0.6
        dalServer = usaServer

        var chiaveDi = [String](repeating: "", count: n)
        var nomeDi: [String: String] = [:]
        var titolo = [String](repeating: "", count: n)
        if usaServer {
            for (i, f) in fatti.enumerated() {
                let x = perNome[f.nome]
                chiaveDi[i] = x?.gruppo ?? "tipo:\(f.tipo.rawValue)"
                if let nome = x?.gruppoNome { nomeDi[chiaveDi[i]] = nome }
                let t = (x?.titolo ?? "").trimmingCharacters(in: .whitespaces)
                titolo[i] = t.isEmpty ? TitoloMappa.ricava(nome: f.nome, descrizione: f.descrizione) : t
            }
        } else {
            // il progetto collegato; una scheda sola in un progetto cade nel gruppo del suo tipo
            var conta: [String: Int] = [:]
            for f in fatti { if let k = f.progettoChiave, !k.isEmpty { conta[k, default: 0] += 1 } }
            for (i, f) in fatti.enumerated() {
                if let k = f.progettoChiave, !k.isEmpty, (conta[k] ?? 0) >= 2 {
                    chiaveDi[i] = "progetto:\(k)"
                    nomeDi[chiaveDi[i]] = f.progetto ?? k
                } else {
                    chiaveDi[i] = "tipo:\(f.tipo.rawValue)"
                    nomeDi[chiaveDi[i]] = f.tipo.titolo
                }
                titolo[i] = TitoloMappa.ricava(nome: f.nome, descrizione: f.descrizione)
            }
        }
        titoli = titolo
        etichette = titolo.map { TitoloMappa.breve($0) }

        // l'ordine dei gruppi: i piu' grossi per primi
        var membriPer: [String: [Int]] = [:]
        for i in 0..<n { membriPer[chiaveDi[i], default: []].append(i) }
        let chiavi = membriPer.keys.sorted {
            let a = membriPer[$0]!.count, b = membriPer[$1]!.count
            return a == b ? $0 < $1 : a > b
        }
        var indiceG: [String: Int] = [:]
        for (k, c) in chiavi.enumerated() { indiceG[c] = k }
        let grp = chiaveDi.map { indiceG[$0] ?? 0 }
        gruppo = grp

        // i colori: quello del server, altrimenti uno stabile dalla chiave, mai due uguali finche' si puo'
        var colori: [String: UInt32] = [:]
        var occupati = Set<UInt32>()
        var serverPer: [String: GruppoServer] = [:]
        for g in server?.gruppi ?? [] { if let k = g.chiave { serverPer[k] = g } }
        for c in chiavi {
            if usaServer, let v = ColoreGruppo.da(testo: serverPer[c]?.colore) { colori[c] = v; occupati.insert(v) }
        }
        for c in chiavi.sorted() where colori[c] == nil {
            let v = ColoreGruppo.stabile(c, occupati: occupati)
            colori[c] = v; occupati.insert(v)
        }

        // i ponti fra i gruppi
        var contaPonti: [Int: [Int: Int]] = [:]
        for (a, b) in lista where grp[a] != grp[b] {
            contaPonti[grp[a], default: [:]][grp[b], default: 0] += 1
            contaPonti[grp[b], default: [:]][grp[a], default: 0] += 1
        }
        let elencoGruppi: [GruppoInfo] = chiavi.enumerated().map { (k, c) in
            GruppoInfo(chiave: c, nome: nomeDi[c] ?? c, colore: colori[c] ?? 0x888888,
                       membri: membriPer[c] ?? [],
                       ponti: (contaPonti[k] ?? [:]).sorted { $0.value == $1.value ? $0.key < $1.key : $0.value > $1.value }
                           .map { ($0.key, $0.value) })
        }
        gruppi = elencoGruppi

        // il rango dentro il gruppo
        var rg = [Float](repeating: 0, count: n)
        for g in elencoGruppi {
            let ordinati = g.membri.sorted { (gr[$0], nm[$1]) > (gr[$1], nm[$0]) }
            for (pos, i) in ordinati.enumerated() { rg[i] = Float(pos) / Float(max(ordinati.count, 1)) }
        }
        rangoNelGruppo = rg

        // --- da dove partono: le isole del server (portate a una scala in cui i dischi non si
        // toccano) se ci sono, altrimenti una disposizione mia; i nodi a girasole intorno all'ancora
        let scala = 62 * Float(max(n, 1)).squareRoot()
        var centriServer: [P2] = []
        if usaServer {
            for c in chiavi {
                if let sg = serverPer[c], let x = sg.x, let y = sg.y {
                    centriServer.append(P2(Float(x) - 0.5, Float(y) - 0.5) * scala)
                }
            }
            if centriServer.count != chiavi.count { centriServer = [] }
        }
        let (iniziali, centri) = InfoGrafo.isole(gruppi: elencoGruppi, gruppo: grp, grado: gr, n: n,
                                                 centri: centriServer.isEmpty ? nil : centriServer)
        topologia = TopologiaGrafo(n: n, archi: lista, iniziali: iniziali, gruppo: grp, centri: centri)
    }

    /// Una disposizione di partenza leggibile: le isole su una spirale (la piu' grossa al
    /// centro) o nei centri dati, allargati quanto basta perche' i dischi non si tocchino; i
    /// nodi di ognuna a girasole intorno alla sua ancora, i piu' collegati dentro.
    static func isole(gruppi: [GruppoInfo], gruppo: [Int], grado: [Int], n: Int,
                      centri dati: [P2]?) -> ([P2], [P2]) {
        var iniziali = [P2](repeating: .zero, count: n)
        let par = ParametriFisica.standard
        let raggi = gruppi.map { par.raggioGruppoPerRadice * Float($0.membri.count).squareRoot() + par.raggioGruppoBase }
        var centri = dati ?? TopologiaGrafo.centriADisco(membri: gruppi.map { $0.membri.count })
        if dati != nil {
            // allarga tutto dall'origine finche' nessuna coppia di dischi si tocca
            var f: Float = 1
            for x in 0..<centri.count {
                for y in (x + 1)..<max(centri.count, x + 1) {
                    let d = centri[x] - centri[y]
                    let dist = (d.x * d.x + d.y * d.y).squareRoot()
                    let serve = raggi[x] + raggi[y] + par.distanzaGruppiBase
                    f = max(f, dist < 1 ? 1 : serve / dist)
                }
            }
            if f > 1 { centri = centri.map { $0 * f } }
        }
        for (k, g) in gruppi.enumerated() {
            let centro = centri[k]
            let ordinati = g.membri.sorted { grado[$0] > grado[$1] }
            let passo = raggi[k] / Float(max(ordinati.count, 1)).squareRoot() * 0.82
            for (j, i) in ordinati.enumerated() {
                let ang = 2.399963 * Float(j)
                let rr = passo * (Float(j) + 0.5).squareRoot()
                iniziali[i] = centro + P2(rr * cos(ang), rr * sin(ang))
            }
        }
        return (iniziali, centri)
    }

    /// I gruppi toccati da un insieme di nodi: serve alla luce sui vicini.
    func gruppiDi(_ nodi: [Int]) -> Set<Int> { Set(nodi.map { gruppo[$0] }) }
}
