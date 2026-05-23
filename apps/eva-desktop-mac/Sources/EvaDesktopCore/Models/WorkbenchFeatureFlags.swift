import Foundation

public enum WorkbenchFeatureFlagKey: String, CaseIterable, Codable, Sendable {
    case providersHub = "providers_hub"
    case sharedBrowser2 = "shared_browser_2"
    case sessionCenter = "session_center"
    case creativeStudio = "creative_studio"

    public var userDefaultsKey: String {
        "EvaDesktop.feature.\(rawValue)"
    }
}

public struct WorkbenchFeatureFlags: Equatable, Sendable {
    private let values: [WorkbenchFeatureFlagKey: Bool]

    public init(values: [WorkbenchFeatureFlagKey: Bool] = [:]) {
        self.values = WorkbenchFeatureFlagKey.allCases.reduce(into: [:]) { result, key in
            result[key] = values[key] ?? false
        }
    }

    public init(userDefaults: UserDefaults) {
        self.values = WorkbenchFeatureFlagKey.allCases.reduce(into: [:]) { result, key in
            if userDefaults.object(forKey: key.userDefaultsKey) == nil {
                result[key] = false
            } else {
                result[key] = userDefaults.bool(forKey: key.userDefaultsKey)
            }
        }
    }

    public func isEnabled(_ key: WorkbenchFeatureFlagKey) -> Bool {
        values[key] ?? false
    }

    public func storedValue(for key: WorkbenchFeatureFlagKey) -> Bool {
        values[key] ?? false
    }

    public var enabledKeys: [WorkbenchFeatureFlagKey] {
        WorkbenchFeatureFlagKey.allCases.filter(isEnabled)
    }
}
