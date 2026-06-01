import Foundation

public struct WorkbenchTeamChatBinding: Codable, Equatable, Sendable {
    public static let schemaVersion = "evaos.team_chat_binding.v1"

    public let schemaVersion: String
    public let customerAccountID: String
    public let clickClackWorkspaceID: String
    public let workspaceRouteID: String
    public let humanUserID: String
    public let serviceBotID: String
    public let assignedAgentID: String
    public let channelID: String
    public let directMessageID: String
    public let botTokenSecretRef: String
    public let revokedAt: Date?
    public let embedURL: URL?
    public let sourcePointer: String
    public let auditID: String?

    public init(
        schemaVersion: String = WorkbenchTeamChatBinding.schemaVersion,
        customerAccountID: String,
        clickClackWorkspaceID: String,
        workspaceRouteID: String,
        humanUserID: String,
        serviceBotID: String,
        assignedAgentID: String,
        channelID: String,
        directMessageID: String,
        botTokenSecretRef: String,
        revokedAt: Date? = nil,
        embedURL: URL? = nil,
        sourcePointer: String,
        auditID: String? = nil
    ) {
        self.schemaVersion = schemaVersion
        self.customerAccountID = customerAccountID
        self.clickClackWorkspaceID = clickClackWorkspaceID
        self.workspaceRouteID = workspaceRouteID
        self.humanUserID = humanUserID
        self.serviceBotID = serviceBotID
        self.assignedAgentID = assignedAgentID
        self.channelID = channelID
        self.directMessageID = directMessageID
        self.botTokenSecretRef = botTokenSecretRef
        self.revokedAt = revokedAt
        self.embedURL = embedURL
        self.sourcePointer = sourcePointer
        self.auditID = auditID
    }

    public var isRevocable: Bool {
        !botTokenSecretRef.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public var isRevoked: Bool {
        revokedAt != nil
    }

    public var hasPilotPath: Bool {
        !customerAccountID.isEmpty
            && !clickClackWorkspaceID.isEmpty
            && !workspaceRouteID.isEmpty
            && !humanUserID.isEmpty
            && !serviceBotID.isEmpty
            && !assignedAgentID.isEmpty
            && !channelID.isEmpty
            && !directMessageID.isEmpty
            && isRevocable
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case customerAccountID = "customer_account_id"
        case clickClackWorkspaceID = "clickclack_workspace_id"
        case workspaceRouteID = "workspace_route_id"
        case humanUserID = "human_user_id"
        case serviceBotID = "service_bot_id"
        case assignedAgentID = "assigned_agent_id"
        case channelID = "channel_id"
        case directMessageID = "direct_message_id"
        case botTokenSecretRef = "bot_token_secret_ref"
        case revokedAt = "revoked_at"
        case embedURL = "embed_url"
        case sourcePointer = "source_pointer"
        case auditID = "audit_id"
    }
}
