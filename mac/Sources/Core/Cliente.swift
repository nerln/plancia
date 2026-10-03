// Il cliente del server locale. Parla solo con 127.0.0.1, alla porta scritta in
// $PLANCIA_HOME/config.json (senza: ~/.plancia). Le letture non portano il token,
// le scritture mandano X-Plancia-Token letto da $PLANCIA_HOME/token, solo in lettura:
// il file non viene mai creato ne' cambiato da qui, e il token non esce da 127.0.0.1.
//
// Come lavora (la velocita' dell'app sta qui sotto):
//  - la rete e la decodifica non toccano mai il thread principale: la richiesta corre in un
//    Task staccato e il JSON si decodifica in un altro, fuori dall'actor, cosi' piu' letture
//    decodificano insieme invece di mettersi in fila dietro l'actor;
//  - due letture identiche insieme (stesso indirizzo) fanno UNA richiesta sola, e il
//    risultato va a tutte e due;
//  - se chi aspetta viene annullato (l'utente ha cambiato sezione, la parola cercata e'
//    cambiata) e non aspetta piu' nessuno, la richiesta in volo si interrompe davvero;
//  - chi legge puo' dire "l'ultima volta ho avuto la risposta con questa impronta": se il
//    server manda gli stessi identici byte, la decodifica non si fa nemmeno e lo Store non
//    riassegna niente (`Lettura.invariata`).

import Foundation

// MARK: - la casa dei dati

/// Un file piccolo riletto solo quando cambia (data di modifica e dimensione): la porta e
/// il token servono a ogni richiesta, e leggerli da disco ogni volta era lavoro per niente.
private final class FileInCache: @unchecked Sendable {
    private let l = NSLock()
    private var chiave: (Date?, Int)?
    private var dati: Data?

    func leggi(_ url: URL) -> Data? {
        let attr = try? url.resourceValues(forKeys: [.contentModificationDateKey, .fileSizeKey])
        let k = (attr?.contentModificationDate, attr?.fileSize ?? -1)
        l.lock(); defer { l.unlock() }
        if let c = chiave, c.0 == k.0, c.1 == k.1, k.0 != nil { return dati }
        let d = try? Data(contentsOf: url)
        chiave = (d == nil ? nil : k)
        dati = d
        return d
    }
}

enum Casa {
    private static let fileConfig = FileInCache()
    private static let fileToken = FileInCache()

    /// `$PLANCIA_HOME` se c'e', altrimenti `~/.plancia`.
    static var dir: URL {
        if let p = ProcessInfo.processInfo.environment["PLANCIA_HOME"], !p.isEmpty {
            return URL(fileURLWithPath: (p as NSString).expandingTildeInPath)
        }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".plancia")
    }

    static var config: [String: Any] {
        guard let d = fileConfig.leggi(dir.appendingPathComponent("config.json")),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        return j
    }

    static var porta: Int {
        let v = config["port"]
        if let i = v as? Int { return i }
        if let s = v as? String, let i = Int(s) { return i }
        return 7773
    }

    static var token: String {
        guard let d = fileToken.leggi(dir.appendingPathComponent("token")),
              let s = String(data: d, encoding: .utf8) else { return "" }
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static var base: String { "http://127.0.0.1:\(porta)" }
}

// MARK: - errori

enum ErroreCliente: Error, LocalizedError {
    /// Il server non risponde (spento, porta sbagliata, tempo scaduto).
    case nonRaggiungibile(String)
    /// Ha risposto con un errore; il testo e' quello del server.
    case http(Int, String)
    /// La risposta non e' JSON o non ha la forma attesa.
    case decodifica(String)

    var errorDescription: String? {
        switch self {
        case .nonRaggiungibile(let s): return s
        case .http(let c, let s): return s.isEmpty ? "HTTP \(c)" : s
        case .decodifica(let s): return s
        }
    }

    var eNonRaggiungibile: Bool { if case .nonRaggiungibile = self { return true } else { return false } }
}

// MARK: - contatori

/// Quante richieste ha fatto il cliente, quanti byte ha scaricato, quante ne ha in volo.
/// Servono alla misura (Sistema/Misura.swift) e alle prove; costano un lucchetto per richiesta.
final class ContatoriRete: @unchecked Sendable {
    private let l = NSLock()
    private var _richieste = 0, _byte = 0, _inVolo = 0, _picco = 0

    func inizia() {
        l.lock(); _richieste += 1; _inVolo += 1; _picco = max(_picco, _inVolo); l.unlock()
    }
    func finisce(byte: Int) {
        l.lock(); _inVolo -= 1; _byte += byte; l.unlock()
    }
    var richieste: Int { l.lock(); defer { l.unlock() }; return _richieste }
    var byte: Int { l.lock(); defer { l.unlock() }; return _byte }
    var inVolo: Int { l.lock(); defer { l.unlock() }; return _inVolo }
    var picco: Int { l.lock(); defer { l.unlock() }; return _picco }
}

