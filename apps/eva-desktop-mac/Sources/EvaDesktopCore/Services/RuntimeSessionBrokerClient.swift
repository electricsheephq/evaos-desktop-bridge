import Foundation

public enum RuntimeSessionBrokerError: Error, LocalizedError {
    case missingSession
    case invalidResponse
    case httpStatus(Int)

    public var errorDescription: String? {
        switch self {
        case .missingSession:
            "Sign in before requesting runtime sessions."
        case .invalidResponse:
            "The runtime session broker returned an invalid response."
        case .httpStatus(let status):
            "The runtime session broker returned HTTP \(status)."
        }
    }
}

public struct RuntimeSessionBrokerClient: Sendable {
    public static let productionEndpoint = URL(string: "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/desktop-runtime-session")!
    public static let productionCapabilityEndpoint = URL(string: "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/cortex-proxy")!

    public let endpoint: URL
    public let capabilityEndpoint: URL
    public let urlSession: URLSession

    public init(
        endpoint: URL,
        capabilityEndpoint: URL = RuntimeSessionBrokerClient.productionCapabilityEndpoint,
        urlSession: URLSession = .shared
    ) {
        self.endpoint = endpoint
        self.capabilityEndpoint = capabilityEndpoint
        self.urlSession = urlSession
    }

    public init(
        projectFunctionEndpoint: URL = RuntimeSessionBrokerClient.productionEndpoint,
        capabilityEndpoint: URL = RuntimeSessionBrokerClient.productionCapabilityEndpoint,
        urlSession: URLSession = .shared
    ) {
        self.init(endpoint: projectFunctionEndpoint, capabilityEndpoint: capabilityEndpoint, urlSession: urlSession)
    }

    public init(
        dashboardBaseURL _: URL,
        urlSession: URLSession = .shared
    ) {
        self.init(endpoint: RuntimeSessionBrokerClient.productionEndpoint, capabilityEndpoint: Self.capabilityEndpoint(), urlSession: urlSession)
    }

    public func launchURL(
        customerId: String,
        runtime: RuntimeKey,
        desktopSession: DesktopSession?
    ) async throws -> RuntimeLaunchResponse {
        try await post(
            RuntimeLaunchRequest(customerId: customerId, runtime: runtime),
            desktopSession: desktopSession,
            decoder: EvaDesktopISO8601.decoder()
        )
    }

    public func runtimeStatus(
        customerId: String,
        runtime: RuntimeKey,
        desktopSession: DesktopSession?
    ) async throws -> RuntimeStatusResponse {
        try await post(
            RuntimeStatusRequest(customerId: customerId, runtime: runtime),
            desktopSession: desktopSession,
            decoder: EvaDesktopISO8601.decoder()
        )
    }

    public func providerProfiles(
        customerId: String,
        desktopSession: DesktopSession?
    ) async throws -> WorkbenchProviderProfilesResponse {
        try await post(
            WorkbenchProviderProfilesRequest(customerId: customerId),
            desktopSession: desktopSession,
            decoder: EvaDesktopISO8601.decoder()
        )
    }

    public func connectProvider(
        _ providerKey: WorkbenchProviderKey,
        customerId: String,
        desktopSession: DesktopSession?
    ) async throws -> WorkbenchProviderAuthStartResponse {
        try await post(
            WorkbenchProviderActionRequest(
                action: "provider_auth_start",
                customerId: customerId,
                providerKey: providerKey
            ),
            desktopSession: desktopSession,
            decoder: EvaDesktopISO8601.decoder()
        )
    }

    public func openSharedBrowserURL(
        _ url: URL,
        customerId: String,
        desktopSession: DesktopSession?
    ) async throws {
        let _: SharedBrowserOpenURLResponse = try await post(
            SharedBrowserOpenURLRequest(customerId: customerId, url: url),
            desktopSession: desktopSession,
            decoder: JSONDecoder()
        )
    }

    public func switchProvider(
        _ providerKey: WorkbenchProviderKey,
        customerId: String,
        desktopSession: DesktopSession?
    ) async throws -> WorkbenchProviderProfilesResponse {
        try await providerAction("provider_switch", providerKey: providerKey, customerId: customerId, desktopSession: desktopSession)
    }

