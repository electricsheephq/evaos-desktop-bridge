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

            if let url = model.runtimeURLs[runtime] {
                RuntimeWebView(webView: model.webViews.webView(for: runtime, customerId: RuntimeURLResolver().sanitizedCustomerId(model.customerId)))
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
                            .webView(for: runtime, customerId: RuntimeURLResolver().sanitizedCustomerId(model.customerId))
                            .load(URLRequest(url: url))
                    }
            } else {
                ContentUnavailableView("Runtime not loaded", systemImage: definition.systemImage)
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
                Text(definition.subtitle)
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

            Button {
                model.loadSelectedRuntime()
            } label: {
                Label("Load", systemImage: "arrow.clockwise")
            }

            Button {
                model.reloadSelectedRuntime()
            } label: {
                Label("Reload", systemImage: "arrow.triangle.2.circlepath")
            }

            Button {
                model.openSelectedRuntimeExternally()
            } label: {
                Label("Open", systemImage: "safari")
            }
        }
    }
}

