import Foundation

public enum WorkbenchFeatureFlagKey: String, CaseIterable, Codable, Sendable {
    case providersHub = "providers_hub"
    case sessionCenter = "session_center"
    case creativeStudio = "creative_studio"

    public var userDefaultsKey: String {
        "EvaDesktop.feature.\(rawValue)"
    }

    public var defaultValue: Bool {
        switch self {
        case .providersHub, .sessionCenter, .creativeStudio:
            return false
        }
    }
}

public struct WorkbenchFeatureFlags: Equatable, Sendable {
    private let values: [WorkbenchFeatureFlagKey: Bool]

    public init(values: [WorkbenchFeatureFlagKey: Bool] = [:]) {
        self.values = WorkbenchFeatureFlagKey.allCases.reduce(into: [:]) { result, key in
            result[key] = values[key] ?? key.defaultValue
        }
    }

    public init(userDefaults: UserDefaults) {
        self.values = WorkbenchFeatureFlagKey.allCases.reduce(into: [:]) { result, key in
            if userDefaults.object(forKey: key.userDefaultsKey) == nil {
                result[key] = key.defaultValue
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
