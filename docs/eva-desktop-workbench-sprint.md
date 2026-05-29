---
title: "Eva Desktop Workbench MVP Sprint"
status: complete
created: 2026-05-20
---

# Eva Desktop Workbench MVP Sprint

## Summary

The sprint creates a downloadable Mac cockpit for existing evaOS runtimes while
preserving the `evaos-desktop-bridge` observer/controller safety split.

Closeout: the MVP Workbench is shipped as the `apps/eva-desktop-mac` SwiftUI app
with brokered runtime tabs, desktop login/Keychain session handling, isolated
WebViews, read-only bridge status, packaging/release docs, and OpenDesign as a
brokered gateway. Supervised local Mac control remains outside this MVP and is
tracked in the deferred epic.

## Milestone

GitHub milestone: **Eva Desktop Workbench MVP**

Tracker issues:

- Epic: Eva Desktop Workbench MVP
- Architecture ADR: Bridge Monorepo And Runtime Cockpit
- SwiftUI App Scaffold
- Runtime Tab Model
- Desktop Login And Keychain Session
- Runtime Session Broker Client
- WebView Isolation And Cookie Safety
- Bridge Status And Audit Panel
- OpenDesign Tab Spike
- Packaging And Notarization Track
- Deferred Epic: Supervised Local Mac Control

## Implementation Order

1. Scaffold the SwiftUI app and run script.
2. Add typed runtime tabs and persistent WebViews.
3. Add desktop login and Keychain storage.
4. Wire runtime session broker calls.
5. Add WebView isolation checks for admin/customer switching.
6. Add bridge status and audit panel.
7. Decide OpenDesign tab behavior.
8. Add packaging/notarization checklist and CI/archive validation.

## Acceptance

- The app launches locally and shows all MVP runtime tabs.
- OpenClaw, Hermes, Mission Control, Shared Browser, Terminal, and OpenDesign are
  represented without rewriting upstream UIs.
- Runtime launch can use broker URLs when signed in and safe fallback routes
  during development.
- Bridge status is read-only.
- Local Mac/iPhone/iMessage control remains deferred.
