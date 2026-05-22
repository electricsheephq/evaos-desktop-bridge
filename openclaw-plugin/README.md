# evaOS Desktop Bridge for OpenClaw

OpenClaw plugin wrapper for `evaos-desktop-bridge`. Codex Desktop tools remain
read-oriented except the visible support fallback. Customer Mac/iPhone tools now
use the Workbench connector's customer-granted control session:

- **Full Access**: live desktop and iPhone actions run continuously after the
  customer starts the session in Workbench.
- **Ask Permission**: navigation stays continuous, but risky clicks, taps,
  hotkeys, typing, sends, and other high-impact actions still require approval
  evidence.
- The connector keeps the visible session state, audit log, and kill switch.

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
- `desktop_bridge_codex_app_server_remote_control_status`
- `desktop_bridge_codex_app_server_threads`
- `desktop_bridge_codex_continue_thread`
- `customer_mac_status`
- `desktop_control_status`
- `desktop_control_start`
- `desktop_control_stop`
- `desktop_kill_switch`
- `customer_mac_complete_pairing`
- `customer_mac_capabilities`
- `desktop_see`
- `desktop_click`
- `desktop_type`
- `desktop_scroll`
- `desktop_drag`
- `desktop_hotkey`
- `desktop_focus_app`
- `desktop_window`
- `desktop_menu`
- `desktop_browser_action`
- `customer_mac_snapshot`
- `customer_mac_ax_tree`
- `customer_mac_app_focus`
- `customer_mac_local_site_open`
- `customer_mac_local_site_action`
- `iphone_see`
- `iphone_tap`
- `iphone_swipe`
- `iphone_type`
- `customer_mac_iphone_mirroring_status`
- `customer_mac_iphone_mirroring_focus`
- `customer_mac_iphone_mirroring_home`
- `customer_mac_iphone_mirroring_app_switcher`
- `customer_mac_iphone_mirroring_spotlight`
- `customer_mac_iphone_mirroring_type_spotlight`
- `customer_mac_iphone_mirroring_open_app`
- `customer_mac_iphone_mirroring_tap_named_target`
- `customer_mac_iphone_mirroring_scroll`
- `customer_mac_iphone_mirroring_swipe_left`
- `customer_mac_iphone_mirroring_swipe_right`
- `customer_mac_iphone_mirroring_swipe_up`
- `customer_mac_iphone_mirroring_swipe_down`
- `customer_mac_iphone_mirroring_type_approved_text`
- `customer_mac_iphone_mirroring_send_approved_message`
- `customer_mac_screen_sharing_status`

The plugin exposes a real computer-use surface for the paired customer Mac and
iPhone Mirroring, but not a generic shell, hidden AppleScript passthrough,
public VNC/SSH, mutation Codex app-server RPCs, session database access, or
Screen Sharing enablement. Approval is enforced by connector control mode, not
by hardcoded per-action prompts.

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
export EVAOS_DESKTOP_BRIDGE_TOKEN="$(cat "$HOME/Library/Application Support/evaos-desktop-bridge/connector.token")"
```

Before a VM has a connector token, `customer_mac_complete_pairing` posts the
one-time enrollment code directly to the Mac connector's
`/v1/enrollment/complete` endpoint. Its `connector_url` must be an `http://`
base URL on port `8765` with a private/tailnet host such as `100.64.x.y`,
`10.x.y.z`, `172.16-31.x.y`, `192.168.x.y`, or a local `.local` hostname.

## Safety Notes

Local plugin tools call fixed bridge argv mappings with `shell: false`. Remote
plugin tools post fixed command keys to `/v1/commands` on the paired Mac
connector. Numeric caps are clamped. A `before_tool_call` firewall blocks common
shell/computer escape hatches that would bypass the bridge boundary and requests
approval for legacy guarded customer Mac actions. New `desktop_*` and
`iphone_*` actions are governed by the Workbench control session: Full Access
allows live action without `approval_audit_id`, Ask Permission gates risky
clicks, taps, hotkeys, typing, sends, and other high-impact actions, and the
kill switch blocks all live control immediately.
