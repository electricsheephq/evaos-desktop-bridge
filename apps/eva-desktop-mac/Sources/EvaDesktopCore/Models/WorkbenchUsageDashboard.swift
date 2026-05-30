import Foundation

public struct WorkbenchUsageStats: Codable, Equatable, Sendable {
    public let callCount: Int
    public let totalInputTokens: Int
    public let totalOutputTokens: Int
    public let costUSD: Double
    public let errorCount: Int
    public let avgLatencyMS: Double?
    public let p50LatencyMS: Double?
    public let p95LatencyMS: Double?

    public var totalTokens: Int {
        totalInputTokens + totalOutputTokens
    }

    enum CodingKeys: String, CodingKey {
        case callCount = "call_count"
        case totalInputTokens = "total_input_tokens"
        case totalOutputTokens = "total_output_tokens"
        case costUSD = "cost_usd"
        case errorCount = "error_count"
        case avgLatencyMS = "avg_latency_ms"
        case p50LatencyMS = "p50_latency_ms"
        case p95LatencyMS = "p95_latency_ms"
    }
}

public struct WorkbenchAgentUsageBucket: Codable, Equatable, Sendable {
    public let tiers: [String: WorkbenchUsageStats]
    public let byOperation: [String: [String: WorkbenchUsageStats]]
    public let total: WorkbenchUsageStats

    enum CodingKeys: String, CodingKey {
        case tiers
        case byOperation = "by_operation"
        case total
    }
}

public struct WorkbenchLLMUsageResponse: Codable, Equatable, Sendable {
    public let tiers: [String: WorkbenchUsageStats]
    public let byOperation: [String: [String: WorkbenchUsageStats]]
    public let byAgent: [String: WorkbenchAgentUsageBucket]
    public let total: WorkbenchUsageStats?
    public let generatedAt: String?
    public let errors: [String]

    enum CodingKeys: String, CodingKey {
        case tiers
        case byOperation = "by_operation"
        case byAgent = "by_agent"
        case total
        case generatedAt = "generated_at"
        case errors
    }
}

public struct WorkbenchAgentUsageCard: Identifiable, Equatable, Sendable {
    public let id: String
    public let agentID: String
    public let title: String
    public let status: String
    public let attentionState: WorkbenchMissionAttentionState
    public let callCount: Int
    public let tokenTotal: Int
    public let tokenCap: Int?
    public let costUSD: Double
    public let dollarCap: Double?
    public let tokenProgress: Double?
    public let dollarProgress: Double?
    public let nextAction: String
    public let primaryActionTitle: String?
    public let secondaryActionTitle: String?
    public let sourcePointer: String
}

public struct WorkbenchBudgetNotificationPlan: Equatable, Sendable {
    public let notifications: [WorkbenchApprovalNotification]
    public let notifiedAgentIDs: Set<String>
}

public enum WorkbenchUsageDashboardDeriver {
    public static func cards(
        from usage: WorkbenchLLMUsageResponse,
        manifestSummary: WorkbenchCapabilityManifestSummary?
    ) -> [WorkbenchAgentUsageCard] {
        var cards = usage.byAgent
            .map { agentID, bucket in
                card(
                    agentID: agentID,
                    stats: bucket.total,
                    budget: agentID == manifestSummary?.agentID ? manifestSummary?.budget : nil
                )
            }
            .sorted { $0.agentID.localizedStandardCompare($1.agentID) == .orderedAscending }

        if
            let manifestSummary,
            usage.byAgent[manifestSummary.agentID] == nil
        {
            cards.append(
                card(
                    agentID: manifestSummary.agentID,
                    stats: emptyStats(),
                    budget: manifestSummary.budget
                )
            )
        }

        return cards
    }

