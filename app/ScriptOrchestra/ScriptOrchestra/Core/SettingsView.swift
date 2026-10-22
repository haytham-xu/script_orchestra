import SwiftUI

struct SettingsView: View {
    @State private var backendURL: String = ""
    @State private var showAlert = false
    @State private var alertTitle = ""
    @State private var alertMessage = ""
    @State private var isTesting = false

    var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("Backend Connection")) {
                    TextField("http://192.168.x.x:50001", text: $backendURL)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .onChange(of: backendURL) { _, newValue in
                            UserDefaults.standard.set(newValue, forKey: "backendURL")
                        }
                }

                Section {
                    Button {
                        Task { await testConnection() }
                    } label: {
                        HStack {
                            Text("Test Connection")
                            Spacer()
                            if isTesting {
                                ProgressView()
                            }
                        }
                    }
                    .disabled(isTesting)
                }

                Section(header: Text("About")) {
                    LabeledContent("Version", value: "1.0")
                    LabeledContent("Tools", value: "Clipboard Share, Knowledge Vault")
                }
            }
            .navigationTitle("Settings")
            .onAppear {
                backendURL = UserDefaults.standard.string(forKey: "backendURL") ?? "http://192.168.1.100:50001"
            }
            .alert(alertTitle, isPresented: $showAlert) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(alertMessage)
            }
        }
    }

    private func testConnection() async {
        isTesting = true
        let ok = await NetworkClient.shared.healthCheck()
        isTesting = false
        alertTitle = ok ? "Connected" : "Connection Failed"
        alertMessage = ok
            ? "Successfully reached \(backendURL)"
            : "Could not reach \(backendURL). Check the IP and port."
        showAlert = true
    }
}
