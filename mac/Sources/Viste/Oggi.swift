// Oggi: quello che c'e' da sapere e da fare adesso, in una colonna di lettura.
//   - una riga col riepilogo della giornata, se c'e' gia' (/api/recap?solo_cache=1), e
//     "Leggi" per sentirlo;
//   - Prossimi (/api/prossimi): una riga per progetto, raggruppate per area, sette e poi
//     "Mostra altri"; un clic apre il progetto nella sezione Progetti;
//   - le proposte (/api/proposte) con un pulsante per riga.
// Il modello di stile e' Viste/Task.swift: dati dallo Store, controlli di sistema, font e
// colori semantici, niente vetro fatto a mano. La larghezza di lettura e' fissa (720 punti)
// e la colonna sta al centro: non si allarga con la finestra.

import SwiftUI

// MARK: - azioni delle proposte

/// L'azione di una proposta con tutti i campi che il server manda. Il modello del nucleo
/// (AzioneProposta) non ha `task_id`, `vista` e `agente`: qui si leggono, e solo quando
/// serve, cioe' al clic sul pulsante di una riga.
private struct AzioneCompleta: Decodable {
    @Lax var tipo: String?
    @Lax var run: Int?
    @Lax var titolo: String?
    @Lax var progetto: String?
    @Lax var modo: String?
    @Lax var taskId: Int?
    @Lax var vista: String?
    @Lax var agente: String?
}

private struct PropostaCompleta: Decodable {
    @Lax var id: String?
    @Lax var azione: AzioneCompleta?
}

/// Un lancio in background in attesa del "si" dell'utente.
private struct LancioDaConfermare: Identifiable {
    let id = UUID()
    let titolo: String
    let progetto: String?
    let agente: String
    let cwd: String?
    let taskId: Int?
}

private struct Esito {
    let testo: String
    let errore: Bool
}

// MARK: - i gruppi di Prossimi

private struct GruppoProssimi: Identifiable {
    let id: String
    let nome: String
    let righe: [RigaProssimo]
}

/// Sette righe in tutto, poi "Mostra altri".
private let tettoProssimi = 7

// MARK: - la vista

struct VistaOggi: View {
    @Environment(Archivio.self) private var archivio

    @State private var mostraTutti = false
    @State private var riepilogoAperto = false
    @State private var inLettura = false
    @State private var occupate: Set<String> = []
    @State private var esito: Esito?
    @State private var daConfermare: LancioDaConfermare?

    var body: some View {
        Group {
            if vuotoTotale {
                vuoto
            } else {
                colonna
            }
        }
        .confirmationDialog(
            tr("Avviare un lancio in background?", "Start a background run?"),
            isPresented: Binding(get: { daConfermare != nil },
                                 set: { if !$0 { daConfermare = nil } }),
            titleVisibility: .visible,
            presenting: daConfermare) { l in
            Button(tr("Avvia senza modificare file", "Start without changing files")) {
                Task { await lancia(l) }
            }
            Button(tr("Annulla", "Cancel"), role: .cancel) {}
        } message: { l in
            Text(tr("Parte \(nomeAgente(l.agente)) in background, in sola lettura.",
                    "\(nomeAgente(l.agente)) starts in the background, read-only."))
        }
    }

    // MARK: struttura

    private var colonna: some View {
        Form {
            if let testo = testoRiepilogo {
                Section { rigaRiepilogo(testo) }
            }
            sezioneProssimi
            if !archivio.proposte.isEmpty {
                sezioneProposte
            }
        }
        .formStyle(.grouped)
        .frame(maxWidth: 720)
        .frame(maxWidth: .infinity)
    }

    // MARK: riepilogo

    private var testoRiepilogo: String? {
        let t = (archivio.recap?.testo ?? "").trimmed
        return t.isEmpty ? nil : t
    }

    private func rigaRiepilogo(_ testo: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            // una riga sola; un clic la apre per intero
            Button {
                riepilogoAperto.toggle()
            } label: {
                Text(testo)
                    .lineLimit(riepilogoAperto ? nil : 1)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help(riepilogoAperto ? tr("Riduci", "Collapse") : tr("Mostra tutto", "Show all"))
            .accessibilityLabel(testo)

            Button {
                Task { await leggi() }
            } label: {
                Label(inLettura ? tr("Ferma", "Stop") : tr("Leggi", "Read aloud"),
                      systemImage: inLettura ? "stop.fill" : "speaker.wave.2")
            }
            .controlSize(.small)
        }
    }

