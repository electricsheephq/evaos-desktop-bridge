import AuthenticationServices
import Darwin
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
    @Published var openDesignURLString: String = UserDefaults.standard.string(forKey: "EvaDesktop.openDesignURL") ?? "" {
        didSet {
            UserDefaults.standard.set(openDesignURLString, forKey: "EvaDesktop.openDesignURL")
            resetRuntime(.openDesign)
        }
    }
    @Published var selectedRuntime: RuntimeKey = .openclaw
    @Published var session: DesktopSession?
    @Published var isSigningIn = false
    @Published var loadingRuntimes: Set<RuntimeKey> = []
    @Published var loadingRuntimePages: Set<RuntimeKey> = []
    @Published var runtimeURLs: [RuntimeKey: URL] = [:]
    @Published var runtimeErrors: [RuntimeKey: String] = [:]
    @Published var bridgeStatusText = "Bridge status has not been checked yet."
    @Published var customerMacStatusText = "Customer Mac connector status has not been checked yet."
    @Published var iPhoneMirroringStatusText = "iPhone Mirroring status has not been checked yet."
    @Published var screenSharingStatusText = "Screen Sharing status has not been checked yet."
    @Published var bridgeCapabilitiesText = "Bridge capabilities have not been checked yet."
    @Published var customerMacCapabilitiesText = "Customer Mac capabilities have not been checked yet."
    @Published var bridgeAuditText = "Bridge audit trail has not been checked yet."
    @Published var customerTargets: [DesktopCustomerTarget] = []
    @Published var isOperatorSession = false
    @Published var isLoadingCustomerTargets = false
    @Published var customerTargetError: String?
    @Published var isRefreshingBridgeStatus = false
    @Published var webViewRefreshToken = UUID()

    let runtimes = RuntimeDefinition.all
    let webViews = WebViewStore()

    private let keychain = KeychainSessionStore()
    private var broker: RuntimeSessionBrokerClient
    private var resolver: RuntimeURLResolver
    private let bridge = BridgeCommandService()
    private var fallbackReloadAttempts: [RuntimeKey: Int] = [:]

    init() {
        let dashboardBaseURL = URL(string: UserDefaults.standard.string(forKey: "EvaDesktop.dashboardBaseURL") ?? "https://www.electricsheephq.com")
            ?? URL(string: "https://www.electricsheephq.com")!
        let runtimeBaseDomain = UserDefaults.standard.string(forKey: "EvaDesktop.runtimeBaseDomain") ?? "ecs.electricsheephq.com"
        broker = RuntimeSessionBrokerClient()
        resolver = RuntimeURLResolver(runtimeBaseDomain: runtimeBaseDomain, dashboardBaseURL: dashboardBaseURL)
        webViews.onNavigationEvent = { [weak self] runtime, event in
            Task { @MainActor in
                self?.handleRuntimeNavigationEvent(runtime, event: event)
            }
        }
        session = try? keychain.load(allowUserInteraction: false)
        if session?.isExpired == true {
            try? keychain.clear(allowUserInteraction: false)
            session = nil
        }
    }

    var selectedRuntimeDefinition: RuntimeDefinition {
        RuntimeDefinition.definition(for: selectedRuntime)
    }

    var loadedRuntimeKeys: [RuntimeKey] {
        runtimes.map(\.key).filter { runtimeURLs[$0] != nil }
    }

    var sanitizedCustomerId: String {
        resolver.sanitizedCustomerId(customerId)
    }

    var isSignedIn: Bool {
        guard let session else { return false }
        return !session.isExpired
    }

    var canSwitchCustomers: Bool {
        isSignedIn && isOperatorSession && !customerTargets.isEmpty
    }

    var currentCustomerTarget: DesktopCustomerTarget? {
        let current = sanitizedCustomerId
        return customerTargets.first { resolver.sanitizedCustomerId($0.customerId) == current }
    }

    func isRuntimeAvailable(_ runtime: RuntimeKey) -> Bool {
        if runtime == .openDesign {
            return configuredOpenDesignURL != nil
        }
        return RuntimeDefinition.definition(for: runtime).availability == .enabled
    }

    func isRuntimeLoading(_ runtime: RuntimeKey) -> Bool {
        loadingRuntimes.contains(runtime)
    }

    func isRuntimePageLoading(_ runtime: RuntimeKey) -> Bool {
        loadingRuntimePages.contains(runtime)
    }

    func loadSelectedRuntime(force: Bool = false) {
        Task {
            await loadRuntime(selectedRuntime, force: force)
        }
    }

    func bootstrap() async {
        await refreshCustomerTargets()
        await loadRuntime(selectedRuntime)
    }

    func reconnectSelectedRuntime() {
        fallbackReloadAttempts[selectedRuntime] = nil
        loadSelectedRuntime(force: true)
    }

    func loadRuntime(_ runtime: RuntimeKey, force: Bool = false) async {
        let targetCustomerId = resolver.sanitizedCustomerId(customerId)

        guard RuntimeDefinition.isBrokeredRuntime(runtime) else {
            loadConfiguredOpenDesign(targetCustomerId: targetCustomerId, force: force)
            return
        }

        guard isSignedIn else {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = nil
            return
        }

        if !force, runtimeURLs[runtime] != nil {
            return
        }

        guard !loadingRuntimes.contains(runtime) else {
            return
        }

        loadingRuntimes.insert(runtime)
        runtimeErrors[runtime] = nil
        defer {
            loadingRuntimes.remove(runtime)
        }

        do {
            let response = try await broker.launchURL(
                customerId: targetCustomerId,
                runtime: runtime,
                desktopSession: session
            )
            guard targetCustomerId == resolver.sanitizedCustomerId(customerId) else {
                return
            }
            runtimeURLs[runtime] = response.launchUrl
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 || status == 403 {
            handleBrokerAuthorizationFailure(status, runtime: runtime)
        } catch {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = "Session broker failed: \(error.localizedDescription)."
        }

        if let url = runtimeURLs[runtime] {
            webViews.webView(for: runtime, customerId: targetCustomerId).load(URLRequest(url: url))
        }
    }

    func reloadSelectedRuntime() {
        if selectedRuntime == .openDesign {
            guard runtimeURLs[selectedRuntime] != nil else {
                loadSelectedRuntime()
                return
            }
            webViews.webView(for: selectedRuntime, customerId: sanitizedCustomerId).reload()
            return
        }

        guard isSignedIn else {
            loadSelectedRuntime()
            return
        }
        guard runtimeURLs[selectedRuntime] != nil else {
            loadSelectedRuntime()
            return
        }
        let sanitized = resolver.sanitizedCustomerId(customerId)
        webViews.webView(for: selectedRuntime, customerId: sanitized).reload()
    }

    func openSelectedRuntimeExternally() {
        let runtime = selectedRuntime
        let targetCustomerId = resolver.sanitizedCustomerId(customerId)
        if runtime == .openDesign {
            if let url = runtimeURLs[runtime] ?? configuredOpenDesignURL {
                NSWorkspace.shared.open(url)
            }
            return
        }

        guard RuntimeDefinition.isBrokeredRuntime(runtime), isSignedIn else { return }
        guard !loadingRuntimes.contains(runtime) else { return }

        loadingRuntimes.insert(runtime)
        runtimeErrors[runtime] = nil
        Task { @MainActor in
            defer {
                loadingRuntimes.remove(runtime)
            }

            do {
                let response = try await broker.launchURL(
                    customerId: targetCustomerId,
                    runtime: runtime,
                    desktopSession: session
                )
                NSWorkspace.shared.open(response.launchUrl)
            } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 || status == 403 {
                handleBrokerAuthorizationFailure(status, runtime: runtime)
            } catch {
                runtimeErrors[runtime] = "External runtime launch failed: \(error.localizedDescription)."
            }
        }
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
                await refreshCustomerTargets()
                await loadRuntime(selectedRuntime, force: true)
            } catch {
                runtimeErrors[selectedRuntime] = "Desktop sign-in failed or was cancelled: \(error.localizedDescription)"
            }
        }
    }

    func signOut() {
        let sessionToRevoke = session
        clearLocalSessionState()
        Task {
            await broker.revoke(desktopSession: sessionToRevoke)
        }
    }

    func handleAuthCallback(_ url: URL) {
        do {
            let newSession = try DesktopSessionCallbackParser.parse(url)
            if session?.accessToken == newSession.accessToken {
                return
            }
            try saveAuthenticatedSession(newSession)
            Task {
                await refreshCustomerTargets()
                await loadRuntime(selectedRuntime, force: true)
            }
        } catch {
            runtimeErrors[selectedRuntime] = "Desktop sign-in callback failed: \(error.localizedDescription)"
        }
    }

    func refreshCustomerTargets() async {
        guard isSignedIn else {
            customerTargets = []
            isOperatorSession = false
            customerTargetError = nil
            return
        }
        guard !isLoadingCustomerTargets else { return }

        isLoadingCustomerTargets = true
        customerTargetError = nil
        defer { isLoadingCustomerTargets = false }

        do {
            let response = try await broker.customerTargets(desktopSession: session)
            customerTargets = response.customers
            isOperatorSession = response.isOperator
            applyDefaultCustomerIfNeeded(response)
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
            clearLocalSessionState()
            customerTargetError = "Your evaOS Workbench session expired. Sign in again."
        } catch {
            customerTargets = []
            isOperatorSession = false
            customerTargetError = "Customer list failed: \(error.localizedDescription)"
        }
    }

    func switchCustomer(to target: DesktopCustomerTarget) {
        let nextCustomerId = resolver.sanitizedCustomerId(target.customerId)
        guard nextCustomerId != sanitizedCustomerId else { return }
        customerId = nextCustomerId
        loadSelectedRuntime(force: true)
    }

    func refreshBridgeStatus() {
        guard !isRefreshingBridgeStatus else {
            return
        }
        isRefreshingBridgeStatus = true
        Task { @MainActor in
            defer { isRefreshingBridgeStatus = false }
            bridgeStatusText = await bridge.run(arguments: ["status", "--json"])
            customerMacStatusText = await bridge.run(arguments: ["customer-mac", "status", "--json"])
            iPhoneMirroringStatusText = await bridge.run(arguments: ["customer-mac", "iphone-mirroring", "status", "--json"])
            screenSharingStatusText = await bridge.run(arguments: ["customer-mac", "screen-sharing", "status", "--json"])
            bridgeCapabilitiesText = await bridge.run(arguments: ["capabilities", "--json"])
            customerMacCapabilitiesText = await bridge.run(arguments: ["customer-mac", "capabilities", "--json"])
            bridgeAuditText = await bridge.run(arguments: ["audit-tail", "--json", "--limit", "12"])
        }
    }

    func applyOpenDesignURLSetting(_ value: String) {
        openDesignURLString = value
        if selectedRuntime == .openDesign {
            loadSelectedRuntime(force: true)
        }
    }

    private var configuredOpenDesignURL: URL? {
        let configuredValue = UserDefaults.standard.string(forKey: "EvaDesktop.openDesignURL") ?? openDesignURLString
        let trimmed = configuredValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        guard let url = URL(string: trimmed), let scheme = url.scheme?.lowercased() else { return nil }
        guard ["http", "https", "file"].contains(scheme) else { return nil }
        return url
    }

    private func loadConfiguredOpenDesign(targetCustomerId: String, force: Bool) {
        guard let url = configuredOpenDesignURL else {
            runtimeURLs[.openDesign] = nil
            runtimeErrors[.openDesign] = "Configure an OpenDesign URL in Settings to enable this gateway."
            return
        }

        runtimeErrors[.openDesign] = nil
        if !force, runtimeURLs[.openDesign] == url {
            return
        }

        runtimeURLs[.openDesign] = url
        webViews.webView(for: .openDesign, customerId: targetCustomerId).load(URLRequest(url: url))
    }

    private func resetRuntime(_ runtime: RuntimeKey) {
        runtimeURLs[runtime] = nil
        runtimeErrors[runtime] = nil
        loadingRuntimes.remove(runtime)
        loadingRuntimePages.remove(runtime)
        fallbackReloadAttempts[runtime] = nil
    }

    private func rebuildClients() {
        guard let dashboardBaseURL = URL(string: dashboardBaseURLString) else {
            runtimeErrors[selectedRuntime] = "Dashboard URL is invalid."
            return
        }

        broker = RuntimeSessionBrokerClient()
        resolver = RuntimeURLResolver(runtimeBaseDomain: runtimeBaseDomain, dashboardBaseURL: dashboardBaseURL)
        webViews.reset()
        loadingRuntimes.removeAll()
        loadingRuntimePages.removeAll()
        runtimeURLs.removeAll()
        runtimeErrors.removeAll()
        fallbackReloadAttempts.removeAll()
        webViewRefreshToken = UUID()
    }

    private func clearLocalSessionState() {
        try? keychain.clear()
        session = nil
        customerTargets = []
        isOperatorSession = false
        isLoadingCustomerTargets = false
        customerTargetError = nil
        webViews.reset()
        loadingRuntimes.removeAll()
        loadingRuntimePages.removeAll()
        runtimeURLs.removeAll()
        runtimeErrors.removeAll()
        fallbackReloadAttempts.removeAll()
        webViewRefreshToken = UUID()
    }

    private func saveAuthenticatedSession(_ newSession: DesktopSession) throws {
        try keychain.save(newSession)
        session = newSession
        customerTargets = []
        isOperatorSession = false
        customerTargetError = nil
        runtimeErrors.removeAll()
        webViews.reset()
        loadingRuntimes.removeAll()
        loadingRuntimePages.removeAll()
        runtimeURLs.removeAll()
        fallbackReloadAttempts.removeAll()
        webViewRefreshToken = UUID()
    }

    private func handleBrokerAuthorizationFailure(_ status: Int, runtime: RuntimeKey) {
        clearLocalSessionState()
        runtimeErrors[runtime] = status == 401
            ? "Your evaOS Workbench session expired or was revoked. Sign in again to open gateways."
            : "This account is not authorized for that runtime or customer. Sign in with the right account or switch customer."
    }

    private func applyDefaultCustomerIfNeeded(_ response: DesktopCustomerTargetsResponse) {
        let knownCustomers = Set(response.customers.map { resolver.sanitizedCustomerId($0.customerId) })
        if knownCustomers.contains(sanitizedCustomerId) {
            return
        }
        guard let defaultCustomerId = response.defaultCustomerId ?? response.customers.first?.customerId else {
            return
        }
        customerId = resolver.sanitizedCustomerId(defaultCustomerId)
    }

    private func handleRuntimeNavigationEvent(_ runtime: RuntimeKey, event: RuntimeNavigationEvent) {
        switch event {
        case .started:
            loadingRuntimePages.insert(runtime)
            runtimeErrors[runtime] = nil
        case .finished:
            loadingRuntimePages.remove(runtime)
            fallbackReloadAttempts[runtime] = nil
        case .failed(let message):
            loadingRuntimePages.remove(runtime)
            runtimeErrors[runtime] = message
        case .httpStatus(let status, let url):
            loadingRuntimePages.remove(runtime)
            let suffix = url.map { " at \($0.absoluteString)" } ?? ""
            runtimeErrors[runtime] = "Runtime page returned HTTP \(status)\(suffix)."
        case .fallbackDetected(let label):
            loadingRuntimePages.remove(runtime)
            let attempts = fallbackReloadAttempts[runtime, default: 0]
            guard attempts < 1, isSignedIn else {
                runtimeErrors[runtime] = "\(label). Reconnect this runtime to refresh the authenticated session."
                return
            }
            fallbackReloadAttempts[runtime] = attempts + 1
            runtimeErrors[runtime] = "\(label). Reconnecting..."
            runtimeURLs[runtime] = nil
            Task {
                await loadRuntime(runtime, force: true)
            }
        }
    }
}

