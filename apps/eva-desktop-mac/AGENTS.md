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
- Autonomous agents must not open `dist/evaOS.app` directly from `/Volumes/LEXAR`;
  use `./script/build_and_run.sh --run-agent-qa` for visible UI checks or
  `--verify-agent-qa` for process-only smoke. Use a Developer ID-signed app on
  the internal disk for real signed-in acceptance.
- Passive signed-in refreshes such as account-policy, Connected Apps, Home, and
  approval-status reads should degrade their cards/status text when a broker
  endpoint is temporarily unauthorized or unavailable. Do not erase a fresh
  desktop session from passive evidence refresh alone; explicit runtime launches
  and user actions may still fail closed on true authorization failure.

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
./script/build_and_run.sh --verify-agent-qa
plutil -lint dist/evaOS.app/Contents/Info.plist
codesign --verify --deep --strict dist/evaOS.app
```

Use GitHub Actions for heavier archive/signing validation once it exists.

## Swift PR Flow

- Treat Swift validation as tiered. Do not turn every copy tweak, docs update,
  review reply, changelog edit, or PR metadata change into a fresh app rebuild.
- For SwiftUI layout/view edits, use previews, fixture views, screenshots from
  an already-built app, or the smallest focused smoke first. Run one
  `swift build`/smoke pass before the first PR push when Swift source changed,
  then let GitHub Actions carry the broader PR matrix.
- The native SwiftUI shell is not browser-hostable. For faster iteration, use a
  local browser/dev server only for Dashboard, onboarding, and embedded WebView
  pages; use the prompt-free Agent QA app or Swift previews/smokes for native
  sidebar/Home/Settings changes. Package and sign only for release acceptance.
- For core model, broker contract, app-command wiring, signing, entitlement, or
  packaging changes, run the focused smoke that proves the contract and one
  compile before push.
- For Python/plugin/dashboard-only work in this mixed repository, skip local
  Swift validation unless the changed contract crosses into Workbench.
- Reserve packaging, notarization, appcast generation, signed-in visual
  acceptance, and Swift CodeQL for sprint-release, main/tag/release,
  scheduled/nightly, security-sensitive Swift changes, or explicit
  release-validation asks.
- If Swift CodeQL is pending on a PR, treat it as a remote release/security
  gate, not a reason to keep rebuilding locally or stall unrelated safe work.
- Prefer CI workflow fixes over repeated local rebuilds when validation is
  noisy or expensive: path gating, `concurrency.cancel-in-progress`, targeted
  manual Swift builds, manual release scans, and release/main/nightly CodeQL.

## Release Notes

- Keep the repository root `CHANGELOG.md` updated for every release-impacting
  Workbench/Desktop Bridge change.
- Add unreleased entries in the implementation PR and move them under the
  concrete version heading when cutting a release.
- Do not rely only on generated Sparkle appcast notes, GitHub release text, or
  dashboard copy; agents need the in-repo changelog as the durable handoff
  record.
