// Mappa della memoria: il disegno.
//
// Un Canvas per fotogramma, a partire da un'istantanea della fisica (FotoScena). Dietro i
// nodi, per ogni gruppo, una regione morbida (l'inviluppo arrotondato dei suoi nodi) nel
// colore stabile del gruppo; fra i gruppi i ponti come nastri da lontano e come fasci di
// curve da vicino; sui nodi il titolo umano corto. Lo zoom e' semantico, relativo
// all'inquadratura che mostra tutto (`zoomTutto`):
//   - da lontano: solo i nomi dei gruppi, col numero di memorie, e i nastri dei ponti;
//   - avvicinandosi: i titoli dei nodi piu' collegati di ogni gruppo, e i legami;
//   - da vicino: i titoli di tutti, senza sovrapporsi.
// Il colore del nodo dice il tipo, la regione dice il gruppo.

import SwiftUI
import AppKit

// MARK: - lo stato che arriva dalla vista

struct StatoDisegno {
    var scelto: Int?
    var hover: Int?
    var livello: LivelloMappa
    var centro: Int?
    var gruppoScelto: Int?
    var scuro: Bool
    /// Stile Legno: lo sfondo e' la texture, le regioni vogliono un po' piu' di corpo.
    var legno: Bool
    var inglese: Bool
}

enum DisegnoMappa {
    /// Il raggio a schermo cresce meno dello zoom: da lontano i nodi restano visibili, da
    /// vicino non diventano dischi enormi.
    static func raggioSchermo(_ r: Float, _ zoom: Float) -> CGFloat {
        CGFloat(max(r * pow(zoom, 0.6), 2.4))
    }

    static func morbido(_ a: Float, _ b: Float, _ x: Float) -> Float {
        let t = min(max((x - a) / (b - a), 0), 1)
        return t * t * (3 - 2 * t)
    }

