import EvaDesktopCore
import SwiftUI

struct RuntimeDetailView: View {
    @ObservedObject var model: WorkbenchModel
    let runtime: RuntimeKey

    private var definition: RuntimeDefinition {
        RuntimeDefinition.definition(for: runtime)
    }

    private var activeRuntimeForDeck: RuntimeKey {
        model.loadedRuntimeKeys.contains(runtime) ? runtime : (model.loadedRuntimeKeys.first ?? runtime)
    }

    var body: some View {
        VStack(spacing: 0) {
            RuntimeToolbar(model: model, definition: definition)
                .padding(.horizontal, 18)
                .padding(.vertical, 14)
                .background(.bar)

            Divider()

            if RuntimeDefinition.isBrokeredRuntime(runtime) {
                RuntimeStatusStrip(model: model, definition: definition)
                Divider()
            }

            ZStack {
                if !model.loadedRuntimeKeys.isEmpty {
                    RuntimeWebViewDeck(
                        store: model.webViews,
                        customerId: model.sanitizedCustomerId,
                        loadedRuntimes: model.loadedRuntimeKeys,
                        activeRuntime: activeRuntimeForDeck
                    )
                }

                if !model.isRuntimeAvailable(definition.key) {
                    RuntimeUnavailableView(definition: definition)
                        .background(.background)
                } else if RuntimeDefinition.isBrokeredRuntime(definition.key) && !model.isSignedIn {
                    RuntimeSignInView(model: model, definition: definition)
                        .background(.background)
                } else if model.isRuntimeLoading(runtime) && model.runtimeURLs[runtime] == nil {
                    RuntimeLoadingView(definition: definition)
                        .background(.regularMaterial)
                } else if model.runtimeURLs[runtime] == nil {
                    RuntimeLaunchView(model: model, definition: definition)
                        .background(.background)
                }
            }
            .overlay(alignment: .topLeading) {
                if model.runtimeURLs[runtime] != nil && model.isRuntimePageLoading(runtime) {
                    HStack(spacing: 8) {
                        ProgressView()
                            .controlSize(.small)
                        Text("Loading \(definition.title)...")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(10)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
                    .padding()
                } else if let error = model.runtimeErrors[runtime] {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(10)
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
                        .padding()
                }
            }
        }
    }
}

private struct RuntimeToolbar: View {
    @ObservedObject var model: WorkbenchModel
    let definition: RuntimeDefinition

    var body: some View {
        HStack(spacing: 14) {
            RuntimeIconBadge(systemImage: definition.systemImage, tint: toolbarTint)

            Text(definition.title)
                .font(.headline)

            Spacer()

            Button {
                Task {
                    await model.refreshSelectedRuntimeStatus()
                }
            } label: {
                Label("Status", systemImage: "waveform.path.ecg")
            }
            .disabled(
                !RuntimeDefinition.isBrokeredRuntime(definition.key)
                || !model.isSignedIn
                || !model.isRuntimeAvailable(definition.key)
                || (definition.key == .liveBrowser && model.isRefreshingSharedBrowserStatus)
            )

            Button {
                model.reconnectSelectedRuntime()
            } label: {
                Label(reconnectTitle, systemImage: "arrow.clockwise")
            }
            .disabled((RuntimeDefinition.isBrokeredRuntime(definition.key) && !model.isSignedIn) || !model.isRuntimeAvailable(definition.key) || model.isRuntimeLoading(definition.key))

            Button {
                model.reloadSelectedRuntime()
            } label: {
                Label("Reload", systemImage: "arrow.triangle.2.circlepath")
            }
            .disabled((RuntimeDefinition.isBrokeredRuntime(definition.key) && !model.isSignedIn) || !model.isRuntimeAvailable(definition.key))

            Button {
                model.openSelectedRuntimeExternally()
            } label: {
                Label("Open", systemImage: "safari")
            }
            .disabled((RuntimeDefinition.isBrokeredRuntime(definition.key) && !model.isSignedIn) || !model.isRuntimeAvailable(definition.key) || model.runtimeURLs[definition.key] == nil)

            if definition.key == .liveBrowser {
                Button {
                    Task {
                        await model.stopSharedBrowserSession()
                    }
                } label: {
                    Label(model.isStoppingSharedBrowser ? "Stopping" : "Stop Browser", systemImage: "power")
                }
                .disabled(!model.isSignedIn || !model.isRuntimeAvailable(definition.key) || model.isStoppingSharedBrowser)
            }

            Button {
                model.closeSelectedRuntimeView()
            } label: {
                Label("Close View", systemImage: "xmark.circle")
            }
            .disabled(model.runtimeURLs[definition.key] == nil)
        }
    }

