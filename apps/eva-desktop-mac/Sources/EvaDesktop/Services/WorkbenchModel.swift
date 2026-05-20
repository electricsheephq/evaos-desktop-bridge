import AuthenticationServices
import EvaDesktopCore
import Foundation
import SwiftUI
import WebKit

@MainActor
final class WorkbenchModel: ObservableObject {
    @Published var dashboardBaseURLString: String = UserDefaults.standard.string(forKey: "EvaDesktop.dashboardBaseURL") ?? "https://www.electricsheephq.com" {
        didSet {
            UserDefaults.standard.set(dashboardBaseURLString, forKey: "EvaDesktop.dashboardBaseURL")
            rebuildClients()
        }
    }
    @Published var runtimeBaseDomain: String = UserDefaults.standard.string(forKey: "EvaDesktop.runtimeBaseDomain") ?? "ecs.electricsheephq.com" {
        didSet {
            UserDefaults.standard.set(runtimeBaseDomain, forKey: "EvaDesktop.runtimeBaseDomain")
            rebuildClients()
        }
    }
    @Published var customerId: String = UserDefaults.standard.string(forKey: "EvaDesktop.customerId") ?? "golden" {
        didSet {
            UserDefaults.standard.set(customerId, forKey: "EvaDesktop.customerId")
            webViews.reset()
            runtimeURLs.removeAll()
            runtimeErrors.removeAll()
            webViewRefreshToken = UUID()
        }
    }
    @Published var selectedRuntime: RuntimeKey = .openclaw
    @Published var session: DesktopSession?
    @Published var isSigningIn = false
    @Published var isLoadingRuntime = false
    @Published var runtimeURLs: [RuntimeKey: URL] = [:]
    @Published var runtimeErrors: [RuntimeKey: String] = [:]
    @Published var bridgeStatusText = "Bridge status has not been checked yet."
    @Published var bridgeCapabilitiesText = "Bridge capabilities have not been checked yet."
    @Published var bridgeAuditText = "Bridge audit trail has not been checked yet."
    @Published var webViewRefreshToken = UUID()

    let runtimes = RuntimeDefinition.all
    let webViews = WebViewStore()

    private let keychain = KeychainSessionStore()
    private var broker: RuntimeSessionBrokerClient
    private var resolver: RuntimeURLResolver
    private let bridge = BridgeCommandService()

    init() {
        let dashboardBaseURL = URL(string: UserDefaults.standard.string(forKey: "EvaDesktop.dashboardBaseURL") ?? "https://www.electricsheephq.com")
            ?? URL(string: "https://www.electricsheephq.com")!
        let runtimeBaseDomain = UserDefaults.standard.string(forKey: "EvaDesktop.runtimeBaseDomain") ?? "ecs.electricsheephq.com"
        broker = RuntimeSessionBrokerClient()
        resolver = RuntimeURLResolver(runtimeBaseDomain: runtimeBaseDomain, dashboardBaseURL: dashboardBaseURL)
        session = try? keychain.load()
        if session?.isExpired == true {
            try? keychain.clear()
            session = nil
        }
    }

    var selectedRuntimeDefinition: RuntimeDefinition {
        RuntimeDefinition.definition(for: selectedRuntime)
    }

    var sanitizedCustomerId: String {
        resolver.sanitizedCustomerId(customerId)
    }

    var isSignedIn: Bool {
        guard let session else { return false }
        return !session.isExpired
    }

    func loadSelectedRuntime() {
        Task {
            await loadRuntime(selectedRuntime)
        }
    }

    func loadRuntime(_ runtime: RuntimeKey) async {
        guard RuntimeDefinition.isBrokeredRuntime(runtime) else {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = "OpenDesign is reserved for the next desktop integration pass."
            return
        }

        guard isSignedIn else {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = nil
            return
        }

        isLoadingRuntime = true
        runtimeErrors[runtime] = nil

        do {
            let response = try await broker.launchURL(
                customerId: resolver.sanitizedCustomerId(customerId),
                runtime: runtime,
                desktopSession: session
            )
            runtimeURLs[runtime] = response.launchUrl
        } catch {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = "Session broker failed: \(error.localizedDescription)."
        }

        if let url = runtimeURLs[runtime] {
            webViews.webView(for: runtime, customerId: resolver.sanitizedCustomerId(customerId)).load(URLRequest(url: url))
        }
        isLoadingRuntime = false
    }

    func reloadSelectedRuntime() {
        guard isSignedIn else {
            loadSelectedRuntime()
            return
        }
        let sanitized = resolver.sanitizedCustomerId(customerId)
        webViews.webView(for: selectedRuntime, customerId: sanitized).reload()
    }

