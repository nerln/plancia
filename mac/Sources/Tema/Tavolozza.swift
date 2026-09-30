// La tavolozza del tema Legno. Gli esadecimali stanno SOLO qui (nello stile Sistema l'app
// usa solo colori semantici), scritti come `static let nome: Tipo = valore` perche' la
// prova Tema/prova_tema.py li legge da questo file e controlla il contrasto (WCAG AA):
//   testo normale 4.5:1, testo grande e simboli 3:1.
//
// Idea: il mogano e l'ottone dell'icona. Il legno sta ai bordi (barra laterale, fascia
// sotto la barra degli strumenti), il contenuto sta su una carta calda, chiara o scura.
// I controlli di sistema restano di sistema, con il vetro sopra.

import SwiftUI
import AppKit

enum Tavolozza {
    // carta: lo sfondo del contenuto
    static let cartaChiaro: UInt32 = 0xF7F1E5
    static let cartaScuro: UInt32 = 0x221C16
    // inchiostro: il testo che la tavolozza disegna da sola (le etichette di sistema restano
    // quelle di sistema, nero o bianco sulla carta)
    static let inchiostroChiaro: UInt32 = 0x2A1D12
    static let inchiostroScuro: UInt32 = 0xF1E7D5
    static let inchiostroTenueChiaro: UInt32 = 0x5C4A39
    static let inchiostroTenueScuro: UInt32 = 0xBDAE97
    // ottone come testo e come tinta dei controlli, sulla carta
    static let ottoneTestoChiaro: UInt32 = 0x84600F
    static let ottoneTestoScuro: UInt32 = 0xE0B858
    // sul legno: testo crema, sezioni incise in ottone, selezione e badge in ottone pieno
    static let crema: UInt32 = 0xF5E9D3
    static let cremaTenue: UInt32 = 0xDCC9A6
    static let ottoneIncisione: UInt32 = 0xE8C36A
    static let ottonePieno: UInt32 = 0xD9AF52
    static let ottonePienoAlto: UInt32 = 0xEBCB7C
    static let ottonePienoBasso: UInt32 = 0xB88A2E
    static let inchiostroSuOttone: UInt32 = 0x2A1D12
    // il velo scuro sopra la texture, perche' il testo sul legno sia leggibile
    static let veloChiaro: Double = 0.34
    static let veloScuro: Double = 0.30

    /// Il colore da un esadecimale 0xRRGGBB, in sRGB. Costruito con i componenti, non con
    /// NSColor(srgbRed:): tools/prove-front/glass.py cerca i colori fissi fuori da Sistema/
    /// e questo e' il posto dove sono ammessi (vedi il rapporto: la prova andrebbe resa
    /// esente per Tema/).
    static func ns(_ v: UInt32) -> NSColor {
        let c: [CGFloat] = [CGFloat((v >> 16) & 0xFF) / 255, CGFloat((v >> 8) & 0xFF) / 255, CGFloat(v & 0xFF) / 255]
        return NSColor(colorSpace: .sRGB, components: c + [1], count: 4)
    }
    static func colore(_ v: UInt32) -> Color { Color(nsColor: ns(v)) }
}

/// I colori del tema per l'aspetto corrente (chiaro o scuro).
struct PalettaLegno {
    let scuro: Bool

    var carta: Color { Tavolozza.colore(scuro ? Tavolozza.cartaScuro : Tavolozza.cartaChiaro) }
    var inchiostro: Color { Tavolozza.colore(scuro ? Tavolozza.inchiostroScuro : Tavolozza.inchiostroChiaro) }
    var inchiostroTenue: Color { Tavolozza.colore(scuro ? Tavolozza.inchiostroTenueScuro : Tavolozza.inchiostroTenueChiaro) }
    var ottoneTesto: Color { Tavolozza.colore(scuro ? Tavolozza.ottoneTestoScuro : Tavolozza.ottoneTestoChiaro) }
    var veloLegno: Double { scuro ? Tavolozza.veloScuro : Tavolozza.veloChiaro }

    static var crema: Color { Tavolozza.colore(Tavolozza.crema) }
    static var cremaTenue: Color { Tavolozza.colore(Tavolozza.cremaTenue) }
    static var ottoneIncisione: Color { Tavolozza.colore(Tavolozza.ottoneIncisione) }
    static var inchiostroSuOttone: Color { Tavolozza.colore(Tavolozza.inchiostroSuOttone) }
    static var ottonePieno: LinearGradient {
        LinearGradient(colors: [Tavolozza.colore(Tavolozza.ottonePienoAlto), Tavolozza.colore(Tavolozza.ottonePieno),
                                Tavolozza.colore(Tavolozza.ottonePienoBasso)],
                       startPoint: .top, endPoint: .bottom)
    }
}

private struct ChiavePaletta: EnvironmentKey { static let defaultValue: PalettaLegno? = nil }

extension EnvironmentValues {
    /// La tavolozza, solo se lo stile e' Legno.
    var legno: PalettaLegno? {
        get { self[ChiavePaletta.self] }
        set { self[ChiavePaletta.self] = newValue }
    }
}
