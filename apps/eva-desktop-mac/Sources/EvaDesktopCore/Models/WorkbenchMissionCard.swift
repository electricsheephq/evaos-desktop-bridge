import Foundation

public enum WorkbenchMissionAttentionState: String, Codable, Sendable {
    case active
    case done
    case idle
    case needsAttention = "needs_attention"
    case unknown
}

public struct WorkbenchMissionCard: Identifiable, Codable, Equatable, Sendable {
    public let id: String
    public let surface: String
    public let runtime: RuntimeKey?
    public let title: String
    public let status: String
    public let attentionState: WorkbenchMissionAttentionState
    public let lastUpdate: String?
    public let nextAction: String
    public let details: [String]
    public let sourcePointer: String
    public let auditId: String?

    public init(
        id: String,
        surface: String,
        runtime: RuntimeKey? = nil,
        title: String,
        status: String,
        attentionState: WorkbenchMissionAttentionState,
        lastUpdate: String? = nil,
        nextAction: String,
        details: [String] = [],
        sourcePointer: String,
        auditId: String? = nil
    ) {
        self.id = id
        self.surface = surface
        self.runtime = runtime
        self.title = title
        self.status = status
        self.attentionState = attentionState
        self.lastUpdate = lastUpdate
        self.nextAction = nextAction
        self.details = details
        self.sourcePointer = sourcePointer
        self.auditId = auditId
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decode(String.self, forKey: .id)
        self.surface = try container.decode(String.self, forKey: .surface)
        self.runtime = try container.decodeIfPresent(RuntimeKey.self, forKey: .runtime)
        self.title = try container.decode(String.self, forKey: .title)
        self.status = try container.decode(String.self, forKey: .status)
        self.attentionState = try container.decode(WorkbenchMissionAttentionState.self, forKey: .attentionState)
        self.lastUpdate = try container.decodeIfPresent(String.self, forKey: .lastUpdate)
        self.nextAction = try container.decode(String.self, forKey: .nextAction)
        self.details = try container.decodeIfPresent([String].self, forKey: .details) ?? []
        self.sourcePointer = try container.decode(String.self, forKey: .sourcePointer)
        self.auditId = try container.decodeIfPresent(String.self, forKey: .auditId)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case surface
        case runtime
        case title
        case status
        case attentionState = "attention_state"
        case lastUpdate = "last_update"
        case nextAction = "next_action"
        case details
        case sourcePointer = "source_pointer"
        case auditId = "audit_id"
    }
}

public enum WorkbenchMissionCardDeriver {
    public static func runtimeCard(
        definition: RuntimeDefinition,
        status: RuntimeStatusResponse?,
        localURLLoaded: Bool,
        error: String? = nil
    ) -> WorkbenchMissionCard {
        let attention: WorkbenchMissionAttentionState
        let statusText: String
        let detail: String
        let lastUpdate = status?.lastActivityAt ?? status?.lastCheckedAt

        if let error {
            attention = .needsAttention
            statusText = "Needs attention"
            detail = error
        } else if let status {
            attention = runtimeAttentionState(status: status, localURLLoaded: localURLLoaded)
            statusText = runtimeStatusText(status: status.status, localURLLoaded: localURLLoaded)
            detail = runtimeNextAction(definition: definition, status: status)
        } else if localURLLoaded {
            attention = .active
            statusText = "Loaded"
            detail = "Workspace is open in Workbench; refresh Home for current status."
        } else {
            attention = .idle
            statusText = "Unchecked"
            detail = "Refresh Home to check this workspace."
        }

        return WorkbenchMissionCard(
            id: "runtime-\(definition.key.rawValue)",
            surface: "broker",
            runtime: definition.key,
            title: definition.title,
            status: statusText,
            attentionState: attention,
            lastUpdate: isoString(lastUpdate),
            nextAction: detail,
            details: runtimeDetails(status: status, fallback: definition.subtitle),
            sourcePointer: "broker:runtime_status:\(definition.key.rawValue)",
            auditId: nil
        )
    }

