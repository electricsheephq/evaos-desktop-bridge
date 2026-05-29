# OpenClaw Plugin Wrapper

The `openclaw-plugin/` package is the first native OpenClaw-facing wrapper for `evaos-desktop-bridge`. It is intentionally a thin adapter around the bridge CLI so the security boundary stays visible and testable.

## Tools

Read-only tools:

- `desktop_bridge_status`: Codex Desktop install/running/permission status.
- `desktop_bridge_capabilities`: bridge capability list, forbidden actions, and data-minimization flags.
- `desktop_bridge_latest`: last redacted observation envelope from local state.
- `desktop_bridge_audit_tail`: capped redacted audit log tail.
- `desktop_bridge_queue_list`: capped local announcement queue events.
- `desktop_bridge_queue_append`: append a local queue event with source audit provenance.
- `desktop_bridge_codex_frontmost`: current frontmost app and Codex-frontmost boolean.
- `desktop_bridge_codex_windows`: visible Codex window metadata.
- `desktop_bridge_codex_threads`: visible Codex thread candidates from GUI state.
- `desktop_bridge_codex_thread_map`: joined visible GUI candidates and saved app-server thread summaries.
- `desktop_bridge_codex_snapshot`: capped visible snapshot; screenshot only when Codex is frontmost.
- `desktop_bridge_codex_inspect`: compact page map of visible windows, controls, and text summaries.
- `desktop_bridge_codex_ax_tree`: capped Accessibility roles/names tree.
- `desktop_bridge_codex_app_server_status`: Codex app-server availability and read allowlist.
- `desktop_bridge_codex_app_server_remote_control_status`: Codex native remote-control readiness probe; no enabling or mutation.
- `desktop_bridge_codex_app_server_threads`: capped app-server thread summaries through the read allowlist.
- `desktop_bridge_codex_connections_status`: Codex Desktop, app-server, daemon, websocket, remote-control, and notification readiness.
- `desktop_bridge_codex_app_server_loaded_threads`: loaded Codex Desktop thread ids eligible for controller actions.
- `desktop_bridge_codex_live_status`: short live-notification read for one loaded thread.
- `customer_mac_status`: paired Mac, permission, iPhone Mirroring, and Screen Sharing readiness.
- `customer_mac_capabilities`: supported customer Mac targets and forbidden actions.
- `desktop_control_status`: current Full Access / Ask Permission session state.
- `desktop_see`: desktop observation through Peekaboo or built-in screen/AX fallback, with visual artifact metadata, screenshot bytes when small enough, element bounds, and a `snapshot_id`.
- `iphone_see`: iPhone Mirroring observation through the same visible Mac surface, with the same visual artifact and element contract.
- `customer_mac_snapshot`: safe screenshot path for the frontmost non-sensitive app.
- `customer_mac_ax_tree`: capped Accessibility tree for the frontmost non-sensitive app.
- `customer_mac_iphone_mirroring_status`: iPhone Mirroring readiness.
- `customer_mac_screen_sharing_status`: Screen Sharing/Remote Management status; cannot enable it.

Guarded visible action:

- `desktop_bridge_codex_select_thread`: select an already-visible thread by `visible_id`; `dry_run` defaults to true.
- `desktop_bridge_codex_send_visible_message`: send an approved message through the visible Codex Desktop composer; `dry_run` defaults to true and live mode requires `confirm` plus a matching `approval_audit_id`.
- `desktop_bridge_codex_continue_thread`: support-only fallback; select a visible thread by title and submit exact `continue` after dry-run approval.
- `customer_mac_app_focus`: focus a non-sensitive Mac app by name.
- `customer_mac_local_site_open`: open a localhost, loopback, or `.local` website.
- `customer_mac_local_site_action`: reload/back/forward in a supported browser.
- `customer_mac_iphone_mirroring_focus`: focus iPhone Mirroring.
- `customer_mac_iphone_mirroring_home`: send Home.
- `customer_mac_iphone_mirroring_app_switcher`: open App Switcher.
- `customer_mac_iphone_mirroring_spotlight`: open Spotlight.
- `customer_mac_iphone_mirroring_type_spotlight`: type short disposable/search text.
- `customer_mac_iphone_mirroring_open_app`: open an app in iPhone Mirroring.
- `customer_mac_iphone_mirroring_tap_named_target`: press an exact visible AX label.
- `customer_mac_iphone_mirroring_scroll`: scroll by named direction.
- `customer_mac_iphone_mirroring_swipe_left/right/up/down`: named gestures; no generic coordinates.
- `customer_mac_iphone_mirroring_type_approved_text`: same-turn-approved text entry.
- `customer_mac_iphone_mirroring_send_approved_message`: visible message send through iPhone Mirroring. Full Access allows it continuously; Ask Permission gates it.

