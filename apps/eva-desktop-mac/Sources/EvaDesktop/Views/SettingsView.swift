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
            TextField("Gateway domain", text: $runtimeBaseDomain)
                .help("Used to resolve customer-scoped gateway hosts for OpenClaw, Hermes, Mission Control, Shared Browser, and Terminal.")
            TextField("Update manifest URL", text: $updateManifestURL)
                .help("Workbench checks this signed release manifest for app updates.")

            Text("Advanced network and update settings. Dashboard and gateway-domain changes apply to new Workbench windows.")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("OpenDesign and the other gateways use short-lived evaOS sessions. Mac and iPhone actions run through audited OpenClaw/Hermes tools with dry-run and approval gates.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(width: 480)
    }
}
