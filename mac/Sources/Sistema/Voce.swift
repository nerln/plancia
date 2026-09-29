// Voce: riproduzione, ascolto e il pannello "Chiedi a Plancia". Il pannello
// Jarvis, piu' grande, sta in jarvis.swift.

import AppKit
import AVFoundation
import Speech

// MARK: - riproduzione

final class Player: NSObject, AVAudioPlayerDelegate {
    static let shared = Player()
    private var player: AVAudioPlayer?
    var onFinish: (() -> Void)?

    func play(path: String) {
        stop()
        guard let p = try? AVAudioPlayer(contentsOf: URL(fileURLWithPath: path)) else { return }
        p.delegate = self
        player = p
        p.play()
    }
    func stop() {
        player?.stop()
        player = nil
    }
    var isPlaying: Bool { player?.isPlaying ?? false }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        self.player = nil
        onFinish?()
    }
}

// MARK: - ascolto

final class Listener {
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var recognizer: SFSpeechRecognizer?
    private(set) var attivo = false

    static func locale(for lang: String) -> Locale {
        let map = ["it": "it-IT", "en": "en-US", "es": "es-ES",
                   "fr": "fr-FR", "de": "de-DE", "pt": "pt-BR"]
        return Locale(identifier: map[lang] ?? "en-US")
    }

    func chiediPermessi(_ done: @escaping (Bool, String) -> Void) {
        SFSpeechRecognizer.requestAuthorization { stato in
            DispatchQueue.main.async {
                guard stato == .authorized else {
                    return done(false, "Riconoscimento vocale non autorizzato. Si abilita in Impostazioni di sistema, Privacy e sicurezza.")
                }
                AVCaptureDevice.requestAccess(for: .audio) { ok in
                    DispatchQueue.main.async {
                        done(ok, ok ? "" : "Microfono non autorizzato.")
                    }
                }
            }
        }
    }

    func start(lang: String, parziale: @escaping (String) -> Void,
               errore: @escaping (String) -> Void) {
        stop()
        let rec = SFSpeechRecognizer(locale: Listener.locale(for: lang))
        guard let rec = rec, rec.isAvailable else {
            return errore("Riconoscimento non disponibile per questa lingua.")
        }
        recognizer = rec
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        request = req

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            req.append(buffer)
        }
        engine.prepare()
        do { try engine.start() } catch {
            return errore("Non riesco ad aprire il microfono.")
        }
        attivo = true
        task = rec.recognitionTask(with: req) { result, err in
            if let result = result {
                parziale(result.bestTranscription.formattedString)
            }
            if err != nil && self.attivo == false { return }
        }
    }

    @discardableResult
    func stop() -> Bool {
        guard attivo else { return false }
        attivo = false
        engine.inputNode.removeTap(onBus: 0)
        if engine.isRunning { engine.stop() }
        request?.endAudio()
        task?.finish()
        request = nil
        task = nil
        return true
    }
}

// MARK: - pannello della voce

final class VoicePanel: NSWindowController {
    private let testo = NSTextView()
    private let stato = NSTextField(labelWithString: "")
    private let bottoneParla = NSButton()
    private let bottoneRiepilogo = NSButton()
    private let bottoneStop = NSButton()
    private let scelta = NSPopUpButton()
    private let listener = Listener()
    private var trascrizione = ""
    private var occupato = false

