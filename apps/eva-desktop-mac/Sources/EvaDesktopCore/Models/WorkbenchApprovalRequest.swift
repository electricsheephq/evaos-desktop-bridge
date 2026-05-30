import Foundation

public enum WorkbenchApprovalRiskClass: String, Codable, Equatable, Sendable {
    case critical
    case warning
    case info
}

public enum WorkbenchApprovalDecision: String, Codable, Equatable, Sendable {
    case allowOnce = "allow-once"
    case allowAlways = "allow-always"
    case deny

    public var displayText: String {
        switch self {
        case .allowOnce:
            return "Allow once"
        case .allowAlways:
            return "Allow always"
        case .deny:
            return "Deny"
        }
    }

    public var defaultScope: WorkbenchApprovalScope {
        switch self {
        case .allowOnce, .deny:
            return .thisCall
        case .allowAlways:
            return .thisAgent
        }
    }
}

public enum WorkbenchApprovalScope: String, Codable, Equatable, Sendable {
    case thisCall = "this-call"
    case thisAgent = "this-agent"
}

public enum WorkbenchApprovalPreviewKind: String, Codable, Equatable, Sendable {
    case emailRecipient = "email_recipient"
    case messageRecipient = "message_recipient"
    case url
    case filePath = "file_path"
    case purchase
    case secretName = "secret_name"
    case budget
    case permission
    case missingDestination = "missing_destination"
}

public struct WorkbenchApprovalDestinationPreview: Codable, Equatable, Sendable {
    public let kind: WorkbenchApprovalPreviewKind
    public let primary: String
    public let secondary: String?
    public let bodyExcerpt: String?
    public let warning: String?

    public init(
        kind: WorkbenchApprovalPreviewKind,
        primary: String,
        secondary: String? = nil,
        bodyExcerpt: String? = nil,
        warning: String? = nil
    ) {
        self.kind = kind
        self.primary = primary
        self.secondary = secondary
        self.bodyExcerpt = bodyExcerpt
        self.warning = warning
    }

    public var isActionable: Bool {
        kind != .missingDestination
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case primary
        case secondary
        case bodyExcerpt = "body_excerpt"
        case warning
    }
}

public struct WorkbenchApprovalRequest: Identifiable, Codable, Equatable, Sendable {
    public let id: String
    public let ownerID: String
    public let agentID: String
    public let toolName: String
    public let riskClass: WorkbenchApprovalRiskClass
    public let actionPayload: [String: String]
    public let destinationPreview: WorkbenchApprovalDestinationPreview
    public let createdAt: String
    public let sourcePointer: String
    public let auditId: String?

    public init(
        id: String,
        ownerID: String,
        agentID: String,
        toolName: String,
        riskClass: WorkbenchApprovalRiskClass,
        actionPayload: [String: String],
        destinationPreview: WorkbenchApprovalDestinationPreview,
        createdAt: String,
        sourcePointer: String,
        auditId: String? = nil
    ) {
        self.id = id
        self.ownerID = ownerID
        self.agentID = agentID
        self.toolName = toolName
        self.riskClass = riskClass
        self.actionPayload = actionPayload
        self.destinationPreview = destinationPreview
        self.createdAt = createdAt
        self.sourcePointer = sourcePointer
        self.auditId = auditId
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        ownerID = try container.decode(String.self, forKey: .ownerID)
        agentID = try container.decode(String.self, forKey: .agentID)
        toolName = try container.decode(String.self, forKey: .toolName)
        riskClass = try container.decode(WorkbenchApprovalRiskClass.self, forKey: .riskClass)
        actionPayload = try WorkbenchApprovalPayloadFlattener.decodePayload(from: container, forKey: .actionPayload)
        createdAt = try container.decode(String.self, forKey: .createdAt)
        sourcePointer = try container.decodeIfPresent(String.self, forKey: .sourcePointer) ?? "approval:\(id)"
        auditId = try container.decodeIfPresent(String.self, forKey: .auditId)
        destinationPreview = WorkbenchApprovalPreviewBuilder.preview(toolName: toolName, payload: actionPayload)
    }

    public static func pending(
        id: String,
        ownerID: String,
        agentID: String,
        toolName: String,
        riskClass: WorkbenchApprovalRiskClass,
        actionPayload: [String: String],
        createdAt: String,
        sourcePointer: String,
        auditId: String? = nil
    ) -> WorkbenchApprovalRequest {
        WorkbenchApprovalRequest(
            id: id,
            ownerID: ownerID,
            agentID: agentID,
            toolName: toolName,
            riskClass: riskClass,
            actionPayload: actionPayload,
            destinationPreview: WorkbenchApprovalPreviewBuilder.preview(toolName: toolName, payload: actionPayload),
            createdAt: createdAt,
            sourcePointer: sourcePointer,
            auditId: auditId
        )
    }

