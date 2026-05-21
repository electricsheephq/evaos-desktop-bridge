---
title: "evaOS Workbench Agent-Control Safety"
status: active
created: 2026-05-22
---

# evaOS Workbench Agent-Control Safety

## Purpose

This is the safety contract for OpenClaw and Hermes agents that use Workbench to
observe or operate a paired customer Mac and iPhone.

## Default Rules

- Reads are allowed through named tools and must redact/cap output.
- Guarded actions are dry-run by default.
- Live guarded actions require human approval and a matching
  `approval_audit_id`.
- Agents must cite the dry-run audit id before asking for live approval.
- Every live action writes connector audit evidence.
- Revoke must block future VM commands.

## Allowed Read Tools

- Mac status
- Mac capabilities
- redacted snapshot
- capped Accessibility tree
- iPhone Mirroring status
- Screen Sharing status
- audit tail

## Allowed Guarded Actions

- focus a non-sensitive Mac app
- open localhost/loopback/`.local` URL
- browser reload/back/forward
- focus iPhone Mirroring
- iPhone Home, App Switcher, Spotlight
- open a non-sensitive iPhone app
- tap an exact visible iPhone Mirroring target label
- named scroll/swipe gestures
- type same-turn-approved text
- send one same-turn-approved message only when the recipient/context and exact
  text are approved

## Blocked Paths

Always block:

- generic shell access to the Mac;
- hidden AppleScript passthrough;
- arbitrary screen coordinates as the public API;
- raw Screen Sharing/VNC enablement;
- CDP or SSH exposure to the Mac;
- raw Codex app-server mutation;
- credential entry;
- payments and purchases;
- account/security settings;
- calls;
- unapproved external messages.

If any blocked path succeeds, stop rollout and file a security blocker.

## Agent Flow

1. Read status/capabilities.
2. Gather snapshot or AX tree only when needed.
3. Run dry-run for the planned action.
4. Ask the human for exact approval and include the dry-run audit id.
5. Execute live action with matching `approval_audit_id`.
6. Report result and audit evidence.

## OpenClaw And Hermes

OpenClaw is the primary plugin path. Hermes must use the same connector command
contract through a thin adapter or wrapper. Do not create a separate Mac-control
backend.