enum RuntimeNavigationEvent {
    case started
    case finished
    case failed(String)
    case httpStatus(Int, URL?)
    case fallbackDetected(String)
}

final class WebViewStore {
    private var webViews: [String: WKWebView] = [:]
    private var delegates: [String: RuntimeNavigationObserver] = [:]

    var onNavigationEvent: ((RuntimeKey, RuntimeNavigationEvent) -> Void)?

    func webView(for runtime: RuntimeKey, customerId: String) -> WKWebView {
        let key = "\(customerId)::\(runtime.rawValue)"
        if let webView = webViews[key] {
            return webView
        }

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.applicationNameForUserAgent = "EvaDesktop/0.1"

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.allowsBackForwardNavigationGestures = true
        let delegate = RuntimeNavigationObserver(runtime: runtime) { [weak self] runtime, event in
            self?.onNavigationEvent?(runtime, event)
        }
        webView.navigationDelegate = delegate
        delegates[key] = delegate
        webViews[key] = webView
        return webView
    }

    func reset() {
        for webView in webViews.values {
            webView.stopLoading()
            webView.loadHTMLString("", baseURL: nil)
        }
        webViews.removeAll()
        delegates.removeAll()
    }
}

final class RuntimeNavigationObserver: NSObject, WKNavigationDelegate {
    private let runtime: RuntimeKey
    private let onEvent: (RuntimeKey, RuntimeNavigationEvent) -> Void

