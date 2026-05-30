# Changelog

All notable repo release changes should be recorded here before a release branch or PR is handed off.

## Unreleased

## 0.6.12 - 2026-05-30

- Enable the issue #144 Approval Center durable decision UI only for approvals
  that have broker `allow_always_supported` evidence plus actionable,
  warning-free destination details. `Allow always` now stays hidden behind
  destination-constrained broker policy writes rather than creating a broad
  owner+agent+tool grant.

## 0.6.11 - 2026-05-30

- Add the issue #144 Approval Center notification slice: Workbench now keeps a
  model-owned broker polling loop active while signed in, sends one local
  notification when a new pending approval appears away from the Approval Center,
  suppresses duplicates and visible-row alerts, and keeps notification text to
  tool/risk/destination only instead of leaking payload body excerpts.
- Add an agent QA launch path that disables Workbench Keychain session/capability
  access for non-authenticated smoke tests and copies the app off Lexar before
  launch, avoiding blocking Keychain and removable-volume permission prompts.

## 0.6.10 - 2026-05-30

- Harden Codex visible GUI post-send waiting for #176: stable composer-visible
  idle now ends the wait instead of timing out forever, while notification
  overlays, focus steals, permission prompts, or operator re-entry during the
  read-only wait phase are returned as inconclusive/contaminated evidence to
  rerun in a quiet window rather than product failures.

## 0.6.9 - 2026-05-30

- Wire Approval Center to the live broker: Workbench now polls authenticated
  pending approvals, submits allow-once/deny decisions to Cortex while
  allow-always is intentionally withheld in the UI,
  keeps allow buttons disabled when actual destination evidence is missing, and
  preserves spoof-resistant preview derivation for broker-shaped payloads.
- Route Workbench capability and Approval Center broker calls through the
  Supabase `cortex-proxy` edge function instead of calling Cortex/Fly directly,
  so desktop-session JWTs are validated by Supabase and forwarded with the
  server-owned Cortex API key and resolved owner.
- Clarify live GUI-control canary protocol: Codex Desktop notification overlays,
  focus steals, permission prompts, or operator re-entry during visible-message
  tests are contaminated/inconclusive runs to rerun, not evidence that the
  shipped visible GUI lane is broken.

## 0.6.8 - 2026-05-30

- Add the issue #143 Workbench Capability Manifest fetch/cache slice: Workbench now fetches broker-issued manifests from the authenticated Cortex capability endpoint, caches only the signed JWT in Keychain, renders broker-provided safe summaries, clears stale manifest state on session/customer/client-boundary changes, and keeps runtime enforcement/OpenClaw/Hermes plugins deferred.

## 0.6.7 - 2026-05-30

- Add the issue #144 Approval Center contract slice with Workbench approval request models, spoof-resistant actual-destination previews, a feature-flagged read-only Approval Center view, and smoke coverage while broker decision endpoints remain deferred.
- Add the issue #143 Capability Manifest contract slice with Python and Workbench HS256 JWT verification, fail-closed tool-grant decisions, safe summaries, a Workbench Keychain manifest-token cache, and contract docs for OpenClaw/Hermes follow-up slices.
- Harden the issue #65 QA canary against transient iPhone Mirroring overlays by retrying visual assertions and allowing screenshot-derived Calculator state when the iPhone surface exposes image evidence but no phone-screen AX text.
- Add the issue #163 computer-use helper IPC auth contract skeleton with length-prefixed framing, capability-token and peer-uid authorization checks, ping-only command exposure, and tests that no live Mac/iPhone action is routed through the helper yet.
- Render Session Center from typed `WorkbenchSessionRecord` values for issue #161, preserving read-only mission-card evidence while gating Jump/Open to broker runtime routes and clearing stale records on reset.
- Harden Codex app-server stdio reads so buffered JSON-RPC responses are consumed even when the child process exits immediately after writing.
- Replace CodeQL default setup with advanced workflows for issue #159: Linux scans cover Actions/Python/JavaScript on relevant PRs, Swift CodeQL moves to main/tag/release/scheduled/manual runs, and PR runs cancel superseded pushes.
- Add the issue #95 v0.5 information-architecture and feature-flag design gate: typed Workbench flag descriptors now include owner, dashboard env, rollout criteria, rollback action, and public copy, and the v0.5 expansion doc maps signed-out, signed-in, admin-switch, gateway fallback, and degraded states.
- Add the shared Session Center and Agent Workspace contract for issue #99, including `evaos.session_center.v1`, typed resume routes, Workbench/dashboard ownership rules, and smoke coverage without adding a new control surface.
- Add Workbench MVP closeout evidence and smoke locks for desktop login/Keychain, runtime broker launch, WebView isolation, and packaging/notarization tracks so stale MVP issues #16, #17, #18, #21, and umbrella #12 can close while #22 remains deferred.
- Document and smoke-lock OpenDesign as a first-class brokered Workbench gateway for issues #20 and #66, including broker route, persistent WebView, runtime-status, auth, and Codex/BYOK separation contracts.
- Expand the evaOS Workbench Provider Hub catalog beyond OpenAI/Codex with planned Google Workspace, Slack, Notion, Linear, and GitHub cards, broker-profile merging, provider OAuth completion refresh handling, and updated card icons while keeping raw provider secrets out of Workbench.
- Add the issue #130 behavior/invariant harness with a native scratch-app fixture, local evidence reports, and probes for intended effects, focus preservation, cursor non-warping, occluded target capture, denied zero-effect behavior, and sensitive observation blocks.
- Fix the customer Mac sensitive-app denylist so `desktop_see` blocks before Peekaboo capture, policy metadata marks the block, and Full Access no longer advertises or performs live desktop control against sensitive frontmost apps.
- Add post-send wait-state reporting for guarded Codex visible GUI sends: live sends can use `thread_id=current`, return `submitted_waiting`, capped read-only observations, screenshot pointers, idle/done/error/timeout state, and OpenClaw `wait_ms`/`poll_interval_ms` controls without additional typing; title-hidden sidebar rows now fail closed for live sends.
- Add Codex Desktop visible GUI control V1: improved visible thread mapping, `codex thread-map`, guarded `codex send-visible-message`, and fixed OpenClaw plugin tools for the audited GUI fallback lane while app-server mutation stays withheld.
- Split the Codex Desktop app-server control sprint to status/readiness only after daemon/proxy acceptance still returned `thread/loaded/list` count 0; live `start-turn`/`steer-turn`/`interrupt-turn` CLI and OpenClaw tools remain withheld pending issue #136.
- Add Codex app-server diagnostics for app-bundled vs PATH CLI mismatch, daemon/control-socket readiness, proxy transport socket validation, and isolated stdio loaded-thread scope.
- Fix the Codex app-server read path to use an initialized JSON-RPC stdio session, parse real `thread/list` `result.data` payloads, clean up the stdio process group after each read, avoid Workbench pipe-EOF refresh hangs, report empty thread lists as idle evidence, and keep Connections/remote-control status read-only.
- Add read-only Session Center mission cards derived from broker runtime status, bridge queue/audit events, and Codex app-server readiness/thread summaries for issue #137.
- Add repo changelog hygiene so future evaOS Workbench/Desktop Bridge releases keep an in-repo record for agents and maintainers.

## 0.6.6 - 2026-05-28

- Fix OpenClaw reconnect failures caused by stale embedded dashboard state pointing at the root public WSS route.
- Reset the embedded OpenClaw runtime webview on forced reload/reconnect so fresh broker connection details replace cached UI state.
- Preserve the signed Sparkle update path, Mac and iPhone controls, private pairing, audited controls, and Workbench kill switch behavior.
