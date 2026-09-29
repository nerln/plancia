// Il delegato dell'applicazione. Il @main SwiftUI (Guscio/PlanciaApp.swift) lo collega
// con NSApplicationDelegateAdaptor: e' lui che porta tutto quello che la 1.x sapeva fare
// oltre alla finestra. Le parti stanno in file propri:
//   Backend.swift    avvio del server se non c'e', e stop di quello avviato da noi
//   BarraMenu.swift  la voce nella barra dei menu
//   Azioni.swift     gli indirizzi plancia:// e le azioni di Jarvis
//   Permessi.swift   microfono e dettatura
//   Schermata.swift  PNG e PDF della finestra
//   jarvis.swift     il pannello vocale e la scorciatoia globale (invariato)
//   Voce.swift       il pannello "Chiedi a Plancia"

import AppKit

@MainActor
final class DelegatoApp: NSObject, NSApplicationDelegate {
    /// SwiftUI mette il suo delegato davanti al nostro: chi ha bisogno di noi (i comandi
    /// dei menu) passa da qui.
    static weak var corrente: DelegatoApp?
    /// Chi apre la finestra principale quando non c'e' piu' (la registra Comandi).
    static var apriFinestraSwiftUI: (() -> Void)?

    let backend = Backend()
    var statusItem: NSStatusItem!
    lazy var voce = VoicePanel()
    lazy var jarvis: JarvisPanel = {
        let p = JarvisPanel()
        p.onAzione = { [weak self] a in self?.eseguiAzione(a) }
        return p
    }()
    var timerRiepilogo: Timer?
    /// Lo stesso indirizzo puo' arrivare due volte (evento Apple e application(_:open:)).
    var ultimoURL: (String, Date)?

    override init() {
        super.init()
        DelegatoApp.corrente = self
    }

    // MARK: avvio

    func applicationWillFinishLaunching(_ n: Notification) {
        guard !Istantanee.attive, !Misura.attiva else { return }
        // Va agganciato prima che l'app finisca di avviarsi, altrimenti il primo
        // plancia:// si perde.
        NSAppleEventManager.shared().setEventHandler(
            self, andSelector: #selector(gestisciEventoURL(_:withReply:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL))
    }

    func applicationDidFinishLaunching(_ n: Notification) {
        if Istantanee.attive {
            // Niente server, niente barra dei menu, niente voce: solo la finestra.
            Istantanee.avvia()
            return
        }
        if Misura.attiva {
            // Niente server, niente barra dei menu, niente voce: la finestra e la misura.
            Misura.avvia()
            return
        }
        Log.write("avvio, backend su \(Conf.base), token \(Conf.token.isEmpty ? "assente" : "presente")")
        costruisciMenuBar()
        Notifiche.richiedi()

        Scorciatoia.azione = { [weak self] in self?.apriJarvis() }
        Scorciatoia.registra()

        backend.ensureRunning { ok in
            Archivio.condiviso.avvia()
            if !ok { self.avvisaBackendNonParte() }
        }
        programmaRiepilogo()
    }

    private func avvisaBackendNonParte() {
        // Se il server risponde piu' tardi (l'avvio e' lento) la finestra si riempie da sola:
        // l'avviso serve solo quando manca proprio il comando.
        guard Conf.executable == nil else { return }
        let a = NSAlert()
        a.messageText = tr("Plancia non parte", "Plancia will not start")
        a.informativeText = tr(
            "Non trovo il comando plancia. Apri il Terminale ed esegui ./bin/plancia install dalla cartella del progetto, poi riapri l'app.",
            "The plancia command is missing. Open Terminal and run ./bin/plancia install from the project folder, then reopen the app.")
        a.addButton(withTitle: "OK")
        a.runModal()
    }

    // MARK: finestra

    func finestraPrincipale() -> NSWindow? {
        let candidate = NSApp.windows.filter { !($0 is NSPanel) && $0.canBecomeMain && $0.contentView != nil }
        return candidate.first { $0.identifier?.rawValue.contains("principale") == true } ?? candidate.first
    }

    @objc func apriFinestra() {
        NSApp.activate(ignoringOtherApps: true)
        if let w = finestraPrincipale() {
            if w.isMiniaturized { w.deminiaturize(nil) }
            w.makeKeyAndOrderFront(nil)
        } else {
            DelegatoApp.apriFinestraSwiftUI?()
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        apriFinestra()
        return true
    }

    // MARK: uscita

    /// L'uscita ferma solo il server avviato da noi: se gira per conto suo (launchd) non e'
    /// compito nostro spegnerlo.
    func applicationWillTerminate(_ n: Notification) { backend.stopIfOurs() }

    @objc func esci() {
        backend.stopIfOurs()
        NSApp.terminate(nil)
    }

    // MARK: riepilogo della mattina

    func programmaRiepilogo() {
        timerRiepilogo?.invalidate()
        // Lo scheduler vero e' launchd (`plancia daily on`). Qui solo se lo si chiede
        // esplicitamente con una chiave diversa, per non parlare due volte.
        guard let ora = Conf.settings["riepilogo_ora_app"] as? String, ora.contains(":") else { return }
        let pezzi = ora.split(separator: ":").compactMap { Int($0) }
        guard pezzi.count == 2 else { return }
        var comp = DateComponents()
        comp.hour = pezzi[0]
        comp.minute = pezzi[1]
        guard let prossimo = Calendar.current.nextDate(after: Date(), matching: comp,
                                                       matchingPolicy: .nextTime) else { return }
        timerRiepilogo = Timer(fire: prossimo, interval: 86400, repeats: true) { _ in
            Task { @MainActor in self.voce.apriEriepiloga() }
        }
        RunLoop.main.add(timerRiepilogo!, forMode: .common)
    }
}
