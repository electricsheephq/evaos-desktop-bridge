import Foundation

public struct DesktopSession: Codable, Equatable, Sendable {
    public let accessToken: String
    public let userEmail: String?
    public let expiresAt: Date?

    public init(accessToken: String, userEmail: String? = nil, expiresAt: Date? = nil) {
        self.accessToken = accessToken
        self.userEmail = userEmail
        self.expiresAt = expiresAt
    }

    public var isExpired: Bool {
        guard let expiresAt else { return true }
        return expiresAt <= Date()
    }
}

public enum DesktopSessionCallbackError: Error, LocalizedError, Sendable {
    case invalidCallback

    public var errorDescription: String? {
        switch self {
        case .invalidCallback:
            "The ElectricSheep login callback did not include a valid desktop session."
        }
    }
}

public enum DesktopSessionCallbackParser {
    public static func parse(_ callbackURL: URL) throws -> DesktopSession {
        guard let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false) else {
            throw DesktopSessionCallbackError.invalidCallback
        }
        let isEvaOSCallback =
            components.scheme == "evaos"
            && components.host == "auth"
            && components.path == "/callback"
        let isLoopbackCallback =
            components.scheme == "http"
            && ["127.0.0.1", "localhost", "::1"].contains(components.host ?? "")
            && components.path == "/auth/callback"
        guard isEvaOSCallback || isLoopbackCallback else {
            throw DesktopSessionCallbackError.invalidCallback
        }

        var items = components.queryItems ?? []
        if
            let fragment = components.fragment,
            let fragmentComponents = URLComponents(string: "evaos://auth/callback?\(fragment)")
        {
            items.append(contentsOf: fragmentComponents.queryItems ?? [])
        }

        let token = items.first(where: { $0.name == "desktop_session" })?.value
        let email = items.first(where: { $0.name == "email" })?.value
        let expiresAtValue = items.first(where: { $0.name == "desktop_session_expires_at" })?.value
            ?? items.first(where: { $0.name == "expires_at" })?.value

        guard
            let token,
            !token.isEmpty,
            let expiresAtValue,
            let expiresAt = EvaDesktopISO8601.parse(expiresAtValue)
        else {
            throw DesktopSessionCallbackError.invalidCallback
        }

        return DesktopSession(accessToken: token, userEmail: email, expiresAt: expiresAt)
    }
}

public enum EvaDesktopISO8601 {
    public static func parse(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) {
            return date
        }

        let standard = ISO8601DateFormatter()
        return standard.date(from: value)
    }

    public static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            if let date = parse(value) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Expected ISO-8601 timestamp"
            )
        }
        return decoder
    }
}

public struct RuntimeLaunchRequest: Codable, Equatable, Sendable {
    public let action: String
    public let customerId: String
    public let runtime: RuntimeKey

    public init(customerId: String, runtime: RuntimeKey) {
        self.action = "runtime_launch"
        self.customerId = customerId
        self.runtime = runtime
    }

    enum CodingKeys: String, CodingKey {
        case action
        case customerId = "customer_id"
        case runtime
    }
}

public struct RuntimeStatusRequest: Codable, Equatable, Sendable {
    public let action: String
    public let customerId: String
    public let runtime: RuntimeKey

    public init(customerId: String, runtime: RuntimeKey) {
        self.action = "runtime_status"
        self.customerId = customerId
        self.runtime = runtime
    }

    enum CodingKeys: String, CodingKey {
        case action
        case customerId = "customer_id"
        case runtime
    }
}

