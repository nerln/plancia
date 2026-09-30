import SwiftUI

// MARK: - il piano di un lavoro in background

/// Cosa farebbe il server per un lavoro che parte da una sessione (`piano` nelle risposte di
/// /api/riprendi, /api/cantiere e nelle anteprime). Il lavoro prosegue nella sessione che
/// il task ha salvato; solo se e' davvero persa ne parte una nuova, e questo lo si dice
/// PRIMA di lanciare.
///
///   riprendi  la sessione e' chiusa: continua li' (stesso id, sua cartella)
///   copia     la sessione e' aperta e si e' chiesta una copia: id nuovo, stessa storia
///   nuova     nessuna sessione da riprendere: parte una nuova, col contesto scritto a mano
///   niente    la sessione e' aperta: da qui non parte niente
@MainActor
struct PianoRipresa: Equatable {
    let modo: String
    let motivo: String

    init?(_ j: JSONValue?) {
        guard let m = j?["modo"]?.testo, !m.isEmpty else { return nil }
        modo = m
        motivo = j?["motivo"]?.testo ?? ""
    }

    /// Parte davvero qualcosa?
    var parte: Bool { modo != "niente" }

    /// La frase che dice cosa succede, nella lingua dell'app.
    var frase: String {
        switch modo {
        case "riprendi":
            return tr("Riprende la sessione originale, nella sua cartella.",
                      "Resumes the original session, in its own folder.")
        case "copia":
            return tr("La sessione è aperta: parte una copia, quella aperta non riceve niente.",
                      "The session is open: a copy starts, the open one gets nothing.")
        case "nuova":
            return tr("La sessione originale non c'è più: parte una sessione nuova.",
                      "The original session is gone: a new session starts.")
        default:
            return tr("La sessione è aperta: da qui non la tocco.",
                      "The session is open: I won't touch it from here.")
        }
    }
}

/// Un lancio in background con il suo piano, in attesa del "si" dell'utente.
@MainActor
struct LancioPronto: Identifiable {
    let id = UUID()
    let percorso: String
    let corpo: [String: Any]
    let piano: PianoRipresa
    let agente: String
    /// Il titolo della finestra e il testo del pulsante che conferma.
    let titolo: String
    let azione: String

    /// Il testo della finestra: cosa succede alla sessione, e che il lavoro in background non scrive.
    var testo: String {
        corpo["apri"] != nil ? piano.frase : piano.frase + " " + tr("In sola lettura.", "Read-only.")
    }

    /// Un lavoro in background (sola lettura): la finestra dice cosa succede prima di partire.
    init(percorso: String, corpo: [String: Any], piano: PianoRipresa, agente: String) {
        self.percorso = percorso; self.corpo = corpo; self.piano = piano; self.agente = agente
        titolo = tr("Avviare un lancio in background?", "Start a background run?")
        azione = tr("Avvia senza modificare file", "Start without changing files")
    }

    /// Una sessione nuova nel Terminale, dopo che il piano ha detto che la vecchia non c'e' piu'.
    init(nuovaNelTerminale percorso: String, piano: PianoRipresa, agente: String) {
        self.percorso = percorso; self.corpo = ["apri": true]; self.piano = piano; self.agente = agente
        titolo = tr("Aprire una sessione nuova?", "Open a new session?")
        azione = tr("Apri nel Terminale", "Open in Terminal")
    }
}

extension Archivio {
    /// Il piano di un task di Plancia (`piano` di GET /api/riprendi/<id>).
    func pianoRipresa(task id: Int) async -> PianoRipresa? {
        guard let r = try? await cliente.ottieni(JSONValue.self, "/api/riprendi/\(id)",
                                                 compartimento: compartimento) else { return nil }
        return PianoRipresa(r["piano"])
    }

    /// Il piano di un lancio senza toccare niente: la stessa richiesta con `anteprima`.
    func anteprima(_ percorso: String, _ corpo: [String: Any]) async -> PianoRipresa? {
        var c = corpo
        c["anteprima"] = true
        c.removeValue(forKey: "background")
        guard let r = try? await cliente.scrivi("POST", percorso, corpo: c,
                                                compartimento: compartimento) else { return nil }
        return PianoRipresa(r["piano"])
    }
}
