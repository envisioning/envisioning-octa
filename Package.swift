// swift-tools-version: 5.9
import PackageDescription

// The font is built by ./build.sh into dist/. This package vends that exact file
// — the target reaches into dist/ rather than keeping a second copy, so there is
// one EnvisioningOcta-VF.ttf in this repo and no copy anywhere else.
let package = Package(
    name: "EnvisioningOcta",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "EnvisioningOcta", targets: ["EnvisioningOcta"])
    ],
    targets: [
        .target(
            name: "EnvisioningOcta",
            path: ".",
            exclude: ["build", "src", "build.sh", "README.md", "AGENTS.md", "CLAUDE.md", "dist/static",
                      "dist/index.html", "dist/glyphs.json", "dist/EnvisioningOcta-VF.woff2"],
            sources: ["Sources"],
            resources: [.copy("dist/EnvisioningOcta-VF.ttf")]
        )
    ]
)
