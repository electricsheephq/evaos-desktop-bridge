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
        guard let expiresAt else { return false }
        return expiresAt <= Date()
    }
}

public struct RuntimeLaunchRequest: Codable, Equatable, Sendable {
    public let customerId: String
    public let runtime: RuntimeKey

    public init(customerId: String, runtime: RuntimeKey) {
        self.customerId = customerId
        self.runtime = runtime
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

