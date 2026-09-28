// Disegna l'icona di ripiego dell'app: l'ago di bussola, in due metà.
//
// La strada buona per l'icona è mac/icona/Plancia.icon (Icon Composer, macOS 26+):
// lì il vetro lo applica il sistema, strato per strato. Questo file serve quando
// quella strada non c'è (Xcode senza actool 26+, o actool che rifiuta il .icon):
// disegna a mano, con CoreGraphics, la stessa forma con un vetro imitato con
// mano leggera, e mac/build.sh la trasforma in Plancia.icns con `iconutil`.
//
// Il segno è uno solo e sta nei due file allo stesso modo: due triangoli
// (nord in ambra, sud in crema) ruotati di 40 gradi attorno al centro di una
// tavola di 1024, ingranditi di 1,35, con gli spigoli arrotondati da un bordo di
// 40. Le coordinate qui sotto sono quelle di mac/icona/Plancia.icon/Assets/*.svg:
// se cambi il segno di là, cambialo anche qui (lo controlla
// tools/prove-front/icona.py).
//
// Coordinate uguali non bastano, conta anche il riferimento. In Icon Composer la
// tela da 1024 del .icon coincide con il CORPO dell'icona (il quadrato
// arrotondato da 824 px sulla griglia di Apple): actool la rimpicciolisce dentro
// i margini. Quindi qui la tavola si porta dentro il corpo, non dentro l'intera
// immagine: se la si portasse sull'intera immagine l'ago uscirebbe più grande
// di 1024/824, cioè del 24 per cento, e con e senza Xcode 26 l'app avrebbe due
// icone diverse (misurato sulle PNG di actool e del ripiego). Il vetro imitato è: un fondo con un gradiente
// sobrio, un filo di luce dentro il bordo in alto, un riflesso morbido, e per
// ogni metà un'ombra corta sotto e un bordo di luce sopra.
//
// Si esegue con `swift mac/makeicon.swift <cartella-iconset>`.

import AppKit
import CoreGraphics
import Foundation

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "./Plancia.iconset"
try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)

// La tavola dei file SVG: 1024 per 1024, con l'origine in alto a sinistra.
let tavola: CGFloat = 1024
let rotazione: CGFloat = 40 * .pi / 180   // in senso orario, come rotate(40) di SVG
let ingrandimento: CGFloat = 1.35        // il "scale" dello strato nel .icon
let bordoSpigoli: CGFloat = 40            // lo stroke-width con linejoin round
// Il margine del corpo sull'immagine intera, in frazione del lato: 0,098 è il
// 100 px su 1024 della griglia di Apple. Una costante sola, usata dal corpo
// (in disegna) e dalla mappa della tavola (in punto e in metà).
let margineCorpo: CGFloat = 0.098

// nord: M512 190 L634 500 H390 Z  ·  sud: M390 524 H634 L512 834 Z
let nord: [CGPoint] = [CGPoint(x: 512, y: 190), CGPoint(x: 634, y: 500), CGPoint(x: 390, y: 500)]
let sud: [CGPoint] = [CGPoint(x: 390, y: 524), CGPoint(x: 634, y: 524), CGPoint(x: 512, y: 834)]

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
    let dx = p.x - c, dy = p.y - c
    // rotate(40) di SVG con l'asse y in giù è una rotazione oraria sullo schermo
    let rx = dx * cos(rotazione) - dy * sin(rotazione)
    let ry = dx * sin(rotazione) + dy * cos(rotazione)
    let x = c + rx * ingrandimento
    let y = c + ry * ingrandimento
    return CGPoint(x: margine + x * scala, y: margine + (tavola - y) * scala)
}

/// Il triangolo con gli spigoli arrotondati: il poligono più il suo bordo.
func metà(_ triangolo: [CGPoint], _ lato: CGFloat) -> CGPath {
    let poligono = CGMutablePath()
    poligono.addLines(between: triangolo.map { punto($0, lato) })
    poligono.closeSubpath()
    let largo = bordoSpigoli * ingrandimento * scalaTavola(lato)
    let bordo = poligono.copy(strokingWithWidth: largo, lineCap: .round, lineJoin: .round,
                              miterLimit: 10)
    return poligono.union(bordo, using: .winding)
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

    // ------------------------------------------------------------ l'ago
    // Sotto il nord in ambra, sopra il sud in crema: come l'ordine degli strati.
    let mezze: [(CGPath, [CGPoint], CGColor, CGColor, CGFloat)] = [
        (metà(nord, s), nord, colore(0xe89c5c), colore(0xc7803f), 1.0),
        (metà(sud, s), sud, colore(0xece8df), colore(0xb7b3aa), 0.94),
    ]
    let lunghezza = s * 0.0065   // profondità dell'ombra corta e dello spessore del bordo di luce

    for (percorso, _, alto, basso, alfa) in mezze {
        let riquadro = percorso.boundingBoxOfPath

        // ombra corta sotto la metà
        ctx.saveGState()
        ctx.setAlpha(alfa)
        ctx.setShadow(offset: CGSize(width: 0, height: -lunghezza * 1.4), blur: s * 0.022,
                      color: CGColor(gray: 0, alpha: 0.5))
        ctx.addPath(percorso)
        ctx.setFillColor(basso)
        ctx.fillPath()
        ctx.restoreGState()

        // il corpo della metà, con un gradiente verticale e una trasparenza misurata
        ctx.saveGState()
        ctx.setAlpha(alfa)
        ctx.addPath(percorso)
        ctx.clip()
        ctx.drawLinearGradient(gradiente([alto, basso], [0, 1]),
                               start: CGPoint(x: 0, y: riquadro.maxY),
                               end: CGPoint(x: 0, y: riquadro.minY), options: [])
        ctx.restoreGState()

        // bordo di luce in alto: la parte della metà che resta fuori dalla sua copia
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
