import EvaDesktopCore
import SwiftUI

struct ProvidersHubView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        WorkbenchSurface(title: "Providers", subtitle: "Connect provider accounts in the Shared Browser on your evaOS server so agents can reuse the VM browser session.") {
            HStack(spacing: 10) {
                StatusPill(title: model.providerHubStatusText, systemImage: "key", tint: providerStatusTint)
                Spacer()
                Button {
                    Task {
                        await model.refreshProviderProfiles()
                    }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .disabled(!model.isSignedIn || model.providerActionInFlight != nil)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 300), spacing: 14)], alignment: .leading, spacing: 14) {
                ForEach(model.providerProfiles) { profile in
                    ProviderProfileCard(
                        profile: profile,
                        isSignedIn: model.isSignedIn,
                        isBusy: model.providerActionInFlight == profile.key,
                        connect: { model.connectProvider(profile.key) },
                        makeActive: { model.switchProvider(profile.key) },
                        mintGrant: { model.mintOpenClawProviderGrant(profile.key) },
                        revoke: { model.revokeProvider(profile.key) }
                    )
                }
            }

            CapabilityManifestPanel(
                statusText: model.capabilityManifestStatusText,
                summary: model.capabilityManifestSummary
            ) {
                Task {
                    await model.refreshCapabilityManifest()
                }
            }
            .disabled(!model.isSignedIn || model.isRefreshingCapabilityManifest)

            WorkbenchInfoPanel(
                title: "Credential Boundary",
                systemImage: "key.slash",
                detail: "Workbench stores metadata and readiness only. Provider sign-in happens in the shared VM browser; raw provider tokens stay out of the Mac app model."
            )
        }
    }

    private var providerStatusTint: Color {
        if model.providerHubStatusText == "Ready" {
            return .electricSheepSuccess
        }
        if model.providerHubStatusText.lowercased().contains("blocked") || model.providerHubStatusText.lowercased().contains("failed") {
            return .electricSheepDanger
        }
        return .electricSheepGoldSoft
    }
}

private struct CapabilityManifestPanel: View {
    let statusText: String
    let summary: WorkbenchCapabilityManifestSummary?
    let refresh: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                RuntimeIconBadge(systemImage: "checklist.checked", tint: tint)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Capability Manifest")
                        .font(.headline)
                        .foregroundStyle(Color.electricSheepPrimaryText)
                    Text(statusText)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint)
                }
                Spacer()
                Button {
                    refresh()
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
            }

            if let summary {
                Text("\(summary.agentID) -> \(summary.ownerID)")
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepSecondaryText)
                Text("Expires \(summary.expiresAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepMutedText)
                grantLine("Allowed", tools: summary.tools(for: .allowed))
                grantLine("Approval", tools: summary.tools(for: .requiresApproval))
                grantLine("Denied", tools: summary.tools(for: .denied))
            } else {
                Text("Signed manifests are fetched from the broker and cached locally. Workbench renders only safe grant metadata; raw JWTs and provider secrets stay hidden.")
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepMutedText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .background(Color.electricSheepSurfaceRaised, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.electricSheepLineWarm, lineWidth: 1)
        )
    }

    private var tint: Color {
        let lowercased = statusText.lowercased()
        if lowercased.contains("ready") || lowercased.contains("cached") {
            return .electricSheepSuccess
        }
        if lowercased.contains("unavailable") || lowercased.contains("expired") || lowercased.contains("policy") {
            return .electricSheepDanger
        }
        return .electricSheepGoldSoft
    }

    @ViewBuilder
    private func grantLine(_ label: String, tools: [String]) -> some View {
        if !tools.isEmpty {
            Text("\(label): \(tools.prefix(4).joined(separator: ", "))\(tools.count > 4 ? " +" + String(tools.count - 4) : "")")
                .font(.caption)
                .foregroundStyle(Color.electricSheepMutedText)
                .lineLimit(2)
        }
    }
}

struct SessionCenterView: View {
    @ObservedObject var model: WorkbenchModel
    let jumpToRuntime: (RuntimeKey) -> Void

