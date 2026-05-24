import EvaDesktopCore
import SwiftUI

struct SidebarView: View {
    @Binding var selection: SidebarSelection?
    @ObservedObject var model: WorkbenchModel
    @State private var pendingCustomerTarget: DesktopCustomerTarget?

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

                if model.featureFlags.isEnabled(.providersHub) {
                    FeatureSidebarRow(title: "Providers", systemImage: "person.badge.key")
                        .tag(SidebarSelection.providersHub)
                }
            }

            if model.featureFlags.isEnabled(.sessionCenter) {
                Section("Workspace") {
                    FeatureSidebarRow(title: "Session Center", systemImage: "rectangle.3.group.bubble.left")
                        .tag(SidebarSelection.sessionCenter)
                }
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
                if model.canAccessAdminRuntimes {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Viewing")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.tertiary)

                        CustomerTargetMenu(model: model, pendingTarget: $pendingCustomerTarget)

                        if let error = model.customerTargetError {
                            Text(error)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                    .padding(.bottom, 4)
                }

                Text("v\(AppBrand.version)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)

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
        .confirmationDialog(
            "Switch customer?",
            isPresented: Binding(
                get: { pendingCustomerTarget != nil },
                set: { isPresented in
                    if !isPresented {
                        pendingCustomerTarget = nil
                    }
                }
            ),
            titleVisibility: .visible
        ) {
            if let target = pendingCustomerTarget {
                Button("Switch to \(target.displayName)") {
                    model.switchCustomer(to: target)
                    pendingCustomerTarget = nil
                }
            }
            Button("Cancel", role: .cancel) {
                pendingCustomerTarget = nil
            }
        } message: {
            if let target = pendingCustomerTarget {
                Text("Loaded gateways for \(model.sanitizedCustomerId) will be replaced with \(target.customerId).")
            }
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

private struct FeatureSidebarRow: View {
    let title: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .foregroundStyle(.secondary)
                .frame(width: 18)

            Text(title)
                .lineLimit(1)
        }
    }
}