    init(runtime: RuntimeKey, onEvent: @escaping (RuntimeKey, RuntimeNavigationEvent) -> Void) {
        self.runtime = runtime
        self.onEvent = onEvent
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        onEvent(runtime, .started)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard runtime == .openclaw else {
            onEvent(runtime, .finished)
            return
        }

        let script = """
        (() => {
          const title = String(document.title || '').toLowerCase();
          const text = String(document.body ? document.body.innerText || '' : '').toLowerCase().slice(0, 4000);
          return title.includes('gateway dashboard') ||
            text.includes('gateway dashboard') ||
            (text.includes('websocket') && text.includes('connect') && text.includes('token'));
        })()
        """

        webView.evaluateJavaScript(script) { [weak self] result, _ in
            guard let self else { return }
            if (result as? Bool) == true {
                self.onEvent(self.runtime, .fallbackDetected("OpenClaw loaded its gateway connect screen"))
            } else {
                self.onEvent(self.runtime, .finished)
            }
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        onEvent(runtime, .failed("Runtime page failed to load: \(error.localizedDescription)."))
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        onEvent(runtime, .failed("Runtime page failed to start loading: \(error.localizedDescription)."))
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        onEvent(runtime, .failed("Runtime web content stopped unexpectedly. Reconnect this runtime to continue."))
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationResponse: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        if
            let response = navigationResponse.response as? HTTPURLResponse,
            response.statusCode >= 400
        {
            onEvent(runtime, .httpStatus(response.statusCode, response.url))
        }
        decisionHandler(.allow)
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
    private static let allowedArgumentLists: Set<String> = [
        bridgeKey(["status", "--json"]),
        bridgeKey(["capabilities", "--json"]),
        bridgeKey(["audit-tail", "--json", "--limit", "12"]),
        bridgeKey(["customer-mac", "status", "--json"]),
        bridgeKey(["customer-mac", "capabilities", "--json"]),
        bridgeKey(["customer-mac", "iphone-mirroring", "status", "--json"]),
        bridgeKey(["customer-mac", "screen-sharing", "status", "--json"])
    ]

    func run(arguments: [String]) async -> String {
        await Task.detached {
            guard Self.allowedArgumentLists.contains(Self.bridgeKey(arguments)) else {
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
            } catch {
                return "Unable to run evaos-desktop-bridge: \(error.localizedDescription)"
            }

            let deadline = Date().addingTimeInterval(8)
            while process.isRunning && Date() < deadline {
                try? await Task.sleep(nanoseconds: 50_000_000)
            }

            var timedOut = false
            if process.isRunning {
                timedOut = true
                process.terminate()
                let terminateDeadline = Date().addingTimeInterval(1)
                while process.isRunning && Date() < terminateDeadline {
                    try? await Task.sleep(nanoseconds: 50_000_000)
                }
                if process.isRunning {
                    kill(process.processIdentifier, SIGKILL)
                }
            }
            process.waitUntilExit()

            let stdout = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let stderr = String(data: errorPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            if timedOut {
                let detail = stderr.isEmpty ? "" : " \(stderr.trimmingCharacters(in: .whitespacesAndNewlines))"
                return "evaos-desktop-bridge timed out after 8 seconds.\(detail)"
            }
            let output = stdout.isEmpty ? stderr : stdout
            return output.trimmingCharacters(in: .whitespacesAndNewlines)
        }.value
    }

    private static func bridgeKey(_ arguments: [String]) -> String {
        arguments.joined(separator: "\u{1f}")
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
