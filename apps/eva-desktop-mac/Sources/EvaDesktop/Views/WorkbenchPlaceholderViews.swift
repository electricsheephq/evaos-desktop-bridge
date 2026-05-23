import EvaDesktopCore
import SwiftUI
import WebKit

struct ProvidersHubView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        WorkbenchSurface(title: "Providers & Auth Hub", subtitle: "Connect provider accounts once, then let evaOS broker safe availability to OpenClaw and Hermes.") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 300), spacing: 14)], alignment: .leading, spacing: 14) {
                ForEach(WorkbenchProviderCatalog.profiles) { profile in
                    ProviderProfileCard(profile: profile, isSignedIn: model.isSignedIn)
                }
            }

            WorkbenchInfoPanel(
                title: "Credential Boundary",
                systemImage: "key.slash",
                detail: "Workbench stores metadata and readiness only. Raw provider tokens stay out of the app model; VM agents receive brokered grant state when the control plane supports it."
            )
        }
    }
}

struct SharedBrowser2View: View {
    @ObservedObject var model: WorkbenchModel
    let openSharedBrowser: () -> Void

    var body: some View {
        WorkbenchSurface(title: "Shared Browser 2.0", subtitle: "A stronger shared browsing room for agent web tasks, authentication handoff, and human takeover.") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: 12)], spacing: 12) {
                MetricTile(title: "Session", value: model.runtimeURLs[.liveBrowser] == nil ? "Not opened" : "Loaded", systemImage: "globe")
                MetricTile(title: "Owner", value: model.sanitizedCustomerId, systemImage: "person.crop.circle")
                MetricTile(title: "Human Takeover", value: "Planned", systemImage: "hand.raised")
                MetricTile(title: "Controller", value: "Status ready", systemImage: "waveform.path.ecg")
            }

            WorkbenchInfoPanel(
                title: "Runtime Contract",
                systemImage: "network",
                detail: "The customer-facing runtime stays Shared Browser. Infrastructure can still call it Live Browser while metadata flows through safe status/control endpoints."
            )

            HStack(spacing: 10) {
                Button("Open Shared Browser") {
                    openSharedBrowser()
                }
                .buttonStyle(.borderedProminent)

                Button("Reload Runtime") {
                    model.selectedRuntime = .liveBrowser
                    model.reloadSelectedRuntime()
                }
                .buttonStyle(.bordered)
                .disabled(model.runtimeURLs[.liveBrowser] == nil)
            }
        }
    }
}

struct SessionCenterView: View {
    @ObservedObject var model: WorkbenchModel
    let jumpToRuntime: (RuntimeKey) -> Void

    var body: some View {
        WorkbenchSurface(title: "Session Center", subtitle: "One place to see active gateways, attention states, Mac control readiness, and recent activity.") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                ForEach(RuntimeDefinition.all) { runtime in
                    SessionCard(
                        title: runtime.title,
                        systemImage: runtime.systemImage,
                        status: model.runtimeURLs[runtime.key] == nil ? "Ready to open" : "Loaded",
                        detail: model.runtimeErrors[runtime.key] ?? runtime.subtitle
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

    private var sessionAttentionSummary: String {
        if model.runtimeErrors.isEmpty && model.bridgeAuditText.lowercased().contains("not checked") {
            return "No attention state has been loaded yet. Open gateways or check Mac & iPhone setup to start collecting activity."
        }
        if !model.runtimeErrors.isEmpty {
            return "\(model.runtimeErrors.count) gateway session needs attention."
        }
        return "No gateway errors in the current Workbench session."
    }
}

struct CreativeStudioPlaceholderView: View {
    @ObservedObject var model: WorkbenchModel
    @StateObject private var webViewModel = CreativeStudioWebViewModel()

    var body: some View {
        WorkbenchSurface(title: "Creative Studio", subtitle: "Hosted ComfyUI-style creative workflows without putting model and GPU operations inside the macOS app.") {
            WorkbenchInfoPanel(
                title: "Hosted-first Gateway",
                systemImage: "paintbrush.pointed",
                detail: "Workbench opens the configured hosted Creative Studio URL. VM-local ComfyUI remains deferred until GPU, storage, node, and model governance are proven."
            )

            HStack(spacing: 10) {
                Text(model.creativeStudioURL.absoluteString)
                    .font(.system(.callout, design: .monospaced))
                    .lineLimit(1)
                    .textSelection(.enabled)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.electricSheepSurfaceRaised, in: RoundedRectangle(cornerRadius: 8, style: .continuous))

                Button("Load") {
                    webViewModel.load(model.creativeStudioURL)
                }
                .buttonStyle(.borderedProminent)

                Link(destination: model.creativeStudioURL) {
                    Label("Open", systemImage: "arrow.up.forward.square")
                }
            }

            RuntimeWebView(webView: webViewModel.webView)
                .frame(minHeight: 420)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(Color.electricSheepLineWarm, lineWidth: 1)
                )
        }
        .onAppear {
            webViewModel.load(model.creativeStudioURL)
        }
    }
}

private final class CreativeStudioWebViewModel: ObservableObject {
    let webView = WKWebView()
    private var loadedURL: URL?

    func load(_ url: URL) {
        guard loadedURL != url else { return }
        loadedURL = url
        webView.load(URLRequest(url: url))
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
    let profile: WorkbenchProviderProfile
    let isSignedIn: Bool

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
        switch profile.readiness {
        case .ready:
            return "Ready"
        case .needsLogin:
            return isSignedIn ? "Needs provider connection" : "Sign in first"
        case .planned:
            return "Planned"
        }
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
        switch profile.readiness {
        case .ready:
            return .electricSheepSuccess
        case .needsLogin:
            return .electricSheepCyan
        case .planned:
            return .electricSheepGoldSoft
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
