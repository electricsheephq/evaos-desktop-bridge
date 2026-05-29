# Codex App-Server Seam

The app-server adapter defaults to a read-only seam around an initialized `codex app-server --listen stdio://` JSON-RPC session. The bridge prefers `/Applications/Codex.app/Contents/Resources/codex` when present and falls back to `codex` on `PATH`, so packaged Workbench and LaunchAgent environments do not depend on a user shell.

The bridge keeps live Codex mutation withheld from the public CLI and plugin surface until issue #136 proves that a visible Codex Desktop thread appears in `thread/loaded/list` through the same app-server transport. There is no generic RPC passthrough.

## Read-Only Methods

- `initialize` plus the required `initialized` notification handshake
- `remoteControl/status/read`
- `thread/list`
- `thread/loaded/list`
- `thread/read`
- `thread/turns/list`
- `getConversationSummary`

Returned data is redacted and capped before it leaves the bridge. The public CLI exposes status, connection readiness, native remote-control readiness, capped thread summaries, loaded thread ids, and short live-notification subscriptions. Empty `thread/list` data is returned as successful idle evidence, not as an app-server outage.

`remoteControl/status/read` is optional and experimental on current Codex CLI builds. If the installed CLI reports that method as unsupported, the bridge reports the native Connections state as unavailable/unsupported without treating the app-server itself as failed.

## Withheld Controller Methods

`turn/start`, `turn/steer`, and `turn/interrupt` remain blocked from the public bridge surface. They stay in the forbidden-methods inventory for future review, but CLI commands and OpenClaw tools are intentionally not registered while local acceptance shows `thread/loaded/list` returning an empty set through both stdio and proxy transports.

## Forbidden Methods

The bridge rejects mutation-capable methods before transport:

- `turn/start`, `turn/steer`, `turn/interrupt`
- `thread/inject_items`, `thread/start`, `thread/resume`, `thread/fork`, `thread/rollback`, `thread/compact/start`
- `thread/shellCommand`, `command/exec`, `command/exec/write`, `command/exec/terminate`
- `fs/writeFile`, `fs/remove`
- `config/value/write`, `config/batchWrite`
- `plugin/install`, `plugin/uninstall`
- `account/login/start`, `account/logout`
- `remoteControl/enable`, `remoteControl/disable`, `remoteControl/approve`, `remoteControl/deny`

## Commands

```bash
evaos-desktop-bridge codex connections status --json
evaos-desktop-bridge codex app-server status --json
evaos-desktop-bridge codex app-server remote-control-status --json
evaos-desktop-bridge codex app-server threads --json --max-items 50
evaos-desktop-bridge codex app-server loaded-threads --json --max-items 50
evaos-desktop-bridge codex app-server subscribe --json --thread-id THREAD --duration-ms 1000
```

These are `evaos-desktop-bridge` commands that wrap Codex's app-server protocol; `codex app-server threads` is not a native Codex CLI command.

If the local Codex app-server cannot be reached, commands return structured JSON errors instead of falling back to session database reads.

## Transport And Connections

Supported transports:

- `stdio` default: starts `codex app-server --listen stdio://` and performs
  `initialize` followed by `initialized`.
- `websocket`: set `EVAOS_CODEX_APP_SERVER_WS_URL=ws://127.0.0.1:PORT`; only
  loopback websocket URLs are accepted and client frames are masked.
- `proxy`: set `EVAOS_CODEX_APP_SERVER_TRANSPORT=proxy`; the bridge uses
  `codex app-server proxy` with an existing local control socket and performs
  the required WebSocket handshake and frame masking over the proxied Unix
  socket stream.

`remote-control-status` is a read-only probe. It checks the installed Codex CLI and `/Applications/Codex.app/Contents/Resources/codex`, reports whether a native `remote-control` command appears available, checks known control socket locations, and attempts `remoteControl/status/read` only. It does not enable remote control, approve remote clients, start turns, steer turns, or expose generic app-server passthrough.

Codex Connections is ChatGPT-mediated product state. This bridge reports that state only; it does not enroll, enable, disable, or treat Connections as the primary OpenClaw control transport.

The adapter does not install plugins, write config/files, read auth/session DBs, or expose arbitrary app-server methods.
