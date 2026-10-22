import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            ClipboardView()
                .tabItem {
                    SwiftUI.Label("Clipboard", systemImage: "doc.on.clipboard")
                }
            KnowledgeVaultView()
                .tabItem {
                    SwiftUI.Label("Knowledge", systemImage: "books.vertical")
                }
            SettingsView()
                .tabItem {
                    SwiftUI.Label("Settings", systemImage: "gear")
                }
        }
    }
}
