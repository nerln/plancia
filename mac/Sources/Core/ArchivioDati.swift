// Lo Store dell'app: i dati di ogni sezione, l'ultimo aggiornamento, se il server
// risponde, il compartimento scelto, la ricerca. Le viste lo leggono dall'ambiente:
//
//     @Environment(Archivio.self) private var archivio
//
// (Il file si chiama ArchivioDati.swift e non Archivio.swift perche' swiftc rifiuta
// due file con lo stesso nome, e Viste/Archivio.swift e' la vista della sezione.)
//
// Regole:
//  - una richiesta che fallisce non cancella i dati che c'erano: la vista li mostra
//    ancora e il sottotitolo della finestra dice che il server non risponde;
//  - ogni sezione carica da sola quello che le serve (`carica(_:)`), a cadenza di 30 s
//    e su richiesta (`aggiorna()`, ⌘R);
//  - le scritture passano da qui, cosi' dopo ognuna i dati si rileggono.

import Foundation
import Observation

// MARK: - sezioni e ambiti

enum Sezione: String, CaseIterable, Identifiable, Hashable {
    case oggi, task, progetti, social, memoria, archivio

    var id: String { rawValue }

    var simbolo: String {
        switch self {
        case .oggi: return "sun.max"
        case .task: return "checklist"
        case .progetti: return "folder"
        case .social: return "text.bubble"
        case .memoria: return "brain"
        case .archivio: return "archivebox"
        }
    }

    @MainActor var titolo: String {
        switch self {
        case .oggi: return tr("Oggi", "Today")
        case .task: return tr("Task", "Tasks")
        case .progetti: return tr("Progetti", "Projects")
        case .social: return tr("Social", "Social")
        case .memoria: return tr("Memoria", "Memory")
        case .archivio: return tr("Archivio", "Archive")
        }
    }

    /// ⌘1 ... ⌘6
    var numero: Int { (Sezione.allCases.firstIndex(of: self) ?? 0) + 1 }

    /// Dal nome di una vista della dashboard web o di un URL plancia://.
    static func da(nome: String?) -> Sezione? {
        switch (nome ?? "").lowercased() {
        case "oggi", "today", "home": return .oggi
        case "task", "tasks", "lavagna": return .task
        case "progetti", "projects", "project", "progetto": return .progetti
        case "social", "post": return .social
        case "memoria", "memory", "knowledge": return .memoria
        case "archivio", "archive", "sessioni", "sessions", "eventi": return .archivio
        default: return nil
        }
    }
}

enum AmbitoRicerca: String, CaseIterable, Identifiable, Hashable {
    case tutto, task, progetti, sessioni, memoria
    var id: String { rawValue }

    @MainActor var titolo: String {
        switch self {
        case .tutto: return tr("Tutto", "All")
        case .task: return tr("Task", "Tasks")
        case .progetti: return tr("Progetti", "Projects")
        case .sessioni: return tr("Sessioni", "Sessions")
        case .memoria: return tr("Memoria", "Memory")
        }
    }
}

// MARK: - lo store

@MainActor
@Observable
final class Archivio {
    static let condiviso = Archivio()

    @ObservationIgnored let cliente: Cliente

    init(cliente: Cliente = .condiviso) { self.cliente = cliente }

    // MARK: stato della rete

    /// Falso quando l'ultima lettura e' fallita perche' il server non risponde.
    private(set) var raggiungibile = true
    /// Quando una lettura e' riuscita per l'ultima volta.
    private(set) var ultimoAggiornamento: Date?
    private(set) var inCaricamento = false
    /// L'ultimo errore che non e' "server spento" (decodifica, HTTP). Nessuna vista lo
    /// deve mostrare a schermo intero: e' per il sottotitolo e per il diario.
    private(set) var ultimoErrore: String?

    // MARK: navigazione e scelte

    var sezione: Sezione = .oggi
    var ricerca = ""
    var ambito: AmbitoRicerca = .tutto
    /// Il campo di ricerca e' in uso: fa comparire gli ambiti sotto la barra degli strumenti.
    var ricercaAperta = false
    /// Selezioni che altre parti dell'app possono chiedere (Jarvis, plancia://, "Apri progetto").
    var progettoScelto: String?
    var memoriaScelta: String?
    var taskScelto: String?
    var postScelto: String?
    var sessioneScelta: String?

