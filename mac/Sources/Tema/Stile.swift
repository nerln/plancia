// Lo stile dell'app: Sistema (identico a prima) o Legno (scheumorfico ma moderno, come
// l'icona). L'aspetto chiaro/scuro e' un'altra scelta, indipendente.

import SwiftUI
import AppKit

enum StileApp: String, CaseIterable, Identifiable {
    case sistema, legno
    static let chiave = "stile"
    var id: String { rawValue }

    @MainActor var titolo: String {
        switch self {
        case .sistema: return tr("Sistema", "System")
        case .legno: return tr("Legno", "Wood")
        }
    }
}

// MARK: - texture

/// La piastrella di legno (texture dall'icona, vedi genera_textura.py), decodificata una volta.
@MainActor
enum PiastrellaLegno {
    private static func carica(_ base64: String) -> NSImage {
        guard let dati = Data(base64Encoded: base64), let im = NSImage(data: dati) else { return NSImage() }
        im.size = NSSize(width: TexturaLegno.larghezza, height: TexturaLegno.altezza)
        return im
    }
    static let chiara = carica(TexturaLegno.chiaro)
    static let scura = carica(TexturaLegno.scuro)
}

/// Tavole di mogano con un velo scuro per la leggibilita'. Riempie lo spazio che gli si da.
struct SuperficieLegno: View {
    let scuro: Bool

    var body: some View {
        let im = scuro ? PiastrellaLegno.scura : PiastrellaLegno.chiara
        Rectangle()
            .fill(ImagePaint(image: Image(nsImage: im), scale: 1))
            .overlay(Color.black.opacity(PalettaLegno(scuro: scuro).veloLegno))
            .accessibilityHidden(true)
    }
}

// MARK: - l'aspetto del sistema

/// Se il sistema e' in scuro. Con lo stile Legno la finestra e' sempre scura (il legno), quindi
/// l'aspetto del sistema non si legge piu' dall'ambiente della vista: lo tiene questo oggetto.
@MainActor @Observable
final class AspettoSistema {
    static let condiviso = AspettoSistema()
    private(set) var scuro: Bool

    private init() {
        scuro = AspettoSistema.leggi()
        DistributedNotificationCenter.default().addObserver(
            forName: Notification.Name("AppleInterfaceThemeChangedNotification"), object: nil, queue: .main) { _ in
            MainActor.assumeIsolated { AspettoSistema.condiviso.scuro = AspettoSistema.leggi() }
        }
    }

    private static func leggi() -> Bool {
        NSApp?.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
    }
}

// MARK: - il contenuto

/// Lo stile del contenuto di una vista: carta calda, tinta ottone, tabelle e liste
/// trasparenti sopra la carta, e la fascia di legno sotto la barra degli strumenti. Con lo
/// stile Sistema non fa niente. Lo applica il guscio (Radice) a tutte le viste insieme.
struct StileVista: ViewModifier {
    @AppStorage(StileApp.chiave) private var stile = StileApp.sistema.rawValue
    @AppStorage("aspetto") private var aspetto = Aspetto.sistema.rawValue
    private var sistema = AspettoSistema.condiviso

    /// La carta e' scura se l'aspetto scelto e' Scuro, o se e' Sistema e il sistema e' scuro.
    private var cartaScura: Bool {
        switch Aspetto(rawValue: aspetto) ?? .sistema {
        case .scuro: return true
        case .chiaro: return false
        case .sistema: return sistema.scuro
        }
    }

    @ViewBuilder func body(content: Content) -> some View {
        if stile == StileApp.legno.rawValue {
            let p = PalettaLegno(scuro: cartaScura)
            content
                // la finestra e' sempre scura (legno); la carta e' chiara o scura a parte
                .environment(\.colorScheme, cartaScura ? .dark : .light)
                .tint(p.ottoneTesto)
                .accentColor(p.ottoneTesto)
                .scrollContentBackground(.hidden)
                // la carta non sale sotto la barra degli strumenti: li' si vede il legno della finestra
                .background(p.carta, ignoresSafeAreaEdges: [.bottom, .leading, .trailing])
                .overlay(alignment: .top) { FiloOttone() }
                .toolbarBackgroundVisibility(.hidden, for: .windowToolbar)
                .environment(\.legno, p)
        } else {
            content
        }
    }
}

/// Il filo d'ottone tra il legno della barra degli strumenti e la carta.
struct FiloOttone: View {
    @Environment(\.fattoreTesto) private var fattore

    var body: some View {
        Rectangle().fill(PalettaLegno.ottoneIncisione.opacity(0.6))
            .frame(height: 1 / max(fattore, 0.1))
            .allowsHitTesting(false)
    }
}

/// Lo sfondo della finestra: nello stile Legno le tavole di mogano (piastrella con il velo
/// gia' dentro) dietro la barra degli strumenti e i bordi, dove il contenuto non arriva;
/// nello stile Sistema il colore di sistema di sempre.
struct FondoFinestra: NSViewRepresentable {
    let legno: Bool
    let scuro: Bool

    func makeNSView(context: Context) -> NSView { NSView() }

    func updateNSView(_ v: NSView, context: Context) {
        DispatchQueue.main.async {
            guard let w = v.window else { return }
            w.backgroundColor = legno ? FondoFinestra.colore(scuro: scuro) : .windowBackgroundColor
        }
    }

    @MainActor static func colore(scuro: Bool) -> NSColor {
        let sorgente = scuro ? PiastrellaLegno.scura : PiastrellaLegno.chiara
        let velo = PalettaLegno(scuro: scuro).veloLegno
        let im = NSImage(size: sorgente.size)
        im.lockFocus()
        sorgente.draw(in: NSRect(origin: .zero, size: sorgente.size))
        NSColor.black.withAlphaComponent(velo).setFill()
        NSRect(origin: .zero, size: sorgente.size).fill()
        im.unlockFocus()
        return NSColor(patternImage: im)
    }
}

extension View {
    func stileVista() -> some View { modifier(StileVista()) }
}
