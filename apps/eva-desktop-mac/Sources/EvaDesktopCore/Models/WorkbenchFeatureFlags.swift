import Foundation

public enum WorkbenchFeatureFlagKey: String, CaseIterable, Codable, Sendable {
    case providersHub = "providers_hub"
    case sharedBrowser2 = "shared_browser_2"
    case sessionCenter = "session_center"
    case approvalCenter = "approval_center"
    case creativeStudio = "creative_studio"

    public var userDefaultsKey: String {
        "EvaDesktop.feature.\(rawValue)"
    }

    public var defaultValue: Bool {
        switch self {
        case .providersHub, .sessionCenter, .approvalCenter, .creativeStudio:
            return true
        case .sharedBrowser2:
            return false
        }
    }

    public var descriptor: WorkbenchFeatureFlagDescriptor {
        switch self {
        case .providersHub:
            return WorkbenchFeatureFlagDescriptor(
                key: self,
                dashboardEnvironmentKey: "VITE_EVAOS_PROVIDERS_HUB",
                primaryIssue: "#96",
                owner: "Workbench + Broker",
                surface: "Connected Apps",
                navigationPlacement: "Settings",
                rolloutCriteria: "Broker app-profile proof, connect/disconnect canary, agent access discovery, rollback runbook",
                rollbackAction: "Disable flag and keep existing workspace tabs unchanged",
                publicCopy: "Connect business apps once so Eva can use approved access without storing passwords or tokens in Workbench."
            )
        case .sharedBrowser2:
            return WorkbenchFeatureFlagDescriptor(
                key: self,
                dashboardEnvironmentKey: "VITE_EVAOS_SHARED_BROWSER_2",
                primaryIssue: "#97",
                owner: "Workbench + Dashboard + ws-proxy",
                surface: "Business Browser",
                navigationPlacement: "Workspace metadata",
                rolloutCriteria: "Runtime-status health proof, KasmVNC/noVNC canary, app handoff canary, customer rollback proof",
                rollbackAction: "Hide enhanced metadata while leaving the base Business Browser workspace visible",
                publicCopy: "Use one shared business browser for sign-in, CAPTCHA, and collaborative web tasks."
            )
        case .sessionCenter:
            return WorkbenchFeatureFlagDescriptor(
                key: self,
                dashboardEnvironmentKey: "VITE_EVAOS_SESSION_CENTER",
                primaryIssue: "#100",
                owner: "Workbench + Dashboard",
                surface: "Home",
                navigationPlacement: "Home",
                rolloutCriteria: "Runtime/session truth, queue/audit/Codex evidence, relaunch restore, dashboard parity, signed-in Workbench canary",
                rollbackAction: "Disable flag and keep direct workspace launch paths available",
                publicCopy: "See what Eva can do, what needs review, and where to jump back in."
            )
        case .approvalCenter:
            return WorkbenchFeatureFlagDescriptor(
                key: self,
                dashboardEnvironmentKey: "VITE_EVAOS_APPROVAL_CENTER",
                primaryIssue: "#144",
                owner: "Workbench + Broker",
                surface: "Approvals",
                navigationPlacement: "Home",
                rolloutCriteria: "Destination preview proof, broker pending-approval endpoint, deny/allow decision canary, spoofed-recipient manual QA",
                rollbackAction: "Disable flag and keep runtime approval decisions blocked in the broker/runtime layer",
                publicCopy: "Review risky agent actions with the actual destination, payload preview, and risk class before anything proceeds."
            )
        case .creativeStudio:
            return WorkbenchFeatureFlagDescriptor(
                key: self,
                dashboardEnvironmentKey: "VITE_EVAOS_CREATIVE_STUDIO",
                primaryIssue: "#102",
                owner: "Workbench + Creative Studio",
                surface: "Creative Studio",
                navigationPlacement: "Workspaces",
                rolloutCriteria: "Hosted Comfy path, login/embedded-page proof, no local GPU dependency",
                rollbackAction: "Disable flag and remove Creative Studio from the workspace list",
                publicCopy: "Open the hosted creative workflow studio from Workbench."
            )
        }
    }
}

public struct WorkbenchFeatureFlagDescriptor: Equatable, Sendable {
    public let key: WorkbenchFeatureFlagKey
    public let dashboardEnvironmentKey: String
    public let primaryIssue: String
    public let owner: String
    public let surface: String
    public let navigationPlacement: String
    public let defaultEnabled: Bool
    public let rolloutCriteria: String
    public let rollbackAction: String
    public let publicCopy: String

    public init(
        key: WorkbenchFeatureFlagKey,
        dashboardEnvironmentKey: String,
        primaryIssue: String,
        owner: String,
        surface: String,
        navigationPlacement: String,
        rolloutCriteria: String,
        rollbackAction: String,
        publicCopy: String
    ) {
        self.key = key
        self.dashboardEnvironmentKey = dashboardEnvironmentKey
        self.primaryIssue = primaryIssue
        self.owner = owner
        self.surface = surface
        self.navigationPlacement = navigationPlacement
        self.defaultEnabled = key.defaultValue
        self.rolloutCriteria = rolloutCriteria
        self.rollbackAction = rollbackAction
        self.publicCopy = publicCopy
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

    public static var descriptors: [WorkbenchFeatureFlagDescriptor] {
        WorkbenchFeatureFlagKey.allCases.map(\.descriptor)
    }
}
