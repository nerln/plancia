// Jarvis: il pannello che sta sopra tutto, si chiama con ⌥Spazio e si ferma con Esc.
//
// Riscritto da capo per la 2.1. Le parti stanno in file propri:
//   JarvisModello.swift  le regole (cosa si puo' fare e cosa no, e il ciclo di una frase)
//   JarvisVista.swift    l'interfaccia SwiftUI, col vetro di sistema
//   JarvisOnda.swift     la forma d'onda
//   JarvisAscolto.swift  microfono e riconoscimento, sul Mac, solo quando lo chiedi
//   JarvisVoce.swift     la voce: neurale locale se c'e', altrimenti le voci avanzate di sistema
//   JarvisRete.swift     il server locale
//   JarvisProva.swift    il modo prova: niente microfono, niente altoparlanti
// Qui c'e' solo la finestra e la scorciatoia globale, e i tre punti che il resto dell'app usa:
// `apri()`, `detta(_:)` (plancia://jarvis?say=) e `schermata(in:)` (plancia://jarvis?shot).

import AppKit
import Carbon.HIToolbox
import SwiftUI

/// Un pannello senza bordi non prende la tastiera se non glielo si dice: serve per scrivere nel
/// campo di testo e per ricevere Esc, senza che l'app rubi il fuoco a quella davanti.
final class FinestraJarvis: NSPanel {
    var alEsc: (() -> Void)?
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    override func cancelOperation(_ sender: Any?) { alEsc?() }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { alEsc?() } else { super.keyDown(with: event) }
    }
}

@MainActor
final class JarvisPanel: NSWindowController, NSWindowDelegate {
    let modello: JarvisModello

    /// Quello che il pannello non sa fare da solo: cambiare vista, aprire un progetto, rileggere le fonti.
    var onAzione: (([String: Any]) -> Void)?

    private var contenuto: NSHostingView<JarvisVista>!
    /// L'angolo in basso a destra del pannello: e' fermo, e il pannello cresce verso l'alto.
    private var ancora = NSPoint.zero
    private var adattamentoInCorso = false

    convenience init() {
        self.init(modello: JarvisModello())
    }

    init(modello: JarvisModello) {
        self.modello = modello
        let f = FinestraJarvis(contentRect: NSRect(x: 0, y: 0, width: 436, height: 320),
                               styleMask: [.borderless, .nonactivatingPanel],
                               backing: .buffered, defer: false)
        f.becomesKeyOnlyIfNeeded = false
        f.isFloatingPanel = true
        f.level = .floating
        f.backgroundColor = .clear
        f.isOpaque = false
        f.hasShadow = true
        f.isMovableByWindowBackground = true
        f.hidesOnDeactivate = false
        f.isReleasedWhenClosed = false
        f.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        f.title = "Jarvis"
        super.init(window: f)
        f.delegate = self
        f.alEsc = { [weak self] in self?.modello.esc() }

        let vista = NSHostingView(rootView: JarvisVista(m: modello))
        // Solo la misura ideale: e' il pannello a decidere la finestra, non il contenuto (che
        // altrimenti la ridimensiona da solo tenendo fermo l'angolo in alto).
        vista.sizingOptions = [.intrinsicContentSize]
        contenuto = vista
        f.contentView = vista

        modello.onChiudi = { [weak self] in self?.nascondi() }
        modello.onAzione = { [weak self] a in
            var d: [String: Any] = ["tipo": a.tipo]
            if let v = a.vista { d["vista"] = v }
            if let c = a.chiave { d["chiave"] = c }
            self?.onAzione?(d)
        }
        osserva()
    }

    required init?(coder: NSCoder) { fatalError("non si crea da un archivio") }

    var visibile: Bool { window?.isVisible == true }

    // MARK: aprire e chiudere

    /// Apre il pannello. Se e' stata la scorciatoia (un gesto tuo) e la preferenza lo permette,
    /// il microfono si accende, e si vede. Dal menu o da un indirizzo plancia:// no.
    func apri() {
        let daTasto = Scorciatoia.appenaPremuta
        if visibile {
            window?.makeKeyAndOrderFront(nil)
            if daTasto { modello.scorciatoiaSuPannelloAperto() }
            return
        }
        mostra()
        modello.apri(ascolta: daTasto)
    }

    /// Per le prove e per plancia://jarvis?say=: si mostra senza toccare il microfono.
    func mostra() {
        guard let f = window else { return }
        if ancora == .zero, let vf = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame {
            ancora = NSPoint(x: vf.maxX - 28, y: vf.minY + 28)
        }
        let h = misura()
        let fine = cornice(altezza: h)
        var inizio = fine
        inizio.origin.y -= 14
        f.setFrame(inizio, display: false)
        f.alphaValue = 0
        f.makeKeyAndOrderFront(nil)
        NSAnimationContext.runAnimationGroup { c in
            c.duration = 0.28
            c.timingFunction = CAMediaTimingFunction(name: .easeOut)
            f.animator().alphaValue = 1
            f.animator().setFrame(fine, display: true)
        }
        modello.visibile = true
    }

