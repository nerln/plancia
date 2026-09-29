// Gli indirizzi plancia:// e quello che Jarvis decide di fare sull'app.
//
//   plancia://recap                     riepilogo vocale
//   plancia://ask?q=...                 una domanda a voce
//   plancia://open?view=task            apre la finestra su una sezione
//   plancia://progetto?key=lumen        apre un progetto
//   plancia://cerca?q=...               scrive nel campo di ricerca
//   plancia://sync  screenshot  pdf  permessi  jarvis
// Serve per legarlo a una scorciatoia di sistema o a Raycast.

import AppKit

extension DelegatoApp {
    @objc func gestisciEventoURL(_ evento: NSAppleEventDescriptor, withReply reply: NSAppleEventDescriptor) {
        guard let s = evento.paramDescriptor(forKeyword: keyDirectObject)?.stringValue,
              let url = URL(string: s) else { return }
        esegui(url)
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        urls.forEach(esegui)
    }

    func esegui(_ url: URL) {
        // lo stesso indirizzo, due volte in un secondo, e' lo stesso evento
        if let (u, quando) = ultimoURL, u == url.absoluteString, Date().timeIntervalSince(quando) < 1 { return }
        ultimoURL = (url.absoluteString, Date())
        Log.write("url ricevuto: \(url.absoluteString)")
        guard url.scheme == "plancia" else { return }
        let azione = url.host ?? url.path.replacingOccurrences(of: "/", with: "")
        let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        func param(_ n: String) -> String? { q.first(where: { $0.name == n })?.value }
        switch azione {
        case "recap", "riepilogo": riepilogoVocale()
        case "ask", "chiedi":
            let dom = param("q") ?? ""
            voce.apri()
            if !dom.isEmpty { voce.chiediTesto(dom) }
        case "sync", "aggiorna": sincronizza()
        case "screenshot", "schermata": schermata()
        case "pdf": scattaPDF()
        case "permessi": chiediPermessi()
        case "jarvis":
            if let frase = param("say"), !frase.isEmpty {
                jarvis.detta(frase)
            } else if q.contains(where: { $0.name == "shot" }) {
                let dir = Conf.dataDir.appendingPathComponent("shots")
                try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                if let f = jarvis.schermata(in: dir) { Log.write("schermata jarvis: \(f.path)") }
            } else {
                apriJarvis()
            }
        case "progetto":
            apriFinestra()
            Archivio.condiviso.vai(.progetti, progetto: param("key"))
        case "cerca", "search":
            apriFinestra()
            Archivio.condiviso.ricerca = param("q") ?? ""
            Archivio.condiviso.avviaRicerca()
        case "open", "apri", "vista":
            apriFinestra()
            vai(vista: param("view"), ui: param("ui"))
        default: apriFinestra()
        }
    }

    /// Porta la finestra su una sezione, opzionalmente in un'altra lingua (solo per questa
    /// esecuzione: quella delle Impostazioni non cambia).
    func vai(vista: String?, ui: String?) {
        if let ui = ui, ui == "it" || ui == "en" { Lingua.condivisa.codice = ui }
        if let s = Sezione.da(nome: vista) { Archivio.condiviso.vai(s) }
    }

    /// Quello che Jarvis decide di fare sull'app: cambiare vista, aprire un progetto,
    /// rileggere le fonti.
    func eseguiAzione(_ a: [String: Any]) {
        switch a["tipo"] as? String {
        case "vai":
            vai(vista: a["vista"] as? String, ui: nil)
        case "progetto":
            if let k = a["chiave"] as? String { Archivio.condiviso.vai(.progetti, progetto: k) }
        case "aggiorna":
            sincronizza()
        default:
            break
        }
        if a["tipo"] as? String != "ferma" { apriFinestra() }
    }
}
