import Foundation

public enum WorkbenchSessionSurface: String, Codable, Sendable {
    case broker
    case queue
    case audit
    case codex
    case bridge
    case unknown
}

public enum WorkbenchSessionResumeRouteKind: String, Codable, Sendable {
    case brokerRuntime = "broker_runtime"
    case queueEvent = "queue_event"
    case auditRecord = "audit_record"
    case codexEvidence = "codex_evidence"
    case evidenceOnly = "evidence_only"
}

public struct WorkbenchSessionResumeRoute: Codable, Equatable, Sendable {
    public let kind: WorkbenchSessionResumeRouteKind
    public let runtime: RuntimeKey?
    public let targetId: String?
    public let sourcePointer: String

    public init(
        kind: WorkbenchSessionResumeRouteKind,
        runtime: RuntimeKey? = nil,
        targetId: String? = nil,
        sourcePointer: String
    ) {
        self.kind = kind
        self.runtime = runtime
        self.targetId = targetId
        self.sourcePointer = sourcePointer
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case runtime
        case targetId = "target_id"
        case sourcePointer = "source_pointer"
    }
}

public struct WorkbenchSessionRecord: Identifiable, Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let id: String
    public let surface: WorkbenchSessionSurface
    public let runtime: RuntimeKey?
    public let customerId: String?
    public let title: String
    public let status: String
    public let attentionState: WorkbenchMissionAttentionState
    public let lastActor: String
    public let updatedAt: String?
    public let nextAction: String
    public let details: [String]
    public let resumeRoute: WorkbenchSessionResumeRoute
    public let sourcePointer: String
    public let auditId: String?

    public init(
        schemaVersion: String = WorkbenchSessionContract.schemaVersion,
        id: String,
        surface: WorkbenchSessionSurface,
        runtime: RuntimeKey? = nil,
        customerId: String? = nil,
        title: String,
        status: String,
        attentionState: WorkbenchMissionAttentionState,
        lastActor: String,
        updatedAt: String? = nil,
        nextAction: String,
        details: [String] = [],
        resumeRoute: WorkbenchSessionResumeRoute,
        sourcePointer: String,
        auditId: String? = nil
    ) {
        self.schemaVersion = schemaVersion
        self.id = id
        self.surface = surface
        self.runtime = runtime
        self.customerId = customerId
        self.title = title
        self.status = status
        self.attentionState = attentionState
        self.lastActor = lastActor
        self.updatedAt = updatedAt
        self.nextAction = nextAction
        self.details = details
        self.resumeRoute = resumeRoute
        self.sourcePointer = sourcePointer
        self.auditId = auditId
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let title = try container.decode(String.self, forKey: .title)
        self.schemaVersion = try container.decode(String.self, forKey: .schemaVersion)
        self.id = try container.decode(String.self, forKey: .id)
        self.surface = try container.decode(WorkbenchSessionSurface.self, forKey: .surface)
        self.runtime = try container.decodeIfPresent(RuntimeKey.self, forKey: .runtime)
        self.customerId = try container.decodeIfPresent(String.self, forKey: .customerId)
        self.title = title
        self.status = try container.decode(String.self, forKey: .status)
        self.attentionState = try container.decode(WorkbenchMissionAttentionState.self, forKey: .attentionState)
        self.lastActor = try container.decode(String.self, forKey: .lastActor)
        self.updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
        self.nextAction = try container.decodeIfPresent(String.self, forKey: .nextAction) ?? "Review \(title)."
        self.details = try container.decodeIfPresent([String].self, forKey: .details) ?? []
        self.resumeRoute = try container.decode(WorkbenchSessionResumeRoute.self, forKey: .resumeRoute)
        self.sourcePointer = try container.decode(String.self, forKey: .sourcePointer)
        self.auditId = try container.decodeIfPresent(String.self, forKey: .auditId)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case id
        case surface
        case runtime
        case customerId = "customer_id"
        case title
        case status
        case attentionState = "attention_state"
        case lastActor = "last_actor"
        case updatedAt = "updated_at"
        case nextAction = "next_action"
        case details
        case resumeRoute = "resume_route"
        case sourcePointer = "source_pointer"
        case auditId = "audit_id"
    }
}

public enum WorkbenchSessionContract {
    public static let schemaVersion = "evaos.session_center.v1"

    public static func record(
        from card: WorkbenchMissionCard,
        customerId: String? = nil
    ) -> WorkbenchSessionRecord {
        let surface = sessionSurface(card.surface)
        let resumeRoute = route(for: card, surface: surface)
        return WorkbenchSessionRecord(
            id: card.id,
            surface: surface,
            runtime: card.runtime,
            customerId: customerId,
            title: card.title,
            status: card.status,
            attentionState: card.attentionState,
            lastActor: actor(for: surface),
            updatedAt: card.lastUpdate,
            nextAction: card.nextAction,
            details: card.details,
            resumeRoute: resumeRoute,
            sourcePointer: card.sourcePointer,
            auditId: card.auditId
        )
    }

    public static func records(
        from cards: [WorkbenchMissionCard],
        customerId: String? = nil
    ) -> [WorkbenchSessionRecord] {
        cards.map { record(from: $0, customerId: customerId) }
    }

    public static func brokerRuntimeToOpen(for record: WorkbenchSessionRecord) -> RuntimeKey? {
        guard record.surface == .broker, record.resumeRoute.kind == .brokerRuntime else {
            return nil
        }
        let runtime = record.resumeRoute.runtime ?? record.runtime
        guard let runtime, RuntimeDefinition.isBrokeredRuntime(runtime) else {
            return nil
        }
        return runtime
    }

    private static func sessionSurface(_ rawSurface: String) -> WorkbenchSessionSurface {
        WorkbenchSessionSurface(rawValue: rawSurface) ?? .unknown
    }

    private static func actor(for surface: WorkbenchSessionSurface) -> String {
        switch surface {
        case .broker:
            return "broker"
        case .queue:
            return "bridge_queue"
        case .audit:
            return "desktop_bridge"
        case .codex:
            return "codex_app_server"
        case .bridge:
            return "desktop_bridge"
        case .unknown:
            return "unknown"
        }
    }

    private static func route(
        for card: WorkbenchMissionCard,
        surface: WorkbenchSessionSurface
    ) -> WorkbenchSessionResumeRoute {
        if surface == .broker, let runtime = card.runtime, RuntimeDefinition.isBrokeredRuntime(runtime) {
            return WorkbenchSessionResumeRoute(
                kind: .brokerRuntime,
                runtime: runtime,
                targetId: runtime.rawValue,
                sourcePointer: card.sourcePointer
            )
        }
        switch surface {
        case .queue:
            return WorkbenchSessionResumeRoute(
                kind: .queueEvent,
                targetId: suffix(after: "queue:", in: card.sourcePointer),
                sourcePointer: card.sourcePointer
            )
        case .audit:
            return WorkbenchSessionResumeRoute(
                kind: .auditRecord,
                targetId: card.auditId ?? suffix(after: "audit:", in: card.sourcePointer),
                sourcePointer: card.sourcePointer
            )
        case .codex:
            return WorkbenchSessionResumeRoute(
                kind: .codexEvidence,
                targetId: card.id,
                sourcePointer: card.sourcePointer
            )
        default:
            return WorkbenchSessionResumeRoute(
                kind: .evidenceOnly,
                targetId: card.id,
                sourcePointer: card.sourcePointer
            )
        }
    }

    private static func suffix(after prefix: String, in value: String) -> String? {
        guard value.hasPrefix(prefix) else {
            return nil
        }
        return String(value.dropFirst(prefix.count))
    }
}
