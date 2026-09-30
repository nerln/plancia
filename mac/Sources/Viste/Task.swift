// Task: tutti i task, di Plancia, di Claude Code e di Codex (la lavagna). E' la prima
// vista vera e il modello per le altre:
//   - i dati vengono dallo Store (@Environment(Archivio.self)), la vista non parla col
//     server tranne che per le scritture, e anche quelle passano dallo Store;
//   - la selezione sta nello Store (taskScelto) cosi' Jarvis, plancia:// e le istantanee
//     possono sceglierla;
//   - Table per l'elenco, Inspector a destra per il dettaglio, ContentUnavailableView
//     per i vuoti, font e colori di sistema, niente vetro fatto a mano.

import SwiftUI

// MARK: - una riga della tabella

struct RigaTask: Identifiable, Hashable {
    let voce: VoceLavagna
    let compito: Compito?

    var id: String { voce.identita }
    var titolo: String { voce.titolo ?? compito?.title ?? "" }
    var fonte: String { voce.fonte ?? "" }
    /// "claude" -> "Claude", per chi legge.
    var fonteNome: String { fonte.prefix(1).uppercased() + fonte.dropFirst() }
    var stato: String { voce.stato ?? compito?.status ?? "aperto" }
    var chiuso: Bool { stato == "fatto" || stato == "archiviato" }
    var progetto: String { voce.progetto ?? compito?.project ?? "" }
    var progettoChiave: String? { voce.progettoChiave ?? compito?.projectKey }
    /// yyyy-MM-dd, se il task ne ha una (solo quelli di Plancia)
    var scadenza: String? { compito?.due }
    /// Per ordinare: i task senza scadenza vanno in fondo.
    var scadenzaOrd: String { scadenza ?? "9999-99-99" }
    var aggiornato: String { voce.aggiornatoAt ?? "" }
    /// L'id del task di Plancia, se questa riga lo e': solo questi si chiudono da qui.
    var taskId: Int? { fonte == "plancia" ? (voce.taskId ?? compito?.id) : nil }
    var dettaglio: String { (voce.dettaglio ?? compito?.body ?? "").trimmed }
}

private enum FiltroStato: String, CaseIterable, Identifiable {
    case aperti, fatti, tutti
    var id: String { rawValue }
    @MainActor var titolo: String {
        switch self {
        case .aperti: return tr("Aperti", "Open")
        case .fatti: return tr("Fatti", "Done")
        case .tutti: return tr("Tutti", "All")
        }
    }
}

@MainActor
private func testoStato(_ s: String) -> String {
    switch s {
    case "aperto": return tr("Aperto", "Open")
    case "in corso": return tr("In corso", "In progress")
    case "bloccato": return tr("Bloccato", "Blocked")
    case "fatto": return tr("Fatto", "Done")
    case "archiviato": return tr("Archiviato", "Archived")
    default: return s
    }
}

private func simboloStato(_ s: String) -> String {
    switch s {
    case "fatto", "archiviato": return "checkmark.circle.fill"
    case "in corso": return "circle.lefthalf.filled"
    case "bloccato": return "exclamationmark.circle"
    default: return "circle"
    }
}

// MARK: - la vista

struct VistaTask: View {
    @Environment(Archivio.self) private var archivio

    @State private var stato: FiltroStato = .aperti
    @State private var fonte: String = ""          // "" = tutte
    @State private var ordine: [KeyPathComparator<RigaTask>] = []
    @State private var nuovo = false

    private var righe: [RigaTask] {
        let perId = Dictionary(archivio.compiti.compactMap { c in c.id.map { ($0, c) } },
                               uniquingKeysWith: { a, _ in a })
        let tutte = (archivio.lavagna?.voci ?? []).map { v in
            RigaTask(voce: v, compito: v.taskId.flatMap { perId[$0] })
        }
        let filtrate = tutte.filter { r in
            (fonte.isEmpty || r.fonte == fonte)
                && (stato == .tutti || (stato == .aperti ? !r.chiuso : r.chiuso))
        }
        return ordine.isEmpty ? filtrate : filtrate.sorted(using: ordine)
    }

