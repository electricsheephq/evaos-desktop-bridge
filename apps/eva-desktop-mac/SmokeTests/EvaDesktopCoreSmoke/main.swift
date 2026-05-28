import EvaDesktopCore
import Foundation

let resolver = RuntimeURLResolver()

precondition(AppBrand.visibleName == "evaOS Workbench")
precondition(AppBrand.runtimeSectionTitle == "Gateways")
precondition(AppBrand.signedOutStatus == "Sign in to launch evaOS gateways")
precondition(AppBrand.bundleDisplayName == "evaOS Workbench")
precondition(AppBrand.defaultUpdateManifestURL == "https://www.electricsheephq.com/evaos-workbench/updates.json")

precondition(WorkbenchFeatureFlagKey.allCases.map(\.rawValue) == [
    "providers_hub",
    "session_center",
    "creative_studio"
])
let featureFlags = WorkbenchFeatureFlags()
precondition(!featureFlags.isEnabled(.providersHub))
precondition(!featureFlags.isEnabled(.sessionCenter))
precondition(!featureFlags.isEnabled(.creativeStudio))
precondition(featureFlags.enabledKeys == [])
precondition(featureFlags.storedValue(for: .creativeStudio) == false)
precondition(featureFlags.storedValue(for: .providersHub) == false)
precondition(featureFlags.storedValue(for: .sessionCenter) == false)

let featureFlagDefaults = UserDefaults(suiteName: "EvaDesktopCoreSmoke.feature-flags.\(UUID().uuidString)")!
featureFlagDefaults.set(false, forKey: WorkbenchFeatureFlagKey.providersHub.userDefaultsKey)
featureFlagDefaults.set(false, forKey: WorkbenchFeatureFlagKey.creativeStudio.userDefaultsKey)
let configuredFeatureFlags = WorkbenchFeatureFlags(userDefaults: featureFlagDefaults)
precondition(!configuredFeatureFlags.isEnabled(.providersHub))
precondition(!configuredFeatureFlags.isEnabled(.sessionCenter))
precondition(!configuredFeatureFlags.isEnabled(.creativeStudio))
precondition(WorkbenchProviderCatalog.profiles.map(\.key) == [.openAICodex])
precondition(WorkbenchProviderCatalog.profiles.allSatisfy { !$0.rawSecretsStoredInWorkbench })
precondition(WorkbenchProviderCatalog.profiles.first?.readiness == .needsLogin)
precondition(WorkbenchProviderCatalog.defaultStates.map(\.key) == [.openAICodex])
precondition(WorkbenchProviderCatalog.defaultStates.allSatisfy { !$0.rawSecretsStoredInWorkbench })
precondition(WorkbenchProviderCatalog.defaultStates.first?.status == .needsLogin)

precondition(resolver.sanitizedCustomerId(" Jackie David ") == "jackie-david")
precondition(resolver.sanitizedCustomerId("David_Poku!") == "david-poku")
precondition(resolver.sanitizedCustomerId("") == "golden")

precondition(RuntimeDefinition.isBrokeredRuntime(.openclaw))
precondition(RuntimeDefinition.isBrokeredRuntime(.terminal))
precondition(RuntimeDefinition.isBrokeredRuntime(.openDesign))
precondition(!RuntimeDefinition.isBrokeredRuntime(.creativeStudio))
precondition(RuntimeDefinition.externalURL(for: .creativeStudio)?.absoluteString == "https://www.comfy.org/cloud")
precondition(RuntimeDefinition.visibleRuntimes(canAccessAdminRuntimes: false).contains { $0.key == .terminal })
precondition(RuntimeDefinition.visibleRuntimes(canAccessAdminRuntimes: true).contains { $0.key == .terminal })
precondition(RuntimeDefinition.definition(for: .openDesign).availability == .enabled)
precondition(RuntimeDefinition.definition(for: .creativeStudio).availability == .enabled)
precondition(RuntimeDefinition.definition(for: .openclaw).title == "evaOS (OpenClaw)")
precondition(RuntimeDefinition.definition(for: .liveBrowser).title == "Shared Browser")
precondition(RuntimeDefinition.definition(for: .creativeStudio).title == "Creative Studio")
precondition(RuntimeDefinition.definition(for: .creativeStudio).subtitle.contains("ComfyUI Cloud"))
precondition(RuntimeDefinition.all.map(\.key) == [.openclaw, .hermes, .missionControl, .openDesign, .liveBrowser, .terminal, .creativeStudio])

let contentViewSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/ContentView.swift", encoding: .utf8)
precondition(!contentViewSource.contains("case .sharedBrowser2"))
precondition(!contentViewSource.contains("CreativeStudioPlaceholderView"))
precondition(contentViewSource.contains("model.runtimeNavigationRequest"))
precondition(contentViewSource.contains("sidebarSelection = .runtime(request.runtime)"))
let osViewsSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/WorkbenchOSViews.swift", encoding: .utf8)
precondition(!osViewsSource.contains("struct SharedBrowser2View"))
precondition(!osViewsSource.contains("struct CreativeStudioPlaceholderView"))
precondition(osViewsSource.contains("model.sessionMissionCards"))
precondition(!osViewsSource.contains("model.runtimeURLs[runtime.key] == nil ? \"Ready to open\" : \"Loaded\""))
precondition(osViewsSource.contains("Needs verification"))
precondition(!osViewsSource.contains("OpenClaw and Hermes"))
precondition(!osViewsSource.contains("Agent Grant"))
precondition(!osViewsSource.contains("Providers & Auth Hub"))
precondition(osViewsSource.contains("WorkbenchSurface(title: \"Providers\""))
precondition(osViewsSource.contains("Connect provider accounts in the Shared Browser"))
precondition(osViewsSource.contains("OpenClaw Grant"))
let sidebarSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/SidebarView.swift", encoding: .utf8)
precondition(!sidebarSource.contains("Preview"))
precondition(!sidebarSource.contains("Shared Browser 2.0"))
precondition(!sidebarSource.contains("Providers & Auth Hub"))
precondition(sidebarSource.contains("FeatureSidebarRow(title: \"Providers\""))
let settingsSection = sidebarSource.range(of: "Section(AppBrand.bridgeSectionTitle)")!
let providersSidebarRow = sidebarSource.range(of: "FeatureSidebarRow(title: \"Providers\"")!
let workspaceSection = sidebarSource.range(of: "Section(\"Workspace\")")!
precondition(settingsSection.lowerBound < providersSidebarRow.lowerBound)
precondition(providersSidebarRow.lowerBound < workspaceSection.lowerBound)
precondition(sidebarSource.contains("CustomerTargetMenu"))
precondition(sidebarSource.contains("Switch customer?"))
let runtimeDetailSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/RuntimeDetailView.swift", encoding: .utf8)
precondition(!runtimeDetailSource.contains("CustomerTargetMenu"))
let customerTargetMenuSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/CustomerTargetMenu.swift", encoding: .utf8)
precondition(customerTargetMenuSource.contains("Reset to Golden"))
let workbenchModelSource = try String(contentsOfFile: "Sources/EvaDesktop/Services/WorkbenchModel.swift", encoding: .utf8)
precondition(!workbenchModelSource.contains("NSWorkspace.shared.open(response.connectURL)"))
precondition(workbenchModelSource.contains("openProviderAuthHandoff(response.connectURL)"))
precondition(workbenchModelSource.contains("broker.openSharedBrowserURL("))
precondition(workbenchModelSource.contains("response.targetURL"))
precondition(workbenchModelSource.contains("runtime: runtime"))
precondition(workbenchModelSource.contains("broker.launchURL("))
precondition(workbenchModelSource.contains("Opening Shared Browser for provider sign-in"))
precondition(workbenchModelSource.contains("shared VM browser"))
precondition(workbenchModelSource.contains("opened inside Workbench"))
precondition(workbenchModelSource.contains("runtimeNavigationRequest = RuntimeNavigationRequest(runtime: runtime)"))
precondition(workbenchModelSource.contains("runtimeURLs[runtime] = url"))
precondition(workbenchModelSource.contains("resetRuntimeWebViewIfNeeded(runtime, customerId: targetCustomerId)"))
precondition(workbenchModelSource.contains("func reset(runtime: RuntimeKey, customerId: String)"))
precondition(workbenchModelSource.contains("webView.removeFromSuperview()"))
precondition(workbenchModelSource.contains("bridgeKey([\"queue\", \"list\", \"--json\", \"--limit\", \"10\"])"))
precondition(workbenchModelSource.contains("bridgeKey([\"codex\", \"app-server\", \"status\", \"--json\"])"))
precondition(workbenchModelSource.contains("bridgeKey([\"codex\", \"app-server\", \"threads\", \"--json\", \"--max-items\", \"5\"])"))
precondition(workbenchModelSource.contains("evaos-bridge-\\(captureID).stdout"))
precondition(workbenchModelSource.contains("FileHandle(forWritingTo: stdoutURL)"))
precondition(!workbenchModelSource.contains("turn/start"))
precondition(!workbenchModelSource.contains("turn/steer"))
precondition(!workbenchModelSource.contains("turn/interrupt"))
precondition(!workbenchModelSource.contains("Complete `/auth openai-codex`"))
let bridgePanelSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/BridgePanelView.swift", encoding: .utf8)
precondition(!bridgePanelSource.contains("Your agent can control this Mac and iPhone until you stop it."))
precondition(bridgePanelSource.contains("Start a visible Agent Control session"))
let releaseScriptSource = try String(contentsOfFile: "script/build_and_run.sh", encoding: .utf8)
precondition(!releaseScriptSource.contains("internal canary"))
precondition(!releaseScriptSource.contains("non-notarized"))
precondition(releaseScriptSource.contains("Developer ID signed, notarized, and stapled"))

