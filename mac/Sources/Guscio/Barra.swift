// La barra laterale (lo stile di lista sidebar lo mette Radice). Stile Sistema: la lista di sistema, identica a sempre. Stile Legno:
// la stessa lista (stessi controlli, stessa tastiera) su tavole di mogano, con le voci
// in crema, la selezione e i conteggi in ottone e due intestazioni incise.

import SwiftUI

struct BarraLaterale: View {
    @Environment(Archivio.self) private var archivio
    @AppStorage("aspetto") private var aspetto = Aspetto.sistema.rawValue
    @AppStorage(StileApp.chiave) private var stile = StileApp.sistema.rawValue
    let selezione: Binding<Sezione?>

    var body: some View {
        if stile == StileApp.legno.rawValue {
            barraLegno
        } else {
            List(selection: selezione) {
                ForEach(Sezione.allCases) { s in
                    Label(s.titolo, systemImage: s.simbolo)
                        .badge(archivio.conteggio(s) ?? 0)
                        .tag(s)
                }
            }
        }
    }

    // MARK: Legno

    private var legnoScuro: Bool {
        switch Aspetto(rawValue: aspetto) ?? .sistema {
        case .scuro: return true
        case .chiaro: return false
        case .sistema: return AspettoSistema.condiviso.scuro
        }
    }

    private let gruppi: [(titolo: (String, String), voci: [Sezione])] = [
        (("Lavoro", "Work"), [.oggi, .task, .progetti, .social]),
        (("Sapere", "Knowledge"), [.memoria, .archivio]),
    ]

    private var barraLegno: some View {
        List(selection: selezione) {
            ForEach(gruppi.indices, id: \.self) { i in
                Section {
                    ForEach(gruppi[i].voci) { s in riga(s) }
                } header: {
                    IntestazioneIncisa(testo: tr(gruppi[i].titolo.0, gruppi[i].titolo.1))
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background { SuperficieLegno(scuro: legnoScuro).ignoresSafeArea() }
        // sul legno il testo e i controlli sono sempre quelli dello schema scuro
        .environment(\.colorScheme, .dark)
        .tint(Tavolozza.colore(Tavolozza.ottonePieno))
    }

    private func riga(_ s: Sezione) -> some View {
        let scelta = archivio.ricerca.trimmed.isEmpty && archivio.sezione == s
        let n = archivio.conteggio(s) ?? 0
        // niente Label: nella barra laterale il suo simbolo prende il colore d'accento del sistema
        return HStack(spacing: 8) {
            Image(systemName: s.simbolo)
                .symbolRenderingMode(.monochrome)
                .frame(width: 22)
                .accessibilityHidden(true)
            Text(s.titolo)
            Spacer(minLength: 4)
            if n > 0 { ContoOttone(n: n, sulla: scelta) }
        }
        .foregroundStyle(scelta ? PalettaLegno.inchiostroSuOttone : PalettaLegno.crema)
        .tag(s)
        .listRowBackground(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(scelta ? AnyShapeStyle(PalettaLegno.ottonePieno) : AnyShapeStyle(Color.clear))
                .padding(.horizontal, 4))
    }
}

/// Il conteggio: una targhetta d'ottone (sulla riga scelta, che e' gia' ottone, scura).
struct ContoOttone: View {
    let n: Int
    let sulla: Bool

    var body: some View {
        Text("\(n)")
            .font(.caption.weight(.semibold).monospacedDigit())
            .foregroundStyle(sulla ? PalettaLegno.crema : PalettaLegno.inchiostroSuOttone)
            .padding(.horizontal, 7)
            .padding(.vertical, 1)
            .background(Capsule().fill(sulla ? AnyShapeStyle(Tavolozza.colore(Tavolozza.inchiostroSuOttone))
                                              : AnyShapeStyle(PalettaLegno.ottonePieno)))
            .accessibilityLabel(Text("\(n)"))
    }
}

/// Un'intestazione di sezione incisa nel legno: ottone chiaro con l'ombra in alto (il
/// solco) e un filo di luce sotto. Misurata: corpo piccolo, niente maiuscole spaziate.
struct IntestazioneIncisa: View {
    let testo: String

    var body: some View {
        Text(testo)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(PalettaLegno.ottoneIncisione)
            .shadow(color: .black.opacity(0.55), radius: 0, x: 0, y: -1)
            .shadow(color: PalettaLegno.ottoneIncisione.opacity(0.28), radius: 0, x: 0, y: 1)
            .accessibilityAddTraits(.isHeader)
    }
}