    var body: some View {
        @Bindable var a = archivio
        let elenco = righe
        Group {
            if elenco.isEmpty {
                vuoto
            } else {
                Table(elenco, selection: $a.taskScelto, sortOrder: $ordine) {
                    TableColumn("") { r in indicatore(r) }
                        .width(26)
                    TableColumn(tr("Titolo", "Title"), value: \.titolo) { r in
                        Text(r.titolo).lineLimit(1)
                    }
                    .width(min: 200, ideal: 420)
                    TableColumn(tr("Progetto", "Project"), value: \.progetto) { r in
                        Text(r.progetto).foregroundStyle(.secondary).lineLimit(1)
                    }
                    .width(min: 90, ideal: 120)
                    TableColumn(tr("Scadenza", "Due"), value: \.scadenzaOrd) { r in scadenza(r) }
                        .width(min: 70, ideal: 90)
                    TableColumn(tr("Fonte", "Source"), value: \.fonte) { r in
                        Text(r.fonteNome).foregroundStyle(.secondary)
                    }
                    .width(min: 60, ideal: 80)
                }
                // le righe a strisce sotto l'ultima sembrano un fantasma: niente
                .alternatingRowBackgrounds(.disabled)
            }
        }
        .inspector(isPresented: mostraDettaglio) {
            if let r = rigaScelta {
                DettaglioTask(riga: r)
                    .inspectorColumnWidth(min: 260, ideal: 320, max: 460)
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Picker(tr("Stato", "Status"), selection: $stato) {
                    ForEach(FiltroStato.allCases) { Text($0.titolo).tag($0) }
                }
                .pickerStyle(.segmented)
            }
            ToolbarItem(placement: .automatic) {
                Picker(tr("Fonte", "Source"), selection: $fonte) {
                    Text(tr("Tutte le fonti", "All sources")).tag("")
                    Text("Plancia").tag("plancia")
                    Text("Claude").tag("claude")
                    Text("Codex").tag("codex")
                }
                .pickerStyle(.menu)
            }
            ToolbarItem(placement: .primaryAction) {
                Button { nuovo = true } label: {
                    Label(tr("Nuovo task", "New task"), systemImage: "plus")
                }
                .keyboardShortcut("n", modifiers: .command)
                .help(tr("Nuovo task", "New task"))
            }
        }
        .sheet(isPresented: $nuovo) { NuovoTask() }
    }

    // MARK: pezzi

    private var rigaScelta: RigaTask? {
        guard let id = archivio.taskScelto else { return nil }
        return righe.first { $0.id == id }
    }

    private var mostraDettaglio: Binding<Bool> {
        Binding(get: { rigaScelta != nil },
                set: { if !$0 { archivio.taskScelto = nil } })
    }

    @ViewBuilder private var vuoto: some View {
        if archivio.lavagna == nil {
            if archivio.raggiungibile {
                ProgressView().controlSize(.small)
            } else {
                ContentUnavailableView(
                    tr("Server non raggiungibile", "Server unreachable"),
                    systemImage: "bolt.horizontal.circle",
                    description: Text(tr("Appena risponde, i task compaiono qui.",
                                         "Tasks appear here as soon as it answers.")))
            }
        } else if stato == .aperti && fonte.isEmpty {
            ContentUnavailableView(
                tr("Nessun task aperto", "No open tasks"),
                systemImage: "checkmark.circle")
        } else {
            ContentUnavailableView.search
        }
    }

    private func indicatore(_ r: RigaTask) -> some View {
        Image(systemName: simboloStato(r.stato))
            .foregroundStyle(r.stato == "bloccato" ? Color.orange : (r.chiuso ? Color.accentColor : Color.secondary))
            .accessibilityLabel(testoStato(r.stato))
    }

    @ViewBuilder private func scadenza(_ r: RigaTask) -> some View {
        if let s = r.scadenza, !s.isEmpty {
            Text(Tempo.giorno(s))
                .foregroundStyle(!r.chiuso && Tempo.scaduto(s) ? Color.red : Color.secondary)
        } else {
            Text("")
        }
    }
}

// MARK: - il dettaglio (Inspector)

private struct DettaglioTask: View {
    let riga: RigaTask
    @Environment(Archivio.self) private var archivio

    @State private var messaggio: String?
    @State private var errore: String?
    @State private var lavora = false
    @State private var pronto: LancioPronto?

