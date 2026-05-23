import EvaDesktopCore
import SwiftUI

struct BridgePanelView: View {
    @ObservedObject var model: WorkbenchModel
    @State private var supportDetailsExpanded = false

    private let setupColumns = [
        GridItem(.flexible(minimum: 340), spacing: 16),
        GridItem(.flexible(minimum: 340), spacing: 16)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                header
                readinessStrip
                setupSection
                accountAndUpdatesSection
                recentActivitySection
                supportDetailsSection
            }
            .foregroundStyle(Color.electricSheepPrimaryText)
            .padding(30)
            .frame(maxWidth: 1320, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color.electricSheepCanvas)
        .tint(Color.electricSheepGoldSoft)
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 18) {
            VStack(alignment: .leading, spacing: 9) {
                Text("Settings")
                    .font(.largeTitle.weight(.semibold))
                    .foregroundStyle(Color.electricSheepPrimaryText)

                Text("Connect this Mac, enable iPhone access, manage updates, and review what Eva can use.")
                    .foregroundStyle(Color.electricSheepSecondaryText)
                    .font(.title3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            Button {
                model.refreshBridgeStatus()
            } label: {
                Label(model.isRefreshingBridgeStatus ? "Checking..." : "Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(model.isRefreshingBridgeStatus)
            .help("Refresh connector, permissions, iPhone, pairing, and recent activity status.")
        }
    }

    private var readinessStrip: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionEyebrow("Readiness")

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 12)], spacing: 12) {
                ReadinessTile(
                    title: "Connector",
                    value: shortStatus(model.connectorServiceText, unchecked: "Unchecked"),
                    state: state(for: model.connectorServiceText),
                    help: "The secure local service that lets approved Eva actions reach this Mac."
                )

                ReadinessTile(
                    title: "Permissions",
                    value: permissionsReadiness,
                    state: state(for: model.customerMacStatusText),
                    help: "Accessibility and Screen Recording let Eva inspect the screen and press visible controls after approval."
                )

                ReadinessTile(
                    title: "Pairing",
                    value: model.pairedDevices.isEmpty ? "Not paired" : "Ready",
                    state: model.pairedDevices.isEmpty ? .needsAttention : .ready,
                    help: "Links this Mac to your private evaOS VM."
                )

                ReadinessTile(
                    title: "iPhone",
                    value: iPhoneReadiness,
                    state: state(for: model.iPhoneMirroringStatusText),
                    help: "Readiness for Apple iPhone Mirroring actions when you want Eva to help with phone workflows."
                )

                ReadinessTile(
                    title: "Agent Control",
                    value: shortStatus(model.controlSessionText, unchecked: "Unchecked"),
                    state: state(for: model.controlSessionText),
                    help: "The customer-granted session that lets your paired evaOS agent control this Mac and iPhone Mirroring."
                )
            }
        }
    }

    private var setupSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("Setup")

            LazyVGrid(columns: setupColumns, alignment: .leading, spacing: 16) {
                SetupStepCard(
                    number: "1",
                    systemImage: "desktopcomputer",
                    title: "Turn On Mac Access",
                    detail: shortStatus(model.connectorServiceText, unchecked: "Start the secure connector on this Mac."),
                    state: state(for: model.connectorServiceText),
                    badge: setupBadge(for: model.connectorServiceText, fallback: "Unchecked"),
                    actions: {
                        Button("Turn On") { model.startConnectorService() }
                            .buttonStyle(.borderedProminent)
                            .help("Starts the local connector service for this Workbench session.")
                        Button("Stop") { model.stopConnectorService() }
                            .buttonStyle(.bordered)
                            .help("Stops the local connector service on this Mac.")
                    }
                )

                SetupStepCard(
                    number: "2",
                    systemImage: "checkmark.shield",
                    title: "Allow Screen & Control",
                    detail: permissionSetupDetail,
                    state: state(for: model.customerMacStatusText),
                    badge: permissionBadge,
                    actions: {
                        Button("Accessibility") { model.openAccessibilitySettings() }
                            .help("Open macOS Accessibility settings so Eva can press approved visible controls.")
                        Button("Screen Recording") { model.openScreenRecordingSettings() }
                            .buttonStyle(.bordered)
                            .help("Open macOS Screen Recording settings so Eva can take redacted visual snapshots.")
                    }
                )

                SetupStepCard(
                    number: "3",
                    systemImage: "link.badge.plus",
                    title: "Link to evaOS",
                    detail: publicPairingStatus,
                    state: model.pairedDevices.isEmpty ? .needsAttention : .ready,
                    badge: model.pairedDevices.isEmpty ? "Not paired" : "Ready",
                    actions: {
                        Button(model.enrollmentCode == nil ? "Create Pairing Code" : "Copy Agent Prompt") {
                            if model.enrollmentCode == nil {
                                model.createMacEnrollment()
                            } else {
                                model.copyAgentPairingPrompt()
                            }
                        }
                        .disabled(!model.isSignedIn || model.isPairingMac)
                        .buttonStyle(.borderedProminent)
                        .help("Creates a short-lived code, then copies a prompt your Eva or OpenClaw agent can use to complete the link.")
                    }
                )

                SetupStepCard(
                    number: "4",
                    systemImage: "iphone",
                    title: "Connect iPhone",
                    detail: iPhoneSetupDetail,
                    state: state(for: model.iPhoneMirroringStatusText),
                    badge: iPhoneBadge,
                    actions: {
                        Button("Open iPhone Mirroring") { model.openIPhoneMirroring() }
                            .help("Open Apple's iPhone Mirroring app. Eva cannot act on the phone without approved tools.")
                        Button("Refresh") { model.refreshBridgeStatus() }
                            .buttonStyle(.bordered)
                            .disabled(model.isRefreshingBridgeStatus)
                            .help("Refresh iPhone Mirroring readiness.")
                    }
                )

                SetupStepCard(
                    number: "5",
                    systemImage: "sparkles",
                    title: "Check Setup",
                    detail: model.agentAccessTestText,
                    state: state(for: model.agentAccessTestText),
                    badge: setupBadge(for: model.agentAccessTestText, fallback: "Unchecked"),
                    actions: {
                        Button("Run Check") { model.testAgentAccess() }
                            .buttonStyle(.borderedProminent)
                            .help("Runs a local readiness check for Mac Access, permissions, and iPhone Mirroring.")
                        Button("Refresh") { model.refreshBridgeStatus() }
                            .buttonStyle(.bordered)
                            .disabled(model.isRefreshingBridgeStatus)
                            .help("Refresh all setup status without running the local check.")
                    }
                )

                SetupStepCard(
                    number: "6",
                    systemImage: "cursorarrow.motionlines",
                    title: "Agent Control",
                    detail: agentControlDetail,
                    state: state(for: model.controlSessionText),
                    badge: agentControlBadge,
                    actions: {
                        Button("Full Access") { model.startFullAccessControl() }
                            .buttonStyle(.borderedProminent)
                            .help("Start a visible session where your paired agent can click, type, scroll, use browsers, and operate iPhone Mirroring continuously.")
                        Button("Ask Permission") { model.startAskPermissionControl() }
                            .buttonStyle(.bordered)
                            .help("Start the same control surface, but ask again around risky clicks, taps, hotkeys, typing, sends, and other high-impact actions.")
                        Button("Stop") { model.stopAgentControl() }
                            .buttonStyle(.bordered)
                            .help("Stop the active agent control session.")
                        Button("Kill Switch", role: .destructive) { model.killAgentControl() }
                            .buttonStyle(.bordered)
                            .help("Immediately block future agent control until a new session is started.")
                    }
                )
            }
        }
    }

    private var accountAndUpdatesSection: some View {
        LazyVGrid(columns: setupColumns, alignment: .leading, spacing: 16) {
            ManagementCard(
                title: "Account & Access",
                systemImage: "xmark.shield",
                badge: model.isSignedIn ? "Signed in" : "Signed out",
                badgeState: model.isSignedIn ? .ready : .neutral,
                detail: accountAccessDetail,
                actions: {
                    Button("Sign Out") { model.signOut() }
                        .disabled(!model.isSignedIn)
                        .help("Signs out of Workbench and clears local runtime sessions.")

                    if !model.pairedDevices.isEmpty {
                        Button("Disconnect This Mac", role: .destructive) { model.revokeFirstPairedMac() }
                            .buttonStyle(.bordered)
                            .disabled(model.isPairingMac)
                            .help("Revokes this Mac link so evaOS agents cannot use the connector.")
                    }
                }
            )

            ManagementCard(
                title: "Updates",
                systemImage: "arrow.triangle.2.circlepath",
                badge: model.updateAvailable ? "Available" : "Current",
                badgeState: model.updateAvailable ? .warning : .neutral,
                detail: model.updateStatusText,
                actions: {
                    Button(model.isCheckingForUpdates ? "Checking..." : "Check Now") {
                        model.checkForUpdatesFromButton()
                    }
                    .disabled(model.isCheckingForUpdates)
                    .help("Checks the ElectricSheep Workbench update manifest.")

                    if model.updateAvailable {
                        Button("Download") {
                            model.openUpdateDownload()
                        }
                        .buttonStyle(.borderedProminent)
                        .help("Open the direct Workbench ZIP download if the in-app updater cannot install the release.")

                        if model.updateReleaseNotesURL != nil {
                            Button("Notes") {
                                model.openUpdateReleaseNotes()
                            }
                            .buttonStyle(.bordered)
                            .help("Open release notes for the available Workbench update.")
                        }
                    }
                }
            )
        }
    }

    private var recentActivitySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle("Recent Activity")

            LuxuryPanel {
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: "waveform.path.ecg")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(Color.electricSheepGoldSoft)
                        .frame(width: 32, height: 32)
                        .background(Color.electricSheepGoldSoft.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))

                    VStack(alignment: .leading, spacing: 6) {
                        Text(recentActivitySummary)
                            .font(.headline)
                            .foregroundStyle(Color.electricSheepPrimaryText)
                        Text("Detailed audit records stay in Support Details.")
                            .font(.callout)
                            .foregroundStyle(Color.electricSheepSecondaryText)
                    }

                    Spacer()
                }
            }
        }
    }

    private var supportDetailsSection: some View {
        DisclosureGroup(isExpanded: $supportDetailsExpanded) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 14)], spacing: 14) {
                BridgeOutputCard(title: "OpenClaw / Hermes", text: model.customerMacCapabilitiesText)
                BridgeOutputCard(title: "Agent Control", text: model.controlSessionText)
                BridgeOutputCard(title: "Codex Remote Control", text: model.codexRemoteControlStatusText)
                BridgeOutputCard(title: "Screen Sharing", text: model.screenSharingStatusText)
                BridgeOutputCard(title: "Bridge Capabilities", text: model.bridgeCapabilitiesText)
                BridgeOutputCard(title: "Pairing Details", text: model.pairingText)
                if model.enrollmentCode != nil {
                    LuxuryPanel {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("SUPPORT PAIRING FALLBACK")
                                .font(.system(.caption, design: .monospaced).weight(.semibold))
                                .tracking(2)
                                .foregroundStyle(Color.electricSheepMutedText)
                            Text("Use this only when an agent cannot reach the connector after the secure network link is ready.")
                                .font(.callout)
                                .foregroundStyle(Color.electricSheepSecondaryText)
                            Button("Pair From This Mac") {
                                model.completeLocalMacEnrollment()
                            }
                            .buttonStyle(.bordered)
                            .disabled(!model.isSignedIn || model.isPairingMac)
                            .help("Support fallback: complete pairing from this Mac without the agent.")
                        }
                    }
                }
            }

            BridgeOutputCard(title: "Audit Records", text: model.bridgeAuditText)
                .padding(.top, 14)
        } label: {
            HStack(spacing: 10) {
                SectionTitle("Support Details")
                StatusBadge(text: supportDetailsExpanded ? "Open" : "Collapsed", state: .neutral)
                Spacer()
            }
        }
        .tint(Color.electricSheepGoldSoft)
        .help("Advanced diagnostics for support. Customer setup only needs the sections above.")
    }

    private var permissionsReadiness: String {
        let setupState = state(for: model.customerMacStatusText)
        switch setupState {
        case .ready:
            return "Ready"
        case .neutral:
            return "Unchecked"
        case .needsAttention:
            return "Needs permission"
        case .warning:
            return "Blocked"
        }
    }

    private var iPhoneReadiness: String {
        let setupState = state(for: model.iPhoneMirroringStatusText)
        switch setupState {
        case .ready:
            return "Ready"
        case .neutral:
            return "Unchecked"
        case .needsAttention:
            return "Blocked"
        case .warning:
            return "Blocked"
        }
    }

    private var permissionSetupDetail: String {
        if state(for: model.customerMacStatusText) == .ready {
            return "Accessibility and Screen Recording are approved."
        }
        if isUnchecked(model.customerMacStatusText) {
            return "Open macOS settings and approve evaOS Workbench, evaOS Connector, or the Peekaboo helper macOS shows."
        }
        return shortStatus(model.customerMacStatusText, unchecked: "Open macOS settings and approve evaOS Workbench, evaOS Connector, or the Peekaboo helper shown there.")
    }

    private var permissionBadge: String {
        switch state(for: model.customerMacStatusText) {
        case .ready:
            return "Ready"
        case .neutral:
            return "Unchecked"
        case .needsAttention:
            return "Needs permission"
        case .warning:
            return "Blocked"
        }
    }

    private var publicPairingStatus: String {
        if !model.pairedDevices.isEmpty {
            let names = model.pairedDevices.map { $0.deviceName ?? $0.id }.joined(separator: ", ")
            return "Ready: \(names)."
        }

        if let code = model.enrollmentCode {
            var lines = ["Pairing code ready: \(code)"]
            if let expiresAt = model.enrollmentExpiresAt {
                lines.append("Expires \(expiresAt.formatted(date: .abbreviated, time: .shortened)).")
            }
            lines.append("Complete the link after the secure network connection is ready.")
            return lines.joined(separator: "\n")
        }

        if model.pairingText.lowercased().contains("failed") {
            return shortStatus(model.pairingText, unchecked: "Create a short-lived pairing code.")
        }

        return "Create a short-lived code to link this Mac to evaOS."
    }

    private var iPhoneSetupDetail: String {
        if state(for: model.iPhoneMirroringStatusText) == .ready {
            return "iPhone Mirroring is ready for approved phone actions."
        }
        if isUnchecked(model.iPhoneMirroringStatusText) {
            return "Open iPhone Mirroring when you want Eva to help with phone workflows."
        }
        return shortStatus(model.iPhoneMirroringStatusText, unchecked: "Open iPhone Mirroring when needed.")
    }

    private var iPhoneBadge: String {
        switch state(for: model.iPhoneMirroringStatusText) {
        case .ready:
            return "Ready"
        case .neutral:
            return "Unchecked"
        case .needsAttention:
            return "Blocked"
        case .warning:
            return "Blocked"
        }
    }

    private var accountAccessDetail: String {
        if model.pairedDevices.isEmpty {
            return "Sign out clears this app login. Link this Mac before disconnect controls appear."
        }
        return "Sign out clears this app login. Disconnect blocks future Eva access to this Mac."
    }

    private var agentControlDetail: String {
        if isUnchecked(model.controlSessionText) {
            return "Your agent can control this Mac and iPhone until you stop it."
        }
        return shortStatus(model.controlSessionText, unchecked: "Start a visible agent control session.")
    }

    private var agentControlBadge: String {
        let lower = model.controlSessionText.lowercased()
        if lower.contains("not active") {
            return "Inactive"
        }
        if lower.contains("full access") {
            return "Full Access"
        }
        if lower.contains("ask permission") {
            return "Ask Permission"
        }
        return setupBadge(for: model.controlSessionText, fallback: "Unchecked")
    }

    private var recentActivitySummary: String {
        let text = model.bridgeAuditText.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = text.lowercased()
        if text.isEmpty || lower.contains("not checked") {
            return "Check setup to load recent activity."
        }
        if lower.contains("no audit events") {
            return "No agent actions recorded yet."
        }
        if lower.contains("unavailable") || lower.contains("failed") && lower.contains("audit") {
            return "Recent activity needs attention. Open Support Details for diagnostics."
        }
        let lines = text.split(separator: "\n").filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        let failed = lines.filter { $0.lowercased().contains("failed") }.count
        if failed > 0 {
            return "\(lines.count) recent events recorded; \(failed) need attention."
        }
        return "\(lines.count) recent events recorded. No failures in the latest sample."
    }

    private func shortStatus(_ value: String, unchecked: String) -> String {
        if isUnchecked(value) {
            return unchecked
        }
        return firstLine(value)
    }

    private func setupBadge(for value: String, fallback: String) -> String {
        if isUnchecked(value) {
            return fallback
        }
        switch state(for: value) {
        case .ready:
            return "Ready"
        case .needsAttention:
            return value.lowercased().contains("permission") ? "Needs permission" : "Blocked"
        case .warning:
            return "Blocked"
        case .neutral:
            return fallback
        }
    }

    private func firstLine(_ value: String) -> String {
        let line = value.split(separator: "\n").first.map(String.init) ?? ""
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "Unchecked" : trimmed
    }

    private func isUnchecked(_ value: String) -> Bool {
        let lower = value.lowercased()
        return lower.contains("not checked") || lower.contains("auto-checking") || lower.contains("check setup when")
    }

    private func state(for value: String) -> SetupVisualState {
        let lower = value.lowercased()
        if isUnchecked(value) || lower.contains("checking") {
            return .neutral
        }
        if lower.contains("update") && lower.contains("available") {
            return .warning
        }
        if lower.contains("ready") || lower.contains("paired") || lower.contains("linked") || lower.contains("available") || lower.contains("running") || lower.contains("granted") || lower.contains("passed") {
            return .ready
        }
        if lower.contains("not running") || lower.contains("unavailable") || lower.contains("not paired") || lower.contains("needs") || lower.contains("failed") || lower.contains("missing") || lower.contains("invalid") || lower.contains("offline") || lower.contains("error") || lower.contains("attention") {
            return .needsAttention
        }
        return .needsAttention
    }
}

