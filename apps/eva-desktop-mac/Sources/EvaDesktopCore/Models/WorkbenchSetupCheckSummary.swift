import Foundation

public enum WorkbenchSetupCheckSummary {
    public static func agentAccessText(
        connectorReady: Bool,
        macReady: Bool,
        iPhoneReady: Bool
    ) -> String {
        guard connectorReady && macReady else {
            return "Blocked. Turn on Mac Access and approve Accessibility and Screen Recording."
        }
        if iPhoneReady {
            return "Ready. Mac Access and iPhone Mirroring passed the local check."
        }
        return "Ready. Mac Access passed. Connect iPhone Mirroring when you want phone actions."
    }
}
