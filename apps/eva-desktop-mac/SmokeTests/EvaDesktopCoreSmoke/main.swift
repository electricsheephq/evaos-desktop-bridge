import EvaDesktopCore
import CryptoKit
import Foundation

func isoDate(_ value: String) -> Date {
    EvaDesktopISO8601.parse(value)!
}

final class SmokeURLProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    static var seenRequests: [URLRequest] = []

    override class func canInit(with request: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        do {
            SmokeURLProtocol.seenRequests.append(request)
            guard let handler = SmokeURLProtocol.handler else {
                throw RuntimeSessionBrokerError.invalidResponse
            }
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}

    static func bodyData(from request: URLRequest) -> Data {
        if let body = request.httpBody {
            return body
        }
        guard let stream = request.httpBodyStream else {
            return Data()
        }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count > 0 {
                data.append(buffer, count: count)
            } else {
                break
            }
        }
        return data
    }
}

let resolver = RuntimeURLResolver()

precondition(AppBrand.visibleName == "evaOS Workbench")
precondition(AppBrand.runtimeSectionTitle == "Gateways")
precondition(AppBrand.signedOutStatus == "Sign in to launch evaOS gateways")
precondition(AppBrand.bundleDisplayName == "evaOS Workbench")
precondition(AppBrand.defaultUpdateManifestURL == "https://www.electricsheephq.com/evaos-workbench/updates.json")

precondition(WorkbenchFeatureFlagKey.allCases.map(\.rawValue) == [
    "providers_hub",
    "shared_browser_2",
    "session_center",
    "approval_center",
    "creative_studio"
])
let featureFlags = WorkbenchFeatureFlags()
precondition(!featureFlags.isEnabled(.providersHub))
precondition(!featureFlags.isEnabled(.sharedBrowser2))
precondition(!featureFlags.isEnabled(.sessionCenter))
precondition(!featureFlags.isEnabled(.approvalCenter))
precondition(!featureFlags.isEnabled(.creativeStudio))
precondition(featureFlags.enabledKeys == [])
precondition(featureFlags.storedValue(for: .creativeStudio) == false)
precondition(featureFlags.storedValue(for: .providersHub) == false)
precondition(featureFlags.storedValue(for: .sharedBrowser2) == false)
precondition(featureFlags.storedValue(for: .sessionCenter) == false)
precondition(featureFlags.storedValue(for: .approvalCenter) == false)
precondition(WorkbenchFeatureFlags.descriptors.map(\.key) == WorkbenchFeatureFlagKey.allCases)
precondition(WorkbenchFeatureFlags.descriptors.allSatisfy { !$0.defaultEnabled })
precondition(WorkbenchFeatureFlags.descriptors.map(\.dashboardEnvironmentKey) == [
    "VITE_EVAOS_PROVIDERS_HUB",
    "VITE_EVAOS_SHARED_BROWSER_2",
    "VITE_EVAOS_SESSION_CENTER",
    "VITE_EVAOS_APPROVAL_CENTER",
    "VITE_EVAOS_CREATIVE_STUDIO"
])
precondition(WorkbenchFeatureFlagKey.providersHub.descriptor.primaryIssue == "#96")
precondition(WorkbenchFeatureFlagKey.sharedBrowser2.descriptor.primaryIssue == "#97")
precondition(WorkbenchFeatureFlagKey.sessionCenter.descriptor.primaryIssue == "#100")
precondition(WorkbenchFeatureFlagKey.approvalCenter.descriptor.primaryIssue == "#144")
precondition(WorkbenchFeatureFlagKey.creativeStudio.descriptor.primaryIssue == "#102")
precondition(WorkbenchFeatureFlagKey.providersHub.descriptor.navigationPlacement == "Settings")
precondition(WorkbenchFeatureFlagKey.sessionCenter.descriptor.navigationPlacement == "Workspace")
precondition(WorkbenchFeatureFlagKey.approvalCenter.descriptor.navigationPlacement == "Workspace")
precondition(WorkbenchFeatureFlagKey.creativeStudio.descriptor.navigationPlacement == "Gateways")
precondition(WorkbenchFeatureFlagKey.sharedBrowser2.descriptor.rollbackAction.contains("base Shared Browser gateway visible"))
precondition(WorkbenchFeatureFlagKey.providersHub.descriptor.publicCopy.contains("without raw secrets"))
precondition(WorkbenchFeatureFlagKey.sessionCenter.descriptor.rolloutCriteria.contains("dashboard parity"))
precondition(WorkbenchFeatureFlagKey.approvalCenter.descriptor.publicCopy.contains("actual destination"))

let featureFlagDefaults = UserDefaults(suiteName: "EvaDesktopCoreSmoke.feature-flags.\(UUID().uuidString)")!
featureFlagDefaults.set(false, forKey: WorkbenchFeatureFlagKey.providersHub.userDefaultsKey)
featureFlagDefaults.set(true, forKey: WorkbenchFeatureFlagKey.sharedBrowser2.userDefaultsKey)
featureFlagDefaults.set(true, forKey: WorkbenchFeatureFlagKey.approvalCenter.userDefaultsKey)
featureFlagDefaults.set(false, forKey: WorkbenchFeatureFlagKey.creativeStudio.userDefaultsKey)
let configuredFeatureFlags = WorkbenchFeatureFlags(userDefaults: featureFlagDefaults)
precondition(!configuredFeatureFlags.isEnabled(.providersHub))
precondition(configuredFeatureFlags.isEnabled(.sharedBrowser2))
precondition(!configuredFeatureFlags.isEnabled(.sessionCenter))
precondition(configuredFeatureFlags.isEnabled(.approvalCenter))
precondition(!configuredFeatureFlags.isEnabled(.creativeStudio))
let providerCatalogKeys = WorkbenchProviderCatalog.profiles.map(\.key)
precondition(providerCatalogKeys == [.openAICodex, .googleWorkspace, .slack, .notion, .linear, .github])
precondition(WorkbenchProviderCatalog.profiles.allSatisfy { !$0.rawSecretsStoredInWorkbench })
precondition(WorkbenchProviderCatalog.profile(for: .googleWorkspace)?.capabilities.contains("Gmail context") == true)
precondition(WorkbenchProviderCatalog.profiles.first { $0.key == .openAICodex }?.readiness == .needsLogin)
precondition(WorkbenchProviderCatalog.profiles.filter { $0.key != .openAICodex }.allSatisfy { $0.readiness == .planned })
precondition(WorkbenchProviderCatalog.defaultStates.map(\.key) == providerCatalogKeys)
precondition(WorkbenchProviderCatalog.defaultStates.allSatisfy { !$0.rawSecretsStoredInWorkbench })
precondition(WorkbenchProviderCatalog.defaultStates.first { $0.key == .openAICodex }?.status == .needsLogin)
precondition(WorkbenchProviderCatalog.defaultStates.filter { $0.key != .openAICodex }.allSatisfy { $0.status == .planned })

let emailApproval = WorkbenchApprovalRequest.pending(
    id: "approval-email-1",
    ownerID: "andrew-main",
    agentID: "email-sorter-2026-05",
    toolName: "gmail.send",
    riskClass: .warning,
    actionPayload: [
        "display_name": "CEO <ceo@electricsheephq.com>",
        "recipient_email": "attacker@evil.example",
        "subject": "Wire instructions",
        "body": String(repeating: "Confirm destination before sending. ", count: 20)
    ],
    allowAlwaysSupported: true,
    createdAt: "2026-05-29T21:20:00Z",
    sourcePointer: "approval:approval-email-1"
)
precondition(emailApproval.destinationPreview.kind == .emailRecipient)
precondition(emailApproval.destinationPreview.primary == "attacker@evil.example")
precondition(!emailApproval.destinationPreview.primary.contains("ceo@electricsheephq.com"))
precondition(emailApproval.destinationPreview.secondary == "Wire instructions")
precondition(emailApproval.destinationPreview.bodyExcerpt?.count == 220)
precondition(emailApproval.isActionable)
precondition(emailApproval.canAllowAlways)
precondition(emailApproval.attentionState == .needsAttention)
precondition(emailApproval.availableDecisions == [.allowOnce, .allowAlways, .deny])

