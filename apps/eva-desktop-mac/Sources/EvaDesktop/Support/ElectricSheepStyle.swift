import AppKit
import SwiftUI

extension Color {
    static let electricSheepCyan = Color(red: 0.55, green: 0.92, blue: 0.94)
    static let electricSheepAmber = Color(red: 0.91, green: 0.70, blue: 0.35)
    static let electricSheepGold = Color(red: 0.76, green: 0.51, blue: 0.23)
    static let electricSheepGoldSoft = Color(red: 0.91, green: 0.71, blue: 0.35)
    static let electricSheepCanvas = Color(red: 0.09, green: 0.08, blue: 0.07)
    static let electricSheepCanvasEdge = Color(red: 0.06, green: 0.05, blue: 0.04)
    static let electricSheepSurface = Color(red: 0.12, green: 0.10, blue: 0.08)
    static let electricSheepSurfaceRaised = Color(red: 0.16, green: 0.14, blue: 0.12)
    static let electricSheepLine = Color.white.opacity(0.10)
    static let electricSheepLineWarm = Color.electricSheepGoldSoft.opacity(0.22)
    static let electricSheepPrimaryText = Color(red: 0.96, green: 0.94, blue: 0.90)
    static let electricSheepSecondaryText = Color(red: 0.70, green: 0.68, blue: 0.63)
    static let electricSheepMutedText = Color(red: 0.50, green: 0.48, blue: 0.43)
    static let electricSheepSuccess = Color(red: 0.49, green: 0.83, blue: 0.66)
    static let electricSheepDanger = Color(red: 0.92, green: 0.34, blue: 0.31)
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