    /// Il compartimento scelto nel Picker; nil finche' non si sceglie.
    var compartimento: String? {
        didSet {
            guard compartimento != oldValue else { return }
            dettagli = [:]
            Task { await aggiorna() }
        }
    }
    private(set) var compartimenti = Compartimenti()

    // MARK: dati

    private(set) var status: Status?
    private(set) var recap: Recap?
    private(set) var prossimi: Prossimi?
    private(set) var proposte: [Proposta] = []
    private(set) var lavagna: Lavagna?
    private(set) var compiti: [Compito] = []
    private(set) var progetti: [Progetto] = []
    private(set) var alberoProgetti: [Progetto] = []
    private(set) var post: [Post] = []
    private(set) var sessioni: [Sessione] = []
    private(set) var registro: Registro?
    private(set) var schede: [Scheda] = []
    private(set) var mappa: MappaMemoria?
    private(set) var lanci: [Lancio] = []
    private(set) var overview: Overview?
    private(set) var dettagli: [String: DettaglioProgetto] = [:]

    // MARK: ricerca

    private(set) var risultati: RisultatiRicerca?
    /// La parola a cui si riferiscono `risultati`.
    private(set) var risultatiPer = ""
    private(set) var ricercaInCorso = false
    @ObservationIgnored private var ricercaTask: Task<Void, Never>?

    // MARK: ciclo

    @ObservationIgnored private var ciclo: Task<Void, Never>?

    /// Parte il ricaricamento leggero a cadenza fissa. Si chiama una volta.
    func avvia(ogniSecondi: Double = 30) {
        guard ciclo == nil else { return }
        ciclo = Task { [weak self] in
            while !Task.isCancelled {
                await self?.aggiorna()
                try? await Task.sleep(nanoseconds: UInt64(ogniSecondi * 1_000_000_000))
            }
        }
    }

    func ferma() {
        ciclo?.cancel()
        ciclo = nil
    }

    // MARK: testo di stato

    /// Il sottotitolo della finestra: l'unico posto in cui si dice quanto e' fresco il dato.
    var sottotitolo: String {
        if !raggiungibile {
            if let u = ultimoAggiornamento {
                return tr("server non raggiungibile, dati delle \(Tempo.ora(u))",
                          "server unreachable, data from \(Tempo.ora(u))")
            }
            return tr("server non raggiungibile", "server unreachable")
        }
        if let u = ultimoAggiornamento {
            return tr("aggiornato alle \(Tempo.ora(u))", "updated at \(Tempo.ora(u))")
        }
        return ""
    }

    /// Task aperti, per il badge della barra laterale. Nil se non si sa o se sono zero.
    func conteggio(_ s: Sezione) -> Int? {
        guard s == .task, let n = lavagna?.aperti, n > 0 else { return nil }
        return n
    }

    // MARK: caricamento

    private enum Esito { case ok, nonRaggiungibile, altro(String) }
    private typealias Lavoro = @MainActor () async -> Esito

    private func lavoro<T: Decodable>(_ percorso: String, _ query: [String: String] = [:],
                                      _ assegna: @escaping @MainActor (T) -> Void) -> Lavoro {
        return { [unowned self] in
            do {
                let v = try await self.cliente.ottieni(T.self, percorso, query: query,
                                                       compartimento: self.compartimento)
                assegna(v)
                return .ok
            } catch let e as ErroreCliente {
                return e.eNonRaggiungibile ? .nonRaggiungibile : .altro(e.localizedDescription)
            } catch {
                return .altro(error.localizedDescription)
            }
        }
    }

    private func lavoroElenco<T: Decodable>(_ tipo: T.Type, _ percorso: String,
                                            _ query: [String: String] = [:],
                                            _ assegna: @escaping @MainActor ([T]) -> Void) -> Lavoro {
        return { [unowned self] in
            do {
                let v = try await self.cliente.elenco(T.self, percorso, query: query,
                                                      compartimento: self.compartimento)
                assegna(v)
                return .ok
            } catch let e as ErroreCliente {
                return e.eNonRaggiungibile ? .nonRaggiungibile : .altro(e.localizedDescription)
            } catch {
                return .altro(error.localizedDescription)
            }
        }
    }