// MARK: - lettura con impronta

/// L'esito di una lettura che conosceva gia' l'impronta dell'ultima risposta.
enum Lettura<T> {
    /// Gli stessi byte di prima: niente da decodificare, niente da riassegnare.
    case invariata
    /// Una risposta nuova, con la sua impronta da ricordare per la volta dopo.
    case nuova(T, impronta: Int)
}

// MARK: - il cliente

actor Cliente {
    static let condiviso = Cliente()
    nonisolated static let contatori = ContatoriRete()

    private let sessione: URLSession

    /// Una lettura in volo, condivisa da chi la chiede insieme.
    private struct Volo {
        let id: Int
        let task: Task<Data, Error>
        var attese: Int
    }
    private var voli: [String: Volo] = [:]
    private var prossimoId = 0

    init() {
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 8
        conf.timeoutIntervalForResource = 60
        conf.waitsForConnectivity = false
        conf.httpMaximumConnectionsPerHost = 6
        conf.requestCachePolicy = .reloadIgnoringLocalCacheData
        sessione = URLSession(configuration: conf)
    }

    // MARK: richieste

    private nonisolated static func url(_ percorso: String, _ query: [String: String], _ compartimento: String?) throws -> URL {
        var c = URLComponents()
        c.scheme = "http"
        c.host = "127.0.0.1"
        c.port = Casa.porta
        c.path = percorso
        var voci = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        if let comp = compartimento, !comp.isEmpty { voci.append(URLQueryItem(name: "compartimento", value: comp)) }
        if !voci.isEmpty { c.queryItems = voci }
        guard let u = c.url else { throw ErroreCliente.decodifica("indirizzo non valido: \(percorso)") }
        return u
    }

    /// La richiesta vera, senza stato: gira dove la chiama chi ha in mano la sessione.
    private nonisolated static func rete(_ sessione: URLSession, _ req: URLRequest) async throws -> Data {
        Cliente.contatori.inizia()
        var scaricati = 0
        defer { Cliente.contatori.finisce(byte: scaricati) }
        do {
            let (dati, risposta) = try await sessione.data(for: req)
            scaricati = dati.count
            let codice = (risposta as? HTTPURLResponse)?.statusCode ?? 0
            if !(200..<300).contains(codice) {
                var messaggio = ""
                if let j = try? JSONSerialization.jsonObject(with: dati) as? [String: Any] {
                    messaggio = (j["errore"] as? String) ?? ""
                }
                throw ErroreCliente.http(codice, messaggio)
            }
            return dati
        } catch let e as ErroreCliente {
            throw e
        } catch is CancellationError {
            throw CancellationError()
        } catch let e as URLError where e.code == .cancelled {
            throw CancellationError()
        } catch let e as URLError {
            throw ErroreCliente.nonRaggiungibile(e.localizedDescription)
        }
    }

    /// Una GET. Se un'altra uguale e' gia' in volo, si aspetta quella. Chi aspetta e viene
    /// annullato rinuncia; l'ultimo che rinuncia interrompe la richiesta.
    private func scarica(_ req: URLRequest) async throws -> Data {
        let chiave = req.url?.absoluteString ?? ""
        if var v = voli[chiave] {
            v.attese += 1
            voli[chiave] = v
            return try await attendi(chiave, v)
        }
        prossimoId += 1
        let id = prossimoId
        let sess = sessione
        let task = Task.detached(priority: .userInitiated) { [weak self] () -> Data in
            do {
                let d = try await Cliente.rete(sess, req)
                await self?.terminato(chiave, id)
                return d
            } catch {
                await self?.terminato(chiave, id)
                throw error
            }
        }
        let v = Volo(id: id, task: task, attese: 1)
        voli[chiave] = v
        return try await attendi(chiave, v)
    }

    private func attendi(_ chiave: String, _ v: Volo) async throws -> Data {
        try await withTaskCancellationHandler {
            try await v.task.value
        } onCancel: {
            Task { await self.rinuncia(chiave, v.id) }
        }
    }

    private func rinuncia(_ chiave: String, _ id: Int) {
        guard var v = voli[chiave], v.id == id else { return }
        v.attese -= 1
        if v.attese <= 0 {
            v.task.cancel()
            voli[chiave] = nil
        } else {
            voli[chiave] = v
        }
    }

    private func terminato(_ chiave: String, _ id: Int) {
        if voli[chiave]?.id == id { voli[chiave] = nil }
    }

    // MARK: decodifica (fuori dall'actor e fuori dal thread principale)

    private nonisolated static func impronta(_ d: Data) -> Int {
        var h = Hasher()
        d.withUnsafeBytes { h.combine(bytes: $0) }
        h.combine(d.count)
        return h.finalize()
    }

    private nonisolated static func decodifica<T: Decodable>(_ tipo: T.Type, _ dati: Data, _ percorso: String) throws -> T {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        do { return try d.decode(T.self, from: dati) }
        catch { throw ErroreCliente.decodifica("\(percorso): \(error.localizedDescription)") }
    }

    private nonisolated func richiestaGET(_ percorso: String, _ query: [String: String],
                                           _ compartimento: String?, _ timeout: TimeInterval) throws -> URLRequest {
        var req = URLRequest(url: try Cliente.url(percorso, query, compartimento), timeoutInterval: timeout)
        req.httpMethod = "GET"
        return req
    }

    /// GET che torna un oggetto, o `.invariata` se la risposta ha la stessa impronta di `nota`.
    nonisolated func leggi<T: Decodable>(_ tipo: T.Type, _ percorso: String, query: [String: String] = [:],
                                         compartimento: String? = nil, timeout: TimeInterval = 8,
                                         nota: Int? = nil) async throws -> Lettura<T> {
        let req = try richiestaGET(percorso, query, compartimento, timeout)
        let dati = try await scarica(req)
        return try await Task.detached(priority: .userInitiated) { () -> Lettura<T> in
            let imp = Cliente.impronta(dati)
            if let n = nota, n == imp { return .invariata }
            return .nuova(try Cliente.decodifica(T.self, dati, percorso), impronta: imp)
        }.value
    }

    /// GET che torna una lista, o `.invariata`. Un elemento che non si decodifica sparisce.
    nonisolated func leggiElenco<T: Decodable>(_ tipo: T.Type, _ percorso: String, query: [String: String] = [:],
                                               compartimento: String? = nil, timeout: TimeInterval = 8,
                                               nota: Int? = nil) async throws -> Lettura<[T]> {
        let req = try richiestaGET(percorso, query, compartimento, timeout)
        let dati = try await scarica(req)
        return try await Task.detached(priority: .userInitiated) { () -> Lettura<[T]> in
            let imp = Cliente.impronta(dati)
            if let n = nota, n == imp { return .invariata }
            let v = try Cliente.decodifica([Elemento<T>].self, dati, percorso)
            return .nuova(v.compactMap { $0.valore }, impronta: imp)
        }.value
    }

    /// GET che torna un oggetto.
    nonisolated func ottieni<T: Decodable>(_ tipo: T.Type, _ percorso: String, query: [String: String] = [:],
                                           compartimento: String? = nil, timeout: TimeInterval = 8) async throws -> T {
        let r = try await leggi(tipo, percorso, query: query, compartimento: compartimento, timeout: timeout)
        if case .nuova(let v, _) = r { return v }
        throw ErroreCliente.decodifica("\(percorso): risposta vuota")
    }

    /// GET che torna una lista. Un elemento che non si decodifica sparisce, la lista resta.
    nonisolated func elenco<T: Decodable>(_ tipo: T.Type, _ percorso: String, query: [String: String] = [:],
                                          compartimento: String? = nil, timeout: TimeInterval = 8) async throws -> [T] {
        let r = try await leggiElenco(tipo, percorso, query: query, compartimento: compartimento, timeout: timeout)
        if case .nuova(let v, _) = r { return v }
        return []
    }

    /// GET che torna testo (il briefing e' Markdown).
    nonisolated func testo(_ percorso: String, query: [String: String] = [:], compartimento: String? = nil) async throws -> String {
        let req = try richiestaGET(percorso, query, compartimento, 8)
        let dati = try await scarica(req)
        return String(data: dati, encoding: .utf8) ?? ""
    }

    /// POST, PATCH o DELETE. Porta il token. Torna la risposta come JSON libero.
    @discardableResult
    nonisolated func scrivi(_ metodo: String, _ percorso: String, corpo: [String: Any]? = nil,
                            query: [String: String] = [:], compartimento: String? = nil,
                            timeout: TimeInterval = 30) async throws -> JSONValue {
        var req = URLRequest(url: try Cliente.url(percorso, query, compartimento), timeoutInterval: timeout)
        req.httpMethod = metodo
        req.setValue(Casa.token, forHTTPHeaderField: "X-Plancia-Token")
        if let corpo = corpo {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: corpo)
        }
        let dati = try await Cliente.rete(sessione, req)
        return (try? Cliente.decodificatoreLibero().decode(JSONValue.self, from: dati)) ?? .null
    }

    private nonisolated static func decodificatoreLibero() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    /// Il server risponde?
    func vivo() async -> Bool {
        do {
            _ = try await ottieni(Status.self, "/api/status", timeout: 2)
            return true
        } catch { return false }
    }
}
