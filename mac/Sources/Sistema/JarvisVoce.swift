// La voce di Jarvis.
//
// Due strade, nell'ordine, e la seconda si dice:
//   1. Voce NEURALE locale (Pocket o Voicebox, quella che il server di Plancia trova su
//      127.0.0.1). Il testo arriva a frasi e ogni frase viene sintetizzata mentre la
//      precedente suona e la successiva sta ancora arrivando: la voce parte alla prima
//      frase, non alla fine della risposta. Se una frase non arriva in tempo si passa alla
//      voce di sistema per il resto della risposta, e per un minuto e mezzo non si riprova.
//   2. Le voci di sistema di qualita' avanzata o premium (AVSpeechSynthesizer). MAI la voce
//      di base, quella robotica: se non ce n'e' installata nessuna Jarvis resta a testo e
//      dice come scaricarne una (a meno che tu non abbia acconsentito alla voce base
//      nel menu del pannello).
// In modo prova non si tocca l'altoparlante: la voce si recita con un livello finto.

import AVFoundation
import AppKit

@MainActor
final class VoceJarvis: NSObject, AVSpeechSynthesizerDelegate, AVAudioPlayerDelegate {
    enum Modo: Equatable { case neurale(String), sistema, muta }

    private(set) var modo: Modo = .muta
    /// "Voce neurale: Voicebox", "Voce di sistema: Zoe (premium)", "Solo testo: ..."
    private(set) var descrizione = ""
    /// Cosa e' successo di strano (ripiego, nessuna voce): una riga per il piede del pannello.
    private(set) var avviso: String?
    private(set) var parlando = false

    var onLivello: ((Double) -> Void)?
    /// Ha finito di dire tutto quello che c'era da dire (o e' stata fermata).
    var onTermine: (() -> Void)?
    var onCambio: (() -> Void)?

    private var lingua = "it"
    private var neuraleOffertoDalServer: String?
    private var neuraleLentoFinoA = Date.distantPast

    // neurale
    private typealias Voce = (testo: String, audio: Task<URL?, Never>)
    private var coda: [Voce] = []
    private var ultimaSintesi: Task<URL?, Never>?
    private var lettore: Task<Void, Never>?
    private var giro = 0
    private var terminataNelGiro = -1
    private var finitoDiAccodare = false
    private var primaFrase = true
    private var player: AVAudioPlayer?
    private var continuazione: CheckedContinuation<Void, Never>?

    // sistema
    private let sintetizzatore = AVSpeechSynthesizer()
    private var pendentiSistema = 0
    private var impulso = 0.0

    private var timerLivello: Timer?
    private var inizioProva = Date()
    private var durataProva: TimeInterval = 0

    override init() {
        super.init()
        sintetizzatore.delegate = self
    }

    // MARK: scelta della voce

    nonisolated static var velocita: Double {
        get { (UserDefaults.standard.object(forKey: "velocitaVoce") as? Double) ?? 0.52 }
        set { UserDefaults.standard.set(min(0.72, max(0.34, newValue)), forKey: "velocitaVoce") }
    }

    /// Le voci di sistema che Jarvis usa: premium prima, poi avanzate, poi (solo se l'hai
    /// permesso) quelle di base non buffe. Ordine: qualita', poi la lingua esatta, poi il nome.
    static func vociDisponibili(lingua: String) -> [AVSpeechSynthesisVoice] {
        let prefisso = lingua == "it" ? "it" : "en"
        let esatta = lingua == "it" ? "it-IT" : "en-US"
        let baseAmmessa = UserDefaults.standard.bool(forKey: "voceBaseAmmessa")
        func punti(_ v: AVSpeechSynthesisVoice) -> Int {
            var p = 0
            switch v.quality {
            case .premium: p += 30
            case .enhanced: p += 20
            default: p += 0
            }
            if v.language == esatta { p += 5 }
            return p
        }
        return AVSpeechSynthesisVoice.speechVoices()
            .filter { $0.language.hasPrefix(prefisso) }
            .filter { $0.quality == .premium || $0.quality == .enhanced || (baseAmmessa && !buffa($0)) }
            .sorted { (punti($0), $1.name) > (punti($1), $0.name) }
    }

