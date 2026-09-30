// Progetti: a sinistra i progetti raggruppati per area (l'area e' il progetto padre, i
// figli sono i sottoprogetti), a destra la scheda del progetto scelto: prossima azione
// (modificabile), task, sessioni recenti, commit e collegamenti.
//   - i dati vengono dallo Store; la selezione e' `progettoScelto`, cosi' "Apri progetto"
//     dalle altre viste, Jarvis e plancia:// la possono impostare;
//   - l'unica scrittura e' la prossima azione (PATCH /api/projects/<chiave>);
//   - List e Form di sistema, font e colori semantici, niente vetro fatto a mano.

import SwiftUI
import AppKit

// MARK: - l'albero, appiattito

enum FiltroProgetti: String, CaseIterable, Identifiable {
    case attivi, tutti
    var id: String { rawValue }
    @MainActor var titolo: String {
        switch self {
        case .attivi: return tr("Attivi", "Active")
        case .tutti: return tr("Tutti", "All")
        }
    }
}

/// Una riga della lista: un progetto, a che livello sta, se ha figli.
private struct RigaAlbero: Identifiable {
    let progetto: Progetto
    let livello: Int
    let figli: Int
    var id: String { progetto.identita }
}

private struct GruppoAlbero: Identifiable {
    let id: String
    let titolo: String?
    let righe: [RigaAlbero]
}

private func spento(_ p: Progetto) -> Bool {
    ["concluso", "archiviato", "in pausa", "idea"].contains(p.status ?? "")
}

@MainActor
private func testoStatoProgetto(_ s: String?) -> String {
    switch s ?? "" {
    case "attivo": return tr("Attivo", "Active")
    case "in pausa": return tr("In pausa", "Paused")
    case "concluso": return tr("Concluso", "Done")
    case "idea": return tr("Idea", "Idea")
    case "archiviato": return tr("Archiviato", "Archived")
    default: return s ?? ""
    }
}

// MARK: - la vista

struct VistaProgetti: View {
    @Environment(Archivio.self) private var archivio

    private let c = ControlliVista.condiviso
    /// Le aree chiuse a mano; all'inizio sono tutte aperte.
    @State private var chiuse: Set<String> = []

    private var radici: [Progetto] {
        archivio.alberoProgetti.isEmpty ? archivio.progetti.filter { $0.parentId == nil } : archivio.alberoProgetti
    }

    /// Un progetto si vede se il filtro lo lascia passare o se e' quello scelto.
    private func visibile(_ p: Progetto) -> Bool {
        if (p.hidden ?? 0) != 0 { return false }
        if p.identita == archivio.progettoScelto { return true }
        if c.filtroProgetti == .tutti { return true }
        return !["concluso", "archiviato"].contains(p.status ?? "")
    }

    private var gruppi: [GruppoAlbero] {
        var aree: [RigaAlbero] = []
        var singoli: [RigaAlbero] = []
        for r in radici {
            let figli = (r.figli ?? []).filter { visibile($0) }
            if figli.isEmpty {
                if visibile(r) { singoli.append(RigaAlbero(progetto: r, livello: 0, figli: 0)) }
            } else {
                aree.append(RigaAlbero(progetto: r, livello: 0, figli: figli.count))
                if !chiuse.contains(r.identita) {
                    aree += figli.map { RigaAlbero(progetto: $0, livello: 1, figli: 0) }
                }
            }
        }
        if aree.isEmpty { return singoli.isEmpty ? [] : [GruppoAlbero(id: "tutti", titolo: nil, righe: singoli)] }
        var g = [GruppoAlbero(id: "aree", titolo: nil, righe: aree)]
        if !singoli.isEmpty {
            g.append(GruppoAlbero(id: "singoli", titolo: nil, righe: singoli))
        }
        return g
    }

