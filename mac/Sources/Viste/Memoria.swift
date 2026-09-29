// Memoria: i fatti che Claude si porta dietro da una sessione all'altra.
//
//   - a sinistra un elenco raggruppato per tipo, con un filtro di testo e un menu per
//     i problemi (in due cartelle, senza legami, link rotti, quasi vuote, da scrivere);
//   - a destra l'Inspector col fatto per intero, la cartella da cui viene e i legami
//     cliccabili;
//   - il grafo non e' la vista principale: e' il modo "Vicinato" (segmentato nella barra
//     degli strumenti), che mette il fatto scelto al centro e i suoi legami su due
//     livelli, al massimo una quindicina di nodi, con un layout radiale calcolato in un
//     colpo solo (niente simulazione di forze);
//   - "Prova il richiamo" e' un pannello a comparsa nella barra degli strumenti.
//
// I dati vengono dallo Store (schede e mappa). Il corpo di un fatto si chiede al server
// solo quando lo si sceglie. Questo file non tocca il Core: i tipi e le chiamate che gli
// servono stanno qui sotto.

import SwiftUI
import AppKit

// MARK: - tipi di fatto

private enum TipoMemoria: String, CaseIterable {
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

private struct FattoMemoria: Identifiable, Hashable {
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
    }
}

private enum FiltroMemoria: String, CaseIterable, Identifiable {
    case tutte, dueCartelle, senzaLegami, linkRotti, quasiVuote, daScrivere
    var id: String { rawValue }