public struct RuntimeStatusResponse: Codable, Equatable, Sendable {
    public let schemaVersion: String?
    public let customerAccountID: String?
    public let customerID: String?
    public let runtimeKey: RuntimeKey
    public let displayLabel: String
    public let status: String
    public let healthSummary: String?
    public let lastCheckedAt: Date?
    public let roomId: String?
    public let sessionID: String?
    public let currentUrl: String?
    public let owner: String?
    public let authNeeded: Bool?
    public let captchaNeeded: Bool?
    public let waitingOnUser: Bool?
    public let controlSessionActive: Bool?
    public let updateAvailable: Bool?
    public let lastActivityAt: Date?
    public let actions: [String]?
    public let browserActions: [WorkbenchBrowserAction]?
    public let currentURLSummary: WorkbenchBrowserURLSummary?
    public let sourcePointer: String?
    public let auditID: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case customerAccountID = "customer_account_id"
        case customerID = "customer_id"
        case runtimeKey = "runtime_key"
        case runtime
        case displayLabel = "display_label"
        case status
        case healthSummary = "health_summary"
        case lastCheckedAt = "last_checked_at"
        case roomId = "room_id"
        case sessionID = "session_id"
        case currentUrl = "current_url"
        case owner
        case authNeeded = "auth_needed"
        case captchaNeeded = "captcha_needed"
        case waitingOnUser = "waiting_on_user"
        case controlSessionActive = "control_session_active"
        case updateAvailable = "update_available"
        case lastActivityAt = "last_activity_at"
        case needsAuth = "needs_auth"
        case needsCaptcha = "needs_captcha"
        case actions
        case sourcePointer = "source_pointer"
        case auditID = "audit_id"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        customerAccountID = try container.decodeIfPresent(String.self, forKey: .customerAccountID)
        customerID = try container.decodeIfPresent(String.self, forKey: .customerID)
        if let decodedRuntime = try container.decodeIfPresent(RuntimeKey.self, forKey: .runtimeKey)
            ?? container.decodeIfPresent(RuntimeKey.self, forKey: .runtime)
        {
            runtimeKey = decodedRuntime
        } else {
            throw DecodingError.keyNotFound(
                CodingKeys.runtimeKey,
                DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Expected runtime_key or runtime")
            )
        }
        displayLabel = try container.decodeIfPresent(String.self, forKey: .displayLabel)
            ?? RuntimeDefinition.definition(for: runtimeKey).title
        status = try container.decode(String.self, forKey: .status)
        healthSummary = try container.decodeIfPresent(String.self, forKey: .healthSummary)
        lastCheckedAt = try container.decodeIfPresent(Date.self, forKey: .lastCheckedAt)
        roomId = try container.decodeIfPresent(String.self, forKey: .roomId)
        sessionID = try container.decodeIfPresent(String.self, forKey: .sessionID)

        if let rawCurrentURL = try? container.decodeIfPresent(String.self, forKey: .currentUrl) {
            currentUrl = rawCurrentURL
            currentURLSummary = WorkbenchBrowserURLSummary.sanitized(from: rawCurrentURL)
        } else if let summary = try? container.decodeIfPresent(WorkbenchBrowserURLSummary.self, forKey: .currentUrl) {
            currentURLSummary = summary
            currentUrl = summary.displayText
        } else {
            currentUrl = nil
            currentURLSummary = nil
        }

