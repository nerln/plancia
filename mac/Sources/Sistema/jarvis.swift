// Modalità Jarvis: parli, lui fa.
//
// Un pannello che sta sopra tutto, ascolta di continuo e capisce quando hai
// finito di parlare dal silenzio, non da un tasto tenuto premuto. Quello che
// dici va al backend, che esegue subito i comandi che riconosce e passa il
// resto a Claude Code con i tool di Plancia aperti. Poi risponde a voce e
// torna in ascolto.

import AppKit
import AVFoundation
import Carbon.HIToolbox
import Speech
import AVFoundation

// MARK: - stato

enum StatoJarvis {
    case spento, ascolto, penso, parlo

    var colore: NSColor {
        switch self {
        case .spento: return NSColor(calibratedRed: 0.38, green: 0.42, blue: 0.49, alpha: 1)
        case .ascolto: return NSColor(calibratedRed: 0.91, green: 0.58, blue: 0.31, alpha: 1)
        case .penso: return NSColor(calibratedRed: 0.56, green: 0.72, blue: 0.85, alpha: 1)
        case .parlo: return NSColor(calibratedRed: 0.36, green: 0.72, blue: 0.61, alpha: 1)
        }
    }

    func didascalia(_ lang: String) -> String {
        let it: [StatoJarvis: String] = [.spento: "premi per iniziare", .ascolto: "ti ascolto",
                                         .penso: "ci penso", .parlo: "…"]
        let en: [StatoJarvis: String] = [.spento: "tap to start", .ascolto: "listening",
                                         .penso: "thinking", .parlo: "…"]
        let es: [StatoJarvis: String] = [.spento: "toca para empezar", .ascolto: "te escucho",
                                         .penso: "lo pienso", .parlo: "…"]
        let m = lang == "en" ? en : (lang == "es" ? es : it)
        return m[self] ?? ""
    }
}

// MARK: - l'orbita

/// Cerchi concentrici che respirano col volume della voce. Non è decorazione:
/// è l'unico modo per sapere, senza guardare la trascrizione, che ti sta
/// davvero sentendo.
final class Orbita: NSView {
    var stato: StatoJarvis = .spento { didSet { needsDisplay = true } }
    var livello: CGFloat = 0
    private var fase: CGFloat = 0
    private var timer: Timer?

    override var isFlipped: Bool { false }

    func anima(_ acceso: Bool) {
        timer?.invalidate()
        guard acceso else { timer = nil; return }
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            self.fase += 0.055
            self.needsDisplay = true
        }
        RunLoop.main.add(timer!, forMode: .common)
    }

    override func draw(_ dirty: NSRect) {
        let c = NSPoint(x: bounds.midX, y: bounds.midY)
        let base = min(bounds.width, bounds.height) * 0.28
        let colore = stato.colore

        // respiro lento di fondo, sempre presente
        let respiro = 1 + sin(fase) * 0.045
        // il volume spinge il raggio, ma con un tetto: non deve saltare
        let spinta = stato == .ascolto ? min(livello, 1) * 0.42 : 0
        let pulsa = stato == .parlo ? (1 + sin(fase * 2.4) * 0.09) : 1

        // aloni
        for (i, k) in [2.15, 1.72, 1.36].enumerated() {
            let r = base * CGFloat(k) * respiro * (1 + spinta * CGFloat(3 - i) / 3) * pulsa
            let p = NSBezierPath(ovalIn: NSRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2))
            colore.withAlphaComponent(0.05 + 0.035 * CGFloat(i)).setFill()
            p.fill()
        }

        // anello
        let ra = base * 1.08 * respiro * (1 + spinta * 0.5)
        let anello = NSBezierPath(ovalIn: NSRect(x: c.x - ra, y: c.y - ra, width: ra * 2, height: ra * 2))
        anello.lineWidth = 1.2
        colore.withAlphaComponent(stato == .spento ? 0.35 : 0.7).setStroke()
        anello.stroke()

        // nucleo
        let rn = base * 0.46 * (stato == .spento ? 0.8 : 1) * pulsa * (1 + spinta * 0.3)
        let nucleo = NSBezierPath(ovalIn: NSRect(x: c.x - rn, y: c.y - rn, width: rn * 2, height: rn * 2))
        colore.withAlphaComponent(stato == .spento ? 0.5 : 0.95).setFill()
        nucleo.fill()

        // mentre pensa, un arco che gira: dice che sta lavorando senza numeri
        if stato == .penso {
            let rr = base * 1.5
            let arco = NSBezierPath()
            let inizio = fase * 60
            arco.appendArc(withCenter: c, radius: rr, startAngle: inizio, endAngle: inizio + 72)
            arco.lineWidth = 2
            arco.lineCapStyle = .round
            colore.withAlphaComponent(0.9).setStroke()
            arco.stroke()
        }
    }
}

// MARK: - ascolto continuo