let malformedApproval = WorkbenchApprovalRequest.pending(
    id: "approval-email-2",
    ownerID: "andrew-main",
    agentID: "email-sorter-2026-05",
    toolName: "gmail.send",
    riskClass: .critical,
    actionPayload: ["display_name": "Trusted CFO"],
    createdAt: "2026-05-29T21:21:00Z",
    sourcePointer: "approval:approval-email-2"
)
precondition(malformedApproval.destinationPreview.kind == .missingDestination)
precondition(!malformedApproval.isActionable)
precondition(malformedApproval.nextAction.contains("missing actual destination"))

let ambiguousRecipientApproval = WorkbenchApprovalRequest.pending(
    id: "approval-email-ambiguous",
    ownerID: "andrew-main",
    agentID: "email-sorter-2026-05",
    toolName: "gmail.send",
    riskClass: .critical,
    actionPayload: ["to": "Trusted CFO", "recipient": "CEO <ceo@electricsheephq.com>"],
    createdAt: "2026-05-29T21:21:30Z",
    sourcePointer: "approval:approval-email-ambiguous"
)
precondition(ambiguousRecipientApproval.destinationPreview.kind == .missingDestination)
precondition(!ambiguousRecipientApproval.isActionable)

let displayOnlyNestedRecipientApprovalJSON = """
{
  "id": "approval-display-only-nested",
  "owner_id": "andrew-main",
  "agent_id": "email-sorter-2026-05",
  "tool_name": "gmail.send",
  "risk_class": "critical",
  "allow_always_supported": true,
  "action_payload": {
    "to": {
      "display": "Trusted CFO <cfo@electricsheephq.com>"
    },
    "subject": "Display-only recipient"
  },
  "created_at": "2026-05-30T03:02:00Z"
}
"""
let displayOnlyNestedRecipientApproval = try JSONDecoder().decode(WorkbenchApprovalRequest.self, from: Data(displayOnlyNestedRecipientApprovalJSON.utf8))
precondition(displayOnlyNestedRecipientApproval.destinationPreview.kind == .missingDestination)
precondition(!displayOnlyNestedRecipientApproval.isActionable)

let urlApproval = WorkbenchApprovalRequest.pending(
    id: "approval-url-1",
    ownerID: "andrew-main",
    agentID: "research-agent",
    toolName: "browser.fetch",
    riskClass: .info,
    actionPayload: [
        "display_url": "https://electricsheephq.com",
        "url": "https://evil.example/login?next=/oauth"
    ],
    createdAt: "2026-05-29T21:22:00Z",
    sourcePointer: "approval:approval-url-1"
)
precondition(urlApproval.destinationPreview.kind == .url)
precondition(urlApproval.destinationPreview.primary == "https://evil.example/login?next=/oauth")
precondition(urlApproval.destinationPreview.secondary == "evil.example")

let brokerHrefApproval = WorkbenchApprovalRequest.pending(
    id: "approval-url-href",
    ownerID: "andrew-main",
    agentID: "research-agent",
    toolName: "browser.open",
    riskClass: .warning,
    actionPayload: ["href": "https://docs.example.com/oauth"],
    createdAt: "2026-05-29T21:22:05Z",
    sourcePointer: "approval:approval-url-href"
)
precondition(brokerHrefApproval.destinationPreview.kind == .url)
precondition(brokerHrefApproval.destinationPreview.secondary == "docs.example.com")

let brokerMessageApproval = WorkbenchApprovalRequest.pending(
    id: "approval-message-channel",
    ownerID: "andrew-main",
    agentID: "slack-agent",
    toolName: "slack.message",
    riskClass: .warning,
    actionPayload: ["channel": "C12345", "message": "Heads up"],
    createdAt: "2026-05-29T21:22:08Z",
    sourcePointer: "approval:approval-message-channel"
)
precondition(brokerMessageApproval.destinationPreview.kind == .messageRecipient)
precondition(brokerMessageApproval.destinationPreview.primary == "C12345")

let credentialURLApproval = WorkbenchApprovalRequest.pending(
    id: "approval-url-credentials",
    ownerID: "andrew-main",
    agentID: "research-agent",
    toolName: "browser.fetch",
    riskClass: .critical,
    actionPayload: ["url": "https://trusted.example@evil.example/login"],
    createdAt: "2026-05-29T21:22:15Z",
    sourcePointer: "approval:approval-url-credentials"
)
precondition(credentialURLApproval.destinationPreview.kind == .url)
precondition(credentialURLApproval.destinationPreview.secondary == "evil.example")
precondition(credentialURLApproval.destinationPreview.warning?.contains("embedded credentials") == true)
precondition(!credentialURLApproval.canAllowAlways)

let malformedURLApproval = WorkbenchApprovalRequest.pending(
    id: "approval-url-2",
    ownerID: "andrew-main",
    agentID: "research-agent",
    toolName: "browser.fetch",
    riskClass: .critical,
    actionPayload: ["url": "/login?next=/oauth"],
    createdAt: "2026-05-29T21:22:30Z",
    sourcePointer: "approval:approval-url-2"
)
precondition(malformedURLApproval.destinationPreview.kind == .missingDestination)
precondition(!malformedURLApproval.isActionable)

let curlToolApproval = WorkbenchApprovalRequest.pending(
    id: "approval-curl-1",
    ownerID: "andrew-main",
    agentID: "diagnostics-agent",
    toolName: "curl.status",
    riskClass: .info,
    actionPayload: ["url": "https://evil.example/status"],
    createdAt: "2026-05-29T21:22:45Z",
    sourcePointer: "approval:approval-curl-1"
)
precondition(curlToolApproval.destinationPreview.kind == .missingDestination)

precondition(WorkbenchApprovalCenterSummary.statusText(for: [emailApproval, urlApproval]) == "2 pending approvals")
precondition(WorkbenchApprovalCenterSummary.statusText(for: []) == "No pending approvals")
precondition(WorkbenchApprovalDecision.allowOnce.rawValue == "allow-once")
precondition(WorkbenchApprovalDecision.allowAlways.defaultScope == .thisAgent)
let encodedApprovalDecision = try JSONEncoder().encode(WorkbenchApprovalDecisionRequest(decision: .allowAlways))
let approvalDecisionJSON = String(data: encodedApprovalDecision, encoding: .utf8) ?? ""
precondition(approvalDecisionJSON.contains("\"decision\":\"allow-always\""))
precondition(approvalDecisionJSON.contains("\"scope\":\"this-agent\""))

let brokerShapedApprovalJSON = """
{
  "id": "approval-broker-1",
  "owner_id": "andrew-main",
  "agent_id": "email-sorter-2026-05",
  "tool_name": "gmail.send",
  "risk_class": "warning",
  "action_payload": {
    "recipient_email": "outside@example.com",
    "subject": "Broker-shaped request"
  },
  "created_at": "2026-05-29T21:23:00Z",
  "source_pointer": "approval:approval-broker-1",
  "audit_id": "audit-approval-broker-1"
}
"""
let brokerShapedApproval = try JSONDecoder().decode(WorkbenchApprovalRequest.self, from: Data(brokerShapedApprovalJSON.utf8))
precondition(brokerShapedApproval.destinationPreview.kind == .emailRecipient)
precondition(brokerShapedApproval.destinationPreview.primary == "outside@example.com")
precondition(brokerShapedApproval.auditId == "audit-approval-broker-1")

