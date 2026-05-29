---
title: "evaOS Desktop Bridge Threat Model"
doc_id: "doc-policy-desktop-bridge-threat-model"
doc_type: "policy"
status: "active"
canonical: true
created_at: "2026-05-02T00:00:00Z"
updated_at: "2026-05-02T00:00:00Z"
revision_count: 1
last_updated_by_agent: "codex"
last_updated_by_session: "codex-desktop-passive-observer-mvp"
tags:
  - evaos
  - desktop-bridge
  - threat-model
  - codex
---

# evaOS Desktop Bridge Threat Model

## Summary

The bridge gives Eva/OpenClaw customer-granted control of visible desktop agent apps. The completed handoff observes Codex Desktop through macOS-visible state, exposes a read-only app-server seam by default, and provides narrow guarded visible focus/select actions. The Codex app-server lane now has separately named, approval-gated controller commands for loaded Desktop threads only. Desktop Control Engine V2 adds customer-controlled Full Access and Ask Permission modes for audited Mac and iPhone Mirroring operation through the Workbench connector. Full Access unlocks the new `desktop_*` and `iphone_*` computer-use tools after the customer starts a visible session; legacy Codex/message fallback commands remain dry-run/approval gated.

## Current Status

Active for MVP issue `100yenadmin/evaos-desktop-bridge#7`.

## Last Update

- Updated At: 2026-05-02T00:00:00Z
- Agent: codex
- Session: codex-desktop-passive-observer-mvp
- Revision Count: 1

## Change Log

- 2026-05-03T00:00:00Z - Added OpenClaw plugin wrapper boundary, latest/audit read APIs, and firewall control.
- 2026-05-20T00:00:00Z - Added support-VM-only Codex remote-control readiness probe plus iPhone Mirroring gesture/message canary boundary.
- 2026-05-21T00:00:00Z - Promoted named iPhone gestures/messages from support canary to customer beta under the same dry-run/approval/audit contract.
- 2026-05-22T00:00:00Z - Added Desktop Control Engine V2 Full Access / Ask Permission modes, Peekaboo-first desktop tooling, and local-user kill-switch reset semantics.
- 2026-05-02T00:00:00Z - Initial MVP threat model for read-only Codex Desktop observation.

## Assets

- Operator trust that the bridge will not silently take over Codex Desktop.
- Codex Desktop session state and visible UI.
- Local auth material, tokens, and account files.
- Local filesystem paths that may reveal user identity or projects.
- Audit trail proving what the bridge observed or attempted.

## Hard Boundaries

The MVP must not:

- Send prompts, messages, turns, approvals, or keyboard text through generic tools.
- Automate iMessage/messages/dating-app sends outside the exact same-turn approval flow.
- Call Codex internal mutation RPCs or mutation-capable app-server methods through generic passthrough.
- Hijack stdio, file descriptors, PTYs, or process streams.
- Read Codex session databases wholesale.
- Expose tokens, auth files, or full home paths.
- Return long transcript-like text from the visible UI.
- Expose public VNC, SSH, CDP, or generic Screen Sharing access to the Mac.
- Enable Screen Sharing or Remote Management.
- Run arbitrary shell, AppleScript, or coordinate-control payloads.
- Control sensitive Mac/iPhone apps such as Messages, Mail, Wallet, Phone,
  Camera, Settings, Passwords, or banking/authenticator apps.

## Allowed MVP Behavior

- Report whether Codex Desktop appears installed or running.
- Report the visible Codex pid when detectable.
- Report macOS permission state where detectable.
- Focus an already-running Codex Desktop process through Accessibility.
- Select an already-visible Codex thread candidate by current `visible_id`.
- Capture a visible-state snapshot with capped window metadata.
- Save a screenshot artifact when Screen Recording permits it.
- Return a capped AX tree containing roles and names only.
- Return capped app-server thread summaries through a hard read-only method allowlist.
- Probe Codex native remote-control readiness without enabling it or calling mutation methods.
- Keep Codex app-server controller methods withheld from the public CLI and
  plugin surface until live loaded-thread acceptance passes.
