// Jarvis parla col server locale (127.0.0.1) e con nessun altro.
//
// Il percorso e' quello sicuro di plancia/jarvis.py:
//   POST /api/jarvis/capisci    una frase dentro, righe JSON fuori man mano (testo che scorre,
//                               frasi intere per la voce, e alla fine l'esito con la scheda
//                               dell'eventuale proposta)
//   POST /api/jarvis/conferma   l'UNICA porta da cui parte qualcosa che scrive o avvia un agente;
//                               la chiama il pulsante Conferma e nient'altro in questo programma
//   POST /api/jarvis/rifiuta    butta la scheda
//   POST /api/jarvis/ferma      Esc: il server smette di pensare
//   POST /api/jarvis/pronto     scalda il modello (in sola lettura) e Kokoro, e dice che voce
//                               neurale c'e'
//   POST /api/voice/speak       una frase in un file audio, con il motore "neurale" (Kokoro,
//                               Pocket o Voicebox, in quest'ordine; mai la voce robotica del server)

import Foundation

// MARK: - forme

struct PropostaJarvis: Identifiable, Equatable, Sendable {
    struct Riga: Equatable, Sendable { let chiave: String; let valore: String }
    let id: String
    let azione: String
    let titolo: String
    let righe: [Riga]
    /// "scrive" (cambia l'archivio), "lancia" (parte un agente in sola lettura),
    /// "lancia_scrive" (parte un agente che puo' modificare file), "legge".
    let rischio: String
    let avviso: String

    init(id: String, azione: String, titolo: String, righe: [Riga], rischio: String, avviso: String) {
        self.id = id; self.azione = azione; self.titolo = titolo
        self.righe = righe; self.rischio = rischio; self.avviso = avviso
    }

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String, !id.isEmpty else { return nil }
        self.id = id
        azione = (d["azione"] as? String) ?? ""
        titolo = (d["titolo"] as? String) ?? ""
        righe = ((d["righe"] as? [[String: Any]]) ?? []).compactMap { r in
            guard let k = r["k"] as? String, let v = r["v"] as? String else { return nil }
            return Riga(chiave: k, valore: v)
        }
        rischio = (d["rischio"] as? String) ?? "scrive"
        avviso = (d["avviso"] as? String) ?? ""
    }
}

struct AzioneJarvis: Equatable, Sendable {
    let tipo: String
    let vista: String?
    let chiave: String?
    let passo: Double?

    init?(_ d: [String: Any]?) {
        guard let d = d, let t = d["tipo"] as? String else { return nil }
        tipo = t
        vista = d["vista"] as? String
        chiave = d["chiave"] as? String
        passo = d["passo"] as? Double
    }
}

struct EsitoJarvis: Sendable {
    var tipo: String
    var risposta: String
    var daDire: String
    var proposta: PropostaJarvis?
    var azione: AzioneJarvis?
    var muto: Bool
    var eseguita: Bool?

    init(_ d: [String: Any]) {
        tipo = (d["tipo"] as? String) ?? ""
        risposta = (d["risposta"] as? String) ?? ""
        daDire = (d["da_dire"] as? String) ?? risposta
        proposta = (d["proposta"] as? [String: Any]).flatMap(PropostaJarvis.init)
        azione = AzioneJarvis(d["azione"] as? [String: Any])
        muto = (d["muto"] as? Bool) ?? false
        eseguita = d["eseguita"] as? Bool
    }

    init(tipo: String, risposta: String) {
        self.tipo = tipo; self.risposta = risposta; daDire = risposta
        proposta = nil; azione = nil; muto = false; eseguita = nil
    }
}

struct EventoJarvis: Sendable {
    /// "stato", "testo", "frase" o "fine"
    var tipo: String
    var testo: String = ""
    var dire: String = ""
    var esito: EsitoJarvis?
}

struct InfoVoceServer: Sendable {
    /// "kokoro", "pocket", "voicebox" o nil quando nessuna voce neurale locale risponde
    var neurale: String?
    /// Perche' Kokoro non parla, se non parla: "non_installato", "in_pausa", "spento",
    /// "senza_voce". nil se parla, o se il server non lo dice.
    var kokoroNo: String?
}

