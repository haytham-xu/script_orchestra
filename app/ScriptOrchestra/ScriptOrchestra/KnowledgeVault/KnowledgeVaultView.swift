import SwiftUI

struct KnowledgeVaultView: View {
    @State private var service = KnowledgeVaultService()
    @State private var selectedTab = 0
    @State private var captureContent = ""
    @State private var captureNote = ""
    @State private var selectedLabelIds: Set<Int> = []
    @State private var isSaving = false
    @State private var toastMessage: String? = nil
    @State private var searchQuery = ""
    @State private var selectedResult: QueryResult? = nil
    @State private var searchTask: Task<Void, Never>? = nil

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("Tab", selection: $selectedTab) {
                    Text("Capture").tag(0)
                    Text("Search").tag(1)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.vertical, 8)

                if selectedTab == 0 {
                    CaptureTab(
                        content: $captureContent,
                        note: $captureNote,
                        selectedLabelIds: $selectedLabelIds,
                        isSaving: isSaving,
                        labels: service.labels,
                        toastMessage: toastMessage,
                        onSave: saveFragment
                    )
                } else {
                    SearchTab(
                        query: $searchQuery,
                        results: service.searchResults,
                        isLoading: service.isLoading,
                        selectedResult: $selectedResult,
                        onSearch: { q in
                            searchTask?.cancel()
                            searchTask = Task {
                                try? await Task.sleep(for: .milliseconds(400))
                                if !Task.isCancelled { await service.search(q) }
                            }
                        }
                    )
                }
            }
            .navigationTitle("Knowledge Vault")
        }
        .task {
            await service.loadFragments()
            await service.loadLabels()
        }
    }

    private func saveFragment() {
        guard !captureContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        isSaving = true
        Task {
            do {
                let req = CreateFragmentRequest(
                    content: captureContent,
                    note: captureNote.isEmpty ? nil : captureNote,
                    kind: nil,
                    label_ids: Array(selectedLabelIds)
                )
                try await service.createFragment(req)
                captureContent = ""
                captureNote = ""
                selectedLabelIds = []
                showToast("Saved!")
            } catch {
                showToast("Save failed")
            }
            isSaving = false
        }
    }

    private func showToast(_ message: String) {
        toastMessage = message
        Task {
            try? await Task.sleep(for: .seconds(2))
            toastMessage = nil
        }
    }
}

private struct CaptureTab: View {
    @Binding var content: String
    @Binding var note: String
    @Binding var selectedLabelIds: Set<Int>
    let isSaving: Bool
    let labels: [KVLabel]
    let toastMessage: String?
    let onSave: () -> Void

    var body: some View {
        ZStack(alignment: .bottom) {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    TextEditor(text: $content)
                        .frame(minHeight: 160)
                        .padding(8)
                        .background(Color(.secondarySystemBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 10))

                    TextField("Note (optional)", text: $note)
                        .padding(10)
                        .background(Color(.secondarySystemBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 10))

                    if !labels.isEmpty {
                        LabelChipPicker(labels: labels, selected: $selectedLabelIds)
                    }

                    Button(action: onSave) {
                        HStack {
                            if isSaving { ProgressView().tint(.white) }
                            Text(isSaving ? "Saving..." : "Save")
                                .bold()
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Color.accentColor)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                    }
                    .disabled(isSaving || content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                .padding()
                .padding(.bottom, 60)
            }

            if let msg = toastMessage {
                Text(msg)
                    .font(.subheadline)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(.regularMaterial)
                    .clipShape(Capsule())
                    .padding(.bottom, 16)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: toastMessage)
    }
}

private struct LabelChipPicker: View {
    let labels: [KVLabel]
    @Binding var selected: Set<Int>

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Labels")
                .font(.caption)
                .foregroundStyle(.secondary)
            FlowLayout(spacing: 8) {
                ForEach(labels) { label in
                    let isSelected = selected.contains(label.id)
                    Button {
                        if isSelected { selected.remove(label.id) }
                        else { selected.insert(label.id) }
                    } label: {
                        Text(label.name)
                            .font(.caption)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(isSelected ? Color.accentColor : Color(.secondarySystemBackground))
                            .foregroundStyle(isSelected ? .white : .primary)
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct SearchTab: View {
    @Binding var query: String
    let results: [QueryResult]
    let isLoading: Bool
    @Binding var selectedResult: QueryResult?
    let onSearch: (String) -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search...", text: $query)
                    .autocorrectionDisabled()
                    .onChange(of: query) { _, newValue in onSearch(newValue) }
                if isLoading { ProgressView().padding(.leading, 4) }
            }
            .padding(10)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding(.horizontal)
            .padding(.vertical, 8)

            List(results) { result in
                Button {
                    selectedResult = result
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(result.displayContent)
                            .lineLimit(2)
                            .foregroundStyle(.primary)
                        if let score = result.score {
                            Text("Match: \(Int(score * 100))%")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .buttonStyle(.plain)
            }
            .listStyle(.plain)
            .overlay {
                if results.isEmpty && !query.isEmpty && !isLoading {
                    ContentUnavailableView("No Results", systemImage: "magnifyingglass", description: Text("Try a different search term"))
                }
            }
        }
        .sheet(item: $selectedResult) { result in
            ResultDetailSheet(result: result)
        }
    }
}

private struct ResultDetailSheet: View {
    let result: QueryResult
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let header = result.header {
                        Text(header).font(.headline)
                    }
                    Text(result.displayContent)
                    if let note = result.note {
                        Text(note)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
            }
            .navigationTitle("Fragment")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}

// Simple flow layout for label chips
private struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var currentX: CGFloat = 0
        var currentY: CGFloat = 0
        var lineHeight: CGFloat = 0

        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if currentX + size.width > maxWidth && currentX > 0 {
                currentY += lineHeight + spacing
                currentX = 0
                lineHeight = 0
            }
            currentX += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
        return CGSize(width: maxWidth, height: currentY + lineHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var currentX = bounds.minX
        var currentY = bounds.minY
        var lineHeight: CGFloat = 0

        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if currentX + size.width > bounds.maxX && currentX > bounds.minX {
                currentY += lineHeight + spacing
                currentX = bounds.minX
                lineHeight = 0
            }
            view.place(at: CGPoint(x: currentX, y: currentY), proposal: ProposedViewSize(size))
            currentX += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
    }
}
