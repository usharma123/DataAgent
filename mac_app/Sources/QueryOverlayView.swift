import SwiftUI

@MainActor
final class QueryViewModel: ObservableObject {
    @Published var query: String = ""
    @Published var answer: String = ""
    @Published var citations: [Citation] = []
    @Published var loading: Bool = false
    @Published var errorText: String = ""

    private let apiClient = APIClient()

    func submit() async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        loading = true
        errorText = ""
        do {
            let response = try await apiClient.ask(question: trimmed, sources: [])
            answer = response.answer ?? ""
            citations = response.citations
            if let error = response.error {
                errorText = error
            }
        } catch {
            errorText = error.localizedDescription
        }
        loading = false
    }
}

struct QueryOverlayView: View {
    @ObservedObject var model: QueryViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Vault Personal Agent")
                .font(.headline)

            TextField("Ask your data...", text: $model.query)
                .textFieldStyle(.roundedBorder)
                .onSubmit {
                    Task { await model.submit() }
                }

            HStack {
                Button("Ask") {
                    Task { await model.submit() }
                }
                .keyboardShortcut(.return, modifiers: [])

                if model.loading {
                    ProgressView()
                }
            }

            if !model.errorText.isEmpty {
                Text(model.errorText)
                    .foregroundStyle(.red)
                    .font(.caption)
            }

            if !model.answer.isEmpty {
                Text(model.answer)
                    .font(.body)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !model.citations.isEmpty {
                Divider()
                Text("Citations")
                    .font(.subheadline)
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(model.citations) { citation in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("[\(citation.source)] \(citation.title ?? "Untitled")")
                                    .font(.caption).bold()
                                Text(citation.snippet)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .frame(maxHeight: 220)
            }
        }
        .padding(16)
        .frame(width: 640, height: 460)
    }
}
