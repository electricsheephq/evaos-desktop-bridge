import Foundation

public struct RuntimeURLResolver: Sendable {
    public let runtimeBaseDomain: String
    public let dashboardBaseURL: URL

    public init(
        runtimeBaseDomain: String = "ecs.electricsheephq.com",
        dashboardBaseURL: URL = URL(string: "https://www.electricsheephq.com")!
    ) {
        self.runtimeBaseDomain = runtimeBaseDomain
        self.dashboardBaseURL = dashboardBaseURL
    }

    public func sanitizedCustomerId(_ value: String) -> String {
        let lowercased = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyz0123456789-")
        let filteredScalars = lowercased.unicodeScalars.map { scalar in
            allowed.contains(scalar) ? Character(scalar) : "-"
        }
        let filtered = String(filteredScalars)
            .split(separator: "-", omittingEmptySubsequences: true)
            .joined(separator: "-")
        return filtered.isEmpty ? "golden" : filtered
    }

    public func creativeStudioURL() -> URL {
        dashboardBaseURL.appendingPathComponent("creative-studio")
    }
}