    public static func queueCards(from raw: String, limit: Int = 10) -> [WorkbenchMissionCard] {
        guard let object = jsonObject(from: raw), object["ok"] as? Bool == true else {
            return raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? [] : [
                bridgeFailureCard(id: "queue-unavailable", title: "Announcement Queue", sourcePointer: "bridge:queue.list")
            ]
        }
        let events = value(at: ["data", "events"], in: object) as? [[String: Any]] ?? []
        return events.prefix(limit).compactMap { event in
            guard let queueId = event["queue_id"] as? String else { return nil }
            let kind = event["kind"] as? String ?? "unknown"
            let message = event["message"] as? String
            let sourceAuditId = event["source_audit_id"] as? String
            return WorkbenchMissionCard(
                id: "queue-\(queueId)",
                surface: "queue",
                runtime: nil,
                title: queueTitle(kind),
                status: kind,
                attentionState: queueAttentionState(kind),
                lastUpdate: event["timestamp"] as? String,
                nextAction: capped(message ?? queueNextAction(kind)),
                sourcePointer: "queue:\(queueId)",
                auditId: sourceAuditId
            )
        }
    }

    public static func auditCards(from raw: String, limit: Int = 3) -> [WorkbenchMissionCard] {
        guard let object = jsonObject(from: raw), object["ok"] as? Bool == true else {
            return raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? [] : [
                bridgeFailureCard(id: "audit-unavailable", title: "Bridge Audit", sourcePointer: "bridge:audit-tail")
            ]
        }
        let records = value(at: ["data", "records"], in: object) as? [[String: Any]] ?? []
        return records.prefix(limit).compactMap { record in
            guard let auditId = record["audit_id"] as? String else { return nil }
            let command = record["command"] as? String ?? "unknown"
            let ok = record["ok"] as? Bool
            return WorkbenchMissionCard(
                id: "audit-\(auditId)",
                surface: "audit",
                runtime: nil,
                title: "Bridge Audit",
                status: ok == false ? "failed" : "ok",
                attentionState: ok == false ? .needsAttention : .done,
                lastUpdate: record["timestamp"] as? String,
                nextAction: capped(command),
                sourcePointer: "audit:\(auditId)",
                auditId: auditId
            )
        }
    }

    public static func codexCards(statusRaw: String, remoteRaw: String, threadsRaw: String) -> [WorkbenchMissionCard] {
        var cards: [WorkbenchMissionCard] = []
        cards.append(codexReadinessCard(statusRaw: statusRaw, remoteRaw: remoteRaw))
        if let threadsCard = codexThreadsCard(threadsRaw: threadsRaw) {
            cards.append(threadsCard)
        }
        return cards
    }

    public static func providerCards(from profiles: [WorkbenchProviderProfileState]) -> [WorkbenchMissionCard] {
        profiles.compactMap { profile in
            guard profile.status != .planned else { return nil }

            let attention: WorkbenchMissionAttentionState
            let nextAction: String
            switch profile.status {
            case .connected:
                if profile.hasConnectionProof {
                    attention = .active
                    nextAction = profile.hasBrokeredGrant
                        ? "\(profile.title) is connected and Eva has an auditable access handle."
                        : "\(profile.title) is connected. Allow Eva when you want agents to use it."
                } else {
                    attention = .needsAttention
                    nextAction = "Refresh Connected Apps to verify \(profile.title) before agents use it."
                }
            case .needsLogin:
                attention = .needsAttention
                nextAction = "Open Connected Apps and sign in to \(profile.title) in the Business Browser."
            case .revoked:
                attention = .needsAttention
                nextAction = "\(profile.title) access was disconnected. Reconnect it before assigned agents use it."
            case .expired:
                attention = .needsAttention
                nextAction = "\(profile.title) access expired. Reconnect it in Connected Apps."
            case .error:
                attention = .needsAttention
                nextAction = profile.usageSummary ?? "Connected Apps could not verify \(profile.title)."
            case .planned:
                return nil
            }

            let expiryDetail = profile.expiresAt.flatMap { expiry in
                isoString(expiry).map { "Expires: \($0)" }
            }
            let details = [
                profile.accountLabel.map { "Account: \($0)" },
                profile.hasBrokeredGrant ? "Eva access handle: ready" : nil,
                expiryDetail,
            ].compactMap { $0 }

            return WorkbenchMissionCard(
                id: "provider-\(profile.key.rawValue)",
                surface: "connected_apps",
                runtime: nil,
                title: profile.title,
                status: profile.status.displayText,
                attentionState: attention,
                lastUpdate: isoString(profile.lastValidatedAt ?? profile.display?.lastCheckedAt),
                nextAction: nextAction,
                details: details,
                sourcePointer: profile.sourcePointer ?? "broker:provider_grant:\(profile.key.rawValue)",
                auditId: profile.auditID
            )
        }
    }