private enum SetupVisualState: Equatable {
    case ready
    case needsAttention
    case warning
    case neutral

    var color: Color {
        switch self {
        case .ready:
            return Color.electricSheepSuccess
        case .needsAttention:
            return Color.electricSheepGoldSoft
        case .warning:
            return Color.electricSheepAmber
        case .neutral:
            return Color.electricSheepMutedText
        }
    }

    var fill: Color {
        switch self {
        case .ready:
            return Color.electricSheepSuccess.opacity(0.12)
        case .needsAttention, .warning:
            return Color.electricSheepGoldSoft.opacity(0.14)
        case .neutral:
            return Color.white.opacity(0.06)
        }
    }
}

private struct SectionEyebrow: View {
    let title: String

    init(_ title: String) {
        self.title = title
    }

    var body: some View {
        Text(title.uppercased())
            .font(.system(.caption, design: .monospaced).weight(.semibold))
            .tracking(3)
            .foregroundStyle(Color.electricSheepGoldSoft)
    }
}

private struct SectionTitle: View {
    let title: String

    init(_ title: String) {
        self.title = title
    }

    var body: some View {
        Text(title)
            .font(.title2.weight(.semibold))
            .foregroundStyle(Color.electricSheepPrimaryText)
    }
}

private struct LuxuryPanel<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(Color.electricSheepLineWarm, lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.20), radius: 16, y: 8)
    }
}

