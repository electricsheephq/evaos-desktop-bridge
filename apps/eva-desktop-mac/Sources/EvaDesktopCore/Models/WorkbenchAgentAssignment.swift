import Foundation

public enum WorkbenchAccountRole: String, Codable, CaseIterable, Sendable {
    case owner
    case admin
    case billingAdmin = "billing_admin"
    case technicalAdmin = "technical_admin"
    case manager
    case member
    case agentOnly = "agent_only"
    case support
}

public struct WorkbenchAgentAssignmentApprovalPolicy: Codable, Equatable, Sendable {
    public let defaultMode: String
    public let allowAlwaysFingerprints: [String]

    public init(defaultMode: String = "ask", allowAlwaysFingerprints: [String] = []) {
        self.defaultMode = defaultMode
        self.allowAlwaysFingerprints = allowAlwaysFingerprints
    }

    enum CodingKeys: String, CodingKey {
        case defaultMode = "default"
        case allowAlwaysFingerprints = "allow_always_fingerprints"
    }
}

public struct WorkbenchAgentAssignmentBudget: Codable, Equatable, Sendable {
    public let dailyUSD: Double?
    public let dailyTokens: Int?

    public init(dailyUSD: Double? = nil, dailyTokens: Int? = nil) {
        self.dailyUSD = dailyUSD
        self.dailyTokens = dailyTokens
    }

    enum CodingKeys: String, CodingKey {
        case dailyUSD = "daily_usd"
        case dailyTokens = "daily_tokens"
    }
}

public struct WorkbenchAgentAssignmentSchedule: Codable, Equatable, Sendable {
    public let enabled: Bool
    public let taskTitle: String?
    public let cadenceLabel: String?
    public let nextRunAt: String?
    public let dueWindow: String?
    public let timezone: String?

    public init(
        enabled: Bool = false,
        taskTitle: String? = nil,
        cadenceLabel: String? = nil,
        nextRunAt: String? = nil,
        dueWindow: String? = nil,
        timezone: String? = nil
    ) {
        self.enabled = enabled
        self.taskTitle = Self.clean(taskTitle)
        self.cadenceLabel = Self.clean(cadenceLabel)
        self.nextRunAt = Self.clean(nextRunAt)
        self.dueWindow = Self.clean(dueWindow)
        self.timezone = Self.clean(timezone)
    }

    public var displayCadence: String {
        guard enabled else { return "Not scheduled" }
        return cadenceLabel ?? "Scheduled work"
    }

    public var displayNextRun: String? {
        guard enabled else { return nil }
        return dueWindow ?? nextRunAt
    }

    public var pauseActionText: String? {
        guard enabled else { return nil }
        return "Open Agent to pause or adjust this schedule."
    }

    enum CodingKeys: String, CodingKey {
        case enabled
        case taskTitle = "task_title"
        case cadenceLabel = "cadence_label"
        case nextRunAt = "next_run_at"
        case dueWindow = "due_window"
        case timezone
    }

    private static func clean(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }
}

public enum WorkbenchAgentAssignmentState: String, Codable, Sendable {
    case running
    case paused
    case blocked
    case done
    case revoked
    case unknown
}

public struct WorkbenchAgentAssignmentKillSwitch: Codable, Equatable, Sendable {
    public let enabled: Bool
    public let state: WorkbenchAgentAssignmentState

    public init(enabled: Bool = true, state: WorkbenchAgentAssignmentState = .running) {
        self.enabled = enabled
        self.state = state
    }
}

public struct WorkbenchAgentAssignment: Identifiable, Codable, Equatable, Sendable {
    public static let schemaVersion = "evaos.agent_assignment.v1"

    public let schemaVersion: String
    public let assignmentID: String
    public let customerAccountID: String
    public let assignedUserID: String
    public let agentID: String
    public let agentDisplayName: String
    public let runtime: RuntimeKey
    public let allowedProviderGrants: [String]
    public let allowedSurfaces: [String]
    public let approvalPolicy: WorkbenchAgentAssignmentApprovalPolicy
    public let budget: WorkbenchAgentAssignmentBudget
    public let schedule: WorkbenchAgentAssignmentSchedule
    public let killSwitch: WorkbenchAgentAssignmentKillSwitch
    public let sourcePointer: String
    public let auditID: String?

    public var id: String { assignmentID }

