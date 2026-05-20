import SwiftUI

struct BridgePanelView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Desktop Bridge")
                            .font(.title2.weight(.semibold))
                        Text("Read-only local bridge status and audit context. Local control is intentionally outside the MVP.")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button {
                        model.refreshBridgeStatus()
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                }

                BridgeOutputCard(title: "Status", text: model.bridgeStatusText)
                BridgeOutputCard(title: "Capabilities", text: model.bridgeCapabilitiesText)
                BridgeOutputCard(title: "Audit Tail", text: model.bridgeAuditText)
            }
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .task {
            model.refreshBridgeStatus()
        }
    }
}

private struct BridgeOutputCard: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)

            ScrollView(.horizontal) {
                Text(text.isEmpty ? "No output." : text)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
}