let trustedDownload = URL(string: "https://github.com/electricsheephq/evaos-workbench-releases/releases/download/evaos-workbench-v0.6.6/evaOS-Workbench-0.6.6.zip")!
let olderManifest = WorkbenchReleaseManifest(version: "0.1.3", build: "1", downloadURL: trustedDownload)
let newerManifest = WorkbenchReleaseManifest(version: "0.6.6", build: "1", downloadURL: trustedDownload)
let newerBuildManifest = WorkbenchReleaseManifest(version: "0.6.6", build: "47", downloadURL: trustedDownload)
precondition(!olderManifest.isNewerThan(currentVersion: AppBrand.version, currentBuild: AppBrand.buildNumber))
precondition(!newerManifest.isNewerThan(currentVersion: AppBrand.version, currentBuild: AppBrand.buildNumber))
precondition(newerBuildManifest.isNewerThan(currentVersion: AppBrand.version, currentBuild: AppBrand.buildNumber))
precondition(WorkbenchUpdateClient.isTrustedUpdateURL(URL(string: AppBrand.defaultUpdateManifestURL)!))
precondition(WorkbenchUpdateClient.isTrustedUpdateURL(trustedDownload))
precondition(!WorkbenchUpdateClient.isTrustedUpdateURL(URL(string: "https://example.com/evaOS-Workbench-0.1.1.zip")!))
try WorkbenchUpdateClient.validate(WorkbenchReleaseManifest(version: "0.6.6", build: "46", downloadURL: trustedDownload, sha256: String(repeating: "a", count: 64), releaseNotesURL: URL(string: "https://www.electricsheephq.com/evaos-workbench")!))

let broker = RuntimeSessionBrokerClient()
precondition(broker.endpoint.absoluteString == "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/desktop-runtime-session")
let macControl = CustomerMacControlClient()
precondition(macControl.endpoint.absoluteString == "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/customer-mac-control")

let smokeKeychain = KeychainSessionStore(service: "com.electricsheephq.EvaDesktop.smoke.\(UUID().uuidString)")
precondition((try? smokeKeychain.load(allowUserInteraction: false)) == nil)

let encodedLaunch = try JSONEncoder().encode(RuntimeLaunchRequest(customerId: "golden", runtime: .liveBrowser))
let launchJSON = String(data: encodedLaunch, encoding: .utf8) ?? ""
precondition(launchJSON.contains("\"action\":\"runtime_launch\""))
precondition(launchJSON.contains("\"customer_id\":\"golden\""))
precondition(launchJSON.contains("\"runtime\":\"browser\""))
precondition(!launchJSON.contains("customerId"))

