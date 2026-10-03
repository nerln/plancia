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

private struct Esito: Identifiable {
    let id = UUID()
    let testo: String
    let errore: Bool
}

/// Dove sta il messaggio dell'ultima azione: sotto l'ultima sezione che si vede.
private enum PosizionePiede { case riepilogo, prossimi, proposte }

// MARK: - i gruppi di Prossimi

private struct GruppoProssimi: Identifiable {
    let id: String
    let nome: String
    let righe: [RigaProssimo]
}

/// Sette righe in tutto, poi "Mostra altri".
private let tettoProssimi = 7

/// La larghezza di lettura della colonna.
private let larghezzaLettura: CGFloat = 720

// MARK: - la vista

struct VistaOggi: View {
    @Environment(Archivio.self) private var archivio

    @State private var mostraTutti = false
    @State private var riepilogoAperto = false
    @State private var lettura: Task<Void, Never>?
    @State private var occupate: Set<String> = []
    @State private var esito: Esito?
    @State private var daConfermare: LancioPronto?

    var body: some View {
        Group {
            if vuotoTotale {
                vuoto
            } else {
                colonna
            }
        }
        .task(id: esito?.id) {
            guard esito != nil else { return }
            try? await Task.sleep(nanoseconds: 8_000_000_000)
            if !Task.isCancelled { esito = nil }
        }
        .confirmationDialog(
            daConfermare?.titolo ?? "",
            isPresented: Binding(get: { daConfermare != nil },
                                 set: { if !$0 { daConfermare = nil } }),
            titleVisibility: .visible,
            presenting: daConfermare) { l in
            Button(l.azione) { Task { await lancia(l) } }
            Button(tr("Annulla", "Cancel"), role: .cancel) {}
        } message: { l in
            // il piano PRIMA di partire: la sessione originale, una copia, o una nuova
            Text(l.testo)
        }
    }

    // MARK: struttura

    /// La colonna di lettura: i margini laterali portano il contenuto a 720 punti al
    /// massimo, ma la barra di scorrimento resta sul bordo della finestra.
    private var colonna: some View {
        GeometryReader { g in
            Form {
                if let testo = testoRiepilogo {
                    Section {
                        rigaRiepilogo(testo)
                    } footer: {
                        piede(.riepilogo)
                    }
                }
                sezioneProssimi
                if !archivio.proposte.isEmpty {
                    sezioneProposte
                }
            }
            .formStyle(.grouped)
            .contentMargins(.horizontal, max(0, (g.size.width - larghezzaLettura) / 2), for: .scrollContent)
        }
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
                if let l = lettura {
                    l.cancel()
                    Player.shared.stop()
                } else {
                    lettura = Task {
                        await leggi()
                        lettura = nil
                    }
                }
            } label: {
                Label(lettura != nil ? tr("Ferma", "Stop") : tr("Leggi", "Read aloud"),
                      systemImage: lettura != nil ? "stop.fill" : "speaker.wave.2")
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

    /// Una sezione per area, con "Prossimi" come titolo sopra la prima: niente righe di
    /// intestazione dentro il riquadro, ogni area ha il suo.
    @ViewBuilder private var sezioneProssimi: some View {
        let tutti = gruppi
        let totale = tutti.reduce(0) { $0 + $1.righe.count }
        let tetto = mostraTutti ? Int.max : tettoProssimi
        let visibili = ritaglia(tutti, a: tetto)
        let mostrate = visibili.reduce(0) { $0 + $1.righe.count }

        if tutti.isEmpty {
            Section {
                Text(tr("Niente in arrivo", "Nothing coming up")).foregroundStyle(.secondary)
            } header: {
                Text(tr("Prossimi", "Up next")).font(.headline)
            }
        }
        ForEach(Array(visibili.enumerated()), id: \.element.id) { i, g in
            Section {
                ForEach(g.righe, id: \.identita) { r in rigaProssimo(r) }
                if i == visibili.count - 1 && totale > mostrate {
                    Button(tr("Mostra altri \(totale - mostrate)", "Show \(totale - mostrate) more")) {
                        mostraTutti = true
                    }
                    .collegamento()
                }
            } header: {
                VStack(alignment: .leading, spacing: 12) {
                    if i == 0 { Text(tr("Prossimi", "Up next")).font(.headline) }
                    Text(g.nome).font(.subheadline).foregroundStyle(.secondary)
                }
            } footer: {
                if i == visibili.count - 1 { piede(.prossimi) }
            }
        }
    }

    /// Le prime `n` righe in tutto, area per area.
    private func ritaglia(_ g: [GruppoProssimi], a n: Int) -> [GruppoProssimi] {
        var restanti = n
        var fuori: [GruppoProssimi] = []
        for gr in g where restanti > 0 {
            let k = min(gr.righe.count, restanti)
            restanti -= k
            fuori.append(GruppoProssimi(id: gr.id, nome: gr.nome, righe: Array(gr.righe.prefix(k))))
        }
        return fuori
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
                        .accessibilityLabel(scaduta
                            ? tr("Scaduto il \(Tempo.giorno(s))", "Overdue since \(Tempo.giorno(s))")
                            : tr("Scade il \(Tempo.giorno(s))", "Due \(Tempo.giorno(s))"))
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
            piede(.proposte)
        }
    }

