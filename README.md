# evaOS Desktop Bridge

Safe bridge between Eva/OpenClaw and visible human desktop agent surfaces.

The first MVP target is **Codex Desktop on macOS**. This slice is deliberately small: it observes visible state, reports permission readiness, focuses an already-running Codex Desktop window, and writes a local audit trail. It does not send prompts, click conversation controls, call Codex internal mutation RPCs, hijack stdio, or read Codex session databases.

## Architecture

- **Eyes:** read-only state adapters that expose safe structured desktop/session metadata.
- **Hands:** CLI-Anything-style GUI harnesses that operate visible desktop apps through macOS Accessibility/screenshot/AppleScript primitives.
- **Brain:** Eva/OpenClaw policy, approvals, audit logging, and announcement queue.

Current MVP implements the first Codex Desktop eyes adapter plus one narrow visible-window focus command. Brain/queue integration and Codex app-server attach are later work.

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

### Focus Codex Desktop

```bash
evaos-desktop-bridge codex focus --json --dry-run
evaos-desktop-bridge codex focus --json
```

Focuses an already-running Codex Desktop process through macOS Accessibility. It does not launch Codex, type text, click session controls, or send turns.

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
- No Codex app-server attach in this MVP.
- No prompt/message/turn sending.
- No Codex session database reads.
- No token, auth-file, or full home-path exposure.
- Read-only first; visible GUI inspection only.

Initial visible desktop concurrency cap: 1 session, 2 maximum after measurement.

## Tests

```bash
python3 -m pytest
```

The automated suite uses mocked macOS runners. Live GUI checks are manual because they depend on the operator's TCC permissions and currently visible desktop state.