    public var availableDecisions: [WorkbenchApprovalDecision] {
        [.allowOnce, .deny]
    }

    public func displayOnly() -> WorkbenchApprovalRequest {
        WorkbenchApprovalRequest(
            id: id,
            ownerID: ownerID,
            agentID: agentID,
            toolName: toolName,
            riskClass: riskClass,
            actionPayload: [:],
            destinationPreview: destinationPreview,
            createdAt: createdAt,
            sourcePointer: sourcePointer,
            auditId: auditId
        )
    }

    public var isActionable: Bool {
        destinationPreview.isActionable
    }

    public var attentionState: WorkbenchMissionAttentionState {
        .needsAttention
    }

    public var nextAction: String {
        if !isActionable {
            return "Approval request is missing actual destination details; ask the runtime to resubmit with recipient, URL, file path, or scope."
        }
        switch riskClass {
        case .critical:
            return "Critical action. Verify the actual destination and payload before deciding."
        case .warning:
            return "Review the actual destination and payload before deciding."
        case .info:
            return "Confirm the destination shown here matches the intended action."
        }
    }

    enum CodingKeys: String, CodingKey {
        case id
        case ownerID = "owner_id"
        case agentID = "agent_id"
        case toolName = "tool_name"
        case riskClass = "risk_class"
        case actionPayload = "action_payload"
        case destinationPreview = "destination_preview"
        case createdAt = "created_at"
        case sourcePointer = "source_pointer"
        case auditId = "audit_id"
    }
}

public struct WorkbenchApprovalRequestsResponse: Codable, Equatable, Sendable {
    public let ok: Bool?
    public let ownerID: String?
    public let requests: [WorkbenchApprovalRequest]

    public init(ok: Bool? = nil, ownerID: String? = nil, requests: [WorkbenchApprovalRequest]) {
        self.ok = ok
        self.ownerID = ownerID
        self.requests = requests
    }

    enum CodingKeys: String, CodingKey {
        case ok
        case ownerID = "owner_id"
        case requests
    }
}

public struct WorkbenchApprovalDecisionRequest: Codable, Equatable, Sendable {
    public let decision: WorkbenchApprovalDecision
    public let scope: WorkbenchApprovalScope

    public init(decision: WorkbenchApprovalDecision, scope: WorkbenchApprovalScope? = nil) {
        self.decision = decision
        self.scope = scope ?? decision.defaultScope
    }
}

public enum WorkbenchApprovalPreviewBuilder {
    public static let excerptLimit = 220

    public static func preview(toolName: String, payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        let tokens = toolTokens(toolName)
        if tokens.contains("gmail") || tokens.contains("email") {
            return emailPreview(payload)
        }
        if tokens.contains("browser") || tokens.contains("fetch") || tokens.contains("url") {
            return urlPreview(payload)
        }
        if tokens.contains("slack") || tokens.contains("message") {
            return messagePreview(payload)
        }
        if tokens.contains("delete") || tokens.contains("file") || (tokens.contains("drive") && tokens.contains("write")) {
            return filePreview(payload)
        }
        if tokens.contains("purchase") || tokens.contains("payment") || tokens.contains("money") {
            return purchasePreview(payload)
        }
        if tokens.contains("secret") {
            return namedPreview(.secretName, keys: ["secret_name", "secret_id", "name"], payload: payload)
        }
        if tokens.contains("budget") {
            return namedPreview(.budget, keys: ["budget", "amount", "limit"], payload: payload)
        }
        if tokens.contains("permission") || tokens.contains("scope") {
            return namedPreview(.permission, keys: ["permission", "scope", "grant"], payload: payload)
        }
        return missingDestinationPreview()
    }

    private static func emailPreview(_ payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        guard let recipient = emailAddress(in: payload, keys: ["recipient_email", "actual_recipient_email", "to", "recipient", "recipients"]) else {
            return missingDestinationPreview()
        }
        return WorkbenchApprovalDestinationPreview(
            kind: .emailRecipient,
            primary: recipient,
            secondary: firstValue(in: payload, keys: ["subject"]),
            bodyExcerpt: firstValue(in: payload, keys: ["body", "message", "text"]).map { capped($0) },
            warning: nil
        )
    }

    private static func urlPreview(_ payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        guard let url = firstValue(in: payload, keys: ["url", "href", "uri", "target_url", "actual_url"]) else {
            return missingDestinationPreview()
        }
        guard let components = URLComponents(string: url),
              let scheme = components.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              let host = components.host,
              !host.isEmpty else {
            return missingDestinationPreview()
        }
        return WorkbenchApprovalDestinationPreview(
            kind: .url,
            primary: url,
            secondary: host,
            bodyExcerpt: nil,
            warning: urlWarning(for: components)
        )
    }