let encodedOpenDesignLaunch = try JSONEncoder().encode(RuntimeLaunchRequest(customerId: "golden", runtime: .openDesign))
let openDesignLaunchJSON = String(data: encodedOpenDesignLaunch, encoding: .utf8) ?? ""
precondition(openDesignLaunchJSON.contains("\"runtime\":\"opendesign\""))

let encodedCreativeStudioLaunch = try JSONEncoder().encode(RuntimeLaunchRequest(customerId: "golden", runtime: .creativeStudio))
let creativeStudioLaunchJSON = String(data: encodedCreativeStudioLaunch, encoding: .utf8) ?? ""
precondition(creativeStudioLaunchJSON.contains("\"runtime\":\"creative_studio\""))

let encodedRuntimeStatus = try JSONEncoder().encode(RuntimeStatusRequest(customerId: "golden", runtime: .liveBrowser))
let runtimeStatusJSON = String(data: encodedRuntimeStatus, encoding: .utf8) ?? ""
precondition(runtimeStatusJSON.contains("\"action\":\"runtime_status\""))
precondition(runtimeStatusJSON.contains("\"runtime\":\"browser\""))

let encodedProviderProfiles = try JSONEncoder().encode(WorkbenchProviderProfilesRequest(customerId: "golden"))
let providerProfilesRequestJSON = String(data: encodedProviderProfiles, encoding: .utf8) ?? ""
precondition(providerProfilesRequestJSON.contains("\"action\":\"provider_profiles\""))
precondition(providerProfilesRequestJSON.contains("\"customer_id\":\"golden\""))

let encodedProviderSwitch = try JSONEncoder().encode(WorkbenchProviderActionRequest(action: "provider_switch", customerId: "golden", providerKey: .openAICodex))
let providerSwitchJSON = String(data: encodedProviderSwitch, encoding: .utf8) ?? ""
precondition(providerSwitchJSON.contains("\"action\":\"provider_switch\""))
precondition(providerSwitchJSON.contains("\"provider_key\":\"openai_codex\""))
precondition(!providerSwitchJSON.contains("access_token"))

let encodedProviderAuthStart = try JSONEncoder().encode(WorkbenchProviderActionRequest(action: "provider_auth_start", customerId: "golden", providerKey: .openAICodex))
let providerAuthStartJSON = String(data: encodedProviderAuthStart, encoding: .utf8) ?? ""
precondition(providerAuthStartJSON.contains("\"action\":\"provider_auth_start\""))
precondition(providerAuthStartJSON.contains("\"provider_key\":\"openai_codex\""))
precondition(!providerAuthStartJSON.contains("access_token"))

let encodedSharedBrowserOpen = try JSONEncoder().encode(SharedBrowserOpenURLRequest(customerId: "golden", url: URL(string: "https://chatgpt.com/codex?token=hidden#secret")!))
let sharedBrowserOpenJSON = String(data: encodedSharedBrowserOpen, encoding: .utf8) ?? ""
precondition(sharedBrowserOpenJSON.contains("\"action\":\"browser_open_url\""))
precondition(sharedBrowserOpenJSON.contains("\"customer_id\":\"golden\""))
precondition(sharedBrowserOpenJSON.contains("\"url\":\"https:\\/\\/chatgpt.com\\/codex\""))
precondition(!sharedBrowserOpenJSON.contains("hidden"))
precondition(!sharedBrowserOpenJSON.contains("secret"))

let encodedTargets = try JSONEncoder().encode(DesktopCustomerTargetsRequest())
let targetsRequestJSON = String(data: encodedTargets, encoding: .utf8) ?? ""
precondition(targetsRequestJSON.contains("\"action\":\"list_customer_targets\""))

let encodedRevoke = try JSONEncoder().encode(DesktopSessionRevokeRequest())
let revokeJSON = try JSONSerialization.jsonObject(with: encodedRevoke) as? [String: String]
precondition(revokeJSON?["action"] == "revoke_desktop_session")

let encodedDeviceCodeClaim = try JSONEncoder().encode(DesktopDeviceCodeClaimRequest(deviceCode: "ABCD-EFGH-IJKL"))
let deviceCodeClaimJSON = String(data: encodedDeviceCodeClaim, encoding: .utf8) ?? ""
precondition(deviceCodeClaimJSON.contains("\"action\":\"claim_desktop_device_code\""))
precondition(deviceCodeClaimJSON.contains("\"device_code\":\"ABCD-EFGH-IJKL\""))

