// Le Impostazioni (⌘,): la lingua, lo stile (Sistema o Legno), l'aspetto e la dimensione del testo. Il tema non e' un pulsante nella finestra.

import SwiftUI

/// Come l'app si veste: segue il sistema, oppure sempre chiaro o sempre scuro.
enum Aspetto: String, CaseIterable, Identifiable {
    case sistema, chiaro, scuro
    var id: String { rawValue }

    @MainActor var titolo: String {
        switch self {
        case .sistema: return tr("Sistema", "System")
        case .chiaro: return tr("Chiaro", "Light")
        case .scuro: return tr("Scuro", "Dark")
        }
    }

    var schema: ColorScheme? {
        switch self {
        case .sistema: return nil
        case .chiaro: return .light
        case .scuro: return .dark
        }
    }
}

struct Impostazioni: View {
    @Environment(Lingua.self) private var lingua
    @AppStorage("aspetto") private var aspetto = Aspetto.sistema.rawValue
    @AppStorage(StileApp.chiave) private var stile = StileApp.sistema.rawValue
    @AppStorage(DimensioneTesto.chiave) private var passoTesto = DimensioneTesto.predefinito

    var body: some View {
        let scelta = Binding<String>(get: { lingua.codice }, set: { lingua.imposta($0) })
        Form {
            Picker(tr("Lingua", "Language"), selection: scelta) {
                Text("Italiano").tag("it")
                Text("English").tag("en")
            }
            Picker(tr("Stile", "Style"), selection: $stile) {
                ForEach(StileApp.allCases) { Text($0.titolo).tag($0.rawValue) }
            }
            Picker(tr("Aspetto", "Appearance"), selection: $aspetto) {
                ForEach(Aspetto.allCases) { Text($0.titolo).tag($0.rawValue) }
            }
            LabeledContent(tr("Dimensione del testo", "Text size")) {
                HStack {
                    Button {
                        passoTesto = DimensioneTesto.limita(passoTesto - 1)
                    } label: { Image(systemName: "textformat.size.smaller") }
                        .disabled(passoTesto <= 0)
                        .help(tr("Riduci", "Smaller"))
                    Text("\(DimensioneTesto.percentuale(passoTesto))%")
                        .monospacedDigit()
                        .frame(minWidth: 44)
                    Button {
                        passoTesto = DimensioneTesto.limita(passoTesto + 1)
                    } label: { Image(systemName: "textformat.size.larger") }
                        .disabled(passoTesto >= DimensioneTesto.passi.count - 1)
                        .help(tr("Ingrandisci", "Larger"))
                    Button(tr("Reale", "Actual")) { passoTesto = DimensioneTesto.predefinito }
                        .disabled(passoTesto == DimensioneTesto.predefinito)
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 380)
        .fixedSize(horizontal: false, vertical: true)
        .preferredColorScheme((Aspetto(rawValue: aspetto) ?? .sistema).schema)
    }
}