    public init(
        schemaVersion: String = WorkbenchAgentAssignment.schemaVersion,
        assignmentID: String,
        customerAccountID: String,
        assignedUserID: String,
        agentID: String,
        agentDisplayName: String,
        runtime: RuntimeKey = .openclaw,
        allowedProviderGrants: [String],
        allowedSurfaces: [String],
        approvalPolicy: WorkbenchAgentAssignmentApprovalPolicy = WorkbenchAgentAssignmentApprovalPolicy(),
        budget: WorkbenchAgentAssignmentBudget = WorkbenchAgentAssignmentBudget(),
        schedule: WorkbenchAgentAssignmentSchedule = WorkbenchAgentAssignmentSchedule(),
        killSwitch: WorkbenchAgentAssignmentKillSwitch = WorkbenchAgentAssignmentKillSwitch(),
        sourcePointer: String,
        auditID: String? = nil
    ) {
        self.schemaVersion = schemaVersion
        self.assignmentID = assignmentID
        self.customerAccountID = customerAccountID
        self.assignedUserID = assignedUserID
        self.agentID = agentID
        self.agentDisplayName = agentDisplayName
        self.runtime = runtime
        self.allowedProviderGrants = Self.normalizedList(allowedProviderGrants)
        self.allowedSurfaces = Self.normalizedList(allowedSurfaces)
        self.approvalPolicy = approvalPolicy
        self.budget = budget
        self.schedule = schedule
        self.killSwitch = killSwitch
        self.sourcePointer = sourcePointer
        self.auditID = auditID
    }

    public var statusText: String {
        switch killSwitch.state {
        case .running:
            return "Running"
        case .paused:
            return "Paused"
        case .blocked:
            return "Blocked"
        case .done:
            return "Done"
        case .revoked:
            return "Revoked"
        case .unknown:
            return "Unknown"
        }
    }

    public var attentionState: WorkbenchMissionAttentionState {
        switch killSwitch.state {
        case .running:
            return .active
        case .done:
            return .done
        case .paused, .blocked, .revoked:
            return .needsAttention
        case .unknown:
            return .unknown
        }
    }

    public var nextAction: String {
        switch killSwitch.state {
        case .running:
            if schedule.enabled {
                let nextRun = schedule.displayNextRun.map { " Next run: \($0)." } ?? ""
                let pause = schedule.pauseActionText.map { " \($0)" } ?? ""
                return "\(agentDisplayName) is scheduled for \(schedule.displayCadence).\(nextRun)\(pause)"
            }
            return "\(agentDisplayName) is limited to assigned apps, budget, and approval rules."
        case .paused:
            return "Owner or admin can resume \(agentDisplayName) in Dashboard."
        case .blocked:
            return "Review app access, budget, approvals, or the kill switch before resuming."
        case .done:
            return "\(agentDisplayName) finished the assigned work."
        case .revoked:
            return "\(agentDisplayName) assignment was revoked. Assign again from Dashboard if needed."
        case .unknown:
            return "Refresh account policy before using this assignment."
        }
    }

    public func allowsSurface(_ surface: String) -> Bool {
        allowedSurfaces.contains(Self.normalize(surface))
    }

    public func canUseProviderGrant(_ grant: String) -> Bool {
        allowedProviderGrants.contains(Self.normalize(grant))
    }

    public func canUseProviderProfile(_ profile: WorkbenchProviderProfileState) -> Bool {
        let directIdentifiers = [
            profile.grantID,
            profile.grantHandle,
            profile.sourcePointer,
            profile.key.rawValue,
        ].compactMap { $0 }.map(Self.normalize)
        if directIdentifiers.contains(where: allowedProviderGrants.contains) {
            return true
        }
        return allowedProviderGrants.contains { grant in
            providerGrantPrefixMatches(profile.key, grant: grant)
        }
    }

    public func canPause(role: WorkbenchAccountRole) -> Bool {
        WorkbenchAgentAssignmentAccessPolicy.canAdministerAssignments(role: role)
    }

    public func canRevoke(role: WorkbenchAccountRole) -> Bool {
        WorkbenchAgentAssignmentAccessPolicy.canAdministerAssignments(role: role)
    }

    public static func fromCapabilitySummary(
        _ summary: WorkbenchCapabilityManifestSummary,
        customerAccountID: String,
        assignedUserID: String,
        displayName: String? = nil
    ) -> WorkbenchAgentAssignment {
        let providerGrants = (summary.tools(for: .allowed) + summary.tools(for: .requiresApproval))
            .map(normalize)
            .filter { !$0.isEmpty }
            .sorted()
        let assignmentID = "assign-\(slug(summary.agentID))"
        return WorkbenchAgentAssignment(
            assignmentID: assignmentID,
            customerAccountID: customerAccountID,
            assignedUserID: assignedUserID,
            agentID: summary.agentID,
            agentDisplayName: displayName?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? displayName! : summary.agentID,
            runtime: .openclaw,
            allowedProviderGrants: providerGrants,
            allowedSurfaces: ["today", "business_browser", "creative_studio", "connected_apps", "approvals"],
            approvalPolicy: WorkbenchAgentAssignmentApprovalPolicy(defaultMode: "ask"),
            budget: WorkbenchAgentAssignmentBudget(
                dailyUSD: summary.budget.dollarsPerDay,
                dailyTokens: summary.budget.tokensPerDay
            ),
            schedule: WorkbenchAgentAssignmentSchedule(enabled: false),
            killSwitch: WorkbenchAgentAssignmentKillSwitch(enabled: true, state: .running),
            sourcePointer: "dashboard:agent_assignment:\(assignmentID)",
            auditID: nil
        )
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case assignmentID = "assignment_id"
        case customerAccountID = "customer_account_id"
        case assignedUserID = "assigned_user_id"
        case agentID = "agent_id"
        case agentDisplayName = "agent_display_name"
        case runtime
        case allowedProviderGrants = "allowed_provider_grants"
        case allowedSurfaces = "allowed_surfaces"
        case approvalPolicy = "approval_policy"
        case budget
        case schedule
        case killSwitch = "kill_switch"
        case sourcePointer = "source_pointer"
        case auditID = "audit_id"
    }

