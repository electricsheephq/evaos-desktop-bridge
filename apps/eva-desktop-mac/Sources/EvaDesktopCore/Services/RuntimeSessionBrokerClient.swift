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
    public let endpoint: URL
    public let urlSession: URLSession

    public init(
        endpoint: URL = URL(string: "https://www.electricsheephq.com/api/desktop/runtime-session")!,
        urlSession: URLSession = .shared
    ) {
        self.endpoint = endpoint
        self.urlSession = urlSession
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

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        do {
            return try decoder.decode(RuntimeLaunchResponse.self, from: data)
        } catch {
            throw RuntimeSessionBrokerError.invalidResponse
        }
    }
}
