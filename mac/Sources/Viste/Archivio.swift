// Archivio: le sessioni di Claude Code e di Codex (/api/sessions) in una Table ordinabile, e
// il registro degli eventi (/api/eventi) come seconda vista, scelta con un Picker nella barra
// degli strumenti. Stesso schema di Task.swift:
//   - i dati vengono dallo Store (@Environment(Archivio.self));
//   - la sessione scelta sta nello Store (sessioneScelta), cosi' la Ricerca e plancia:// possono
//     sceglierla; l'evento scelto, che nessun altro sceglie, sta qui;
//   - Table per l'elenco, Inspector a destra per il dettaglio, ContentUnavailableView per i
//     vuoti, font e colori di sistema, niente vetro fatto a mano.

import SwiftUI
import AppKit

// MARK: - le righe

/// Una sessione, con le chiavi che servono a ordinare (mai opzionali: la Table non ordina
/// gli opzionali).
private struct RigaSessioneArch: Identifiable, Hashable {
    let sessione: Sessione

    init(_ s: Sessione) { sessione = s }

    var id: String { sessione.identita }
    var titolo: String {
        let t = (sessione.title ?? "").trimmed
        if !t.isEmpty { return t }
        return (sessione.firstPrompt ?? sessione.prompt ?? "").trimmed
    }
    var quando: String { sessione.startedAt ?? "" }
    var agente: String { (sessione.agent ?? "claude").lowercased() }
    var progetto: String { sessione.progetto ?? "" }
    var messaggi: Int { (sessione.nUser ?? 0) + (sessione.nAssistant ?? 0) }
    /// In secondi; zero se la fine non c'e' o non viene dopo l'inizio.
    var durata: Double {
        guard let a = Tempo.data(sessione.startedAt), let b = Tempo.data(sessione.endedAt) else { return 0 }
        return max(0, b.timeIntervalSince(a))
    }
}

private struct RigaEventoArch: Identifiable, Hashable {
    let evento: EventoRegistro

    init(_ e: EventoRegistro) { evento = e }

    var id: String { evento.identita }
    var quando: String { evento.ts ?? "" }
    var tipo: String { evento.tipo ?? "" }
    var titolo: String { evento.titolo ?? "" }
    var progetto: String { evento.progetto ?? "" }
    var origine: String { evento.origine ?? "" }
}

private enum ModoArch: String, CaseIterable, Identifiable {
    case sessioni, registro
    var id: String { rawValue }
    @MainActor var titolo: String {
        switch self {
        case .sessioni: return tr("Sessioni", "Sessions")
        case .registro: return tr("Registro", "Log")
        }
    }
}

// MARK: - formati

@MainActor
private enum FormatoArch {
    private static var formattatori: [String: DateFormatter] = [:]

    private static func formattatore(_ modello: String) -> DateFormatter {
        let chiave = Lingua.condivisa.codice + modello
        if let f = formattatori[chiave] { return f }
        let f = DateFormatter()
        f.locale = Lingua.condivisa.locale
        f.setLocalizedDateFormatFromTemplate(modello)
        formattatori[chiave] = f
        return f
    }

    /// "29 set, 11:34"
    static func quando(_ s: String?) -> String {
        guard let d = Tempo.data(s) else { return "" }
        return formattatore("d MMM HH:mm").string(from: d)
    }

    /// "29 settembre 2026, 11:34"
    static func quandoEsteso(_ s: String?) -> String {
        guard let d = Tempo.data(s) else { return "" }
        return formattatore("d MMMM y HH:mm").string(from: d)
    }

    /// "45 s", "12 min", "1 h 05"; vuoto se zero.
    static func durata(_ secondi: Double) -> String {
        let s = Int(secondi.rounded())
        if s <= 0 { return "" }
        if s < 60 { return "\(s) s" }
        if s < 3600 { return "\(s / 60) min" }
        let m = (s % 3600) / 60
        return m == 0 ? "\(s / 3600) h" : "\(s / 3600) h \(String(format: "%02d", m))"
    }

    static func agente(_ a: String) -> String {
        switch a {
        case "claude": return "Claude"
        case "codex": return "Codex"
        default: return a.prefix(1).uppercased() + a.dropFirst()
        }
    }

    static func numero(_ n: Int?) -> String {
        guard let n = n else { return "" }
        return n.formatted(.number.notation(.compactName).locale(Lingua.condivisa.locale))
    }

