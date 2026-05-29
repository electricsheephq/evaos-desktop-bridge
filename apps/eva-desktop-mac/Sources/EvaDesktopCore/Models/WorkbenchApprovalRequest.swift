import Foundation

public enum WorkbenchApprovalRiskClass: String, Codable, Equatable, Sendable {
    case critical
    case warning
    case info
}

public enum WorkbenchApprovalDecision: String, Codable, Equatable, Sendable {
    case allowOnce = "allow_once"
    case allowAlways = "allow_always"
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
        actionPayload = try container.decode([String: String].self, forKey: .actionPayload)
        createdAt = try container.decode(String.self, forKey: .createdAt)
        sourcePointer = try container.decode(String.self, forKey: .sourcePointer)
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
        [.allowOnce, .allowAlways, .deny]
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

public enum WorkbenchApprovalPreviewBuilder {
    public static let excerptLimit = 220

    public static func preview(toolName: String, payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        let normalizedTool = toolName.lowercased()
        if normalizedTool.contains("gmail") || normalizedTool.contains("email") {
            return emailPreview(payload)
        }
        if normalizedTool.contains("browser") || normalizedTool.contains("fetch") || normalizedTool.contains("url") {
            return urlPreview(payload)
        }
        if normalizedTool.contains("slack") || normalizedTool.contains("message") {
            return messagePreview(payload)
        }
        if normalizedTool.contains("delete") || normalizedTool.contains("file") || normalizedTool.contains("drive.write") {
            return filePreview(payload)
        }
        if normalizedTool.contains("purchase") || normalizedTool.contains("payment") || normalizedTool.contains("money") {
            return purchasePreview(payload)
        }
        if normalizedTool.contains("secret") {
            return namedPreview(.secretName, keys: ["secret_name", "secret_id", "name"], payload: payload)
        }
        if normalizedTool.contains("budget") {
            return namedPreview(.budget, keys: ["budget", "amount", "limit"], payload: payload)
        }
        if normalizedTool.contains("permission") || normalizedTool.contains("scope") {
            return namedPreview(.permission, keys: ["permission", "scope", "grant"], payload: payload)
        }
        return missingDestinationPreview()
    }

    private static func emailPreview(_ payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        guard let recipient = emailAddress(in: payload, keys: ["recipient_email", "actual_recipient_email"]) else {
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
        guard let url = firstValue(in: payload, keys: ["url", "target_url", "actual_url"]) else {
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
            warning: nil
        )
    }

    private static func messagePreview(_ payload: [String: String]) -> WorkbenchApprovalDestinationPreview {
        guard let recipient = firstValue(in: payload, keys: ["recipient_id", "channel_id", "actual_recipient_id", "actual_channel_id"]) else {
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
