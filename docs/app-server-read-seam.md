# Codex App-Server Read Seam

The app-server adapter is a read-only seam around an initialized `codex app-server --listen stdio://` JSON-RPC session. The bridge prefers `/Applications/Codex.app/Contents/Resources/codex` when present and falls back to `codex` on `PATH`.

## Allowed Methods

- `initialize`
- `remoteControl/status/read`
- `thread/list`
- `thread/loaded/list`
- `thread/read`
- `thread/turns/list`
- `getConversationSummary`

Returned data is redacted and capped before it leaves the bridge. The public CLI currently exposes status, native remote-control readiness, and capped thread summaries. Empty `thread/list` data is returned as successful idle evidence, not as an app-server outage.

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
evaos-desktop-bridge codex app-server status --json
evaos-desktop-bridge codex app-server remote-control-status --json
evaos-desktop-bridge codex app-server threads --json --max-items 50
```

These are `evaos-desktop-bridge` commands that wrap Codex's app-server protocol; `codex app-server threads` is not a native Codex CLI command.

If the local Codex app-server cannot be reached, commands return structured JSON errors instead of falling back to session database reads.

`remote-control-status` is a read-only probe. It checks the installed Codex CLI
and `/Applications/Codex.app/Contents/Resources/codex`, reports whether a
native `remote-control` command appears available, checks known control socket
locations, and attempts `remoteControl/status/read` only. It does not enable
remote control, approve remote clients, start turns, steer turns, or expose
generic app-server passthrough.

Codex Connections is ChatGPT-mediated product state. This bridge reports that state only; it does not enroll, enable, disable, or treat Connections as the primary OpenClaw control transport.
