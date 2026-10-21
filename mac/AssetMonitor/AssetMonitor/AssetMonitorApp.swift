import SwiftUI

@main
struct AssetMonitorApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 900, minHeight: 560)
        }
        .defaultSize(width: 1100, height: 700)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("数据") {
                Button("刷新当前源") {
                    NotificationCenter.default.post(name: .assetMonitorRefresh, object: nil)
                }
                .keyboardShortcut("r", modifiers: [.command])
            }
        }

        Settings {
            Form {
                LabeledContent("数据源") {
                    Text("https://ai862.github.io/asset-monitor/")
                        .textSelection(.enabled)
                }
                Text("缓存目录：~/Library/Application Support/AssetMonitor/")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(20)
            .frame(width: 420)
        }
    }
}

extension Notification.Name {
    static let assetMonitorRefresh = Notification.Name("assetMonitorRefresh")
}
