// L'Inspector della finestra: uno solo, in Radice, con il contenuto scelto dalla sezione.
// Un `.inspector` per vista costava 10-25 ms a ogni cambio di sezione (misurato): qui la
// colonna resta la stessa e cambia solo quello che ci sta dentro.
//
// Il contenuto viene dai dati dello Store (la selezione di ogni sezione sta li') e da
// ControlliVista (l'evento del registro, il dettaglio di un risultato di ricerca).

import SwiftUI

/// Aggiunge l'Inspector al contenuto della finestra.
struct IspettoreFinestra: ViewModifier {
    @Environment(Archivio.self) private var archivio
    private let c = ControlliVista.condiviso

    @ViewBuilder func body(content: Content) -> some View {
        if Sper.senzaInspector { content } else {
        content.inspector(isPresented: Binding(get: { presente }, set: { if !$0 { chiudi() } })) {
            ContenutoIspettore()
                .inspectorColumnWidth(min: 260, ideal: 330, max: 480)
        }
        }
    }

    private var inRicerca: Bool { !archivio.ricerca.trimmed.isEmpty }

    /// C'e' qualcosa di scelto da mostrare nella sezione aperta.
    private var presente: Bool {
        if inRicerca { return c.dettaglioRisultato != nil }
        switch archivio.sezione {
        case .task: return archivio.rigaTaskScelta() != nil
        case .social: return archivio.postSceltoOra() != nil
        case .memoria: return archivio.memoriaScelta.flatMap { archivio.datiMemoria.perNome[$0] } != nil
        case .archivio:
            return c.modoArchivio == .sessioni ? archivio.rigaSessioneScelta() != nil : archivio.rigaEventoScelta() != nil
        case .oggi, .progetti: return false
        }
    }

    private func chiudi() {
        if inRicerca { return }
        switch archivio.sezione {
        case .task: archivio.taskScelto = nil
        case .social: archivio.postScelto = nil
        case .memoria: archivio.memoriaScelta = nil
        case .archivio: archivio.sessioneScelta = nil; c.eventoScelto = nil
        case .oggi, .progetti: break
        }
    }
}

/// Quello che sta nella colonna.
struct ContenutoIspettore: View {
    @Environment(Archivio.self) private var archivio
    private let c = ControlliVista.condiviso

    var body: some View {
        Group {
            if !archivio.ricerca.trimmed.isEmpty {
                if let d = c.dettaglioRisultato { d }
            } else {
                switch archivio.sezione {
                case .task:
                    if let r = archivio.rigaTaskScelta() { DettaglioTask(riga: r).id(r.id) }
                case .social:
                    if let p = archivio.postSceltoOra() { DettaglioPost(post: p).id(p.identita) }
                case .memoria:
                    let dati = archivio.datiMemoria
                    if let f = archivio.memoriaScelta.flatMap({ dati.perNome[$0] }) {
                        DettaglioMemoria(fatto: f, dati: dati)
                    }
                case .archivio:
                    if c.modoArchivio == .sessioni {
                        if let r = archivio.rigaSessioneScelta() { DettaglioSessioneArch(riga: r) }
                    } else {
                        if let r = archivio.rigaEventoScelta() { DettaglioEventoArch(riga: r) }
                    }
                case .oggi, .progetti:
                    EmptyView()
                }
            }
        }
        .stileIspettore()
    }
}

extension View {
    func ispettoreFinestra() -> some View { modifier(IspettoreFinestra()) }
}
