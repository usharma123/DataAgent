import Foundation

struct PersonalAskRequest: Codable {
    let question: String
    let source_filters: [String]
    let include_debug: Bool
}

struct Citation: Codable, Identifiable {
    var id: String { citation_id }
    let citation_id: String
    let source: String
    let title: String?
    let snippet: String
    let author: String?
    let timestamp: String?
    let deep_link: String?
    let confidence: Double
}

struct PersonalAskResponse: Codable {
    let run_id: String
    let status: String
    let answer: String?
    let citations: [Citation]
    let missing_evidence: [String]
    let error: String?
}

@MainActor
final class APIClient {
    private let session = URLSession.shared
    private let baseURL: URL

    init(baseURL: URL = URL(string: "http://127.0.0.1:8000")!) {
        self.baseURL = baseURL
    }

    func ask(question: String, sources: [String]) async throws -> PersonalAskResponse {
        var request = URLRequest(url: baseURL.appendingPathComponent("/native/v1/personal/ask"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(PersonalAskRequest(question: question, source_filters: sources, include_debug: false))

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw NSError(domain: "DashSpotlight", code: 1, userInfo: [NSLocalizedDescriptionKey: "Request failed"])
        }
        return try JSONDecoder().decode(PersonalAskResponse.self, from: data)
    }
}
