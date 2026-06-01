import EvaDesktopCore
import SwiftUI

struct ProvidersHubView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        WorkbenchSurface(title: "Connected Apps", subtitle: "Connect the business apps Eva can use for email, files, projects, code, and research.") {
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
                ForEach(customerFacingProfiles) { profile in
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

            if !plannedBusinessProfiles.isEmpty {
                MoreConnectedAppsPanel(profiles: plannedBusinessProfiles)
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

            UsageDashboardView(model: model)
                .disabled(!model.isSignedIn || model.isRefreshingUsageDashboard)

            WorkbenchInfoPanel(
                title: "Credentials Stay Private",
                systemImage: "key.slash",
                detail: "Workbench shows connection status only. Sign-in happens in the business browser, and raw app tokens stay out of the Mac app."
            )

            if !technicalProfiles.isEmpty {
                DisclosureGroup {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 300), spacing: 14)], alignment: .leading, spacing: 14) {
                        ForEach(technicalProfiles) { profile in
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
                    .padding(.top, 8)
                } label: {
                    Label("Technical AI connections", systemImage: "wrench.and.screwdriver")
                        .font(.headline)
                }
            }
        }
    }

    private var customerFacingProfiles: [WorkbenchProviderProfileState] {
        model.providerProfiles.filter { profile in
            profile.key != .openAICodex && profile.status != .planned
        }
    }

    private var plannedBusinessProfiles: [WorkbenchProviderProfileState] {
        model.providerProfiles.filter { profile in
            profile.key != .openAICodex && profile.status == .planned
        }
    }

    private var technicalProfiles: [WorkbenchProviderProfileState] {
        model.providerProfiles.filter { $0.key == .openAICodex }
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
                    Text("What Eva Can Access")
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
                Text("Permission summary expires \(summary.expiresAt.formatted(date: .abbreviated, time: .shortened)).")
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepMutedText)
                grantLine("Can use", tools: summary.tools(for: .allowed))
                grantLine("Asks first", tools: summary.tools(for: .requiresApproval))
                grantLine("Off", tools: summary.tools(for: .denied))
            } else {
                Text("Eva's app permissions appear here after a connection is checked. Workbench shows safe summaries only; raw credentials stay hidden.")
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

private struct MoreConnectedAppsPanel: View {
    let profiles: [WorkbenchProviderProfileState]

    var body: some View {
        WorkbenchInfoPanel(
            title: "More Apps Coming Soon",
            systemImage: "plus.app",
            detail: "Next up: \(profiles.map(\.title).joined(separator: ", ")). These stay out of the main setup path until their sign-in flow is ready."
        )
    }
}

struct UsageDashboardView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                RuntimeIconBadge(systemImage: "gauge.with.dots.needle.bottom.50percent", tint: tint)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Usage & Budget")
                        .font(.headline)
                        .foregroundStyle(Color.electricSheepPrimaryText)
                    Text(model.usageDashboardStatusText)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint)
                }
                Spacer()
                Button {
                    Task {
                        await model.refreshUsageDashboard()
                    }
                } label: {
                    Label(model.isRefreshingUsageDashboard ? "Refreshing" : "Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
            }

            if model.usageDashboardCards.isEmpty {
                Text("Usage appears after Eva reports work. Budget caps come from your approved workspace policy.")
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepMutedText)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                ForEach(model.usageDashboardCards) { card in
                    UsageAgentCard(card: card)
                }
            }
        }
        .padding(14)
        .background(Color.electricSheepSurfaceRaised, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.electricSheepLineWarm, lineWidth: 1)
        )
        .onAppear {
            model.setUsageDashboardVisible(true)
        }
        .onDisappear {
            model.setUsageDashboardVisible(false)
        }
    }

    private var tint: Color {
        let lowercased = model.usageDashboardStatusText.lowercased()
        if lowercased.contains("attention") || lowercased.contains("unavailable") || lowercased.contains("expired") {
            return .electricSheepDanger
        }
        if lowercased.contains("ready") {
            return .electricSheepSuccess
        }
        return .electricSheepGoldSoft
    }
}

