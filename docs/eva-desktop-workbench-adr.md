---
title: "ADR: Eva Desktop Workbench Lives In evaos-desktop-bridge"
status: active
created: 2026-05-20
---

# ADR: Eva Desktop Workbench Lives In evaos-desktop-bridge

## Decision

The first downloadable Eva Desktop Mac app lives in `evaos-desktop-bridge` as a
monorepo sibling to the Python bridge and OpenClaw plugin wrapper.

## Rationale

The product shell and the local bridge share one trust boundary: Electric Sheep
may show the user their runtime workspaces and may observe local bridge status,
but MVP must not silently control the user's Mac. Keeping the SwiftUI app,
bridge CLI, plugin wrapper, permissions docs, and threat model together makes
that boundary reviewable.

## MVP Boundary

Eva Desktop MVP is a native SwiftUI cockpit with persistent `WKWebView` tabs for:

- evaOS / OpenClaw
- evaOS / Hermes
- Mission Control
- OpenDesign
- Live Browser
- Terminal

The runtime apps remain upstream and unmodified. The desktop app resolves
customer/runtime launch URLs through a server-side session broker and stores only
desktop app session material in Keychain.

## Explicit Non-Goals

- No broad local Mac control.
- No iPhone Mirroring automation.
- No iMessage read/send integration.
- No prompt sending or approval clicking through Codex/OpenClaw desktop surfaces.
- No raw VM secrets, runtime backend tokens, auth headers, or session database
  reads in the desktop app.
- No generic shell execution, arbitrary local subprocess runner, Accessibility,
  Screen Recording, Full Disk Access, or Apple Events permissions in the first
  workbench MVP. The Bridge Status panel may run fixed read-only
  `evaos-desktop-bridge` CLI commands after an explicit user refresh.

## Future Split Criteria

Create a separate product repo only if the Mac app grows independent release
cadence, installer infrastructure, or platform scope that makes the bridge
policy layer hard to review in one repository.
