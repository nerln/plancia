// L'ascolto di Jarvis.
//
// Regole, tutte tenute qui e in nessun altro posto:
//   - il microfono si apre SOLO quando `avvia` viene chiamato da un gesto dell'utente (il
//     pulsante del microfono o la scorciatoia); nessun timer, nessuna risposta di rete e
//     nessun avviso lo riaccende;
//   - il riconoscimento e' quello di Speech SUL MAC (`requiresOnDeviceRecognition`): se la
//     lingua non e' disponibile in locale non si ripiega sui server di Apple, si dice e
//     basta, e si puo' scrivere;
//   - una sola frase per volta: quando finisce, o quando si preme di nuovo, il motore audio
//     si ferma del tutto. Non c'e' un ascolto che resta acceso fra un turno e l'altro;
//   - se non si sente niente per 20 secondi, o dopo un minuto, si chiude da solo e lo dice.
//
// In modo prova (JarvisProva.attivo) non si tocca nessun microfono: si recita una frase
// scritta, con un livello finto.

import AVFoundation
import AppKit
import Speech

@MainActor
final class AscoltoContinuo {
    private let motore = AVAudioEngine()
    private var richiesta: SFSpeechAudioBufferRecognitionRequest?
    private var compito: SFSpeechRecognitionTask?
    private var timerSilenzio: Timer?
    private var timerNiente: Timer?
    private var timerMassimo: Timer?
    private var timerProva: Timer?
    private var ultimo = ""
    private var giro = 0
    private(set) var attivo = false

    /// Il motore audio e' partito davvero: da qui la spia del microfono e' vera.
    var onAperto: (() -> Void)?
    var onParziale: ((String) -> Void)?
    /// La frase e' finita (silenzio o pulsante premuto di nuovo). Il microfono e' gia' spento.
    var onFrase: ((String) -> Void)?
    var onLivello: ((Double) -> Void)?
    /// Il microfono si e' chiuso senza una frase: perche', in parole.
    var onChiuso: ((String?) -> Void)?

    /// Quanto silenzio, dopo l'ultima parola, chiude la frase.
    var attesa: TimeInterval = 1.2

    /// Come stiamo messi coi permessi, senza chiedere niente.
    nonisolated static var stato: (voce: Bool, micro: Bool, decisi: Bool) {
        let v = SFSpeechRecognizer.authorizationStatus()
        let m = AVCaptureDevice.authorizationStatus(for: .audio)
        return (v == .authorized, m == .authorized, v != .notDetermined && m != .notDetermined)
    }

    nonisolated static func locale(_ lingua: String) -> Locale {
        Locale(identifier: lingua == "it" ? "it-IT" : "en-US")
    }

    // MARK: apertura

    /// Accende il microfono. Solo da un gesto dell'utente.
    func avvia(lingua: String, vocabolario: [String], frasePerLaProva: String? = nil) {
        guard !attivo else { return }
        giro += 1
        let mio = giro
        if JarvisProva.attivo {
            return avviaProva(frasePerLaProva ?? JarvisProva.frase)
        }
        permessi { [weak self] ok, messaggio in
            // nel frattempo Esc, o un'altra richiesta, puo' averla annullata
            guard let self = self, self.giro == mio else { return }
            guard ok else { return self.onChiuso?(messaggio) ?? () }
            self.apri(lingua: lingua, vocabolario: vocabolario)
        }
    }