private struct UsageAgentCard: View {
    let card: WorkbenchAgentUsageCard

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(card.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Color.electricSheepPrimaryText)
                    .lineLimit(1)
                Spacer()
                Text(card.status)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(statusTint)
            }

            HStack(spacing: 12) {
                usageMetric("Calls", value: String(card.callCount))
                usageMetric("Tokens", value: tokenText)
                usageMetric("Cost", value: costText)
            }

            if let dollarProgress = card.dollarProgress {
                ProgressView(value: dollarProgress)
                    .tint(progressTint(dollarProgress))
            }
            if let tokenProgress = card.tokenProgress {
                ProgressView(value: tokenProgress)
                    .tint(progressTint(tokenProgress))
            }

            Text(card.nextAction)
                .font(.caption)
                .foregroundStyle(Color.electricSheepMutedText)
                .fixedSize(horizontal: false, vertical: true)

            if card.primaryActionTitle != nil || card.secondaryActionTitle != nil {
                HStack(spacing: 8) {
                    if let primary = card.primaryActionTitle {
                        Button(primary) {}
                            .buttonStyle(.borderedProminent)
                            .disabled(true)
                    }
                    if let secondary = card.secondaryActionTitle {
                        Button(secondary) {}
                            .buttonStyle(.bordered)
                            .disabled(true)
                    }
                }
                .help("Budget actions need a signed Needs Your Okay request.")
            }
        }
        .padding(.vertical, 4)
    }

    private var statusTint: Color {
        switch card.attentionState {
        case .needsAttention:
            return .electricSheepDanger
        case .active, .done:
            return .electricSheepSuccess
        case .idle, .unknown:
            return .electricSheepGoldSoft
        }
    }

    private var tokenText: String {
        if let tokenCap = card.tokenCap {
            return "\(card.tokenTotal)/\(tokenCap)"
        }
        return "\(card.tokenTotal)"
    }

    private var costText: String {
        if let dollarCap = card.dollarCap {
            return "$\(formatDollars(card.costUSD))/$\(formatDollars(dollarCap))"
        }
        return "$\(formatDollars(card.costUSD))"
    }

    private func usageMetric(_ label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(Color.electricSheepMutedText)
            Text(value)
                .font(.caption)
                .foregroundStyle(Color.electricSheepSecondaryText)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func progressTint(_ progress: Double) -> Color {
        progress >= 1 ? .electricSheepDanger : .electricSheepSuccess
    }

    private func formatDollars(_ value: Double) -> String {
        if value.rounded() == value {
            return String(Int(value))
        }
        return String(format: "%.2f", value)
    }
}

struct SessionCenterView: View {
    @ObservedObject var model: WorkbenchModel
    let openConnectedApps: () -> Void
    let openApprovals: () -> Void
    let openCompanyBrain: () -> Void
    let jumpToRuntime: (RuntimeKey) -> Void

    var body: some View {
        WorkbenchSurface(title: "Home", subtitle: "Your AI office in one place: connect apps, review approvals, open workspaces, and resume recent work.") {
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

            AgentQuickActionGrid(
                canOpenConnectedApps: model.canOpenSurface("connected_apps"),
                canOpenApprovals: model.canOpenSurface("approvals"),
                canOpenBusinessBrowser: model.canOpenSurface("business_browser"),
                canOpenCreativeStudio: model.canOpenSurface("creative_studio"),
                openConnectedApps: openConnectedApps,
                openApprovals: openApprovals,
                openBusinessBrowser: {
                    jumpToRuntime(.liveBrowser)
                },
                openCreativeStudio: {
                    jumpToRuntime(.creativeStudio)
                }
            )

            AionReferenceSpikeSection(
                assignments: model.agentAssignments,
                providerProfiles: model.providerProfiles,
                capabilitySummary: model.capabilityManifestSummary,
                todayItems: model.todayItems,
                pendingApprovalCount: model.approvalRequests.count
            )

            AgentWorkspaceSummaryGrid(
                attentionCount: recordsNeedingAttention.count,
                activeCount: activeRecordCount,
                gatewayCount: gatewayRecords.count,
                recentCount: model.recentSessionRecords.count,
                lastEvidenceText: latestEvidenceText
            )

            if model.todayItems.isEmpty {
                WorkbenchInfoPanel(
                    title: "Everything Looks Clear",
                    systemImage: "checkmark.seal",
                    detail: sessionAttentionSummary
                )
            } else {
                TodayItemSection(items: model.todayItems) { item in
                    openTodayItem(item)
                }
            }

            if !evidenceRecords.isEmpty {
                DisclosureGroup {
                    recordSection(
                        title: "Technical activity",
                        subtitle: "Read-only queue and audit signals for support review.",
                        records: evidenceRecords
                    )
                    .padding(.top, 8)
                } label: {
                    Label("Technical activity", systemImage: "list.clipboard")
                        .font(.headline)
                }
            }
        }
    }

    private func openTodayItem(_ item: WorkbenchTodayItem) {
        switch item.kind {
        case .connectedAppNeeded:
            openConnectedApps()
        case .approvalNeeded:
            openApprovals()
        case .browserLoginNeeded:
            jumpToRuntime(.liveBrowser)
        case .recentWork:
            if let runtime = item.resumeRoute.runtime, RuntimeDefinition.isBrokeredRuntime(runtime) {
                jumpToRuntime(runtime)
            } else if item.resumeRoute.kind == .evidenceOnly {
                openConnectedApps()
            }
        case .agentRunning, .agentDone, .agentBlocked:
            if let runtime = item.resumeRoute.runtime, RuntimeDefinition.isBrokeredRuntime(runtime) {
                jumpToRuntime(runtime)
            }
        case .companyBrainSourceNeeded:
            openCompanyBrain()
        case .systemAttention:
            break
        }
    }

