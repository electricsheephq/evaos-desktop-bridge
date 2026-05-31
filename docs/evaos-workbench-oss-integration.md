# evaOS Workbench OSS Integration Evidence

This sprint stops rebuilding provider and workspace surfaces blind. It records
what is safe to reuse from `cc-switch`, what must stay design-only from `cmux`,
and which Workbench surfaces remain dark until they have live behavior.

## Research Checkouts

- `cc-switch`: `/Volumes/LEXAR/repos/oss-research/cc-switch`
  - commit: `5315fa284b8fcb8c30d15b52e39dcbaffc09f704`
  - license: MIT
  - latest observed release: `v3.15.0`
- `cmux`: `/Volumes/LEXAR/repos/oss-research/cmux`
  - commit: `00b97ce6f3f6d4c62e761f4ec129ba8f3852d585`
  - license: GPL-3.0-or-later or commercial
  - latest observed release: `v0.64.10`

## cc-switch Reuse Map

`cc-switch` is MIT licensed, so evaOS may fork, vendor, port, or rewrite modules
with attribution. Reuse still needs a product/security filter because provider
auth code can easily leak secrets into app state.

Candidate modules to port or adapt:

- `src-tauri/src/openclaw_config.rs`
  - typed provider/default model structs
  - provider health scan patterns
  - config-section write patterns with backup/rollback requirements
- `src-tauri/src/hermes_config.rs`
  - read-only overlay and model normalization patterns
  - do not port memory-file mutators into Workbench
- `src-tauri/src/codex_config.rs`
  - TOML reader/writer helper patterns
  - keep raw Codex credentials outside Workbench state and UI payloads
- `src-tauri/src/services/model_fetch.rs`
  - provider model discovery and refresh behavior
- Codex/OpenClaw/Hermes session usage modules
  - useful for Session Center read-only adapters after provider grants are real

Rejected for direct reuse:

- `src-tauri/src/proxy/providers/codex_oauth_auth.rs`
  - reverse-engineered OAuth/device handling plus refresh-token storage is too
    risky for the Workbench product boundary

The `evaos-provider-engine` should be broker-first and metadata-only:

- input: `customer_id`, provider key, runtime type
- output: verified provider profile, active profile, opaque grant readiness,
  health state, last validation timestamp, and audit event ids
- never output: raw access tokens, refresh tokens, API keys, cookies, or auth
  headers

## cmux Design-Only Map

`cmux` is not a code-vendoring source for proprietary Workbench unless evaOS
chooses GPL-compatible distribution or obtains a commercial license. It is a
behavioral reference only.

Rebuild these concepts as evaOS-native requirements:

- notification rings: unread/attention indicators per Workbench surface group
- attention queue: append-only redacted events with `target_kind`, `target_id`,
  `severity`, `jump_route`, `source_audit_id`, and `status`
- active/recent sessions: active gateways from runtime registry plus recent
  sessions from safe broker metadata
- jump-back-in: deep-link to brokered runtime URLs or stable thread/session
  tokens, not replayed shell commands
- split patterns: constrained `gateway + shared browser`, `gateway + terminal`,
  or `gateway + support details` layouts rather than arbitrary pane trees
- persistence: selected customer, selected runtime, sidebar selection, filters,
  unread cache, and safe jump targets only

Do not copy cmux source, schemas, reducer structures, or UI wording into
Workbench.

## Current Product Boundary

Until the above engines exist:

- Providers stays feature-flagged off by default.
- Session Center stays feature-flagged off by default.
- Creative Studio stays feature-flagged off by default.
- Shared Browser remains the single visible browser workspace.
- Creative Studio can be enabled only as an honest hosted Comfy web surface;
  brokered VM-local ComfyUI remains future graduation scope.
