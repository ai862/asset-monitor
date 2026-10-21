import Foundation

enum RemoteStoreError: LocalizedError {
    case invalidURL
    case httpStatus(Int)
    case invalidJSON(String)
    case noCache

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "无效的 URL"
        case .httpStatus(let code): return "HTTP \(code)"
        case .invalidJSON(let msg): return msg
        case .noCache: return "无可用缓存"
        }
    }
}

@MainActor
final class RemoteStore: ObservableObject {
    static let shared = RemoteStore()

    let baseURL = URL(string: "https://ai862.github.io/asset-monitor/")!

    @Published private(set) var config: AppConfig?
    @Published private(set) var recordsBySource: [String: [AssetRecord]] = [:]
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?
    @Published private(set) var offlineBanner: String?
    @Published private(set) var lastUpdatedAt: String?

    private let session: URLSession
    private let cacheDirectory: URL
    private var memoryCache: [String: [AssetRecord]] = [:]

    private init() {
        let memoryCapacity = 6 * 1024 * 1024
        let diskCapacity = 32 * 1024 * 1024
        let urlCache = URLCache(memoryCapacity: memoryCapacity, diskCapacity: diskCapacity)
        let config = URLSessionConfiguration.default
        config.urlCache = urlCache
        config.requestCachePolicy = .returnCacheDataElseLoad
        config.timeoutIntervalForRequest = 20
        config.timeoutIntervalForResource = 40
        self.session = URLSession(configuration: config)

        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = support.appendingPathComponent("AssetMonitor", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        self.cacheDirectory = dir
    }

    func bootstrap() async {
        await refreshAll(forceNetwork: true)
    }

    func refreshAll(forceNetwork: Bool = true) async {
        isLoading = true
        lastError = nil
        defer { isLoading = false }
        do {
            let cfg = try await loadConfig(forceNetwork: forceNetwork)
            config = cfg
            lastUpdatedAt = cfg.updatedAt
            if let selected = cfg.sources.first {
                _ = try await loadSource(selected, forceNetwork: forceNetwork)
            }
        } catch {
            lastError = error.localizedDescription
            if config == nil, let cached = try? loadCachedConfig() {
                config = cached
                lastUpdatedAt = cached.updatedAt
                offlineBanner = "离线缓存 · \(cached.updatedAt)"
            }
        }
    }

    func ensureSource(_ source: SourceConfig, forceNetwork: Bool = false) async {
        if !forceNetwork, recordsBySource[source.id] != nil { return }
        isLoading = true
        lastError = nil
        defer { isLoading = false }
        do {
            _ = try await loadSource(source, forceNetwork: forceNetwork)
        } catch {
            lastError = error.localizedDescription
            if recordsBySource[source.id] == nil,
               let cached = try? loadCachedRecords(sourceId: source.id) {
                recordsBySource[source.id] = cached
                memoryCache[source.id] = cached
                offlineBanner = "离线缓存 · \(source.name)"
            }
        }
    }

    func reloadSelected(_ source: SourceConfig) async {
        offlineBanner = nil
        await ensureSource(source, forceNetwork: true)
        // Also refresh config metadata
        if let cfg = try? await loadConfig(forceNetwork: true) {
            config = cfg
            lastUpdatedAt = cfg.updatedAt
        }
    }

    // MARK: - Loaders

    func loadConfig(forceNetwork: Bool) async throws -> AppConfig {
        let url = baseURL.appendingPathComponent("config.json")
        let data: Data
        do {
            data = try await fetchData(url, forceNetwork: forceNetwork)
            try writeCache(named: "config.json", data: data)
            offlineBanner = nil
        } catch {
            if let cached = try? Data(contentsOf: cacheDirectory.appendingPathComponent("config.json")) {
                offlineBanner = "离线缓存 · config"
                data = cached
            } else {
                throw error
            }
        }
        return try JSONDecoder().decode(AppConfig.self, from: data)
    }

    func loadSource(_ source: SourceConfig, forceNetwork: Bool) async throws -> [AssetRecord] {
        if !forceNetwork, let mem = memoryCache[source.id] {
            recordsBySource[source.id] = mem
            return mem
        }
        let url = resolve(source.data)
        let data: Data
        do {
            data = try await fetchData(url, forceNetwork: forceNetwork)
            try writeCache(named: "data-\(source.id).json", data: data)
            offlineBanner = nil
        } catch {
            if let cached = try? Data(contentsOf: cacheFile(named: "data-\(source.id).json")) {
                offlineBanner = "离线缓存 · \(source.name)"
                data = cached
            } else {
                throw error
            }
        }
        let records = try AssetRecord.decodeArray(from: data)
        memoryCache[source.id] = records
        recordsBySource[source.id] = records
        return records
    }

    // MARK: - Helpers

    private func resolve(_ relative: String) -> URL {
        let trimmed = relative.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return baseURL.appendingPathComponent(trimmed)
    }

    private func fetchData(_ url: URL, forceNetwork: Bool) async throws -> Data {
        var request = URLRequest(url: url)
        request.cachePolicy = forceNetwork ? .reloadIgnoringLocalCacheData : .returnCacheDataElseLoad
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw RemoteStoreError.httpStatus(http.statusCode)
        }
        return data
    }

    private func cacheFile(named: String) -> URL {
        cacheDirectory.appendingPathComponent(named)
    }

    private func writeCache(named: String, data: Data) throws {
        try data.write(to: cacheFile(named: named), options: .atomic)
    }

    private func loadCachedConfig() throws -> AppConfig {
        let data = try Data(contentsOf: cacheFile(named: "config.json"))
        return try JSONDecoder().decode(AppConfig.self, from: data)
    }

    private func loadCachedRecords(sourceId: String) throws -> [AssetRecord] {
        let data = try Data(contentsOf: cacheFile(named: "data-\(sourceId).json"))
        return try AssetRecord.decodeArray(from: data)
    }
}