    @ViewBuilder
    private func recordSection(title: String, subtitle: String, records: [WorkbenchSessionRecord]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SessionWorkspaceSectionHeader(
                title: title,
                subtitle: subtitle,
                status: "\(records.count)",
                systemImage: "rectangle.stack",
                tint: title == "Needs attention" ? Color.electricSheepDanger : Color.electricSheepGoldSoft
            )
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                ForEach(records) { record in
                    SessionRecordCard(record: record, systemImage: systemImage(for: record)) {
                        if let runtime = WorkbenchSessionContract.brokerRuntimeToOpen(for: record) {
                            jumpToRuntime(runtime)
                        }
                    }
                }
            }
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
        case .assignedAgent:
            return "person.crop.circle.badge.checkmark"
        default:
            return "rectangle.3.group.bubble.left"
        }
    }

    private var recordsNeedingAttention: [WorkbenchSessionRecord] {
        model.sessionRecords.filter { $0.attentionState == .needsAttention }
    }

    private var gatewayRecords: [WorkbenchSessionRecord] {
        model.sessionRecords.filter { $0.surface == .broker && $0.attentionState != .needsAttention }
    }

    private var assignedAgentRecords: [WorkbenchSessionRecord] {
        model.sessionRecords.filter { $0.surface == .assignedAgent && $0.attentionState != .needsAttention }
    }

    private var evidenceRecords: [WorkbenchSessionRecord] {
        model.sessionRecords.filter { ![.broker, .assignedAgent, .connectedApps].contains($0.surface) && $0.attentionState != .needsAttention }
    }

    private var activeRecordCount: Int {
        model.sessionRecords.filter { $0.attentionState == .active }.count
    }

    private var latestEvidenceText: String {
        let candidates = (model.sessionRecords + model.recentSessionRecords)
            .compactMap(\.updatedAt)
            .sorted()
        guard let latest = candidates.last else {
            return "Not checked"
        }
        return String(latest.prefix(16)).replacingOccurrences(of: "T", with: " ")
    }

    private var sessionAttentionSummary: String {
        if model.sessionRecords.isEmpty {
            if !model.recentSessionRecords.isEmpty {
                return "Recent workspaces are saved below. Refresh Home to check current status."
            }
            return "Connect apps, open the business browser, or start from a workspace below."
        }
        let attentionCount = model.sessionRecords.filter { $0.attentionState == .needsAttention }.count
        if attentionCount == 1 {
            return "1 session needs review."
        }
        if attentionCount > 1 {
            return "\(attentionCount) sessions need review."
        }
        return "No app, approval, or work item is asking for help right now."
    }
}

private struct TodayItemSection: View {
    let items: [WorkbenchTodayItem]
    let openItem: (WorkbenchTodayItem) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            SessionWorkspaceSectionHeader(
                title: "Today",
                subtitle: "The next useful things Eva needs or has ready for you.",
                status: "\(items.count)",
                systemImage: "checklist",
                tint: Color.electricSheepSuccess
            )
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 12)], spacing: 12) {
                ForEach(items) { item in
                    TodayItemCard(item: item) {
                        openItem(item)
                    }
                }
            }
        }
    }
}

private struct TodayItemCard: View {
    let item: WorkbenchTodayItem
    let action: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: systemImage)
                    .font(.title3)
                    .foregroundStyle(tint)
                    .frame(width: 32, height: 32)
                    .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: 8))
                VStack(alignment: .leading, spacing: 6) {
                    Text(item.title)
                        .font(.headline)
                    Text(item.nextAction)
                        .font(.callout)
                        .foregroundStyle(Color.electricSheepSecondaryText)
                        .lineLimit(3)
                }
                Spacer()
                StatusPill(title: statusLabel, systemImage: statusImage, tint: tint)
            }
            HStack {
                Button(action: action) {
                    Label(actionTitle, systemImage: "arrow.right.circle")
                }
                .buttonStyle(.bordered)
                .disabled(!hasAction)
                Spacer()
            }
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(item.technicalDetails, id: \.self) { detail in
                        Text(detail)
                            .font(.caption.monospaced())
                            .foregroundStyle(Color.electricSheepMutedText)
                            .lineLimit(2)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 4)
            } label: {
                Text("Technical details")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.electricSheepMutedText)
            }
        }
        .padding(16)
        .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(tint.opacity(0.35), lineWidth: 1)
        )
    }

    private var hasAction: Bool {
        switch item.kind {
        case .systemAttention:
            return false
        case .recentWork:
            if let runtime = item.resumeRoute.runtime {
                return RuntimeDefinition.isBrokeredRuntime(runtime)
            }
            return item.resumeRoute.kind == .evidenceOnly
        default:
            return true
        }
    }

    private var actionTitle: String {
        switch item.kind {
        case .connectedAppNeeded:
            return "Open Apps"
        case .approvalNeeded:
            return "Review"
        case .browserLoginNeeded:
            return "Open Browser"
        case .recentWork:
            if item.resumeRoute.kind == .evidenceOnly {
                return "Open Apps"
            }
            return "Resume"
        case .agentRunning, .agentDone, .agentBlocked:
            return "Open Agent"
        case .companyBrainSourceNeeded:
            return "Open Company Brain"
        case .systemAttention:
            return "View Details"
        }
    }

    private var systemImage: String {
        switch item.kind {
        case .connectedAppNeeded:
            return "person.badge.key"
        case .approvalNeeded:
            return "checkmark.shield"
        case .browserLoginNeeded:
            return "globe"
        case .agentRunning:
            return "person.crop.circle.badge.checkmark"
        case .agentDone:
            return "checkmark.seal"
        case .agentBlocked:
            return "exclamationmark.triangle"
        case .companyBrainSourceNeeded:
            return "brain"
        case .recentWork:
            return "clock.arrow.circlepath"
        case .systemAttention:
            return "bell.badge"
        }
    }

    private var statusLabel: String {
        switch item.status {
        case .needsInput:
            return "Needs input"
        case .active:
            return "Active"
        case .done:
            return "Done"
        case .blocked:
            return "Blocked"
        case .idle:
            return "Saved"
        case .unavailable:
            return "Unavailable"
        }
    }

    private var statusImage: String {
        switch item.status {
        case .needsInput, .blocked, .unavailable:
            return "exclamationmark.triangle"
        case .active:
            return "waveform"
        case .done:
            return "checkmark.seal"
        case .idle:
            return "clock"
        }
    }

    private var tint: Color {
        switch item.status {
        case .needsInput, .blocked:
            return .electricSheepDanger
        case .active, .done:
            return .electricSheepSuccess
        case .idle:
            return .electricSheepMutedText
        case .unavailable:
            return .electricSheepGoldSoft
        }
    }
}

