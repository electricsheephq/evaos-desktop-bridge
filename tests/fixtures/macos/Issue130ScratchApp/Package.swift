// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "Issue130ScratchApp",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "Issue130ScratchApp", targets: ["Issue130ScratchApp"])
    ],
    targets: [
        .executableTarget(name: "Issue130ScratchApp")
    ]
)
