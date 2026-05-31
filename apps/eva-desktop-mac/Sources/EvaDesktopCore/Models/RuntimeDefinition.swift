import Foundation

public enum RuntimeKey: String, CaseIterable, Codable, Identifiable, Sendable {
    case openclaw
    case hermes
    case missionControl = "paperclip"
    case openDesign = "opendesign"
    case liveBrowser = "browser"
    case terminal
    case creativeStudio = "creative_studio"

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
            title: "evaOS (OpenClaw)",
            subtitle: "Main Eva agent dashboard and chat runtime.",
            systemImage: "bubble.left.and.bubble.right"
        ),
        RuntimeDefinition(
            key: .hermes,
            title: "evaOS (Hermes)",
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
            systemImage: "paintpalette"
        ),
        RuntimeDefinition(
            key: .liveBrowser,
            title: "Shared Browser",
            subtitle: "Shared browser for working with Eva on your evaOS server.",
            systemImage: "globe"
        ),
        RuntimeDefinition(
            key: .terminal,
            title: "Terminal",
            subtitle: "Terminal access to your private evaOS server.",
            systemImage: "terminal"
        ),
        RuntimeDefinition(
            key: .creativeStudio,
            title: "Creative Studio",
            subtitle: "Open the customer ComfyUI workspace through the evaOS gateway.",
            systemImage: "paintbrush.pointed"
        )
    ]

    public static func definition(for key: RuntimeKey) -> RuntimeDefinition {
        all.first { $0.key == key } ?? all[0]
    }

    public static func visibleRuntimes(canAccessAdminRuntimes: Bool) -> [RuntimeDefinition] {
        all.filter { !$0.requiresAdmin || canAccessAdminRuntimes }
    }

    public static func isBrokeredRuntime(_ key: RuntimeKey) -> Bool {
        switch key {
        case .openclaw, .hermes, .missionControl, .openDesign, .liveBrowser, .terminal, .creativeStudio:
            return true
        }
    }

    public static func externalURL(for key: RuntimeKey) -> URL? {
        switch key {
        case .openclaw, .hermes, .missionControl, .openDesign, .liveBrowser, .terminal, .creativeStudio:
            return nil
        }
    }

    public static func providerAuthRuntime(for url: URL) -> RuntimeKey {
        let host = (url.host ?? "").lowercased()
        let path = url.path.lowercased()
        let urlText = url.absoluteString.lowercased()

        if host.hasPrefix("browser-") || host.hasPrefix("shared-browser-") || path.contains("browser") || urlText.contains("novnc") {
            return .liveBrowser
        }

        return .liveBrowser
    }
}