    private static func messagePreview(_ payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        guard let recipient = firstValue(in: payload, keys: ["recipient", "recipients", "channel", "to", "recipient_id", "channel_id", "actual_recipient_id", "actual_channel_id"]) else {
            return missingDestinationPreview()
        }
        return WorkbenchApprovalDestinationPreview(
            kind: .messageRecipient,
            primary: recipient,
            secondary: firstValue(in: payload, keys: ["channel_name", "subject"]),
            bodyExcerpt: firstValue(in: payload, keys: ["body", "message", "text"]).map { capped($0) }
        )
    }

    private static func filePreview(_ payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        namedPreview(.filePath, keys: ["file_path", "path", "target_path"], payload: payload)
    }

    private static func purchasePreview(_ payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        guard let merchant = firstValue(in: payload, keys: ["merchant", "vendor", "payment_target"]) else {
            return missingDestinationPreview()
        }
        return WorkbenchApprovalDestinationPreview(
            kind: .purchase,
            primary: merchant,
            secondary: firstValue(in: payload, keys: ["amount", "total", "price"]),
            bodyExcerpt: firstValue(in: payload, keys: ["description", "item"]).map { capped($0) }
        )
    }

    private static func namedPreview(
        _ kind: WorkbenchApprovalPreviewKind,
        keys: [String],
        payload: [String: String]
    ) -> WorkbenchApprovalDestinationPreview {
        guard let value = firstValue(in: payload, keys: keys) else {
            return missingDestinationPreview()
        }
        return WorkbenchApprovalDestinationPreview(kind: kind, primary: value)
    }

    private static func missingDestinationPreview() -> WorkbenchApprovalDestinationPreview {
        WorkbenchApprovalDestinationPreview(
            kind: .missingDestination,
            primary: "Missing actual destination",
            secondary: nil,
            bodyExcerpt: nil,
            warning: "The broker/runtime must include the real recipient, URL, file path, payment target, secret name, budget, or permission scope."
        )
    }

    private static func firstValue(in payload: [String: String], keys: [String]) -> String? {
        for key in keys {
            if let value = payload[key]?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty {
                return value
            }
        }
        return nil
    }

    private static func toolTokens(_ toolName: String) -> Set<String> {
        let tokens = toolName
            .lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
        return Set(tokens)
    }

    private static func emailAddress(in payload: [String: String], keys: [String]) -> String? {
        guard let value = firstValue(in: payload, keys: keys), isLikelyEmailAddress(value) else {
            return nil
        }
        return value
    }

    private static func isLikelyEmailAddress(_ value: String) -> Bool {
        guard !value.contains(where: { $0.isWhitespace || $0 == "<" || $0 == ">" }) else {
            return false
        }
        let parts = value.split(separator: "@", omittingEmptySubsequences: false)
        guard parts.count == 2, !parts[0].isEmpty, !parts[1].isEmpty else {
            return false
        }
        return parts[1].contains(".")
    }

    private static func urlWarning(for components: URLComponents) -> String? {
        if components.user != nil || components.password != nil {
            return "URL includes embedded credentials; verify the actual host before approving."
        }
        return nil
    }

    private static func capped(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > excerptLimit else {
            return trimmed
        }
        return String(trimmed.prefix(excerptLimit))
    }
}

public enum WorkbenchApprovalCenterSummary {
    public static func statusText(for requests: [WorkbenchApprovalRequest]) -> String {
        if requests.isEmpty {
            return "No pending approvals"
        }
        if requests.count == 1 {
            return "1 pending approval"
        }
        return "\(requests.count) pending approvals"
    }
}

private enum WorkbenchApprovalPayloadValue: Decodable, Equatable {
    case string(String)
    case number(String)
    case bool(Bool)
    case object([String: WorkbenchApprovalPayloadValue])
    case array([WorkbenchApprovalPayloadValue])
    case null

    init(from decoder: Decoder) throws {
        if let container = try? decoder.singleValueContainer() {
            if container.decodeNil() {
                self = .null
                return
            }
            if let value = try? container.decode(String.self) {
                self = .string(value)
                return
            }
            if let value = try? container.decode(Int.self) {
                self = .number(String(value))
                return
            }
            if let value = try? container.decode(Double.self) {
                self = .number(String(value))
                return
            }
            if let value = try? container.decode(Bool.self) {
                self = .bool(value)
                return
            }
        }
        if let object = try? decoder.container(keyedBy: DynamicCodingKey.self) {
            var values: [String: WorkbenchApprovalPayloadValue] = [:]
            for key in object.allKeys {
                values[key.stringValue] = try object.decode(WorkbenchApprovalPayloadValue.self, forKey: key)
            }
            self = .object(values)
            return
        }
        var array = try decoder.unkeyedContainer()
        var values: [WorkbenchApprovalPayloadValue] = []
        while !array.isAtEnd {
            values.append(try array.decode(WorkbenchApprovalPayloadValue.self))
        }
        self = .array(values)
    }
}