    /// Esegue i lavori insieme e ne riassume l'esito: raggiungibile se almeno uno e' riuscito.
    private func esegui(_ lavori: [Lavoro]) async {
        inCaricamento = true
        defer { inCaricamento = false }
        var esiti: [Esito] = []
        await withTaskGroup(of: Esito.self) { gruppo in
            for l in lavori { gruppo.addTask { @MainActor in await l() } }
            for await e in gruppo { esiti.append(e) }
        }
        var riusciti = 0, spenti = 0
        var errore: String?
        for e in esiti {
            switch e {
            case .ok: riusciti += 1
            case .nonRaggiungibile: spenti += 1
            case .altro(let m): errore = m
            }
        }
        if riusciti > 0 {
            raggiungibile = true
            ultimoAggiornamento = Date()
            ultimoErrore = errore
        } else if spenti > 0 {
            raggiungibile = false
        } else {
            ultimoErrore = errore
        }
    }

    private var lavoriBase: [Lavoro] {
        [
            lavoro("/api/status") { (v: Status) in self.status = v },
            lavoro("/api/compartimenti") { (v: Compartimenti) in
                self.compartimenti = v
                // un compartimento scelto che non c'e' piu' (o compartimenti spenti) si dimentica
                if let c = self.compartimento, !v.attivi || !(v.elenco ?? []).contains(c) {
                    self.compartimento = nil
                }
            },
            lavoro("/api/lavagna", ["stato": "tutti", "limite": "500"]) { (v: Lavagna) in self.lavagna = v },
        ]
    }

    private func lavori(per s: Sezione) -> [Lavoro] {
        switch s {
        case .oggi:
            return [
                lavoro("/api/recap", ["solo_cache": "1", "lang": Lingua.condivisa.codice]) { (v: Recap) in self.recap = v },
                lavoro("/api/prossimi") { (v: Prossimi) in self.prossimi = v },
                lavoroElenco(Proposta.self, "/api/proposte", ["lang": Lingua.condivisa.codice]) { self.proposte = $0 },
                lavoroElenco(Lancio.self, "/api/runs", ["limite": "10"]) { self.lanci = $0 },
            ]
        case .task:
            return [
                lavoroElenco(Compito.self, "/api/tasks", ["status": "tutti", "limit": "500"]) { self.compiti = $0 },
                lavoroElenco(Progetto.self, "/api/projects") { self.progetti = $0 },
            ]
        case .progetti:
            return [
                lavoroElenco(Progetto.self, "/api/projects") { self.progetti = $0 },
                lavoroElenco(Progetto.self, "/api/projects", ["albero": "1"]) { self.alberoProgetti = $0 },
            ]
        case .social:
            return [
                lavoroElenco(Post.self, "/api/posts") { self.post = $0 },
                lavoroElenco(Progetto.self, "/api/projects") { self.progetti = $0 },
            ]
        case .memoria:
            return [
                lavoroElenco(Scheda.self, "/api/knowledge") { self.schede = $0 },
                lavoro("/api/memoria/mappa") { (v: MappaMemoria) in self.mappa = v },
            ]
        case .archivio:
            return [
                lavoroElenco(Sessione.self, "/api/sessions", ["limit": "400"]) { self.sessioni = $0 },
                lavoro("/api/eventi", ["limite": "300"]) { (v: Registro) in self.registro = v },
            ]
        }
    }

    /// Carica quello che serve a una sezione, piu' lo stato del server. Le viste lo
    /// chiamano quando compaiono; il ciclo lo richiama ogni 30 s.
    func carica(_ s: Sezione) async {
        var l = lavoriBase + lavori(per: s)
        if s == .progetti, let k = progettoScelto {
            l.append(lavoroDettaglio(k))
        }
        await esegui(l)
    }

    /// Ricarica la sezione aperta (⌘R e il ciclo).
    func aggiorna() async {
        await carica(sezione)
        if !ricerca.trimmed.isEmpty { avviaRicerca() }
    }

    /// Il riepilogo generale (statistiche, agenti, attivita'): non lo carica nessuna
    /// sezione da sola, chi lo vuole lo chiede.
    func caricaOverview() async {
        await esegui([lavoro("/api/overview", ["lang": Lingua.condivisa.codice]) { (v: Overview) in self.overview = v }])
    }

    // MARK: dettaglio di un progetto

    private func lavoroDettaglio(_ chiave: String) -> Lavoro {
        let percorso = "/api/projects/" + (chiave.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? chiave)
        return lavoro(percorso) { (v: DettaglioProgetto) in self.dettagli[chiave] = v }
    }

    func caricaDettaglio(_ chiave: String) async {
        await esegui([lavoroDettaglio(chiave)])
    }

    // MARK: ricerca (il filtro locale sta nella vista Risultati)