    var body: some View {
        @Bindable var a = archivio
        let elenco = gruppi
        Group {
            if elenco.isEmpty {
                vuoto
            } else {
                HSplitView {
                    lista(elenco, selezione: $a.progettoScelto)
                        .frame(minWidth: 250, idealWidth: 300, maxWidth: 420, maxHeight: .infinity)
                    scheda
                        .frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task(id: archivio.progettoScelto) {
            if let k = archivio.progettoScelto { await archivio.caricaDettaglio(k) }
        }
    }

    // MARK: pezzi

    private func lista(_ elenco: [GruppoAlbero], selezione: Binding<String?>) -> some View {
        List(selection: selezione) {
            ForEach(elenco) { g in
                if let t = g.titolo {
                    Section(t) { righe(g.righe) }
                } else {
                    Section { righe(g.righe) }
                }
            }
        }
        .listStyle(.inset)
    }

    private func righe(_ r: [RigaAlbero]) -> some View {
        ForEach(r) { riga in
            RigaProgetto(riga: riga, chiusa: chiuse.contains(riga.id)) {
                if chiuse.contains(riga.id) { chiuse.remove(riga.id) } else { chiuse.insert(riga.id) }
            }
            .tag(riga.id)
        }
    }

    @ViewBuilder private var scheda: some View {
        if let k = archivio.progettoScelto {
            SchedaProgetto(chiave: k).id(k)
        } else {
            ContentUnavailableView(tr("Scegli un progetto", "Choose a project"), systemImage: "folder")
        }
    }

    @ViewBuilder private var vuoto: some View {
        if archivio.progetti.isEmpty && archivio.alberoProgetti.isEmpty {
            if archivio.raggiungibile && archivio.ultimoAggiornamento == nil {
                ProgressView().controlSize(.small)
            } else if !archivio.raggiungibile {
                ContentUnavailableView(
                    tr("Server non raggiungibile", "Server unreachable"),
                    systemImage: "bolt.horizontal.circle",
                    description: Text(tr("Appena risponde, i progetti compaiono qui.",
                                         "Projects appear here as soon as it answers.")))
            } else {
                ContentUnavailableView(tr("Nessun progetto", "No projects"), systemImage: "folder")
            }
        } else {
            ContentUnavailableView(tr("Nessun progetto attivo", "No active projects"), systemImage: "folder",
                                   description: Text(tr("Con Tutti si vedono anche i conclusi.",
                                                        "Choose All to include finished ones.")))
        }
    }
}

// MARK: - una riga della lista

private struct RigaProgetto: View {
    let riga: RigaAlbero
    let chiusa: Bool
    let alterna: () -> Void

    var body: some View {
        let p = riga.progetto
        HStack(spacing: 6) {
            if riga.figli > 0 {
                Button(action: alterna) {
                    Image(systemName: chiusa ? "chevron.right" : "chevron.down")
                        .imageScale(.small)
                        .foregroundStyle(.secondary)
                        .frame(width: 12)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel(chiusa ? tr("Apri l'area", "Expand area") : tr("Chiudi l'area", "Collapse area"))
            } else if riga.livello > 0 {
                Color.clear.frame(width: 12)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(p.nome)
                    .font(riga.figli > 0 ? .headline : .body)
                    .foregroundStyle(spento(p) ? .secondary : .primary)
                    .lineLimit(1)
                if let n = p.nextAction?.trimmed, !n.isEmpty {
                    Text(n).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                } else if p.status != "attivo" {
                    Text(testoStatoProgetto(p.status)).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .badge(p.taskAperti ?? 0)
    }
}

// MARK: - la scheda del progetto

private struct SchedaProgetto: View {
    let chiave: String
    @Environment(Archivio.self) private var archivio

    @State private var prossima = ""
    @State private var salvando = false
    @State private var errore: String?
    @State private var tuttiFatti = false
    @State private var tutteSessioni = false
    @State private var tuttiCommit = false

    private static let quanti = 5

    private var dettaglio: DettaglioProgetto? { archivio.dettagli[chiave] }

    /// Il progetto: dal dettaglio se c'e', altrimenti dalla lista (compare subito).
    private var progetto: Progetto? {
        if let p = dettaglio?.progetto { return p }
        func cerca(_ l: [Progetto]) -> Progetto? {
            for p in l {
                if p.identita == chiave { return p }
                if let f = cerca(p.figli ?? []) { return f }
            }
            return nil
        }
        return cerca(archivio.alberoProgetti) ?? cerca(archivio.progetti)
    }

    private var valoreServer: String { progetto?.nextAction ?? "" }
    private var modificata: Bool { prossima.trimmed != valoreServer.trimmed }

    var body: some View {
        Group {
            if let p = progetto {
                Form {
                    intestazione(p)
                    sezioneProssima
                    if let d = dettaglio {
                        sezioneTask(d.task ?? [])
                        sezioneSessioni(d.sessioni ?? [])
                        sezioneCommit(d.commit ?? [])
                        sezioneCollegamenti(d.repo ?? [], d.link ?? [])
                    } else if archivio.raggiungibile {
                        Section { ProgressView().controlSize(.small) }
                    }
                }
                .formStyle(.grouped)
            } else {
                ContentUnavailableView(tr("Progetto non trovato", "Project not found"), systemImage: "folder")
            }
        }
        .onAppear { prossima = valoreServer }
        // il server cambia il valore (un'altra scrittura, la rilettura): si segue solo
        // se chi scrive non ha ancora toccato il campo
        .onChange(of: valoreServer) { vecchio, nuovo in
            if prossima == vecchio { prossima = nuovo }
        }
    }

    // MARK: intestazione

    @ViewBuilder private func intestazione(_ p: Progetto) -> some View {
        Section {
            Text(p.nome).font(.title2).textSelection(.enabled)
            if let s = p.summary?.trimmed, !s.isEmpty {
                Text(s).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
            }
            LabeledContent(tr("Stato", "Status"), value: testoStatoProgetto(p.status))
            if let k = p.kind, !k.isEmpty { LabeledContent(tr("Tipo", "Kind"), value: k) }
            if let u = p.lastActivity, !u.isEmpty {
                LabeledContent(tr("Ultima attività", "Last activity"), value: Tempo.relativo(u))
            }
        }
    }

    // MARK: prossima azione

    private var sezioneProssima: some View {
        Section(tr("Prossima azione", "Next action")) {
            TextField(tr("Prossima azione", "Next action"), text: $prossima,
                      prompt: Text(tr("Cosa si fa dopo", "What comes next")), axis: .vertical)
                .labelsHidden()
                .lineLimit(1...4)
                .onSubmit { Task { await salva() } }
            HStack {
                if let e = errore { Text(e).font(.callout).foregroundStyle(.red) }
                Spacer()
                Button(tr("Aggiorna prossima azione", "Update next action")) { Task { await salva() } }
                    .disabled(!modificata || salvando)
            }
        }
    }

    private func salva() async {
        guard modificata, !salvando else { return }
        salvando = true; errore = nil
        let percorso = "/api/projects/" + (chiave.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? chiave)
        errore = await archivio.scrivi("PATCH", percorso, corpo: ["next_action": prossima.trimmed])
        salvando = false
    }

    // MARK: task

    private func chiuso(_ c: Compito) -> Bool { ["fatto", "archiviato"].contains(c.status ?? "") }

    private func sezioneTask(_ tutti: [Compito]) -> some View {
        let aperti = tutti.filter { !chiuso($0) }
        let fatti = tutti.filter { chiuso($0) }
        return Section(tr("Task", "Tasks")) {
            if aperti.isEmpty {
                Text(tr("Nessun task aperto", "No open tasks")).foregroundStyle(.secondary)
            }
            ForEach(aperti, id: \.identita) { riga($0) }
            if !fatti.isEmpty {
                DisclosureGroup(isExpanded: $tuttiFatti) {
                    ForEach(fatti, id: \.identita) { riga($0) }
                } label: {
                    Text(tr("Fatti (\(fatti.count))", "Done (\(fatti.count))")).foregroundStyle(.secondary)
                }
            }
        }
    }

    private func riga(_ c: Compito) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: simbolo(c.status))
                .foregroundStyle(c.status == "bloccato" ? Color.orange : (chiuso(c) ? Color.accentColor : Color.secondary))
                .accessibilityHidden(true)
            Text(c.title ?? "").lineLimit(2)
                .foregroundStyle(chiuso(c) ? .secondary : .primary)
            Spacer(minLength: 8)
            if let s = c.due, !s.isEmpty {
                Text(Tempo.giorno(s))
                    .foregroundStyle(!chiuso(c) && Tempo.scaduto(s) ? Color.red : Color.secondary)
            }
        }
    }

    private func simbolo(_ s: String?) -> String {
        switch s ?? "" {
        case "fatto", "archiviato": return "checkmark.circle.fill"
        case "in corso": return "circle.lefthalf.filled"
        case "bloccato": return "exclamationmark.circle"
        default: return "circle"
        }
    }

    // MARK: sessioni

    @ViewBuilder private func sezioneSessioni(_ tutte: [Sessione]) -> some View {
        if !tutte.isEmpty {
            let viste = tutteSessioni ? tutte : Array(tutte.prefix(Self.quanti))
            Section(tr("Sessioni recenti", "Recent sessions")) {
                ForEach(viste, id: \.identita) { s in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(titolo(s)).lineLimit(1)
                        Text(dettaglioSessione(s)).font(.caption).foregroundStyle(.secondary)
                    }
                }
                if tutte.count > Self.quanti {
                    Button(tutteSessioni ? tr("Mostra meno", "Show fewer")
                                         : tr("Mostra altre \(tutte.count - Self.quanti)", "Show \(tutte.count - Self.quanti) more")) {
                        tutteSessioni.toggle()
                    }
                    .collegamento()
                }
            }
        }
    }

    private func titolo(_ s: Sessione) -> String {
        let t = (s.title ?? "").trimmed
        return t.isEmpty ? (s.prompt ?? s.firstPrompt ?? "").trimmed : t
    }

    private func dettaglioSessione(_ s: Sessione) -> String {
        var parti = [Tempo.relativo(s.startedAt)]
        if let n = s.nUser, n > 0 { parti.append(tr("\(n) messaggi", "\(n) messages")) }
        return parti.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    // MARK: commit

    @ViewBuilder private func sezioneCommit(_ tutti: [Commit]) -> some View {
        if !tutti.isEmpty {
            let visti = tuttiCommit ? tutti : Array(tutti.prefix(Self.quanti))
            Section("Commit") {
                ForEach(visti, id: \.identita) { c in
                    HStack(spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text((c.message ?? "").trimmed).lineLimit(1)
                            Text(dettaglioCommit(c)).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer(minLength: 8)
                        if let u = indirizzoWeb(c.url) {
                            Link(destination: u) { Image(systemName: "arrow.up.right.square") }
                                .accessibilityLabel(tr("Apri il commit", "Open commit"))
                        }
                    }
                }
                if tutti.count > Self.quanti {
                    Button(tuttiCommit ? tr("Mostra meno", "Show fewer")
                                       : tr("Mostra altri \(tutti.count - Self.quanti)", "Show \(tutti.count - Self.quanti) more")) {
                        tuttiCommit.toggle()
                    }
                    .collegamento()
                }
            }
        }
    }

    private func dettaglioCommit(_ c: Commit) -> String {
        var parti: [String] = []
        if let s = c.sha, !s.isEmpty { parti.append(String(s.prefix(7))) }
        if let r = c.repo, !r.isEmpty { parti.append(r) }
        parti.append(Tempo.relativo(c.date))
        return parti.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    // MARK: collegamenti

    @ViewBuilder private func sezioneCollegamenti(_ repo: [Repo], _ link: [LinkProgetto]) -> some View {
        let nomiRepo = Set(repo.compactMap { $0.name })
        let altri = link.filter { !($0.kind == "repo" && nomiRepo.contains($0.value ?? "")) }
        if !repo.isEmpty || !altri.isEmpty {
            Section(tr("Collegamenti", "Links")) {
                ForEach(repo, id: \.name) { r in
                    HStack(spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(r.name ?? "").lineLimit(1)
                            let sotto = [r.visibility, r.branch].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
                            if !sotto.isEmpty { Text(sotto).font(.caption).foregroundStyle(.secondary) }
                        }
                        Spacer(minLength: 8)
                        if let u = indirizzoWeb(r.url) {
                            Link(destination: u) { Image(systemName: "arrow.up.right.square") }
                                .accessibilityLabel(tr("Apri il repository", "Open repository"))
                        }
                        if let p = r.localPath, !p.isEmpty { pulsanteCartella(p) }
                    }
                }
                ForEach(altri, id: \.self) { l in
                    HStack(spacing: 8) {
                        LabeledContent(l.kind ?? "", value: l.value ?? "")
                        if l.kind == "path", let p = l.value, !p.isEmpty { pulsanteCartella(p) }
                        else if let u = indirizzoWeb(l.value) {
                            Link(destination: u) { Image(systemName: "arrow.up.right.square") }
                                .accessibilityLabel(tr("Apri il collegamento", "Open link"))
                        }
                    }
                }
            }
        }
    }

    private func pulsanteCartella(_ percorso: String) -> some View {
        Button {
            let url = URL(fileURLWithPath: (percorso as NSString).expandingTildeInPath)
            NSWorkspace.shared.activateFileViewerSelecting([url])
        } label: {
            Image(systemName: "folder")
        }
        .buttonStyle(.borderless)
        .help(tr("Mostra nel Finder", "Show in Finder"))
        .accessibilityLabel(tr("Mostra nel Finder", "Show in Finder"))
    }

    /// Solo http e https: un collegamento con un altro schema non si apre da qui.
    private func indirizzoWeb(_ s: String?) -> URL? {
        guard let s = s, let u = URL(string: s), ["http", "https"].contains(u.scheme?.lowercased() ?? "") else { return nil }
        return u
    }
}
