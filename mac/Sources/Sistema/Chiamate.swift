// Le chiamate al backend che usano il pannello vocale e Jarvis. Le viste native
// non passano da qui: usano il Cliente (Core/Cliente.swift).

import Foundation

// MARK: - chiamate al backend

enum API {
    static func request(_ path: String, method: String = "GET", body: [String: Any]? = nil,
                        timeout: TimeInterval = 180,
                        done: @escaping ([String: Any]?, String?) -> Void) {
        guard let url = URL(string: Conf.base + path) else { return done(nil, "url non valida") }
        var req = URLRequest(url: url, timeoutInterval: timeout)
        req.httpMethod = method
        req.setValue(Conf.token, forHTTPHeaderField: "X-Plancia-Token")
        if let body = body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        // Il registro non deve riempirsi di niente: il pannello vocale chiede
        // gli eventi ogni sei secondi, e sarebbero milleduecento righe l'ora.
        let silenzioso = path.hasPrefix("/api/eventi")
        if !silenzioso { Log.write("richiesta \(method) \(path)") }
        URLSession.shared.dataTask(with: req) { data, res, err in
            if let err = err {
                Log.write("errore \(path): \(err.localizedDescription)")
                return DispatchQueue.main.async { done(nil, err.localizedDescription) }
            }
            let code = (res as? HTTPURLResponse)?.statusCode ?? 0
            let j = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
            if !silenzioso { Log.write("risposta \(path): \(code)") }
            DispatchQueue.main.async { done(j, j?["errore"] as? String) }
        }.resume()
    }

    /// Come `request`, ma per le rotte che tornano una lista invece di un
    /// oggetto: `/api/projects`, `/api/runs`.
    static func lista(_ path: String, timeout: TimeInterval = 20,
                      done: @escaping ([[String: Any]]) -> Void) {
        guard let url = URL(string: Conf.base + path) else { return done([]) }
        var req = URLRequest(url: url, timeoutInterval: timeout)
        req.setValue(Conf.token, forHTTPHeaderField: "X-Plancia-Token")
        URLSession.shared.dataTask(with: req) { data, _, _ in
            let j = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [[String: Any]]
            DispatchQueue.main.async { done(j ?? []) }
        }.resume()
    }

    static func alive(_ done: @escaping (Bool) -> Void) {
        guard let url = URL(string: Conf.base + "/api/status") else { return done(false) }
        var req = URLRequest(url: url, timeoutInterval: 2)
        req.httpMethod = "GET"
        URLSession.shared.dataTask(with: req) { data, res, _ in
            let ok = (res as? HTTPURLResponse)?.statusCode == 200 && data != nil
            DispatchQueue.main.async { done(ok) }
        }.resume()
    }
}
