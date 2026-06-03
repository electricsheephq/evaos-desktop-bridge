import Foundation

public enum WorkbenchTodayItemKind: String, Codable, CaseIterable, Sendable {
    case connectedAppNeeded = "connected_app_needed"
    case approvalNeeded = "approval_needed"
    case browserLoginNeeded = "browser_login_needed"
    case agentRunning = "agent_running"
    case agentDone = "agent_done"
    case agentBlocked = "agent_blocked"
    case companyBrainSourceNeeded = "company_brain_source_needed"
    case recentWork = "recent_work"
    case scheduledWork = "scheduled_work"
    case systemAttention = "system_attention"
}

public enum WorkbenchTodayItemStatus: String, Codable, Sendable {
    case needsInput = "needs_input"
    case active
    case done
    case scheduled
    case blocked
    case idle
    case unavailable
}

public struct WorkbenchTodayItem: Identifiable, Codable, Equatable, Sendable {
    public static let schemaVersion = "evaos.today_item.v1"

    public let schemaVersion: String
    public let id: String
    public let kind: WorkbenchTodayItemKind
    public let title: String
    public let status: WorkbenchTodayItemStatus
    public let nextAction: String
    public let assignedAgentID: String?
    public let assignedUserID: String?
    public let sourcePointer: String
    public let auditID: String?
    public let updatedAt: String?
    public let resumeRoute: WorkbenchSessionResumeRoute
    public let technicalDetails: [String]

    public init(
        schemaVersion: String = WorkbenchTodayItem.schemaVersion,
        id: String,
        kind: WorkbenchTodayItemKind,
        title: String,
        status: WorkbenchTodayItemStatus,
        nextAction: String,
        assignedAgentID: String? = nil,
        assignedUserID: String? = nil,
        sourcePointer: String,
        auditID: String? = nil,
        updatedAt: String? = nil,
        resumeRoute: WorkbenchSessionResumeRoute? = nil,
        technicalDetails: [String] = []
    ) {
        self.schemaVersion = schemaVersion
        self.id = id
        self.kind = kind
        self.title = title
        self.status = status
        self.nextAction = nextAction
        self.assignedAgentID = assignedAgentID
        self.assignedUserID = assignedUserID
        self.sourcePointer = sourcePointer
        self.auditID = auditID
        self.updatedAt = updatedAt
        self.resumeRoute = resumeRoute ?? WorkbenchSessionResumeRoute(
            kind: .evidenceOnly,
            targetId: id,
            sourcePointer: sourcePointer
        )
        self.technicalDetails = Self.defaultTechnicalDetails(
            sourcePointer: sourcePointer,
            auditID: auditID,
            details: technicalDetails
        )
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.schemaVersion = try container.decode(String.self, forKey: .schemaVersion)
        guard schemaVersion == Self.schemaVersion else {
            throw DecodingError.dataCorruptedError(
                forKey: .schemaVersion,
                in: container,
                debugDescription: "Unsupported Workbench Today item schema version"
            )
        }
        self.id = try container.decode(String.self, forKey: .id)
        self.kind = try container.decode(WorkbenchTodayItemKind.self, forKey: .kind)
        self.title = try container.decode(String.self, forKey: .title)
        self.status = try container.decode(WorkbenchTodayItemStatus.self, forKey: .status)
        self.nextAction = try container.decode(String.self, forKey: .nextAction)
        self.assignedAgentID = try container.decodeIfPresent(String.self, forKey: .assignedAgentID)
        self.assignedUserID = try container.decodeIfPresent(String.self, forKey: .assignedUserID)
        self.sourcePointer = try container.decode(String.self, forKey: .sourcePointer)
        self.auditID = try container.decodeIfPresent(String.self, forKey: .auditID)
        self.updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
        self.resumeRoute = try container.decodeIfPresent(WorkbenchSessionResumeRoute.self, forKey: .resumeRoute)
            ?? WorkbenchSessionResumeRoute(kind: .evidenceOnly, targetId: id, sourcePointer: sourcePointer)
        self.technicalDetails = Self.defaultTechnicalDetails(
            sourcePointer: sourcePointer,
            auditID: auditID,
            details: try container.decodeIfPresent([String].self, forKey: .technicalDetails) ?? []
        )
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case id
        case kind
        case title
        case status
        case nextAction = "next_action"
        case assignedAgentID = "assigned_agent_id"
        case assignedUserID = "assigned_user_id"
        case sourcePointer = "source_pointer"
        case auditID = "audit_id"
        case updatedAt = "updated_at"
        case resumeRoute = "resume_route"
        case technicalDetails = "technical_details"
    }

