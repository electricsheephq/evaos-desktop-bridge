# Changelog

All notable repo release changes should be recorded here before a release branch or PR is handed off.

## Unreleased

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
