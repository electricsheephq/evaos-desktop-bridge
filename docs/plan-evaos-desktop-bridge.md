---
title: "evaos-desktop-bridge plan"
type: plan
tags: [evaos, desktop, codex, claude, bridge]
created: 2026-05-02
status: proposed
canonical: true
---

# evaos-desktop-bridge

## Product framing
`evaos-desktop-bridge` is the safe layer between Eva/OpenClaw’s brain and a human-visible desktop agent surface. The goal is not “remote control of desktop AI.” The goal is **shared situational awareness with constrained assistance**: Eva can see what the human-facing desktop agent is showing, decide what matters, and route suggestions or tightly-scoped actions without silently taking over.

MVP target: **Codex Desktop only**. Claude Desktop comes later through the same adapter contract. Start with **at most 1–2 visible desktop agents total** so review, permissions, and operator trust stay manageable.

## Architecture
Three-part system:
1. **Eyes adapter (read-only first):** per-desktop-app adapter that exposes stable state JSON: app installed/running, windows, visible threads/sessions, workspace metadata, permissions, warnings. For Codex Desktop, prefer the app-server seam (`app-server proxy --sock ...`) when safely attachable; otherwise fall back to passive local-state/process inspection and, later, AX tree reads.
2. **Hands harness:** a CLI-Anything-style harness for explicit guarded actions only. Initial actions should be narrow: focus/select visible thread, bring window frontmost, maybe click a known control. No generic prompt typing, no send/approve, no hidden background mutation in MVP; support-only canary fallbacks must stay exact and audited.
3. **Brain + announcement queue:** Eva/OpenClaw consumes normalized snapshots, reasons over relevance/risk, and emits suggestions, alerts, or approval requests into an announcement queue. Desktop bridge should support “observe → summarize → propose” before “act.”

## Security boundaries
- **Default read-only.** Mutation is opt-in per command and off by default.
- **No generic RPC passthrough.** Only allowlisted subcommands.
- **No secret scraping.** Adapters must redact local state and thread text unless explicitly approved for debug.
- **Single attach, serialized requests.** Experimental desktop control seams should run one live attach per machine.
- **Human-visible provenance.** Every suggested/attempted action should log source snapshot, command, actor, and result.
- **Surface isolation.** Codex Desktop and later Claude Desktop each get separate adapters; no shared implicit session mutation.

## Repo structure
- `apps/cli/` — `desktop-bridge` CLI entrypoints (`status`, `snapshot`, `list-visible`, `focus-thread`, `permissions`)
- `packages/core/` — shared types, policy gates, redaction, audit logging, queue contracts
- `packages/adapters/codex-desktop/` — passive state readers, socket discovery, read-only RPC allowlist
- `packages/adapters/claude-desktop/` — stub contract + future implementation
- `packages/hands/` — CLI-Anything harness wrappers / guarded visible actions
- `packages/queue/` — announcement event schema and sinks
- `tests/` — fixture snapshots, policy tests, integration smoke tests
- `docs/` — setup, TCC permissions, threat model

## MVP milestones
1. **M0 framing + contracts:** repo scaffold, normalized snapshot schema, policy layer, audit log format.
2. **M1 Codex passive observer:** installed/running/version, permissions, passive local state, candidate socket discovery, `status` and `snapshot`.
3. **M2 Codex live read seam:** safe `initialize` + read-only list/read methods through app-server proxy if socket discovery works.
4. **M3 Guarded visible actions:** focus/select thread via AX/CLI-Anything harness, strict allowlist, full audit trail.
5. **M4 Eva integration:** announcement queue, “suggest don’t act” workflow, operator-facing summaries.
6. **M5 Claude Desktop adapter spike:** validate same contract, no broadening of action scope.

## Testing strategy
- Unit tests for snapshot normalization, redaction, policy gates, and command allowlists.
- Fixture-driven adapter tests using recorded Codex metadata/log samples.
- Integration smoke tests against isolated/mock app-server before any live attach.
- Manual TCC checklist on real macOS for Accessibility/Automation/Screen Recording behavior.
- Adversarial tests: malformed socket responses, multiple candidate sockets, denied permissions, accidental mutation attempts.

## Build workflow
Codex can build this repo directly: scaffold CLI/types/adapters/tests, then iterate milestone-by-milestone. Eva’s role is architecture review, safety review, and live operator loop design. Keep Codex as the implementation surface and Eva as reviewer/orchestrator until the bridge proves trustworthy.

## Proposed GitHub issues
- Bootstrap `evaos-desktop-bridge` repo with shared snapshot schema and policy core
- Add Codex Desktop passive observer (`status`/`snapshot`)
- Implement Codex app-server socket discovery and read-only proxy attach
- Add guarded visible thread focus action via AX / CLI-Anything harness
- Create announcement queue contract for Eva desktop observations
- Add audit log + provenance trail for every bridge action
- Write TCC permissions setup and threat-model docs
- Spike Claude Desktop adapter against shared bridge contract
