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
- `desktop_bridge_codex_thread_map`
- `desktop_bridge_codex_select_thread`
- `desktop_bridge_codex_send_visible_message`
- `desktop_bridge_codex_snapshot`
- `desktop_bridge_codex_inspect`
- `desktop_bridge_codex_ax_tree`
- `desktop_bridge_codex_app_server_status`
- `desktop_bridge_codex_app_server_remote_control_status`
- `desktop_bridge_codex_app_server_threads`
- `desktop_bridge_codex_connections_status`
- `desktop_bridge_codex_app_server_loaded_threads`
- `desktop_bridge_codex_live_status`
- `desktop_bridge_codex_continue_thread`
- `evaos_provider_profiles`
- `evaos_provider_active_profile`
- `evaos_provider_complete_auth`
- `evaos_shared_browser_guidance`
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
- `desktop_set_value`
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
iPhone Mirroring, plus named guarded Codex Desktop app-server controller tools,
but not a generic shell, hidden AppleScript passthrough, public VNC/SSH,
generic Codex app-server RPC passthrough, session database access, or Screen
Sharing enablement. Codex controller live mode requires `confirm:true` and a
`source_audit_id`; customer Mac/iPhone approval is enforced by connector control
mode, not by hardcoded per-action prompts.

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

Provider/Auth Hub and Shared Browser discovery are metadata-only VM tools.
When the control plane has minted an opaque provider grant, the plugin can
discover the active provider profile from the broker; otherwise it falls back to
optional VM environment snapshots. It never exposes raw provider credentials:

```bash
export EVAOS_CUSTOMER_ID="<customer-id>"
export EVAOS_PROVIDER_DISCOVERY_URL="https://<supabase-project>.supabase.co/functions/v1/desktop-runtime-session"
export EVAOS_PROVIDER_GRANT_HANDLE="epg_..."
export EVAOS_PROVIDER_AUTH_PROOF_SECRET="<control-plane-proof-secret>"
export EVAOS_PROVIDER_SERVER_SECRET_REF="provider://openai_codex/<customer-id>/openclaw"
export EVAOS_PROVIDER_AUTH_IDENTITY="user@example.com"
export EVAOS_PROVIDER_GRANT_CACHE_FILE="$HOME/.openclaw/evaos-provider-grants.json"
export EVAOS_PROVIDER_PROFILES_JSON='{"provider_profiles":[]}'
export EVAOS_PROVIDER_GRANTS_JSON='[]'
export EVAOS_SHARED_BROWSER_STATUS_JSON='{"schema_version":"evaos.browser_status.v1","customer_account_id":"acct_123","customer_id":"david-poku","runtime":"browser","status":"ready","room_id":"shared-browser:david-poku","session_id":"browser-session-123","owner":"david-poku","current_url":{"host":"accounts.google.com","path":"/signin","query_redacted":true},"last_activity_at":"2026-06-01T00:00:00Z","needs_auth":true,"needs_captcha":false,"actions":["start_attach","refresh_status","stop_browser"],"source_pointer":"broker:runtime_status:browser","audit_id":"audit_123"}'
```

`evaos_shared_browser_guidance` returns the same `evaos.browser_status.v1`
metadata shape that Workbench uses for Business Browser status. It is guidance
only: agents may prefer the brokered browser for auth/CAPTCHA and cloud web
tasks, but this does not add generic browser automation or raw cookie access.
`room_id` identifies the shared browser room; `session_id` identifies the
current browser session when broker evidence includes it.

`evaos_provider_complete_auth` posts signed metadata proof for the VM-side
Codex/OpenAI readiness check. The proof includes identity, scopes, expiry, and a
server-side secret reference only; raw OpenAI/Codex cookies, access tokens,
refresh tokens, API keys, and authorization headers are never returned through
the plugin. When the broker returns an OpenClaw grant, the plugin stores only
that opaque grant handle in `EVAOS_PROVIDER_GRANT_CACHE_FILE` or
`~/.openclaw/evaos-provider-grants.json` so later discovery works without a
human manually injecting environment variables.

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
approval for guarded Codex visible GUI message sends and legacy guarded customer Mac actions. Codex visible sends also accept `thread_id=current` for the already-open visible thread plus optional `wait_ms` and `poll_interval_ms` parameters for capped read-only post-send progress evidence. New `desktop_*` and
`iphone_*` actions are governed by the Workbench control session: Full Access
allows live action without `approval_audit_id`, Ask Permission gates risky
clicks, taps, hotkeys, typing, sends, and other high-impact actions, and the
kill switch blocks all live control immediately.