        owner = try container.decodeIfPresent(String.self, forKey: .owner)
        authNeeded = try container.decodeIfPresent(Bool.self, forKey: .authNeeded)
            ?? container.decodeIfPresent(Bool.self, forKey: .needsAuth)
        captchaNeeded = try container.decodeIfPresent(Bool.self, forKey: .captchaNeeded)
            ?? container.decodeIfPresent(Bool.self, forKey: .needsCaptcha)
        waitingOnUser = try container.decodeIfPresent(Bool.self, forKey: .waitingOnUser)
        controlSessionActive = try container.decodeIfPresent(Bool.self, forKey: .controlSessionActive)
        updateAvailable = try container.decodeIfPresent(Bool.self, forKey: .updateAvailable)
        lastActivityAt = try container.decodeIfPresent(Date.self, forKey: .lastActivityAt)
        let decodedActions = try container.decodeIfPresent([String].self, forKey: .actions)
        actions = decodedActions
        browserActions = decodedActions?.compactMap(WorkbenchBrowserAction.init(rawValue:))
        sourcePointer = try container.decodeIfPresent(String.self, forKey: .sourcePointer)
        auditID = try container.decodeIfPresent(String.self, forKey: .auditID)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(schemaVersion, forKey: .schemaVersion)
        try container.encodeIfPresent(customerAccountID, forKey: .customerAccountID)
        try container.encodeIfPresent(customerID, forKey: .customerID)
        try container.encode(runtimeKey, forKey: .runtimeKey)
        try container.encode(displayLabel, forKey: .displayLabel)
        try container.encode(status, forKey: .status)
        try container.encodeIfPresent(healthSummary, forKey: .healthSummary)
        try container.encodeIfPresent(lastCheckedAt, forKey: .lastCheckedAt)
        try container.encodeIfPresent(roomId, forKey: .roomId)
        try container.encodeIfPresent(sessionID, forKey: .sessionID)
        if let currentURLSummary {
            try container.encode(currentURLSummary, forKey: .currentUrl)
        } else {
            try container.encodeIfPresent(currentUrl, forKey: .currentUrl)
        }
        try container.encodeIfPresent(owner, forKey: .owner)
        try container.encodeIfPresent(authNeeded, forKey: .authNeeded)
        try container.encodeIfPresent(captchaNeeded, forKey: .captchaNeeded)
        try container.encodeIfPresent(waitingOnUser, forKey: .waitingOnUser)
        try container.encodeIfPresent(controlSessionActive, forKey: .controlSessionActive)
        try container.encodeIfPresent(updateAvailable, forKey: .updateAvailable)
        try container.encodeIfPresent(lastActivityAt, forKey: .lastActivityAt)
        try container.encodeIfPresent(browserActions ?? actions?.compactMap(WorkbenchBrowserAction.init(rawValue:)), forKey: .actions)
        try container.encodeIfPresent(sourcePointer, forKey: .sourcePointer)
        try container.encodeIfPresent(auditID, forKey: .auditID)
    }
}

public struct WorkbenchProviderProfilesRequest: Codable, Equatable, Sendable {
    public let action: String
    public let customerId: String

    public init(customerId: String) {
        self.action = "provider_profiles"
        self.customerId = customerId
    }

    enum CodingKeys: String, CodingKey {
        case action
        case customerId = "customer_id"
    }
}

public struct WorkbenchProviderActionRequest: Codable, Equatable, Sendable {
    public let action: String
    public let customerId: String
    public let providerKey: WorkbenchProviderKey
    public let agentRuntime: String?

    public init(action: String, customerId: String, providerKey: WorkbenchProviderKey, agentRuntime: String? = nil) {
        self.action = action
        self.customerId = customerId
        self.providerKey = providerKey
        self.agentRuntime = agentRuntime
    }

    enum CodingKeys: String, CodingKey {
        case action
        case customerId = "customer_id"
        case providerKey = "provider_key"
        case agentRuntime = "agent_runtime"
    }
}

public struct WorkbenchProviderAuthStartResponse: Codable, Equatable, Sendable {
    public let providerKey: WorkbenchProviderKey
    public let status: String
    public let connectURL: URL
    public let targetURL: URL?
    public let expiresAt: Date?
    public let instructions: String?
    public let profiles: [WorkbenchProviderProfileState]
    public let activeProviderKey: WorkbenchProviderKey?
    public let rawSecretsStoredInWorkbench: Bool

    enum CodingKeys: String, CodingKey {
        case providerKey = "provider_key"
        case status
        case connectURL = "connect_url"
        case targetURL = "target_url"
        case expiresAt = "expires_at"
        case instructions
        case profiles = "provider_profiles"
        case activeProviderKey = "active_provider_key"
        case rawSecretsStoredInWorkbench = "raw_secrets_stored_in_workbench"
    }
}

public struct SharedBrowserOpenURLRequest: Encodable, Equatable, Sendable {
    public let action: String
    public let customerId: String
    public let url: URL

    public init(customerId: String, url: URL) {
        self.action = "browser_open_url"
        self.customerId = customerId
        self.url = SharedBrowserOpenURLRequest.sanitizedURL(url)
    }

    private static func sanitizedURL(_ url: URL) -> URL {
        guard
            let scheme = url.scheme?.lowercased(),
            scheme == "https" || scheme == "http",
            let host = url.host,
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else {
            return url
        }
        components.scheme = scheme
        components.host = host
        components.query = nil
        components.fragment = nil
        return components.url ?? url
    }