    private static func card(
        agentID: String,
        stats: WorkbenchUsageStats,
        budget: WorkbenchCapabilityBudget?
    ) -> WorkbenchAgentUsageCard {
        let tokenProgress = progress(value: Double(stats.totalTokens), cap: budget?.tokensPerDay.map(Double.init))
        let dollarProgress = progress(value: stats.costUSD, cap: budget?.dollarsPerDay)
        let budgetPaused = (tokenProgress.map { $0 >= 1.0 } ?? false) || (dollarProgress.map { $0 >= 1.0 } ?? false)
        let status: String
        let attentionState: WorkbenchMissionAttentionState
        let nextAction: String
        let primaryAction: String?
        let secondaryAction: String?

        if budgetPaused {
            status = "Budget paused"
            attentionState = .needsAttention
            primaryAction = increaseCapTitle(for: budget)
            secondaryAction = "Stop agent"
            nextAction = "\(primaryAction ?? "Increase cap") or stop agent."
        } else if stats.callCount > 0 {
            status = "Active"
            attentionState = .active
            primaryAction = nil
            secondaryAction = nil
            nextAction = "Monitor usage against the manifest budget."
        } else {
            status = "Idle"
            attentionState = .idle
            primaryAction = nil
            secondaryAction = nil
            nextAction = "No usage recorded for this agent today."
        }

        return WorkbenchAgentUsageCard(
            id: "usage-\(agentID)",
            agentID: agentID,
            title: agentID,
            status: status,
            attentionState: attentionState,
            callCount: stats.callCount,
            tokenTotal: stats.totalTokens,
            tokenCap: budget?.tokensPerDay,
            costUSD: stats.costUSD,
            dollarCap: budget?.dollarsPerDay,
            tokenProgress: tokenProgress,
            dollarProgress: dollarProgress,
            nextAction: nextAction,
            primaryActionTitle: primaryAction,
            secondaryActionTitle: secondaryAction,
            sourcePointer: "usage:agent:\(agentID)"
        )
    }

    private static func progress(value: Double, cap: Double?) -> Double? {
        guard let cap, cap > 0 else { return nil }
        return min(1.0, max(0.0, value / cap))
    }

    private static func increaseCapTitle(for budget: WorkbenchCapabilityBudget?) -> String {
        if let dollars = budget?.dollarsPerDay, dollars > 0 {
            return "Increase cap to $\(wholeDollarString(dollars * 2))"
        }
        if let tokens = budget?.tokensPerDay, tokens > 0 {
            return "Increase cap to \(tokens * 2) tokens"
        }
        return "Increase cap"
    }

    private static func wholeDollarString(_ value: Double) -> String {
        if value.rounded() == value {
            return String(Int(value))
        }
        return String(format: "%.2f", value)
    }

    private static func emptyStats() -> WorkbenchUsageStats {
        WorkbenchUsageStats(
            callCount: 0,
            totalInputTokens: 0,
            totalOutputTokens: 0,
            costUSD: 0,
            errorCount: 0,
            avgLatencyMS: nil,
            p50LatencyMS: nil,
            p95LatencyMS: nil
        )
    }
}

public enum WorkbenchBudgetNotificationPlanner {
    public static func plan(
        cards: [WorkbenchAgentUsageCard],
        notifiedAgentIDs: Set<String>,
        usageDashboardVisible: Bool
    ) -> WorkbenchBudgetNotificationPlan {
        let pausedCards = cards.filter { $0.attentionState == .needsAttention && $0.status == "Budget paused" }
        let pausedIDs = Set(pausedCards.map(\.agentID))
        var nextNotified = notifiedAgentIDs.intersection(pausedIDs)

        guard !usageDashboardVisible else {
            nextNotified.formUnion(pausedIDs)
            return WorkbenchBudgetNotificationPlan(notifications: [], notifiedAgentIDs: nextNotified)
        }

        let notifications = pausedCards
            .filter { !nextNotified.contains($0.agentID) }
            .map { card in
                WorkbenchApprovalNotification(
                    notificationID: "budget:\(card.agentID)",
                    requestID: "budget:\(card.agentID)",
                    title: "Budget paused: \(card.agentID)",
                    body: "\(card.primaryActionTitle ?? "Increase cap") or \(card.secondaryActionTitle?.lowercased() ?? "stop agent").",
                    sourcePointer: card.sourcePointer,
                    auditID: nil
                )
            }
        nextNotified.formUnion(pausedIDs)
        return WorkbenchBudgetNotificationPlan(notifications: notifications, notifiedAgentIDs: nextNotified)
    }
}
