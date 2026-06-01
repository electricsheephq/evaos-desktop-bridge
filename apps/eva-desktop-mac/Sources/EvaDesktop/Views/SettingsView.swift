import EvaDesktopCore
import SwiftUI

struct SettingsView: View {
    @AppStorage("EvaDesktop.runtimeBaseDomain") private var runtimeBaseDomain = "ecs.electricsheephq.com"
    @AppStorage("EvaDesktop.dashboardBaseURL") private var dashboardBaseURL = "https://www.electricsheephq.com"
    @AppStorage("EvaDesktop.updateManifestURL") private var updateManifestURL = AppBrand.defaultUpdateManifestURL

    var body: some View {
        Form {
            Text("Advanced")
                .font(.headline)

            TextField("Dashboard URL", text: $dashboardBaseURL)
                .help("Used for ElectricSheep login and desktop session handoff.")
            TextField("Workspace domain", text: $runtimeBaseDomain)
                .help("Used to resolve customer-scoped workspace hosts for Eva Workspace, Agent Workspace, Mission Control, Business Browser, and Terminal.")
            TextField("Update manifest URL", text: $updateManifestURL)
                .help("Workbench checks this signed release manifest for app updates.")

            Text("Advanced network and update settings. Dashboard and workspace-domain changes apply to new Workbench windows.")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("Design Workspace and the other workspaces use short-lived evaOS sessions. Mac and iPhone actions run through audited agent tools with customer-controlled Full Access or Ask Permission mode.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(width: 480)
    }
}
