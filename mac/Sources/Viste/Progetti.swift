// Segnaposto. La vista vera di questa sezione la scrive un altro agente e sostituisce
// solo questo file: il guscio (Guscio/Radice.swift) crea `VistaProgetti()` e non sa altro.
// Il modello da seguire e' Viste/Task.swift. I dati stanno nello Store
// (Core/ArchivioDati.swift), letto con @Environment(Archivio.self); le stringhe passano
// da tr("italiano", "english").

import SwiftUI

struct VistaProgetti: View {
    @Environment(Archivio.self) private var archivio

    var body: some View {
        ContentUnavailableView(
            tr("Progetti", "Projects"),
            systemImage: "folder",
            description: Text(archivio.raggiungibile ? "" : archivio.sottotitolo))
    }
}