private struct ReadinessTile: View {
    let title: String
    let value: String
    let state: SetupVisualState
    let help: String

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text(title.uppercased())
                    .font(.system(.caption2, design: .monospaced).weight(.semibold))
                    .tracking(2)
                    .foregroundStyle(Color.electricSheepMutedText)
                Spacer()
                Circle()
                    .fill(state.color)
                    .frame(width: 8, height: 8)
                    .shadow(color: state.color.opacity(0.4), radius: 5)
            }
            Text(value)
                .font(.headline.weight(.semibold))
                .foregroundStyle(Color.electricSheepPrimaryText)
                .lineLimit(2)
                .minimumScaleFactor(0.82)
        }
        .padding(15)
        .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.electricSheepLine, lineWidth: 1)
        )
        .help(help)
    }
}

private struct SetupStepCard<Actions: View>: View {
    let number: String
    let systemImage: String
    let title: String
    let detail: String
    let state: SetupVisualState
    let badge: String
    @ViewBuilder let actions: Actions

    var body: some View {
        LuxuryPanel {
            VStack(alignment: .leading, spacing: 15) {
                HStack(spacing: 12) {
                    Text(number)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Color.electricSheepCanvasEdge)
                        .frame(width: 27, height: 27)
                        .background(Color.electricSheepGoldSoft, in: Circle())

                    Image(systemName: systemImage)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(state.color)
                        .frame(width: 18)

                    Text(title)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(Color.electricSheepPrimaryText)

                    Spacer()
                    StatusBadge(text: badge, state: state)
                }

                Text(detail)
                    .font(.callout)
                    .foregroundStyle(Color.electricSheepSecondaryText)
                    .lineLimit(5)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)

                HStack(spacing: 9) {
                    actions
                }
            }
        }
    }
}

