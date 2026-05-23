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

    public let endpoint: URL
    public let urlSession: URLSession

    public init(
        endpoint: URL,
        urlSession: URLSession = .shared
    ) {
        self.endpoint = endpoint
        self.urlSession = urlSession
    }

    public init(
        projectFunctionEndpoint: URL = RuntimeSessionBrokerClient.productionEndpoint,
        urlSession: URLSession = .shared
    ) {
        self.init(endpoint: projectFunctionEndpoint, urlSession: urlSession)
    }

    public init(
        dashboardBaseURL _: URL,
        urlSession: URLSession = .shared
    ) {
        self.init(endpoint: RuntimeSessionBrokerClient.productionEndpoint, urlSession: urlSession)
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
    ) async throws -> WorkbenchProviderProfilesResponse {
        try await providerAction("provider_connect", providerKey: providerKey, customerId: customerId, desktopSession: desktopSession)
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
}