let brokerPendingResponseJSON = """
{
  "ok": true,
  "owner_id": "andrew-main",
  "requests": [
    {
      "id": "00000000-0000-4000-8000-000000000001",
      "owner_id": "andrew-main",
      "agent_id": "email-sorter-2026-05",
      "tool_name": "gmail.send",
      "risk_class": "critical",
      "action_payload": {
        "to": [{"name": "Trusted CFO", "email": "attacker@example.net"}],
        "subject": "Wire instructions",
        "body": "Please send the payment details."
      },
      "destination_preview": {
        "kind": "email",
        "to": ["trusted@example.com"],
        "subject": "Safe-looking subject"
      },
      "created_at": "2026-05-30T03:00:00Z",
      "expires_at": "2026-05-30T03:15:00Z"
    }
  ]
}
"""
let brokerPendingResponse = try JSONDecoder().decode(WorkbenchApprovalRequestsResponse.self, from: Data(brokerPendingResponseJSON.utf8))
let brokerNestedApproval = brokerPendingResponse.requests[0]
precondition(brokerNestedApproval.destinationPreview.kind == .emailRecipient)
precondition(brokerNestedApproval.destinationPreview.primary == "attacker@example.net")
precondition(brokerNestedApproval.destinationPreview.secondary == "Wire instructions")
precondition(brokerNestedApproval.actionPayload["recipient_email"] == "attacker@example.net")
precondition(brokerNestedApproval.sourcePointer == "approval:00000000-0000-4000-8000-000000000001")
precondition(brokerNestedApproval.expiresAt == "2026-05-30T03:15:00Z")
precondition(brokerNestedApproval.expirationText(now: isoDate("2026-05-30T03:10:00Z")) == "Expires in 5 min")
let displayOnlyBrokerNestedApproval = brokerNestedApproval.displayOnly()
precondition(displayOnlyBrokerNestedApproval.actionPayload.isEmpty)
precondition(displayOnlyBrokerNestedApproval.destinationPreview.primary == "attacker@example.net")
precondition(displayOnlyBrokerNestedApproval.expiresAt == "2026-05-30T03:15:00Z")

let nestedURLOnlyApprovalJSON = """
{
  "id": "approval-nested-url-only",
  "owner_id": "andrew-main",
  "agent_id": "research-agent",
  "tool_name": "browser.open",
  "risk_class": "critical",
  "action_payload": {
    "metadata": {
      "url": "https://evil.example/hidden"
    }
  },
  "created_at": "2026-05-30T03:03:00Z"
}
"""
let nestedURLOnlyApproval = try JSONDecoder().decode(WorkbenchApprovalRequest.self, from: Data(nestedURLOnlyApprovalJSON.utf8))
precondition(nestedURLOnlyApproval.destinationPreview.kind == .missingDestination)
precondition(nestedURLOnlyApproval.actionPayload["metadata_url"] == "https://evil.example/hidden")

let approvalHTTPConfig = URLSessionConfiguration.ephemeral
approvalHTTPConfig.protocolClasses = [SmokeURLProtocol.self]
let approvalHTTPClient = RuntimeSessionBrokerClient(
    endpoint: URL(string: "https://session.example.test/desktop-runtime-session")!,
    capabilityEndpoint: URL(string: "https://supabase.example.test/functions/v1/cortex-proxy/")!,
    urlSession: URLSession(configuration: approvalHTTPConfig)
)
let approvalHTTPSession = DesktopSession(
    accessToken: "desktop-token",
    expiresAt: Date(timeIntervalSinceNow: 3600)
)
let approvalRowJSON = """
{
  "id": "00000000-0000-4000-8000-000000000001",
  "owner_id": "andrew-main",
  "agent_id": "email-sorter-2026-05",
  "tool_name": "gmail.send",
  "risk_class": "critical",
  "allow_always_supported": true,
  "action_payload": {
    "to": [{"name": "Trusted CFO", "email": "attacker@example.net"}],
    "subject": "Wire instructions"
  },
  "created_at": "2026-05-30T03:00:00Z"
}
"""
SmokeURLProtocol.seenRequests = []
SmokeURLProtocol.handler = { request in
    precondition(request.value(forHTTPHeaderField: "Authorization") == "Bearer desktop-token")
    precondition(request.value(forHTTPHeaderField: "Accept") == "application/json")
    let url = request.url!
    let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
    precondition(request.httpMethod == "POST")
    precondition(url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) == "functions/v1/cortex-proxy")
    let proxyPayload = try! JSONSerialization.jsonObject(with: SmokeURLProtocol.bodyData(from: request)) as! [String: Any]
    if proxyPayload["method"] as? String == "GET" {
        precondition(proxyPayload["path"] as? String == "/api/v1/approvals/pending?limit=7")
        let body = """
        {"ok": true, "owner_id": "andrew-main", "requests": [\(approvalRowJSON)]}
        """
        return (response, Data(body.utf8))
    }
    precondition(proxyPayload["method"] as? String == "POST")
    precondition(proxyPayload["path"] as? String == "/api/v1/approvals/00000000-0000-4000-8000-000000000001/decide")
    let proxyBody = proxyPayload["body"] as! [String: Any]
    precondition(proxyBody["decision"] as? String == "allow-once")
    precondition(proxyBody["scope"] as? String == "this-call")
    return (response, Data(approvalRowJSON.utf8))
}
let pendingApprovalHTTPResponse = try await approvalHTTPClient.pendingApprovals(
    desktopSession: approvalHTTPSession,
    limit: 7
)
precondition(pendingApprovalHTTPResponse.requests.first?.destinationPreview.primary == "attacker@example.net")
precondition(pendingApprovalHTTPResponse.requests.first?.canAllowAlways == true)
let decidedApprovalHTTPResponse = try await approvalHTTPClient.decideApproval(
    approvalID: "00000000-0000-4000-8000-000000000001",
    decision: .allowOnce,
    desktopSession: approvalHTTPSession
)
precondition(decidedApprovalHTTPResponse.id == "00000000-0000-4000-8000-000000000001")
precondition(SmokeURLProtocol.seenRequests.map(\.httpMethod) == ["POST", "POST"])
SmokeURLProtocol.handler = nil

let spoofedPreviewJSON = """
{
  "id": "approval-spoofed-preview",
  "owner_id": "andrew-main",
  "agent_id": "email-sorter-2026-05",
  "tool_name": "gmail.send",
  "risk_class": "warning",
  "action_payload": {
    "recipient_email": "outside@example.com",
    "subject": "Broker-shaped request"
  },
  "destination_preview": {
    "kind": "email_recipient",
    "primary": "Trusted CFO",
    "secondary": "Safe-looking subject"
  },
  "created_at": "2026-05-29T21:24:00Z",
  "source_pointer": "approval:approval-spoofed-preview"
}
"""
let spoofedPreviewApproval = try JSONDecoder().decode(WorkbenchApprovalRequest.self, from: Data(spoofedPreviewJSON.utf8))
precondition(spoofedPreviewApproval.destinationPreview.kind == .emailRecipient)
precondition(spoofedPreviewApproval.destinationPreview.primary == "outside@example.com")
precondition(spoofedPreviewApproval.destinationPreview.secondary == "Broker-shaped request")

let awayNotificationPlan = WorkbenchApprovalNotificationPlanner.plan(
    requests: [brokerNestedApproval],
    previousPendingIDs: [],
    notifiedRequestIDs: [],
    approvalCenterVisible: false
)
precondition(awayNotificationPlan.notifications.count == 1)
precondition(awayNotificationPlan.notifications[0].requestID == "00000000-0000-4000-8000-000000000001")
precondition(awayNotificationPlan.notifications[0].title == "Approval needed: gmail.send")
precondition(awayNotificationPlan.notifications[0].body.contains("attacker@example.net"))
precondition(!awayNotificationPlan.notifications[0].body.contains("Wire instructions"))
precondition(awayNotificationPlan.pendingRequestIDs == ["00000000-0000-4000-8000-000000000001"])
precondition(awayNotificationPlan.notifiedRequestIDs == ["00000000-0000-4000-8000-000000000001"])

let duplicateAwayNotificationPlan = WorkbenchApprovalNotificationPlanner.plan(
    requests: [brokerNestedApproval],
    previousPendingIDs: awayNotificationPlan.pendingRequestIDs,
    notifiedRequestIDs: awayNotificationPlan.notifiedRequestIDs,
    approvalCenterVisible: false
)
precondition(duplicateAwayNotificationPlan.notifications.isEmpty)

let visibleNotificationPlan = WorkbenchApprovalNotificationPlanner.plan(
    requests: [emailApproval],
    previousPendingIDs: [],
    notifiedRequestIDs: [],
    approvalCenterVisible: true
)
precondition(visibleNotificationPlan.notifications.isEmpty)
precondition(visibleNotificationPlan.pendingRequestIDs == ["approval-email-1"])
precondition(visibleNotificationPlan.notifiedRequestIDs == ["approval-email-1"])

