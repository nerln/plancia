// Modalita' istantanee: l'app si fotografa da sola, perche' il controllo del computer e la
// registrazione schermo non ci sono. Serve a chi sviluppa e alle prove.
//
//   PLANCIA_HOME=<casa di prova> Plancia.app/Contents/MacOS/Plancia \
//       --istantanee <cartella> [--aspetto chiaro|scuro] [--lingua it|en] [--parola <testo>]
//       [--larghezza 1280] [--altezza 820]   (punti; il minimo della finestra vale sempre)
//       [--stile sistema|legno] [--testo 0...6]   (il passo della dimensione del testo, 3 = reale)
//       [--sezioni task,progetti,...]  solo queste sezioni, in questo ordine (default: tutte)
//       [--prova-tasti]  premi ⌘+ ⌘- ⌘0 ⌘= veri e stampa il passo dopo ognuno (senza --testo)
//       [--inattiva]  fotografa la finestra NON attiva (come quando si lavora in un'altra app)
//       [--primo-risultato]  nella Ricerca sceglie la prima riga: si vede l'Inspector dei Risultati
//       [--albero]  stampa l'albero delle viste di AppKit (righe ALB), per capire chi dipinge cosa
//       [--prova-clic]  clic finti sulle righe di Task e Progetti: dice se colpiscono la riga giusta
//
// Apre la finestra a 1280x820, visita ogni sezione (con l'Inspector di un elemento scelto
// dove c'e') e la Ricerca con una parola, aspetta che i dati siano caricati, salva un PNG
// per ogni passo (nome-aspetto.png) ed esce con codice 0. Non avvia il server: usa quello
// che trova sulla porta di $PLANCIA_HOME/config.json. Non avvia nemmeno la barra dei menu,
// Jarvis o le notifiche. Non scrive mai le preferenze: aspetto e lingua passano da un
// dominio volatile.
//
// Il PNG e' la finestra vera (vedi Sistema/Cattura.swift), col vetro di sistema.

import AppKit

@MainActor
enum Istantanee {
    static var attive: Bool { CommandLine.arguments.contains("--istantanee") }

    private static func valore(_ nome: String) -> String? {
        guard let i = CommandLine.arguments.firstIndex(of: nome), i + 1 < CommandLine.arguments.count else { return nil }
        return CommandLine.arguments[i + 1]
    }

    private static func esci(_ codice: Int32, _ messaggio: String? = nil) -> Never {
        if let m = messaggio { FileHandle.standardError.write(Data((m + "\n").utf8)) }
        exit(codice)
    }

    static func avvia() {
        guard let cartella = valore("--istantanee") else { esci(2, "manca la cartella dopo --istantanee") }
        let aspetto = valore("--aspetto") ?? "chiaro"
        let parola = valore("--parola") ?? "lumen"

        // aspetto e lingua solo per questa esecuzione
        var dominio = UserDefaults.standard.volatileDomain(forName: UserDefaults.argumentDomain)
        dominio["aspetto"] = aspetto == "scuro" ? "scuro" : "chiaro"
        if let l = valore("--lingua"), l == "it" || l == "en" {
            dominio["lingua"] = l
            Lingua.condivisa.codice = l
        }
        if let st = valore("--stile"), StileApp(rawValue: st) != nil { dominio[StileApp.chiave] = st }
        if let t = valore("--testo"), let n = Int(t) { dominio[DimensioneTesto.chiave] = DimensioneTesto.limita(n) }
        UserDefaults.standard.setVolatileDomain(dominio, forName: UserDefaults.argumentDomain)
        NSApp.appearance = NSAppearance(named: aspetto == "scuro" ? .darkAqua : .aqua)

        Task { await esegui(URL(fileURLWithPath: cartella), aspetto, parola) }
    }