    private static func normalizedList(_ values: [String]) -> [String] {
        values.map(normalize).filter { !$0.isEmpty }
    }

    private static func normalize(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func providerGrantPrefixMatches(_ key: WorkbenchProviderKey, grant: String) -> Bool {
        let normalizedGrant = grant.lowercased()
        switch key {
        case .googleWorkspace:
            return normalizedGrant.hasPrefix("gmail.")
                || normalizedGrant.hasPrefix("calendar.")
                || normalizedGrant.hasPrefix("drive.")
                || normalizedGrant.hasPrefix("google_workspace")
        case .pipedream:
            return normalizedGrant.hasPrefix("pipedream")
        case .slack:
            return normalizedGrant.hasPrefix("slack.")
        case .notion:
            return normalizedGrant.hasPrefix("notion.")
        case .linear:
            return normalizedGrant.hasPrefix("linear.")
        case .github:
            return normalizedGrant.hasPrefix("github.")
        case .openAICodex:
            return normalizedGrant.hasPrefix("codex.")
                || normalizedGrant.hasPrefix("openai_codex")
        case .openClaw:
            return normalizedGrant.hasPrefix("openclaw.")
                || normalizedGrant.hasPrefix("open_claw")
        case .hermes:
            return normalizedGrant.hasPrefix("hermes.")
        }
    }

    private static func slug(_ value: String) -> String {
        let lowered = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let allowed = lowered.unicodeScalars.map { scalar -> Character in
            CharacterSet.alphanumerics.contains(scalar) ? Character(scalar) : "-"
        }
        let collapsed = String(allowed)
            .split(separator: "-", omittingEmptySubsequences: true)
            .joined(separator: "-")
        return collapsed.isEmpty ? "agent" : collapsed
    }
}

public enum WorkbenchAgentAssignmentAccessPolicy {
    public static func visibleSurfaces(
        for role: WorkbenchAccountRole,
        assignment: WorkbenchAgentAssignment?
    ) -> Set<String> {
        switch role {
        case .owner, .admin:
            return [
                "today",
                "connected_apps",
                "approvals",
                "business_browser",
                "creative_studio",
                "company_brain",
                "members",
                "billing",
                "technical_dashboards",
                "terminal",
                "team_chat",
                "assigned_agent_workspace"
            ]
        case .technicalAdmin, .support:
            return [
                "today",
                "connected_apps",
                "approvals",
                "business_browser",
                "creative_studio",
                "company_brain",
                "technical_dashboards",
                "terminal",
                "team_chat",
                "assigned_agent_workspace"
            ]
        case .billingAdmin:
            return ["today", "billing"]
        case .manager:
            return ["today", "approvals", "business_browser", "creative_studio", "company_brain", "assigned_agent_workspace"]
        case .member:
            return ["today", "business_browser", "creative_studio", "company_brain", "assigned_agent_workspace"]
        case .agentOnly:
            var surfaces = Set(assignment?.allowedSurfaces ?? [])
            surfaces.insert("assigned_agent_workspace")
            return surfaces
        }
    }

    public static func canAdministerAssignments(role: WorkbenchAccountRole) -> Bool {
        switch role {
        case .owner, .admin, .technicalAdmin:
            return true
        case .billingAdmin, .manager, .member, .agentOnly, .support:
            return false
        }
    }

    public static func canAccessTechnicalDashboards(role: WorkbenchAccountRole) -> Bool {
        switch role {
        case .owner, .admin, .technicalAdmin, .support:
            return true
        case .billingAdmin, .manager, .member, .agentOnly:
            return false
        }
    }

    public static func canAccessRuntime(
        _ runtime: RuntimeKey,
        role: WorkbenchAccountRole,
        assignment: WorkbenchAgentAssignment?
    ) -> Bool {
        guard role == .agentOnly else {
            return true
        }
        guard let assignment else {
            return false
        }
        switch runtime {
        case .liveBrowser:
            return assignment.allowsSurface("business_browser")
        case .creativeStudio:
            return assignment.allowsSurface("creative_studio")
        case .openDesign:
            return assignment.allowsSurface("open_design")
        case .teamChat:
            return assignment.allowsSurface("team_chat")
        case .openclaw, .hermes, .missionControl, .terminal:
            return false
        }
    }
}
