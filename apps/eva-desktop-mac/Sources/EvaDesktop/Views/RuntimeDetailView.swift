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
                model.reconnectSelectedRuntime()
            } label: {
                Label("Reconnect", systemImage: "arrow.clockwise")
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
        }
    }

    private var toolbarTint: Color {
        if !model.isRuntimeAvailable(definition.key) {
            return .secondary
        }
        return definition.requiresAdmin ? .electricSheepAmber : .electricSheepCyan
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
                Text("Ready to open an authenticated gateway session.")
                    .foregroundStyle(.secondary)
            }

            Button {
                model.loadSelectedRuntime()
            } label: {
                Label("Open \(definition.title)", systemImage: "play.fill")
                    .frame(minWidth: 220)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(model.isRuntimeLoading(definition.key))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
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
            Text("Requesting a short-lived gateway session.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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
