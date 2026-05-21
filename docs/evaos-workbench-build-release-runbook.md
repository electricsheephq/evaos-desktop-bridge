---
title: "evaOS Workbench Build And Release Runbook"
status: active
created: 2026-05-20
---

# evaOS Workbench Build And Release Runbook

## Purpose

This runbook captures the current repeatable path for editing, validating, and
packaging the Mac Workbench app under `apps/eva-desktop-mac`.

For release execution, use the shorter gate checklist in
`docs/evaos-workbench-release-checklist.md`. For customer install recovery, use
`docs/evaos-workbench-customer-install-update.md`. For known broken builds, use
`docs/evaos-workbench-broken-release-recovery.md`.

## Current Customer Release Target

Workbench `0.2.3` / build `5` is the self-serve pairing release. It keeps the
`0.2.1` Sparkle/rpath repair, adds customer-safe pairing prompt copy, adds
pre-token OpenClaw/Hermes pairing helpers, and makes the app-generated
sign-in fallback code valid even when the browser never reaches the backup-code
board. When publishing it, keep the older `0.2.0`, `0.2.1`, and `0.2.2` ZIP
paths aliased to the fixed current ZIP so stale links cannot reinstall a broken
or stale build.

## Edit Map

- Product copy and stable labels:
  `apps/eva-desktop-mac/Sources/EvaDesktopCore/Models/AppBrand.swift`
- Runtime names, keys, and broker routing:
  `apps/eva-desktop-mac/Sources/EvaDesktopCore/Models/RuntimeDefinition.swift`
- Configurable OpenDesign route, connector status refresh, Keychain/WebView lifetime:
  `apps/eva-desktop-mac/Sources/EvaDesktop/Services/WorkbenchModel.swift`
- Sidebar and gateway launcher UI:
  `apps/eva-desktop-mac/Sources/EvaDesktop/Views/SidebarView.swift`
- Runtime WebView wrapper and toolbar:
  `apps/eva-desktop-mac/Sources/EvaDesktop/Views/RuntimeDetailView.swift`
- Settings -> Mac & iPhone panel:
  `apps/eva-desktop-mac/Sources/EvaDesktop/Views/BridgePanelView.swift`
- Resource bundling and local app verification:
  `apps/eva-desktop-mac/script/build_and_run.sh`

## Local Build

Run from the repository root:

```bash
cd apps/eva-desktop-mac
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --verify
./script/build_and_run.sh --package-beta
```

The raw `swift run EvaDesktop` command is useful for fast compiler feedback but
does not register the `evaos://` callback scheme. Use the app bundle for desktop
auth testing.

## Signing

`script/build_and_run.sh` signs the final app bundle after it writes resources
and `Info.plist`.

When no explicit identity is provided, the script uses the first local Apple
Development identity it can find, then falls back to ad-hoc signing. Ad-hoc
signing is enough to launch and verify the bundle shape, but it is not a stable
identity for Keychain trust across rebuilds.

For a prompt-free internal build, set one of:

```bash
export EVA_DESKTOP_CODESIGN_IDENTITY="Apple Development: ..."
```

Then rebuild:

```bash
./script/build_and_run.sh --verify
codesign -dvvv --entitlements :- dist/evaOS.app
codesign --verify --deep --strict dist/evaOS.app
spctl --assess --type execute dist/evaOS.app
```

If `security find-identity -p codesigning -v` reports zero identities, local
development can still proceed, but Keychain prompt-free behavior can only be
fully proven after a stable signing identity is installed.

## Beta Package

Use the beta path for internal/friendly builds that are not Developer ID signed
or notarized:

```bash
cd apps/eva-desktop-mac
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --package-beta
```

The beta artifact is:

```text
apps/eva-desktop-mac/dist/evaOS-Workbench-Beta-<version>.zip
apps/eva-desktop-mac/dist/updates.json
```

The beta packaging path accepts Apple Development or ad-hoc signing, refuses
Developer ID identities, and writes install notes that tell beta users to
right-click and Open if Gatekeeper blocks first launch. Do not ask users to
disable Gatekeeper globally.

## Developer ID Release Package

Use the release path when a Developer ID Application identity is available.
Prefer the identity SHA-1 plus an explicit release keychain so duplicate
identity names in the login keychain do not hang `codesign`:

```bash
cd apps/eva-desktop-mac
export EVA_DESKTOP_CODESIGN_IDENTITY="B605F28E822AB594CEC82D98BD11F5A02B42BB40"
export EVA_DESKTOP_CODESIGN_KEYCHAIN="/Volumes/LEXAR/Codex/apple-developer-certs/evaos-release-signing.keychain-db"
security unlock-keychain -p "$(cat /Volumes/LEXAR/Codex/apple-developer-certs/.evaos-release-signing-keychain-pass)" \
  "$EVA_DESKTOP_CODESIGN_KEYCHAIN"
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --package-release
codesign --verify --deep --strict dist/evaOS.app
codesign -dvvv --entitlements :- dist/evaOS.app
spctl --assess --type execute dist/evaOS.app
```

