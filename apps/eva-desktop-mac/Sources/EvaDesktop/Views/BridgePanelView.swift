import EvaDesktopCore
import SwiftUI

struct BridgePanelView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 270), spacing: 14)], spacing: 14) {
                    SetupStepCard(
                        number: "1",
                        title: "Connect This Mac",
                        status: model.connectorServiceText,
                        actions: {
                            Button("Start Connector") { model.startConnectorService() }
                            Button("Stop") { model.stopConnectorService() }
                                .buttonStyle(.bordered)
                        }
                    )

                    SetupStepCard(
                        number: "2",
                        title: "Enable Permissions",
                        status: "Accessibility lets agents inspect visible controls. Screen Recording enables redacted screenshots. Apple Events stays optional.",
                        actions: {
                            Button("Accessibility") { model.openAccessibilitySettings() }
                            Button("Screen Recording") { model.openScreenRecordingSettings() }
                                .buttonStyle(.bordered)
                        }
                    )

                    SetupStepCard(
                        number: "3",
                        title: "Pair with evaOS VM",
                        status: pairingStatus,
                        actions: {
                            Button(model.enrollmentCode == nil ? "Create Pairing Code" : "Complete Pairing") {
                                if model.enrollmentCode == nil {
                                    model.createMacEnrollment()
                                } else {
                                    model.completeLocalMacEnrollment()
                                }
                            }
                            .disabled(!model.isSignedIn || model.isPairingMac)

                            if !model.pairedDevices.isEmpty {
                                Button("Revoke") { model.revokeFirstPairedMac() }
                                    .buttonStyle(.bordered)
                                    .disabled(model.isPairingMac)
                            }
                        }
                    )

                    SetupStepCard(
                        number: "4",
                        title: "Connect iPhone",
                        status: model.iPhoneMirroringStatusText,
                        actions: {
                            Button("Open iPhone Mirroring") { model.openIPhoneMirroring() }
                            Button("Refresh") { model.refreshBridgeStatus() }
                                .buttonStyle(.bordered)
                        }
                    )

                    SetupStepCard(
                        number: "5",
                        title: "Test Agent Access",
                        status: model.customerMacStatusText,
                        actions: {
                            Button("Run Local Smoke") { model.testAgentAccess() }
                            Button("Refresh") { model.refreshBridgeStatus() }
                                .buttonStyle(.bordered)
                                .disabled(model.isRefreshingBridgeStatus)
                        }
                    )

                    SetupStepCard(
                        number: "6",
                        title: "Revoke / Disconnect",
                        status: "Revoking the Workbench session signs out this app. Revoking a Mac pairing blocks future VM agent access to this connector grant.",
                        actions: {
                            Button("Revoke Session") { model.signOut() }
                                .disabled(!model.isSignedIn)
                            if !model.pairedDevices.isEmpty {
                                Button("Revoke Mac") { model.revokeFirstPairedMac() }
                                    .buttonStyle(.bordered)
                            }
                        }
                    )
                }

                VStack(alignment: .leading, spacing: 14) {
                    Text("Agent Tool Readiness")
                        .font(.title3.weight(.semibold))

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 14)], spacing: 14) {
                        BridgeOutputCard(title: "OpenClaw / Hermes Tool Surface", text: model.customerMacCapabilitiesText)
                        BridgeOutputCard(title: "Codex Remote Control", text: model.codexRemoteControlStatusText)
                        BridgeOutputCard(title: "Screen Sharing", text: model.screenSharingStatusText)
                    }

                    BridgeOutputCard(title: "Audit Tail", text: model.bridgeAuditText)
                }
            }
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(.background)
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Agent Control Setup")
                    .font(.title2.weight(.semibold))
                Text("Connect this Mac to evaOS so OpenClaw and Hermes agents can use audited Mac and iPhone tools.")
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                model.refreshBridgeStatus()
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(model.isRefreshingBridgeStatus)
        }
    }

    private var pairingStatus: String {
        var lines = [model.pairingText]
        if let code = model.enrollmentCode {
            lines.append("Pairing code: \(code)")
        }
        if let expiresAt = model.enrollmentExpiresAt {
            lines.append("Expires: \(expiresAt.formatted(date: .abbreviated, time: .shortened))")
        }
        if !model.pairedDevices.isEmpty {
            lines.append("Paired Macs: \(model.pairedDevices.map { $0.deviceName ?? $0.id }.joined(separator: ", "))")
        }
        return lines.joined(separator: "\n")
    }
}

private struct SetupStepCard<Actions: View>: View {
    let number: String
    let title: String
    let status: String
    @ViewBuilder let actions: Actions

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Text(number)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.black)
                    .frame(width: 24, height: 24)
                    .background(Color.electricSheepCyan, in: Circle())
                Text(title)
                    .font(.headline)
                Spacer()
            }

            Text(status.isEmpty ? "Not checked yet." : status)
                .font(.callout)
                .foregroundStyle(.secondary)
                .lineLimit(10)
                .textSelection(.enabled)

            HStack(spacing: 8) {
                actions
            }
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.electricSheepCyan.opacity(0.12), lineWidth: 1)
        )
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
                    .font(.callout)
                    .foregroundStyle(.secondary)
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
