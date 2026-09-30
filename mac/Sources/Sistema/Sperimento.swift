// TEMPORANEO: interruttori di esperimento per la misura (PLANCIA_SP=notoolbar,noinspector,righe).
import AppKit
import SwiftUI

enum Sper {
    static let v: Set<String> = Set((ProcessInfo.processInfo.environment["PLANCIA_SP"] ?? "").split(separator: ",").map(String.init))
    static var senzaToolbar: Bool { v.contains("notoolbar") }
    static var senzaInspector: Bool { v.contains("noinspector") }
    static var titoloFisso: Bool { v.contains("titolo") }
    static var barraId: Bool { v.contains("barraid") }
}