    private static func codexReadinessCard(statusRaw: String, remoteRaw: String) -> WorkbenchMissionCard {
        guard let statusObject = jsonObject(from: statusRaw), statusObject["ok"] as? Bool == true else {
            return bridgeFailureCard(id: "codex-readiness", title: "Codex Readiness", sourcePointer: "bridge:codex.app_server.status")
        }
        let available = value(at: ["data", "available"], in: statusObject) as? Bool
        let remoteObject = jsonObject(from: remoteRaw)
        let remoteOK = remoteObject?["ok"] as? Bool
        let supported = value(at: ["data", "remote_control_command", "supported"], in: remoteObject ?? [:]) as? Bool
        let daemon = value(at: ["data", "daemon", "version_available"], in: remoteObject ?? [:]) as? Bool
        let attention: WorkbenchMissionAttentionState = available == true ? .active : .needsAttention
        let status = available == true ? "available" : "unavailable"
        let detail = [
            "App-server \(status)",
            remoteOK == true ? nil : "remote status unavailable",
            supported.map { "remote command \($0 ? "detected" : "missing")" },
            daemon.map { "daemon \($0 ? "reported" : "unreported")" },
        ].compactMap { $0 }.joined(separator: "; ")

        return WorkbenchMissionCard(
            id: "codex-readiness",
            surface: "codex",
            runtime: nil,
            title: "Codex Readiness",
            status: status,
            attentionState: attention,
            lastUpdate: nil,
            nextAction: detail,
            sourcePointer: "bridge:codex.app_server.status",
            auditId: statusObject["audit_id"] as? String
        )
    }

    private static func codexThreadsCard(threadsRaw: String) -> WorkbenchMissionCard? {
        guard let object = jsonObject(from: threadsRaw), object["ok"] as? Bool == true else {
            return bridgeFailureCard(id: "codex-threads", title: "Codex Threads", sourcePointer: "bridge:codex.app_server.threads")
        }
        let threads = value(at: ["data", "threads"], in: object) as? [[String: Any]] ?? []
        guard !threads.isEmpty else {
            return WorkbenchMissionCard(
                id: "codex-threads",
                surface: "codex",
                runtime: nil,
                title: "Codex Threads",
                status: "idle",
                attentionState: .idle,
                lastUpdate: nil,
                nextAction: "No app-server thread summaries returned.",
                sourcePointer: "bridge:codex.app_server.threads",
                auditId: object["audit_id"] as? String
            )
        }
        let title = threads.first?["title"] as? String ?? "Recent Codex thread"
        return WorkbenchMissionCard(
            id: "codex-threads",
            surface: "codex",
            runtime: nil,
            title: "Codex Threads",
            status: "\(threads.count) visible",
            attentionState: .active,
            lastUpdate: threads.first?["updated_at"] as? String,
            nextAction: capped(title),
            sourcePointer: "bridge:codex.app_server.threads",
            auditId: object["audit_id"] as? String
        )
    }

    private static func runtimeAttentionState(status: RuntimeStatusResponse, localURLLoaded: Bool) -> WorkbenchMissionAttentionState {
        let normalized = normalizedRuntimeStatus(status.status)
        if status.authNeeded == true || status.captchaNeeded == true || status.waitingOnUser == true || status.updateAvailable == true {
            return .needsAttention
        }
        switch normalized {
        case "degraded", "disabled", "error", "failed", "unavailable", "offline":
            return .needsAttention
        case "enabled", "active", "ready", "loaded":
            return .active
        case "coming_soon", "coming-soon", "unknown":
            return .unknown
        default:
            if status.controlSessionActive == true || localURLLoaded {
                return .active
            }
            return .idle
        }
    }

    private static func runtimeStatusText(status: String, localURLLoaded: Bool) -> String {
        switch normalizedRuntimeStatus(status) {
        case "enabled", "ready":
            return localURLLoaded ? "Loaded" : "Ready"
        case "active", "loaded":
            return "Active"
        case "degraded", "error", "failed":
            return "Needs attention"
        case "disabled":
            return "Blocked"
        case "unavailable", "offline", "coming_soon", "coming-soon":
            return "Unavailable"
        default:
            return status
                .replacingOccurrences(of: "_", with: " ")
                .replacingOccurrences(of: "-", with: " ")
                .capitalized
        }
    }

