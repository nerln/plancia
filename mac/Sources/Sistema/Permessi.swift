// Microfono e dettatura, chiesti da un clic dentro la finestra (vedi il commento).

import AppKit
import AVFoundation
import Speech

extension DelegatoApp {
    /// Chiede microfono e dettatura partendo da un clic dentro la finestra.
    ///
    /// Non è un giro inutile. La richiesta fatta dal pannello vocale, che è una
    /// finestra che di proposito non attiva l'app, spesso non fa comparire
    /// niente: il sistema mostra quelle finestre solo a un'app davanti, e la
    /// riconosce tale se la richiesta arriva dopo una cosa che hai fatto tu.
    /// Qui si porta l'app davanti, si spiega cosa sta per succedere, e solo dopo
    /// il tuo sì si chiede al sistema.
    @objc func chiediPermessi() {
        apriFinestra()

        let a = NSAlert()
        a.messageText = Conf.lang == "en" ? "Turn on the voice"
                      : (Conf.lang == "es" ? "Activar la voz" : "Attiva la voce")
        a.informativeText = Conf.lang == "en"
            ? "macOS will ask twice: for the microphone and for dictation. Both stay on this Mac: recognition runs locally and no audio is ever sent anywhere."
            : (Conf.lang == "es"
               ? "macOS te lo preguntará dos veces: micrófono y dictado. Los dos se quedan en este Mac: el reconocimiento es local y no se envía ningún audio."
               : "macOS te lo chiederà due volte: microfono e dettatura. Restano tutti e due su questo Mac, il riconoscimento è locale e nessun audio esce di qui.")
        a.addButton(withTitle: Conf.lang == "en" ? "Continue" : "Continua")
        a.addButton(withTitle: Conf.lang == "en" ? "Not now" : "Non ora")
        let scelta = a.runModal()
        Log.write("permessi: risposta alla finestra \(scelta.rawValue)")
        guard scelta == .alertFirstButtonReturn else { return }

        AVCaptureDevice.requestAccess(for: .audio) { micro in
            Log.write("permessi: microfono \(micro)")
            SFSpeechRecognizer.requestAuthorization { voce in
                Log.write("permessi: dettatura \(voce.rawValue)")
                DispatchQueue.main.async {
                    let fatto = micro && voce == .authorized
                    let b = NSAlert()
                    b.messageText = fatto
                        ? (Conf.lang == "en" ? "Voice is on" : "La voce è accesa")
                        : (Conf.lang == "en" ? "Still missing something" : "Manca ancora qualcosa")
                    b.informativeText = fatto
                        ? (Conf.lang == "en" ? "Press option space anywhere to talk to it."
                                             : "Premi opzione spazio da qualsiasi app per parlarci.")
                        : (Conf.lang == "en"
                           ? "Open System Settings, Privacy and Security, and allow Plancia under Microphone and Speech Recognition."
                           : "Apri Impostazioni di sistema, Privacy e sicurezza, e autorizza Plancia sotto Microfono e Riconoscimento vocale.")
                    b.addButton(withTitle: "OK")
                    if !fatto { b.addButton(withTitle: Conf.lang == "en" ? "Open settings" : "Apri le impostazioni") }
                    if b.runModal() == .alertSecondButtonReturn,
                       let u = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") {
                        NSWorkspace.shared.open(u)
                    }
                    if fatto { self.apriJarvis() }
                }
            }
        }
    }
}
