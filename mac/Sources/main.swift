// Plancia per macOS.
//
// L'app è una finestra nativa sulla dashboard più le cose che il browser non
// può fare: tenere vivo il backend, stare nella barra dei menu, parlare e
// ascoltare. Il contenuto resta quello servito da 127.0.0.1, così l'app e il
// browser mostrano sempre la stessa cosa.

import AppKit
import AVFoundation
import CoreServices
import Speech
import UserNotifications
import WebKit

// MARK: - configurazione

struct Conf {
    static let home = FileManager.default.homeDirectoryForCurrentUser
    static var dataDir: URL { home.appendingPathComponent(".plancia") }

    static var settings: [String: Any] {
        guard let d = try? Data(contentsOf: dataDir.appendingPathComponent("config.json")),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        return j
    }
    static var port: Int { (settings["port"] as? Int) ?? 7773 }
    static var lang: String { (settings["lingua"] as? String) ?? "it" }
    static var base: String { "http://127.0.0.1:\(port)" }
    static var token: String {
        (try? String(contentsOf: dataDir.appendingPathComponent("token"), encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    /// Il comando `plancia`. Il percorso vero lo scrive lo script di build,
    /// gli altri sono i posti dove finisce normalmente.
    static var executable: String? {
        var candidati: [String] = []
        if let p = Bundle.main.object(forInfoDictionaryKey: "PlanciaExecutable") as? String {
            candidati.append(p)
        }
        candidati += [
            home.appendingPathComponent(".local/bin/plancia").path,
            "/usr/local/bin/plancia",
            "/opt/homebrew/bin/plancia",
            home.appendingPathComponent("dev/plancia/bin/plancia").path,
        ]
        return candidati.first { FileManager.default.isExecutableFile(atPath: $0) }
    }
}

// MARK: - diario

/// Un file di testo in ~/.plancia/app.log. Senza questo, quando l'app non fa
/// quello che dovrebbe non si vede niente da nessuna parte.
enum Log {
    static let file = Conf.dataDir.appendingPathComponent("app.log")
    static func write(_ s: String) {
        let riga = "\(ISO8601DateFormatter().string(from: Date())) \(s)\n"
        guard let d = riga.data(using: .utf8) else { return }
        if let fh = try? FileHandle(forWritingTo: file) {
            fh.seekToEndOfFile(); fh.write(d); try? fh.close()
        } else {
            try? d.write(to: file)
        }
    }
}

// MARK: - chiamate al backend

enum API {
    static func request(_ path: String, method: String = "GET", body: [String: Any]? = nil,
                        timeout: TimeInterval = 180,
                        done: @escaping ([String: Any]?, String?) -> Void) {
        guard let url = URL(string: Conf.base + path) else { return done(nil, "url non valida") }
        var req = URLRequest(url: url, timeoutInterval: timeout)
        req.httpMethod = method
        req.setValue(Conf.token, forHTTPHeaderField: "X-Plancia-Token")
        if let body = body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        // Il registro non deve riempirsi di niente: il pannello vocale chiede
        // gli eventi ogni sei secondi, e sarebbero milleduecento righe l'ora.
        let silenzioso = path.hasPrefix("/api/eventi")
        if !silenzioso { Log.write("richiesta \(method) \(path)") }
        URLSession.shared.dataTask(with: req) { data, res, err in
            if let err = err {
                Log.write("errore \(path): \(err.localizedDescription)")
                return DispatchQueue.main.async { done(nil, err.localizedDescription) }
            }
            let code = (res as? HTTPURLResponse)?.statusCode ?? 0
            let j = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
            if !silenzioso { Log.write("risposta \(path): \(code)") }
            DispatchQueue.main.async { done(j, j?["errore"] as? String) }
        }.resume()
    }

    /// Come `request`, ma per le rotte che tornano una lista invece di un
    /// oggetto: `/api/projects`, `/api/runs`.
    static func lista(_ path: String, timeout: TimeInterval = 20,
                      done: @escaping ([[String: Any]]) -> Void) {
        guard let url = URL(string: Conf.base + path) else { return done([]) }
        var req = URLRequest(url: url, timeoutInterval: timeout)
        req.setValue(Conf.token, forHTTPHeaderField: "X-Plancia-Token")
        URLSession.shared.dataTask(with: req) { data, _, _ in
            let j = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [[String: Any]]
            DispatchQueue.main.async { done(j ?? []) }
        }.resume()
    }

    static func alive(_ done: @escaping (Bool) -> Void) {
        guard let url = URL(string: Conf.base + "/api/status") else { return done(false) }
        var req = URLRequest(url: url, timeoutInterval: 2)
        req.httpMethod = "GET"
        URLSession.shared.dataTask(with: req) { data, res, _ in
            let ok = (res as? HTTPURLResponse)?.statusCode == 200 && data != nil
            DispatchQueue.main.async { done(ok) }
        }.resume()
    }
}

// MARK: - il backend, tenuto vivo

final class Backend {
    private var process: Process?
    private(set) var avviatoDaNoi = false

    func ensureRunning(_ done: @escaping (Bool) -> Void) {
        API.alive { up in
            if up { return done(true) }
            guard let exe = Conf.executable else { return done(false) }
            let p = Process()
            p.executableURL = URL(fileURLWithPath: exe)
            p.arguments = ["serve"]
            p.standardOutput = FileHandle.nullDevice
            p.standardError = FileHandle.nullDevice
            do { try p.run() } catch { return done(false) }
            self.process = p
            self.avviatoDaNoi = true
            self.attendi(tentativi: 25, done: done)
        }
    }

    private func attendi(tentativi: Int, done: @escaping (Bool) -> Void) {
        if tentativi <= 0 { return done(false) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            API.alive { up in
                if up { done(true) } else { self.attendi(tentativi: tentativi - 1, done: done) }
            }
        }
    }

    func stopIfOurs() {
        // Se il backend gira per conto suo (launchd) non è compito nostro spegnerlo.
        if avviatoDaNoi, let p = process, p.isRunning { p.terminate() }
    }
}

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

// MARK: - applicazione

extension WKWebView {
    /// Altezza vera del documento, per non tagliare il PDF a metà pagina.
    func scrollView_altezza() -> CGFloat {
        var h: CGFloat = 900
        let semaforo = DispatchSemaphore(value: 0)
        evaluateJavaScript("document.body.scrollHeight") { r, _ in
            if let n = r as? CGFloat { h = n } else if let n = r as? Double { h = CGFloat(n) }
            semaforo.signal()
        }
        _ = semaforo.wait(timeout: .now() + 0.4)
        return max(700, h)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    private var window: NSWindow!
    private var web: WKWebView!
    /// Il materiale nativo dietro tutta la finestra (NSGlassEffectView o
    /// NSVisualEffectView, vedi costruisciFinestra()). Tenuto in una
    /// proprietà, non in una variabile locale, perché il gestore `tema` più
    /// sotto deve poterci scrivere sopra dopo che la finestra è già in piedi:
    /// vedi il commento su userContentController(_:didReceive:).
    private var materiale: NSView!
    private let backend = Backend()
    private var statusItem: NSStatusItem!
    private lazy var voce = VoicePanel()
    private lazy var jarvis: JarvisPanel = {
        let p = JarvisPanel()
        p.onAzione = { [weak self] a in self?.eseguiAzione(a) }
        return p
    }()
    private var timerRiepilogo: Timer?

    /// L'evento di apertura URL va agganciato prima che l'app finisca di
    /// avviarsi, altrimenti il primo `plancia://` si perde.
    func applicationWillFinishLaunching(_ n: Notification) {
        NSAppleEventManager.shared().setEventHandler(
            self, andSelector: #selector(gestisciEventoURL(_:withReply:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL))
    }

    @objc func gestisciEventoURL(_ evento: NSAppleEventDescriptor,
                                 withReply reply: NSAppleEventDescriptor) {
        guard let s = evento.paramDescriptor(forKeyword: keyDirectObject)?.stringValue,
              let url = URL(string: s) else { return }
        esegui(url)
    }

    func applicationDidFinishLaunching(_ n: Notification) {
        Log.write("avvio, backend su \(Conf.base), token \(Conf.token.isEmpty ? "assente" : "presente")")
        costruisciFinestra()
        costruisciMenuBar()
        costruisciMenuPrincipale()
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }

        Scorciatoia.azione = { [weak self] in self?.apriJarvis() }
        Scorciatoia.registra()

        backend.ensureRunning { ok in
            if ok {
                self.carica()
            } else {
                self.mostraErroreBackend()
            }
        }
        programmaRiepilogo()
    }

    // --- finestra ---

    private func costruisciFinestra() {
        let conf = WKWebViewConfiguration()
        let js = """
        document.documentElement.dataset.app = 'mac';
        """
        conf.userContentController.addUserScript(
            WKUserScript(source: js, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        // Tema dell'app e tema della pagina (L4-VETRO-2, consigliata del
        // critico del primo giro, punto 7 del lotto - contratto con
        // L4-MEMORIA che possiede web/app.js e ci manda il messaggio). Il
        // materiale nativo dietro la finestra segue l'aspetto di SISTEMA per
        // default; la pagina invece segue `plancia-theme`, che può essere
        // forzato al contrario del sistema, o lasciato su 'auto'. Senza
        // questo handler, con tema forzato, il testo che sta FUORI dai
        // pannelli di vetro (non coperto da nessun .panel/.card) si
        // troverebbe sopra un materiale nativo del colore sbagliato - lo
        // stesso problema che gli aloni di body::before risolvono fuori
        // dall'app, qui dentro l'app. Quando la pagina calcola il tema
        // risolto chiama webkit.messageHandlers.tema.postMessage('light'|
        // 'dark'); questo handler forza l'aspetto sul MATERIALE, non sulla
        // finestra (vedi userContentController(_:didReceive:) più sotto):
        // window.appearance è l'antenato di cui web/app.js:2061-2075 legge
        // prefers-color-scheme via matchMedia per risolvere 'auto', quindi
        // se lo forzassimo qui, in modalità 'auto' il primo messaggio
        // fisserebbe la vista sul valore di quel momento e un cambio di
        // aspetto del sistema, dopo, non arriverebbe più alla pagina (il
        // listener 'change' di matchMedia non scatterebbe mai). Il
        // materiale, invece, è fratello della WKWebView sotto `contenuto`
        // (vedi costruisciFinestra() più sotto): assegnargli .appearance non
        // tocca ciò che la pagina legge, la pagina continua a seguire il
        // sistema, e il materiale segue il tema che la pagina ha risolto.
        // Una pagina vecchia (senza quella chiamata) non manda mai il
        // messaggio: il materiale resta sull'aspetto di sistema,
        // comportamento invariato.
        conf.userContentController.add(self, name: "tema")
        web = WKWebView(frame: .zero, configuration: conf)
        web.navigationDelegate = self
        // Vetro L2-GLASS: senza questo, WKWebView dipinge il proprio sfondo
        // bianco/nero opaco prima ancora che arrivi il CSS della pagina, e
        // col body trasparente su tutta la finestra dentro l'app (L4-VETRO,
        // decisione 18/09: non più solo la colonna del rail, vedi
        // web/style.css "dentro l'app") si vedrebbe quell'opaco al posto
        // del materiale nativo dietro, su tutta la finestra.
        web.setValue(false, forKey: "drawsBackground")

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1180, height: 780),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable,
                                      .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.title = "Plancia"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.minSize = NSSize(width: 880, height: 560)
        // Vetro L2-GLASS: la finestra stessa deve smettere di dipingere il
        // proprio sfondo opaco, altrimenti coprirebbe il materiale nativo
        // messo dietro tutta la finestra qui sotto ancora prima del WKWebView.
        window.isOpaque = false
        window.backgroundColor = .clear

        let contenuto = NSView(frame: NSRect(x: 0, y: 0, width: 1180, height: 780))

        // Il materiale nativo dietro TUTTA la finestra (decisione di Eugenio
        // del 18/09/2026, L4-VETRO, parole sue: "voglio un più ampio uso di
        // liquid glass per tutti i progetti ... deve sembrare tutto vetro":
        // SOSTITUISCE il materiale di L2-GLASS, largo solo quanto il rail -
        // Self.railW e la sua sincronia a mano con --rail-w in CSS sono
        // spariti con lui, vedi docs/lotti/LOTTO-L4-VETRO.md). Da macOS 26
        // NSGlassEffectView (Liquid Glass); prima NSVisualEffectView con
        // .underWindowBackground - il materiale che Apple documenta apposta
        // per lo sfondo di un'intera finestra, a differenza di .sidebar (una
        // fascia stretta, giusto per il vecchio rail) o di .hudWindow (un
        // pannello scuro isolato tipo HUD, non l'intera finestra): scelto
        // per questo, non verificato a vista qui (l'app non si apre da
        // questo lotto, lo fa il coordinatore con Eugenio). Sta DIETRO il
        // WKWebView nello z-order (aggiunto per primo), prende il bounds del
        // contentView con autoresizingMask width+height, così segue il
        // ridimensionamento della finestra su entrambi gli assi: ogni
        // pannello di vetro della pagina (non solo il rail, vedi
        // web/style.css) lo lascia intravedere col proprio backdrop-filter.
        // Proprietà dell'istanza (non `let` locale): il gestore `tema` più
        // sotto ci scrive .appearance dopo che la finestra è già in piedi.
        if #available(macOS 26, *) {
            let vetro = NSGlassEffectView(frame: contenuto.bounds)
            // Letto dall'header di questa macchina (macOS 27, Xcode 27,
            // NSGlassEffectView.h): esistono anche cornerRadius, tintColor,
            // style (.regular/.clear) e, da macOS 27, effectIsInteractive;
            // c'è pure NSGlassEffectContainerView, ma è per fondere più
            // NSGlassEffectView vicini fra loro (qui ce n'è uno solo, dietro
            // tutta la finestra: non serve). cornerRadius resta 0 (il
            // materiale copre l'intera finestra, senza angoli da smussare) e
            // tintColor resta assente (l'ambra rimane solo un accento nei
            // pannelli CSS, non nel materiale nativo).
            // style, punto 6 del lotto L4-VETRO-2: esplicito a .regular, non
            // lasciato al default implicito. .clear è pensato per un
            // elemento isolato e piccolo (un controllo, una card fluttuante)
            // che deve sembrare vetro sottile e quasi invisibile sopra
            // quello che ha dietro; .regular è il materiale "di sistema",
            // pensato per una superficie grande e stabile come lo sfondo di
            // un'intera finestra - la stessa distinzione che la scelta di
            // .underWindowBackground faceva già nel ramo else qui sotto.
            vetro.style = .regular
            self.materiale = vetro
        } else {
            let effetto = NSVisualEffectView(frame: contenuto.bounds)
            effetto.material = .underWindowBackground
            effetto.blendingMode = .behindWindow
            effetto.state = .active
            self.materiale = effetto
        }
        materiale.autoresizingMask = [.width, .height]

        web.frame = contenuto.bounds
        web.autoresizingMask = [.width, .height]
        contenuto.addSubview(materiale)
        contenuto.addSubview(web)
        window.contentView = contenuto

        window.setFrameAutosaveName("PlanciaMain")
        window.center()
        window.makeKeyAndOrderFront(nil)
    }

    private func carica() {
        guard let url = URL(string: Conf.base) else { return }
        web.load(URLRequest(url: url))
    }

    private func mostraErroreBackend() {
        let html = """
        <html><body style="font:14px -apple-system;background:#0b0e13;color:#e9edf4;
        display:flex;align-items:center;justify-content:center;height:100vh;text-align:center">
        <div><h2>Plancia non parte</h2>
        <p>Non trovo il comando <code>plancia</code>.<br>
        Apri il Terminale ed esegui <code>cd ~/dev/plancia &amp;&amp; ./bin/plancia install</code>,
        poi riapri l'app.</p></div></body></html>
        """
        web.loadHTMLString(html, baseURL: nil)
    }

    // --- barra dei menu ---
    private func costruisciMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "location.north.circle",
                                   accessibilityDescription: "Plancia")
            button.image?.isTemplate = true
        }
        let menu = NSMenu()
        menu.addItem(voceMenu("Jarvis  ⌥Spazio", #selector(apriJarvis), "j"))
        menu.addItem(voceMenu("Riepilogo vocale", #selector(riepilogoVocale), "r"))
        menu.addItem(voceMenu("Chiedi a Plancia", #selector(apriVoce), "d"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(voceMenu("Apri la dashboard", #selector(apriFinestra), "o"))
        menu.addItem(voceMenu("Aggiorna i dati", #selector(sincronizza), "u"))
        menu.addItem(voceMenu("Salva una schermata", #selector(schermata), "s"))
        // Compare solo finché serve: una voce di menu che non serve più è
        // rumore.
        if !AscoltoContinuo.stato.micro || !AscoltoContinuo.stato.voce {
            menu.addItem(NSMenuItem.separator())
            menu.addItem(voceMenu("Attiva la voce…", #selector(chiediPermessi), ""))
        }
        menu.addItem(NSMenuItem.separator())
        menu.addItem(voceMenu("Esci da Plancia", #selector(esci), "q"))
        statusItem.menu = menu
    }

    private func voceMenu(_ titolo: String, _ sel: Selector, _ tasto: String) -> NSMenuItem {
        let item = NSMenuItem(title: titolo, action: sel, keyEquivalent: tasto)
        item.target = self
        return item
    }

    private func costruisciMenuPrincipale() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        main.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(voceMenu("Riepilogo vocale", #selector(riepilogoVocale), "r"))
        appMenu.addItem(voceMenu("Jarvis", #selector(apriJarvis), "j"))
        appMenu.addItem(voceMenu("Chiedi a Plancia", #selector(apriVoce), "d"))
        appMenu.addItem(voceMenu("Aggiorna i dati", #selector(sincronizza), "u"))
        appMenu.addItem(NSMenuItem.separator())
        // Nascondi va al responder chain, non a noi
        appMenu.addItem(NSMenuItem(title: "Nascondi", action: #selector(NSApplication.hide(_:)),
                                   keyEquivalent: "h"))
        appMenu.addItem(voceMenu("Esci da Plancia", #selector(esci), "q"))
        appItem.submenu = appMenu

        let vista = NSMenuItem()
        main.addItem(vista)
        let vistaMenu = NSMenu(title: "Vista")
        vistaMenu.addItem(voceMenu("Ricarica", #selector(ricarica), "R"))
        vistaMenu.addItem(voceMenu("Schermo intero", #selector(schermoIntero), "f"))
        vista.submenu = vistaMenu

        NSApp.mainMenu = main
    }

    // --- azioni ---
    @objc func apriFinestra() {
        if !window.isVisible { window.makeKeyAndOrderFront(nil) }
        NSApp.activate(ignoringOtherApps: true)
    }
    @objc func ricarica() { carica() }
    @objc func schermoIntero() { window.toggleFullScreen(nil) }
    @objc func apriVoce() { voce.apri() }
    @objc func apriJarvis() { jarvis.apri() }

    /// Quello che Jarvis decide di fare sull'app: cambiare vista, aprire un
    /// progetto, rileggere le fonti.
    private func eseguiAzione(_ a: [String: Any]) {
        switch a["tipo"] as? String {
        case "vai":
            if let v = a["vista"] as? String { vai(vista: v, ui: nil) }
        case "progetto":
            if let k = a["chiave"] as? String {
                vai(vista: "progetti", ui: nil)
                let js = #"setTimeout(function(){var e=document.querySelector('[data-project="\#(k)"]'); if (e) e.click();}, 700)"#
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                    self.web.evaluateJavaScript(js, completionHandler: nil)
                }
            }
        case "aggiorna":
            sincronizza()
        default:
            break
        }
        if a["tipo"] as? String != "ferma" { apriFinestra() }
    }
    @objc func riepilogoVocale() { voce.apriEriepiloga() }
    @objc func sincronizza() {
        API.request("/api/sync", method: "POST", body: [:]) { _, _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self.carica() }
        }
    }
    /// Salva la finestra in un PNG. Serve per gli screenshot dei post e per
    /// vedere com'è venuta senza dover essere davanti al Mac.
    @objc func schermata() {
        // Con la finestra coperta il sistema non aggiorna il disegno della
        // pagina e lo scatto esce vuoto: prima si porta davanti, poi si aspetta
        // un giro di disegno.
        // Se davanti c'è un'app a tutto schermo, la finestra sta in un altro
        // Spazio ed è considerata coperta: WebKit smette di disegnare e lo
        // scatto esce a metà. La si porta sullo Spazio corrente per il tempo
        // dello scatto e poi si rimette com'era.
        let comportamento = window.collectionBehavior
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
        attendiVisibile(tentativi: 24) {
            self.scatta()
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                self.window.collectionBehavior = comportamento
            }
        }
    }

    /// WebKit smette di disegnare quando la finestra è coperta: lo scatto
    /// uscirebbe con la sola parte già disegnata. Si aspetta che il sistema la
    /// dichiari visibile, non un tempo a caso.
    private func attendiVisibile(tentativi: Int, poi: @escaping () -> Void) {
        if tentativi <= 0 || window.occlusionState.contains(.visible) {
            return DispatchQueue.main.asyncAfter(deadline: .now() + 0.45, execute: poi)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            self.attendiVisibile(tentativi: tentativi - 1, poi: poi)
        }
    }

    /// Il PDF non copia quello che c'è sullo schermo: ridisegna la pagina da
    /// zero. È l'unico modo per avere l'immagine giusta anche quando la
    /// finestra è coperta da un'app a tutto schermo.
    private func scattaPDF(_ done: @escaping (URL?) -> Void) {
        let conf = WKPDFConfiguration()
        conf.rect = CGRect(x: 0, y: 0, width: web.bounds.width,
                           height: min(web.scrollView_altezza(), 2400))
        web.createPDF(configuration: conf) { esito in
            switch esito {
            case .success(let dati):
                let dir = Conf.dataDir.appendingPathComponent("shots")
                try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                let f = DateFormatter()
                f.dateFormat = "yyyyMMdd-HHmmss"
                let dest = dir.appendingPathComponent("plancia-\(f.string(from: Date())).pdf")
                try? dati.write(to: dest)
                Log.write("pdf salvato: \(dest.path)")
                done(dest)
            case .failure(let e):
                Log.write("pdf fallito: \(e.localizedDescription)")
                done(nil)
            }
        }
    }

    private func scatta() {
        let conf = WKSnapshotConfiguration()
        conf.afterScreenUpdates = true
        web.takeSnapshot(with: conf) { image, errore in
            guard let image = image,
                  let tiff = image.tiffRepresentation,
                  let rep = NSBitmapImageRep(data: tiff),
                  let png = rep.representation(using: .png, properties: [:]) else {
                Log.write("schermata fallita: \(errore?.localizedDescription ?? "?")")
                return
            }
            let dir = Conf.dataDir.appendingPathComponent("shots")
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let f = DateFormatter()
            f.dateFormat = "yyyyMMdd-HHmmss"
            let dest = dir.appendingPathComponent("plancia-\(f.string(from: Date())).png")
            try? png.write(to: dest)
            Log.write("schermata salvata: \(dest.path)")
        }
    }

    @objc func esci() {
        backend.stopIfOurs()
        NSApp.terminate(nil)
    }

    // --- riepilogo della mattina ---
    private func programmaRiepilogo() {
        timerRiepilogo?.invalidate()
        // Lo scheduler vero è launchd (`plancia daily on`). Qui solo se lo si
        // chiede esplicitamente con una chiave diversa, per non parlare due volte.
        guard let ora = Conf.settings["riepilogo_ora_app"] as? String, ora.contains(":") else { return }
        let pezzi = ora.split(separator: ":").compactMap { Int($0) }
        guard pezzi.count == 2 else { return }
        var comp = DateComponents()
        comp.hour = pezzi[0]
        comp.minute = pezzi[1]
        guard let prossimo = Calendar.current.nextDate(after: Date(), matching: comp,
                                                       matchingPolicy: .nextTime) else { return }
        timerRiepilogo = Timer(fire: prossimo, interval: 86400, repeats: true) { _ in
            self.voce.apriEriepiloga()
        }
        RunLoop.main.add(timerRiepilogo!, forMode: .common)
    }

    /// Chiede microfono e dettatura partendo da un clic dentro la finestra.
    ///
    /// Non è un giro inutile. La richiesta fatta dal pannello vocale, che è una
    /// finestra che di proposito non attiva l'app, spesso non fa comparire
    /// niente: il sistema mostra quelle finestre solo a un'app davanti, e la
    /// riconosce tale se la richiesta arriva dopo una cosa che hai fatto tu.
    /// Qui si porta l'app davanti, si spiega cosa sta per succedere, e solo dopo
    /// il tuo sì si chiede al sistema.
    @objc func chiediPermessi() {
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)

        let a = NSAlert()
        a.messageText = Conf.lang == "en" ? "Turn on the voice"
                      : (Conf.lang == "es" ? "Activar la voz" : "Attiva la voce")
        a.informativeText = Conf.lang == "en"
            ? "macOS will ask twice: for the microphone and for dictation. Both stay on this Mac: recognition runs locally and no audio is ever sent anywhere."
            : (Conf.lang == "es"
               ? "macOS te lo preguntará dos veces: micrófono y dictado. Los dos se quedan en este Mac: el reconocimiento es local y no se envía ningún audio."
               : "macOS te lo chiederà due volte: microfono e dettatura. Restano tutti e due su questo Mac, il riconoscimento è locale e nessun audio esce di qui.")
        a.addButton(withTitle: Conf.lang == "en" ? "Continue" : "Continua")
        a.addButton(withTitle: Conf.lang == "en" ? "Not now" : "Non ora")
        let scelta = a.runModal()
        Log.write("permessi: risposta alla finestra \(scelta.rawValue)")
        guard scelta == .alertFirstButtonReturn else { return }

        AVCaptureDevice.requestAccess(for: .audio) { micro in
            Log.write("permessi: microfono \(micro)")
            SFSpeechRecognizer.requestAuthorization { voce in
                Log.write("permessi: dettatura \(voce.rawValue)")
                DispatchQueue.main.async {
                    let fatto = micro && voce == .authorized
                    let b = NSAlert()
                    b.messageText = fatto
                        ? (Conf.lang == "en" ? "Voice is on" : "La voce è accesa")
                        : (Conf.lang == "en" ? "Still missing something" : "Manca ancora qualcosa")
                    b.informativeText = fatto
                        ? (Conf.lang == "en" ? "Press option space anywhere to talk to it."
                                             : "Premi opzione spazio da qualsiasi app per parlarci.")
                        : (Conf.lang == "en"
                           ? "Open System Settings, Privacy and Security, and allow Plancia under Microphone and Speech Recognition."
                           : "Apri Impostazioni di sistema, Privacy e sicurezza, e autorizza Plancia sotto Microfono e Riconoscimento vocale.")
                    b.addButton(withTitle: "OK")
                    if !fatto { b.addButton(withTitle: Conf.lang == "en" ? "Open settings" : "Apri le impostazioni") }
                    if b.runModal() == .alertSecondButtonReturn,
                       let u = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") {
                        NSWorkspace.shared.open(u)
                    }
                    if fatto { self.apriJarvis() }
                }
            }
        }
    }

    /// plancia://recap, plancia://ask?q=..., plancia://open, plancia://sync
    /// Serve per legarlo a una scorciatoia di sistema o a Raycast.
    func application(_ application: NSApplication, open urls: [URL]) {
        urls.forEach(esegui)
    }

    private func esegui(_ url: URL) {
        Log.write("url ricevuto: \(url.absoluteString)")
        guard url.scheme == "plancia" else { return }
        let azione = url.host ?? url.path.replacingOccurrences(of: "/", with: "")
        switch azione {
        case "recap", "riepilogo": riepilogoVocale()
        case "ask", "chiedi":
            let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "q" })?.value ?? ""
            voce.apri()
            if !q.isEmpty { voce.chiediTesto(q) }
        case "sync", "aggiorna": sincronizza()
        case "screenshot", "schermata": schermata()
        case "pdf": scattaPDF { _ in }
        case "permessi": chiediPermessi()
        case "jarvis":
            let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
            if let frase = q.first(where: { $0.name == "say" })?.value, !frase.isEmpty {
                jarvis.detta(frase)
            } else if q.contains(where: { $0.name == "shot" }) {
                let dir = Conf.dataDir.appendingPathComponent("shots")
                try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                if let f = jarvis.schermata(in: dir) { Log.write("schermata jarvis: \(f.path)") }
            } else {
                apriJarvis()
            }
        case "open", "apri", "vista":
            let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
            let vista = q.first(where: { $0.name == "view" })?.value
            let ui = q.first(where: { $0.name == "ui" })?.value
            apriFinestra()
            if vista != nil || ui != nil { vai(vista: vista, ui: ui) }
        default: apriFinestra()
        }
    }

    /// Porta la finestra su una vista precisa, opzionalmente in un'altra lingua.
    private func vai(vista: String?, ui: String?) {
        var s = Conf.base + "/"
        if let ui = ui { s += "?ui=" + ui }
        if let v = vista { s += "#/" + v }
        if let u = URL(string: s) { web.load(URLRequest(url: u)) }
    }

    /// Il messaggio 'tema' della pagina (vedi il commento su
    /// conf.userContentController.add(self, name: "tema") in
    /// costruisciFinestra()): quando plancia-theme risolve un tema, la
    /// pagina manda "light" o "dark" e il MATERIALE segue - non la finestra:
    /// window.appearance è quello che matchMedia('prefers-color-scheme')
    /// legge dentro la pagina (web/app.js:2061-2075) per risolvere 'auto', e
    /// se lo forzassimo qui romperemmo 'auto' (vedi il commento più sopra su
    /// costruisciFinestra()). Il materiale è un fratello della WKWebView
    /// sotto lo stesso `contenuto`, quindi restare sul materiale non tocca
    /// ciò che la pagina legge. Qualunque altro nome o corpo che non sia
    /// esattamente questi due viene ignorato: un valore imprevisto non deve
    /// lasciare il materiale in uno stato a metà.
    func userContentController(_ userContentController: WKUserContentController,
                                didReceive message: WKScriptMessage) {
        guard message.name == "tema", let valore = message.body as? String else { return }
        switch valore {
        case "dark": materiale.appearance = NSAppearance(named: .darkAqua)
        case "light": materiale.appearance = NSAppearance(named: .aqua)
        default: break
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        apriFinestra()
        return true
    }
    func applicationWillTerminate(_ n: Notification) { backend.stopIfOurs() }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
