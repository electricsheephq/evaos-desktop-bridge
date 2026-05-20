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

public struct DesktopSessionRevokeRequest: Codable, Equatable, Sendable {
    public let action: String

    public init() {
        self.action = "revoke_desktop_session"
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