    /// I modelli arrivano come testo JSON: ["claude-opus-5"].
    static func modelli(_ testo: String?) -> String {
        guard let d = testo?.data(using: .utf8),
              let a = try? JSONDecoder().decode([String].self, from: d) else { return testo ?? "" }
        return a.joined(separator: ", ")
    }

    /// Un valore JSON in una riga di testo, per l'Inspector del registro.
    static func descrivi(_ v: JSONValue) -> String {
        switch v {
        case .null: return ""
        case .bool, .numero, .testo: return v.testo ?? ""
        case .lista(let l): return l.map { descrivi($0) }.filter { !$0.isEmpty }.joined(separator: ", ")
        case .oggetto(let o):
            return o.keys.sorted().compactMap { k in
                let t = descrivi(o[k] ?? .null)
                return t.isEmpty ? nil : "\(k): \(t)"
            }.joined(separator: "; ")
        }
    }
}

// MARK: - la vista

struct VistaArchivio: View {
    @Environment(Archivio.self) private var archivio

    @State private var modo: ModoArch = .sessioni
    @State private var agente = ""                  // "" = tutti
    @State private var tipo = ""                    // "" = tutti
    @State private var ordineSessioni: [KeyPathComparator<RigaSessioneArch>] =
        [KeyPathComparator(\RigaSessioneArch.quando, order: .reverse)]
    @State private var ordineRegistro: [KeyPathComparator<RigaEventoArch>] =
        [KeyPathComparator(\RigaEventoArch.quando, order: .reverse)]
    @State private var eventoScelto: String?

    private var righeSessioni: [RigaSessioneArch] {
        let tutte = archivio.sessioni.map(RigaSessioneArch.init)
        let filtrate = agente.isEmpty ? tutte : tutte.filter { $0.agente == agente }
        return filtrate.sorted(using: ordineSessioni)
    }

    private var righeRegistro: [RigaEventoArch] {
        let tutte = (archivio.registro?.eventi ?? []).map(RigaEventoArch.init)
        let filtrate = tipo.isEmpty ? tutte : tutte.filter { $0.tipo == tipo }
        return filtrate.sorted(using: ordineRegistro)
    }

    private var tipiEvento: [String] {
        let dichiarati = archivio.registro?.stato?.tipi ?? []
        let visti = Set((archivio.registro?.eventi ?? []).compactMap { $0.tipo })
        return Array(Set(dichiarati).union(visti)).sorted()
    }