/// Come il push to talk, ma la fine della frase la decide il silenzio.
///
/// Tre scelte che fanno la differenza fra una conversazione e un'interrogazione:
///
/// 1. **Il microfono non si spegne mai** durante una sessione. Fermare e
///    riavviare il motore audio a ogni turno costa mezzo secondo e si mangia le
///    prime sillabe della frase dopo. Qui si ricicla solo la richiesta di
///    riconoscimento, che è istantaneo.
/// 2. **Si continua ad ascoltare anche mentre parla lui.** Così puoi
///    interromperlo. Perché funzioni serve la cancellazione dell'eco, altrimenti
///    si sente da solo e si interrompe da solo: la fa il nodo di ingresso con
///    `setVoiceProcessingEnabled`.
/// 3. **Il vocabolario dei tuoi progetti** viene passato al riconoscitore. Senza,
///    "Voicebox" diventa "voice books" e il comando si perde.
final class AscoltoContinuo {
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var recognizer: SFSpeechRecognizer?
    private var timerSilenzio: Timer?
    private var ultimo = ""
    private var lingua = "it"

    /// Il motore audio gira.
    private(set) var attivo = false
    /// Le frasi vengono raccolte. Falso mentre parla lui: il microfono resta
    /// aperto solo per accorgersi che lo stai interrompendo.
    private(set) var raccoglie = false

    private var fortiDiFila = 0
    private var eco = false
    /// Il microfono ha portato almeno un campione diverso da zero.
    private var sentitoQualcosa = false

    var onParziale: ((String) -> Void)?
    var onFrase: ((String) -> Void)?
    var onLivello: ((CGFloat) -> Void)?
    var onErrore: ((String) -> Void)?
    /// Hai cominciato a parlare mentre parlava lui.
    var onInterruzione: (() -> Void)?

    /// Nomi di progetto e comandi, passati al riconoscitore come contesto.
    var vocabolario: [String] = []

    /// Quanto silenzio serve per considerare finita la frase. Sotto il secondo
    /// taglia le pause di chi pensa mentre parla.
    var attesa: TimeInterval = 1.1

    /// Sopra questo livello, mentre parla lui, si considera che tu lo stia
    /// interrompendo. Con l'eco cancellato la sua voce sta molto sotto.
    private let sogliaInterruzione: Float = 0.055

    /// Come stiamo messi, senza chiedere niente. Serve a saperlo prima di
    /// aprire il microfono e a scriverlo nel registro quando qualcosa non torna.
    static var stato: (voce: Bool, micro: Bool, decisi: Bool) {
        let v = SFSpeechRecognizer.authorizationStatus()
        let m = AVCaptureDevice.authorizationStatus(for: .audio)
        return (v == .authorized, m == .authorized,
                v != .notDetermined && m != .notDetermined)
    }