    private func nascondi() {
        guard let f = window, f.isVisible else { return }
        NSAnimationContext.runAnimationGroup { c in
            c.duration = 0.18
            f.animator().alphaValue = 0
        } completionHandler: { [weak self] in
            Task { @MainActor in
                f.orderOut(nil)
                f.alphaValue = 1
                self?.modello.visibile = false
            }
        }
    }

    func chiudi() { modello.chiudi() }

    /// Ferma tutto senza chiudere.
    func sospendi() { modello.ferma() }

    /// Frase iniettata da fuori (plancia://jarvis?say=): stessa strada della tastiera, mai il microfono.
    func detta(_ frase: String) {
        if !visibile {
            mostra()
            modello.apri(ascolta: false)
        }
        modello.invia(frase)
    }

    /// Il pannello che si fotografa da solo, per vedere com'e' venuto.
    func schermata(in cartella: URL) -> URL? {
        guard let f = window, let png = Cattura.png(f) else { return nil }
        let dest = cartella.appendingPathComponent("jarvis-\(Int(Date().timeIntervalSince1970)).png")
        do { try png.write(to: dest) } catch { return nil }
        return dest
    }

    // MARK: misure

    private func misura() -> CGFloat {
        contenuto.layoutSubtreeIfNeeded()
        return max(200, ceil(contenuto.fittingSize.height))
    }

    private func cornice(altezza: CGFloat) -> NSRect {
        let larghezza = ceil(contenuto.fittingSize.width > 100 ? contenuto.fittingSize.width : 400)
        return NSRect(x: ancora.x - larghezza, y: ancora.y, width: larghezza, height: altezza)
    }

    /// Il pannello segue l'altezza del contenuto, restando ancorato in basso a destra.
    private func adatta() {
        guard let f = window, f.isVisible, !adattamentoInCorso else { return }
        let nuova = cornice(altezza: misura())
        if abs(nuova.height - f.frame.height) < 1, abs(nuova.width - f.frame.width) < 1 { return }
        adattamentoInCorso = true
        NSAnimationContext.runAnimationGroup { c in
            c.duration = 0.28
            c.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            f.animator().setFrame(nuova, display: true)
        } completionHandler: { [weak self] in
            Task { @MainActor in self?.adattamentoInCorso = false }
        }
    }

    private func osserva() {
        withObservationTracking {
            _ = modello.fase
            _ = modello.pezzi.count
            _ = modello.proposta
            _ = modello.messaggio
            _ = modello.trascritto.isEmpty
            _ = modello.voceAvviso
            _ = modello.inAttivita
            _ = modello.microfonoInApertura
            _ = modello.voceDescrizione
        } onChange: { [weak self] in
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.06) {
                MainActor.assumeIsolated {
                    self?.adatta()
                    self?.osserva()
                }
            }
        }
    }

    // se lo sposti tu, l'ancora si sposta con te
    func windowDidMove(_ notification: Notification) {
        // solo se lo stai trascinando tu (tasto premuto): gli spostamenti del pannello stesso, che
        // cresce e si ritira, non cambiano l'ancora
        guard NSEvent.pressedMouseButtons & 1 != 0, let f = window else { return }
        ancora = NSPoint(x: f.frame.maxX, y: f.frame.minY)
    }
}

// MARK: - scorciatoia globale

/// ⌥Spazio ovunque. Passa da Carbon perche' e' l'unica strada che non chiede l'accesso
/// all'accessibilita' solo per leggere una combinazione di tasti.
enum Scorciatoia {
    private static var ref: EventHotKeyRef?
    static var azione: (() -> Void)?
    /// Quando e' stata premuta l'ultima volta: il pannello si apre col microfono solo se e' stata la
    /// tastiera, non il menu o un indirizzo plancia://.
    nonisolated(unsafe) static var ultimaPressione = Date.distantPast
    static var appenaPremuta: Bool { Date().timeIntervalSince(ultimaPressione) < 0.6 }

    static func registra() {
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                                 eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
            DispatchQueue.main.async {
                Scorciatoia.ultimaPressione = Date()
                Scorciatoia.azione?()
            }
            return noErr
        }, 1, &spec, nil, nil)
        let id = EventHotKeyID(signature: OSType(0x504C4E43), id: 1)
        let esito = RegisterEventHotKey(UInt32(kVK_Space), UInt32(optionKey), id,
                                        GetApplicationEventTarget(), 0, &ref)
        Log.write(esito == noErr ? "scorciatoia ⌥Spazio registrata"
                                 : "scorciatoia ⌥Spazio occupata da un'altra app (\(esito))")
    }
}
