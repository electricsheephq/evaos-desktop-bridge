import CryptoKit
import Foundation
import LocalAuthentication
import Security

public enum WorkbenchCapabilityGrantDecision: String, Codable, Equatable, Hashable, Sendable {
    case allowed
    case requiresApproval = "requires_approval"
    case denied
}

public struct WorkbenchCapabilityBudget: Codable, Equatable, Sendable {
    public let tokensPerDay: Int?
    public let dollarsPerDay: Double?

    public init(tokensPerDay: Int? = nil, dollarsPerDay: Double? = nil) {
        self.tokensPerDay = tokensPerDay
        self.dollarsPerDay = dollarsPerDay
    }

    enum CodingKeys: String, CodingKey {
        case tokensPerDay = "tokens_per_day"
        case dollarsPerDay = "dollars_per_day"
    }
}

public struct WorkbenchCapabilityManifestClaims: Codable, Equatable, Sendable {
    public let agentID: String
    public let ownerID: String
    public let issuedAt: Date
    public let expiresAt: Date
    public let grants: [String: WorkbenchCapabilityGrantDecision]
    public let budget: WorkbenchCapabilityBudget
    public let approvalChannel: String
    public let issuer: String
    public let audience: String

    public init(
        agentID: String,
        ownerID: String,
        issuedAt: Date,
        expiresAt: Date,
        grants: [String: WorkbenchCapabilityGrantDecision],
        budget: WorkbenchCapabilityBudget,
        approvalChannel: String,
        issuer: String,
        audience: String
    ) {
        self.agentID = agentID
        self.ownerID = ownerID
        self.issuedAt = issuedAt
        self.expiresAt = expiresAt
        self.grants = grants
        self.budget = budget
        self.approvalChannel = approvalChannel
        self.issuer = issuer
        self.audience = audience
    }

    public func decision(for toolName: String) -> WorkbenchCapabilityGrantDecision {
        grants[toolName] ?? .denied
    }

    public var safeSummary: WorkbenchCapabilityManifestSummary {
        var grouped: [WorkbenchCapabilityGrantDecision: [String]] = [
            .allowed: [],
            .requiresApproval: [],
            .denied: []
        ]
        for (toolName, decision) in grants {
            grouped[decision, default: []].append(toolName)
        }
        for decision in grouped.keys {
            grouped[decision]?.sort()
        }
        return WorkbenchCapabilityManifestSummary(
            agentID: agentID,
            ownerID: ownerID,
            expiresAt: expiresAt,
            approvalChannel: approvalChannel,
            budget: budget,
            grants: grouped
        )
    }

    enum CodingKeys: String, CodingKey {
        case agentID = "agent_id"
        case ownerID = "owner_id"
        case issuedAt = "issued_at"
        case expiresAt = "expires_at"
        case grants
        case budget
        case approvalChannel = "approval_channel"
        case issuer = "iss"
        case audience = "aud"
    }
}

public struct WorkbenchCapabilityManifestSummary: Equatable, Sendable {
    public let agentID: String
    public let ownerID: String
    public let expiresAt: Date
    public let approvalChannel: String
    public let budget: WorkbenchCapabilityBudget
    public let grants: [WorkbenchCapabilityGrantDecision: [String]]

    public var totalGrantCount: Int {
        grants.values.reduce(0) { total, tools in
            total + tools.count
        }
    }

    public func tools(for decision: WorkbenchCapabilityGrantDecision) -> [String] {
        grants[decision] ?? []
    }
}

public struct WorkbenchCapabilityManifestWireSummary: Codable, Equatable, Sendable {
    public let agentID: String
    public let ownerID: String
    public let expiresAt: Date
    public let approvalChannel: String
    public let budget: WorkbenchCapabilityBudget
    public let grants: [String: [String]]