    var body: some View {
        Group {
            switch modo {
            case .sessioni: sessioni
            case .registro: registro
            }
        }
        // solo nelle istantanee con --registro: apre il registro invece delle sessioni
        .onAppear {
            if Istantanee.attive, CommandLine.arguments.contains("--registro") { modo = .registro }
        }
        .onChange(of: righeRegistro.first?.id, initial: true) { _, primo in
            if Istantanee.attive, CommandLine.arguments.contains("--registro"),
               eventoScelto == nil, let p = primo { eventoScelto = p }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Picker(tr("Vista", "View"), selection: $modo) {
                    ForEach(ModoArch.allCases) { Text($0.titolo).tag($0) }
                }
                .pickerStyle(.segmented)
            }
            ToolbarItem(placement: .automatic) {
                switch modo {
                case .sessioni:
                    Picker(tr("Agente", "Agent"), selection: $agente) {
                        Text(tr("Tutti gli agenti", "All agents")).tag("")
                        Text("Claude").tag("claude")
                        Text("Codex").tag("codex")
                    }
                    .pickerStyle(.menu)
                case .registro:
                    Picker(tr("Tipo", "Type"), selection: $tipo) {
                        Text(tr("Tutti i tipi", "All types")).tag("")
                        ForEach(tipiEvento, id: \.self) { Text($0).tag($0) }
                    }
                    .pickerStyle(.menu)
                }
            }
        }
    }

    // MARK: sessioni

    @ViewBuilder private var sessioni: some View {
        @Bindable var a = archivio
        let elenco = righeSessioni
        Group {
            if elenco.isEmpty {
                vuotoSessioni
            } else {
                Table(elenco, selection: $a.sessioneScelta, sortOrder: $ordineSessioni) {
                    TableColumn(tr("Quando", "When"), value: \.quando) { r in
                        Text(FormatoArch.quando(r.quando)).foregroundStyle(.secondary).lineLimit(1)
                    }
                    .width(min: 90, ideal: 110)
                    TableColumn(tr("Titolo", "Title"), value: \.titolo) { r in
                        Text(r.titolo).lineLimit(1)
                    }
                    .width(min: 200, ideal: 420)
                    TableColumn(tr("Progetto", "Project"), value: \.progetto) { r in
                        Text(r.progetto).foregroundStyle(.secondary).lineLimit(1)
                    }
                    .width(min: 90, ideal: 120)
                    TableColumn(tr("Agente", "Agent"), value: \.agente) { r in
                        Text(FormatoArch.agente(r.agente)).foregroundStyle(.secondary)
                    }
                    .width(min: 60, ideal: 70)
                    TableColumn(tr("Durata", "Length"), value: \.durata) { r in
                        Text(FormatoArch.durata(r.durata)).foregroundStyle(.secondary)
                    }
                    .width(min: 60, ideal: 70)
                    TableColumn(tr("Messaggi", "Messages"), value: \.messaggi) { r in
                        Text(r.messaggi.formatted()).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    .width(min: 70, ideal: 80)
                }
                .alternatingRowBackgrounds(.disabled)
            }
        }
        .inspector(isPresented: mostraSessione) {
            if let r = sessioneScelta {
                DettaglioSessioneArch(riga: r)
                    .inspectorColumnWidth(min: 260, ideal: 320, max: 460)
            }
        }
    }

    private var sessioneScelta: RigaSessioneArch? {
        guard let id = archivio.sessioneScelta else { return nil }
        return archivio.sessioni.first { $0.identita == id }.map(RigaSessioneArch.init)
    }

    private var mostraSessione: Binding<Bool> {
        Binding(get: { modo == .sessioni && sessioneScelta != nil },
                set: { if !$0 { archivio.sessioneScelta = nil } })
    }

    @ViewBuilder private var vuotoSessioni: some View {
        if archivio.sessioni.isEmpty {
            if !archivio.raggiungibile {
                nonRaggiungibile
            } else if archivio.ultimoAggiornamento == nil {
                ProgressView().controlSize(.small)
            } else {
                ContentUnavailableView(tr("Nessuna sessione", "No sessions"), systemImage: "archivebox")
            }
        } else {
            ContentUnavailableView(tr("Nessuna sessione", "No sessions"), systemImage: "line.3.horizontal.decrease.circle",
                                   description: Text(tr("Cambia il filtro sull'agente.", "Change the agent filter.")))
        }
    }

    // MARK: registro

    @ViewBuilder private var registro: some View {
        let elenco = righeRegistro
        Group {
            if elenco.isEmpty {
                vuotoRegistro
            } else {
                Table(elenco, selection: $eventoScelto, sortOrder: $ordineRegistro) {
                    TableColumn(tr("Quando", "When"), value: \.quando) { r in
                        Text(FormatoArch.quando(r.quando)).foregroundStyle(.secondary).lineLimit(1)
                    }
                    .width(min: 90, ideal: 110)
                    TableColumn(tr("Tipo", "Type"), value: \.tipo) { r in
                        Text(r.tipo).foregroundStyle(.secondary).lineLimit(1)
                    }
                    .width(min: 130, ideal: 200)
                    TableColumn(tr("Titolo", "Title"), value: \.titolo) { r in
                        Text(r.titolo).lineLimit(1)
                    }
                    .width(min: 200, ideal: 380)
                    TableColumn(tr("Progetto", "Project"), value: \.progetto) { r in
                        Text(r.progetto).foregroundStyle(.secondary).lineLimit(1)
                    }
                    .width(min: 90, ideal: 120)
                    TableColumn(tr("Origine", "Origin"), value: \.origine) { r in
                        Text(r.origine).foregroundStyle(.secondary).lineLimit(1)
                    }
                    .width(min: 70, ideal: 90)
                }
                .alternatingRowBackgrounds(.disabled)
            }
        }
        .inspector(isPresented: mostraEvento) {
            if let r = eventoCorrente {
                DettaglioEventoArch(riga: r)
                    .inspectorColumnWidth(min: 260, ideal: 320, max: 460)
            }
        }
        .task { if archivio.registro == nil { await archivio.carica(.archivio) } }
    }

    private var eventoCorrente: RigaEventoArch? {
        guard let id = eventoScelto else { return nil }
        return righeRegistro.first { $0.id == id }
    }

    private var mostraEvento: Binding<Bool> {
        Binding(get: { modo == .registro && eventoCorrente != nil },
                set: { if !$0 { eventoScelto = nil } })
    }

    @ViewBuilder private var vuotoRegistro: some View {
        if archivio.registro == nil {
            if archivio.raggiungibile {
                ProgressView().controlSize(.small)
            } else {
                nonRaggiungibile
            }
        } else if tipo.isEmpty {
            ContentUnavailableView(tr("Nessun evento", "No events"), systemImage: "list.bullet.rectangle")
        } else {
            ContentUnavailableView(tr("Nessun evento", "No events"), systemImage: "line.3.horizontal.decrease.circle",
                                   description: Text(tr("Cambia il filtro sul tipo.", "Change the type filter.")))
        }
    }

    private var nonRaggiungibile: some View {
        ContentUnavailableView(
            tr("Server non raggiungibile", "Server unreachable"),
            systemImage: "bolt.horizontal.circle",
            description: Text(tr("Appena risponde, l'archivio compare qui.",
                                 "The archive appears here as soon as it answers.")))
    }
}

