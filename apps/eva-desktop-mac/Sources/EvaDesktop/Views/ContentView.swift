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
                ProvidersHubView(model: model)
            case .sessionCenter:
                SessionCenterView(model: model) { runtime in
                    sidebarSelection = .runtime(runtime)
                    model.selectedRuntime = runtime
                    model.loadSelectedRuntime()
                }
            case .approvalCenter:
                ApprovalCenterView(model: model)
            case .none:
                Text("Choose a runtime")
                    .foregroundStyle(.secondary)
            }
        }
        .onChange(of: sidebarSelection) { _, newValue in
            model.setApprovalCenterVisible(newValue == .approvalCenter)
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
        .onChange(of: model.runtimeNavigationRequest) { _, request in
            guard let request else { return }
            sidebarSelection = .runtime(request.runtime)
            model.selectedRuntime = request.runtime
        }
        .task {
            model.setApprovalCenterVisible(sidebarSelection == .approvalCenter)
            await model.bootstrap()
            model.startApprovalCenterPolling()
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
    case sessionCenter
    case approvalCenter
}
