import EvaDesktopCore
import Foundation

let resolver = RuntimeURLResolver()

precondition(resolver.sanitizedCustomerId(" Jackie David ") == "jackie-david")
precondition(resolver.sanitizedCustomerId("David_Poku!") == "david-poku")
precondition(resolver.sanitizedCustomerId("") == "golden")

precondition(RuntimeDefinition.isBrokeredRuntime(.openclaw))
precondition(RuntimeDefinition.isBrokeredRuntime(.terminal))
precondition(!RuntimeDefinition.isBrokeredRuntime(.openDesign))
precondition(RuntimeDefinition.definition(for: .openDesign).availability == .comingSoon)

let broker = RuntimeSessionBrokerClient()
precondition(broker.endpoint.absoluteString == "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/desktop-runtime-session")

let encodedLaunch = try JSONEncoder().encode(RuntimeLaunchRequest(customerId: "golden", runtime: .liveBrowser))
let launchJSON = String(data: encodedLaunch, encoding: .utf8) ?? ""
precondition(launchJSON.contains("\"action\":\"runtime_launch\""))
precondition(launchJSON.contains("\"customer_id\":\"golden\""))
precondition(launchJSON.contains("\"runtime\":\"browser\""))
precondition(!launchJSON.contains("customerId"))

let encodedRevoke = try JSONEncoder().encode(DesktopSessionRevokeRequest())
let revokeJSON = try JSONSerialization.jsonObject(with: encodedRevoke) as? [String: String]
precondition(revokeJSON?["action"] == "revoke_desktop_session")

let fractionalResponse = """
{"launch_url":"https://browser-golden.ecs.electricsheephq.com/auth/callback?session=test","expires_at":"2026-05-20T10:48:51.123Z"}
""".data(using: .utf8)!
let decodedResponse = try EvaDesktopISO8601.decoder().decode(RuntimeLaunchResponse.self, from: fractionalResponse)
precondition(decodedResponse.expiresAt != nil)
precondition(EvaDesktopISO8601.parse("2026-05-20T10:48:51.123Z") != nil)
precondition(EvaDesktopISO8601.parse("2026-05-20T10:48:51Z") != nil)

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