    /// Chiede microfono e dettatura, in quest'ordine e con una sveglia.
    ///
    /// L'ordine conta: la richiesta del microfono è quella che il sistema mostra
    /// sempre, quella della dettatura a volte resta appesa senza far comparire
    /// niente. Chiedendo prima il microfono, quando arriva il turno della
    /// dettatura l'app è già una che ha parlato col sistema.
    ///
    /// La sveglia serve al caso peggiore: se dopo dodici secondi non ha
    /// risposto nessuno, la finestra non è comparsa, e restare in silenzio ad
    /// aspettarla è il modo migliore per far credere che l'app sia rotta.
    func permessi(_ done: @escaping (Bool, String) -> Void) {
        Log.write("jarvis: permessi voce=\(SFSpeechRecognizer.authorizationStatus().rawValue) "
                  + "micro=\(AVCaptureDevice.authorizationStatus(for: .audio).rawValue)")
        var risposto = false
        let rispondi: (Bool, String) -> Void = { ok, messaggio in
            guard !risposto else { return }
            risposto = true
            DispatchQueue.main.async { done(ok, messaggio) }
        }

        // Se il consenso è già dato non si chiede niente: si parte.
        if AVCaptureDevice.authorizationStatus(for: .audio) == .authorized,
           SFSpeechRecognizer.authorizationStatus() == .authorized {
            return rispondi(true, "")
        }

        // Si chiede, e si aspetta. Aprire il microfono senza consenso non serve
        // a far comparire la finestra: blocca il thread principale dentro
        // CoreAudio, e l'app resta piantata senza nemmeno potersi chiudere.
        AVCaptureDevice.requestAccess(for: .audio) { micro in
            Log.write("jarvis: microfono \(micro)")
            SFSpeechRecognizer.requestAuthorization { stato in
                Log.write("jarvis: dettatura \(stato.rawValue)")
                rispondi(micro && stato == .authorized,
                         micro ? "La dettatura non è autorizzata. Impostazioni di sistema, Privacy e sicurezza."
                               : "Il microfono non è autorizzato.")
            }
        }

        // La finestra di sistema compare solo se è l'app stessa a chiederla, ed
        // è così solo quando l'app l'ha aperta il Finder o launchd. Lanciata da
        // un terminale, la richiesta viene attribuita al terminale e non compare
        // niente: qui non si resta ad aspettare per sempre, lo si dice.
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) {
            guard !risposto else { return }
            Log.write("jarvis: la finestra dei permessi non è comparsa")
            rispondi(false, "Non riesco a chiederti i permessi da qui. Usa Attiva la voce nel menu di Plancia, in alto a destra.")
        }
    }

    /// Accende il microfono per tutta la sessione. Da chiamare una volta.
    func accendi(lang: String) {
        lingua = lang
        guard !attivo else { return riprendi() }
        // Senza consenso non si tocca il motore audio: `setVoiceProcessingEnabled`
        // su un ingresso che il sistema non lascia aprire non torna più, e con
        // lui resta piantato il thread principale dell'app.
        guard AscoltoContinuo.stato.micro else {
            Log.write("jarvis: niente microfono, non apro il motore audio")
            return onErrore?("Il microfono non è autorizzato.") ?? ()
        }
        guard let rec = SFSpeechRecognizer(locale: Listener.locale(for: lang)), rec.isAvailable else {
            Log.write("jarvis: riconoscitore non disponibile per \(lang)")
            return onErrore?("Il riconoscimento non è disponibile in questa lingua.") ?? ()
        }
        recognizer = rec

        let input = engine.inputNode
        // La cancellazione dell'eco va accesa prima di prendere il formato: lo
        // cambia. Se non è disponibile si va avanti lo stesso, ma senza poterlo
        // interrompere mentre parla.
        do {
            try input.setVoiceProcessingEnabled(true)
            eco = true
            Log.write("jarvis: eco cancellato, si può interrompere")
        } catch {
            eco = false
            Log.write("jarvis: eco non cancellabile su questo ingresso, niente interruzione")
        }

        let formato = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: formato) { [weak self] buffer, _ in
            guard let self = self else { return }
            if self.raccoglie { self.request?.append(buffer) }
            self.misura(buffer)
        }
        engine.prepare()
        do { try engine.start() } catch {
            Log.write("jarvis: microfono non apribile: \(error.localizedDescription)")
            return onErrore?("Non riesco ad aprire il microfono.") ?? ()
        }
        attivo = true
        riprendi()
        Log.write("jarvis: microfono aperto, formato \(formato.sampleRate) Hz")

        // Il microfono può aprirsi anche senza consenso: in quel caso arriva
        // solo silenzio digitale, esatto, e senza questo controllo l'app
        // sembrerebbe in ascolto per sempre senza sentire niente.
        sentitoQualcosa = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 6) { [weak self] in
            guard let self = self, self.attivo, !self.sentitoQualcosa else { return }
            Log.write("jarvis: sei secondi di silenzio perfetto, il microfono non ci sente")
            self.onErrore?("Il microfono non sente niente. Controlla i permessi di Plancia in Impostazioni di sistema, Privacy e sicurezza.")
        }
    }

    /// Ricomincia a raccogliere. Il motore audio non si tocca, quindi è
    /// istantaneo e non perde l'inizio della frase.
    func riprendi() {
        guard attivo else { return }
        nuovaRichiesta()
        raccoglie = true
        fortiDiFila = 0
    }

    /// Smette di raccogliere ma resta in ascolto per l'interruzione.
    func pausa() {
        raccoglie = false
        timerSilenzio?.invalidate()
        timerSilenzio = nil
        chiudiRichiesta()
        ultimo = ""
        fortiDiFila = 0
    }

    private func nuovaRichiesta() {
        chiudiRichiesta()
        guard let rec = recognizer else { return }
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        // I nomi che il modello generico non conosce: progetti, agenti, comandi.
        if !vocabolario.isEmpty { req.contextualStrings = Array(vocabolario.prefix(100)) }
        request = req
        ultimo = ""
        task = rec.recognitionTask(with: req) { [weak self] result, errore in
            guard let self = self else { return }
            if errore != nil && self.raccoglie && self.ultimo.isEmpty {
                // Il riconoscitore chiude da solo dopo un minuto di niente:
                // si riapre senza dire niente a nessuno.
                DispatchQueue.main.async { if self.raccoglie { self.nuovaRichiesta() } }
                return
            }
            guard self.raccoglie, let result = result else { return }
            let testo = result.bestTranscription.formattedString
            if testo != self.ultimo {
                self.ultimo = testo
                DispatchQueue.main.async {
                    self.onParziale?(testo)
                    self.riarma()
                }
            }
        }
    }

    private func chiudiRichiesta() {
        request?.endAudio()
        task?.cancel()
        request = nil
        task = nil
    }

    private func misura(_ buffer: AVAudioPCMBuffer) {
        guard let dati = buffer.floatChannelData?[0] else { return }
        let n = Int(buffer.frameLength)
        guard n > 0 else { return }
        var somma: Float = 0
        for i in 0..<n { somma += dati[i] * dati[i] }
        let rms = sqrt(somma / Float(n))
        if rms > 0.0005 { sentitoQualcosa = true }

        // Mentre parla lui il microfono serve a una cosa sola: accorgersi che
        // hai ripreso la parola. Tre buffer di fila sopra soglia, non uno: un
        // colpo di tosse o una porta non devono zittirlo.
        if !raccoglie {
            if eco && rms > sogliaInterruzione {
                fortiDiFila += 1
                if fortiDiFila >= 3 {
                    fortiDiFila = 0
                    DispatchQueue.main.async { self.onInterruzione?() }
                }
            } else if fortiDiFila > 0 {
                fortiDiFila -= 1
            }
            return
        }

        // la voce sta in un intervallo stretto: si allarga per renderla visibile
        let livello = min(1, CGFloat(rms) * 14)
        DispatchQueue.main.async { self.onLivello?(livello) }
    }

    private func riarma() {
        timerSilenzio?.invalidate()
        // Una frase corta è quasi sempre un comando e non ha senso farlo
        // aspettare; una lunga è un pensiero in corso e va lasciato finire.
        let parole = ultimo.split(separator: " ").count
        let quanto = parole <= 3 ? attesa * 0.8 : (parole >= 12 ? attesa * 1.5 : attesa)
        timerSilenzio = Timer.scheduledTimer(withTimeInterval: quanto, repeats: false) { [weak self] _ in
            guard let self = self, self.raccoglie else { return }
            let frase = self.ultimo.trimmingCharacters(in: .whitespacesAndNewlines)
            guard frase.count > 1 else { return }
            self.pausa()
            self.onFrase?(frase)
        }
        RunLoop.main.add(timerSilenzio!, forMode: .common)
    }

    /// Spegne tutto. Da chiamare quando la sessione finisce, non fra un turno e
    /// l'altro.
    func spegni() {
        timerSilenzio?.invalidate()
        timerSilenzio = nil
        raccoglie = false
        guard attivo else { return }
        attivo = false
        engine.inputNode.removeTap(onBus: 0)
        if engine.isRunning { engine.stop() }
        chiudiRichiesta()
        onLivello?(0)
    }
}

