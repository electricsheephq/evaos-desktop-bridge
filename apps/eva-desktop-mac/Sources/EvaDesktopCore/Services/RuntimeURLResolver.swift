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

    public func fallbackURL(for runtime: RuntimeKey, customerId: String) -> URL {
        let slug = sanitizedCustomerId(customerId)

        switch runtime {
        case .openclaw:
            return URL(string: "https://openclaw-\(slug).\(runtimeBaseDomain)/ui/")!
        case .hermes:
            return URL(string: "https://hermes-\(slug).\(runtimeBaseDomain)/")!
        case .missionControl:
            return URL(string: "https://paperclip-\(slug).\(runtimeBaseDomain)/")!
        case .liveBrowser:
            return URL(string: "https://browser-\(slug).\(runtimeBaseDomain)/")!
        case .terminal:
            return dashboardURL(path: "/dashboard/workspace", customerId: slug, runtime: "terminal")
        case .openDesign:
            return dashboardURL(path: "/dashboard/opendesign", customerId: slug, runtime: "opendesign")
        }
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

    private func dashboardURL(path: String, customerId: String, runtime: String) -> URL {
        var components = URLComponents(url: dashboardBaseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "customer_id", value: customerId),
            URLQueryItem(name: "runtime", value: runtime)
        ]
        return components.url!
    }
}