let deviceCodeResponse = """
{"desktop_session":"eds_device","desktop_session_expires_at":"2026-05-20T10:48:51.123Z","email":"david@example.com"}
""".data(using: .utf8)!
let decodedDeviceCodeResponse = try EvaDesktopISO8601.decoder().decode(DesktopDeviceCodeClaimResponse.self, from: deviceCodeResponse)
precondition(decodedDeviceCodeResponse.session.accessToken == "eds_device")
precondition(decodedDeviceCodeResponse.session.userEmail == "david@example.com")

let encodedPairing = try JSONEncoder().encode(CustomerMacActionRequest(action: "create_enrollment", customerId: "golden", deviceName: "Test Mac", screenSharingOptIn: false))
let pairingJSON = String(data: encodedPairing, encoding: .utf8) ?? ""
precondition(pairingJSON.contains("\"action\":\"create_enrollment\""))
precondition(pairingJSON.contains("\"customer_id\":\"golden\""))
precondition(pairingJSON.contains("\"screen_sharing_opt_in\":false"))

let encodedCompletion = try JSONEncoder().encode(CustomerMacActionRequest(
    action: "complete_enrollment",
    enrollmentCode: "ABC123",
    deviceIdentifier: "mac-test",
    tailnetIp: "100.64.1.10",
    connectorUrl: "http://100.64.1.10:8765",
    connectorToken: "fixture-token-abcdefghijklmnopqrstuvwxyz"
))
let completionJSON = String(data: encodedCompletion, encoding: .utf8) ?? ""
precondition(completionJSON.contains("\"connector_url\":\"http:\\/\\/100.64.1.10:8765\""))
precondition(completionJSON.contains("\"connector_token\":\"fixture-token-abcdefghijklmnopqrstuvwxyz\""))

let fractionalResponse = """
{"launch_url":"https://browser-golden.ecs.electricsheephq.com/auth/callback?session=test","expires_at":"2026-05-20T10:48:51.123Z"}
""".data(using: .utf8)!
let decodedResponse = try EvaDesktopISO8601.decoder().decode(RuntimeLaunchResponse.self, from: fractionalResponse)
precondition(decodedResponse.expiresAt != nil)
precondition(EvaDesktopISO8601.parse("2026-05-20T10:48:51.123Z") != nil)
precondition(EvaDesktopISO8601.parse("2026-05-20T10:48:51Z") != nil)

let targetsResponse = """
{"roles":["admin","customer"],"is_operator":true,"default_customer_id":"golden","customers":[{"customer_id":"golden","display_name":"Golden","email":"admin@100yen.org","status":"active","health_status":"healthy","is_default":true}]}
""".data(using: .utf8)!
let decodedTargets = try JSONDecoder().decode(DesktopCustomerTargetsResponse.self, from: targetsResponse)
precondition(decodedTargets.isOperator)
precondition(decodedTargets.defaultCustomerId == "golden")
precondition(decodedTargets.customers.first?.displayName == "Golden")

let providerProfilesResponse = """
{"provider_profiles":[{"provider_key":"openai_codex","title":"OpenAI / Codex","subtitle":"Connect once","status":"connected","active":true,"raw_secrets_stored_in_workbench":false,"capabilities":["codex"],"usage_summary":"Ready","grant_handle":"evaos-grant-123","last_validated_at":"2026-05-23T10:00:00Z"}],"active_provider_key":"openai_codex","raw_secrets_stored_in_workbench":false}
""".data(using: .utf8)!
let decodedProviderProfiles = try EvaDesktopISO8601.decoder().decode(WorkbenchProviderProfilesResponse.self, from: providerProfilesResponse)
precondition(decodedProviderProfiles.profiles.first?.key == .openAICodex)
precondition(decodedProviderProfiles.profiles.first?.status == .connected)
precondition(decodedProviderProfiles.profiles.first?.hasConnectionProof == true)
precondition(decodedProviderProfiles.profiles.first?.rawSecretsStoredInWorkbench == false)
precondition(decodedProviderProfiles.activeProviderKey == .openAICodex)
precondition(decodedProviderProfiles.rawSecretsStoredInWorkbench == false)

