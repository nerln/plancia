// Il pannello di Jarvis in SwiftUI: vetro di sistema, un'onda che vive, il testo che scorre
// mentre arriva, e la scheda di conferma quando c'e' qualcosa da approvare.
//
// Regole di design: solo font e colori semantici (i colori di sistema per gli stati), il vetro
// solo sul corpo del pannello (mai vetro su vetro: i controlli dentro sono bordati o
// prominenti, non "glass"), niente ombre finte. Il pulsante Conferma NON e' l'azione
// predefinita: Invio non conferma mai, si preme.

import AppKit
import SwiftUI

struct JarvisVista: View {
    @Bindable var m: JarvisModello
    @State private var scritto = ""
    @FocusState private var campoAttivo: Bool

    private let larghezza: CGFloat = 400

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            intestazione
            OndaJarvis(tipo: tipoOnda, livello: m.livello, colore: colore, altezza: altezzaOnda,
                       pausa: !m.visibile)
            testi
            if let p = m.proposta {
                SchedaProposta(proposta: p, inCorso: m.confermaInCorso,
                               conferma: { m.conferma() }, annulla: { m.rifiuta() })
                    .transition(.blurReplace.combined(with: .scale(0.96, anchor: .bottom)))
            }
            controlli
            piede
        }
        .padding(18)
        .frame(width: larghezza)
        .glassEffect(.regular, in: .rect(cornerRadius: 30, style: .continuous))
        .animation(.smooth(duration: 0.35), value: m.proposta)
        .animation(.smooth(duration: 0.35), value: m.fase)
        .animation(.smooth(duration: 0.3), value: m.messaggio)
        .animation(.smooth(duration: 0.3), value: altezzaOnda)
        .onExitCommand { m.esc() }
    }

    // MARK: stato

    private var colore: Color {
        switch m.fase {
        case .ascolta: return .orange
        case .pensa: return .blue
        case .risponde: return .green
        case .conferma: return .yellow
        case .errore: return .red
        case .inattivo: return .secondary
        }
    }

    /// L'onda si fa piccola quando non c'e' niente da ascoltare: a riposo, con una scheda o un errore.
    private var altezzaOnda: CGFloat {
        switch m.fase {
        case .ascolta, .pensa, .risponde: return 72
        default: return 30
        }
    }

    private var tipoOnda: OndaJarvis.Tipo {
        switch m.fase {
        case .ascolta: return .ascolta
        case .pensa: return .pensa
        case .risponde: return m.parla ? .parla : .pensa
        default: return .quieta
        }
    }

    private var titoloStato: String {
        let it = m.lingua == "it"
        if m.microfonoInApertura && !m.microfonoAcceso { return it ? "Apro il microfono" : "Opening the microphone" }
        switch m.fase {
        case .ascolta: return it ? "Microfono acceso" : "Microphone on"
        case .pensa: return it ? "Sto pensando" : "Thinking"
        case .risponde: return m.parla ? (it ? "Parlo" : "Speaking") : (it ? "Rispondo" : "Answering")
        case .conferma: return it ? "Aspetto la tua conferma" : "Waiting for your confirmation"
        case .errore: return it ? "Non ci sono riuscito" : "That did not work"
        case .inattivo: return it ? "Jarvis" : "Jarvis"
        }
    }

    // MARK: parti

    private var intestazione: some View {
        HStack(spacing: 8) {
            Circle().fill(colore).frame(width: 9, height: 9)
                .opacity(m.fase == .ascolta ? 1 : 0.9)
                .overlay {
                    if m.fase == .ascolta {
                        Circle().stroke(colore, lineWidth: 1.5).scaleEffect(1.9).opacity(0.5)
                    }
                }
                .accessibilityHidden(true)
            Text(titoloStato)
                .font(.headline)
                .contentTransition(.opacity)
            if JarvisProva.attivo {
                Text(m.lingua == "it" ? "prova, niente audio" : "test, no audio")
                    .font(.caption).foregroundStyle(.secondary)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(.quaternary, in: Capsule())
            }
            Spacer(minLength: 4)
            if m.inAttivita {
                Button {
                    m.ferma()
                } label: {
                    Label(m.lingua == "it" ? "Ferma" : "Stop", systemImage: "stop.fill")
                        .labelStyle(.titleAndIcon)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .help(m.lingua == "it" ? "Ferma tutto (Esc)" : "Stop everything (Esc)")
            }
            Button {
                m.chiudi()
            } label: {
                Image(systemName: "xmark").imageScale(.small)
            }
            .buttonStyle(.borderless)
            .accessibilityLabel(m.lingua == "it" ? "Chiudi Jarvis" : "Close Jarvis")
        }
    }

    @ViewBuilder
    private var testi: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !m.trascritto.isEmpty {
                Text(m.trascritto)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
                    .truncationMode(.head)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityLabel((m.lingua == "it" ? "Hai detto: " : "You said: ") + m.trascritto)
            }
            if !m.pezzi.isEmpty {
                RispostaCheScorre(pezzi: m.pezzi)
            }
            if let msg = m.messaggio {
                Label {
                    Text(msg).font(.callout).fixedSize(horizontal: false, vertical: true)
                } icon: {
                    Image(systemName: m.erroreGrave ? "exclamationmark.triangle.fill" : "info.circle.fill")
                        .foregroundStyle(m.erroreGrave ? Color.red : Color.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            if m.trascritto.isEmpty, m.pezzi.isEmpty, m.messaggio == nil, m.fase == .inattivo {
                Text(m.lingua == "it"
                     ? "Tocca il microfono, o premi ⌥Spazio, e parla. Oppure scrivi qui sotto."
                     : "Tap the microphone, or press ⌥Space, and talk. Or type below.")
                    .font(.callout).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var controlli: some View {
        HStack(spacing: 8) {
            HStack(spacing: 6) {
                TextField(m.lingua == "it" ? "Scrivi a Jarvis" : "Write to Jarvis", text: $scritto)
                    .textFieldStyle(.plain)
                    .focused($campoAttivo)
                    .onSubmit { manda() }
                    .accessibilityLabel(m.lingua == "it" ? "Scrivi a Jarvis" : "Write to Jarvis")
                if !scritto.isEmpty {
                    Button { manda() } label: {
                        Image(systemName: "arrow.up.circle.fill").imageScale(.large)
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel(m.lingua == "it" ? "Invia" : "Send")
                }
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(.quaternary.opacity(0.7), in: Capsule())

            Button { m.toggleMicrofono() } label: {
                Image(systemName: m.microfonoAcceso ? "waveform" : "mic.fill")
                    .symbolEffect(.variableColor.iterative, isActive: m.microfonoAcceso)
                    .fontWeight(.semibold)
                    .frame(width: 22, height: 22)
            }
            .buttonStyle(.borderedProminent)
            .buttonBorderShape(.circle)
            // microfono acceso: rosso pieno con l'icona bianca piena (l'arancione di prima
            // diventava un giallo pallido, quasi senza contrasto con l'icona chiara)
            .tint(m.microfonoAcceso || m.microfonoInApertura ? .red : .accentColor)
            .controlSize(.large)
            .accessibilityLabel(m.microfonoAcceso
                                ? (m.lingua == "it" ? "Spegni il microfono e invia" : "Turn the microphone off and send")
                                : (m.lingua == "it" ? "Accendi il microfono" : "Turn the microphone on"))
            .help(m.microfonoAcceso
                  ? (m.lingua == "it" ? "Il microfono è acceso: premi per inviare quello che hai detto" : "The microphone is on: press to send what you said")
                  : (m.lingua == "it" ? "Accendi il microfono (⌥Spazio)" : "Turn the microphone on (⌥Space)"))
        }
    }

    private var piede: some View {
        HStack(spacing: 6) {
            Image(systemName: m.voceDescrizione.hasPrefix("Solo testo") || m.voceDescrizione.hasPrefix("Text only")
                  ? "speaker.slash" : "speaker.wave.2")
                .imageScale(.small)
            VStack(alignment: .leading, spacing: 1) {
                Text(m.voceDescrizione).lineLimit(1)
                if let a = m.voceAvviso {
                    Text(a).lineLimit(2).fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 4)
            if m.voicebox == .inAvvio {
                ProgressView().controlSize(.small)
            } else if m.offriVoicebox {
                Button(m.lingua == "it" ? "Avvia Voicebox" : "Start Voicebox") { m.avviaVoicebox(daUtente: true) }
                    .buttonStyle(.borderless)
                    .accessibilityLabel(m.lingua == "it" ? "Avvia Voicebox" : "Start Voicebox")
            }
            MenuImpostazioniJarvis(m: m)
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    private func manda() {
        let t = scritto
        scritto = ""
        m.invia(t)
    }
}

// MARK: - il testo che scorre

/// La risposta, con le parole appena arrivate che compaiono dal trasparente. Dopo mezzo secondo
/// dall'ultimo pezzo non c'e' piu' niente da animare e il disegno si ferma.
struct RispostaCheScorre: View {
    let pezzi: [JarvisModello.Pezzo]
    private let durata = 0.45

    var body: some View {
        let ultimo = pezzi.last?.arrivo ?? .distantPast
        ScrollViewReader { proxy in
            ScrollView {
                // Il disegno gira solo finche' c'e' una parola che sta comparendo, poi si ferma da solo.
                TimelineView(FinoA(fine: ultimo.addingTimeInterval(durata + 0.1))) { tl in
                    Text(attribuito(adesso: tl.date))
                        .font(.body)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
                Color.clear.frame(height: 1).id("fondo")
            }
            .frame(maxHeight: 210)
            .fixedSize(horizontal: false, vertical: true)
            .scrollIndicators(.hidden)
            .mask(
                LinearGradient(stops: [.init(color: .clear, location: 0), .init(color: .black, location: 0.06),
                                       .init(color: .black, location: 1)], startPoint: .top, endPoint: .bottom)
            )
            .onChange(of: pezzi.count) {
                withAnimation(.smooth(duration: 0.3)) { proxy.scrollTo("fondo", anchor: .bottom) }
            }
        }
    }

    private func attribuito(adesso: Date) -> AttributedString {
        var tutto = AttributedString()
        for p in pezzi {
            var a = AttributedString(p.testo)
            let eta = adesso.timeIntervalSince(p.arrivo)
            let opacita = max(0.0, min(1.0, eta / durata))
            a.foregroundColor = Color.primary.opacity(opacita)
            tutto.append(a)
        }
        return tutto
    }
}

/// Un fotogramma ogni trentesimo di secondo fino a `fine`, e poi basta.
struct FinoA: TimelineSchedule {
    let fine: Date

    func entries(from inizio: Date, mode: Mode) -> Entries {
        Entries(inizio: inizio, fine: fine)
    }

    struct Entries: Sequence, IteratorProtocol {
        var corrente: Date
        let fine: Date
        var finito = false

        init(inizio: Date, fine: Date) {
            corrente = inizio
            self.fine = fine
        }

        mutating func next() -> Date? {
            if finito { return nil }
            if corrente >= fine {
                finito = true
                return corrente
            }
            defer { corrente = Swift.min(fine, corrente.addingTimeInterval(1.0 / 30)) }
            return corrente
        }
    }
}

// MARK: - la scheda

struct SchedaProposta: View {
    let proposta: PropostaJarvis
    let inCorso: Bool
    let conferma: () -> Void
    let annulla: () -> Void

    private var it: Bool { Lingua.risolvi() == "it" }

    private var tinta: Color {
        switch proposta.rischio {
        case "lancia_scrive": return .red
        case "lancia": return .blue
        case "legge": return .gray
        default: return .orange
        }
    }

    private var simbolo: String {
        switch proposta.rischio {
        case "lancia_scrive": return "exclamationmark.triangle.fill"
        case "lancia": return "play.circle.fill"
        case "legge": return "arrow.triangle.2.circlepath"
        default: return "square.and.pencil"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(proposta.titolo, systemImage: simbolo)
                .font(.headline)
                .foregroundStyle(tinta)

            if !proposta.righe.isEmpty {
                Grid(alignment: .topLeading, horizontalSpacing: 10, verticalSpacing: 4) {
                    ForEach(Array(proposta.righe.enumerated()), id: \.offset) { _, r in
                        GridRow {
                            Text(r.chiave).foregroundStyle(.secondary)
                                .gridColumnAlignment(.trailing)
                            Text(r.valore).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .font(.callout)
            }

            if !proposta.avviso.isEmpty {
                Text(proposta.avviso)
                    .font(.caption)
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(tinta.opacity(0.14), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            }

            HStack {
                Button(it ? "Annulla" : "Cancel", action: annulla)
                    .buttonStyle(.bordered)
                Spacer()
                Button(action: conferma) {
                    HStack(spacing: 6) {
                        if inCorso { ProgressView().controlSize(.small) }
                        Text(it ? "Conferma" : "Confirm")
                    }
                }
                .buttonStyle(PulsanteConferma(colore: tinta))
                .disabled(inCorso)
                // niente .defaultAction: Invio non conferma
                .accessibilityLabel((it ? "Conferma: " : "Confirm: ") + proposta.titolo)
            }
        }
        .padding(14)
        .background(.quaternary.opacity(0.55), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).strokeBorder(tinta.opacity(0.35), lineWidth: 1))
        .accessibilityElement(children: .contain)
    }
}

/// Il pulsante che fa partire qualcosa: pieno, con il colore del rischio scurito perche' il testo
/// bianco si legga sempre, anche sul vetro e con la finestra non in primo piano.
struct PulsanteConferma: ButtonStyle {
    let colore: Color
    @Environment(\.isEnabled) private var attivo

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 16).padding(.vertical, 6)
            .background(colore.mix(with: .black, by: 0.3), in: Capsule())
            .opacity(attivo ? (configuration.isPressed ? 0.8 : 1) : 0.5)
            .contentShape(Capsule())
    }
}

// MARK: - il menu

struct MenuImpostazioniJarvis: View {
    @Bindable var m: JarvisModello

    var body: some View {
        let it = m.lingua == "it"
        Menu {
            let voci = VoceJarvis.vociDisponibili(lingua: m.lingua)
            Picker(selection: Binding(get: { Preferenze.voceScelta ?? "" },
                                      set: { Preferenze.voceScelta = $0.isEmpty ? nil : $0; m.preferenzeCambiate() })) {
                Text(it ? "Automatica" : "Automatic").tag("")
                ForEach(voci, id: \.identifier) { v in
                    Text(VoceJarvis.etichetta(v)).tag(v.identifier)
                }
            } label: {
                Text(it ? "Voce di sistema" : "System voice")
            }
            .pickerStyle(.inline)
            Divider()
            Toggle(it ? "Ascolta subito con ⌥Spazio" : "Listen right away with ⌥Space",
                   isOn: Binding(get: { Preferenze.ascoltaSubito },
                                 set: { Preferenze.ascoltaSubito = $0; m.preferenzeCambiate() }))
            Toggle(it ? "Conversazione continua" : "Continuous conversation",
                   isOn: Binding(get: { Preferenze.conversazione },
                                 set: { Preferenze.conversazione = $0; m.preferenzeCambiate() }))
            Toggle(it ? "Avvia Voicebox da solo" : "Start Voicebox automatically",
                   isOn: Binding(get: { Preferenze.avviaVoicebox },
                                 set: { Preferenze.avviaVoicebox = $0; m.preferenzeCambiate() }))
            Toggle(it ? "Consenti anche la voce di base" : "Also allow the basic voice",
                   isOn: Binding(get: { Preferenze.voceBase },
                                 set: { Preferenze.voceBase = $0; m.preferenzeCambiate() }))
            Divider()
            Button(it ? "Voci di sistema…" : "System voices…") {
                if let u = URL(string: "x-apple.systempreferences:com.apple.Accessibility-Settings.extension?SpokenContent") {
                    NSWorkspace.shared.open(u)
                }
            }
        } label: {
            Image(systemName: "ellipsis.circle").imageScale(.medium)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .id(m.versionePreferenze)
        .accessibilityLabel(it ? "Impostazioni di Jarvis" : "Jarvis settings")
    }
}
