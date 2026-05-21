import EvaDesktopCore
import SwiftUI

struct SidebarView: View {
    @Binding var selection: SidebarSelection?
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        List(selection: $selection) {
            Section(AppBrand.runtimeSectionTitle) {
                ForEach(model.visibleRuntimes) { runtime in
                    RuntimeSidebarRow(runtime: runtime)
                        .tag(SidebarSelection.runtime(runtime.key))
                }
            }

            Section(AppBrand.bridgeSectionTitle) {
                Label(AppBrand.macAndIPhoneTitle, systemImage: "macbook.and.iphone")
                    .tag(SidebarSelection.bridge)
            }
        }
        .listStyle(.sidebar)
        .tint(Color.electricSheepGoldSoft)
        .navigationTitle("")
        .safeAreaInset(edge: .top, spacing: 0) {
            SidebarBrandHeader()
                .padding(.horizontal, 14)
                .padding(.top, 14)
                .padding(.bottom, 10)
        }
        .safeAreaInset(edge: .bottom) {
            VStack(alignment: .leading, spacing: 8) {
                Text(model.isSignedIn ? (model.session?.userEmail ?? "Signed in") : AppBrand.signedOutStatus)
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

private struct SidebarBrandHeader: View {
    var body: some View {
        BrandWordmark()
            .frame(maxWidth: 170, minHeight: 28, maxHeight: 34, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct RuntimeSidebarRow: View {
    let runtime: RuntimeDefinition

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: runtime.systemImage)
                .foregroundStyle(rowColor)
                .frame(width: 18)

            Text(runtime.title)
                .lineLimit(1)
        }
    }

    private var rowColor: Color {
        if runtime.availability != .enabled {
            return .secondary
        }
        return runtime.requiresAdmin ? .electricSheepAmber : .secondary
    }
}
