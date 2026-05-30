import Foundation

public struct WorkbenchApprovalNotification: Equatable, Sendable {
    public let requestID: String
    public let title: String
    public let body: String
    public let sourcePointer: String
    public let auditID: String?

    public init(requestID: String, title: String, body: String, sourcePointer: String, auditID: String? = nil) {
        self.requestID = requestID
        self.title = title
        self.body = body
        self.sourcePointer = sourcePointer
        self.auditID = auditID
    }
}

public struct WorkbenchApprovalNotificationPlan: Equatable, Sendable {
    public let notifications: [WorkbenchApprovalNotification]
    public let pendingRequestIDs: Set<String>
    public let notifiedRequestIDs: Set<String>

    public init(
        notifications: [WorkbenchApprovalNotification],
        pendingRequestIDs: Set<String>,
        notifiedRequestIDs: Set<String>
    ) {
        self.notifications = notifications
        self.pendingRequestIDs = pendingRequestIDs
        self.notifiedRequestIDs = notifiedRequestIDs
    }
}

public enum WorkbenchApprovalNotificationPlanner {
    private static let destinationLimit = 96

    public static func plan(
        requests: [WorkbenchApprovalRequest],
        previousPendingIDs: Set<String>,
        notifiedRequestIDs: Set<String>,
        approvalCenterVisible: Bool
    ) -> WorkbenchApprovalNotificationPlan {
        let currentIDs = Set(requests.map(\.id))
        var nextNotifiedIDs = notifiedRequestIDs.intersection(currentIDs)

        if approvalCenterVisible {
            nextNotifiedIDs.formUnion(currentIDs)
            return WorkbenchApprovalNotificationPlan(
                notifications: [],
                pendingRequestIDs: currentIDs,
                notifiedRequestIDs: nextNotifiedIDs
            )
        }

        let notifications = requests
            .filter { !previousPendingIDs.contains($0.id) && !nextNotifiedIDs.contains($0.id) }
            .map(notification(for:))

        nextNotifiedIDs.formUnion(notifications.map(\.requestID))
        return WorkbenchApprovalNotificationPlan(
            notifications: notifications,
            pendingRequestIDs: currentIDs,
            notifiedRequestIDs: nextNotifiedIDs
        )
    }

    private static func notification(for request: WorkbenchApprovalRequest) -> WorkbenchApprovalNotification {
        WorkbenchApprovalNotification(
            requestID: request.id,
            title: "Approval needed: \(capped(request.toolName, limit: 48))",
            body: body(for: request),
            sourcePointer: request.sourcePointer,
            auditID: request.auditId
        )
    }

    private static func body(for request: WorkbenchApprovalRequest) -> String {
        guard request.destinationPreview.isActionable else {
            return "Missing actual destination. Open Approval Center to review before deciding."
        }

        let destination = capped(request.destinationPreview.primary, limit: destinationLimit)
        switch request.riskClass {
        case .critical:
            return "Critical action for \(destination). Open Approval Center to review actual destination."
        case .warning:
            return "Review \(destination) before allowing this agent action."
        case .info:
            return "Confirm \(destination) before allowing this agent action."
        }
    }

    private static func capped(_ value: String, limit: Int) -> String {
        guard value.count > limit else { return value }
        let prefix = value.prefix(max(0, limit - 3))
        return "\(prefix)..."
    }
}
