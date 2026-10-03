// I controlli della barra degli strumenti. La barra e' una sola, della finestra (Radice), con
// gli stessi elementi in ogni sezione: quello che cambia da una sezione all'altra e' il
// contenuto di ciascun elemento, non la lista degli elementi. Farli comparire e sparire
// insieme alla vista costava a ogni cambio di sezione 30-60 ms di ricalcolo della barra
// (misurato con `sample`: NSToolbarView layout).
//
// Lo stato che i controlli muovono (filtri, modalita', fogli) sta qui e non nelle viste,
// perche' la barra e' fuori dalle viste: le viste lo leggono.

import SwiftUI

@MainActor @Observable
final class ControlliVista {
    static let condiviso = ControlliVista()

    // Task
    var statoTask: FiltroStato = .aperti
    var fonteTask = ""                       // "" = tutte
    var nuovoTask = false
    // Progetti
    var filtroProgetti: FiltroProgetti = .attivi
    // Social
    var filtroPost: FiltroPost = .inCoda
    var nuovaBozza = false
    // Archivio
    var modoArchivio: ModoArch = .sessioni
    var agenteArchivio = ""                  // "" = tutti
    var tipoEvento = ""                      // "" = tutti
    var eventoScelto: String?
    // Memoria
    var provaAperta = false
    // Ricerca: il dettaglio della riga scelta, costruito dalla vista Risultati
    var dettaglioRisultato: AnyView?
    /// Quale istanza di VistaRisultati ha pubblicato il dettaglio (chi non e' il proprietario non lo cancella).
    var proprietarioDettaglio: UUID?
}

extension Archivio {
    /// I tipi di evento del registro, per il menu del filtro.
    var tipiEvento: [String] {
        let dichiarati = registro?.stato?.tipi ?? []
        let visti = Set((registro?.eventi ?? []).compactMap { $0.tipo })
        return Array(Set(dichiarati).union(visti)).sorted()
    }
}

// MARK: - i tre elementi che cambiano contenuto

/// Il primo controllo: un selettore segmentato (stato, filtro, modo). Vuoto dove la sezione non ne ha.
struct PrimoControllo: View {
    @Environment(Archivio.self) private var archivio

    var body: some View {
        if archivio.ricerca.trimmed.isEmpty {
            switch archivio.sezione {
            case .task: ControlloStatoTask()
            case .progetti: ControlloProgetti()
            case .social: ControlloSocial()
            case .memoria: ControlloModoMemoria()
            case .archivio: ControlloVistaArchivio()
            case .oggi: EmptyView()
            }
        }
    }
}

/// Il secondo controllo: un menu di filtro (fonte, agente, tipo).
struct SecondoControllo: View {
    @Environment(Archivio.self) private var archivio

    var body: some View {
        if archivio.ricerca.trimmed.isEmpty {
            switch archivio.sezione {
            case .task: ControlloFonteTask()
            case .archivio: ControlloFiltroArchivio()
            default: EmptyView()
            }
        }
    }
}

/// L'azione: nuovo task, nuova bozza, prova della memoria.
struct AzioneSezione: View {
    @Environment(Archivio.self) private var archivio

    var body: some View {
        if archivio.ricerca.trimmed.isEmpty {
            switch archivio.sezione {
            case .task: AzioneNuovoTask()
            case .social: AzioneNuovaBozza()
            case .memoria: AzioneProvaMemoria()
            default: EmptyView()
            }
        }
    }
}

// MARK: - i controlli, uno per sezione

private struct ControlloStatoTask: View {
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        Picker(tr("Stato", "Status"), selection: $c.statoTask) {
            ForEach(FiltroStato.allCases) { Text($0.titolo).tag($0) }
        }
        .pickerStyle(.segmented)
    }
}