    private static func defaultTechnicalDetails(
        sourcePointer: String,
        auditID: String?,
        details: [String]
    ) -> [String] {
        var merged = details
        if !merged.contains(where: { $0.hasPrefix("Source:") }) {
            merged.insert("Source: \(sourcePointer)", at: 0)
        }
        if let auditID, !merged.contains(where: { $0.contains(auditID) }) {
            merged.insert("Audit: \(auditID)", at: min(1, merged.count))
        }
        return merged
    }
}

public enum WorkbenchTodayItemDeriver {
    public static func items(
        from records: [WorkbenchSessionRecord],
        recentRecords: [WorkbenchSessionRecord],
        limit: Int = 12
    ) -> [WorkbenchTodayItem] {
        let currentItems = records.compactMap(item(from:))
        let recentItems = recentRecords.compactMap(recentWorkItem(from:))
        return Array((currentItems + recentItems).prefix(limit))
    }

    private static func item(from record: WorkbenchSessionRecord) -> WorkbenchTodayItem? {
        if record.sourcePointer.lowercased().contains("company_brain") {
            return baseItem(
                record: record,
                kind: .companyBrainSourceNeeded,
                title: "Check Company Brain sources",
                status: .needsInput,
                nextAction: record.nextAction
            )
        }

        switch record.surface {
        case .connectedApps:
            return connectedAppItem(from: record)
        case .assignedAgent:
            return assignedAgentItem(from: record)
        case .broker:
            return brokerItem(from: record)
        case .queue:
            return queueItem(from: record)
        case .audit, .codex, .bridge, .unknown:
            if record.attentionState == .needsAttention {
                return baseItem(
                    record: record,
                    kind: .systemAttention,
                    title: "Eva needs a support check",
                    status: .needsInput,
                    nextAction: record.nextAction
                )
            }
            return nil
        }
    }

    private static func assignedAgentItem(from record: WorkbenchSessionRecord) -> WorkbenchTodayItem {
        if record.attentionState == .active,
           let scheduledWorkTitle = detailValue(prefix: "Scheduled work:", in: record.details) {
            return scheduledAgentItem(from: record, scheduledWorkTitle: scheduledWorkTitle)
        }

        let kind: WorkbenchTodayItemKind
        let status: WorkbenchTodayItemStatus
        let title: String
        switch record.attentionState {
        case .done:
            kind = .agentDone
            status = .done
            title = "\(record.title) finished"
        case .needsAttention:
            kind = .agentBlocked
            status = .blocked
            title = "\(record.title) is blocked"
        case .active:
            kind = .agentRunning
            status = .active
            title = "\(record.title) is running"
        case .idle, .unknown:
            kind = .agentRunning
            status = .idle
            title = "\(record.title) is ready"
        }
        return baseItem(
            record: record,
            kind: kind,
            title: title,
            status: status,
            nextAction: record.nextAction,
            assignedAgentID: detailValue(prefix: "Agent ID:", in: record.details),
            assignedUserID: detailValue(prefix: "Assigned user:", in: record.details)
        )
    }

    private static func scheduledAgentItem(
        from record: WorkbenchSessionRecord,
        scheduledWorkTitle: String
    ) -> WorkbenchTodayItem {
        let assignedAgent = detailValue(prefix: "Agent display:", in: record.details) ?? record.title
        let cadence = detailValue(prefix: "Schedule:", in: record.details)
        let nextRun = detailValue(prefix: "Next run:", in: record.details)
        let pauseAction = detailValue(prefix: "Pause:", in: record.details) ?? "Open Agent to pause or adjust this schedule."
        var nextActionParts = ["Assigned to \(assignedAgent)."]
        if let nextRun {
            nextActionParts.append("Next run: \(nextRun).")
        } else if let cadence {
            nextActionParts.append("Runs \(cadence).")
        }
        nextActionParts.append(pauseAction)

        return baseItem(
            record: record,
            kind: .scheduledWork,
            title: "\(scheduledWorkTitle) is scheduled",
            status: .scheduled,
            nextAction: nextActionParts.joined(separator: " "),
            assignedAgentID: detailValue(prefix: "Agent ID:", in: record.details),
            assignedUserID: detailValue(prefix: "Assigned user:", in: record.details)
        )
    }

