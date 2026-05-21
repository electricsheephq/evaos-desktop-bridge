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
- `desktop_bridge_codex_snapshot`: capped visible snapshot; screenshot only when Codex is frontmost.
- `desktop_bridge_codex_inspect`: compact page map of visible windows, controls, and text summaries.
- `desktop_bridge_codex_ax_tree`: capped Accessibility roles/names tree.
- `desktop_bridge_codex_app_server_status`: Codex app-server availability and read allowlist.
- `desktop_bridge_codex_app_server_remote_control_status`: Codex native remote-control readiness probe; no enabling or mutation.
- `desktop_bridge_codex_app_server_threads`: capped app-server thread summaries through the read allowlist.
- `customer_mac_status`: paired Mac, permission, iPhone Mirroring, and Screen Sharing readiness.
- `customer_mac_capabilities`: supported customer Mac targets and forbidden actions.
- `customer_mac_snapshot`: safe screenshot path for the frontmost non-sensitive app.
- `customer_mac_ax_tree`: capped Accessibility tree for the frontmost non-sensitive app.
- `customer_mac_iphone_mirroring_status`: iPhone Mirroring readiness.
- `customer_mac_screen_sharing_status`: Screen Sharing/Remote Management status; cannot enable it.

Guarded visible action:

- `desktop_bridge_codex_select_thread`: select an already-visible thread by `visible_id`; `dry_run` defaults to true.
- `desktop_bridge_codex_continue_thread`: support-only fallback; select a visible thread by title and submit exact `continue` after dry-run approval.
- `customer_mac_app_focus`: focus a non-sensitive Mac app by name.
- `customer_mac_local_site_open`: open a localhost, loopback, or `.local` website.
- `customer_mac_local_site_action`: reload/back/forward in a supported browser.
- `customer_mac_iphone_mirroring_focus`: focus iPhone Mirroring.
- `customer_mac_iphone_mirroring_home`: send Home.
- `customer_mac_iphone_mirroring_app_switcher`: open App Switcher.
- `customer_mac_iphone_mirroring_spotlight`: open Spotlight.
- `customer_mac_iphone_mirroring_type_spotlight`: type short disposable/search text.
- `customer_mac_iphone_mirroring_open_app`: open a non-sensitive app.
- `customer_mac_iphone_mirroring_tap_named_target`: press an exact visible AX label.
- `customer_mac_iphone_mirroring_scroll`: scroll by named direction.
- `customer_mac_iphone_mirroring_swipe_left/right/up/down`: named gestures; no generic coordinates.
- `customer_mac_iphone_mirroring_type_approved_text`: same-turn-approved text entry.
- `customer_mac_iphone_mirroring_send_approved_message`: same-turn-approved message send with exact recipient/context and text.

No plugin tool exposes generic prompt sending, arbitrary Codex app-server RPCs, hidden shell, session database reads, Screen Sharing enablement, arbitrary coordinates, or arbitrary shell commands. The only Codex prompt-like fallback is `desktop_bridge_codex_continue_thread`, which is support-only, fixed to exact `continue`, dry-run/approval-gated, and should be used only when native Codex remote-control is unavailable.

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
unknown commands and rejects remote live guarded actions unless `dry_run=false`
includes `approval_audit_id`.

Customer-facing iPhone live gestures/messages use the same approval flow as
every other guarded action. They require a prior dry-run, plugin approval,
matching `approval_audit_id`, and local connector audit evidence.

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

This hook is a defense-in-depth control. The primary safety boundary remains the fixed bridge CLI allowlist and the absence of mutation tools.

## Hands Boundary

GUI control is limited to named actions. Codex Desktop remains read-only plus
the existing visible thread-selection action and the support-only exact
`continue` fallback. Customer Mac and iPhone Mirroring actions are dry-run by
default, approval-gated in the plugin, audited by the bridge, and blocked for
sensitive apps/labels. Approved iPhone message sends require exact same-turn
approval of both recipient/context and message text. Broader hands should remain
a separate, approval-gated macro layer, not arbitrary coordinates or text
injection.