Full-access computer-control tools:

- `desktop_control_start`, `desktop_control_stop`, `desktop_kill_switch`
- `desktop_click`, `desktop_type`, `desktop_scroll`, `desktop_drag`,
  `desktop_hotkey`, `desktop_focus_app`, `desktop_window`, `desktop_menu`,
  `desktop_browser_action`
- `iphone_tap`, `iphone_swipe`, `iphone_type`

`desktop_click` and `iphone_tap` accept `snapshot_id` plus either `element_id`,
`target_label`, or `x/y` coordinates. Prefer `element_id` from the latest
`desktop_see` / `iphone_see` result; stale snapshots are rejected by the
connector so the agent does not act on an old screen.

Every live control result includes engine evidence. For `0.4.10`, a healthy
install should show `engine=peekaboo` for snapshot element clicks, coordinate
clicks, drags/swipes, menu paths, window actions, and URL opens unless the
bridge explicitly reports a fallback engine such as `quartz`, `system_events`,
or `ax_fallback`.

No plugin tool exposes arbitrary Codex app-server RPCs, hidden shell, session
database reads, Screen Sharing enablement, public VNC/SSH/CDP, or arbitrary
shell commands. Codex prompt-like control is limited to fixed named GUI tools:
`desktop_bridge_codex_send_visible_message` for an explicitly approved visible
message and `desktop_bridge_codex_continue_thread` for the support-only exact
`continue` canary. Native Codex app-server controller tools are intentionally
withheld until issue #136 proves a visible Desktop thread is present in
`thread/loaded/list`.

## Runtime Contract

The wrapper resolves the bridge executable from `EVAOS_DESKTOP_BRIDGE_BIN`, falling back to `evaos-desktop-bridge` on `PATH`.

Each tool maps to a fixed argv list. User parameters can only change numeric caps, queue fields, dry-run, or a visible thread id; numeric values are clamped before execution.

For paired customer VMs, the wrapper can call the customer's Mac connector over
Headscale instead of execing a local bridge binary:

```bash
export EVAOS_DESKTOP_BRIDGE_URL=http://<mac-headscale-ip>:8765
export EVAOS_DESKTOP_BRIDGE_TOKEN="$(cat "$HOME/Library/Application Support/evaos-desktop-bridge/connector.token")"
```

Remote mode posts fixed command keys to `/v1/commands`. The connector rejects
unknown commands. Live `desktop_*` and `iphone_*` tools require an active
Workbench control session. Full Access permits continuous live actions. Ask
Permission permits navigation actions and requires approval evidence only for
risky clicks, taps, hotkeys, typing, sends, and other high-impact actions. The
kill switch blocks future live commands.

For visual commands, the OpenClaw wrapper materializes screenshot evidence under
`/root/agent-files/downloads/desktop-bridge/` by default and removes inline
base64 from the tool response after writing the file. If the screenshot is too
large to inline, the wrapper fetches the short-lived connector artifact over the
same authenticated `/v1/artifacts/...` route and writes that file instead. Set
`EVAOS_DESKTOP_BRIDGE_ARTIFACT_DIR` to override the VM-side artifact path.

## Firewall Hook

The plugin registers a `before_tool_call` hook named `evaos-desktop-bridge-firewall`. It blocks suspicious desktop-control or Codex-internal escape hatches when they appear in generic shell/computer-style tool calls, including:

- `osascript`
- `screencapture`
- `cliclick`
- `pyautogui`
- `pynput`
- `codex app-server`
- `turn/start`
- `thread/inject_items`
- `config/batchWrite`
- `plugin/install`
- `session.db`
- prompt sending or typewrite-style operations

This hook is a defense-in-depth control. The primary boundary is the fixed bridge
CLI allowlist, connector token auth, Workbench control mode, audit log, and kill
switch.

## Hands Boundary

Codex Desktop remains read-only plus the existing visible thread-selection
action and the support-only exact `continue` fallback. Customer Mac and iPhone
Mirroring control is now session-based: Full Access is intended to approach
local Mac computer-use parity; Ask Permission keeps a higher-friction mode for
customers who want confirmation around high-impact actions.
