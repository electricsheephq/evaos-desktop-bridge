import EvaDesktopCore
import SwiftUI

struct CustomerTargetMenu: View {
    @ObservedObject var model: WorkbenchModel
    @Binding var pendingTarget: DesktopCustomerTarget?

    var body: some View {
        Menu {
            if model.customerTargets.isEmpty {
                Text("No customer targets loaded")
            } else {
                ForEach(model.customerTargets) { target in
                    Button {
                        pendingTarget = target
                    } label: {
                        HStack {
                            Text(target.displayName)
                            Text(target.customerId)
                        }
                    }
                    .disabled(normalized(target.customerId) == model.sanitizedCustomerId)
                }
            }

            Divider()

            Button {
                Task {
                    await model.refreshCustomerTargets()
                }
            } label: {
                Label("Refresh Customers", systemImage: "arrow.clockwise")
            }
            .disabled(model.isLoadingCustomerTargets)

            Button {
                model.resetCustomerTargetToDefault()
            } label: {
                Label("Reset to Golden", systemImage: "arrow.uturn.backward")
            }
            .disabled(model.sanitizedCustomerId == "golden")
        } label: {
            Label(customerLabel, systemImage: "person.2.badge.key")
                .lineLimit(1)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .disabled(model.isLoadingCustomerTargets)
        .help("Admin customer switcher")
    }

    private var customerLabel: String {
        if let target = model.currentCustomerTarget {
            return target.displayName
        }
        return model.sanitizedCustomerId
    }

    private func normalized(_ value: String) -> String {
        value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "_", with: "-")
            .replacingOccurrences(of: " ", with: "-")
            .filter { $0.isLetter || $0.isNumber || $0 == "-" }
    }
}
