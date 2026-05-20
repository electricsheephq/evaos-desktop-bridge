---
title: "evaOS Workbench Build And Release Runbook"
status: active
created: 2026-05-20
---

# evaOS Workbench Build And Release Runbook

## Purpose

This runbook captures the current repeatable path for editing, validating, and
packaging the Mac Workbench app under `apps/eva-desktop-mac`.

## Edit Map

- Product copy and stable labels:
  `apps/eva-desktop-mac/Sources/EvaDesktopCore/Models/AppBrand.swift`
- Runtime names, keys, and broker routing:
  `apps/eva-desktop-mac/Sources/EvaDesktopCore/Models/RuntimeDefinition.swift`
- Sidebar and gateway launcher UI:
  `apps/eva-desktop-mac/Sources/EvaDesktop/Views/SidebarView.swift`
- Runtime WebView wrapper and toolbar:
  `apps/eva-desktop-mac/Sources/EvaDesktop/Views/RuntimeDetailView.swift`
- Auth, Keychain, WebView lifetime, and broker loading:
  `apps/eva-desktop-mac/Sources/EvaDesktop/Services/WorkbenchModel.swift`
- Resource bundling and local app verification:
  `apps/eva-desktop-mac/script/build_and_run.sh`

## Local Build

Run from the Lexar-backed app directory:

```bash
cd /Volumes/LEXAR/repos/evaos-desktop-bridge/apps/eva-desktop-mac
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --verify
```

The raw `swift run EvaDesktop` command is useful for fast compiler feedback but
does not register the `evaos://` callback scheme. Use the app bundle for desktop
auth testing.

## Signing

`script/build_and_run.sh` signs the final app bundle after it writes resources
and `Info.plist`.

For local development without a certificate, the script falls back to ad-hoc
signing. This is enough to launch and verify the bundle shape, but it is not a
stable identity for Keychain trust across rebuilds.

For a prompt-free release build, set one of:

```bash
export EVA_DESKTOP_CODESIGN_IDENTITY="Apple Development: ..."
export EVA_DESKTOP_CODESIGN_IDENTITY="Developer ID Application: Electric Sheep ..."
```

Then rebuild:

```bash
./script/build_and_run.sh --verify
codesign -dvvv --entitlements :- dist/EvaDesktop.app
codesign --verify --deep --strict dist/EvaDesktop.app
spctl --assess --type execute dist/EvaDesktop.app
```

If `security find-identity -p codesigning -v` reports zero identities, local
development can still proceed, but Keychain prompt-free behavior can only be
fully proven after a stable signing identity is installed.

## Keychain Prompt Triage

Symptom: macOS asks for Keychain access every time the app launches.

Likely cause: the local app bundle was rebuilt with a different ad-hoc code
identity than the one that created the existing desktop session item.

Current app behavior:

- Startup Keychain reads are non-interactive.
- If macOS refuses the read without user interaction, Workbench treats the user
  as signed out instead of opening a prompt.
- User-initiated sign-in and sign-out may still touch Keychain normally.

Repair steps:

1. Confirm the bundle is signed after assembly:

   ```bash
   codesign -dvvv dist/EvaDesktop.app
   ```

2. Prefer installing and using a stable Apple Development or Developer ID
   signing identity.
3. If a stale local dev item keeps prompting, clear only the Workbench desktop
   session item and sign in again:

   ```bash
   security delete-generic-password \
     -s com.electricsheephq.EvaDesktop.session \
     -a desktop-session
   ```

## UI Regression Checklist

- Sidebar shows ElectricSheep branding once.
- Runtime section is named `Gateways`.
- Runtime rows have no noisy descriptive subtext.
- Runtime toolbar does not duplicate `connected` or signed-in state.
- Customer target is not editable on the main runtime surface.
- Switching gateway tabs preserves existing `WKWebView` instances and does not
  reload unless the user reconnects/reloads.

## Release Readiness

Before announcing a build:

- Focused local validation passes.
- GitHub CI/archive validation passes if configured.
- App is signed with a stable identity.
- Hardened runtime and notarization path are proven.
- Desktop auth opens through `ASWebAuthenticationSession`, returns to
  `evaos://auth/callback`, and launches at least OpenClaw, Hermes, Mission
  Control, Live Browser, and Terminal for an admin canary.
