import EvaDesktopCore
import Foundation

let resolver = RuntimeURLResolver()

precondition(AppBrand.visibleName == "evaOS Workbench")
precondition(AppBrand.runtimeSectionTitle == "Gateways")
precondition(AppBrand.signedOutStatus == "Sign in to launch evaOS gateways")
precondition(AppBrand.bundleDisplayName == "evaOS Workbench")

precondition(resolver.sanitizedCustomerId(" Jackie David ") == "jackie-david")
precondition(resolver.sanitizedCustomerId("David_Poku!") == "david-poku")
precondition(resolver.sanitizedCustomerId("") == "golden")

precondition(RuntimeDefinition.isBrokeredRuntime(.openclaw))
precondition(RuntimeDefinition.isBrokeredRuntime(.terminal))
precondition(!RuntimeDefinition.isBrokeredRuntime(.openDesign))
precondition(RuntimeDefinition.definition(for: .openDesign).availability == .comingSoon)
precondition(RuntimeDefinition.definition(for: .openclaw).title == "evaOS (OpenClaw)")

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

let encodedTargets = try JSONEncoder().encode(DesktopCustomerTargetsRequest())
let targetsRequestJSON = String(data: encodedTargets, encoding: .utf8) ?? ""
precondition(targetsRequestJSON.contains("\"action\":\"list_customer_targets\""))

let encodedRevoke = try JSONEncoder().encode(DesktopSessionRevokeRequest())
let revokeJSON = try JSONSerialization.jsonObject(with: encodedRevoke) as? [String: String]
precondition(revokeJSON?["action"] == "revoke_desktop_session")

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

let callbackURL = URL(string: "evaos://auth/callback?desktop_session=eds_test&desktop_session_expires_at=2026-05-20T10:48:51.123Z&email=admin%40100yen.org")!
let callbackSession = try DesktopSessionCallbackParser.parse(callbackURL)
precondition(callbackSession.accessToken == "eds_test")
precondition(callbackSession.userEmail == "admin@100yen.org")
let expectedCallbackExpiry = EvaDesktopISO8601.parse("2026-05-20T10:48:51.123Z")
precondition(expectedCallbackExpiry != nil)
precondition(callbackSession.expiresAt != nil)
precondition(abs(callbackSession.expiresAt!.timeIntervalSince(expectedCallbackExpiry!)) < 0.001)

let fragmentCallbackURL = URL(string: "evaos://auth/callback#desktop_session=eds_fragment&expires_at=2026-05-20T10:48:51Z")!
let fragmentCallbackSession = try DesktopSessionCallbackParser.parse(fragmentCallbackURL)
precondition(fragmentCallbackSession.accessToken == "eds_fragment")
precondition(fragmentCallbackSession.expiresAt != nil)

print("EvaDesktopCoreSmoke passed")
