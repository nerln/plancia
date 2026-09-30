// Risultati: la vista che sostituisce il contenuto finche' il campo di ricerca non e' vuoto.
//
// Come lavora:
//   1. filtro locale, istantaneo, sui dati che l'Archivio ha gia' in memoria (task, progetti,
//      sessioni, memoria): compare alla prima lettera;
//   2. lo Store (Archivio.avviaRicerca) chiede /api/search dopo circa 200 ms senza nuovi
//      caratteri e annulla la richiesta precedente; qui i risultati del server si fondono con
//      quelli locali senza far saltare la lista: una riga locale non si sposta mai, quelle
//      che arrivano solo dal server si aggiungono in fondo al loro gruppo, e le anteprime
//      del server si attaccano alle righe locali che gia' ci sono;
//   3. i risultati sono raggruppati per tipo, in un ordine fisso; i gruppi lunghi mostrano le
//      prime righe e "Mostra altri".
//
// Una riga scelta apre il suo Inspector con un'anteprima e il pulsante Apri, che porta alla
// sezione giusta con l'elemento gia' scelto. Ambiti (Tutto, Task, Progetti, Sessioni, Memoria)
// li mette il guscio con searchScopes; qui si legge archivio.ambito.

import SwiftUI

// MARK: - modello

private enum TipoRis: String, CaseIterable, Hashable {
    case task, progetto, sessione, memoria, turno, altro

    var simbolo: String {
        switch self {
        case .task: return "checklist"
        case .progetto: return "folder"
        case .sessione: return "archivebox"
        case .memoria: return "brain"
        case .turno: return "bubble.left.and.bubble.right"
        case .altro: return "ellipsis.circle"
        }
    }

    @MainActor var titolo: String {
        switch self {
        case .task: return tr("Task", "Tasks")
        case .progetto: return tr("Progetti", "Projects")
        case .sessione: return tr("Sessioni", "Sessions")
        case .memoria: return tr("Memoria", "Memory")
        case .turno: return tr("Nelle conversazioni", "In conversations")
        case .altro: return tr("Altro", "Other")
        }
    }

    @MainActor var singolare: String {
        switch self {
        case .task: return tr("Task", "Task")
        case .progetto: return tr("Progetto", "Project")
        case .sessione: return tr("Sessione", "Session")
        case .memoria: return tr("Memoria", "Memory")
        case .turno: return tr("Conversazione", "Conversation")
        case .altro: return tr("Altro", "Other")
        }
    }
}

/// Dove porta "Apri".
private enum DestRis: Hashable {
    case task(String?)        // identita della voce di lavagna
    case progetto(String)     // chiave
    case sessione(String)     // session_id
    case memoria(String)      // nome
    case post(String)         // id
    case nessuna
}

private struct RigaRis: Identifiable, Hashable {
    let id: String
    let tipo: TipoRis
    var titolo: String
    var sottotitolo: String
    /// Il testo trovato: un frammento del server (con «» attorno alle parole) o il dettaglio locale.
    var anteprima: String?
    var quando: String?
    var progetto: String?
    var ruolo: String?
    var apri: DestRis
    /// Chiave per attaccare l'anteprima del server alla riga locale che c'e' gia'.
    var unione: String?
}

private struct GruppoRis: Identifiable {
    let tipo: TipoRis
    var righe: [RigaRis]
    var id: String { tipo.rawValue }
}

// MARK: - testo

/// Le parole scritte nel campo, senza spazi.
private func risTermini(_ q: String) -> [String] {
    q.split(whereSeparator: { $0.isWhitespace }).map(String.init)
}

private func risContiene(_ testo: String, _ t: String) -> Bool {
    testo.range(of: t, options: [.caseInsensitive, .diacriticInsensitive]) != nil
}

/// 0 se tutte le parole stanno nel titolo, 1 se stanno fra titolo e altri campi, nil se ne manca una.
private func risCombacia(_ termini: [String], titolo: String, altri: [String]) -> Int? {
    var soloTitolo = true
    for t in termini {
        if risContiene(titolo, t) { continue }
        soloTitolo = false
        if !altri.contains(where: { risContiene($0, t) }) { return nil }
    }
    return soloTitolo ? 0 : 1
}

/// Il testo con le parole cercate in grassetto.
private func risEvidenzia(_ testo: String, _ termini: [String]) -> AttributedString {
    var a = AttributedString(testo)
    for t in termini where !t.isEmpty {
        var da = a.startIndex
        while da < a.endIndex,
              let r = a[da...].range(of: t, options: [.caseInsensitive, .diacriticInsensitive]) {
            a[r].inlinePresentationIntent = .stronglyEmphasized
            da = r.upperBound
        }
    }
    return a
}

