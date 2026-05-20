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
        guard let desktopSession, !desktopSession.isExpired else {
            throw RuntimeSessionBrokerError.missingSession
        }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(desktopSession.accessToken)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONEncoder().encode(RuntimeLaunchRequest(customerId: customerId, runtime: runtime))

        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw RuntimeSessionBrokerError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw RuntimeSessionBrokerError.httpStatus(httpResponse.statusCode)
        }

        do {
            return try EvaDesktopISO8601.decoder().decode(RuntimeLaunchResponse.self, from: data)
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
        request.httpBody = try? JSONEncoder().encode(DesktopSessionRevokeRequest())

        _ = try? await urlSession.data(for: request)
    }
}