let providerAuthStartResponse = """
{"provider_key":"openai_codex","status":"pending","connect_url":"https://browser-golden.ecs.electricsheephq.com/auth/callback?session=test","target_url":"https://chatgpt.com/codex","expires_at":"2026-05-23T10:30:00Z","instructions":"Complete Codex sign-in in Shared Browser.","provider_profiles":[{"provider_key":"openai_codex","title":"OpenAI / Codex","subtitle":"Connect once","status":"needs_login","active":false,"raw_secrets_stored_in_workbench":false,"capabilities":["codex"],"usage_summary":null,"last_validated_at":null}],"active_provider_key":null,"raw_secrets_stored_in_workbench":false}
""".data(using: .utf8)!
let decodedProviderAuthStart = try EvaDesktopISO8601.decoder().decode(WorkbenchProviderAuthStartResponse.self, from: providerAuthStartResponse)
precondition(decodedProviderAuthStart.providerKey == .openAICodex)
precondition(decodedProviderAuthStart.status == "pending")
precondition(decodedProviderAuthStart.connectURL.absoluteString.contains("browser-golden"))
precondition(decodedProviderAuthStart.targetURL?.absoluteString == "https://chatgpt.com/codex")
precondition(RuntimeDefinition.providerAuthRuntime(for: decodedProviderAuthStart.connectURL) == .liveBrowser)
precondition(RuntimeDefinition.providerAuthRuntime(for: URL(string: "https://browser-golden.ecs.electricsheephq.com/")!) == .liveBrowser)
precondition(RuntimeDefinition.providerAuthRuntime(for: URL(string: "https://shared-browser-golden.ecs.electricsheephq.com/")!) == .liveBrowser)
precondition(RuntimeDefinition.providerAuthRuntime(for: URL(string: "https://hermes-golden.ecs.electricsheephq.com/")!) == .liveBrowser)
precondition(decodedProviderAuthStart.instructions?.contains("Shared Browser") == true)
precondition(decodedProviderAuthStart.rawSecretsStoredInWorkbench == false)

let unverifiedProviderProfilesResponse = """
{"provider_profiles":[{"provider_key":"openai_codex","title":"OpenAI / Codex","subtitle":"Connect once","status":"connected","active":true,"raw_secrets_stored_in_workbench":false,"capabilities":["codex"],"usage_summary":"Ready"}],"active_provider_key":"openai_codex","raw_secrets_stored_in_workbench":false}
""".data(using: .utf8)!
let decodedUnverifiedProviderProfiles = try EvaDesktopISO8601.decoder().decode(WorkbenchProviderProfilesResponse.self, from: unverifiedProviderProfilesResponse)
precondition(decodedUnverifiedProviderProfiles.profiles.first?.hasConnectionProof == false)
precondition(WorkbenchProviderHubSummary.statusText(for: decodedUnverifiedProviderProfiles) == "Needs verification")

let needsLoginProviderProfilesResponse = """
{"provider_profiles":[{"provider_key":"openai_codex","title":"OpenAI / Codex","subtitle":"Connect once","status":"needs_login","active":false,"raw_secrets_stored_in_workbench":false,"capabilities":["codex"],"usage_summary":null,"last_validated_at":null}],"active_provider_key":null,"raw_secrets_stored_in_workbench":false}
""".data(using: .utf8)!
let decodedNeedsLoginProviderProfiles = try EvaDesktopISO8601.decoder().decode(WorkbenchProviderProfilesResponse.self, from: needsLoginProviderProfilesResponse)
precondition(WorkbenchProviderHubSummary.statusText(for: decodedNeedsLoginProviderProfiles) == "Needs login")
precondition(WorkbenchProviderHubSummary.statusText(for: decodedProviderProfiles) == "Ready")

