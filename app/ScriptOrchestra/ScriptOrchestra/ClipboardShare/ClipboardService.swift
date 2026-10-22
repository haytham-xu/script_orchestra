import Foundation
import Observation

@Observable
class ClipboardService {
    var items: [ClipboardItem] = []
    var latest: ClipboardItem? = nil
    var isLoading = false
    var error: String? = nil

    private var pollingTask: Task<Void, Never>? = nil
    private let client = NetworkClient.shared

    func loadHistory() async {
        isLoading = true
        defer { isLoading = false }
        do {
            items = try await client.get("/clipboard/history?limit=50")
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadLatest() async {
        do {
            latest = try await client.get("/clipboard/latest")
        } catch let e as NetworkError {
            // 404 means clipboard is empty — not a real error
            if case .httpError(404, _) = e { return }
            self.error = e.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }
    }

    func addItem(_ content: String) async {
        do {
            let body = AddClipboardRequest(content: content, source: "ios")
            let newItem: ClipboardItem = try await client.post("/clipboard/add", body: body)
            latest = newItem
            items.insert(newItem, at: 0)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func clearAll() async {
        do {
            try await client.delete("/clipboard/clear")
            items = []
            latest = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    func startPolling() {
        stopPolling()
        pollingTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                if !Task.isCancelled {
                    await loadLatest()
                }
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }
}
