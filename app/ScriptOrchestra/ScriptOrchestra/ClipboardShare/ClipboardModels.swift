import Foundation

struct ClipboardItem: Codable, Identifiable {
    let id: Int
    let content: String
    let source: String
    let timestamp: String
    let length: Int
}

struct AddClipboardRequest: Codable {
    let content: String
    let source: String
}

struct ClearResponse: Codable {
    let message: String
    let count: Int
}