let clearedNotificationPlan = WorkbenchApprovalNotificationPlanner.plan(
    requests: [],
    previousPendingIDs: awayNotificationPlan.pendingRequestIDs,
    notifiedRequestIDs: awayNotificationPlan.notifiedRequestIDs,
    approvalCenterVisible: false
)
precondition(clearedNotificationPlan.notifications.isEmpty)
precondition(clearedNotificationPlan.pendingRequestIDs.isEmpty)
precondition(clearedNotificationPlan.notifiedRequestIDs.isEmpty)

let longDestinationApproval = WorkbenchApprovalRequest.pending(
    id: "approval-long-url",
    ownerID: "andrew-main",
    agentID: "browser-agent",
    toolName: "browser.fetch",
    riskClass: .warning,
    actionPayload: ["url": "https://example.com/" + String(repeating: "destination-", count: 20)],
    createdAt: "2026-05-30T03:04:00Z",
    sourcePointer: "approval:approval-long-url"
)
let longDestinationNotificationPlan = WorkbenchApprovalNotificationPlanner.plan(
    requests: [longDestinationApproval],
    previousPendingIDs: [],
    notifiedRequestIDs: [],
    approvalCenterVisible: false
)
precondition(longDestinationNotificationPlan.notifications[0].body.contains("..."))
precondition(longDestinationNotificationPlan.notifications[0].body.count < 180)

let expiringApproval = WorkbenchApprovalRequest.pending(
    id: "approval-expiring",
    ownerID: "andrew-main",
    agentID: "email-sorter-2026-05",
    toolName: "gmail.send",
    riskClass: .critical,
    actionPayload: ["to": "attacker@example.net"],
    createdAt: "2026-05-30T12:00:00Z",
    expiresAt: "2026-05-30T12:01:00Z",
    sourcePointer: "approval:approval-expiring",
    auditId: "audit-expiring"
)
precondition(expiringApproval.expirationText(now: isoDate("2026-05-30T12:00:30Z")) == "Expires in 30 sec")
precondition(expiringApproval.expirationText(now: isoDate("2026-05-30T12:02:00Z")) == "Expired")
precondition(expiringApproval.nextAction(now: isoDate("2026-05-30T12:00:30Z")).contains("expires soon"))
let fractionalExpiryApproval = WorkbenchApprovalRequest.pending(
    id: "approval-expiring-fractional",
    ownerID: "andrew-main",
    agentID: "email-sorter-2026-05",
    toolName: "gmail.send",
    riskClass: .critical,
    actionPayload: ["to": "operator@example.net"],
    createdAt: "2026-05-30T12:00:00.123Z",
    expiresAt: "2026-05-30T12:01:00.123Z",
    sourcePointer: "approval:approval-expiring-fractional",
    auditId: "audit-expiring-fractional"
)
precondition(fractionalExpiryApproval.expirationText(now: isoDate("2026-05-30T12:00:00.123Z")) == "Expires in 1 min")
let expiringNotificationPlan = WorkbenchApprovalNotificationPlanner.plan(
    requests: [expiringApproval],
    previousPendingIDs: ["approval-expiring"],
    notifiedRequestIDs: ["approval-expiring"],
    approvalCenterVisible: false,
    now: isoDate("2026-05-30T12:00:30Z")
)
precondition(expiringNotificationPlan.notifications.count == 1)
precondition(expiringNotificationPlan.notifications[0].notificationID == "approval-expiring:expiring")
precondition(expiringNotificationPlan.notifications[0].title == "Approval expiring: gmail.send")
precondition(expiringNotificationPlan.notifications[0].body.contains("30 sec"))
precondition(expiringNotificationPlan.notifiedRequestIDs.contains("approval-expiring:expiring"))
let duplicateExpiringNotificationPlan = WorkbenchApprovalNotificationPlanner.plan(
    requests: [expiringApproval],
    previousPendingIDs: expiringNotificationPlan.pendingRequestIDs,
    notifiedRequestIDs: expiringNotificationPlan.notifiedRequestIDs,
    approvalCenterVisible: false,
    now: isoDate("2026-05-30T12:00:40Z")
)
precondition(duplicateExpiringNotificationPlan.notifications.isEmpty)

let manifestPayload = """
{
  "agent_id": "email-sorter-2026-05",
  "owner_id": "andrew-main",
  "issued_at": "2026-05-29T18:00:00Z",
  "expires_at": "2026-05-30T18:00:00Z",
  "grants": {
    "gmail.read": "allowed",
    "gmail.send": "requires_approval",
    "drive.write": "denied"
  },
  "budget": { "tokens_per_day": 200000, "dollars_per_day": 5.0 },
  "approval_channel": "evaos://approvals/email-sorter-2026-05",
  "iss": "evaos-broker",
  "aud": "evaos-runtime"
}
"""
let manifestSecret = Data("capability-manifest-test-secret".utf8)
let manifestJWT = signedHS256JWT(payloadJSON: manifestPayload, secret: manifestSecret)
let verifiedManifest = try WorkbenchCapabilityManifestVerifier.verifyHS256JWT(
    manifestJWT,
    secret: manifestSecret,
    now: ISO8601DateFormatter().date(from: "2026-05-29T19:00:00Z")!
)
precondition(verifiedManifest.agentID == "email-sorter-2026-05")
precondition(verifiedManifest.ownerID == "andrew-main")
precondition(verifiedManifest.grants["gmail.read"] == .allowed)
precondition(verifiedManifest.grants["gmail.send"] == .requiresApproval)
precondition(verifiedManifest.grants["drive.write"] == .denied)
precondition(verifiedManifest.decision(for: "unknown.tool") == .denied)
precondition(verifiedManifest.budget.tokensPerDay == 200000)
precondition(verifiedManifest.budget.dollarsPerDay == 5.0)
precondition(verifiedManifest.safeSummary.grants[.requiresApproval] == ["gmail.send"])
precondition(verifiedManifest.safeSummary.grants[.allowed] == ["gmail.read"])
precondition(verifiedManifest.safeSummary.grants[.denied] == ["drive.write"])
precondition(verifiedManifest.safeSummary.approvalChannel == "evaos://approvals/email-sorter-2026-05")
do {
    var invalidManifestParts = manifestJWT.split(separator: ".").map(String.init)
    invalidManifestParts[2] = base64URLEncode(Data("bad-signature".utf8))
    _ = try WorkbenchCapabilityManifestVerifier.verifyHS256JWT(
        invalidManifestParts.joined(separator: "."),
        secret: manifestSecret,
        now: ISO8601DateFormatter().date(from: "2026-05-29T19:00:00Z")!
    )
    preconditionFailure("invalid capability manifest signature should fail")
} catch WorkbenchCapabilityManifestError.invalidSignature {
    // Expected.
}
let blankClaimPayload = manifestPayload.replacingOccurrences(
    of: "\"approval_channel\": \"evaos://approvals/email-sorter-2026-05\"",
    with: "\"approval_channel\": \"   \""
)
do {
    _ = try WorkbenchCapabilityManifestVerifier.verifyHS256JWT(
        signedHS256JWT(payloadJSON: blankClaimPayload, secret: manifestSecret),
        secret: manifestSecret,
        now: ISO8601DateFormatter().date(from: "2026-05-29T19:00:00Z")!
    )
    preconditionFailure("blank capability manifest claims should fail")
} catch WorkbenchCapabilityManifestError.invalidClaims {
    // Expected.
}
let capabilityStore = WorkbenchCapabilityManifestStore(service: "com.electricsheephq.EvaDesktop.capabilities.smoke.\(UUID().uuidString)")
precondition(capabilityStore.storagePointer().contains("capability-manifest"))
try capabilityStore.saveToken(manifestJWT)
let cachedManifestToken = try capabilityStore.loadToken(allowUserInteraction: false)
precondition(cachedManifestToken == manifestJWT)
let cachedManifest = try capabilityStore.loadVerifiedManifest(
    secret: manifestSecret,
    now: ISO8601DateFormatter().date(from: "2026-05-29T19:00:00Z")!,
    allowUserInteraction: false
)
precondition(cachedManifest?.agentID == "email-sorter-2026-05")
try capabilityStore.clear(allowUserInteraction: false)
let clearedManifestToken = try capabilityStore.loadToken(allowUserInteraction: false)
precondition(clearedManifestToken == nil)

