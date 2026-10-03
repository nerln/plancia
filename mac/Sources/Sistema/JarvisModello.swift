// Il cervello del pannello Jarvis: una macchina a stati piccola, e tutte le regole di sicurezza
// in un punto solo.
//
//   - Il microfono si accende solo da `toggleMicrofono` (il pulsante) o dalla scorciatoia
//     (`apri(ascolta: true)`). Nient'altro lo riapre, salvo la "conversazione continua" che
//     e' spenta di serie, si accende dal menu del pannello e si vede.
//   - Niente parte da una frase. Una proposta arriva come scheda (`proposta`), e l'unico
//     punto che chiama `ReteJarvis.conferma` e' `conferma()`, che il pulsante Conferma
//     chiama e nessun altro: non la voce, non un timer, non un evento del server.
//   - Esc e il pulsante Ferma spengono tutto: microfono, voce, richiesta al server.
//   - Il pannello mostra sempre cosa sta per succedere: la scheda ha le righe vere del
//     server (agente, modo, cartella, sessione), non un riassunto scritto qui.

import AppKit
import Observation

/// Il livello dell'audio, letto a ogni fotogramma dal disegno dell'onda. Non e' osservabile
/// di proposito: trenta aggiornamenti al secondo non devono rifare tutta la vista.
final class LivelloAudio {
    var valore: Double = 0
}

enum Preferenze {
    static var ascoltaSubito: Bool {
        get { (UserDefaults.standard.object(forKey: "jarvisAscoltaSubito") as? Bool) ?? true }
        set { UserDefaults.standard.set(newValue, forKey: "jarvisAscoltaSubito") }
    }
    /// Il microfono si riapre da solo dopo ogni risposta. Spenta di serie.
    static var conversazione: Bool {
        get { UserDefaults.standard.bool(forKey: "jarvisConversazione") }
        set { UserDefaults.standard.set(newValue, forKey: "jarvisConversazione") }
    }
    static var voceBase: Bool {
        get { UserDefaults.standard.bool(forKey: "voceBaseAmmessa") }
        set { UserDefaults.standard.set(newValue, forKey: "voceBaseAmmessa") }
    }
    static var voceScelta: String? {
        get { UserDefaults.standard.string(forKey: "voceJarvis") }
        set { UserDefaults.standard.set(newValue, forKey: "voceJarvis") }
    }
}

@MainActor
@Observable
final class JarvisModello {
    enum Fase { case inattivo, ascolta, pensa, risponde, conferma, errore }

    struct Pezzo: Identifiable, Equatable {
        let id: Int
        let testo: String
        let arrivo: Date
    }

    // MARK: cosa si vede

    var trascritto = ""
    var pezzi: [Pezzo] = []
    var proposta: PropostaJarvis?
    var messaggio: String?
    var erroreGrave = false
    var microfonoAcceso = false
    /// Ha chiesto di ascoltare ma il motore non e' ancora partito (i permessi, il sistema).
    var microfonoInApertura = false
    var elabora = false
    var parla = false
    var confermaInCorso = false
    /// Il pannello e' sullo schermo: se no, l'onda non si disegna.
    var visibile = false
    var voceDescrizione = ""
    var voceAvviso: String?
    /// Cambia quando cambia una preferenza, per far rileggere il menu.
    var versionePreferenze = 0

    @ObservationIgnored let livello = LivelloAudio()
    @ObservationIgnored let ascolto = AscoltoContinuo()
    @ObservationIgnored let voce = VoceJarvis()
    @ObservationIgnored var onAzione: ((AzioneJarvis) -> Void)?
    @ObservationIgnored var onChiudi: (() -> Void)?
    @ObservationIgnored private var compito: Task<Void, Never>?
    @ObservationIgnored private var contaPezzi = 0
    @ObservationIgnored private var haParlato = false
    @ObservationIgnored private var neuraleNoto: String?
    @ObservationIgnored private var kokoroNoNoto: String?
    /// Quante volte e' arrivato Esc: serve alla prova per dire che arriva una volta sola.
    @ObservationIgnored var escRicevuti = 0
    private static var neuraleScaldato = false

    var lingua: String { Lingua.risolvi() }
    var risposta: String { pezzi.map(\.testo).joined() }

    var fase: Fase {
        if proposta != nil { return .conferma }
        if microfonoAcceso { return .ascolta }
        if parla || (elabora && !pezzi.isEmpty) { return .risponde }
        if elabora { return .pensa }
        if erroreGrave { return .errore }
        return .inattivo
    }

    /// C'e' qualcosa in corso che Esc o Ferma possono fermare.
    var inAttivita: Bool { microfonoAcceso || microfonoInApertura || elabora || parla }