    var body: some View {
        Form {
            Section {
                Text(riga.titolo).font(.headline).textSelection(.enabled)
                if !riga.dettaglio.isEmpty {
                    Text(riga.dettaglio).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }
            Section {
                LabeledContent(tr("Stato", "Status"), value: testoStato(riga.stato))
                if !riga.progetto.isEmpty { LabeledContent(tr("Progetto", "Project"), value: riga.progetto) }
                if let s = riga.scadenza, !s.isEmpty { LabeledContent(tr("Scadenza", "Due"), value: Tempo.giorno(s)) }
                LabeledContent(tr("Fonte", "Source"), value: riga.fonteNome)
                if !riga.aggiornato.isEmpty {
                    LabeledContent(tr("Aggiornato", "Updated"), value: Tempo.relativo(riga.aggiornato))
                }
            }
            Section {
                Button { Task { await riprendi() } } label: {
                    Label(tr("Riprendi", "Resume"), systemImage: "play")
                }
                .disabled(lavora)
                if let id = riga.taskId {
                    Button { Task { await inBackground(id) } } label: {
                        Label(tr("In background", "In background"), systemImage: "play.circle")
                    }
                    .disabled(lavora)
                    Button { Task { await cambia(id, riga.chiuso ? "aperto" : "fatto") } } label: {
                        Label(riga.chiuso ? tr("Riapri", "Reopen") : tr("Fatto", "Done"),
                              systemImage: riga.chiuso ? "arrow.uturn.backward" : "checkmark")
                    }
                    .disabled(lavora)
                }
                if let k = riga.progettoChiave, !k.isEmpty {
                    Button { archivio.vai(.progetti, progetto: k) } label: {
                        Label(tr("Apri progetto", "Open project"), systemImage: "folder")
                    }
                }
            }
            if let m = messaggio {
                Section { Text(m).font(.callout).foregroundStyle(.secondary) }
            }
            if let e = errore {
                Section { Text(e).font(.callout).foregroundStyle(.red) }
            }
        }
        .formStyle(.grouped)
        .confirmationDialog(
            pronto?.titolo ?? "",
            isPresented: Binding(get: { pronto != nil }, set: { if !$0 { pronto = nil } }),
            titleVisibility: .visible, presenting: pronto) { l in
            Button(l.azione) { Task { await avvia(l) } }
            Button(tr("Annulla", "Cancel"), role: .cancel) {}
        } message: { l in
            // il piano PRIMA di partire: la sessione originale, una copia, o una nuova
            Text(l.testo)
        }
    }

    private func cambia(_ id: Int, _ stato: String) async {
        lavora = true; errore = nil; messaggio = nil
        errore = await archivio.imposta(task: id, stato: stato)
        lavora = false
    }

    /// Riprendi: nel Terminale, nella sessione del task. Se la sessione non c'e' piu' lo dice
    /// prima, invece di aprirne una nuova senza avvisare.
    private func riprendi() async {
        errore = nil; messaggio = nil
        if let id = riga.taskId {
            lavora = true
            let piano = await archivio.pianoRipresa(task: id)
            lavora = false
            if let p = piano, p.modo == "nuova" {
                pronto = LancioPronto(nuovaNelTerminale: "/api/riprendi/\(id)", piano: p,
                                      agente: riga.voce.agente ?? "claude")
                return
            }
            await apriNelTerminale(id)
        } else {
            // i task di Claude Code e di Codex non hanno un id di Plancia: parte un lancio,
            // nella sessione che la riga ricorda
            await preparaLancio(percorso: "/api/cantiere", corpo: corpoLancio())
        }
    }

    /// In background: il lavoro senza testa riprende la sessione del task (o dice che non c'e').
    private func inBackground(_ id: Int) async {
        errore = nil; messaggio = nil
        await preparaLancio(
            percorso: "/api/riprendi/\(id)",
            corpo: ["background": true, "scrive": false, "lang": Lingua.condivisa.codice])
    }

    private func apriNelTerminale(_ id: Int) async {
        lavora = true
        let r = await archivio.scriviRisposta("POST", "/api/riprendi/\(id)", corpo: ["apri": true])
        lavora = false
        switch r {
        case .success(let j):
            messaggio = j["riga"]?.testo ?? j["messaggio"]?.testo ?? tr("Avviato", "Started")
        case .failure(let e):
            errore = e.localizedDescription
        }
    }

    /// Chiede al server cosa farebbe (anteprima) e, se parte qualcosa, lo mostra prima di lanciare.
    private func preparaLancio(percorso: String, corpo: [String: Any]) async {
        lavora = true
        let piano = await archivio.anteprima(percorso, corpo)
        lavora = false
        guard let p = piano else {
            errore = tr("Non riesco a sapere cosa farebbe il lancio: il server non risponde.",
                        "Can't tell what the run would do: the server isn't answering.")
            return
        }
        if !p.parte {
            messaggio = p.frase
            return
        }
        pronto = LancioPronto(percorso: percorso, corpo: corpo, piano: p,
                              agente: riga.voce.agente ?? "claude")
    }

    private func corpoLancio() -> [String: Any] {
        var corpo: [String: Any] = ["titolo": riga.titolo, "dettaglio": String(riga.dettaglio.prefix(600)),
                                    "agente": riga.voce.agente ?? "claude", "scrive": false,
                                    "lang": Lingua.condivisa.codice]
        if let k = riga.progettoChiave { corpo["progetto"] = k }
        if let s = riga.voce.sessione, !s.isEmpty { corpo["sessione"] = s }
        return corpo
    }

    private func avvia(_ l: LancioPronto) async {
        lavora = true
        let r = await archivio.scriviRisposta("POST", l.percorso, corpo: l.corpo)
        lavora = false
        switch r {
        case .success(let j):
            if j["lanciato"]?.testo == "false" {
                messaggio = l.piano.frase   // nel frattempo la sessione si e' aperta: non e' partito niente
            } else if l.corpo["apri"] != nil {
                messaggio = j["riga"]?.testo ?? j["messaggio"]?.testo ?? tr("Avviato", "Started")
            } else {
                messaggio = tr("Lancio avviato. ", "Run started. ") + l.piano.frase
            }
        case .failure(let e):
            errore = e.localizedDescription
        }
    }
}

// MARK: - nuovo task (⌘N)

private struct NuovoTask: View {
    @Environment(Archivio.self) private var archivio
    @Environment(\.dismiss) private var dismiss