    /// Le voci a effetto (robot, sussurri, campane) non sono mai una scelta per Jarvis.
    private static func buffa(_ v: AVSpeechSynthesisVoice) -> Bool {
        let id = v.identifier.lowercased()
        return id.contains("speech.synthesis.voice") || id.contains("eloquence")
    }

    static func voceDiSistema(lingua: String) -> AVSpeechSynthesisVoice? {
        let voci = vociDisponibili(lingua: lingua)
        if let scelta = UserDefaults.standard.string(forKey: "voceJarvis"),
           let v = voci.first(where: { $0.identifier == scelta }) { return v }
        return voci.first
    }

    static func etichetta(_ v: AVSpeechSynthesisVoice) -> String {
        let q = v.quality == .premium ? "premium" : (v.quality == .enhanced ? (Lingua.risolvi() == "it" ? "avanzata" : "enhanced")
                                                                            : (Lingua.risolvi() == "it" ? "base" : "basic"))
        return "\(v.name) (\(q))"
    }

    /// Una voce neurale appena comparsa (Voicebox avviato): il ricordo del "non ha risposto in
    /// tempo" non vale piu', si riprova subito.
    func dimenticaRitardo() { neuraleLentoFinoA = .distantPast }

    /// Da chiamare quando il pannello si apre: decide che voce avra' e lo scrive.
    func prepara(lingua: String, neurale: String?) {
        self.lingua = lingua
        neuraleOffertoDalServer = neurale
        avviso = nil
        let it = lingua == "it"
        if let n = neurale, Date() >= neuraleLentoFinoA {
            // anche in prova: la sintesi vera passa dal server, e solo il suono non c'e'
            modo = .neurale(n)
            descrizione = (it ? "Voce neurale: " : "Neural voice: ") + (n == "pocket" ? "Pocket" : "Voicebox")
        } else if JarvisProva.attivo {
            modo = .muta
            descrizione = it ? "Prova: nessun audio, voce recitata" : "Test: no audio, voice simulated"
        } else if let v = VoceJarvis.voceDiSistema(lingua: lingua) {
            modo = .sistema
            descrizione = (it ? "Voce di sistema: " : "System voice: ") + VoceJarvis.etichetta(v)
            if neurale == nil {
                avviso = it ? "Nessuna voce neurale locale in ascolto (Voicebox non risponde)."
                            : "No local neural voice is listening (Voicebox is not answering)."
            }
        } else {
            modo = .muta
            descrizione = it ? "Solo testo: nessuna voce avanzata installata"
                             : "Text only: no enhanced voice installed"
            avviso = it ? "Scarica una voce avanzata o premium in Impostazioni di sistema, Accessibilità, Contenuto letto."
                        : "Download an enhanced or premium voice in System Settings, Accessibility, Spoken Content."
        }
        onCambio?()
    }

    // MARK: una risposta

    /// Comincia una risposta nuova: quella che stava parlando si zittisce.
    func nuovaRisposta() {
        fermaSilenziosa()
        giro += 1
        finitoDiAccodare = false
        primaFrase = true
        durataProva = 0
        inizioProva = Date()
    }

