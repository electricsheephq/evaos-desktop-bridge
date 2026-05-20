# evaOS Desktop Bridge

Safe bridge between Eva/OpenClaw and visible human desktop agent surfaces.

The first target is **Codex Desktop on macOS**. The completed handoff slice observes visible state, reports permission readiness, exposes a read-only app-server seam, provides one guarded visible thread-selection action, adds a separately guarded app-server remote-control lane, writes local audit/queue trails, and ships an OpenClaw plugin wrapper. It does not type text, click send/approval controls, expose generic mutation RPCs, hijack stdio, or read Codex session databases.

## Architecture

- **Eyes:** read-only state adapters that expose safe structured desktop/session metadata.
- **Hands:** CLI-Anything-style GUI harnesses that operate visible desktop apps through macOS Accessibility/screenshot/AppleScript primitives.
- **Brain:** Eva/OpenClaw policy, approvals, audit logging, and announcement queue.

Current implementation covers the Codex Desktop eyes adapter, guarded visible focus/select actions, a read-only app-server adapter, guarded named remote-control actions, local announcement queue, and OpenClaw plugin wrapper. External relay/mobile push remains a future sink on top of the local queue contract.

## Install

Requirements:

- macOS for live desktop inspection.
- Python 3.10 or newer.
- Codex Desktop installed manually by the operator.

```bash
git clone https://github.com/100yenadmin/evaos-desktop-bridge
cd evaos-desktop-bridge
python3 -m pip install -e .
evaos-desktop-bridge --help
```

For test-only use without installing the console script:

```bash
PYTHONPATH=src python3 -m evaos_desktop_bridge.cli --help
```

## Commands

All MVP commands emit the same JSON envelope:

```json
{
  "schema_version": "2026-05-02.mvp1",
  "command": "codex.snapshot",
  "target": "codex",
  "timestamp": "2026-05-02T00:00:00Z",
  "ok": true,
  "data": {},
  "warnings": [],
  "errors": [],
  "audit_id": "audit-..."
}
```

### Desktop status

```bash
evaos-desktop-bridge status --json
```

Reports whether Codex Desktop appears installed/running, the visible process pid if present, and permission status where macOS exposes it.

### Capability and local state

```bash
evaos-desktop-bridge capabilities --json
evaos-desktop-bridge latest --json
evaos-desktop-bridge audit-tail --json --limit 20
```

`capabilities` reports the read-only command surface and forbidden actions. `latest` returns the last redacted observation envelope written by `status` or a Codex observer command. `audit-tail` returns a capped, redacted tail of local audit records for OpenClaw/Eva provenance.

### Visible Codex State

```bash
evaos-desktop-bridge codex frontmost --json
evaos-desktop-bridge codex windows --json
evaos-desktop-bridge codex threads --json --max-items 50
evaos-desktop-bridge codex inspect --json --max-nodes 120
```

These commands read only visible GUI state. `threads` returns capped visible thread candidates with deterministic `visible_id` values that can be compared against the Codex Desktop UI.

### Guarded Visible Actions

```bash
evaos-desktop-bridge codex focus --json --dry-run
evaos-desktop-bridge codex focus --json
evaos-desktop-bridge codex select-thread --json --thread-id visible-0-... --dry-run
```

Focuses Codex or selects an already-visible thread candidate through macOS Accessibility. These actions do not launch Codex, type text, click send/approval controls, or send turns. `select-thread` should be dry-run first and fails closed if the target is stale, offscreen, missing bounds, or permissions are absent.

### Visible snapshot

```bash
evaos-desktop-bridge codex snapshot --json --max-chars 4000
```

Returns the frontmost app, front window title when available, a screenshot path if capture succeeds, and a timestamp. Text is capped and redacted before output.

### Accessibility tree

```bash
evaos-desktop-bridge codex ax-tree --json --max-nodes 200
```

Returns a capped Accessibility tree with `role` and `name` only. It omits values, descriptions, full text buffers, tokens, and session database content.

### Read-Only App-Server Seam

```bash
evaos-desktop-bridge codex app-server status --json
evaos-desktop-bridge codex app-server threads --json --max-items 50
evaos-desktop-bridge codex connections status --json
evaos-desktop-bridge codex app-server subscribe --json --thread-id THREAD --duration-ms 1000
```

