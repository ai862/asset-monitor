import Foundation

/// Flexible record backed by a JSON object with Chinese keys.
struct AssetRecord: Identifiable, Hashable {
    let raw: [String: JSONValue]

    var id: String {
        string("去重键")
            ?? string("产品")
            ?? UUID().uuidString
    }

    func string(_ key: String) -> String? {
        guard let value = raw[key] else { return nil }
        switch value {
        case .string(let s):
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            return t.isEmpty ? nil : t
        case .number(let n):
            if n.rounded() == n { return String(Int(n)) }
            return String(n)
        case .bool(let b):
            return b ? "是" : "否"
        case .null:
            return nil
        case .array, .object:
            return nil
        }
    }

    func bool(_ key: String) -> Bool? {
        guard let value = raw[key] else { return nil }
        switch value {
        case .bool(let b): return b
        case .string(let s):
            let lower = s.lowercased()
            if ["true", "yes", "1", "是"].contains(lower) { return true }
            if ["false", "no", "0", "否"].contains(lower) { return false }
            return nil
        case .number(let n): return n != 0
        default: return nil
        }
    }

    func int(_ key: String) -> Int? {
        guard let value = raw[key] else { return nil }
        switch value {
        case .number(let n): return Int(n)
        case .string(let s): return Int(s)
        default: return nil
        }
    }

    func stringArray(_ key: String) -> [String] {
        guard let value = raw[key] else { return [] }
        switch value {
        case .array(let items):
            return items.compactMap { item in
                switch item {
                case .string(let s):
                    let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
                    return t.isEmpty ? nil : t
                case .object(let obj):
                    if case .string(let title)? = obj["title"] {
                        return title
                    }
                    return nil
                default:
                    return nil
                }
            }
        case .string(let s):
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            return t.isEmpty ? [] : [t]
        default:
            return []
        }
    }

    /// Objects like 开工前先看: [{title, url}, ...]
    func linkItems(_ key: String) -> [(title: String, url: String)] {
        guard let value = raw[key], case .array(let items) = value else { return [] }
        return items.compactMap { item in
            guard case .object(let obj) = item else { return nil }
            let title: String
            if case .string(let t)? = obj["title"] {
                title = t
            } else {
                return nil
            }
            let url: String
            if case .string(let u)? = obj["url"] {
                url = u
            } else {
                return nil
            }
            guard !title.isEmpty, !url.isEmpty else { return nil }
            return (title, url)
        }
    }

    func displayURL(_ key: String) -> URL? {
        guard let s = string(key), let url = URL(string: s),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else { return nil }
        return url
    }

    /// Sorted keys for debug / leftover fields (skips empties).
    var nonEmptyKeys: [String] {
        raw.keys.sorted().filter { string($0) != nil || !stringArray($0).isEmpty || linkItems($0).count > 0 || bool($0) != nil }
    }

    static func decodeArray(from data: Data) throws -> [AssetRecord] {
        let root = try JSONDecoder().decode(JSONValue.self, from: data)
        guard case .array(let items) = root else {
            throw RemoteStoreError.invalidJSON("期望 JSON 数组")
        }
        return items.compactMap { item in
            guard case .object(let obj) = item else { return nil }
            return AssetRecord(raw: obj)
        }
    }
}

enum JSONValue: Codable, Hashable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let b = try? container.decode(Bool.self) {
            self = .bool(b)
        } else if let i = try? container.decode(Int.self) {
            self = .number(Double(i))
        } else if let d = try? container.decode(Double.self) {
            self = .number(d)
        } else if let s = try? container.decode(String.self) {
            self = .string(s)
        } else if let a = try? container.decode([JSONValue].self) {
            self = .array(a)
        } else if let o = try? container.decode([String: JSONValue].self) {
            self = .object(o)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let s): try container.encode(s)
        case .number(let n): try container.encode(n)
        case .bool(let b): try container.encode(b)
        case .object(let o): try container.encode(o)
        case .array(let a): try container.encode(a)
        case .null: try container.encodeNil()
        }
    }
}
