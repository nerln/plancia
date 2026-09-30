// La prova del pannello Jarvis, senza il resto dell'app: compila Core/, Conf, Cattura e i file
// Jarvis*.swift con questo main (vedi tools/prova-jarvis-mac.sh).
//
// Non tocca il microfono ne' gli altoparlanti (PLANCIA_JARVIS_PROVA=1 e' obbligatorio), non
// scrive nelle preferenze (dominio volatile) e parla solo con il server della casa di prova
// indicata da PLANCIA_HOME.
//
//   PLANCIA_HOME=<casa di prova> PLANCIA_JARVIS_PROVA=1 prova-jarvis <cartella PNG> chiaro|scuro <tutto|spento>
//
// Stampa "  ok   ..." e "  NO   ..." una riga per controllo, ed esce con 1 se ce n'e' uno rosso.

import AppKit
import Speech

@MainActor var esiti = (ok: 0, no: 0)

@MainActor func prova(_ nome: String, _ ok: Bool, _ dettaglio: String = "") {
    if ok { esiti.ok += 1; print("  ok   \(nome)") } else { esiti.no += 1; print("  NO   \(nome) \(dettaglio)") }
    fflush(stdout)
}

@MainActor func attendi(_ tempo: TimeInterval = 20, _ condizione: () -> Bool) async -> Bool {
    let fine = Date().addingTimeInterval(tempo)
    while Date() < fine {
        if condizione() { return true }
        try? await Task.sleep(nanoseconds: 50_000_000)
    }
    return condizione()
}

final class DelegatoProva: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ n: Notification) {
        Task { @MainActor in
            await ProvaJarvis.esegui()
            print("\n\(esiti.ok) ok, \(esiti.no) no")
            exit(esiti.no == 0 ? 0 : 1)
        }
    }
}

@main
struct ProvaJarvis {
    @MainActor static func main() {
        guard JarvisProva.attivo else {
            print("serve PLANCIA_JARVIS_PROVA=1: questa prova non deve toccare microfono e altoparlanti")
            exit(2)
        }
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let d = DelegatoProva()
        app.delegate = d
        app.run()
    }

    @MainActor static func esegui() async {
        let args = CommandLine.arguments
        guard args.count >= 4 else { print("uso: prova-jarvis <cartella> chiaro|scuro tutto|spento"); exit(2) }
        let cartella = URL(fileURLWithPath: args[1])
        let aspetto = args[2] == "scuro" ? "scuro" : "chiaro"
        let modo = args[3]
        try? FileManager.default.createDirectory(at: cartella, withIntermediateDirectories: true)

        // aspetto e lingua solo per questa esecuzione, mai nelle preferenze vere
        var dominio = UserDefaults.standard.volatileDomain(forName: UserDefaults.argumentDomain)
        dominio["lingua"] = "it"
        dominio["jarvisAscoltaSubito"] = true
        dominio["jarvisConversazione"] = false
        UserDefaults.standard.setVolatileDomain(dominio, forName: UserDefaults.argumentDomain)
        Lingua.condivisa.codice = "it"
        NSApp.appearance = NSAppearance(named: aspetto == "scuro" ? .darkAqua : .aqua)

        let pannello = JarvisPanel()
        var azioni: [[String: Any]] = []
        pannello.onAzione = { azioni.append($0) }

        if modo == "spento" {
            await serverSpento(pannello)
            return
        }

        // ---- che voci e che riconoscimento ha questo Mac (informazioni, non controlli)
        for l in ["it", "en"] {
            let voci = VoceJarvis.vociDisponibili(lingua: l)
            let scelta = VoceJarvis.voceDiSistema(lingua: l).map { VoceJarvis.etichetta($0) } ?? "nessuna"
            let sulMac = SFSpeechRecognizer(locale: AscoltoContinuo.locale(l))?.supportsOnDeviceRecognition ?? false
            print("  info \(l): \(voci.count) voci avanzate o premium, scelta: \(scelta); riconoscimento sul Mac: \(sulMac ? "si" : "no")")
        }

        // ---- le scene fisse
        var altezze: [JarvisProva.Scena: CGFloat] = [:]
        for s in JarvisProva.Scena.allCases {
            let f = await JarvisProva.scatta(s, pannello: pannello, cartella: cartella, aspetto: aspetto)
            let ok = f.map { (try? Data(contentsOf: $0).count) ?? 0 > 4000 } ?? false
            prova("scena \(s.rawValue): PNG scritto", ok, f?.path ?? "cattura fallita")
            altezze[s] = pannello.window?.frame.height
            if let fr = pannello.window?.frame, let vf = NSScreen.main?.visibleFrame {
                prova("scena \(s.rawValue): il pannello sta nello schermo", vf.insetBy(dx: -2, dy: -2).contains(fr), "\(fr) in \(vf)")
            }
        }
        if let a = altezze[.inattivo], let b = altezze[.schedaAgente] {
            prova("la scheda dell'agente fa crescere il pannello", b > a + 60, "\(a) -> \(b)")
        }
        if let a = altezze[.lunga] { prova("una risposta lunga scorre e non fa esplodere il pannello", a < 640, "\(a)") }

        await sicurezza(pannello, cartella, aspetto, &azioni)
    }

