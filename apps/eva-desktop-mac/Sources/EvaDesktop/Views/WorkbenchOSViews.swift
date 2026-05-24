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
                ForEach(model.visibleRuntimes) { runtime in
                    let status = model.runtimeStatuses[runtime.key]
                    SessionCard(
                        title: runtime.title,
                        systemImage: runtime.systemImage,
                        status: sessionStatusCopy(status?.status, localURLLoaded: model.runtimeURLs[runtime.key] != nil),
                        detail: sessionDetail(runtime: runtime, status: status)
                    ) {
                        jumpToRuntime(runtime.key)
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

    private func sessionStatusCopy(_ status: String?, localURLLoaded: Bool) -> String {
        guard let status else {
            return localURLLoaded ? "Loaded" : "Unchecked"
        }
        switch status {
        case "enabled":
            return localURLLoaded ? "Loaded" : "Ready"
        case "degraded":
            return "Needs attention"
        case "disabled":
            return "Blocked"
        case "coming_soon":
            return "Unavailable"
        default:
            return status.capitalized
        }
    }

    private func sessionDetail(runtime: RuntimeDefinition, status: RuntimeStatusResponse?) -> String {
        if let error = model.runtimeErrors[runtime.key] {
            return error
        }
        guard let status else {
            return "Runtime status has not been checked yet."
        }
        if runtime.key == .liveBrowser {
            if status.authNeeded == true {
                return "Shared Browser needs auth handoff."
            }
            if status.captchaNeeded == true {
                return "Shared Browser reports CAPTCHA needed."
            }
        }
        return status.healthSummary ?? runtime.subtitle
    }

    private var sessionAttentionSummary: String {
        if model.runtimeStatuses.isEmpty {
            return "No broker session state has been loaded yet. Refresh Session Center to read gateway status."
        }
        if !model.runtimeErrors.isEmpty {
            return "\(model.runtimeErrors.count) gateway session needs attention."
        }
        let attentionCount = model.runtimeStatuses.values.filter { response in
            response.status == "degraded" || response.authNeeded == true || response.captchaNeeded == true
        }.count
        if attentionCount > 0 {
            return "\(attentionCount) session attention state needs review."
        }
        return "No gateway errors in the brokered session state."
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

private struct SessionCard: View {
    let title: String
    let systemImage: String
    let status: String
    let detail: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    RuntimeIconBadge(systemImage: systemImage, tint: .electricSheepCyan)
                    Spacer()
                    StatusPill(title: status, systemImage: status == "Loaded" ? "checkmark.circle" : "circle", tint: status == "Loaded" ? .electricSheepSuccess : .electricSheepMutedText)
                }
                Text(title)
                    .font(.headline)
                    .foregroundStyle(Color.electricSheepPrimaryText)
                Text(detail)
                    .font(.callout)
                    .foregroundStyle(Color.electricSheepSecondaryText)
                    .lineLimit(2)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.electricSheepSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Color.electricSheepLineWarm, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
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
