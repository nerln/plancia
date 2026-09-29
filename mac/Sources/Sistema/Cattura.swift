// Fotografare una finestra dell'app: serve alle istantanee (Guscio/Istantanee.swift),
// a "Salva una schermata" e a plancia://pdf.
//
// Primo metodo: CGWindowListCreateImage sulla finestra. Una finestra della propria app
// si legge senza il permesso "Registrazione schermo", e il risultato e' quello vero:
// barra laterale con il vetro, barra degli strumenti, sottotitolo, campo di ricerca.
// La funzione e' segnata "non piu' disponibile" nell'SDK, quindi si cerca a runtime.
// Richiede la finestra sullo schermo (anche coperta va bene; su un altro Spazio no).
//
// Ripiego: cacheDisplay della cornice della finestra. Rende i testi e i colori, ma
// non le viste con materiale (la barra laterale esce vuota): vale per il layout, non
// per il vetro.

import AppKit

@MainActor
enum Cattura {
    private typealias FunzioneImmagine = @convention(c) (CGRect, UInt32, UInt32, UInt32) -> Unmanaged<CGImage>?

    /// PNG della finestra, o nil se non si riesce.
    static func png(_ finestra: NSWindow) -> Data? {
        if let cg = immagineDiSistema(finestra) {
            return NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:])
        }
        return pngDaVista(finestra)
    }

    private static func immagineDiSistema(_ finestra: NSWindow) -> CGImage? {
        guard finestra.windowNumber > 0,
              let h = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "CGWindowListCreateImage") else { return nil }
        let f = unsafeBitCast(h, to: FunzioneImmagine.self)
        // kCGWindowListOptionIncludingWindow = 1 << 3, kCGWindowImageBoundsIgnoreFraming = 1 << 0
        let im = f(.null, 1 << 3, UInt32(finestra.windowNumber), 1 << 0)?.takeRetainedValue()
        // un'immagine di 1x1 o vuota e' una finestra che il sistema non ha dipinto
        guard let im = im, im.width > 8, im.height > 8 else { return nil }
        return im
    }

    private static func pngDaVista(_ finestra: NSWindow) -> Data? {
        guard let cornice = finestra.contentView?.superview ?? finestra.contentView else { return nil }
        let r = cornice.bounds
        guard let rep = cornice.bitmapImageRepForCachingDisplay(in: r) else { return nil }
        cornice.cacheDisplay(in: r, to: rep)
        // dove il materiale non si dipinge il fondo resta trasparente: lo si mette sotto
        let img = NSImage(size: r.size)
        img.addRepresentation(rep)
        guard let fuori = cornice.bitmapImageRepForCachingDisplay(in: r) else { return nil }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: fuori)
        finestra.effectiveAppearance.performAsCurrentDrawingAppearance {
            NSColor.windowBackgroundColor.setFill()
        }
        r.fill()
        img.draw(in: r, from: .zero, operation: .sourceOver, fraction: 1)
        NSGraphicsContext.restoreGraphicsState()
        return fuori.representation(using: .png, properties: [:])
    }

    /// PDF del contenuto della finestra.
    static func pdf(_ finestra: NSWindow) -> Data? {
        guard let v = finestra.contentView else { return nil }
        return v.dataWithPDF(inside: v.bounds)
    }
}
