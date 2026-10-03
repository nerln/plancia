// Social: la coda dei post, per stato, con l'anteprima dell'immagine; il dettaglio sta
// nell'Inspector e da li' si cambia lo stato.
//   - i dati vengono dallo Store; la selezione e' `postScelto` (l'id del post);
//   - le scritture passano da `archivio.scrivi`: PATCH /api/posts/<id> per lo stato,
//     POST /api/posts per una bozza nuova (⌘N);
//   - l'immagine e' un file locale (il campo media e' un percorso): si legge da disco con
//     ImageIO, ridotta, fuori dal thread principale. Niente richieste di rete.

import SwiftUI
import AppKit
import ImageIO

// MARK: - stati e piattaforme

private let statiPost = ["programmato", "approvato", "bozza", "idea", "pubblicato", "scartato"]
private let statiInCoda: Set<String> = ["idea", "bozza", "approvato", "programmato"]

@MainActor
private func testoStato(_ s: String) -> String {
    switch s {
    case "idea": return tr("Idea", "Idea")
    case "bozza": return tr("Bozza", "Draft")
    case "approvato": return tr("Pronto", "Ready")
    case "programmato": return tr("Programmato", "Scheduled")
    case "pubblicato": return tr("Pubblicato", "Published")
    case "scartato": return tr("Scartato", "Discarded")
    default: return s
    }
}

private func simboloStatoPost(_ s: String) -> String {
    switch s {
    case "idea": return "lightbulb"
    case "bozza": return "pencil"
    case "approvato": return "checkmark.circle"
    case "programmato": return "clock"
    case "pubblicato": return "paperplane.fill"
    case "scartato": return "xmark.circle"
    default: return "circle"
    }
}

private func nomePiattaforma(_ p: String?) -> String {
    switch (p ?? "").lowercased() {
    case "x": return "X"
    case "linkedin": return "LinkedIn"
    case "bluesky": return "Bluesky"
    case "mastodon": return "Mastodon"
    case "hn": return "Hacker News"
    case "reddit": return "Reddit"
    default: return p ?? ""
    }
}

enum FiltroPost: String, CaseIterable, Identifiable {
    case inCoda, pubblicati, tutti
    var id: String { rawValue }
    @MainActor var titolo: String {
        switch self {
        case .inCoda: return tr("In coda", "Queue")
        case .pubblicati: return tr("Pubblicati", "Published")
        case .tutti: return tr("Tutti", "All")
        }
    }
    func passa(_ stato: String) -> Bool {
        switch self {
        case .inCoda: return statiInCoda.contains(stato)
        case .pubblicati: return stato == "pubblicato"
        case .tutti: return true
        }
    }
}

private extension Post {
    var stato: String { status ?? "bozza" }
    var testo: String { (text ?? "").trimmed }
    var percorsoImmagine: String { (media ?? "").trimmed }
}

extension Archivio {
    /// Il post scelto, per l'Inspector della finestra (Guscio/Ispettore.swift).
    func postSceltoOra() -> Post? {
        guard let id = postScelto else { return nil }
        return post.first { $0.identita == id }
    }
}

// MARK: - la vista

struct VistaSocial: View {
    @Environment(Archivio.self) private var archivio

    private let c = ControlliVista.condiviso

    /// I post che passano il filtro, per stato nell'ordine della coda.
    private var gruppi: [(stato: String, post: [Post])] {
        let filtro = c.filtroPost
        let visibili = archivio.post.filter { filtro.passa($0.stato) }
        return statiPost.compactMap { s in
            let p = visibili.filter { $0.stato == s }.sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
            return p.isEmpty ? nil : (s, p)
        }
    }