private enum WorkbenchApprovalPayloadFlattener {
    static func decodePayload<Key: CodingKey>(
        from container: KeyedDecodingContainer<Key>,
        forKey key: Key
    ) throws -> [String: String] {
        if let payload = try? container.decode([String: String].self, forKey: key) {
            return payload
        }
        let payload = try container.decode([String: WorkbenchApprovalPayloadValue].self, forKey: key)
        return flatten(payload)
    }

    private static func flatten(_ payload: [String: WorkbenchApprovalPayloadValue]) -> [String: String] {
        var output: [String: String] = [:]
        for (key, value) in payload {
            flatten(value, key: normalizedKey(key), into: &output)
        }
        return output
    }

    private static func flatten(
        _ value: WorkbenchApprovalPayloadValue,
        key: String,
        into output: inout [String: String]
    ) {
        switch value {
        case .string(let string):
            store(string, key: key, into: &output)
            if isRecipientKey(key), let email = emailCandidate(from: string) {
                output["recipient_email"] = email
            }
        case .number(let number):
            store(number, key: key, into: &output)
        case .bool(let bool):
            store(bool ? "true" : "false", key: key, into: &output)
        case .object(let object):
            if isRecipientKey(key), let email = firstEmail(in: .object(object)) {
                output["recipient_email"] = email
            }
            for (childKey, childValue) in object {
                flatten(childValue, key: nestedKey(parent: key, child: childKey), into: &output)
            }
        case .array(let values):
            if isRecipientKey(key), let email = firstEmail(in: .array(values)) {
                output["recipient_email"] = email
            }
            let previewValues = values.compactMap(stringValue)
            if !previewValues.isEmpty {
                store(previewValues.joined(separator: ", "), key: key, into: &output)
            }
        case .null:
            return
        }
    }

    private static func firstEmail(in value: WorkbenchApprovalPayloadValue) -> String? {
        switch value {
        case .string(let string):
            return emailCandidate(from: string)
        case .object(let object):
            for key in ["email", "address", "value", "recipient_email", "actual_recipient_email"] {
                if let value = object[key], let email = firstEmail(in: value) {
                    return email
                }
            }
            return nil
        case .array(let values):
            for value in values {
                if let email = firstEmail(in: value) {
                    return email
                }
            }
            return nil
        case .number, .bool, .null:
            return nil
        }
    }

    private static func stringValue(_ value: WorkbenchApprovalPayloadValue) -> String? {
        switch value {
        case .string(let string):
            return string
        case .number(let number):
            return number
        case .bool(let bool):
            return bool ? "true" : "false"
        case .object(let object):
            return firstEmail(in: .object(object))
        case .array, .null:
            return nil
        }
    }

    private static func emailCandidate(from raw: String) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let candidate: String
        if let start = trimmed.firstIndex(of: "<"), let end = trimmed[start...].firstIndex(of: ">") {
            candidate = String(trimmed[trimmed.index(after: start)..<end])
        } else {
            candidate = trimmed
        }
        return isLikelyEmailAddress(candidate) ? candidate : nil
    }

    private static func isLikelyEmailAddress(_ value: String) -> Bool {
        guard !value.contains(where: { $0.isWhitespace || $0 == "<" || $0 == ">" }) else {
            return false
        }
        let parts = value.split(separator: "@", omittingEmptySubsequences: false)
        guard parts.count == 2, !parts[0].isEmpty, !parts[1].isEmpty else {
            return false
        }
        return parts[1].contains(".")
    }

    private static func isRecipientKey(_ key: String) -> Bool {
        ["to", "recipient", "recipients", "recipient_email", "actual_recipient_email"].contains(key)
    }

    private static func normalizedKey(_ key: String) -> String {
        key.lowercased().replacingOccurrences(of: "-", with: "_")
    }

    private static func nestedKey(parent: String, child: String) -> String {
        let childKey = normalizedKey(child)
        guard !parent.isEmpty else {
            return childKey
        }
        return "\(parent)_\(childKey)"
    }

    private static func store(_ value: String, key: String, into output: inout [String: String]) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, output[key] == nil else { return }
        output[key] = trimmed.count > 800 ? String(trimmed.prefix(800)) + "...[truncated]" : trimmed
    }
}

private struct DynamicCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?

    init?(stringValue: String) {
        self.stringValue = stringValue
        intValue = nil
    }

    init?(intValue: Int) {
        stringValue = String(intValue)
        self.intValue = intValue
    }
}