let capabilityFetchWithoutSummaryJSON = """
{
  "ok": true,
  "agent_id": "openclaw",
  "owner_id": "andrew-main",
  "manifest_jwt": "\(manifestJWT)",
  "expires_at": "2026-05-30T18:00:00Z",
  "approval_channel": "evaos://approvals/openclaw",
  "grant_count": 3,
  "budget": { "tokens_per_day": 200000, "dollars_per_day": 5.0 }
}
""".data(using: .utf8)!
let decodedCapabilityFetch = try EvaDesktopISO8601.decoder().decode(WorkbenchCapabilityManifestFetchResponse.self, from: capabilityFetchWithoutSummaryJSON)
precondition(decodedCapabilityFetch.validatedCacheToken() == manifestJWT)
precondition(decodedCapabilityFetch.brokerSafeSummary == nil)
precondition(decodedCapabilityFetch.grantCount == 3)

let capabilityFetchWithSummaryJSON = """
{
  "ok": true,
  "agent_id": "openclaw",
  "owner_id": "andrew-main",
  "manifest_jwt": "\(manifestJWT)",
  "expires_at": "2026-05-30T18:00:00Z",
  "approval_channel": "evaos://approvals/openclaw",
  "grant_count": 3,
  "budget": { "tokens_per_day": 200000, "dollars_per_day": 5.0 },
  "safe_summary": {
    "agent_id": "openclaw",
    "owner_id": "andrew-main",
    "expires_at": "2026-05-30T18:00:00Z",
    "approval_channel": "evaos://approvals/openclaw",
    "budget": { "tokens_per_day": 200000, "dollars_per_day": 5.0 },
    "grants": {
      "allowed": ["gmail.read"],
      "requires_approval": ["gmail.send"],
      "denied": ["drive.write"]
    }
  }
}
""".data(using: .utf8)!
let decodedCapabilityFetchWithSummary = try EvaDesktopISO8601.decoder().decode(WorkbenchCapabilityManifestFetchResponse.self, from: capabilityFetchWithSummaryJSON)
precondition(decodedCapabilityFetchWithSummary.validatedCacheToken() == manifestJWT)
precondition(decodedCapabilityFetchWithSummary.brokerSafeSummary?.tools(for: .requiresApproval) == ["gmail.send"])
precondition(decodedCapabilityFetchWithSummary.brokerSafeSummary?.totalGrantCount == 3)

let invalidCapabilityFetchJSON = """
{
  "ok": false,
  "agent_id": "openclaw",
  "owner_id": "andrew-main",
  "manifest_jwt": " ",
  "expires_at": "2026-05-30T18:00:00Z",
  "approval_channel": "evaos://approvals/openclaw",
  "grant_count": 0,
  "budget": { "tokens_per_day": 200000, "dollars_per_day": 5.0 }
}
""".data(using: .utf8)!
let invalidCapabilityFetch = try EvaDesktopISO8601.decoder().decode(WorkbenchCapabilityManifestFetchResponse.self, from: invalidCapabilityFetchJSON)
precondition(invalidCapabilityFetch.validatedCacheToken() == nil)
precondition(RuntimeSessionBrokerClient.normalizedCapabilityAgentID(" bad.agent!/ ") == "badagent")
precondition(RuntimeSessionBrokerClient.normalizedCapabilityAgentID("   ") == "openclaw")

precondition(resolver.sanitizedCustomerId(" Jackie David ") == "jackie-david")
precondition(resolver.sanitizedCustomerId("David_Poku!") == "david-poku")
precondition(resolver.sanitizedCustomerId("") == "golden")

precondition(RuntimeDefinition.isBrokeredRuntime(.openclaw))
precondition(RuntimeDefinition.isBrokeredRuntime(.terminal))
precondition(RuntimeDefinition.isBrokeredRuntime(.openDesign))
precondition(!RuntimeDefinition.isBrokeredRuntime(.creativeStudio))
precondition(RuntimeDefinition.externalURL(for: .creativeStudio)?.absoluteString == "https://www.comfy.org/cloud")
precondition(RuntimeDefinition.externalURL(for: .openDesign) == nil)
precondition(RuntimeDefinition.visibleRuntimes(canAccessAdminRuntimes: false).contains { $0.key == .terminal })
precondition(RuntimeDefinition.visibleRuntimes(canAccessAdminRuntimes: true).contains { $0.key == .terminal })
precondition(RuntimeDefinition.visibleRuntimes(canAccessAdminRuntimes: false).contains { $0.key == .openDesign })
precondition(RuntimeDefinition.visibleRuntimes(canAccessAdminRuntimes: true).contains { $0.key == .openDesign })
precondition(RuntimeDefinition.definition(for: .openDesign).availability == .enabled)
precondition(RuntimeDefinition.definition(for: .creativeStudio).availability == .enabled)
precondition(RuntimeDefinition.definition(for: .openclaw).title == "evaOS (OpenClaw)")
precondition(RuntimeDefinition.definition(for: .openDesign).title == "OpenDesign")
precondition(RuntimeDefinition.definition(for: .liveBrowser).title == "Shared Browser")
precondition(RuntimeDefinition.definition(for: .creativeStudio).title == "Creative Studio")
precondition(RuntimeDefinition.definition(for: .creativeStudio).subtitle.contains("ComfyUI Cloud"))
precondition(RuntimeDefinition.all.map(\.key) == [.openclaw, .hermes, .missionControl, .openDesign, .liveBrowser, .terminal, .creativeStudio])

let contentViewSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/ContentView.swift", encoding: .utf8)
precondition(!contentViewSource.contains("case .sharedBrowser2"))
precondition(!contentViewSource.contains("CreativeStudioPlaceholderView"))
precondition(contentViewSource.contains("model.runtimeNavigationRequest"))
precondition(contentViewSource.contains("sidebarSelection = .runtime(request.runtime)"))
precondition(contentViewSource.contains("case .approvalCenter"))
precondition(contentViewSource.contains("model.setApprovalCenterVisible"))
precondition(contentViewSource.contains("model.startApprovalCenterPolling()"))
let osViewsSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/WorkbenchOSViews.swift", encoding: .utf8)
precondition(!osViewsSource.contains("struct SharedBrowser2View"))
precondition(!osViewsSource.contains("struct CreativeStudioPlaceholderView"))
precondition(osViewsSource.contains("struct ApprovalCenterView"))
precondition(osViewsSource.contains("model.decideApprovalRequest"))
precondition(osViewsSource.contains("decision != .deny && (!request.isActionable || request.isExpired())"))
precondition(!osViewsSource.contains("try? await Task.sleep(nanoseconds: 5_000_000_000)"))
precondition(osViewsSource.contains("Display names and summaries alone are not enough"))
precondition(osViewsSource.contains("Allow always requires a durable destination constraint"))
let noPendingTintIndex = osViewsSource.range(of: "model.approvalCenterStatusText == \"No pending approvals\"")!.lowerBound
let pendingTintIndex = osViewsSource.range(of: "model.approvalCenterStatusText.contains(\"pending\")")!.lowerBound
precondition(noPendingTintIndex < pendingTintIndex)
precondition(osViewsSource.contains("model.sessionRecords"))
precondition(!osViewsSource.contains("model.runtimeURLs[runtime.key] == nil ? \"Ready to open\" : \"Loaded\""))
precondition(osViewsSource.contains("Needs verification"))
precondition(!osViewsSource.contains("OpenClaw and Hermes"))
precondition(!osViewsSource.contains("Agent Grant"))
precondition(!osViewsSource.contains("Providers & Auth Hub"))
precondition(osViewsSource.contains("WorkbenchSurface(title: \"Providers\""))
precondition(osViewsSource.contains("Connect provider accounts in the Shared Browser"))
precondition(osViewsSource.contains("OpenClaw Grant"))
let sidebarSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/SidebarView.swift", encoding: .utf8)
precondition(sidebarSource.contains("Approval Center"))
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
precondition(runtimeDetailSource.contains("RuntimeWebViewDeck("))
let runtimeWebViewSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/RuntimeWebView.swift", encoding: .utf8)
precondition(runtimeWebViewSource.contains("private var attached: [RuntimeKey: WKWebView] = [:]"))
precondition(runtimeWebViewSource.contains("attached[entry.runtime] = webView"))
precondition(runtimeWebViewSource.contains("entry.runtime == activeRuntime ? 1 : 0"))
let customerTargetMenuSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/CustomerTargetMenu.swift", encoding: .utf8)
precondition(customerTargetMenuSource.contains("Reset to Golden"))
let expansionDoc = try String(contentsOfFile: "../../docs/evaos-workbench-v050-one-app-expansion.md", encoding: .utf8)
precondition(expansionDoc.contains("| Signed out |"))
precondition(expansionDoc.contains("| Signed in, normal customer |"))
precondition(expansionDoc.contains("| Signed in, admin/support customer switch |"))
precondition(expansionDoc.contains("Feature rollback disables only the new surface; direct gateway launch remains available"))
precondition(expansionDoc.contains("Dashboard env"))
precondition(expansionDoc.contains("Rollout criteria"))
precondition(expansionDoc.contains("Rollback action"))
precondition(expansionDoc.contains("Public copy"))
precondition(expansionDoc.contains("VITE_EVAOS_SHARED_BROWSER_2"))
precondition(expansionDoc.contains("No provider, session, or runtime truth is inferred from cached UI state"))
let workbenchModelSource = try String(contentsOfFile: "Sources/EvaDesktop/Services/WorkbenchModel.swift", encoding: .utf8)
precondition(workbenchModelSource.contains("sessionMissionCards = nextCards"))
precondition(!workbenchModelSource.contains("NSWorkspace.shared.open(response.connectURL)"))
precondition(workbenchModelSource.contains("openProviderAuthHandoff(response.connectURL)"))
precondition(workbenchModelSource.contains("broker.openSharedBrowserURL("))
precondition(workbenchModelSource.contains("response.targetURL"))
precondition(workbenchModelSource.contains("runtime: runtime"))
precondition(!workbenchModelSource.contains("profiles.filter { $0.key == .openAICodex }"))
precondition(workbenchModelSource.contains("WorkbenchProviderCatalog.visibleStates(from: profiles)"))
precondition(workbenchModelSource.contains("WorkbenchProviderOAuthCallback.isOAuthComplete(url)"))
precondition(workbenchModelSource.contains("decidePolicyFor navigationAction"))
precondition(workbenchModelSource.contains(".providerOAuthComplete(url)"))
precondition(workbenchModelSource.contains("decisionHandler(.cancel)"))
precondition(workbenchModelSource.contains("broker.launchURL("))
precondition(workbenchModelSource.contains("for definition in visibleRuntimes where RuntimeDefinition.isBrokeredRuntime(definition.key)"))
precondition(workbenchModelSource.contains("broker.runtimeStatus("))
precondition(workbenchModelSource.contains("Opening Shared Browser for provider sign-in"))
precondition(workbenchModelSource.contains("shared VM browser"))
precondition(workbenchModelSource.contains("opened inside Workbench"))
precondition(workbenchModelSource.contains("let currentRequest = approvalRequests.first { $0.id == request.id }"))
precondition(workbenchModelSource.contains("requestForDecision.canAllowAlways"))
precondition(workbenchModelSource.contains("decision == .deny || !requestForDecision.isExpired()"))
precondition(workbenchModelSource.contains("session = try? keychain.load(allowUserInteraction: false)"))
precondition(workbenchModelSource.contains("try? keychain.clear(allowUserInteraction: false)"))
precondition(workbenchModelSource.contains("try keychain.save(newSession)"))
precondition(workbenchModelSource.contains("await broker.revoke(desktopSession: sessionToRevoke)"))
precondition(workbenchModelSource.contains("clearLocalSessionState(allowKeychainInteraction: false)"))
precondition(workbenchModelSource.contains("runtimeNavigationRequest = RuntimeNavigationRequest(runtime: runtime)"))
precondition(workbenchModelSource.contains("runtimeURLs[runtime] = url"))
precondition(workbenchModelSource.contains("let key = \"\\(customerId)::\\(runtime.rawValue)\""))
precondition(workbenchModelSource.contains("configuration.websiteDataStore = .nonPersistent()"))
precondition(workbenchModelSource.contains("resetRuntimeWebViewIfNeeded(runtime, customerId: targetCustomerId)"))
precondition(workbenchModelSource.contains("func reset(runtime: RuntimeKey, customerId: String)"))
precondition(workbenchModelSource.contains("webView.removeFromSuperview()"))
precondition(workbenchModelSource.contains("resetApprovalCenterState(statusText: \"Unchecked\")"))
precondition(workbenchModelSource.contains("approvalNotificationService.deliver"))
precondition(workbenchModelSource.contains("subtracting(candidateNotificationIDs)"))
precondition(workbenchModelSource.contains("15_000_000_000"))
precondition(workbenchModelSource.contains("resetCapabilityManifestState(statusText: \"Unchecked\", clearCache: true)"))
precondition(workbenchModelSource.contains("bridgeKey([\"queue\", \"list\", \"--json\", \"--limit\", \"10\"])"))
precondition(workbenchModelSource.contains("bridgeKey([\"codex\", \"app-server\", \"status\", \"--json\"])"))
precondition(workbenchModelSource.contains("bridgeKey([\"codex\", \"app-server\", \"threads\", \"--json\", \"--max-items\", \"5\"])"))
precondition(workbenchModelSource.contains("evaos-bridge-\\(captureID).stdout"))
precondition(workbenchModelSource.contains("FileHandle(forWritingTo: stdoutURL)"))
precondition(!workbenchModelSource.contains("turn/start"))
precondition(!workbenchModelSource.contains("turn/steer"))
precondition(!workbenchModelSource.contains("turn/interrupt"))
precondition(workbenchModelSource.contains("await refreshCapabilityManifest(trigger: \"provider_profiles\")"))
precondition(workbenchModelSource.contains("await refreshCapabilityManifest(trigger: \"provider_connect\")"))
precondition(workbenchModelSource.contains("await refreshCapabilityManifest(trigger: \"provider_action\")"))
precondition(workbenchModelSource.contains("capabilityManifestStatusText = \"Cached: summary pending\""))
precondition(workbenchModelSource.contains("capabilityManifestStatusText = \"Ready: \\(summary.totalGrantCount) grants\""))
precondition(workbenchModelSource.contains("capabilityManifestStore.clear"))
precondition(!workbenchModelSource.contains("Complete `/auth openai-codex`"))
precondition(workbenchModelSource.contains("lastSignInURL"))
precondition(workbenchModelSource.contains("func reopenSignIn()"))
precondition(workbenchModelSource.contains("func cancelSignIn()"))
precondition(workbenchModelSource.contains("DesktopAuthSessionError.couldNotStart"))
precondition(workbenchModelSource.contains("NSWorkspace.shared.open(authURL)"))
precondition(workbenchModelSource.contains("finishActiveSignIn"))
precondition(workbenchModelSource.contains("DesktopAuthSessionError.timedOut"))
precondition(!workbenchModelSource.contains("deviceCodeInput = fallbackCode"))
let bridgePanelSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/BridgePanelView.swift", encoding: .utf8)
precondition(!bridgePanelSource.contains("Your agent can control this Mac and iPhone until you stop it."))
precondition(bridgePanelSource.contains("Start a visible Agent Control session"))
let releaseScriptSource = try String(contentsOfFile: "script/build_and_run.sh", encoding: .utf8)
precondition(!releaseScriptSource.contains("internal canary"))
precondition(!releaseScriptSource.contains("non-notarized"))
precondition(releaseScriptSource.contains("args+=(--options runtime)"))
precondition(releaseScriptSource.contains("CFBundleURLSchemes:0 string evaos"))
precondition(releaseScriptSource.contains("--run-agent-qa"))
precondition(releaseScriptSource.contains("run_agent_qa_app"))
precondition(releaseScriptSource.contains("EVAOS_WORKBENCH_ALLOW_REMOVABLE_LAUNCH"))
precondition(releaseScriptSource.contains("""
  --logs|logs)
    open_app_from_dist
"""))
precondition(releaseScriptSource.contains("""
  --telemetry|telemetry)
    open_app_from_dist
"""))
precondition(releaseScriptSource.contains("package_release()"))
precondition(releaseScriptSource.contains("notarize_release()"))
precondition(releaseScriptSource.contains("Developer ID signed, notarized, and stapled"))

