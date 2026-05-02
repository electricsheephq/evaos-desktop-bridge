---
title: Research: Happy patterns for evaos-desktop-bridge
type: research
tags: [happy, evaos-desktop-bridge, architecture]
created: 2026-05-02
status: done
---

Happy steal list for `evaos-desktop-bridge`

**Copy**
- **Mobile approval/notification model:** Treat phone as an approval + status surface, not a full local runtime. Happy’s value prop is push for permission/errors plus instant device handoff (`README.md:55-72`). Good pattern: bridge emits structured approval events and completion/error notifications to mobile.
- **Machine/session abstraction:** Keep **machine-scoped** and **session-scoped** channels distinct. Happy’s protocol cleanly separates user/session/machine clients and gives machines their own state + presence (`docs/protocol.md:31-49,94-122`). That maps well to “desktop host” vs “running agent session.”
- **Daemon/relay model:** A background daemon on the desktop that can spawn/manage sessions while no terminal is open is worth copying (`packages/happy-cli/README.md:43-55`). This is probably the core pattern to steal for desktop bridge reliability.
- **Minimal encrypted relay mindset:** Server as sync/control relay, not brains. Happy’s backend stays small and mostly transports encrypted blobs + realtime updates (`packages/happy-server/README.md:7-23`). For Eva, keep relay/control-plane thin.
- **Codex app-server use:** Yes, copy. Happy explicitly hand-rolls against `codex app-server` because the SDK lacks interactive approvals and bidirectional control needed for mobile approval routing (`packages/happy-cli/src/codex/codexAppServerClient.ts:1-13`). This is directly relevant to desktop bridge.
- **Independent Electron app parts:** If we build a desktop app, steal the local-only shell pieces: PTY hosting, IPC bridge, file picker, auth helpers, and isolated worker/session bridge (`packages/codium/sources/boot/main/index.ts:1-120`, `packages/codium/sources/shared/agent-protocol.ts`). These are useful as app infrastructure, not as product architecture.

**Do NOT copy**
- **“Restart session into remote mode” UX literally:** Happy swaps control between keyboard and phone (`README.md:55-57`). For Eva, prefer continuous session identity with multiple attached control surfaces, not mode flips that feel fragile.
- **Permission state reconstructed from transcript-ish state:** Their docs admit permission handling has had awkward state reconstruction and protocol gaps. Copy the lesson, not the implementation; Eva should model approvals as first-class typed objects/events.
- **Monolithic Electron ambition:** `codium` includes a lot of full-app/editor surface area. For `evaos-desktop-bridge`, do not copy the whole independent desktop IDE idea unless product scope explicitly expands.
- **Happy’s broader social/feed/account surface:** feed, relationships, social routes, etc. are noise for Eva bridge.

**Split by requested areas**
- **Mobile approval/notification model:** copy the approval + push pattern; don’t copy weakly typed permission plumbing.
- **Machine/session abstraction:** strongly copy.
- **Daemon/relay model:** strongly copy.
- **Codex app-server use:** strongly copy.
- **CLI wrapper parts:** selectively copy daemon bootstrap, resume/spawn/session bookkeeping; avoid wrapper-specific UX assumptions.
- **Independent Electron app parts:** copy only local platform primitives (PTY, IPC, auth bridge, worker-hosted sessions), not the full product shell.

**Recommendation**
Build `evaos-desktop-bridge` around: **desktop daemon + typed machine/session protocol + thin relay + Codex app-server adapter + mobile approval notifications**. Skip the big Electron app unless we later want a first-class desktop UI.