    public func revokeProvider(
        _ providerKey: WorkbenchProviderKey,
        customerId: String,
        desktopSession: DesktopSession?
    ) async throws -> WorkbenchProviderProfilesResponse {
        try await providerAction("provider_revoke", providerKey: providerKey, customerId: customerId, desktopSession: desktopSession)
    }

    @discardableResult
    public func mintProviderGrant(
        _ providerKey: WorkbenchProviderKey,
        agentRuntime: String,
        customerId: String,
        desktopSession: DesktopSession?
    ) async throws -> WorkbenchProviderProfilesResponse {
        try await providerAction(
            "provider_mint_grant",
            providerKey: providerKey,
            customerId: customerId,
            agentRuntime: agentRuntime,
            desktopSession: desktopSession
        )
    }

    public func customerTargets(desktopSession: DesktopSession?) async throws -> DesktopCustomerTargetsResponse {
        try await post(DesktopCustomerTargetsRequest(), desktopSession: desktopSession)
    }

    public func capabilityManifest(
        agentID: String,
        desktopSession: DesktopSession?
    ) async throws -> WorkbenchCapabilityManifestFetchResponse {
        try await get(
            pathComponents: ["capabilities", RuntimeSessionBrokerClient.normalizedCapabilityAgentID(agentID)],
            desktopSession: desktopSession,
            decoder: EvaDesktopISO8601.decoder()
        )
    }

    public func pendingApprovals(
        desktopSession: DesktopSession?,
        limit: Int = 50
    ) async throws -> WorkbenchApprovalRequestsResponse {
        try await get(
            pathComponents: ["approvals", "pending"],
            queryItems: [URLQueryItem(name: "limit", value: String(max(1, min(limit, 100))))],
            desktopSession: desktopSession,
            decoder: EvaDesktopISO8601.decoder()
        )
    }

    @discardableResult
    public func decideApproval(
        approvalID: String,
        decision: WorkbenchApprovalDecision,
        scope: WorkbenchApprovalScope? = nil,
        desktopSession: DesktopSession?
    ) async throws -> WorkbenchApprovalRequest {
        try await postCapability(
            pathComponents: ["approvals", approvalID, "decide"],
            body: WorkbenchApprovalDecisionRequest(decision: decision, scope: scope),
            desktopSession: desktopSession,
            decoder: EvaDesktopISO8601.decoder()
        )
    }

    public func claimDeviceCode(_ deviceCode: String) async throws -> DesktopSession {
        let normalizedCode = deviceCode
            .uppercased()
            .filter { $0.isLetter || $0.isNumber }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(DesktopDeviceCodeClaimRequest(deviceCode: normalizedCode))

        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw RuntimeSessionBrokerError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw RuntimeSessionBrokerError.httpStatus(httpResponse.statusCode)
        }

