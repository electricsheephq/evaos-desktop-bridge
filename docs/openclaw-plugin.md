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
- `desktop_bridge_codex_connections_status`: Codex Desktop/app-server connection and remote-control readiness.
- `desktop_bridge_codex_app_server_status`: Codex app-server availability and read allowlist.
- `desktop_bridge_codex_app_server_threads`: capped app-server thread summaries through the read allowlist.
- `desktop_bridge_codex_app_server_loaded_threads`: currently loaded app-server controller threads for safe remote-control targeting.
- `desktop_bridge_codex_live_status`: short capped app-server notification window for a thread.

Guarded visible action:

- `desktop_bridge_codex_select_thread`: select an already-visible thread by `visible_id`; `dry_run` defaults to true.

Guarded remote-control actions:

- `desktop_bridge_codex_remote_start_turn`: start a Codex Desktop turn through app-server; dry-run defaults to true.
- `desktop_bridge_codex_remote_steer_turn`: steer an active Codex Desktop turn through app-server; dry-run defaults to true.
- `desktop_bridge_codex_remote_interrupt_turn`: interrupt an active Codex Desktop turn through app-server; dry-run defaults to true.

No plugin tool types text, clicks send/approval controls, launches Codex, calls arbitrary app-server RPCs, reads session databases, or accepts arbitrary shell commands. Live remote-control tools require explicit params, OpenClaw approval, and a thread already present in `desktop_bridge_codex_app_server_loaded_threads`.

## Runtime Contract

The wrapper resolves the bridge executable from `EVAOS_DESKTOP_BRIDGE_BIN`, falling back to `evaos-desktop-bridge` on `PATH`.

Each tool maps to a fixed argv list. User parameters can only change numeric caps, queue fields, dry-run/live controller flags, source audit id, thread/turn ids, and bounded messages; numeric values are clamped before execution.

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

For live controller tools, the same hook requests approval when `dry_run` is `false`. The bridge CLI also requires `--live --confirm --source-audit-id audit-...`, so approval UI and local provenance both have to line up before a turn is started, steered, or interrupted.

## Hands Boundary

GUI control is limited to the named visible `select_thread` action. Broader hands should be added as a separate, approval-gated macro layer, not arbitrary coordinates or text injection.
