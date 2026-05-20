import Foundation

public enum CustomerMacControlError: Error, LocalizedError {
    case missingSession
    case invalidResponse
    case httpStatus(Int)

    public var errorDescription: String? {
        switch self {
        case .missingSession:
            "Sign in before pairing a Mac."
        case .invalidResponse:
            "The Mac connector service returned an invalid response."
        case .httpStatus(let status):
            "The Mac connector service returned HTTP \(status)."
        }
    }
}

public struct CustomerMacControlClient: Sendable {
    public static let productionEndpoint = URL(string: "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/customer-mac-control")!

    public let endpoint: URL
    public let urlSession: URLSession

    public init(
        endpoint: URL = CustomerMacControlClient.productionEndpoint,
        urlSession: URLSession = .shared
    ) {
        self.endpoint = endpoint
        self.urlSession = urlSession
    }

    public func list(desktopSession: DesktopSession?) async throws -> CustomerMacListResponse {
        try await request(CustomerMacActionRequest(action: "list"), desktopSession: desktopSession)
    }

    public func auditTail(desktopSession: DesktopSession?, limit: Int = 10) async throws -> CustomerMacAuditTailResponse {
        try await request(CustomerMacActionRequest(action: "audit_tail", limit: limit), desktopSession: desktopSession)
    }

    public func createEnrollment(
        desktopSession: DesktopSession?,
        customerId: String,
        deviceName: String,
        screenSharingOptIn: Bool
    ) async throws -> CustomerMacEnrollmentResponse {
        try await request(
            CustomerMacActionRequest(
                action: "create_enrollment",
                customerId: customerId,
                deviceName: deviceName,
                screenSharingOptIn: screenSharingOptIn
            ),
            desktopSession: desktopSession
        )
    }

    public func revoke(
        desktopSession: DesktopSession?,
        deviceId: String,
        customerId: String
    ) async throws -> CustomerMacDeviceResponse {
        try await request(
            CustomerMacActionRequest(action: "revoke_device", customerId: customerId, deviceId: deviceId),
            desktopSession: desktopSession
        )
    }

    public func completeEnrollment(
        enrollmentCode: String,
        deviceName: String,
        deviceIdentifier: String?,
        tailnetIp: String?,
        capabilities: [String: String],
        permissionState: [String: String]
    ) async throws -> CustomerMacDeviceResponse {
        try await request(
            CustomerMacActionRequest(
                action: "complete_enrollment",
                deviceName: deviceName,
                enrollmentCode: enrollmentCode,
                deviceIdentifier: deviceIdentifier,
                tailnetIp: tailnetIp,
                capabilities: capabilities,
                permissionState: permissionState
            ),
            desktopSession: nil,
            allowMissingSession: true
        )
    }

    private func request<Response: Decodable>(
        _ body: CustomerMacActionRequest,
        desktopSession: DesktopSession?,
        allowMissingSession: Bool = false
    ) async throws -> Response {
        if !allowMissingSession {
            guard let desktopSession, !desktopSession.isExpired else {
                throw CustomerMacControlError.missingSession
            }
        }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let desktopSession, !desktopSession.isExpired {
            request.setValue("Bearer \(desktopSession.accessToken)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw CustomerMacControlError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw CustomerMacControlError.httpStatus(httpResponse.statusCode)
        }

        do {
            return try EvaDesktopISO8601.decoder().decode(Response.self, from: data)
        } catch {
            throw CustomerMacControlError.invalidResponse
        }
    }
}

public struct CustomerMacActionRequest: Codable, Equatable, Sendable {
    public let action: String
    public let customerId: String?
    public let deviceName: String?
    public let screenSharingOptIn: Bool?
    public let deviceId: String?
    public let enrollmentCode: String?
    public let deviceIdentifier: String?
    public let tailnetIp: String?
    public let capabilities: [String: String]?
    public let permissionState: [String: String]?
    public let limit: Int?

    public init(
        action: String,
        customerId: String? = nil,
        deviceName: String? = nil,
        screenSharingOptIn: Bool? = nil,
        deviceId: String? = nil,
        enrollmentCode: String? = nil,
        deviceIdentifier: String? = nil,
        tailnetIp: String? = nil,
        capabilities: [String: String]? = nil,
        permissionState: [String: String]? = nil,
        limit: Int? = nil
    ) {
        self.action = action
        self.customerId = customerId
        self.deviceName = deviceName
        self.screenSharingOptIn = screenSharingOptIn
        self.deviceId = deviceId
        self.enrollmentCode = enrollmentCode
        self.deviceIdentifier = deviceIdentifier
        self.tailnetIp = tailnetIp
        self.capabilities = capabilities
        self.permissionState = permissionState
        self.limit = limit
    }

    enum CodingKeys: String, CodingKey {
        case action
        case customerId = "customer_id"
        case deviceName = "device_name"
        case screenSharingOptIn = "screen_sharing_opt_in"
        case deviceId = "device_id"
        case enrollmentCode = "enrollment_code"
        case deviceIdentifier = "device_identifier"
        case tailnetIp = "tailnet_ip"
        case capabilities
        case permissionState = "permission_state"
        case limit
    }
}

public struct CustomerMacDevice: Codable, Equatable, Identifiable, Sendable {
    public let id: String
    public let customerId: String
    public let deviceName: String?
    public let status: String
    public let tailnetIp: String?
    public let lastSeenAt: Date?
    public let screenSharingOptIn: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case customerId = "customer_id"
        case deviceName = "device_name"
        case status
        case tailnetIp = "tailnet_ip"
        case lastSeenAt = "last_seen_at"
        case screenSharingOptIn = "screen_sharing_opt_in"
    }
}

public struct CustomerMacListResponse: Codable, Equatable, Sendable {
    public let customerId: String
    public let devices: [CustomerMacDevice]

    enum CodingKeys: String, CodingKey {
        case customerId = "customer_id"
        case devices
    }
}

public struct CustomerMacEnrollmentResponse: Codable, Equatable, Sendable {
    public let customerId: String
    public let device: CustomerMacDevice?
    public let enrollmentCode: String
    public let enrollmentExpiresAt: Date
    public let headscale: CustomerMacHeadscaleInfo?

    enum CodingKeys: String, CodingKey {
        case customerId = "customer_id"
        case device
        case enrollmentCode = "enrollment_code"
        case enrollmentExpiresAt = "enrollment_expires_at"
        case headscale
    }
}

public struct CustomerMacHeadscaleInfo: Codable, Equatable, Sendable {
    public let configured: Bool?
    public let created: Bool?
    public let mode: String?
    public let tag: String?
    public let preauthKey: String?

    enum CodingKeys: String, CodingKey {
        case configured
        case created
        case mode
        case tag
        case preauthKey = "preauth_key"
    }
}

public struct CustomerMacDeviceResponse: Codable, Equatable, Sendable {
    public let device: CustomerMacDevice?
}

public struct CustomerMacAuditTailResponse: Codable, Equatable, Sendable {
    public let customerId: String?
    public let events: [CustomerMacAuditEvent]

    enum CodingKeys: String, CodingKey {
        case customerId = "customer_id"
        case events
    }
}

public struct CustomerMacAuditEvent: Codable, Equatable, Identifiable, Sendable {
    public let id: String
    public let action: String
    public let outcome: String
    public let createdAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case action
        case outcome
        case createdAt = "created_at"
    }
}
