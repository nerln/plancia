// Il modo prova di Jarvis: niente microfono, niente altoparlanti.
//
//   PLANCIA_JARVIS_PROVA=1           l'ascolto recita una frase (PLANCIA_JARVIS_PROVA_FRASE) con un
//                                    livello finto e la voce si recita con un livello finto: nessun
//                                    motore audio, nessun permesso, nessun suono
//   JarvisProva.scatta(...)          fotografa il pannello in una scena fissa (ascolto, pensa,
//                                    risponde, chiede conferma, errore...) per vedere com'e'
//
// Le scene sono dati scritti qui, senza nomi veri. Il PNG e' la finestra vera, col vetro di sistema.

import AppKit
import SwiftUI

enum JarvisProva {
    static var attivo: Bool {
        !(ProcessInfo.processInfo.environment["PLANCIA_JARVIS_PROVA"] ?? "").isEmpty
    }
    static var frase: String {
        let f = ProcessInfo.processInfo.environment["PLANCIA_JARVIS_PROVA_FRASE"] ?? ""
        return f.isEmpty ? "ricordami di chiamare Mario" : f
    }

    enum Scena: String, CaseIterable {
        case inattivo, ascolto, penso, risposta, scheda, schedaAgente, schedaSessione
        case senzaVoce, serverSpento, lunga
    }
}