    var body: some View {
        WorkbenchSurface(title: "Session Center", subtitle: "One place to see active gateways, attention states, Mac control readiness, and recent activity.") {
            HStack(spacing: 10) {
                StatusPill(title: model.sessionCenterStatusText, systemImage: "rectangle.3.group.bubble.left", tint: sessionCenterTint)
                Spacer()
                Button {
                    Task {
                        await model.refreshSessionCenterState()
                    }
                } label: {
                    Label(model.isRefreshingSessionCenter ? "Refreshing" : "Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .disabled(!model.isSignedIn || model.isRefreshingSessionCenter)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                ForEach(model.sessionRecords) { record in
                    SessionRecordCard(record: record, systemImage: systemImage(for: record)) {
                        if let runtime = WorkbenchSessionContract.brokerRuntimeToOpen(for: record) {
                            jumpToRuntime(runtime)
                        }
                    }
                }
            }

            WorkbenchInfoPanel(
                title: "Needs Input",
                systemImage: "bell.badge",
                detail: sessionAttentionSummary
            )
        }
    }

    private var sessionCenterTint: Color {
        if model.sessionCenterStatusText == "Ready" {
            return .electricSheepSuccess
        }
        if model.sessionCenterStatusText == "Unavailable" {
            return .electricSheepDanger
        }
        return .electricSheepGoldSoft
    }

    private func systemImage(for record: WorkbenchSessionRecord) -> String {
        if let runtime = WorkbenchSessionContract.brokerRuntimeToOpen(for: record) {
            return RuntimeDefinition.definition(for: runtime).systemImage
        }
        switch record.surface {
        case .queue:
            return "bell.badge"
        case .audit:
            return "list.clipboard"
        case .codex:
            return "sparkle.magnifyingglass"
        default:
            return "rectangle.3.group.bubble.left"
        }
    }

    private var sessionAttentionSummary: String {
        if model.sessionRecords.isEmpty {
            return "No broker session state has been loaded yet. Refresh Session Center to read gateway status."
        }
        let attentionCount = model.sessionRecords.filter { $0.attentionState == .needsAttention }.count
        if attentionCount == 1 {
            return "1 session needs review."
        }
        if attentionCount > 1 {
            return "\(attentionCount) sessions need review."
        }
        return "No gateway, queue, audit, or Codex attention states in the read-only evidence."
    }
}

struct ApprovalCenterView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        WorkbenchSurface(title: "Approval Center", subtitle: "Review risky agent actions with the actual destination, payload preview, and risk class before a runtime proceeds.") {
            HStack(spacing: 10) {
                StatusPill(title: model.approvalCenterStatusText, systemImage: "checkmark.shield", tint: approvalTint)
                Spacer()
                Button {
                    Task {
                        await model.refreshApprovalCenterState()
                    }
                } label: {
                    Label(model.isRefreshingApprovalCenter ? "Refreshing" : "Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .disabled(!model.isSignedIn || model.isRefreshingApprovalCenter)
            }

            if model.approvalRequests.isEmpty {
                WorkbenchInfoPanel(
                    title: "No Pending Approvals",
                    systemImage: "checkmark.seal",
                    detail: "The Workbench destination-preview contract is ready. Live broker pending-approval fetch and decision submission remain gated behind issue #144."
                )
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 12)], spacing: 12) {
                    ForEach(model.approvalRequests) { request in
                        ApprovalRequestCard(request: request)
                    }
                }
            }

            WorkbenchInfoPanel(
                title: "Destination Preview",
                systemImage: "eye",
                detail: "Approval rows must show the real recipient, URL, file path, payment target, secret name, budget, or permission scope. Display names and summaries alone are not enough."
            )
        }
    }

    private var approvalTint: Color {
        if model.approvalCenterStatusText == "No pending approvals" {
            return .electricSheepSuccess
        }
        if model.approvalCenterStatusText.contains("pending") {
            return .electricSheepDanger
        }
        return .electricSheepGoldSoft
    }
}

private struct WorkbenchSurface<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder let content: Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(title)
                        .font(.largeTitle.weight(.semibold))
                        .foregroundStyle(Color.electricSheepPrimaryText)
                    Text(subtitle)
                        .font(.title3)
                        .foregroundStyle(Color.electricSheepSecondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }

                content
            }
            .padding(30)
            .frame(maxWidth: 1320, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color.electricSheepCanvas)
        .tint(Color.electricSheepGoldSoft)
    }
}

