# 资产监控（macOS 原生客户端）

低内存的 SwiftUI macOS 应用，直接拉取 [asset-monitor](https://ai862.github.io/asset-monitor/) 的静态 JSON，**不嵌入浏览器 / 不用 Electron / 不用 WKWebView**。

- 显示名：`资产监控`
- Bundle ID：`com.ai862.AssetMonitor`
- 最低系统：macOS 14 Sonoma
- 数据源：`https://ai862.github.io/asset-monitor/config.json` 及各 `data/*.json`

## 在 Mac 上运行（约 1 分钟）

1. 把本仓库里的 `mac/AssetMonitor/` 拷到 Mac（或直接 clone 整个 `monitor-hub`）。
2. 双击打开 `AssetMonitor.xcodeproj`（需已安装 Xcode 15+）。
3. 左上角 Scheme 选 **AssetMonitor**，目标选 **My Mac**。
4. 按 `⌘R` 运行。首次会请求网络拉取 JSON；断网时自动读 `~/Library/Application Support/AssetMonitor/` 缓存。
5. 若提示签名：Target → Signing & Capabilities → Team 选个人账号，或保持 `Sign to Run Locally`（`CODE_SIGN_IDENTITY = "-"`）。

命令行亦可（在 Mac 上）：

```bash
cd mac/AssetMonitor
xcodebuild -scheme AssetMonitor -configuration Debug -derivedDataPath ./DerivedData build
open ./DerivedData/Build/Products/Debug/资产监控.app
```

> 本工程在 Linux 开发机上**无法交叉编译** macOS GUI，只能在装有 Xcode 的 Mac 上构建。

## 功能对照网页版

| 能力 | 说明 |
|------|------|
| 侧栏数据源 | AI Web / 工控 Web / 信创 Web / 每日情报，带条数徽章 |
| 搜索 | 产品 / 厂商 / 备注 / 去重键 / 状态 |
| 状态筛选 | 顶部胶囊（可下、待核、SRC速报、赏金技巧、推荐流…） |
| 详情 | 基本信息、链接（系统浏览器打开）、备注；AI Web 含启动指引 / 研判摘要 |
| Notion | 源配置有 notion 时显示「打开 Notion」；每日情报无 notion 则隐藏 |
| 刷新 | 工具栏按钮或菜单「数据 → 刷新当前源」/`⌘R` |
| 离线 | 失败时用 Application Support 上次成功 JSON，顶部黄条提示 |

## 架构（低内存）

- `RemoteStore`：单一内存缓存 `recordsBySource`；`URLSession` + `URLCache`（内存约 6MB，磁盘 32MB）。
- `AssetRecord`：用灵活的 `JSONValue` 字典承载中文键，不预加载图片。
- 列表用 SwiftUI `List`（懒加载），无 WebView。
- 主题跟随系统深浅色；侧栏强调色取自 `config.json` 的 `accent`。

```
AssetMonitor/
  AssetMonitorApp.swift      # 入口、菜单、设置页
  ContentView.swift          # NavigationSplitView 三栏
  Models/Config.swift
  Models/AssetRecord.swift   # 灵活 Codable
  Services/RemoteStore.swift # 拉取 + 磁盘缓存
  Services/AccentColor.swift
  Views/SidebarView.swift
  Views/AssetListView.swift
  Views/AssetDetailView.swift
  Views/StatusBadge.swift
  Resources/Assets.xcassets
```

## 未来可选（未实现）

- 菜单栏常驻 / 状态栏图标
- 新「每日情报」本地通知
- Sparkle 自动更新
- 自定义 App Icon

## 许可

与上级 `monitor-hub` 仓库一致；仅客户端壳，数据仍来自公开 GitHub Pages。
