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

The bridge gives Eva/OpenClaw safe situational awareness of visible desktop agent apps. The MVP observes Codex Desktop through macOS-visible state and one narrow focus action; it does not provide hidden session control.

## Current Status

Active for MVP issue `100yenadmin/evaos-desktop-bridge#7`.

## Last Update

- Updated At: 2026-05-02T00:00:00Z
- Agent: codex
- Session: codex-desktop-passive-observer-mvp
- Revision Count: 1

## Change Log

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
- Call Codex internal mutation RPCs.
- Attach to Codex app-server sockets.
- Hijack stdio, file descriptors, PTYs, or process streams.
- Read Codex session databases wholesale.
- Expose tokens, auth files, or full home paths.
- Return long transcript-like text from the visible UI.

## Allowed MVP Behavior

- Report whether Codex Desktop appears installed or running.
- Report the visible Codex pid when detectable.
- Report macOS permission state where detectable.
- Focus an already-running Codex Desktop process through Accessibility.
- Capture a visible-state snapshot with capped window metadata.
- Save a screenshot artifact when Screen Recording permits it.
- Return a capped AX tree containing roles and names only.
- Append a redacted local JSONL audit record for every valid command invocation.

## Threats and Controls

| Threat | Control |
| --- | --- |
| Silent prompt sending | No command types, pastes, clicks send controls, or exposes prompt APIs. |
| Hidden Codex state mutation | No app-server attach or internal RPC calls in MVP. |
| Session data leakage | No database reads; AX output is capped to roles/names only. |
| Secret leakage | Redaction replaces home paths, API-key-like strings, bearer tokens, and authorization headers. |
| Permission confusion | Commands return structured permission errors with setup guidance. |
| Unreviewable behavior | Every valid command writes an append-only local audit record. |
| Scope creep into issue #3 | App-server discovery/proxy attach remains explicitly out of scope for this branch. |

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

Before adding issue `#3` or any app-server integration:

- Define a read-only RPC allowlist.
- Prove no mutation method can be called through generic passthrough.
- Add fixture tests for malformed responses and accidental mutation attempts.
- Require a separate threat-model revision and PR review.
