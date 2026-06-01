import Foundation

public enum WorkbenchProviderKey: String, CaseIterable, Codable, Identifiable, Sendable {
    case openAICodex = "openai_codex"
    case openClaw = "openclaw"
    case hermes = "hermes"
    case googleWorkspace = "google_workspace"
    case pipedream = "pipedream"
    case slack = "slack"
    case notion = "notion"
    case linear = "linear"
    case github = "github"

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
    case expired
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
        case .expired:
            return "Expired"
        case .error:
            return "Blocked"
        }
    }

    public init(from decoder: Decoder) throws {
        let rawValue = try decoder.singleValueContainer().decode(String.self)
        switch rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "connected":
            self = .connected
        case "needs_login", "needs_auth", "needs_input":
            self = .needsLogin
        case "planned", "unavailable", "coming_soon":
            self = .planned
        case "revoked", "disconnected":
            self = .revoked
        case "expired":
            self = .expired
        case "error", "blocked", "failed":
            self = .error
        default:
            self = .error
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}

public struct WorkbenchProviderGrantDisplay: Codable, Equatable, Sendable {
    public let accountLabel: String?
    public let lastCheckedAt: Date?

    public init(accountLabel: String? = nil, lastCheckedAt: Date? = nil) {
        self.accountLabel = accountLabel
        self.lastCheckedAt = lastCheckedAt
    }

    enum CodingKeys: String, CodingKey {
        case accountLabel = "account_label"
        case lastCheckedAt = "last_checked_at"
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
    public let schemaVersion: String?
    public let key: WorkbenchProviderKey
    public let title: String
    public let subtitle: String
    public let status: WorkbenchProviderStatus
    public let active: Bool
    public let rawSecretsStoredInWorkbench: Bool
    public let capabilities: [String]
    public let usageSummary: String?
    public let grantID: String?
    public let customerAccountID: String?
    public let ownerKind: String?
    public let ownerUserID: String?
    public let grantedScopes: [String]
    public let expiresAt: Date?
    public let grantHandle: String?
    public let revokeHandle: String?
    public let display: WorkbenchProviderGrantDisplay?
    public let sourcePointer: String?
    public let auditID: String?
    public let lastValidatedAt: Date?

    public var id: WorkbenchProviderKey { key }

    public var hasConnectionProof: Bool {
        status == .connected
            && !rawSecretsStoredInWorkbench
            && (lastValidatedAt != nil || grantHandle != nil || grantID != nil)
    }

    public var hasBrokeredGrant: Bool {
        status == .connected && !rawSecretsStoredInWorkbench && (grantHandle != nil || grantID != nil)
    }

    public var accountLabel: String? {
        display?.accountLabel
    }

    public init(
        schemaVersion: String? = nil,
        key: WorkbenchProviderKey,
        title: String,
        subtitle: String,
        status: WorkbenchProviderStatus,
        active: Bool = false,
        rawSecretsStoredInWorkbench: Bool = false,
        capabilities: [String],
        usageSummary: String? = nil,
        grantID: String? = nil,
        customerAccountID: String? = nil,
        ownerKind: String? = nil,
        ownerUserID: String? = nil,
        grantedScopes: [String] = [],
        expiresAt: Date? = nil,
        grantHandle: String? = nil,
        revokeHandle: String? = nil,
        display: WorkbenchProviderGrantDisplay? = nil,
        sourcePointer: String? = nil,
        auditID: String? = nil,
        lastValidatedAt: Date? = nil
    ) {
        self.schemaVersion = schemaVersion
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.status = status
        self.active = active
        self.rawSecretsStoredInWorkbench = rawSecretsStoredInWorkbench
        self.capabilities = capabilities
        self.usageSummary = usageSummary
        self.grantID = grantID
        self.customerAccountID = customerAccountID
        self.ownerKind = ownerKind
        self.ownerUserID = ownerUserID
        self.grantedScopes = grantedScopes
        self.expiresAt = expiresAt
        self.grantHandle = grantHandle
        self.revokeHandle = revokeHandle
        self.display = display
        self.sourcePointer = sourcePointer
        self.auditID = auditID
        self.lastValidatedAt = lastValidatedAt
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case key = "provider_key"
        case title
        case subtitle
        case status
        case active
        case rawSecretsStoredInWorkbench = "raw_secrets_stored_in_workbench"
        case capabilities
        case usageSummary = "usage_summary"
        case grantID = "grant_id"
        case customerAccountID = "customer_account_id"
        case ownerKind = "owner_kind"
        case ownerUserID = "owner_user_id"
        case grantedScopes = "scopes"
        case expiresAt = "expires_at"
        case grantHandle = "grant_handle"
        case revokeHandle = "revoke_handle"
        case display
        case sourcePointer = "source_pointer"
        case auditID = "audit_id"
        case lastValidatedAt = "last_validated_at"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        key = try container.decode(WorkbenchProviderKey.self, forKey: .key)
        title = try container.decode(String.self, forKey: .title)
        subtitle = try container.decode(String.self, forKey: .subtitle)
        status = try container.decode(WorkbenchProviderStatus.self, forKey: .status)
        active = try container.decodeIfPresent(Bool.self, forKey: .active) ?? false
        rawSecretsStoredInWorkbench = try container.decodeIfPresent(Bool.self, forKey: .rawSecretsStoredInWorkbench) ?? false
        capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
        usageSummary = try container.decodeIfPresent(String.self, forKey: .usageSummary)
        grantID = try container.decodeIfPresent(String.self, forKey: .grantID)
        customerAccountID = try container.decodeIfPresent(String.self, forKey: .customerAccountID)
        ownerKind = try container.decodeIfPresent(String.self, forKey: .ownerKind)
        ownerUserID = try container.decodeIfPresent(String.self, forKey: .ownerUserID)
        grantedScopes = try container.decodeIfPresent([String].self, forKey: .grantedScopes) ?? []
        expiresAt = try container.decodeIfPresent(Date.self, forKey: .expiresAt)
        grantHandle = try container.decodeIfPresent(String.self, forKey: .grantHandle)
        revokeHandle = try container.decodeIfPresent(String.self, forKey: .revokeHandle)
        display = try container.decodeIfPresent(WorkbenchProviderGrantDisplay.self, forKey: .display)
        sourcePointer = try container.decodeIfPresent(String.self, forKey: .sourcePointer)
        auditID = try container.decodeIfPresent(String.self, forKey: .auditID)
        lastValidatedAt = try container.decodeIfPresent(Date.self, forKey: .lastValidatedAt)
    }
}

public struct WorkbenchProviderProfilesResponse: Codable, Equatable, Sendable {
    public let schemaVersion: String?
    public let profiles: [WorkbenchProviderProfileState]
    public let activeProviderKey: WorkbenchProviderKey?
    public let rawSecretsStoredInWorkbench: Bool

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
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
        if profiles.contains(where: { $0.status == .expired }) {
            return "Needs reconnection"
        }
        if profiles.contains(where: { $0.status == .error }) {
            return "Blocked"
        }
        if profiles.contains(where: { $0.status == .planned }) {
            return "Unavailable"
        }
        return "Unchecked"
    }
}