`--package-release` requires a Developer ID Application identity, signs with
hardened runtime, writes `evaOS-Workbench-<version>.zip`, writes
`updates.json`, and writes the Sparkle `appcast.xml`. If notarization is not
complete, `spctl` may still reject the app even though the Developer ID
signature is valid. Treat that as the remaining notarization gate, not a signing
failure.

Before publishing a Sparkle build, verify the framework and rpath:

```bash
test -d dist/evaOS.app/Contents/Frameworks/Sparkle.framework
otool -l dist/evaOS.app/Contents/MacOS/EvaDesktop | grep -A2 LC_RPATH
```

The executable must include `@executable_path/../Frameworks`. Workbench `0.2.0`
failed at launch because this rpath was missing.

When notary credentials are stored in the release keychain, use:

```bash
export EVA_DESKTOP_NOTARY_PROFILE="evaos-workbench-notary"
export EVA_DESKTOP_NOTARY_KEYCHAIN="$EVA_DESKTOP_CODESIGN_KEYCHAIN"
./script/build_and_run.sh --notarize-release
```

`--notarize-release` packages the signed app, submits the zip to Apple, staples
the accepted ticket to `dist/evaOS.app`, validates the staple, rebuilds the zip
so it contains the stapled app, regenerates `updates.json` and `appcast.xml`,
and runs `spctl --assess` when Apple has accepted the submission. If Apple keeps
the submission in progress, record the submission id and continue polling out of
band instead of blocking a terminal for hours.

Host the selected zip and update manifest at:

```text
https://www.electricsheephq.com/evaos-workbench/evaOS-Workbench-Beta-<version>.zip
https://www.electricsheephq.com/evaos-workbench/evaOS-Workbench-<version>.zip
https://www.electricsheephq.com/evaos-workbench/updates.json
https://www.electricsheephq.com/evaos-workbench/appcast.xml
```

For the Lovable dashboard deploy, copy those two files into the dashboard repo:

```bash
mkdir -p public/evaos-workbench
cp apps/eva-desktop-mac/dist/evaOS-Workbench-<version>.zip \
  /path/to/electric-sheep-website-dashboard-6158a244/public/evaos-workbench/
cp apps/eva-desktop-mac/dist/updates.json \
  /path/to/electric-sheep-website-dashboard-6158a244/public/evaos-workbench/updates.json
cp apps/eva-desktop-mac/dist/appcast.xml \
  /path/to/electric-sheep-website-dashboard-6158a244/public/evaos-workbench/appcast.xml
```

Then merge the dashboard install-page PR and publish through Lovable:
project -> Publish -> Update. The public install page is
`https://www.electricsheephq.com/evaos-workbench`.

Workbench `0.2.0+` uses Sparkle for in-app update install/relaunch. Older builds
may only discover the new download and require manual reinstall.

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
   codesign -dvvv dist/evaOS.app
   ```

2. Prefer installing and using a stable Apple Development or Developer ID
   signing identity.
3. If a stale local dev item keeps prompting, use `Reset Local Session` on the
   Workbench sign-in screen, or clear only the Workbench desktop session item
   and sign in again:

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
- OpenDesign launches through the brokered `opendesign` runtime and stays
  loaded while switching gateways.
- Shared Browser is used in customer-facing copy. Do not reintroduce Live
  Browser unless referring to old implementation history.
- Settings -> Mac & iPhone refreshes connector, Customer Mac, iPhone
  Mirroring, Codex Remote Control, Screen Sharing, capabilities, and audit tail
  without exposing a generic command runner or raw bridge JSON as the primary
  setup experience.
- Settings setup shows clean states for connector, permissions, pairing,
  iPhone readiness, local smoke, and revoke.
- Settings setup uses customer-facing labels and standard native cards;
  raw CLI/JSON output should never be the primary setup experience.
- Turn On Mac Access uses the Workbench-managed beta connector; LaunchAgent remains
  a background/restart test path until stable helper signing is in place.

## Release Readiness

Before announcing a build:

- Focused local validation passes.
- GitHub CI/archive validation passes if configured.
- Beta: app is Apple Development signed when available, otherwise ad-hoc signed,
  and `--package-beta` produced the zip artifact.
- Release: app is signed with a stable Developer ID Application identity and
  `--package-release` produced the release zip artifact.
- GA only: notarization path is proven, `stapler validate` passes, and
  `spctl --assess --type execute dist/evaOS.app` accepts the app.
- Desktop auth opens through `ASWebAuthenticationSession`, returns to
  `evaos://auth/callback`, and launches at least OpenClaw, Hermes, Mission
  Control, OpenDesign, Shared Browser, and Terminal for an admin canary.
- Connector status can be refreshed locally; paired-Mac control remains behind
  Headscale ACLs, connector tokens, and OpenClaw approval gates.
- OpenClaw agent proof has run through the actual plugin/tool path, not only a
  raw curl or local CLI call.
- Hermes proof has run through the same connector command contract.
- At least one cross-customer reachability check fails closed before customer
  beta release.
- Customer-facing iPhone controls remain named, approval-gated, audited, and
  free of generic coordinates or hidden mutation paths.
