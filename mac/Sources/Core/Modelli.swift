// I modelli dei dati che il server manda. Nessuno schema garantito: l'API e' scritta
// a mano e cambia, quindi ogni campo e' opzionale e ogni campo si decodifica da solo.
// Un campo mancante, nullo o del tipo sbagliato (un numero dove ci si aspetta un testo,
// un booleano dove ci si aspetta un intero) diventa `nil` e non fa cadere la vista.
//
// Le chiavi arrivano in snake_case e si leggono in camelCase (`project_key` diventa
// `projectKey`): il Cliente usa `.convertFromSnakeCase`.
//
// Le fixture in mac/Prove/fixture/ vengono dall'archivio dimostrativo; la prova
// tools/prova-mac.sh le decodifica tutte con questi tipi.

import Foundation

// MARK: - decodifica tollerante

/// Un campo che non fa mai fallire chi lo contiene.
@propertyWrapper
struct Lax<T: Decodable>: Decodable {
    var wrappedValue: T?

    init(wrappedValue: T?) { self.wrappedValue = wrappedValue }

    init(from decoder: Decoder) throws {
        guard let c = try? decoder.singleValueContainer(), !c.decodeNil() else {
            wrappedValue = nil
            return
        }
        if let v = try? c.decode(T.self) {
            wrappedValue = v
            return
        }
        wrappedValue = Lax.convertito(c)
    }

    /// Gli scambi di tipo che il server fa davvero: 0/1 per i booleani, numeri come
    /// testo e viceversa.
    private static func convertito(_ c: SingleValueDecodingContainer) -> T? {
        if T.self == Int.self {
            if let d = try? c.decode(Double.self) { return Int(exactly: d.rounded()) as? T }
            if let b = try? c.decode(Bool.self) { return (b ? 1 : 0) as? T }
            if let s = try? c.decode(String.self) { return Int(s) as? T }
        } else if T.self == Double.self {
            if let s = try? c.decode(String.self) { return Double(s) as? T }
            if let b = try? c.decode(Bool.self) { return (b ? 1.0 : 0.0) as? T }
        } else if T.self == Bool.self {
            if let i = try? c.decode(Int.self) { return (i != 0) as? T }
            if let s = try? c.decode(String.self) {
                return ["1", "true", "si", "yes"].contains(s.lowercased()) as? T
            }
        } else if T.self == String.self {
            if let i = try? c.decode(Int.self) { return String(i) as? T }
            if let d = try? c.decode(Double.self) { return String(d) as? T }
            if let b = try? c.decode(Bool.self) { return String(b) as? T }
        }
        return nil
    }
}

extension Lax: Equatable where T: Equatable {
    static func == (a: Lax, b: Lax) -> Bool { a.wrappedValue == b.wrappedValue }
}

extension Lax: Hashable where T: Hashable {
    func hash(into h: inout Hasher) { h.combine(wrappedValue) }
}

/// Come `Lax`, per le liste: un elemento che non si decodifica (un `null`, un testo dove
/// serve un oggetto) sparisce e gli altri restano.
@propertyWrapper
struct LaxLista<E: Decodable>: Decodable {
    var wrappedValue: [E]?

    init(wrappedValue: [E]?) { self.wrappedValue = wrappedValue }

    init(from decoder: Decoder) throws {
        guard let c = try? decoder.singleValueContainer(), !c.decodeNil(),
              let v = try? c.decode([Elemento<E>].self) else {
            wrappedValue = nil
            return
        }
        wrappedValue = v.compactMap { $0.valore }
    }
}

extension LaxLista: Equatable where E: Equatable {
    static func == (a: LaxLista, b: LaxLista) -> Bool { a.wrappedValue == b.wrappedValue }
}

extension LaxLista: Hashable where E: Hashable {
    func hash(into h: inout Hasher) { h.combine(wrappedValue) }
}

extension KeyedDecodingContainer {
    /// Senza questi l'inizializzatore sintetizzato lancerebbe per una chiave mancante.
    func decode<T>(_ type: Lax<T>.Type, forKey key: Key) throws -> Lax<T> {
        if let v = try? decodeIfPresent(Lax<T>.self, forKey: key) { return v }
        return Lax(wrappedValue: nil)
    }

    func decode<E>(_ type: LaxLista<E>.Type, forKey key: Key) throws -> LaxLista<E> {
        if let v = try? decodeIfPresent(LaxLista<E>.self, forKey: key) { return v }
        return LaxLista(wrappedValue: nil)
    }
}

