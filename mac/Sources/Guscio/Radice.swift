// La finestra: barra laterale di sistema con le sei sezioni, il contenuto, la barra degli
// strumenti (compartimento se attivi, Aggiorna), il campo di ricerca di sistema e lo stato
// nel sottotitolo. Niente logo, niente pulsanti Tema o lingua, niente sfondi propri: i
// materiali li danno i controlli standard.

import SwiftUI

struct Radice: View {
    @Environment(Archivio.self) private var archivio
    @Environment(Lingua.self) private var lingua
    @AppStorage("aspetto") private var aspetto = Aspetto.sistema.rawValue

    var body: some View {
        @Bindable var a = archivio
        let sezione = Binding<Sezione?>(
            get: { archivio.sezione },
            set: { if let s = $0 { archivio.vai(s) } })

        NavigationSplitView {
            List(selection: sezione) {
                ForEach(Sezione.allCases) { s in
                    Label(s.titolo, systemImage: s.simbolo)
                        .badge(archivio.conteggio(s) ?? 0)
                        .tag(s)
                }
            }
            .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(min: 170, ideal: 200, max: 260)
        } detail: {
            contenuto
                .navigationTitle(archivio.ricerca.trimmed.isEmpty ? archivio.sezione.titolo : tr("Ricerca", "Search"))
                .navigationSubtitle(archivio.sottotitolo)
        }
        .searchable(text: $a.ricerca, placement: .toolbar, prompt: Text(tr("Cerca", "Search")))
        .searchScopes($a.ambito, activation: .onTextEntry) {
            ForEach(AmbitoRicerca.allCases) { Text($0.titolo).tag($0) }
        }
        .toolbar {
            if archivio.compartimenti.attivi {
                ToolbarItem(placement: .automatic) { selettoreCompartimento }
            }
            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await archivio.aggiorna() }
                } label: {
                    Label(tr("Aggiorna", "Refresh"), systemImage: "arrow.clockwise")
                }
                .help(tr("Aggiorna", "Refresh"))
            }
        }
        .onChange(of: archivio.ricerca) { archivio.avviaRicerca() }
        .task(id: archivio.sezione) { await archivio.carica(archivio.sezione) }
        .preferredColorScheme((Aspetto(rawValue: aspetto) ?? .sistema).schema)
    }

    @ViewBuilder private var contenuto: some View {
        if !archivio.ricerca.trimmed.isEmpty {
            VistaRisultati()
        } else {
            switch archivio.sezione {
            case .oggi: VistaOggi()
            case .task: VistaTask()
            case .progetti: VistaProgetti()
            case .social: VistaSocial()
            case .memoria: VistaMemoria()
            case .archivio: VistaArchivio()
            }
        }
    }

    private var selettoreCompartimento: some View {
        let corrente = Binding<String>(
            get: { archivio.compartimento ?? archivio.compartimenti.scelto ?? archivio.compartimenti.predefinito ?? "" },
            set: { archivio.compartimento = $0 })
        return Picker(tr("Compartimento", "Compartment"), selection: corrente) {
            ForEach(archivio.compartimenti.elenco ?? [], id: \.self) { Text($0).tag($0) }
        }
        .pickerStyle(.menu)
    }
}
