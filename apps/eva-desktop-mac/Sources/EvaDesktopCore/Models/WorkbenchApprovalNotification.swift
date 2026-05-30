import Foundation

public struct WorkbenchApprovalNotification: Equatable, Sendable {
    public let notificationID: String
    public let requestID: String
    public let title: String
    public let body: String
    public let sourcePointer: String
    public let auditID: String?

    public init(
        notificationID: String? = nil,
        requestID: String,
        title: String,
        body: String,
        sourcePointer: String,
        auditID: String? = nil
    ) {
        self.notificationID = notificationID ?? requestID
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
        approvalCenterVisible: Bool,
        now: Date = Date()
    ) -> WorkbenchApprovalNotificationPlan {
        let currentIDs = Set(requests.map(\.id))
        let currentNotificationIDs = currentIDs.union(currentIDs.map(expiringNotificationID(for:)))
        var nextNotifiedIDs = notifiedRequestIDs.intersection(currentNotificationIDs)

        if approvalCenterVisible {
            nextNotifiedIDs.formUnion(currentIDs)
            return WorkbenchApprovalNotificationPlan(
                notifications: [],
                pendingRequestIDs: currentIDs,
                notifiedRequestIDs: nextNotifiedIDs
            )
        }

        let newRequestNotifications = requests
            .filter { !previousPendingIDs.contains($0.id) && !nextNotifiedIDs.contains($0.id) }
            .map(notification(for:))
        let expiringNotifications = requests
            .filter { previousPendingIDs.contains($0.id) }
            .filter { $0.isExpiringSoon(now: now) }
            .filter { !nextNotifiedIDs.contains(expiringNotificationID(for: $0.id)) }
            .map { expiringNotification(for: $0, now: now) }
        let notifications = newRequestNotifications + expiringNotifications

        nextNotifiedIDs.formUnion(notifications.map(\.notificationID))
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

    private static func expiringNotification(for request: WorkbenchApprovalRequest, now: Date) -> WorkbenchApprovalNotification {
        let expirationText = request.expirationText(now: now) ?? "Expires soon"
        return WorkbenchApprovalNotification(
            notificationID: expiringNotificationID(for: request.id),
            requestID: request.id,
            title: "Approval expiring: \(capped(request.toolName, limit: 48))",
            body: "\(expirationText). Open Approval Center to decide before the runtime times out.",
            sourcePointer: request.sourcePointer,
            auditID: request.auditId
        )
    }

    private static func expiringNotificationID(for requestID: String) -> String {
        "\(requestID):expiring"
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