private struct AgentQuickActionGrid: View {
    let canOpenConnectedApps: Bool
    let canOpenApprovals: Bool
    let canOpenBusinessBrowser: Bool
    let canOpenCreativeStudio: Bool
    let openConnectedApps: () -> Void
    let openApprovals: () -> Void
    let openBusinessBrowser: () -> Void
    let openCreativeStudio: () -> Void

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 12)], spacing: 12) {
            if canOpenConnectedApps {
                AgentQuickActionCard(
                    title: "Connect work apps",
                    detail: "Set up Gmail, Calendar, Drive, and other business tools Eva can use.",
                    systemImage: "person.badge.key",
                    actionTitle: "Open Apps",
                    action: openConnectedApps
                )
            }
            if canOpenApprovals {
                AgentQuickActionCard(
                    title: "Review approvals",
                    detail: "See decisions waiting for you before Eva sends, spends, writes, or controls anything sensitive.",
                    systemImage: "checkmark.shield",
                    actionTitle: "Open Approvals",
                    action: openApprovals
                )
            }
            if canOpenBusinessBrowser {
                AgentQuickActionCard(
                    title: "Open business browser",
                    detail: "Use the shared browser for sign-ins, CAPTCHA, and web tasks Eva can help with.",
                    systemImage: "globe",
                    actionTitle: "Open Browser",
                    action: openBusinessBrowser
                )
            }
            if canOpenCreativeStudio {
                AgentQuickActionCard(
                    title: "Create visuals",
                    detail: "Launch hosted Comfy Cloud for images and video workflows without installing ComfyUI locally.",
                    systemImage: "paintbrush.pointed",
                    actionTitle: "Creative Studio",
                    action: openCreativeStudio
                )
            }
        }
    }
}

private struct AgentQuickActionCard: View {
    let title: String
    let detail: String
    let systemImage: String
    let actionTitle: String
    let action: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            RuntimeIconBadge(systemImage: systemImage, tint: Color.electricSheepCyan)
            Text(title)
                .font(.headline)
                .foregroundStyle(Color.electricSheepPrimaryText)
            Text(detail)
                .font(.callout)
                .foregroundStyle(Color.electricSheepSecondaryText)
                .lineLimit(3)
            Button(actionTitle) {
                action()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(18)
        .frame(maxWidth: .infinity, minHeight: 190, alignment: .topLeading)
        .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.electricSheepLineWarm, lineWidth: 1)
        )
    }
}

private struct AionReferenceSpikeSection: View {
    let assignments: [WorkbenchAgentAssignment]
    let providerProfiles: [WorkbenchProviderProfileState]
    let capabilitySummary: WorkbenchCapabilityManifestSummary?
    let todayItems: [WorkbenchTodayItem]
    let pendingApprovalCount: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SessionWorkspaceSectionHeader(
                title: "Agent Workspace Preview",
                subtitle: "Native evaOS patterns for agents, teams, tasks, app readiness, and approvals.",
                status: "Preview",
                systemImage: "sparkles.rectangle.stack",
                tint: Color.electricSheepCyan
            )

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 12)], spacing: 12) {
                AgentTeamPreviewCard(assignment: primaryAssignment)
                TaskLauncherPreviewCard()
                AssistantCatalogPreviewCard(assignedAgentName: primaryAgentName)
                AppToolReadinessPreviewCard(providerProfiles: businessProfiles, capabilitySummary: capabilitySummary)
                PermissionBadgesPreviewCard(pendingApprovalCount: pendingApprovalCount, todayItems: todayItems)
            }
        }
    }

    private var primaryAssignment: WorkbenchAgentAssignment? {
        assignments.first
    }

    private var primaryAgentName: String {
        primaryAssignment?.agentDisplayName ?? "Sales Follow-up"
    }

    private var businessProfiles: [WorkbenchProviderProfileState] {
        providerProfiles
            .filter { $0.key != .openAICodex && $0.status != .planned }
            .prefix(3)
            .map { $0 }
    }
}

