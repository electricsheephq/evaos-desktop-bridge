import EvaDesktopCore
import SwiftUI

struct SettingsView: View {
    @AppStorage("EvaDesktop.runtimeBaseDomain") private var runtimeBaseDomain = "ecs.electricsheephq.com"
    @AppStorage("EvaDesktop.dashboardBaseURL") private var dashboardBaseURL = "https://www.electricsheephq.com"
    @AppStorage("EvaDesktop.openDesignURL") private var openDesignURL = ""
    @AppStorage("EvaDesktop.updateManifestURL") private var updateManifestURL = AppBrand.defaultUpdateManifestURL

    var body: some View {
        Form {
            Text(AppBrand.visibleName)
                .font(.headline)

            TextField("Dashboard URL", text: $dashboardBaseURL)
            TextField("Gateway domain", text: $runtimeBaseDomain)
            TextField("OpenDesign URL", text: $openDesignURL)
            TextField("Update manifest URL", text: $updateManifestURL)

            Text("Dashboard and gateway-domain changes apply to new Workbench windows. OpenDesign URL changes apply when that gateway is opened or reconnected.")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("OpenDesign stays unavailable until a route is configured. Mac and iPhone actions run through audited OpenClaw/Hermes tools with dry-run and approval gates.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .onChange(of: openDesignURL) { _, newValue in
            NotificationCenter.default.post(name: .evaDesktopOpenDesignURLChanged, object: newValue)
        }
        .padding()
        .frame(width: 480)
    }
}

extension Notification.Name {
    static let evaDesktopOpenDesignURLChanged = Notification.Name("EvaDesktop.openDesignURLChanged")
}
