import EvaDesktopCore
import SwiftUI

struct BridgePanelView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(AppBrand.bridgeSectionTitle)
                            .font(.title2.weight(.semibold))
                        Text("Connector status, permission readiness, and audit context for supervised local control.")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button {
                        model.signOut()
                    } label: {
                        Label("Revoke Session", systemImage: "xmark.shield")
                    }
                    .disabled(!model.isSignedIn)

                    Button {
                        model.refreshBridgeStatus()
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .disabled(model.isRefreshingBridgeStatus)
                }

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 14)], spacing: 14) {
                    BridgeOutputCard(title: "Desktop Bridge", text: model.bridgeStatusText)
                    BridgeOutputCard(title: "Customer Mac", text: model.customerMacStatusText)
                    BridgeOutputCard(title: "iPhone Mirroring", text: model.iPhoneMirroringStatusText)
                    BridgeOutputCard(title: "Codex Remote Control", text: model.codexRemoteControlStatusText)
                    BridgeOutputCard(title: "Screen Sharing", text: model.screenSharingStatusText)
                }

                BridgeOutputCard(title: "Bridge Capabilities", text: model.bridgeCapabilitiesText)
                BridgeOutputCard(title: "Customer Mac Capabilities", text: model.customerMacCapabilitiesText)
                BridgeOutputCard(title: "Audit Tail", text: model.bridgeAuditText)
            }
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(.background)
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
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.electricSheepCyan.opacity(0.10), lineWidth: 1)
        )
    }
}