    // MARK: prossimi

    private var gruppi: [GruppoProssimi] {
        var g: [GruppoProssimi] = (archivio.prossimi?.aree ?? []).map {
            GruppoProssimi(id: $0.identita, nome: $0.name ?? $0.key ?? "", righe: $0.righe ?? [])
        }
        let senza = archivio.prossimi?.senzaArea ?? []
        if !senza.isEmpty {
            g.append(GruppoProssimi(id: "senza-area", nome: tr("Senza area", "No area"), righe: senza))
        }
        return g.filter { !$0.righe.isEmpty }
    }

    private var sezioneProssimi: some View {
        let tutti = gruppi
        let totale = tutti.reduce(0) { $0 + $1.righe.count }
        var restanti = mostraTutti ? Int.max : tettoProssimi
        var visibili: [GruppoProssimi] = []
        for g in tutti where restanti > 0 {
            let n = min(g.righe.count, restanti)
            restanti -= n
            visibili.append(GruppoProssimi(id: g.id, nome: g.nome, righe: Array(g.righe.prefix(n))))
        }
        let mostrate = visibili.reduce(0) { $0 + $1.righe.count }

        return Section {
            if tutti.isEmpty {
                Text(tr("Niente in arrivo", "Nothing coming up")).foregroundStyle(.secondary)
            }
            ForEach(visibili) { g in
                Text(g.nome)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .accessibilityAddTraits(.isHeader)
                ForEach(g.righe, id: \.identita) { r in rigaProssimo(r) }
            }
            if totale > mostrate {
                Button(tr("Mostra altri \(totale - mostrate)", "Show \(totale - mostrate) more")) {
                    mostraTutti = true
                }
                .buttonStyle(.link)
            }
        } header: {
            Text(tr("Prossimi", "Up next"))
        }
    }

    private func rigaProssimo(_ r: RigaProssimo) -> some View {
        let scaduta = Tempo.scaduto(r.scadenza)
        return Button {
            if let k = r.key { archivio.vai(.progetti, progetto: k) }
        } label: {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(r.name ?? r.key ?? "")
                    if let c = r.cosa, !c.isEmpty {
                        Text(c)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 12)
                if let s = r.scadenza, !s.isEmpty {
                    Text(Tempo.giorno(s))
                        .font(.callout)
                        .monospacedDigit()
                        .foregroundStyle(scaduta ? Color.red : Color.secondary)
                }
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tertiary)
                    .accessibilityHidden(true)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(r.key == nil)
        .accessibilityHint(tr("Apre il progetto", "Opens the project"))
    }

    // MARK: proposte