/// Un valore JSON qualunque, per i campi la cui forma non e' fissa.
enum JSONValue: Decodable, Hashable {
    case null
    case bool(Bool)
    case numero(Double)
    case testo(String)
    case lista([JSONValue])
    case oggetto([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .numero(v) }
        else if let v = try? c.decode(String.self) { self = .testo(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .lista(v) }
        else if let v = try? c.decode([String: JSONValue].self) { self = .oggetto(v) }
        else { self = .null }
    }

    var testo: String? {
        switch self {
        case .testo(let s): return s
        case .numero(let n): return n == n.rounded() ? String(Int(n)) : String(n)
        case .bool(let b): return String(b)
        default: return nil
        }
    }
    var intero: Int? { if case .numero(let n) = self { return Int(n) } else { return nil } }
    var isNull: Bool { if case .null = self { return true } else { return false } }
    subscript(chiave: String) -> JSONValue? {
        if case .oggetto(let d) = self { return d[chiave] } else { return nil }
    }
}

/// Un elemento di lista che, se non si decodifica, sparisce invece di rovinare la lista.
struct Elemento<T: Decodable>: Decodable {
    let valore: T?
    init(from decoder: Decoder) throws { valore = try? T(from: decoder) }
}

// MARK: - stato del server

struct StatoSync: Decodable, Hashable {
    @Lax var running: Bool?
    @Lax var message: String?
    @Lax var started: String?
    @Lax var result: JSONValue?
}

/// /api/status
struct Status: Decodable, Hashable {
    @Lax var sync: StatoSync?
    @Lax var ultimoSync: String?
    @Lax var sessioneViva: JSONValue?
    @Lax var ultimaVoce: String?
    @Lax var ultimaVoceDa: String?
}

/// /api/compartimenti
struct Compartimenti: Decodable, Hashable {
    @Lax var attivo: Bool?
    @LaxLista var elenco: [String]?
    @Lax var scelto: String?
    @Lax var predefinito: String?

    init() {}
    var attivi: Bool { (attivo ?? false) && !(elenco ?? []).isEmpty }
}

// MARK: - progetti

struct Progetto: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var key: String?
    @Lax var name: String?
    @Lax var kind: String?
    @Lax var status: String?
    @Lax var priority: Int?
    @Lax var pinned: Int?
    @Lax var summary: String?
    @Lax var nextAction: String?
    @Lax var auto: Int?
    @Lax var hidden: Int?
    @Lax var createdAt: String?
    @Lax var updatedAt: String?
    @Lax var lastActivity: String?
    @Lax var parentId: Int?
    @Lax var compartimento: String?
    // solo /api/overview
    @Lax var taskAperti: Int?
    @Lax var sessioni: Int?
    @Lax var token30g: Int?
    @Lax var repos: String?
    // solo /api/projects?albero=1
    @LaxLista var figli: [Progetto]?
    @Lax var eventi: Int?

    var identita: String { key ?? id.map { "p\($0)" } ?? "?" }
    var nome: String { name ?? key ?? "?" }
}

struct LinkProgetto: Decodable, Hashable {
    @Lax var kind: String?
    @Lax var value: String?
}

struct Repo: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var name: String?
    @Lax var description: String?
    @Lax var visibility: String?
    @Lax var url: String?
    @Lax var pushedAt: String?
    @Lax var projectId: Int?
    @Lax var localPath: String?
    @Lax var branch: String?
    @Lax var dirty: Int?
    @Lax var updatedAt: String?
}

struct Commit: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var repo: String?
    @Lax var sha: String?
    @Lax var message: String?
    @Lax var date: String?
    @Lax var url: String?
    @Lax var sessionId: String?
    @Lax var sessioneTitolo: String?
    var identita: String { sha ?? id.map(String.init) ?? "?" }
}

/// /api/projects/<chiave>
struct DettaglioProgetto: Decodable, Hashable {
    @Lax var progetto: Progetto?
    @LaxLista var link: [LinkProgetto]?
    @LaxLista var task: [Compito]?
    @LaxLista var post: [Post]?
    @LaxLista var sessioni: [Sessione]?
    @LaxLista var memoria: [Scheda]?
    @LaxLista var repo: [Repo]?
    @LaxLista var commit: [Commit]?
    @LaxLista var eventi: [Evento]?
}

