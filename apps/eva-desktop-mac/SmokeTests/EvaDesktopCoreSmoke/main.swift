import EvaDesktopCore
import Foundation

let resolver = RuntimeURLResolver()

precondition(resolver.sanitizedCustomerId(" Jackie David ") == "jackie-david")
precondition(resolver.sanitizedCustomerId("David_Poku!") == "david-poku")
precondition(resolver.sanitizedCustomerId("") == "golden")

let expected: [(RuntimeKey, String)] = [
    (.openclaw, "https://openclaw-golden.ecs.electricsheephq.com/ui/"),
    (.hermes, "https://hermes-golden.ecs.electricsheephq.com/"),
    (.missionControl, "https://paperclip-golden.ecs.electricsheephq.com/"),
    (.liveBrowser, "https://browser-golden.ecs.electricsheephq.com/"),
    (.terminal, "https://www.electricsheephq.com/dashboard/workspace?customer_id=golden&runtime=terminal"),
    (.openDesign, "https://www.electricsheephq.com/dashboard/opendesign?customer_id=golden&runtime=opendesign")
]

for (runtime, url) in expected {
    precondition(resolver.fallbackURL(for: runtime, customerId: "golden").absoluteString == url)
}

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

print("EvaDesktopCoreSmoke passed")
