import Foundation

public struct WorkbenchRecentLaunchRecord: Identifiable, Codable, Equatable, Sendable {
    public let id: String
    public let runtime: RuntimeKey
    public let customerId: String
    public let title: String
    public let status: String
    public let openedAt: String
    public let nextAction: String
    public let details: [String]
    public let sourcePointer: String

    public init(
        runtime: RuntimeKey,
        customerId: String,
        openedAt: String? = nil
    ) {
        let definition = RuntimeDefinition.definition(for: runtime)
        let safeCustomerId = WorkbenchRecentLaunchStore.sanitizedCustomerId(customerId)
        let timestamp = openedAt ?? ISO8601DateFormatter().string(from: Date())
        self.id = "recent-\(runtime.rawValue)"
        self.runtime = runtime
        self.customerId = safeCustomerId
        self.title = definition.title
        self.status = "Restorable"
        self.openedAt = timestamp
        self.nextAction = "Reopen with a fresh broker URL."
        self.details = [
            "Runtime metadata only",
            "Last opened: \(timestamp)"
        ]
        self.sourcePointer = "broker:runtime_status:\(runtime.rawValue)"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case runtime
        case customerId = "customer_id"
        case title
        case status
        case openedAt = "opened_at"
        case nextAction = "next_action"
        case details
        case sourcePointer = "source_pointer"
    }
}

public enum WorkbenchRecentLaunchStore {
    public static let maxRecords = 8

    public static func storageKey(customerId: String) -> String {
        "EvaDesktop.recentLaunches.\(sanitizedCustomerId(customerId))"
    }

    public static func sanitizedCustomerId(_ value: String) -> String {
        let lowercased = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let parts = lowercased
            .split { character in
                !character.isLetter && !character.isNumber
            }
            .map(String.init)
        let sanitized = parts.joined(separator: "-")
        return sanitized.isEmpty ? "unknown" : sanitized
    }

    public static func records(
        from data: Data?,
        customerId: String,
        maxRecords: Int = WorkbenchRecentLaunchStore.maxRecords
    ) -> [WorkbenchRecentLaunchRecord] {
        guard let data, let decoded = try? JSONDecoder().decode([WorkbenchRecentLaunchRecord].self, from: data) else {
            return []
        }
        let scopedCustomerId = sanitizedCustomerId(customerId)
        return Array(decoded
            .filter { sanitizedCustomerId($0.customerId) == scopedCustomerId }
            .filter { RuntimeDefinition.isBrokeredRuntime($0.runtime) }
            .sorted(by: isNewer)
            .prefix(maxRecords))
    }

    public static func merged(
        _ record: WorkbenchRecentLaunchRecord,
        into existing: [WorkbenchRecentLaunchRecord],
        maxRecords: Int = WorkbenchRecentLaunchStore.maxRecords
    ) -> [WorkbenchRecentLaunchRecord] {
        let withoutDuplicateRuntime = existing.filter {
            !($0.runtime == record.runtime && sanitizedCustomerId($0.customerId) == sanitizedCustomerId(record.customerId))
        }
        return Array(([record] + withoutDuplicateRuntime)
            .sorted(by: isNewer)
            .prefix(maxRecords))
    }

    public static func sessionRecords(
        from records: [WorkbenchRecentLaunchRecord]
    ) -> [WorkbenchSessionRecord] {
        records.map { sessionRecord(from: $0) }
    }

    public static func sessionRecord(
        from record: WorkbenchRecentLaunchRecord
    ) -> WorkbenchSessionRecord {
        WorkbenchSessionRecord(
            id: record.id,
            surface: .broker,
            runtime: record.runtime,
            customerId: record.customerId,
            title: record.title,
            status: record.status,
            attentionState: .idle,
            lastActor: "workbench",
            updatedAt: record.openedAt,
            nextAction: record.nextAction,
            details: record.details,
            resumeRoute: WorkbenchSessionResumeRoute(
                kind: .brokerRuntime,
                runtime: record.runtime,
                targetId: record.runtime.rawValue,
                sourcePointer: record.sourcePointer
            ),
            sourcePointer: record.sourcePointer,
            auditId: nil
        )
    }

    private static func isNewer(
        _ lhs: WorkbenchRecentLaunchRecord,
        _ rhs: WorkbenchRecentLaunchRecord
    ) -> Bool {
        switch (openedAtDate(lhs.openedAt), openedAtDate(rhs.openedAt)) {
        case let (lhsDate?, rhsDate?):
            if lhsDate == rhsDate {
                return lhs.openedAt > rhs.openedAt
            }
            return lhsDate > rhsDate
        case (_?, nil):
            return true
        case (nil, _?):
            return false
        case (nil, nil):
            return lhs.openedAt > rhs.openedAt
        }
    }

    private static func openedAtDate(_ value: String) -> Date? {
        EvaDesktopISO8601.parse(value)
    }
}