    convenience init() {
        let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 460, height: 340),
                            styleMask: [.titled, .closable, .utilityWindow, .hudWindow],
                            backing: .buffered, defer: false)
        panel.title = "Plancia"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        self.init(window: panel)
        costruisci()
    }

    private func costruisci() {
        guard let content = window?.contentView else { return }

        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        testo.isEditable = false
        testo.drawsBackground = false
        testo.font = NSFont.systemFont(ofSize: 13)
        testo.textContainerInset = NSSize(width: 6, height: 6)
        testo.string = ""
        scroll.documentView = testo
        scroll.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(scroll)

        stato.font = NSFont.systemFont(ofSize: 11)
        stato.textColor = .secondaryLabelColor
        stato.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(stato)

        for (b, titolo, sel) in [
            (bottoneRiepilogo, "Riepilogo", #selector(riepilogo)),
            (bottoneParla, "Tieni premuto e parla", #selector(parla)),
            (bottoneStop, "Ferma", #selector(ferma)),
        ] {
            b.title = titolo
            b.bezelStyle = .rounded
            b.target = self
            b.action = sel
            b.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(b)
        }
        bottoneParla.setButtonType(.pushOnPushOff)

        scelta.addItems(withTitles: ["it", "en", "es", "fr", "de", "pt"])
        scelta.selectItem(withTitle: Conf.lang)
        scelta.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(scelta)

        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: content.topAnchor, constant: 12),
            scroll.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 12),
            scroll.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -12),
            scroll.bottomAnchor.constraint(equalTo: stato.topAnchor, constant: -8),

            stato.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 14),
            stato.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -14),
            stato.bottomAnchor.constraint(equalTo: bottoneParla.topAnchor, constant: -8),

            bottoneRiepilogo.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 12),
            bottoneRiepilogo.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
            bottoneParla.leadingAnchor.constraint(equalTo: bottoneRiepilogo.trailingAnchor, constant: 8),
            bottoneParla.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
            bottoneStop.leadingAnchor.constraint(equalTo: bottoneParla.trailingAnchor, constant: 8),
            bottoneStop.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
            scelta.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -12),
            scelta.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
            scelta.widthAnchor.constraint(equalToConstant: 66),
        ])
    }

    private var lingua: String { scelta.titleOfSelectedItem ?? Conf.lang }

    private func mostra(_ s: String) {
        testo.string = s
        testo.scrollToBeginningOfDocument(nil)
    }

    private func lavora(_ acceso: Bool, _ messaggio: String = "") {
        occupato = acceso
        stato.stringValue = messaggio
        bottoneRiepilogo.isEnabled = !acceso
    }

    @objc func riepilogo() {
        guard !occupato else { return }
        lavora(true, "preparo il riepilogo…")
        mostra("")
        API.request("/api/recap", method: "POST",
                    body: ["voce": true, "lang": lingua]) { j, err in
            self.lavora(false, "")
            if let err = err { return self.mostra("Errore: \(err)") }
            guard let j = j else { return self.mostra("Nessuna risposta dal backend.") }
            self.mostra((j["testo"] as? String) ?? "")
            self.stato.stringValue = "voce: \((j["motore"] as? String) ?? "?")"
            if let file = j["file"] as? String { Player.shared.play(path: file) }
            else { self.scaricaEsuona(j["url"] as? String) }
        }
    }

    private func scaricaEsuona(_ url: String?) {
        guard let url = url, let u = URL(string: Conf.base + url) else { return }
        URLSession.shared.downloadTask(with: u) { tmp, _, _ in
            guard let tmp = tmp else { return }
            let dest = FileManager.default.temporaryDirectory
                .appendingPathComponent("plancia-\(UUID().uuidString).wav")
            try? FileManager.default.moveItem(at: tmp, to: dest)
            DispatchQueue.main.async { Player.shared.play(path: dest.path) }
        }.resume()
    }

    @objc func ferma() {
        Player.shared.stop()
        if listener.stop() { bottoneParla.state = .off }
        lavora(false, "")
    }

    @objc func parla() {
        if listener.attivo {
            listener.stop()
            bottoneParla.state = .off
            invia(trascrizione)
            return
        }
        listener.chiediPermessi { ok, messaggio in
            guard ok else {
                self.bottoneParla.state = .off
                return self.mostra(messaggio)
            }
            self.trascrizione = ""
            self.mostra("")
            self.stato.stringValue = "ti ascolto, premi di nuovo quando hai finito"
            self.bottoneParla.state = .on
            self.listener.start(lang: self.lingua, parziale: { t in
                self.trascrizione = t
                self.mostra(t)
            }, errore: { e in
                self.bottoneParla.state = .off
                self.mostra(e)
            })
        }
    }

    fileprivate func invia(_ domanda: String) {
        let q = domanda.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return lavora(false, "non ho sentito niente") }
        lavora(true, "ci penso…")
        mostra(q + "\n\n…")
        API.request("/api/voice/ask", method: "POST",
                    body: ["domanda": q, "lang": lingua, "voce": true]) { j, err in
            self.lavora(false, "")
            if let err = err { return self.mostra("Errore: \(err)") }
            let risposta = (j?["risposta"] as? String) ?? ""
            self.mostra("\(q)\n\n\(risposta)")
            if let file = j?["file"] as? String { Player.shared.play(path: file) }
            else { self.scaricaEsuona(j?["url"] as? String) }
        }
    }

    /// Domanda arrivata da fuori, per esempio da uno schema URL.
    func chiediTesto(_ q: String) {
        invia(q)
    }

    func apri() {
        window?.center()
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func apriEriepiloga() {
        apri()
        riepilogo()
    }
}