    /// Una frase da dire, gia' ripulita dal server.
    func accoda(_ frase: String) {
        let f = frase.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !f.isEmpty else { return }
        avviaLivello()
        switch modo {
        case .muta:
            if JarvisProva.attivo {
                parlando = true
                durataProva += max(0.8, Double(f.count) / 14)
            }
        case .sistema:
            parlaSistema(f)
        case .neurale:
            let precedente = ultimaSintesi
            // quanto aspettare una frase: quanto il server (`attesa_voce_neurale` in config.json,
            // di serie 9 secondi) piu' un secondo; alle frasi dopo la prima, che si preparano
            // mentre l'altra suona, si concede di piu'
            let base = (Casa.config["attesa_voce_neurale"] as? Double) ?? 9
            let attesa: TimeInterval = primaFrase ? base + 1 : max(25, base + 1)
            primaFrase = false
            let l = lingua
            let t = Task<URL?, Never> {
                _ = await precedente?.value
                if Task.isCancelled { return nil }
                let via = Date()
                let u = await ReteJarvis.sintetizza(f, lingua: l, attesa: attesa)
                Log.write("jarvis: voce neurale, frase di \(f.count) caratteri in \(String(format: "%.1f", Date().timeIntervalSince(via))) s: \(u == nil ? "niente" : "pronta")")
                return u
            }
            ultimaSintesi = t
            coda.append((f, t))
            parlando = true
            if lettore == nil {
                let g = giro
                lettore = Task { [weak self] in await self?.leggi(g) }
            }
        }
    }

    /// Non arrivano altre frasi.
    func finito() {
        Log.write("jarvis: voce, non arrivano altre frasi (in coda \(coda.count), lettore \(lettore != nil ? "si" : "no"))")
        finitoDiAccodare = true
        controllaTermine()
    }

    /// Esc, un clic su Ferma, o il pannello si chiude.
    func ferma() {
        fermaSilenziosa()
        giro += 1
        finitoDiAccodare = true
        terminataNelGiro = giro
        onTermine?()
    }

    private func fermaSilenziosa() {
        lettore?.cancel()
        lettore = nil
        for v in coda { v.audio.cancel() }
        ultimaSintesi?.cancel()
        ultimaSintesi = nil
        coda.removeAll()
        player?.stop()
        player = nil
        sintetizzatore.stopSpeaking(at: .immediate)
        pendentiSistema = 0
        if let c = continuazione { continuazione = nil; c.resume() }
        parlando = false
        durataProva = 0
        fermaLivello()
        onLivello?(0)
    }

    private func controllaTermine() {
        guard finitoDiAccodare, terminataNelGiro != giro else { return }
        if JarvisProva.attivo, modo == .muta, Date().timeIntervalSince(inizioProva) < durataProva { return }
        guard coda.isEmpty, lettore == nil, pendentiSistema == 0, player == nil else { return }
        terminataNelGiro = giro
        parlando = false
        fermaLivello()
        onLivello?(0)
        onTermine?()
    }

    // MARK: neurale

    private func leggi(_ g: Int) async {
        while g == giro, !Task.isCancelled {
            guard !coda.isEmpty else {
                if finitoDiAccodare { break }
                try? await Task.sleep(nanoseconds: 40_000_000)
                continue
            }
            let voce = coda.removeFirst()
            let url = await voce.audio.value
            if g != giro || Task.isCancelled { return }
            if let url = url {
                await suona(url)
                continue
            }
            // La frase non e' arrivata: per il resto della risposta parla il sistema.
            Log.write("jarvis: la voce neurale non ha risposto in tempo, passo alla voce di sistema")
            neuraleLentoFinoA = Date().addingTimeInterval(90)
            let resto = [voce.testo] + coda.map { $0.testo }
            for v in coda { v.audio.cancel() }
            coda.removeAll()
            passaAlSistema()
            for f in resto { parlaSistema(f) }
            break
        }
        if g == giro {
            lettore = nil
            controllaTermine()
        }
    }

