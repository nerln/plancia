// Notifiche: l'app chiede il permesso all'avvio, come la 1.x. Le notifiche vere le
// pubblicano i lanci in background e il riepilogo (vedi Voce.swift e jarvis.swift).

import UserNotifications

enum Notifiche {
    static func richiedi() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }
}
