---
title: "evaOS Workbench Beta Release"
status: active
created: 2026-05-21
---

# evaOS Workbench Beta Release

## Boundary

This beta is for friendly customer release. The preferred customer artifact is
now the Developer ID signed and notarized release zip when notary credentials
are available. Use the unsigned/ad-hoc beta path only for internal canaries.

The beta includes the native Workbench shell, gateway tabs, desktop auth,
admin/customer-service customer switching, OpenDesign configuration, Bridge
status, customer-facing Mac and iPhone control through audited OpenClaw/Hermes
tools, and support-runbook coverage for the support VM Codex canary. It does not
expose arbitrary shell, hidden AppleScript, password capture, payment/purchase
automation, or generic Codex app-server mutation.

## Build

Run from the repo root:

```bash
cd apps/eva-desktop-mac
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --package-beta
```

The beta artifact is written to:

```text
apps/eva-desktop-mac/dist/evaOS-Workbench-Beta-<version>.zip
apps/eva-desktop-mac/dist/updates.json
```

`build_and_run.sh --package-beta` uses an Apple Development code-signing
identity when one is available locally. If no Apple Development identity exists,
it falls back to ad-hoc signing. The beta package command refuses Developer ID
identities so we do not accidentally imply notarized release readiness before
notarization has passed.

For the Developer ID signed customer artifact:

```bash
cd apps/eva-desktop-mac
export EVA_DESKTOP_CODESIGN_IDENTITY="B605F28E822AB594CEC82D98BD11F5A02B42BB40"
export EVA_DESKTOP_CODESIGN_KEYCHAIN="/Volumes/LEXAR/Codex/apple-developer-certs/evaos-release-signing.keychain-db"
security unlock-keychain -p "$(cat /Volumes/LEXAR/Codex/apple-developer-certs/.evaos-release-signing-keychain-pass)" \
  "$EVA_DESKTOP_CODESIGN_KEYCHAIN"
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --package-release
```

The release artifact is written to:

```text
apps/eva-desktop-mac/dist/evaOS-Workbench-<version>.zip
apps/eva-desktop-mac/dist/updates.json
apps/eva-desktop-mac/dist/appcast.xml
```

Once notary credentials have been stored with `notarytool`, use the notarized
release path instead:

```bash
export EVA_DESKTOP_NOTARY_PROFILE="evaos-workbench-notary"
export EVA_DESKTOP_NOTARY_KEYCHAIN="$EVA_DESKTOP_CODESIGN_KEYCHAIN"
./script/build_and_run.sh --notarize-release
```

That command staples the accepted notarization ticket, rebuilds the zip, and
regenerates the manifest from the final stapled artifact.

## Updates

Workbench checks the public update manifest on launch:

```text
https://www.electricsheephq.com/evaos-workbench/updates.json
```

The package command writes the matching manifest JSON next to the ZIP. For
v0.5.0 and later, upload the ZIP to the matching GitHub Release and copy only
`updates.json` plus `appcast.xml` into the Lovable dashboard repo under
`public/evaos-workbench/`. Merge that dashboard PR, then publish through
Lovable: project -> Publish -> Update. The customer-facing install page is:

```text
https://www.electricsheephq.com/evaos-workbench
```

Workbench `0.2.0+` uses Sparkle for in-app update install/relaunch through the
public `appcast.xml`. `updates.json` remains as a legacy compatibility manifest
and download-page smoke check. Older builds may only open the download URL and
require manual reinstall.

## Install

1. Unzip the beta artifact.
2. Drag `evaOS.app` to Applications or run it from the unzipped folder.
3. If macOS shows a first-launch confirmation, right-click the app and choose
   Open to confirm you trust evaOS Workbench from ElectricSheep.
4. Do not globally disable Gatekeeper.

## Keychain

Startup Keychain reads are non-interactive. If a signing mismatch prevents
access to an older desktop session item, Workbench should appear signed out
rather than opening a Keychain prompt repeatedly.

User-initiated sign-in and Sign Out may still touch Keychain. If a stale
beta item keeps prompting, use `Reset Local Session` on the Workbench sign-in
screen or clear only the Workbench desktop session item:

```bash
security delete-generic-password \
  -s com.electricsheephq.EvaDesktop.session \
  -a desktop-session
```

Fully prompt-free Keychain trust across updates requires stable Apple
Development signing for internal canaries or Developer ID signing for release.

## Beta Smoke

- Launch `evaOS Workbench`.
- Sign in through the ElectricSheep popup.
- Open OpenClaw, Hermes, Mission Control, OpenDesign, Shared Browser, and
  Terminal.
- Switch tabs repeatedly and confirm WebViews stay loaded.
- As admin/customer-service, switch between at least two customer targets and
  confirm gateway sessions do not bleed across targets.
- Sign Out and confirm the app returns to the sign-in state.
- In Settings -> Mac & iPhone, turn on Mac access from Workbench, approve the
  displayed permission target, and confirm status reads Ready without raw JSON.
- Refresh Settings -> Mac & iPhone status and confirm only clean status/capability/audit
  summaries appear in the Workbench UI.
- Confirm Workbench checks the update feed and can install/relaunch from a newer
  Sparkle appcast when testing from an older Sparkle-enabled build.

## Agent Control

Customer beta agents can use Mac and iPhone tools once the customer pairs their
Mac. Full Access mode lets the active agent operate continuously until the user
stops the session or hits the kill switch. Ask Permission mode keeps the same
tool surface but prompts at high-impact boundaries.

Allowed customer-facing controls include app focus, localhost/browser actions,
iPhone Mirroring focus/Home/App Switcher/Spotlight/open-app/tap named target,
scroll/swipe gestures, approved text entry, and one approved message send with
exact recipient/context and exact text.

Codex Desktop mutation remains a separate canary path. Use
`docs/support-vm-mac-iphone-codex-canary.md` for Codex remote-control fallback
testing.

## Public GA Blockers

- External friendly-customer canary evidence.
- Live canary evidence that the Workbench-managed helper keeps TCC ownership on
  evaOS Workbench and fails closed when grants are missing.
- Accepted notarization, stapled app, and passing `spctl --assess`.
- Sparkle update proven from an older installed build.
