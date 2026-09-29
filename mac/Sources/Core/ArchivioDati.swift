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
//
// Come sta veloce (le misure sono in tools/misura-mac.sh):
//  - il thread principale non fa rete ne' decodifica: le risposte arrivano gia' decodificate
//    dal Cliente (Core/Cliente.swift) e qui si fa solo l'assegnazione;
//  - ogni lettura ricorda l'impronta dell'ultima risposta consegnata: se il server manda gli
//    stessi byte, non si decodifica e non si assegna niente, quindi le viste non si
//    ridisegnano (il ciclo di 30 s con dati fermi costa quasi zero);
//  - una sezione che si sta gia' caricando non parte due volte: chi la chiede di nuovo
//    aspetta quella in corso; una ricarica forzata (⌘R, dopo una scrittura) durante un
//    caricamento ne fa una sola di seguito, non tante quante sono le richieste;
//  - se chi aspettava una sezione se ne va (cambia sezione), le richieste di quella
//    sezione si interrompono, a meno che qualcun altro non le stia aspettando;
//  - tornare in una sezione appena caricata (meno di 3 s fa) non rilegge niente, e le
//    letture pesanti che cambiano di rado (la mappa della memoria) hanno una freschezza
//    minima propria: nel ciclo di sottofondo non si rifanno finche' le schede non cambiano;
//  - la ricerca ricorda le ultime risposte: cancellare un carattere non rifa la richiesta.

