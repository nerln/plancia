// Le Impostazioni (⌘,): la lingua e l'aspetto. Il tema non e' un pulsante nella finestra.

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

    var body: some View {
        let scelta = Binding<String>(get: { lingua.codice }, set: { lingua.imposta($0) })
        Form {
            Picker(tr("Lingua", "Language"), selection: scelta) {
                Text("Italiano").tag("it")
                Text("English").tag("en")
            }
            Picker(tr("Aspetto", "Appearance"), selection: $aspetto) {
                ForEach(Aspetto.allCases) { Text($0.titolo).tag($0.rawValue) }
            }
        }
        .formStyle(.grouped)
        .frame(width: 380)
        .fixedSize(horizontal: false, vertical: true)
        .preferredColorScheme((Aspetto(rawValue: aspetto) ?? .sistema).schema)
    }
}
