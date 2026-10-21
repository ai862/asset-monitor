import SwiftUI

struct SidebarView: View {
    @ObservedObject var store: RemoteStore
    @Binding var selection: String?

    var body: some View {
        List(selection: $selection) {
            Section("数据源") {
                if let sources = store.config?.sources {
                    ForEach(sources) { source in
                        Label {
                            HStack {
                                Text(source.name)
                                Spacer()
                                if let count = store.recordsBySource[source.id]?.count {
                                    Text("\(count)")
                                        .font(.caption2.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color.secondary.opacity(0.15), in: Capsule())
                                }
                            }
                        } icon: {
                            Image(systemName: iconName(for: source.id))
                                .foregroundStyle(source.accentColor)
                        }
                        .tag(source.id)
                    }
                } else {
                    Text("加载中…")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle(store.config?.title ?? "资产监控中心")
    }

    private func iconName(for id: String) -> String {
        switch id {
        case "ai-web": return "cpu"
        case "ics": return "gearshape.2"
        case "xinchuang": return "building.2"
        case "intel": return "newspaper"
        default: return "tray.full"
        }
    }
}