    @MainActor var titolo: String {
        switch self {
        case .tutte: return tr("Tutte", "All")
        case .dueCartelle: return tr("In due cartelle", "In two folders")
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

private enum ModoMemoria: String, CaseIterable, Identifiable {
    case elenco, vicinato
    var id: String { rawValue }
    @MainActor var titolo: String {
        self == .elenco ? tr("Elenco", "List") : tr("Vicinato", "Neighbours")
    }
}

// MARK: - i dati, calcolati una volta per ogni disegno

private struct DatiMemoria {
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

private func semplice(_ s: String) -> String {
    s.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
}

private func accorcia(_ s: String, _ massimo: Int = 26) -> String {
    guard s.count > massimo else { return s }
    let testa = (massimo - 1) / 2 + 1
    let coda = massimo - 1 - testa
    return String(s.prefix(testa)) + "…" + String(s.suffix(coda))
}

// MARK: - la vista

struct VistaMemoria: View {
    @Environment(Archivio.self) private var archivio
    @AppStorage("memoriaModo") private var modoGuardato = ModoMemoria.elenco.rawValue

    @State private var filtro: FiltroMemoria = .tutte
    @State private var testo = ""
    @State private var provaAperta = false

    private var modo: ModoMemoria { ModoMemoria(rawValue: modoGuardato) ?? .elenco }

    var body: some View {
        @Bindable var a = archivio
        let dati = DatiMemoria(schede: archivio.schede, mappa: archivio.mappa)
        let modoBinding = Binding<ModoMemoria>(
            get: { modo }, set: { modoGuardato = $0.rawValue })
        let scelto = archivio.memoriaScelta.flatMap { dati.perNome[$0] }

        Group {
            if dati.fatti.isEmpty {
                vuoto
            } else if modo == .vicinato {
                if let centro = scelto {
                    PannelloVicinato(centro: centro, dati: dati)
                } else {
                    ContentUnavailableView(tr("Scegli un fatto", "Pick a fact"),
                                           systemImage: "brain")
                }
            } else {
                elenco(dati)
            }
        }
        .inspector(isPresented: Binding(
            get: { scelto != nil },
            set: { if !$0 { archivio.memoriaScelta = nil } })) {
            if let f = scelto {
                DettaglioMemoria(fatto: f, dati: dati)
                    .inspectorColumnWidth(min: 280, ideal: 340, max: 480)
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Picker(tr("Modo", "Mode"), selection: modoBinding) {
                    ForEach(ModoMemoria.allCases) { Text($0.titolo).tag($0) }
                }
                .pickerStyle(.segmented)
                .help(tr("Elenco o vicinato del fatto scelto", "List, or the neighbourhood of the chosen fact"))
            }
            ToolbarItem(placement: .primaryAction) {
                Button { provaAperta.toggle() } label: {
                    Label(tr("Prova il richiamo", "Test recall"), systemImage: "sparkle.magnifyingglass")
                }
                .help(tr("Scrivi una frase e guarda cosa ti direbbe la memoria",
                         "Write a sentence and see what memory would tell you"))
                .popover(isPresented: $provaAperta, arrowEdge: .bottom) { ProvaRichiamo() }
            }
        }
        .task(id: dati.fatti.count) { assicuraScelta(dati) }
        .onChange(of: modoGuardato) { assicuraScelta(dati) }
    }

    /// Il vicinato ha bisogno di un fatto al centro: se non c'e', si parte dal primo.
    private func assicuraScelta(_ dati: DatiMemoria) {
        guard modo == .vicinato else { return }
        let gia = archivio.memoriaScelta.flatMap { dati.perNome[$0] }
        if gia == nil, let primo = visibili(dati).first ?? dati.fatti.first {
            archivio.memoriaScelta = primo.nome
        }
    }

    // MARK: elenco

    private func visibili(_ dati: DatiMemoria) -> [FattoMemoria] {
        let insieme = dati.insieme(filtro)
        let q = semplice(testo.trimmed)
        return dati.fatti.filter { f in
            (insieme == nil || insieme!.contains(f.nome))
                && (q.isEmpty || semplice(f.nome).contains(q) || semplice(f.descrizione).contains(q))
        }
    }

    private func gruppi(_ fatti: [FattoMemoria]) -> [(TipoMemoria, [FattoMemoria])] {
        TipoMemoria.allCases.compactMap { t in
            let v = fatti.filter { $0.tipo == t }
            return v.isEmpty ? nil : (t, v)
        }
    }

    private func elenco(_ dati: DatiMemoria) -> some View {
        @Bindable var a = archivio
        let fatti = visibili(dati)
        return VStack(spacing: 0) {
            barraFiltro(dati)
            Divider()
            List(selection: $a.memoriaScelta) {
                if filtro == .daScrivere {
                    Section {
                        ForEach(dati.daScrivere, id: \.self) { nome in
                            Label(nome, systemImage: "square.and.pencil")
                        }
                    } footer: {
                        Text(tr("Altre memorie le citano, ma nessuno le ha scritte.",
                                "Other facts mention them, but nobody wrote them."))
                    }
                } else if fatti.isEmpty {
                    Section { corpoVuoto }
                } else {
                    ForEach(gruppi(fatti), id: \.0) { (tipo, voci) in
                        Section {
                            ForEach(voci) { f in
                                RigaMemoria(fatto: f).tag(f.nome)
                            }
                        } header: {
                            HStack {
                                Text(tipo.titolo)
                                Spacer()
                                Text("\(voci.count)").foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                if filtro == .tutte && testo.trimmed.isEmpty {
                    let problemi = FiltroMemoria.allCases.filter { $0 != .tutte && dati.conteggio($0) > 0 }
                    if !problemi.isEmpty {
                        Section(tr("Da sistemare", "To fix")) {
                            ForEach(problemi) { p in rigaProblema(p, dati) }
                        }
                    }
                }
            }
            .listStyle(.inset)
            .alternatingRowBackgrounds(.disabled)
            Divider()
            riepilogo(dati)
        }
    }

    private func barraFiltro(_ dati: DatiMemoria) -> some View {
        HStack(spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "line.3.horizontal.decrease").foregroundStyle(.secondary)
                TextField(tr("Filtra", "Filter"), text: $testo)
                    .textFieldStyle(.plain)
                if !testo.isEmpty {
                    Button { testo = "" } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(tr("Cancella il filtro", "Clear the filter"))
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(.quaternary, in: .rect(cornerRadius: 8))

            Picker(tr("Mostra", "Show"), selection: $filtro) {
                ForEach(FiltroMemoria.allCases) { f in
                    if f == .tutte || dati.conteggio(f) > 0 {
                        Text(f == .tutte ? f.titolo : "\(f.titolo) (\(dati.conteggio(f)))").tag(f)
                    }
                }
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .fixedSize()
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    private func rigaProblema(_ p: FiltroMemoria, _ dati: DatiMemoria) -> some View {
        Button { filtro = p } label: {
            HStack {
                Label(p.titolo, systemImage: p.simbolo)
                Spacer()
                Text("\(dati.conteggio(p))").foregroundStyle(.secondary)
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func riepilogo(_ dati: DatiMemoria) -> some View {
        Text(tr("\(dati.fatti.count) fatti, \(dati.richiamabili) ritrovabili da ogni cartella",
                "\(dati.fatti.count) facts, \(dati.richiamabili) found from any folder"))
            .font(.caption)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
    }

    @ViewBuilder private var corpoVuoto: some View {
        if filtro == .tutte {
            ContentUnavailableView.search(text: testo)
        } else {
            ContentUnavailableView(tr("Niente da sistemare", "Nothing to fix"),
                                   systemImage: "checkmark.circle")
        }
    }

    @ViewBuilder private var vuoto: some View {
        if archivio.schede.isEmpty && archivio.mappa == nil {
            if archivio.raggiungibile {
                ProgressView().controlSize(.small)
            } else {
                ContentUnavailableView(
                    tr("Server non raggiungibile", "Server unreachable"),
                    systemImage: "bolt.horizontal.circle",
                    description: Text(tr("Appena risponde, i fatti compaiono qui.",
                                         "Facts appear here as soon as it answers.")))
            }
        } else {
            ContentUnavailableView(
                tr("Nessun fatto", "No facts"),
                systemImage: "brain",
                description: Text(tr("Claude Code li scrive mentre lavori.",
                                     "Claude Code writes them as you work.")))
        }
    }
}

// MARK: - una riga dell'elenco

private struct RigaMemoria: View {
    let fatto: FattoMemoria

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: "circle.fill")
                .font(.caption2)
                .foregroundStyle(fatto.tipo.colore)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(fatto.nome).lineLimit(1)
                if !fatto.descrizione.isEmpty {
                    Text(fatto.descrizione)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 8)
            if let g = fatto.aggiornata, !g.isEmpty {
                Text(Tempo.giorno(g)).font(.caption).foregroundStyle(.tertiary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - il fatto per intero (Inspector)

private struct DettaglioMemoria: View {
    let fatto: FattoMemoria
    let dati: DatiMemoria
    @Environment(Archivio.self) private var archivio

    @State private var corpo: String?
    @State private var carico = false

    var body: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    Label {
                        Text(fatto.tipo.singolare)
                    } icon: {
                        Image(systemName: "circle.fill").foregroundStyle(fatto.tipo.colore)
                    }
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    Text(fatto.nome).font(.headline).textSelection(.enabled)
                    if !fatto.descrizione.isEmpty {
                        Text(fatto.descrizione).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            Section {
                if let c = corpo, !c.isEmpty {
                    TestoMemoria(testo: c, noti: Set(dati.perNome.keys))
                } else if carico {
                    ProgressView().controlSize(.small)
                } else {
                    Text(tr("Nessun testo oltre alla descrizione.", "No text beyond the description."))
                        .font(.callout).foregroundStyle(.secondary)
                }
            }

            Section {
                if let g = fatto.aggiornata, !g.isEmpty {
                    LabeledContent(tr("Aggiornata", "Updated"), value: Tempo.relativo(g))
                }
                if let p = fatto.progetto, !p.isEmpty {
                    LabeledContent(tr("Progetto", "Project")) {
                        if let k = fatto.progettoChiave, !k.isEmpty {
                            Button(p) { archivio.vai(.progetti, progetto: k) }.buttonStyle(.link)
                        } else {
                            Text(p)
                        }
                    }
                }
                if !fatto.cartelle.isEmpty {
                    LabeledContent(tr("Cartella", "Folder"), value: fatto.cartelle.joined(separator: ", "))
                }
                if let r = ritrovabile {
                    LabeledContent(tr("Ritrovabile", "Recall"), value: r)
                }
                if dati.doppie.contains(fatto.nome) {
                    Label(tr("Esiste in due cartelle: ne basta una.", "It exists in two folders: one is enough."),
                          systemImage: "doc.on.doc")
                        .font(.callout).foregroundStyle(.secondary)
                }
            }

            Section(tr("Legami", "Links")) {
                let vicini = dati.vicini[fatto.nome] ?? []
                let rotti = dati.rotti[fatto.nome] ?? []
                if vicini.isEmpty && rotti.isEmpty {
                    Text(tr("Nessun legame.", "No links."))
                        .font(.callout).foregroundStyle(.secondary)
                }
                ForEach(vicini, id: \.self) { nome in
                    Button { archivio.memoriaScelta = nome } label: {
                        Label {
                            Text(nome)
                        } icon: {
                            Image(systemName: "circle.fill")
                                .foregroundStyle(dati.perNome[nome]?.tipo.colore ?? .gray)
                        }
                    }
                    .buttonStyle(.link)
                }
                ForEach(rotti, id: \.self) { nome in
                    Label {
                        Text("\(nome) · \(tr("non esiste", "missing"))")
                    } icon: {
                        Image(systemName: "exclamationmark.triangle")
                    }
                    .font(.callout)
                    .foregroundStyle(.secondary)
                }
            }

            if let p = fatto.percorso, FileManager.default.fileExists(atPath: p) {
                Section {
                    Button {
                        NSWorkspace.shared.selectFile(p, inFileViewerRootedAtPath: "")
                    } label: {
                        Label(tr("Mostra nel Finder", "Show in Finder"), systemImage: "folder")
                    }
                }
            }
        }
        .formStyle(.grouped)
        .environment(\.openURL, OpenURLAction { url in
            guard url.scheme == "plancia-memoria",
                  let nome = String(url.absoluteString.dropFirst("plancia-memoria:".count)).removingPercentEncoding,
                  dati.perNome[nome] != nil else { return .discarded }
            archivio.memoriaScelta = nome
            return .handled
        })
        .task(id: fatto.nome) { await caricaCorpo() }
    }

    private var ritrovabile: String? {
        guard dati.haMappa else { return nil }
        if fatto.richiamabile == true { return tr("sì, da ogni cartella", "yes, from any folder") }
        if fatto.tipo == .project { return tr("no, solo nel suo progetto", "no, only in its project") }
        if dati.vuote.contains(fatto.nome) { return tr("no, troppo corta", "no, too short") }
        return tr("no", "no")
    }

    private func caricaCorpo() async {
        corpo = nil
        carico = true
        defer { carico = false }
        let nome = fatto.nome
        let s = try? await archivio.cliente.ottieni(Scheda.self, "/api/knowledge",
                                                    query: ["name": nome],
                                                    compartimento: archivio.compartimento)
        guard !Task.isCancelled else { return }
        corpo = Self.pulisci(s?.body ?? "", nome: nome, descrizione: fatto.descrizione)
    }

    /// Toglie l'intestazione tecnica (frontmatter, titolo uguale al nome, descrizione
    /// ripetuta): sono gia' scritti sopra.
    static func pulisci(_ testo: String, nome: String, descrizione: String) -> String {
        var righe = testo.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n")
        if righe.first?.trimmed == "---", let fine = righe.dropFirst().firstIndex(where: { $0.trimmed == "---" }) {
            righe.removeSubrange(0...fine)
        }
        func salta() { while righe.first?.trimmed.isEmpty == true { righe.removeFirst() } }
        salta()
        if let p = righe.first, p.hasPrefix("#"), String(p.drop(while: { $0 == "#" })).trimmed == nome {
            righe.removeFirst(); salta()
        }
        if !descrizione.isEmpty, let p = righe.first, p.trimmed == descrizione {
            righe.removeFirst(); salta()
        }
        return righe.joined(separator: "\n").trimmed
    }
}

// MARK: - il testo di un fatto

private struct TestoMemoria: View {
    let testo: String
    let noti: Set<String>

    private enum Blocco { case titolo(String), voce(String), paragrafo(String) }

    private var blocchi: [Blocco] {
        var fuori: [Blocco] = []
        var corrente: [String] = []
        func chiudi() {
            if !corrente.isEmpty { fuori.append(.paragrafo(corrente.joined(separator: " "))); corrente = [] }
        }
        for riga in testo.components(separatedBy: "\n") {
            let r = riga.trimmed
            if r.isEmpty { chiudi(); continue }
            if r.hasPrefix("#") {
                chiudi()
                fuori.append(.titolo(String(r.drop(while: { $0 == "#" })).trimmed))
            } else if r.hasPrefix("- ") || r.hasPrefix("* ") {
                chiudi()
                fuori.append(.voce(String(r.dropFirst(2))))
            } else {
                corrente.append(r)
            }
        }
        chiudi()
        return fuori
    }

    /// Markdown in linea; i [[legami]] a fatti che esistono diventano link cliccabili.
    private func inLinea(_ s: String) -> AttributedString {
        var t = s
        if let re = try? NSRegularExpression(pattern: "\\[\\[([^\\]]+)\\]\\]") {
            let ns = t as NSString
            var risultato = ""
            var ultimo = 0
            for m in re.matches(in: t, range: NSRange(location: 0, length: ns.length)) {
                risultato += ns.substring(with: NSRange(location: ultimo, length: m.range.location - ultimo))
                let nome = ns.substring(with: m.range(at: 1))
                if noti.contains(nome), let enc = nome.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) {
                    risultato += "[\(nome)](plancia-memoria:\(enc))"
                } else {
                    risultato += nome
                }
                ultimo = m.range.location + m.range.length
            }
            risultato += ns.substring(from: ultimo)
            t = risultato
        }
        let opzioni = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: t, options: opzioni)) ?? AttributedString(t)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(blocchi.enumerated()), id: \.offset) { _, b in
                switch b {
                case .titolo(let s):
                    Text(inLinea(s)).font(.subheadline.weight(.semibold))
                case .voce(let s):
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("•").foregroundStyle(.secondary)
                        Text(inLinea(s))
                    }
                    .font(.callout)
                case .paragrafo(let s):
                    Text(inLinea(s)).font(.callout)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
    }
}

// MARK: - Vicinato: il grafo radiale

/// Il fatto al centro, i suoi legami su un primo anello, i legami di questi su un
/// secondo. Le posizioni sono angoli, calcolati qui in un colpo solo: niente iterazioni.
private struct Vicinato {
    struct Nodo {
        let nome: String
        let tipo: TipoMemoria
        let livello: Int          // 0 centro, 1, 2
        let angolo: Double
        let grado: Int
    }

    var nodi: [Nodo] = []
    /// (da, a, struttura): struttura = i legami che formano l'albero, gli altri sono
    /// disegnati piu' sottili.
    var archi: [(Int, Int, Bool)] = []
    var omessi = 0

    static let totaleMassimo = 15

    init(centro: String, dati: DatiMemoria, livelli: Int) {
        func nodo(_ nome: String, _ livello: Int, _ angolo: Double) -> Nodo {
            Nodo(nome: nome, tipo: dati.perNome[nome]?.tipo ?? .altro, livello: livello,
                 angolo: angolo, grado: dati.vicini[nome]?.count ?? 0)
        }
        nodi = [nodo(centro, 0, 0)]

        let primi = dati.vicini[centro] ?? []
        // i piu' collegati restano, gli altri si contano
        let tenuti = primi
            .sorted { (dati.vicini[$0]?.count ?? 0, $1) > (dati.vicini[$1]?.count ?? 0, $0) }
            .prefix(livelli == 1 ? Vicinato.totaleMassimo - 1 : 8)
        omessi = primi.count - tenuti.count
        // in cerchio l'ordine e' alfabetico: un layout che non cambia da un disegno all'altro
        let anello1 = tenuti.sorted()
        let n1 = max(anello1.count, 1)
        let passo = 2 * Double.pi / Double(n1)
        for (i, nome) in anello1.enumerated() {
            nodi.append(nodo(nome, 1, -Double.pi / 2 + passo * Double(i)))
            archi.append((0, i + 1, true))
        }

        if livelli >= 2 && !anello1.isEmpty {
            let presenti = Set(anello1 + [centro])
            var assegnati = Set<String>()
            var figli: [[String]] = Array(repeating: [], count: anello1.count)
            let candidati: [[String]] = anello1.map { p in
                (dati.vicini[p] ?? []).filter { !presenti.contains($0) }
                    .sorted { (dati.vicini[$0]?.count ?? 0, $1) > (dati.vicini[$1]?.count ?? 0, $0) }
            }
            var posto = Vicinato.totaleMassimo - nodi.count
            var giro = 0
            while posto > 0 && giro < 8 {
                var mosso = false
                for (i, lista) in candidati.enumerated() where posto > 0 {
                    guard giro < lista.count else { continue }
                    let nome = lista[giro]
                    if assegnati.contains(nome) { continue }
                    assegnati.insert(nome)
                    figli[i].append(nome)
                    posto -= 1
                    mosso = true
                }
                if !mosso && giro >= 8 { break }
                giro += 1
            }
            for (i, fs) in figli.enumerated() where !fs.isEmpty {
                let k = fs.count
                let passoFiglio = min(0.34, passo * 0.8 / Double(k))
                for (j, nome) in fs.enumerated() {
                    let a = nodi[i + 1].angolo + (Double(j) - Double(k - 1) / 2) * passoFiglio
                    nodi.append(nodo(nome, 2, a))
                    archi.append((i + 1, nodi.count - 1, true))
                }
            }
        }

        // gli altri legami che ci sono comunque fra i nodi mostrati
        let indice = Dictionary(uniqueKeysWithValues: nodi.enumerated().map { ($1.nome, $0) })
        var struttura = Set<[Int]>()
        for (a, b, _) in archi { struttura.insert([min(a, b), max(a, b)]) }
        for (i, n) in nodi.enumerated() {
            for v in dati.vicini[n.nome] ?? [] {
                guard let j = indice[v], j > i, !struttura.contains([i, j]) else { continue }
                archi.append((i, j, false))
            }
        }
    }
}

/// Dove cade ogni nodo e la sua etichetta, per una data grandezza del disegno.
private struct Geometria {
    var centri: [CGPoint] = []
    var raggi: [CGFloat] = []
    var etichette: [CGRect] = []

    static func font(_ livello: Int) -> NSFont {
        switch livello {
        case 0: return .systemFont(ofSize: NSFont.preferredFont(forTextStyle: .body).pointSize, weight: .semibold)
        case 1: return .preferredFont(forTextStyle: .callout)
        default: return .preferredFont(forTextStyle: .subheadline)
        }
    }

    static func raggio(_ livello: Int) -> CGFloat {
        switch livello {
        case 0: return 18
        case 1: return 11
        default: return 8
        }
    }

    init(_ v: Vicinato, in size: CGSize) {
        let c = CGPoint(x: size.width / 2, y: size.height / 2)
        let larghezze: [CGFloat] = v.nodi.map {
            (accorcia($0.nome) as NSString).size(withAttributes: [.font: Geometria.font($0.livello)]).width + 12
        }
        // il secondo anello lascia sui lati lo spazio per la sua etichetta piu' larga
        let piuLarga = v.nodi.enumerated().filter { $0.element.livello == 2 }.map { larghezze[$0.offset] }.max() ?? 0
        let margineX = max(piuLarga + 28, 90)
        let rx2 = max(size.width / 2 - margineX, 80)
        let ry2 = max(size.height / 2 - 44, 80)
        let due = v.nodi.contains { $0.livello == 2 }
        let f1: CGFloat = due ? 0.5 : 0.85

        for (i, n) in v.nodi.enumerated() {
            let r = Geometria.raggio(n.livello)
            let p: CGPoint
            switch n.livello {
            case 0: p = c
            case 1: p = CGPoint(x: c.x + CGFloat(cos(n.angolo)) * rx2 * f1, y: c.y + CGFloat(sin(n.angolo)) * ry2 * f1)
            default: p = CGPoint(x: c.x + CGFloat(cos(n.angolo)) * rx2, y: c.y + CGFloat(sin(n.angolo)) * ry2)
            }
            centri.append(p)
            raggi.append(r)

            let alt = Geometria.font(n.livello).boundingRectForFont.height + 4
            let w = larghezze[i]
            var rect: CGRect
            if n.livello == 0 {
                rect = CGRect(x: p.x - w / 2, y: p.y + r + 5, width: w, height: alt)
            } else {
                let cx = CGFloat(cos(n.angolo)), sy = CGFloat(sin(n.angolo))
                if cx > 0.35 {
                    rect = CGRect(x: p.x + r + 4, y: p.y - alt / 2, width: w, height: alt)
                } else if cx < -0.35 {
                    rect = CGRect(x: p.x - r - 4 - w, y: p.y - alt / 2, width: w, height: alt)
                } else if sy > 0 {
                    rect = CGRect(x: p.x - w / 2, y: p.y + r + 3, width: w, height: alt)
                } else {
                    rect = CGRect(x: p.x - w / 2, y: p.y - r - 3 - alt, width: w, height: alt)
                }
            }
            // mai fuori dal disegno
            rect.origin.x = min(max(rect.origin.x, 6), max(size.width - rect.width - 6, 6))
            rect.origin.y = min(max(rect.origin.y, 6), max(size.height - rect.height - 6, 6))
            etichette.append(rect)
        }
    }

    /// Il nodo sotto un punto: sul cerchio o sull'etichetta.
    func nodo(in p: CGPoint) -> Int? {
        var migliore: (Int, CGFloat)?
        for i in centri.indices {
            let d = hypot(p.x - centri[i].x, p.y - centri[i].y)
            let dentro = d <= raggi[i] + 8 || etichette[i].insetBy(dx: -3, dy: -3).contains(p)
            if dentro, migliore == nil || d < migliore!.1 { migliore = (i, d) }
        }
        return migliore?.0
    }
}

private struct PannelloVicinato: View {
    let centro: FattoMemoria
    let dati: DatiMemoria
    @Environment(Archivio.self) private var archivio

    @State private var livelli = 2
    @State private var sotto: Int?

    var body: some View {
        let v = Vicinato(centro: centro.nome, dati: dati, livelli: livelli)
        GeometryReader { geo in
            let g = Geometria(v, in: geo.size)
            ZStack {
                Canvas { contesto, _ in disegna(&contesto, v, g) }
                    .contentShape(Rectangle())
                    .onTapGesture(count: 1, coordinateSpace: .local) { p in
                        if let i = g.nodo(in: p), i > 0 { archivio.memoriaScelta = v.nodi[i].nome }
                    }
                    .onContinuousHover { fase in
                        switch fase {
                        case .active(let p):
                            let i = g.nodo(in: p)
                            let nuovo = (i == 0) ? nil : i
                            if nuovo != sotto { sotto = nuovo }
                        case .ended:
                            sotto = nil
                        }
                    }
                    .pointerStyle(sotto != nil ? .link : .default)
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(tr("Vicinato di \(centro.nome)", "Neighbourhood of \(centro.nome)"))
                    .accessibilityChildren {
                        ForEach(Array(v.nodi.enumerated().dropFirst()), id: \.offset) { _, n in
                            Button(n.nome) { archivio.memoriaScelta = n.nome }
                        }
                    }

                if v.nodi.count == 1 {
                    Text(tr("Nessun legame", "No links"))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .position(x: geo.size.width / 2, y: geo.size.height / 2 + 64)
                }
            }
            .overlay(alignment: .bottomLeading) { legenda(v).padding() }
            .overlay(alignment: .bottomTrailing) { controllo(v).padding() }
        }
    }

    // MARK: disegno

    private func disegna(_ c: inout GraphicsContext, _ v: Vicinato, _ g: Geometria) {
        // i legami prima, cosi' i nodi e le etichette ci stanno sopra
        for (a, b, struttura) in v.archi {
            var p = Path()
            p.move(to: g.centri[a])
            p.addLine(to: g.centri[b])
            let evidenziato = sotto == a || sotto == b
            c.stroke(p, with: .color(.primary.opacity(evidenziato ? 0.55 : (struttura ? 0.28 : 0.09))),
                     lineWidth: evidenziato ? 1.6 : (struttura ? 1.2 : 0.8))
        }

        // i nodi
        for (i, n) in v.nodi.enumerated() {
            let r = g.raggi[i] + (sotto == i ? 2 : 0)
            let cerchio = Path(ellipseIn: CGRect(x: g.centri[i].x - r, y: g.centri[i].y - r,
                                                  width: 2 * r, height: 2 * r))
            c.fill(cerchio, with: .color(n.tipo.colore))
            c.stroke(cerchio, with: .style(.background), lineWidth: 2)
            if n.livello == 0 {
                let e = r + 4
                let alone = Path(ellipseIn: CGRect(x: g.centri[i].x - e, y: g.centri[i].y - e,
                                                    width: 2 * e, height: 2 * e))
                c.stroke(alone, with: .color(.accentColor), lineWidth: 2)
            }
        }

        // le etichette, su una targhetta dello sfondo: i legami che ci passano sotto
        // non le rendono illeggibili
        for (i, n) in v.nodi.enumerated() {
            let r = g.etichette[i]
            let attivo = n.livello == 0 || sotto == i
            let chip = Path(roundedRect: r.insetBy(dx: 1, dy: 1), cornerRadius: 5)
            c.fill(chip, with: .style(.background.opacity(0.85)))
            var testo = Text(accorcia(n.nome))
            switch n.livello {
            case 0: testo = testo.font(.body.weight(.semibold))
            case 1: testo = testo.font(.callout)
            default: testo = testo.font(.subheadline)
            }
            testo = testo.foregroundColor(attivo || n.livello == 1 ? .primary : .secondary)
            c.draw(c.resolve(testo), at: CGPoint(x: r.midX, y: r.midY), anchor: .center)
        }
    }

    // MARK: pezzi sopra il disegno

    private func legenda(_ v: Vicinato) -> some View {
        let presenti = TipoMemoria.allCases.filter { t in v.nodi.contains { $0.tipo == t } }
        return VStack(alignment: .leading, spacing: 4) {
            ForEach(presenti, id: \.self) { t in
                Label {
                    Text(t.titolo)
                } icon: {
                    Image(systemName: "circle.fill").foregroundStyle(t.colore)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            if v.omessi > 0 {
                Text(tr("e altri \(v.omessi) legami", "and \(v.omessi) more links"))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    // Sta sul disegno, non sul contenuto di una lista: un controllo standard, senza vetro fatto a mano.
    private func controllo(_ v: Vicinato) -> some View {
        Picker(tr("Livelli", "Levels"), selection: $livelli) {
            Text(tr("1 livello", "1 level")).tag(1)
            Text(tr("2 livelli", "2 levels")).tag(2)
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .fixedSize()
    }
}

// MARK: - prova del richiamo

private struct ProvaRichiamo: View {
    @Environment(Archivio.self) private var archivio
    @Environment(\.dismiss) private var dismiss

    @State private var frase = ""
    @State private var esito: ProvaMemoria?
    @State private var lavora = false
    @State private var errore: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            TextField(tr("Una frase, come la scriveresti a Claude", "A sentence, as you would write it to Claude"),
                      text: $frase)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel(tr("Frase da provare", "Sentence to test"))
            risultato
        }
        .padding()
        .frame(width: 400)
        .task(id: frase) { await chiedi() }
    }

    @ViewBuilder private var risultato: some View {
        if frase.trimmed.isEmpty {
            Text(tr("Scrivi una frase e guarda cosa ti direbbe la memoria.",
                    "Write a sentence and see what memory would tell you."))
                .font(.callout).foregroundStyle(.secondary)
        } else if let e = errore {
            Text(e).font(.callout).foregroundStyle(.red)
        } else if let r = esito {
            if r.corta == true {
                Text(tr("Servono almeno due parole.", "At least two words."))
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                let presi = r.presi ?? []
                let scartati = r.scartati ?? []
                if presi.isEmpty {
                    ContentUnavailableView(tr("Non ti direbbe niente", "It would say nothing"),
                                           systemImage: "quote.bubble",
                                           description: Text(tr("Nessun fatto supera la soglia.",
                                                                "No fact passes the threshold.")))
                } else {
                    gruppo(tr("Te la direbbe", "It would tell you"), presi, spento: false)
                }
                if !scartati.isEmpty {
                    gruppo(tr("In gara, ma sotto la soglia", "Considered, below the threshold"), scartati, spento: true)
                }
            }
        } else if lavora {
            ProgressView().controlSize(.small)
        }
    }

    private func gruppo(_ titolo: String, _ voci: [VoceProva], spento: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(titolo).font(.headline)
            ForEach(voci, id: \.identita) { p in
                HStack(alignment: .firstTextBaseline) {
                    Button {
                        archivio.memoriaScelta = p.nome
                        dismiss()
                    } label: {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(p.identita)
                            if let d = p.descrizione, !d.isEmpty {
                                Text(d).font(.callout).foregroundStyle(.secondary).lineLimit(2)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    if let s = p.punteggio {
                        Text(s, format: .number.precision(.fractionLength(1)))
                            .font(.callout.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
                .opacity(spento ? 0.75 : 1)
            }
        }
    }

    private func chiedi() async {
        let q = frase.trimmed
        guard !q.isEmpty else { esito = nil; errore = nil; return }
        // aspetta che si smetta di scrivere; una nuova lettera annulla questa attesa
        try? await Task.sleep(nanoseconds: 350_000_000)
        guard !Task.isCancelled else { return }
        lavora = true
        defer { lavora = false }
        do {
            let r = try await archivio.cliente.ottieni(ProvaMemoria.self, "/api/memoria/prova",
                                                       query: ["q": q], compartimento: archivio.compartimento)
            guard !Task.isCancelled else { return }
            esito = r
            errore = nil
        } catch is CancellationError {
            return
        } catch {
            guard !Task.isCancelled else { return }
            errore = error.localizedDescription
        }
    }
}
