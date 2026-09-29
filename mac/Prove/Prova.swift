// La prova del Core, senza interfaccia: decodifica tutte le fixture con i modelli,
// prova che un campo mancante o del tipo sbagliato non fa cadere niente, e fa girare
// lo Store e il Cliente contro un server finto che serve le stesse fixture.
// La lancia tools/prova-mac.sh (compila Core/*.swift insieme a questo file).

import Foundation

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
