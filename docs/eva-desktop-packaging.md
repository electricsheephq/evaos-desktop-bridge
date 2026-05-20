---
title: "Eva Desktop Packaging And Notarization"
status: proposed
created: 2026-05-20
---

# Eva Desktop Packaging And Notarization

## Distribution Default

Ship Eva Desktop outside the Mac App Store first as a Developer ID signed,
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

Before release:

```bash
codesign --verify --deep --strict dist/EvaDesktop.app
spctl --assess --type execute dist/EvaDesktop.app
```

Notarization should be added once the app has a real Developer ID signing
identity and release artifact path.

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
