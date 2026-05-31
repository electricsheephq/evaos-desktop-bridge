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
        case .providersHub, .sharedBrowser2, .sessionCenter, .approvalCenter, .creativeStudio:
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
                surface: "Providers",
                navigationPlacement: "Settings",
                rolloutCriteria: "Broker provider-profile proof, provider connect/revoke canary, OpenClaw/Hermes grant discovery, rollback runbook",
                rollbackAction: "Disable flag and keep existing gateway tabs unchanged",
                publicCopy: "Connect provider accounts once so Eva agents can reuse brokered access without raw secrets in Workbench."
            )
        case .sharedBrowser2:
            return WorkbenchFeatureFlagDescriptor(
                key: self,
                dashboardEnvironmentKey: "VITE_EVAOS_SHARED_BROWSER_2",
                primaryIssue: "#97",
                owner: "Workbench + Dashboard + ws-proxy",
                surface: "Shared Browser",
                navigationPlacement: "Gateway metadata",
                rolloutCriteria: "Runtime-status health proof, KasmVNC/noVNC canary, provider handoff canary, customer rollback proof",
                rollbackAction: "Hide enhanced metadata while leaving the base Shared Browser gateway visible",
                publicCopy: "Use one shared VM browser for sign-in, CAPTCHA, and collaborative web tasks."
            )
        case .sessionCenter:
            return WorkbenchFeatureFlagDescriptor(
                key: self,
                dashboardEnvironmentKey: "VITE_EVAOS_SESSION_CENTER",
                primaryIssue: "#100",
                owner: "Workbench + Dashboard",
                surface: "Session Center",
                navigationPlacement: "Workspace",
                rolloutCriteria: "Runtime/session truth, queue/audit/Codex evidence, relaunch restore, dashboard parity, signed-in Workbench canary",
                rollbackAction: "Disable flag and keep direct gateway launch paths available",
                publicCopy: "See active Eva sessions, attention states, and where to jump back in."
            )
        case .approvalCenter:
            return WorkbenchFeatureFlagDescriptor(
                key: self,
                dashboardEnvironmentKey: "VITE_EVAOS_APPROVAL_CENTER",
                primaryIssue: "#144",
                owner: "Workbench + Broker",
                surface: "Approval Center",
                navigationPlacement: "Workspace",
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
                navigationPlacement: "Gateways",
                rolloutCriteria: "Hosted Comfy path, login/embedded-page proof, no local GPU dependency",
                rollbackAction: "Disable flag and remove Creative Studio from the gateway list",
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