extension JarvisModello {
    /// Mette il modello in una scena fissa, senza rete, senza audio.
    func mostraScena(_ s: JarvisProva.Scena) {
        let it = lingua == "it"
        func azzera() {
            trascritto = ""; pezzi = []; proposta = nil; messaggio = nil; erroreGrave = false
            microfonoAcceso = false; microfonoInApertura = false; elabora = false; parla = false
            confermaInCorso = false; livello.valore = 0
            voceDescrizione = it ? "Voce neurale: Kokoro" : "Neural voice: Kokoro"
            voceAvviso = nil
        }
        func testo(_ t: String, eta: TimeInterval = 5) {
            pezzi = [Pezzo(id: 1, testo: t, arrivo: Date().addingTimeInterval(-eta))]
        }
        azzera()
        switch s {
        case .inattivo:
            break
        case .ascolto:
            microfonoAcceso = true
            livello.valore = 0.62
            trascritto = it ? "ricordami di chiamare Mario domani" : "remind me to call Mario tomorrow"
        case .penso:
            elabora = true
            trascritto = it ? "cosa devo fare oggi su Atlas" : "what do I have to do today on Atlas"
        case .risposta:
            parla = true
            livello.valore = 0.55
            trascritto = it ? "cosa devo fare oggi su Atlas" : "what do I have to do today on Atlas"
            testo(it ? "Su Atlas hai due task aperti. Il primo è togliere i biglietti duplicati prima di calcolare i punteggi, il secondo è confrontare i tre modelli sulla stessa partizione."
                     : "On Atlas you have two open tasks. The first is dropping duplicate tickets before scoring, the second is comparing the three models on the same split.")
        case .lunga:
            parla = true
            livello.valore = 0.4
            trascritto = it ? "fammi il punto sulla settimana" : "give me the week so far"
            testo(String(repeating: it ? "Questa settimana hai chiuso sette task e fatto quattordici commit su tre progetti. " : "This week you closed seven tasks and made fourteen commits across three projects. ", count: 7))
        case .scheda:
            trascritto = it ? "ricordami di chiamare Mario" : "remind me to call Mario"
            testo(it ? "Ho preparato la scheda: guarda cosa succede e conferma col pulsante." : "I prepared the card: check what happens and confirm with the button.")
            proposta = PropostaJarvis(id: "prova1", azione: "task_add",
                                      titolo: it ? "Segnare un task" : "Add a task",
                                      righe: [.init(chiave: "Task", valore: it ? "Chiamare Mario" : "Call Mario"),
                                              .init(chiave: it ? "Progetto" : "Project", valore: "Atlas")],
                                      rischio: "scrive", avviso: it ? "Modifica l'archivio." : "Changes the archive.")
        case .schedaAgente:
            trascritto = it ? "fallo, e fallo davvero" : "do it, for real"
            testo(it ? "Ho preparato la scheda: guarda cosa succede e conferma col pulsante." : "I prepared the card: check what happens and confirm with the button.")
            proposta = PropostaJarvis(id: "prova2", azione: "lancia",
                                      titolo: it ? "Mandare un agente" : "Send an agent",
                                      righe: [.init(chiave: it ? "Cosa" : "What", valore: "Drop duplicate tickets before scoring"),
                                              .init(chiave: it ? "Agente" : "Agent", valore: "claude"),
                                              .init(chiave: it ? "Modo" : "Mode", valore: it ? "può modificare file" : "may change files"),
                                              .init(chiave: it ? "Cartella" : "Folder", valore: "~/dev/atlas"),
                                              .init(chiave: it ? "Sessione" : "Session", valore: it ? "riparte dalla sessione che ha salvato il task" : "picks up the session that saved the task")],
                                      rischio: "lancia_scrive",
                                      avviso: it ? "Parte un agente che può modificare i file della cartella." : "An agent starts and may change the files in the folder.")
        case .schedaSessione:
            trascritto = it ? "riprendi il task 4" : "resume task 4"
            testo(it ? "Ho preparato la scheda: guarda cosa succede e conferma col pulsante." : "I prepared the card: check what happens and confirm with the button.")
            proposta = PropostaJarvis(id: "prova3", azione: "riprendi_task",
                                      titolo: it ? "Riprendere un task" : "Resume a task",
                                      righe: [.init(chiave: "Task", valore: "Score all three models on the same split"),
                                              .init(chiave: it ? "Sessione" : "Session", valore: it ? "la sessione è chiusa: riparte da quella" : "the session is closed: it resumes that one")],
                                      rischio: "lancia", avviso: it ? "Parte un agente sul tuo computer." : "An agent starts on your computer.")
        case .senzaVoce:
            trascritto = it ? "che ore sono a Roma" : "what time is it in Rome"
            testo(it ? "Non lo so dai dati di Plancia, ma posso dirti cosa c'è in agenda." : "I can not tell from the Plancia data, but I can tell you what is on the agenda.")
            voceDescrizione = it ? "Solo testo: nessuna voce avanzata installata" : "Text only: no enhanced voice installed"
            voceAvviso = it ? "Scarica una voce avanzata o premium in Impostazioni di sistema, Accessibilità, Contenuto letto."
                            : "Download an enhanced or premium voice in System Settings, Accessibility, Spoken Content."
        case .serverSpento:
            avvisa(ErroreJarvis.nonRaggiungibile.localizedDescription, grave: true)
            voceDescrizione = it ? "Voce di sistema: Zoe (premium)" : "System voice: Zoe (premium)"
            voceAvviso = it ? "Nessuna voce neurale locale. Per averne una: plancia voce installa (Kokoro)."
                            : "No local neural voice. To get one: plancia voce installa (Kokoro)."
        }
    }
}

@MainActor
extension JarvisProva {
    /// Scatta una scena e salva il PNG. Torna il percorso, o nil se la cattura non e' riuscita.
    static func scatta(_ scena: Scena, pannello: JarvisPanel, cartella: URL, aspetto: String) async -> URL? {
        pannello.modello.mostraScena(scena)
        if !pannello.visibile { pannello.mostra() }
        // il tempo di adattare l'altezza e di far correre l'onda
        try? await Task.sleep(nanoseconds: 900_000_000)
        guard let f = pannello.window, let png = Cattura.png(f) else { return nil }
        let file = cartella.appendingPathComponent("jarvis-\(scena.rawValue)-\(aspetto).png")
        do { try png.write(to: file) } catch { return nil }
        return file
    }
}