let trustedDownload = URL(string: "https://github.com/electricsheephq/evaos-workbench-releases/releases/download/evaos-workbench-v0.6.13/evaOS-Workbench-0.6.13.zip")!
let olderManifest = WorkbenchReleaseManifest(version: "0.1.3", build: "1", downloadURL: trustedDownload)
let newerManifest = WorkbenchReleaseManifest(version: "0.6.13", build: "1", downloadURL: trustedDownload)
let newerBuildManifest = WorkbenchReleaseManifest(version: "0.6.13", build: "54", downloadURL: trustedDownload)
precondition(!olderManifest.isNewerThan(currentVersion: AppBrand.version, currentBuild: AppBrand.buildNumber))
precondition(!newerManifest.isNewerThan(currentVersion: AppBrand.version, currentBuild: AppBrand.buildNumber))
precondition(newerBuildManifest.isNewerThan(currentVersion: AppBrand.version, currentBuild: AppBrand.buildNumber))
precondition(WorkbenchUpdateClient.isTrustedUpdateURL(URL(string: AppBrand.defaultUpdateManifestURL)!))
precondition(WorkbenchUpdateClient.isTrustedUpdateURL(trustedDownload))
precondition(!WorkbenchUpdateClient.isTrustedUpdateURL(URL(string: "https://example.com/evaOS-Workbench-0.1.1.zip")!))
try WorkbenchUpdateClient.validate(WorkbenchReleaseManifest(version: "0.6.13", build: "53", downloadURL: trustedDownload, sha256: String(repeating: "a", count: 64), releaseNotesURL: URL(string: "https://www.electricsheephq.com/evaos-workbench")!))

let broker = RuntimeSessionBrokerClient()
precondition(broker.endpoint.absoluteString == "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/desktop-runtime-session")
precondition(broker.capabilityEndpoint.absoluteString == "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/cortex-proxy")
let macControl = CustomerMacControlClient()
precondition(macControl.endpoint.absoluteString == "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/customer-mac-control")

let smokeKeychain = KeychainSessionStore(service: "com.electricsheephq.EvaDesktop.smoke.\(UUID().uuidString)")
precondition((try? smokeKeychain.load(allowUserInteraction: false)) == nil)
let keychainSource = try String(contentsOfFile: "Sources/EvaDesktopCore/Services/KeychainSessionStore.swift", encoding: .utf8)
precondition(keychainSource.contains("kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly"))
precondition(keychainSource.contains("context.interactionNotAllowed = true"))
let brokerSource = try String(contentsOfFile: "Sources/EvaDesktopCore/Services/RuntimeSessionBrokerClient.swift", encoding: .utf8)
precondition(brokerSource.contains("RuntimeLaunchRequest(customerId: customerId, runtime: runtime)"))
precondition(brokerSource.contains("request.setValue(\"Bearer \\(desktopSession.accessToken)\", forHTTPHeaderField: \"Authorization\")"))
precondition(brokerSource.contains("func capabilityManifest("))
precondition(brokerSource.contains("\"method\": method"))
precondition(brokerSource.contains("usesCapabilityProxy"))
precondition(brokerSource.contains("trimmingCharacters(in: CharacterSet(charactersIn: \"/\"))"))
precondition(brokerSource.contains("pathComponents: [\"capabilities\", RuntimeSessionBrokerClient.normalizedCapabilityAgentID(agentID)]"))
precondition(brokerSource.contains("func pendingApprovals("))
precondition(brokerSource.contains("pathComponents: [\"approvals\", \"pending\"]"))
precondition(brokerSource.contains("pathComponents: [\"approvals\", approvalID, \"decide\"]"))
let manifestModelSource = try String(contentsOfFile: "Sources/EvaDesktopCore/Models/WorkbenchCapabilityManifest.swift", encoding: .utf8)
precondition(manifestModelSource.contains("safeSummary"))
precondition(manifestModelSource.contains("manifestJWT"))
precondition(osViewsSource.contains("Capability Manifest"))
precondition(osViewsSource.contains("capabilityManifestStatusText"))
precondition(!osViewsSource.contains("manifestJWT"))
precondition(!osViewsSource.contains("manifest_jwt"))

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
let mergedProviderProfiles = WorkbenchProviderCatalog.visibleStates(from: decodedProviderProfiles.profiles)
precondition(mergedProviderProfiles.count == WorkbenchProviderCatalog.profiles.count)
precondition(mergedProviderProfiles.first { $0.key == .openAICodex }?.status == .connected)
precondition(mergedProviderProfiles.first { $0.key == .slack }?.status == .planned)

let expandedProviderProfilesResponse = """
{"provider_profiles":[{"provider_key":"google_workspace","title":"Google Workspace","subtitle":"Gmail, Calendar, and Drive","status":"needs_login","active":false,"raw_secrets_stored_in_workbench":false,"capabilities":["gmail","calendar","drive"],"usage_summary":null,"last_validated_at":null},{"provider_key":"slack","title":"Slack","subtitle":"Workspace chat","status":"connected","active":false,"raw_secrets_stored_in_workbench":false,"capabilities":["channels"],"usage_summary":"Ready","last_validated_at":"2026-05-23T10:00:00Z"},{"provider_key":"github","title":"GitHub","subtitle":"Code hosting","status":"planned","active":false,"raw_secrets_stored_in_workbench":false,"capabilities":["pull_requests"],"usage_summary":null,"last_validated_at":null}],"active_provider_key":"slack","raw_secrets_stored_in_workbench":false}
""".data(using: .utf8)!
let decodedExpandedProviderProfiles = try EvaDesktopISO8601.decoder().decode(WorkbenchProviderProfilesResponse.self, from: expandedProviderProfilesResponse)
let expandedVisibleProfiles = WorkbenchProviderCatalog.visibleStates(from: decodedExpandedProviderProfiles.profiles)
precondition(decodedExpandedProviderProfiles.activeProviderKey == .slack)
precondition(expandedVisibleProfiles.map(\.key) == providerCatalogKeys)
precondition(expandedVisibleProfiles.first { $0.key == .googleWorkspace }?.status == .needsLogin)
precondition(expandedVisibleProfiles.first { $0.key == .slack }?.hasConnectionProof == true)
precondition(expandedVisibleProfiles.first { $0.key == .notion }?.status == .planned)

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
let runtimeSessionRecord = WorkbenchSessionContract.record(from: runtimeMissionCard, customerId: "david-poku")
precondition(runtimeSessionRecord.schemaVersion == "evaos.session_center.v1")
precondition(runtimeSessionRecord.surface == .broker)
precondition(runtimeSessionRecord.runtime == .liveBrowser)
precondition(runtimeSessionRecord.customerId == "david-poku")
precondition(runtimeSessionRecord.attentionState == .active)
precondition(runtimeSessionRecord.lastActor == "broker")
precondition(runtimeSessionRecord.nextAction == runtimeMissionCard.nextAction)
precondition(runtimeSessionRecord.resumeRoute.kind == .brokerRuntime)
precondition(runtimeSessionRecord.resumeRoute.runtime == .liveBrowser)
precondition(runtimeSessionRecord.resumeRoute.targetId == "browser")
precondition(WorkbenchSessionContract.brokerRuntimeToOpen(for: runtimeSessionRecord) == .liveBrowser)
let sessionRecordEncoder = JSONEncoder()
sessionRecordEncoder.outputFormatting = [.sortedKeys]
let encodedRuntimeSessionRecord = try sessionRecordEncoder.encode(runtimeSessionRecord)
let encodedRuntimeSessionRecordText = String(data: encodedRuntimeSessionRecord, encoding: .utf8)!
precondition(encodedRuntimeSessionRecordText.contains("\"next_action\""))
let decodedRuntimeSessionRecord = try JSONDecoder().decode(WorkbenchSessionRecord.self, from: encodedRuntimeSessionRecord)
precondition(decodedRuntimeSessionRecord == runtimeSessionRecord)
let legacySessionRecordJSON = """
{"schema_version":"evaos.session_center.v1","id":"runtime-browser","surface":"broker","runtime":"browser","customer_id":"david-poku","title":"Shared Browser","status":"Loaded","attention_state":"active","last_actor":"broker","updated_at":"2026-05-29T16:00:00Z","resume_route":{"kind":"broker_runtime","runtime":"browser","target_id":"browser","source_pointer":"broker:runtime_status:browser"},"source_pointer":"broker:runtime_status:browser","audit_id":null}
""".data(using: .utf8)!
let legacySessionRecord = try JSONDecoder().decode(WorkbenchSessionRecord.self, from: legacySessionRecordJSON)
precondition(legacySessionRecord.nextAction == "Review Shared Browser.")
precondition(WorkbenchSessionContract.brokerRuntimeToOpen(for: legacySessionRecord) == .liveBrowser)

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
let queueSessionRecord = WorkbenchSessionContract.record(from: queueCards[0])
precondition(queueSessionRecord.surface == .queue)
precondition(queueSessionRecord.lastActor == "bridge_queue")
precondition(queueSessionRecord.resumeRoute.kind == .queueEvent)
precondition(queueSessionRecord.resumeRoute.targetId == "queue-approval")
precondition(WorkbenchSessionContract.brokerRuntimeToOpen(for: queueSessionRecord) == nil)
let malformedRuntimeEvidence = WorkbenchMissionCard(
    id: "queue-runtime-injection",
    surface: "queue",
    runtime: .openclaw,
    title: "Queue Runtime Injection",
    status: "attention",
    attentionState: .needsAttention,
    nextAction: "This queue record must not become a broker runtime action.",
    sourcePointer: "queue:runtime-injection"
)
let malformedRuntimeRecord = WorkbenchSessionContract.record(from: malformedRuntimeEvidence)
precondition(malformedRuntimeRecord.resumeRoute.kind == .queueEvent)
precondition(WorkbenchSessionContract.brokerRuntimeToOpen(for: malformedRuntimeRecord) == nil)
let nonBrokerRuntimeEvidence = WorkbenchMissionCard(
    id: "runtime-creative-studio",
    surface: "broker",
    runtime: .creativeStudio,
    title: "Creative Studio",
    status: "external",
    attentionState: .idle,
    nextAction: "External runtime should not be opened through broker runtime route.",
    sourcePointer: "broker:runtime_status:creative_studio"
)
let nonBrokerRuntimeRecord = WorkbenchSessionContract.record(from: nonBrokerRuntimeEvidence)
precondition(nonBrokerRuntimeRecord.resumeRoute.kind == .evidenceOnly)
precondition(WorkbenchSessionContract.brokerRuntimeToOpen(for: nonBrokerRuntimeRecord) == nil)

