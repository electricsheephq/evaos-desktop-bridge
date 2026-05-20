import AppKit
import SwiftUI

extension Color {
    static let electricSheepCyan = Color(red: 0.55, green: 0.92, blue: 0.94)
    static let electricSheepAmber = Color(red: 0.91, green: 0.70, blue: 0.35)
}

struct BrandWordmark: View {
    @ViewBuilder
    var body: some View {
        if let image = NSImage.electricSheepWordmark {
            Image(nsImage: image)
                .resizable()
                .scaledToFit()
                .accessibilityLabel("ElectricSheep")
        } else {
            Text("ELECTRICSHEEP")
                .font(.system(size: 15, weight: .semibold, design: .monospaced))
                .foregroundStyle(Color.electricSheepCyan)
        }
    }
}

struct RuntimeIconBadge: View {
    let systemImage: String
    var tint: Color = .electricSheepCyan

    var body: some View {
        Image(systemName: systemImage)
            .font(.system(size: 17, weight: .semibold))
            .foregroundStyle(tint)
            .frame(width: 34, height: 34)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(tint.opacity(0.22), lineWidth: 1)
            )
    }
}

struct StatusPill: View {
    let title: String
    let systemImage: String
    var tint: Color = .electricSheepCyan

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.system(.caption2, design: .monospaced).weight(.semibold))
            .lineLimit(1)
            .textCase(.uppercase)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .foregroundStyle(tint)
            .background(tint.opacity(0.10), in: Capsule())
            .overlay(Capsule().stroke(tint.opacity(0.25), lineWidth: 1))
    }
}

private extension NSImage {
    static var electricSheepWordmark: NSImage? {
        guard let url = Bundle.main.url(forResource: "electric-sheep-wordmark", withExtension: "png") else {
            return nil
        }
        return NSImage(contentsOf: url)
    }
}
