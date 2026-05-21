# AGENTS.md - evaOS Workbench Mac App

## Scope

This app is the native macOS shell for evaOS gateways. It wraps existing runtime
pages in persistent `WKWebView` tabs and does not re-skin OpenClaw, Hermes,
Mission Control, Live Browser, Terminal, or OpenDesign internals.

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
  approved.
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
- Live actions must stay named, allowlisted, audited, dry-run-first, and
  approval-gated. Never add arbitrary shell, generic coordinates, hidden
  AppleScript passthrough, password capture, purchase/payment automation, or
  generic Codex app-server mutation.

## Focused Validation

Run from the repository root:

```bash
cd apps/eva-desktop-mac
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --verify
plutil -lint dist/EvaDesktop.app/Contents/Info.plist
codesign --verify --deep --strict dist/EvaDesktop.app
```

Use GitHub Actions for heavier archive/signing validation once it exists.
