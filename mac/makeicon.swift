// Disegna l'icona di ripiego dell'app: la plancia della nave, vista di lato.
//
// La strada buona per l'icona è mac/icona/Plancia.icon (Icon Composer, macOS 26+):
// lì il vetro lo applica il sistema, strato per strato. Questo file serve quando
// quella strada non c'è (Xcode senza actool 26+, o actool che rifiuta il .icon):
// disegna a mano, con CoreGraphics, la stessa forma con un vetro imitato con
// mano leggera, e mac/build.sh la trasforma in Plancia.icns con `iconutil`.
//
// Il segno è uno solo e sta nei due file allo stesso modo: una sagoma sola, bassa
// e slanciata, fatta di uno scafo (poppa corta, prua che sale con un'unica curva)
// e di UNA casa del ponte compatta con il fronte inclinato in avanti (la nave
// crema, un unico strato, con il buco dei vetri) e i vetri accesi d'ambra, che
// corrono su tutto il fronte della casa (il secondo strato). Sono tre poligoni sulla tavola di
// 1024 dei file SVG (mac/icona/Plancia.icon/Assets/nave.svg e vetri.svg), ognuno con
// un raggio che ne arrotonda gli spigoli: dal vertice si va verso i due vicini per
// `raggio` unità (al più metà lato) e si chiude la curva con una quadratica che ha
// il vertice per punto di controllo. È la stessa regola con cui sono scritti gli
// SVG. I vetri stanno dentro la casa a distanza costante dai suoi bordi, e il loro
// raggio è quello della casa meno quella distanza: gli angoli sono concentrici.
// Se cambi il segno di là, cambialo anche qui: tools/prove-front/icona.py
// ricalcola i percorsi da queste coordinate e li confronta con gli SVG.
//
// Coordinate uguali non bastano, conta anche il riferimento. In Icon Composer la
// tela da 1024 del .icon coincide con il CORPO dell'icona (il quadrato
// arrotondato da 824 px sulla griglia di Apple): actool la rimpicciolisce dentro
// i margini. Quindi qui la tavola si porta dentro il corpo, non dentro l'intera
// immagine: se la si portasse sull'intera immagine il segno uscirebbe più grande
// di 1024/824, cioè del 24 per cento, e con e senza Xcode 26 l'app avrebbe due
// icone diverse (misurato sulle PNG di actool e del ripiego). Il vetro imitato è:
// un fondo con un gradiente sobrio, un filo di luce dentro il bordo in alto, un
// riflesso morbido, e per ogni strato un'ombra corta sotto e un bordo di luce
// sopra.
//
// Si esegue con `swift mac/makeicon.swift <cartella-iconset>`.

import AppKit
import CoreGraphics
import Foundation

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "./Plancia.iconset"
try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)

// La tavola dei file SVG: 1024 per 1024, con l'origine in alto a sinistra.
let tavola: CGFloat = 1024
let ingrandimento: CGFloat = 1.0         // il "scale" degli strati nel .icon
// Il margine del corpo sull'immagine intera, in frazione del lato: 0,098 è il
// 100 px su 1024 della griglia di Apple. Una costante sola, usata dal corpo
// (in disegna) e dalla mappa della tavola (in punto).
let margineCorpo: CGFloat = 0.098

/// Un poligono chiuso con gli spigoli arrotondati di `raggio` (unità della tavola).
struct Forma {
    let punti: [CGPoint]
    let raggio: CGFloat
}

// Lo strato crema (nave.svg): scafo e casa fusi in una sagoma, con il buco dei vetri.
let scafo = Forma(punti: [CGPoint(x: 119, y: 576), CGPoint(x: 217, y: 576), CGPoint(x: 604, y: 561), CGPoint(x: 918, y: 486), CGPoint(x: 872, y: 605), CGPoint(x: 787, y: 669), CGPoint(x: 173, y: 669)], raggio: 35)
let casa = Forma(punti: [CGPoint(x: 229, y: 659), CGPoint(x: 260, y: 330), CGPoint(x: 597, y: 330), CGPoint(x: 546, y: 659)], raggio: 58)
// Lo strato ambra (vetri.svg): la fascia dei vetri, inclinata in avanti come la casa.
// È anche il buco dello strato crema, così l'ambra riempie esattamente la finestra.
let vetri = Forma(punti: [CGPoint(x: 294, y: 368), CGPoint(x: 552, y: 368), CGPoint(x: 538, y: 459), CGPoint(x: 285, y: 459)], raggio: 21)