    private var sezioneProposte: some View {
        Section {
            ForEach(archivio.proposte, id: \.identita) { p in
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text(p.testo ?? "")
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Button(etichetta(p)) {
                        Task { await esegui(p) }
                    }
                    .controlSize(.small)
                    .disabled(occupate.contains(p.identita))
                }
            }
        } header: {
            Text(tr("Proposte", "Suggestions"))
        } footer: {
            if let e = esito {
                Text(e.testo).foregroundStyle(e.errore ? Color.red : Color.secondary)
            }
        }
    }

    private func etichetta(_ p: Proposta) -> String {
        switch p.azione?.tipo {
        case "manda": return tr("Riprendi", "Resume")
        case "rilancia": return tr("Rilancia", "Retry")
        default: return tr("Apri", "Open")
        }
    }

    private func nomeAgente(_ a: String) -> String {
        a.lowercased() == "codex" ? "Codex" : "Claude"
    }

    // MARK: stati vuoti

    private var vuotoTotale: Bool {
        testoRiepilogo == nil && gruppi.isEmpty && archivio.proposte.isEmpty
    }

    @ViewBuilder private var vuoto: some View {
        if archivio.prossimi == nil {
            if archivio.raggiungibile {
                ProgressView().controlSize(.small)
            } else {
                ContentUnavailableView(
                    tr("Server non raggiungibile", "Server unreachable"),
                    systemImage: "bolt.horizontal.circle",
                    description: Text(tr("Appena risponde, il giorno compare qui.",
                                         "Your day appears here as soon as it answers.")))
            }
        } else {
            ContentUnavailableView(
                tr("Niente in arrivo", "Nothing coming up"),
                systemImage: "sun.max")
        }
    }

    // MARK: azioni

    private func leggi() async {
        if inLettura {
            Player.shared.stop()
            return
        }
        inLettura = true
        esito = nil
        defer { inLettura = false }
        do {
            let r = try await archivio.cliente.scrivi(
                "POST", "/api/recap",
                corpo: ["voce": true, "lang": Lingua.condivisa.codice],
                compartimento: archivio.compartimento, timeout: 120)
            if let f = r["file"]?.testo, !f.isEmpty {
                Player.shared.play(path: f)
            } else if let u = r["url"]?.testo, let url = URL(string: Conf.base + u) {
                let (tmp, _) = try await URLSession.shared.download(from: url)
                let dest = FileManager.default.temporaryDirectory
                    .appendingPathComponent("plancia-\(UUID().uuidString).wav")
                try FileManager.default.moveItem(at: tmp, to: dest)
                Player.shared.play(path: dest.path)
            } else {
                esito = Esito(testo: r["nota_voce"]?.testo ?? tr("La voce non è disponibile.", "Voice is not available."),
                              errore: true)
                return
            }
            while Player.shared.isPlaying {
                try? await Task.sleep(nanoseconds: 400_000_000)
            }
        } catch {
            esito = Esito(testo: error.localizedDescription, errore: true)
        }
    }

    /// Il pulsante di una proposta. Il server manda i dettagli dell'azione (a quale task si
    /// riferisce, a quale vista porta): si rileggono qui, al clic, invece di caricarli
    /// due volte a ogni aggiornamento.
    private func esegui(_ p: Proposta) async {
        let chiave = p.identita
        occupate.insert(chiave)
        defer { occupate.remove(chiave) }
        esito = nil

        let complete = try? await archivio.cliente.elenco(
            PropostaCompleta.self, "/api/proposte",
            query: ["lang": Lingua.condivisa.codice], compartimento: archivio.compartimento)
        let az = complete?.first { $0.id == p.id }?.azione

        switch p.azione?.tipo {
        case "vai":
            if let s = Sezione.da(nome: az?.vista) {
                archivio.vai(s)
            } else {
                esito = Esito(testo: tr("Non so dove aprirlo.", "Can't tell where to open it."), errore: true)
            }

        case "manda":
            if let t = az?.taskId {
                let r = await archivio.scriviRisposta("POST", "/api/riprendi/\(t)", corpo: ["apri": true])
                switch r {
                case .success(let j):
                    esito = Esito(testo: j["riga"]?.testo ?? j["messaggio"]?.testo ?? tr("Avviato", "Started"),
                                  errore: false)
                case .failure(let e):
                    esito = Esito(testo: e.localizedDescription, errore: true)
                }
            } else {
                // senza un task di Plancia non c'e' una sessione da riprendere: parte un lancio
                let titolo = (az?.titolo ?? p.azione?.titolo ?? p.testo ?? "").trimmed
                guard !titolo.isEmpty else { return }
                daConfermare = LancioDaConfermare(
                    titolo: titolo, progetto: az?.progetto ?? p.azione?.progetto,
                    agente: az?.agente ?? "claude", cwd: nil, taskId: nil)
            }

        case "rilancia":
            guard let id = az?.run ?? p.azione?.run else { return }
            do {
                let l = try await archivio.cliente.ottieni(
                    Lancio.self, "/api/runs/\(id)", compartimento: archivio.compartimento)
                let titolo = String((l.prompt ?? p.testo ?? "").trimmed.prefix(200))
                guard !titolo.isEmpty else { return }
                daConfermare = LancioDaConfermare(
                    titolo: titolo, progetto: nil, agente: l.agente ?? "claude",
                    cwd: l.cwd, taskId: l.taskId)
            } catch {
                esito = Esito(testo: error.localizedDescription, errore: true)
            }

        default:
            break
        }
    }

    private func lancia(_ l: LancioDaConfermare) async {
        var corpo: [String: Any] = ["titolo": l.titolo, "agente": l.agente, "scrive": false,
                                    "lang": Lingua.condivisa.codice]
        if let k = l.progetto, !k.isEmpty { corpo["progetto"] = k }
        if let c = l.cwd, !c.isEmpty { corpo["cwd"] = c }
        if let t = l.taskId { corpo["task_id"] = t }
        let r = await archivio.scriviRisposta("POST", "/api/cantiere", corpo: corpo)
        switch r {
        case .success: esito = Esito(testo: tr("Lancio avviato", "Run started"), errore: false)
        case .failure(let e): esito = Esito(testo: e.localizedDescription, errore: true)
        }
    }
}
