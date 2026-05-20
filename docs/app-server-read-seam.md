# Codex App-Server Seam

The app-server adapter is read-only by default and uses `codex app-server` over stdio or a loopback websocket configured with `EVAOS_DESKTOP_BRIDGE_CODEX_APP_SERVER_WS`.

By default the bridge prefers the Codex Desktop bundled CLI at `/Applications/Codex.app/Contents/Resources/codex` when present, because Desktop may ship newer app-server protocol support than a Homebrew or npm `codex` on `PATH`. Override with `EVAOS_DESKTOP_BRIDGE_CODEX_BIN=/path/to/codex` when needed.

Set `EVAOS_DESKTOP_BRIDGE_CODEX_APP_SERVER_TRANSPORT=proxy` to attach through `codex app-server proxy` to a running managed daemon/control socket instead of launching a fresh stdio app-server. This is the transport to use for live Desktop remote-control smokes once the local Codex remote-control daemon is bootstrapped.

## Allowed Methods

- `initialize`
- `thread/list`
- `thread/loaded/list`
- `thread/read`
- `thread/turns/list`
- `getConversationSummary`

Returned data is redacted and capped before it leaves the bridge. The public CLI exposes status, connection readiness, capped thread summaries, and a short live notification window.

## Guarded Controller Methods

These are exposed only through named controller commands with dry-run, confirmation, source audit provenance, redaction, and audit logging:

- `turn/start`
- `turn/steer`
- `turn/interrupt`

There is no public generic app-server RPC passthrough.

## Forbidden Methods

The bridge rejects mutation-capable methods before transport:

- `thread/inject_items`, `thread/start`, `thread/resume`, `thread/fork`, `thread/rollback`, `thread/compact/start`
- `thread/shellCommand`, `command/exec`, `command/exec/write`, `command/exec/terminate`
- `fs/writeFile`, `fs/remove`
- `config/value/write`, `config/batchWrite`
- `plugin/install`, `plugin/uninstall`
- `account/login/start`, `account/logout`

## Commands

```bash
evaos-desktop-bridge codex app-server status --json
evaos-desktop-bridge codex app-server threads --json --max-items 50
evaos-desktop-bridge codex connections status --json
evaos-desktop-bridge codex app-server subscribe --json --thread-id THREAD --duration-ms 1000
evaos-desktop-bridge codex app-server start-turn --json --thread-id THREAD --message "..." --dry-run
evaos-desktop-bridge codex app-server steer-turn --json --thread-id THREAD --turn-id TURN --message "..." --dry-run
evaos-desktop-bridge codex app-server interrupt-turn --json --thread-id THREAD --turn-id TURN --dry-run
```

If the local Codex app-server cannot be reached, commands return structured JSON errors instead of falling back to session database reads.