// MARK: - il pannello

/// Un pannello senza bordi non prende la tastiera, quindi il campo di testo
/// dentro non riceverebbe niente. `becomesKeyOnlyIfNeeded` insieme a questo
/// permette di scriverci senza che l'app rubi il fuoco a quella davanti.
final class PannelloScrivibile: NSPanel {
    override var canBecomeKey: Bool { true }
}

final class JarvisPanel: NSWindowController, AVSpeechSynthesizerDelegate, NSTextFieldDelegate {
    private let orbita = Orbita()
    private let trascritto = NSTextField(labelWithString: "")
    private let risposta = NSTextField(wrappingLabelWithString: "")
    private let didascalia = NSTextField(labelWithString: "")
    private let ascolto = AscoltoContinuo()
    private let campo = NSTextField()
    private var stato: StatoJarvis = .spento { didSet { orbita.stato = stato; aggiornaTesti() } }
    /// Il microfono si apre solo dopo che l'utente ha detto di sì una volta.
    /// Senza questo, riprendere l'ascolto da solo fa comparire la richiesta di
    /// sistema in un momento qualsiasi e l'app resta ferma ad aspettarla.
    private var autorizzato = false
    private var soloTesto = false
    /// Quando finisce di parlare torna in ascolto, tranne dopo un errore che ha
    /// già spento tutto.
    private var riprendeDopoAverParlato = true
    /// L'ho zittito io perché hai ripreso a parlare, non ha finito da solo.
    private var interrottoDaMe = false
    /// Avvisi arrivati mentre non era il momento di darli.
    private var daDire: [String] = []
    private var timerLavori: Timer?
    private var ultimoEvento = ""
    private var timerAttesa: Timer?
    /// Dopo un po' che non parli il microfono si chiude da solo. Un'app che si
    /// vanta di non mandare niente fuori non può tenere il microfono aperto
    /// tutto il giorno perché ti sei alzato senza dire niente.
    private var timerInattivita: Timer?
    private let inattivita: TimeInterval = 180
    /// Quanto va svelta la voce. Si cambia dicendo "più piano" o "più veloce" e
    /// resta com'era anche dopo aver chiuso, perché è una preferenza, non un
    /// capriccio del momento.
    private var velocita: Double {
        get { (UserDefaults.standard.object(forKey: "velocitaVoce") as? Double) ?? 0.52 }
        set { UserDefaults.standard.set(min(0.72, max(0.34, newValue)), forKey: "velocitaVoce") }
    }
    /// La voce di sistema la fa l'app: aspettare che il server sintetizzi un
    /// file e lo rimandi indietro costa due secondi buoni a ogni risposta.
    private let sintetizzatore = AVSpeechSynthesizer()
    private var lingua: String { Conf.lang }