// MARK: - task

/// Un task di Plancia (tabella tasks).
struct Compito: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var title: String?
    @Lax var body: String?
    @Lax var status: String?
    @Lax var priority: Int?
    @Lax var projectId: Int?
    @Lax var due: String?
    @Lax var tags: String?
    @Lax var source: String?
    @Lax var sessionId: String?
    @Lax var agent: String?
    @Lax var prompt: String?
    @Lax var cwd: String?
    @Lax var runId: Int?
    @Lax var createdAt: String?
    @Lax var updatedAt: String?
    @Lax var doneAt: String?
    @Lax var host: String?
    @Lax var compartimento: String?
    @Lax var project: String?
    @Lax var projectKey: String?
    var identita: String { id.map(String.init) ?? "?" }
}

/// Una riga della lavagna: i task di Plancia, di Claude Code e di Codex insieme.
struct VoceLavagna: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var fonte: String?
    @Lax var chiave: String?
    @Lax var titolo: String?
    @Lax var dettaglio: String?
    @Lax var stato: String?
    @Lax var statoOrigine: String?
    @Lax var agente: String?
    @Lax var sessione: String?
    @Lax var projectId: Int?
    @Lax var taskId: Int?
    @Lax var creatoAt: String?
    @Lax var aggiornatoAt: String?
    @Lax var vistoAt: String?
    @Lax var progetto: String?
    @Lax var progettoChiave: String?
    var identita: String { "\(fonte ?? "?")-\(id ?? 0)-\(chiave ?? "")" }
}

/// /api/lavagna
struct Lavagna: Decodable, Hashable {
    @LaxLista var voci: [VoceLavagna]?
    /// fonte -> { stato -> quanti }, come JSON libero ("aperti" e' la somma di quelli non chiusi)
    @Lax var conteggi: [String: JSONValue]?
    @Lax var inCorso: Int?

    /// Quanti task aperti in tutto.
    var aperti: Int {
        (conteggi ?? [:]).values.reduce(0) { $0 + (Int($1["aperti"]?.testo ?? "") ?? 0) }
    }
}

// MARK: - social

struct Post: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var platform: String?
    @Lax var status: String?
    @Lax var text: String?
    @Lax var url: String?
    @Lax var projectId: Int?
    @Lax var sourceRef: String?
    @Lax var scheduledFor: String?
    @Lax var publishedAt: String?
    @Lax var createdAt: String?
    @Lax var updatedAt: String?
    @Lax var media: String?
    @Lax var compartimento: String?
    @Lax var project: String?
    @Lax var projectKey: String?
    var identita: String { id.map(String.init) ?? "?" }
}

// MARK: - sessioni ed eventi

/// Una sessione di Claude Code o di Codex. /api/sessions porta tutti i campi;
/// gli elenchi dentro overview e project_detail solo alcuni.
struct Sessione: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var sessionId: String?
    @Lax var projectId: Int?
    @Lax var cwd: String?
    @Lax var gitBranch: String?
    @Lax var title: String?
    @Lax var firstPrompt: String?
    @Lax var prompt: String?
    @Lax var startedAt: String?
    @Lax var endedAt: String?
    @Lax var nUser: Int?
    @Lax var nAssistant: Int?
    @Lax var nTools: Int?
    @Lax var models: String?
    @Lax var inTokens: Int?
    @Lax var outTokens: Int?
    @Lax var agent: String?
    @Lax var scambi: Int?
    @Lax var progetto: String?
    @Lax var projectKey: String?
    var identita: String { sessionId ?? id.map(String.init) ?? "?" }
}

/// Un evento della cronologia (tabella events, /api/events).
struct Evento: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var ts: String?
    @Lax var kind: String?
    @Lax var title: String?
    @Lax var detail: String?
    @Lax var projectId: Int?
    @Lax var ref: String?
    @Lax var source: String?
    @Lax var progetto: String?
    @Lax var projectKey: String?
    var identita: String { id.map(String.init) ?? "?" }
}

/// Una riga del registro eventi (eventi.jsonl, /api/eventi).
struct EventoRegistro: Decodable, Hashable {
    @Lax var schema: String?
    @Lax var id: String?
    @Lax var ts: String?
    @Lax var tipo: String?
    @Lax var titolo: String?
    @Lax var progetto: String?
    @Lax var origine: String?
    @Lax var dati: JSONValue?
    var identita: String { id ?? "\(ts ?? "")-\(titolo ?? "")" }
}

