import SwiftUI

enum AccentColor {
    static func from(hex: String) -> Color {
        var h = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if h.hasPrefix("#") { h.removeFirst() }
        guard h.count == 6 || h.count == 8, let value = UInt64(h, radix: 16) else {
            return Color.accentColor
        }
        let hasAlpha = h.count == 8
        let a = hasAlpha ? Double((value >> 24) & 0xFF) / 255.0 : 1.0
        let r = Double((value >> 16) & 0xFF) / 255.0
        let g = Double((value >> 8) & 0xFF) / 255.0
        let b = Double(value & 0xFF) / 255.0
        return Color(.sRGB, red: r, green: g, blue: b, opacity: a)
    }
}
