# evaOS Desktop Bridge for OpenClaw

OpenClaw plugin wrapper for `evaos-desktop-bridge`. The Codex Desktop tools are
read-only except the visible thread-select dry-run action. Customer Mac tools are
named and approval-gated.

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
- `customer_mac_status`
- `customer_mac_capabilities`
- `customer_mac_snapshot`
- `customer_mac_ax_tree`
- `customer_mac_app_focus`
- `customer_mac_local_site_open`
- `customer_mac_local_site_action`
- `customer_mac_iphone_mirroring_status`
- `customer_mac_iphone_mirroring_focus`
- `customer_mac_iphone_mirroring_home`
- `customer_mac_iphone_mirroring_app_switcher`
- `customer_mac_iphone_mirroring_spotlight`
- `customer_mac_iphone_mirroring_type_spotlight`
- `customer_mac_iphone_mirroring_open_app`
- `customer_mac_iphone_mirroring_tap_named_target`
- `customer_mac_iphone_mirroring_scroll`
- `customer_mac_screen_sharing_status`

The plugin deliberately does not expose generic click, type, prompt-send,
mutation app-server, session database, arbitrary coordinates, Screen Sharing
enablement, or arbitrary shell tools. Guarded actions default to dry-run.

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

For a paired customer VM calling the customer's Mac over Headscale, point the
plugin at the connector server instead:

```bash
export EVAOS_DESKTOP_BRIDGE_URL=http://<mac-headscale-ip>:8765
export EVAOS_DESKTOP_BRIDGE_TOKEN=<connector-token>
```

## Safety Notes

Local plugin tools call fixed bridge argv mappings with `shell: false`. Remote
plugin tools post fixed command keys to `/v1/commands` on the paired Mac
connector. Numeric caps are clamped. A `before_tool_call` firewall blocks common
shell/computer escape hatches that would bypass the bridge boundary and requests
approval for live guarded customer Mac actions. The connector also rejects remote
live guarded actions unless `dry_run=false` is accompanied by `approval_audit_id`.