    private static func runtimeNextAction(definition: RuntimeDefinition, status: RuntimeStatusResponse) -> String {
        if status.authNeeded == true {
            return "\(definition.title) needs sign-in."
        }
        if status.captchaNeeded == true {
            return "\(definition.title) reports CAPTCHA needed."
        }
        if status.waitingOnUser == true {
            return "\(definition.title) is waiting on the user."
        }
        if status.updateAvailable == true {
            return "\(definition.title) has an update available."
        }
        if status.controlSessionActive == true {
            return "\(definition.title) has an active control session."
        }
        if definition.key == .liveBrowser {
            switch normalizedRuntimeStatus(status.status) {
            case "unavailable", "offline", "degraded", "error", "failed":
                return "Open Business Browser to start or reattach; refresh status after it loads."
            default:
                break
            }
        }
        switch normalizedRuntimeStatus(status.status) {
        case "unavailable", "offline":
            return "\(definition.title) is unavailable right now."
        case "degraded", "error", "failed":
            return status.healthSummary ?? "\(definition.title) reports a runtime error."
        case "disabled":
            return status.healthSummary ?? "\(definition.title) is disabled."
        default:
            break
        }
        return status.healthSummary ?? definition.subtitle
    }

    private static func runtimeDetails(status: RuntimeStatusResponse?, fallback: String) -> [String] {
        guard let status else { return [fallback] }
        return [
            status.roomId.map { "Room: \(capped($0, limit: 80))" },
            status.owner.map { "Owner: \(capped($0, limit: 80))" },
            safeURLSummary(status.currentUrl).map { "Current URL: \($0)" },
            (status.lastActivityAt ?? status.lastCheckedAt).flatMap { isoString($0) }.map { "Last activity: \($0)" },
        ].compactMap { $0 }
    }

    private static func safeURLSummary(_ value: String?) -> String? {
        guard let value, let url = URL(string: value) else {
            return nil
        }
        let path = String(url.path.prefix(80))
        if let host = url.host, !host.isEmpty {
            return capped(host + path, limit: 140)
        }
        if !path.isEmpty {
            return path
        }
        return nil
    }

    private static func normalizedRuntimeStatus(_ status: String) -> String {
        status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private static func queueAttentionState(_ kind: String) -> WorkbenchMissionAttentionState {
        switch kind {
        case "approval_needed", "attention", "error":
            return .needsAttention
        case "done":
            return .done
        case "idle":
            return .idle
        default:
            return .unknown
        }
    }

    private static func queueTitle(_ kind: String) -> String {
        switch kind {
        case "approval_needed":
            return "Approval Needed"
        case "done":
            return "Queue Done"
        case "error":
            return "Queue Error"
        case "idle":
            return "Queue Idle"
        case "attention":
            return "Needs Attention"
        default:
            return "Queue Event"
        }
    }

    private static func queueNextAction(_ kind: String) -> String {
        switch kind {
        case "approval_needed":
            return "Review the referenced audit record before continuing."
        case "attention":
            return "Review the referenced bridge event."
        case "error":
            return "Inspect the source audit record for failure details."
        case "done":
            return "No action required."
        case "idle":
            return "No active queue work."
        default:
            return "Queue event kind is not recognized."
        }
    }

    private static func bridgeFailureCard(id: String, title: String, sourcePointer: String) -> WorkbenchMissionCard {
        WorkbenchMissionCard(
            id: id,
            surface: "bridge",
            runtime: nil,
            title: title,
            status: "unavailable",
            attentionState: .needsAttention,
            lastUpdate: nil,
            nextAction: "Read-only bridge evidence was unavailable or malformed.",
            sourcePointer: sourcePointer,
            auditId: nil
        )
    }

    private static func jsonObject(from raw: String) -> [String: Any]? {
        guard let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return nil
        }
        return object
    }

    private static func value(at path: [String], in object: [String: Any]) -> Any? {
        var current: Any? = object
        for key in path {
            current = (current as? [String: Any])?[key]
        }
        return current
    }

    private static func isoString(_ date: Date?) -> String? {
        guard let date else { return nil }
        return ISO8601DateFormatter().string(from: date)
    }

    private static func capped(_ value: String, limit: Int = 180) -> String {
        if value.count <= limit {
            return value
        }
        return String(value.prefix(limit)) + "..."
    }
}
