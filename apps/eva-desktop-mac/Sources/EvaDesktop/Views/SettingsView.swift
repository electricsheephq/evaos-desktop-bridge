import EvaDesktopCore
import SwiftUI

struct SettingsView: View {
    @AppStorage("EvaDesktop.runtimeBaseDomain") private var runtimeBaseDomain = "ecs.electricsheephq.com"
    @AppStorage("EvaDesktop.dashboardBaseURL") private var dashboardBaseURL = "https://www.electricsheephq.com"

    var body: some View {
        Form {
            Text(AppBrand.visibleName)
                .font(.headline)

            TextField("Dashboard URL", text: $dashboardBaseURL)
            TextField("Gateway domain", text: $runtimeBaseDomain)

            Text("These settings are read when a new Workbench window is opened. Existing windows rebuild gateway clients when changed from the main toolbar in a later sprint.")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("MVP settings are intentionally narrow. Local Mac control, iMessage, iPhone Mirroring, shell execution, and Screen Recording are deferred.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(width: 480)
    }
}