    private var toolbarTint: Color {
        if !model.isRuntimeAvailable(definition.key) {
            return .secondary
        }
        return definition.requiresAdmin ? .electricSheepAmber : .electricSheepCyan
    }

    private var reconnectTitle: String {
        if definition.key == .liveBrowser, model.runtimeURLs[definition.key] == nil {
            return "Start / Attach"
        }
        return "Reconnect"
    }
}

private struct RuntimeSignInView: View {
    @ObservedObject var model: WorkbenchModel
    let definition: RuntimeDefinition

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "person.crop.circle.badge.checkmark")
                .font(.system(size: 44))
                .foregroundStyle(Color.electricSheepCyan)
                .frame(width: 72, height: 72)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 16))

            VStack(spacing: 6) {
                Text("Sign in once to open \(AppBrand.visibleName)")
                    .font(.title3.weight(.semibold))
                Text("Login opens in a secure ElectricSheep popup, then this tab loads \(definition.title) directly. The app stores only an opaque desktop session in Keychain.")
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 520)
            }

            Button {
                model.signIn()
            } label: {
                Label(model.isSigningIn ? "Open Login Again" : "Sign In with ElectricSheep", systemImage: "arrow.up.forward.app")
                    .frame(minWidth: 220)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(model.isSigningIn && model.lastSignInURL == nil)

            if model.isSigningIn {
                Button {
                    model.cancelSignIn()
                } label: {
                    Label("Cancel Login", systemImage: "xmark.circle")
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Backup code from browser")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    TextField("ABCD-EFGH-IJKL", text: $model.deviceCodeInput)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(.body, design: .monospaced))
                        .onSubmit {
                            model.claimDeviceCode()
                        }

                    Button(model.isClaimingDeviceCode ? "Checking..." : "Use Code") {
                        model.claimDeviceCode()
                    }
                    .buttonStyle(.bordered)
                    .disabled(model.isClaimingDeviceCode || model.deviceCodeInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                Text(model.deviceCodeStatusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Use the Backup code shown on the browser page. If no page appears, press Open Login Again; if a code fails, start a fresh sign-in.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .frame(maxWidth: 420)
            .padding(14)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))

            Button {
                model.resetLocalSession()
            } label: {
                Label("Reset Local Session", systemImage: "key.slash")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

private struct RuntimeStatusStrip: View {
    @ObservedObject var model: WorkbenchModel
    let definition: RuntimeDefinition

    private var status: RuntimeStatusResponse? {
        model.runtimeStatuses[definition.key]
    }

    private var error: String? {
        model.runtimeErrors[definition.key]
    }

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            RuntimeIconBadge(systemImage: statusIcon, tint: tint)
            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 8) {
                    Text(statusTitle)
                        .font(.subheadline.weight(.semibold))
                    StatusPill(title: statusPillText, systemImage: statusIcon, tint: tint)
                }
                Text(statusDetail)
                    .font(.caption)
                    .foregroundStyle(Color.electricSheepSecondaryText)
                    .lineLimit(2)
                HStack(spacing: 10) {
                    ForEach(detailChips, id: \.self) { chip in
                        Text(chip)
                            .font(.caption2.monospaced())
                            .foregroundStyle(Color.electricSheepMutedText)
                            .lineLimit(1)
                    }
                }
            }
            Spacer()
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .background(Color.electricSheepSurfaceRaised)
    }

    private var statusTitle: String {
        if definition.key == .liveBrowser {
            return "Shared Browser status"
        }
        return "\(definition.title) status"
    }

    private var statusPillText: String {
        if let error {
            return error.isEmpty ? "Unavailable" : "Needs attention"
        }
        if definition.key == .liveBrowser, model.sharedBrowserStatusText != "Unchecked" {
            return model.sharedBrowserStatusText
        }
        guard let status else { return "Not checked" }
        return status.status
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "-", with: " ")
            .capitalized
    }

    private var statusDetail: String {
        if let error {
            return error
        }
        guard let status else {
            return "Refresh status to read broker runtime metadata for this customer."
        }
        if status.authNeeded == true {
            return "\(definition.title) needs sign-in."
        }
        if status.captchaNeeded == true {
            return "\(definition.title) needs a CAPTCHA or browser challenge."
        }
        if status.waitingOnUser == true {
            return "\(definition.title) is waiting on the user."
        }
        if status.updateAvailable == true {
            return "\(definition.title) has an update available."
        }
        if status.controlSessionActive == true {
            return "\(definition.title) has an active control session."
        }
        if definition.key == .liveBrowser, isInactiveSharedBrowserStatus(status) {
            return "Open Shared Browser to start or reattach. Startup can take up to a minute after the browser has been idle."
        }
        return status.healthSummary ?? definition.subtitle
    }

    private var detailChips: [String] {
        if definition.key == .liveBrowser {
            return [
                "room \(capped(model.sharedBrowserRoomText, limit: 48))",
                "url \(capped(model.sharedBrowserCurrentURLText, limit: 64))",
                "activity \(capped(model.sharedBrowserLastActivityText, limit: 64))",
            ]
        }
        guard let status else {
            return ["source broker:runtime_status:\(definition.key.rawValue)"]
        }
        return [
            status.owner.map { "owner \(capped($0, limit: 48))" },
            status.roomId.map { "room \(capped($0, limit: 48))" },
            status.lastCheckedAt.map { "checked \(shortDate($0))" },
        ].compactMap { $0 }
    }

    private var tint: Color {
        if isAttention {
            return .electricSheepDanger
        }
        guard let status else {
            return .electricSheepGoldSoft
        }
        switch status.status.lowercased() {
        case "enabled", "ready", "active", "loaded":
            return .electricSheepSuccess
        default:
            return .electricSheepGoldSoft
        }
    }

    private var isAttention: Bool {
        if error != nil {
            return true
        }
        guard let status else {
            return false
        }
        if status.authNeeded == true || status.captchaNeeded == true || status.waitingOnUser == true || status.updateAvailable == true {
            return true
        }
        switch status.status.lowercased() {
        case "degraded", "disabled", "error", "failed", "unavailable", "offline":
            return true
        default:
            return false
        }
    }

    private var statusIcon: String {
        isAttention ? "exclamationmark.triangle" : "waveform.path.ecg"
    }

    private func isInactiveSharedBrowserStatus(_ status: RuntimeStatusResponse) -> Bool {
        switch status.status.lowercased() {
        case "degraded", "disabled", "error", "failed", "unavailable", "offline":
            return true
        default:
            return false
        }
    }

    private func shortDate(_ date: Date) -> String {
        date.formatted(date: .omitted, time: .shortened)
    }

    private func capped(_ value: String, limit: Int) -> String {
        if value.count <= limit {
            return value
        }
        return String(value.prefix(limit)) + "..."
    }
}

