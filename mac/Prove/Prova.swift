// La prova del Core, senza interfaccia: decodifica tutte le fixture con i modelli,
// prova che un campo mancante o del tipo sbagliato non fa cadere niente, e fa girare
// lo Store e il Cliente contro un server finto che serve le stesse fixture.
// La lancia tools/prova-mac.sh (compila Core/*.swift insieme a questo file).

import Foundation
import Observation

@MainActor var falliti = 0
@MainActor var passati = 0

@MainActor func prova(_ nome: String, _ ok: Bool, _ dettaglio: String = "") {
    if ok { passati += 1; print("  ok   \(nome)") }
    else { falliti += 1; print("  NO   \(nome) \(dettaglio)") }
}

func decodificatore() -> JSONDecoder {
    let d = JSONDecoder()
    d.keyDecodingStrategy = .convertFromSnakeCase
    return d
}

func dati(_ percorso: String) -> Data? { FileManager.default.contents(atPath: percorso) }

/// Una scatola per sapere, da un callback, se e' scattato.
final class Segnale: @unchecked Sendable { var scattato = false }

@main
struct ProvaCore {
    @MainActor static func main() async {
        let args = CommandLine.arguments
        guard args.count >= 3 else { print("uso: prova <cartella fixture> <porta del server finto>"); exit(2) }
        let cartella = args[1]
        let porta = args[2]

        print("== decodifica delle fixture")
        func oggetto<T: Decodable>(_ file: String, _ tipo: T.Type, _ controllo: (T) -> String?) {
            guard let d = dati("\(cartella)/\(file)") else { return prova("\(file) esiste", false) }
            do {
                let v = try decodificatore().decode(T.self, from: d)
                if let problema = controllo(v) { prova("\(file) come \(T.self)", false, problema) }
                else { prova("\(file) come \(T.self)", true) }
            } catch { prova("\(file) come \(T.self)", false, "\(error)") }
        }
        func elenco<T: Decodable>(_ file: String, _ tipo: T.Type, _ controllo: ([T]) -> String?) {
            guard let d = dati("\(cartella)/\(file)") else { return prova("\(file) esiste", false) }
            do {
                let v = try decodificatore().decode([Elemento<T>].self, from: d).compactMap { $0.valore }
                if let problema = controllo(v) { prova("\(file) come [\(T.self)]", false, problema) }
                else { prova("\(file) come [\(T.self)]", true) }
            } catch { prova("\(file) come [\(T.self)]", false, "\(error)") }
        }

        oggetto("status.json", Status.self) { $0.ultimoSync == nil ? "ultimo_sync mancante" : ($0.sync?.running == nil ? "sync.running mancante" : nil) }
        oggetto("compartimenti.json", Compartimenti.self) { $0.attivo == false && $0.predefinito == "predefinito" ? nil : "campi sbagliati" }
        oggetto("overview.json", Overview.self) {
            ($0.stats?.taskAperti ?? 0) > 0 && !($0.progetti ?? []).isEmpty && !($0.sessioniRecenti ?? []).isEmpty ? nil : "vuoto" }
        oggetto("prossimi.json", Prossimi.self) {
            !($0.aree ?? []).isEmpty && !($0.senzaArea ?? []).isEmpty && $0.aree?.first?.righe?.first?.cosa != nil ? nil : "vuoto" }
        elenco("projects.json", Progetto.self) { $0.count > 5 && $0.allSatisfy { $0.key != nil && $0.name != nil } ? nil : "\($0.count) progetti" }
        oggetto("project_detail.json", DettaglioProgetto.self) {
            $0.progetto?.key != nil && !($0.task ?? []).isEmpty && !($0.commit ?? []).isEmpty && !($0.sessioni ?? []).isEmpty ? nil : "vuoto" }
        elenco("projects_albero_1.json", Progetto.self) { $0.contains { !($0.figli ?? []).isEmpty } ? nil : "senza figli" }
        elenco("tasks_status_tutti.json", Compito.self) { $0.count > 5 && $0.allSatisfy { $0.id != nil && $0.title != nil } ? nil : "\($0.count) task" }
        elenco("posts.json", Post.self) { !$0.isEmpty && $0.allSatisfy { $0.text != nil && $0.status != nil } ? nil : "vuoto" }
        elenco("sessions.json", Sessione.self) { !$0.isEmpty && $0.allSatisfy { $0.sessionId != nil && $0.startedAt != nil } ? nil : "vuoto" }
        elenco("events.json", Evento.self) { !$0.isEmpty && $0.allSatisfy { $0.kind != nil } ? nil : "vuoto" }
        oggetto("eventi.json", Registro.self) { !($0.eventi ?? []).isEmpty && $0.stato?.schema != nil ? nil : "vuoto" }
        elenco("knowledge.json", Scheda.self) { !$0.isEmpty && $0.allSatisfy { $0.name != nil && $0.type != nil } ? nil : "vuoto" }
        oggetto("memoria_mappa.json", MappaMemoria.self) { !($0.nodi ?? []).isEmpty && $0.diagnosi?.totale != nil ? nil : "vuoto" }
        elenco("proposte.json", Proposta.self) { !$0.isEmpty && $0.allSatisfy { $0.testo != nil && $0.azione?.tipo != nil } ? nil : "vuoto" }
        elenco("runs.json", Lancio.self) { !$0.isEmpty && $0.allSatisfy { $0.stato != nil } ? nil : "vuoto" }
        oggetto("search_q_plancia.json", RisultatiRicerca.self) { !($0.schede ?? []).isEmpty ? nil : "senza schede" }
        oggetto("recap_solo_cache_1.json", Recap.self) { $0.giorno != nil ? nil : "senza giorno" }
        oggetto("lavagna.json", Lavagna.self) { !($0.voci ?? []).isEmpty && $0.aperti > 0 ? nil : "vuoto" }

        print("== tolleranza")
        elenco("tolleranza/progetti-sporchi.json", Progetto.self) { v in
            // l'elemento che non e' un oggetto sparisce, gli altri restano
            guard v.count == 3 else { return "\(v.count) elementi invece di 3" }
            let primo = v[0]
            // "7" diventa 7, 42 diventa "42", "2" diventa 2, true diventa 1, il resto e' nil
            guard primo.id == 7, primo.name == "42", primo.priority == 2, primo.pinned == 1 else { return "conversioni: \(primo)" }
            guard primo.key == nil, primo.figli == nil, primo.summary == nil, primo.nextAction == nil else { return "campi sbagliati non nil" }
            guard v[2].key == "ok", v[2].taskAperti == 3 else { return "terzo: \(v[2])" }
            return nil
        }
        oggetto("tolleranza/lavagna-storta.json", Lavagna.self) { l in
            guard (l.voci ?? []).count >= 2 else { return "voci: \(l.voci?.count ?? -1)" }
            return l.aperti == 4 ? nil : "aperti: \(l.aperti)"
        }
        oggetto("tolleranza/errore-del-server.json", Status.self) { $0.ultimoSync == nil ? nil : "non doveva leggere niente" }
        prova("un testo che non e' JSON non decodifica ma non manda in crash",
              (try? decodificatore().decode(Status.self, from: Data("<html>".utf8))) == nil)
        prova("Tempo.data legge data e ora ISO", Tempo.data("2026-09-29T20:06:31Z") != nil)
        prova("Tempo.data legge il solo giorno", Tempo.data("2026-10-02") != nil)
        prova("Tempo.data non inventa", Tempo.data("ieri") == nil && Tempo.data(nil) == nil)
        prova("Sezione.da riconosce i nomi della dashboard web",
              Sezione.da(nome: "lavagna") == .task && Sezione.da(nome: "Progetti") == .progetti && Sezione.da(nome: "boh") == nil)

        print("== cliente e store contro il server finto")
        Lingua.condivisa.codice = "it"
        let a = Archivio(cliente: Cliente())
        await a.carica(.task)
        prova("il server finto risponde", a.raggiungibile)
        prova("dopo il primo caricamento c'e' un ultimo aggiornamento", a.ultimoAggiornamento != nil)
        prova("il sottotitolo dice l'ora", a.sottotitolo.hasPrefix("aggiornato alle "), a.sottotitolo)
        prova("la lavagna e' nello store", (a.lavagna?.voci ?? []).count > 5, "\(a.lavagna?.voci?.count ?? -1)")
        prova("il badge dei task conta gli aperti", (a.conteggio(.task) ?? 0) > 0)
        prova("i task di Plancia sono nello store", !a.compiti.isEmpty)
        prova("i progetti sono nello store", !a.progetti.isEmpty)
        await a.carica(.oggi)
        prova("Oggi: prossimi e proposte", a.prossimi != nil && !a.proposte.isEmpty)
        await a.carica(.progetti)
        prova("Progetti: l'albero ha figli", a.alberoProgetti.contains { !($0.figli ?? []).isEmpty })
        await a.caricaDettaglio("apiary")
        prova("dettaglio di un progetto", a.dettagli["apiary"]?.progetto?.key == "apiary")
        await a.carica(.memoria)
        prova("Memoria: schede e mappa", !a.schede.isEmpty && !(a.mappa?.nodi ?? []).isEmpty)
        await a.carica(.archivio)
        prova("Archivio: sessioni e registro", !a.sessioni.isEmpty && !(a.registro?.eventi ?? []).isEmpty)
        await a.carica(.social)
        prova("Social: post", !a.post.isEmpty)

        a.ricerca = "plancia"
        a.avviaRicerca()
        for _ in 0..<40 where a.ricercaInCorso { try? await Task.sleep(nanoseconds: 100_000_000) }
        prova("la ricerca sul server torna risultati", a.risultatiPer == "plancia" && !(a.risultati?.schede ?? []).isEmpty)
        a.azzeraRicerca()
        prova("azzerare la ricerca svuota i risultati", a.risultati == nil && a.ricerca.isEmpty)

        print("== concorrenza")
        // il server finto scrive ogni richiesta nel registro e legge il ritardo da <registro>.ritardo
        let registro = ProcessInfo.processInfo.environment["PLANCIA_PROVA_REGISTRO"] ?? ""
        func ritardo(_ ms: Int) { try? Data("\(ms)".utf8).write(to: URL(fileURLWithPath: registro + ".ritardo")) }
        func righeRegistro() -> [String] {
            ((try? String(contentsOfFile: registro, encoding: .utf8)) ?? "").split(separator: "\n").map(String.init)
        }
        func quante(_ pezzo: String) -> Int { righeRegistro().filter { $0.contains(pezzo) }.count }
        let cli = Cliente()

        let r0 = Cliente.contatori.richieste
        async let p1 = cli.ottieni(Status.self, "/api/lento", query: ["ms": "300"])
        async let p2 = cli.ottieni(Status.self, "/api/lento", query: ["ms": "300"])
        let (s1, s2) = (try? await p1, try? await p2)
        prova("due letture uguali insieme fanno una richiesta sola",
              s1 != nil && s2 != nil && Cliente.contatori.richieste - r0 == 1,
              "\(Cliente.contatori.richieste - r0) richieste")

        let annullata = Task { try? await cli.ottieni(Status.self, "/api/lento", query: ["ms": "1500"]) }
        try? await Task.sleep(nanoseconds: 150_000_000)
        annullata.cancel()
        try? await Task.sleep(nanoseconds: 300_000_000)
        prova("annullare una lettura la interrompe davvero", Cliente.contatori.inVolo == 0,
              "\(Cliente.contatori.inVolo) in volo")

        let ta = Task { try? await cli.ottieni(Status.self, "/api/lento", query: ["ms": "500"]) }
        let tb = Task { try? await cli.ottieni(Status.self, "/api/lento", query: ["ms": "500"]) }
        try? await Task.sleep(nanoseconds: 100_000_000)
        ta.cancel()
        let rb = await tb.value
        prova("se uno dei due che aspettano se ne va, l'altro riceve la risposta", rb != nil)

        ritardo(150)
        let q0 = Cliente.contatori.richieste
        let solo = Archivio(cliente: Cliente())
        await solo.carica(.task)
        let singolo = Cliente.contatori.richieste - q0
        prova("una sezione si carica con qualche richiesta", singolo >= 4 && singolo <= 8, "\(singolo)")

        let doppio = Archivio(cliente: Cliente())
        let q1 = Cliente.contatori.richieste
        async let x1: Void = doppio.carica(.task)
        async let x2: Void = doppio.carica(.task)
        _ = await (x1, x2)
        prova("due caricamenti insieme della stessa sezione ne fanno uno",
              Cliente.contatori.richieste - q1 == singolo,
              "\(Cliente.contatori.richieste - q1) richieste invece di \(singolo)")

        doppio.vai(.task)
        let q2 = Cliente.contatori.richieste
        async let f1: Void = doppio.aggiorna()
        async let f2: Void = doppio.aggiorna()
        async let f3: Void = doppio.aggiorna()
        _ = await (f1, f2, f3)
        prova("tre ricariche forzate insieme fanno al massimo due letture della sezione",
              Cliente.contatori.richieste - q2 <= 2 * singolo,
              "\(Cliente.contatori.richieste - q2) richieste, una lettura ne fa \(singolo)")

        ritardo(400)
        let via = Archivio(cliente: Cliente())
        let lasciata = Task { await via.carica(.memoria) }
        try? await Task.sleep(nanoseconds: 120_000_000)
        lasciata.cancel()
        await lasciata.value
        try? await Task.sleep(nanoseconds: 250_000_000)
        prova("lasciare una sezione interrompe le sue richieste", Cliente.contatori.inVolo == 0,
              "\(Cliente.contatori.inVolo) in volo")
        prova("una sezione lasciata non conta come errore",
              via.ultimoErrore == nil && via.raggiungibile, via.ultimoErrore ?? "raggiungibile: \(via.raggiungibile)")

        ritardo(0)
        let mem = Archivio(cliente: Cliente())
        mem.vai(.memoria)
        await mem.carica(.memoria)
        let m0 = quante("/api/memoria/mappa")
        try? await Task.sleep(nanoseconds: 3_300_000_000)   // oltre la freschezza della sezione
        await mem.passoDiSottofondo()
        await mem.passoDiSottofondo()
        prova("il ciclo di sottofondo non rilegge la mappa della memoria", quante("/api/memoria/mappa") == m0,
              "\(quante("/api/memoria/mappa") - m0) letture in piu'")
        await mem.aggiorna()
        prova("⌘R rilegge la mappa", quante("/api/memoria/mappa") == m0 + 1,
              "\(quante("/api/memoria/mappa") - m0) letture in piu'")

        let quieto = Archivio(cliente: Cliente())
        await quieto.carica(.task)
        let segnale = Segnale()
        withObservationTracking { _ = quieto.sottotitolo; _ = quieto.ultimoAggiornamento } onChange: { segnale.scattato = true }
        let minuto = Int(Date().timeIntervalSince1970 / 60)
        await quieto.aggiorna()
        prova("un ricaricamento a dati fermi non cambia il sottotitolo",
              !segnale.scattato || Int(Date().timeIntervalSince1970 / 60) != minuto)

        #if !SENZA_IMPRONTA
        let l1 = try? await cli.leggi(Status.self, "/api/status")
        var impronta: Int?
        if case .nuova(_, let i)? = l1 { impronta = i }
        prova("una lettura senza impronta torna la risposta", impronta != nil)
        let l2 = try? await cli.leggi(Status.self, "/api/status", nota: impronta)
        var invariata = false
        if case .invariata? = l2 { invariata = true }
        prova("gli stessi byte con la stessa impronta tornano invariati", invariata)
        let l3 = try? await cli.leggi(Compartimenti.self, "/api/compartimenti", nota: impronta)
        var nuova = false
        if case .nuova? = l3 { nuova = true }
        prova("un'impronta diversa torna la risposta", nuova)
        #endif

        print("== date")
        let isoV = ISO8601DateFormatter(); isoV.formatOptions = [.withInternetDateTime]
        let isoF = ISO8601DateFormatter(); isoF.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let giornoV = DateFormatter(); giornoV.locale = Locale(identifier: "en_US_POSIX"); giornoV.dateFormat = "yyyy-MM-dd"
        func vecchia(_ s: String) -> Date? {
            isoV.date(from: s) ?? isoF.date(from: s) ?? giornoV.date(from: String(s.prefix(10)))
        }
        var diverse: [String] = []
        for t in ["2026-09-29T20:06:31Z", "2026-09-29T20:06:31.123Z", "2026-09-29T20:06:31.5+02:00",
                  "2026-01-01T00:00:00-05:30", "2024-02-29T23:59:59Z", "2023-02-29T10:00:00Z",
                  "2026-02-30T10:00:00Z", "2026-09-29T20:06:31", "2026-09-29", "garbage",
                  "2026-13-01T00:00:00Z", "2026-09-29T24:00:00Z", "2026-09-29 20:06:31Z",
                  "1969-12-31T23:59:59Z", "2100-02-28T12:00:00Z", "2026-09-29T20:06:31+0200"] {
            let v = vecchia(t), n = Tempo.data(t)
            let uguali = (v == nil && n == nil) || (v != nil && n != nil && abs(v!.timeIntervalSince(n!)) < 0.001)
            if !uguali { diverse.append(t) }
        }
        prova("Tempo.data da' lo stesso risultato dei formattatori su date buone e cattive", diverse.isEmpty,
              diverse.joined(separator: ", "))
        let ieri = Date().addingTimeInterval(-2 * 3600)
        let ieriISO = isoV.string(from: ieri)
        Lingua.condivisa.codice = "it"
        let inItaliano = Tempo.relativo(ieriISO)
        prova("Tempo.relativo dice quanto tempo fa, uguale alla seconda volta",
              !inItaliano.isEmpty && Tempo.relativo(ieriISO) == inItaliano, inItaliano)
        Lingua.condivisa.codice = "en"
        let inInglese = Tempo.relativo(ieriISO)
        prova("Tempo.relativo segue la lingua anche con la memoria dei valori", !inInglese.isEmpty && inInglese != inItaliano,
              "\(inItaliano) / \(inInglese)")
        Lingua.condivisa.codice = "it"
        prova("Tempo.relativo di niente e' vuoto", Tempo.relativo(nil) == "" && Tempo.relativo("boh") == "")
        prova("Tempo.scaduto: ieri si', domani no",
              Tempo.scaduto(isoV.string(from: Date().addingTimeInterval(-86400 * 2))) &&
              !Tempo.scaduto(isoV.string(from: Date().addingTimeInterval(86400 * 2))) && !Tempo.scaduto(nil))

        print("== scritture e compartimento")
        let esito = await a.imposta(task: 3, stato: "fatto")
        prova("una scrittura riuscita non torna errori", esito == nil, esito ?? "")
        let nuovo = await a.nuovoTask(titolo: "Prova", progetto: "apiary", scadenza: "2026-10-01")
        prova("nuovo task", nuovo == nil, nuovo ?? "")
        a.compartimento = "Lavoro"
        _ = await a.scrivi("POST", "/api/sync", corpo: [:])
        await a.aggiorna()

        print("== server spento")
        // una porta su cui non ascolta nessuno: si cambia config.json della casa di prova
        let casa = ProcessInfo.processInfo.environment["PLANCIA_HOME"] ?? ""
        let config = URL(fileURLWithPath: casa).appendingPathComponent("config.json")
        try? Data("{\"port\": 1}".utf8).write(to: config)
        await a.aggiorna()
        prova("server spento: non raggiungibile", !a.raggiungibile)
        prova("server spento: i dati di prima restano", !(a.lavagna?.voci ?? []).isEmpty)
        prova("server spento: il sottotitolo lo dice con l'ora dei dati",
              a.sottotitolo.hasPrefix("server non raggiungibile, dati delle "), a.sottotitolo)
        let b = Archivio(cliente: Cliente())
        await b.carica(.oggi)
        prova("server spento dall'inizio: sottotitolo senza ora", b.sottotitolo == "server non raggiungibile", b.sottotitolo)
        let errore = await b.imposta(task: 1, stato: "fatto")
        prova("scrivere a server spento torna un errore", errore != nil)
        _ = porta

        print("\n\(passati) passate, \(falliti) fallite")
        exit(falliti == 0 ? 0 : 1)
    }
}
