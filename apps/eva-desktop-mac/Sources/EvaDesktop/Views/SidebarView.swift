import EvaDesktopCore
import SwiftUI

struct SidebarView: View {
    @Binding var selection: SidebarSelection?
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        List(selection: $selection) {
            Section("Workspaces") {
                ForEach(model.runtimes) { runtime in
                    RuntimeSidebarRow(runtime: runtime)
                        .tag(SidebarSelection.runtime(runtime.key))
                }
            }

            Section("Local Bridge") {
                Label("Status & Audit", systemImage: "shield.lefthalf.filled")
                    .tag(SidebarSelection.bridge)
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Eva Desktop")
        .safeAreaInset(edge: .bottom) {
            VStack(alignment: .leading, spacing: 8) {
                Text(model.isSignedIn ? (model.session?.userEmail ?? "Signed in") : "Sign in to launch runtimes")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                HStack {
                    if !model.isSignedIn {
                        Button(model.isSigningIn ? "Opening..." : "Sign In") {
                            model.signIn()
                        }
                        .disabled(model.isSigningIn)
                    } else {
                        Button("Sign Out") {
                            model.signOut()
                        }
                    }
                }
                .buttonStyle(.bordered)
            }
            .padding()
        }
    }
}

private struct RuntimeSidebarRow: View {
    let runtime: RuntimeDefinition

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: runtime.systemImage)
                .foregroundStyle(rowColor)
                .frame(width: 18)

            VStack(alignment: .leading, spacing: 2) {
                Text(runtime.title)
                    .lineLimit(1)

                Text(runtime.requiresAdmin ? "Admin pilot" : runtime.subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
    }

    private var rowColor: Color {
        if runtime.availability != .enabled {
            return .secondary
        }
        return runtime.requiresAdmin ? .orange : .secondary
    }
}