    private static func cerchio(_ c: CGPoint, _ r: CGFloat) -> Path {
        Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r))
    }

    private static func meta(_ a: CGPoint, _ b: CGPoint) -> CGPoint {
        CGPoint(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
    }

    // MARK: l'inviluppo di un gruppo

    /// L'inviluppo convesso dei cerchi dei nodi, ingranditi di `pad`: la regione del gruppo.
    static func involucro(_ pts: [CGPoint], _ raggi: [CGFloat], pad: CGFloat) -> [CGPoint] {
        let lati = pts.count > 40 ? 6 : 10
        var campioni: [CGPoint] = []
        campioni.reserveCapacity(pts.count * lati)
        for (k, p) in pts.enumerated() {
            let r = raggi[k] + pad
            for j in 0..<lati {
                let a = CGFloat(j) / CGFloat(lati) * 2 * .pi
                campioni.append(CGPoint(x: p.x + r * cos(a), y: p.y + r * sin(a)))
            }
        }
        campioni.sort { $0.x == $1.x ? $0.y < $1.y : $0.x < $1.x }
        guard campioni.count >= 3 else { return campioni }
        func giro(_ o: CGPoint, _ a: CGPoint, _ b: CGPoint) -> CGFloat {
            (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
        }
        var basso: [CGPoint] = []
        for p in campioni {
            while basso.count >= 2 && giro(basso[basso.count - 2], basso[basso.count - 1], p) <= 0 { basso.removeLast() }
            basso.append(p)
        }
        var alto: [CGPoint] = []
        for p in campioni.reversed() {
            while alto.count >= 2 && giro(alto[alto.count - 2], alto[alto.count - 1], p) <= 0 { alto.removeLast() }
            alto.append(p)
        }
        basso.removeLast(); alto.removeLast()
        return basso + alto
    }

    private static func percorsoMorbido(_ h: [CGPoint]) -> Path {
        var p = Path()
        let n = h.count
        guard n >= 3 else { return p }
        p.move(to: meta(h[n - 1], h[0]))
        for i in 0..<n { p.addQuadCurve(to: meta(h[i], h[(i + 1) % n]), control: h[i]) }
        p.closeSubpath()
        return p
    }

    private struct RegioneG {
        var presente = false
        var alto: CGFloat = 0
        var centroX: CGFloat = 0
        var minX: CGFloat = 0, maxX: CGFloat = 0, minY: CGFloat = 0, maxY: CGFloat = 0
        var baricentro = CGPoint.zero
        var raggio: CGFloat = 0
    }

    // MARK: il disegno

    static func disegna(_ ctx: inout GraphicsContext, _ size: CGSize, foto: FotoScena,
                        info: InfoGrafo, stato: StatoDisegno) {
        let n = info.nomi.count
        guard n > 0, foto.pos.count == n, foto.presenza.count == n, foto.evidenza.count == n else { return }
        let ng = info.gruppi.count
        let zoom = foto.camera.z
        let rho = zoom / max(foto.zoomTutto, 0.0001)
        let pochi = stato.livello != .tutto
        let luce = Double(foto.luce)
        let scuro = stato.scuro

        var punti = [CGPoint](repeating: .zero, count: n)
        for i in 0..<n {
            let s = foto.camera.schermo(foto.pos[i])
            punti[i] = CGPoint(x: CGFloat(s.x), y: CGFloat(s.y))
        }
        let area = CGRect(origin: .zero, size: size).insetBy(dx: -60, dy: -60)
        let vista = CGRect(origin: .zero, size: size)

        // quanto si vede di ogni cosa, secondo lo zoom relativo
        let daLontano: Float = pochi ? 0 : 1 - morbido(1.15, 2.3, rho)
        let kIntra: Double = pochi ? 1 : Double(morbido(0.8, 1.7, rho))
        let kFascio: Double = pochi ? 1 : Double(morbido(1.0, 2.1, rho))
        let kNastro: Double = pochi ? 0 : Double(1 - morbido(1.3, 2.5, rho))

        func attenua(_ i: Int) -> Double { 1 - luce * Double(1 - foto.evidenza[i]) * 0.82 }

        // --- le regioni dei gruppi
        var regioni = [RegioneG](repeating: RegioneG(), count: ng)
        let pad = CGFloat(max(11, 21 * pow(zoom, 0.85)))
        for g in 0..<ng {
            let presenza = foto.presenzaGruppo.count > g ? foto.presenzaGruppo[g] : 1
            if presenza <= 0.02 { continue }
            var pp: [CGPoint] = [], rr: [CGFloat] = []
            var coinvolto: Float = 0
            for i in info.gruppi[g].membri where foto.voluto[i] || foto.presenza[i] > 0.05 {
                if foto.presenza[i] <= 0.05 { continue }
                pp.append(punti[i])
                rr.append(raggioSchermo(info.topologia.raggio[i], zoom) * CGFloat(foto.presenza[i]))
                coinvolto = max(coinvolto, foto.evidenza[i])
            }
            if pp.isEmpty { continue }
            let h = involucro(pp, rr, pad: pad)
            guard h.count >= 3 else { continue }
            var r = RegioneG()
            r.presente = true
            r.minX = h.map { $0.x }.min() ?? 0; r.maxX = h.map { $0.x }.max() ?? 0
            r.minY = h.map { $0.y }.min() ?? 0; r.maxY = h.map { $0.y }.max() ?? 0
            r.alto = r.minY
            r.centroX = (r.minX + r.maxX) / 2
            let bx = pp.reduce(0) { $0 + $1.x } / CGFloat(pp.count), by = pp.reduce(0) { $0 + $1.y } / CGFloat(pp.count)
            r.baricentro = CGPoint(x: bx, y: by)
            r.raggio = pp.map { hypot($0.x - bx, $0.y - by) }.max() ?? 0
            regioni[g] = r
            if !vista.insetBy(dx: -80, dy: -80).intersects(CGRect(x: r.minX, y: r.minY, width: r.maxX - r.minX, height: r.maxY - r.minY)) { continue }

            let colore = ColoreGruppo.colore(info.gruppi[g].colore)
            let scelta = stato.gruppoScelto == g || foto.gruppoInLuce == g
            var spento = 1.0
            if luce > 0.001 { spento = 1 - luce * Double(1 - coinvolto) * 0.78 }
            let base: Double = stato.legno ? 0.26 : (scuro ? 0.20 : 0.15)
            let percorso = percorsoMorbido(h)
            let a = Double(presenza) * spento
            ctx.fill(percorso, with: .color(colore.opacity(base * a * (scelta ? 1.35 : 1))))
            ctx.stroke(percorso, with: .color(colore.opacity((stato.legno ? 0.7 : 0.5) * a * (scelta ? 1.4 : 1))),
                       lineWidth: scelta ? 2 : 1.2)
        }

        // --- i nastri dei ponti, da lontano
        if kNastro > 0.01 {
            for (g, gi) in info.gruppi.enumerated() where regioni[g].presente {
                for (altro, quanti) in gi.ponti where altro > g && regioni[altro].presente {
                    nastro(&ctx, info: info, regioni: regioni, da: g, a: altro, quanti: quanti,
                           opacita: kNastro * Double(min(foto.presenzaGruppo[g], foto.presenzaGruppo[altro])),
                           luce: luce, foto: foto)
                }
            }
        }

        // --- i legami
        var interni = Path(), fasci = Path(), evidenza = Path()
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
            let acceso = luce > 0.001 && foto.evidenza[a] > 0.5 && foto.evidenza[b] > 0.5
                && (stato.hover != nil || foto.gruppoInLuce == nil)
            let ponte = info.gruppo[a] != info.gruppo[b]
            if acceso && stato.hover != nil && (a == stato.hover || b == stato.hover) {
                legame(&evidenza, p1, p2, ponte: ponte, regioni: regioni, info: info, a: a, b: b)
            } else if ponte {
                legame(&fasci, p1, p2, ponte: true, regioni: regioni, info: info, a: a, b: b)
            } else {
                interni.move(to: p1); interni.addLine(to: p2)
            }
        }
        let spentoLegami = 1 - luce * 0.85
        let baseInterni: Double = pochi ? 0.30 : 0.26
        ctx.stroke(interni, with: .color(.primary.opacity(baseInterni * kIntra * (luce > 0 ? spentoLegami : 1))),
                   lineWidth: pochi ? 1.2 : 0.9)
        ctx.stroke(fasci, with: .color(.primary.opacity(0.30 * kFascio * (luce > 0 ? spentoLegami : 1))),
                   lineWidth: pochi ? 1.4 : 1.0)
        for (a, b, p) in incerti {
            var t = Path()
            t.move(to: punti[a]); t.addLine(to: punti[b])
            ctx.stroke(t, with: .color(.primary.opacity(0.22 * p)), lineWidth: 0.8)
        }
        ctx.stroke(evidenza, with: .color(.accentColor.opacity(0.85)), lineWidth: 1.7)

        // --- i nodi: prima gli attenuati, poi gli evidenziati, in cima il centro
        var ordine: [Int] = []
        ordine.reserveCapacity(n)
        for i in 0..<n where foto.presenza[i] > 0.01 && area.contains(punti[i]) { ordine.append(i) }
        func peso(_ i: Int) -> Int {
            if i == stato.hover { return 4 }
            if i == stato.centro || i == stato.scelto { return 3 }
            return foto.evidenza[i] > 0.5 && luce > 0.001 ? 1 : 0
        }
        ordine.sort { peso($0) < peso($1) }
        for i in ordine {
            let p = foto.presenza[i]
            let grande = (i == stato.centro) ? 1.35 : 1.0
            let r = raggioSchermo(info.topologia.raggio[i] * Float(grande), zoom)
                * CGFloat(p) + (i == stato.hover ? 2 : 0)
            let c = cerchio(punti[i], r)
            // da lontano i nodi lasciano il campo ai nomi dei gruppi
            let lieve = 1 - 0.35 * Double(daLontano)
            ctx.fill(c, with: .color(info.tipi[i].colore.opacity(Double(p) * attenua(i) * lieve)))
            if zoom > 0.45 {
                ctx.stroke(c, with: .style(.background), lineWidth: 1.2)
            }
            if i == stato.scelto || (i == stato.centro && pochi) || i == stato.hover {
                ctx.stroke(cerchio(punti[i], r + 3.5), with: .color(.accentColor.opacity(i == stato.hover && i != stato.scelto ? 0.7 : 1)),
                           lineWidth: 2)
            }
        }

        var occupati: [CGRect] = []
        nomiGruppi(&ctx, size, foto: foto, info: info, stato: stato, regioni: regioni,
                   daLontano: daLontano, occupati: &occupati, luce: luce)
        titoli(&ctx, size, foto: foto, info: info, stato: stato, punti: punti, rho: rho,
               area: area, occupati: &occupati)
    }

    // MARK: i ponti

    /// Un legame fra due gruppi si piega verso il punto di mezzo fra i loro centri: i legami
    /// che vanno dallo stesso gruppo allo stesso gruppo diventano un fascio.
    private static func legame(_ path: inout Path, _ p1: CGPoint, _ p2: CGPoint, ponte: Bool,
                               regioni: [RegioneG], info: InfoGrafo, a: Int, b: Int) {
        path.move(to: p1)
        guard ponte else { path.addLine(to: p2); return }
        let ga = regioni[info.gruppo[a]], gb = regioni[info.gruppo[b]]
        guard ga.presente, gb.presente else { path.addLine(to: p2); return }
        let m = meta(p1, p2)
        let centro = meta(ga.baricentro, gb.baricentro)
        let controllo = CGPoint(x: m.x + (centro.x - m.x) * 0.55, y: m.y + (centro.y - m.y) * 0.55)
        path.addQuadCurve(to: p2, control: controllo)
    }

    /// Il nastro fra due gruppi: largo secondo quanti legami li uniscono, dal colore dell'uno
    /// a quello dell'altro, appena curvo, che parte dal bordo di un'isola e arriva al bordo dell'altra.
    private static func nastro(_ ctx: inout GraphicsContext, info: InfoGrafo, regioni: [RegioneG],
                               da: Int, a: Int, quanti: Int, opacita: Double, luce: Double, foto: FotoScena) {
        let ra = regioni[da], rb = regioni[a]
        let dx = rb.baricentro.x - ra.baricentro.x, dy = rb.baricentro.y - ra.baricentro.y
        let lung = hypot(dx, dy)
        guard lung > 1 else { return }
        let ux = dx / lung, uy = dy / lung
        let ia = ra.raggio + 6, ib = rb.raggio + 6
        guard lung > ia + ib + 8 else { return }
        let inizio = CGPoint(x: ra.baricentro.x + ux * ia, y: ra.baricentro.y + uy * ia)
        let fine = CGPoint(x: rb.baricentro.x - ux * ib, y: rb.baricentro.y - uy * ib)
        let curva = lung * 0.10 * ((da + a) % 2 == 0 ? 1 : -1)
        let mid = meta(inizio, fine)
        let controllo = CGPoint(x: mid.x - uy * curva, y: mid.y + ux * curva)
        var p = Path()
        p.move(to: inizio)
        p.addQuadCurve(to: fine, control: controllo)
        let larghezza = CGFloat(2.0 + 2.2 * Double(quanti).squareRoot())
        let ca = ColoreGruppo.colore(info.gruppi[da].colore), cb = ColoreGruppo.colore(info.gruppi[a].colore)
        let spento = luce > 0.001 ? 1 - luce * 0.7 : 1
        let alfa = 0.46 * opacita * spento
        let sfumatura = GraphicsContext.Shading.linearGradient(
            Gradient(colors: [ca.opacity(alfa), cb.opacity(alfa)]), startPoint: inizio, endPoint: fine)
        ctx.stroke(p, with: sfumatura, style: StrokeStyle(lineWidth: larghezza, lineCap: .round))
    }

    // MARK: i nomi dei gruppi

    private static func nomiGruppi(_ ctx: inout GraphicsContext, _ size: CGSize, foto: FotoScena,
                                   info: InfoGrafo, stato: StatoDisegno, regioni: [RegioneG],
                                   daLontano: Float, occupati: inout [CGRect], luce: Double) {
        let vista = CGRect(origin: .zero, size: size)
        let corpo = CGFloat(13 + 11 * daLontano)
        let ordine = info.gruppi.indices.sorted {
            let a = stato.gruppoScelto == $0 ? 1_000_000 : info.gruppi[$0].membri.count
            let b = stato.gruppoScelto == $1 ? 1_000_000 : info.gruppi[$1].membri.count
            return a > b
        }
        for g in ordine {
            let r = regioni[g]
            guard r.presente else { continue }
            let quanti = foto.quantiGruppo.count > g ? foto.quantiGruppo[g] : info.gruppi[g].membri.count
            if quanti == 0 { continue }
            let gi = info.gruppi[g]
            // il corpo cambia con lo zoom: si risolve il testo con un font semantico e lo si scala
            let titolo = Text(gi.nomeVisto(inglese: stato.inglese)).font(.title3.weight(.semibold))
                .foregroundStyle(ColoreGruppo.testo(gi.colore, scuro: stato.scuro))
            let numero = Text("\(quanti)").font(.callout)
                .foregroundStyle(Color.secondary)
            let ris = ctx.resolve(Text("\(titolo)  \(numero)"))
            let m0 = ris.measure(in: CGSize(width: 420, height: 60))
            let scala = corpo / 20
            let m = CGSize(width: m0.width * scala, height: m0.height * scala)
            // sul bordo alto dell'isola; se non c'e' posto, al centro
            let candidati = [CGPoint(x: r.centroX, y: r.alto - m.height / 2 - 6),
                             CGPoint(x: r.centroX, y: r.alto - m.height * 1.5 - 8),
                             CGPoint(x: r.centroX, y: r.maxY + m.height / 2 + 6),
                             CGPoint(x: r.baricentro.x, y: r.baricentro.y)]
            for c in candidati {
                var x = c.x, y = c.y
                x = min(max(x, m.width / 2 + 6), max(size.width - m.width / 2 - 6, m.width / 2 + 6))
                y = min(max(y, m.height / 2 + 4), max(size.height - m.height / 2 - 4, m.height / 2 + 4))
                let rect = CGRect(x: x - m.width / 2 - 5, y: y - m.height / 2 - 1, width: m.width + 10, height: m.height + 2)
                if !vista.insetBy(dx: -40, dy: -40).intersects(CGRect(x: r.minX, y: r.minY, width: r.maxX - r.minX, height: r.maxY - r.minY)) { break }
                if occupati.contains(where: { $0.intersects(rect.insetBy(dx: -2, dy: -1)) }) { continue }
                occupati.append(rect)
                var strato = ctx
                let presenza = Double(foto.presenzaGruppo.count > g ? foto.presenzaGruppo[g] : 1)
                var coinvolto = 1.0
                if luce > 0.001 {
                    var mx: Float = 0
                    for i in gi.membri { mx = max(mx, foto.evidenza[i]) }
                    coinvolto = 1 - luce * Double(1 - mx) * 0.7
                }
                strato.opacity = presenza * coinvolto
                strato.fill(Path(roundedRect: rect, cornerRadius: 7), with: .style(.background.opacity(0.7)))
                strato.translateBy(x: x, y: y)
                strato.scaleBy(x: scala, y: scala)
                strato.draw(ris, at: .zero, anchor: .center)
                break
            }
        }
    }

    // MARK: i titoli dei nodi

    private static func titoli(_ ctx: inout GraphicsContext, _ size: CGSize, foto: FotoScena,
                               info: InfoGrafo, stato: StatoDisegno, punti: [CGPoint], rho: Float,
                               area: CGRect, occupati: inout [CGRect]) {
        let n = info.nomi.count
        let zoom = foto.camera.z
        let pochi = stato.livello != .tutto
        let luce = Double(foto.luce)
        var vicini = Set<Int>()
        if let f = stato.hover { for v in info.vicini[f] { vicini.insert(Int(v)) } }

        var candidati: [(Int, Float)] = []
        for i in 0..<n where foto.presenza[i] > 0.6 && foto.voluto[i] && area.contains(punti[i]) {
            var pr = info.rango[i]
            if i == stato.hover { pr += 5 }
            else if i == stato.scelto || i == stato.centro { pr += 4 }
            else if vicini.contains(i) { pr += 3 }
            candidati.append((i, pr))
        }
        candidati.sort { $0.1 > $1.1 }

        let visibile = CGRect(origin: .zero, size: size)
        var messe = 0
        let tutti = pochi || candidati.count <= 40
        for (i, _) in candidati {
            if messe >= 110 { break }
            let evidente = i == stato.hover || i == stato.scelto || i == stato.centro
            var alfa: Float
            if evidente || vicini.contains(i) {
                alfa = 1
            } else if tutti {
                alfa = min(max((zoom - 0.3) / 0.18, 0), 1)
            } else {
                // i titoli compaiono con lo zoom relativo: prima il nodo piu' collegato di ogni gruppo
                let soglia = 1.5 + 1.9 * info.rangoNelGruppo[i]
                alfa = min(max((rho - soglia) / 0.35, 0), 1)
            }
            if alfa <= 0.02 { continue }

            let testo = evidente ? TitoloMappa.breve(info.titoli[i], massimo: 54) : info.etichette[i]
            var t = Text(testo)
            t = evidente ? t.font(.callout.weight(.semibold)) : t.font(.caption)
            let ris = ctx.resolve(t.foregroundStyle(.primary))
            let misura = ris.measure(in: CGSize(width: 360, height: 40))
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
            var spento = 1.0
            if luce > 0.001 { spento = 1 - luce * Double(1 - foto.evidenza[i]) * 0.65 }
            strato.opacity = Double(alfa) * spento
            let targhetta = Path(roundedRect: rect, cornerRadius: 5)
            strato.fill(targhetta, with: .style(.background.opacity(0.82)))
            strato.draw(ris, at: CGPoint(x: rect.minX + 4, y: rect.midY), anchor: .leading)
        }
    }
}
