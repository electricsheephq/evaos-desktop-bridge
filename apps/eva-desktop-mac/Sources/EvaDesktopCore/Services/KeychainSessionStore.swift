import Foundation
import LocalAuthentication
import Security

public enum KeychainSessionStoreError: Error {
    case encodeFailed
    case decodeFailed
    case unexpectedStatus(OSStatus)
}

public final class KeychainSessionStore: Sendable {
    private let service: String
    private let account: String
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(
        service: String = "com.electricsheephq.EvaDesktop.session",
        account: String = "desktop-session"
    ) {
        self.service = service
        self.account = account
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601
    }

    public func load(allowUserInteraction: Bool = true) throws -> DesktopSession? {
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
            throw KeychainSessionStoreError.unexpectedStatus(status)
        }
        guard
            let data = result as? Data,
            let session = try? decoder.decode(DesktopSession.self, from: data)
        else {
            throw KeychainSessionStoreError.decodeFailed
        }
        return session
    }

    public func save(_ session: DesktopSession) throws {
        guard let data = try? encoder.encode(session) else {
            throw KeychainSessionStoreError.encodeFailed
        }

        var query = baseQuery()
        let attributes = [kSecValueData as String: data]
        let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)

        if updateStatus == errSecSuccess {
            return
        }
        if updateStatus != errSecItemNotFound {
            throw KeychainSessionStoreError.unexpectedStatus(updateStatus)
        }

        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(query as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw KeychainSessionStoreError.unexpectedStatus(addStatus)
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
        throw KeychainSessionStoreError.unexpectedStatus(status)
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