/// Toglie il Markdown dal frammento: "# " dei titoli, "- " e "> " a inizio riga, grassetti e
/// apici inversi. Le righe si uniscono con uno spazio.
private func risSenzaMarkdown(_ s: String) -> String {
    let righe = s.components(separatedBy: "\n").map { riga -> String in
        riga.trimmed.replacingOccurrences(
            of: #"^(#{1,6}|>|[-*+])\s+"#, with: "", options: .regularExpression)
    }
    return righe.filter { !$0.isEmpty }.joined(separator: " ")
        .replacingOccurrences(of: "**", with: "")
        .replacingOccurrences(of: "`", with: "")
}

/// Un frammento del server: le parole trovate sono fra « e ».
private func risFrammento(_ s: String) -> AttributedString {
    var fuori = AttributedString()
    var grassetto = false
    var tratto = ""
    func chiudi() {
        guard !tratto.isEmpty else { return }
        var pezzo = AttributedString(tratto)
        if grassetto { pezzo.inlinePresentationIntent = .stronglyEmphasized }
        fuori += pezzo
        tratto = ""
    }
    for c in risSenzaMarkdown(s) {
        if c == "«" { chiudi(); grassetto = true }
        else if c == "»" { chiudi(); grassetto = false }
        else { tratto.append(c) }
    }
    chiudi()
    return fuori
}

/// Vero se l'anteprima ripete il titolo (o ne e' la continuazione): non serve mostrarla.
private func risRipete(_ anteprima: String, _ titolo: String) -> Bool {
    func pulisci(_ t: String) -> String {
        t.replacingOccurrences(of: "«", with: "").replacingOccurrences(of: "»", with: "")
            .replacingOccurrences(of: "…", with: "").replacingOccurrences(of: "\n", with: " ").trimmed
            .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
    }
    let a = pulisci(anteprima), t = pulisci(titolo)
    guard !a.isEmpty, !t.isEmpty else { return false }
    return a.hasPrefix(t) || t.hasPrefix(a)
}

private func risUnisci(_ pezzi: [String?]) -> String {
    pezzi.compactMap { $0 }.map { $0.trimmed }.filter { !$0.isEmpty }.joined(separator: " · ")
}

// MARK: - la vista

struct VistaRisultati: View {
    @Environment(Archivio.self) private var archivio

    @State private var scelto: String?
    @State private var espansi: Set<TipoRis> = []

    private var q: String { archivio.ricerca.trimmed }

    // MARK: costruzione dei gruppi

    private static let limiteTutto = 5

    /// Quali tipi entrano nell'ambito scelto.
    private func inAmbito(_ t: TipoRis) -> Bool {
        switch archivio.ambito {
        case .tutto: return true
        case .task: return t == .task
        case .progetti: return t == .progetto
        case .sessioni: return t == .sessione || t == .turno
        case .memoria: return t == .memoria
        }
    }

    /// I risultati locali, in ordine di pertinenza (titolo prima) e poi come stanno nella sorgente.
    private func locali(_ termini: [String]) -> [TipoRis: [RigaRis]] {
        var out: [TipoRis: [RigaRis]] = [:]
        func ordina(_ v: [(Int, Int, RigaRis)]) -> [RigaRis] {
            v.sorted { ($0.0, $0.1) < ($1.0, $1.1) }.map { $0.2 }
        }

        if inAmbito(.task) {
            var v: [(Int, Int, RigaRis)] = []
            for (i, x) in (archivio.lavagna?.voci ?? []).enumerated() {
                let titolo = x.titolo ?? ""
                guard let rango = risCombacia(termini, titolo: titolo,
                                              altri: [x.dettaglio ?? "", x.progetto ?? ""]) else { continue }
                let chiuso = x.stato == "fatto" || x.stato == "archiviato"
                v.append((rango, i, RigaRis(
                    id: "task:\(x.identita)", tipo: .task, titolo: titolo,
                    sottotitolo: risUnisci([x.progetto, chiuso ? tr("Fatto", "Done") : nil,
                                            Tempo.relativo(x.aggiornatoAt)]),
                    anteprima: nil, quando: x.aggiornatoAt, progetto: x.progetto, ruolo: nil,
                    apri: .task(x.identita), unione: x.taskId.map { "task:\($0)" })))
            }
            out[.task] = ordina(v)
        }
        if inAmbito(.progetto) {
            var v: [(Int, Int, RigaRis)] = []
            for (i, p) in archivio.progetti.enumerated() where (p.hidden ?? 0) == 0 {
                guard let rango = risCombacia(termini, titolo: p.nome,
                                              altri: [p.key ?? "", p.summary ?? "", p.nextAction ?? ""]) else { continue }
                v.append((rango, i, RigaRis(
                    id: "progetto:\(p.identita)", tipo: .progetto, titolo: p.nome,
                    sottotitolo: (p.nextAction ?? p.summary ?? "").trimmed,
                    anteprima: nil, quando: p.lastActivity, progetto: nil, ruolo: nil,
                    apri: .progetto(p.key ?? p.identita), unione: nil)))
            }
            out[.progetto] = ordina(v)
        }
        if inAmbito(.sessione) {
            var v: [(Int, Int, RigaRis)] = []
            for (i, s) in archivio.sessioni.enumerated() {
                let titolo = (s.title ?? s.firstPrompt ?? "").trimmed
                guard let rango = risCombacia(termini, titolo: titolo,
                                              altri: [s.firstPrompt ?? "", s.progetto ?? ""]) else { continue }
                v.append((rango, i, RigaRis(
                    id: "sessione:\(s.identita)", tipo: .sessione, titolo: titolo,
                    sottotitolo: risUnisci([s.progetto, s.agent.map { $0.capitalized }, Tempo.relativo(s.startedAt)]),
                    anteprima: nil, quando: s.startedAt, progetto: s.progetto, ruolo: nil,
                    apri: .sessione(s.sessionId ?? s.identita), unione: s.id.map { "sessione:\($0)" })))
            }
            out[.sessione] = ordina(v)
        }
        if inAmbito(.memoria) {
            var v: [(Int, Int, RigaRis)] = []
            for (i, m) in archivio.schede.enumerated() {
                let nome = m.name ?? ""
                guard let rango = risCombacia(termini, titolo: nome,
                                              altri: [m.description ?? "", m.progetto ?? ""]) else { continue }
                v.append((rango, i, RigaRis(
                    id: "memoria:\(m.identita)", tipo: .memoria, titolo: nome,
                    sottotitolo: (m.description ?? "").trimmed,
                    anteprima: nil, quando: m.updatedAt, progetto: m.progetto, ruolo: nil,
                    apri: .memoria(m.identita), unione: m.id.map { "memoria:\($0)" })))
            }
            out[.memoria] = ordina(v)
        }
        return out
    }

    /// Il server risponde per la parola scritta; mentre ne arriva una nuova si tiene la
    /// vecchia se le parole sono imparentate, cosi' la lista non si svuota a ogni lettera.
    private var risposta: RisultatiRicerca? {
        guard let r = archivio.risultati else { return nil }
        let per = archivio.risultatiPer
        if per == q { return r }
        if archivio.ricercaInCorso && !per.isEmpty && (q.hasPrefix(per) || per.hasPrefix(q)) { return r }
        return nil
    }

    private func gruppi() -> [GruppoRis] {
        let termini = risTermini(q)
        var per = locali(termini)

        if let r = risposta {
            let sessioniPerId = Dictionary(archivio.sessioni.compactMap { s in s.sessionId.map { ($0, s) } },
                                           uniquingKeysWith: { a, _ in a })
            for h in r.schede ?? [] {
                guard let kind = h.kind, let ref = h.refId else { continue }
                let tipo: TipoRis
                switch kind {
                case "task": tipo = .task
                case "memoria": tipo = .memoria
                case "sessione": tipo = .sessione
                default: tipo = .altro
                }
                switch (archivio.ambito, tipo) {
                case (.tutto, _), (.task, .task), (.memoria, .memoria), (.sessioni, .sessione): break
                default: continue
                }
                let snip = (h.snip ?? "").trimmed
                let unione = "\(kind):\(ref)"
                var righe = per[tipo] ?? []
                if let i = righe.firstIndex(where: { $0.unione == unione }) {
                    // la riga c'e' gia': prende l'anteprima del server, non si muove
                    if righe[i].anteprima == nil, !snip.isEmpty { righe[i].anteprima = snip }
                    per[tipo] = righe
                    continue
                }
                var dest: DestRis = .nessuna
                switch kind {
                case "task":
                    dest = .task((archivio.lavagna?.voci ?? []).first { $0.taskId == ref }?.identita)
                case "memoria":
                    dest = .memoria(archivio.schede.first { $0.id == ref }?.name ?? h.title ?? "")
                case "sessione":
                    if let x = archivio.sessioni.first(where: { $0.id == ref }) {
                        dest = .sessione(x.sessionId ?? x.identita)
                    }
                case "post":
                    dest = .post(String(ref))
                default:
                    break
                }
                let etichetta: String?
                switch kind {
                case "commit": etichetta = "Commit"
                case "post": etichetta = "Post"
                case "capacita": etichetta = tr("Capacità", "Capability")
                default: etichetta = nil
                }
                righe.append(RigaRis(
                    id: "srv:\(kind):\(ref)", tipo: tipo, titolo: h.title ?? "",
                    sottotitolo: risUnisci([etichetta, h.project, Tempo.relativo(h.ts)]),
                    anteprima: snip.isEmpty ? nil : snip, quando: h.ts, progetto: h.project, ruolo: nil,
                    apri: dest, unione: unione))
                per[tipo] = righe
            }
            if inAmbito(.turno) {
                var righe: [RigaRis] = []
                for t in r.turni ?? [] {
                    let sessione = t.sessione ?? ""
                    let titolo = sessioniPerId[sessione]?.title ?? t.progetto ?? tr("Conversazione", "Conversation")
                    righe.append(RigaRis(
                        id: "turno:\(t.identita)", tipo: .turno, titolo: titolo,
                        sottotitolo: risUnisci([t.progetto, ruoloTesto(t.ruolo), Tempo.relativo(t.ts)]),
                        anteprima: t.frammento, quando: t.ts, progetto: t.progetto,
                        ruolo: ruoloTesto(t.ruolo),
                        apri: sessione.isEmpty ? .nessuna : .sessione(sessione), unione: nil))
                }
                per[.turno] = righe
            }
        }
        return TipoRis.allCases.compactMap { t in
            guard let r = per[t], !r.isEmpty else { return nil }
            return GruppoRis(tipo: t, righe: r)
        }
    }

    private func ruoloTesto(_ r: String?) -> String? {
        switch r {
        case "user": return tr("Tu", "You")
        case "assistant": return "Claude"
        default: return nil
        }
    }

    // MARK: vista

    /// Sta ancora cercando nelle conversazioni (l'unico gruppo che arriva dal server da solo).
    private var cercaNelleConversazioni: Bool {
        archivio.ricercaInCorso && inAmbito(.turno) && q.count >= 2
    }

    var body: some View {
        let elenco = gruppi()
        let tutte = elenco.flatMap { $0.righe }
        Group {
            if elenco.isEmpty {
                vuoto
            } else {
                List(selection: $scelto) {
                    ForEach(elenco) { g in
                        Section {
                            ForEach(g.righe.prefix(limite(g.tipo))) { r in
                                RigaRisultato(riga: r, termini: risTermini(q))
                                    .tag(r.id)
                            }
                            if g.righe.count > limite(g.tipo) {
                                Button {
                                    espansi.insert(g.tipo)
                                } label: {
                                    Text(tr("Mostra altri \(g.righe.count - limite(g.tipo))",
                                            "Show \(g.righe.count - limite(g.tipo)) more"))
                                }
                                .collegamento()
                            }
                        } header: {
                            intestazione(g)
                        }
                    }
                }
                .listStyle(.inset)
                .contextMenu(forSelectionType: String.self) { ids in
                    if let r = tutte.first(where: { ids.contains($0.id) }), r.apri != .nessuna {
                        Button(tr("Apri", "Open")) { VistaRisultati.apri(r) }
                    }
                } primaryAction: { ids in
                    if let r = tutte.first(where: { ids.contains($0.id) }) { VistaRisultati.apri(r) }
                }
            }
        }
        // l'Inspector e' della finestra (Guscio/Ispettore.swift): la riga scelta gli passa il suo dettaglio
        .onChange(of: tutte.first(where: { $0.id == scelto }), initial: true) { _, corrente in
            pubblica(corrente)
        }
        .onDisappear { ControlliVista.condiviso.dettaglioRisultato = nil }
        // solo nelle istantanee con --primo-risultato: sceglie la prima riga, per fotografare l'Inspector
        .onChange(of: tutte.first?.id, initial: true) { _, primo in
            if scelto == nil, let p = primo, Istantanee.attive,
               CommandLine.arguments.contains("--primo-risultato") { scelto = p }
        }
    }

    private func limite(_ t: TipoRis) -> Int {
        (archivio.ambito == .tutto && !espansi.contains(t)) ? Self.limiteTutto : Int.max / 2
    }

    @ViewBuilder private func intestazione(_ g: GruppoRis) -> some View {
        HStack(spacing: 6) {
            Text(g.tipo.titolo)
            if g.tipo == .turno && cercaNelleConversazioni {
                ProgressView().controlSize(.small)
            }
        }
    }

    @ViewBuilder private var vuoto: some View {
        if cercaNelleConversazioni {
            // niente di locale e il server sta ancora cercando: un indicatore piccolo, non una pagina
            ProgressView().controlSize(.small)
        } else {
            ContentUnavailableView(
                tr("Nessun risultato", "No results"),
                systemImage: "magnifyingglass",
                description: Text(archivio.raggiungibile
                                  ? tr("Niente per \"\(q)\".", "Nothing for \"\(q)\".")
                                  : tr("Niente per \"\(q)\" nei dati che ci sono. Il server non risponde.",
                                       "Nothing for \"\(q)\" in the data at hand. The server is not answering.")))
        }
    }

    private func pubblica(_ riga: RigaRis?) {
        let termini = risTermini(q)
        ControlliVista.condiviso.dettaglioRisultato = riga.map { r in
            AnyView(DettaglioRisultato(riga: r, termini: termini) { VistaRisultati.apri(r) })
        }
    }

    // MARK: azioni

    private static func apri(_ r: RigaRis) {
        let archivio = Archivio.condiviso
        switch r.apri {
        case .task(let id):
            archivio.vai(.task)
            archivio.taskScelto = id
        case .progetto(let k):
            archivio.vai(.progetti, progetto: k)
        case .sessione(let sid):
            archivio.vai(.archivio)
            archivio.sessioneScelta = sid
        case .memoria(let nome):
            archivio.vai(.memoria)
            archivio.memoriaScelta = nome
        case .post(let id):
            archivio.vai(.social)
            archivio.postScelto = id
        case .nessuna:
            break
        }
    }
}

// MARK: - una riga

private struct RigaRisultato: View {
    let riga: RigaRis
    let termini: [String]

    /// L'anteprima si mostra se dice qualcosa che il titolo non dice gia'.
    private var anteprima: String? {
        guard let a = riga.anteprima, !a.isEmpty else { return nil }
        return (riga.tipo == .turno || !risRipete(a, riga.titolo)) ? a : nil
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: riga.tipo.simbolo)
                .foregroundStyle(.secondary)
                .frame(width: 20)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                if riga.tipo == .turno {
                    if let a = anteprima { Text(risFrammento(a)).lineLimit(2) }
                    Text(risUnisci([riga.titolo, riga.sottotitolo]))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                } else {
                    Text(risEvidenzia(riga.titolo, termini)).lineLimit(1)
                    if let a = anteprima {
                        Text(a.contains("«") ? risFrammento(a) : risEvidenzia(a, termini))
                            .font(.callout).foregroundStyle(.secondary).lineLimit(2)
                        if riga.tipo == .sessione || riga.tipo == .task || riga.tipo == .altro, !riga.sottotitolo.isEmpty {
                            Text(riga.sottotitolo).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                    } else if !riga.sottotitolo.isEmpty {
                        Text(risEvidenzia(riga.sottotitolo, termini))
                            .font(.callout).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - il dettaglio (Inspector)

private struct DettaglioRisultato: View {
    let riga: RigaRis
    let termini: [String]
    let apri: () -> Void

    var body: some View {
        Form {
            Section {
                if riga.tipo == .turno {
                    Text(riga.titolo).font(.headline).textSelection(.enabled)
                } else {
                    Text(risEvidenzia(riga.titolo, termini)).font(.headline).textSelection(.enabled)
                }
                if let a = riga.anteprima, !a.isEmpty, riga.tipo == .turno || !risRipete(a, riga.titolo) {
                    Text(a.contains("«") ? risFrammento(a) : risEvidenzia(a, termini))
                        .font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                } else if !riga.sottotitolo.isEmpty, riga.tipo == .progetto || riga.tipo == .memoria {
                    Text(riga.sottotitolo).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }
            Section {
                LabeledContent(tr("Tipo", "Type"), value: riga.tipo.singolare)
                if let p = riga.progetto, !p.isEmpty { LabeledContent(tr("Progetto", "Project"), value: p) }
                if let r = riga.ruolo { LabeledContent(tr("Chi", "Who"), value: r) }
                if let q = riga.quando, !q.isEmpty { LabeledContent(tr("Quando", "When"), value: Tempo.relativo(q)) }
            }
            if riga.apri != .nessuna {
                Section {
                    Button(action: apri) {
                        Label(tr("Apri", "Open"), systemImage: "arrow.up.forward.square")
                    }
                }
            }
        }
        .formStyle(.grouped)
    }
}
