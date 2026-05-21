---
title: "Eva Desktop Packaging And Notarization"
status: proposed
created: 2026-05-20
---

# Eva Desktop Packaging And Notarization

## Distribution Default

Current friendly release: ship outside the Mac App Store as a Developer ID
signed, hardened-runtime app. Notarize the customer-hosted artifact whenever
notary credentials are available.

Public GA target: ship outside the Mac App Store as a Developer ID signed,
hardened-runtime, notarized app.

## MVP Entitlements

Keep entitlements narrow:

- Network client.
- Keychain access group for desktop session material.
- Associated Domains or custom URL scheme for auth callbacks/deep links.
- User-selected downloads/files only if runtime export requires it.

Do not request Accessibility, Screen Recording, Full Disk Access, Apple Events,
Input Monitoring, microphone, camera, arbitrary local shell, or iMessage
permissions in the Workbench MVP.

The Bridge Status panel may invoke fixed read-only `evaos-desktop-bridge` CLI
commands from a pinned install path after the user clicks refresh. It must not
expose a generic command runner or local-control action surface.

## Validation

Before beta:

```bash
cd apps/eva-desktop-mac
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --package-beta
codesign --verify --deep --strict dist/EvaDesktop.app
```

Before signed release:

```bash
cd apps/eva-desktop-mac
export EVA_DESKTOP_CODESIGN_IDENTITY="B605F28E822AB594CEC82D98BD11F5A02B42BB40"
export EVA_DESKTOP_CODESIGN_KEYCHAIN="/Volumes/LEXAR/Codex/apple-developer-certs/evaos-release-signing.keychain-db"
./script/build_and_run.sh --package-release
codesign --verify --deep --strict dist/EvaDesktop.app
codesign -dvvv --entitlements :- dist/EvaDesktop.app
```

Before public GA:

```bash
export EVA_DESKTOP_NOTARY_PROFILE="evaos-workbench-notary"
export EVA_DESKTOP_NOTARY_KEYCHAIN="$EVA_DESKTOP_CODESIGN_KEYCHAIN"
./script/build_and_run.sh --notarize-release
xcrun stapler validate dist/EvaDesktop.app
codesign --verify --deep --strict dist/EvaDesktop.app
spctl --assess --type execute dist/EvaDesktop.app
```

The final hosted zip must be rebuilt after stapling so users download the
stapled app, not only the pre-notarization submission archive.

## Keychain Trust Note

The app must be signed after final bundle assembly, not only as a raw SwiftPM
binary. `Info.plist`, resources, and the executable all need to belong to the
same final code identity. Local ad-hoc signing can launch the app but is not a
durable Keychain identity across rebuilds. Use a stable Apple Development
identity for internal canaries and Developer ID for release builds.

## Reference

OpenClaw's Mac app packaging/update surfaces are a useful reference for Sparkle,
appcast, and helper-tool patterns. Eva Desktop should borrow patterns, not take a
runtime dependency on the OpenClaw app.
