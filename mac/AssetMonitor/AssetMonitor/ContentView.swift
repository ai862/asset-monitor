import SwiftUI

struct ContentView: View {
    @ObservedObject private var store = RemoteStore.shared
    @State private var selectedSourceID: String?
    @State private var selectedRecordID: AssetRecord.ID?
    @State private var searchText = ""
    @State private var statusFilter: String?

    private var selectedSource: SourceConfig? {
        store.config?.sources.first { $0.id == selectedSourceID }
            ?? store.config?.sources.first
    }

    private var records: [AssetRecord] {
        guard let id = selectedSource?.id else { return [] }
        return store.recordsBySource[id] ?? []
    }

    private var selectedRecord: AssetRecord? {
        records.first { $0.id == selectedRecordID }
    }

    var body: some View {
        NavigationSplitView {
            SidebarView(store: store, selection: $selectedSourceID)
                .frame(minWidth: 180)
        } content: {
            if let source = selectedSource {
                AssetListView(
                    source: source,
                    records: records,
                    selection: $selectedRecordID,
                    searchText: $searchText,
                    statusFilter: $statusFilter
                )
                .frame(minWidth: 280)
            } else {
                ContentUnavailableView("选择数据源", systemImage: "sidebar.left")
            }
        } detail: {
            if let source = selectedSource, let record = selectedRecord {
                AssetDetailView(record: record, source: source)
            } else {
                ContentUnavailableView(
                    records.isEmpty ? "暂无数据" : "选择一条记录",
                    systemImage: "doc.text.magnifyingglass",
                    description: Text(store.isLoading ? "加载中…" : "从左侧列表点选")
                )
            }
        }
        .searchable(text: $searchText, placement: .toolbar, prompt: "搜索 产品 / 厂商 / 备注…")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task {
                        if let source = selectedSource {
                            await store.reloadSelected(source)
                        } else {
                            await store.refreshAll(forceNetwork: true)
                        }
                    }
                } label: {
                    Label("刷新", systemImage: "arrow.clockwise")
                }
                .disabled(store.isLoading)
                .keyboardShortcut("r", modifiers: [.command])
            }
        }
        .overlay(alignment: .top) {
            if let banner = store.offlineBanner {
                Text(banner)
                    .font(.caption)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(.yellow.opacity(0.85), in: Capsule())
                    .padding(.top, 8)
            }
        }
        .task {
            await store.bootstrap()
            if selectedSourceID == nil {
                selectedSourceID = store.config?.sources.first?.id
            }
        }
        .onChange(of: selectedSourceID) { _, newValue in
            selectedRecordID = nil
            statusFilter = nil
            searchText = ""
            guard let newValue,
                  let source = store.config?.sources.first(where: { $0.id == newValue }) else { return }
            Task { await store.ensureSource(source) }
        }
        .onChange(of: store.config) { _, newConfig in
            if selectedSourceID == nil {
                selectedSourceID = newConfig?.sources.first?.id
            }
        }
        .tint(selectedSource?.accentColor)
        .onReceive(NotificationCenter.default.publisher(for: .assetMonitorRefresh)) { _ in
            Task {
                if let source = selectedSource {
                    await store.reloadSelected(source)
                } else {
                    await store.refreshAll(forceNetwork: true)
                }
            }
        }
    }
}
