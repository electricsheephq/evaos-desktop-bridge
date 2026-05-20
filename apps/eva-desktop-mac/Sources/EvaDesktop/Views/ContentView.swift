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
        .task {
            model.loadSelectedRuntime()
        }
    }
}

enum SidebarSelection: Hashable {
    case runtime(RuntimeKey)
    case bridge
}