let auditRaw = """
{"ok":true,"data":{"records":[{"audit_id":"audit-ok","timestamp":"2026-05-28T01:10:00Z","command":"status","ok":true},{"audit_id":"audit-failed","timestamp":"2026-05-28T01:11:00Z","command":"codex.app_server.status","ok":false}]}}
"""
let auditCards = WorkbenchMissionCardDeriver.auditCards(from: auditRaw)
precondition(auditCards.count == 2)
precondition(auditCards[0].sourcePointer == "audit:audit-ok")
precondition(auditCards[1].attentionState == .needsAttention)
let auditSessionRecord = WorkbenchSessionContract.record(from: auditCards[0])
precondition(auditSessionRecord.surface == .audit)
precondition(auditSessionRecord.resumeRoute.kind == .auditRecord)
precondition(auditSessionRecord.resumeRoute.targetId == "audit-ok")

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
let codexSessionRecord = WorkbenchSessionContract.record(from: codexCards[1])
precondition(codexSessionRecord.surface == .codex)
precondition(codexSessionRecord.resumeRoute.kind == .codexEvidence)
precondition(codexSessionRecord.resumeRoute.targetId == "codex-threads")
let sessionRecords = WorkbenchSessionContract.records(from: [runtimeMissionCard, queueCards[0], auditCards[0], codexCards[1]], customerId: "golden")
precondition(sessionRecords.count == 4)
precondition(sessionRecords[0].customerId == "golden")
precondition(sessionRecords[0].resumeRoute.kind == .brokerRuntime)
precondition(sessionRecords[1].resumeRoute.kind == .queueEvent)
precondition(sessionRecords[2].resumeRoute.kind == .auditRecord)
precondition(sessionRecords[3].resumeRoute.kind == .codexEvidence)

let malformedCards = WorkbenchMissionCardDeriver.queueCards(from: "{")
precondition(malformedCards.count == 1)
precondition(malformedCards[0].attentionState == .needsAttention)
precondition(malformedCards[0].sourcePointer == "bridge:queue.list")
let bridgeFailureSessionRecord = WorkbenchSessionContract.record(from: malformedCards[0])
precondition(bridgeFailureSessionRecord.surface == .bridge)
precondition(bridgeFailureSessionRecord.resumeRoute.kind == .evidenceOnly)
let sessionContractSource = try String(contentsOfFile: "Sources/EvaDesktopCore/Models/WorkbenchSessionRecord.swift", encoding: .utf8)
precondition(sessionContractSource.contains("evaos.session_center.v1"))
precondition(sessionContractSource.contains("brokerRuntime = \"broker_runtime\""))
precondition(sessionContractSource.contains("nextAction = \"next_action\""))
precondition(!sessionContractSource.contains("shell"))
precondition(!sessionContractSource.contains("app-server rpc"))
precondition(workbenchModelSource.contains("@Published var sessionRecords: [WorkbenchSessionRecord]"))
precondition(workbenchModelSource.contains("sessionRecords = WorkbenchSessionContract.records"))
precondition(workbenchModelSource.contains("sessionRecords.removeAll()"))
let workbenchOSViewsSource = try String(contentsOfFile: "Sources/EvaDesktop/Views/WorkbenchOSViews.swift", encoding: .utf8)
precondition(workbenchOSViewsSource.contains("ForEach(model.sessionRecords)"))
precondition(workbenchOSViewsSource.contains("WorkbenchSessionContract.brokerRuntimeToOpen"))
let sessionContractDoc = try String(contentsOfFile: "../../docs/session-center-agent-workspace-contract.md", encoding: .utf8)
precondition(sessionContractDoc.contains("Canonical Session Record"))
precondition(sessionContractDoc.contains("No Generic Control Surface"))
precondition(sessionContractDoc.contains("broker_runtime"))
precondition(sessionContractDoc.contains("next_action"))
precondition(sessionContractDoc.contains("Readers should tolerate it missing"))

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
precondition(WorkbenchProviderOAuthCallback.isOAuthComplete(URL(string: "evaos://oauth-complete?provider_key=google_workspace")!))
precondition(WorkbenchProviderOAuthCallback.isOAuthComplete(URL(string: "evaos://oauth-complete")!))
precondition(WorkbenchProviderOAuthCallback.isOAuthComplete(URL(string: "EVAOS://OAUTH-COMPLETE")!))
precondition(!WorkbenchProviderOAuthCallback.isOAuthComplete(callbackURL))
precondition(fragmentCallbackSession.expiresAt != nil)

func signedHS256JWT(payloadJSON: String, secret: Data) -> String {
    let headerJSON = #"{"alg":"HS256","typ":"JWT"}"#
    let encodedHeader = base64URLEncode(Data(headerJSON.utf8))
    let encodedPayload = base64URLEncode(Data(payloadJSON.utf8))
    let signingInput = "\(encodedHeader).\(encodedPayload)"
    let key = SymmetricKey(data: secret)
    let signature = HMAC<SHA256>.authenticationCode(for: Data(signingInput.utf8), using: key)
    return "\(signingInput).\(base64URLEncode(Data(signature)))"
}

func base64URLEncode(_ data: Data) -> String {
    data.base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
}

print("EvaDesktopCoreSmoke passed")