// MARK: - il dettaglio di una sessione (Inspector)

private struct DettaglioSessioneArch: View {
    let riga: RigaSessioneArch
    @Environment(Archivio.self) private var archivio

    private var s: Sessione { riga.sessione }

    var body: some View {
        Form {
            Section {
                Text(riga.titolo).font(.headline).textSelection(.enabled)
                if let p = s.firstPrompt?.trimmed, !p.isEmpty, p != riga.titolo {
                    Text(p).font(.callout).foregroundStyle(.secondary).lineLimit(8).textSelection(.enabled)
                }
            }
            Section {
                LabeledContent(tr("Quando", "When"), value: FormatoArch.quandoEsteso(s.startedAt))
                if riga.durata > 0 { LabeledContent(tr("Durata", "Length"), value: FormatoArch.durata(riga.durata)) }
                LabeledContent(tr("Agente", "Agent"), value: FormatoArch.agente(riga.agente))
                if !riga.progetto.isEmpty { LabeledContent(tr("Progetto", "Project"), value: riga.progetto) }
                if let c = s.cwd, !c.isEmpty { LabeledContent(tr("Cartella", "Folder"), value: c) }
                if let b = s.gitBranch, !b.isEmpty { LabeledContent(tr("Ramo", "Branch"), value: b) }
            }
            Section {
                LabeledContent(tr("Messaggi", "Messages"), value: riga.messaggi.formatted())
                if let n = s.nTools, n > 0 { LabeledContent(tr("Strumenti", "Tools"), value: n.formatted()) }
                if s.inTokens != nil || s.outTokens != nil {
                    LabeledContent(tr("Token", "Tokens"),
                                   value: "\(FormatoArch.numero(s.inTokens)) / \(FormatoArch.numero(s.outTokens))")
                }
                let m = FormatoArch.modelli(s.models)
                if !m.isEmpty { LabeledContent(tr("Modelli", "Models"), value: m) }
            }
            Section {
                if let k = s.projectKey, !k.isEmpty {
                    Button { archivio.vai(.progetti, progetto: k) } label: {
                        Label(tr("Apri progetto", "Open project"), systemImage: "folder")
                    }
                }
                if let id = s.sessionId, !id.isEmpty {
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(id, forType: .string)
                    } label: {
                        Label(tr("Copia l'ID", "Copy ID"), systemImage: "doc.on.doc")
                    }
                }
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - il dettaglio di un evento (Inspector)

private struct DettaglioEventoArch: View {
    let riga: RigaEventoArch

    private var dati: [(String, String)] {
        guard case .oggetto(let o)? = riga.evento.dati else { return [] }
        return o.keys.sorted().compactMap { k in
            let t = FormatoArch.descrivi(o[k] ?? .null)
            return t.isEmpty ? nil : (k, t)
        }
    }

    var body: some View {
        Form {
            Section {
                Text(riga.titolo).font(.headline).textSelection(.enabled)
            }
            Section {
                LabeledContent(tr("Quando", "When"), value: FormatoArch.quandoEsteso(riga.quando))
                LabeledContent(tr("Tipo", "Type"), value: riga.tipo)
                if !riga.progetto.isEmpty { LabeledContent(tr("Progetto", "Project"), value: riga.progetto) }
                if !riga.origine.isEmpty { LabeledContent(tr("Origine", "Origin"), value: riga.origine) }
            }
            if !dati.isEmpty {
                Section {
                    ForEach(dati, id: \.0) { k, v in
                        LabeledContent(k, value: v)
                    }
                }
            }
        }
        .formStyle(.grouped)
    }
}
