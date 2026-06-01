import Foundation

public enum RuntimeKey: String, CaseIterable, Codable, Identifiable, Sendable {
    case openclaw
    case hermes
    case missionControl = "paperclip"
    case openDesign = "opendesign"
    case liveBrowser = "browser"
    case terminal
    case creativeStudio = "creative_studio"
    case teamChat = "team_chat"

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
            title: "Eva Workspace",
            subtitle: "Main Eva dashboard and chat workspace.",
            systemImage: "bubble.left.and.bubble.right"
        ),
        RuntimeDefinition(
            key: .hermes,
            title: "Agent Workspace",
            subtitle: "Second agent workspace on the same evaOS server.",
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
            title: "Design Workspace",
            subtitle: "Design workspace and visual product building.",
            systemImage: "paintpalette"
        ),
        RuntimeDefinition(
            key: .liveBrowser,
            title: "Business Browser",
            subtitle: "Shared browser for sign-ins, CAPTCHA, and web tasks Eva can help with.",
            systemImage: "globe"
        ),
        RuntimeDefinition(
            key: .terminal,
            title: "Terminal",
            subtitle: "Terminal access to your private evaOS server.",
            systemImage: "terminal",
            requiresAdmin: true
        ),
        RuntimeDefinition(
            key: .creativeStudio,
            title: "Creative Studio",
            subtitle: "Open the hosted Comfy creative workspace in Workbench.",
            systemImage: "paintbrush.pointed"
        ),
        RuntimeDefinition(
            key: .teamChat,
            title: "Team Chat",
            subtitle: "Company chat for people and assigned Eva agents.",
            systemImage: "message.badge"
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
        case .openclaw, .hermes, .missionControl, .openDesign, .liveBrowser, .terminal, .teamChat:
            return true
        case .creativeStudio:
            return false
        }
    }

    public static func externalURL(for key: RuntimeKey) -> URL? {
        switch key {
        case .openclaw, .hermes, .missionControl, .openDesign, .liveBrowser, .terminal, .teamChat:
            return nil
        case .creativeStudio:
            return URL(string: "https://www.comfy.org/cloud")
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
