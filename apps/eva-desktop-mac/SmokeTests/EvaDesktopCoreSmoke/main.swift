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
    (.liveBrowser, "https://browser-golden.ecs.electricsheephq.com/")
]

for (runtime, url) in expected {
    precondition(resolver.fallbackURL(for: runtime, customerId: "golden").absoluteString == url)
}

print("EvaDesktopCoreSmoke passed")
