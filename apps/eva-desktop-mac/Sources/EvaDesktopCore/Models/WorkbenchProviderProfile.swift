import Foundation

public enum WorkbenchProviderKey: String, CaseIterable, Codable, Identifiable, Sendable {
    case openAICodex = "openai_codex"
    case openClaw = "openclaw"
    case hermes = "hermes"

    public var id: String { rawValue }
}

public enum WorkbenchProviderReadiness: String, Codable, Sendable {
    case ready
    case needsLogin = "needs_login"
    case planned
}

public struct WorkbenchProviderProfile: Codable, Equatable, Identifiable, Sendable {
    public let key: WorkbenchProviderKey
    public let title: String
    public let subtitle: String
    public let readiness: WorkbenchProviderReadiness
    public let rawSecretsStoredInWorkbench: Bool
    public let capabilities: [String]

    public var id: WorkbenchProviderKey { key }

    public init(
        key: WorkbenchProviderKey,
        title: String,
        subtitle: String,
        readiness: WorkbenchProviderReadiness,
        rawSecretsStoredInWorkbench: Bool = false,
        capabilities: [String]
    ) {
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.readiness = readiness
        self.rawSecretsStoredInWorkbench = rawSecretsStoredInWorkbench
        self.capabilities = capabilities
    }
}

public enum WorkbenchProviderCatalog {
    public static let profiles: [WorkbenchProviderProfile] = [
        WorkbenchProviderProfile(
            key: .openAICodex,
            title: "OpenAI / Codex",
            subtitle: "Connect once, then broker account availability to evaOS agents without storing raw provider secrets in Workbench.",
            readiness: .needsLogin,
            capabilities: ["Codex remote control readiness", "OpenAI profile status", "VM grant metadata"]
        ),
        WorkbenchProviderProfile(
            key: .openClaw,
            title: "OpenClaw",
            subtitle: "Uses the evaOS VM session and provider grants exposed by the control plane.",
            readiness: .planned,
            capabilities: ["Provider discovery", "Agent skill defaults", "Shared Browser preference"]
        ),
        WorkbenchProviderProfile(
            key: .hermes,
            title: "Hermes",
            subtitle: "Uses the same provider grant contract as OpenClaw; no separate credential backend.",
            readiness: .planned,
            capabilities: ["Provider discovery", "Adapter parity", "Session recovery"]
        )
    ]
}
