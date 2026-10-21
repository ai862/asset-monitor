import SwiftUI
import AppKit

struct AssetDetailView: View {
    let record: AssetRecord
    let source: SourceConfig

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                basicSection
                linksSection
                if hasLaunchGuide {
                    launchSection
                }
                if let remark = record.string("备注") {
                    section("备注") {
                        Text(remark)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                if let value = record.string("实用价值"), !value.isEmpty {
                    section("实用价值") {
                        Text(value)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                extrasSection
            }
            .padding(20)
            .frame(maxWidth: 720, alignment: .leading)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .toolbar {
            if let notion = source.notionURL {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        NSWorkspace.shared.open(notion)
                    } label: {
                        Label("打开 Notion", systemImage: "link")
                    }
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(record.string("产品") ?? "（无标题）")
                .font(.title2.weight(.semibold))
                .textSelection(.enabled)
            HStack(spacing: 10) {
                if let vendor = record.string("厂商") {
                    Text(vendor)
                        .foregroundStyle(.secondary)
                }
                StatusBadge(status: record.string("状态"))
                if let batch = record.string("批次") {
                    Text("批次 \(batch)")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
        }
    }

    private var basicSection: some View {
        section("基本信息") {
            Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 16, verticalSpacing: 8) {
                field("厂商", record.string("厂商"))
                field("状态", record.string("状态"))
                field("类型", record.string("类型"))
                field("语言", record.string("语言"))
                field("行业", record.string("行业"))
                field("地区", record.string("地区"))
                field("Stars", record.string("Stars"))
                field("搭建难度", record.string("搭建难度"))
                field("资产号", record.string("资产号"))
                field("首次写入", record.string("首次写入"))
                field("批次", record.string("批次"))
                field("去重键", record.string("去重键"))
                field("Web服务", record.bool("Web服务").map { $0 ? "是" : "否" })
                if !record.stringArray("部署方式").isEmpty {
                    field("部署方式", record.stringArray("部署方式").joined(separator: "、"))
                }
                field("下载条件", record.string("下载条件"))
                field("研判状态", record.string("研判状态"))
                field("研判时间", record.string("研判时间"))
            }
        }
    }

    @ViewBuilder
    private var linksSection: some View {
        let pairs: [(String, String)] = [
            ("官网", "官网"),
            ("文档", "文档"),
            ("GitHub", "GitHub"),
            ("下载页", "下载页"),
            ("DeepWiki", "DeepWiki"),
            ("指引URL", "指引URL")
        ]
        let present = pairs.compactMap { label, key -> (String, URL)? in
            guard let url = record.displayURL(key) else { return nil }
            return (label, url)
        }
        let preReads = record.linkItems("开工前先看")
        if !present.isEmpty || !preReads.isEmpty {
            section("链接") {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(present, id: \.0) { label, url in
                        linkRow(label, url: url)
                    }
                    ForEach(Array(preReads.enumerated()), id: \.offset) { _, item in
                        if let url = URL(string: item.url) {
                            linkRow(item.title, url: url)
                        }
                    }
                }
            }
        }
    }

    private var hasLaunchGuide: Bool {
        record.string("启动指引") != nil || record.string("研判摘要") != nil
            || !record.stringArray("建议追问").isEmpty
            || !record.stringArray("已知坑").isEmpty
            || record.string("成功标准") != nil
            || record.string("推荐启动") != nil
    }

    private var launchSection: some View {
        section("启动指引") {
            VStack(alignment: .leading, spacing: 12) {
                if let summary = record.string("研判摘要") {
                    labeledBlock("研判摘要", summary)
                }
                if let guide = record.string("启动指引") {
                    labeledBlock("指引", guide)
                }
                if let rec = record.string("推荐启动") {
                    labeledBlock("推荐启动", rec)
                }
                if let ok = record.string("成功标准") {
                    labeledBlock("成功标准", ok)
                }
                let asks = record.stringArray("建议追问")
                if !asks.isEmpty {
                    labeledBlock("建议追问", asks.map { "· \($0)" }.joined(separator: "\n"))
                }
                let pits = record.stringArray("已知坑")
                if !pits.isEmpty {
                    labeledBlock("已知坑", pits.map { "· \($0)" }.joined(separator: "\n"))
                }
            }
        }
    }

    private var extrasSection: some View {
        let known: Set<String> = [
            "产品", "厂商", "状态", "类型", "语言", "行业", "地区", "Stars", "GitHub",
            "官网", "文档", "下载页", "DeepWiki", "指引URL", "Web服务", "部署方式",
            "下载条件", "去重键", "备注", "资产号", "首次写入", "批次", "搭建难度",
            "研判状态", "研判时间", "启动指引", "研判摘要", "推荐启动", "指引URL",
            "开工前先看", "建议追问", "已知坑", "成功标准", "实用价值",
            "下载核验时间", "下载核验来源"
        ]
        let extras = record.nonEmptyKeys.filter { !known.contains($0) }
        return Group {
            if !extras.isEmpty {
                section("其他字段") {
                    Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 16, verticalSpacing: 8) {
                        ForEach(extras, id: \.self) { key in
                            if let s = record.string(key) {
                                field(key, s)
                            } else {
                                let arr = record.stringArray(key)
                                if !arr.isEmpty {
                                    field(key, arr.joined(separator: "、"))
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Building blocks

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
            content()
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
        }
    }

    @ViewBuilder
    private func field(_ label: String, _ value: String?) -> some View {
        if let value, !value.isEmpty {
            GridRow {
                Text(label)
                    .foregroundStyle(.secondary)
                    .frame(minWidth: 72, alignment: .trailing)
                Text(value)
                    .textSelection(.enabled)
            }
        }
    }

    private func labeledBlock(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func linkRow(_ title: String, url: URL) -> some View {
        Button {
            NSWorkspace.shared.open(url)
        } label: {
            HStack {
                Image(systemName: "link")
                Text(title)
                Spacer()
                Text(url.host ?? url.absoluteString)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
        .buttonStyle(.plain)
        .foregroundStyle(source.accentColor)
    }
}