    init() {
        ascolto.onAperto = { [weak self] in
            self?.microfonoInApertura = false
            self?.microfonoAcceso = true
        }
        ascolto.onLivello = { [weak self] l in self?.livello.valore = l }
        ascolto.onParziale = { [weak self] t in self?.trascritto = t }
        ascolto.onFrase = { [weak self] f in
            guard let self = self else { return }
            self.microfonoAcceso = false
            self.microfonoInApertura = false
            self.livello.valore = 0
            self.invia(f)
        }
        ascolto.onChiuso = { [weak self] motivo in
            guard let self = self else { return }
            self.microfonoAcceso = false
            self.microfonoInApertura = false
            self.livello.valore = 0
            if let m = motivo { self.avvisa(m, grave: false) }
        }
        voce.onLivello = { [weak self] l in
            guard let self = self, !self.microfonoAcceso else { return }
            self.livello.valore = l
        }
        voce.onCambio = { [weak self] in self?.rileggiVoce() }
        voce.onTermine = { [weak self] in self?.laVoceHaFinito() }
    }

    private func rileggiVoce() {
        voceDescrizione = voce.descrizione
        voceAvviso = voce.avviso
    }

    /// La prima frase con una voce neurale paga il caricamento del modello (con Kokoro il server
    /// ha gia' avviato il lavoratore: qui si aspetta che sia pronto): la si paga adesso, una volta
    /// per esecuzione, con una frase che poi resta in cache.
    private func scaldaNeurale() {
        guard !JarvisProva.attivo, !JarvisModello.neuraleScaldato else { return }
        JarvisModello.neuraleScaldato = true
        let l = lingua
        Task { _ = await ReteJarvis.sintetizza(l == "it" ? "Va bene." : "All right.", lingua: l, attesa: 90) }
    }

    // MARK: apertura e chiusura

    /// Il pannello e' comparso. `ascolta` e' vero solo se e' comparso per la scorciatoia (un
    /// gesto tuo) e la preferenza lo permette.
    func apri(ascolta: Bool) {
        if !inAttivita, proposta == nil {
            trascritto = ""
            pezzi = []
            messaggio = nil
            erroreGrave = false
        }
        voce.prepara(lingua: lingua, neurale: neuraleNoto, kokoroNo: kokoroNoNoto)
        rileggiVoce()
        Task { [weak self] in
            guard let self = self else { return }
            let info = await ReteJarvis.pronto(lingua: self.lingua)
            if JarvisProva.attivo, info == nil { return }
            self.neuraleNoto = info?.neurale
            self.kokoroNoNoto = info?.kokoroNo
            if info?.neurale != nil { self.scaldaNeurale() }
            if !self.parla { self.voce.prepara(lingua: self.lingua, neurale: info?.neurale, kokoroNo: info?.kokoroNo) }
            self.rileggiVoce()
            if info == nil, self.pezzi.isEmpty {
                self.avvisa(ErroreJarvis.nonRaggiungibile.localizedDescription, grave: true)
            }
        }
        if ascolta, Preferenze.ascoltaSubito { avviaMicrofono() }
    }

    /// La scorciatoia premuta a pannello gia' aperto: accende o spegne il microfono.
    func scorciatoiaSuPannelloAperto() {
        if microfonoAcceso { ascolto.chiudi(inviando: true, motivo: nil) }
        else if microfonoInApertura { ferma() }
        else if !confermaInCorso { avviaMicrofono() }
    }

    func chiudi() {
        ferma()
        if let p = proposta {
            proposta = nil
            Task { await ReteJarvis.rifiuta(id: p.id) }
        }
        onChiudi?()
    }

    // MARK: microfono

    func toggleMicrofono() {
        if microfonoAcceso {
            // di nuovo il pulsante: quello che hai detto fin qui parte, se c'e'
            ascolto.chiudi(inviando: true, motivo: nil)
        } else {
            avviaMicrofono()
        }
    }

    private func avviaMicrofono() {
        guard !microfonoAcceso, !microfonoInApertura else { return }
        ferma()
        messaggio = nil
        erroreGrave = false
        trascritto = ""
        pezzi = []
        microfonoInApertura = true
        ascolto.avvia(lingua: lingua, vocabolario: vocabolario())
        // se l'ascolto si e' rifiutato subito, `onChiuso` ha gia' spento la spia
    }

    private func vocabolario() -> [String] {
        var parole = Set<String>(["Plancia", "Claude", "Codex", "Jarvis", "riepilogo",
                                  "lavagna", "recap"])
        for p in Archivio.condiviso.progetti {
            if let n = p.name { parole.insert(n) }
            if let k = p.key { parole.insert(k.replacingOccurrences(of: "-", with: " ")) }
        }
        return Array(parole)
    }

    // MARK: una frase

    func invia(_ testo: String) {
        let t = testo.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count > 1 else { return }
        // La scheda aperta resta finche' il server non risponde: un "si" detto a voce non la
        // conferma, e il server lo rimanda al pulsante lasciandola dov'e'.
        ferma()
        trascritto = t
        pezzi = []
        contaPezzi = 0
        messaggio = nil
        erroreGrave = false
        haParlato = false
        elabora = true
        voce.nuovaRisposta()
        Log.write("jarvis: frase (\(t.count) caratteri)")
        compito = Task { [weak self] in await self?.turno(t) }
    }

