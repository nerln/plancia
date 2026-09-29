// Modalita' istantanee: l'app si fotografa da sola, perche' il controllo del computer e la
// registrazione schermo non ci sono. Serve a chi sviluppa e alle prove.
//
//   PLANCIA_HOME=<casa di prova> Plancia.app/Contents/MacOS/Plancia \
//       --istantanee <cartella> [--aspetto chiaro|scuro] [--lingua it|en] [--parola <testo>]
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
        UserDefaults.standard.setVolatileDomain(dominio, forName: UserDefaults.argumentDomain)
        NSApp.appearance = NSAppearance(named: aspetto == "scuro" ? .darkAqua : .aqua)

        Task { await esegui(URL(fileURLWithPath: cartella), aspetto, parola) }
    }

    private static func esegui(_ cartella: URL, _ aspetto: String, _ parola: String) async {
        try? FileManager.default.createDirectory(at: cartella, withIntermediateDirectories: true)

        // la finestra la crea SwiftUI, un momento dopo l'avvio
        var finestra: NSWindow?
        for _ in 0..<80 {
            if let w = DelegatoApp.corrente?.finestraPrincipale(), w.isVisible { finestra = w; break }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        guard let w = finestra else { esci(1, "la finestra non e' comparsa") }
        w.setContentSize(NSSize(width: 1280, height: 820))
        w.setFrameTopLeftPoint(NSPoint(x: 60, y: (NSScreen.main?.visibleFrame.maxY ?? 900) - 40))
        w.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
        try? await Task.sleep(nanoseconds: 800_000_000)

        let a = Archivio.condiviso
        var scritti: [String] = []

        func scatta(_ nome: String) async {
            try? await Task.sleep(nanoseconds: 1_300_000_000)
            guard let png = Cattura.png(w) else { esci(1, "cattura fallita: \(nome)") }
            let file = cartella.appendingPathComponent("\(nome)-\(aspetto).png")
            do { try png.write(to: file) } catch { esci(1, "scrittura fallita: \(file.path)") }
            scritti.append(file.path)
        }

        for s in Sezione.allCases {
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

        // la ricerca con una parola
        a.vai(.oggi)
        a.ricercaAperta = true
        a.ricerca = parola
        a.avviaRicerca()
        for _ in 0..<50 where a.ricercaInCorso || a.risultatiPer != parola {
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        await scatta("ricerca")
        a.azzeraRicerca()

        FileHandle.standardOutput.write(Data((scritti.joined(separator: "\n") + "\n").utf8))
        FileHandle.standardOutput.write(Data("raggiungibile: \(a.raggiungibile)\n".utf8))
        exit(0)
    }
}