func colore(_ hex: UInt32, _ alfa: CGFloat = 1) -> CGColor {
    CGColor(red: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255, alpha: alfa)
}

let spazio = CGColorSpaceCreateDeviceRGB()

func gradiente(_ colori: [CGColor], _ punti: [CGFloat]) -> CGGradient {
    CGGradient(colorsSpace: spazio, colors: colori as CFArray, locations: punti)!
}

/// Quanti pixel del disegno di `lato` pixel valgono un'unità della tavola: la tavola
/// occupa il corpo dell'icona (lato meno i due margini), non l'immagine intera.
func scalaTavola(_ lato: CGFloat) -> CGFloat {
    (lato - 2 * lato * margineCorpo) / tavola
}

/// Un punto della tavola SVG (y in giù) portato nel disegno di `lato` pixel (y in su),
/// dentro il corpo dell'icona.
func punto(_ p: CGPoint, _ lato: CGFloat) -> CGPoint {
    let c = tavola / 2
    let margine = lato * margineCorpo
    let scala = scalaTavola(lato)
    let x = c + (p.x - c) * ingrandimento
    let y = c + (p.y - c) * ingrandimento
    return CGPoint(x: margine + x * scala, y: margine + (tavola - y) * scala)
}

/// Il poligono con gli spigoli arrotondati: come i percorsi degli SVG, un tratto
/// dritto fino a `raggio` dal vertice e una quadratica che lo gira.
func arrotondata(_ forma: Forma, _ lato: CGFloat) -> CGPath {
    let p = forma.punti.map { punto($0, lato) }
    let r = forma.raggio * ingrandimento * scalaTavola(lato)
    func verso(_ da: CGPoint, _ a: CGPoint) -> CGPoint {
        let dx = a.x - da.x, dy = a.y - da.y
        let lunghezza = (dx * dx + dy * dy).squareRoot()
        let t = min(r, lunghezza / 2) / lunghezza
        return CGPoint(x: da.x + dx * t, y: da.y + dy * t)
    }
    let percorso = CGMutablePath()
    for i in 0..<p.count {
        let prima = p[(i + p.count - 1) % p.count], qui = p[i], dopo = p[(i + 1) % p.count]
        let entra = verso(qui, prima), esce = verso(qui, dopo)
        if i == 0 { percorso.move(to: entra) } else { percorso.addLine(to: entra) }
        percorso.addQuadCurve(to: esce, control: qui)
    }
    percorso.closeSubpath()
    return percorso
}

/// Lo strato crema: scafo e casa fusi in una forma sola, meno i vetri.
func nave(_ lato: CGFloat) -> CGPath {
    let corpo = arrotondata(scafo, lato)
        .union(arrotondata(casa, lato), using: .winding)
    return corpo.subtracting(arrotondata(vetri, lato), using: .winding)
}