private struct AgentTeamPreviewCard: View {
    let assignment: WorkbenchAgentAssignment?

    var body: some View {
        PreviewPatternCard(title: "Agent Team", systemImage: "person.3.sequence", status: statusText, tint: tint) {
            VStack(alignment: .leading, spacing: 8) {
                Text(agentName)
                    .font(.headline)
                    .foregroundStyle(Color.electricSheepPrimaryText)
                    .lineLimit(1)
                previewLine("Role", value: "Assigned agent")
                previewLine("Apps", value: allowedAppsText)
                previewLine("Budget", value: budgetText)
                previewLine("Approvals", value: assignment?.approvalPolicy.defaultMode == "ask" ? "Asks before sensitive actions" : "Policy required")
            }
        }
    }

    private var agentName: String {
        assignment?.agentDisplayName ?? "Sales Follow-up"
    }

    private var statusText: String {
        assignment?.statusText ?? "Preview"
    }

    private var tint: Color {
        switch assignment?.attentionState {
        case .active, .done:
            return .electricSheepSuccess
        case .needsAttention:
            return .electricSheepDanger
        case .idle, .unknown, nil:
            return .electricSheepGoldSoft
        }
    }

    private var allowedAppsText: String {
        let grants = assignment?.allowedProviderGrants.prefix(3).map(readableGrant) ?? ["Google Workspace"]
        return grants.isEmpty ? "Assigned apps only" : grants.joined(separator: ", ")
    }

    private var budgetText: String {
        guard let budget = assignment?.budget else {
            return "$5/day cap"
        }
        if let dailyUSD = budget.dailyUSD {
            return "$\(formatPreviewDollars(dailyUSD))/day"
        }
        if let dailyTokens = budget.dailyTokens {
            return "\(dailyTokens) tokens/day"
        }
        return "Policy controlled"
    }
}

private struct TaskLauncherPreviewCard: View {
    private let tasks = [
        ("Email follow-up", "Needs Gmail", "Ask first"),
        ("Sales research", "Uses browser", "Ready"),
        ("Admin inbox", "Needs approval", "Review"),
        ("Creative brief", "Uses Creative Studio", "Ready")
    ]

    var body: some View {
        PreviewPatternCard(title: "Task Launcher", systemImage: "bolt.square", status: "4 templates", tint: Color.electricSheepGoldSoft) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(tasks, id: \.0) { task in
                    HStack(spacing: 8) {
                        Image(systemName: "arrow.right.circle")
                            .foregroundStyle(Color.electricSheepCyan)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(task.0)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Color.electricSheepPrimaryText)
                            Text("\(task.1) · \(task.2)")
                                .font(.caption2)
                                .foregroundStyle(Color.electricSheepMutedText)
                                .lineLimit(1)
                        }
                    }
                }
            }
        }
    }
}

private struct AssistantCatalogPreviewCard: View {
    let assignedAgentName: String

    private var rows: [(String, String, String)] {
        [
            (assignedAgentName, "Assigned", "Limited to this user"),
            ("Email Ops", "evaOS", "Built-in business template"),
            ("Pitch Deck Creator", "Extension", "Creative workflow"),
            ("Research Assistant", "Customer", "Admin-created")
        ]
    }

    var body: some View {
        PreviewPatternCard(title: "Assistant Catalog", systemImage: "rectangle.stack.badge.person.crop", status: "Source labels", tint: Color.electricSheepCyan) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(rows, id: \.0) { row in
                    HStack(spacing: 8) {
                        Text(row.0)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Color.electricSheepPrimaryText)
                            .lineLimit(1)
                        Spacer(minLength: 8)
                        Text(row.1)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(sourceTint(row.1))
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(sourceTint(row.1).opacity(0.14), in: Capsule())
                    }
                    Text(row.2)
                        .font(.caption2)
                        .foregroundStyle(Color.electricSheepMutedText)
                        .lineLimit(1)
                }
            }
        }
    }
}

private struct AppToolReadinessPreviewCard: View {
    let providerProfiles: [WorkbenchProviderProfileState]
    let capabilitySummary: WorkbenchCapabilityManifestSummary?