    private func passaAlSistema() {
        let it = lingua == "it"
        if JarvisProva.attivo {
            modo = .muta
            descrizione = it ? "Prova: voce di sistema recitata, nessun audio" : "Test: system voice simulated, no audio"
            avviso = it ? "La voce neurale non ha risposto in tempo: per ora parla la voce di sistema."
                        : "The neural voice did not answer in time: the system voice is speaking for now."
            durataProva = 0
            inizioProva = Date()
        } else if let v = VoceJarvis.voceDiSistema(lingua: lingua) {
            modo = .sistema
            descrizione = (it ? "Voce di sistema: " : "System voice: ") + VoceJarvis.etichetta(v)
            avviso = it ? "La voce neurale non ha risposto in tempo: per ora parla la voce di sistema."
                        : "The neural voice did not answer in time: the system voice is speaking for now."
        } else {
            modo = .muta
            descrizione = it ? "Solo testo: nessuna voce avanzata installata" : "Text only: no enhanced voice installed"
            avviso = it ? "La voce neurale non ha risposto e non c'è una voce avanzata di sistema."
                        : "The neural voice did not answer and there is no enhanced system voice."
        }
        onCambio?()
    }

    private func suona(_ url: URL) async {
        if JarvisProva.attivo {
            // Niente altoparlante: si legge quanto dura il file e si aspetta altrettanto.
            let durata = (try? AVAudioFile(forReading: url)).map {
                Double($0.length) / $0.processingFormat.sampleRate } ?? 0.5
            parlando = true
            inizioProva = Date()
            durataProva = durata
            try? await Task.sleep(nanoseconds: UInt64(durata * 1_000_000_000))
            return
        }
        guard let p = try? AVAudioPlayer(contentsOf: url) else { return }
        p.delegate = self
        p.isMeteringEnabled = true
        player = p
        p.prepareToPlay()
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            continuazione = c
            if !p.play() {
                continuazione = nil
                c.resume()
            }
        }
        if player === p { player = nil }
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            if let c = self.continuazione { self.continuazione = nil; c.resume() }
        }
    }

    // MARK: sistema

    private func parlaSistema(_ frase: String) {
        if JarvisProva.attivo {
            // mai la voce vera in prova: si recita
            parlando = true
            avviaLivello()
            durataProva += max(0.8, Double(frase.count) / 14)
            return
        }
        guard let v = VoceJarvis.voceDiSistema(lingua: lingua) else { return }
        let u = AVSpeechUtterance(string: frase)
        u.voice = v
        u.rate = Float(VoceJarvis.velocita)
        u.postUtteranceDelay = 0.04
        pendentiSistema += 1
        parlando = true
        sintetizzatore.speak(u)
    }

    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) {
        Task { @MainActor in
            self.pendentiSistema = max(0, self.pendentiSistema - 1)
            self.controllaTermine()
        }
    }

    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) {
        Task { @MainActor in self.pendentiSistema = max(0, self.pendentiSistema - 1) }
    }

    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, willSpeakRangeOfSpeechString r: NSRange,
                                       utterance u: AVSpeechUtterance) {
        // il sistema non da' il livello dell'audio: ogni parola e' un impulso, che poi cala
        Task { @MainActor in self.impulso = 0.55 + Double.random(in: 0...0.4) }
    }

    // MARK: livello per l'onda

    private func avviaLivello() {
        guard timerLivello == nil else { return }
        timerLivello = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.passoLivello() }
        }
    }

    private func fermaLivello() {
        timerLivello?.invalidate()
        timerLivello = nil
        impulso = 0
    }

    private func passoLivello() {
        var l = 0.0
        if let p = player, p.isPlaying {
            p.updateMeters()
            let db = Double(p.averagePower(forChannel: 0))
            l = min(1, max(0, (db + 46) / 40))
        } else if pendentiSistema > 0 {
            impulso *= 0.86
            l = impulso
        } else if JarvisProva.attivo, parlando {
            let t = Date().timeIntervalSince(inizioProva)
            if t >= durataProva, modo == .muta {
                controllaTermine()
                return
            }
            l = t < durataProva ? 0.25 + 0.45 * abs(sin(t * 9)) * abs(sin(t * 3.1)) : 0.05
        }
        onLivello?(l)
    }
}
