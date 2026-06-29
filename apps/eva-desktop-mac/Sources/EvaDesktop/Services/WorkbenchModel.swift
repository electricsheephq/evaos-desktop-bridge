import AuthenticationServices
import AppKit
import ApplicationServices
import CoreGraphics
import Darwin
import EvaDesktopCore
import Foundation
import SwiftUI
import WebKit

private enum WorkbenchAgentQAOptions {
    private static let disableKeychainDefaultKey = "EvaDesktop.disableKeychainForAgentQA"
    private static let disableKeychainEnvironmentKeys = [
        "EVAOS_WORKBENCH_DISABLE_KEYCHAIN",
        "EVA_DESKTOP_DISABLE_KEYCHAIN"
    ]
    private static let truthyValues: Set<String> = ["1", "true", "yes", "on"]

    static var disablesKeychain: Bool {
        if UserDefaults.standard.bool(forKey: disableKeychainDefaultKey) {
            return true
        }
        return disableKeychainEnvironmentKeys.contains { key in
            guard let rawValue = ProcessInfo.processInfo.environment[key] else {
                return false
            }
            return truthyValues.contains(rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
        }
    }
}

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
            sharedBrowserRoomText = "Not opened"
            sharedBrowserCurrentURLText = "Unavailable"
            sharedBrowserLastActivityText = "Not checked"
            businessBrowserStatus = nil
            isRefreshingSharedBrowserStatus = false
            isStoppingSharedBrowser = false
            loadRecentSessionRecords()
            resetSessionCenterState(statusText: "Unchecked")
            resetCapabilityManifestState(statusText: "Unchecked", clearCache: true)
            resetApprovalCenterState(statusText: "Unchecked")
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
    @Published var lastSignInURL: URL?
    @Published var deviceCodeInput = ""
    @Published var deviceCodeStatusText = "Press Sign In to open the ElectricSheep login page. Backup codes must come from the browser page."
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
    @Published var capabilityManifestSummary: WorkbenchCapabilityManifestSummary?
    @Published var capabilityManifestStatusText = "Unchecked"
    @Published var capabilityManifestAgentID = "openclaw"
    @Published var isRefreshingCapabilityManifest = false
    @Published var agentAssignments: [WorkbenchAgentAssignment] = []
    @Published var usageDashboardCards: [WorkbenchAgentUsageCard] = []
    @Published var usageDashboardStatusText = "Unchecked"
    @Published var isRefreshingUsageDashboard = false
    @Published var sharedBrowserStatusText = "Unchecked"
    @Published var sharedBrowserRoomText = "Not opened"
    @Published var sharedBrowserCurrentURLText = "Unavailable"
    @Published var sharedBrowserLastActivityText = "Not checked"
    @Published var businessBrowserStatus: WorkbenchBrowserStatus?
    @Published var isRefreshingSharedBrowserStatus = false
    @Published var isStoppingSharedBrowser = false
    @Published var runtimeStatuses: [RuntimeKey: RuntimeStatusResponse] = [:]
    @Published var sessionMissionCards: [WorkbenchMissionCard] = []
    @Published var sessionRecords: [WorkbenchSessionRecord] = []
    @Published var recentSessionRecords: [WorkbenchSessionRecord] = []
    @Published var sessionCenterStatusText = "Unchecked"
    @Published var isRefreshingSessionCenter = false
    @Published var approvalRequests: [WorkbenchApprovalRequest] = []
    @Published var approvalCenterStatusText = "Unchecked"
    @Published var isRefreshingApprovalCenter = false
    @Published var approvalDecisionInFlight: String?
    let featureFlags: WorkbenchFeatureFlags

    let webViews = WebViewStore()
    private var activeAuthCoordinator: DesktopAuthCoordinator?