    @State private var titolo = ""
    @State private var note = ""
    @State private var progetto = ""
    @State private var conScadenza = false
    @State private var scadenza = Date()
    @State private var priorita = 2
    @State private var errore: String?
    @State private var lavora = false

    var body: some View {
        VStack(spacing: 0) {
            Form {
                TextField(tr("Titolo", "Title"), text: $titolo)
                TextField(tr("Note", "Notes"), text: $note, axis: .vertical)
                    .lineLimit(3...6)
                Picker(tr("Progetto", "Project"), selection: $progetto) {
                    Text(tr("Nessuno", "None")).tag("")
                    ForEach(archivio.progetti.filter { $0.key != nil }, id: \.identita) { p in
                        Text(p.nome).tag(p.key ?? "")
                    }
                }
                Picker(tr("Priorità", "Priority"), selection: $priorita) {
                    Text(tr("Alta", "High")).tag(1)
                    Text(tr("Normale", "Normal")).tag(2)
                    Text(tr("Bassa", "Low")).tag(3)
                }
                Toggle(tr("Scadenza", "Due date"), isOn: $conScadenza)
                if conScadenza {
                    DatePicker(tr("Data", "Date"), selection: $scadenza, displayedComponents: .date)
                }
                if let e = errore { Text(e).foregroundStyle(.red) }
            }
            .formStyle(.grouped)
            HStack {
                Spacer()
                Button(tr("Annulla", "Cancel"), role: .cancel) { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button(tr("Aggiungi", "Add")) { Task { await aggiungi() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(titolo.trimmed.isEmpty || lavora)
            }
            .padding([.horizontal, .bottom])
        }
        .frame(width: 440)
        .task { if archivio.progetti.isEmpty { await archivio.carica(.task) } }
    }

    private func aggiungi() async {
        lavora = true
        var data: String?
        if conScadenza {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.dateFormat = "yyyy-MM-dd"
            data = f.string(from: scadenza)
        }
        let e = await archivio.nuovoTask(titolo: titolo.trimmed, note: note.trimmed,
                                         progetto: progetto, priorita: priorita, scadenza: data)
        lavora = false
        if let e = e { errore = e } else { dismiss() }
    }
}