private struct ApprovalRequestCard: View {
    let request: WorkbenchApprovalRequest

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                RuntimeIconBadge(systemImage: "checkmark.shield", tint: tint)
                VStack(alignment: .leading, spacing: 3) {
                    Text(request.toolName)
                        .font(.headline)
                        .foregroundStyle(Color.electricSheepPrimaryText)
                    Text(request.agentID)
                        .font(.caption)
                        .foregroundStyle(Color.electricSheepMutedText)
                }
                Spacer()
                StatusPill(title: request.riskClass.rawValue, systemImage: riskIcon, tint: tint)
            }

            VStack(alignment: .leading, spacing: 7) {
                Label(request.destinationPreview.kind.rawValue, systemImage: request.isActionable ? "scope" : "exclamationmark.triangle")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint)
                Text(request.destinationPreview.primary)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(Color.electricSheepPrimaryText)
                    .textSelection(.enabled)
                if let secondary = request.destinationPreview.secondary {
                    Text(secondary)
                        .font(.callout)
                        .foregroundStyle(Color.electricSheepSecondaryText)
                        .textSelection(.enabled)
                }
                if let bodyExcerpt = request.destinationPreview.bodyExcerpt {
                    Text(bodyExcerpt)
                        .font(.caption)
                        .foregroundStyle(Color.electricSheepSecondaryText)
                        .lineLimit(4)
                        .textSelection(.enabled)
                }
                if let warning = request.destinationPreview.warning {
                    Text(warning)
                        .font(.caption)
                        .foregroundStyle(Color.electricSheepDanger)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Text(request.nextAction)
                .font(.caption)
                .foregroundStyle(Color.electricSheepSecondaryText)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 8) {
                ForEach(request.availableDecisions, id: \.self) { decision in
                    Button(decision.displayText) {}
                        .buttonStyle(.bordered)
                        .disabled(true)
                        .help("Decision submission is deferred until the broker Approval Center endpoint lands.")
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(request.sourcePointer)
                Text(request.createdAt)
                if let auditId = request.auditId {
                    Text(auditId)
                }
            }
            .font(.caption2.monospaced())
            .foregroundStyle(Color.electricSheepMutedText)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.electricSheepLineWarm, lineWidth: 1)
        )
    }

    private var tint: Color {
        switch request.riskClass {
        case .critical:
            return .electricSheepDanger
        case .warning:
            return .electricSheepGoldSoft
        case .info:
            return .electricSheepCyan
        }
    }

    private var riskIcon: String {
        switch request.riskClass {
        case .critical:
            return "exclamationmark.octagon"
        case .warning:
            return "exclamationmark.triangle"
        case .info:
            return "info.circle"
        }
    }
}

private struct ProviderProfileCard: View {
    let profile: WorkbenchProviderProfileState
    let isSignedIn: Bool
    let isBusy: Bool
    let connect: () -> Void
    let makeActive: () -> Void
    let mintGrant: () -> Void
    let revoke: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                RuntimeIconBadge(systemImage: iconName, tint: tint)
                VStack(alignment: .leading, spacing: 3) {
                    Text(profile.title)
                        .font(.headline)
                        .foregroundStyle(Color.electricSheepPrimaryText)
                    Text(statusText)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint)
                }
                Spacer()
            }

            Text(profile.subtitle)
                .font(.callout)
                .foregroundStyle(Color.electricSheepSecondaryText)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 6) {
                ForEach(profile.capabilities, id: \.self) { capability in
                    Label(capability, systemImage: "checkmark.circle")
                        .font(.caption)
                        .foregroundStyle(Color.electricSheepMutedText)
                }
            }

            if let usageSummary = profile.usageSummary, !usageSummary.isEmpty {
                Text(usageSummary)
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepGoldSoft)
            }

            HStack(spacing: 8) {
                Button(actionButtonTitle) {
                    if profile.status == .connected {
                        makeActive()
                    } else {
                        connect()
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!isSignedIn || isBusy || profile.status == .planned || profile.active)

                Button("OpenClaw Grant") {
                    mintGrant()
                }
                .buttonStyle(.bordered)
                .disabled(!isSignedIn || isBusy || profile.status != .connected)

                Button("Revoke") {
                    revoke()
                }
                .buttonStyle(.bordered)
                .disabled(!isSignedIn || isBusy || profile.status != .connected)
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.electricSheepLineWarm, lineWidth: 1)
        )
    }

    private var statusText: String {
        if profile.active {
            return profile.hasConnectionProof ? "Active" : "Needs verification"
        }
        if !isSignedIn, profile.status != .planned {
            return "Sign in first"
        }
        if profile.status == .connected && !profile.hasConnectionProof {
            return "Needs verification"
        }
        return profile.status.displayText
    }

    private var actionButtonTitle: String {
        if profile.active {
            return "Active"
        }
        if profile.status == .connected {
            return profile.hasConnectionProof ? "Make Active" : "Verify"
        }
        return "Connect"
    }

    private var iconName: String {
        switch profile.key {
        case .openAICodex:
            return "sparkle.magnifyingglass"
        case .openClaw:
            return "bubble.left.and.bubble.right"
        case .hermes:
            return "sparkles"
        case .googleWorkspace:
            return "envelope.fill"
        case .slack:
            return "message.fill"
        case .notion:
            return "doc.text.fill"
        case .linear:
            return "line.3.horizontal.decrease.circle.fill"
        case .github:
            return "chevron.left.forwardslash.chevron.right"
        }
    }

    private var tint: Color {
        if profile.active {
            return .electricSheepSuccess
        }
        switch profile.status {
        case .connected:
            return .electricSheepSuccess
        case .needsLogin:
            return .electricSheepCyan
        case .planned:
            return .electricSheepGoldSoft
        case .revoked:
            return .electricSheepMutedText
        case .error:
            return .electricSheepDanger
        }
    }
}

