import Foundation

enum NetworkError: LocalizedError {
    case httpError(Int, String)
    case badURL

    var errorDescription: String? {
        switch self {
        case .httpError(let code, let body): return "HTTP \(code): \(body)"
        case .badURL: return "Invalid URL"
        }
    }
}

class NetworkClient {
    static let shared = NetworkClient()

    var baseURL: String {
        UserDefaults.standard.string(forKey: "backendURL") ?? "http://192.168.1.100:50001"
    }

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .useDefaultKeys
        return d
    }()

    private func checkStatus(_ response: URLResponse, _ data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200...299).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw NetworkError.httpError(http.statusCode, body)
        }
    }

    func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: baseURL + path) else { throw NetworkError.badURL }
        let (data, response) = try await URLSession.shared.data(from: url)
        try checkStatus(response, data)
        return try decoder.decode(T.self, from: data)
    }

    func post<B: Encodable, T: Decodable>(_ path: String, body: B) async throws -> T {
        guard let url = URL(string: baseURL + path) else { throw NetworkError.badURL }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await URLSession.shared.data(for: req)
        try checkStatus(response, data)
        return try decoder.decode(T.self, from: data)
    }

    func delete(_ path: String) async throws {
        guard let url = URL(string: baseURL + path) else { throw NetworkError.badURL }
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        let (data, response) = try await URLSession.shared.data(for: req)
        try checkStatus(response, data)
    }

    func healthCheck() async -> Bool {
        guard let url = URL(string: baseURL + "/health") else { return false }
        do {
            let (_, response) = try await URLSession.shared.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}