    func openSelectedRuntimeExternally() {
        guard let url = runtimeURLs[selectedRuntime] else { return }
        NSWorkspace.shared.open(url)
    }

    func signIn() {
        guard !isSigningIn else { return }
        isSigningIn = true

        Task {
            let coordinator = DesktopAuthCoordinator(dashboardBaseURL: resolver.dashboardBaseURL)
            defer { isSigningIn = false }

            do {
                let newSession = try await coordinator.signIn()
                try saveAuthenticatedSession(newSession)
                await loadRuntime(selectedRuntime)
            } catch {
                runtimeErrors[selectedRuntime] = "Desktop sign-in failed or was cancelled: \(error.localizedDescription)"
            }
        }
    }

    func signOut() {
        let sessionToRevoke = session
        try? keychain.clear()
        session = nil
        webViews.reset()
        runtimeURLs.removeAll()
        runtimeErrors.removeAll()
        webViewRefreshToken = UUID()
        Task {
            await broker.revoke(desktopSession: sessionToRevoke)
        }
    }

    func handleAuthCallback(_ url: URL) {
        do {
            let newSession = try DesktopSessionCallbackParser.parse(url)
            try saveAuthenticatedSession(newSession)
            loadSelectedRuntime()
        } catch {
            runtimeErrors[selectedRuntime] = "Desktop sign-in callback failed: \(error.localizedDescription)"
        }
    }

    func refreshBridgeStatus() {
        Task {
            bridgeStatusText = await bridge.run(arguments: ["status", "--json"])
            bridgeCapabilitiesText = await bridge.run(arguments: ["capabilities", "--json"])
            bridgeAuditText = await bridge.run(arguments: ["audit-tail", "--json", "--limit", "12"])
        }
    }

    private func rebuildClients() {
        guard let dashboardBaseURL = URL(string: dashboardBaseURLString) else {
            runtimeErrors[selectedRuntime] = "Dashboard URL is invalid."
            return
        }

        broker = RuntimeSessionBrokerClient()
        resolver = RuntimeURLResolver(runtimeBaseDomain: runtimeBaseDomain, dashboardBaseURL: dashboardBaseURL)
        webViews.reset()
        runtimeURLs.removeAll()
        runtimeErrors.removeAll()
        webViewRefreshToken = UUID()
    }

    private func saveAuthenticatedSession(_ newSession: DesktopSession) throws {
        try keychain.save(newSession)
        session = newSession
        runtimeErrors.removeAll()
        webViews.reset()
        runtimeURLs.removeAll()
        webViewRefreshToken = UUID()
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
        for webView in webViews.values {
            webView.stopLoading()
            webView.loadHTMLString("", baseURL: nil)
        }
        webViews.removeAll()
    }
}

final class DesktopAuthCoordinator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var authSession: ASWebAuthenticationSession?
    private let dashboardBaseURL: URL

    init(dashboardBaseURL: URL) {
        self.dashboardBaseURL = dashboardBaseURL
    }

    func signIn() async throws -> DesktopSession {
        var components = URLComponents(url: dashboardBaseURL.appendingPathComponent("desktop-auth"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "desktop_app", value: "1")]
        let authURL = components.url!

        return try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(
                url: authURL,
                callbackURLScheme: "evaos"
            ) { callbackURL, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }

                guard let callbackURL else {
                    continuation.resume(throwing: RuntimeSessionBrokerError.invalidResponse)
                    return
                }

                do {
                    continuation.resume(returning: try DesktopSessionCallbackParser.parse(callbackURL))
                } catch {
                    continuation.resume(throwing: RuntimeSessionBrokerError.invalidResponse)
                }
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
    private static let allowedCommands: Set<String> = [
        "status",
        "capabilities",
        "audit-tail"
    ]

    func run(arguments: [String]) async -> String {
        await Task.detached {
            guard
                let command = arguments.first,
                Self.allowedCommands.contains(command)
            else {
                return "Blocked unsupported bridge command."
            }
            guard let bridgeURL = Self.resolveBridgeExecutable() else {
                return "evaos-desktop-bridge was not found at /opt/homebrew/bin/evaos-desktop-bridge or /usr/local/bin/evaos-desktop-bridge. Install the bridge CLI before refreshing local status."
            }

            let process = Process()
            process.executableURL = bridgeURL
            process.arguments = arguments

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

    private static func resolveBridgeExecutable() -> URL? {
        let paths = [
            "/opt/homebrew/bin/evaos-desktop-bridge",
            "/usr/local/bin/evaos-desktop-bridge"
        ]
        for path in paths where FileManager.default.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        return nil
    }
}
