import Foundation

public enum WorkbenchUpdateError: Error, LocalizedError, Sendable {
    case invalidManifestURL
    case invalidResponse
    case httpStatus(Int)
    case untrustedURL

    public var errorDescription: String? {
        switch self {
        case .invalidManifestURL:
            "The Workbench update manifest URL is invalid."
        case .invalidResponse:
            "The Workbench update manifest returned an invalid response."
        case .httpStatus(let status):
            "The Workbench update manifest returned HTTP \(status)."
        case .untrustedURL:
            "The Workbench update URL is not trusted."
        }
    }
}

public struct WorkbenchReleaseManifest: Codable, Equatable, Sendable {
    public let version: String
    public let build: String?
    public let channel: String?
    public let minimumSystemVersion: String?
    public let downloadURL: URL
    public let sha256: String?
    public let releaseNotesURL: URL?
    public let publishedAt: Date?

    public init(
        version: String,
        build: String? = nil,
        channel: String? = nil,
        minimumSystemVersion: String? = nil,
        downloadURL: URL,
        sha256: String? = nil,
        releaseNotesURL: URL? = nil,
        publishedAt: Date? = nil
    ) {
        self.version = version
        self.build = build
        self.channel = channel
        self.minimumSystemVersion = minimumSystemVersion
        self.downloadURL = downloadURL
        self.sha256 = sha256
        self.releaseNotesURL = releaseNotesURL
        self.publishedAt = publishedAt
    }

    enum CodingKeys: String, CodingKey {
        case version
        case build
        case channel
        case minimumSystemVersion = "minimum_system_version"
        case downloadURL = "download_url"
        case sha256
        case releaseNotesURL = "release_notes_url"
        case publishedAt = "published_at"
    }

    public func isNewerThan(currentVersion: String, currentBuild: String) -> Bool {
        let versionComparison = Self.compareVersion(version, currentVersion)
        if versionComparison != 0 {
            return versionComparison > 0
        }
        return Self.intValue(build) > Self.intValue(currentBuild)
    }

    public var displayName: String {
        if let build, !build.isEmpty {
            return "\(version) (\(build))"
        }
        return version
    }

    private static func compareVersion(_ lhs: String, _ rhs: String) -> Int {
        let left = lhs.split(separator: ".").map { Int($0) ?? 0 }
        let right = rhs.split(separator: ".").map { Int($0) ?? 0 }
        let count = max(left.count, right.count)
        for index in 0..<count {
            let l = index < left.count ? left[index] : 0
            let r = index < right.count ? right[index] : 0
            if l != r {
                return l > r ? 1 : -1
            }
        }
        return 0
    }

    private static func intValue(_ value: String?) -> Int {
        Int(value ?? "") ?? 0
    }
}

public struct WorkbenchUpdateClient: Sendable {
    public let urlSession: URLSession

    public init(urlSession: URLSession = .shared) {
        self.urlSession = urlSession
    }

    public func fetchManifest(from manifestURL: URL) async throws -> WorkbenchReleaseManifest {
        guard Self.isTrustedUpdateURL(manifestURL) else {
            throw WorkbenchUpdateError.untrustedURL
        }
        let (data, response) = try await urlSession.data(from: manifestURL)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkbenchUpdateError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw WorkbenchUpdateError.httpStatus(httpResponse.statusCode)
        }
        let manifest: WorkbenchReleaseManifest
        do {
            manifest = try EvaDesktopISO8601.decoder().decode(WorkbenchReleaseManifest.self, from: data)
        } catch {
            throw WorkbenchUpdateError.invalidResponse
        }
        try Self.validate(manifest)
        return manifest
    }

    public static func validate(_ manifest: WorkbenchReleaseManifest) throws {
        guard isTrustedUpdateURL(manifest.downloadURL) else {
            throw WorkbenchUpdateError.untrustedURL
        }
        if let releaseNotesURL = manifest.releaseNotesURL, !isTrustedUpdateURL(releaseNotesURL, allowExactWorkbenchPath: true) {
            throw WorkbenchUpdateError.untrustedURL
        }
        if let sha256 = manifest.sha256, !isValidSHA256(sha256) {
            throw WorkbenchUpdateError.invalidResponse
        }
    }

    public static func isTrustedUpdateURL(_ url: URL, allowExactWorkbenchPath: Bool = false) -> Bool {
        guard let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased() else {
            return false
        }
        let isLocalhost = ["localhost", "127.0.0.1", "::1"].contains(host)
        if isLocalhost {
            return scheme == "http" || scheme == "https"
        }
        guard scheme == "https" else {
            return false
        }
        if host == "github.com" {
            return url.path.hasPrefix("/electricsheephq/evaos-desktop-bridge/releases/download/evaos-workbench-v")
                && url.path.hasSuffix(".zip")
        }
        guard host == "www.electricsheephq.com" || host == "electricsheephq.com" else {
            return false
        }
        if allowExactWorkbenchPath, url.path == "/evaos-workbench" {
            return true
        }
        return url.path.hasPrefix("/evaos-workbench/")
    }

    private static func isValidSHA256(_ value: String) -> Bool {
        let allowed = Set("0123456789abcdef")
        return value.count == 64 && value.allSatisfy { allowed.contains($0) }
    }
}
