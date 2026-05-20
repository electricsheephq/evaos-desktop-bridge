// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "EvaDesktop",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "EvaDesktop", targets: ["EvaDesktop"]),
        .executable(name: "EvaDesktopCoreSmoke", targets: ["EvaDesktopCoreSmoke"]),
        .library(name: "EvaDesktopCore", targets: ["EvaDesktopCore"])
    ],
    targets: [
        .target(
            name: "EvaDesktopCore",
            path: "Sources/EvaDesktopCore"
        ),
        .executableTarget(
            name: "EvaDesktop",
            dependencies: ["EvaDesktopCore"],
            path: "Sources/EvaDesktop"
        ),
        .executableTarget(
            name: "EvaDesktopCoreSmoke",
            dependencies: ["EvaDesktopCore"],
            path: "SmokeTests/EvaDesktopCoreSmoke"
        )
    ]
)
