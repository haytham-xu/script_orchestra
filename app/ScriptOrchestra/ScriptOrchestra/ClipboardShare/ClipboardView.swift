import SwiftUI
import UIKit

struct ClipboardView: View {
    @State private var service = ClipboardService()
    @State private var showAddSheet = false
    @State private var showClearConfirm = false
    @State private var newContent = ""
    @State private var toastMessage: String? = nil

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottom) {
                List {
                    if let latest = service.latest {
                        Section("Latest") {
                            LatestCard(item: latest) {
                                copyToClipboard(latest.content)
                            }
                        }
                    }

                    Section("History") {
                        if service.items.isEmpty && !service.isLoading {
                            Text("No items yet")
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(service.items) { item in
                                ClipboardRow(item: item) {
                                    copyToClipboard(item.content)
                                }
                            }
                        }
                    }
                }
                .refreshable {
                    await service.loadHistory()
                    await service.loadLatest()
                }
                .navigationTitle("Clipboard")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Clear All") { showClearConfirm = true }
                            .foregroundStyle(.red)
                    }
                    ToolbarItem(placement: .topBarLeading) {
                        if service.isLoading { ProgressView() }
                    }
                }
                .confirmationDialog("Clear all clipboard items?", isPresented: $showClearConfirm, titleVisibility: .visible) {
                    Button("Clear All", role: .destructive) {
                        Task { await service.clearAll() }
                    }
                }
                .sheet(isPresented: $showAddSheet) {
                    AddClipboardSheet(isPresented: $showAddSheet) { content in
                        Task { await service.addItem(content) }
                    }
                }

                // FAB
                Button {
                    newContent = ""
                    showAddSheet = true
                } label: {
                    Image(systemName: "plus")
                        .font(.title2.bold())
                        .foregroundStyle(.white)
                        .frame(width: 56, height: 56)
                        .background(Color.accentColor)
                        .clipShape(Circle())
                        .shadow(radius: 4)
                }
                .padding(.bottom, 16)

                // Toast
                if let msg = toastMessage {
                    Text(msg)
                        .font(.subheadline)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(.regularMaterial)
                        .clipShape(Capsule())
                        .padding(.bottom, 80)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(.easeInOut(duration: 0.25), value: toastMessage)
        }
        .task {
            await service.loadHistory()
            await service.loadLatest()
            service.startPolling()
        }
        .onDisappear {
            service.stopPolling()
        }
    }

    private func copyToClipboard(_ text: String) {
        UIPasteboard.general.string = text
        showToast("Copied!")
    }

    private func showToast(_ message: String) {
        toastMessage = message
        Task {
            try? await Task.sleep(for: .seconds(2))
            toastMessage = nil
        }
    }
}

private struct LatestCard: View {
    let item: ClipboardItem
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 6) {
                Text(item.content)
                    .lineLimit(4)
                    .multilineTextAlignment(.leading)
                    .foregroundStyle(.primary)
                HStack {
                    Text(item.timestamp)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("Tap to copy")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(12)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }
}

private struct ClipboardRow: View {
    let item: ClipboardItem
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 4) {
                Text(item.content)
                    .lineLimit(2)
                    .foregroundStyle(.primary)
                Text(item.timestamp)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .buttonStyle(.plain)
    }
}

private struct AddClipboardSheet: View {
    @Binding var isPresented: Bool
    @State private var content = ""
    let onSave: (String) -> Void

    var body: some View {
        NavigationStack {
            TextEditor(text: $content)
                .padding()
                .navigationTitle("Add Item")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Cancel") { isPresented = false }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Send") {
                            guard !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
                            onSave(content)
                            isPresented = false
                        }
                        .bold()
                        .disabled(content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
        }
        .presentationDetents([.medium, .large])
    }
}
