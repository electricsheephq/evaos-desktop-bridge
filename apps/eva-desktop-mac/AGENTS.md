# AGENTS.md - evaOS Workbench Mac App

## Scope

This app is the native macOS shell for evaOS gateways. It wraps existing runtime
pages in persistent `WKWebView` tabs and does not re-skin OpenClaw, Hermes,
Mission Control, Shared Browser, Terminal, or OpenDesign internals.

## UI Rules

- Visible app name: `evaOS Workbench`.
- Runtime section label: `Gateways`.
- Keep runtime rows compact: icon plus name. Avoid explanatory subtext for
  self-explanatory gateways.
- Do not show duplicate connection labels. If a runtime works, let it work.
- Do not show the app name twice in the sidebar/split-view chrome.
- Do not add an editable customer target field to the main runtime surface.
  Customer targeting belongs in settings or server-side account selection.
- Preserve persistent WebViews when switching gateway tabs. Do not rebuild all
  WebViews on simple tab selection.

## Auth And Keychain

- Keep `EvaDesktop` as the executable name and
  `com.electricsheephq.EvaDesktop` as the bundle id unless a migration plan is
  approved. The packaged `.app` bundle is `evaOS.app`.
- Desktop sessions are opaque broker tokens stored in Keychain. Never store VM
  gateway tokens, runtime cookies, backend service keys, auth headers, or raw
  session payloads in app model state.
- Startup Keychain reads must be non-interactive. A local signing mismatch
  should make the app appear signed out rather than opening a Keychain prompt.
- Sign the final `.app` bundle after `Info.plist` and resources are written.
  Stable Apple Development or Developer ID signing is required for a prompt-free
  release experience.

## Agent Control Boundary

- The Bridge panel is the customer setup surface for connector status,
  permissions, pairing, iPhone readiness, update checks, audit, and revoke.
- Customer-facing Mac and iPhone control lives in OpenClaw/Hermes tools, not in
  hidden Workbench buttons.
- Live actions must stay named, allowlisted, and audited. Full Access mode can
  run the new desktop/iPhone tools continuously after the customer starts a
  visible session; Ask Permission and legacy guarded actions still require
  dry-run/approval at high-impact boundaries. Never add arbitrary shell,
  hidden AppleScript passthrough, password capture, purchase/payment
  automation, or generic Codex app-server mutation.

## Focused Validation

Run from the repository root:

```bash
cd apps/eva-desktop-mac
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --verify
plutil -lint dist/evaOS.app/Contents/Info.plist
codesign --verify --deep --strict dist/evaOS.app
```

Use GitHub Actions for heavier archive/signing validation once it exists.

## Release Notes

- Keep the repository root `CHANGELOG.md` updated for every release-impacting
  Workbench/Desktop Bridge change.
- Add unreleased entries in the implementation PR and move them under the
  concrete version heading when cutting a release.
- Do not rely only on generated Sparkle appcast notes, GitHub release text, or
  dashboard copy; agents need the in-repo changelog as the durable handoff
  record.