public enum WorkbenchProviderCatalog {
    public static let profiles: [WorkbenchProviderProfile] = [
        WorkbenchProviderProfile(
            key: .openAICodex,
            title: "Codex Desktop",
            subtitle: "Technical readiness for advanced Codex handoff. Most businesses do not need to configure this directly.",
            readiness: .needsLogin,
            capabilities: ["Codex remote control readiness", "OpenAI profile status", "OpenClaw VM grant metadata"]
        ),
        WorkbenchProviderProfile(
            key: .googleWorkspace,
            title: "Google Workspace",
            subtitle: "Let Eva help with Gmail, Calendar, and Drive after you sign in through the business browser.",
            readiness: .needsLogin,
            capabilities: ["Read email context", "Draft calendar work", "Find Drive files"]
        ),
        WorkbenchProviderProfile(
            key: .pipedream,
            title: "Pipedream Connection Service",
            subtitle: "Eva uses this secure integration engine behind the scenes for apps like Gmail, Slack, Notion, and GitHub.",
            readiness: .planned,
            capabilities: ["Brokered app connections", "Connection health", "Revocation status"]
        ),
        WorkbenchProviderProfile(
            key: .slack,
            title: "Slack",
            subtitle: "Prepare workspace messaging access for approved agent workflows.",
            readiness: .planned,
            capabilities: ["Channel search", "Thread context", "Message drafting"]
        ),
        WorkbenchProviderProfile(
            key: .notion,
            title: "Notion",
            subtitle: "Prepare workspace docs and operating-system knowledge access through brokered OAuth.",
            readiness: .planned,
            capabilities: ["Database lookup", "Page context", "Roadmap evidence"]
        ),
        WorkbenchProviderProfile(
            key: .linear,
            title: "Linear",
            subtitle: "Prepare issue, milestone, and product-roadmap access for agent handoffs.",
            readiness: .planned,
            capabilities: ["Issue triage", "Milestone state", "Roadmap updates"]
        ),
        WorkbenchProviderProfile(
            key: .github,
            title: "GitHub",
            subtitle: "Prepare repository, pull request, and CI access through brokered provider grants.",
            readiness: .planned,
            capabilities: ["Repository context", "Pull requests", "CI status"]
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

    public static func profile(for key: WorkbenchProviderKey) -> WorkbenchProviderProfile? {
        profiles.first { $0.key == key }
    }

    public static func visibleStates(from brokerProfiles: [WorkbenchProviderProfileState]) -> [WorkbenchProviderProfileState] {
        let knownKeys = Set(profiles.map(\.key))
        let brokerByKey = brokerProfiles
            .filter { knownKeys.contains($0.key) }
            .reduce(into: [WorkbenchProviderKey: WorkbenchProviderProfileState]()) { statesByKey, state in
                statesByKey[state.key] = state
            }
        return defaultStates.map { defaultState in
            brokerByKey[defaultState.key] ?? defaultState
        }
    }
}

public enum WorkbenchProviderOAuthCallback {
    public static func isOAuthComplete(_ callbackURL: URL) -> Bool {
        guard let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false) else {
            return false
        }
        return components.scheme?.lowercased() == "evaos"
            && components.host?.lowercased() == "oauth-complete"
    }
}
