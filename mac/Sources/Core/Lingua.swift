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
    ///
    /// Le date ISO con fuso ("...Z" o "+02:00", con o senza frazione di secondo) si leggono a
    /// mano: le viste le chiedono per ogni riga e per ogni confronto di un ordinamento, e un
    /// ISO8601DateFormatter costa qualche microsecondo a chiamata. Tutto il resto (il solo
    /// giorno, forme strane) passa dai formattatori di prima, con lo stesso risultato.
    nonisolated static func data(_ s: String?) -> Date? {
        guard let s = s, !s.isEmpty else { return nil }
        if let d = leggiVeloce(s) { return d }
        return iso.date(from: s) ?? isoFrazione.date(from: s) ?? giornoSolo.date(from: String(s.prefix(10)))
    }

    private nonisolated static func leggiVeloce(_ s: String) -> Date? {
        let r: Date?? = s.utf8.withContiguousStorageIfAvailable { b -> Date? in
            let n = b.count
            guard n >= 20 else { return nil }
            @inline(__always) func cifre(_ da: Int, _ quante: Int) -> Int? {
                var v = 0
                for i in da..<(da + quante) {
                    let c = Int(b[i]) - 48
                    guard c >= 0 && c <= 9 else { return nil }
                    v = v * 10 + c
                }
                return v
            }
            guard b[4] == 45, b[7] == 45, b[10] == 84, b[13] == 58, b[16] == 58,
                  let anno = cifre(0, 4), let mese = cifre(5, 2), let giorno = cifre(8, 2),
                  let ora = cifre(11, 2), let minuto = cifre(14, 2), let secondo = cifre(17, 2),
                  mese >= 1, mese <= 12, giorno >= 1, ora < 24, minuto < 60, secondo < 61 else { return nil }
            let giorniDelMese = [31, (anno % 4 == 0 && (anno % 100 != 0 || anno % 400 == 0)) ? 29 : 28,
                                 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            guard giorno <= giorniDelMese[mese - 1] else { return nil }
            var i = 19
            var frazione = 0.0
            if b[i] == 46 {
                var scala = 0.1
                i += 1
                let inizio = i
                while i < n, b[i] >= 48, b[i] <= 57 {
                    frazione += Double(b[i] - 48) * scala
                    scala /= 10
                    i += 1
                }
                guard i > inizio else { return nil }
            }
            guard i < n else { return nil }
            var scarto = 0
            if b[i] == 90 {
                guard i == n - 1 else { return nil }
            } else if b[i] == 43 || b[i] == 45 {
                guard n - i == 6, b[i + 3] == 58, let oh = cifre(i + 1, 2), let om = cifre(i + 4, 2),
                      oh < 24, om < 60 else { return nil }
                scarto = (oh * 3600 + om * 60) * (b[i] == 45 ? -1 : 1)
            } else {
                return nil
            }
            // giorni dal 1970 (Howard Hinnant, days_from_civil)
            let a = mese <= 2 ? anno - 1 : anno
            let era = (a >= 0 ? a : a - 399) / 400
            let yoe = a - era * 400
            let doy = (153 * ((mese + 9) % 12) + 2) / 5 + giorno - 1
            let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
            let giorni = era * 146097 + doe - 719468
            let secondi = giorni * 86400 + ora * 3600 + minuto * 60 + secondo - scarto
            return Date(timeIntervalSince1970: Double(secondi) + frazione)
        }
        return r ?? nil
    }

    // I formattatori costano piu' di quello che formattano: uno per lingua, creato una volta.
    @MainActor private static var formatiOra: [String: DateFormatter] = [:]
    @MainActor private static var formatiGiorno: [String: DateFormatter] = [:]
    @MainActor private static var formatiRelativi: [String: RelativeDateTimeFormatter] = [:]

    /// "21:59"
    @MainActor static func ora(_ d: Date) -> String {
        let codice = Lingua.condivisa.codice
        let f = formatiOra[codice] ?? {
            let f = DateFormatter()
            f.locale = Lingua.condivisa.locale
            f.timeStyle = .short
            f.dateStyle = .none
            formatiOra[codice] = f
            return f
        }()
        return f.string(from: d)
    }

    /// "29 set" / "Sep 29"
    @MainActor static func giorno(_ d: Date) -> String {
        let codice = Lingua.condivisa.codice
        let f = formatiGiorno[codice] ?? {
            let f = DateFormatter()
            f.locale = Lingua.condivisa.locale
            f.setLocalizedDateFormatFromTemplate("d MMM")
            formatiGiorno[codice] = f
            return f
        }()
        return f.string(from: d)
    }

    @MainActor static func giorno(_ s: String?) -> String {
        guard let d = data(s) else { return "" }
        return giorno(d)
    }

    // "2 ore fa" cambia al massimo una volta al minuto: le viste lo chiedono per ogni riga a
    // ogni ridisegno (la ricerca a ogni lettera), e formattarlo costa piu' di leggerlo qui.
    @MainActor private static var relativiFatti: [String: String] = [:]
    @MainActor private static var minutoRelativi = 0

    /// "2 ore fa" / "2 hours ago"
    @MainActor static func relativo(_ s: String?) -> String {
        guard let s = s, !s.isEmpty else { return "" }
        let minuto = Int(Date().timeIntervalSince1970 / 60)
        if minuto != minutoRelativi {
            relativiFatti.removeAll(keepingCapacity: true)
            minutoRelativi = minuto
        }
        let codice = Lingua.condivisa.codice
        let chiave = codice + "|" + s
        if let v = relativiFatti[chiave] { return v }
        guard let d = data(s) else { return "" }
        let f = formatiRelativi[codice] ?? {
            let f = RelativeDateTimeFormatter()
            f.locale = Lingua.condivisa.locale
            f.unitsStyle = .short
            formatiRelativi[codice] = f
            return f
        }()
        let testo = f.localizedString(for: d, relativeTo: Date())
        if relativiFatti.count < 8192 { relativiFatti[chiave] = testo }
        return testo
    }

    /// L'inizio di oggi, ricalcolato solo quando passa la mezzanotte.
    private final class InizioGiorno: @unchecked Sendable {
        private let l = NSLock()
        private var inizio = Date.distantFuture
        private var fine = Date.distantPast
        func oggi() -> Date {
            l.lock(); defer { l.unlock() }
            let ora = Date()
            if ora >= fine || ora < inizio {
                let cal = Calendar.current
                inizio = cal.startOfDay(for: ora)
                fine = cal.date(byAdding: .day, value: 1, to: inizio) ?? ora.addingTimeInterval(3600)
            }
            return inizio
        }
    }
    private static let inizioGiorno = InizioGiorno()

    /// Vero se il giorno (yyyy-MM-dd) e' prima di oggi.
    nonisolated static func scaduto(_ s: String?) -> Bool {
        guard let d = data(s) else { return false }
        return d < inizioGiorno.oggi()
    }
}