    /// Azioni che il pannello non sa eseguire da solo: navigare, sincronizzare.
    var onAzione: (([String: Any]) -> Void)?

    convenience init() {
        let panel = PannelloScrivibile(contentRect: NSRect(x: 0, y: 0, width: 320, height: 400),
                                       styleMask: [.borderless, .nonactivatingPanel],
                                       backing: .buffered, defer: false)
        panel.becomesKeyOnlyIfNeeded = true
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.init(window: panel)
        costruisci()
        collega()
    }

    private func costruisci() {
        guard let content = window?.contentView else { return }
        content.wantsLayer = true

        let sfondo = NSVisualEffectView(frame: content.bounds)
        sfondo.material = .hudWindow
        sfondo.blendingMode = .behindWindow
        sfondo.state = .active
        sfondo.wantsLayer = true
        sfondo.layer?.cornerRadius = 24
        sfondo.layer?.masksToBounds = true
        sfondo.layer?.borderWidth = 1
        sfondo.layer?.borderColor = NSColor.white.withAlphaComponent(0.08).cgColor
        sfondo.autoresizingMask = [.width, .height]
        content.addSubview(sfondo)

        orbita.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(orbita)

        didascalia.font = .systemFont(ofSize: 11, weight: .medium)
        didascalia.textColor = .tertiaryLabelColor
        didascalia.alignment = .center
        didascalia.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(didascalia)

        trascritto.font = .systemFont(ofSize: 12)
        trascritto.textColor = .secondaryLabelColor
        trascritto.alignment = .center
        trascritto.lineBreakMode = .byTruncatingHead
        trascritto.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(trascritto)

        risposta.font = .systemFont(ofSize: 13.5)
        risposta.textColor = .labelColor
        risposta.alignment = .center
        risposta.maximumNumberOfLines = 6
        risposta.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(risposta)

        NSLayoutConstraint.activate([
            orbita.topAnchor.constraint(equalTo: content.topAnchor, constant: 22),
            orbita.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            orbita.widthAnchor.constraint(equalToConstant: 150),
            orbita.heightAnchor.constraint(equalToConstant: 150),

            didascalia.topAnchor.constraint(equalTo: orbita.bottomAnchor, constant: 8),
            didascalia.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 16),
            didascalia.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -16),

            trascritto.topAnchor.constraint(equalTo: didascalia.bottomAnchor, constant: 4),
            trascritto.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 16),
            trascritto.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -16),

            risposta.topAnchor.constraint(equalTo: trascritto.bottomAnchor, constant: 12),
            risposta.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 20),
            risposta.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -20),
            risposta.bottomAnchor.constraint(lessThanOrEqualTo: content.bottomAnchor, constant: -54),
        ])

        // Il campo serve a due cose: lavorare lo stesso quando il microfono non
        // è disponibile, e correggere una frase capita male senza doverla
        // ripetere tutta a voce.
        campo.placeholderString = ["it": "oppure scrivi", "en": "or type",
                                   "es": "o escribe"][lingua] ?? "or type"
        campo.font = .systemFont(ofSize: 12)
        campo.bezelStyle = .roundedBezel
        campo.focusRingType = .none
        campo.delegate = self
        campo.target = self
        campo.action = #selector(scritto)
        campo.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(campo)

        NSLayoutConstraint.activate([
            campo.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 20),
            campo.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -20),
            campo.topAnchor.constraint(greaterThanOrEqualTo: risposta.bottomAnchor, constant: 12),
            campo.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -16),
        ])

        let click = NSClickGestureRecognizer(target: self, action: #selector(tocca))
        orbita.addGestureRecognizer(click)
    }

    private func collega() {
        ascolto.onLivello = { [weak self] l in self?.orbita.livello = l }
        ascolto.onParziale = { [weak self] t in self?.trascritto.stringValue = t }
        ascolto.onErrore = { [weak self] e in
            guard let self = self else { return }
            self.stato = .spento
            self.risposta.stringValue = e
            // A mani libere un errore scritto è un errore che non esiste.
            self.parla(e, poiAscolta: false)
        }
        ascolto.onFrase = { [weak self] frase in self?.manda(frase) }
        ascolto.onInterruzione = { [weak self] in self?.interrompi() }
        sintetizzatore.delegate = self
        Player.shared.onFinish = { [weak self] in
            guard let self = self, self.window?.isVisible == true else { return }
            if self.interrottoDaMe { self.interrottoDaMe = false; return }
            self.riprendiAscolto()
        }
    }

    /// Hai ripreso la parola mentre parlava lui: si zittisce e ti ascolta.
    private func interrompi() {
        guard stato == .parlo else { return }
        // Fermare la sintesi fa scattare lo stesso il messaggio di "ho finito
        // di parlare", che rimetterebbe in ascolto una seconda volta buttando
        // via la frase appena cominciata. Questa bandierina lo dice a chi
        // arriva dopo.
        interrottoDaMe = true
        sintetizzatore.stopSpeaking(at: .immediate)
        Player.shared.stop()
        Log.write("jarvis: interrotto dalla voce")
        riprendiAscolto()
    }

    private func aggiornaTesti() {
        // Quando c'è un avviso da leggere, non lo si copre con "premi per
        // iniziare": chi non ha il microfono deve vedere cosa fare.
        if stato == .spento && !risposta.stringValue.isEmpty { return }
        didascalia.stringValue = stato.didascalia(lingua)
        orbita.anima(stato != .spento)
    }

    @objc private func scritto() {
        let frase = campo.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard frase.count > 1 else { return }
        campo.stringValue = ""
        ascolto.pausa()
        manda(frase)
    }

    // --- ciclo ---

    @objc private func tocca() {
        if stato == .spento { avvia() } else { sospendi() }
    }

    func apri() {
        posiziona()
        window?.orderFrontRegardless()
        // Il primo turno paga l'avvio del processo Claude: lo si fa partire
        // adesso, mentre l'utente sta ancora aprendo la bocca.
        API.request("/api/jarvis/scalda", method: "POST",
                    body: ["lang": lingua], timeout: 20) { _, _ in }
        caricaVocabolario()
        if stato == .spento { avvia() }
    }

    private func vociSistema(_ lang: String) -> AVSpeechSynthesisVoice? {
        let codice = ["it": "it-IT", "en": "en-US", "es": "es-ES",
                      "fr": "fr-FR", "de": "de-DE", "pt": "pt-BR"][lang] ?? "en-US"
        return AVSpeechSynthesisVoice(language: codice)
    }

    private func parla(_ testo: String, poiAscolta: Bool = true) {
        sintetizzatore.stopSpeaking(at: .immediate)
        riprendeDopoAverParlato = poiAscolta
        let frase = AVSpeechUtterance(string: testo)
        frase.voice = vociSistema(lingua)
        frase.rate = Float(velocita)
        stato = .parlo
        sintetizzatore.speak(frase)
    }

    private func posiziona() {
        guard let w = window, let schermo = NSScreen.main else { return }
        let vf = schermo.visibleFrame
        w.setFrameOrigin(NSPoint(x: vf.maxX - w.frame.width - 28, y: vf.minY + 28))
    }

    /// Il perché a voce, non scritto: se il microfono non è autorizzato la
    /// persona sta guardando da un'altra parte, ed è esattamente il momento in
    /// cui non deve restare in silenzio.
    private func spiegaPermessi() -> String {
        let m = ["it": "Mi mancano i permessi per il microfono e la dettatura. Usa Attiva la voce nel menu di Plancia, in alto a destra. Intanto puoi scrivermi qui sotto.",
                 "en": "I am missing microphone and dictation permission. Use Turn on the voice in the Plancia menu, top right. Meanwhile you can type below.",
                 "es": "Me faltan los permisos de micrófono y dictado. Usa Activar la voz en el menú de Plancia, arriba a la derecha. Mientras tanto puedes escribir aquí abajo."]
        return m[lingua] ?? m["en"]!
    }

    private func mostraImpostazioni() {
        let voce = SFSpeechRecognizer.authorizationStatus() != .authorized
        let dove = voce ? "Privacy_SpeechRecognition" : "Privacy_Microphone"
        if let u = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(dove)") {
            NSWorkspace.shared.open(u)
        }
    }

    func avvia() {
        // Le finestre di sistema per microfono e dettatura non compaiono se
        // l'app non è davanti, e il pannello è di proposito una finestra che non
        // attiva l'app. Risultato: la richiesta restava appesa e Jarvis non
        // partiva senza dire perché. La prima volta si porta l'app davanti.
        if !AscoltoContinuo.stato.decisi {
            NSApp.activate(ignoringOtherApps: true)
            didascalia.stringValue = ["it": "autorizza microfono e dettatura",
                                      "en": "allow microphone and dictation",
                                      "es": "autoriza micrófono y dictado"][lingua] ?? ""
        }
        ascolto.permessi { [weak self] ok, messaggio in
            guard let self = self else { return }
            guard ok else {
                self.autorizzato = false
                self.stato = .spento
                self.risposta.stringValue = messaggio
                Log.write("jarvis: permessi negati: \(messaggio)")
                // Senza microfono il pannello non diventa inutile: si scrive.
                self.didascalia.stringValue = ["it": "senza microfono: scrivi qui sotto",
                                               "en": "no microphone: type below",
                                               "es": "sin micrófono: escribe abajo"][self.lingua] ?? ""
                self.parla(self.spiegaPermessi(), poiAscolta: false)
                self.mostraImpostazioni()
                self.window?.makeFirstResponder(self.campo)
                return
            }
            self.autorizzato = true
            self.soloTesto = false
            self.risposta.stringValue = ""
            self.trascritto.stringValue = ""
            self.stato = .ascolto
            self.ascolto.accendi(lang: self.lingua)
            self.seguiLavori()
            self.armaInattivita()
            Log.write("jarvis: in ascolto (\(self.lingua))")
        }
    }

    func sospendi() {
        timerInattivita?.invalidate()
        timerInattivita = nil
        ascolto.spegni()
        sintetizzatore.stopSpeaking(at: .immediate)
        Player.shared.stop()
        timerLavori?.invalidate()
        timerLavori = nil
        stato = .spento
        trascritto.stringValue = ""
    }

    func chiudi() {
        sospendi()
        window?.orderOut(nil)
    }

    private func riprendiAscolto() {
        guard autorizzato, !soloTesto, stato != .spento else {
            stato = .spento
            return
        }
        stato = .ascolto
        trascritto.stringValue = ""
        ascolto.riprendi()
        armaInattivita()
        if let dopo = daDire.first {
            daDire.removeFirst()
            parla(dopo)
        }
    }

    private func armaInattivita() {
        timerInattivita?.invalidate()
        timerInattivita = Timer.scheduledTimer(withTimeInterval: inattivita, repeats: false) {
            [weak self] _ in
            guard let self = self, self.stato == .ascolto,
                  self.trascritto.stringValue.isEmpty else { return }
            Log.write("jarvis: tre minuti di silenzio, chiudo il microfono")
            self.sospendi()
            self.didascalia.stringValue = ["it": "microfono chiuso, tocca per riprendere",
                                           "en": "microphone closed, tap to resume",
                                           "es": "micrófono cerrado, toca para seguir"][self.lingua] ?? ""
        }
        RunLoop.main.add(timerInattivita!, forMode: .common)
    }

    /// Il vocabolario: i nomi dei tuoi progetti, più le parole che contano.
    /// Senza, il riconoscitore scrive "voice books" e il comando non arriva.
    private func caricaVocabolario() {
        API.lista("/api/projects") { [weak self] progetti in
            guard let self = self else { return }
            var parole = Set<String>()
            for p in progetti {
                if let n = p["name"] as? String { parole.insert(n) }
                if let k = p["key"] as? String { parole.insert(k.replacingOccurrences(of: "-", with: " ")) }
            }
            parole.formUnion(["Plancia", "Claude", "Codex", "lavagna", "riepilogo",
                              "proposta", "esegui", "fallo", "archivia", "board",
                              "recap", "dispatch"])
            self.ascolto.vocabolario = Array(parole)
        }
    }

    /// Un lancio dura minuti. Se finisce e nessuno te lo dice, sei tornato a
    /// guardare lo schermo: qui il pannello segue il registro degli eventi e ti
    /// avvisa a voce quando c'è qualcosa da sapere.
    private func seguiLavori() {
        timerLavori?.invalidate()
        API.request("/api/eventi?limite=1") { [weak self] j, _ in
            if let e = (j?["eventi"] as? [[String: Any]])?.last {
                self?.ultimoEvento = (e["id"] as? String) ?? ""
            }
            guard let self = self else { return }
            self.timerLavori = Timer.scheduledTimer(withTimeInterval: 6, repeats: true) { [weak self] _ in
                self?.guardaEventi()
            }
            RunLoop.main.add(self.timerLavori!, forMode: .common)
        }
    }

    private func guardaEventi() {
        guard window?.isVisible == true else { return }
        let coda = ultimoEvento.isEmpty ? "" : "&dopo=\(ultimoEvento)"
        API.request("/api/eventi?limite=20\(coda)", timeout: 10) { [weak self] j, _ in
            guard let self = self,
                  let eventi = j?["eventi"] as? [[String: Any]], !eventi.isEmpty else { return }
            self.ultimoEvento = (eventi.last?["id"] as? String) ?? self.ultimoEvento
            for e in eventi {
                let tipo = (e["tipo"] as? String) ?? ""
                guard tipo == "lavoro.completato" || tipo == "lavoro.fallito" else { continue }
                let titolo = (e["titolo"] as? String) ?? ""
                let corto = titolo.count > 70 ? String(titolo.prefix(70)) + "…" : titolo
                let frasi = [
                    "it": tipo == "lavoro.completato" ? "Ho finito: \(corto)." : "È andata male su: \(corto).",
                    "en": tipo == "lavoro.completato" ? "Done: \(corto)." : "That failed: \(corto).",
                    "es": tipo == "lavoro.completato" ? "Listo: \(corto)." : "Ha fallado: \(corto).",
                ]
                let frase = frasi[self.lingua] ?? frasi["en"]!
                // Se stai parlando o sta pensando, l'avviso aspetta il suo turno:
                // interrompere una risposta a metà per dare una notizia è peggio
                // che darla dieci secondi dopo.
                if self.stato == .ascolto && self.trascritto.stringValue.isEmpty {
                    self.risposta.stringValue = frase
                    self.ascolto.pausa()
                    self.parla(frase)
                } else if self.daDire.count < 3 {
                    // Più di tre avvisi in coda vuol dire che non stavi
                    // ascoltando: sentirteli tutti dopo mezz'ora non serve a
                    // niente, i lanci restano scritti nella lavagna.
                    self.daDire.append(frase)
                }
            }
        }
    }

    /// Frase iniettata da fuori (schema URL o riga di comando): stesso percorso
    /// della voce, senza microfono. Serve a provarlo e a usarlo scrivendo.
    func detta(_ frase: String) {
        posiziona()
        window?.orderFrontRegardless()
        soloTesto = !autorizzato
        orbita.anima(true)
        manda(frase)
    }

    /// Il pannello che si fotografa da solo, per vedere com'è venuto.
    func schermata(in cartella: URL) -> URL? {
        guard let v = window?.contentView,
              let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { return nil }
        v.cacheDisplay(in: v.bounds, to: rep)
        guard let png = rep.representation(using: .png, properties: [:]) else { return nil }
        let dest = cartella.appendingPathComponent("jarvis-\(Int(Date().timeIntervalSince1970)).png")
        try? png.write(to: dest)
        return dest
    }

    private func manda(_ frase: String) {
        stato = .penso
        trascritto.stringValue = frase
        Log.write("jarvis: \"\(frase)\"")
        // Un colpetto: sai che ha preso la frase senza dover guardare.
        NSSound(named: "Pop")?.play()
        attendiConPazienza()
        API.request("/api/jarvis", method: "POST",
                    body: ["testo": frase, "lang": lingua, "voce": true,
                           "voce_nativa": true]) { [weak self] j, err in
            guard let self = self else { return }
            self.timerAttesa?.invalidate()
            if let err = err {
                self.risposta.stringValue = err
                // Detto, non solo scritto: a mani libere il testo non lo legge
                // nessuno.
                self.parla(self.scusa(err))
                return
            }
            let testo = (j?["risposta"] as? String) ?? ""
            // Quello che si legge e quello che si dice non sono la stessa cosa:
            // il secondo non ha indirizzi, percorsi né sha.
            let perLaVoce = (j?["da_dire"] as? String) ?? testo
            self.risposta.stringValue = testo
            if let azione = j?["azione"] as? [String: Any] {
                if (azione["tipo"] as? String) == "velocita",
                   let passo = azione["passo"] as? Double {
                    self.velocita = self.velocita + passo
                    Log.write("jarvis: voce a \(self.velocita)")
                } else {
                    self.onAzione?(azione)
                }
                if (azione["tipo"] as? String) == "ferma" { return self.chiudi() }
            }
            if let file = j?["file"] as? String {
                self.stato = .parlo
                Player.shared.play(path: file)
            } else if !perLaVoce.isEmpty {
                self.parla(perLaVoce)
            } else {
                self.riprendiAscolto()
            }
        }
    }

    /// Se la risposta tarda, lo dice invece di lasciarti nel silenzio a chiederti
    /// se ti ha sentito.
    private func attendiConPazienza() {
        timerAttesa?.invalidate()
        timerAttesa = Timer.scheduledTimer(withTimeInterval: 4.5, repeats: false) { [weak self] _ in
            guard let self = self, self.stato == .penso else { return }
            let m = ["it": "un attimo", "en": "one moment", "es": "un momento"]
            self.didascalia.stringValue = m[self.lingua] ?? m["en"]!
        }
        RunLoop.main.add(timerAttesa!, forMode: .common)
    }

    /// L'errore tecnico non si legge ad alta voce: si dice cosa è successo.
    private func scusa(_ errore: String) -> String {
        let m = ["it": "Non ci sono riuscito. \(errore)",
                 "en": "That did not work. \(errore)",
                 "es": "No he podido. \(errore)"]
        return m[lingua] ?? m["en"]!
    }

    func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        guard window?.isVisible == true else { return }
        if interrottoDaMe {
            interrottoDaMe = false
            return
        }
        guard riprendeDopoAverParlato else {
            riprendeDopoAverParlato = true
            stato = .spento
            return
        }
        riprendiAscolto()
    }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { chiudi() } else { super.keyDown(with: event) }
    }
}

// MARK: - scorciatoia globale

/// ⌥Spazio ovunque. Passa da Carbon perché è l'unica strada che non chiede
/// l'accesso all'accessibilità solo per leggere una combinazione di tasti.
enum Scorciatoia {
    private static var ref: EventHotKeyRef?
    static var azione: (() -> Void)?

    static func registra() {
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                                 eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
            DispatchQueue.main.async { Scorciatoia.azione?() }
            return noErr
        }, 1, &spec, nil, nil)
        let id = EventHotKeyID(signature: OSType(0x504C4E43), id: 1)
        let esito = RegisterEventHotKey(UInt32(kVK_Space), UInt32(optionKey), id,
                                        GetApplicationEventTarget(), 0, &ref)
        Log.write(esito == noErr ? "scorciatoia ⌥Spazio registrata"
                                 : "scorciatoia ⌥Spazio occupata da un'altra app (\(esito))")
    }
}
