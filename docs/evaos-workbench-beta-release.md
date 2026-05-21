---
title: "evaOS Workbench Beta Release"
status: active
created: 2026-05-21
---

# evaOS Workbench Beta Release

## Boundary

This beta is for friendly customer release. It intentionally ships without
Developer ID signing or notarization until Apple approval lands.

The beta includes the native Workbench shell, gateway tabs, desktop auth,
admin/customer-service customer switching, OpenDesign configuration, Bridge
status, customer-facing Mac and iPhone control through audited OpenClaw/Hermes
tools, and support-runbook coverage for the support VM Codex canary. It does not
expose arbitrary shell, generic coordinates, hidden AppleScript, password
capture, payment/purchase automation, or generic Codex app-server mutation.

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
apps/eva-desktop-mac/dist/evaOS-Workbench-Beta-0.1.0.zip
apps/eva-desktop-mac/dist/updates.json
```

`build_and_run.sh --package-beta` uses an Apple Development code-signing
identity when one is available locally. If no Apple Development identity exists,
it falls back to ad-hoc signing. The beta package command refuses Developer ID
identities so we do not accidentally imply notarized release readiness before
Apple approval lands.

## Updates

Workbench checks the public update manifest on launch:

```text
https://www.electricsheephq.com/evaos-workbench/updates.json
```

The package command writes the matching manifest JSON next to the beta zip. For
the current ElectricSheep release path, copy the zip and manifest into the
Lovable dashboard repo under `public/evaos-workbench/`, merge that dashboard PR,
then publish through Lovable: project -> Publish -> Update. The customer-facing
install page is:

```text
https://www.electricsheephq.com/evaos-workbench
```

Because this beta is not Developer ID signed, update installation is
user-mediated: Workbench shows that an update is available and opens the
download URL. Background self-replacement moves to Sparkle after Developer ID
signing and notarization are available.

## Install

1. Unzip the beta artifact.
2. Drag `EvaDesktop.app` to Applications or run it from the unzipped folder.
3. If Gatekeeper blocks first launch, right-click the app and choose Open.
4. Do not globally disable Gatekeeper.

## Keychain

Startup Keychain reads are non-interactive. If a signing mismatch prevents
access to an older desktop session item, Workbench should appear signed out
rather than opening a Keychain prompt repeatedly.

User-initiated sign-in and Revoke Session may still touch Keychain. If a stale
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
- Open OpenClaw, Hermes, Mission Control, Live Browser, and Terminal.
- Switch tabs repeatedly and confirm WebViews stay loaded.
- As admin/customer-service, switch between at least two customer targets and
  confirm gateway sessions do not bleed across targets.
- Revoke Session and confirm the app returns to the sign-in state.
- In Agent Control Setup, start the connector from Workbench, approve the
  displayed permission target, and confirm status reads Ready without raw JSON.
- Refresh Desktop Bridge status and confirm only clean status/capability/audit
  summaries appear in the Workbench UI.
- Confirm Workbench checks the update manifest and shows Download Update when a
  newer manifest version is hosted.

## Agent Control

Customer beta agents can use named Mac and iPhone tools once the customer pairs
their Mac. Reads are available by default; live actions require a prior dry-run,
human approval, and a matching approval audit id.

Allowed customer-facing controls include app focus, localhost/browser actions,
iPhone Mirroring focus/Home/App Switcher/Spotlight/open-app/tap named target,
scroll/swipe gestures, approved text entry, and one approved message send with
exact recipient/context and exact text.

Codex Desktop mutation remains a separate canary path. Use
`docs/support-vm-mac-iphone-codex-canary.md` for Codex remote-control fallback
testing.

## Public GA Blockers

- Developer ID approval and stable release signing.
- Notarization.
- External friendly-customer canary evidence.
- Stable app-owned/helper-owned TCC identity for background connector startup.