    private func permessi(_ fatto: @escaping (Bool, String) -> Void) {
        let it = Lingua.risolvi() == "it"
        let s = AscoltoContinuo.stato
        if s.micro && s.voce { return fatto(true, "") }
        if AVCaptureDevice.authorizationStatus(for: .audio) == .denied
            || SFSpeechRecognizer.authorizationStatus() == .denied
            || SFSpeechRecognizer.authorizationStatus() == .restricted {
            return fatto(false, it
                ? "Microfono o dettatura non autorizzati. Impostazioni di sistema, Privacy e sicurezza."
                : "Microphone or speech recognition not allowed. System Settings, Privacy and Security.")
        }
        // La finestra di sistema compare solo a un'app davanti, e il pannello di proposito non
        // attiva l'app: qui, dopo un gesto dell'utente, la si porta davanti.
        NSApp.activate(ignoringOtherApps: true)
        var risposto = false
        let rispondi: (Bool, String) -> Void = { ok, m in
            guard !risposto else { return }
            risposto = true
            fatto(ok, m)
        }
        AscoltoContinuo.chiediAlSistema { micro, voce in
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    rispondi(micro && voce,
                             micro ? (it ? "La dettatura non e' autorizzata." : "Speech recognition is not allowed.")
                                   : (it ? "Il microfono non e' autorizzato." : "The microphone is not allowed."))
                }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 12) {
            MainActor.assumeIsolated {
                rispondi(false, it ? "Il sistema non ha mostrato la richiesta dei permessi. Usa Attiva la voce nel menu di Plancia."
                                   : "The system did not show the permission request. Use Turn on the voice in the Plancia menu.")
            }
        }
    }

    /// Le due richieste al sistema (microfono, poi dettatura), fuori dall'attore: le risposte
    /// arrivano su una coda qualsiasi.
    nonisolated private static func chiediAlSistema(_ fatto: @escaping @Sendable (Bool, Bool) -> Void) {
        AVCaptureDevice.requestAccess(for: .audio) { micro in
            SFSpeechRecognizer.requestAuthorization { voce in fatto(micro, voce == .authorized) }
        }
    }

    /// Il blocco che il motore audio chiama su un suo thread: niente che sia dell'attore principale.
    nonisolated private static func creaTap(_ req: SFSpeechAudioBufferRecognitionRequest,
                                            _ livello: @escaping @Sendable (Double) -> Void) -> AVAudioNodeTapBlock {
        return { buffer, _ in
            req.append(buffer)
            livello(AscoltoContinuo.misura(buffer))
        }
    }

    nonisolated private static func avviaRiconoscimento(
        _ rec: SFSpeechRecognizer, _ req: SFSpeechAudioBufferRecognitionRequest,
        _ consegna: @escaping @Sendable (String?, Bool) -> Void) -> SFSpeechRecognitionTask {
        rec.recognitionTask(with: req) { risultato, errore in
            consegna(risultato?.bestTranscription.formattedString, errore != nil)
        }
    }

    private func apri(lingua: String, vocabolario: [String]) {
        let it = lingua == "it"
        guard let rec = SFSpeechRecognizer(locale: AscoltoContinuo.locale(lingua)), rec.isAvailable else {
            return onChiuso?(it ? "Il riconoscimento vocale non e' disponibile in questa lingua."
                                : "Speech recognition is not available in this language.") ?? ()
        }
        // Niente server: se il Mac non sa riconoscere questa lingua da solo, si scrive.
        guard rec.supportsOnDeviceRecognition else {
            Log.write("jarvis: riconoscimento sul Mac non disponibile per \(lingua)")
            return onChiuso?(it
                ? "Il riconoscimento sul Mac non e' disponibile per l'italiano: scarica la dettatura nelle impostazioni di Tastiera, oppure scrivi. Non mando l'audio ai server."
                : "On-device recognition is not available for this language: download dictation in Keyboard settings, or type. I do not send audio to any server.") ?? ()
        }
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        req.requiresOnDeviceRecognition = true
        req.addsPunctuation = true
        if !vocabolario.isEmpty { req.contextualStrings = Array(vocabolario.prefix(100)) }
        richiesta = req

        let ingresso = motore.inputNode
        let formato = ingresso.outputFormat(forBus: 0)
        ingresso.removeTap(onBus: 0)
        let livello: @Sendable (Double) -> Void = { [weak self] l in
            DispatchQueue.main.async { MainActor.assumeIsolated { self?.onLivello?(l) } }
        }
        ingresso.installTap(onBus: 0, bufferSize: 1024, format: formato, block: AscoltoContinuo.creaTap(req, livello))
        motore.prepare()
        do { try motore.start() } catch {
            ingresso.removeTap(onBus: 0)
            richiesta = nil
            Log.write("jarvis: microfono non apribile: \(error.localizedDescription)")
            return onChiuso?(it ? "Non riesco ad aprire il microfono." : "I cannot open the microphone.") ?? ()
        }
        attivo = true
        ultimo = ""
        Log.write("jarvis: microfono acceso (\(lingua), sul Mac)")
        onAperto?()

        let consegna: @Sendable (String?, Bool) -> Void = { [weak self] testo, errore in
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    guard let self = self, self.attivo else { return }
                    if let t = testo {
                        if t != self.ultimo {
                            self.ultimo = t
                            self.onParziale?(t)
                            self.riarma()
                        }
                    } else if errore, self.ultimo.isEmpty {
                        // il riconoscitore ha smesso da solo senza aver sentito niente
                        self.chiudi(inviando: false, motivo: nil)
                    }
                }
            }
        }
        compito = AscoltoContinuo.avviaRiconoscimento(rec, req, consegna)
        // Se non si sente niente per 20 secondi il microfono si chiude da solo e lo dice.
        timerNiente = Timer.scheduledTimer(withTimeInterval: 20, repeats: false) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self = self, self.attivo, self.ultimo.isEmpty else { return }
                self.chiudi(inviando: false, motivo: it ? "Non ho sentito niente: microfono chiuso."
                                                        : "I heard nothing: microphone closed.")
            }
        }
        timerMassimo = Timer.scheduledTimer(withTimeInterval: 60, repeats: false) { [weak self] _ in
            MainActor.assumeIsolated { self?.chiudi(inviando: true, motivo: nil) }
        }
    }

    nonisolated static func misura(_ b: AVAudioPCMBuffer) -> Double {
        guard let dati = b.floatChannelData?[0] else { return 0 }
        let n = Int(b.frameLength)
        guard n > 0 else { return 0 }
        var somma: Float = 0
        for i in 0..<n { somma += dati[i] * dati[i] }
        // la voce sta in un intervallo stretto: si allarga per renderla visibile
        return min(1, Double(sqrt(somma / Float(n))) * 14)
    }

    private func riarma() {
        timerSilenzio?.invalidate()
        // una frase corta e' quasi sempre un comando, una lunga un pensiero ancora in corso
        let parole = ultimo.split(separator: " ").count
        let quanto = parole <= 3 ? attesa * 0.8 : (parole >= 12 ? attesa * 1.5 : attesa)
        timerSilenzio = Timer.scheduledTimer(withTimeInterval: quanto, repeats: false) { [weak self] _ in
            MainActor.assumeIsolated { self?.chiudi(inviando: true, motivo: nil) }
        }
    }

    // MARK: chiusura

    /// Spegne tutto. Con `inviando` la frase sentita fin qui parte come `onFrase`.
    func chiudi(inviando: Bool, motivo: String?) {
        let frase = ultimo.trimmingCharacters(in: .whitespacesAndNewlines)
        fermaTutto()
        if inviando, frase.count > 1 { onFrase?(frase) } else { onChiuso?(motivo) }
    }

    /// Spegne senza dire niente a nessuno: Esc, o si e' chiuso il pannello.
    func ferma() {
        fermaTutto()
        onLivello?(0)
    }

    private func fermaTutto() {
        giro += 1
        for t in [timerSilenzio, timerNiente, timerMassimo, timerProva] { t?.invalidate() }
        timerSilenzio = nil; timerNiente = nil; timerMassimo = nil; timerProva = nil
        let eraAttivo = attivo
        attivo = false
        if eraAttivo, !JarvisProva.attivo {
            motore.inputNode.removeTap(onBus: 0)
            if motore.isRunning { motore.stop() }
            richiesta?.endAudio()
            compito?.cancel()
            Log.write("jarvis: microfono spento")
        }
        richiesta = nil
        compito = nil
    }

    // MARK: prova

    private func avviaProva(_ frase: String) {
        attivo = true
        ultimo = ""
        onAperto?()
        let parole = frase.split(separator: " ").map(String.init)
        var i = 0
        var t = 0.0
        timerProva = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] tm in
            MainActor.assumeIsolated {
                guard let self = self, self.attivo else { tm.invalidate(); return }
                t += 1.0 / 30
                self.onLivello?(0.35 + 0.35 * abs(sin(t * 7)) * abs(sin(t * 2.3)))
                if i < parole.count, t > 0.5 + Double(i) * 0.16 {
                    i += 1
                    self.ultimo = parole[0..<i].joined(separator: " ")
                    self.onParziale?(self.ultimo)
                }
                if i >= parole.count, t > 0.5 + Double(parole.count) * 0.16 + 0.4 {
                    tm.invalidate()
                    self.chiudi(inviando: true, motivo: nil)
                }
            }
        }
    }
}
