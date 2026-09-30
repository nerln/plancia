// La finestra: barra laterale (Guscio/Barra.swift) con le sei sezioni, il contenuto, la barra degli
// strumenti (compartimento se attivi, Aggiorna), il campo di ricerca di sistema e lo stato
// nel sottotitolo. Niente logo, niente pulsanti Tema o lingua, niente sfondi propri: i
// materiali li danno i controlli standard.

import SwiftUI

struct Radice: View {
    @Environment(Archivio.self) private var archivio
    @Environment(Lingua.self) private var lingua
    @AppStorage("aspetto") private var aspetto = Aspetto.sistema.rawValue
    @AppStorage(StileApp.chiave) private var stile = StileApp.sistema.rawValue
    @AppStorage(DimensioneTesto.chiave) private var passoTesto = DimensioneTesto.predefinito

    var body: some View {
        @Bindable var a = archivio
        let sezione = Binding<Sezione?>(
            // durante la ricerca il contenuto e' Risultati: nessuna voce resta evidenziata
            get: { archivio.ricerca.trimmed.isEmpty ? archivio.sezione : nil },
            set: { if let s = $0 { archivio.vai(s) } })

        NavigationSplitView {
            BarraLaterale(selezione: sezione)
                .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(min: 170, ideal: 200, max: 260)
        } detail: {
            contenuto
                .ispettoreFinestra()
                .stileVista()
                .navigationTitle(Sper.titoloFisso ? "Plancia" : (archivio.ricerca.trimmed.isEmpty ? archivio.sezione.titolo : tr("Ricerca", "Search")))
                .navigationSubtitle(Sper.titoloFisso ? "" : archivio.sottotitolo)
        }
        .searchable(text: $a.ricerca, isPresented: $a.ricercaAperta, placement: .toolbar, prompt: Text(tr("Cerca", "Search")))
        .searchScopes($a.ambito, activation: .onSearchPresentation) {
            ForEach(AmbitoRicerca.allCases) { Text($0.titolo).tag($0) }
        }
        .modifier(BarraStrumenti())
        .onChange(of: archivio.ricerca) { archivio.avviaRicerca() }
        .task(id: archivio.sezione) { await archivio.carica(archivio.sezione) }
        // Legno: la finestra e' sempre scura, la carta del contenuto e' chiara o scura (StileVista)
        .preferredColorScheme(stile == StileApp.legno.rawValue ? .dark : (Aspetto(rawValue: aspetto) ?? .sistema).schema)
        .background(FondoFinestra(legno: stile == StileApp.legno.rawValue, scuro: fondoScuro))
        .scalaTesto(passoTesto)
    }

    /// Il legno della finestra: chiaro o scuro come la carta.
    private var fondoScuro: Bool {
        switch Aspetto(rawValue: aspetto) ?? .sistema {
        case .scuro: return true
        case .chiaro: return false
        case .sistema: return AspettoSistema.condiviso.scuro
        }
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
}


/// La barra degli strumenti della finestra: la stessa in ogni sezione (Guscio/Controlli.swift).
struct BarraStrumenti: ViewModifier {
    @Environment(Archivio.self) private var archivio
    @ViewBuilder func body(content: Content) -> some View {
        if Sper.barraId {
            content.toolbar(id: "principale") {
                if archivio.compartimenti.attivi {
                    ToolbarItem(id: "compartimento", placement: .automatic) { selettoreCompartimento }
                }
                ToolbarItem(id: "aggiorna", placement: .automatic) { pulsanteAggiorna }
                if !Sper.senzaToolbar {
                    ToolbarItem(id: "primo", placement: .automatic) { PrimoControllo() }
                    ToolbarItem(id: "secondo", placement: .automatic) { SecondoControllo() }
                    ToolbarItem(id: "azione", placement: .primaryAction) { AzioneSezione() }
                }
            }
        } else {
            content.toolbar {
                if archivio.compartimenti.attivi {
                    ToolbarItem(placement: .automatic) { selettoreCompartimento }
                }
                ToolbarItem(placement: .automatic) { pulsanteAggiorna }
                if !Sper.senzaToolbar {
                    ToolbarItem(placement: .automatic) { PrimoControllo() }
                    ToolbarItem(placement: .automatic) { SecondoControllo() }
                    ToolbarItem(placement: .primaryAction) { AzioneSezione() }
                }
            }
        }
    }

    private var selettoreCompartimento: some View {
        let corrente = Binding<String>(
            get: { archivio.compartimento ?? archivio.compartimenti.scelto ?? archivio.compartimenti.predefinito ?? "" },
            set: { archivio.compartimento = $0 })
        return Picker(tr("Compartimento", "Compartment"), selection: corrente) {
            ForEach(archivio.compartimenti.elenco ?? [], id: \.self) { nome in
                Text(nome.prefix(1).uppercased() + nome.dropFirst()).tag(nome)
            }
        }
        .pickerStyle(.menu)
        .help(tr("Compartimento", "Compartment"))
    }

    private var pulsanteAggiorna: some View {
        Button {
            Task { await archivio.aggiorna() }
        } label: {
            Label(tr("Aggiorna", "Refresh"), systemImage: "arrow.clockwise")
        }
        .help(tr("Aggiorna", "Refresh"))
    }
}
