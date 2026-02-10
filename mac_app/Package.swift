// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "DashSpotlight",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "DashSpotlight", targets: ["DashSpotlight"]),
    ],
    targets: [
        .executableTarget(
            name: "DashSpotlight",
            path: "Sources"
        ),
    ]
)