import AppKit
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
    /// Il minuto (dal 1970) dell'ultimo aggiornamento riuscito. E' l'unica parte
    /// dell'orario che le viste osservano: cambia una volta al minuto, non a ogni ciclo.
    private(set) var minutoUltimo = 0
    @ObservationIgnored private var ultimo: Date?
    /// Quando una lettura e' riuscita per l'ultima volta. Chi la legge viene avvisato solo
    /// quando cambia il minuto (o da nil a un valore), non a ogni ciclo di 30 s.
    var ultimoAggiornamento: Date? { _ = minutoUltimo; return ultimo }
    /// Vero mentre almeno un caricamento e' in corso.
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
            // i dati di un altro compartimento sono un'altra cosa: nessuna impronta vale piu'
            impronte.removeAll()
            ultimaLettura.removeAll()
            sezioneLetta.removeAll()
            cacheRicerca.removeAll()
            Task { await aggiorna() }
        }
    }
    private(set) var compartimenti = Compartimenti()

    // MARK: dati

    private(set) var status: Status?
    private(set) var recap: Recap?
    private(set) var prossimi: Prossimi?
    private(set) var proposte: [Proposta] = []
    private(set) var lavagna: Lavagna? {
        didSet { apertiTotali = lavagna?.aperti ?? 0 }
    }
    /// I task aperti, per il badge: separato da `lavagna` cosi' la barra laterale non si
    /// ridisegna ogni volta che cambia una riga della lavagna, ma solo se cambia il numero.
    private(set) var apertiTotali = 0
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
    /// Le ultime risposte della ricerca, per compartimento e parola.
    @ObservationIgnored private var cacheRicerca: [String: (quando: Date, risultati: RisultatiRicerca)] = [:]

    // MARK: ciclo

    @ObservationIgnored private var ciclo: Task<Void, Never>?
    @ObservationIgnored private var osservatoreAttivazione: NSObjectProtocol?

    /// Parte il ricaricamento leggero a cadenza fissa. Si chiama una volta. Con l'app in
    /// secondo piano il ciclo rallenta (un giro ogni quattro) e al ritorno in primo piano
    /// rilegge subito se i dati hanno piu' di un ciclo.
    func avvia(ogniSecondi: Double = 30) {
        guard ciclo == nil else { return }
        osservatoreAttivazione = NotificationCenter.default.addObserver(
            forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                guard let self = self else { return }
                let vecchio = self.ultimo.map { Date().timeIntervalSince($0) } ?? .infinity
                if vecchio > ogniSecondi { await self.passoDiSottofondo() }
            }
        }
        ciclo = Task { [weak self] in
            var saltati = 0
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(ogniSecondi * 1_000_000_000))
                guard let self = self, !Task.isCancelled else { return }
                if !NSApplication.shared.isActive && saltati < 3 {
                    saltati += 1
                    continue
                }
                saltati = 0
                await self.passoDiSottofondo()
            }
        }
        Task {
            await passoDiSottofondo()
            await precarica()
        }
    }

    /// Dopo il primo giro porta in memoria, una alla volta e con calma, le altre sezioni,
    /// cosi' la prima volta che si entra c'e' gia' tutto e la vista si disegna una volta sola
    /// invece di vuota e poi piena. Della memoria si prendono le schede ma non la mappa (il
    /// layout costa al server secondi): quella si legge quando si apre la sezione.
    private func precarica() async {
        for s in Sezione.allCases where s != sezione {
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled, ciclo != nil else { return }
            let l: [Lavoro] = s == .memoria
                ? [lavoroElenco(Scheda.self, "/api/knowledge") { self.schede = $0 }]
                : lavori(per: s)
            await esegui(l, forza: false)
        }
    }

    /// Quello che il ciclo fa a ogni giro: rilegge la sezione aperta senza forzare le
    /// letture che cambiano di rado.
    func passoDiSottofondo() async { await aggiorna(forza: false) }

    func ferma() {
        ciclo?.cancel()
        ciclo = nil
        if let o = osservatoreAttivazione { NotificationCenter.default.removeObserver(o) }
        osservatoreAttivazione = nil
    }

    // MARK: testo di stato

    /// Il sottotitolo della finestra: l'unico posto in cui si dice quanto e' fresco il dato.
    /// Cambia al massimo una volta al minuto (vedi `minutoUltimo`).
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
        guard s == .task, apertiTotali > 0 else { return nil }
        return apertiTotali
    }

    // MARK: caricamento: le letture

    private enum Esito { case ok, nonRaggiungibile, altro(String), annullato }

    /// Una lettura da fare: da dove, quanto puo' restare fresca senza rifarla, e come.
    private struct Lavoro {
        let corpo: @MainActor (_ forza: Bool) async -> [Esito]
    }

    /// Le impronte delle ultime risposte consegnate, per fonte e compartimento.
    @ObservationIgnored private var impronte: [String: Int] = [:]
    /// Quando ogni fonte e' stata letta con successo l'ultima volta.
    @ObservationIgnored private var ultimaLettura: [String: Date] = [:]
    /// Quando ogni sezione e' stata caricata per intero con successo l'ultima volta.
    @ObservationIgnored private var sezioneLetta: [Sezione: Date] = [:]
    /// La freschezza sotto cui tornare in una sezione non rilegge niente.
    private static let freschezzaSezione: TimeInterval = 3

    private func chiaveFonte(_ percorso: String, _ query: [String: String]) -> String {
        let q = query.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: "&")
        return percorso + "?" + q + "|" + (compartimento ?? "")
    }

    private func esitoDi(_ errore: Error) -> Esito {
        if errore is CancellationError { return .annullato }
        if let e = errore as? ErroreCliente { return e.eNonRaggiungibile ? .nonRaggiungibile : .altro(e.localizedDescription) }
        return .altro(errore.localizedDescription)
    }

    /// Il cuore di ogni lettura: salta se e' fresca, altrimenti chiede con l'impronta di
    /// prima, assegna solo se la risposta e' nuova, e ricorda impronta e ora.
    private func leggi<V>(_ chiave: String, minimo: TimeInterval, forza: Bool,
                          _ richiesta: (Int?) async throws -> Lettura<V>,
                          _ assegna: @escaping @MainActor (V) -> Void) async -> Esito {
        if !forza, minimo > 0, let t = ultimaLettura[chiave], Date().timeIntervalSince(t) < minimo { return .ok }
        let compartimentoDiPartenza = compartimento
        do {
            let r = try await richiesta(impronte[chiave])
            // una risposta arrivata dopo il cambio di compartimento e' di un altro archivio
            guard compartimento == compartimentoDiPartenza else { return .annullato }
            if case .nuova(let v, let imp) = r {
                consegna { [unowned self] in
                    guard self.compartimento == compartimentoDiPartenza else { return }
                    assegna(v)
                    self.impronte[chiave] = imp
                }
            }
            ultimaLettura[chiave] = Date()
            return .ok
        } catch {
            return esitoDi(error)
        }
    }

    // MARK: assegnazioni a gruppi

    /// Le risposte nuove non si assegnano una a una appena arrivano: una sezione ne legge
    /// quattro o cinque, e ogni assegnazione farebbe ricalcolare la vista da capo. Si
    /// raccolgono per una trentina di millisecondi (o fino alla fine del caricamento) e si
    /// assegnano tutte insieme, cosi' la vista si ridisegna una volta sola.
    @ObservationIgnored private var inAttesa: [@MainActor () -> Void] = []
    @ObservationIgnored private var svuotamento: Task<Void, Never>?

    private func consegna(_ f: @escaping @MainActor () -> Void) {
        inAttesa.append(f)
        guard svuotamento == nil else { return }
        svuotamento = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 30_000_000)
            guard !Task.isCancelled else { return }
            self?.svuota()
        }
    }

    private func svuota() {
        svuotamento?.cancel()
        svuotamento = nil
        let lista = inAttesa
        inAttesa = []
        for f in lista { f() }
    }

    private func lavoro<T: Decodable>(_ percorso: String, _ query: [String: String] = [:], minimo: TimeInterval = 0,
                                      timeout: TimeInterval = 8,
                                      _ assegna: @escaping @MainActor (T) -> Void) -> Lavoro {
        Lavoro { [unowned self] forza in
            let chiave = self.chiaveFonte(percorso, query)
            let c = self.compartimento
            return [await self.leggi(chiave, minimo: minimo, forza: forza, { nota in
                try await self.cliente.leggi(T.self, percorso, query: query, compartimento: c,
                                             timeout: timeout, nota: nota)
            }, assegna)]
        }
    }

    private func lavoroElenco<T: Decodable>(_ tipo: T.Type, _ percorso: String,
                                            _ query: [String: String] = [:], minimo: TimeInterval = 0,
                                            _ assegna: @escaping @MainActor ([T]) -> Void) -> Lavoro {
        Lavoro { [unowned self] forza in
            let chiave = self.chiaveFonte(percorso, query)
            let c = self.compartimento
            return [await self.leggi(chiave, minimo: minimo, forza: forza, { nota in
                try await self.cliente.leggiElenco(T.self, percorso, query: query, compartimento: c, nota: nota)
            }, assegna)]
        }
    }

    /// Esegue i lavori insieme e ne riassume l'esito: raggiungibile se almeno uno e' riuscito.
    /// Torna vero se sono riusciti tutti (la sezione allora si considera fresca).
    @discardableResult
    private func esegui(_ lavori: [Lavoro], forza: Bool) async -> Bool {
        caricamentiAttivi += 1
        if caricamentiAttivi == 1 { inCaricamento = true }
        defer {
            caricamentiAttivi -= 1
            if caricamentiAttivi == 0 { inCaricamento = false }
        }
        var esiti: [Esito] = []
        await withTaskGroup(of: [Esito].self) { gruppo in
            for l in lavori { gruppo.addTask { @MainActor in await l.corpo(forza) } }
            for await e in gruppo { esiti += e }
        }
        // quello che e' arrivato si assegna adesso, prima che chi aspettava riparta
        svuota()
        var riusciti = 0, spenti = 0, annullati = 0
        var errore: String?
        for e in esiti {
            switch e {
            case .ok: riusciti += 1
            case .nonRaggiungibile: spenti += 1
            case .annullato: annullati += 1
            case .altro(let m): errore = m
            }
        }
        if riusciti > 0 {
            if !raggiungibile { raggiungibile = true }
            segnaAggiornato()
            if ultimoErrore != errore { ultimoErrore = errore }
        } else if spenti > 0 {
            if raggiungibile { raggiungibile = false }
        } else if annullati == 0 {
            if ultimoErrore != errore { ultimoErrore = errore }
        }
        return riusciti == esiti.count
    }

    @ObservationIgnored private var caricamentiAttivi = 0

    private func segnaAggiornato() {
        let adesso = Date()
        ultimo = adesso
        let minuto = Int(adesso.timeIntervalSince1970 / 60)
        if minuto != minutoUltimo { minutoUltimo = minuto }
    }

    private var lavoriBase: [Lavoro] {
        [
            lavoro("/api/status") { (v: Status) in if self.status != v { self.status = v } },
            lavoro("/api/compartimenti", minimo: 20) { (v: Compartimenti) in
                if self.compartimenti != v { self.compartimenti = v }
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
            return [lavoroMemoria]
        case .archivio:
            return [
                lavoroElenco(Sessione.self, "/api/sessions", ["limit": "400"]) { self.sessioni = $0 },
                lavoro("/api/eventi", ["limite": "300"]) { (v: Registro) in self.registro = v },
            ]
        }
    }

    /// Le schede e la mappa. La mappa e' la lettura piu' cara del server (il layout si
    /// calcola a ogni richiesta e con qualche centinaio di schede ci vogliono secondi),
    /// quindi si rilegge solo se le schede sono cambiate, se non c'e' ancora, se l'utente
    /// forza la ricarica, o se sono passati due minuti.
    private var lavoroMemoria: Lavoro {
        let schede = lavoroElenco(Scheda.self, "/api/knowledge") { [unowned self] in
            self.schede = $0
            self.schedeCambiate = true
        }
        let mappa = lavoro("/api/memoria/mappa", minimo: 120, timeout: 60) { (v: MappaMemoria) in self.mappa = v }
        return Lavoro { [unowned self] forza in
            self.schedeCambiate = false
            let a = await schede.corpo(forza)
            let b = await mappa.corpo(forza || self.schedeCambiate || self.mappa == nil)
            return a + b
        }
    }

    @ObservationIgnored private var schedeCambiate = false

    // MARK: caricamento: una sezione alla volta

    private struct Volo {
        let id: Int
        let task: Task<Void, Never>
        var attese: Int
        var ripeti: Bool
    }
    @ObservationIgnored private var voli: [Sezione: Volo] = [:]
    @ObservationIgnored private var prossimoVolo = 0

    /// Carica quello che serve a una sezione, piu' lo stato del server. Le viste lo
    /// chiamano quando compaiono; il ciclo lo richiama ogni 30 s.
    ///  - se la sezione si sta gia' caricando, aspetta quella (non parte una seconda);
    ///  - con `forza` (⌘R, dopo una scrittura) una lettura gia' in corso non basta, perche'
    ///    potrebbe essere partita prima del cambiamento: se ne fa una sola di seguito;
    ///  - senza `forza`, una sezione caricata meno di 3 s fa non si rilegge.
    /// Se chi aspetta viene annullato e non aspetta piu' nessuno, le richieste si interrompono.
    func carica(_ s: Sezione, forza: Bool = false) async {
        if var v = voli[s] {
            v.attese += 1
            if forza { v.ripeti = true }
            voli[s] = v
            await attendi(s, v)
            return
        }
        if !forza, let t = sezioneLetta[s], Date().timeIntervalSince(t) < Archivio.freschezzaSezione { return }
        prossimoVolo += 1
        let id = prossimoVolo
        let task = Task { [weak self] in
            guard let self = self else { return }
            var forzato = forza
            while true {
                self.voli[s]?.ripeti = false
                await self.caricaSezione(s, forza: forzato)
                forzato = true
                if Task.isCancelled || !(self.voli[s]?.id == id && self.voli[s]?.ripeti == true) { break }
            }
            if self.voli[s]?.id == id { self.voli[s] = nil }
        }
        let v = Volo(id: id, task: task, attese: 1, ripeti: false)
        voli[s] = v
        await attendi(s, v)
    }

    private func attendi(_ s: Sezione, _ v: Volo) async {
        await withTaskCancellationHandler {
            await v.task.value
        } onCancel: {
            Task { @MainActor [weak self] in self?.rinuncia(s, v.id) }
        }
    }

    private func rinuncia(_ s: Sezione, _ id: Int) {
        guard var v = voli[s], v.id == id else { return }
        v.attese -= 1
        if v.attese <= 0 {
            v.task.cancel()
            voli[s] = nil
        } else {
            voli[s] = v
        }
    }

    private func caricaSezione(_ s: Sezione, forza: Bool) async {
        var l = lavoriBase + lavori(per: s)
        if s == .progetti, let k = progettoScelto { l.append(lavoroDettaglio(k)) }
        let tutti = await esegui(l, forza: forza)
        if tutti && !Task.isCancelled { sezioneLetta[s] = Date() }
    }

    /// Ricarica la sezione aperta (⌘R e il ciclo). `forza: false` (il ciclo) lascia stare le
    /// letture che hanno una freschezza propria (la mappa della memoria).
    func aggiorna(forza: Bool = true) async {
        await carica(sezione, forza: forza)
        if !ricerca.trimmed.isEmpty { avviaRicerca(ignoraCache: forza) }
    }

    /// Il riepilogo generale (statistiche, agenti, attivita'): non lo carica nessuna
    /// sezione da sola, chi lo vuole lo chiede.
    func caricaOverview() async {
        await esegui([lavoro("/api/overview", ["lang": Lingua.condivisa.codice], minimo: 2) { (v: Overview) in self.overview = v }],
                     forza: false)
    }

    // MARK: dettaglio di un progetto

    private func lavoroDettaglio(_ chiave: String) -> Lavoro {
        let percorso = "/api/projects/" + (chiave.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? chiave)
        return lavoro(percorso, minimo: 2) { (v: DettaglioProgetto) in self.dettagli[chiave] = v }
    }

    func caricaDettaglio(_ chiave: String) async {
        await esegui([lavoroDettaglio(chiave)], forza: false)
    }

    // MARK: ricerca (il filtro locale sta nella vista Risultati)

    /// Da chiamare quando cambia `ricerca`: annulla la richiesta precedente e, dopo
    /// circa 200 ms senza nuovi caratteri, chiede al server. Una parola gia' cercata da
    /// meno di 30 s (tornando indietro con il cancella) non rifa la richiesta.
    func avviaRicerca(ignoraCache: Bool = false) {
        ricercaTask?.cancel()
        let q = ricerca.trimmed
        guard q.count >= 2 else {
            risultati = nil
            risultatiPer = ""
            ricercaInCorso = false
            return
        }
        let chiave = (compartimento ?? "") + "|" + q
        if !ignoraCache, let c = cacheRicerca[chiave], Date().timeIntervalSince(c.quando) < 30 {
            if risultatiPer != q { risultatiPer = q }
            if risultati != c.risultati { risultati = c.risultati }
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
                self.ricordaRicerca(chiave, r)
                if self.risultati != r { self.risultati = r }
                if self.risultatiPer != q { self.risultatiPer = q }
                self.ricercaInCorso = false
                if !self.raggiungibile { self.raggiungibile = true }
            } catch is CancellationError {
                return
            } catch let e as ErroreCliente {
                guard !Task.isCancelled else { return }
                self.ricercaInCorso = false
                if e.eNonRaggiungibile, self.raggiungibile { self.raggiungibile = false }
            } catch {
                self.ricercaInCorso = false
            }
        }
    }

    private func ricordaRicerca(_ chiave: String, _ r: RisultatiRicerca) {
        cacheRicerca[chiave] = (Date(), r)
        if cacheRicerca.count > 16, let vecchia = cacheRicerca.min(by: { $0.value.quando < $1.value.quando })?.key {
            cacheRicerca[vecchia] = nil
        }
    }

    /// Porta in memoria quello su cui filtra la ricerca locale, se non c'e' ancora.
    private func assicuraDatiLocali() async {
        var l: [Lavoro] = []
        if progetti.isEmpty { l += lavori(per: .progetti).prefix(1) }
        if compiti.isEmpty { l += lavori(per: .task).prefix(1) }
        if sessioni.isEmpty { l += lavori(per: .archivio).prefix(1) }
        if schede.isEmpty { l += lavori(per: .memoria) }
        if !l.isEmpty { await esegui(l, forza: false) }
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
