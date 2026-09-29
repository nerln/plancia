// Lingua dell'interfaccia (italiano e inglese) e formati di data e ora.
//
// Niente String Catalog: senza Xcode non c'e' un compilatore di cataloghi, e ogni
// vista e' scritta da un agente diverso. Le stringhe stanno accanto a dove servono:
//
//     Text(tr("Fatto", "Done"))
//
// `tr` legge la lingua da un oggetto osservabile, quindi cambiarla nelle
// Impostazioni riscrive le viste aperte senza riavviare.

import Foundation
import Observation

@MainActor
@Observable
final class Lingua {
    static let condivisa = Lingua()

    /// "it" o "en"
    var codice: String

    private init() { codice = Lingua.risolvi() }

    func imposta(_ nuovo: String) {
        let c = (nuovo == "it") ? "it" : "en"
        UserDefaults.standard.set(c, forKey: "lingua")
        codice = c
    }

    var locale: Locale { Locale(identifier: codice == "it" ? "it_IT" : "en_US") }

    /// La scelta fatta nelle Impostazioni; se manca, `lingua` di config.json; se manca,
    /// la lingua del sistema. Le altre lingue del server (es, fr...) qui diventano inglese.
    nonisolated static func risolvi() -> String {
        if let s = UserDefaults.standard.string(forKey: "lingua"), s == "it" || s == "en" { return s }
        if let c = Casa.config["lingua"] as? String {
            if c == "it" { return "it" }
            if !c.isEmpty { return "en" }
        }
        return (Locale.preferredLanguages.first ?? "en").hasPrefix("it") ? "it" : "en"
    }
}

/// Il testo nella lingua corrente.
@MainActor
func tr(_ it: String, _ en: String) -> String {
    Lingua.condivisa.codice == "it" ? it : en
}

// MARK: - date e ore

enum Tempo {
    private nonisolated(unsafe) static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    private nonisolated(unsafe) static let isoFrazione: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let giornoSolo: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    /// "2026-09-29T20:06:31Z" o "2026-09-29".
    nonisolated static func data(_ s: String?) -> Date? {
        guard let s = s, !s.isEmpty else { return nil }
        return iso.date(from: s) ?? isoFrazione.date(from: s) ?? giornoSolo.date(from: String(s.prefix(10)))
    }

    /// "21:59"
    @MainActor static func ora(_ d: Date) -> String {
        let f = DateFormatter()
        f.locale = Lingua.condivisa.locale
        f.timeStyle = .short
        f.dateStyle = .none
        return f.string(from: d)
    }

    /// "29 set" / "Sep 29"
    @MainActor static func giorno(_ d: Date) -> String {
        let f = DateFormatter()
        f.locale = Lingua.condivisa.locale
        f.setLocalizedDateFormatFromTemplate("d MMM")
        return f.string(from: d)
    }

    @MainActor static func giorno(_ s: String?) -> String {
        guard let d = data(s) else { return "" }
        return giorno(d)
    }

    /// "2 ore fa" / "2 hours ago"
    @MainActor static func relativo(_ s: String?) -> String {
        guard let d = data(s) else { return "" }
        let f = RelativeDateTimeFormatter()
        f.locale = Lingua.condivisa.locale
        f.unitsStyle = .short
        return f.localizedString(for: d, relativeTo: Date())
    }

    /// Vero se il giorno (yyyy-MM-dd) e' prima di oggi.
    nonisolated static func scaduto(_ s: String?) -> Bool {
        guard let d = data(s) else { return false }
        return d < Calendar.current.startOfDay(for: Date())
    }
}