- In support-VM canary mode only, select a visible Codex thread by title and submit exact `continue` as a guarded fallback when native remote-control is unavailable.
- Return the last redacted observation envelope.
- Return a capped redacted local audit-log tail.
- Append/list local Eva/OpenClaw queue events.
- Expose fixed read-only OpenClaw plugin tools that call the bridge CLI with non-shell argv.
- Report customer Mac, iPhone Mirroring, and Screen Sharing readiness.
- Capture customer Mac snapshot/AX evidence only for non-sensitive frontmost apps.
- Run named customer Mac/iPhone Mirroring dry-run actions, and live actions only
  when a plugin approval and `approval_audit_id` are present.
- Run named iPhone Mirroring gestures and one approved message-send flow after
  exact same-turn recipient/context and text approval.
- Serve the same fixed command surface through a token-gated connector endpoint
  for paired-VM/Headscale canaries.
- Append a redacted local JSONL audit record for every valid command invocation.

## Threats and Controls

| Threat | Control |
| --- | --- |
| Silent prompt sending | No command types, pastes, clicks send controls, or exposes prompt APIs. |
| Support Codex fallback drift | The only prompt-like fallback is fixed to exact `continue` and requires a matching dry-run audit id. |
| Hidden Codex state mutation | App-server methods are denied unless on the read-only allowlist. |
| Codex controller abuse | `turn/start`, `turn/steer`, and `turn/interrupt` are not registered in the CLI, connector, or OpenClaw plugin while #136 remains blocked; no generic RPC tool exists. |
| Session data leakage | No database reads; AX output is capped to roles/names only. |
| Secret leakage | Redaction replaces home paths, API-key-like strings, bearer tokens, and authorization headers. |
| Permission confusion | Commands return structured permission errors with setup guidance. |
| Unreviewable behavior | Every valid command writes an append-only local audit record. |
| Plugin shell escape | OpenClaw wrapper exposes fixed command mappings only and uses `execFile` with `shell: false`. |
| Generic desktop-control bypass | Plugin `before_tool_call` firewall blocks suspicious shell/computer calls containing desktop-control, Codex app-server, prompt-send, token, or session database patterns. |
| Stale visible action target | `select-thread` re-reads visible candidates and fails when the requested `visible_id` is absent or lacks bounds. |
| Cross-customer Mac exposure | Connector is bound locally by default; paired-VM mode requires Headscale ACLs and a connector token. |
| Accidental live control | Live desktop/phone tools require an active Workbench control session; kill switch blocks future live commands. |
| Accidental broad iPhone control | iPhone actions operate through the visible iPhone Mirroring window and are governed by Full Access / Ask Permission mode. |
| Sensitive app mutation | Sensitive Mac/iPhone app names and dangerous visible labels are blocked before action execution. |
| Unapproved real-world messages | `send-approved-message` requires exact same-turn recipient/context and text, then presses only an exact visible Send label with audit evidence. |

## Audit Log

Audit records are local JSONL entries containing:

- `schema_version`
- `audit_id`
- `timestamp`
- `command`
- `target`
- redacted `args`
- `ok`
- redacted `warnings`
- redacted `errors`

The audit log is not a telemetry upload. It is a local provenance trail for operator review and future Eva/OpenClaw policy integration.

## Data Minimization

- Store screenshots only when the operator runs snapshot and macOS permits capture.
- Return redacted paths in command output.
- Keep Accessibility tree output capped by `--max-nodes`.
- Keep visible text capped by `--max-chars`.
- Avoid session, account, auth, token, and database files entirely.

## Future Review Gates

Before broadening app-server integration:

- Define a read-only RPC allowlist.
- Prove no mutation method can be called through generic passthrough.
- Add fixture tests for malformed responses and accidental mutation attempts.
- Require a separate threat-model revision and PR review.

Before adding GUI hands beyond focus:

- Split hands tools from passive observer tools.
- Require explicit operator approval for click/type/send-capable macros.
- Prefer named visible targets, but allow audited coordinate fallback inside the customer-granted control session.
- Preserve screenshot/AX caps and append-only audit records for every hands attempt.

Before broad paired-Mac rollout:

- Add support/control-plane device records and grant revocation.
- Prove Headscale ACLs allow only the paired VM to reach the paired Mac connector.
- Rotate connector tokens during offboarding and provisioning.
- Run one friendly external Mac canary before broad customer GA.
