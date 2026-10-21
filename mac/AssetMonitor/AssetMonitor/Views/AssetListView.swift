import SwiftUI

struct AssetListView: View {
    let source: SourceConfig
    let records: [AssetRecord]
    @Binding var selection: AssetRecord.ID?
    @Binding var searchText: String
    @Binding var statusFilter: String?

    private var allStatuses: [String] {
        let set = Set(records.compactMap { $0.string("状态") })
        return set.sorted()
    }

    private var filtered: [AssetRecord] {
        records.filter { record in
            if let statusFilter, !statusFilter.isEmpty {
                guard record.string("状态") == statusFilter else { return false }
            }
            let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !q.isEmpty else { return true }
            let hay = [
                record.string("产品"),
                record.string("厂商"),
                record.string("备注"),
                record.string("去重键"),
                record.string("状态"),
                record.string("批次"),
                record.string("类型")
            ].compactMap { $0 }.joined(separator: "\n")
            return hay.localizedCaseInsensitiveContains(q)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if !allStatuses.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        chip("全部", selected: statusFilter == nil) {
                            statusFilter = nil
                        }
                        ForEach(allStatuses, id: \.self) { status in
                            chip(status, selected: statusFilter == status) {
                                statusFilter = status
                            }
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                }
                Divider()
            }

            List(filtered, selection: $selection) { record in
                AssetRowView(record: record, sourceId: source.id)
                    .tag(record.id)
            }
            .listStyle(.inset)
        }
        .navigationTitle(source.name)
        .navigationSubtitle(subtitle)
    }

    private var subtitle: String {
        let total = records.count
        let shown = filtered.count
        if shown == total {
            return "\(total) 条"
        }
        return "\(shown) / \(total) 条"
    }

    @ViewBuilder
    private func chip(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.caption)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(selected ? source.accentColor.opacity(0.25) : Color.secondary.opacity(0.12), in: Capsule())
                .foregroundStyle(selected ? source.accentColor : .primary)
        }
        .buttonStyle(.plain)
    }
}

struct AssetRowView: View {
    let record: AssetRecord
    let sourceId: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(record.string("产品") ?? "（无标题）")
                    .font(.body.weight(.medium))
                    .lineLimit(2)
                Spacer(minLength: 8)
                StatusBadge(status: record.string("状态"))
            }
            HStack(spacing: 8) {
                if let vendor = record.string("厂商") {
                    Text(vendor)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                if sourceId == "intel", let batch = record.string("批次") {
                    Text(batch)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                if sourceId == "ai-web", let difficulty = record.string("搭建难度") {
                    Text("难度·\(difficulty)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                if let type = record.string("类型"), sourceId != "intel" {
                    Text(type)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 2)
    }
}