private struct ControlloFonteTask: View {
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        Picker(tr("Fonte", "Source"), selection: $c.fonteTask) {
            Text(tr("Tutte le fonti", "All sources")).tag("")
            Text("Plancia").tag("plancia")
            Text("Claude").tag("claude")
            Text("Codex").tag("codex")
        }
        .pickerStyle(.menu)
    }
}

private struct AzioneNuovoTask: View {
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        Button { c.nuovoTask = true } label: {
            Label(tr("Nuovo task", "New task"), systemImage: "plus")
        }
        .keyboardShortcut("n", modifiers: .command)
        .help(tr("Nuovo task", "New task"))
    }
}

private struct ControlloProgetti: View {
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        Picker(tr("Mostra", "Show"), selection: $c.filtroProgetti) {
            ForEach(FiltroProgetti.allCases) { Text($0.titolo).tag($0) }
        }
        .pickerStyle(.segmented)
    }
}

private struct ControlloSocial: View {
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        Picker(tr("Mostra", "Show"), selection: $c.filtroPost) {
            ForEach(FiltroPost.allCases) { Text($0.titolo).tag($0) }
        }
        .pickerStyle(.segmented)
    }
}

private struct AzioneNuovaBozza: View {
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        Button { c.nuovaBozza = true } label: {
            Label(tr("Nuova bozza", "New draft"), systemImage: "plus")
        }
        .keyboardShortcut("n", modifiers: .command)
        .help(tr("Nuova bozza", "New draft"))
    }
}

private struct ControlloModoMemoria: View {
    @AppStorage("memoriaModo") private var modoGuardato = ModoMemoria.elenco.rawValue

    var body: some View {
        // nelle istantanee con --memoria-scena la mappa si apre da sola, senza scrivere le preferenze
        let modo = Binding<ModoMemoria>(
            get: { ScenaMappa.nome != nil ? .mappa : (ModoMemoria(rawValue: modoGuardato) ?? .elenco) },
            set: { if ScenaMappa.nome == nil { modoGuardato = $0.rawValue } })
        Picker(tr("Modo", "Mode"), selection: modo) {
            ForEach(ModoMemoria.allCases) { Text($0.titolo).tag($0) }
        }
        .pickerStyle(.segmented)
        .help(tr("Elenco, vicinato del fatto scelto, o mappa di tutta la memoria",
                 "List, neighbourhood of the chosen fact, or map of all memory"))
    }
}

private struct AzioneProvaMemoria: View {
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        Button { c.provaAperta.toggle() } label: {
            Label(tr("Prova la memoria", "Try memory"), systemImage: "text.magnifyingglass")
        }
        .labelStyle(.iconOnly)
        .help(tr("Scrivi una frase e guarda cosa ti direbbe la memoria",
                 "Write a sentence and see what memory would tell you"))
        .popover(isPresented: $c.provaAperta, arrowEdge: .bottom) { ProvaRichiamo() }
    }
}

private struct ControlloVistaArchivio: View {
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        Picker(tr("Vista", "View"), selection: $c.modoArchivio) {
            ForEach(ModoArch.allCases) { Text($0.titolo).tag($0) }
        }
        .pickerStyle(.segmented)
    }
}

private struct ControlloFiltroArchivio: View {
    @Environment(Archivio.self) private var archivio
    @Bindable private var c = ControlliVista.condiviso

    var body: some View {
        switch c.modoArchivio {
        case .sessioni:
            Picker(tr("Agente", "Agent"), selection: $c.agenteArchivio) {
                Text(tr("Tutti gli agenti", "All agents")).tag("")
                Text("Claude").tag("claude")
                Text("Codex").tag("codex")
            }
            .pickerStyle(.menu)
        case .registro:
            Picker(tr("Tipo", "Type"), selection: $c.tipoEvento) {
                Text(tr("Tutti i tipi", "All types")).tag("")
                ForEach(archivio.tipiEvento, id: \.self) { Text($0).tag($0) }
            }
            .pickerStyle(.menu)
        }
    }
}
