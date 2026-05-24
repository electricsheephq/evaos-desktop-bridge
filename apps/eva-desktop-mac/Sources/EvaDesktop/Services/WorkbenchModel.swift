import AuthenticationServices
import AppKit
import ApplicationServices
import CoreGraphics
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
            providerProfiles = WorkbenchProviderCatalog.defaultStates
            providerHubStatusText = "Unchecked"
            sharedBrowserStatusText = "Unchecked"
            webViewRefreshToken = UUID()
        }
    }
    @Published var updateManifestURLString: String = UserDefaults.standard.string(forKey: "EvaDesktop.updateManifestURL") ?? AppBrand.defaultUpdateManifestURL {
        didSet {
            UserDefaults.standard.set(updateManifestURLString, forKey: "EvaDesktop.updateManifestURL")
        }
    }
    @Published var selectedRuntime: RuntimeKey = .openclaw
    @Published var runtimeNavigationRequest: RuntimeNavigationRequest?
    @Published var session: DesktopSession?
    @Published var isSigningIn = false
    @Published var deviceCodeInput = ""
    @Published var deviceCodeStatusText = "If the browser keeps spinning, press Sign In again, wait a few seconds, then press Use Code with the prefilled fallback code."
    @Published var isClaimingDeviceCode = false
    @Published var loadingRuntimes: Set<RuntimeKey> = []
    @Published var loadingRuntimePages: Set<RuntimeKey> = []
    @Published var runtimeURLs: [RuntimeKey: URL] = [:]
    @Published var runtimeErrors: [RuntimeKey: String] = [:]
    @Published var bridgeStatusText = "Bridge status has not been checked yet."
    @Published var customerMacStatusText = "Customer Mac connector status has not been checked yet."
    @Published var iPhoneMirroringStatusText = "iPhone Mirroring status has not been checked yet."
    @Published var controlSessionText = "Agent control session has not been checked yet."
    @Published var screenSharingStatusText = "Screen Sharing status has not been checked yet."
    @Published var codexRemoteControlStatusText = "Codex remote-control readiness has not been checked yet."
    @Published var bridgeCapabilitiesText = "Bridge capabilities have not been checked yet."
    @Published var customerMacCapabilitiesText = "Customer Mac capabilities have not been checked yet."
    @Published var bridgeAuditText = "Bridge audit trail has not been checked yet."
    @Published var connectorServiceText = "Connector service status has not been checked yet."
    @Published var pairingText = "Link this Mac to let Eva use approved Mac and iPhone actions."
    @Published var agentAccessTestText = "Check setup when Mac Access is on and permissions are approved."
    @Published var pairedDevices: [CustomerMacDevice] = []
    @Published var enrollmentCode: String?
    @Published var enrollmentExpiresAt: Date?
    @Published var isPairingMac = false
    @Published var customerTargets: [DesktopCustomerTarget] = []
    @Published var sessionRoles: [String] = []
    @Published var isOperatorSession = false
    @Published var isLoadingCustomerTargets = false
    @Published var customerTargetError: String?
    @Published var isRefreshingBridgeStatus = false
    @Published var webViewRefreshToken = UUID()
    @Published var isCheckingForUpdates = false
    @Published var updateStatusText = "Workbench checks for updates automatically."
    @Published var updateAvailable = false
    @Published var updateDownloadURL: URL?
    @Published var updateReleaseNotesURL: URL?
    @Published var providerProfiles: [WorkbenchProviderProfileState] = WorkbenchProviderCatalog.defaultStates
    @Published var providerHubStatusText = "Unchecked"
    @Published var providerActionInFlight: WorkbenchProviderKey?
    @Published var sharedBrowserStatusText = "Unchecked"
    @Published var sharedBrowserRoomText = "Not opened"
    @Published var sharedBrowserCurrentURLText = "Unavailable"
    @Published var sharedBrowserLastActivityText = "Not checked"
    @Published var isRefreshingSharedBrowserStatus = false
    @Published var runtimeStatuses: [RuntimeKey: RuntimeStatusResponse] = [:]
    @Published var sessionCenterStatusText = "Unchecked"
    @Published var isRefreshingSessionCenter = false
    let featureFlags: WorkbenchFeatureFlags

    let webViews = WebViewStore()

    private let keychain = KeychainSessionStore()
    private var broker: RuntimeSessionBrokerClient
    private var resolver: RuntimeURLResolver
    private let bridge = BridgeCommandService()
    private let macControl = CustomerMacControlClient()
    private let updateClient = WorkbenchUpdateClient()
    private let connectorProcess = WorkbenchConnectorProcessManager()
    private var fallbackReloadAttempts: [RuntimeKey: Int] = [:]
    private let connectorRefreshBuildKey = "EvaDesktop.lastConnectorRefreshAppBuild"

    init() {
        let dashboardBaseURL = URL(string: UserDefaults.standard.string(forKey: "EvaDesktop.dashboardBaseURL") ?? "https://www.electricsheephq.com")
            ?? URL(string: "https://www.electricsheephq.com")!
        let runtimeBaseDomain = UserDefaults.standard.string(forKey: "EvaDesktop.runtimeBaseDomain") ?? "ecs.electricsheephq.com"
        featureFlags = WorkbenchFeatureFlags(userDefaults: .standard)
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

    var canAccessAdminRuntimes: Bool {
        guard isSignedIn else { return false }
        let normalizedRoles = Set(sessionRoles.map { $0.lowercased() })
        if isOperatorSession && (normalizedRoles.contains("admin") || normalizedRoles.contains("customer_service") || normalizedRoles.contains("support")) {
            return true
        }
        let email = session?.userEmail?.lowercased() ?? ""
        return email == "admin@100yen.org"
    }

    var visibleRuntimes: [RuntimeDefinition] {
        RuntimeDefinition
            .visibleRuntimes(canAccessAdminRuntimes: canAccessAdminRuntimes)
            .filter { definition in
                definition.key != .creativeStudio || featureFlags.isEnabled(.creativeStudio)
            }
    }

    var loadedRuntimeKeys: [RuntimeKey] {
        RuntimeDefinition.all.map(\.key).filter { runtimeURLs[$0] != nil }
    }

    var sanitizedCustomerId: String {
        resolver.sanitizedCustomerId(customerId)
    }

    var isSignedIn: Bool {
        guard let session else { return false }
        return !session.isExpired
    }

    var canSwitchCustomers: Bool {
        canAccessAdminRuntimes && !customerTargets.isEmpty
    }

    var currentCustomerTarget: DesktopCustomerTarget? {
        let current = sanitizedCustomerId
        return customerTargets.first { resolver.sanitizedCustomerId($0.customerId) == current }
    }

    func isRuntimeAvailable(_ runtime: RuntimeKey) -> Bool {
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
        await refreshConnectorServiceAfterAppUpdateIfNeeded()
        await refreshCustomerTargets()
        await refreshFlaggedOSShellState()
        await loadRuntime(selectedRuntime)
        await checkForUpdates(silent: true)
    }

    func reconnectSelectedRuntime() {
        fallbackReloadAttempts[selectedRuntime] = nil
        loadSelectedRuntime(force: true)
    }

    func loadRuntime(_ runtime: RuntimeKey, force: Bool = false) async {
        let targetCustomerId = resolver.sanitizedCustomerId(customerId)

        guard isSignedIn else {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = nil
            return
        }

        guard canAccess(runtime) else {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = "This gateway is available to ElectricSheep admins only."
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

        guard RuntimeDefinition.isBrokeredRuntime(runtime), isSignedIn else { return }
        guard canAccess(runtime) else {
            runtimeErrors[runtime] = "This gateway is available to ElectricSheep admins only."
            return
        }
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
        let fallbackCode = UUID().uuidString
        deviceCodeInput = fallbackCode
        deviceCodeStatusText = "Opening ElectricSheep login. If the browser stays on the spinner, wait a few seconds and press Use Code."

        Task {
            let coordinator = DesktopAuthCoordinator(dashboardBaseURL: resolver.dashboardBaseURL)
            defer { isSigningIn = false }

            do {
                let newSession = try await coordinator.signIn(fallbackCode: fallbackCode)
                try saveAuthenticatedSession(newSession)
                await refreshCustomerTargets()
                await refreshFlaggedOSShellState()
                await loadRuntime(selectedRuntime, force: true)
            } catch {
                deviceCodeStatusText = "Login did not complete. If the browser is still open, wait a few seconds and press Use Code."
                runtimeErrors[selectedRuntime] = "Desktop sign-in failed or was cancelled: \(error.localizedDescription)"
            }
        }
    }

    func claimDeviceCode() {
        let normalizedCode = deviceCodeInput
            .uppercased()
            .filter { $0.isLetter || $0.isNumber }
        guard !normalizedCode.isEmpty else {
            deviceCodeStatusText = "Enter the Backup code from the browser page."
            return
        }
        guard !isClaimingDeviceCode else { return }

        isClaimingDeviceCode = true
        deviceCodeStatusText = "Checking code..."

        Task { @MainActor in
            defer { isClaimingDeviceCode = false }
            do {
                let newSession = try await broker.claimDeviceCode(normalizedCode)
                try saveAuthenticatedSession(newSession)
                deviceCodeInput = ""
                deviceCodeStatusText = "Signed in."
                await refreshCustomerTargets()
                await refreshFlaggedOSShellState()
                await loadRuntime(selectedRuntime, force: true)
            } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
                deviceCodeStatusText = "That code expired or was already used. Generate a new Backup code from the login page."
            } catch {
                deviceCodeStatusText = "Code sign-in failed: \(error.localizedDescription)"
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
                await refreshFlaggedOSShellState()
                await loadRuntime(selectedRuntime, force: true)
            }
        } catch {
            runtimeErrors[selectedRuntime] = "Desktop sign-in callback failed: \(error.localizedDescription)"
        }
    }

    func refreshCustomerTargets() async {
        guard isSignedIn else {
            customerTargets = []
            sessionRoles = []
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
            sessionRoles = response.roles
            isOperatorSession = response.isOperator
            applyDefaultCustomerIfNeeded(response)
            ensureSelectedRuntimeIsVisible()
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
        Task {
            await refreshFlaggedOSShellState()
        }
    }

    func resetCustomerTargetToDefault() {
        if let defaultTarget = customerTargets.first(where: { $0.isDefault })
            ?? customerTargets.first(where: { resolver.sanitizedCustomerId($0.customerId) == "golden" }) {
            switchCustomer(to: defaultTarget)
            return
        }

        guard canAccessAdminRuntimes, sanitizedCustomerId != "golden" else { return }
        customerId = "golden"
        loadSelectedRuntime(force: true)
        Task {
            await refreshFlaggedOSShellState()
        }
    }

    func refreshFlaggedOSShellState() async {
        if featureFlags.isEnabled(.providersHub) {
            await refreshProviderProfiles()
        }
        if featureFlags.isEnabled(.sessionCenter) {
            await refreshSessionCenterState()
        }
    }

    func refreshProviderProfiles() async {
        guard isSignedIn else {
            providerProfiles = WorkbenchProviderCatalog.defaultStates
            providerHubStatusText = "Sign in to connect providers."
            return
        }
        providerHubStatusText = "Refreshing..."
        do {
            let response = try await broker.providerProfiles(customerId: sanitizedCustomerId, desktopSession: session)
            let visibleProfiles = visibleProviderProfiles(response.profiles)
            providerProfiles = visibleProfiles
            providerHubStatusText = WorkbenchProviderHubSummary.statusText(
                rawSecretsStoredInWorkbench: response.rawSecretsStoredInWorkbench,
                profiles: visibleProfiles
            )
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
            clearLocalSessionState(allowKeychainInteraction: false)
            providerHubStatusText = "Session expired. Sign in again."
        } catch {
            providerProfiles = WorkbenchProviderCatalog.defaultStates
            providerHubStatusText = "Unavailable: \(error.localizedDescription)"
        }
    }

    func connectProvider(_ providerKey: WorkbenchProviderKey) {
        guard isSignedIn else {
            providerHubStatusText = "Sign in before connecting provider access."
            return
        }
        guard providerActionInFlight == nil else { return }
        providerActionInFlight = providerKey
        providerHubStatusText = "Opening provider login in Workbench..."

        Task { @MainActor in
            defer { providerActionInFlight = nil }
            do {
                let response = try await broker.connectProvider(
                    providerKey,
                    customerId: sanitizedCustomerId,
                    desktopSession: session
                )
                providerProfiles = visibleProviderProfiles(response.profiles)
                let runtime = openProviderAuthHandoff(response.connectURL)
                let runtimeTitle = RuntimeDefinition.definition(for: runtime).title
                let fallbackInstruction = "\(runtimeTitle) opened inside Workbench. Complete the Codex sign-in there, then return to Providers and refresh."
                providerHubStatusText = providerAuthInstruction(
                    response.instructions,
                    runtimeTitle: runtimeTitle,
                    fallback: fallbackInstruction
                )
            } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
                clearLocalSessionState(allowKeychainInteraction: false)
                providerHubStatusText = "Session expired. Sign in again."
            } catch {
                providerHubStatusText = "Provider auth failed to start: \(error.localizedDescription)"
            }
        }
    }

    private func openProviderAuthHandoff(_ url: URL) -> RuntimeKey {
        let runtime = RuntimeDefinition.providerAuthRuntime(for: url)
        let targetCustomerId = resolver.sanitizedCustomerId(customerId)
        selectedRuntime = runtime
        runtimeNavigationRequest = RuntimeNavigationRequest(runtime: runtime)
        runtimeErrors[runtime] = nil
        runtimeURLs[runtime] = url
        webViews.webView(for: runtime, customerId: targetCustomerId).load(URLRequest(url: url))
        return runtime
    }

    private func providerAuthInstruction(_ instructions: String?, runtimeTitle: String, fallback: String) -> String {
        guard var copy = instructions, !copy.isEmpty else {
            return fallback
        }
        copy = copy.replacingOccurrences(of: "OpenClaw will open.", with: "\(runtimeTitle) opened inside Workbench.")
        copy = copy.replacingOccurrences(of: "OpenClaw will open", with: "\(runtimeTitle) opened inside Workbench")
        copy = copy.replacingOccurrences(of: "OpenClaw auth handoff started.", with: "\(runtimeTitle) auth handoff opened inside Workbench.")
        return copy
    }

    func switchProvider(_ providerKey: WorkbenchProviderKey) {
        runProviderAction(providerKey, statusPrefix: "Switching") {
            try await self.broker.switchProvider(providerKey, customerId: self.sanitizedCustomerId, desktopSession: self.session)
        }
    }

    func revokeProvider(_ providerKey: WorkbenchProviderKey) {
        runProviderAction(providerKey, statusPrefix: "Revoking") {
            try await self.broker.revokeProvider(providerKey, customerId: self.sanitizedCustomerId, desktopSession: self.session)
        }
    }

    func mintOpenClawProviderGrant(_ providerKey: WorkbenchProviderKey) {
        runProviderAction(providerKey, statusPrefix: "Preparing OpenClaw grant") {
            try await self.broker.mintProviderGrant(
                providerKey,
                agentRuntime: "openclaw",
                customerId: self.sanitizedCustomerId,
                desktopSession: self.session
            )
        }
    }

    private func runProviderAction(
        _ providerKey: WorkbenchProviderKey,
        statusPrefix: String,
        action: @escaping () async throws -> WorkbenchProviderProfilesResponse
    ) {
        guard isSignedIn else {
            providerHubStatusText = "Sign in before changing provider access."
            return
        }
        guard providerActionInFlight == nil else { return }
        providerActionInFlight = providerKey
        providerHubStatusText = "\(statusPrefix)..."

        Task { @MainActor in
            defer { providerActionInFlight = nil }
            do {
                let response = try await action()
                let visibleProfiles = visibleProviderProfiles(response.profiles)
                providerProfiles = visibleProfiles
                providerHubStatusText = WorkbenchProviderHubSummary.statusText(
                    rawSecretsStoredInWorkbench: response.rawSecretsStoredInWorkbench,
                    profiles: visibleProfiles
                )
            } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
                clearLocalSessionState(allowKeychainInteraction: false)
                providerHubStatusText = "Session expired. Sign in again."
            } catch {
                providerHubStatusText = "Provider update failed: \(error.localizedDescription)"
            }
        }
    }

    private func visibleProviderProfiles(_ profiles: [WorkbenchProviderProfileState]) -> [WorkbenchProviderProfileState] {
        let visible = profiles.filter { $0.key == .openAICodex }
        return visible.isEmpty ? WorkbenchProviderCatalog.defaultStates : visible
    }

    func refreshSharedBrowserStatus() async {
        guard isSignedIn else {
            sharedBrowserStatusText = "Sign in first"
            sharedBrowserRoomText = "Unavailable"
            sharedBrowserCurrentURLText = "Unavailable"
            sharedBrowserLastActivityText = "Not checked"
            return
        }
        guard !isRefreshingSharedBrowserStatus else { return }
        isRefreshingSharedBrowserStatus = true
        defer { isRefreshingSharedBrowserStatus = false }
        do {
            let status = try await broker.runtimeStatus(
                customerId: sanitizedCustomerId,
                runtime: .liveBrowser,
                desktopSession: session
            )
            sharedBrowserStatusText = Self.shortRuntimeStatus(status.status)
            sharedBrowserRoomText = status.roomId ?? status.displayLabel
            sharedBrowserCurrentURLText = Self.safeURLSummary(status.currentUrl)
            sharedBrowserLastActivityText = Self.activitySummary(status.lastActivityAt ?? status.lastCheckedAt)
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
            clearLocalSessionState(allowKeychainInteraction: false)
            sharedBrowserStatusText = "Session expired"
        } catch {
            sharedBrowserStatusText = "Unavailable"
            sharedBrowserRoomText = "Status unavailable"
            sharedBrowserCurrentURLText = "Unavailable"
            sharedBrowserLastActivityText = error.localizedDescription
        }
    }

    func refreshSessionCenterState() async {
        guard isSignedIn else {
            runtimeStatuses.removeAll()
            sessionCenterStatusText = "Sign in first"
            return
        }
        guard !isRefreshingSessionCenter else { return }
        isRefreshingSessionCenter = true
        sessionCenterStatusText = "Refreshing..."
        defer { isRefreshingSessionCenter = false }

        var nextStatuses: [RuntimeKey: RuntimeStatusResponse] = [:]
        var failures = 0
        for definition in visibleRuntimes where RuntimeDefinition.isBrokeredRuntime(definition.key) {
            do {
                let status = try await broker.runtimeStatus(
                    customerId: sanitizedCustomerId,
                    runtime: definition.key,
                    desktopSession: session
                )
                nextStatuses[definition.key] = status
                if definition.key == .liveBrowser {
                    sharedBrowserStatusText = Self.shortRuntimeStatus(status.status)
                    sharedBrowserRoomText = status.roomId ?? status.displayLabel
                    sharedBrowserCurrentURLText = Self.safeURLSummary(status.currentUrl)
                    sharedBrowserLastActivityText = Self.activitySummary(status.lastActivityAt ?? status.lastCheckedAt)
                }
            } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
                clearLocalSessionState(allowKeychainInteraction: false)
                sessionCenterStatusText = "Session expired"
                return
            } catch {
                failures += 1
            }
        }
        runtimeStatuses = nextStatuses
        if nextStatuses.isEmpty && failures > 0 {
            sessionCenterStatusText = "Unavailable"
        } else if failures > 0 {
            sessionCenterStatusText = "\(nextStatuses.count) checked, \(failures) unavailable"
        } else {
            sessionCenterStatusText = "Ready"
        }
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
            let controlRaw = await bridge.run(arguments: ["customer-mac", "control", "status", "--json"])
            let screenRaw = await bridge.run(arguments: ["customer-mac", "screen-sharing", "status", "--json"])
            let codexRaw = await bridge.run(arguments: ["codex", "app-server", "remote-control-status", "--json"])
            let bridgeCapsRaw = await bridge.run(arguments: ["capabilities", "--json"])
            let macCapsRaw = await bridge.run(arguments: ["customer-mac", "capabilities", "--json"])
            let auditRaw = await bridge.run(arguments: ["audit-tail", "--json", "--limit", "12"])

            bridgeStatusText = BridgeStatusFormatter.bridge(raw: bridgeRaw)
            connectorServiceText = BridgeStatusFormatter.connector(raw: serviceRaw)
            customerMacStatusText = BridgeStatusFormatter.customerMac(raw: macRaw)
            iPhoneMirroringStatusText = BridgeStatusFormatter.iPhone(raw: iphoneRaw)
            controlSessionText = BridgeStatusFormatter.controlSession(raw: controlRaw)
            screenSharingStatusText = BridgeStatusFormatter.screenSharing(raw: screenRaw)
            codexRemoteControlStatusText = BridgeStatusFormatter.codex(raw: codexRaw)
            bridgeCapabilitiesText = BridgeStatusFormatter.capabilities(raw: bridgeCapsRaw, title: "Bridge")
            customerMacCapabilitiesText = BridgeStatusFormatter.capabilities(raw: macCapsRaw, title: "Agent tools")
            bridgeAuditText = BridgeStatusFormatter.audit(raw: auditRaw)
            await refreshMacPairing()
        }
    }

    func checkForUpdates(silent: Bool = false) async {
        guard !isCheckingForUpdates else { return }
        let configuredManifest = UserDefaults.standard.string(forKey: "EvaDesktop.updateManifestURL") ?? updateManifestURLString
        updateManifestURLString = configuredManifest
        guard let manifestURL = URL(string: configuredManifest.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            updateAvailable = false
            updateDownloadURL = nil
            updateReleaseNotesURL = nil
            if !silent {
                updateStatusText = WorkbenchUpdateError.invalidManifestURL.localizedDescription
            }
            return
        }

        isCheckingForUpdates = true
        if !silent {
            updateStatusText = "Checking for the latest Workbench build..."
        }
        defer { isCheckingForUpdates = false }

        do {
            let manifest = try await updateClient.fetchManifest(from: manifestURL)
            updateAvailable = manifest.isNewerThan(currentVersion: AppBrand.version, currentBuild: AppBrand.buildNumber)
            updateDownloadURL = manifest.downloadURL
            updateReleaseNotesURL = manifest.releaseNotesURL
            if updateAvailable {
                updateStatusText = "Update \(manifest.displayName) is available."
            } else if !silent {
                updateStatusText = "Workbench is up to date."
            }
        } catch {
            updateAvailable = false
            updateDownloadURL = nil
            updateReleaseNotesURL = nil
            if !silent {
                updateStatusText = "Update check failed: \(error.localizedDescription)"
            }
        }
    }

    func checkForUpdatesFromButton() {
        updateStatusText = "Opening the Workbench updater..."
        SparkleUpdateService.shared.checkForUpdates()
        Task { @MainActor in
            await checkForUpdates(silent: false)
        }
    }

    func openUpdateDownload() {
        guard let updateDownloadURL else {
            updateStatusText = "Opening the Workbench updater..."
            SparkleUpdateService.shared.checkForUpdates()
            return
        }
        NSWorkspace.shared.open(updateDownloadURL)
    }

    func openUpdateReleaseNotes() {
        guard let updateReleaseNotesURL else { return }
        NSWorkspace.shared.open(updateReleaseNotesURL)
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

    private func refreshConnectorServiceAfterAppUpdateIfNeeded() async {
        let currentBuild = "\(AppBrand.version)-\(AppBrand.buildNumber)"
        guard UserDefaults.standard.string(forKey: connectorRefreshBuildKey) != currentBuild else {
            return
        }

        let initialStatusRaw = await bridge.run(arguments: ["connector-service", "status", "--json"])
        guard Self.connectorServiceIsRunning(statusText: initialStatusRaw) else {
            UserDefaults.standard.set(currentBuild, forKey: connectorRefreshBuildKey)
            connectorServiceText = BridgeStatusFormatter.connector(raw: initialStatusRaw)
            return
        }

        connectorServiceText = "Refreshing Mac Access for this Workbench update..."
        _ = await bridge.run(arguments: ["connector-service", "stop", "--json"])
        try? await Task.sleep(nanoseconds: 800_000_000)
        _ = await bridge.run(arguments: ["connector-service", "start", "--json"])
        try? await Task.sleep(nanoseconds: 800_000_000)

        let refreshedStatusRaw = await bridge.run(arguments: ["connector-service", "status", "--json"])
        connectorServiceText = BridgeStatusFormatter.connector(raw: refreshedStatusRaw)
        UserDefaults.standard.set(currentBuild, forKey: connectorRefreshBuildKey)
    }

    func startFullAccessControl() {
        startAgentControl(mode: "full-access")
    }

    func startAskPermissionControl() {
        startAgentControl(mode: "ask-permission")
    }

    func stopAgentControl() {
        Task { @MainActor in
            let raw = await bridge.run(arguments: ["customer-mac", "control", "stop", "--json"])
            controlSessionText = BridgeStatusFormatter.controlSession(raw: raw)
            refreshBridgeStatus()
        }
    }

    func killAgentControl() {
        Task { @MainActor in
            let raw = await bridge.run(arguments: ["customer-mac", "control", "kill-switch", "--json"])
            controlSessionText = BridgeStatusFormatter.controlSession(raw: raw)
            refreshBridgeStatus()
        }
    }

    private func startAgentControl(mode: String) {
        Task { @MainActor in
            let label = session?.userEmail ?? "Eva agent"
            let raw = await bridge.run(arguments: ["customer-mac", "control", "start", "--json", "--mode", mode, "--agent-label", label])
            controlSessionText = BridgeStatusFormatter.controlSession(raw: raw)
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
                var nextPairingText = "Pairing code \(response.enrollmentCode) is ready. Use it after Mac Access is on and the secure network link is connected."
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

    func copyAgentPairingPrompt() {
        guard let enrollmentCode, !enrollmentCode.isEmpty else {
            pairingText = "Create a pairing code before copying the agent prompt."
            return
        }

        Task { @MainActor in
            let service = await bridge.run(arguments: ["connector-service", "status", "--json"])
            connectorServiceText = BridgeStatusFormatter.connector(raw: service)
            do {
                let connector = try Self.localConnectorEnrollmentContext(from: service)
                let prompt = Self.agentPairingPrompt(
                    enrollmentCode: enrollmentCode,
                    connectorUrl: connector.connectorUrl,
                    customerId: sanitizedCustomerId
                )
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(prompt, forType: .string)
                pairingText = "Agent setup prompt copied. Paste it into your Eva or OpenClaw agent so it can complete the link."
            } catch {
                pairingText = "Prompt unavailable: \(error.localizedDescription)"
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
                        "desktop_control": "full_access_or_ask_permission",
                        "iphone_mirroring": "visible_control_surface"
                    ],
                    permissionState: [
                        "accessibility": "check_required",
                        "screen_recording": "check_required"
                    ]
                )
                self.enrollmentCode = nil
                self.enrollmentExpiresAt = nil
                pairingText = "This Mac is linked. Refresh status, then run Check Setup."
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
                pairingText = "Mac access disconnected. Eva can no longer use this connector grant."
                await refreshMacPairing()
            } catch {
                pairingText = "Revoke failed: \(error.localizedDescription)"
            }
        }
    }

    func testAgentAccess() {
        Task { @MainActor in
            agentAccessTestText = "Checking Mac Access, permissions, and iPhone readiness..."
            let service = await bridge.run(arguments: ["connector-service", "status", "--json"])
            let localStatus = await bridge.run(arguments: ["customer-mac", "status", "--json"])
            let iphone = await bridge.run(arguments: ["customer-mac", "iphone-mirroring", "status", "--json"])
            connectorServiceText = BridgeStatusFormatter.connector(raw: service)
            customerMacStatusText = BridgeStatusFormatter.customerMac(raw: localStatus)
            iPhoneMirroringStatusText = BridgeStatusFormatter.iPhone(raw: iphone)
            let connectorReady = BridgeStatusFormatter.connectorReady(raw: service)
            let macReady = BridgeStatusFormatter.customerMacReady(raw: localStatus)
            let iphoneReady = BridgeStatusFormatter.iPhoneReady(raw: iphone)
            agentAccessTestText = WorkbenchSetupCheckSummary.agentAccessText(
                connectorReady: connectorReady,
                macReady: macReady,
                iPhoneReady: iphoneReady
            )
        }
    }

    func stopManagedConnectorForAppTermination() {
        _ = connectorProcess.stop()
    }

    func openAccessibilitySettings() {
        requestAccessibilityPermission()
        openSystemSettings("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    }

    func openScreenRecordingSettings() {
        requestScreenRecordingPermission()
        openSystemSettings("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
    }

    func requestAccessibilityPermission() {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        _ = AXIsProcessTrustedWithOptions(options)
        Task { @MainActor in
            let raw = await bridge.run(arguments: ["permissions", "prime", "--json", "--permission", "accessibility"])
            customerMacStatusText = BridgeStatusFormatter.permissionPrimer(raw: raw, fallback: customerMacStatusText)
        }
    }

    func requestScreenRecordingPermission() {
        _ = CGRequestScreenCaptureAccess()
        Task { @MainActor in
            let raw = await bridge.run(arguments: ["permissions", "prime", "--json", "--permission", "screen-recording"])
            customerMacStatusText = BridgeStatusFormatter.permissionPrimer(raw: raw, fallback: customerMacStatusText)
        }
    }

    func openIPhoneMirroring() {
        let appURL = URL(fileURLWithPath: "/System/Applications/iPhone Mirroring.app")
        NSWorkspace.shared.open(appURL)
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
                "The secure network link is not connected yet. Connect this Mac to evaOS before completing pairing."
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

    private static func connectorServiceIsRunning(statusText: String) -> Bool {
        guard let object = connectorStatusObject(from: statusText) else {
            return false
        }

        if object["running"] as? Bool == true || object["loaded"] as? Bool == true {
            return true
        }
        if let health = object["health"] as? [String: Any], health["reachable"] as? Bool == true {
            return true
        }
        return false
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

    private static func agentPairingPrompt(enrollmentCode: String, connectorUrl: String, customerId: String) -> String {
        """
        Finish my evaOS Workbench Mac pairing.

        Customer: \(customerId)
        Pairing code: \(enrollmentCode)
        Mac connector URL: \(connectorUrl)

        From my evaOS VM, complete the pairing with the customer_mac_complete_pairing tool.
        Use exactly:
        - connector_url: \(connectorUrl)
        - enrollment_code: \(enrollmentCode)
        - customer_id: \(customerId)

        Do not ask me for a connector token. The Mac connector keeps it locally and sends it directly to evaOS.

        Success criteria:
        1. customer_mac_complete_pairing returns ok=true.
        2. customer_mac_status reports the Mac connector and permissions state.
        3. customer_mac_iphone_mirroring_status reports iPhone Mirroring readiness, even if the phone is not connected yet.
        4. desktop_control_status reports whether a Full Access or Ask Permission session is active.
        5. desktop_bridge_audit_tail shows the pairing/check evidence without secrets.

        Do not perform live Mac or iPhone actions until I start Agent Control in Workbench. If Full Access is active, use desktop_see first, then operate normally. If Ask Permission is active, ask before risky clicks, taps, hotkeys, typing, sends, and other high-impact actions.
        """
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

    private static func shortRuntimeStatus(_ value: String) -> String {
        switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "enabled":
            return "Ready"
        case "degraded":
            return "Degraded"
        case "disabled":
            return "Blocked"
        case "coming_soon":
            return "Not configured"
        default:
            return value.isEmpty ? "Unchecked" : value
        }
    }

    private static func safeURLSummary(_ value: String?) -> String {
        guard let value, let url = URL(string: value) else {
            return "Unavailable"
        }
        if let host = url.host, !host.isEmpty {
            return host + String(url.path.prefix(80))
        }
        return url.path.prefix(80).isEmpty ? "Unavailable" : String(url.path.prefix(80))
    }

    private static func activitySummary(_ date: Date?) -> String {
        guard let date else { return "Not checked" }
        return shortDateFormatter.string(from: date)
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
        sessionRoles = []
        isOperatorSession = false
        isLoadingCustomerTargets = false
        customerTargetError = nil
        pairedDevices = []
        enrollmentCode = nil
        enrollmentExpiresAt = nil
        providerProfiles = WorkbenchProviderCatalog.defaultStates
        providerHubStatusText = "Sign in to connect providers."
        providerActionInFlight = nil
        sharedBrowserStatusText = "Unchecked"
        sharedBrowserRoomText = "Unavailable"
        sharedBrowserCurrentURLText = "Unavailable"
        sharedBrowserLastActivityText = "Not checked"
        isRefreshingSharedBrowserStatus = false
        pairingText = "Sign in, start the connector, then pair this Mac with evaOS."
        deviceCodeInput = ""
        deviceCodeStatusText = "If the browser keeps spinning, press Sign In again, wait a few seconds, then press Use Code with the prefilled fallback code."
        isClaimingDeviceCode = false
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
        sessionRoles = []
        isOperatorSession = false
        customerTargetError = nil
        runtimeErrors.removeAll()
        deviceCodeInput = ""
        deviceCodeStatusText = "Signed in."
        isClaimingDeviceCode = false
        providerProfiles = WorkbenchProviderCatalog.defaultStates
        providerHubStatusText = "Unchecked"
        providerActionInFlight = nil
        sharedBrowserStatusText = "Unchecked"
        sharedBrowserRoomText = "Not opened"
        sharedBrowserCurrentURLText = "Unavailable"
        sharedBrowserLastActivityText = "Not checked"
        isRefreshingSharedBrowserStatus = false
        webViews.reset()
        loadingRuntimes.removeAll()
        loadingRuntimePages.removeAll()
        runtimeURLs.removeAll()
        fallbackReloadAttempts.removeAll()
        webViewRefreshToken = UUID()
    }

    private func handleBrokerAuthorizationFailure(_ status: Int, runtime: RuntimeKey) {
        if status == 401 {
            clearLocalSessionState(allowKeychainInteraction: false)
            runtimeErrors[runtime] = "Your evaOS Workbench session expired or was revoked. Sign in again to open gateways."
            return
        }
        runtimeURLs[runtime] = nil
        runtimeErrors[runtime] = "This account is not authorized for that gateway or customer."
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

    private func canAccess(_ runtime: RuntimeKey) -> Bool {
        let definition = RuntimeDefinition.definition(for: runtime)
        return !definition.requiresAdmin || canAccessAdminRuntimes
    }

    private func ensureSelectedRuntimeIsVisible() {
        if !canAccess(selectedRuntime) {
            selectedRuntime = .openclaw
        }
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

struct RuntimeNavigationRequest: Equatable {
    let id = UUID()
    let runtime: RuntimeKey
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

@MainActor
final class DesktopAuthCoordinator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var authSession: ASWebAuthenticationSession?
    private let dashboardBaseURL: URL

    init(dashboardBaseURL: URL) {
        self.dashboardBaseURL = dashboardBaseURL
    }

    func signIn(fallbackCode: String) async throws -> DesktopSession {
        return try await withCheckedThrowingContinuation { continuation in
            var didComplete = false
            var loopbackReceiver: DesktopAuthLoopbackReceiver?

            @MainActor
            func finish(_ result: Result<DesktopSession, Error>) {
                guard !didComplete else { return }
                didComplete = true
                loopbackReceiver?.stop()
                authSession?.cancel()
                authSession = nil
                switch result {
                case .success(let desktopSession):
                    continuation.resume(returning: desktopSession)
                case .failure(let error):
                    continuation.resume(throwing: error)
                }
            }

            loopbackReceiver = try? DesktopAuthLoopbackReceiver.start { result in
                Task { @MainActor in
                    finish(result)
                }
            }

            var components = URLComponents(url: dashboardBaseURL.appendingPathComponent("desktop-auth"), resolvingAgainstBaseURL: false)!
            components.queryItems = [
                URLQueryItem(name: "desktop_app", value: "1"),
                URLQueryItem(name: "fresh", value: fallbackCode),
                loopbackReceiver.map { URLQueryItem(name: "desktop_callback", value: $0.callbackURL.absoluteString) }
            ].compactMap { $0 }
            let authURL = components.url!

            let session = ASWebAuthenticationSession(
                url: authURL,
                callbackURLScheme: "evaos"
            ) { callbackURL, error in
                Task { @MainActor in
                    if let error {
                        finish(.failure(error))
                        return
                    }

                    guard let callbackURL else {
                        finish(.failure(RuntimeSessionBrokerError.invalidResponse))
                        return
                    }

                    do {
                        finish(.success(try DesktopSessionCallbackParser.parse(callbackURL)))
                    } catch {
                        finish(.failure(RuntimeSessionBrokerError.invalidResponse))
                    }
                }
            }

            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = true
            authSession = session
            session.start()
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        NSApplication.shared.keyWindow ?? NSApplication.shared.windows.first ?? NSWindow()
    }
}

final class DesktopAuthLoopbackReceiver {
    let callbackURL: URL

    private let socketFileDescriptor: Int32
    private let queue = DispatchQueue(label: "com.electricsheephq.EvaDesktop.auth-loopback")
    private let onComplete: (Result<DesktopSession, Error>) -> Void
    private var stopped = false

    static func start(onComplete: @escaping (Result<DesktopSession, Error>) -> Void) throws -> DesktopAuthLoopbackReceiver {
        let socketFileDescriptor = socket(AF_INET, SOCK_STREAM, 0)
        guard socketFileDescriptor >= 0 else {
            throw RuntimeSessionBrokerError.invalidResponse
        }

        var reuse: Int32 = 1
        setsockopt(socketFileDescriptor, SOL_SOCKET, SO_REUSEADDR, &reuse, socklen_t(MemoryLayout<Int32>.size))

        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = in_port_t(0).bigEndian
        address.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))

        let bindResult = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
                bind(socketFileDescriptor, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bindResult == 0, listen(socketFileDescriptor, 1) == 0 else {
            close(socketFileDescriptor)
            throw RuntimeSessionBrokerError.invalidResponse
        }

        var boundAddress = sockaddr_in()
        var boundAddressLength = socklen_t(MemoryLayout<sockaddr_in>.size)
        let nameResult = withUnsafeMutablePointer(to: &boundAddress) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
                getsockname(socketFileDescriptor, sockaddrPointer, &boundAddressLength)
            }
        }
        guard nameResult == 0 else {
            close(socketFileDescriptor)
            throw RuntimeSessionBrokerError.invalidResponse
        }

        let port = UInt16(bigEndian: boundAddress.sin_port)
        let receiver = DesktopAuthLoopbackReceiver(
            socketFileDescriptor: socketFileDescriptor,
            callbackURL: URL(string: "http://127.0.0.1:\(port)/auth/callback")!,
            onComplete: onComplete
        )
        receiver.startAccepting()
        return receiver
    }

    private init(socketFileDescriptor: Int32, callbackURL: URL, onComplete: @escaping (Result<DesktopSession, Error>) -> Void) {
        self.socketFileDescriptor = socketFileDescriptor
        self.callbackURL = callbackURL
        self.onComplete = onComplete
    }

    func stop() {
        queue.async {
            guard !self.stopped else { return }
            self.stopped = true
            close(self.socketFileDescriptor)
        }
    }

    private func startAccepting() {
        queue.async {
            guard !self.stopped else { return }
            let client = accept(self.socketFileDescriptor, nil, nil)
            guard client >= 0 else { return }
            self.handle(client)
            close(client)
        }
    }

    private func handle(_ client: Int32) {
        var buffer = [UInt8](repeating: 0, count: 8192)
        let count = recv(client, &buffer, buffer.count, 0)
        guard count > 0 else {
            writeResponse(client, status: "400 Bad Request", body: "Invalid evaOS Workbench callback.")
            onComplete(.failure(RuntimeSessionBrokerError.invalidResponse))
            return
        }

        let request = String(decoding: buffer.prefix(count), as: UTF8.self)
        guard
            let firstLine = request.split(separator: "\r\n", maxSplits: 1, omittingEmptySubsequences: false).first,
            let path = firstLine.split(separator: " ").dropFirst().first,
            let callbackURL = URL(string: "http://127.0.0.1\(path)")
        else {
            writeResponse(client, status: "400 Bad Request", body: "Invalid evaOS Workbench callback.")
            onComplete(.failure(RuntimeSessionBrokerError.invalidResponse))
            return
        }

        do {
            let desktopSession = try DesktopSessionCallbackParser.parse(callbackURL)
            writeResponse(
                client,
                status: "200 OK",
                body: "evaOS Workbench is connected. You can return to the app."
            )
            onComplete(.success(desktopSession))
        } catch {
            writeResponse(client, status: "400 Bad Request", body: "Invalid evaOS Workbench callback.")
            onComplete(.failure(error))
        }
    }

    private func writeResponse(_ client: Int32, status: String, body: String) {
        let html = """
        <!doctype html><html><head><meta charset="utf-8"><title>evaOS Workbench</title></head><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#171513;color:#f7f3ea;padding:32px;"><h1>evaOS Workbench</h1><p>\(body)</p></body></html>
        """
        let response = """
        HTTP/1.1 \(status)\r
        Content-Type: text/html; charset=utf-8\r
        Content-Length: \(html.utf8.count)\r
        Connection: close\r
        \r
        \(html)
        """
        _ = response.withCString { pointer in
            send(client, pointer, strlen(pointer), 0)
        }
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
        bridgeKey(["permissions", "prime", "--json", "--permission", "accessibility"]),
        bridgeKey(["permissions", "prime", "--json", "--permission", "screen-recording"]),
        bridgeKey(["customer-mac", "status", "--json"]),
        bridgeKey(["customer-mac", "capabilities", "--json"]),
        bridgeKey(["customer-mac", "control", "status", "--json"]),
        bridgeKey(["customer-mac", "control", "stop", "--json"]),
        bridgeKey(["customer-mac", "control", "kill-switch", "--json"]),
        bridgeKey(["customer-mac", "iphone-mirroring", "status", "--json"]),
        bridgeKey(["customer-mac", "screen-sharing", "status", "--json"]),
        bridgeKey(["codex", "app-server", "remote-control-status", "--json"])
    ]

    func run(arguments: [String]) async -> String {
        await Task.detached {
            guard Self.isAllowed(arguments) else {
                return "Blocked unsupported bridge command."
            }
            guard let bridgeURL = Self.resolveBridgeExecutable() else {
                return "evaos-desktop-bridge was not found in this app bundle, /opt/homebrew/bin, or /usr/local/bin. Reinstall evaOS Workbench before refreshing local status."
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

    private static func isAllowed(_ arguments: [String]) -> Bool {
        if allowedArgumentLists.contains(bridgeKey(arguments)) {
            return true
        }
        guard arguments.count == 8,
              arguments[0...3].elementsEqual(["customer-mac", "control", "start", "--json"]),
              arguments[4] == "--mode",
              ["full-access", "ask-permission"].contains(arguments[5]),
              arguments[6] == "--agent-label" else {
            return false
        }
        let label = arguments[7]
        return !label.isEmpty && label.count <= 80 && !label.contains(where: { $0.isNewline })
    }

    private static func resolveBridgeExecutable() -> URL? {
        if let bundled = bundledBridgeExecutable() {
            return bundled
        }
        let paths = [
            "/opt/homebrew/bin/evaos-desktop-bridge",
            "/usr/local/bin/evaos-desktop-bridge"
        ]
        for path in paths where FileManager.default.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        return nil
    }

    private static func bundledBridgeExecutable() -> URL? {
        guard let url = Bundle.main.resourceURL?
            .appendingPathComponent("Bridge", isDirectory: true)
            .appendingPathComponent("evaos-desktop-bridge"),
            FileManager.default.isExecutableFile(atPath: url.path) else {
            return nil
        }
        return url
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
            return "Starting connector on \(host):8765. Keep Workbench open while the connector is running."
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
        if let bundled = bundledBridgeExecutable() {
            return bundled
        }
        return [
            "/opt/homebrew/bin/evaos-desktop-bridge",
            "/usr/local/bin/evaos-desktop-bridge"
        ]
            .first { FileManager.default.isExecutableFile(atPath: $0) }
            .map { URL(fileURLWithPath: $0) }
    }

    private static func bundledBridgeExecutable() -> URL? {
        guard let url = Bundle.main.resourceURL?
            .appendingPathComponent("Bridge", isDirectory: true)
            .appendingPathComponent("evaos-desktop-bridge"),
            FileManager.default.isExecutableFile(atPath: url.path) else {
            return nil
        }
        return url
    }

    private static func tailnetIPv4() async -> String? {
        await Task.detached {
            if let interfaceAddress = commandOutput("/sbin/ifconfig", [])?
                .split(separator: "\n")
                .compactMap({ activeTailnetAddress(fromIfconfigLine: String($0)) })
                .first {
                return interfaceAddress
            }

            let statusCommands: [(String, [String])] = [
                ("/opt/homebrew/bin/tailscale", ["status", "--json"]),
                ("/usr/local/bin/tailscale", ["status", "--json"]),
                ("/usr/bin/env", ["tailscale", "status", "--json"])
            ]
            for command in statusCommands {
                guard let output = commandOutput(command.0, command.1),
                      let address = onlineTailnetAddress(fromStatusJSON: output) else {
                    continue
                }
                return address
            }

            let commands: [(String, [String])] = [
                ("/opt/homebrew/bin/tailscale", ["ip", "-4"]),
                ("/usr/local/bin/tailscale", ["ip", "-4"]),
                ("/usr/bin/env", ["tailscale", "ip", "-4"])
            ]
            for command in commands {
                guard let output = commandOutput(command.0, command.1) else { continue }
                if let address = output
                    .split(separator: "\n")
                    .map({ String($0.trimmingCharacters(in: .whitespacesAndNewlines)) })
                    .first(where: { looksLikeTailnetIPv4($0) }) {
                    return address
                }
            }
            return nil
        }.value
    }

    nonisolated private static func commandOutput(_ executable: String, _ arguments: [String]) -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
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
        return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)
    }

    nonisolated private static func activeTailnetAddress(fromIfconfigLine line: String) -> String? {
        let parts = line.trimmingCharacters(in: .whitespacesAndNewlines)
            .split(whereSeparator: { $0 == " " || $0 == "\t" })
            .map(String.init)
        guard parts.count >= 2, parts[0] == "inet", looksLikeTailnetIPv4(parts[1]) else {
            return nil
        }
        return parts[1]
    }

    nonisolated private static func onlineTailnetAddress(fromStatusJSON output: String) -> String? {
        guard let data = output.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["BackendState"] as? String == "Running",
              let selfNode = object["Self"] as? [String: Any],
              selfNode["Online"] as? Bool == true,
              let addresses = selfNode["TailscaleIPs"] as? [String] else {
            return nil
        }
        return addresses.first(where: looksLikeTailnetIPv4)
    }

    nonisolated private static func looksLikeTailnetIPv4(_ value: String) -> Bool {
        let parts = value.split(separator: ".")
        guard parts.count == 4, parts[0] == "100" else { return false }
        return parts.allSatisfy { part in
            guard let number = Int(part) else { return false }
            return number >= 0 && number <= 255
        }
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

    static func permissionPrimer(raw: String, fallback: String) -> String {
        guard let object = object(from: raw), object["ok"] as? Bool == true else {
            return fallback
        }
        let permission = value(at: ["data", "permission"], in: object) as? String ?? "permission"
        let status = value(at: ["data", "status"], in: object) as? String ?? "requested"
        let target = value(at: ["data", "target"], in: object) as? String
        let label = permission == "screen_recording" ? "Screen Recording" : "Accessibility"
        let suffix = target.map { " Approve \($0) if macOS shows it." } ?? ""
        if status == "granted" {
            return "\(label): Ready."
        }
        return "\(label): requested.\(suffix)"
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
        let permissionHolder = value(at: ["permission_target", "permission_holder"], in: status) as? String
        let tokenPresent = status["token_present"] as? Bool == true
        let reachable = health?["reachable"] as? Bool == true
        let mode = managedBy == "launchagent" ? "Background helper" : reachable ? "Workbench-managed connector" : "Offline"
        return compact([
            ok ? "Ready" : "Needs attention",
            "Mode: \(mode)",
            (host != nil && port != nil) ? "Address: \(host!):\(port!)" : nil,
            "Token: \(tokenPresent ? "ready" : "missing")",
            permissionTarget.map { "Permission target: \($0)" },
            permissionHolder.map { "Permission holder: \($0)" },
            permissionPath.map { "Bridge file: \($0)" },
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
        let approvedMessages = value(at: ["data", "safety", "approved_message_send_audited"], in: object) as? Bool
        return compact([
            customerMacReady(raw: raw) ? "Ready" : "Needs Permission",
            frontmost.map { "Frontmost: \($0)" },
            accessibility.map { "Accessibility: \($0)" },
            screenRecording.map { "Screen Recording: \($0)" },
            iphoneRunning.map { "iPhone Mirroring: \($0 ? "running" : "not running")" },
            approvedMessages.map { "Approved message audit: \($0 ? "ready" : "unavailable")" }
        ])
    }

    static func iPhone(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        guard object["ok"] as? Bool == true else { return errorSummary(object, fallback: "iPhone Mirroring needs attention") }
        let installed = value(at: ["data", "installed"], in: object) as? Bool
        let running = value(at: ["data", "running"], in: object) as? Bool
        let frontmost = value(at: ["data", "frontmost"], in: object) as? Bool
        let guardedActions = value(at: ["data", "guarded_actions"], in: object) as? [Any]
        return compact([
            iPhoneReady(raw: raw) ? "Ready" : "Needs iPhone Mirroring",
            installed.map { "Installed: \($0 ? "yes" : "no")" },
            running.map { "App: \($0 ? "running" : "not running")" },
            frontmost.map { "Focused: \($0 ? "yes" : "no")" },
            guardedActions.map { "Agent controls: \($0.count) visible actions" }
        ])
    }

    static func controlSession(raw: String) -> String {
        guard let object = object(from: raw) else { return cleanFallback(raw) }
        guard object["ok"] as? Bool == true else { return errorSummary(object, fallback: "Agent control needs attention") }
        let active = value(at: ["data", "active"], in: object) as? Bool
        let mode = value(at: ["data", "mode"], in: object) as? String
        let killSwitch = value(at: ["data", "kill_switch"], in: object) as? Bool
        let currentApp = value(at: ["data", "current_app"], in: object) as? String
        let peekabooAvailable = value(at: ["data", "peekaboo", "available"], in: object) as? Bool
        if killSwitch == true {
            return "Blocked. Kill switch is active."
        }
        guard active == true else {
            return compact([
                "Not active",
                currentApp.map { "Current app: \($0)" },
                peekabooAvailable.map { "Peekaboo: \($0 ? "ready" : "fallback mode")" }
            ])
        }
        return compact([
            "Ready",
            mode.map { $0 == "full_access" ? "Mode: Full Access" : "Mode: Ask Permission" },
            currentApp.map { "Current app: \($0)" },
            peekabooAvailable.map { "Peekaboo: \($0 ? "ready" : "fallback mode")" }
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
