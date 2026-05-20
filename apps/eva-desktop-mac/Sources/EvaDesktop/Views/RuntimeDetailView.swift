import EvaDesktopCore
import SwiftUI

struct RuntimeDetailView: View {
    @ObservedObject var model: WorkbenchModel
    let runtime: RuntimeKey

    private var definition: RuntimeDefinition {
        RuntimeDefinition.definition(for: runtime)
    }

    var body: some View {
        VStack(spacing: 0) {
            RuntimeToolbar(model: model, definition: definition)
                .padding()
                .background(.regularMaterial)

            Divider()

            if definition.availability != .enabled {
                RuntimeUnavailableView(definition: definition)
            } else if !model.isSignedIn {
                RuntimeSignInView(model: model, definition: definition)
            } else if model.isLoadingRuntime && model.runtimeURLs[runtime] == nil {
                RuntimeLoadingView(definition: definition)
            } else if let url = model.runtimeURLs[runtime] {
                RuntimeWebView(webView: model.webViews.webView(for: runtime, customerId: model.sanitizedCustomerId))
                    .id("\(runtime.rawValue)-\(model.sanitizedCustomerId)-\(model.webViewRefreshToken)")
                    .overlay(alignment: .topLeading) {
                        if let error = model.runtimeErrors[runtime] {
                            Text(error)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(10)
                                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
                                .padding()
                        }
                    }
                    .task(id: url) {
                        model.webViews
                            .webView(for: runtime, customerId: model.sanitizedCustomerId)
                            .load(URLRequest(url: url))
                    }
            } else {
                RuntimeLaunchView(model: model, definition: definition)
            }
        }
    }
}

private struct RuntimeToolbar: View {
    @ObservedObject var model: WorkbenchModel
    let definition: RuntimeDefinition

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: definition.systemImage)
                .font(.title2)
                .frame(width: 34, height: 34)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 3) {
                Text(definition.title)
                    .font(.headline)
                Text(model.session?.userEmail.map { "Signed in as \($0)" } ?? definition.subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            TextField("Customer", text: $model.customerId)
                .textFieldStyle(.roundedBorder)
                .frame(width: 180)
                .onSubmit {
                    model.loadSelectedRuntime()
                }
                .help("Preview/admin target. The runtime session broker remains the authority for customer and runtime access.")

            Button {
                model.loadSelectedRuntime()
            } label: {
                Label("Load", systemImage: "arrow.clockwise")
            }
            .disabled(!model.isSignedIn || definition.availability != .enabled || model.isLoadingRuntime)

            Button {
                model.reloadSelectedRuntime()
            } label: {
                Label("Reload", systemImage: "arrow.triangle.2.circlepath")
            }
            .disabled(!model.isSignedIn || definition.availability != .enabled)

            Button {
                model.openSelectedRuntimeExternally()
            } label: {
                Label("Open", systemImage: "safari")
            }
            .disabled(!model.isSignedIn || definition.availability != .enabled || model.runtimeURLs[definition.key] == nil)
        }
    }
}

private struct RuntimeSignInView: View {
    @ObservedObject var model: WorkbenchModel
    let definition: RuntimeDefinition

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "person.crop.circle.badge.checkmark")
                .font(.system(size: 44))
                .foregroundStyle(.teal)
                .frame(width: 72, height: 72)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 16))

            VStack(spacing: 6) {
                Text("Sign in once to open Eva Desktop")
                    .font(.title3.weight(.semibold))
                Text("Login opens in a secure ElectricSheep popup, then this tab loads \(definition.title) directly. The app stores only an opaque desktop session in Keychain.")
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 520)
            }

            Button {
                model.signIn()
            } label: {
                Label(model.isSigningIn ? "Opening Login..." : "Sign In with ElectricSheep", systemImage: "arrow.up.forward.app")
                    .frame(minWidth: 220)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(model.isSigningIn)
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
                .foregroundStyle(.teal)
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
                Text("Ready to open an authenticated runtime session.")
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
            .disabled(model.isLoadingRuntime)
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
            Text("Requesting a short-lived runtime session.")
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
            Text("This tab is reserved for the next Workbench integration pass.")
        }
    }
}
