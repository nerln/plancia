// Il cliente del server locale. Parla solo con 127.0.0.1, alla porta scritta in
// $PLANCIA_HOME/config.json (senza: ~/.plancia). Le letture non portano il token,
// le scritture mandano X-Plancia-Token letto da $PLANCIA_HOME/token, solo in lettura:
// il file non viene mai creato ne' cambiato da qui, e il token non esce da 127.0.0.1.

import Foundation

// MARK: - la casa dei dati

enum Casa {
    /// `$PLANCIA_HOME` se c'e', altrimenti `~/.plancia`.
    static var dir: URL {
        if let p = ProcessInfo.processInfo.environment["PLANCIA_HOME"], !p.isEmpty {
            return URL(fileURLWithPath: (p as NSString).expandingTildeInPath)
        }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".plancia")
    }

    static var config: [String: Any] {
        guard let d = try? Data(contentsOf: dir.appendingPathComponent("config.json")),
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
        (try? String(contentsOf: dir.appendingPathComponent("token"), encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
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

// MARK: - il cliente

actor Cliente {
    static let condiviso = Cliente()

    private let sessione: URLSession
    private let decodificatore: JSONDecoder

    init() {
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 8
        conf.timeoutIntervalForResource = 60
        conf.waitsForConnectivity = false
        conf.httpMaximumConnectionsPerHost = 6
        conf.requestCachePolicy = .reloadIgnoringLocalCacheData
        sessione = URLSession(configuration: conf)
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        decodificatore = d
    }

    // MARK: richieste

    private func url(_ percorso: String, _ query: [String: String], _ compartimento: String?) throws -> URL {
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

    private func esegui(_ req: URLRequest) async throws -> Data {
        do {
            let (dati, risposta) = try await sessione.data(for: req)
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
        } catch let e as URLError where e.code == .cancelled {
            throw CancellationError()
        } catch let e as URLError {
            throw ErroreCliente.nonRaggiungibile(e.localizedDescription)
        }
    }

    /// GET che torna un oggetto.
    func ottieni<T: Decodable>(_ tipo: T.Type, _ percorso: String, query: [String: String] = [:],
                               compartimento: String? = nil, timeout: TimeInterval = 8) async throws -> T {
        var req = URLRequest(url: try url(percorso, query, compartimento), timeoutInterval: timeout)
        req.httpMethod = "GET"
        let dati = try await esegui(req)
        do { return try decodificatore.decode(T.self, from: dati) }
        catch { throw ErroreCliente.decodifica("\(percorso): \(error.localizedDescription)") }
    }

    /// GET che torna una lista. Un elemento che non si decodifica sparisce, la lista resta.
    func elenco<T: Decodable>(_ tipo: T.Type, _ percorso: String, query: [String: String] = [:],
                              compartimento: String? = nil, timeout: TimeInterval = 8) async throws -> [T] {
        let v = try await ottieni([Elemento<T>].self, percorso, query: query,
                                  compartimento: compartimento, timeout: timeout)
        return v.compactMap { $0.valore }
    }

    /// GET che torna testo (il briefing e' Markdown).
    func testo(_ percorso: String, query: [String: String] = [:], compartimento: String? = nil) async throws -> String {
        var req = URLRequest(url: try url(percorso, query, compartimento), timeoutInterval: 8)
        req.httpMethod = "GET"
        let dati = try await esegui(req)
        return String(data: dati, encoding: .utf8) ?? ""
    }

    /// POST, PATCH o DELETE. Porta il token. Torna la risposta come JSON libero.
    @discardableResult
    func scrivi(_ metodo: String, _ percorso: String, corpo: [String: Any]? = nil,
                query: [String: String] = [:], compartimento: String? = nil,
                timeout: TimeInterval = 30) async throws -> JSONValue {
        var req = URLRequest(url: try url(percorso, query, compartimento), timeoutInterval: timeout)
        req.httpMethod = metodo
        req.setValue(Casa.token, forHTTPHeaderField: "X-Plancia-Token")
        if let corpo = corpo {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: corpo)
        }
        let dati = try await esegui(req)
        return (try? decodificatore.decode(JSONValue.self, from: dati)) ?? .null
    }

    /// Il server risponde?
    func vivo() async -> Bool {
        do {
            _ = try await ottieni(Status.self, "/api/status", timeout: 2)
            return true
        } catch { return false }
    }
}