/// Una frase sintetizzata: il file, chi l'ha fatta, e se un motore piu' in alto ha ceduto.
struct FraseSintetizzata: Sendable {
    var url: URL?
    /// "kokoro", "pocket", "voicebox" o "cache"
    var motore: String?
    /// C'e' un testo del server quando un motore piu' in alto non ha risposto.
    var ripiego: String?
}

enum ErroreJarvis: Error, LocalizedError {
    case nonRaggiungibile
    case senzaToken
    case http(Int, String)

    var errorDescription: String? {
        switch self {
        case .senzaToken:
            return Lingua.risolvi() == "it"
                ? "Manca il token di Plancia. Apri la finestra di Plancia una volta, poi riprova."
                : "Plancia's token is missing. Open the Plancia window once, then try again."
        case .nonRaggiungibile:
            return Lingua.risolvi() == "it" ? "Plancia non risponde. Il server locale e' spento?"
                                            : "Plancia is not answering. Is the local server off?"
        case .http(let c, let s):
            return s.isEmpty ? "HTTP \(c)" : s
        }
    }
}

// MARK: - il cliente

enum ReteJarvis {
    private static let sessione: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 120
        c.timeoutIntervalForResource = 600
        c.waitsForConnectivity = false
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: c)
    }()

    private static func richiesta(_ percorso: String, _ corpo: [String: Any], timeout: TimeInterval) -> URLRequest {
        var r = URLRequest(url: URL(string: Casa.base + percorso)!, timeoutInterval: timeout)
        r.httpMethod = "POST"
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.setValue(Casa.token, forHTTPHeaderField: "X-Plancia-Token")
        r.httpBody = try? JSONSerialization.data(withJSONObject: corpo)
        return r
    }

    private static func json(_ dati: Data) -> [String: Any] {
        ((try? JSONSerialization.jsonObject(with: dati)) as? [String: Any]) ?? [:]
    }

    /// Una richiesta, ripetuta una volta se la connessione riusata era stata chiusa dal server nel
    /// frattempo (succede: il server locale chiude le connessioni quando gli pare).
    private static func scambia(_ req: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await sessione.data(for: req)
        } catch let e as URLError where e.code == .networkConnectionLost {
            return try await sessione.data(for: req)
        }
    }

    // MARK: la frase

    /// Una frase dentro, eventi fuori. Annullare il compito che lo consuma chiude la
    /// connessione, e il server ferma il modello.
    static func flusso(testo: String, lingua: String) -> AsyncThrowingStream<EventoJarvis, Error> {
        AsyncThrowingStream { cont in
            let compito = Task {
                do {
                    // Senza token il server rifiuta la richiesta senza leggerne il corpo, e la
                    // connessione riusata dopo esce sporca: meglio non mandarla.
                    if Casa.token.isEmpty { throw ErroreJarvis.senzaToken }
                    let req = richiesta("/api/jarvis/capisci", ["testo": testo, "lang": lingua], timeout: 120)
                    let (byte, risposta) = try await sessione.bytes(for: req)
                    let codice = (risposta as? HTTPURLResponse)?.statusCode ?? 0
                    if codice != 200 {
                        var corpo = Data()
                        for try await b in byte { corpo.append(b); if corpo.count > 4000 { break } }
                        throw ErroreJarvis.http(codice, (json(corpo)["errore"] as? String) ?? "")
                    }
                    for try await riga in byte.lines {
                        if let e = analizza(riga) { cont.yield(e) }
                    }
                    cont.finish()
                } catch let e as URLError where e.code != .cancelled {
                    cont.finish(throwing: ErroreJarvis.nonRaggiungibile)
                } catch {
                    cont.finish(throwing: error)
                }
            }
            cont.onTermination = { _ in compito.cancel() }
        }
    }

    static func analizza(_ riga: String) -> EventoJarvis? {
        guard let d = riga.data(using: .utf8),
              let j = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any],
              let t = j["t"] as? String else { return nil }
        switch t {
        case "stato": return EventoJarvis(tipo: "stato", testo: (j["v"] as? String) ?? "")
        case "testo": return EventoJarvis(tipo: "testo", testo: (j["d"] as? String) ?? "")
        case "frase":
            return EventoJarvis(tipo: "frase", testo: (j["d"] as? String) ?? "",
                                dire: (j["dire"] as? String) ?? (j["d"] as? String) ?? "")
        case "fine":
            return EventoJarvis(tipo: "fine", esito: EsitoJarvis((j["esito"] as? [String: Any]) ?? [:]))
        default: return nil
        }
    }

    // MARK: la scheda

    /// Esegue la proposta. Da chiamare solo dal pulsante Conferma.
    static func conferma(id: String, lingua: String) async throws -> EsitoJarvis {
        if Casa.token.isEmpty { throw ErroreJarvis.senzaToken }
        do {
            let (dati, r) = try await scambia(richiesta("/api/jarvis/conferma",
                                                        ["id": id, "lang": lingua], timeout: 60))
            let codice = (r as? HTTPURLResponse)?.statusCode ?? 0
            let j = json(dati)
            if codice != 200 { throw ErroreJarvis.http(codice, (j["errore"] as? String) ?? "") }
            return EsitoJarvis(j)
        } catch let e as URLError {
            if e.code == .cancelled { throw CancellationError() }
            throw ErroreJarvis.nonRaggiungibile
        }
    }

    static func rifiuta(id: String) async {
        _ = try? await scambia(richiesta("/api/jarvis/rifiuta", ["id": id], timeout: 8))
    }

    static func ferma() async {
        _ = try? await scambia(richiesta("/api/jarvis/ferma", [:], timeout: 5))
    }

    // MARK: la voce

    /// Scalda il modello in sola lettura e chiede quale voce neurale c'e'. nil se il
    /// server non risponde.
    static func pronto(lingua: String) async -> InfoVoceServer? {
        guard !Casa.token.isEmpty else { return nil }
        guard let (dati, r) = try? await scambia(richiesta("/api/jarvis/pronto",
                                                                       ["lang": lingua], timeout: 6)),
              (r as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        let j = json(dati)
        let n = j["neurale"] as? String
        let k = j["kokoro"] as? String
        return InfoVoceServer(neurale: (n?.isEmpty ?? true) ? nil : n,
                              kokoroNo: (k?.isEmpty ?? true) ? nil : k)
    }

    /// Una frase in un file audio. Il server prova Kokoro, Pocket e Voicebox e sollevera' un
    /// "nota_voce" se nessuno risponde: allora `url` e' nil, e chi chiama passa alla voce di
    /// sistema. `attesa` e' quanto si e' disposti ad aspettare questa frase; `velocita` e' un
    /// fattore (1 e' la voce normale) che vale per Kokoro.
    static func sintetizza(_ frase: String, lingua: String, attesa: TimeInterval,
                           velocita: Double = 1) async -> FraseSintetizzata {
        let req = richiesta("/api/voice/speak",
                            ["testo": frase, "lang": lingua, "motore": "neurale", "velocita": velocita],
                            timeout: attesa)
        do {
            if Casa.token.isEmpty { return FraseSintetizzata() }
            let (dati, r) = try await scambia(req)
            let codice = (r as? HTTPURLResponse)?.statusCode ?? 0
            let j = json(dati)
            guard codice == 200, let file = j["file"] as? String, !file.isEmpty,
                  FileManager.default.fileExists(atPath: file) else {
                Log.write("jarvis: sintesi senza file (HTTP \(codice)) \((j["nota_voce"] as? String) ?? (j["errore"] as? String) ?? "")")
                return FraseSintetizzata(url: nil, motore: nil, ripiego: j["nota_voce"] as? String)
            }
            return FraseSintetizzata(url: URL(fileURLWithPath: file), motore: j["motore"] as? String,
                                     ripiego: j["ripiego"] as? String)
        } catch {
            Log.write("jarvis: sintesi fallita: \(error.localizedDescription)")
            return FraseSintetizzata()
        }
    }
}