The app-server adapter uses a hard read allowlist for observation and a separate guarded controller allowlist for `turn/start`, `turn/steer`, and `turn/interrupt`. Generic app-server RPC passthrough remains forbidden. `subscribe` opens a short read-only notification window and returns capped/redacted live events.

### Guarded Remote-Control Actions

```bash
evaos-desktop-bridge codex app-server start-turn --json --thread-id THREAD --message "..." --dry-run
evaos-desktop-bridge codex app-server steer-turn --json --thread-id THREAD --turn-id TURN --message "..." --dry-run
evaos-desktop-bridge codex app-server interrupt-turn --json --thread-id THREAD --turn-id TURN --dry-run
```

Live controller calls require `--live --confirm --source-audit-id audit-...`. They are audited, redacted, capped, and intentionally named; the bridge still blocks injection, shell commands, file writes, config writes, plugin installs, login/logout, and arbitrary app-server methods.

### Announcement Queue

```bash
evaos-desktop-bridge queue append --json --kind attention --source-audit-id audit-...
evaos-desktop-bridge queue list --json --limit 20
```

The local queue is a JSONL contract for Eva/OpenClaw notifications such as `idle`, `approval_needed`, `done`, `error`, and `attention`. It is local-only and references bridge audit ids for provenance.

### OpenClaw plugin wrapper

The `openclaw-plugin/` package exposes fixed read-only and guarded controller tools for OpenClaw:

- `desktop_bridge_status`
- `desktop_bridge_capabilities`
- `desktop_bridge_latest`
- `desktop_bridge_audit_tail`
- `desktop_bridge_queue_list`
- `desktop_bridge_queue_append`
- `desktop_bridge_codex_frontmost`
- `desktop_bridge_codex_windows`
- `desktop_bridge_codex_threads`
- `desktop_bridge_codex_select_thread`
- `desktop_bridge_codex_snapshot`
- `desktop_bridge_codex_inspect`
- `desktop_bridge_codex_ax_tree`
- `desktop_bridge_codex_app_server_status`
- `desktop_bridge_codex_app_server_threads`
- `desktop_bridge_codex_connections_status`
- `desktop_bridge_codex_live_status`
- `desktop_bridge_codex_remote_start_turn`
- `desktop_bridge_codex_remote_steer_turn`
- `desktop_bridge_codex_remote_interrupt_turn`

The plugin calls `evaos-desktop-bridge` through fixed argv mappings only. It does not expose a generic shell, arbitrary bridge command runner, typer, generic mutation app-server client, or session database reader. Live remote-control tools are separate from read-only tools and request OpenClaw approval. See [docs/openclaw-plugin.md](docs/openclaw-plugin.md).

## Local audit log

Every valid bridge command appends a redacted JSONL record to:

```text
~/Library/Application Support/evaos-desktop-bridge/audit.jsonl
```

Set `EVAOS_DESKTOP_BRIDGE_STATE_DIR` to redirect audit logs and screenshots during tests:

```bash
EVAOS_DESKTOP_BRIDGE_STATE_DIR=/tmp/evaos-desktop-bridge \
  evaos-desktop-bridge status --json
```

## macOS permissions

Live focus and Accessibility-tree reads require Accessibility permission. Screenshots require Screen Recording permission. See [docs/macos-permissions.md](docs/macos-permissions.md) for setup and troubleshooting.

## Safety posture

- No full internal control socket.
- No hidden mutation backdoor.
- No generic mutation-capable Codex app-server passthrough.
- No prompt/message/turn sending except named, guarded, audited remote-control controller tools.
- No generic OpenClaw shell passthrough through the plugin.
- No Codex session database reads.
- No token, auth-file, or full home-path exposure.
- Read-only first; controller actions opt-in, named, dry-runnable, and approval-gated.

Initial visible desktop concurrency cap: 1 session, 2 maximum after measurement.

## Tests

```bash
python3 -m pytest
```

The automated suite uses mocked macOS runners. Live GUI checks are manual because they depend on the operator's TCC permissions and currently visible desktop state.
