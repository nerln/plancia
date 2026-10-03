// Mappa della memoria: i dati dei gruppi.
//
// Il server (/api/memoria/mappa) dice per ogni nodo il `gruppo` (la chiave stabile del
// cluster), il `gruppo_nome` e un `titolo` umano, e porta l'elenco dei gruppi con colore
// stabile e ponti. Questo file li legge per conto suo, senza toccare il Core: i modelli
// del Core non conoscono questi campi. Se il server e' piu' vecchio, o i nomi non
// corrispondono, i gruppi si ricavano dalla scheda stessa: il progetto, altrimenti il tipo.

import Foundation
import SwiftUI

// MARK: - la risposta del server

struct LegameGruppo: Decodable, Hashable {
    @Lax var gruppo: String?
    @Lax var n: Int?
}

struct GruppoServer: Decodable, Hashable {
    @Lax var chiave: String?
    @Lax var nome: String?
    @Lax var colore: String?
    @Lax var memorie: Int?
    @Lax var x: Double?
    @Lax var y: Double?
    @LaxLista var legami: [LegameGruppo]?
}

struct NodoGruppo: Decodable, Hashable {
    @Lax var nome: String?
    @Lax var gruppo: String?
    @Lax var gruppoNome: String?
    @Lax var titolo: String?
}

/// Solo i campi nuovi di /api/memoria/mappa.
struct MappaGruppi: Decodable, Hashable {
    @LaxLista var nodi: [NodoGruppo]?
    @LaxLista var gruppi: [GruppoServer]?

    var impronta: Int {
        var h = Hasher()
        for n in nodi ?? [] { h.combine(n.nome); h.combine(n.gruppo); h.combine(n.titolo) }
        for g in gruppi ?? [] { h.combine(g.chiave); h.combine(g.colore) }
        return h.finalize()
    }
}

enum CaricaGruppi {
    /// La mappa dei gruppi dal server; `nil` se non risponde o se non conosce i gruppi.
    static func carica(compartimento: String?) async -> MappaGruppi? {
        guard let m = try? await Cliente.condiviso.ottieni(MappaGruppi.self, "/api/memoria/mappa",
                                                           compartimento: compartimento, timeout: 60),
              !(m.gruppi ?? []).isEmpty, !(m.nodi ?? []).isEmpty else { return nil }
        return m
    }
}

// MARK: - colori

enum ColoreGruppo {
    /// La stessa tavolozza del server (plancia/mappa.py): se il server non manda il colore,
    /// il gruppo ne prende uno stabile dalla sua chiave.
    static let tavolozza: [UInt32] = [0xe07b2a, 0x3b6fd0, 0x3fa066, 0xa35cc2, 0xd4546a, 0x20a39e,
                                       0xc9a227, 0x6a6bd6, 0xa0714a, 0x42b0d5, 0x8fb339, 0xcc5fa8]

    static func da(testo: String?) -> UInt32? {
        guard var t = testo?.trimmingCharacters(in: .whitespaces), !t.isEmpty else { return nil }
        if t.hasPrefix("#") { t.removeFirst() }
        guard t.count == 6, let v = UInt32(t, radix: 16) else { return nil }
        return v
    }

    static func stabile(_ chiave: String, occupati: Set<UInt32>) -> UInt32 {
        var h: UInt32 = 2166136261
        for b in chiave.utf8 { h = (h ^ UInt32(b)) &* 16777619 }
        let n = tavolozza.count
        for passo in 0..<n {
            let c = tavolozza[(Int(h % UInt32(n)) + passo) % n]
            if !occupati.contains(c) { return c }
        }
        return tavolozza[Int(h % UInt32(n))]
    }

    /// Il colore (i colori fissi vivono in Tema/Tavolozza.swift: qui arriva solo il numero).
    static func colore(_ v: UInt32) -> Color { Tavolozza.colore(v) }

    /// Un colore adatto al testo sullo sfondo: piu' scuro sul chiaro, piu' chiaro sullo scuro.
    static func testo(_ v: UInt32, scuro: Bool) -> Color {
        func canale(_ c: UInt32) -> UInt32 {
            let x = Double(c)
            let t = scuro ? 0.38 : 0.34
            let m = scuro ? 255.0 : 0.0
            return UInt32(min(max((x + (m - x) * t).rounded(), 0), 255))
        }
        let r = canale((v >> 16) & 0xFF), g = canale((v >> 8) & 0xFF), b = canale(v & 0xFF)
        return Tavolozza.colore(r << 16 | g << 8 | b)
    }
}

// MARK: - titoli

enum TitoloMappa {
    /// Il testo che sta su un nodo: corto, mai la sigla del file. Taglia a una parola.
    static func breve(_ testo: String, massimo: Int = 28) -> String {
        let t = testo.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count > massimo else { return t }
        let taglio = String(t.prefix(massimo - 1))
        if let spazio = taglio.lastIndex(of: " "), taglio.distance(from: taglio.startIndex, to: spazio) >= massimo / 2 {
            return String(taglio[..<spazio]).trimmingCharacters(in: CharacterSet(charactersIn: " ,;:-")) + "…"
        }
        return taglio + "…"
    }

    /// Se il server non da' il titolo: la prima frase della descrizione, altrimenti il nome
    /// reso leggibile ("harbour-config-format" diventa "Harbour config format").
    static func ricava(nome: String, descrizione: String) -> String {
        let d = descrizione.split(whereSeparator: { $0.isNewline }).joined(separator: " ")
            .trimmingCharacters(in: .whitespaces)
        if !d.isEmpty {
            var fine = d.endIndex
            for (i, c) in zip(d.indices, d) where ".!?;".contains(c) {
                let dopo = d.index(after: i)
                if dopo == d.endIndex || d[dopo] == " " { fine = i; break }
            }
            let frase = String(d[..<fine]).trimmingCharacters(in: CharacterSet(charactersIn: " .,;:-"))
            if !frase.isEmpty { return frase.prefix(1).uppercased() + frase.dropFirst() }
        }
        let umano = nome.replacingOccurrences(of: "-", with: " ").replacingOccurrences(of: "_", with: " ")
            .trimmingCharacters(in: .whitespaces)
        return umano.prefix(1).uppercased() + umano.dropFirst()
    }
}