struct StatoRegistro: Decodable, Hashable {
    @Lax var schema: String?
    @Lax var eventi: Int?
    @Lax var byte: Int?
    @LaxLista var tipi: [String]?
}

/// /api/eventi
struct Registro: Decodable, Hashable {
    @LaxLista var eventi: [EventoRegistro]?
    @Lax var stato: StatoRegistro?
}

// MARK: - memoria

/// Una scheda di memoria (/api/knowledge senza nome).
struct Scheda: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var name: String?
    @Lax var description: String?
    @Lax var type: String?
    @Lax var updatedAt: String?
    /// JSON come testo, es. "[\"altra-memoria\"]"
    @Lax var links: String?
    @Lax var progetto: String?
    @Lax var projectKey: String?
    // solo /api/knowledge?name=
    @Lax var body: String?
    @Lax var path: String?
    var identita: String { name ?? id.map(String.init) ?? "?" }

    /// I nomi delle memorie a cui questa rimanda.
    var legami: [String] {
        guard let d = links?.data(using: .utf8),
              let a = try? JSONDecoder().decode([String].self, from: d) else { return [] }
        return a
    }
}

struct NodoMemoria: Decodable, Hashable {
    @Lax var nome: String?
    @Lax var tipo: String?
    @Lax var descrizione: String?
    @Lax var aggiornata: String?
    @Lax var peso: Int?
    @Lax var path: String?
    @Lax var grado: Int?
    @LaxLista var cartelle: [String]?
    @LaxLista var dove: [String]?
    @Lax var richiamabile: Bool?
    @Lax var x: Double?
    @Lax var y: Double?
    var identita: String { nome ?? "?" }
}

struct ArcoMemoria: Decodable, Hashable {
    @Lax var da: String?
    @Lax var a: String?
}

struct LegameRotto: Decodable, Hashable {
    @Lax var da: String?
    @Lax var verso: String?
}

struct DoppiaMemoria: Decodable, Hashable {
    @Lax var nome: String?
    @LaxLista var cartelle: [String]?
}

struct CartellaMemoria: Decodable, Hashable {
    @Lax var nome: String?
    @Lax var quante: Int?
}

struct DiagnosiMemoria: Decodable, Hashable {
    @Lax var totale: Int?
    @Lax var richiamabili: Int?
    @LaxLista var doppie: [DoppiaMemoria]?
    @LaxLista var orfane: [String]?
    @LaxLista var rotti: [LegameRotto]?
    @LaxLista var daScrivere: [String]?
    @LaxLista var vuote: [String]?
    @LaxLista var cartelle: [CartellaMemoria]?
}

/// /api/memoria/mappa
struct MappaMemoria: Decodable, Hashable {
    @LaxLista var nodi: [NodoMemoria]?
    @LaxLista var archi: [ArcoMemoria]?
    @Lax var diagnosi: DiagnosiMemoria?
}

struct VoceProva: Decodable, Hashable {
    @Lax var nome: String?
    @Lax var tipo: String?
    @Lax var descrizione: String?
    @Lax var punteggio: Double?
    var identita: String { nome ?? "?" }
}

/// /api/memoria/prova?q=
struct ProvaMemoria: Decodable, Hashable {
    @LaxLista var termini: [String]?
    @Lax var corta: Bool?
    @Lax var soglia: Double?
    @LaxLista var presi: [VoceProva]?
    @LaxLista var scartati: [VoceProva]?
}

// MARK: - oggi

struct RigaProssimo: Decodable, Hashable {
    @Lax var key: String?
    @Lax var name: String?
    @Lax var area: String?
    @Lax var cosa: String?
    @Lax var fonte: String?
    @Lax var taskId: Int?
    @Lax var scadenza: String?
    @Lax var ultimaAttivita: String?
    var identita: String { "\(key ?? "?")-\(taskId ?? 0)" }
}

struct AreaProssimi: Decodable, Hashable {
    @Lax var key: String?
    @Lax var name: String?
    @LaxLista var righe: [RigaProssimo]?
    var identita: String { key ?? name ?? "?" }
}

/// /api/prossimi
struct Prossimi: Decodable, Hashable {
    @LaxLista var aree: [AreaProssimi]?
    @LaxLista var senzaArea: [RigaProssimo]?
}