    private func turno(_ t: String) async {
        var finale: EsitoJarvis?
        do {
            for try await ev in ReteJarvis.flusso(testo: t, lingua: lingua) {
                if Task.isCancelled { return }
                switch ev.tipo {
                case "testo":
                    contaPezzi += 1
                    pezzi.append(Pezzo(id: contaPezzi, testo: ev.testo, arrivo: Date()))
                case "frase":
                    haParlato = true
                    parla = true
                    voce.accoda(ev.dire)
                case "fine":
                    finale = ev.esito
                default:
                    break
                }
            }
        } catch is CancellationError {
            return
        } catch {
            if Task.isCancelled { return }
            elabora = false
            voce.ferma()
            avvisa(error.localizedDescription, grave: true)
            return
        }
        if Task.isCancelled { return }
        elabora = false
        guard let e = finale else { return voce.finito() }
        applica(e)
    }

    private func applica(_ e: EsitoJarvis) {
        if e.tipo == "interrotto" { return voce.finito() }
        // Quello che il server ha detto per intero vince su quello che e' scorso: e' identico
        // salvo la riga della proposta, che il server toglie prima.
        if !e.risposta.isEmpty, e.risposta != risposta {
            pezzi = [Pezzo(id: contaPezzi + 1, testo: e.risposta, arrivo: Date.distantPast)]
        }
        if e.tipo != "attende" {
            if let vecchia = proposta, e.proposta?.id != vecchia.id {
                Task { await ReteJarvis.rifiuta(id: vecchia.id) }
            }
            proposta = e.proposta
        }
        if !haParlato, !e.muto, !e.daDire.isEmpty {
            haParlato = true
            parla = true
            voce.accoda(e.daDire)
        }
        if let a = e.azione { eseguiAzione(a) }
        voce.finito()
    }

    private func eseguiAzione(_ a: AzioneJarvis) {
        switch a.tipo {
        case "velocita":
            if let p = a.passo { VoceJarvis.velocita += p }
        case "ferma":
            // "basta": tace e si chiude
            voce.ferma()
            parla = false
            onChiudi?()
        default:
            onAzione?(a)
        }
    }

    private func laVoceHaFinito() {
        parla = false
        livello.valore = 0
        // La conversazione continua e' l'unico caso in cui il microfono si riapre da solo: e' una
        // scelta tua, spenta di serie, e la spia si vede. Con una scheda aperta non si riapre mai.
        if Preferenze.conversazione, proposta == nil, !elabora, !microfonoAcceso, !confermaInCorso,
           messaggio == nil, !JarvisProva.attivo {
            avviaMicrofono()
        }
    }

    // MARK: la scheda

    /// SOLO dal pulsante Conferma.
    func conferma() {
        guard let p = proposta, !confermaInCorso else { return }
        confermaInCorso = true
        Log.write("jarvis: conferma \(p.azione)")
        Task { [weak self] in
            guard let self = self else { return }
            defer { self.confermaInCorso = false }
            do {
                let e = try await ReteJarvis.conferma(id: p.id, lingua: self.lingua)
                self.proposta = nil
                self.contaPezzi += 1
                self.pezzi = [Pezzo(id: self.contaPezzi, testo: e.risposta, arrivo: Date())]
                if e.eseguita != true { self.avvisa(e.risposta, grave: false) }
                if !e.daDire.isEmpty {
                    self.voce.nuovaRisposta()
                    self.parla = true
                    self.voce.accoda(e.daDire)
                    self.voce.finito()
                }
                if e.eseguita == true, let a = e.azione { self.eseguiAzione(a) }
            } catch is CancellationError {
                return
            } catch {
                self.avvisa(error.localizedDescription, grave: false)
            }
        }
    }

    func rifiuta() {
        guard let p = proposta else { return }
        proposta = nil
        Task { await ReteJarvis.rifiuta(id: p.id) }
    }

    // MARK: fermare

    /// Esc: prima ferma quello che sta succedendo; se non succede niente e c'e' una scheda,
    /// la butta; se non c'e' niente, chiude il pannello.
    func esc() {
        escRicevuti += 1
        if inAttivita { ferma() }
        else if proposta != nil { rifiuta() }
        else { chiudi() }
    }

    /// Ferma microfono, voce e richiesta al server. Non tocca la scheda.
    func ferma() {
        compito?.cancel()
        compito = nil
        ascolto.ferma()
        microfonoAcceso = false
        microfonoInApertura = false
        voce.ferma()
        parla = false
        if elabora {
            elabora = false
            Task { await ReteJarvis.ferma() }
        }
        livello.valore = 0
    }

    // MARK: messaggi

    func avvisa(_ testo: String, grave: Bool) {
        messaggio = testo
        erroreGrave = grave
    }

    func preferenzeCambiate() {
        versionePreferenze += 1
        voce.prepara(lingua: lingua, neurale: neuraleNoto, kokoroNo: kokoroNoNoto)
        rileggiVoce()
    }
}
