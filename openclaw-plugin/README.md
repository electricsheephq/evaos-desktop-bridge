# evaOS Desktop Bridge for OpenClaw

Read-only OpenClaw plugin wrapper for `evaos-desktop-bridge`.

## Exposed Tools

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

The plugin deliberately does not expose generic click, type, prompt-send, mutation app-server, session database, or arbitrary shell tools. `desktop_bridge_codex_select_thread` is the only guarded visible action and defaults to dry-run.

## Local Setup

Install the bridge CLI first:

```bash
python3 -m pip install -e .
evaos-desktop-bridge capabilities --json
```

If OpenClaw cannot find the executable, set:

```bash
export EVAOS_DESKTOP_BRIDGE_BIN=/absolute/path/to/evaos-desktop-bridge
```

## Safety Notes

All plugin tools call fixed bridge argv mappings with `shell: false`. Numeric caps are clamped. A `before_tool_call` firewall blocks common shell/computer escape hatches that would bypass the read-only observer boundary.
