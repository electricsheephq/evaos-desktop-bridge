import EvaDesktopCore
import SwiftUI

struct BridgePanelView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                statusStrip
                setupChecklist
                updateCard
                readinessSection
            }
            .padding(28)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(.background)
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 18) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Connect Your Mac")
                    .font(.largeTitle.weight(.semibold))
                Text("Pair this computer with evaOS so your agents can use supervised Mac and iPhone tools with clear approval and audit trails.")
                    .foregroundStyle(.secondary)
                    .font(.title3)
                    .fixedSize(horizontal: false, vertical: true)
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

    private var statusStrip: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 12)], spacing: 12) {
            StatusTile(title: "Connector", value: firstLine(model.connectorServiceText), state: state(for: model.connectorServiceText))
            StatusTile(title: "Mac Permissions", value: firstLine(model.customerMacStatusText), state: state(for: model.customerMacStatusText))
            StatusTile(title: "iPhone", value: firstLine(model.iPhoneMirroringStatusText), state: state(for: model.iPhoneMirroringStatusText))
            StatusTile(title: "VM Pairing", value: model.pairedDevices.isEmpty ? "Not paired" : "Paired", state: model.pairedDevices.isEmpty ? .needsAttention : .ready)
        }
    }

    private var setupChecklist: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Setup")
                .font(.title2.weight(.semibold))

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 300), spacing: 14)], spacing: 14) {
                SetupStepCard(
                    number: "1",
                    systemImage: "desktopcomputer",
                    title: "Start Mac Connector",
                    status: model.connectorServiceText,
                    state: state(for: model.connectorServiceText),
                    actions: {
                        Button("Start") { model.startConnectorService() }
                        Button("Stop") { model.stopConnectorService() }
                            .buttonStyle(.bordered)
                    }
                )

                SetupStepCard(
                    number: "2",
                    systemImage: "checkmark.shield",
                    title: "Enable Permissions",
                    status: "Approve Accessibility and Screen Recording for the app or helper macOS shows. These let Eva see the screen and press visible controls.",
                    state: state(for: model.customerMacStatusText),
                    actions: {
                        Button("Accessibility") { model.openAccessibilitySettings() }
                        Button("Screen Recording") { model.openScreenRecordingSettings() }
                            .buttonStyle(.bordered)
                    }
                )

                SetupStepCard(
                    number: "3",
                    systemImage: "link.badge.plus",
                    title: "Pair With evaOS",
                    status: pairingStatus,
                    state: model.pairedDevices.isEmpty ? .needsAttention : .ready,
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
                    systemImage: "iphone",
                    title: "Connect iPhone",
                    status: model.iPhoneMirroringStatusText,
                    state: state(for: model.iPhoneMirroringStatusText),
                    actions: {
                        Button("Open iPhone Mirroring") { model.openIPhoneMirroring() }
                        Button("Refresh") { model.refreshBridgeStatus() }
                            .buttonStyle(.bordered)
                    }
                )

                SetupStepCard(
                    number: "5",
                    systemImage: "sparkles",
                    title: "Test Agent Access",
                    status: model.customerMacStatusText,
                    state: state(for: model.customerMacStatusText),
                    actions: {
                        Button("Run Local Test") { model.testAgentAccess() }
                        Button("Refresh") { model.refreshBridgeStatus() }
                            .buttonStyle(.bordered)
                            .disabled(model.isRefreshingBridgeStatus)
                    }
                )

                SetupStepCard(
                    number: "6",
                    systemImage: "xmark.shield",
                    title: "Sign Out / Revoke",
                    status: "Sign out clears this app login. Revoke Mac Access blocks VM agents from this connector grant.",
                    state: .neutral,
                    actions: {
                        Button("Sign Out") { model.signOut() }
                            .disabled(!model.isSignedIn)
                        if !model.pairedDevices.isEmpty {
                            Button("Revoke Mac Access") { model.revokeFirstPairedMac() }
                                .buttonStyle(.bordered)
                        }
                    }
                )
            }
        }
    }

    private var updateCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .foregroundStyle(Color.electricSheepCyan)
                Text("Updates")
                    .font(.headline)
                StatusBadge(text: model.updateAvailable ? "Available" : "Auto-checking", state: model.updateAvailable ? .warning : .neutral)
                Spacer()
            }

            Text(model.updateStatusText)
                .font(.callout)
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                Button(model.isCheckingForUpdates ? "Checking..." : "Check Now") {
                    model.checkForUpdatesFromButton()
                }
                .disabled(model.isCheckingForUpdates)

                if model.updateAvailable {
                    Button("Download Update") {
                        model.openUpdateDownload()
                    }
                    .buttonStyle(.borderedProminent)
                    if model.updateReleaseNotesURL != nil {
                        Button("Release Notes") {
                            model.openUpdateReleaseNotes()
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.electricSheepCyan.opacity(0.12), lineWidth: 1)
        )
    }

    private var readinessSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Agent Tool Readiness")
                .font(.title2.weight(.semibold))

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 14)], spacing: 14) {
                BridgeOutputCard(title: "OpenClaw / Hermes", text: model.customerMacCapabilitiesText)
                BridgeOutputCard(title: "Codex Remote Control", text: model.codexRemoteControlStatusText)
                BridgeOutputCard(title: "Screen Sharing", text: model.screenSharingStatusText)
            }

            BridgeOutputCard(title: "Audit Tail", text: model.bridgeAuditText)
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
            lines.append("Paired: \(model.pairedDevices.map { $0.deviceName ?? $0.id }.joined(separator: ", "))")
        }
        return lines.joined(separator: "\n")
    }

    private func firstLine(_ value: String) -> String {
        value.split(separator: "\n").first.map(String.init) ?? "Not checked"
    }

    private func state(for value: String) -> SetupVisualState {
        let lower = value.lowercased()
        if lower.contains("not checked") || lower.contains("auto-checking") {
            return .neutral
        }
        if lower.contains("not running") || lower.contains("unavailable") || lower.contains("not paired") || lower.contains("needs") || lower.contains("failed") || lower.contains("missing") || lower.contains("invalid") || lower.contains("offline") || lower.contains("error") {
            return .needsAttention
        }
        if lower.contains("ready") || lower.contains("paired") || lower.contains("available") || lower.contains("running") || lower.contains("granted") || lower.contains("test passed") {
            return .ready
        }
        return .needsAttention
    }
}

