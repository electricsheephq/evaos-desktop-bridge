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
- Workbench has two customer modes: Full Access and Ask Permission.
- Full Access allows continuous live desktop/phone operation after the customer
  starts a session.
- Ask Permission gates risky clicks, taps, hotkeys, typing, sends, and other
  high-impact actions with human approval and a matching `approval_audit_id`.
- Agents should cite the dry-run audit id when Ask Permission or a legacy
  guarded action requires approval.
- Every live action writes connector audit evidence.
- Revoke must block future VM commands.

## Allowed Read Tools

- Mac status
- Mac capabilities
- control session status
- desktop see
- iPhone see
- redacted snapshot
- capped Accessibility tree
- iPhone Mirroring status
- Screen Sharing status
- audit tail

## Allowed Control Actions

- click a visible target or audited coordinate fallback
- type text
- scroll and drag
- use hotkeys, windows, menus, and local browser actions
- focus a Mac app
- open localhost/loopback/`.local` URL
- browser reload/back/forward
- focus iPhone Mirroring
- iPhone Home, App Switcher, Spotlight
- open a non-sensitive iPhone app
- tap an exact visible iPhone Mirroring target label
- iPhone tap, swipe, and text entry through visible iPhone Mirroring

## Blocked Paths

Always block:

- generic shell access to the Mac;
- hidden AppleScript passthrough;
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

1. Read status/capabilities and `desktop_control_status`.
2. Gather `desktop_see`, `iphone_see`, snapshot, or AX tree only when needed.
3. If Full Access is active, operate through the new `desktop_*` / `iphone_*`
   tools and report audit evidence.
4. If Ask Permission is active and the action is high impact, run a dry-run,
   ask the human for exact approval, then execute with matching
   `approval_audit_id`.
5. For legacy guarded actions, always use the dry-run -> approval -> live
   pattern.
6. Stop immediately if the kill switch is active; only the local Workbench user
   can start a fresh session after a kill.

## OpenClaw And Hermes

OpenClaw is the primary plugin path. Hermes must use the same connector command
contract through a thin adapter or wrapper. Do not create a separate Mac-control
backend.