    // MARK: server spento

    @MainActor static func serverSpento(_ pannello: JarvisPanel) async {
        let m = pannello.modello
        pannello.mostra()
        m.apri(ascolta: false)
        m.invia("come va")
        let fatto = await attendi(15) { !m.elabora && m.messaggio != nil }
        prova("con il server spento il pannello lo dice e non resta appeso", fatto, m.messaggio ?? "")
        prova("...come errore grave, senza scheda", m.erroreGrave && m.proposta == nil)
        prova("...e il microfono e' spento", !m.microfonoAcceso && !m.microfonoInApertura)
        await voiceboxSpento(pannello, serverAcceso: false)
        let f = await JarvisProva.scatta(.serverSpento, pannello: pannello, cartella: URL(fileURLWithPath: CommandLine.arguments[1]), aspetto: CommandLine.arguments[2] == "scuro" ? "scuro" : "chiaro")
        prova("scena server spento fotografata", f != nil)
    }

    // MARK: la sicurezza, contro il server di prova

    @MainActor static func sicurezza(_ pannello: JarvisPanel, _ cartella: URL, _ aspetto: String,
                                     _ azioni: inout [[String: Any]]) async {
        let m = pannello.modello
        pannello.window?.orderOut(nil)
        m.mostraScena(.inattivo)
        pannello.mostra()
        m.apri(ascolta: false)
        try? await Task.sleep(nanoseconds: 700_000_000)
        prova("aprire il pannello non accende il microfono", !m.microfonoAcceso && !m.microfonoInApertura)

        // una domanda: il testo scorre a pezzi, niente scheda
        m.invia("spiegami cosa bolle in pentola")
        var vistoPrimaDelFine = false
        let ok1 = await attendi(25) {
            if m.elabora && m.pezzi.count >= 1 { vistoPrimaDelFine = true }
            return !m.elabora && !m.parla && !m.pezzi.isEmpty
        }
        prova("una domanda ha risposta dal modello finto", ok1 && m.risposta.contains("Hai tre task"),
              "risposta=\(m.risposta) messaggio=\(m.messaggio ?? "-")")
        prova("il testo e' scorso a pezzi mentre il server lavorava", vistoPrimaDelFine && m.pezzi.count >= 3, "\(m.pezzi.count) pezzi")
        prova("una domanda non crea nessuna scheda", m.proposta == nil)
        prova("il microfono e' rimasto spento", !m.microfonoAcceso)

        // una proposta del modello: scheda, e nessun effetto
        m.invia(#"proponi: {"azione":"task_add","titolo":"Task dalla prova Jarvis","progetto":"atlas"}"#)
        let ok2 = await attendi(25) { !m.elabora && !m.parla && m.proposta != nil }
        prova("una proposta del modello arriva come scheda", ok2 && m.proposta?.azione == "task_add", m.risposta)
        prova("la riga @@PROPOSTA non compare nel testo", !m.risposta.contains("@@") && !m.risposta.contains("PROPOSTA"), m.risposta)
        prova("con la scheda aperta la fase e' conferma", m.fase == .conferma)
        let id1 = m.proposta?.id ?? ""
        let f = await scattaAdesso(pannello, cartella, "e2e-scheda", aspetto)
        prova("la scheda vera del server e' stata fotografata", f)

        // "si" scritto o detto: la scheda resta, non parte niente
        m.invia("sì")
        let ok3 = await attendi(20) { !m.elabora && !m.parla && m.risposta.contains("pulsante") }
        prova("dire si non conferma: il pannello rimanda al pulsante", ok3, m.risposta)
        prova("...e la scheda e' la stessa, ancora aperta", m.proposta?.id == id1 && id1 != "")

        // il pulsante conferma: qui, e solo qui, parte
        m.conferma()
        let ok4 = await attendi(20) { m.proposta == nil && !m.confermaInCorso && m.risposta.contains("Segnato") }
        prova("il pulsante Conferma esegue e il pannello lo dice", ok4, m.risposta)
        let f2 = await scattaAdesso(pannello, cartella, "e2e-dopo-conferma", aspetto)
        prova("l'esito e' stato fotografato", f2)

        // la stessa scheda non si conferma due volte
        let seconda = try? await ReteJarvis.conferma(id: id1, lingua: "it")
        prova("la stessa scheda non si conferma due volte", seconda?.eseguita != true, seconda?.risposta ?? "")

        // Esc con una scheda aperta la butta
        m.invia(#"proponi: {"azione":"task_add","titolo":"Da buttare con Esc"}"#)
        let ok5 = await attendi(25) { !m.elabora && !m.parla && m.proposta != nil }
        let id2 = m.proposta?.id ?? ""
        m.esc()
        prova("Esc butta la scheda", ok5 && m.proposta == nil)
        try? await Task.sleep(nanoseconds: 500_000_000)
        let terza = try? await ReteJarvis.conferma(id: id2, lingua: "it")
        prova("...anche sul server: la scheda buttata non si conferma", terza?.eseguita != true, terza?.risposta ?? "")

        // Esc vero, dalla tastiera, col campo di testo in primo piano: arriva UNA volta sola
        m.invia(#"proponi: {"azione":"task_add","titolo":"Da buttare con Esc dalla tastiera"}"#)
        _ = await attendi(25) { !m.elabora && !m.parla && m.proposta != nil }
        if let f = pannello.window {
            if let campo = trova(NSTextField.self, in: f.contentView) { f.makeFirstResponder(campo) }
            let prima = m.escRicevuti
            premiEsc(f)
            try? await Task.sleep(nanoseconds: 300_000_000)
            prova("Esc dalla tastiera col campo di testo attivo arriva una volta sola e butta la scheda",
                  m.escRicevuti == prima + 1 && m.proposta == nil && pannello.visibile,
                  "esc=\(m.escRicevuti - prima) scheda=\(m.proposta != nil) visibile=\(pannello.visibile)")
            f.makeFirstResponder(nil)
            let prima2 = m.escRicevuti
            premiEsc(f)
            try? await Task.sleep(nanoseconds: 300_000_000)
            prova("Esc dalla tastiera senza campo attivo arriva una volta sola",
                  m.escRicevuti == prima2 + 1, "esc=\(m.escRicevuti - prima2)")
            // a riposo Esc chiude il pannello: si riapre per il resto
            try? await Task.sleep(nanoseconds: 500_000_000)
            prova("a riposo, senza scheda, Esc chiude il pannello", !pannello.visibile)
            pannello.mostra()
            m.apri(ascolta: false)
            try? await Task.sleep(nanoseconds: 500_000_000)
        }

        // Esc mentre pensa ferma il server
        m.invia("una cosa lento lento")
        let ok6 = await attendi(10) { m.elabora && !m.pezzi.isEmpty }
        try? await Task.sleep(nanoseconds: 400_000_000)
        m.esc()
        prova("Esc ferma la risposta in corso", ok6 && !m.elabora && !m.parla)
        prova("...e il pannello resta aperto (un Esc alla volta)", pannello.visibile)

        // il microfono in prova: si accende solo dal pulsante, si vede, e si spegne da solo
        var vistoAcceso = false
        m.toggleMicrofono()
        let ok7 = await attendi(15) {
            if m.microfonoAcceso { vistoAcceso = true }
            return vistoAcceso && !m.microfonoAcceso && !m.elabora && m.proposta != nil
        }
        prova("dal pulsante il microfono (finto) si accende, si vede, e dopo la frase si spegne da solo", ok7 && !m.microfonoAcceso)
        prova("la frase detta e' quella recitata e produce una scheda, non un fatto",
              m.trascritto.lowercased().contains("mario") && m.proposta?.azione == "task_add", m.trascritto)
        let f3 = await scattaAdesso(pannello, cartella, "e2e-voce-scheda", aspetto)
        prova("la scheda nata dalla voce e' stata fotografata", f3)
        m.rifiuta()

        // Esc a microfono acceso lo spegne
        m.toggleMicrofono()
        _ = await attendi(3) { m.microfonoAcceso }
        m.esc()
        prova("Esc a microfono acceso lo spegne senza inviare", !m.microfonoAcceso && !m.elabora)

        // conversazione continua spenta: dopo la risposta il microfono resta spento
        m.invia("raccontami una storia sul mare")
        _ = await attendi(20) { !m.elabora && !m.parla && !m.pezzi.isEmpty }
        try? await Task.sleep(nanoseconds: 600_000_000)
        prova("dopo una risposta il microfono non si riapre da solo", !m.microfonoAcceso && !m.microfonoInApertura)

        // ---- la voce neurale (un Pocket finto, la sintesi vera passa dal server)
        await voceNeurale(pannello)

        // ---- Voicebox spento: Jarvis lo avvia (qui un avvio finto) e la voce neurale compare
        await voiceboxSpento(pannello, serverAcceso: true)

        // chiudere il pannello butta le schede
        m.invia(#"proponi: {"azione":"task_add","titolo":"Da buttare chiudendo"}"#)
        _ = await attendi(20) { !m.elabora && !m.parla && m.proposta != nil }
        let id3 = m.proposta?.id ?? ""
        m.chiudi()
        try? await Task.sleep(nanoseconds: 500_000_000)
        let quarta = try? await ReteJarvis.conferma(id: id3, lingua: "it")
        prova("chiudere il pannello butta la scheda aperta", m.proposta == nil && quarta?.eseguita != true)
        _ = pannello
    }

    /// Voicebox e' spento e installato: Jarvis lo apre (un avvio finto, mai l'app vera) e, quando il
    /// server vede la voce neurale, la usa; se il server non la vede mai, lo dice e lascia il pulsante.
    @MainActor static func voiceboxSpento(_ pannello: JarvisPanel, serverAcceso: Bool) async {
        let m = pannello.modello
        let quale = serverAcceso ? "col server acceso" : "col server spento"
        m.mostraScena(.voiceboxSpento)
        prova("Voicebox spento e installato: il pannello offre il pulsante (\(quale))", m.offriVoicebox)

        // in prova, senza l'avvio finto, non si apre niente
        Voicebox.finto = nil
        m.avviaVoicebox(daUtente: true)
        prova("in prova Voicebox non si apre da solo (\(quale))", m.voicebox == .nessuno)

        var aperture = 0
        Voicebox.finto = { aperture += 1; return true }
        Voicebox.intervallo = 0.05
        Voicebox.tentativi = 24
        defer { Voicebox.finto = nil; Voicebox.intervallo = 3; Voicebox.tentativi = 28 }

        // la preferenza spenta ferma l'avvio automatico, non il pulsante
        var dominio = UserDefaults.standard.volatileDomain(forName: UserDefaults.argumentDomain)
        dominio["jarvisAvviaVoicebox"] = false
        UserDefaults.standard.setVolatileDomain(dominio, forName: UserDefaults.argumentDomain)
        m.avviaVoicebox(daUtente: false)
        prova("con 'Avvia Voicebox da solo' spento l'avvio automatico non parte (\(quale))",
              m.voicebox == .nessuno && aperture == 0, "aperture=\(aperture)")
        dominio["jarvisAvviaVoicebox"] = true
        UserDefaults.standard.setVolatileDomain(dominio, forName: UserDefaults.argumentDomain)

        var vistoInAvvio = false
        var avvisoInAvvio = ""
        m.avviaVoicebox(daUtente: true)
        if m.voicebox == .inAvvio { vistoInAvvio = true; avvisoInAvvio = m.voceAvviso ?? "" }
        prova("il pulsante avvia: stato 'in avvio' e la riga lo dice (\(quale))",
              vistoInAvvio && avvisoInAvvio.contains("Avvio Voicebox"), avvisoInAvvio)
        m.avviaVoicebox(daUtente: true)
        let finito = await attendi(8) { m.voicebox != .inAvvio }
        prova("l'app di Voicebox viene aperta una volta sola (\(quale))", aperture == 1, "aperture=\(aperture)")
        if serverAcceso {
            prova("appena il server vede la voce neurale Jarvis la usa e lo dice",
                  finito && m.voicebox == .nessuno && !m.voceSenzaNeurale && m.voceDescrizione.contains("Pocket"),
                  "\(m.voicebox) \(m.voceDescrizione)")
            prova("...e non offre piu' il pulsante", !m.offriVoicebox)
        } else {
            prova("se la voce neurale non compare mai lo dice e lascia riprovare",
                  finito && m.voicebox == .nonPartito && (m.voceAvviso ?? "").contains("non ha risposto") && m.offriVoicebox,
                  "\(m.voicebox) \(m.voceAvviso ?? "-")")
        }
    }

    /// Le righe del registro del Pocket finto: (quando, testo).
    static func richiestePocket() -> [(Double, String)] {
        guard let p = ProcessInfo.processInfo.environment["PLANCIA_POCKET_LOG"],
              let t = try? String(contentsOfFile: p, encoding: .utf8) else { return [] }
        return t.split(separator: "\n").compactMap { r in
            let pezzi = r.split(separator: " ", maxSplits: 1).map(String.init)
            guard pezzi.count == 2, let d = Double(pezzi[0]) else { return nil }
            return (d, pezzi[1])
        }
    }

    @MainActor static func voceNeurale(_ pannello: JarvisPanel) async {
        guard ProcessInfo.processInfo.environment["PLANCIA_POCKET_LOG"] != nil else { return }
        let m = pannello.modello
        m.rifiuta()
        m.chiudi()
        try? await Task.sleep(nanoseconds: 400_000_000)
        pannello.mostra()
        m.apri(ascolta: false)
        let vede = await attendi(6) { m.voceDescrizione.contains("Pocket") }
        prova("il server offre una voce neurale e il pannello la nomina", vede, m.voceDescrizione)

        // due frasi: la sintesi della seconda parte mentre la prima suona
        let prima = richiestePocket().count
        let sale = String(UUID().uuidString.prefix(6))
        m.invia("eco: Prima frase del giro \(sale). Seconda frase del giro \(sale), un po' piu' lunga della prima.")
        var parlato = false
        let ok = await attendi(25) {
            if m.parla { parlato = true }
            return parlato && !m.elabora && !m.parla
        }
        let nuove = Array(richiestePocket().dropFirst(prima))
        prova("con la voce neurale ogni frase passa dalla sintesi del server", ok && nuove.count >= 2, "\(nuove.count) richieste")
        if nuove.count >= 2 {
            let scarto = nuove[1].0 - nuove[0].0
            prova("la seconda frase viene sintetizzata mentre la prima suona (0,8 s di audio)", scarto < 0.75, "scarto \(scarto)")
            prova("...nell'ordine giusto", nuove[0].1.contains("Prima frase del giro") && nuove[1].1.contains("Seconda frase del giro"), nuove.map { $0.1 }.joined(separator: " | "))
        }
        prova("il testo era gia' tutto sullo schermo e la voce ha finito da sola", !m.parla && m.risposta.contains("Seconda frase del giro"))

        // Esc mentre parla: la voce tace e non partono altre richieste
        m.invia("eco: Terza frase per l'Esc \(sale). Quarta frase per l'Esc \(sale), che non deve mai partire.")
        _ = await attendi(20) { m.parla }
        m.esc()
        let dopoEsc = richiestePocket().count
        try? await Task.sleep(nanoseconds: 1_500_000_000)
        prova("Esc mentre parla ferma la voce", !m.parla)
        prova("...e non parte nessuna altra sintesi", richiestePocket().count == dopoEsc, "\(dopoEsc) -> \(richiestePocket().count)")

        // il ripiego: una frase che il motore rifiuta -> voce di sistema (qui recitata), e lo dice
        m.invia("una frase guasto")
        let ripiego = await attendi(25) { !m.elabora && !m.parla && m.voceAvviso != nil && m.voceDescrizione.hasPrefix("Prova") }
        prova("se la sintesi neurale fallisce si passa alla voce di sistema e il pannello lo dice", ripiego,
              "\(m.voceDescrizione) | \(m.voceAvviso ?? "-")")
        prova("...l'avviso spiega che la voce neurale non ha risposto", (m.voceAvviso ?? "").contains("non ha risposto"))
    }

    @MainActor static func trova<T: NSView>(_ tipo: T.Type, in vista: NSView?) -> T? {
        guard let vista = vista else { return nil }
        if let t = vista as? T { return t }
        for s in vista.subviews { if let t = trova(tipo, in: s) { return t } }
        return nil
    }

    @MainActor static func premiEsc(_ f: NSWindow) {
        guard let ev = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [],
                                        timestamp: ProcessInfo.processInfo.systemUptime,
                                        windowNumber: f.windowNumber, context: nil, characters: "\u{1b}",
                                        charactersIgnoringModifiers: "\u{1b}", isARepeat: false, keyCode: 53) else { return }
        f.sendEvent(ev)
    }

    @MainActor static func scattaAdesso(_ pannello: JarvisPanel, _ cartella: URL, _ nome: String, _ aspetto: String) async -> Bool {
        try? await Task.sleep(nanoseconds: 900_000_000)
        guard let f = pannello.window, let png = Cattura.png(f) else { return false }
        return (try? png.write(to: cartella.appendingPathComponent("jarvis-\(nome)-\(aspetto).png"))) != nil
    }
}
