# Changelog

All notable repo release changes should be recorded here before a release branch or PR is handed off.

## Unreleased

## 0.6.21 - 2026-05-31

- Add the issue #97/#100 Shared Browser and Session Center sprint slice:
  brokered runtime pages now expose a read-only status strip with safe Shared
  Browser room/current URL/last-activity metadata, per-runtime status refresh
  updates the matching Session Center record, and local Close detaches only the
  Workbench view without pretending to stop the broker runtime.
- Harden Session Center runtime cards for issue #100 by decoding broker hints
  for waiting-on-user, active control sessions, update-available, unavailable,
  and runtime-error states instead of flattening them into generic idle text.

## 0.6.20 - 2026-05-31

- Extend the native operator warning sound from a short single beep into an
  explicit multi-second alert loop so live GUI canaries are harder to miss
  before Accessibility or mouse control begins.
- Extend the Workbench pre-canary stale `EvaDesktop.app` scan to legacy Lexar
  worktree roots after an old `0.1.0` `EvaDesktop.app` was found running beside
  the canonical `/Applications/evaOS.app`.
- Add a `--control-surface bridge-peekaboo` pre-canary mode so Workbench GUI
  canaries driven by audited bridge/Peekaboo commands are not blocked by stale
  or broken Codex `mcp__computer_use` helper processes, while Codex-MCP canaries
  still fail closed on helper herds.
- Fix the Workbench pre-canary helper detection so shell cleanup commands that
  merely mention `SkyComputerUseClient mcp` are not counted as live Computer Use
  helpers, and document the safer recovery path when the current Codex tool
  transport is stale.
- Fix Workbench focus safety so `EvaDesktop`/`evaOS Workbench` aliases resolve
  only to canonical `/Applications/evaOS.app`, and extend the pre-canary guard
  to fail when old `EvaDesktop.app` artifact bundles could contaminate macOS
  app-name lookup.

## 0.6.19 - 2026-05-31

- Add issue #207 agent takeover warning: starting a customer Mac control
  session now creates a 10-second countdown before live desktop/iPhone actions
  can run, Workbench surfaces `Taking over screen...` status, and local/remote
  live commands fail closed with `control_takeover_warning_active` until the
  warning window expires.
- Add an `evaos-workbench-pre-canary` guard for signed-in Workbench acceptance:
  it verifies the canonical `/Applications/evaOS.app` version/build, detects
  duplicate same-bundle-id app registrations, flags translocated stale
  `EvaDesktop.app` processes, and catches stale Computer Use helper herds before
  OAuth or GUI canary evidence is trusted.
- Fix Provider/Auth Hub summary priority so a real broker/provider error is
  reported as `Blocked` even when other catalog providers are merely planned or
  unavailable.
- Add the Creative Studio issue #101 design gate ADR for the hosted/configured
  ComfyUI-first path, API grant lane, unavailable-state behavior, and deferred
  VM-local graduation criteria.
- Add Workbench development runbook guidance for batching related issues into
  sprint releases, using validation tiers, isolating GUI canary windows from
  Slack/notification/TCC noise, and reserving Swift CodeQL for release,
  security, main, nightly, or manual gates instead of every tiny PR push.
- Retire the Tier-2 global HID event fallback for issue #124. Mouse
  click/scroll/drag helper actuation now requires an audited target process and
  dispatches through `CGEventPostToPid`, with browser web content treated as
  inert/escalated rather than falsely successful.

## 0.6.18 - 2026-05-31

- Add issue #123 Tier-1 AX actuation for fresh desktop snapshot elements:
  helper IPC now supports fixed semantic `ax_action` verbs (`press`,
  editable-field `set_value`, selected-text replacement, and menu traversal)
  after bridge-side policy, target-sensitive-app/process checks,
  dry-run/approval gates, and audit dispatch records. The OpenClaw wrapper
  exposes only the fixed `desktop_set_value` tool, materializes values into
  0600 temp files instead of subprocess argv, and continues to block raw AX
  primitive bypasses.

## 0.6.17 - 2026-05-31

- Complete issue #129 IPC-seam safety for the current helper route: every
  helper `mouse_action` now writes an append-only `helper.mouse_action`
  authorized-dispatch audit record before IPC dispatch, sends that durable
  audit id through the helper envelope, and writes a separate completion record
  after the helper returns or fails. This keeps the helper as authenticated
  dumb hands while preserving bridge-side policy, approval, sensitive-app, and
  kill-switch gates above the seam.

## 0.6.16 - 2026-05-31

- Implement issue #122 signed-helper/TCC identity closure: Workbench now starts
  the resident computer-use helper before the customer Mac connector, passes a
  Workbench bundle/app identity marker into the helper, verifies the helper's
  parent process is inside that app bundle, enables enforced Accessibility/
  Screen Recording preflight, and gives the connector only that managed helper
  socket/token. Helper `ping` now reports identity/grant provenance, and helper
  `mouse_action` fails closed with structured `helper_identity_unverified` or
  `permission_missing` errors instead of silently falling back to a terminal/
  Python permission owner.

## 0.6.15 - 2026-05-31

- Start the issue #121 persistent computer-use helper foundation: add a local
  authenticated Unix-socket helper server/client, expose `helper ping`, use a
  short default helper socket path for macOS `AF_UNIX` limits, rotate the
  private token file on helper start, atomically validate/read helper tokens,
  require bridge audit provenance for helper `mouse_action`, timeout stalled
  helper clients, route opted-in Quartz mouse fallback actions through the
  helper without per-action Python subprocess fallback, and keep the helper
  command surface limited to `ping` plus structured click/scroll/drag
  `mouse_action`.

## 0.6.14 - 2026-05-31

- Add issue #147 per-agent usage budget cards: Workbench decodes broker-proxied
  LLM `by_agent` usage, compares the active agent against Capability Manifest
  token/dollar caps, renders progress/paused states in Providers, and plans a
  local budget-paused notification. Approval Center now renders broker
  budget-pause rows with the expected "Increase cap" and "Stop agent" actions
  without adding a generic mutation endpoint.

## 0.6.13 - 2026-05-30

- Add issue #144 Approval Center timeout awareness: Workbench now decodes
  broker `expires_at` deadlines, renders deadline text on approval rows, and
  sends one separate expiring notification for already-surfaced pending rows
  without leaking payload excerpts.
- Harden agent QA launch discipline: `build_and_run.sh run` now routes Lexar
  or removable-volume launches through prompt-free agent QA by default, and
  `--run-agent-qa`
  launches a copied internal-disk bundle with Workbench Keychain access disabled
  so autonomous UI checks do not get stuck behind Keychain or volume prompts.

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