    private let keychain = KeychainSessionStore()
    private let capabilityManifestStore = WorkbenchCapabilityManifestStore()
    private let keychainDisabledForAgentQA = WorkbenchAgentQAOptions.disablesKeychain
    private var broker: RuntimeSessionBrokerClient
    private var resolver: RuntimeURLResolver
    private let bridge = BridgeCommandService()
    private let macControl = CustomerMacControlClient()
    private let updateClient = WorkbenchUpdateClient()
    private let approvalNotificationService = ApprovalCenterNotificationService()
    private let connectorProcess = WorkbenchConnectorProcessManager()
    private var fallbackReloadAttempts: [RuntimeKey: Int] = [:]
    private var approvalCenterVisible = false
    private var usageDashboardVisible = false
    private var approvalCenterPollingTask: Task<Void, Never>?
    private var approvalPendingRequestIDs: Set<String> = []
    private var approvalNotifiedRequestIDs: Set<String> = []
    private var budgetNotifiedAgentIDs: Set<String> = []
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
        if !keychainDisabledForAgentQA {
            session = try? keychain.load(allowUserInteraction: false)
            if session?.isExpired == true {
                try? keychain.clear(allowUserInteraction: false)
                session = nil
            }
        }
        loadRecentSessionRecords()
    }

    var selectedRuntimeDefinition: RuntimeDefinition {
        RuntimeDefinition.definition(for: selectedRuntime)
    }

    var canAccessAdminRuntimes: Bool {
        guard isSignedIn else { return false }
        let normalizedRoles = Set(sessionRoles.map { $0.lowercased().replacingOccurrences(of: "-", with: "_") })
        if normalizedRoles.contains("owner")
            || normalizedRoles.contains("admin")
            || normalizedRoles.contains("technical_admin") {
            return true
        }
        if isOperatorSession
            && (normalizedRoles.contains("customer_service")
                || normalizedRoles.contains("support")) {
            return true
        }
        let email = session?.userEmail?.lowercased() ?? ""
        return email == "admin@100yen.org"
    }

    var currentAccountRole: WorkbenchAccountRole {
        let normalizedRoles = Set(sessionRoles.map { $0.lowercased().replacingOccurrences(of: "-", with: "_") })
        if let role = WorkbenchAccountRole.allCases.first(where: { normalizedRoles.contains($0.rawValue) }) {
            return role
        }
        return canAccessAdminRuntimes ? .technicalAdmin : .member
    }

    var currentAssignment: WorkbenchAgentAssignment? {
        agentAssignments.first
    }

    var todayItems: [WorkbenchTodayItem] {
        WorkbenchTodayItemDeriver.items(
            from: sessionRecords,
            recentRecords: recentSessionRecords
        )
    }

    var visibleRuntimes: [RuntimeDefinition] {
        RuntimeDefinition
            .visibleRuntimes(canAccessAdminRuntimes: canAccessAdminRuntimes)
            .filter { runtime in
                runtime.key != .teamChat || featureFlags.isEnabled(.teamChat)
            }
            .filter { WorkbenchAgentAssignmentAccessPolicy.canAccessRuntime($0.key, role: currentAccountRole, assignment: currentAssignment) }
    }

    var visibleWorkspaceRuntimes: [RuntimeDefinition] {
        visibleRuntimes.filter { !$0.isTechnicalDashboard }
    }

    var visibleTechnicalDashboardRuntimes: [RuntimeDefinition] {
        guard canAccessAdminRuntimes else { return [] }
        return visibleRuntimes.filter(\.isTechnicalDashboard)
    }

    func canOpenSurface(_ surface: String) -> Bool {
        let visibleSurfaces = WorkbenchAgentAssignmentAccessPolicy.visibleSurfaces(
            for: currentAccountRole,
            assignment: currentAssignment
        )
        return visibleSurfaces.contains(Self.normalizedSurface(surface))
    }

    var canOpenPeopleAccessDashboard: Bool {
        isSignedIn && canOpenSurface("members")
    }

    var canOpenCompanyBrainDashboard: Bool {
        isSignedIn && canOpenSurface("company_brain")
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

    func bootstrap(loadInitialRuntime: Bool = true) async {
        await refreshConnectorServiceAfterAppUpdateIfNeeded()
        await refreshCustomerTargets()
        await refreshFlaggedOSShellState()
        if loadInitialRuntime {
            await loadRuntime(selectedRuntime)
        } else if featureFlags.isEnabled(.sessionCenter) {
            await refreshSessionCenterState()
        }
        await checkForUpdates(silent: true)
    }

    func setApprovalCenterVisible(_ visible: Bool) {
        approvalCenterVisible = visible
        guard visible else { return }
        let currentIDs = Set(approvalRequests.map(\.id))
        approvalPendingRequestIDs = currentIDs
        approvalNotifiedRequestIDs.formUnion(currentIDs)
    }

    func setUsageDashboardVisible(_ visible: Bool) {
        usageDashboardVisible = visible
        guard visible else { return }
        budgetNotifiedAgentIDs.formUnion(
            usageDashboardCards
                .filter { $0.attentionState == .needsAttention && $0.status == "Budget paused" }
                .map(\.agentID)
        )
    }

    func startApprovalCenterPolling() {
        guard featureFlags.isEnabled(.approvalCenter), approvalCenterPollingTask == nil else {
            return
        }

        approvalCenterPollingTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                if self.isSignedIn {
                    await self.refreshApprovalCenterState()
                }
                let interval: UInt64 = self.approvalCenterVisible ? 5_000_000_000 : 15_000_000_000
                try? await Task.sleep(nanoseconds: interval)
            }
        }
    }

    func reconnectSelectedRuntime() {
        fallbackReloadAttempts[selectedRuntime] = nil
        loadSelectedRuntime(force: true)
    }

    func closeSelectedRuntimeView() {
        closeRuntimeView(selectedRuntime)
    }

    func closeRuntimeView(_ runtime: RuntimeKey) {
        let sanitized = resolver.sanitizedCustomerId(customerId)
        resetRuntime(runtime)
        webViews.reset(runtime: runtime, customerId: sanitized)
        if runtime == .liveBrowser {
            sharedBrowserStatusText = "Closed locally"
            sharedBrowserRoomText = "Detached"
            sharedBrowserCurrentURLText = "Unavailable"
            sharedBrowserLastActivityText = "Not checked"
        }
        updateSessionRecord(for: runtime, status: runtimeStatuses[runtime], error: runtimeErrors[runtime])
        webViewRefreshToken = UUID()
    }

    func stopSharedBrowserSession() async {
        let runtime = RuntimeKey.liveBrowser
        let customerSnapshot = sanitizedCustomerId
        guard isSignedIn else {
            sharedBrowserStatusText = "Sign in first"
            return
        }
        guard !isStoppingSharedBrowser else { return }
        isStoppingSharedBrowser = true
        defer { isStoppingSharedBrowser = false }
        do {
            _ = try await broker.stopSharedBrowser(
                customerId: customerSnapshot,
                desktopSession: session
            )
            guard sanitizedCustomerId == customerSnapshot else { return }
            resetRuntime(runtime)
            webViews.reset(runtime: runtime, customerId: customerSnapshot)
            runtimeStatuses[runtime] = nil
            runtimeErrors[runtime] = nil
            sharedBrowserStatusText = "Stopped"
            sharedBrowserRoomText = "Stopped at broker"
            sharedBrowserCurrentURLText = "Unavailable"
            sharedBrowserLastActivityText = "Refresh status before reopening"
            businessBrowserStatus = WorkbenchBrowserStatus(
                customerID: customerSnapshot,
                status: "stopped",
                actions: [.startAttach, .refreshStatus],
                sourcePointer: "broker:runtime_status:browser"
            )
            updateSessionRecord(for: runtime, status: nil, error: nil)
            webViewRefreshToken = UUID()
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
            guard sanitizedCustomerId == customerSnapshot else { return }
            degradeRuntimeAuthorization(
                runtime,
                message: "Account permissions unavailable. Refresh or sign out and back in if this persists."
            )
        } catch {
            guard sanitizedCustomerId == customerSnapshot else { return }
            runtimeErrors[runtime] = error.localizedDescription
            sharedBrowserStatusText = "Stop failed"
            sharedBrowserLastActivityText = error.localizedDescription
            updateSessionRecord(for: runtime, status: nil, error: error.localizedDescription)
        }
    }

    func loadRuntime(_ runtime: RuntimeKey, force: Bool = false) async {
        let targetCustomerId = resolver.sanitizedCustomerId(customerId)

        if let externalURL = RuntimeDefinition.externalURL(for: runtime) {
            runtimeURLs[runtime] = externalURL
            runtimeErrors[runtime] = nil
            recordRecentLaunch(runtime: runtime, customerId: targetCustomerId)
            webViews.webView(for: runtime, customerId: targetCustomerId).load(URLRequest(url: externalURL))
            return
        }

        guard isSignedIn else {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = nil
            return
        }

        guard canAccess(runtime) else {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = "This workspace is available to ElectricSheep admins only."
            return
        }

        if !force, runtimeURLs[runtime] != nil {
            return
        }

        guard !loadingRuntimes.contains(runtime) else {
            return
        }

        if force {
            resetRuntimeWebViewIfNeeded(runtime, customerId: targetCustomerId)
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
            recordRecentLaunch(runtime: runtime, customerId: targetCustomerId)
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 || status == 403 {
            handleBrokerAuthorizationFailure(status, runtime: runtime)
        } catch {
            runtimeURLs[runtime] = nil
            runtimeErrors[runtime] = "Workspace launch failed: \(error.localizedDescription)."
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
        if selectedRuntime == .openclaw {
            runtimeURLs[selectedRuntime] = nil
            fallbackReloadAttempts[selectedRuntime] = nil
            let sanitized = resolver.sanitizedCustomerId(customerId)
            resetRuntimeWebViewIfNeeded(selectedRuntime, customerId: sanitized)
            loadSelectedRuntime(force: true)
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

        if let externalURL = RuntimeDefinition.externalURL(for: runtime) {
            recordRecentLaunch(runtime: runtime, customerId: targetCustomerId)
            NSWorkspace.shared.open(externalURL)
            return
        }

        guard RuntimeDefinition.isBrokeredRuntime(runtime), isSignedIn else { return }
        guard canAccess(runtime) else {
            runtimeErrors[runtime] = "This workspace is available to ElectricSheep admins only."
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
                runtimeErrors[runtime] = "Workspace launch failed: \(error.localizedDescription)."
            }
        }
    }

    func refreshSelectedRuntimeStatus() async {
        await refreshRuntimeStatus(selectedRuntime)
    }

    func signIn() {
        guard !isSigningIn else {
            reopenSignIn()
            return
        }
        isSigningIn = true
        let fallbackCode = UUID().uuidString
        lastSignInURL = nil
        deviceCodeInput = ""
        deviceCodeStatusText = "Opening ElectricSheep login. If no page loads, press Open Login Again; use only a Backup code shown in the browser."

        Task {
            let coordinator = DesktopAuthCoordinator(dashboardBaseURL: resolver.dashboardBaseURL)
            activeAuthCoordinator = coordinator
            defer {
                if activeAuthCoordinator === coordinator {
                    activeAuthCoordinator = nil
                }
                isSigningIn = false
            }

            do {
                let newSession = try await coordinator.signIn(fallbackCode: fallbackCode) { [weak self] authURL in
                    self?.lastSignInURL = authURL
                }
                try saveAuthenticatedSession(newSession)
                await refreshCustomerTargets()
                await refreshFlaggedOSShellState()
                await loadRuntime(selectedRuntime, force: true)
            } catch DesktopAuthSessionError.cancelled {
                deviceCodeStatusText = "Login cancelled. Press Sign In to generate a fresh Backup code."
            } catch DesktopAuthSessionError.timedOut {
                deviceCodeStatusText = "Login timed out. Press Sign In to generate a fresh Backup code, or use the Backup code shown in the browser."
                runtimeErrors[selectedRuntime] = "Desktop sign-in timed out before Workbench received the callback."
            } catch DesktopAuthSessionError.couldNotStart {
                deviceCodeStatusText = "Workbench could not open the login page. Press Sign In again to generate a fresh Backup code."
                runtimeErrors[selectedRuntime] = "Desktop sign-in could not open the ElectricSheep login page."
            } catch {
                deviceCodeStatusText = "Login did not complete. If the browser is still open, use the Backup code shown there."
                runtimeErrors[selectedRuntime] = "Desktop sign-in failed or was cancelled: \(error.localizedDescription)"
            }
        }
    }

    func reopenSignIn() {
        guard let lastSignInURL else {
            if !isSigningIn {
                signIn()
            }
            return
        }
        deviceCodeStatusText = "Opening the current ElectricSheep login page again. If it still does not load, cancel and start a fresh sign-in."
        if !NSWorkspace.shared.open(lastSignInURL) {
            deviceCodeStatusText = "Workbench could not reopen the login page. Cancel and start a fresh sign-in."
        }
    }

    func cancelSignIn() {
        guard isSigningIn else { return }
        activeAuthCoordinator?.cancel()
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
                deviceCodeInput = ""
                deviceCodeStatusText = "That code expired, was already used, or was never registered by the browser. Press Sign In to generate a fresh Backup code."
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
        cancelSignIn()
        clearLocalSessionState(allowKeychainInteraction: false)
    }

    func handleAuthCallback(_ url: URL) {
        if WorkbenchProviderOAuthCallback.isOAuthComplete(url) {
            handleProviderOAuthComplete()
            return
        }
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

    private func handleProviderOAuthComplete() {
        providerHubStatusText = "App sign-in complete. Refreshing..."
        Task {
            await refreshProviderProfiles()
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
            customerTargets = []
            sessionRoles = []
            isOperatorSession = false
            ensureSelectedRuntimeIsVisible()
            customerTargetError = "Sign-in succeeded, but account permissions could not load. Refresh or sign out and back in if this persists."
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
        if featureFlags.isEnabled(.approvalCenter) {
            await refreshApprovalCenterState()
        }
    }

    func refreshProviderProfiles() async {
        guard isSignedIn else {
            providerProfiles = WorkbenchProviderCatalog.defaultStates
            updateConnectedAppMissionCards(from: providerProfiles)
            providerHubStatusText = "Sign in to connect apps."
            resetCapabilityManifestState(statusText: "Sign in first", clearCache: false)
            return
        }
        providerHubStatusText = "Refreshing..."
        do {
            let response = try await broker.providerProfiles(customerId: sanitizedCustomerId, desktopSession: session)
            let visibleProfiles = visibleProviderProfiles(response.profiles)
            providerProfiles = visibleProfiles
            updateConnectedAppMissionCards(from: visibleProfiles)
            providerHubStatusText = WorkbenchProviderHubSummary.statusText(
                rawSecretsStoredInWorkbench: response.rawSecretsStoredInWorkbench,
                profiles: visibleProfiles
            )
            await refreshCapabilityManifest(trigger: "provider_profiles")
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
            providerProfiles = WorkbenchProviderCatalog.defaultStates
            updateConnectedAppMissionCards(from: providerProfiles)
            providerHubStatusText = "Account permissions unavailable. Refresh or sign out and back in if this persists."
            resetCapabilityManifestState(statusText: "Account permissions unavailable", clearCache: false)
        } catch {
            providerProfiles = WorkbenchProviderCatalog.defaultStates
            updateConnectedAppMissionCards(from: providerProfiles)
            providerHubStatusText = "Unavailable: \(error.localizedDescription)"
            resetCapabilityManifestState(statusText: "Unavailable", clearCache: false)
        }
    }

    func connectProvider(_ providerKey: WorkbenchProviderKey) {
        guard isSignedIn else {
            providerHubStatusText = "Sign in before connecting apps."
            return
        }
        guard canUseProvider(providerKey) else {
            return
        }
        guard providerActionInFlight == nil else { return }
        providerActionInFlight = providerKey
        providerHubStatusText = "Opening Business Browser for app sign-in..."

        Task { @MainActor in
            defer { providerActionInFlight = nil }
            if let warmupURL = providerDashboardURL(providerKey: providerKey) {
                _ = try? await openProviderAuthHandoff(warmupURL)
            }
            do {
                let response = try await broker.connectProvider(
                    providerKey,
                    customerId: sanitizedCustomerId,
                    desktopSession: session
                )
                let visibleProfiles = visibleProviderProfiles(response.profiles)
                providerProfiles = visibleProfiles
                updateConnectedAppMissionCards(from: visibleProfiles)
                await refreshCapabilityManifest(trigger: "provider_connect")
                let runtime = try await openProviderAuthHandoff(response.connectURL)
                var targetOpenWarning: String?
                if let targetURL = response.targetURL {
                    do {
                        try await broker.openSharedBrowserURL(
                            targetURL,
                            customerId: sanitizedCustomerId,
                            desktopSession: session
                        )
                    } catch {
                        targetOpenWarning = "If the sign-in page is not already open, use the browser address bar to go to \(Self.safeURLSummary(targetURL.absoluteString))."
                    }
                }
                let runtimeTitle = RuntimeDefinition.definition(for: runtime).title
                let providerTitle = WorkbenchProviderCatalog.profile(for: providerKey)?.title ?? "this app"
                let fallbackInstruction = "\(runtimeTitle) opened inside Workbench. Sign in to \(providerTitle) in the business browser so Eva can reuse that browser session, then return to Connected Apps and refresh."
                let instruction = providerAuthInstruction(
                    response.instructions,
                    runtimeTitle: runtimeTitle,
                    fallback: fallbackInstruction
                )
                providerHubStatusText = [instruction, targetOpenWarning].compactMap { $0 }.joined(separator: " ")
            } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
                degradeProviderAuthorization()
            } catch RuntimeSessionBrokerError.httpStatus(let status) where [502, 503, 504].contains(status) {
                if let fallbackURL = providerDashboardURL(providerKey: providerKey) {
                    _ = try? await openProviderAuthHandoff(fallbackURL)
                    let providerTitle = WorkbenchProviderCatalog.profile(for: providerKey)?.title ?? "the app"
                    providerHubStatusText = "\(providerTitle) setup opened in Business Browser. The connection service is warming up or temporarily unavailable; use the Connected Apps page there, then refresh Workbench."
                } else {
                    providerHubStatusText = "App setup is temporarily unavailable: HTTP \(status)."
                }
            } catch {
                providerHubStatusText = "App sign-in failed to start: \(error.localizedDescription)"
            }
        }
    }

    func openCompanyBrainDashboard() {
        guard isSignedIn else { return }
        guard canOpenCompanyBrainDashboard else { return }
        openDashboardHandoff(pathComponent: "dashboard/company-brain", surface: "company-brain")
    }

    func openPeopleAccessDashboard() {
        guard isSignedIn else { return }
        guard canOpenPeopleAccessDashboard else { return }
        openDashboardHandoff(pathComponent: "dashboard/invites", surface: "people-access")
    }

    private func openDashboardHandoff(pathComponent: String, surface: String) {
        guard let url = dashboardURL(pathComponent: pathComponent, queryItems: [
            URLQueryItem(name: "customer_id", value: sanitizedCustomerId),
            URLQueryItem(name: "surface", value: surface),
        ]) else {
            runtimeErrors[selectedRuntime] = "Dashboard URL is invalid."
            return
        }

        Task { @MainActor in
            _ = try? await openProviderAuthHandoff(url)
        }
    }

    private func providerDashboardURL(providerKey: WorkbenchProviderKey) -> URL? {
        dashboardURL(pathComponent: "dashboard/providers", queryItems: [
            URLQueryItem(name: "provider", value: providerKey.rawValue),
            URLQueryItem(name: "customer_id", value: sanitizedCustomerId),
            URLQueryItem(name: "surface", value: "workbench"),
        ])
    }

    private func dashboardURL(pathComponent: String, queryItems: [URLQueryItem]) -> URL? {
        guard var components = URLComponents(string: dashboardBaseURLString) else {
            return nil
        }
        var path = components.path
        if path.hasSuffix("/") {
            path.removeLast()
        }
        components.path = path + "/" + pathComponent
        components.queryItems = queryItems
        return components.url
    }

    private func openProviderAuthHandoff(_ url: URL) async throws -> RuntimeKey {
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
        let lowercasedCopy = copy.lowercased()
        if lowercasedCopy.contains("/auth") || lowercasedCopy.contains("openclaw") {
            return fallback
        }
        copy = copy.replacingOccurrences(of: "OpenClaw will open.", with: "\(runtimeTitle) opened inside Workbench.")
        copy = copy.replacingOccurrences(of: "OpenClaw will open", with: "\(runtimeTitle) opened inside Workbench")
        copy = copy.replacingOccurrences(of: "OpenClaw auth handoff started.", with: "\(runtimeTitle) sign-in opened inside Workbench.")
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
        runProviderAction(providerKey, statusPrefix: "Preparing Eva access") {
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
            providerHubStatusText = "Sign in before changing app access."
            return
        }
        guard canUseProvider(providerKey) else {
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
                updateConnectedAppMissionCards(from: visibleProfiles)
                providerHubStatusText = WorkbenchProviderHubSummary.statusText(
                    rawSecretsStoredInWorkbench: response.rawSecretsStoredInWorkbench,
                    profiles: visibleProfiles
                )
                await refreshCapabilityManifest(trigger: "provider_action")
            } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
                degradeProviderAuthorization()
            } catch {
                providerHubStatusText = "App update failed: \(error.localizedDescription)"
                resetCapabilityManifestState(statusText: "Needs refresh", clearCache: false)
            }
        }
    }

    private func visibleProviderProfiles(_ profiles: [WorkbenchProviderProfileState]) -> [WorkbenchProviderProfileState] {
        let visibleProfiles = WorkbenchProviderCatalog.visibleStates(from: profiles)
        guard currentAccountRole == .agentOnly else {
            return visibleProfiles
        }
        return visibleProfiles.filter { profile in
            agentAssignments.contains { $0.canUseProviderProfile(profile) }
        }
    }

    private func updateConnectedAppMissionCards(from profiles: [WorkbenchProviderProfileState]) {
        let providerCards = WorkbenchMissionCardDeriver.providerCards(from: profiles)
        var nextCards = sessionMissionCards.filter { $0.surface != "connected_apps" }
        nextCards.append(contentsOf: providerCards)
        sessionMissionCards = nextCards
        sessionRecords = WorkbenchSessionContract.records(from: nextCards, customerId: sanitizedCustomerId)
    }

    private func updateAssignedAgentMissionCards() {
        let assignmentCards = WorkbenchMissionCardDeriver.assignedAgentCards(from: agentAssignments)
        var nextCards = sessionMissionCards.filter { $0.surface != "assigned_agent" }
        nextCards.insert(contentsOf: assignmentCards, at: 0)
        sessionMissionCards = nextCards
        sessionRecords = WorkbenchSessionContract.records(from: nextCards, customerId: sanitizedCustomerId)
    }

    func refreshCapabilityManifest(trigger _: String = "manual") async {
        guard isSignedIn else {
            resetCapabilityManifestState(statusText: "Sign in first", clearCache: false)
            return
        }
        guard !isRefreshingCapabilityManifest else { return }
        let agentID = RuntimeSessionBrokerClient.normalizedCapabilityAgentID(capabilityManifestAgentID)
        capabilityManifestAgentID = agentID
        isRefreshingCapabilityManifest = true
        capabilityManifestStatusText = "Refreshing..."
        defer { isRefreshingCapabilityManifest = false }

        do {
            let response = try await broker.capabilityManifest(agentID: agentID, desktopSession: session)
            guard let token = response.validatedCacheToken() else {
                throw RuntimeSessionBrokerError.invalidResponse
            }
            if !keychainDisabledForAgentQA {
                try capabilityManifestStore.saveToken(token)
            }
            capabilityManifestSummary = response.brokerSafeSummary
            if let assignments = response.agentAssignments, !assignments.isEmpty {
                agentAssignments = assignments
                capabilityManifestStatusText = "Ready: \(assignments.count) assigned agent"
            } else if let summary = response.brokerSafeSummary {
                capabilityManifestStatusText = "Ready: \(summary.totalGrantCount) permissions"
                agentAssignments = [
                    WorkbenchAgentAssignment.fromCapabilitySummary(
                        summary,
                        customerAccountID: sanitizedCustomerId,
                        assignedUserID: session?.userEmail ?? sanitizedCustomerId,
                        displayName: summary.agentID
                    )
                ]
            } else {
                capabilityManifestStatusText = "Cached: summary pending"
                agentAssignments.removeAll()
            }
            updateAssignedAgentMissionCards()
            await refreshUsageDashboard(trigger: "capability_manifest")
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 || status == 403 {
            resetCapabilityManifestState(statusText: "Account permissions unavailable", clearCache: false)
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 404 {
            resetCapabilityManifestState(statusText: "No policy for agent", clearCache: true)
        } catch {
            resetCapabilityManifestState(statusText: "Unavailable", clearCache: false)
        }
    }

    func refreshUsageDashboard(trigger _: String = "manual") async {
        guard isSignedIn else {
            resetUsageDashboardState(statusText: "Sign in first")
            return
        }
        guard !isRefreshingUsageDashboard else { return }
        isRefreshingUsageDashboard = true
        usageDashboardStatusText = "Refreshing..."
        defer { isRefreshingUsageDashboard = false }

        do {
            let response = try await broker.llmUsage(desktopSession: session)
            let cards = WorkbenchUsageDashboardDeriver.cards(
                from: response,
                manifestSummary: capabilityManifestSummary
            )
            usageDashboardCards = cards
            if !response.errors.isEmpty {
                usageDashboardStatusText = "Usage warnings"
            } else if cards.isEmpty {
                usageDashboardStatusText = "No usage yet"
            } else if cards.contains(where: { $0.attentionState == .needsAttention }) {
                usageDashboardStatusText = "Budget attention"
            } else {
                usageDashboardStatusText = "Ready: \(cards.count) agents"
            }

            let notificationPlan = WorkbenchBudgetNotificationPlanner.plan(
                cards: cards,
                notifiedAgentIDs: budgetNotifiedAgentIDs,
                usageDashboardVisible: usageDashboardVisible
            )
            let candidateAgentIDs = Set(notificationPlan.notifications.compactMap { budgetAgentID(from: $0.requestID) })
            let deliveredNotificationIDs = await approvalNotificationService.deliver(notificationPlan.notifications)
            let deliveredAgentIDs = Set(deliveredNotificationIDs.compactMap(budgetAgentID(from:)))
            budgetNotifiedAgentIDs = notificationPlan.notifiedAgentIDs
                .subtracting(candidateAgentIDs)
                .union(deliveredAgentIDs)
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 || status == 403 {
            resetUsageDashboardState(statusText: "Account permissions unavailable")
        } catch {
            resetUsageDashboardState(statusText: "Usage unavailable")
        }
    }

    func refreshSharedBrowserStatus() async {
        await refreshRuntimeStatus(.liveBrowser)
    }

    func refreshRuntimeStatus(_ runtime: RuntimeKey) async {
        let customerSnapshot = sanitizedCustomerId
        guard isSignedIn else {
            if runtime == .liveBrowser {
                sharedBrowserStatusText = "Sign in first"
                sharedBrowserRoomText = "Unavailable"
                sharedBrowserCurrentURLText = "Unavailable"
                sharedBrowserLastActivityText = "Not checked"
                businessBrowserStatus = nil
            }
            return
        }
        if runtime == .liveBrowser {
            guard !isRefreshingSharedBrowserStatus else { return }
            isRefreshingSharedBrowserStatus = true
        }
        defer {
            if runtime == .liveBrowser {
                isRefreshingSharedBrowserStatus = false
            }
        }
        do {
            let status = try await broker.runtimeStatus(
                customerId: customerSnapshot,
                runtime: runtime,
                desktopSession: session
            )
            guard sanitizedCustomerId == customerSnapshot else { return }
            runtimeStatuses[runtime] = status
            runtimeErrors[runtime] = nil
            if runtime == .liveBrowser {
                applyBusinessBrowserStatus(status, customerId: customerSnapshot)
            }
            updateSessionRecord(for: runtime, status: status, error: nil)
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
            guard sanitizedCustomerId == customerSnapshot else { return }
            degradeRuntimeAuthorization(
                runtime,
                message: "Account permissions unavailable. Refresh or sign out and back in if this persists."
            )
        } catch {
            guard sanitizedCustomerId == customerSnapshot else { return }
            runtimeErrors[runtime] = error.localizedDescription
            if runtime == .liveBrowser {
                sharedBrowserStatusText = "Unavailable"
                sharedBrowserRoomText = "Status unavailable"
                sharedBrowserCurrentURLText = "Unavailable"
                sharedBrowserLastActivityText = error.localizedDescription
                businessBrowserStatus = nil
            }
            updateSessionRecord(for: runtime, status: nil, error: error.localizedDescription)
        }
    }

    private func updateSessionRecord(for runtime: RuntimeKey, status: RuntimeStatusResponse?, error: String?) {
        let card = WorkbenchMissionCardDeriver.runtimeCard(
            definition: RuntimeDefinition.definition(for: runtime),
            status: status,
            localURLLoaded: runtimeURLs[runtime] != nil,
            error: error
        )
        var nextCards = sessionMissionCards.filter { $0.id != card.id }
        nextCards.insert(card, at: 0)
        sessionMissionCards = nextCards
        sessionRecords = WorkbenchSessionContract.records(from: nextCards, customerId: sanitizedCustomerId)
        if sessionCenterStatusText == "Unchecked" {
            sessionCenterStatusText = "Ready"
        }
    }

    private func degradeRuntimeAuthorization(_ runtime: RuntimeKey, message: String) {
        runtimeURLs[runtime] = nil
        runtimeStatuses[runtime] = nil
        runtimeErrors[runtime] = message
        if runtime == .liveBrowser {
            sharedBrowserStatusText = "Account permissions unavailable"
            sharedBrowserRoomText = "Status unavailable"
            sharedBrowserCurrentURLText = "Unavailable"
            sharedBrowserLastActivityText = "Refresh or sign out and back in if this persists"
            businessBrowserStatus = nil
        }
        updateSessionRecord(for: runtime, status: nil, error: message)
    }

    private func applyBusinessBrowserStatus(_ status: RuntimeStatusResponse, customerId: String) {
        let browserStatus = WorkbenchBrowserStatus.from(runtimeStatus: status, customerID: customerId)
        businessBrowserStatus = browserStatus
        sharedBrowserStatusText = Self.shortRuntimeStatus(browserStatus.status)
        sharedBrowserRoomText = browserStatus.roomID ?? status.displayLabel
        sharedBrowserCurrentURLText = browserStatus.currentURL?.displayText ?? "Unavailable"
        sharedBrowserLastActivityText = Self.activitySummary(browserStatus.lastActivityAt)
    }

    func refreshSessionCenterState() async {
        guard isSignedIn else {
            resetSessionCenterState(statusText: "Sign in first")
            return
        }
        let customerSnapshot = sanitizedCustomerId
        guard !isRefreshingSessionCenter else { return }
        isRefreshingSessionCenter = true
        sessionCenterStatusText = "Refreshing..."
        defer { isRefreshingSessionCenter = false }

        var nextStatuses: [RuntimeKey: RuntimeStatusResponse] = [:]
        var nextErrors: [RuntimeKey: String] = [:]
        var failures = 0
        for definition in visibleRuntimes where RuntimeDefinition.isBrokeredRuntime(definition.key) {
            do {
                let status = try await broker.runtimeStatus(
                    customerId: customerSnapshot,
                    runtime: definition.key,
                    desktopSession: session
                )
                guard sanitizedCustomerId == customerSnapshot else { return }
                nextStatuses[definition.key] = status
                if definition.key == .liveBrowser {
                    applyBusinessBrowserStatus(status, customerId: customerSnapshot)
                }
            } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
                guard sanitizedCustomerId == customerSnapshot else { return }
                let message = "Account permissions unavailable"
                nextErrors[definition.key] = message
                degradeRuntimeAuthorization(definition.key, message: message)
                failures += 1
            } catch {
                guard sanitizedCustomerId == customerSnapshot else { return }
                nextErrors[definition.key] = error.localizedDescription
                failures += 1
            }
        }
        let queueRaw = await bridge.run(arguments: ["queue", "list", "--json", "--limit", "10"])
        let auditRaw = await bridge.run(arguments: ["audit-tail", "--json", "--limit", "12"])
        let codexStatusRaw = await bridge.run(arguments: ["codex", "app-server", "status", "--json"])
        let codexRemoteRaw = await bridge.run(arguments: ["codex", "app-server", "remote-control-status", "--json"])
        let codexThreadsRaw = await bridge.run(arguments: ["codex", "app-server", "threads", "--json", "--max-items", "5"])

        var nextCards = visibleRuntimes
            .filter { RuntimeDefinition.isBrokeredRuntime($0.key) }
            .map { definition in
                WorkbenchMissionCardDeriver.runtimeCard(
                    definition: definition,
                    status: nextStatuses[definition.key],
                    localURLLoaded: runtimeURLs[definition.key] != nil,
                    error: nextErrors[definition.key]
                )
            }
        nextCards.append(contentsOf: WorkbenchMissionCardDeriver.queueCards(from: queueRaw))
        nextCards.append(contentsOf: WorkbenchMissionCardDeriver.auditCards(from: auditRaw))
        nextCards.append(contentsOf: WorkbenchMissionCardDeriver.codexCards(statusRaw: codexStatusRaw, remoteRaw: codexRemoteRaw, threadsRaw: codexThreadsRaw))
        nextCards.append(contentsOf: WorkbenchMissionCardDeriver.assignedAgentCards(from: agentAssignments))
        nextCards.append(contentsOf: WorkbenchMissionCardDeriver.providerCards(from: providerProfiles))

        guard sanitizedCustomerId == customerSnapshot else { return }
        var mergedRuntimeErrors = runtimeErrors
        for definition in visibleRuntimes where RuntimeDefinition.isBrokeredRuntime(definition.key) {
            if let error = nextErrors[definition.key] {
                mergedRuntimeErrors[definition.key] = error
            } else {
                mergedRuntimeErrors[definition.key] = nil
            }
        }
        runtimeStatuses = nextStatuses
        runtimeErrors = mergedRuntimeErrors
        sessionMissionCards = nextCards
        sessionRecords = WorkbenchSessionContract.records(from: nextCards, customerId: customerSnapshot)
        if nextStatuses.isEmpty && failures > 0 {
            sessionCenterStatusText = "Unavailable"
        } else if failures > 0 {
            sessionCenterStatusText = "\(nextStatuses.count) checked, \(failures) unavailable"
        } else {
            sessionCenterStatusText = "Ready"
        }
    }

    func reopenRecentSession(_ record: WorkbenchSessionRecord) async {
        guard let runtime = record.resumeRoute.runtime ?? record.runtime,
              RuntimeDefinition.isBrokeredRuntime(runtime) || RuntimeDefinition.externalURL(for: runtime) != nil else {
            return
        }
        selectedRuntime = runtime
        runtimeNavigationRequest = RuntimeNavigationRequest(runtime: runtime)
        await loadRuntime(runtime, force: true)
    }

    func refreshApprovalCenterState() async {
        guard isSignedIn else {
            resetApprovalCenterState(statusText: "Sign in first")
            return
        }
        guard !isRefreshingApprovalCenter else { return }
        isRefreshingApprovalCenter = true
        defer { isRefreshingApprovalCenter = false }

        do {
            let response = try await broker.pendingApprovals(desktopSession: session, limit: 50)
            let displayRequests = response.requests.map { $0.displayOnly() }
            approvalRequests = displayRequests
            approvalCenterStatusText = WorkbenchApprovalCenterSummary.statusText(for: approvalRequests)
            let notificationPlan = WorkbenchApprovalNotificationPlanner.plan(
                requests: displayRequests,
                previousPendingIDs: approvalPendingRequestIDs,
                notifiedRequestIDs: approvalNotifiedRequestIDs,
                approvalCenterVisible: approvalCenterVisible
            )
            approvalPendingRequestIDs = notificationPlan.pendingRequestIDs
            let candidateNotificationIDs = Set(notificationPlan.notifications.map(\.notificationID))
            let deliveredNotificationIDs = await approvalNotificationService.deliver(notificationPlan.notifications)
            approvalNotifiedRequestIDs = notificationPlan.notifiedRequestIDs
                .subtracting(candidateNotificationIDs)
                .union(deliveredNotificationIDs)
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
            approvalRequests = []
            approvalCenterStatusText = "Account permissions unavailable"
        } catch {
            approvalRequests = []
            approvalCenterStatusText = "Approval Center unavailable: \(error.localizedDescription)"
        }
    }

    func decideApprovalRequest(_ request: WorkbenchApprovalRequest, decision: WorkbenchApprovalDecision) async {
        guard isSignedIn else {
            resetApprovalCenterState(statusText: "Sign in first")
            return
        }
        guard approvalDecisionInFlight == nil else { return }
        let currentRequest = approvalRequests.first { $0.id == request.id }
        guard decision != .allowAlways || currentRequest != nil else {
            approvalCenterStatusText = "Approval request changed; refresh before deciding"
            return
        }
        let requestForDecision = currentRequest ?? request
        guard requestForDecision.isActionable || decision == .deny else {
            approvalCenterStatusText = "Missing destination; deny or ask Eva to retry"
            return
        }
        guard requestForDecision.hasDestinationProof || decision == .deny else {
            approvalCenterStatusText = "Missing destination proof; deny or ask Eva to retry"
            return
        }
        guard decision == .deny || !requestForDecision.isExpired() else {
            approvalCenterStatusText = "Approval request has expired; refresh before deciding"
            return
        }
        guard decision != .allowAlways || requestForDecision.canAllowAlways else {
            approvalCenterStatusText = "Allow always requires a durable destination constraint"
            return
        }

        approvalDecisionInFlight = requestForDecision.id
        defer { approvalDecisionInFlight = nil }

        do {
            let response = try await broker.decideApproval(
                approvalID: requestForDecision.id,
                decision: decision,
                request: requestForDecision,
                desktopSession: session
            )
            approvalRequests.removeAll { $0.id == requestForDecision.id }
            approvalPendingRequestIDs.remove(requestForDecision.id)
            approvalNotifiedRequestIDs.remove(requestForDecision.id)
            if let runtimeResult = response.runtimeResult {
                approvalCenterStatusText = "Resolved: \(runtimeResult.displayText)"
            } else {
                approvalCenterStatusText = WorkbenchApprovalCenterSummary.statusText(for: approvalRequests)
            }
        } catch RuntimeSessionBrokerError.httpStatus(let status) where status == 401 {
            approvalCenterStatusText = "Account permissions unavailable"
        } catch {
            approvalCenterStatusText = "Decision failed: \(error.localizedDescription)"
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
            let codexRaw = await bridge.run(arguments: ["codex", "connections", "status", "--json"])
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
                if response.headscale?.preauthKey?.isEmpty == false || response.headscale?.mode != nil {
                    nextPairingText += "\nSecure network material is held server-side."
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
        if let enrollmentExpiresAt, enrollmentExpiresAt <= Date() {
            self.enrollmentCode = nil
            self.enrollmentExpiresAt = nil
            pairingText = "Pairing code expired. Create a new pairing code before copying the agent prompt."
            return
        }

        let prompt = Self.agentPairingPrompt(
            enrollmentCode: enrollmentCode,
            enrollmentExpiresAt: enrollmentExpiresAt,
            customerId: sanitizedCustomerId
        )
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(prompt, forType: .string)
        pairingText = "Agent setup prompt copied. Paste it into your Eva or OpenClaw agent so it can complete the link."
    }

    func completeLocalMacEnrollment() {
        guard let enrollmentCode, !enrollmentCode.isEmpty, !isPairingMac else { return }
        isPairingMac = true
        pairingText = "Completing this Mac enrollment..."
        Task { @MainActor in
            defer { isPairingMac = false }
            do {
                let service = await bridge.run(arguments: ["connector-service", "status", "--json", "--support-internal"])
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

    private static func agentPairingPrompt(enrollmentCode: String, enrollmentExpiresAt: Date?, customerId: String) -> String {
        let expiryText = enrollmentExpiresAt.map { Self.shortDateFormatter.string(from: $0) } ?? "unknown"
        """
        Finish my evaOS Workbench Mac pairing.

        Customer: \(customerId)
        Pairing code: \(enrollmentCode)
        Expires: \(expiryText)

        From my evaOS VM, complete the pairing with the customer_mac_complete_pairing tool.
        Use exactly:
        - enrollment_code: \(enrollmentCode)
        - customer_id: \(customerId)

        Use only the fields above. If a tool asks for additional connector material, stop and report a Mac pairing contract mismatch.

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
        if runtime == .liveBrowser {
            runtimeStatuses[runtime] = nil
            businessBrowserStatus = nil
        }
    }

    private func resetRuntimeWebViewIfNeeded(_ runtime: RuntimeKey, customerId: String) {
        guard runtime == .openclaw else { return }
        webViews.reset(runtime: runtime, customerId: customerId)
        webViewRefreshToken = UUID()
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
        resetCapabilityManifestState(statusText: "Unchecked", clearCache: true)
        webViewRefreshToken = UUID()
    }

    private func clearLocalSessionState(allowKeychainInteraction: Bool) {
        if !keychainDisabledForAgentQA {
            try? keychain.clear(allowUserInteraction: allowKeychainInteraction)
        }
        resetCapabilityManifestState(statusText: "Sign in first", clearCache: true, allowKeychainInteraction: allowKeychainInteraction)
        session = nil
        resetSessionCenterState(statusText: "Sign in first")
        resetApprovalCenterState(statusText: "Sign in first")
        customerTargets = []
        sessionRoles = []
        isOperatorSession = false
        isLoadingCustomerTargets = false
        customerTargetError = nil
        pairedDevices = []
        enrollmentCode = nil
        enrollmentExpiresAt = nil
        providerProfiles = WorkbenchProviderCatalog.defaultStates
        providerHubStatusText = "Sign in to connect apps."
        providerActionInFlight = nil
        recentSessionRecords.removeAll()
        lastSignInURL = nil
        sharedBrowserStatusText = "Unchecked"
        sharedBrowserRoomText = "Unavailable"
        sharedBrowserCurrentURLText = "Unavailable"
        sharedBrowserLastActivityText = "Not checked"
        businessBrowserStatus = nil
        isRefreshingSharedBrowserStatus = false
        isStoppingSharedBrowser = false
        pairingText = "Sign in, start the connector, then pair this Mac with evaOS."
        deviceCodeInput = ""
        deviceCodeStatusText = "Press Sign In to open the ElectricSheep login page. Backup codes must come from the browser page."
        isClaimingDeviceCode = false
        isSigningIn = false
        webViews.reset()
        loadingRuntimes.removeAll()
        loadingRuntimePages.removeAll()
        runtimeURLs.removeAll()
        runtimeErrors.removeAll()
        fallbackReloadAttempts.removeAll()
        webViewRefreshToken = UUID()
    }

    private func saveAuthenticatedSession(_ newSession: DesktopSession) throws {
        if !keychainDisabledForAgentQA {
            try keychain.save(newSession)
        }
        session = newSession
        resetSessionCenterState(statusText: "Unchecked")
        resetApprovalCenterState(statusText: "Unchecked")
        customerTargets = []
        sessionRoles = []
        isOperatorSession = false
        customerTargetError = nil
        runtimeErrors.removeAll()
        lastSignInURL = nil
        deviceCodeInput = ""
        deviceCodeStatusText = "Signed in."
        isClaimingDeviceCode = false
        isSigningIn = false
        providerProfiles = WorkbenchProviderCatalog.defaultStates
        providerHubStatusText = "Unchecked"
        providerActionInFlight = nil
        loadRecentSessionRecords()
        resetCapabilityManifestState(statusText: "Unchecked", clearCache: false)
        sharedBrowserStatusText = "Unchecked"
        sharedBrowserRoomText = "Not opened"
        sharedBrowserCurrentURLText = "Unavailable"
        sharedBrowserLastActivityText = "Not checked"
        businessBrowserStatus = nil
        isRefreshingSharedBrowserStatus = false
        isStoppingSharedBrowser = false
        webViews.reset()
        loadingRuntimes.removeAll()
        loadingRuntimePages.removeAll()
        runtimeURLs.removeAll()
        fallbackReloadAttempts.removeAll()
        webViewRefreshToken = UUID()
    }

    private func resetSessionCenterState(statusText: String) {
        runtimeStatuses.removeAll()
        sessionMissionCards.removeAll()
        sessionRecords.removeAll()
        sessionCenterStatusText = statusText
        isRefreshingSessionCenter = false
    }

    private func loadRecentSessionRecords() {
        guard isSignedIn else {
            recentSessionRecords.removeAll()
            return
        }
        let key = WorkbenchRecentLaunchStore.storageKey(customerId: sanitizedCustomerId)
        let records = WorkbenchRecentLaunchStore.records(
            from: UserDefaults.standard.data(forKey: key),
            customerId: sanitizedCustomerId
        )
        recentSessionRecords = WorkbenchRecentLaunchStore.sessionRecords(from: records)
    }

    private func recordRecentLaunch(runtime: RuntimeKey, customerId: String) {
        guard RuntimeDefinition.isBrokeredRuntime(runtime) || RuntimeDefinition.externalURL(for: runtime) != nil else {
            return
        }
        let key = WorkbenchRecentLaunchStore.storageKey(customerId: customerId)
        let existing = WorkbenchRecentLaunchStore.records(
            from: UserDefaults.standard.data(forKey: key),
            customerId: customerId
        )
        let record = WorkbenchRecentLaunchRecord(runtime: runtime, customerId: customerId)
        let merged = WorkbenchRecentLaunchStore.merged(record, into: existing)
        if let data = try? JSONEncoder().encode(merged) {
            UserDefaults.standard.set(data, forKey: key)
        }
        if WorkbenchRecentLaunchStore.sanitizedCustomerId(customerId) == sanitizedCustomerId {
            recentSessionRecords = WorkbenchRecentLaunchStore.sessionRecords(from: merged)
        }
    }

    private func resetApprovalCenterState(statusText: String) {
        approvalRequests.removeAll()
        approvalCenterStatusText = statusText
        isRefreshingApprovalCenter = false
        approvalDecisionInFlight = nil
        approvalPendingRequestIDs.removeAll()
        approvalNotifiedRequestIDs.removeAll()
    }

    private func resetUsageDashboardState(statusText: String) {
        usageDashboardCards.removeAll()
        usageDashboardStatusText = statusText
        isRefreshingUsageDashboard = false
        budgetNotifiedAgentIDs.removeAll()
    }

    private func resetCapabilityManifestState(
        statusText: String,
        clearCache: Bool,
        allowKeychainInteraction: Bool = false
    ) {
        if clearCache && !keychainDisabledForAgentQA {
            try? capabilityManifestStore.clear(allowUserInteraction: allowKeychainInteraction)
        }
        capabilityManifestSummary = nil
        agentAssignments.removeAll()
        sessionMissionCards.removeAll { $0.surface == "assigned_agent" }
        sessionRecords = WorkbenchSessionContract.records(from: sessionMissionCards, customerId: sanitizedCustomerId)
        capabilityManifestStatusText = statusText
        isRefreshingCapabilityManifest = false
        resetUsageDashboardState(statusText: statusText)
    }

    private func degradeProviderAuthorization() {
        providerHubStatusText = "Account permissions unavailable. Refresh or sign out and back in if this persists."
        resetCapabilityManifestState(statusText: "Account permissions unavailable", clearCache: false)
    }

    private func budgetAgentID(from notificationID: String) -> String? {
        guard notificationID.hasPrefix("budget:") else { return nil }
        let agentID = String(notificationID.dropFirst("budget:".count))
        return agentID.isEmpty ? nil : agentID
    }

    private func handleBrokerAuthorizationFailure(_ status: Int, runtime: RuntimeKey) {
        if status == 401 {
            degradeRuntimeAuthorization(
                runtime,
                message: "Account permissions unavailable for this workspace. Refresh or sign out and back in if this persists."
            )
            return
        }
        runtimeURLs[runtime] = nil
        runtimeErrors[runtime] = "This account is not authorized for that workspace or customer."
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
        return (!definition.requiresAdmin || canAccessAdminRuntimes)
            && WorkbenchAgentAssignmentAccessPolicy.canAccessRuntime(runtime, role: currentAccountRole, assignment: currentAssignment)
    }

    private func canUseProvider(_ providerKey: WorkbenchProviderKey) -> Bool {
        guard currentAccountRole == .agentOnly else {
            return true
        }
        guard let profile = providerProfiles.first(where: { $0.key == providerKey }) else {
            providerHubStatusText = "That app is not assigned to this user."
            return false
        }
        let allowed = agentAssignments.contains { $0.canUseProviderProfile(profile) }
        if !allowed {
            let title = WorkbenchProviderCatalog.profile(for: providerKey)?.title ?? "That app"
            providerHubStatusText = "\(title) is not assigned to this user."
        }
        return allowed
    }

    private static func normalizedSurface(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func ensureSelectedRuntimeIsVisible() {
        if !canAccess(selectedRuntime) {
            selectedRuntime = visibleRuntimes.first?.key ?? .liveBrowser
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
            runtimeErrors[runtime] = "Workspace page returned HTTP \(status)\(suffix)."
        case .fallbackDetected(let label):
            loadingRuntimePages.remove(runtime)
            let attempts = fallbackReloadAttempts[runtime, default: 0]
            guard attempts < 1, isSignedIn else {
                runtimeErrors[runtime] = "\(label). Reconnect this workspace to refresh the authenticated session."
                return
            }
            fallbackReloadAttempts[runtime] = attempts + 1
            runtimeErrors[runtime] = "\(label). Reconnecting..."
            runtimeURLs[runtime] = nil
            Task {
                await loadRuntime(runtime, force: true)
            }
        case .providerOAuthComplete:
            loadingRuntimePages.remove(runtime)
            runtimeErrors[runtime] = nil
            handleProviderOAuthComplete()
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
    case providerOAuthComplete(URL)
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

    func reset(runtime: RuntimeKey, customerId: String) {
        let key = "\(customerId)::\(runtime.rawValue)"
        if let webView = webViews.removeValue(forKey: key) {
            discard(webView)
        }
        delegates.removeValue(forKey: key)
    }

    func reset() {
        for webView in webViews.values {
            discard(webView)
        }
        webViews.removeAll()
        delegates.removeAll()
    }

    private func discard(_ webView: WKWebView) {
        webView.stopLoading()
        webView.navigationDelegate = nil
        webView.loadHTMLString("", baseURL: nil)
        webView.removeFromSuperview()
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

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        if
            let url = navigationAction.request.url,
            WorkbenchProviderOAuthCallback.isOAuthComplete(url)
        {
            onEvent(runtime, .providerOAuthComplete(url))
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
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
                self.onEvent(self.runtime, .fallbackDetected("This workspace opened its connection screen"))
            } else {
                self.onEvent(self.runtime, .finished)
            }
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        onEvent(runtime, .failed("Workspace page failed to load: \(error.localizedDescription)."))
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        onEvent(runtime, .failed("Workspace page failed to start loading: \(error.localizedDescription)."))
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        onEvent(runtime, .failed("Workspace web content stopped unexpectedly. Reconnect this workspace to continue."))
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

private enum DesktopAuthSessionError: Error, LocalizedError {
    case couldNotStart
    case timedOut
    case cancelled

    var errorDescription: String? {
        switch self {
        case .couldNotStart:
            "Workbench could not open the ElectricSheep login page."
        case .timedOut:
            "Workbench did not receive a desktop login callback before the sign-in window timed out."
        case .cancelled:
            "The desktop login was cancelled."
        }
    }
}

@MainActor
final class DesktopAuthCoordinator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private static let loginTimeoutNanoseconds: UInt64 = 180 * 1_000_000_000

    private var authSession: ASWebAuthenticationSession?
    private var finishActiveSignIn: (@MainActor (Result<DesktopSession, Error>) -> Void)?
    private let dashboardBaseURL: URL

    init(dashboardBaseURL: URL) {
        self.dashboardBaseURL = dashboardBaseURL
    }

    func cancel() {
        finishActiveSignIn?(.failure(DesktopAuthSessionError.cancelled))
    }

    func signIn(
        fallbackCode: String,
        onAuthURL: @escaping @MainActor (URL) -> Void = { _ in }
    ) async throws -> DesktopSession {
        return try await withCheckedThrowingContinuation { continuation in
            var didComplete = false
            var loopbackReceiver: DesktopAuthLoopbackReceiver?
            var timeoutTask: Task<Void, Never>?

            @MainActor
            func finish(_ result: Result<DesktopSession, Error>) {
                guard !didComplete else { return }
                didComplete = true
                timeoutTask?.cancel()
                loopbackReceiver?.stop()
                authSession?.cancel()
                authSession = nil
                finishActiveSignIn = nil
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
            onAuthURL(authURL)

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
            finishActiveSignIn = { result in
                finish(result)
            }
            timeoutTask = Task { @MainActor in
                try? await Task.sleep(nanoseconds: Self.loginTimeoutNanoseconds)
                guard !Task.isCancelled else { return }
                finish(.failure(DesktopAuthSessionError.timedOut))
            }

            let didStart = session.start()
            guard didStart else {
                guard NSWorkspace.shared.open(authURL) else {
                    finish(.failure(DesktopAuthSessionError.couldNotStart))
                    return
                }
                return
            }
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
        bridgeKey(["queue", "list", "--json", "--limit", "10"]),
        bridgeKey(["codex", "connections", "status", "--json"]),
        bridgeKey(["codex", "app-server", "status", "--json"]),
        bridgeKey(["codex", "app-server", "remote-control-status", "--json"]),
        bridgeKey(["codex", "app-server", "threads", "--json", "--max-items", "5"])
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

            let fileManager = FileManager.default
            let captureID = UUID().uuidString
            let stdoutURL = fileManager.temporaryDirectory.appendingPathComponent("evaos-bridge-\(captureID).stdout")
            let stderrURL = fileManager.temporaryDirectory.appendingPathComponent("evaos-bridge-\(captureID).stderr")
            guard fileManager.createFile(atPath: stdoutURL.path, contents: nil),
                  fileManager.createFile(atPath: stderrURL.path, contents: nil) else {
                return "Unable to create bridge command capture files."
            }
            let stdoutHandle: FileHandle
            let stderrHandle: FileHandle
            do {
                stdoutHandle = try FileHandle(forWritingTo: stdoutURL)
                stderrHandle = try FileHandle(forWritingTo: stderrURL)
            } catch {
                try? fileManager.removeItem(at: stdoutURL)
                try? fileManager.removeItem(at: stderrURL)
                return "Unable to create bridge command capture files: \(error.localizedDescription)"
            }
            defer {
                try? stdoutHandle.close()
                try? stderrHandle.close()
                try? fileManager.removeItem(at: stdoutURL)
                try? fileManager.removeItem(at: stderrURL)
            }
            process.standardOutput = stdoutHandle
            process.standardError = stderrHandle

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
            try? stdoutHandle.close()
            try? stderrHandle.close()

            let stdout = (try? String(contentsOf: stdoutURL, encoding: .utf8)) ?? ""
            let stderr = (try? String(contentsOf: stderrURL, encoding: .utf8)) ?? ""
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
    private var helperProcess: Process?
    private var helperLogHandle: FileHandle?

    func start() async -> String {
        if let process, process.isRunning {
            if let helperProcess, helperProcess.isRunning {
                return "Starting connector: already running from Workbench with the managed helper."
            }
            process.terminate()
            self.process = nil
            try? logHandle?.close()
            logHandle = nil
        }
        guard let bridgeURL = Self.resolveBridgeExecutable() else {
            return "Connector offline: install evaos-desktop-bridge before starting this Mac connector."
        }

        let helperLaunch = await startComputerUseHelper(bridgeURL: bridgeURL)
        guard helperLaunch.canStartConnector else {
            return helperLaunch.message
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
            helperLaunch.connectorEnvironment.forEach { key, value in
                environment[key] = value
            }
            next.environment = environment
            next.standardOutput = handle
            next.standardError = handle
            try next.run()
            process = next
            logHandle = handle
            return "\(helperLaunch.message)\nStarting connector on \(host):8765. Keep Workbench open while the connector is running."
        } catch {
            _ = stopComputerUseHelper()
            return "Connector failed to start: \(error.localizedDescription)"
        }
    }

    func stop() -> String {
        let helperStop = stopComputerUseHelper()
        guard let process else {
            return "Workbench-managed connector was not running.\n\(helperStop)"
        }
        if process.isRunning {
            process.terminate()
        }
        self.process = nil
        try? logHandle?.close()
        logHandle = nil
        return "Workbench-managed connector stopped.\n\(helperStop)"
    }

    deinit {
        if let process, process.isRunning {
            process.terminate()
        }
        try? logHandle?.close()
        if let helperProcess, helperProcess.isRunning {
            helperProcess.terminate()
        }
        try? helperLogHandle?.close()
    }

    private func startComputerUseHelper(bridgeURL: URL) async -> HelperLaunchResult {
        let paths = Self.helperPaths()
        let connectorEnvironment = [
            "EVAOS_DESKTOP_BRIDGE_USE_HELPER": "1",
            "EVAOS_DESKTOP_BRIDGE_HELPER_SOCKET": paths.socket.path,
            "EVAOS_DESKTOP_BRIDGE_HELPER_TOKEN_FILE": paths.token.path
        ]

        if let helperProcess, helperProcess.isRunning {
            let ping = await Self.helperPing(bridgeURL: bridgeURL, paths: paths)
            return HelperLaunchResult(
                canStartConnector: ping != nil,
                connectorEnvironment: ping == nil ? [:] : connectorEnvironment,
                message: ping.map(Self.helperLaunchMessage(from:)) ?? "Computer-use helper is running but did not answer ping; Mac Access stayed off to avoid falling back to a terminal or Python permission identity."
            )
        }

        do {
            try FileManager.default.createDirectory(
                at: paths.log.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try FileManager.default.createDirectory(
                at: paths.token.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            if !FileManager.default.fileExists(atPath: paths.log.path) {
                FileManager.default.createFile(atPath: paths.log.path, contents: nil)
            }
            let handle = try FileHandle(forWritingTo: paths.log)
            try handle.seekToEnd()

            let next = Process()
            next.executableURL = bridgeURL
            next.arguments = [
                "helper",
                "run",
                "--socket-path",
                paths.socket.path,
                "--token-file",
                paths.token.path
            ]
            var environment = ProcessInfo.processInfo.environment
            environment["EVAOS_DESKTOP_BRIDGE_MODE"] = "computer-use-helper"
            environment["EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID"] = Bundle.main.bundleIdentifier ?? "com.electricsheephq.EvaDesktop"
            environment["EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH"] = Bundle.main.bundlePath
            environment["EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS"] = "1"
            next.environment = environment
            next.standardOutput = handle
            next.standardError = handle
            try next.run()
            helperProcess = next
            helperLogHandle = handle

            let ping = await Self.waitForHelperPing(bridgeURL: bridgeURL, paths: paths)
            guard let ping else {
                _ = stopComputerUseHelper()
                return HelperLaunchResult(
                    canStartConnector: false,
                    connectorEnvironment: [:],
                    message: "Computer-use helper did not become reachable under the evaOS Workbench identity. Mac Access stayed off to avoid a Python or terminal TCC prompt."
                )
            }
            return HelperLaunchResult(
                canStartConnector: true,
                connectorEnvironment: connectorEnvironment,
                message: Self.helperLaunchMessage(from: ping)
            )
        } catch {
            return HelperLaunchResult(
                canStartConnector: false,
                connectorEnvironment: [:],
                message: "Computer-use helper failed to start under evaOS Workbench: \(error.localizedDescription)"
            )
        }
    }

    private func stopComputerUseHelper() -> String {
        guard let helperProcess else {
            return "Computer-use helper was not running from Workbench."
        }
        if helperProcess.isRunning {
            helperProcess.terminate()
        }
        self.helperProcess = nil
        try? helperLogHandle?.close()
        helperLogHandle = nil
        return "Workbench-managed computer-use helper stopped."
    }

    private struct HelperPaths: Sendable {
        let socket: URL
        let token: URL
        let log: URL
    }

    private struct HelperLaunchResult: Sendable {
        let canStartConnector: Bool
        let connectorEnvironment: [String: String]
        let message: String
    }

    private static func helperPaths() -> HelperPaths {
        let base = applicationSupportDirectory()
        return HelperPaths(
            socket: URL(fileURLWithPath: "/tmp/evaos-helper-\(getuid()).sock"),
            token: base.appendingPathComponent("computer-use-helper.token"),
            log: base.appendingPathComponent("computer-use-helper.log")
        )
    }

    private static func applicationSupportDirectory() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("evaos-desktop-bridge", isDirectory: true)
    }

    private static func waitForHelperPing(bridgeURL: URL, paths: HelperPaths) async -> String? {
        let deadline = Date().addingTimeInterval(3)
        while Date() < deadline {
            if let ping = await helperPing(bridgeURL: bridgeURL, paths: paths) {
                return ping
            }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        return nil
    }

    private static func helperPing(bridgeURL: URL, paths: HelperPaths) async -> String? {
        await Task.detached {
            commandOutput(bridgeURL.path, [
                "helper",
                "ping",
                "--json",
                "--socket-path",
                paths.socket.path,
                "--token-file",
                paths.token.path
            ])
        }.value
    }

    nonisolated private static func helperLaunchMessage(from raw: String) -> String {
        guard let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let dataObject = object["data"] as? [String: Any],
              let preflight = dataObject["permission_preflight"] as? [String: Any],
              let identity = preflight["identity"] as? [String: Any],
              let permissions = preflight["permissions"] as? [String: Any] else {
            return "Computer-use helper is running under evaOS Workbench; permission preflight could not be summarized."
        }
        let identityStatus = identity["status"] as? String ?? "unknown"
        let accessibility = (permissions["accessibility"] as? [String: Any])?["status"] as? String ?? "unknown"
        let screenRecording = (permissions["screen_recording"] as? [String: Any])?["status"] as? String ?? "unknown"
        if preflight["ok"] as? Bool == true {
            return "Computer-use helper is running under the evaOS Workbench identity with Accessibility and Screen Recording ready."
        }
        return "Computer-use helper is running with identity \(identityStatus). Accessibility: \(accessibility). Screen Recording: \(screenRecording). Live actions will fail closed until evaOS Workbench has both grants."
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
        applicationSupportDirectory()
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
        let ready = value(at: ["data", "ready"], in: object) as? Bool
        let warningActive = value(at: ["data", "takeover_warning", "active"], in: object) as? Bool
        let warningRemaining = value(at: ["data", "takeover_warning", "remaining_seconds"], in: object) as? Int
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
        if warningActive == true {
            let remaining = max(1, warningRemaining ?? 10)
            return compact([
                "Taking over screen in \(remaining)s",
                "Live agent actions are paused for the operator warning.",
                mode.map { $0 == "full_access" ? "Mode: Full Access" : "Mode: Ask Permission" },
                currentApp.map { "Current app: \($0)" }
            ])
        }
        return compact([
            ready == false ? "Starting" : "Ready",
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
        let appServerReady = value(at: ["data", "app_server", "available"], in: object) as? Bool
        let transport = value(at: ["data", "app_server", "transport"], in: object) as? String
        let remoteCommand = value(at: ["data", "remote_control_command", "supported"], in: object) as? Bool
        let daemonReady = value(at: ["data", "daemon", "version_available"], in: object) as? Bool
        let controlSockets = value(at: ["data", "control_sockets"], in: object) as? [[String: Any]]
        let socketDetected = controlSockets?.contains { socket in
            socket["exists"] as? Bool == true
        }
        let notifications = value(at: ["data", "live_notifications", "supported"], in: object) as? Bool
        return compact([
            ok ? "Checked" : "Needs attention",
            appServerReady.map { "App-server: \($0 ? "ready" : "unavailable")" },
            transport.map { "Transport: \($0)" },
            remoteCommand.map { "Remote-control command: \($0 ? "supported" : "missing")" },
            daemonReady.map { "Daemon: \($0 ? "ready" : "not running")" },
            socketDetected.map { "Control socket: \($0 ? "detected" : "not detected")" },
            notifications.map { "Live events: \($0 ? "supported" : "unavailable")" },
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
