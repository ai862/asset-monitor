import Foundation
import SwiftUI

struct AppConfig: Codable, Hashable {
    var title: String
    var updatedAt: String
    var sources: [SourceConfig]
}

struct SourceConfig: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var data: String
    var notion: String
    var accent: String

    var notionURL: URL? {
        let trimmed = notion.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return URL(string: trimmed)
    }

    var accentColor: Color {
        AccentColor.from(hex: accent)
    }
}