    private var doveIlPiede: PosizionePiede {
        if !archivio.proposte.isEmpty { return .proposte }
        if !gruppi.isEmpty { return .prossimi }
        return .riepilogo
    }

    @ViewBuilder private func piede(_ dove: PosizionePiede) -> some View {
        if dove == doveIlPiede, let e = esito {
            Text(e.testo).foregroundStyle(e.errore ? Color.red : Color.secondary)
        }
    }

    private func etichetta(_ p: Proposta) -> String {
        switch p.azione?.tipo {
        case "manda": return tr("Riprendi", "Resume")
        case "rilancia": return tr("Rilancia", "Relaunch")
        default: return tr("Apri", "Open")
        }
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
        esito = nil
        do {
            let r = try await archivio.cliente.scrivi(
                "POST", "/api/recap",
                corpo: ["voce": true, "lang": Lingua.condivisa.codice],
                compartimento: archivio.compartimento, timeout: 120)
            try Task.checkCancellation()
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
            while Player.shared.isPlaying && !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 400_000_000)
            }
        } catch is CancellationError {
            Player.shared.stop()
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
                // nel Terminale, nella sessione del task; se non c'e' piu' lo dice prima
                if let piano = await archivio.pianoRipresa(task: t), piano.modo == "nuova" {
                    daConfermare = LancioPronto(nuovaNelTerminale: "/api/riprendi/\(t)", piano: piano,
                                                agente: az?.agente ?? "claude")
                    return
                }
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
                var corpo: [String: Any] = ["titolo": titolo, "agente": az?.agente ?? "claude",
                                            "scrive": false, "lang": Lingua.condivisa.codice]
                if let k = az?.progetto ?? p.azione?.progetto, !k.isEmpty { corpo["progetto"] = k }
                await mostraPiano(percorso: "/api/cantiere", corpo: corpo, agente: az?.agente ?? "claude")
            }

        case "rilancia":
            // il lancio riprende la conversazione in cui era girato (o quella del suo task);
            // il server lo sa dall'id del lancio
            guard let id = az?.run ?? p.azione?.run else { return }
            let corpo: [String: Any] = ["run": id, "scrive": false, "lang": Lingua.condivisa.codice]
            await mostraPiano(percorso: "/api/cantiere", corpo: corpo, agente: "claude")

        default:
            break
        }
    }

    /// Chiede al server cosa farebbe il lancio (anteprima) e lo mostra prima di partire.
    private func mostraPiano(percorso: String, corpo: [String: Any], agente: String) async {
        guard let piano = await archivio.anteprima(percorso, corpo) else {
            esito = Esito(testo: tr("Non riesco a sapere cosa farebbe il lancio: il server non risponde.",
                                    "Can't tell what the run would do: the server isn't answering."),
                          errore: true)
            return
        }
        if !piano.parte {
            esito = Esito(testo: piano.frase, errore: false)
            return
        }
        daConfermare = LancioPronto(percorso: percorso, corpo: corpo, piano: piano, agente: agente)
    }

    private func lancia(_ l: LancioPronto) async {
        let r = await archivio.scriviRisposta("POST", l.percorso, corpo: l.corpo)
        switch r {
        case .success(let j):
            if j["lanciato"]?.testo == "false" {
                esito = Esito(testo: l.piano.frase, errore: false)   // nel frattempo si e' aperta
            } else if l.corpo["apri"] != nil {
                esito = Esito(testo: j["riga"]?.testo ?? j["messaggio"]?.testo ?? tr("Avviato", "Started"),
                              errore: false)
            } else {
                esito = Esito(testo: tr("Lancio avviato. ", "Run started. ") + l.piano.frase, errore: false)
            }
        case .failure(let e): esito = Esito(testo: e.localizedDescription, errore: true)
        }
    }
}