private enum SetupVisualState {
    case ready
    case needsAttention
    case warning
    case neutral

    var label: String {
        switch self {
        case .ready:
            return "Ready"
        case .needsAttention:
            return "Needs setup"
        case .warning:
            return "Update"
        case .neutral:
            return "Info"
        }
    }

    var color: Color {
        switch self {
        case .ready:
            return Color.electricSheepCyan
        case .needsAttention:
            return Color.electricSheepAmber
        case .warning:
            return Color.electricSheepAmber
        case .neutral:
            return .secondary
        }
    }
}

private struct StatusTile: View {
    let title: String
    let value: String
    let state: SetupVisualState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Circle()
                    .fill(state.color)
                    .frame(width: 8, height: 8)
            }
            Text(value)
                .font(.headline)
                .lineLimit(2)
                .minimumScaleFactor(0.85)
        }
        .padding(14)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}

private struct SetupStepCard<Actions: View>: View {
    let number: String
    let systemImage: String
    let title: String
    let status: String
    let state: SetupVisualState
    @ViewBuilder let actions: Actions

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Text(number)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.black)
                    .frame(width: 24, height: 24)
                    .background(Color.electricSheepCyan, in: Circle())
                Image(systemName: systemImage)
                    .foregroundStyle(state.color)
                    .frame(width: 18)
                Text(title)
                    .font(.headline)
                Spacer()
                StatusBadge(text: state.label, state: state)
            }

            Text(status.isEmpty ? "Not checked yet." : status)
                .font(.callout)
                .foregroundStyle(.secondary)
                .lineLimit(8)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)

            HStack(spacing: 8) {
                actions
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(state.color.opacity(0.16), lineWidth: 1)
        )
    }
}

private struct StatusBadge: View {
    let text: String
    let state: SetupVisualState

    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(state.color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(state.color.opacity(0.12), in: Capsule())
    }
}

private struct BridgeOutputCard: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)

            Text(text.isEmpty ? "Not checked yet." : text)
                .font(.callout)
                .foregroundStyle(.secondary)
                .lineLimit(8)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.electricSheepCyan.opacity(0.10), lineWidth: 1)
        )
    }
}
