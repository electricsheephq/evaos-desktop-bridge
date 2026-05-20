import AuthenticationServices
import EvaDesktopCore
import Foundation
import SwiftUI
import WebKit

@MainActor
final class WorkbenchModel: ObservableObject {
    @Published var customerId: String = UserDefaults.standard.string(forKey: "EvaDesktop.customerId") ?? "golden" {
        didSet {
            UserDefaults.standard.set(customerId, forKey: "EvaDesktop.customerId")
        }
    }
    @Published var selectedRuntime: RuntimeKey = .openclaw
    @Published var session: DesktopSession?
    @Published var isLoadingRuntime = false
    @Published var runtimeURLs: [RuntimeKey: URL] = [:]
    @Published var runtimeErrors: [RuntimeKey: String] = [:]
    @Published var bridgeStatusText = "Bridge status has not been checked yet."
    @Published var bridgeCapabilitiesText = "Bridge capabilities have not been checked yet."
    @Published var bridgeAuditText = "Bridge audit trail has not been checked yet."

    let runtimes = RuntimeDefinition.all
    let webViews = WebViewStore()

    private let keychain = KeychainSessionStore()
    private let broker = RuntimeSessionBrokerClient()
    private let resolver = RuntimeURLResolver()
    private let bridge = BridgeCommandService()

    init() {
        session = try? keychain.load()
        for runtime in RuntimeDefinition.all {
            runtimeURLs[runtime.key] = resolver.fallbackURL(for: runtime.key, customerId: customerId)
        }
    }

    var selectedRuntimeDefinition: RuntimeDefinition {
        RuntimeDefinition.definition(for: selectedRuntime)
    }

    func loadSelectedRuntime() {
        Task {
            await loadRuntime(selectedRuntime)
        }
    }

    func loadRuntime(_ runtime: RuntimeKey) async {
        isLoadingRuntime = true
        runtimeErrors[runtime] = nil

        do {
            let response = try await broker.launchURL(
                customerId: resolver.sanitizedCustomerId(customerId),
                runtime: runtime,
                desktopSession: session
            )
            runtimeURLs[runtime] = response.launchUrl
        } catch RuntimeSessionBrokerError.missingSession {
            runtimeURLs[runtime] = resolver.fallbackURL(for: runtime, customerId: customerId)
            runtimeErrors[runtime] = "Using the public runtime route until desktop login and broker session are connected."
        } catch {
            runtimeURLs[runtime] = resolver.fallbackURL(for: runtime, customerId: customerId)
            runtimeErrors[runtime] = "Session broker failed: \(error.localizedDescription). Showing the fallback route."
        }

        if let url = runtimeURLs[runtime] {
            webViews.webView(for: runtime, customerId: resolver.sanitizedCustomerId(customerId)).load(URLRequest(url: url))
        }
        isLoadingRuntime = false
    }

    func reloadSelectedRuntime() {
        let sanitized = resolver.sanitizedCustomerId(customerId)
        webViews.webView(for: selectedRuntime, customerId: sanitized).reload()
    }

    func openSelectedRuntimeExternally() {
        guard let url = runtimeURLs[selectedRuntime] else { return }
        NSWorkspace.shared.open(url)
    }

    func signIn() {
        Task {
            let coordinator = DesktopAuthCoordinator()
            do {
                let newSession = try await coordinator.signIn()
                try keychain.save(newSession)
                session = newSession
                await loadRuntime(selectedRuntime)
            } catch {
                runtimeErrors[selectedRuntime] = "Desktop sign-in failed or was cancelled: \(error.localizedDescription)"
            }
        }
    }

    func signOut() {
        try? keychain.clear()
        session = nil
        webViews.reset()
        for runtime in RuntimeDefinition.all {
            runtimeURLs[runtime.key] = resolver.fallbackURL(for: runtime.key, customerId: customerId)
        }
    }

    func refreshBridgeStatus() {
        Task {
            bridgeStatusText = await bridge.run(arguments: ["status", "--json"])
            bridgeCapabilitiesText = await bridge.run(arguments: ["capabilities", "--json"])
            bridgeAuditText = await bridge.run(arguments: ["audit-tail", "--json", "--limit", "12"])
        }
    }
}

final class WebViewStore {
    private var webViews: [String: WKWebView] = [:]

    func webView(for runtime: RuntimeKey, customerId: String) -> WKWebView {
        let key = "\(customerId)::\(runtime.rawValue)"
        if let webView = webViews[key] {
            return webView
        }

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.allowsBackForwardNavigationGestures = true
        webView.customUserAgent = "EvaDesktop/0.1 WKWebView"
        webViews[key] = webView
        return webView
    }

    func reset() {
        webViews.removeAll()
    }
}

final class DesktopAuthCoordinator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var authSession: ASWebAuthenticationSession?

    func signIn() async throws -> DesktopSession {
        let authURL = URL(string: "https://www.electricsheephq.com/dashboard?desktop_app=1")!

        return try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(
                url: authURL,
                callbackURLScheme: "evaos"
            ) { callbackURL, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }

                guard
                    let callbackURL,
                    let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)
                else {
                    continuation.resume(throwing: RuntimeSessionBrokerError.invalidResponse)
                    return
                }

                let items = components.queryItems ?? []
                let token = items.first(where: { $0.name == "desktop_session" })?.value
                    ?? items.first(where: { $0.name == "access_token" })?.value
                    ?? items.first(where: { $0.name == "code" })?.value
                let email = items.first(where: { $0.name == "email" })?.value

                guard let token, !token.isEmpty else {
                    continuation.resume(throwing: RuntimeSessionBrokerError.invalidResponse)
                    return
                }

                continuation.resume(returning: DesktopSession(accessToken: token, userEmail: email))
            }

            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            authSession = session
            session.start()
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        NSApplication.shared.keyWindow ?? NSApplication.shared.windows.first ?? NSWindow()
    }
}

struct BridgeCommandService {
    func run(arguments: [String]) async -> String {
        await Task.detached {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["evaos-desktop-bridge"] + arguments

            let pipe = Pipe()
            let errorPipe = Pipe()
            process.standardOutput = pipe
            process.standardError = errorPipe

            do {
                try process.run()
                process.waitUntilExit()
            } catch {
                return "Unable to run evaos-desktop-bridge: \(error.localizedDescription)"
            }

            let stdout = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let stderr = String(data: errorPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let output = stdout.isEmpty ? stderr : stdout
            return output.trimmingCharacters(in: .whitespacesAndNewlines)
        }.value
    }
}

