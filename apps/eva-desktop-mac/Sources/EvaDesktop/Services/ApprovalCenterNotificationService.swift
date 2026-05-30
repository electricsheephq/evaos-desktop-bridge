import EvaDesktopCore
import Foundation
import UserNotifications

@MainActor
final class ApprovalCenterNotificationService {
    private let center: UNUserNotificationCenter

    init(center: UNUserNotificationCenter = .current()) {
        self.center = center
    }

    func deliver(_ notifications: [WorkbenchApprovalNotification]) async -> Set<String> {
        guard !notifications.isEmpty else { return [] }
        guard await ensureAuthorization() else { return [] }

        var deliveredRequestIDs: Set<String> = []
        for notification in notifications {
            let content = UNMutableNotificationContent()
            content.title = notification.title
            content.body = notification.body
            content.sound = .default
            content.userInfo = [
                "source_pointer": notification.sourcePointer,
                "audit_id": notification.auditID ?? "",
                "approval_request_id": notification.requestID
            ]

            let request = UNNotificationRequest(
                identifier: "evaos.approval.\(notification.requestID)",
                content: content,
                trigger: nil
            )
            do {
                try await center.add(request)
                deliveredRequestIDs.insert(notification.requestID)
            } catch {
                continue
            }
        }
        return deliveredRequestIDs
    }

    private func ensureAuthorization() async -> Bool {
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .ephemeral, .provisional:
            return true
        case .notDetermined:
            return (try? await center.requestAuthorization(options: [.alert, .sound])) == true
        case .denied:
            return false
        @unknown default:
            return false
        }
    }
}