    private static func esegui(_ cartella: URL, _ aspetto: String, _ parola: String) async {
        try? FileManager.default.createDirectory(at: cartella, withIntermediateDirectories: true)

        // la finestra la crea SwiftUI, un momento dopo l'avvio
        var finestra: NSWindow?
        for n in 0..<400 {
            if let w = DelegatoApp.corrente?.finestraPrincipale(), w.isVisible { finestra = w; break }
            // macOS, a un avvio su due dopo un'uscita con la finestra aperta, non la ripristina
            // e SwiftUI non ne crea una: la si apre a mano, come farebbe un clic sull'icona
            if n >= 20, n % 20 == 0 { DelegatoApp.corrente?.apriFinestra() }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        guard let w = finestra else { esci(1, "la finestra non è comparsa") }
        let larghezza = valore("--larghezza").flatMap { Double($0) } ?? 1280
        let altezza = valore("--altezza").flatMap { Double($0) } ?? 820
        w.setContentSize(NSSize(width: larghezza, height: altezza))
        w.setFrameTopLeftPoint(NSPoint(x: 60, y: (NSScreen.main?.visibleFrame.maxY ?? 900) - 40))
        w.orderFrontRegardless()
        w.makeKey()
        NSApp.activate(ignoringOtherApps: true)
        try? await Task.sleep(nanoseconds: 800_000_000)
        // le istantanee vogliono la finestra ATTIVA (semafori colorati, controlli pieni): se il
        // sistema non ha ceduto il primo piano si riprova con il modo nuovo, poi con l'altro
        for tentativo in 0..<6 where !(NSApp.isActive && w.isKeyWindow) {
            if tentativo % 2 == 0 { NSApp.activate() } else { NSRunningApplication.current.activate(options: [.activateAllWindows]) }
            w.makeKeyAndOrderFront(nil)
            try? await Task.sleep(nanoseconds: 500_000_000)
        }
        FileHandle.standardOutput.write(Data("finestra attiva: \(NSApp.isActive && w.isKeyWindow)\n".utf8))
        // --inattiva: fotografa la finestra NON attiva (semafori grigi, vetro spento), per vedere
        // come stanno le superfici quando l'utente lavora in un'altra app
        if CommandLine.arguments.contains("--inattiva") {
            NSApp.deactivate()
            try? await Task.sleep(nanoseconds: 800_000_000)
            FileHandle.standardOutput.write(Data("finestra inattiva: \(!NSApp.isActive && !w.isKeyWindow)\n".utf8))
        }

        let a = Archivio.condiviso
        var scritti: [String] = []

        func scatta(_ nome: String) async {
            try? await Task.sleep(nanoseconds: 1_300_000_000)
            guard let png = Cattura.png(w) else { esci(1, "cattura fallita: \(nome)") }
            let file = cartella.appendingPathComponent("\(nome)-\(aspetto).png")
            do { try png.write(to: file) } catch { esci(1, "scrittura fallita: \(file.path)") }
            scritti.append(file.path)
        }

        // --sezioni task,social,...: solo quelle, in quell'ordine (per provare un passaggio preciso,
        // per esempio da Task con l'Inspector aperto a Progetti)
        let ordine = valore("--sezioni").map { $0.split(separator: ",").compactMap { Sezione(rawValue: String($0)) } } ?? Sezione.allCases
        for s in ordine {
            a.vai(s)
            a.taskScelto = nil; a.progettoScelto = nil; a.memoriaScelta = nil
            a.postScelto = nil; a.sessioneScelta = nil
            await a.carica(s)
            await scatta(s.rawValue)

            // l'Inspector di un elemento, dove la sezione ne ha
            var scelto = false
            switch s {
            case .task:
                if let v = a.lavagna?.voci?.first(where: { $0.stato != "fatto" }) { a.taskScelto = v.identita; scelto = true }
            case .progetti:
                if let k = a.progetti.first?.key { a.progettoScelto = k; scelto = true }
            case .social:
                if let p = a.post.first { a.postScelto = p.identita; scelto = true }
            case .memoria:
                if let n = a.schede.first?.name { a.memoriaScelta = n; scelto = true }
            case .archivio:
                if let x = a.sessioni.first { a.sessioneScelta = x.identita; scelto = true }
            case .oggi:
                break
            }
            if scelto {
                if s == .progetti, let k = a.progettoScelto { await a.caricaDettaglio(k) }
                await scatta("\(s.rawValue)-dettaglio")
            }
        }

        if CommandLine.arguments.contains("--albero") {
            a.vai(.task); await a.carica(.task)
            if let v = a.lavagna?.voci?.first(where: { $0.stato != "fatto" }) { a.taskScelto = v.identita }
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            func giu(_ v: NSView, _ liv: Int) {
                let n = String(describing: type(of: v))
                var extra = ""
                if let e = v as? NSVisualEffectView { extra = " MATERIAL=\(e.material.rawValue) stato=\(e.state.rawValue) blend=\(e.blendingMode.rawValue) emph=\(e.isEmphasized)" }
                let f = v.convert(v.bounds, to: nil)
                FileHandle.standardOutput.write(Data("ALB \(String(repeating: " ", count: liv))\(n) x=\(Int(f.minX)) y=\(Int(f.minY)) w=\(Int(f.width)) h=\(Int(f.height)) hid=\(v.isHidden)\(extra)\n".utf8))
                for s in v.subviews { giu(s, liv + 1) }
            }
            if let cv = w.contentView?.superview { giu(cv, 0) }
        }
        if CommandLine.arguments.contains("--prova-tasti") { await provaTasti(w) }
        if CommandLine.arguments.contains("--prova-clic") { await provaClic(w, a, scatta) }

        // la ricerca con una parola
        a.vai(.oggi)
        a.ricercaAperta = true
        a.ricerca = parola
        a.avviaRicerca()
        for _ in 0..<50 where a.ricercaInCorso || a.risultatiPer != parola {
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        // con --primo-risultato la riga scelta pubblica il suo dettaglio e l'Inspector si apre: si
        // aspetta che ci sia, invece di fotografare a caso un momento prima
        if CommandLine.arguments.contains("--primo-risultato") {
            for _ in 0..<60 where ControlliVista.condiviso.dettaglioRisultato == nil {
                try? await Task.sleep(nanoseconds: 100_000_000)
            }
            FileHandle.standardOutput.write(Data("risultato: dettaglio pubblicato \(ControlliVista.condiviso.dettaglioRisultato != nil)\n".utf8))
        }
        await scatta("ricerca")
        a.azzeraRicerca()

        FileHandle.standardOutput.write(Data((scritti.joined(separator: "\n") + "\n").utf8))
        FileHandle.standardOutput.write(Data("raggiungibile: \(a.raggiungibile)\n".utf8))
        exit(0)
    }

    private static func tabelle(_ v: NSView, _ out: inout [NSTableView]) {
        if let t = v as? NSTableView { out.append(t) }
        for f in v.subviews { tabelle(f, &out) }
    }

    /// Con la scala del testo diversa da 100% i clic devono colpire la riga che si vede.
    /// AppKit decide il bersaglio di un clic con la geometria delle sue viste: se il
    /// rettangolo di una riga, convertito nelle coordinate della finestra, cade dove la riga
    /// e' disegnata (la si legge nell'immagine), il clic la colpisce. Qui si stampa il centro
    /// della terza riga della tabella dei Task e la vista che risponde a un clic li'.
    private static func provaClic(_ w: NSWindow, _ a: Archivio, _ scatta: (String) async -> Void) async {
        a.vai(.task)
        a.taskScelto = nil
        await a.carica(.task)
        try? await Task.sleep(nanoseconds: 1_200_000_000)
        guard let cv = w.contentView else { return }
        var elenco: [NSTableView] = []
        tabelle(cv, &elenco)
        guard let t = elenco.first(where: { $0.numberOfRows >= 3 }) else {
            FileHandle.standardOutput.write(Data("clic: nessuna tabella\n".utf8))
            return
        }
        FileHandle.standardOutput.write(Data("righe: altezza \(t.rect(ofRow: 0).height) pt, rowHeight \(t.rowHeight), automatica \(t.usesAutomaticRowHeights)\n".utf8))
        let r = t.convert(t.rect(ofRow: 2), to: nil)
        let alto = w.contentLayoutRect.height
        let x = r.midX, y = w.frame.height - r.midY
        let colpita = w.contentView?.hitTest(NSPoint(x: r.midX, y: r.midY))
        let riga = colpita.flatMap { v -> Int? in
            var c: NSView? = v
            while let x = c { if let t2 = x as? NSTableView { return t2.row(at: t2.convert(NSPoint(x: r.midX, y: r.midY), from: nil)) }; c = x.superview }
            return nil
        }
        FileHandle.standardOutput.write(Data("clic: riga 3 al centro (\(Int(x)), \(Int(y))) pt dall'alto, alto=\(Int(alto)), il clic lì cade sulla riga \(riga.map { String($0 + 1) } ?? "nessuna")\n".utf8))
        await scatta("prova-clic")
    }

    /// ⌘+ ⌘- ⌘0 ⌘= come eventi di tastiera veri dati all'applicazione: passano dal menu
    /// Vista e dal monitor di TastiTesto. Stampa il passo salvato dopo ogni tasto.
    private static func provaTasti(_ w: NSWindow) async {
        let d = UserDefaults.standard
        d.removeObject(forKey: DimensioneTesto.chiave)
        func passo() -> Int { d.object(forKey: DimensioneTesto.chiave) as? Int ?? DimensioneTesto.predefinito }
        func premi(_ c: String, codice: UInt16) async -> Int {
            if let e = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [.command],
                                        timestamp: ProcessInfo.processInfo.systemUptime,
                                        windowNumber: w.windowNumber, context: nil, characters: c,
                                        charactersIgnoringModifiers: c, isARepeat: false, keyCode: codice) {
                NSApp.sendEvent(e)
            }
            try? await Task.sleep(nanoseconds: 300_000_000)
            return passo()
        }
        var righe: [String] = ["tasti: inizio \(passo())"]
        func cerca(_ m: NSMenu?, _ chiavi: Set<String>, _ via: String) {
            for i in m?.items ?? [] {
                if chiavi.contains(i.keyEquivalent), i.keyEquivalentModifierMask.contains(.command) {
                    righe.append("tasti: menu \(via) > \(i.title) [cmd+\(i.keyEquivalent)] attivo=\(i.isEnabled)")
                }
                cerca(i.submenu, chiavi, via + "/" + i.title)
            }
        }
        cerca(NSApp.mainMenu, ["0", "+", "-", "="], "")
        righe.append("tasti: cmd+ -> \(await premi("+", codice: 24))")
        righe.append("tasti: cmd+ -> \(await premi("+", codice: 24))")
        righe.append("tasti: cmd- -> \(await premi("-", codice: 27))")
        righe.append("tasti: cmd0 -> \(await premi("0", codice: 29))")
        righe.append("tasti: cmd= -> \(await premi("=", codice: 24))")
        for _ in 0..<8 { _ = await premi("+", codice: 24) }
        righe.append("tasti: molti cmd+ -> \(passo()) (massimo \(DimensioneTesto.passi.count - 1))")
        for _ in 0..<12 { _ = await premi("-", codice: 27) }
        righe.append("tasti: molti cmd- -> \(passo()) (minimo 0)")
        d.removeObject(forKey: DimensioneTesto.chiave)
        FileHandle.standardOutput.write(Data((righe.joined(separator: "\n") + "\n").utf8))
    }
}