    enum CodingKeys: String, CodingKey {
        case action
        case customerId = "customer_id"
        case url
    }
}

public struct SharedBrowserOpenURLResponse: Decodable, Equatable, Sendable {
    public let ok: Bool?
    public let status: String?
}

public struct SharedBrowserStopRequest: Encodable, Equatable, Sendable {
    public let action: String
    public let customerId: String

    public init(customerId: String) {
        self.action = "browser_stop"
        self.customerId = customerId
    }

    enum CodingKeys: String, CodingKey {
        case action
        case customerId = "customer_id"
    }
}

public struct SharedBrowserStopResponse: Decodable, Equatable, Sendable {
    public let ok: Bool?
    public let status: String?
}

public struct DesktopCustomerTargetsRequest: Codable, Equatable, Sendable {
    public let action: String

    public init() {
        self.action = "list_customer_targets"
    }
}

public struct DesktopSessionRevokeRequest: Codable, Equatable, Sendable {
    public let action: String

    public init() {
        self.action = "revoke_desktop_session"
    }
}

public struct DesktopDeviceCodeClaimRequest: Codable, Equatable, Sendable {
    public let action: String
    public let deviceCode: String

    public init(deviceCode: String) {
        self.action = "claim_desktop_device_code"
        self.deviceCode = deviceCode
    }

    enum CodingKeys: String, CodingKey {
        case action
        case deviceCode = "device_code"
    }
}

public struct DesktopDeviceCodeClaimResponse: Codable, Equatable, Sendable {
    public let desktopSession: String
    public let desktopSessionExpiresAt: Date
    public let email: String?

    public var session: DesktopSession {
        DesktopSession(accessToken: desktopSession, userEmail: email, expiresAt: desktopSessionExpiresAt)
    }

    enum CodingKeys: String, CodingKey {
        case desktopSession = "desktop_session"
        case desktopSessionExpiresAt = "desktop_session_expires_at"
        case email
    }
}

public struct DesktopCustomerTarget: Codable, Equatable, Identifiable, Sendable {
    public let customerId: String
    public let displayName: String
    public let email: String?
    public let status: String?
    public let healthStatus: String?
    public let isDefault: Bool

    public var id: String { customerId }

    public init(
        customerId: String,
        displayName: String,
        email: String? = nil,
        status: String? = nil,
        healthStatus: String? = nil,
        isDefault: Bool = false
    ) {
        self.customerId = customerId
        self.displayName = displayName
        self.email = email
        self.status = status
        self.healthStatus = healthStatus
        self.isDefault = isDefault
    }

    enum CodingKeys: String, CodingKey {
        case customerId = "customer_id"
        case displayName = "display_name"
        case email
        case status
        case healthStatus = "health_status"
        case isDefault = "is_default"
    }
}

public struct DesktopCustomerTargetsResponse: Codable, Equatable, Sendable {
    public let roles: [String]
    public let isOperator: Bool
    public let defaultCustomerId: String?
    public let customers: [DesktopCustomerTarget]

    public init(
        roles: [String],
        isOperator: Bool,
        defaultCustomerId: String? = nil,
        customers: [DesktopCustomerTarget]
    ) {
        self.roles = roles
        self.isOperator = isOperator
        self.defaultCustomerId = defaultCustomerId
        self.customers = customers
    }

    enum CodingKeys: String, CodingKey {
        case roles
        case isOperator = "is_operator"
        case defaultCustomerId = "default_customer_id"
        case customers
    }
}

public struct RuntimeLaunchResponse: Codable, Equatable, Sendable {
    public let launchUrl: URL
    public let expiresAt: Date?

    public init(launchUrl: URL, expiresAt: Date? = nil) {
        self.launchUrl = launchUrl
        self.expiresAt = expiresAt
    }

    enum CodingKeys: String, CodingKey {
        case launchUrl = "launch_url"
        case expiresAt = "expires_at"
    }
}