    var body: some View {
        PreviewPatternCard(title: "App & Tool Readiness", systemImage: "slider.horizontal.3", status: readinessStatus, tint: readinessTint) {
            VStack(alignment: .leading, spacing: 8) {
                if providerProfiles.isEmpty {
                    previewLine("Apps", value: "Connect Google Workspace first")
                } else {
                    ForEach(providerProfiles) { profile in
                        readinessRow(profile.title, status: profile.status.displayText, tint: providerStatusTint(profile.status))
                    }
                }
                previewLine("Safe tools", value: toolsText)
            }
        }
    }

    private var readinessStatus: String {
        providerProfiles.contains { $0.status == .needsLogin || $0.status == .error || $0.status == .expired } ? "Needs check" : "Readable"
    }

    private var readinessTint: Color {
        readinessStatus == "Readable" ? .electricSheepSuccess : .electricSheepGoldSoft
    }

    private var toolsText: String {
        guard let capabilitySummary else {
            return "Safe summaries only"
        }
        let allowed = capabilitySummary.tools(for: .allowed).prefix(2)
        if allowed.isEmpty {
            return "No allowed tools yet"
        }
        return allowed.joined(separator: ", ")
    }
}

private struct PermissionBadgesPreviewCard: View {
    let pendingApprovalCount: Int
    let todayItems: [WorkbenchTodayItem]

    var body: some View {
        PreviewPatternCard(title: "Permission Badges", systemImage: "checkmark.shield", status: "\(pendingCount) pending", tint: pendingCount > 0 ? .electricSheepDanger : .electricSheepSuccess) {
            VStack(alignment: .leading, spacing: 8) {
                readinessRow("Needs Your Okay", status: pendingCount > 0 ? "\(pendingCount) waiting" : "Clear", tint: pendingCount > 0 ? .electricSheepDanger : .electricSheepSuccess)
                readinessRow("Browser sign-in", status: browserNeedsLogin ? "Needs login" : "Clear", tint: browserNeedsLogin ? .electricSheepGoldSoft : .electricSheepSuccess)
                readinessRow("App access", status: appNeedsConnection ? "Needs app" : "Ready", tint: appNeedsConnection ? .electricSheepGoldSoft : .electricSheepSuccess)
                Text("Badges point back to broker approvals and Today items; they are not local permission memory.")
                    .font(.caption2)
                    .foregroundStyle(Color.electricSheepMutedText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var pendingCount: Int {
        max(pendingApprovalCount, todayItems.filter { $0.kind == .approvalNeeded }.count)
    }

    private var browserNeedsLogin: Bool {
        todayItems.contains { $0.kind == .browserLoginNeeded }
    }

    private var appNeedsConnection: Bool {
        todayItems.contains { $0.kind == .connectedAppNeeded }
    }
}

private struct PreviewPatternCard<Content: View>: View {
    let title: String
    let systemImage: String
    let status: String
    let tint: Color
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                RuntimeIconBadge(systemImage: systemImage, tint: tint)
                Text(title)
                    .font(.headline)
                    .foregroundStyle(Color.electricSheepPrimaryText)
                    .lineLimit(1)
                Spacer(minLength: 8)
                StatusPill(title: status, systemImage: "sparkles", tint: tint)
            }
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 220, alignment: .topLeading)
        .background(Color.electricSheepSurfaceRaised, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(tint.opacity(0.32), lineWidth: 1)
        )
    }
}

private func previewLine(_ label: String, value: String) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: 8) {
        Text(label)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(Color.electricSheepMutedText)
            .frame(width: 68, alignment: .leading)
        Text(value)
            .font(.caption)
            .foregroundStyle(Color.electricSheepSecondaryText)
            .lineLimit(1)
        Spacer(minLength: 0)
    }
}

private func readinessRow(_ title: String, status: String, tint: Color) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: 8) {
        Circle()
            .fill(tint)
            .frame(width: 7, height: 7)
        Text(title)
            .font(.caption.weight(.semibold))
            .foregroundStyle(Color.electricSheepPrimaryText)
            .lineLimit(1)
        Spacer(minLength: 8)
        Text(status)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(tint)
            .lineLimit(1)
    }
}

private func sourceTint(_ source: String) -> Color {
    switch source.lowercased() {
    case "assigned":
        return .electricSheepSuccess
    case "evaos":
        return .electricSheepCyan
    case "extension":
        return .electricSheepGoldSoft
    default:
        return .electricSheepSecondaryText
    }
}

private func readableGrant(_ grant: String) -> String {
    grant
        .replacingOccurrences(of: "_", with: " ")
        .replacingOccurrences(of: "-", with: " ")
        .split(separator: " ")
        .map { word in
            word.prefix(1).uppercased() + word.dropFirst().lowercased()
        }
        .joined(separator: " ")
}

private func providerStatusTint(_ status: WorkbenchProviderStatus) -> Color {
    switch status {
    case .connected:
        return .electricSheepSuccess
    case .needsLogin:
        return .electricSheepCyan
    case .planned:
        return .electricSheepGoldSoft
    case .revoked:
        return .electricSheepMutedText
    case .expired, .error:
        return .electricSheepDanger
    }
}

