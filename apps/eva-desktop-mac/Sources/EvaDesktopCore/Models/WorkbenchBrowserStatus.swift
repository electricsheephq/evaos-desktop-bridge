import Foundation

public enum WorkbenchBrowserAction: String, Codable, Equatable, Sendable {
    case startAttach = "start_attach"
    case refreshStatus = "refresh_status"
    case stopBrowser = "stop_browser"
}

public struct WorkbenchBrowserURLSummary: Codable, Equatable, Sendable {
    public let host: String
    public let path: String?
    public let queryRedacted: Bool

    enum CodingKeys: String, CodingKey {
        case host
        case path
        case queryRedacted = "query_redacted"
    }

    public init(host: String, path: String? = nil, queryRedacted: Bool = false) {
        self.host = host
        self.path = path
        self.queryRedacted = queryRedacted
    }

    public static func sanitized(from rawURL: String?) -> WorkbenchBrowserURLSummary? {
        guard
            let rawURL,
            let components = URLComponents(string: rawURL),
            let host = components.host,
            !host.isEmpty
        else {
            return nil
        }
        let path = components.path.isEmpty || components.path == "/" ? nil : components.path
        return WorkbenchBrowserURLSummary(
            host: host,
            path: path,
            queryRedacted: components.query != nil || components.fragment != nil
        )
    }

    public var displayText: String {
        let pathText = path ?? ""
        let redactionText = queryRedacted ? "..." : ""
        return "\(host)\(pathText)\(redactionText)"
    }
}

public struct WorkbenchBrowserStatus: Codable, Equatable, Sendable {
    public static let schemaVersion = "evaos.browser_status.v1"

    public let schemaVersion: String
    public let customerAccountID: String?
    public let customerID: String
    public let runtime: RuntimeKey
    public let status: String
    public let roomID: String?
    public let sessionID: String?
    public let owner: String?
    public let currentURL: WorkbenchBrowserURLSummary?
    public let lastActivityAt: Date?
    public let needsAuth: Bool
    public let needsCaptcha: Bool
    public let actions: [WorkbenchBrowserAction]
    public let sourcePointer: String
    public let auditID: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case customerAccountID = "customer_account_id"
        case customerID = "customer_id"
        case runtime
        case status
        case roomID = "room_id"
        case sessionID = "session_id"
        case owner
        case currentURL = "current_url"
        case lastActivityAt = "last_activity_at"
        case needsAuth = "needs_auth"
        case needsCaptcha = "needs_captcha"
        case actions
        case sourcePointer = "source_pointer"
        case auditID = "audit_id"
    }

    public init(
        schemaVersion: String = WorkbenchBrowserStatus.schemaVersion,
        customerAccountID: String? = nil,
        customerID: String,
        runtime: RuntimeKey = .liveBrowser,
        status: String,
        roomID: String? = nil,
        sessionID: String? = nil,
        owner: String? = nil,
        currentURL: WorkbenchBrowserURLSummary? = nil,
        lastActivityAt: Date? = nil,
        needsAuth: Bool = false,
        needsCaptcha: Bool = false,
        actions: [WorkbenchBrowserAction] = [.startAttach, .refreshStatus, .stopBrowser],
        sourcePointer: String = "broker:runtime_status:browser",
        auditID: String? = nil
    ) {
        self.schemaVersion = schemaVersion
        self.customerAccountID = customerAccountID
        self.customerID = customerID
        self.runtime = runtime
        self.status = status
        self.roomID = roomID
        self.sessionID = sessionID
        self.owner = owner
        self.currentURL = currentURL
        self.lastActivityAt = lastActivityAt
        self.needsAuth = needsAuth
        self.needsCaptcha = needsCaptcha
        self.actions = actions
        self.sourcePointer = sourcePointer
        self.auditID = auditID
    }

    public static func from(runtimeStatus status: RuntimeStatusResponse, customerID: String) -> WorkbenchBrowserStatus {
        WorkbenchBrowserStatus(
            schemaVersion: status.schemaVersion ?? WorkbenchBrowserStatus.schemaVersion,
            customerAccountID: status.customerAccountID,
            customerID: status.customerID ?? customerID,
            runtime: status.runtimeKey,
            status: status.status,
            roomID: status.roomId,
            sessionID: status.sessionID,
            owner: status.owner,
            currentURL: status.currentURLSummary ?? WorkbenchBrowserURLSummary.sanitized(from: status.currentUrl),
            lastActivityAt: status.lastActivityAt ?? status.lastCheckedAt,
            needsAuth: status.authNeeded ?? false,
            needsCaptcha: status.captchaNeeded ?? false,
            actions: status.browserActions ?? [.startAttach, .refreshStatus, .stopBrowser],
            sourcePointer: status.sourcePointer ?? "broker:runtime_status:\(status.runtimeKey.rawValue)",
            auditID: status.auditID
        )
    }
}