private struct RuntimeLaunchView: View {
    @ObservedObject var model: WorkbenchModel
    let definition: RuntimeDefinition

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: definition.systemImage)
                .font(.system(size: 38))
                .foregroundStyle(Color.electricSheepCyan)
                .frame(width: 68, height: 68)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 16))

            Text(definition.title)
                .font(.title3.weight(.semibold))

            if let error = model.runtimeErrors[definition.key] {
                Text(error)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 560)
            } else {
                Text(launchDetail)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 560)
            }

            Button {
                model.loadSelectedRuntime()
            } label: {
                Label(launchButtonTitle, systemImage: "play.fill")
                    .frame(minWidth: 220)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(model.isRuntimeLoading(definition.key))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var launchDetail: String {
        if definition.key == .liveBrowser {
            return "Ready to start or attach to the shared VM browser."
        }
        return "Ready to open an authenticated gateway session."
    }

    private var launchButtonTitle: String {
        if definition.key == .liveBrowser {
            return "Start / Attach Shared Browser"
        }
        return "Open \(definition.title)"
    }
}

private struct RuntimeLoadingView: View {
    let definition: RuntimeDefinition

    var body: some View {
        VStack(spacing: 14) {
            ProgressView()
                .controlSize(.large)
            Text("Opening \(definition.title)...")
                .font(.headline)
            Text(loadingDetail)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var loadingDetail: String {
        if definition.key == .liveBrowser {
            return "Starting or attaching to the shared VM browser. This can take up to a minute after idle."
        }
        return "Requesting a short-lived gateway session."
    }
}

private struct RuntimeUnavailableView: View {
    let definition: RuntimeDefinition

    var body: some View {
        ContentUnavailableView {
            Label(definition.title, systemImage: definition.systemImage)
        } description: {
            Text("This gateway is not available yet.")
        }
    }
}