    /// Da chiamare quando cambia `ricerca`: annulla la richiesta precedente e, dopo
    /// circa 200 ms senza nuovi caratteri, chiede al server.
    func avviaRicerca() {
        ricercaTask?.cancel()
        let q = ricerca.trimmed
        guard q.count >= 2 else {
            risultati = nil
            risultatiPer = ""
            ricercaInCorso = false
            return
        }
        ricercaInCorso = true
        ricercaTask = Task { [weak self] in
            // il filtro locale lavora sui dati gia' in memoria: se mancano, si portano
            await self?.assicuraDatiLocali()
            try? await Task.sleep(nanoseconds: 200_000_000)
            guard !Task.isCancelled, let self = self else { return }
            do {
                let r = try await self.cliente.ottieni(RisultatiRicerca.self, "/api/search",
                                                       query: ["q": q], compartimento: self.compartimento,
                                                       timeout: 15)
                guard !Task.isCancelled else { return }
                self.risultati = r
                self.risultatiPer = q
                self.ricercaInCorso = false
                self.raggiungibile = true
            } catch is CancellationError {
                return
            } catch let e as ErroreCliente {
                guard !Task.isCancelled else { return }
                self.ricercaInCorso = false
                if e.eNonRaggiungibile { self.raggiungibile = false }
            } catch {
                self.ricercaInCorso = false
            }
        }
    }

    /// Porta in memoria quello su cui filtra la ricerca locale, se non c'e' ancora.
    private func assicuraDatiLocali() async {
        var l: [Lavoro] = []
        if progetti.isEmpty { l += lavori(per: .progetti).prefix(1) }
        if compiti.isEmpty { l += lavori(per: .task).prefix(1) }
        if sessioni.isEmpty { l += lavori(per: .archivio).prefix(1) }
        if schede.isEmpty { l += lavori(per: .memoria).prefix(1) }
        if !l.isEmpty { await esegui(l) }
    }

    func azzeraRicerca() {
        ricercaTask?.cancel()
        ricerca = ""
        ricercaAperta = false
        risultati = nil
        risultatiPer = ""
        ricercaInCorso = false
    }

    // MARK: navigazione richiesta da fuori

    func vai(_ s: Sezione, progetto: String? = nil) {
        azzeraRicerca()
        if let p = progetto { progettoScelto = p }
        sezione = s
    }

    // MARK: scritture

    /// Una scrittura e, se riesce, la rilettura della sezione. Torna il messaggio d'errore
    /// del server, o nil se e' andata.
    @discardableResult
    func scrivi(_ metodo: String, _ percorso: String, corpo: [String: Any]? = nil) async -> String? {
        do {
            try await cliente.scrivi(metodo, percorso, corpo: corpo, compartimento: compartimento)
            await aggiorna()
            return nil
        } catch let e as ErroreCliente {
            if e.eNonRaggiungibile { raggiungibile = false }
            return e.localizedDescription
        } catch {
            return error.localizedDescription
        }
    }

    /// Stessa cosa, ma torna la risposta del server (Riprendi ne usa il messaggio).
    func scriviRisposta(_ metodo: String, _ percorso: String, corpo: [String: Any]? = nil) async -> Result<JSONValue, ErroreCliente> {
        do {
            let r = try await cliente.scrivi(metodo, percorso, corpo: corpo, compartimento: compartimento)
            await aggiorna()
            return .success(r)
        } catch let e as ErroreCliente {
            if e.eNonRaggiungibile { raggiungibile = false }
            return .failure(e)
        } catch {
            return .failure(.decodifica(error.localizedDescription))
        }
    }

    /// Cambia lo stato di un task di Plancia: aperto, in corso, bloccato, fatto, archiviato.
    @discardableResult
    func imposta(task id: Int, stato: String) async -> String? {
        await scrivi("PATCH", "/api/tasks/\(id)", corpo: ["status": stato])
    }

    @discardableResult
    func nuovoTask(titolo: String, note: String = "", progetto: String? = nil,
                   priorita: Int = 2, scadenza: String? = nil) async -> String? {
        var c: [String: Any] = ["title": titolo, "body": note, "priority": priorita]
        if let p = progetto, !p.isEmpty { c["project"] = p }
        if let s = scadenza, !s.isEmpty { c["due"] = s }
        return await scrivi("POST", "/api/tasks", corpo: c)
    }

    /// Chiede al server di rileggere le fonti (Claude Code, Codex, repository).
    func sincronizza() async {
        _ = await scrivi("POST", "/api/sync", corpo: [:])
    }
}

extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}
