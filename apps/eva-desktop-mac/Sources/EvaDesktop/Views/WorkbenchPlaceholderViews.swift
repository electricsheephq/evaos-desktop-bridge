import SwiftUI

struct WorkbenchPlaceholderView: View {
    let title: String
    let systemImage: String
    let message: String

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: systemImage)
                .font(.system(size: 36))
                .foregroundStyle(Color.electricSheepCyan)
                .frame(width: 72, height: 72)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 16))

            VStack(spacing: 8) {
                Text(title)
                    .font(.title3.weight(.semibold))

                Text(message)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 520)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(24)
        .background(.background)
    }
}

struct CreativeStudioPlaceholderView: View {
    @ObservedObject var model: WorkbenchModel

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "paintbrush.pointed")
                .font(.system(size: 36))
                .foregroundStyle(Color.electricSheepCyan)
                .frame(width: 72, height: 72)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 16))

            VStack(spacing: 8) {
                Text("Creative Studio")
                    .font(.title3.weight(.semibold))

                Text("Workbench keeps Creative Studio pointed at a hosted dashboard URL first. No VM-local ComfyUI dependency is required for this preview surface.")
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 560)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Configured hosted URL")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)

                Text(model.creativeStudioURL.absoluteString)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)

                Link(destination: model.creativeStudioURL) {
                    Label("Open Hosted URL", systemImage: "arrow.up.forward.square")
                }
            }
            .padding(16)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(24)
        .background(.background)
    }
}