    private static func connectedAppItem(from record: WorkbenchSessionRecord) -> WorkbenchTodayItem {
        if record.attentionState == .needsAttention {
            return baseItem(
                record: record,
                kind: .connectedAppNeeded,
                title: "Connect \(record.title)",
                status: .needsInput,
                nextAction: record.nextAction
            )
        }
        return baseItem(
            record: record,
            kind: .recentWork,
            title: "\(record.title) is connected",
            status: .active,
            nextAction: "Eva can use \(record.title) when an assigned task needs it."
        )
    }

    private static func brokerItem(from record: WorkbenchSessionRecord) -> WorkbenchTodayItem? {
        if record.runtime == .liveBrowser && record.attentionState == .needsAttention {
            return baseItem(
                record: record,
                kind: .browserLoginNeeded,
                title: "Sign in to Business Browser",
                status: .needsInput,
                nextAction: record.nextAction
            )
        }
        if record.attentionState == .needsAttention {
            return baseItem(
                record: record,
                kind: .systemAttention,
                title: "\(record.title) needs attention",
                status: .needsInput,
                nextAction: record.nextAction
            )
        }
        if record.attentionState == .active {
            return baseItem(
                record: record,
                kind: .recentWork,
                title: "Resume \(record.title)",
                status: .active,
                nextAction: record.nextAction
            )
        }
        return nil
    }

    private static func queueItem(from record: WorkbenchSessionRecord) -> WorkbenchTodayItem? {
        switch record.status {
        case "approval_needed":
            return baseItem(
                record: record,
                kind: .approvalNeeded,
                title: "Review an approval request",
                status: .needsInput,
                nextAction: record.nextAction
            )
        case "done":
            return baseItem(
                record: record,
                kind: .agentDone,
                title: "Eva finished a queued task",
                status: .done,
                nextAction: record.nextAction
            )
        default:
            if record.attentionState == .needsAttention {
                return baseItem(
                    record: record,
                    kind: .systemAttention,
                    title: "Eva needs your attention",
                    status: .needsInput,
                    nextAction: record.nextAction
                )
            }
            return nil
        }
    }

    private static func recentWorkItem(from record: WorkbenchSessionRecord) -> WorkbenchTodayItem? {
        guard let runtime = record.resumeRoute.runtime ?? record.runtime,
              runtime != .terminal,
              RuntimeDefinition.isBrokeredRuntime(runtime) || RuntimeDefinition.externalURL(for: runtime) != nil else {
            return nil
        }
        return baseItem(
            record: record,
            kind: .recentWork,
            title: "Resume \(record.title)",
            status: .idle,
            nextAction: "Open \(record.title) again."
        )
    }

    private static func baseItem(
        record: WorkbenchSessionRecord,
        kind: WorkbenchTodayItemKind,
        title: String,
        status: WorkbenchTodayItemStatus,
        nextAction: String,
        assignedAgentID: String? = nil,
        assignedUserID: String? = nil
    ) -> WorkbenchTodayItem {
        WorkbenchTodayItem(
            id: "today-\(record.id)",
            kind: kind,
            title: title,
            status: status,
            nextAction: nextAction,
            assignedAgentID: assignedAgentID,
            assignedUserID: assignedUserID,
            sourcePointer: record.sourcePointer,
            auditID: record.auditId,
            updatedAt: record.updatedAt,
            resumeRoute: record.resumeRoute,
            technicalDetails: record.details
        )
    }

    private static func detailValue(prefix: String, in details: [String]) -> String? {
        details.first { $0.hasPrefix(prefix) }?
            .dropFirst(prefix.count)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
