import Foundation

public enum RuntimeKey: String, CaseIterable, Codable, Identifiable, Sendable {
    case openclaw
    case hermes
    case missionControl = "paperclip"
    case openDesign = "opendesign"
    case liveBrowser = "browser"
    case terminal

    public var id: String { rawValue }
}

public enum RuntimeAvailability: String, Codable, Sendable {
    case enabled
    case disabled
    case comingSoon = "coming-soon"
    case degraded
}

public struct RuntimeDefinition: Identifiable, Equatable, Sendable {
    public let key: RuntimeKey
    public let title: String
    public let subtitle: String
    public let systemImage: String
    public let availability: RuntimeAvailability
    public let requiresAdmin: Bool

    public var id: RuntimeKey { key }

    public init(
        key: RuntimeKey,
        title: String,
        subtitle: String,
        systemImage: String,
        availability: RuntimeAvailability = .enabled,
        requiresAdmin: Bool = false
    ) {
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.availability = availability
        self.requiresAdmin = requiresAdmin
    }

    public static let all: [RuntimeDefinition] = [
        RuntimeDefinition(
            key: .openclaw,
            title: "evaOS / OpenClaw",
            subtitle: "Main Eva agent dashboard and chat runtime.",
            systemImage: "bubble.left.and.bubble.right"
        ),
        RuntimeDefinition(
            key: .hermes,
            title: "evaOS / Hermes",
            subtitle: "Hermes agent workspace on the same evaOS VM.",
            systemImage: "sparkles"
        ),
        RuntimeDefinition(
            key: .missionControl,
            title: "Mission Control",
            subtitle: "Goals, jobs, approvals, and agent coordination.",
            systemImage: "checklist"
        ),
        RuntimeDefinition(
            key: .openDesign,
            title: "OpenDesign",
            subtitle: "Design workspace and visual product building.",
            systemImage: "paintpalette",
            availability: .comingSoon
        ),
        RuntimeDefinition(
            key: .liveBrowser,
            title: "Live Browser",
            subtitle: "Watch and test the VM browser Eva uses.",
            systemImage: "globe"
        ),
        RuntimeDefinition(
            key: .terminal,
            title: "Terminal",
            subtitle: "Admin/service terminal access through evaOS.",
            systemImage: "terminal",
            requiresAdmin: true
        )
    ]

    public static func definition(for key: RuntimeKey) -> RuntimeDefinition {
        all.first { $0.key == key } ?? all[0]
    }

    public static func isBrokeredRuntime(_ key: RuntimeKey) -> Bool {
        switch key {
        case .openclaw, .hermes, .missionControl, .liveBrowser, .terminal:
            return true
        case .openDesign:
            return false
        }
    }
}