private func formatPreviewDollars(_ value: Double) -> String {
    if value.rounded() == value {
        return String(Int(value))
    }
    return String(format: "%.2f", value)
}

private struct AgentWorkspaceSummaryGrid: View {
    let attentionCount: Int
    let activeCount: Int
    let gatewayCount: Int
    let recentCount: Int
    let lastEvidenceText: String

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
            MetricTile(title: "Needs attention", value: "\(attentionCount)", systemImage: "bell.badge")
            MetricTile(title: "Ready now", value: "\(activeCount)", systemImage: "bolt.circle")
            MetricTile(title: "Workspaces", value: "\(gatewayCount)", systemImage: "point.3.connected.trianglepath.dotted")
            MetricTile(title: "Recent", value: "\(recentCount)", systemImage: "clock.arrow.circlepath")
            MetricTile(title: "Last update", value: lastEvidenceText, systemImage: "calendar.badge.clock")
        }
    }
}

private struct SessionWorkspaceSectionHeader: View {
    let title: String
    let subtitle: String
    let status: String
    let systemImage: String
    let tint: Color

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(Color.electricSheepPrimaryText)
                Text(subtitle)
                    .font(.callout)
                    .foregroundStyle(Color.electricSheepSecondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
            StatusPill(title: status, systemImage: systemImage, tint: tint)
        }
    }
}