    public var safeSummary: WorkbenchCapabilityManifestSummary? {
        guard
            !Self.isBlank(agentID),
            !Self.isBlank(ownerID),
            !Self.isBlank(approvalChannel)
        else {
            return nil
        }

        var grouped: [WorkbenchCapabilityGrantDecision: [String]] = [
            .allowed: [],
            .requiresApproval: [],
            .denied: []
        ]

        for (rawDecision, rawTools) in grants {
            guard let decision = WorkbenchCapabilityGrantDecision(rawValue: rawDecision) else {
                return nil
            }
            let tools = rawTools
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
                .sorted()
            grouped[decision, default: []].append(contentsOf: tools)
        }

        for decision in grouped.keys {
            grouped[decision]?.sort()
        }

        guard grouped.values.contains(where: { !$0.isEmpty }) else {
            return nil
        }

        return WorkbenchCapabilityManifestSummary(
            agentID: agentID,
            ownerID: ownerID,
            expiresAt: expiresAt,
            approvalChannel: approvalChannel,
            budget: budget,
            grants: grouped
        )
    }

    enum CodingKeys: String, CodingKey {
        case agentID = "agent_id"
        case ownerID = "owner_id"
        case expiresAt = "expires_at"
        case approvalChannel = "approval_channel"
        case budget
        case grants
    }

