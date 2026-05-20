---
title: "evaOS Workbench Beta Release"
status: active
created: 2026-05-21
---

# evaOS Workbench Beta Release

## Boundary

This beta is for internal and friendly canary users. It intentionally ships
without Developer ID signing, notarization, auto-update, or public GA claims.

The beta includes the native Workbench shell, gateway tabs, desktop auth,
admin/customer-service customer switching, OpenDesign configuration, Bridge
status, and support-runbook coverage for the support VM Mac/iPhone/Codex canary.
It does not expose broad local Mac control, iPhone messaging, Bumble actions,
arbitrary shell, or Codex mutation controls in customer builds.

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
```

`build_and_run.sh --package-beta` uses an Apple Development code-signing
identity when one is available locally. If no Apple Development identity exists,
it falls back to ad-hoc signing. The beta package command refuses Developer ID
identities so we do not accidentally imply notarized release readiness before
Apple approval lands.

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
- Refresh Desktop Bridge status and confirm only status/capability/audit output
  appears in the Workbench UI.

## Support VM Canary

The support-only Mac/iPhone/Codex canary remains separate from customer beta
distribution. Use `docs/support-vm-mac-iphone-codex-canary.md` for pairing,
dry-run, approval, and revocation steps.

Customer beta builds must not launch connectors with
`EVAOS_SUPPORT_CANARY_CONTROLS=1`.

## Public GA Blockers

- Developer ID approval and stable release signing.
- Notarization.
- External friendly-customer canary evidence.
- Update/distribution policy.
- Final support matrix for customer-owned Macs.
