// Configurazione e diario dell'app. Il codice di sistema (avvio del server, barra
// dei menu, plancia://, notifiche, registro) sta in Sistema/, spezzato per compito.

import Foundation

// MARK: - configurazione

struct Conf {
    static let home = FileManager.default.homeDirectoryForCurrentUser
    /// La cartella dei dati: `$PLANCIA_HOME` se c'e' (le prove e le istantanee ne
    /// usano una propria), altrimenti `~/.plancia`. La logica sta in Core/Cliente.swift.
    static var dataDir: URL { Casa.dir }
    static var settings: [String: Any] { Casa.config }
    static var port: Int { Casa.porta }
    /// La lingua dell'interfaccia e della voce: la scelta fatta nelle Impostazioni
    /// se c'e', poi `lingua` di config.json, poi quella del sistema.
    static var lang: String { Lingua.risolvi() }
    static var base: String { Casa.base }
    static var token: String { Casa.token }

    /// Il comando `plancia`. Il percorso vero lo scrive lo script di build,
    /// gli altri sono i posti dove finisce normalmente.
    static var executable: String? {
        var candidati: [String] = []
        if let p = Bundle.main.object(forInfoDictionaryKey: "PlanciaExecutable") as? String {
            candidati.append(p)
        }
        candidati += [
            home.appendingPathComponent(".local/bin/plancia").path,
            "/usr/local/bin/plancia",
            "/opt/homebrew/bin/plancia",
            home.appendingPathComponent("dev/plancia/bin/plancia").path,
        ]
        return candidati.first { FileManager.default.isExecutableFile(atPath: $0) }
    }
}

// MARK: - diario

/// Un file di testo in ~/.plancia/app.log. Senza questo, quando l'app non fa
/// quello che dovrebbe non si vede niente da nessuna parte.
enum Log {
    static let file = Conf.dataDir.appendingPathComponent("app.log")
    static func write(_ s: String) {
        let riga = "\(ISO8601DateFormatter().string(from: Date())) \(s)\n"
        guard let d = riga.data(using: .utf8) else { return }
        if let fh = try? FileHandle(forWritingTo: file) {
            fh.seekToEndOfFile(); fh.write(d); try? fh.close()
        } else {
            try? d.write(to: file)
        }
    }
}