let blockedProviderProfilesResponse = """
{"provider_profiles":[{"provider_key":"openai_codex","title":"OpenAI / Codex","subtitle":"Connect once","status":"connected","active":true,"raw_secrets_stored_in_workbench":true,"capabilities":["codex"],"usage_summary":"Ready","grant_handle":"evaos-grant-123","last_validated_at":"2026-05-23T10:00:00Z"}],"active_provider_key":"openai_codex","raw_secrets_stored_in_workbench":true}
""".data(using: .utf8)!
let decodedBlockedProviderProfiles = try EvaDesktopISO8601.decoder().decode(WorkbenchProviderProfilesResponse.self, from: blockedProviderProfilesResponse)
precondition(WorkbenchProviderHubSummary.statusText(for: decodedBlockedProviderProfiles) == "Blocked")

precondition(WorkbenchSetupCheckSummary.agentAccessText(connectorReady: true, macReady: true, iPhoneReady: true) == "Ready. Mac Access and iPhone Mirroring passed the local check.")
precondition(WorkbenchSetupCheckSummary.agentAccessText(connectorReady: true, macReady: true, iPhoneReady: false) == "Ready. Mac Access passed. Connect iPhone Mirroring when you want phone actions.")
precondition(WorkbenchSetupCheckSummary.agentAccessText(connectorReady: true, macReady: false, iPhoneReady: true) == "Blocked. Turn on Mac Access and approve Accessibility and Screen Recording.")
precondition(WorkbenchSetupCheckSummary.agentAccessText(connectorReady: false, macReady: true, iPhoneReady: false) == "Blocked. Turn on Mac Access and approve Accessibility and Screen Recording.")

let runtimeStatusResponse = """
{"runtime_key":"browser","display_label":"Shared Browser","status":"enabled","health_summary":"Ready","last_checked_at":"2026-05-23T10:00:00Z","room_id":"room-1","current_url":"https://example.com/path","owner":"golden","auth_needed":false,"captcha_needed":false,"last_activity_at":"2026-05-23T10:01:00Z"}
""".data(using: .utf8)!
let decodedRuntimeStatus = try EvaDesktopISO8601.decoder().decode(RuntimeStatusResponse.self, from: runtimeStatusResponse)
precondition(decodedRuntimeStatus.runtimeKey == .liveBrowser)
precondition(decodedRuntimeStatus.displayLabel == "Shared Browser")
precondition(decodedRuntimeStatus.roomId == "room-1")
precondition(decodedRuntimeStatus.currentUrl == "https://example.com/path")
let runtimeMissionCard = WorkbenchMissionCardDeriver.runtimeCard(
    definition: RuntimeDefinition.definition(for: .liveBrowser),
    status: decodedRuntimeStatus,
    localURLLoaded: true
)
precondition(runtimeMissionCard.id == "runtime-browser")
precondition(runtimeMissionCard.attentionState == .active)
precondition(runtimeMissionCard.sourcePointer == "broker:runtime_status:browser")

let degradedRuntimeStatusResponse = """
{"runtime_key":"openclaw","display_label":"evaOS (OpenClaw)","status":"degraded","health_summary":"Needs login","last_checked_at":"2026-05-23T10:00:00Z","auth_needed":true,"captcha_needed":false}
""".data(using: .utf8)!
let decodedDegradedRuntimeStatus = try EvaDesktopISO8601.decoder().decode(RuntimeStatusResponse.self, from: degradedRuntimeStatusResponse)
let degradedMissionCard = WorkbenchMissionCardDeriver.runtimeCard(
    definition: RuntimeDefinition.definition(for: .openclaw),
    status: decodedDegradedRuntimeStatus,
    localURLLoaded: false
)
precondition(degradedMissionCard.attentionState == .needsAttention)
precondition(degradedMissionCard.nextAction.contains("auth handoff"))

let queueRaw = """
{"ok":true,"data":{"events":[{"queue_id":"queue-approval","timestamp":"2026-05-28T01:00:00Z","kind":"approval_needed","source_audit_id":"audit-approval","message":"Approve visible action"},{"queue_id":"queue-attention","timestamp":"2026-05-28T01:01:00Z","kind":"attention","source_audit_id":"audit-attention"},{"queue_id":"queue-done","timestamp":"2026-05-28T01:02:00Z","kind":"done","source_audit_id":"audit-done"},{"queue_id":"queue-error","timestamp":"2026-05-28T01:03:00Z","kind":"error","source_audit_id":"audit-error"},{"queue_id":"queue-idle","timestamp":"2026-05-28T01:04:00Z","kind":"idle","source_audit_id":"audit-idle"}]}}
"""
let queueCards = WorkbenchMissionCardDeriver.queueCards(from: queueRaw)
precondition(queueCards.count == 5)
precondition(queueCards[0].attentionState == .needsAttention)
precondition(queueCards[0].auditId == "audit-approval")
precondition(queueCards[1].attentionState == .needsAttention)
precondition(queueCards[2].attentionState == .done)
precondition(queueCards[3].attentionState == .needsAttention)
precondition(queueCards[4].attentionState == .idle)
precondition(queueCards[4].sourcePointer == "queue:queue-idle")