        do {
            return try EvaDesktopISO8601.decoder().decode(DesktopDeviceCodeClaimResponse.self, from: data).session
        } catch {
            throw RuntimeSessionBrokerError.invalidResponse
        }
    }

    public func revoke(desktopSession: DesktopSession?) async {
        guard let desktopSession else { return }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(desktopSession.accessToken)", forHTTPHeaderField: "Authorization")
        guard let body = try? JSONEncoder().encode(DesktopSessionRevokeRequest()) else {
            return
        }
        request.httpBody = body

        _ = try? await urlSession.data(for: request)
    }

    private func providerAction(
        _ action: String,
        providerKey: WorkbenchProviderKey,
        customerId: String,
        agentRuntime: String? = nil,
        desktopSession: DesktopSession?
    ) async throws -> WorkbenchProviderProfilesResponse {
        try await post(
            WorkbenchProviderActionRequest(
                action: action,
                customerId: customerId,
                providerKey: providerKey,
                agentRuntime: agentRuntime
            ),
            desktopSession: desktopSession,
            decoder: EvaDesktopISO8601.decoder()
        )
    }

    private func post<Request: Encodable, Response: Decodable>(
        _ body: Request,
        desktopSession: DesktopSession?,
        decoder: JSONDecoder = JSONDecoder()
    ) async throws -> Response {
        guard let desktopSession, !desktopSession.isExpired else {
            throw RuntimeSessionBrokerError.missingSession
        }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(desktopSession.accessToken)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw RuntimeSessionBrokerError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw RuntimeSessionBrokerError.httpStatus(httpResponse.statusCode)
        }

        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw RuntimeSessionBrokerError.invalidResponse
        }
    }

    private func get<Response: Decodable>(
        pathComponents: [String],
        queryItems: [URLQueryItem] = [],
        desktopSession: DesktopSession?,
        decoder: JSONDecoder = JSONDecoder()
    ) async throws -> Response {
        guard let desktopSession, !desktopSession.isExpired else {
            throw RuntimeSessionBrokerError.missingSession
        }

        let request = try capabilityRequest(
            method: "GET",
            pathComponents: pathComponents,
            queryItems: queryItems,
            body: nil as Data?,
            desktopSession: desktopSession
        )

        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw RuntimeSessionBrokerError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw RuntimeSessionBrokerError.httpStatus(httpResponse.statusCode)
        }

        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw RuntimeSessionBrokerError.invalidResponse
        }
    }

    private func postCapability<Request: Encodable, Response: Decodable>(
        pathComponents: [String],
        body: Request,
        desktopSession: DesktopSession?,
        decoder: JSONDecoder = JSONDecoder()
    ) async throws -> Response {
        guard let desktopSession, !desktopSession.isExpired else {
            throw RuntimeSessionBrokerError.missingSession
        }

        let request = try capabilityRequest(
            method: "POST",
            pathComponents: pathComponents,
            body: try JSONEncoder().encode(body),
            desktopSession: desktopSession
        )

        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw RuntimeSessionBrokerError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw RuntimeSessionBrokerError.httpStatus(httpResponse.statusCode)
        }

        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw RuntimeSessionBrokerError.invalidResponse
        }
    }

    public static func normalizedCapabilityAgentID(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
        let scalars = trimmed.unicodeScalars.filter { allowed.contains($0) }
        let normalized = String(String.UnicodeScalarView(scalars))
        return normalized.isEmpty ? "openclaw" : String(normalized.prefix(200))
    }

    private static func capabilityEndpoint() -> URL {
        return productionCapabilityEndpoint
    }

    private func capabilityRequest(
        method: String,
        pathComponents: [String],
        queryItems: [URLQueryItem] = [],
        body: Data?,
        desktopSession: DesktopSession
    ) throws -> URLRequest {
        if usesCapabilityProxy {
            var request = URLRequest(url: capabilityEndpoint)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("Bearer \(desktopSession.accessToken)", forHTTPHeaderField: "Authorization")

            var payload: [String: Any] = [
                "path": capabilityPath(pathComponents: pathComponents, queryItems: queryItems),
                "method": method
            ]
            if let body, method.uppercased() != "GET" {
                payload["body"] = try JSONSerialization.jsonObject(with: body)
            }
            request.httpBody = try JSONSerialization.data(withJSONObject: payload, options: [])
            return request
        }

        var url = capabilityEndpoint
        for component in pathComponents {
            url.appendPathComponent(component)
        }
        if !queryItems.isEmpty, var components = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            components.queryItems = queryItems
            url = components.url ?? url
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(desktopSession.accessToken)", forHTTPHeaderField: "Authorization")
        if let body, method.uppercased() != "GET" {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }
        return request
    }

    private var usesCapabilityProxy: Bool {
        let normalizedPath = capabilityEndpoint.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return normalizedPath == "functions/v1/cortex-proxy"
            || normalizedPath.hasSuffix("/functions/v1/cortex-proxy")
    }

    private func capabilityPath(
        pathComponents: [String],
        queryItems: [URLQueryItem] = []
    ) -> String {
        var url = URL(string: "https://cortex.invalid/api/v1")!
        for component in pathComponents {
            url.appendPathComponent(component)
        }
        if !queryItems.isEmpty, var components = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            components.queryItems = queryItems
            url = components.url ?? url
        }
        if let query = url.query, !query.isEmpty {
            return "\(url.path)?\(query)"
        }
        return url.path
    }
}
