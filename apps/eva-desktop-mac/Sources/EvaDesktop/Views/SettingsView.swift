import SwiftUI

struct SettingsView: View {
    @AppStorage("EvaDesktop.runtimeBaseDomain") private var runtimeBaseDomain = "ecs.electricsheephq.com"
    @AppStorage("EvaDesktop.dashboardBaseURL") private var dashboardBaseURL = "https://www.electricsheephq.com"

    var body: some View {
        Form {
            TextField("Dashboard URL", text: $dashboardBaseURL)
            TextField("Runtime domain", text: $runtimeBaseDomain)

            Text("MVP settings are intentionally narrow. Local Mac control, iMessage, iPhone Mirroring, shell execution, and Screen Recording are deferred.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(width: 480)
    }
}