let auditRaw = """
{"ok":true,"data":{"records":[{"audit_id":"audit-ok","timestamp":"2026-05-28T01:10:00Z","command":"status","ok":true},{"audit_id":"audit-failed","timestamp":"2026-05-28T01:11:00Z","command":"codex.app_server.status","ok":false}]}}
"""
let auditCards = WorkbenchMissionCardDeriver.auditCards(from: auditRaw)
precondition(auditCards.count == 2)
precondition(auditCards[0].sourcePointer == "audit:audit-ok")
precondition(auditCards[1].attentionState == .needsAttention)

let codexStatusRaw = """
{"ok":true,"audit_id":"audit-codex-status","data":{"available":true,"read_only":true}}
"""
let codexRemoteRaw = """
{"ok":true,"data":{"remote_control_command":{"supported":true},"daemon":{"version_available":true},"safety":{"read_only_probe":true}}}
"""
let codexThreadsRaw = """
{"ok":true,"audit_id":"audit-codex-threads","data":{"threads":[{"id":"t1","title":"Release handoff","updated_at":"2026-05-28T01:20:00Z"}],"count":1}}
"""
let codexCards = WorkbenchMissionCardDeriver.codexCards(statusRaw: codexStatusRaw, remoteRaw: codexRemoteRaw, threadsRaw: codexThreadsRaw)
precondition(codexCards.count == 2)
precondition(codexCards[0].attentionState == .active)
precondition(codexCards[0].auditId == "audit-codex-status")
precondition(codexCards[1].attentionState == .active)
precondition(codexCards[1].sourcePointer == "bridge:codex.app_server.threads")

let malformedCards = WorkbenchMissionCardDeriver.queueCards(from: "{")
precondition(malformedCards.count == 1)
precondition(malformedCards[0].attentionState == .needsAttention)
precondition(malformedCards[0].sourcePointer == "bridge:queue.list")

let callbackURL = URL(string: "evaos://auth/callback?desktop_session=eds_test&desktop_session_expires_at=2026-05-20T10:48:51.123Z&email=admin%40100yen.org")!
let callbackSession = try DesktopSessionCallbackParser.parse(callbackURL)
precondition(callbackSession.accessToken == "eds_test")
precondition(callbackSession.userEmail == "admin@100yen.org")
let expectedCallbackExpiry = EvaDesktopISO8601.parse("2026-05-20T10:48:51.123Z")
precondition(expectedCallbackExpiry != nil)
precondition(callbackSession.expiresAt != nil)
precondition(abs(callbackSession.expiresAt!.timeIntervalSince(expectedCallbackExpiry!)) < 0.001)

let loopbackCallbackURL = URL(string: "http://127.0.0.1:49152/auth/callback?desktop_session=eds_loopback&desktop_session_expires_at=2026-05-20T10:48:51.123Z&email=david%40example.com")!
let loopbackCallbackSession = try DesktopSessionCallbackParser.parse(loopbackCallbackURL)
precondition(loopbackCallbackSession.accessToken == "eds_loopback")
precondition(loopbackCallbackSession.userEmail == "david@example.com")
precondition(loopbackCallbackSession.expiresAt != nil)

let fragmentCallbackURL = URL(string: "evaos://auth/callback#desktop_session=eds_fragment&expires_at=2026-05-20T10:48:51Z")!
let fragmentCallbackSession = try DesktopSessionCallbackParser.parse(fragmentCallbackURL)
precondition(fragmentCallbackSession.accessToken == "eds_fragment")
precondition(fragmentCallbackSession.expiresAt != nil)

print("EvaDesktopCoreSmoke passed")
