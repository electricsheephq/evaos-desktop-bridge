# Codex App-Server Seam

The app-server adapter defaults to a read-only seam around an initialized `codex app-server --listen stdio://` JSON-RPC session. The bridge prefers `/Applications/Codex.app/Contents/Resources/codex` when present and falls back to `codex` on `PATH`, so packaged Workbench and LaunchAgent environments do not depend on a user shell.

The bridge also exposes a separate guarded remote-control lane for already-loaded Codex Desktop threads. There is no generic RPC passthrough.

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

## Guarded Controller Methods

The bridge can call these methods only through named controller commands:

- `turn/start`
- `turn/steer`
- `turn/interrupt`

Live controller calls require all of:

- explicit `--thread-id`
- `--dry-run` first by default, or explicit `--live`
- `--confirm`
- `--source-audit-id audit-...`
- target thread present in `thread/loaded/list`

Dry-run returns the exact intended method/thread/message preview and does not open a JSON-RPC connection for mutation. Live mode fails closed when the thread is stale, not present in Codex Desktop's loaded-thread set, or the current app-server transport is unavailable.

## Forbidden Methods

The bridge rejects mutation-capable methods before transport unless they are one of the three named controller methods above and pass the guarded live gate:

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
evaos-desktop-bridge codex app-server start-turn --json --thread-id THREAD --message "continue" --dry-run
evaos-desktop-bridge codex app-server start-turn --json --thread-id THREAD --message "continue" --live --confirm --source-audit-id audit-...
evaos-desktop-bridge codex app-server steer-turn --json --thread-id THREAD --turn-id TURN --message "adjust" --dry-run
evaos-desktop-bridge codex app-server interrupt-turn --json --thread-id THREAD --turn-id TURN --dry-run
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
  `codex app-server proxy` and performs the required WebSocket handshake and
  frame masking over the proxied Unix socket stream.

`remote-control-status` is a read-only probe. It checks the installed Codex CLI and `/Applications/Codex.app/Contents/Resources/codex`, reports whether a native `remote-control` command appears available, checks known control socket locations, and attempts `remoteControl/status/read` only. It does not enable remote control, approve remote clients, start turns, steer turns, or expose generic app-server passthrough.

Codex Connections is ChatGPT-mediated product state. This bridge reports that state only; it does not enroll, enable, disable, or treat Connections as the primary OpenClaw control transport.

The adapter does not install plugins, write config/files, read auth/session DBs, or expose arbitrary app-server methods.
