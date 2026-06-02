import EvaDesktopCore
import SwiftUI

struct SidebarView: View {
    @Binding var selection: SidebarSelection?
    @ObservedObject var model: WorkbenchModel
    @State private var pendingCustomerTarget: DesktopCustomerTarget?

    var body: some View {
        List(selection: $selection) {
            if model.featureFlags.isEnabled(.sessionCenter), model.featureFlags.isEnabled(.approvalCenter) {
                Section("Home") {
                    homeSidebarRows
                }
            } else if model.featureFlags.isEnabled(.sessionCenter) || model.featureFlags.isEnabled(.approvalCenter) {
                homeSidebarRows
            }

            Section(AppBrand.runtimeSectionTitle) {
                ForEach(model.visibleWorkspaceRuntimes) { runtime in
                    RuntimeSidebarRow(runtime: runtime)
                        .tag(SidebarSelection.runtime(runtime.key))
                }
            }

            if shouldShowBusinessAdminSection {
                Section("Business Admin") {
                    if model.featureFlags.isEnabled(.providersHub), model.canOpenSurface("connected_apps") {
                        FeatureSidebarRow(title: "Connected Apps", systemImage: "person.badge.key")
                            .tag(SidebarSelection.providersHub)
                    }
                    if model.canOpenPeopleAccessDashboard {
                        Button {
                            model.openPeopleAccessDashboard()
                        } label: {
                            FeatureSidebarRow(title: "People & Access", systemImage: "person.2.badge.gearshape")
                        }
                        .buttonStyle(.plain)
                    }
                    if model.canOpenCompanyBrainDashboard {
                        Button {
                            model.openCompanyBrainDashboard()
                        } label: {
                            FeatureSidebarRow(title: "Company Brain", systemImage: "brain")
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            if !model.visibleTechnicalDashboardRuntimes.isEmpty {
                Section("Technical Dashboards") {
                    ForEach(model.visibleTechnicalDashboardRuntimes) { runtime in
                        RuntimeSidebarRow(runtime: runtime, title: runtime.technicalDashboardTitle)
                            .tag(SidebarSelection.runtime(runtime.key))
                    }
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
                        Button(model.isSigningIn ? "Open Login" : "Sign In") {
                            model.signIn()
                        }
                        .disabled(model.isSigningIn && model.lastSignInURL == nil)
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
                Text("Open workspaces for \(model.sanitizedCustomerId) will be replaced with \(target.customerId).")
            }
        }
    }

    @ViewBuilder
    private var homeSidebarRows: some View {
        if model.featureFlags.isEnabled(.sessionCenter) {
            FeatureSidebarRow(title: "Home", systemImage: "house")
                .tag(SidebarSelection.sessionCenter)
        }

        if model.featureFlags.isEnabled(.approvalCenter), model.canOpenSurface("approvals") {
            FeatureSidebarRow(title: "Approvals", systemImage: "checkmark.shield")
                .tag(SidebarSelection.approvalCenter)
        }
    }

    private var shouldShowBusinessAdminSection: Bool {
        model.canOpenPeopleAccessDashboard
            || model.canOpenCompanyBrainDashboard
            || (model.featureFlags.isEnabled(.providersHub) && model.canOpenSurface("connected_apps"))
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
    var title: String? = nil

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: runtime.systemImage)
                .foregroundStyle(rowColor)
                .frame(width: 18)

            Text(title ?? runtime.title)
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
