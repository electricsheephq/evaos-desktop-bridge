from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, TextIO

from .adapters.codex_app_server import CodexAppServerObserver
from .adapters.codex_acpx import AcpxWorkerObserver
from .adapters.codex_macos import MacOSCodexObserver
from .adapters.codex_sessions import CodexSessionObserver
from .adapters.customer_mac import CustomerMacObserver
from .audit import append_audit
from .policy import PolicyError, command_metadata, ensure_allowed
from .queue import append_queue_event, list_queue_events
from .schema import build_envelope
from .state import read_audit_tail, read_latest, write_latest
from .types import CommandResult

LATEST_OBSERVATION_COMMANDS = frozenset(
    {
        "status",
        "capabilities",
        "codex.frontmost",
        "codex.windows",
        "codex.threads",
        "codex.acpx_list",
        "codex.acpx_show",
        "codex.acpx_status",
        "codex.acpx_prompt",
        "codex.acpx_history",
        "codex.acpx_tail_events",
        "codex.indexed_threads",
        "codex.read_thread_tail",
        "codex.open_thread",
        "codex.desktop_freshness",
        "codex.rehydrate_thread",
        "codex.steer_thread",
        "codex.menu_action",
        "codex.find_control",
        "codex.snapshot",
        "codex.inspect",
        "codex.ax_tree",
        "codex.app_server.status",
        "codex.app_server.threads",
        "customer_mac.status",
        "customer_mac.capabilities",
        "customer_mac.snapshot",
        "customer_mac.ax_tree",
        "customer_mac.iphone_mirroring_status",
        "customer_mac.screen_sharing_status",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaos-desktop-bridge",
        description="Safe read-only bridge for visible desktop agent surfaces.",
    )
    subparsers = parser.add_subparsers(dest="scope")

    status_parser = subparsers.add_parser("status", help="Report desktop bridge and Codex Desktop status.")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    status_parser.set_defaults(command_id="status", target="desktop")

    capabilities_parser = subparsers.add_parser("capabilities", help="Report the safe bridge capability surface.")
    capabilities_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    capabilities_parser.set_defaults(command_id="capabilities", target="desktop")

    latest_parser = subparsers.add_parser("latest", help="Return the last observed bridge envelope.")
    latest_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    latest_parser.set_defaults(command_id="latest", target="desktop")

    audit_parser = subparsers.add_parser("audit-tail", help="Return a redacted tail of the local audit log.")
    audit_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    audit_parser.add_argument("--limit", type=_positive_int, default=20, help="Maximum audit records to return.")
    audit_parser.set_defaults(command_id="audit_tail", target="desktop")

    queue_parser = subparsers.add_parser("queue", help="Eva/OpenClaw announcement queue commands.")
    queue_subparsers = queue_parser.add_subparsers(dest="queue_command")

    queue_list_parser = queue_subparsers.add_parser("list", help="List local announcement queue events.")
    queue_list_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    queue_list_parser.add_argument("--limit", type=_positive_int, default=20, help="Maximum queue events to return.")
    queue_list_parser.set_defaults(command_id="queue.list", target="queue")

    queue_append_parser = queue_subparsers.add_parser("append", help="Append an Eva/OpenClaw announcement queue event.")
    queue_append_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    queue_append_parser.add_argument("--kind", required=True, help="Queue kind: idle, approval_needed, done, error, attention.")
    queue_append_parser.add_argument("--source-audit-id", required=True, help="Source audit id for provenance.")
    queue_append_parser.add_argument("--message", default=None, help="Optional capped announcement message.")
    queue_append_parser.set_defaults(command_id="queue.append", target="queue")

    codex_parser = subparsers.add_parser("codex", help="Codex Desktop passive observer commands.")
    codex_subparsers = codex_parser.add_subparsers(dest="codex_command")

    frontmost_parser = codex_subparsers.add_parser("frontmost", help="Report the current frontmost app without capturing screenshots.")
    frontmost_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    frontmost_parser.set_defaults(command_id="codex.frontmost", target="codex")

    windows_parser = codex_subparsers.add_parser("windows", help="List visible Codex Desktop windows via Accessibility.")
    windows_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    windows_parser.set_defaults(command_id="codex.windows", target="codex")

    threads_parser = codex_subparsers.add_parser("threads", help="List visible Codex Desktop thread candidates from GUI state.")
    threads_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    threads_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum visible thread candidates to return.")
    threads_parser.set_defaults(command_id="codex.threads", target="codex")

    acpx_list_parser = codex_subparsers.add_parser("acpx-worker-list", help="List acpx-managed Codex background workers.")
    acpx_list_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    acpx_list_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum workers to return.")
    acpx_list_parser.set_defaults(command_id="codex.acpx_list", target="codex")

    acpx_show_parser = codex_subparsers.add_parser("acpx-worker-show", help="Show acpx worker metadata for current cwd or named session.")
    acpx_show_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    acpx_show_parser.add_argument("--session", default=None, help="Optional acpx named session.")
    acpx_show_parser.set_defaults(command_id="codex.acpx_show", target="codex")

    acpx_status_parser = codex_subparsers.add_parser("acpx-worker-status", help="Show acpx worker process/status information.")
    acpx_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    acpx_status_parser.add_argument("--session", default=None, help="Optional acpx named session.")
    acpx_status_parser.set_defaults(command_id="codex.acpx_status", target="codex")

    acpx_prompt_parser = codex_subparsers.add_parser("acpx-worker-prompt", help="Prompt an acpx-managed Codex background worker.")
    acpx_prompt_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    acpx_prompt_parser.add_argument("--message", required=True, help="Prompt text to send.")
    acpx_prompt_parser.add_argument("--session", default=None, help="Optional acpx named session.")
    acpx_prompt_parser.add_argument("--no-wait", action="store_true", help="Queue and return when worker is busy.")
    acpx_prompt_parser.add_argument("--dry-run", action="store_true", help="Preview without sending.")
    acpx_prompt_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum preview chars.")
    acpx_prompt_parser.set_defaults(command_id="codex.acpx_prompt", target="codex")

    acpx_history_parser = codex_subparsers.add_parser("acpx-worker-history", help="Read acpx worker history.")
    acpx_history_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    acpx_history_parser.add_argument("--session", default=None, help="Optional acpx named session.")
    acpx_history_parser.add_argument("--limit", type=_positive_int, default=20, help="History item limit.")
    acpx_history_parser.set_defaults(command_id="codex.acpx_history", target="codex")

    acpx_tail_parser = codex_subparsers.add_parser("acpx-worker-tail-events", help="Read acpx worker stream event tail by acpxRecordId.")
    acpx_tail_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    acpx_tail_parser.add_argument("--record-id", required=True, help="acpxRecordId from acpx-worker-list.")
    acpx_tail_parser.add_argument("--max-events", type=_positive_int, default=40, help="Maximum stream events to return.")
    acpx_tail_parser.set_defaults(command_id="codex.acpx_tail_events", target="codex")

    indexed_threads_parser = codex_subparsers.add_parser("indexed-threads", help="List persisted Codex Desktop/interactive threads from session_index.jsonl.")
    indexed_threads_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    indexed_threads_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum indexed threads to return.")
    indexed_threads_parser.set_defaults(command_id="codex.indexed_threads", target="codex")

    read_tail_parser = codex_subparsers.add_parser("read-thread-tail", help="Read a redacted tail from a Codex rollout file by thread id.")
    read_tail_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    read_tail_parser.add_argument("--thread-id", required=True, help="Codex thread id.")
    read_tail_parser.add_argument("--max-events", type=_positive_int, default=40, help="Maximum relevant rollout events to return.")
    read_tail_parser.add_argument("--max-chars", type=_positive_int, default=12000, help="Maximum chars per included text field / output budget hint.")
    read_tail_parser.set_defaults(command_id="codex.read_thread_tail", target="codex")

    open_thread_parser = codex_subparsers.add_parser("open-thread", help="Open a Codex Desktop thread by codex:// deep link.")
    open_thread_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    open_thread_parser.add_argument("--thread-id", required=True, help="Codex thread id.")
    open_thread_parser.add_argument("--dry-run", action="store_true", help="Report URL without opening Codex Desktop.")
    open_thread_parser.set_defaults(command_id="codex.open_thread", target="codex")

    freshness_parser = codex_subparsers.add_parser("desktop-freshness", help="Compare rollout truth against visible Desktop text for a thread.")
    freshness_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    freshness_parser.add_argument("--thread-id", required=True, help="Codex thread id.")
    freshness_parser.add_argument("--visible-text", default="", help="Visible Desktop text/marker from inspect or OCR/screenshot analysis.")
    freshness_parser.add_argument("--max-events", type=_positive_int, default=20, help="Maximum rollout events to inspect.")
    freshness_parser.set_defaults(command_id="codex.desktop_freshness", target="codex")

    rehydrate_parser = codex_subparsers.add_parser("rehydrate-thread", help="Open a Codex Desktop thread deep link to force read-after-write visibility.")
    rehydrate_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    rehydrate_parser.add_argument("--thread-id", required=True, help="Codex thread id.")
    rehydrate_parser.add_argument("--dry-run", action="store_true", default=True, help="Preview by default; pass through future explicit live gate before opening.")
    rehydrate_parser.add_argument("--live", action="store_true", help="Actually open the codex:// thread deep link.")
    rehydrate_parser.add_argument("--wait-ms", type=_positive_int, default=1500, help="Suggested wait before visible verification.")
    rehydrate_parser.set_defaults(command_id="codex.rehydrate_thread", target="codex")

    steer_thread_parser = codex_subparsers.add_parser("steer-thread", help="Send a steering prompt to an existing Codex Desktop thread via Codex CLI resume.")
    steer_thread_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    steer_thread_parser.add_argument("--thread-id", required=True, help="Codex thread id from indexed-threads.")
    steer_thread_parser.add_argument("--message", required=True, help="Steering prompt to send to the thread.")
    steer_thread_parser.add_argument("--dry-run", action="store_true", help="Preview the steering command without sending.")
    steer_thread_parser.add_argument("--timeout-seconds", type=_positive_int, default=120, help="Maximum seconds to wait for Codex CLI resume to finish.")
    steer_thread_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum chars for message/output previews.")
    steer_thread_parser.set_defaults(command_id="codex.steer_thread", target="codex")

    focus_parser = codex_subparsers.add_parser("focus", help="Focus the visible Codex Desktop app.")
    focus_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    focus_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without focusing.")
    focus_parser.set_defaults(command_id="codex.focus", target="codex")

    menu_action_parser = codex_subparsers.add_parser("menu-action", help="Invoke one allowlisted visible Codex menu action.")
    menu_action_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    menu_action_parser.add_argument("--menu", required=True, help="Menu name, e.g. File.")
    menu_action_parser.add_argument("--item", required=True, help="Menu item name, e.g. New Chat.")
    menu_action_parser.add_argument("--dry-run", action="store_true", help="Verify the visible menu action without clicking it.")
    menu_action_parser.set_defaults(command_id="codex.menu_action", target="codex")

    find_control_parser = codex_subparsers.add_parser("find-control", help="Find exact visible Codex controls by AX label without pressing them.")
    find_control_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    find_control_parser.add_argument("--label", required=True, help="Exact AX label to find, e.g. 'New chat'.")
    find_control_parser.add_argument("--max-nodes", type=_positive_int, default=500, help="Maximum AX nodes to inspect.")
    find_control_parser.set_defaults(command_id="codex.find_control", target="codex")

    press_control_parser = codex_subparsers.add_parser("press-control", help="Press an allowlisted visible Codex control via AXPress.")
    press_control_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    press_control_parser.add_argument("--label", required=True, help="Exact allowlisted AX label to press, e.g. 'New chat'.")
    press_control_parser.add_argument("--dry-run", action="store_true", help="Report the target without pressing.")
    press_control_parser.add_argument("--match-index", type=int, default=None, help="Specific match index from find-control when a label is not unique.")
    press_control_parser.add_argument("--max-nodes", type=_positive_int, default=500, help="Maximum AX nodes to inspect.")
    press_control_parser.set_defaults(command_id="codex.press_control", target="codex")

    select_parser = codex_subparsers.add_parser("select-thread", help="Select an already-visible Codex Desktop thread candidate.")
    select_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    select_parser.add_argument("--thread-id", required=True, help="Visible thread id from codex threads output.")
    select_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without clicking/selecting.")
    select_parser.set_defaults(command_id="codex.select_thread", target="codex")

    snapshot_parser = codex_subparsers.add_parser("snapshot", help="Capture safe visible Codex Desktop state.")
    snapshot_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    snapshot_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum visible text chars.")
    snapshot_parser.set_defaults(command_id="codex.snapshot", target="codex")

    inspect_parser = codex_subparsers.add_parser("inspect", help="Return a compact page map of visible Codex Desktop state.")
    inspect_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    inspect_parser.add_argument("--max-nodes", type=_positive_int, default=120, help="Maximum AX nodes to include.")
    inspect_parser.set_defaults(command_id="codex.inspect", target="codex")

    ax_parser = codex_subparsers.add_parser("ax-tree", help="Capture a capped Accessibility tree summary.")
    ax_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    ax_parser.add_argument("--max-nodes", type=_positive_int, default=200, help="Maximum AX nodes to return.")
    ax_parser.set_defaults(command_id="codex.ax_tree", target="codex")

    app_server_parser = codex_subparsers.add_parser("app-server", help="Read-only Codex app-server seam commands.")
    app_server_subparsers = app_server_parser.add_subparsers(dest="app_server_command")

    app_server_status_parser = app_server_subparsers.add_parser("status", help="Report read-only app-server availability and allowlist.")
    app_server_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_status_parser.set_defaults(command_id="codex.app_server.status", target="codex")

    app_server_threads_parser = app_server_subparsers.add_parser("threads", help="Read Codex threads through the app-server read allowlist.")
    app_server_threads_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_threads_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum app-server thread summaries to return.")
    app_server_threads_parser.set_defaults(command_id="codex.app_server.threads", target="codex")

    customer_mac_parser = subparsers.add_parser("customer-mac", help="Customer Mac connector commands.")
    customer_mac_subparsers = customer_mac_parser.add_subparsers(dest="customer_mac_command")

    mac_status_parser = customer_mac_subparsers.add_parser("status", help="Report customer Mac connector readiness.")
    mac_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    mac_status_parser.set_defaults(command_id="customer_mac.status", target="customer_mac")

    mac_capabilities_parser = customer_mac_subparsers.add_parser("capabilities", help="Report supported named customer Mac actions.")
    mac_capabilities_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    mac_capabilities_parser.set_defaults(command_id="customer_mac.capabilities", target="customer_mac")

    mac_snapshot_parser = customer_mac_subparsers.add_parser("snapshot", help="Capture a safe screenshot unless a sensitive app is frontmost.")
    mac_snapshot_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    mac_snapshot_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum visible text chars.")
    mac_snapshot_parser.set_defaults(command_id="customer_mac.snapshot", target="customer_mac")

    mac_ax_parser = customer_mac_subparsers.add_parser("ax-tree", help="Capture a capped Accessibility tree for the frontmost non-sensitive app.")
    mac_ax_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    mac_ax_parser.add_argument("--max-nodes", type=_positive_int, default=200, help="Maximum AX nodes to return.")
    mac_ax_parser.set_defaults(command_id="customer_mac.ax_tree", target="customer_mac")

    mac_focus_parser = customer_mac_subparsers.add_parser("app-focus", help="Focus a named non-sensitive Mac app.")
    mac_focus_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    mac_focus_parser.add_argument("--app-name", required=True, help="Visible macOS app name.")
    mac_focus_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without focusing.")
    mac_focus_parser.set_defaults(command_id="customer_mac.app_focus", target="customer_mac")

    local_site_parser = customer_mac_subparsers.add_parser("local-site", help="Customer-local website commands.")
    local_site_subparsers = local_site_parser.add_subparsers(dest="local_site_command")

    local_site_open_parser = local_site_subparsers.add_parser("open", help="Open a localhost, loopback, or .local website.")
    local_site_open_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    local_site_open_parser.add_argument("--url", required=True, help="Local website URL.")
    local_site_open_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without opening.")
    local_site_open_parser.set_defaults(command_id="customer_mac.local_site_open", target="customer_mac")

    local_site_action_parser = local_site_subparsers.add_parser("action", help="Run a named browser action against the frontmost local-site browser.")
    local_site_action_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    local_site_action_parser.add_argument("--action", required=True, choices=["reload", "back", "forward"], help="Named browser action.")
    local_site_action_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
    local_site_action_parser.set_defaults(command_id="customer_mac.local_site_action", target="customer_mac")

    iphone_parser = customer_mac_subparsers.add_parser("iphone-mirroring", help="Named iPhone Mirroring commands.")
    iphone_subparsers = iphone_parser.add_subparsers(dest="iphone_command")

    iphone_status_parser = iphone_subparsers.add_parser("status", help="Report iPhone Mirroring readiness and supported actions.")
    iphone_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_status_parser.set_defaults(command_id="customer_mac.iphone_mirroring_status", target="customer_mac")

    iphone_focus_parser = iphone_subparsers.add_parser("focus", help="Focus iPhone Mirroring.")
    iphone_focus_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_focus_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without focusing.")
    iphone_focus_parser.set_defaults(command_id="customer_mac.iphone_mirroring_focus", target="customer_mac")

    for subcommand, command_id, help_text in [
        ("home", "customer_mac.iphone_mirroring_home", "Send the iPhone Mirroring Home named action."),
        ("app-switcher", "customer_mac.iphone_mirroring_app_switcher", "Send the iPhone Mirroring App Switcher named action."),
        ("spotlight", "customer_mac.iphone_mirroring_spotlight", "Send the iPhone Mirroring Spotlight named action."),
        ("scroll", "customer_mac.iphone_mirroring_scroll", "Report that scroll is disabled pending evidence."),
    ]:
        parser_for_action = iphone_subparsers.add_parser(subcommand, help=help_text)
        parser_for_action.add_argument("--json", action="store_true", help="Emit JSON.")
        parser_for_action.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
        parser_for_action.set_defaults(command_id=command_id, target="customer_mac")

    iphone_type_parser = iphone_subparsers.add_parser("type-spotlight", help="Type short disposable/search text into iPhone Spotlight.")
    iphone_type_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_type_parser.add_argument("--text", required=True, help="Short disposable/search text.")
    iphone_type_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without typing.")
    iphone_type_parser.set_defaults(command_id="customer_mac.iphone_mirroring_type_spotlight", target="customer_mac")

    iphone_open_app_parser = iphone_subparsers.add_parser("open-app", help="Open a non-sensitive iPhone app through Spotlight.")
    iphone_open_app_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_open_app_parser.add_argument("--app-name", required=True, help="Non-sensitive iPhone app name.")
    iphone_open_app_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without opening.")
    iphone_open_app_parser.set_defaults(command_id="customer_mac.iphone_mirroring_open_app", target="customer_mac")

    iphone_tap_parser = iphone_subparsers.add_parser("tap-named-target", help="Press an exact visible iPhone Mirroring AX label.")
    iphone_tap_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_tap_parser.add_argument("--target-label", required=True, help="Exact visible target label.")
    iphone_tap_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without pressing.")
    iphone_tap_parser.set_defaults(command_id="customer_mac.iphone_mirroring_tap_named_target", target="customer_mac")

    screen_sharing_parser = customer_mac_subparsers.add_parser("screen-sharing", help="Screen Sharing/Remote Management status commands.")
    screen_sharing_subparsers = screen_sharing_parser.add_subparsers(dest="screen_sharing_command")
    screen_sharing_status_parser = screen_sharing_subparsers.add_parser("status", help="Report whether Screen Sharing is enabled.")
    screen_sharing_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    screen_sharing_status_parser.set_defaults(command_id="customer_mac.screen_sharing_status", target="customer_mac")

    return parser


def main(
    argv: list[str] | None = None,
    *,
    observer_factory: Callable[[], MacOSCodexObserver] | None = None,
    customer_mac_factory: Callable[[], CustomerMacObserver] | None = None,
    app_server_factory: Callable[[], CodexAppServerObserver] | None = None,
    session_factory: Callable[[], CodexSessionObserver] | None = None,
    acpx_factory: Callable[[], AcpxWorkerObserver] | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    state_dir: Path | None = None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if not hasattr(args, "command_id"):
        parser.print_help(stdout)
        return 0

    command_id = args.command_id
    target = args.target
    args.state_dir = state_dir
    try:
        ensure_allowed(command_id)
        observer = observer_factory() if observer_factory is not None else MacOSCodexObserver(state_dir=state_dir)
        customer_mac = customer_mac_factory() if customer_mac_factory is not None else CustomerMacObserver(state_dir=state_dir)
        app_server = app_server_factory() if app_server_factory is not None else CodexAppServerObserver()
        sessions = session_factory() if session_factory is not None else CodexSessionObserver()
        acpx = acpx_factory() if acpx_factory is not None else AcpxWorkerObserver()
        result = _run_command(command_id, observer, customer_mac, app_server, sessions, acpx, args)
    except PolicyError as exc:
        result = CommandResult(ok=False, errors=[exc.error])
    except Exception as exc:
        result = CommandResult(
            ok=False,
            errors=[
                {
                    "code": "command_failed",
                    "message": str(exc),
                    "guidance": "Rerun with the same command after checking local macOS permissions and bridge logs.",
                }
            ],
        )

    audit_id = append_audit(
        command=command_id,
        target=target,
        args={key: value for key, value in vars(args).items() if key not in {"command_id", "target", "state_dir"}},
        ok=result.ok,
        warnings=result.warnings,
        errors=result.errors,
        provenance={
            **command_metadata(command_id),
            **result.provenance,
            "dry_run": getattr(args, "dry_run", None),
            "selected_visible_target_id": getattr(args, "thread_id", None),
            "source_audit_id": getattr(args, "source_audit_id", None),
        },
        state_dir=state_dir,
    )
    envelope = build_envelope(
        command=command_id,
        target=target,
        ok=result.ok,
        data=result.data,
        warnings=result.warnings,
        errors=result.errors,
        audit_id=audit_id,
    )
    if command_id in LATEST_OBSERVATION_COMMANDS:
        write_latest(envelope, state_dir=state_dir)
    stdout.write(json.dumps(envelope, sort_keys=True) + "\n")
    return 0 if result.ok else 2


def entrypoint() -> None:
    raise SystemExit(main())


def _run_command(
    command_id: str,
    observer: MacOSCodexObserver,
    customer_mac: CustomerMacObserver,
    app_server: CodexAppServerObserver,
    sessions: CodexSessionObserver,
    acpx: AcpxWorkerObserver,
    args: argparse.Namespace,
) -> CommandResult:
    if command_id == "status":
        return observer.status()
    if command_id == "capabilities":
        return CommandResult(ok=True, data=_capabilities())
    if command_id == "latest":
        latest = read_latest(getattr(args, "state_dir", None))
        if latest is None:
            return CommandResult(
                ok=False,
                errors=[
                    {
                        "code": "latest_not_found",
                        "message": "No latest observation has been recorded yet.",
                        "guidance": "Run evaos-desktop-bridge status --json or a codex observer command first.",
                    }
                ],
            )
        return CommandResult(ok=True, data={"latest": latest})
    if command_id == "audit_tail":
        records = read_audit_tail(limit=args.limit, state_dir=getattr(args, "state_dir", None))
        return CommandResult(ok=True, data={"records": records, "count": len(records), "limit": args.limit}, provenance={"source": "audit"})
    if command_id == "queue.list":
        return list_queue_events(limit=args.limit, state_dir=getattr(args, "state_dir", None))
    if command_id == "queue.append":
        return append_queue_event(
            kind=args.kind,
            source_audit_id=args.source_audit_id,
            message=args.message,
            state_dir=getattr(args, "state_dir", None),
        )
    if command_id == "codex.frontmost":
        return observer.frontmost()
    if command_id == "codex.windows":
        return observer.windows()
    if command_id == "codex.threads":
        return observer.threads(max_items=args.max_items)
    if command_id == "codex.acpx_list":
        return acpx.list_workers(max_items=args.max_items)
    if command_id == "codex.acpx_show":
        return acpx.show_worker(name=args.session)
    if command_id == "codex.acpx_status":
        return acpx.status(name=args.session)
    if command_id == "codex.acpx_prompt":
        return acpx.prompt(message=args.message, name=args.session, no_wait=args.no_wait, dry_run=args.dry_run, max_chars=args.max_chars)
    if command_id == "codex.acpx_history":
        return acpx.history(name=args.session, limit=args.limit)
    if command_id == "codex.acpx_tail_events":
        return acpx.tail_events(record_id=args.record_id, max_events=args.max_events)
    if command_id == "codex.indexed_threads":
        return sessions.indexed_threads(max_items=args.max_items)
    if command_id == "codex.read_thread_tail":
        return sessions.read_thread_tail(thread_id=args.thread_id, max_events=args.max_events, max_chars=args.max_chars)
    if command_id == "codex.open_thread":
        return sessions.open_thread(thread_id=args.thread_id, dry_run=args.dry_run)
    if command_id == "codex.desktop_freshness":
        return sessions.desktop_freshness(thread_id=args.thread_id, visible_text=args.visible_text, max_events=args.max_events)
    if command_id == "codex.rehydrate_thread":
        return sessions.rehydrate_thread(thread_id=args.thread_id, dry_run=not args.live, wait_ms=args.wait_ms)
    if command_id == "codex.steer_thread":
        return sessions.steer_thread(thread_id=args.thread_id, message=args.message, dry_run=args.dry_run, timeout_seconds=args.timeout_seconds, max_chars=args.max_chars)
    if command_id == "codex.focus":
        return observer.focus(dry_run=args.dry_run)
    if command_id == "codex.menu_action":
        return observer.menu_action(menu=args.menu, item=args.item, dry_run=args.dry_run)
    if command_id == "codex.find_control":
        return observer.find_control(label=args.label, max_nodes=args.max_nodes)
    if command_id == "codex.press_control":
        return observer.press_control(label=args.label, dry_run=args.dry_run, max_nodes=args.max_nodes, match_index=args.match_index)
    if command_id == "codex.select_thread":
        return observer.select_thread(thread_id=args.thread_id, dry_run=args.dry_run)
    if command_id == "codex.snapshot":
        return observer.snapshot(max_chars=args.max_chars)
    if command_id == "codex.inspect":
        return observer.inspect(max_nodes=args.max_nodes)
    if command_id == "codex.ax_tree":
        return observer.ax_tree(max_nodes=args.max_nodes)
    if command_id == "codex.app_server.status":
        return app_server.status()
    if command_id == "codex.app_server.threads":
        return app_server.threads(max_items=args.max_items)
    if command_id == "customer_mac.status":
        return customer_mac.status()
    if command_id == "customer_mac.capabilities":
        return customer_mac.capabilities()
    if command_id == "customer_mac.snapshot":
        return customer_mac.snapshot(max_chars=args.max_chars)
    if command_id == "customer_mac.ax_tree":
        return customer_mac.ax_tree(max_nodes=args.max_nodes)
    if command_id == "customer_mac.app_focus":
        return customer_mac.app_focus(app_name=args.app_name, dry_run=args.dry_run)
    if command_id == "customer_mac.local_site_open":
        return customer_mac.local_site_open(url=args.url, dry_run=args.dry_run)
    if command_id == "customer_mac.local_site_action":
        return customer_mac.local_site_action(action=args.action, dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_status":
        return customer_mac.iphone_mirroring_status()
    if command_id == "customer_mac.iphone_mirroring_focus":
        return customer_mac.iphone_mirroring_focus(dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_home":
        return customer_mac.iphone_mirroring_action(action="home", dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_app_switcher":
        return customer_mac.iphone_mirroring_action(action="app_switcher", dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_spotlight":
        return customer_mac.iphone_mirroring_action(action="spotlight", dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_type_spotlight":
        return customer_mac.iphone_mirroring_action(action="type_spotlight", text=args.text, dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_open_app":
        return customer_mac.iphone_mirroring_action(action="open_app", app_name=args.app_name, dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_tap_named_target":
        return customer_mac.iphone_mirroring_action(action="tap_named_target", target_label=args.target_label, dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_scroll":
        return customer_mac.iphone_mirroring_action(action="scroll", dry_run=args.dry_run)
    if command_id == "customer_mac.screen_sharing_status":
        return customer_mac.screen_sharing_status()
    raise PolicyError(command_id)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def _capabilities() -> dict[str, object]:
    return {
        "modes": {
            "eyes": "Read-only visible desktop observation with redaction and caps.",
            "hands": "Guarded visible focus/select only; no typing, send controls, prompt sending, or session mutation.",
            "brain": "Local Eva/OpenClaw announcement queue contract with external relay left to future sinks.",
        },
        "commands": [
            {"id": command, "target": _target_for_command(command), **command_metadata(command)}
            for command in [
                "status",
                "capabilities",
                "latest",
                "audit_tail",
                "queue.list",
                "queue.append",
                "codex.frontmost",
                "codex.windows",
                "codex.threads",
                "codex.acpx_list",
        "codex.acpx_show",
        "codex.acpx_status",
        "codex.acpx_prompt",
        "codex.acpx_history",
        "codex.acpx_tail_events",
        "codex.indexed_threads",
                "codex.read_thread_tail",
                "codex.open_thread",
                "codex.desktop_freshness",
                "codex.rehydrate_thread",
                "codex.steer_thread",
                "codex.focus",
                "codex.menu_action",
                "codex.find_control",
                "codex.press_control",
                "codex.select_thread",
                "codex.snapshot",
                "codex.inspect",
                "codex.ax_tree",
                "codex.app_server.status",
                "codex.app_server.threads",
                "customer_mac.status",
                "customer_mac.capabilities",
                "customer_mac.snapshot",
                "customer_mac.ax_tree",
                "customer_mac.app_focus",
                "customer_mac.local_site_open",
                "customer_mac.local_site_action",
                "customer_mac.iphone_mirroring_status",
                "customer_mac.iphone_mirroring_focus",
                "customer_mac.iphone_mirroring_home",
                "customer_mac.iphone_mirroring_app_switcher",
                "customer_mac.iphone_mirroring_spotlight",
                "customer_mac.iphone_mirroring_type_spotlight",
                "customer_mac.iphone_mirroring_open_app",
                "customer_mac.iphone_mirroring_tap_named_target",
                "customer_mac.iphone_mirroring_scroll",
                "customer_mac.screen_sharing_status",
            ]
        ],
        "forbidden": [
            "send_prompts_or_messages",
            "type_into_codex",
            "click_codex_controls",
            "call_codex_internal_mutation_rpc",
            "hijack_stdio_or_file_descriptors",
            "read_session_databases_wholesale",
            "expose_tokens_auth_files_or_full_home_paths",
            "customer_mac_generic_remote_desktop",
            "customer_mac_generic_coordinates",
            "customer_mac_arbitrary_text",
            "customer_mac_sensitive_app_control",
            "customer_mac_screen_sharing_enablement",
        ],
        "data_minimization": {
            "redacts_home_paths": True,
            "redacts_secret_like_values": True,
            "caps_visible_text": True,
            "caps_ax_nodes": True,
            "skips_non_codex_screenshots": True,
            "append_only_audit_log": True,
        },
    }


def _target_for_command(command: str) -> str:
    if command.startswith("customer_mac."):
        return "customer_mac"
    if command.startswith("codex."):
        return "codex"
    if command.startswith("queue."):
        return "queue"
    return "desktop"


if __name__ == "__main__":
    entrypoint()
