import Foundation
import Observation

@Observable
class KnowledgeVaultService {
    var fragments: [Fragment] = []
    var labels: [KVLabel] = []
    var searchResults: [QueryResult] = []
    var isLoading = false
    var error: String? = nil

    private let client = NetworkClient.shared

    func loadFragments() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response: FragmentListResponse = try await client.get("/knowledge-vault/fragments")
            fragments = response.fragments
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadLabels() async {
        do {
            let response: LabelListResponse = try await client.get("/knowledge-vault/labels")
            labels = response.labels
        } catch {
            self.error = error.localizedDescription
        }
    }

    func createFragment(_ req: CreateFragmentRequest) async throws {
        let response: CreateFragmentResponse = try await client.post("/knowledge-vault/fragments", body: req)
        fragments.insert(response.fragment, at: 0)
    }

    func deleteFragment(_ id: Int) async {
        do {
            try await client.delete("/knowledge-vault/fragments/\(id)")
            fragments.removeAll { $0.id == id }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func search(_ q: String) async {
        guard !q.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            searchResults = []
            return
        }
        let encoded = q.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? q
        do {
            let response: QueryResponse = try await client.get("/knowledge-vault/query?q=\(encoded)&top_k=20")
            searchResults = response.results
        } catch {
            self.error = error.localizedDescription
        }
    }
}
