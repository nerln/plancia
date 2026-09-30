// La dimensione del testo di tutta l'app, a passi: ⌘+ ingrandisce, ⌘- riduce, ⌘0 torna
// alla dimensione reale. Il passo (un numero) si ricorda fra un avvio e l'altro; la
// radice della finestra lo traduce in un DynamicTypeSize, che scala i font semantici
// delle viste, delle tabelle e del grafo.

import SwiftUI
import AppKit

enum DimensioneTesto {
    static let chiave = "dimensioneTesto"

    /// I passi, dal piu' piccolo al piu' grande. Il quarto e' la dimensione reale.
    static let passi: [DynamicTypeSize] = [
        .xSmall, .small, .medium, .large, .xLarge, .xxLarge, .xxxLarge,
    ]
    static let predefinito = 3

    static func limita(_ passo: Int) -> Int { min(max(passo, 0), passi.count - 1) }
    static func tipo(_ passo: Int) -> DynamicTypeSize { passi[limita(passo)] }

    /// Percentuale rispetto alla dimensione reale. Il tetto e' 125%: oltre, alla larghezza
    /// normale della finestra (1280 punti) Progetti e Memoria non stanno piu' nello spazio.
    static func percentuale(_ passo: Int) -> Int {
        let scala: [Int] = [85, 90, 95, 100, 108, 116, 125]
        return scala[limita(passo)]
    }
}

extension DimensioneTesto {
    static func fattore(_ passo: Int) -> CGFloat { CGFloat(percentuale(passo)) / 100 }
}

/// Su macOS `dynamicTypeSize` non cambia nulla ai font di sistema (verificato: il
/// testo misura uguale a ogni passo), quindi la scala la fa l'app.
struct ScalaTesto: ViewModifier {
    let fattore: CGFloat

    func body(content: Content) -> some View {
        if abs(fattore - 1) < 0.001 {
            content.environment(\.fattoreTesto, 1)
        } else {
            GeometryReader { g in
                content
                    .environment(\.fattoreTesto, fattore)
                    .frame(width: g.size.width / fattore, height: g.size.height / fattore, alignment: .topLeading)
                    .scaleEffect(fattore, anchor: .topLeading)
                    .frame(width: g.size.width, height: g.size.height, alignment: .topLeading)
            }
        }
    }
}

extension View {
    func scalaTesto(_ passo: Int) -> some View { modifier(ScalaTesto(fattore: DimensioneTesto.fattore(passo))) }
}

/// ⌘= come ⌘+: sulle tastiere americane il piu' vuole la Maiuscola, e Safari, Pages e
/// gli altri accettano anche il tasto uguale. Il menu tiene ⌘+ e ⌘-, questo aggiunge ⌘=.
@MainActor
enum TastiTesto {
    private static var installato = false

    static func installa() {
        guard !installato else { return }
        installato = true
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { e in
            let mod = e.modifierFlags.intersection([.command, .shift, .option, .control])
            guard mod == .command, e.charactersIgnoringModifiers == "=" else { return e }
            // col puntatore sulla mappa della memoria i tasti sono dello zoom della mappa
            if MappaMemoriaTasti.puntatoreSopra(e.window) { return e }
            let d = UserDefaults.standard
            let corrente = d.object(forKey: DimensioneTesto.chiave) as? Int ?? DimensioneTesto.predefinito
            d.set(DimensioneTesto.limita(corrente + 1), forKey: DimensioneTesto.chiave)
            return nil
        }
    }
}

private struct ChiaveFattoreTesto: EnvironmentKey { static let defaultValue: CGFloat = 1 }

extension EnvironmentValues {
    /// Di quanto l'app e' ingrandita (1 = dimensione reale): serve a chi disegna in punti
    /// della finestra, come la fascia sotto la barra degli strumenti, che non scala.
    var fattoreTesto: CGFloat {
        get { self[ChiaveFattoreTesto.self] }
        set { self[ChiaveFattoreTesto.self] = newValue }
    }
}

/// Il ponte fra il tema e la mappa della memoria, per non far litigare gli zoom.
typealias MappaMemoriaTasti = AscoltoInput.VistaAscolto
