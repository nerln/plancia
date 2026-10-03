// L'Inspector della finestra: uno solo, in Radice, con il contenuto scelto dalla sezione. Le
// viste non ne hanno uno loro: la sezione sceglie solo cosa mostrarci dentro.
//
// Il contenuto viene dai dati dello Store (la selezione di ogni sezione sta li') e da
// ControlliVista (l'evento del registro, il dettaglio di un risultato di ricerca).

import SwiftUI

/// Aggiunge l'Inspector al contenuto della finestra. L'Inspector sta sul contenuto vero (e' lui che
/// deve restringersi quando la colonna si apre) e cambia identita' a ogni sezione, come il
/// contenuto, che e' gia' una vista diversa per sezione: la colonna nasce nello stato giusto invece
/// di chiudersi con l'animazione di AppKit quando si lascia una sezione con l'Inspector aperto
/// (NSSplitViewItem collapse, misurato con sample: 700-1700 milioni di istruzioni a cambio).
/// Costo in piu' rispetto a non averlo: nessuno, la sezione si ricostruisce comunque.
struct IspettoreFinestra: ViewModifier {
    @Environment(Archivio.self) private var archivio
    private let c = ControlliVista.condiviso

    func body(content: Content) -> some View {
        content
            .inspector(isPresented: Binding(get: { presente }, set: { if !$0 { chiudi() } })) {
                ContenutoIspettore()
                    .inspectorColumnWidth(min: larghezze.min, ideal: larghezze.ideale, max: larghezze.max)
            }
            .id(inRicerca ? "ricerca" : archivio.sezione.rawValue)
    }

    /// Le larghezze della colonna. Con la finestra al minimo (900 punti, anche a 125% perche' il
    /// minimo scala col testo) barra laterale + Inspector lasciano alla tabella quello che resta:
    /// con 320 di larghezza ideale restavano 380 punti e l'ultima colonna di Task e Archivio usciva
    /// a destra, sotto l'Inspector. Con 280 (260 in Archivio, che ha sei colonne) ne restano 420
    /// (440), e le colonne delle tabelle hanno minimi che ci stanno (Task.swift e Archivio.swift;
    /// la prova e' mac/Prove/controlli_sorgenti.py: ogni colonna costa ~18 punti di margine).
    private var larghezze: (min: CGFloat, ideale: CGFloat, max: CGFloat) {
        guard !inRicerca else { return (240, 280, 460) }
        switch archivio.sezione {
        case .social: return (280, 340, 480)
        case .memoria: return (280, 340, 480)
        case .archivio: return (240, 260, 460)
        default: return (240, 280, 460)
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
