// La forma d'onda di Jarvis: viva mentre ascolta (il livello vero del microfono), mentre pensa
// (un respiro lento) e mentre parla (il livello della voce). Sono nastri sottili che si
// muovono: l'ampiezza segue il livello con attacco veloce e rilascio lento, cosi' non scatta.
// Con "Riduci movimento" al posto dei nastri c'e' una barra che segue il livello e basta.

import SwiftUI

struct OndaJarvis: View {
    enum Tipo { case quieta, ascolta, pensa, parla }

    let tipo: Tipo
    let livello: LivelloAudio
    let colore: Color
    var altezza: CGFloat = 72
    /// Il pannello e' nascosto: niente da disegnare.
    var pausa = false

    @Environment(\.accessibilityReduceMotion) private var riduciMovimento
    @State private var memoria = Memoria()

    /// Lo stato del disegno fra un fotogramma e l'altro. Una classe: si modifica dentro il Canvas.
    final class Memoria {
        var valore = 0.0
        var ultimo = 0.0
    }

    var body: some View {
        Group {
            if riduciMovimento {
                barra
            } else {
                TimelineView(.animation(minimumInterval: tipo == .quieta ? 1.0 / 24 : 1.0 / 60, paused: pausa)) { tl in
                    Canvas { ctx, size in
                        disegna(&ctx, size, tl.date.timeIntervalSinceReferenceDate)
                    }
                }
            }
        }
        .frame(height: altezza)
        // i nastri nascono e muoiono ai lati, e il bagliore non finisce contro un bordo
        .mask(LinearGradient(stops: [.init(color: .clear, location: 0), .init(color: .black, location: 0.09),
                                     .init(color: .black, location: 0.91), .init(color: .clear, location: 1)],
                             startPoint: .leading, endPoint: .trailing))
        .accessibilityElement()
        .accessibilityLabel(Text(etichetta))
    }

    private var etichetta: String {
        switch tipo {
        case .quieta: return Lingua.risolvi() == "it" ? "Jarvis a riposo" : "Jarvis is idle"
        case .ascolta: return Lingua.risolvi() == "it" ? "Jarvis ascolta" : "Jarvis is listening"
        case .pensa: return Lingua.risolvi() == "it" ? "Jarvis sta pensando" : "Jarvis is thinking"
        case .parla: return Lingua.risolvi() == "it" ? "Jarvis sta parlando" : "Jarvis is speaking"
        }
    }

    private var barra: some View {
        GeometryReader { g in
            Capsule().fill(colore.opacity(0.25))
                .overlay(alignment: .leading) {
                    Capsule().fill(colore).frame(width: max(8, g.size.width * livelloDiRiposo))
                }
                .frame(height: 8)
                .frame(maxHeight: .infinity)
        }
    }

    private var livelloDiRiposo: Double {
        switch tipo {
        case .quieta: return 0.05
        case .pensa: return 0.3
        default: return max(0.06, livello.valore)
        }
    }

    private func disegna(_ ctx: inout GraphicsContext, _ size: CGSize, _ t: Double) {
        let bersaglio: Double
        switch tipo {
        case .quieta: bersaglio = 0.05 + 0.02 * sin(t * 1.4)
        case .pensa: bersaglio = 0.24 + 0.1 * sin(t * 2.2)
        case .ascolta, .parla: bersaglio = max(0.04, livello.valore)
        }
        // attacco veloce, rilascio lento
        let dt = min(0.1, max(0.001, t - memoria.ultimo))
        memoria.ultimo = t
        let k = bersaglio > memoria.valore ? 1 - pow(0.0005, dt) : 1 - pow(0.12, dt)
        memoria.valore += (bersaglio - memoria.valore) * k
        let ampiezza = memoria.valore

        let meta = size.height / 2
        let massimo = size.height * 0.46
        let strati: [(freq: Double, vel: Double, fase: Double, peso: Double, opacita: Double, spessore: CGFloat)] = [
            (1.6, 1.4, 0.0, 1.00, 0.95, 2.4),
            (2.3, -1.1, 1.7, 0.72, 0.55, 1.8),
            (3.1, 1.9, 3.1, 0.50, 0.38, 1.4),
            (4.4, -1.6, 4.4, 0.32, 0.26, 1.1),
        ]
        var lucido = ctx
        lucido.addFilter(.blur(radius: 7))
        for (i, s) in strati.enumerated() {
            var percorso = Path()
            let passi = Int(size.width / 3)
            for n in 0...passi {
                let x = size.width * CGFloat(n) / CGFloat(passi)
                let u = Double(n) / Double(passi)
                // finestra: i nastri nascono e muoiono ai lati
                let finestra = pow(sin(.pi * u), 1.6)
                let onda = sin(u * .pi * 2 * s.freq + t * s.vel * (tipo == .pensa ? 0.6 : 1) + s.fase)
                    * (0.55 + 0.45 * sin(u * .pi * 2 * 0.7 + t * 0.8 + Double(i)))
                let y = meta + CGFloat(onda * finestra * ampiezza * s.peso) * massimo
                if n == 0 { percorso.move(to: CGPoint(x: x, y: y)) }
                else { percorso.addLine(to: CGPoint(x: x, y: y)) }
            }
            let stile = StrokeStyle(lineWidth: s.spessore, lineCap: .round, lineJoin: .round)
            if i == 0 { lucido.stroke(percorso, with: .color(colore.opacity(0.7)), style: StrokeStyle(lineWidth: 5, lineCap: .round)) }
            ctx.stroke(percorso, with: .color(colore.opacity(s.opacita)), style: stile)
        }
    }
}
