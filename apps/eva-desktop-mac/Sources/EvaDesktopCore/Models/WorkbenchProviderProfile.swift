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

public enum WorkbenchProviderStatus: String, Codable, Sendable {
    case connected
    case needsLogin = "needs_login"
    case planned
    case revoked
    case error

    public var displayText: String {
        switch self {
        case .connected:
            return "Connected"
        case .needsLogin:
            return "Needs login"
        case .planned:
            return "Unavailable"
        case .revoked:
            return "Revoked"
        case .error:
            return "Blocked"
        }
    }
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

public struct WorkbenchProviderProfileState: Codable, Equatable, Identifiable, Sendable {
    public let key: WorkbenchProviderKey
    public let title: String
    public let subtitle: String
    public let status: WorkbenchProviderStatus
    public let active: Bool
    public let rawSecretsStoredInWorkbench: Bool
    public let capabilities: [String]
    public let usageSummary: String?
    public let grantHandle: String?
    public let lastValidatedAt: Date?

    public var id: WorkbenchProviderKey { key }

    public var hasConnectionProof: Bool {
        status == .connected && !rawSecretsStoredInWorkbench && lastValidatedAt != nil
    }

    public init(
        key: WorkbenchProviderKey,
        title: String,
        subtitle: String,
        status: WorkbenchProviderStatus,
        active: Bool = false,
        rawSecretsStoredInWorkbench: Bool = false,
        capabilities: [String],
        usageSummary: String? = nil,
        grantHandle: String? = nil,
        lastValidatedAt: Date? = nil
    ) {
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.status = status
        self.active = active
        self.rawSecretsStoredInWorkbench = rawSecretsStoredInWorkbench
        self.capabilities = capabilities
        self.usageSummary = usageSummary
        self.grantHandle = grantHandle
        self.lastValidatedAt = lastValidatedAt
    }

    enum CodingKeys: String, CodingKey {
        case key = "provider_key"
        case title
        case subtitle
        case status
        case active
        case rawSecretsStoredInWorkbench = "raw_secrets_stored_in_workbench"
        case capabilities
        case usageSummary = "usage_summary"
        case grantHandle = "grant_handle"
        case lastValidatedAt = "last_validated_at"
    }
}

public struct WorkbenchProviderProfilesResponse: Codable, Equatable, Sendable {
    public let profiles: [WorkbenchProviderProfileState]
    public let activeProviderKey: WorkbenchProviderKey?
    public let rawSecretsStoredInWorkbench: Bool

    enum CodingKeys: String, CodingKey {
        case profiles = "provider_profiles"
        case activeProviderKey = "active_provider_key"
        case rawSecretsStoredInWorkbench = "raw_secrets_stored_in_workbench"
    }
}

public enum WorkbenchProviderHubSummary {
    public static func statusText(for response: WorkbenchProviderProfilesResponse) -> String {
        statusText(
            rawSecretsStoredInWorkbench: response.rawSecretsStoredInWorkbench,
            profiles: response.profiles
        )
    }

    public static func statusText(
        rawSecretsStoredInWorkbench: Bool,
        profiles: [WorkbenchProviderProfileState]
    ) -> String {
        if rawSecretsStoredInWorkbench || profiles.contains(where: \.rawSecretsStoredInWorkbench) {
            return "Blocked"
        }
        if profiles.contains(where: \.hasConnectionProof) {
            return "Ready"
        }
        if profiles.contains(where: { $0.status == .connected }) {
            return "Needs verification"
        }
        if profiles.contains(where: { $0.status == .needsLogin }) {
            return "Needs login"
        }
        if profiles.contains(where: { $0.status == .revoked }) {
            return "Revoked"
        }
        if profiles.contains(where: { $0.status == .planned }) {
            return "Unavailable"
        }
        if profiles.contains(where: { $0.status == .error }) {
            return "Blocked"
        }
        return "Unchecked"
    }
}

public enum WorkbenchProviderCatalog {
    public static let profiles: [WorkbenchProviderProfile] = [
        WorkbenchProviderProfile(
            key: .openAICodex,
            title: "OpenAI / Codex",
            subtitle: "Connect once, then broker account availability to evaOS agents without storing raw provider secrets in Workbench.",
            readiness: .needsLogin,
            capabilities: ["Codex remote control readiness", "OpenAI profile status", "OpenClaw VM grant metadata"]
        )
    ]

    public static let defaultStates: [WorkbenchProviderProfileState] = profiles.map { profile in
        WorkbenchProviderProfileState(
            key: profile.key,
            title: profile.title,
            subtitle: profile.subtitle,
            status: {
                switch profile.readiness {
                case .ready:
                    return .connected
                case .needsLogin:
                    return .needsLogin
                case .planned:
                    return .planned
                }
            }(),
            capabilities: profile.capabilities
        )
    }
}