func disegna(lato: Int) -> Data? {
    let s = CGFloat(lato)
    guard let ctx = CGContext(data: nil, width: lato, height: lato, bitsPerComponent: 8,
                              bytesPerRow: 0, space: spazio,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    else { return nil }

    // ------------------------------------------------------------ il fondo
    // Il corpo dell'icona è un quadrato arrotondato di 824 su 1024, come da
    // griglia di Apple, lasciando il margine per l'ombra.
    let margine = s * margineCorpo
    let corpo = CGRect(x: margine, y: margine, width: s - margine * 2, height: s - margine * 2)
    let raggio = corpo.width * 0.225
    let forma = CGPath(roundedRect: corpo, cornerWidth: raggio, cornerHeight: raggio, transform: nil)

    // ombra dell'intera icona
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -s * 0.010), blur: s * 0.028,
                  color: CGColor(gray: 0, alpha: 0.38))
    ctx.addPath(forma)
    ctx.setFillColor(colore(0x141822))
    ctx.fillPath()
    ctx.restoreGState()

    ctx.saveGState()
    ctx.addPath(forma)
    ctx.clip()
    // gradiente sobrio: la stessa tinta del fondo del .icon (#121620), più chiara in alto
    ctx.drawLinearGradient(gradiente([colore(0x1b202d), colore(0x121620), colore(0x0e1118)],
                                     [0, 0.55, 1]),
                           start: CGPoint(x: 0, y: corpo.maxY), end: CGPoint(x: 0, y: corpo.minY),
                           options: [])
    // riflesso morbido in alto: un velo, non una macchia
    ctx.drawLinearGradient(gradiente([colore(0xffffff, 0.045), colore(0xffffff, 0)], [0, 1]),
                           start: CGPoint(x: 0, y: corpo.maxY),
                           end: CGPoint(x: 0, y: corpo.maxY - corpo.height * 0.42), options: [])
    ctx.restoreGState()

    // filo di luce dentro il bordo: forte in alto, quasi spento in basso
    ctx.saveGState()
    ctx.addPath(forma)
    ctx.clip()
    ctx.addPath(forma)
    ctx.setLineWidth(max(1, s * 0.006) * 2)
    ctx.replacePathWithStrokedPath()
    ctx.clip()
    ctx.drawLinearGradient(gradiente([colore(0xffffff, 0.24), colore(0xffffff, 0.04),
                                      colore(0xffffff, 0.09)], [0, 0.5, 1]),
                           start: CGPoint(x: 0, y: corpo.maxY), end: CGPoint(x: 0, y: corpo.minY),
                           options: [])
    ctx.restoreGState()

    // ------------------------------------------------------------ la nave
    // Sotto lo strato crema, sopra i vetri d'ambra: come l'ordine degli strati
    // (nel .icon il primo è quello in cima, qui si disegna dal fondo).
    let strati: [(CGPath, CGColor, CGColor, CGFloat)] = [
        (nave(s), colore(0xece8df), colore(0xb7b3aa), 0.94),
        (arrotondata(vetri, s), colore(0xe89c5c), colore(0xc7803f), 1.0),
    ]
    let lunghezza = s * 0.0065   // profondità dell'ombra corta e dello spessore del bordo di luce

    for (percorso, alto, basso, alfa) in strati {
        let riquadro = percorso.boundingBoxOfPath

        // ombra corta sotto lo strato
        ctx.saveGState()
        ctx.setAlpha(alfa)
        ctx.setShadow(offset: CGSize(width: 0, height: -lunghezza * 1.4), blur: s * 0.022,
                      color: CGColor(gray: 0, alpha: 0.5))
        ctx.addPath(percorso)
        ctx.setFillColor(basso)
        ctx.fillPath()
        ctx.restoreGState()

        // il corpo dello strato, con un gradiente verticale e una trasparenza misurata
        ctx.saveGState()
        ctx.setAlpha(alfa)
        ctx.addPath(percorso)
        ctx.clip()
        ctx.drawLinearGradient(gradiente([alto, basso], [0, 1]),
                               start: CGPoint(x: 0, y: riquadro.maxY),
                               end: CGPoint(x: 0, y: riquadro.minY), options: [])
        ctx.restoreGState()

        // bordo di luce in alto: la parte dello strato che resta fuori dalla sua copia
        // spostata in giù, cioè una sottile falce lungo i lati che guardano in su
        ctx.saveGState()
        ctx.addPath(percorso)
        ctx.clip()
        var giù = CGAffineTransform(translationX: 0, y: -lunghezza)
        if let spostata = percorso.copy(using: &giù) {
            ctx.addRect(CGRect(x: -s, y: -s, width: s * 3, height: s * 3))
            ctx.addPath(spostata)
            ctx.clip(using: .evenOdd)
            ctx.setFillColor(colore(0xffffff, 0.45))
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
        }
        ctx.restoreGState()
    }

    guard let img = ctx.makeImage() else { return nil }
    let rep = NSBitmapImageRep(cgImage: img)
    return rep.representation(using: .png, properties: [:])
}

let misure: [(String, Int)] = [
    ("icon_16x16", 16), ("icon_16x16@2x", 32),
    ("icon_32x32", 32), ("icon_32x32@2x", 64),
    ("icon_128x128", 128), ("icon_128x128@2x", 256),
    ("icon_256x256", 256), ("icon_256x256@2x", 512),
    ("icon_512x512", 512), ("icon_512x512@2x", 1024),
]
for (nome, lato) in misure {
    if let data = disegna(lato: lato) {
        try? data.write(to: URL(fileURLWithPath: "\(out)/\(nome).png"))
    }
}
print("iconset in \(out)")
