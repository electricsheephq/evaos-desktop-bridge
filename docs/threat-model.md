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

The bridge gives Eva/OpenClaw safe situational awareness of visible desktop agent apps. The completed handoff observes Codex Desktop through macOS-visible state, exposes a read-only app-server seam, and provides narrow guarded visible focus/select actions; it does not provide hidden mutation control.

## Current Status

Active for MVP issue `100yenadmin/evaos-desktop-bridge#7`.

## Last Update

- Updated At: 2026-05-02T00:00:00Z
- Agent: codex
- Session: codex-desktop-passive-observer-mvp
- Revision Count: 1

## Change Log

- 2026-05-03T00:00:00Z - Added OpenClaw plugin wrapper boundary, latest/audit read APIs, and firewall control.
- 2026-05-02T00:00:00Z - Initial MVP threat model for read-only Codex Desktop observation.

## Assets

- Operator trust that the bridge will not silently take over Codex Desktop.
- Codex Desktop session state and visible UI.
- Local auth material, tokens, and account files.
- Local filesystem paths that may reveal user identity or projects.
- Audit trail proving what the bridge observed or attempted.

## Hard Boundaries

The MVP must not:

- Send prompts, messages, turns, approvals, or keyboard text.
- Call Codex internal mutation RPCs or mutation-capable app-server methods.
- Hijack stdio, file descriptors, PTYs, or process streams.
- Read Codex session databases wholesale.
- Expose tokens, auth files, or full home paths.
- Return long transcript-like text from the visible UI.

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
- Return the last redacted observation envelope.
- Return a capped redacted local audit-log tail.
- Append/list local Eva/OpenClaw queue events.
- Expose fixed read-only OpenClaw plugin tools that call the bridge CLI with non-shell argv.
- Append a redacted local JSONL audit record for every valid command invocation.

## Threats and Controls

| Threat | Control |
| --- | --- |
| Silent prompt sending | No command types, pastes, clicks send controls, or exposes prompt APIs. |
| Hidden Codex state mutation | App-server methods are denied unless on the read-only allowlist. |
| Session data leakage | No database reads; AX output is capped to roles/names only. |
| Secret leakage | Redaction replaces home paths, API-key-like strings, bearer tokens, and authorization headers. |
| Permission confusion | Commands return structured permission errors with setup guidance. |
| Unreviewable behavior | Every valid command writes an append-only local audit record. |
| Plugin shell escape | OpenClaw wrapper exposes fixed read-only tool mappings only and uses `execFile` with `shell: false`. |
| Generic desktop-control bypass | Plugin `before_tool_call` firewall blocks suspicious shell/computer calls containing desktop-control, Codex app-server, prompt-send, token, or session database patterns. |
| Stale visible action target | `select-thread` re-reads visible candidates and fails when the requested `visible_id` is absent or lacks bounds. |

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
- Use named visible macros instead of arbitrary coordinates or text injection.
- Preserve screenshot/AX caps and append-only audit records for every hands attempt.
