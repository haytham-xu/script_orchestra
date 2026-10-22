import Foundation

// The backend stores content either as a plain string or as a blocks array.
// This wrapper safely decodes both forms into a display string.
struct FlexibleContent: Codable {
    let text: String

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let str = try? container.decode(String.self) {
            text = str
        } else if let blocks = try? container.decode([[String: String]].self) {
            text = blocks.compactMap { $0["content"] ?? $0["text"] }.joined(separator: "\n")
        } else {
            text = ""
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(text)
    }
}

struct Fragment: Codable, Identifiable {
    let id: Int
    let content: FlexibleContent?
    let note: String?
    let kind: String?
    let header: String?
    let created_at: String
    let updated_at: String
    let label_ids: [Int]

    var displayContent: String { content?.text ?? "" }
}

struct KVLabel: Codable, Identifiable {
    let id: Int
    let name: String
    let color: String
}

struct FragmentListResponse: Codable {
    let fragments: [Fragment]
}

struct LabelListResponse: Codable {
    let labels: [KVLabel]
}

struct QueryResult: Codable, Identifiable {
    let id: Int
    let content: FlexibleContent?
    let note: String?
    let header: String?
    let score: Double?

    var displayContent: String { content?.text ?? "" }
}

struct QueryResponse: Codable {
    let results: [QueryResult]
}

struct CreateFragmentRequest: Codable {
    let content: String
    let note: String?
    let kind: String?
    let label_ids: [Int]
}

struct CreateFragmentResponse: Codable {
    let fragment: Fragment
}