struct ApprovalCenterView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        WorkbenchSurface(title: "Needs Your Okay", subtitle: "Approve or deny agent actions that need a human decision before they continue.") {
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
                    title: "No Requests Waiting",
                    systemImage: "checkmark.seal",
                    detail: "When Eva needs permission to send, spend, write, use a sensitive tool, or control something on your behalf, the request appears here with the real destination and a safe preview."
                )
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 12)], spacing: 12) {
                    ForEach(model.approvalRequests) { request in
                        ApprovalRequestCard(
                            request: request,
                            isSubmitting: model.approvalDecisionInFlight == request.id,
                            isDisabled: model.approvalDecisionInFlight != nil
                        ) { decision in
                            Task {
                                await model.decideApprovalRequest(request, decision: decision)
                            }
                        }
                    }
                }
            }

            WorkbenchInfoPanel(
                title: "How Approvals Work",
                systemImage: "eye",
                detail: "Allow only when the destination, payload preview, and risk class match what you expect. Denying keeps the work paused instead of guessing."
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
    let isSubmitting: Bool
    let isDisabled: Bool
    let decide: (WorkbenchApprovalDecision) -> Void

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

            if let expirationText = request.expirationText() {
                Label(expirationText, systemImage: request.isExpired() ? "clock.badge.exclamationmark" : "clock")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(request.isExpiringSoon() || request.isExpired() ? Color.electricSheepDanger : Color.electricSheepMutedText)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text(request.nextAction)
                .font(.caption)
                .foregroundStyle(Color.electricSheepSecondaryText)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 8) {
                ForEach(request.availableDecisions, id: \.self) { decision in
                    Button(role: decision == .deny ? .destructive : nil) {
                        decide(decision)
                    } label: {
                        Text(isSubmitting ? "Submitting" : request.actionTitle(for: decision))
                    }
                        .buttonStyle(.bordered)
                        .disabled(isDisabled || (decision != .deny && (!request.isActionable || request.isExpired())))
                        .help(decisionHelp(for: decision))
                }
                if request.availableDecisions.contains(.allowAlways) && !request.canAllowAlways {
                    Text("Allow always requires a durable destination constraint")
                        .font(.caption2)
                        .foregroundStyle(Color.electricSheepMutedText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Label("Requested \(shortTimestamp(request.createdAt))", systemImage: "clock")
                Label("Evidence saved in audit trail", systemImage: "lock.shield")
            }
            .font(.caption2)
            .foregroundStyle(Color.electricSheepMutedText)
            .help(approvalEvidenceHelp)
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

    private func decisionHelp(for decision: WorkbenchApprovalDecision) -> String {
        if decision != .deny && !request.isActionable {
            return "Allow is disabled because this approval is missing actual destination evidence."
        }
        if decision != .deny && request.isExpired() {
            return "Allow is disabled because this approval has expired. Refresh Needs Your Okay before deciding."
        }
        switch decision {
        case .allowOnce:
            if request.isBudgetApproval {
                return "Approve the budget cap increase request for this paused agent."
            }
            return "Allow only this pending tool call."
        case .allowAlways:
            return "Allow this agent to use this tool again only for the same broker-constrained destination."
        case .deny:
            if request.isBudgetApproval {
                return "Keep the budget pause in place and stop this agent from continuing."
            }
            return "Deny this pending tool call."
        }
    }

    private var approvalEvidenceHelp: String {
        let audit = request.auditId.map { " Audit: \($0)." } ?? ""
        let proof = request.destinationProof.map { " Destination proof: \($0.fingerprint)." } ?? " Destination proof missing."
        return "Source: \(request.sourcePointer).\(audit)\(proof)"
    }

    private func shortTimestamp(_ value: String) -> String {
        String(value.prefix(16)).replacingOccurrences(of: "T", with: " ")
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

            if let accountLabel = profile.accountLabel, !accountLabel.isEmpty {
                Label("Connected account: \(accountLabel)", systemImage: "person.crop.circle.badge.checkmark")
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepSecondaryText)
                    .lineLimit(2)
            }

            if profile.hasBrokeredGrant {
                Label("Eva has an auditable access handle for this app.", systemImage: "checkmark.seal")
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepSuccess)
            }

            if let expiresAt = profile.expiresAt {
                Label("Access expires \(expiresAt.formatted(date: .abbreviated, time: .shortened))", systemImage: "calendar.badge.clock")
                    .font(.caption)
                    .foregroundStyle(profile.status == .expired ? Color.electricSheepDanger : Color.electricSheepMutedText)
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

                Button("Allow Eva") {
                    mintGrant()
                }
                .buttonStyle(.bordered)
                .help("Share this connected app with Eva through a brokered, auditable permission handle.")
                .disabled(!isSignedIn || isBusy || profile.status != .connected)

                Button("Disconnect") {
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
            return "Check connection"
        }
        if profile.status == .expired {
            return "Reconnect"
        }
        if profile.status == .planned {
            return "Coming soon"
        }
        return profile.status.displayText
    }

    private var actionButtonTitle: String {
        if profile.active {
            return "Active"
        }
        if profile.status == .connected {
            return profile.hasConnectionProof ? "Use This App" : "Check Connection"
        }
        if profile.status == .expired {
            return "Reconnect"
        }
        if profile.status == .planned {
            return "Coming Soon"
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
        case .pipedream:
            return "point.3.connected.trianglepath.dotted"
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
        case .expired:
            return .electricSheepDanger
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
        content
            .help(helpText)
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                RuntimeIconBadge(systemImage: systemImage, tint: tint)
                Spacer()
                StatusPill(title: displayStatus, systemImage: statusIcon, tint: tint)
            }
            Text(record.title)
                .font(.headline)
                .foregroundStyle(Color.electricSheepPrimaryText)
            Text(displayNextAction)
                .font(.callout)
                .foregroundStyle(Color.electricSheepSecondaryText)
                .lineLimit(2)
            if !displayDetails.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(displayDetails.prefix(3), id: \.self) { detail in
                        Text(detail)
                            .font(.caption)
                            .foregroundStyle(Color.electricSheepSecondaryText)
                            .lineLimit(1)
                    }
                }
            }

            HStack(spacing: 10) {
                if WorkbenchSessionContract.brokerRuntimeToOpen(for: record) != nil {
                    Button(actionTitle) {
                        action()
                    }
                    .buttonStyle(.borderedProminent)
                }
                Spacer()
                if let lastUpdate = shortLastUpdate {
                    Label(lastUpdate, systemImage: "clock")
                        .font(.caption2)
                        .foregroundStyle(Color.electricSheepMutedText)
                }
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

    private var displayStatus: String {
        switch record.attentionState {
        case .active:
            if record.surface == .assignedAgent {
                return record.status
            }
            return record.status.lowercased() == "loaded" ? "Loaded" : "Ready"
        case .done:
            return "Done"
        case .idle:
            return record.status.lowercased() == "restorable" ? "Saved" : "Idle"
        case .needsAttention:
            if record.surface == .assignedAgent {
                return record.status
            }
            return "Needs attention"
        case .unknown:
            return "Unknown"
        }
    }

    private var displayDetails: [String] {
        record.details.filter { detail in
            let lowercased = detail.lowercased()
            return !lowercased.contains("metadata only")
                && !lowercased.contains("broker:")
                && !lowercased.contains("queue:")
                && !lowercased.contains("audit:")
        }
    }

    private var displayNextAction: String {
        let lowercased = record.nextAction.lowercased()
        if record.id.hasPrefix("recent-") || lowercased.contains("fresh broker url") {
            return "Open this workspace again."
        }
        if lowercased.contains("auth handoff") {
            return record.nextAction.replacingOccurrences(of: "auth handoff", with: "sign-in")
        }
        return record.nextAction
    }

    private var actionTitle: String {
        record.id.hasPrefix("recent-") ? "Reopen" : "Open"
    }

    private var shortLastUpdate: String? {
        guard let value = record.updatedAt, !value.isEmpty else {
            return nil
        }
        return String(value.prefix(16)).replacingOccurrences(of: "T", with: " ")
    }

    private var helpText: String {
        if WorkbenchSessionContract.brokerRuntimeToOpen(for: record) != nil {
            return "Open this workspace."
        }
        let audit = record.auditId.map { " Audit: \($0)." } ?? ""
        return "Read-only evidence from \(record.sourcePointer).\(audit)"
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
