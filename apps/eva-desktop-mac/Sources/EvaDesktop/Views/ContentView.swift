import EvaDesktopCore
import SwiftUI

struct ContentView: View {
    @StateObject private var model = WorkbenchModel()
    @State private var sidebarSelection: SidebarSelection? = .runtime(.openclaw)

    var body: some View {
        NavigationSplitView {
            SidebarView(selection: $sidebarSelection, model: model)
        } detail: {
            switch sidebarSelection {
            case .runtime(let runtime):
                RuntimeDetailView(model: model, runtime: runtime)
            case .bridge:
                BridgePanelView(model: model)
            case .providersHub:
                WorkbenchPlaceholderView(
                    title: "Providers & Auth Hub",
                    systemImage: "person.badge.key",
                    message: "Workbench can dark-launch provider and auth management here without storing raw provider tokens in the app."
                )
            case .sharedBrowser2:
                WorkbenchPlaceholderView(
                    title: "Shared Browser 2.0",
                    systemImage: "globe.badge.chevron.backward",
                    message: "This preview stays separate from the existing Shared Browser gateway tab and does not replace its live runtime."
                )
            case .sessionCenter:
                WorkbenchPlaceholderView(
                    title: "Session Center",
                    systemImage: "rectangle.3.group.bubble.left",
                    message: "Future multi-session management can land here while the current gateway launch flow stays unchanged."
                )
            case .creativeStudio:
                CreativeStudioPlaceholderView(model: model)
            case .none:
                Text("Choose a runtime")
                    .foregroundStyle(.secondary)
            }
        }
        .onChange(of: sidebarSelection) { _, newValue in
            if case .runtime(let runtime) = newValue {
                model.selectedRuntime = runtime
                model.loadSelectedRuntime()
            }
        }
        .onChange(of: model.selectedRuntime) { _, runtime in
            if sidebarSelection != .runtime(runtime) {
                sidebarSelection = .runtime(runtime)
            }
        }
        .task {
            await model.bootstrap()
        }
        .onOpenURL { url in
            model.handleAuthCallback(url)
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
            model.stopManagedConnectorForAppTermination()
        }
    }
}

enum SidebarSelection: Hashable {
    case runtime(RuntimeKey)
    case bridge
    case providersHub
    case sharedBrowser2
    case sessionCenter
    case creativeStudio
}
