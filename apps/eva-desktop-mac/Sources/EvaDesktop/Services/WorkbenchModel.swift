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
    @Published var codexRemoteControlStatusText = "Codex remote-control readiness has not been checked yet."
    @Published var bridgeCapabilitiesText = "Bridge capabilities have not been checked yet."
    @Published var customerMacCapabilitiesText = "Customer Mac capabilities have not been checked yet."
    @Published var bridgeAuditText = "Bridge audit trail has not been checked yet."
    @Published var connectorServiceText = "Connector service status has not been checked yet."
    @Published var pairingText = "Pair this Mac to enable VM agents to use the audited connector tools."
    @Published var pairedDevices: [CustomerMacDevice] = []
    @Published var enrollmentCode: String?
    @Published var enrollmentExpiresAt: Date?
    @Published var isPairingMac = false
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
    private let macControl = CustomerMacControlClient()
    private let connectorProcess = WorkbenchConnectorProcessManager()
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
        clearLocalSessionState(allowKeychainInteraction: true)
        Task {
            await broker.revoke(desktopSession: sessionToRevoke)
        }
    }

    func resetLocalSession() {
        clearLocalSessionState(allowKeychainInteraction: false)
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
            clearLocalSessionState(allowKeychainInteraction: false)
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
            let bridgeRaw = await bridge.run(arguments: ["status", "--json"])
            let serviceRaw = await bridge.run(arguments: ["connector-service", "status", "--json"])
            let macRaw = await bridge.run(arguments: ["customer-mac", "status", "--json"])
            let iphoneRaw = await bridge.run(arguments: ["customer-mac", "iphone-mirroring", "status", "--json"])
            let screenRaw = await bridge.run(arguments: ["customer-mac", "screen-sharing", "status", "--json"])
            let codexRaw = await bridge.run(arguments: ["codex", "app-server", "remote-control-status", "--json"])
            let bridgeCapsRaw = await bridge.run(arguments: ["capabilities", "--json"])
            let macCapsRaw = await bridge.run(arguments: ["customer-mac", "capabilities", "--json"])
            let auditRaw = await bridge.run(arguments: ["audit-tail", "--json", "--limit", "12"])

            bridgeStatusText = BridgeStatusFormatter.bridge(raw: bridgeRaw)
            connectorServiceText = BridgeStatusFormatter.connector(raw: serviceRaw)
            customerMacStatusText = BridgeStatusFormatter.customerMac(raw: macRaw)
            iPhoneMirroringStatusText = BridgeStatusFormatter.iPhone(raw: iphoneRaw)
            screenSharingStatusText = BridgeStatusFormatter.screenSharing(raw: screenRaw)
            codexRemoteControlStatusText = BridgeStatusFormatter.codex(raw: codexRaw)
            bridgeCapabilitiesText = BridgeStatusFormatter.capabilities(raw: bridgeCapsRaw, title: "Bridge")
            customerMacCapabilitiesText = BridgeStatusFormatter.capabilities(raw: macCapsRaw, title: "Agent tools")
            bridgeAuditText = BridgeStatusFormatter.audit(raw: auditRaw)
            await refreshMacPairing()
        }
    }

    func startConnectorService() {
        Task { @MainActor in
            connectorServiceText = await connectorProcess.start()
            try? await Task.sleep(nanoseconds: 500_000_000)
            let serviceRaw = await bridge.run(arguments: ["connector-service", "status", "--json"])
            connectorServiceText = BridgeStatusFormatter.connector(raw: serviceRaw)
            refreshBridgeStatus()
        }
    }

    func stopConnectorService() {
        Task { @MainActor in
            let appManagedStop = connectorProcess.stop()
            _ = await bridge.run(arguments: ["connector-service", "stop", "--json"])
            let serviceRaw = await bridge.run(arguments: ["connector-service", "status", "--json"])
            connectorServiceText = "\(appManagedStop)\n\(BridgeStatusFormatter.connector(raw: serviceRaw))"
            refreshBridgeStatus()
        }
    }

    func createMacEnrollment() {
        guard !isPairingMac else { return }
        isPairingMac = true
        pairingText = "Creating a short-lived pairing grant..."
        Task { @MainActor in
            defer { isPairingMac = false }
            do {
                let response = try await macControl.createEnrollment(
                    desktopSession: session,
                    customerId: sanitizedCustomerId,
                    deviceName: Host.current().localizedName ?? "Customer Mac",
                    screenSharingOptIn: false
                )
                enrollmentCode = response.enrollmentCode
                enrollmentExpiresAt = response.enrollmentExpiresAt
                var nextPairingText = "Pairing code \(response.enrollmentCode) is ready. Use it after the connector is running and Tailscale/Headscale is connected."
                if let key = response.headscale?.preauthKey, !key.isEmpty {
                    nextPairingText += "\nHeadscale key: \(key)"
                } else if let mode = response.headscale?.mode {
                    nextPairingText += "\nHeadscale: \(mode)"
                }
                pairingText = nextPairingText
                await refreshMacPairing()
            } catch {
                pairingText = "Pairing failed: \(error.localizedDescription)"
            }
        }
    }

    func completeLocalMacEnrollment() {
        guard let enrollmentCode, !enrollmentCode.isEmpty, !isPairingMac else { return }
        isPairingMac = true
        pairingText = "Completing this Mac enrollment..."
        Task { @MainActor in
            defer { isPairingMac = false }
            do {
                let service = await bridge.run(arguments: ["connector-service", "status", "--json"])
                connectorServiceText = BridgeStatusFormatter.connector(raw: service)
                let connector = try Self.localConnectorEnrollmentContext(from: service)
                _ = try await macControl.completeEnrollment(
                    enrollmentCode: enrollmentCode,
                    deviceName: Host.current().localizedName ?? "Customer Mac",
                    deviceIdentifier: localDeviceIdentifier,
                    tailnetIp: connector.tailnetIp,
                    connectorUrl: connector.connectorUrl,
                    connectorToken: connector.connectorToken,
                    capabilities: [
                        "connector": "evaos-desktop-bridge",
                        "openclaw_tools": "enabled",
                        "iphone_mirroring": "named_actions"
                    ],
                    permissionState: [
                        "accessibility": "check_required",
                        "screen_recording": "check_required"
                    ]
                )
                self.enrollmentCode = nil
                self.enrollmentExpiresAt = nil
                pairingText = "This Mac is paired. Refresh status, then run Test Agent Access."
                await refreshMacPairing()
            } catch {
                pairingText = "Enrollment completion failed: \(error.localizedDescription)"
            }
        }
    }

    func revokeFirstPairedMac() {
        guard let device = pairedDevices.first, !isPairingMac else { return }
        isPairingMac = true
        pairingText = "Revoking \(device.deviceName ?? "Customer Mac")..."
        Task { @MainActor in
            defer { isPairingMac = false }
            do {
                _ = try await macControl.revoke(
                    desktopSession: session,
                    deviceId: device.id,
                    customerId: sanitizedCustomerId
                )
                pairingText = "Mac pairing revoked. VM agents can no longer use this connector grant."
                await refreshMacPairing()
            } catch {
                pairingText = "Revoke failed: \(error.localizedDescription)"
            }
        }
    }

    func testAgentAccess() {
        Task { @MainActor in
            let service = await bridge.run(arguments: ["connector-service", "status", "--json"])
            let localStatus = await bridge.run(arguments: ["customer-mac", "status", "--json"])
            let iphone = await bridge.run(arguments: ["customer-mac", "iphone-mirroring", "status", "--json"])
            connectorServiceText = BridgeStatusFormatter.connector(raw: service)
            customerMacStatusText = BridgeStatusFormatter.customerMac(raw: localStatus)
            iPhoneMirroringStatusText = BridgeStatusFormatter.iPhone(raw: iphone)
            let connectorReady = BridgeStatusFormatter.connectorReady(raw: service)
            let macReady = BridgeStatusFormatter.customerMacReady(raw: localStatus)
            let iphoneReady = BridgeStatusFormatter.iPhoneReady(raw: iphone)
            pairingText = connectorReady && macReady && iphoneReady
                ? "Test passed locally. Next proof: run support-control mac-connector smoke for \(sanitizedCustomerId)."
                : "Test failed locally. Fix the connector or macOS permissions before VM agent proof."
        }
    }

    func stopManagedConnectorForAppTermination() {
        _ = connectorProcess.stop()
    }

    func openAccessibilitySettings() {
        openSystemSettings("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    }

    func openScreenRecordingSettings() {
        openSystemSettings("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
    }

    func openIPhoneMirroring() {
        let appURL = URL(fileURLWithPath: "/System/Applications/iPhone Mirroring.app")
        NSWorkspace.shared.open(appURL)
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

    private var localDeviceIdentifier: String {
        let key = "EvaDesktop.localDeviceIdentifier"
        if let existing = UserDefaults.standard.string(forKey: key), !existing.isEmpty {
            return existing
        }
        let next = "mac-\(UUID().uuidString.lowercased())"
        UserDefaults.standard.set(next, forKey: key)
        return next
    }

    private var connectorTailnetIp: String? {
        Self.connectorStatusObject(from: connectorServiceText)?["tailnet_ip"] as? String
    }

    private struct LocalConnectorEnrollmentContext {
        let tailnetIp: String
        let connectorUrl: String
        let connectorToken: String
    }

    private enum LocalConnectorEnrollmentError: LocalizedError {
        case statusUnavailable
        case connectorNotReady
        case missingTailnetIp
        case missingTokenPath
        case missingToken

        var errorDescription: String? {
            switch self {
            case .statusUnavailable:
                "Connector status could not be read. Start the connector service, then try again."
            case .connectorNotReady:
                "The local connector is not ready. Start the connector service and confirm it is reachable first."
            case .missingTailnetIp:
                "Tailscale/Headscale is not connected yet. Connect the Mac to the evaOS tailnet before completing pairing."
            case .missingTokenPath:
                "Connector token path is missing. Restart the connector service so it can mint a local token."
            case .missingToken:
                "Connector token is missing or invalid. Restart the connector service, then try pairing again."
            }
        }
    }

    private static func connectorStatusObject(from text: String) -> [String: Any]? {
        guard let data = text.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return nil
        }
        if let status = object["status"] as? [String: Any] {
            return status
        }
        return object
    }

    private static func localConnectorEnrollmentContext(from statusText: String) throws -> LocalConnectorEnrollmentContext {
        guard let object = connectorStatusObject(from: statusText) else {
            throw LocalConnectorEnrollmentError.statusUnavailable
        }
        guard object["ok"] as? Bool == true || object["running"] as? Bool == true else {
            throw LocalConnectorEnrollmentError.connectorNotReady
        }
        guard let tailnetIp = object["tailnet_ip"] as? String, !tailnetIp.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw LocalConnectorEnrollmentError.missingTailnetIp
        }
        guard let tokenPath = object["token_path"] as? String, !tokenPath.isEmpty else {
            throw LocalConnectorEnrollmentError.missingTokenPath
        }

        let token = (try? String(contentsOfFile: tokenPath, encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard token.count >= 24,
              token.rangeOfCharacter(from: .whitespacesAndNewlines) == nil
        else {
            throw LocalConnectorEnrollmentError.missingToken
        }

        return LocalConnectorEnrollmentContext(
            tailnetIp: tailnetIp,
            connectorUrl: "http://\(tailnetIp):8765",
            connectorToken: token
        )
    }

    private func refreshMacPairing() async {
        guard isSignedIn else {
            pairedDevices = []
            return
        }
        do {
            let response = try await macControl.list(desktopSession: session)
            pairedDevices = response.devices.filter { $0.status != "revoked" }
            let audit = try await macControl.auditTail(desktopSession: session, limit: 10)
            if !audit.events.isEmpty {
                let summary = audit.events.prefix(5).map { event in
                    "\(event.createdAt.map { Self.shortDateFormatter.string(from: $0) } ?? "-") \(event.action) \(event.outcome)"
                }.joined(separator: "\n")
                bridgeAuditText = summary
            }
        } catch {
            pairedDevices = []
            pairingText = "Pairing status unavailable: \(error.localizedDescription)"
        }
    }

    private func openSystemSettings(_ urlString: String) {
        guard let url = URL(string: urlString) else { return }
        NSWorkspace.shared.open(url)
    }

    private static let shortDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .medium
        return formatter
    }()

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

    private func clearLocalSessionState(allowKeychainInteraction: Bool) {
        try? keychain.clear(allowUserInteraction: allowKeychainInteraction)
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
        clearLocalSessionState(allowKeychainInteraction: false)
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
        bridgeKey(["connector-service", "status", "--json"]),
        bridgeKey(["connector-service", "start", "--json"]),
        bridgeKey(["connector-service", "stop", "--json"]),
        bridgeKey(["customer-mac", "status", "--json"]),
        bridgeKey(["customer-mac", "capabilities", "--json"]),
        bridgeKey(["customer-mac", "iphone-mirroring", "status", "--json"]),
        bridgeKey(["customer-mac", "screen-sharing", "status", "--json"]),
        bridgeKey(["codex", "app-server", "remote-control-status", "--json"])
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

@MainActor
final class WorkbenchConnectorProcessManager {
    private var process: Process?
    private var logHandle: FileHandle?

    func start() async -> String {
        if let process, process.isRunning {
            return "Starting connector: already running from Workbench."
        }
        guard let bridgeURL = Self.resolveBridgeExecutable() else {
            return "Connector offline: install evaos-desktop-bridge before starting this Mac connector."
        }

        let host = await Self.tailnetIPv4() ?? "127.0.0.1"
        let logURL = Self.logURL()
        do {
            try FileManager.default.createDirectory(
                at: logURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            if !FileManager.default.fileExists(atPath: logURL.path) {
                FileManager.default.createFile(atPath: logURL.path, contents: nil)
            }
            let handle = try FileHandle(forWritingTo: logURL)
            try handle.seekToEnd()

            let next = Process()
            next.executableURL = bridgeURL
            next.arguments = ["serve", "--host", host, "--port", "8765"]
            var environment = ProcessInfo.processInfo.environment
            environment["EVAOS_DESKTOP_BRIDGE_MODE"] = "customer-mac-connector"
            next.environment = environment
            next.standardOutput = handle
            next.standardError = handle
            try next.run()
            process = next
            logHandle = handle
            return "Starting connector on \(host):8765. Keep Workbench open during the beta."
        } catch {
            return "Connector failed to start: \(error.localizedDescription)"
        }
    }

    func stop() -> String {
        guard let process else {
            return "Workbench-managed connector was not running."
        }
        if process.isRunning {
            process.terminate()
        }
        self.process = nil
        try? logHandle?.close()
        logHandle = nil
        return "Workbench-managed connector stopped."
    }

    deinit {
        if let process, process.isRunning {
            process.terminate()
        }
        try? logHandle?.close()
    }

    private static func resolveBridgeExecutable() -> URL? {
        [
            "/opt/homebrew/bin/evaos-desktop-bridge",
            "/usr/local/bin/evaos-desktop-bridge"
        ]
            .first { FileManager.default.isExecutableFile(atPath: $0) }
            .map { URL(fileURLWithPath: $0) }
    }

    private static func tailnetIPv4() async -> String? {
        await Task.detached {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["tailscale", "ip", "-4"]
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = Pipe()
            do {
                try process.run()
            } catch {
                return nil
            }
            process.waitUntilExit()
            guard process.terminationStatus == 0 else { return nil }
            let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            return output
                .split(separator: "\n")
                .map { String($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
                .first { $0.hasPrefix("100.") }
        }.value
    }

    private static func logURL() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return base
            .appendingPathComponent("evaos-desktop-bridge", isDirectory: true)
            .appendingPathComponent("workbench-connector.log")
    }
}

enum BridgeStatusFormatter {
    static func rawLooksOK(_ raw: String) -> Bool {
        guard let object = object(from: raw) else { return false }
        if let ok = object["ok"] as? Bool {
            return ok
        }
        if let status = object["status"] as? [String: Any], let ok = status["ok"] as? Bool {
            return ok
        }
        return false
    }

    static func connectorReady(raw: String) -> Bool {
        guard let object = object(from: raw) else { return false }
        let status = (object["status"] as? [String: Any]) ?? object
        let health = status["health"] as? [String: Any]
        return status["ok"] as? Bool == true
            && status["token_present"] as? Bool == true
            && health?["reachable"] as? Bool == true
    }

    static func customerMacReady(raw: String) -> Bool {
        guard let object = object(from: raw), object["ok"] as? Bool == true else { return false }
        let accessibility = value(at: ["data", "permissions", "accessibility", "status"], in: object) as? String
        let screenRecording = value(at: ["data", "permissions", "screen_recording", "status"], in: object) as? String
        return accessibility == "granted" && screenRecording == "granted"
    }

    static func iPhoneReady(raw: String) -> Bool {
        guard let object = object(from: raw), object["ok"] as? Bool == true else { return false }
        let installed = value(at: ["data", "installed"], in: object) as? Bool
        let running = value(at: ["data", "running"], in: object) as? Bool
        return installed == true && running == true
    }

    static func bridge(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        if object["ok"] as? Bool == true {
            let frontmost = value(at: ["data", "frontmost_app"], in: object) as? String
            return compact(["Ready", frontmost.map { "Frontmost app: \($0)" }])
        }
        return errorSummary(object, fallback: "Bridge needs attention")
    }

    static func connector(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        let status = (object["status"] as? [String: Any]) ?? object
        let ok = status["ok"] as? Bool == true
        let health = status["health"] as? [String: Any]
        let host = health?["host"] as? String
        let port = health?["port"] as? Int
        let managedBy = (status["managed_by"] as? String) ?? ((status["loaded"] as? Bool == true) ? "launchagent" : "workbench")
        let permissionTarget = value(at: ["permission_target", "name"], in: status) as? String
        let permissionPath = value(at: ["permission_target", "bridge_executable"], in: status) as? String
        let pythonPath = value(at: ["permission_target", "python_executable"], in: status) as? String
        let tokenPresent = status["token_present"] as? Bool == true
        let reachable = health?["reachable"] as? Bool == true
        let mode = managedBy == "launchagent" ? "Background helper" : reachable ? "Workbench-managed beta connector" : "Offline"
        return compact([
            ok ? "Ready" : "Needs attention",
            "Mode: \(mode)",
            (host != nil && port != nil) ? "Address: \(host!):\(port!)" : nil,
            "Token: \(tokenPresent ? "ready" : "missing")",
            permissionTarget.map { "Permission target: \($0)" },
            permissionPath.map { "Bridge file: \($0)" },
            pythonPath.map { "Python helper: \($0)" },
            ok ? nil : firstGuidance(status)
        ])
    }

    static func customerMac(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        guard object["ok"] as? Bool == true else { return errorSummary(object, fallback: "Customer Mac needs attention") }
        let frontmost = value(at: ["data", "frontmost_app"], in: object) as? String
        let accessibility = value(at: ["data", "permissions", "accessibility", "status"], in: object) as? String
        let screenRecording = value(at: ["data", "permissions", "screen_recording", "status"], in: object) as? String
        let iphoneRunning = value(at: ["data", "iphone_mirroring", "running"], in: object) as? Bool
        let supportCanary = value(at: ["data", "safety", "support_canary_controls_enabled"], in: object) as? Bool
        return compact([
            customerMacReady(raw: raw) ? "Ready" : "Needs Permission",
            frontmost.map { "Frontmost: \($0)" },
            accessibility.map { "Accessibility: \($0)" },
            screenRecording.map { "Screen Recording: \($0)" },
            iphoneRunning.map { "iPhone Mirroring: \($0 ? "running" : "not running")" },
            supportCanary.map { "Support canary controls: \($0 ? "enabled" : "disabled")" }
        ])
    }

    static func iPhone(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        guard object["ok"] as? Bool == true else { return errorSummary(object, fallback: "iPhone Mirroring needs attention") }
        let installed = value(at: ["data", "installed"], in: object) as? Bool
        let running = value(at: ["data", "running"], in: object) as? Bool
        let frontmost = value(at: ["data", "frontmost"], in: object) as? Bool
        let supportEnabled = value(at: ["data", "support_canary", "enabled"], in: object) as? Bool
        return compact([
            iPhoneReady(raw: raw) ? "Ready" : "Needs iPhone Mirroring",
            installed.map { "Installed: \($0 ? "yes" : "no")" },
            running.map { "App: \($0 ? "running" : "not running")" },
            frontmost.map { "Focused: \($0 ? "yes" : "no")" },
            supportEnabled.map { "Support-only gestures: \($0 ? "enabled" : "disabled")" }
        ])
    }

    static func screenSharing(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        guard object["ok"] as? Bool == true else { return errorSummary(object, fallback: "Screen Sharing status unavailable") }
        let enabled = value(at: ["data", "enabled"], in: object) as? Bool
        let vnc = value(at: ["data", "vnc_5900_listening"], in: object) as? Bool
        return compact([
            enabled == true ? "Available" : "Disabled",
            vnc.map { "VNC listener: \($0 ? "present" : "not present")" },
            "Status only; Workbench does not enable Screen Sharing."
        ])
    }

    static func codex(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        let ok = object["ok"] as? Bool == true
        let data = object["data"] as? [String: Any]
        let available = data?["available"] as? Bool
        let socket = data?["socket_path"] as? String
        return compact([
            ok ? "Checked" : "Needs attention",
            available.map { "Native remote-control: \($0 ? "available" : "not available")" },
            socket == nil ? nil : "Socket detected",
            ok ? nil : errorSummary(object, fallback: "Codex readiness check failed")
        ])
    }

    static func capabilities(raw: String, title: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        guard object["ok"] as? Bool == true else { return errorSummary(object, fallback: "\(title) capabilities unavailable") }
        if let actions = value(at: ["data", "actions"], in: object) as? [String: Any] {
            let groups = actions.keys.sorted().joined(separator: ", ")
            return groups.isEmpty ? "\(title): ready" : "\(title): \(groups)"
        }
        if let commands = value(at: ["data", "commands"], in: object) as? [Any] {
            return "\(title): \(commands.count) commands allowlisted"
        }
        return "\(title): ready"
    }

    static func audit(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        guard object["ok"] as? Bool == true else { return errorSummary(object, fallback: "Audit unavailable") }
        let records = value(at: ["data", "records"], in: object) as? [[String: Any]] ?? []
        guard !records.isEmpty else { return "No audit events yet." }
        return records.prefix(6).map { record in
            let command = record["command"] as? String ?? "unknown"
            let ok = record["ok"] as? Bool == true ? "ok" : "failed"
            let auditId = record["audit_id"] as? String ?? ""
            return "\(ok) \(command) \(auditId)"
        }.joined(separator: "\n")
    }

    private static func object(from raw: String) -> [String: Any]? {
        guard let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return nil
        }
        return object
    }

    private static func value(at path: [String], in object: [String: Any]) -> Any? {
        var current: Any = object
        for key in path {
            guard let dict = current as? [String: Any], let next = dict[key] else {
                return nil
            }
            current = next
        }
        return current
    }

    private static func errorSummary(_ object: [String: Any], fallback: String) -> String {
        if let errors = object["errors"] as? [[String: Any]], let first = errors.first {
            return compact([
                fallback,
                first["message"] as? String,
                first["guidance"] as? String
            ])
        }
        return compact([fallback, firstGuidance(object)])
    }

    private static func firstGuidance(_ object: [String: Any]) -> String? {
        if let guidance = object["guidance"] as? [String] {
            return guidance.first
        }
        return nil
    }

    private static func cleanFallback(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "Not checked yet."
        }
        if trimmed.lowercased().contains("usage:") || trimmed.lowercased().contains("invalid choice") {
            return "Check failed: the installed bridge CLI does not match this Workbench build."
        }
        return trimmed.count > 240 ? String(trimmed.prefix(240)) + "..." : trimmed
    }

    private static func compact(_ lines: [String?]) -> String {
        lines.compactMap { line in
            let trimmed = line?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return trimmed.isEmpty ? nil : trimmed
        }.joined(separator: "\n")
    }
}
