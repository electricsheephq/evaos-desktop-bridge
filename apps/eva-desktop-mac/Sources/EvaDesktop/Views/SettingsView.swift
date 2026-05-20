import EvaDesktopCore
import SwiftUI

struct SettingsView: View {
    @AppStorage("EvaDesktop.runtimeBaseDomain") private var runtimeBaseDomain = "ecs.electricsheephq.com"
    @AppStorage("EvaDesktop.dashboardBaseURL") private var dashboardBaseURL = "https://www.electricsheephq.com"
    @AppStorage("EvaDesktop.openDesignURL") private var openDesignURL = ""

    var body: some View {
        Form {
            Text(AppBrand.visibleName)
                .font(.headline)

            TextField("Dashboard URL", text: $dashboardBaseURL)
            TextField("Gateway domain", text: $runtimeBaseDomain)
            TextField("OpenDesign URL", text: $openDesignURL)

            Text("Dashboard and gateway-domain changes apply to new Workbench windows. OpenDesign URL changes apply when that gateway is opened or reconnected.")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("OpenDesign stays unavailable until a route is configured. Local Mac control and iPhone Mirroring appear only as bridge status in this canary; live actions stay behind audited OpenClaw tools.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(width: 480)
    }
}
