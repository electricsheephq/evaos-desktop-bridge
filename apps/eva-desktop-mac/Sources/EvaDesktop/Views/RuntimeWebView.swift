import EvaDesktopCore
import SwiftUI
import WebKit

struct RuntimeWebViewDeck: NSViewRepresentable {
    let store: WebViewStore
    let customerId: String
    let loadedRuntimes: [RuntimeKey]
    let activeRuntime: RuntimeKey

    func makeNSView(context: Context) -> RuntimeWebViewDeckContainer {
        RuntimeWebViewDeckContainer()
    }

    func updateNSView(_ nsView: RuntimeWebViewDeckContainer, context: Context) {
        let webViews = loadedRuntimes.map { runtime in
            RuntimeWebViewDeckContainer.Entry(
                runtime: runtime,
                webView: store.webView(for: runtime, customerId: customerId)
            )
        }
        nsView.update(entries: webViews, activeRuntime: activeRuntime)
    }
}

final class RuntimeWebViewDeckContainer: NSView {
    struct Entry {
        let runtime: RuntimeKey
        let webView: WKWebView
    }

    private var attached: [RuntimeKey: WKWebView] = [:]

    override func layout() {
        super.layout()
        for webView in attached.values {
            webView.frame = bounds
        }
    }

    func update(entries: [Entry], activeRuntime: RuntimeKey) {
        let nextKeys = Set(entries.map(\.runtime))

        let staleRuntimes = attached.keys.filter { !nextKeys.contains($0) }
        for runtime in staleRuntimes {
            attached[runtime]?.removeFromSuperview()
            attached.removeValue(forKey: runtime)
        }

        for entry in entries {
            let webView = entry.webView
            if webView.superview !== self {
                webView.removeFromSuperview()
                addSubview(webView)
            }
            attached[entry.runtime] = webView
            webView.frame = bounds
            webView.autoresizingMask = [.width, .height]
            webView.isHidden = false
            webView.alphaValue = entry.runtime == activeRuntime ? 1 : 0
        }

        if let active = attached[activeRuntime] {
            active.isHidden = false
            active.alphaValue = 1
            active.frame = bounds
            active.autoresizingMask = [.width, .height]
            addSubview(active, positioned: .above, relativeTo: nil)
        }
    }
}

struct RuntimeWebView: NSViewRepresentable {
    let webView: WKWebView

    func makeNSView(context: Context) -> WKWebView {
        webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}
}
