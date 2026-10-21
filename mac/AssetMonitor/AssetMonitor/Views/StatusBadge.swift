import SwiftUI

struct StatusBadge: View {
    let status: String?

    var body: some View {
        if let status, !status.isEmpty {
            Text(status)
                .font(.caption2.weight(.semibold))
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .foregroundStyle(foreground)
                .background(background, in: Capsule())
        }
    }

    private var foreground: Color {
        switch status {
        case "可下": return Color.green
        case "待核": return Color.orange
        case "SRC速报": return Color.green
        case "赏金技巧": return Color.orange
        case "推荐流": return Color.purple
        default: return Color.secondary
        }
    }

    private var background: Color {
        foreground.opacity(0.18)
    }
}
