// Memoria: i dati puri (tipi di fatto, un fatto, i filtri, e i dati uniti di schede e mappa).
//
// Niente viste qui dentro: il Core (Core/ArchivioDati.swift) tiene in cache `DatiMemoria`, quindi
// la prova del Core (tools/prova-mac.sh) compila questo file insieme al Core.

import SwiftUI
import AppKit

// MARK: - tipi di fatto

enum TipoMemoria: String, CaseIterable {
    case user, feedback, reference, project, altro

    init(_ testo: String?) {
        self = TipoMemoria(rawValue: (testo ?? "").lowercased()) ?? .altro
    }

    @MainActor var titolo: String {
        switch self {
        case .user: return tr("Chi sei", "About you")
        case .feedback: return tr("Preferenze", "Preferences")
        case .reference: return tr("Riferimenti", "References")
        case .project: return tr("Progetti", "Projects")
        case .altro: return tr("Altro", "Other")
        }
    }

    @MainActor var singolare: String {
        switch self {
        case .user: return tr("Chi sei", "About you")
        case .feedback: return tr("Preferenza", "Preference")
        case .reference: return tr("Riferimento", "Reference")
        case .project: return tr("Progetto", "Project")
        case .altro: return tr("Altro", "Other")
        }
    }

    var colore: Color {
        switch self {
        case .user: return .blue
        case .feedback: return .orange
        case .reference: return .green
        case .project: return .purple
        case .altro: return .gray
        }
    }
}

// MARK: - un fatto

struct FattoMemoria: Identifiable, Hashable {
    let nome: String
    let tipo: TipoMemoria
    let descrizione: String
    let aggiornata: String?
    let progetto: String?
    let progettoChiave: String?
    let peso: Int?
    let cartelle: [String]
    let percorso: String?
    let richiamabile: Bool?
    /// Dove il server ha messo il nodo nella sua mappa (0...1), per partire da una forma gia' buona.
    let x: Double?
    let y: Double?

    var id: String { nome }

    init(scheda: Scheda?, nodo: NodoMemoria?) {
        nome = scheda?.name ?? nodo?.nome ?? "?"
        tipo = TipoMemoria(scheda?.type ?? nodo?.tipo)
        descrizione = ((scheda?.description ?? nodo?.descrizione) ?? "").trimmed
        aggiornata = scheda?.updatedAt ?? nodo?.aggiornata
        progetto = scheda?.progetto
        progettoChiave = scheda?.projectKey
        peso = nodo?.peso
        cartelle = nodo?.dove ?? nodo?.cartelle ?? []
        percorso = nodo?.path ?? scheda?.path
        richiamabile = nodo?.richiamabile
        x = nodo?.x
        y = nodo?.y
    }
}

enum FiltroMemoria: String, CaseIterable, Identifiable {
    case tutte, dueCartelle, senzaLegami, linkRotti, quasiVuote, daScrivere
    var id: String { rawValue }

    @MainActor var titolo: String {
        switch self {
        case .tutte: return tr("Tutte", "All")
        case .dueCartelle: return tr("Doppie", "Duplicates")
        case .senzaLegami: return tr("Senza legami", "No links")
        case .linkRotti: return tr("Link rotti", "Broken links")
        case .quasiVuote: return tr("Quasi vuote", "Nearly empty")
        case .daScrivere: return tr("Da scrivere", "To write")
        }
    }

    var simbolo: String {
        switch self {
        case .tutte: return "brain"
        case .dueCartelle: return "doc.on.doc"
        case .senzaLegami: return "link.badge.plus"
        case .linkRotti: return "link"
        case .quasiVuote: return "text.alignleft"
        case .daScrivere: return "square.and.pencil"
        }
    }
}

// MARK: - i dati, calcolati una volta per ogni disegno

struct DatiMemoria {
    let fatti: [FattoMemoria]
    let perNome: [String: FattoMemoria]
    /// Legami in entrambe le direzioni, ordinati.
    let vicini: [String: [String]]
    /// Per ogni fatto, i legami che puntano a niente.
    let rotti: [String: [String]]
    let doppie: Set<String>
    let orfane: Set<String>
    let vuote: Set<String>
    let conRotti: Set<String>
    let daScrivere: [String]
    let richiamabili: Int
    let haMappa: Bool

    init(schede: [Scheda], mappa: MappaMemoria?) {
        var nodi: [String: NodoMemoria] = [:]
        for n in mappa?.nodi ?? [] { nodi[n.identita] = n }

        // una scheda per nome: se e' in due cartelle si tiene la piu' recente
        var perScheda: [String: Scheda] = [:]
        for s in schede {
            let k = s.identita
            if let v = perScheda[k], (v.updatedAt ?? "") >= (s.updatedAt ?? "") { continue }
            perScheda[k] = s
        }
        var elenco = perScheda.values.map { FattoMemoria(scheda: $0, nodo: nodi[$0.identita]) }
        for (k, n) in nodi where perScheda[k] == nil { elenco.append(FattoMemoria(scheda: nil, nodo: n)) }
        elenco.sort {
            let a = $0.aggiornata ?? "", b = $1.aggiornata ?? ""
            return a == b ? $0.nome < $1.nome : a > b
        }
        fatti = elenco
        var per: [String: FattoMemoria] = [:]
        for f in elenco { per[f.nome] = f }
        perNome = per

        var v: [String: Set<String>] = [:]
        if let archi = mappa?.archi {
            for a in archi {
                guard let da = a.da, let verso = a.a, da != verso, per[da] != nil, per[verso] != nil else { continue }
                v[da, default: []].insert(verso)
                v[verso, default: []].insert(da)
            }
        } else {
            for s in perScheda.values {
                guard let da = s.name else { continue }
                for verso in s.legami where verso != da && per[verso] != nil {
                    v[da, default: []].insert(verso)
                    v[verso, default: []].insert(da)
                }
            }
        }
        vicini = v.mapValues { $0.sorted() }

        let d = mappa?.diagnosi
        var r: [String: [String]] = [:]
        for x in d?.rotti ?? [] {
            if let da = x.da, let verso = x.verso { r[da, default: []].append(verso) }
        }
        rotti = r
        conRotti = Set(r.keys)
        doppie = Set((d?.doppie ?? []).compactMap { $0.nome })
        orfane = Set(d?.orfane ?? [])
        vuote = Set(d?.vuote ?? [])
        daScrivere = d?.daScrivere ?? []
        richiamabili = d?.richiamabili ?? elenco.filter { $0.richiamabile == true }.count
        haMappa = mappa != nil
    }

    func insieme(_ f: FiltroMemoria) -> Set<String>? {
        switch f {
        case .tutte, .daScrivere: return nil
        case .dueCartelle: return doppie
        case .senzaLegami: return orfane
        case .linkRotti: return conRotti
        case .quasiVuote: return vuote
        }
    }

    func conteggio(_ f: FiltroMemoria) -> Int {
        switch f {
        case .tutte: return fatti.count
        case .daScrivere: return daScrivere.count
        default: return insieme(f)?.count ?? 0
        }
    }
}

func accorcia(_ s: String, _ massimo: Int = 26) -> String {
    guard s.count > massimo else { return s }
    let testa = (massimo - 1) / 2 + 1
    let coda = massimo - 1 - testa
    return String(s.prefix(testa)) + "…" + String(s.suffix(coda))
}