    var body: some View {
        @Bindable var a = archivio
        @Bindable var cc = c
        let elenco = gruppi
        Group {
            if elenco.isEmpty {
                vuoto
            } else {
                List(selection: $a.postScelto) {
                    ForEach(elenco, id: \.stato) { g in
                        Section {
                            ForEach(g.post, id: \.identita) { p in
                                RigaPost(post: p).tag(p.identita)
                            }
                        } header: {
                            Label("\(testoStato(g.stato)) · \(g.post.count)", systemImage: simboloStatoPost(g.stato))
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .sheet(isPresented: $cc.nuovaBozza) { NuovaBozza() }
    }

    @ViewBuilder private var vuoto: some View {
        if archivio.post.isEmpty {
            if !archivio.raggiungibile {
                ContentUnavailableView(
                    tr("Server non raggiungibile", "Server unreachable"),
                    systemImage: "bolt.horizontal.circle",
                    description: Text(tr("Appena risponde, i post compaiono qui.",
                                         "Posts appear here as soon as it answers.")))
            } else if archivio.ultimoAggiornamento == nil {
                ProgressView().controlSize(.small)
            } else {
                ContentUnavailableView(tr("Nessun post", "No posts"), systemImage: "text.bubble")
            }
        } else if c.filtroPost == .inCoda {
            ContentUnavailableView(tr("Coda vuota", "Queue is empty"), systemImage: "checkmark.circle")
        } else {
            ContentUnavailableView.search
        }
    }
}

// MARK: - una riga

private struct RigaPost: View {
    let post: Post

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            if !post.percorsoImmagine.isEmpty {
                AnteprimaImmagine(percorso: post.percorsoImmagine, lato: 44)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(post.testo).lineLimit(2)
                Text(sotto).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(.vertical, 2)
    }

    private var sotto: String {
        let data = post.stato == "pubblicato" ? post.publishedAt
            : (post.stato == "programmato" ? post.scheduledFor : post.updatedAt)
        return [nomePiattaforma(post.platform), post.project ?? "", Tempo.relativo(data)]
            .filter { !$0.isEmpty }.joined(separator: " · ")
    }
}

// MARK: - l'immagine

/// Un file immagine locale, ridotto. Se il file non c'e' o non si legge, un segnaposto.
private struct AnteprimaImmagine: View {
    let percorso: String
    /// Il lato del quadrato; 0 = larga quanto lo spazio, proporzioni dell'immagine.
    let lato: CGFloat
    @State private var immagine: CGImage?
    @State private var provata = false

    var body: some View {
        Group {
            if let i = immagine {
                if lato > 0 {
                    Image(decorative: i, scale: 2).resizable().scaledToFill()
                } else {
                    Image(decorative: i, scale: 2).resizable().scaledToFit()
                }
            } else {
                Image(systemName: "photo").foregroundStyle(.secondary)
            }
        }
        .frame(width: lato > 0 ? lato : nil, height: lato > 0 ? lato : nil)
        .frame(maxHeight: lato > 0 ? nil : 240)
        .background(immagine == nil ? AnyShapeStyle(.quaternary) : AnyShapeStyle(.clear))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .accessibilityLabel(tr("Immagine del post", "Post image"))
        .task(id: percorso) {
            provata = false
            let px = Int((lato > 0 ? lato : 480) * 2)
            immagine = await Miniatura.carica(percorso, massimo: px)
            provata = true
        }
    }

    var mancante: Bool { provata && immagine == nil }
}

private enum Miniatura {
    /// Legge e riduce il file fuori dal thread principale. Nil se non c'e' o non e' un'immagine.
    static func carica(_ percorso: String, massimo: Int) async -> CGImage? {
        await Task.detached(priority: .utility) { () -> CGImage? in
            let p = (percorso as NSString).expandingTildeInPath
            guard p.hasPrefix("/") else { return nil }
            let url = URL(fileURLWithPath: p) as CFURL
            guard let src = CGImageSourceCreateWithURL(url, nil) else { return nil }
            let opzioni: [CFString: Any] = [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: massimo,
            ]
            return CGImageSourceCreateThumbnailAtIndex(src, 0, opzioni as CFDictionary)
        }.value
    }

    static func esiste(_ percorso: String) -> Bool {
        let p = (percorso as NSString).expandingTildeInPath
        return p.hasPrefix("/") && FileManager.default.isReadableFile(atPath: p)
    }
}

// MARK: - il dettaglio (Inspector)

struct DettaglioPost: View {
    let post: Post
    @Environment(Archivio.self) private var archivio

    @State private var errore: String?
    @State private var lavora = false
    @State private var copiato = false

    var body: some View {
        Form {
            Section {
                Text(post.testo).textSelection(.enabled)
                if !post.percorsoImmagine.isEmpty {
                    if Miniatura.esiste(post.percorsoImmagine) {
                        AnteprimaImmagine(percorso: post.percorsoImmagine, lato: 0)
                    } else {
                        Label(tr("Immagine non trovata", "Image not found"), systemImage: "photo")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                }
            }
            Section {
                Picker(tr("Stato", "Status"), selection: statoScelto) {
                    ForEach(statiPost, id: \.self) { s in
                        Label(testoStato(s), systemImage: simboloStatoPost(s)).tag(s)
                    }
                }
                .disabled(lavora)
                LabeledContent(tr("Piattaforma", "Platform"), value: nomePiattaforma(post.platform))
                if let p = post.project, !p.isEmpty { LabeledContent(tr("Progetto", "Project"), value: p) }
                if let f = post.sourceRef, !f.isEmpty { LabeledContent(tr("Fonte", "Source"), value: f) }
                if let d = post.scheduledFor, !d.isEmpty {
                    LabeledContent(tr("Programmato", "Scheduled"), value: Tempo.giorno(d))
                }
                if let d = post.publishedAt, !d.isEmpty {
                    LabeledContent(tr("Pubblicato", "Published"), value: Tempo.giorno(d))
                }
                if let d = post.createdAt, !d.isEmpty {
                    LabeledContent(tr("Creato", "Created"), value: Tempo.relativo(d))
                }
            }
            Section {
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(post.testo, forType: .string)
                    copiato = true
                } label: {
                    Label(copiato ? tr("Copiato", "Copied") : tr("Copia il testo", "Copy text"),
                          systemImage: copiato ? "checkmark" : "doc.on.doc")
                }
                if let s = post.url, let u = URL(string: s), ["http", "https"].contains(u.scheme?.lowercased() ?? "") {
                    Link(destination: u) {
                        Label(tr("Apri il post", "Open post"), systemImage: "arrow.up.right.square")
                    }
                }
                if let k = post.projectKey, !k.isEmpty {
                    Button { archivio.vai(.progetti, progetto: k) } label: {
                        Label(tr("Apri progetto", "Open project"), systemImage: "folder")
                    }
                }
            }
            if let e = errore {
                Section { Text(e).font(.callout).foregroundStyle(.red) }
            }
        }
        .formStyle(.grouped)
        .onChange(of: post.identita) { copiato = false; errore = nil }
    }

    private var statoScelto: Binding<String> {
        Binding(get: { post.stato },
                set: { nuovo in
                    guard nuovo != post.stato, let id = post.id else { return }
                    Task { await cambia(id, nuovo) }
                })
    }

    private func cambia(_ id: Int, _ stato: String) async {
        lavora = true; errore = nil
        errore = await archivio.scrivi("PATCH", "/api/posts/\(id)", corpo: ["status": stato])
        lavora = false
    }
}

// MARK: - nuova bozza (⌘N)

struct NuovaBozza: View {
    @Environment(Archivio.self) private var archivio
    @Environment(\.dismiss) private var dismiss

    @State private var testo = ""
    @State private var piattaforma = "x"
    @State private var progetto = ""
    @State private var errore: String?
    @State private var lavora = false

    private let piattaforme = ["x", "linkedin", "bluesky", "mastodon", "hn", "reddit"]

    var body: some View {
        VStack(spacing: 0) {
            Form {
                TextField(tr("Testo", "Text"), text: $testo, axis: .vertical)
                    .lineLimit(4...8)
                Picker(tr("Piattaforma", "Platform"), selection: $piattaforma) {
                    ForEach(piattaforme, id: \.self) { Text(nomePiattaforma($0)).tag($0) }
                }
                Picker(tr("Progetto", "Project"), selection: $progetto) {
                    Text(tr("Nessuno", "None")).tag("")
                    ForEach(archivio.progetti.filter { $0.key != nil }, id: \.identita) { p in
                        Text(p.nome).tag(p.key ?? "")
                    }
                }
                if let e = errore { Text(e).foregroundStyle(.red) }
            }
            .formStyle(.grouped)
            HStack {
                Spacer()
                Button(tr("Annulla", "Cancel"), role: .cancel) { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button(tr("Salva bozza", "Save draft")) { Task { await salva() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(testo.trimmed.isEmpty || lavora)
            }
            .padding([.horizontal, .bottom])
        }
        .frame(width: 460)
        .task { if archivio.progetti.isEmpty { await archivio.carica(.social) } }
    }

    private func salva() async {
        lavora = true
        var c: [String: Any] = ["text": testo.trimmed, "platform": piattaforma, "status": "bozza"]
        if !progetto.isEmpty { c["project"] = progetto }
        let e = await archivio.scrivi("POST", "/api/posts", corpo: c)
        lavora = false
        if let e = e { errore = e } else { dismiss() }
    }
}