struct AzioneProposta: Decodable, Hashable {
    @Lax var tipo: String?
    @Lax var run: Int?
    @Lax var titolo: String?
    @Lax var progetto: String?
    @Lax var modo: String?
}

/// /api/proposte
struct Proposta: Decodable, Hashable {
    @Lax var id: String?
    @Lax var testo: String?
    @Lax var motivo: String?
    @Lax var urgenza: Int?
    @Lax var azione: AzioneProposta?
    var identita: String { id ?? testo ?? "?" }
}

/// /api/recap?solo_cache=1
struct Recap: Decodable, Hashable {
    @Lax var giorno: String?
    @Lax var lingua: String?
    @Lax var testo: String?
    @Lax var fonte: String?
    @Lax var fresco: Bool?
    @Lax var daCache: Bool?
}

/// Un lancio in background (/api/runs)
struct Lancio: Decodable, Hashable {
    @Lax var id: Int?
    @Lax var taskId: Int?
    @Lax var agente: String?
    @Lax var modo: String?
    @Lax var prompt: String?
    @Lax var cwd: String?
    @Lax var stato: String?
    @Lax var inizio: String?
    @Lax var fine: String?
    @Lax var esito: String?
    @Lax var token: Int?
    @Lax var costo: Double?
    @Lax var task: String?
    var identita: String { id.map(String.init) ?? "?" }
}

// MARK: - riepilogo (overview)

struct IndiceRicerca: Decodable, Hashable {
    @Lax var turni: Int?
    @Lax var file: Int?
    @Lax var testoMb: Double?
}

struct Statistiche: Decodable, Hashable {
    @Lax var progettiAttivi: Int?
    @Lax var taskAperti: Int?
    @Lax var taskScaduti: Int?
    @Lax var sessioniTotali: Int?
    @Lax var sessioniSettimana: Int?
    @Lax var commitMese: Int?
    @Lax var postPubblicati: Int?
    @Lax var postInCoda: Int?
    @Lax var memorie: Int?
    @Lax var scambi: Int?
    @Lax var tokenOutMese: Int?
    @Lax var fuga: JSONValue?
    @Lax var lavagnaAperti: Int?
    @Lax var indice: IndiceRicerca?
}

struct AgenteRiga: Decodable, Hashable {
    @Lax var agente: String?
    @Lax var sessioni: Int?
    @Lax var token: Int?
    @Lax var tool: Int?
    @Lax var scambiTuoi: Int?
    @Lax var ultimo: String?
}

struct GiornoAttivita: Decodable, Hashable {
    @Lax var giorno: String?
    @Lax var sessioni: Int?
    @Lax var claude: Int?
    @Lax var codex: Int?
    @Lax var commit: Int?
}

/// /api/overview
struct Overview: Decodable, Hashable {
    @Lax var stats: Statistiche?
    @LaxLista var proposte: [Proposta]?
    @Lax var benvenuto: Bool?
    @LaxLista var agenti: [AgenteRiga]?
    @LaxLista var progetti: [Progetto]?
    @LaxLista var task: [Compito]?
    @LaxLista var post: [Post]?
    @LaxLista var eventi: [Evento]?
    @LaxLista var attivita: [GiornoAttivita]?
    @LaxLista var sessioniRecenti: [Sessione]?
    @Lax var ultimoSync: String?
    @Lax var sync: StatoSync?
}

// MARK: - ricerca

struct TurnoTrovato: Decodable, Hashable {
    @Lax var sessione: String?
    @Lax var ruolo: String?
    @Lax var ts: String?
    @Lax var progetto: String?
    @Lax var percorso: String?
    @Lax var riga: Int?
    @Lax var frammento: String?
    var identita: String { "\(sessione ?? "")-\(riga ?? 0)-\(ts ?? "")" }
}

struct GruppoProgetto: Decodable, Hashable {
    @Lax var progetto: String?
    @Lax var turni: Int?
}

struct SchedaTrovata: Decodable, Hashable {
    @Lax var kind: String?
    @Lax var refId: Int?
    @Lax var title: String?
    @Lax var project: String?
    @Lax var ts: String?
    @Lax var snip: String?
    var identita: String { "\(kind ?? "?")-\(refId ?? 0)" }
}

/// /api/search?q=
struct RisultatiRicerca: Decodable, Hashable {
    @LaxLista var turni: [TurnoTrovato]?
    @LaxLista var progetti: [GruppoProgetto]?
    @LaxLista var schede: [SchedaTrovata]?
}