private struct ManagementCard<Actions: View>: View {
    let title: String
    let systemImage: String
    let badge: String
    let badgeState: SetupVisualState
    let detail: String
    @ViewBuilder let actions: Actions

    var body: some View {
        LuxuryPanel {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 10) {
                    Image(systemName: systemImage)
                        .foregroundStyle(badgeState.color)
                        .frame(width: 18)
                    Text(title)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(Color.electricSheepPrimaryText)
                    Spacer()
                    StatusBadge(text: badge, state: badgeState)
                }

                Text(detail)
                    .font(.callout)
                    .foregroundStyle(Color.electricSheepSecondaryText)
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 9) {
                    actions
                }
            }
        }
    }
}

private struct StatusBadge: View {
    let text: String
    let state: SetupVisualState

    var body: some View {
        Text(text)
            .font(.system(.caption, design: .rounded).weight(.semibold))
            .foregroundStyle(state.color)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(state.fill, in: Capsule())
            .overlay(Capsule().stroke(state.color.opacity(0.22), lineWidth: 1))
    }
}

private struct BridgeOutputCard: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(title.uppercased())
                .font(.system(.caption, design: .monospaced).weight(.semibold))
                .tracking(2)
                .foregroundStyle(Color.electricSheepMutedText)

            Text(displayText)
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(Color.electricSheepSecondaryText)
                .lineLimit(9)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.electricSheepCanvasEdge, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.electricSheepLine, lineWidth: 1)
        )
    }

    private var displayText: String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "Unchecked" : trimmed
    }
}
