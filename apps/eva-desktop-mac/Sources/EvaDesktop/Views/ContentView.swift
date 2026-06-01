import EvaDesktopCore
import SwiftUI

struct ContentView: View {
    @StateObject private var model = WorkbenchModel()
    @State private var sidebarSelection: SidebarSelection? = .sessionCenter

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
                if model.featureFlags.isEnabled(.sessionCenter) {
                    SessionCenterView(
                        model: model,
                        openConnectedApps: {
                            sidebarSelection = .providersHub
                        },
                        openApprovals: {
                            sidebarSelection = .approvalCenter
                        }
                    ) { runtime in
                        sidebarSelection = .runtime(runtime)
                        model.selectedRuntime = runtime
                        model.loadSelectedRuntime()
                    }
                } else {
                    RuntimeDetailView(model: model, runtime: model.selectedRuntime)
                }
            case .approvalCenter:
                if model.featureFlags.isEnabled(.approvalCenter) {
                    ApprovalCenterView(model: model)
                } else {
                    RuntimeDetailView(model: model, runtime: model.selectedRuntime)
                }
            case .none:
                RuntimeDetailView(model: model, runtime: model.selectedRuntime)
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
            let shouldLoadInitialRuntime: Bool
            if case .runtime = sidebarSelection {
                shouldLoadInitialRuntime = true
            } else {
                shouldLoadInitialRuntime = !model.featureFlags.isEnabled(.sessionCenter)
            }
            await model.bootstrap(loadInitialRuntime: shouldLoadInitialRuntime)
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