    private static func isBlank(_ value: String) -> Bool {
        value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

public struct WorkbenchCapabilityManifestFetchResponse: Codable, Equatable, Sendable {
    public let ok: Bool?
    public let agentID: String
    public let ownerID: String
    public let manifestJWT: String
    public let expiresAt: Date
    public let approvalChannel: String
    public let grantCount: Int?
    public let budget: WorkbenchCapabilityBudget
    public let safeSummary: WorkbenchCapabilityManifestWireSummary?
    public let agentAssignments: [WorkbenchAgentAssignment]?

    public var brokerSafeSummary: WorkbenchCapabilityManifestSummary? {
        safeSummary?.safeSummary
    }

    public func validatedCacheToken() -> String? {
        let token = manifestJWT.trimmingCharacters(in: .whitespacesAndNewlines)
        guard
            ok != false,
            !token.isEmpty,
            !Self.isBlank(agentID),
            !Self.isBlank(ownerID),
            !Self.isBlank(approvalChannel),
            grantCount.map({ $0 > 0 }) ?? true
        else {
            return nil
        }
        return token
    }

    enum CodingKeys: String, CodingKey {
        case ok
        case agentID = "agent_id"
        case ownerID = "owner_id"
        case manifestJWT = "manifest_jwt"
        case expiresAt = "expires_at"
        case approvalChannel = "approval_channel"
        case grantCount = "grant_count"
        case budget
        case safeSummary = "safe_summary"
        case agentAssignments = "agent_assignments"
    }

    private static func isBlank(_ value: String) -> Bool {
        value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

public enum WorkbenchCapabilityManifestError: Error, Equatable {
    case malformedToken
    case invalidHeader
    case unsupportedAlgorithm
    case invalidSignature
    case invalidClaims
    case invalidIssuer
    case invalidAudience
    case expired
    case notYetValid
}

public enum WorkbenchCapabilityManifestStoreError: Error {
    case decodeFailed
    case unexpectedStatus(OSStatus)
}

public enum WorkbenchCapabilityManifestVerifier {
    public static let expectedIssuer = "evaos-broker"
    public static let expectedAudience = "evaos-runtime"

    public static func verifyHS256JWT(
        _ token: String,
        secret: Data,
        now: Date = Date(),
        issuer: String = expectedIssuer,
        audience: String = expectedAudience
    ) throws -> WorkbenchCapabilityManifestClaims {
        guard !secret.isEmpty else {
            throw WorkbenchCapabilityManifestError.invalidSignature
        }
        let parts = token.split(separator: ".", omittingEmptySubsequences: false).map(String.init)
        guard parts.count == 3, parts.allSatisfy({ !$0.isEmpty }) else {
            throw WorkbenchCapabilityManifestError.malformedToken
        }
        let headerData = try base64URLDecode(parts[0])
        let payloadData = try base64URLDecode(parts[1])
        let signature = try base64URLDecode(parts[2])
        let header: [String: Any]?
        do {
            header = try JSONSerialization.jsonObject(with: headerData) as? [String: Any]
        } catch {
            throw WorkbenchCapabilityManifestError.invalidHeader
        }
        guard let algorithm = header?["alg"] as? String else {
            throw WorkbenchCapabilityManifestError.invalidHeader
        }
        guard algorithm == "HS256" else {
            throw WorkbenchCapabilityManifestError.unsupportedAlgorithm
        }
        let signingInput = "\(parts[0]).\(parts[1])"
        let key = SymmetricKey(data: secret)
        guard HMAC<SHA256>.isValidAuthenticationCode(signature, authenticating: Data(signingInput.utf8), using: key) else {
            throw WorkbenchCapabilityManifestError.invalidSignature
        }
        let decoder = EvaDesktopISO8601.decoder()
        let claims: WorkbenchCapabilityManifestClaims
        do {
            claims = try decoder.decode(WorkbenchCapabilityManifestClaims.self, from: payloadData)
        } catch {
            throw WorkbenchCapabilityManifestError.invalidClaims
        }
        guard claims.issuer == issuer else {
            throw WorkbenchCapabilityManifestError.invalidIssuer
        }
        guard claims.audience == audience else {
            throw WorkbenchCapabilityManifestError.invalidAudience
        }
        guard !isBlank(claims.agentID), !isBlank(claims.ownerID), !isBlank(claims.approvalChannel), !claims.grants.isEmpty else {
            throw WorkbenchCapabilityManifestError.invalidClaims
        }
        guard claims.expiresAt > claims.issuedAt else {
            throw WorkbenchCapabilityManifestError.invalidClaims
        }
        guard now <= claims.expiresAt else {
            throw WorkbenchCapabilityManifestError.expired
        }
        guard now >= claims.issuedAt else {
            throw WorkbenchCapabilityManifestError.notYetValid
        }
        return claims
    }

    private static func base64URLDecode(_ value: String) throws -> Data {
        var normalized = value.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        let padding = normalized.count % 4
        if padding > 0 {
            normalized += String(repeating: "=", count: 4 - padding)
        }
        guard let data = Data(base64Encoded: normalized) else {
            throw WorkbenchCapabilityManifestError.malformedToken
        }
        return data
    }

    private static func isBlank(_ value: String) -> Bool {
        value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

public final class WorkbenchCapabilityManifestStore: Sendable {
    public static let defaultService = "com.electricsheephq.EvaDesktop.capabilities"

    private let service: String
    private let account: String

    public init(service: String = defaultService, account: String = "capability-manifest") {
        self.service = service
        self.account = account
    }

    public func storagePointer() -> String {
        "\(service):\(account)"
    }

    public func loadToken(allowUserInteraction: Bool = true) throws -> String? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        if !allowUserInteraction {
            query[kSecUseAuthenticationContext as String] = nonInteractiveAuthenticationContext()
        }

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound || status == errSecInteractionNotAllowed || status == errSecAuthFailed {
            return nil
        }
        guard status == errSecSuccess else {
            throw WorkbenchCapabilityManifestStoreError.unexpectedStatus(status)
        }
        guard let data = result as? Data, let token = String(data: data, encoding: .utf8), !token.isEmpty else {
            throw WorkbenchCapabilityManifestStoreError.decodeFailed
        }
        return token
    }

    public func loadVerifiedManifest(
        secret: Data,
        now: Date = Date(),
        allowUserInteraction: Bool = true
    ) throws -> WorkbenchCapabilityManifestClaims? {
        guard let token = try loadToken(allowUserInteraction: allowUserInteraction) else {
            return nil
        }
        return try WorkbenchCapabilityManifestVerifier.verifyHS256JWT(token, secret: secret, now: now)
    }

    public func saveToken(_ token: String) throws {
        let data = Data(token.utf8)
        var query = baseQuery()
        let attributes = [kSecValueData as String: data]
        let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)

        if updateStatus == errSecSuccess {
            return
        }
        if updateStatus != errSecItemNotFound {
            throw WorkbenchCapabilityManifestStoreError.unexpectedStatus(updateStatus)
        }

        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(query as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw WorkbenchCapabilityManifestStoreError.unexpectedStatus(addStatus)
        }
    }

    public func clear(allowUserInteraction: Bool = true) throws {
        var query = baseQuery()
        if !allowUserInteraction {
            query[kSecUseAuthenticationContext as String] = nonInteractiveAuthenticationContext()
        }
        let status = SecItemDelete(query as CFDictionary)
        if status == errSecItemNotFound || status == errSecSuccess || status == errSecInteractionNotAllowed || status == errSecAuthFailed {
            return
        }
        throw WorkbenchCapabilityManifestStoreError.unexpectedStatus(status)
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }

    private func nonInteractiveAuthenticationContext() -> LAContext {
        let context = LAContext()
        context.interactionNotAllowed = true
        return context
    }
}