private struct MetricTile: View {
    let title: String
    let value: String
    let systemImage: String

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Label(title.uppercased(), systemImage: systemImage)
                    .font(.system(.caption2, design: .monospaced).weight(.semibold))
                    .tracking(1.5)
                    .foregroundStyle(Color.electricSheepMutedText)
                Spacer()
            }
            Text(value)
                .font(.headline)
                .foregroundStyle(Color.electricSheepPrimaryText)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.electricSheepLine, lineWidth: 1)
        )
    }
}

private struct SessionRecordCard: View {
    let record: WorkbenchSessionRecord
    let systemImage: String
    let action: () -> Void

    var body: some View {
        if WorkbenchSessionContract.brokerRuntimeToOpen(for: record) == nil {
            content
                .help("Read-only evidence record; no runtime jump is available.")
        } else {
            Button(action: action) {
                content
            }
            .buttonStyle(.plain)
            .help("Open this gateway.")
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                RuntimeIconBadge(systemImage: systemImage, tint: tint)
                Spacer()
                StatusPill(title: record.status, systemImage: statusIcon, tint: tint)
            }
            Text(record.title)
                .font(.headline)
                .foregroundStyle(Color.electricSheepPrimaryText)
            Text(record.nextAction)
                .font(.callout)
                .foregroundStyle(Color.electricSheepSecondaryText)
                .lineLimit(2)
            VStack(alignment: .leading, spacing: 4) {
                Text(record.resumeRoute.kind.rawValue)
                Text(record.sourcePointer)
                if let auditId = record.auditId {
                    Text(auditId)
                }
                if let lastUpdate = record.updatedAt {
                    Text(lastUpdate)
                }
            }
            .font(.caption2.monospaced())
            .foregroundStyle(Color.electricSheepMutedText)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.electricSheepLineWarm, lineWidth: 1)
        )
    }

    private var tint: Color {
        switch record.attentionState {
        case .active:
            return .electricSheepSuccess
        case .done:
            return .electricSheepCyan
        case .idle:
            return .electricSheepMutedText
        case .needsAttention:
            return .electricSheepDanger
        case .unknown:
            return .electricSheepGoldSoft
        }
    }

    private var statusIcon: String {
        switch record.attentionState {
        case .active:
            return "checkmark.circle"
        case .done:
            return "checkmark.seal"
        case .idle:
            return "pause.circle"
        case .needsAttention:
            return "exclamationmark.triangle"
        case .unknown:
            return "questionmark.circle"
        }
    }
}

private struct WorkbenchInfoPanel: View {
    let title: String
    let systemImage: String
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: systemImage)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(Color.electricSheepGoldSoft)
                .frame(width: 34, height: 34)
                .background(Color.electricSheepGoldSoft.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))

            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(Color.electricSheepPrimaryText)
                Text(detail)
                    .font(.callout)
                    .foregroundStyle(Color.electricSheepSecondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.electricSheepSurfaceRaised, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.electricSheepLineWarm, lineWidth: 1)
        )
    }
}
