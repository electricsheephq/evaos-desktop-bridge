from __future__ import annotations

import argparse
import hashlib
import io
import ipaddress
import json
import os
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, TextIO

from .adapters.codex_app_server import CodexAppServerObserver
from .adapters.codex_macos import MacOSCodexObserver
from .adapters.customer_mac import CustomerMacObserver
from .audit import append_audit, default_state_dir
from .bundled_tools import bundled_bridge_bin_candidates
from .connector_server import (
    build_diagnostics_payload,
    build_ready_payload,
    complete_enrollment_via_control,
    read_token,
    run_connector_server,
)
from .helper_ipc import HelperIpcError, UnixSocketHelperClient, default_helper_socket_path, read_helper_token, run_helper_server
from .policy import PolicyError, command_metadata, ensure_allowed
from .queue import append_queue_event, list_queue_events
from .redaction import redact_value
from .schema import build_envelope, make_error
from .state import approval_audit_freshness_error, read_audit_record, read_audit_tail, read_control_session, read_latest, write_latest
from .types import CommandResult

LATEST_OBSERVATION_COMMANDS = frozenset(
    {
        "status",
        "capabilities",
        "helper.ping",
        "codex.frontmost",
        "codex.windows",
        "codex.threads",
        "codex.thread_map",
        "codex.snapshot",
        "codex.inspect",
        "codex.ax_tree",
        "codex.connections.status",
        "codex.app_server.status",
        "codex.app_server.threads",
        "codex.app_server.loaded_threads",
        "codex.app_server.subscribe",
        "codex.app_server.remote_control_status",
        "customer_mac.status",
        "customer_mac.capabilities",
        "customer_mac.control_status",
        "customer_mac.desktop_see",
        "customer_mac.iphone_see",
        "customer_mac.snapshot",
        "customer_mac.ax_tree",
        "customer_mac.iphone_mirroring_status",
        "customer_mac.screen_sharing_status",
    }
)

INLINE_SCREENSHOT_BYTES_OMITTED_REASON = (
    "inline screenshot bytes omitted from CLI JSON by default; "
    "rerun the visual command with --include-screenshot-bytes to include them"
)

GUARDED_APPROVAL_FIELDS: dict[str, tuple[str, ...]] = {
    "codex.select_thread": ("thread_id",),
    "codex.send_visible_message": ("thread_id", "message_hash"),
    "codex.continue_thread": ("title", "prompt"),
    "customer_mac.app_focus": ("app_name",),
    "customer_mac.local_site_open": ("url",),
    "customer_mac.local_site_action": ("action",),
    "customer_mac.iphone_mirroring_focus": (),
    "customer_mac.iphone_mirroring_home": (),
    "customer_mac.iphone_mirroring_app_switcher": (),
    "customer_mac.iphone_mirroring_spotlight": (),
    "customer_mac.iphone_mirroring_type_spotlight": ("text",),
    "customer_mac.iphone_mirroring_open_app": ("app_name",),
    "customer_mac.iphone_mirroring_tap_named_target": ("target_label",),
    "customer_mac.iphone_mirroring_scroll": ("direction",),
    "customer_mac.iphone_mirroring_swipe_left": (),
    "customer_mac.iphone_mirroring_swipe_right": (),
    "customer_mac.iphone_mirroring_swipe_up": (),
    "customer_mac.iphone_mirroring_swipe_down": (),
    "customer_mac.iphone_mirroring_type_approved_text": ("text",),
    "customer_mac.iphone_mirroring_send_approved_message": ("text", "recipient_context", "target_label"),
    "customer_mac.desktop_click": ("snapshot_id", "element_id", "target_label", "x", "y"),
    "customer_mac.desktop_type": ("text",),
    "customer_mac.desktop_set_value": ("snapshot_id", "element_id", "attribute", "value_hash"),
    "customer_mac.desktop_scroll": ("direction", "amount"),
    "customer_mac.desktop_drag": ("from_x", "from_y", "to_x", "to_y"),
    "customer_mac.desktop_hotkey": ("keys",),
    "customer_mac.desktop_focus_app": ("app_name",),
    "customer_mac.desktop_window": ("action",),
    "customer_mac.desktop_menu": ("menu_path",),
    "customer_mac.desktop_browser_action": ("action", "url"),
    "customer_mac.iphone_tap": ("snapshot_id", "element_id", "target_label", "x", "y"),
    "customer_mac.iphone_swipe": ("direction",),
    "customer_mac.iphone_type": ("text",),
}

CODEX_SOURCE_AUDIT_FIELDS: dict[str, tuple[str, ...]] = {}

CONTROL_SESSION_COMMANDS = frozenset(
    {
        "customer_mac.control_start",
        "customer_mac.control_stop",
        "customer_mac.control_kill_switch",
    }
)

CONTROLLED_LIVE_COMMANDS = frozenset(
    {
        "customer_mac.iphone_mirroring_focus",
        "customer_mac.iphone_mirroring_home",
        "customer_mac.iphone_mirroring_app_switcher",
        "customer_mac.iphone_mirroring_spotlight",
        "customer_mac.iphone_mirroring_type_spotlight",
        "customer_mac.iphone_mirroring_open_app",
        "customer_mac.iphone_mirroring_tap_named_target",
        "customer_mac.iphone_mirroring_scroll",
        "customer_mac.iphone_mirroring_swipe_left",
        "customer_mac.iphone_mirroring_swipe_right",
        "customer_mac.iphone_mirroring_swipe_up",
        "customer_mac.iphone_mirroring_swipe_down",
        "customer_mac.iphone_mirroring_type_approved_text",
        "customer_mac.iphone_mirroring_send_approved_message",
        "customer_mac.desktop_click",
        "customer_mac.desktop_type",
        "customer_mac.desktop_set_value",
        "customer_mac.desktop_scroll",
        "customer_mac.desktop_drag",
        "customer_mac.desktop_hotkey",
        "customer_mac.desktop_focus_app",
        "customer_mac.desktop_window",
        "customer_mac.desktop_menu",
        "customer_mac.desktop_browser_action",
        "customer_mac.iphone_tap",
        "customer_mac.iphone_swipe",
        "customer_mac.iphone_type",
    }
)

TAKEOVER_WARNING_GATED_COMMANDS = CONTROLLED_LIVE_COMMANDS | frozenset(
    {
        "customer_mac.app_focus",
        "customer_mac.local_site_open",
        "customer_mac.local_site_action",
    }
)

ASK_PERMISSION_HIGH_IMPACT_COMMANDS = frozenset(
    {
        "customer_mac.iphone_mirroring_swipe_left",
        "customer_mac.iphone_mirroring_swipe_right",
        "customer_mac.iphone_mirroring_swipe_up",
        "customer_mac.iphone_mirroring_swipe_down",
        "customer_mac.iphone_mirroring_type_approved_text",
        "customer_mac.iphone_mirroring_send_approved_message",
        "customer_mac.desktop_type",
        "customer_mac.desktop_set_value",
        "customer_mac.iphone_swipe",
        "customer_mac.iphone_type",
    }
)

ASK_PERMISSION_RISK_WORDS = frozenset(
    {
        "approve",
        "buy",
        "confirm",
        "delete",
        "dispatch",
        "like",
        "match",
        "pay",
        "post",
        "purchase",
        "remove",
        "send",
        "submit",
        "transfer",
        "unlike",
    }
)

ASK_PERMISSION_SAFE_HOTKEYS = frozenset(
    {
        "cmd+[",
        "cmd+]",
        "cmd+l",
        "cmd+r",
        "cmd+t",
        "escape",
        "tab",
    }
)


def _add_remote_control_flags(parser: argparse.ArgumentParser) -> None:
    dry_run_group = parser.add_mutually_exclusive_group()
    dry_run_group.add_argument("--dry-run", dest="dry_run", action="store_true", default=True, help="Report what would happen without mutating Codex Desktop.")
    dry_run_group.add_argument("--live", dest="dry_run", action="store_false", help="Run the approved Codex Desktop remote-control action.")
    parser.add_argument("--confirm", action="store_true", help="Required with --live.")
    parser.add_argument("--source-audit-id", default=None, help="Audit id from the evidence/dry-run command that approved this live action.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaos-desktop-bridge",
        description="evaOS Workbench connector for audited Mac and iPhone agent control.",
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

    diagnostics_parser = subparsers.add_parser("diagnostics", help="Return redacted connector diagnostics for support.")
    diagnostics_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    diagnostics_parser.add_argument(
        "--token-file",
        default=None,
        help="Optional connector token file. Defaults to the bridge state directory when present.",
    )
    diagnostics_parser.set_defaults(command_id="diagnostics", target="connector")

    ready_parser = subparsers.add_parser(
        "ready",
        help="Return connector readiness for release proof and support diagnostics.",
    )
    ready_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    ready_parser.add_argument(
        "--token-file",
        default=None,
        help="Optional connector token file. Defaults to the bridge state directory when present.",
    )
    ready_parser.set_defaults(command_id="ready", target="connector")

    audit_parser = subparsers.add_parser("audit-tail", help="Return a redacted tail of the local audit log.")
    audit_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    audit_parser.add_argument("--limit", type=_positive_int, default=20, help="Maximum audit records to return.")
    audit_parser.set_defaults(command_id="audit_tail", target="desktop")

    permissions_parser = subparsers.add_parser("permissions", help="Prime macOS permission prompts for the bridge helper.")
    permissions_subparsers = permissions_parser.add_subparsers(dest="permissions_command")

    permissions_prime_parser = permissions_subparsers.add_parser("prime", help="Request or check a macOS permission from the bridge helper process.")
    permissions_prime_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    permissions_prime_parser.add_argument("--permission", required=True, choices=["accessibility", "screen-recording"], help="Permission to request/check.")
    permissions_prime_parser.set_defaults(command_id="permissions.prime", target="desktop")

    helper_parser = subparsers.add_parser("helper", help="Run or inspect the local persistent computer-use helper.")
    helper_subparsers = helper_parser.add_subparsers(dest="helper_command")
    helper_run_parser = helper_subparsers.add_parser("run", help="Run the local Unix-socket computer-use helper daemon.")
    helper_run_parser.add_argument("--socket-path", default=None, help="Unix socket path. Defaults to /tmp/evaos-helper-<uid>.sock.")
    helper_run_parser.add_argument("--token-file", default=None, help="Capability-token file. Defaults to the bridge state directory.")
    helper_run_parser.set_defaults(command_id="helper.run", target="computer_use_helper")
    helper_ping_parser = helper_subparsers.add_parser("ping", help="Ping the local persistent computer-use helper.")
    helper_ping_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    helper_ping_parser.add_argument("--socket-path", default=None, help="Unix socket path. Defaults to /tmp/evaos-helper-<uid>.sock.")
    helper_ping_parser.add_argument("--token-file", default=None, help="Capability-token file. Defaults to the bridge state directory.")
    helper_ping_parser.set_defaults(command_id="helper.ping", target="computer_use_helper")

    serve_parser = subparsers.add_parser("serve", help="Run the token-gated customer Mac connector HTTP server.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host. Prefer loopback or the paired Headscale interface.")
    serve_parser.add_argument("--port", type=_positive_int, default=8765, help="Bind port.")
    serve_parser.add_argument(
        "--token-file",
        default=None,
        help="File containing the connector bearer token. Defaults to a per-user Application Support token.",
    )
    serve_parser.set_defaults(command_id="serve", target="connector")

    service_parser = subparsers.add_parser("connector-service", help="Manage the local LaunchAgent-backed connector service.")
    service_subparsers = service_parser.add_subparsers(dest="connector_service_command")

    for service_command, help_text in [
        ("status", "Report LaunchAgent, token, and loopback health status."),
        ("start", "Start or kick the LaunchAgent-backed connector."),
        ("stop", "Stop the LaunchAgent-backed connector."),
    ]:
        service_action = service_subparsers.add_parser(service_command, help=help_text)
        service_action.add_argument("--json", action="store_true", help="Emit JSON.")
        service_action.set_defaults(command_id=f"connector_service.{service_command}", target="connector")

    service_complete_parser = service_subparsers.add_parser(
        "complete-enrollment",
        help="Privately register the local connector with the broker for a Workbench pairing code.",
    )
    service_complete_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    service_complete_parser.add_argument("--enrollment-code", required=True, help="Short-lived Workbench pairing code.")
    service_complete_parser.add_argument("--customer-id", required=True, help="Customer id for the selected Workbench customer.")
    service_complete_parser.add_argument("--device-name", default=None, help="Friendly Mac device name.")
    service_complete_parser.set_defaults(command_id="connector_service.complete_enrollment", target="connector")

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

    thread_map_parser = codex_subparsers.add_parser("thread-map", help="Join visible Codex GUI thread candidates with read-only app-server thread summaries.")
    thread_map_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    thread_map_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum visible/app-server thread candidates to return.")
    thread_map_parser.set_defaults(command_id="codex.thread_map", target="codex")

    focus_parser = codex_subparsers.add_parser("focus", help="Focus the visible Codex Desktop app.")
    focus_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    focus_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without focusing.")
    focus_parser.set_defaults(command_id="codex.focus", target="codex")

    select_parser = codex_subparsers.add_parser("select-thread", help="Select an already-visible Codex Desktop thread candidate.")
    select_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    select_parser.add_argument("--thread-id", required=True, help="Visible thread id from codex threads output.")
    select_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without clicking/selecting.")
    select_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    select_parser.set_defaults(command_id="codex.select_thread", target="codex")

    send_visible_parser = codex_subparsers.add_parser("send-visible-message", help="Guarded visible GUI action: send an approved message through the frontmost Codex Desktop composer.")
    send_visible_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    send_visible_parser.add_argument("--thread-id", required=True, help="Visible thread id from codex threads/thread-map output.")
    send_visible_message_group = send_visible_parser.add_mutually_exclusive_group(required=True)
    send_visible_message_group.add_argument("--message", default=None, help="Approved message text to send through the visible Codex composer.")
    send_visible_message_group.add_argument("--message-file", default=None, help="Path to a UTF-8 file containing the approved message; preferred for plugin/connector wrappers.")
    send_visible_group = send_visible_parser.add_mutually_exclusive_group()
    send_visible_group.add_argument("--dry-run", dest="dry_run", action="store_true", default=True, help="Report what would happen without typing or submitting.")
    send_visible_group.add_argument("--live", dest="dry_run", action="store_false", help="Type and submit the approved message after matching dry-run approval.")
    send_visible_parser.add_argument("--confirm", action="store_true", help="Required with --live.")
    send_visible_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    send_visible_parser.add_argument("--wait-ms", type=_nonnegative_int, default=0, help="After a live send, poll read-only visible state for up to this many milliseconds.")
    send_visible_parser.add_argument("--poll-interval-ms", type=_positive_int, default=2000, help="Read-only post-send poll interval in milliseconds.")
    send_visible_parser.set_defaults(command_id="codex.send_visible_message", target="codex")

    continue_parser = codex_subparsers.add_parser("continue-thread", help="Support-only visible fallback: select a visible Codex thread by title and submit the exact prompt 'continue'.")
    continue_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    continue_parser.add_argument("--title", required=True, help="Visible Codex thread title query, for example SDK Docs.")
    continue_parser.add_argument("--prompt", default="continue", help="Must be exactly 'continue'.")
    continue_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without selecting/submitting.")
    continue_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    continue_parser.set_defaults(command_id="codex.continue_thread", target="codex")

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

    connections_parser = codex_subparsers.add_parser("connections", help="Codex Desktop native connection/status commands.")
    connections_subparsers = connections_parser.add_subparsers(dest="connections_command")

    connections_status_parser = connections_subparsers.add_parser("status", help="Report Codex Desktop, app-server, remote-control, websocket, and notification readiness.")
    connections_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    connections_status_parser.set_defaults(command_id="codex.connections.status", target="codex")

    app_server_parser = codex_subparsers.add_parser("app-server", help="Read-only Codex app-server seam commands.")
    app_server_subparsers = app_server_parser.add_subparsers(dest="app_server_command")

    app_server_status_parser = app_server_subparsers.add_parser("status", help="Report read-only app-server availability and allowlist.")
    app_server_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_status_parser.set_defaults(command_id="codex.app_server.status", target="codex")

    app_server_threads_parser = app_server_subparsers.add_parser("threads", help="Read Codex threads through the app-server read allowlist.")
    app_server_threads_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_threads_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum app-server thread summaries to return.")
    app_server_threads_parser.set_defaults(command_id="codex.app_server.threads", target="codex")

    app_server_loaded_parser = app_server_subparsers.add_parser("loaded-threads", help="Read Codex Desktop's currently loaded app-server thread ids.")
    app_server_loaded_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_loaded_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum loaded thread ids to return.")
    app_server_loaded_parser.set_defaults(command_id="codex.app_server.loaded_threads", target="codex")

    app_server_subscribe_parser = app_server_subparsers.add_parser("subscribe", help="Read buffered Codex app-server notifications for a loaded thread.")
    app_server_subscribe_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_subscribe_parser.add_argument("--thread-id", required=True, help="Loaded Codex app-server thread id.")
    app_server_subscribe_parser.add_argument("--duration-ms", type=_positive_int, default=1000, help="How long to buffer notifications.")
    app_server_subscribe_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum JSON chars per notification payload.")
    app_server_subscribe_parser.set_defaults(command_id="codex.app_server.subscribe", target="codex")

    app_server_remote_parser = app_server_subparsers.add_parser("remote-control-status", help="Probe Codex native remote-control readiness without enabling or mutating it.")
    app_server_remote_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_remote_parser.set_defaults(command_id="codex.app_server.remote_control_status", target="codex")

    customer_mac_parser = subparsers.add_parser("customer-mac", help="Customer Mac connector commands.")
    customer_mac_subparsers = customer_mac_parser.add_subparsers(dest="customer_mac_command")

    mac_status_parser = customer_mac_subparsers.add_parser("status", help="Report customer Mac connector readiness.")
    mac_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    mac_status_parser.set_defaults(command_id="customer_mac.status", target="customer_mac")

    mac_capabilities_parser = customer_mac_subparsers.add_parser("capabilities", help="Report supported named customer Mac actions.")
    mac_capabilities_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    mac_capabilities_parser.set_defaults(command_id="customer_mac.capabilities", target="customer_mac")

    control_parser = customer_mac_subparsers.add_parser("control", help="Manage customer-granted agent control sessions.")
    control_subparsers = control_parser.add_subparsers(dest="control_command")

    control_status_parser = control_subparsers.add_parser("status", help="Report Full Access / Ask Permission session state.")
    control_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    control_status_parser.set_defaults(command_id="customer_mac.control_status", target="customer_mac")

    control_start_parser = control_subparsers.add_parser("start", help="Start a customer-granted agent control session.")
    control_start_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    control_start_parser.add_argument("--mode", choices=["full-access", "ask-permission"], default="full-access", help="Control mode for this session.")
    control_start_parser.add_argument("--agent-label", default=None, help="Human-readable current agent label.")
    control_start_parser.set_defaults(command_id="customer_mac.control_start", target="customer_mac")

    control_stop_parser = control_subparsers.add_parser("stop", help="Stop the active agent control session.")
    control_stop_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    control_stop_parser.set_defaults(command_id="customer_mac.control_stop", target="customer_mac")

    control_kill_parser = control_subparsers.add_parser("kill-switch", help="Immediately stop and block future connector control commands.")
    control_kill_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    control_kill_parser.set_defaults(command_id="customer_mac.control_kill_switch", target="customer_mac")

    desktop_parser = customer_mac_subparsers.add_parser("desktop", help="Full-access desktop computer-control commands.")
    desktop_subparsers = desktop_parser.add_subparsers(dest="desktop_command")

    desktop_see_parser = desktop_subparsers.add_parser("see", help="See the current desktop through Peekaboo or fallback screen/AX capture.")
    desktop_see_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_see_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum visible text chars.")
    desktop_see_parser.add_argument("--max-nodes", type=_positive_int, default=200, help="Maximum AX nodes.")
    desktop_see_parser.add_argument(
        "--include-screenshot-bytes",
        action="store_true",
        help="Opt in to inline screenshot bytes in JSON output.",
    )
    desktop_see_parser.set_defaults(command_id="customer_mac.desktop_see", target="customer_mac")

    desktop_click_parser = desktop_subparsers.add_parser("click", help="Click a visible target label or x/y point.")
    desktop_click_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_click_parser.add_argument("--target-label", default=None, help="Visible target label to click.")
    desktop_click_parser.add_argument("--snapshot-id", default=None, help="Snapshot id returned by desktop_see.")
    desktop_click_parser.add_argument("--element-id", default=None, help="Element id returned by desktop_see.")
    desktop_click_parser.add_argument("--x", type=int, default=None, help="Screen x coordinate fallback.")
    desktop_click_parser.add_argument("--y", type=int, default=None, help="Screen y coordinate fallback.")
    desktop_click_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without clicking.")
    desktop_click_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    desktop_click_parser.set_defaults(command_id="customer_mac.desktop_click", target="customer_mac")

    desktop_type_parser = desktop_subparsers.add_parser("type", help="Type exact text into the focused field.")
    desktop_type_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_type_parser.add_argument("--text", required=True, help="Exact text to type.")
    desktop_type_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without typing.")
    desktop_type_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode.")
    desktop_type_parser.set_defaults(command_id="customer_mac.desktop_type", target="customer_mac")

    desktop_set_value_parser = desktop_subparsers.add_parser("set-value", help="Set an AX-backed native text field from a fresh desktop_see snapshot.")
    desktop_set_value_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_set_value_parser.add_argument("--snapshot-id", required=True, help="Snapshot id returned by desktop_see.")
    desktop_set_value_parser.add_argument("--element-id", required=True, help="AX element id returned by desktop_see.")
    desktop_set_value_group = desktop_set_value_parser.add_mutually_exclusive_group(required=True)
    desktop_set_value_group.add_argument("--value", help="Exact value to set; secrets and secure fields are blocked.")
    desktop_set_value_group.add_argument("--value-file", help="Path to a UTF-8 file containing the exact value to set.")
    desktop_set_value_parser.add_argument("--attribute", choices=["value", "selected_text"], default="value", help="Fixed AX attribute setter.")
    desktop_set_value_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without setting text.")
    desktop_set_value_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode.")
    desktop_set_value_parser.set_defaults(command_id="customer_mac.desktop_set_value", target="customer_mac")

    desktop_scroll_parser = desktop_subparsers.add_parser("scroll", help="Scroll the focused surface.")
    desktop_scroll_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_scroll_parser.add_argument("--direction", choices=["up", "down", "left", "right"], default="down", help="Scroll direction.")
    desktop_scroll_parser.add_argument("--amount", type=_positive_int, default=600, help="Scroll amount.")
    desktop_scroll_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without scrolling.")
    desktop_scroll_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    desktop_scroll_parser.set_defaults(command_id="customer_mac.desktop_scroll", target="customer_mac")

    desktop_drag_parser = desktop_subparsers.add_parser("drag", help="Drag from one point to another.")
    desktop_drag_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_drag_parser.add_argument("--from-x", type=int, required=True, help="Start x coordinate.")
    desktop_drag_parser.add_argument("--from-y", type=int, required=True, help="Start y coordinate.")
    desktop_drag_parser.add_argument("--to-x", type=int, required=True, help="End x coordinate.")
    desktop_drag_parser.add_argument("--to-y", type=int, required=True, help="End y coordinate.")
    desktop_drag_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without dragging.")
    desktop_drag_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    desktop_drag_parser.set_defaults(command_id="customer_mac.desktop_drag", target="customer_mac")

    desktop_hotkey_parser = desktop_subparsers.add_parser("hotkey", help="Press a hotkey such as cmd+l.")
    desktop_hotkey_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_hotkey_parser.add_argument("--keys", required=True, help="Plus-delimited keys, for example cmd+l.")
    desktop_hotkey_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without pressing.")
    desktop_hotkey_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    desktop_hotkey_parser.set_defaults(command_id="customer_mac.desktop_hotkey", target="customer_mac")

    desktop_focus_parser = desktop_subparsers.add_parser("focus-app", help="Focus a Mac app by name.")
    desktop_focus_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_focus_parser.add_argument("--app-name", required=True, help="Visible macOS app name.")
    desktop_focus_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without focusing.")
    desktop_focus_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    desktop_focus_parser.set_defaults(command_id="customer_mac.desktop_focus_app", target="customer_mac")

    desktop_window_parser = desktop_subparsers.add_parser("window", help="Perform a named window action.")
    desktop_window_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_window_parser.add_argument("--action", choices=["focus", "minimize", "maximize", "zoom", "close"], required=True, help="Window action.")
    desktop_window_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
    desktop_window_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    desktop_window_parser.set_defaults(command_id="customer_mac.desktop_window", target="customer_mac")

    desktop_menu_parser = desktop_subparsers.add_parser("menu", help="Choose a visible menu path through Peekaboo.")
    desktop_menu_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_menu_parser.add_argument("--menu-path", required=True, help="Menu path, for example File > New Tab.")
    desktop_menu_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
    desktop_menu_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    desktop_menu_parser.set_defaults(command_id="customer_mac.desktop_menu", target="customer_mac")

    desktop_browser_parser = desktop_subparsers.add_parser("browser-action", help="Perform a browser action on the focused Mac browser.")
    desktop_browser_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    desktop_browser_parser.add_argument("--action", choices=["reload", "back", "forward", "new_tab", "open_url"], required=True, help="Browser action.")
    desktop_browser_parser.add_argument("--url", default=None, help="URL for open_url.")
    desktop_browser_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
    desktop_browser_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    desktop_browser_parser.set_defaults(command_id="customer_mac.desktop_browser_action", target="customer_mac")

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
    mac_focus_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    mac_focus_parser.set_defaults(command_id="customer_mac.app_focus", target="customer_mac")

    local_site_parser = customer_mac_subparsers.add_parser("local-site", help="Customer-local website commands.")
    local_site_subparsers = local_site_parser.add_subparsers(dest="local_site_command")

    local_site_open_parser = local_site_subparsers.add_parser("open", help="Open a localhost, loopback, or .local website.")
    local_site_open_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    local_site_open_parser.add_argument("--url", required=True, help="Local website URL.")
    local_site_open_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without opening.")
    local_site_open_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    local_site_open_parser.set_defaults(command_id="customer_mac.local_site_open", target="customer_mac")

    local_site_action_parser = local_site_subparsers.add_parser("action", help="Run a named browser action against the frontmost local-site browser.")
    local_site_action_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    local_site_action_parser.add_argument("--action", required=True, choices=["reload", "back", "forward"], help="Named browser action.")
    local_site_action_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
    local_site_action_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    local_site_action_parser.set_defaults(command_id="customer_mac.local_site_action", target="customer_mac")

    iphone_parser = customer_mac_subparsers.add_parser("iphone-mirroring", help="Named iPhone Mirroring commands.")
    iphone_subparsers = iphone_parser.add_subparsers(dest="iphone_command")

    iphone_status_parser = iphone_subparsers.add_parser("status", help="Report iPhone Mirroring readiness and supported actions.")
    iphone_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_status_parser.set_defaults(command_id="customer_mac.iphone_mirroring_status", target="customer_mac")

    iphone_see_parser = iphone_subparsers.add_parser("see", help="See the visible iPhone Mirroring surface.")
    iphone_see_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_see_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum visible text chars.")
    iphone_see_parser.add_argument("--max-nodes", type=_positive_int, default=200, help="Maximum AX nodes.")
    iphone_see_parser.add_argument(
        "--include-screenshot-bytes",
        action="store_true",
        help="Opt in to inline screenshot bytes in JSON output.",
    )
    iphone_see_parser.set_defaults(command_id="customer_mac.iphone_see", target="customer_mac")

    iphone_tap_v2_parser = iphone_subparsers.add_parser("tap", help="Tap/click a visible iPhone label or fallback point.")
    iphone_tap_v2_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_tap_v2_parser.add_argument("--target-label", default=None, help="Visible target label.")
    iphone_tap_v2_parser.add_argument("--snapshot-id", default=None, help="Snapshot id returned by iphone_see.")
    iphone_tap_v2_parser.add_argument("--element-id", default=None, help="Element id returned by iphone_see.")
    iphone_tap_v2_parser.add_argument("--x", type=int, default=None, help="Screen x coordinate fallback.")
    iphone_tap_v2_parser.add_argument("--y", type=int, default=None, help="Screen y coordinate fallback.")
    iphone_tap_v2_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without tapping.")
    iphone_tap_v2_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    iphone_tap_v2_parser.set_defaults(command_id="customer_mac.iphone_tap", target="customer_mac")

    iphone_swipe_v2_parser = iphone_subparsers.add_parser("swipe", help="Swipe the focused iPhone Mirroring window.")
    iphone_swipe_v2_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_swipe_v2_parser.add_argument("--direction", choices=["left", "right", "up", "down"], required=True, help="Swipe direction.")
    iphone_swipe_v2_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without swiping.")
    iphone_swipe_v2_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode for high-impact actions.")
    iphone_swipe_v2_parser.set_defaults(command_id="customer_mac.iphone_swipe", target="customer_mac")

    iphone_type_v2_parser = iphone_subparsers.add_parser("type", help="Type text into the focused iPhone Mirroring field.")
    iphone_type_v2_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_type_v2_parser.add_argument("--text", required=True, help="Exact text to type.")
    iphone_type_v2_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without typing.")
    iphone_type_v2_parser.add_argument("--approval-audit-id", default=None, help="Dry-run audit id required in Ask Permission mode.")
    iphone_type_v2_parser.set_defaults(command_id="customer_mac.iphone_type", target="customer_mac")

    iphone_focus_parser = iphone_subparsers.add_parser("focus", help="Focus iPhone Mirroring.")
    iphone_focus_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_focus_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without focusing.")
    iphone_focus_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    iphone_focus_parser.set_defaults(command_id="customer_mac.iphone_mirroring_focus", target="customer_mac")

    for subcommand, command_id, help_text in [
        ("home", "customer_mac.iphone_mirroring_home", "Send the iPhone Mirroring Home named action."),
        ("app-switcher", "customer_mac.iphone_mirroring_app_switcher", "Send the iPhone Mirroring App Switcher named action."),
        ("spotlight", "customer_mac.iphone_mirroring_spotlight", "Send the iPhone Mirroring Spotlight named action."),
    ]:
        parser_for_action = iphone_subparsers.add_parser(subcommand, help=help_text)
        parser_for_action.add_argument("--json", action="store_true", help="Emit JSON.")
        parser_for_action.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
        parser_for_action.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
        parser_for_action.set_defaults(command_id=command_id, target="customer_mac")

    iphone_scroll_parser = iphone_subparsers.add_parser("scroll", help="Approval-gated action: scroll the focused iPhone Mirroring window by named direction.")
    iphone_scroll_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_scroll_parser.add_argument("--direction", choices=["up", "down"], default="down", help="Named scroll direction.")
    iphone_scroll_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
    iphone_scroll_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    iphone_scroll_parser.set_defaults(command_id="customer_mac.iphone_mirroring_scroll", target="customer_mac")

    for subcommand, command_id, help_text in [
        ("swipe-left", "customer_mac.iphone_mirroring_swipe_left", "Approval-gated action: swipe left in the focused iPhone Mirroring window."),
        ("swipe-right", "customer_mac.iphone_mirroring_swipe_right", "Approval-gated action: swipe right in the focused iPhone Mirroring window."),
        ("swipe-up", "customer_mac.iphone_mirroring_swipe_up", "Approval-gated action: swipe up in the focused iPhone Mirroring window."),
        ("swipe-down", "customer_mac.iphone_mirroring_swipe_down", "Approval-gated action: swipe down in the focused iPhone Mirroring window."),
    ]:
        swipe_parser = iphone_subparsers.add_parser(subcommand, help=help_text)
        swipe_parser.add_argument("--json", action="store_true", help="Emit JSON.")
        swipe_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without acting.")
        swipe_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
        swipe_parser.set_defaults(command_id=command_id, target="customer_mac")

    iphone_type_parser = iphone_subparsers.add_parser("type-spotlight", help="Type short disposable/search text into iPhone Spotlight.")
    iphone_type_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_type_parser.add_argument("--text", required=True, help="Short disposable/search text.")
    iphone_type_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without typing.")
    iphone_type_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    iphone_type_parser.set_defaults(command_id="customer_mac.iphone_mirroring_type_spotlight", target="customer_mac")

    iphone_open_app_parser = iphone_subparsers.add_parser("open-app", help="Open a non-sensitive iPhone app through Spotlight.")
    iphone_open_app_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_open_app_parser.add_argument("--app-name", required=True, help="Non-sensitive iPhone app name.")
    iphone_open_app_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without opening.")
    iphone_open_app_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    iphone_open_app_parser.set_defaults(command_id="customer_mac.iphone_mirroring_open_app", target="customer_mac")

    iphone_tap_parser = iphone_subparsers.add_parser("tap-named-target", help="Press an exact visible iPhone Mirroring AX label.")
    iphone_tap_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_tap_parser.add_argument("--target-label", required=True, help="Exact visible target label.")
    iphone_tap_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without pressing.")
    iphone_tap_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    iphone_tap_parser.set_defaults(command_id="customer_mac.iphone_mirroring_tap_named_target", target="customer_mac")

    iphone_type_approved_parser = iphone_subparsers.add_parser("type-approved-text", help="Approval-gated action: type exact same-turn-approved text into the focused iPhone Mirroring window.")
    iphone_type_approved_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_type_approved_parser.add_argument("--text", required=True, help="Exact same-turn-approved text, capped at 240 chars.")
    iphone_type_approved_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without typing.")
    iphone_type_approved_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    iphone_type_approved_parser.set_defaults(command_id="customer_mac.iphone_mirroring_type_approved_text", target="customer_mac")

    iphone_send_parser = iphone_subparsers.add_parser("send-approved-message", help="Full Access action: type and send one exact message through visible iPhone Mirroring; Ask Permission gates it.")
    iphone_send_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    iphone_send_parser.add_argument("--text", required=True, help="Exact same-turn-approved message text, capped at 240 chars.")
    iphone_send_parser.add_argument("--recipient-context", required=True, help="Short human-approved recipient/context for audit evidence.")
    iphone_send_parser.add_argument("--target-label", default="Send", help="Exact visible send control label.")
    iphone_send_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without sending.")
    iphone_send_parser.add_argument("--approval-audit-id", default=None, help="Audit id from the approving dry-run/evidence record.")
    iphone_send_parser.set_defaults(command_id="customer_mac.iphone_mirroring_send_approved_message", target="customer_mac")

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
    if command_id == "serve":
        token = read_token(args.token_file, state_dir=state_dir, auto_create=True)
        run_connector_server(
            host=args.host,
            port=args.port,
            token=token,
            command_runner=lambda bridge_argv: _run_bridge_argv(bridge_argv, state_dir=state_dir),
            state_dir=state_dir,
            owner_provider=_connector_http_owner_summary,
        )
        return 0

    if command_id == "diagnostics":
        token = _read_connector_token_optional(args.token_file, state_dir=state_dir)
        result = _build_cli_diagnostics_payload(token=token, token_file=args.token_file, state_dir=state_dir)
        if getattr(args, "json", None) is True:
            stdout.write(json.dumps(redact_value(result), sort_keys=True) + "\n")
        else:
            ready = result.get("connector", {}).get("ready", {}) if isinstance(result.get("connector"), dict) else {}
            status = "ready" if ready.get("ok") is True else "not ready"
            stdout.write(f"evaOS desktop bridge diagnostics: {status}\n")
            blockers = ready.get("blockers") if isinstance(ready.get("blockers"), list) else []
            for blocker in blockers:
                if isinstance(blocker, dict):
                    stdout.write(f"- {blocker.get('code') or 'unknown'}: {blocker.get('message') or ''}\n")
        return 0

    if command_id == "ready":
        token = _read_connector_token_optional(args.token_file, state_dir=state_dir)
        result = _build_cli_ready_payload(token=token, token_file=args.token_file, state_dir=state_dir)
        if getattr(args, "json", None) is True:
            stdout.write(json.dumps(redact_value(result), sort_keys=True) + "\n")
        else:
            status = "ready" if result.get("ok") is True else "not ready"
            stdout.write(f"evaOS desktop bridge connector: {status}\n")
            blockers = result.get("blockers") if isinstance(result.get("blockers"), list) else []
            for blocker in blockers:
                if isinstance(blocker, dict):
                    stdout.write(f"- {blocker.get('code') or 'unknown'}: {blocker.get('message') or ''}\n")
        return 0 if result.get("ok") is True else 2

    if command_id == "helper.run":
        token = read_helper_token(token_file=args.token_file, state_dir=state_dir, auto_create=True)
        run_helper_server(
            socket_path=Path(args.socket_path).expanduser() if args.socket_path else default_helper_socket_path(state_dir),
            token=token,
        )
        return 0

    if command_id == "connector_service.complete_enrollment":
        result = _complete_connector_service_enrollment(args, state_dir=state_dir)
        stdout.write(json.dumps(redact_value(result), sort_keys=True) + "\n")
        return 0 if result.get("ok") is True else 2

    if command_id.startswith("connector_service."):
        result = _run_connector_service(command_id.split(".", 1)[1], state_dir=state_dir)
        stdout.write(json.dumps(redact_value(_public_connector_service_result(result)), sort_keys=True) + "\n")
        return 0 if result.get("ok") is True else 2

    try:
        if command_id == "codex.send_visible_message":
            args.message = _resolve_visible_message_arg(args)
            args.message_hash = _short_hash(str(getattr(args, "message", "") or "").strip())
        if command_id == "customer_mac.desktop_set_value":
            args.value = _resolve_desktop_set_value_arg(args)
            args.value_hash = _short_hash(str(getattr(args, "value", "") or ""))
        ensure_allowed(command_id)
        observer = observer_factory() if observer_factory is not None else MacOSCodexObserver(state_dir=state_dir)
        customer_mac = customer_mac_factory() if customer_mac_factory is not None else CustomerMacObserver(state_dir=state_dir)
        app_server = app_server_factory() if app_server_factory is not None else CodexAppServerObserver()
        result = _validate_guarded_approval(command_id, args, state_dir)
        if result.ok:
            result = _run_command(command_id, observer, customer_mac, app_server, args)
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
        args=_audit_args(command_id, args),
        ok=result.ok,
        warnings=result.warnings,
        errors=result.errors,
        provenance={
            **command_metadata(command_id),
            **result.provenance,
            "dry_run": getattr(args, "dry_run", None),
            "selected_visible_target_id": getattr(args, "thread_id", None),
            "source_audit_id": getattr(args, "source_audit_id", None),
            "approval_audit_id": getattr(args, "approval_audit_id", None),
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
    if not getattr(args, "include_screenshot_bytes", False):
        envelope = _omit_inline_screenshot_bytes(envelope)
    if command_id in LATEST_OBSERVATION_COMMANDS:
        write_latest(envelope, state_dir=state_dir)
    stdout.write(json.dumps(envelope, sort_keys=True) + "\n")
    return 0 if result.ok else 2


def entrypoint() -> None:
    raise SystemExit(main())


def _run_bridge_argv(argv: list[str], *, state_dir: Path | None = None) -> tuple[int, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(argv, stdout=stdout, stderr=stderr, state_dir=state_dir)
    output = stdout.getvalue() or stderr.getvalue()
    return exit_code, output


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _omit_inline_screenshot_bytes(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        omitted = False
        omitted_reason: str | None = None
        for key, item in value.items():
            if key == "bytes_base64":
                omitted = True
                continue
            if key == "bytes_base64_omitted":
                omitted = omitted or bool(item)
                continue
            if key == "bytes_base64_omitted_reason":
                if isinstance(item, str) and item.strip():
                    omitted_reason = item
                continue
            sanitized[key] = _omit_inline_screenshot_bytes(item)
        if omitted:
            sanitized["inline_screenshot_bytes_omitted"] = True
            sanitized["inline_screenshot_bytes_omitted_reason"] = omitted_reason or INLINE_SCREENSHOT_BYTES_OMITTED_REASON
        return sanitized
    if isinstance(value, list):
        return [_omit_inline_screenshot_bytes(item) for item in value]
    return value


def _message_preview(value: str, *, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        return text[:limit]
    return text


def _resolve_visible_message_arg(args: argparse.Namespace) -> str:
    message_file = getattr(args, "message_file", None)
    if isinstance(message_file, str) and message_file.strip():
        return Path(message_file).expanduser().read_text(encoding="utf-8")
    return str(getattr(args, "message", "") or "")


def _resolve_desktop_set_value_arg(args: argparse.Namespace) -> str:
    value_file = getattr(args, "value_file", None)
    if isinstance(value_file, str) and value_file.strip():
        return Path(value_file).expanduser().read_text(encoding="utf-8")
    return str(getattr(args, "value", "") or "")


def _audit_args(command_id: str, args: argparse.Namespace) -> dict[str, object]:
    excluded = {"command_id", "target", "state_dir"}
    if command_id == "codex.send_visible_message":
        excluded.add("message")
        excluded.add("message_file")
    if command_id == "customer_mac.desktop_set_value":
        excluded.add("value")
        excluded.add("value_file")
    values = {key: value for key, value in vars(args).items() if key not in excluded}
    if command_id == "codex.send_visible_message":
        values["message_hash"] = getattr(args, "message_hash", _short_hash(str(getattr(args, "message", "") or "").strip()))
        values["message_preview"] = _message_preview(str(getattr(args, "message", "") or ""))
    if command_id == "customer_mac.desktop_set_value":
        values["value_hash"] = getattr(args, "value_hash", _short_hash(str(getattr(args, "value", "") or "")))
    return values


def _run_command(
    command_id: str,
    observer: MacOSCodexObserver,
    customer_mac: CustomerMacObserver,
    app_server: CodexAppServerObserver,
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
    if command_id == "permissions.prime":
        return _prime_permission(args.permission)
    if command_id == "helper.ping":
        return _helper_ping(args, state_dir=getattr(args, "state_dir", None))
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
    if command_id == "codex.thread_map":
        return _build_codex_thread_map(observer=observer, app_server=app_server, max_items=args.max_items)
    if command_id == "codex.focus":
        return observer.focus(dry_run=args.dry_run)
    if command_id == "codex.select_thread":
        return observer.select_thread(thread_id=args.thread_id, dry_run=args.dry_run)
    if command_id == "codex.send_visible_message":
        return observer.send_visible_message(
            thread_id=args.thread_id,
            message=args.message,
            dry_run=args.dry_run,
            confirmed=args.confirm,
            wait_ms=args.wait_ms,
            poll_interval_ms=args.poll_interval_ms,
        )
    if command_id == "codex.continue_thread":
        return observer.continue_thread(title=args.title, prompt=args.prompt, dry_run=args.dry_run)
    if command_id == "codex.snapshot":
        return observer.snapshot(max_chars=args.max_chars)
    if command_id == "codex.inspect":
        return observer.inspect(max_nodes=args.max_nodes)
    if command_id == "codex.ax_tree":
        return observer.ax_tree(max_nodes=args.max_nodes)
    if command_id == "codex.connections.status":
        return app_server.connections_status()
    if command_id == "codex.app_server.status":
        return app_server.status()
    if command_id == "codex.app_server.threads":
        return app_server.threads(max_items=args.max_items)
    if command_id == "codex.app_server.loaded_threads":
        return app_server.loaded_threads(max_items=args.max_items)
    if command_id == "codex.app_server.subscribe":
        return app_server.subscribe(thread_id=args.thread_id, duration_ms=args.duration_ms, max_chars=args.max_chars)
    if command_id == "codex.app_server.remote_control_status":
        return app_server.remote_control_status()
    if command_id == "customer_mac.status":
        return customer_mac.status()
    if command_id == "customer_mac.capabilities":
        return customer_mac.capabilities()
    if command_id == "customer_mac.control_status":
        return customer_mac.control_status()
    if command_id == "customer_mac.control_start":
        return customer_mac.control_start(mode=args.mode, agent_label=args.agent_label)
    if command_id == "customer_mac.control_stop":
        return customer_mac.control_stop()
    if command_id == "customer_mac.control_kill_switch":
        return customer_mac.control_kill_switch()
    if command_id == "customer_mac.desktop_see":
        return customer_mac.desktop_see(max_chars=args.max_chars, max_nodes=args.max_nodes)
    if command_id == "customer_mac.desktop_click":
        return customer_mac.desktop_click(target_label=args.target_label, x=args.x, y=args.y, snapshot_id=args.snapshot_id, element_id=args.element_id, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_type":
        return customer_mac.desktop_type(text=args.text, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_set_value":
        return customer_mac.desktop_set_value(snapshot_id=args.snapshot_id, element_id=args.element_id, value=args.value, attribute=args.attribute, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_scroll":
        return customer_mac.desktop_scroll(direction=args.direction, amount=args.amount, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_drag":
        return customer_mac.desktop_drag(from_x=args.from_x, from_y=args.from_y, to_x=args.to_x, to_y=args.to_y, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_hotkey":
        return customer_mac.desktop_hotkey(keys=args.keys, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_focus_app":
        return customer_mac.desktop_focus_app(app_name=args.app_name, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_window":
        return customer_mac.desktop_window(action=args.action, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_menu":
        return customer_mac.desktop_menu(menu_path=args.menu_path, dry_run=args.dry_run)
    if command_id == "customer_mac.desktop_browser_action":
        return customer_mac.desktop_browser_action(action=args.action, url=args.url, dry_run=args.dry_run)
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
    if command_id == "customer_mac.iphone_see":
        return customer_mac.iphone_see(max_chars=args.max_chars, max_nodes=args.max_nodes)
    if command_id == "customer_mac.iphone_tap":
        return customer_mac.iphone_tap(target_label=args.target_label, x=args.x, y=args.y, snapshot_id=args.snapshot_id, element_id=args.element_id, dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_swipe":
        return customer_mac.iphone_swipe(direction=args.direction, dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_type":
        return customer_mac.iphone_type(text=args.text, dry_run=args.dry_run)
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
        return customer_mac.iphone_mirroring_action(action="scroll", direction=args.direction, dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_swipe_left":
        return customer_mac.iphone_mirroring_action(action="swipe_left", dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_swipe_right":
        return customer_mac.iphone_mirroring_action(action="swipe_right", dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_swipe_up":
        return customer_mac.iphone_mirroring_action(action="swipe_up", dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_swipe_down":
        return customer_mac.iphone_mirroring_action(action="swipe_down", dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_type_approved_text":
        return customer_mac.iphone_mirroring_action(action="type_approved_text", text=args.text, dry_run=args.dry_run)
    if command_id == "customer_mac.iphone_mirroring_send_approved_message":
        return customer_mac.iphone_mirroring_action(action="send_approved_message", text=args.text, recipient_context=args.recipient_context, target_label=args.target_label, dry_run=args.dry_run)
    if command_id == "customer_mac.screen_sharing_status":
        return customer_mac.screen_sharing_status()
    raise PolicyError(command_id)


def _build_codex_thread_map(
    *,
    observer: MacOSCodexObserver,
    app_server: CodexAppServerObserver,
    max_items: int,
) -> CommandResult:
    frontmost_result = observer.frontmost()
    frontmost_data: dict[str, object] = {}
    visible_send_ready = False
    frontmost_warnings: list[str] = []
    if frontmost_result.ok:
        frontmost_data = dict(frontmost_result.data)
        visible_send_ready = frontmost_data.get("codex_frontmost") is True
        frontmost_warnings.extend(frontmost_result.warnings)
        if not visible_send_ready:
            frontmost_warnings.append("Codex Desktop is not frontmost; live visible sends will fail until Codex is focused.")
    else:
        frontmost_data = {"codex_frontmost": False, "available": False}
        frontmost_warnings.extend(frontmost_result.warnings)
        frontmost_warnings.append("Codex Desktop frontmost state unavailable; live visible sends will fail closed until frontmost state can be verified.")

    visible_result = observer.threads(max_items=max_items)
    if not visible_result.ok:
        visible_result.provenance.update({"source": "codex_visible_gui"})
        return visible_result
    app_result = app_server.threads(max_items=max_items)
    warnings = frontmost_warnings + list(visible_result.warnings)
    app_threads: list[dict[str, object]] = []
    app_server_available = app_result.ok
    if app_result.ok:
        app_threads = list(app_result.data.get("threads", []))
        warnings.extend(app_result.warnings)
    else:
        warnings.extend(app_result.warnings)
        warnings.append("app-server thread summaries unavailable; returning visible GUI candidates without saved-thread matches")

    visible_threads = list(visible_result.data.get("threads", []))
    matches: list[dict[str, object]] = []
    matched_app_ids: set[str] = set()
    for visible in visible_threads:
        visible_title = str(visible.get("title") or "")
        visible_norm = _normalize_title_for_match(visible_title)
        best: dict[str, object] | None = None
        best_score = 0
        match_reason = "normalized_title"
        for app_thread in app_threads:
            app_title = str(app_thread.get("title") or app_thread.get("name") or "")
            app_norm = _normalize_title_for_match(app_title)
            score = _title_match_score(visible_norm, app_norm)
            if score > best_score:
                best = app_thread
                best_score = score
        if best is None and visible.get("title_available") is False:
            index = visible.get("index")
            if isinstance(index, int) and 0 <= index < len(app_threads) and visible.get("updated_label"):
                best = app_threads[index]
                best_score = 2
                match_reason = "visible_order_title_hidden"
        if best is not None and best_score > 0:
            app_id = str(best.get("id") or "")
            if app_id:
                matched_app_ids.add(app_id)
            matches.append(
                {
                    "visible_id": visible.get("visible_id"),
                    "visible_title": visible_title,
                    "app_server_id": best.get("id"),
                    "app_server_title": best.get("title") or best.get("name"),
                    "confidence": "high" if best_score >= 3 else "medium",
                    "match_reason": match_reason,
                }
            )

    return CommandResult(
        ok=True,
        data={
            "visible_threads": visible_threads,
            "app_server_threads": app_threads,
            "matches": matches,
            "visible_count": len(visible_threads),
            "app_server_count": len(app_threads),
            "matched_count": len(matches),
            "unmatched_visible_count": max(0, len(visible_threads) - len(matches)),
            "unmatched_app_server_count": len([thread for thread in app_threads if str(thread.get("id") or "") not in matched_app_ids]),
            "app_server_available": app_server_available,
            "frontmost": frontmost_data,
            "visible_send_ready": visible_send_ready,
            "max_items": max_items,
            "source": "codex_visible_gui_app_server_read",
        },
        warnings=warnings,
        provenance={"source": "codex_visible_gui_app_server_read"},
    )


def _normalize_title_for_match(value: str) -> str:
    lowered = "".join(char.lower() if char.isalnum() else " " for char in value)
    return " ".join(lowered.split())


def _title_match_score(left: str, right: str) -> int:
    if not left or not right:
        return 0
    if left == right:
        return 3
    if left in right or right in left:
        return 2
    left_words = set(left.split())
    right_words = set(right.split())
    if len(left_words & right_words) >= 2:
        return 1
    return 0


def _helper_ping(args: argparse.Namespace, *, state_dir: Path | None) -> CommandResult:
    socket_path = Path(args.socket_path).expanduser() if args.socket_path else default_helper_socket_path(state_dir)
    try:
        token = read_helper_token(token_file=getattr(args, "token_file", None), state_dir=state_dir, auto_create=False)
    except (HelperIpcError, OSError) as exc:
        code = getattr(exc, "code", "helper_token_missing")
        message = getattr(exc, "message", str(exc))
        return CommandResult(
            ok=False,
            data={"helper_socket": str(socket_path)},
            errors=[
                make_error(
                    code=code,
                    message=message,
                    guidance="Start the helper with `evaos-desktop-bridge helper run` so the token file is created, then retry ping.",
                )
            ],
            provenance={"source": "computer_use_helper"},
        )
    return UnixSocketHelperClient(socket_path=socket_path, token=token).dispatch("ping", {"client": "bridge"})


def _validate_guarded_approval(command_id: str, args: argparse.Namespace, state_dir: Path | None) -> CommandResult:
    if command_id in TAKEOVER_WARNING_GATED_COMMANDS and getattr(args, "dry_run", None) is False:
        session = read_control_session(state_dir)
        if session.get("kill_switch") is True:
            return CommandResult(
                ok=False,
                data={"session": session},
                errors=[
                    make_error(
                        code="control_kill_switch_active",
                        message="The customer Mac kill switch is active; live agent control commands are blocked.",
                        guidance="The customer must start a new control session in Workbench before agents can act again.",
                    )
                ],
            )
        warning = session.get("takeover_warning") if isinstance(session.get("takeover_warning"), dict) else {}
        if session.get("active") is True and warning.get("active") is True:
            return _takeover_warning_active_result(warning)
        if command_id in CONTROLLED_LIVE_COMMANDS and session.get("active") is True:
            if session.get("mode") == "full_access":
                return CommandResult(ok=True)
            if session.get("mode") == "ask_permission" and not _ask_permission_requires_approval(command_id, args):
                return CommandResult(ok=True)

    source_fields = CODEX_SOURCE_AUDIT_FIELDS.get(command_id)
    if source_fields is not None and getattr(args, "dry_run", None) is False:
        if getattr(args, "confirm", None) is not True:
            return CommandResult(ok=True)
        source_audit_id = getattr(args, "source_audit_id", None)
        if not isinstance(source_audit_id, str) or not source_audit_id.strip().startswith("audit-"):
            return _source_audit_required_result(command_id, source_fields)
        record = read_audit_record(source_audit_id.strip(), state_dir=state_dir)
        if record is None:
            return _source_audit_required_result(command_id, source_fields, "source_audit_id was not found in the local audit log.")
        if record.get("command") != command_id or record.get("ok") is not True:
            return _source_audit_required_result(command_id, source_fields, "source_audit_id does not reference a successful dry-run for this command.")
        record_args = record.get("args")
        if not isinstance(record_args, dict) or record_args.get("dry_run") is not True:
            return _source_audit_required_result(command_id, source_fields, "source_audit_id must reference a dry-run record.")
        freshness_error = approval_audit_freshness_error(record)
        if freshness_error is not None:
            return _source_audit_required_result(command_id, source_fields, freshness_error.replace("approval_audit_id", "source_audit_id"))
        for field in source_fields:
            if record_args.get(field) != getattr(args, field, None):
                return _source_audit_required_result(command_id, source_fields, f"source_audit_id does not match {field}.")
        return CommandResult(ok=True)

    fields = GUARDED_APPROVAL_FIELDS.get(command_id)
    if fields is None or getattr(args, "dry_run", None) is not False:
        return CommandResult(ok=True)
    if command_id == "codex.send_visible_message" and getattr(args, "confirm", None) is not True:
        return CommandResult(
            ok=False,
            data={"required_fields": ["confirm", *fields]},
            errors=[
                make_error(
                    code="visible_message_confirmation_required",
                    message="Live Codex visible GUI messaging requires --confirm after a matching dry-run audit.",
                    guidance="Run the command with --dry-run first, then rerun with --live --confirm --approval-audit-id.",
                )
            ],
        )
    approval_audit_id = getattr(args, "approval_audit_id", None)
    if not isinstance(approval_audit_id, str) or not approval_audit_id.strip():
        return _approval_required_result(command_id, fields)
    record = read_audit_record(approval_audit_id.strip(), state_dir=state_dir)
    if record is None:
        return _approval_required_result(command_id, fields, "approval_audit_id was not found in the local audit log.")
    if record.get("command") != command_id or record.get("ok") is not True:
        return _approval_required_result(command_id, fields, "approval_audit_id does not reference a successful dry-run for this command.")
    record_args = record.get("args")
    if not isinstance(record_args, dict) or record_args.get("dry_run") is not True:
        return _approval_required_result(command_id, fields, "approval_audit_id must reference a dry-run record.")
    freshness_error = approval_audit_freshness_error(record)
    if freshness_error is not None:
        return _approval_required_result(command_id, fields, freshness_error)
    for field in fields:
        if record_args.get(field) != getattr(args, field, None):
            return _approval_required_result(command_id, fields, f"approval_audit_id does not match {field}.")
    return CommandResult(ok=True)


def _ask_permission_requires_approval(command_id: str, args: argparse.Namespace) -> bool:
    if command_id in ASK_PERMISSION_HIGH_IMPACT_COMMANDS:
        return True
    if command_id in {"customer_mac.desktop_click", "customer_mac.iphone_tap"}:
        label = getattr(args, "target_label", None)
        if not isinstance(label, str) or not label.strip():
            return True
        return _contains_risk_word(label)
    if command_id == "customer_mac.desktop_hotkey":
        keys = str(getattr(args, "keys", "") or "").strip().lower().replace("command", "cmd").replace(" ", "")
        return keys not in ASK_PERMISSION_SAFE_HOTKEYS
    if command_id == "customer_mac.desktop_window":
        return str(getattr(args, "action", "") or "").strip().lower() == "close"
    if command_id == "customer_mac.desktop_browser_action":
        return str(getattr(args, "action", "") or "").strip().lower() in {"open_url"}
    if command_id == "customer_mac.desktop_menu":
        return _contains_risk_word(str(getattr(args, "menu_path", "") or ""))
    return False


def _contains_risk_word(value: str) -> bool:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in value)
    words = set(normalized.split())
    return any(word in words for word in ASK_PERMISSION_RISK_WORDS)


def _approval_required_result(command_id: str, fields: tuple[str, ...], message: str | None = None) -> CommandResult:
    return CommandResult(
        ok=False,
        data={"required_fields": list(fields)},
        errors=[
            make_error(
                code="approval_audit_required",
                message=message or "Live guarded actions require a prior matching dry-run audit id.",
                guidance=f"Run {command_id} with --dry-run first, then rerun the exact same action with --approval-audit-id set to that audit_id.",
            )
        ],
    )


def _takeover_warning_active_result(warning: dict[str, object]) -> CommandResult:
    seconds = warning.get("seconds") if isinstance(warning.get("seconds"), int) else 10
    return CommandResult(
        ok=False,
        data={"takeover_warning": warning},
        errors=[
            make_error(
                code="control_takeover_warning_active",
                message=f"Agent control is starting; live actions are blocked until the {seconds}-second takeover warning finishes.",
                guidance="Wait for the visible takeover countdown to finish, then rerun the same live action. Read-only status, stop, and kill-switch remain available.",
            )
        ],
        provenance={"source": "control_session", "takeover_warning": warning},
    )


def _source_audit_required_result(command_id: str, fields: tuple[str, ...], message: str | None = None) -> CommandResult:
    return CommandResult(
        ok=False,
        data={"required_fields": list(fields)},
        errors=[
            make_error(
                code="source_audit_id_required",
                message=message or "Live Codex remote-control actions require a prior matching dry-run audit id.",
                guidance=f"Run {command_id} with --dry-run first, then rerun the exact same action with --source-audit-id set to that audit_id.",
            )
        ],
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def _capabilities() -> dict[str, object]:
    return {
        "modes": {
            "eyes": "Read-only visible desktop observation with redaction and caps.",
            "hands": "Guarded visible focus/select only; Codex app-server mutation commands remain withheld until live loaded-thread acceptance passes.",
            "brain": "Local Eva/OpenClaw announcement queue contract with external relay left to future sinks.",
        },
        "commands": [
            {"id": command, "target": _target_for_command(command), **command_metadata(command)}
            for command in [
                "status",
                "capabilities",
                "latest",
                "audit_tail",
                "permissions.prime",
                "helper.ping",
                "queue.list",
                "queue.append",
                "codex.frontmost",
                "codex.windows",
                "codex.threads",
                "codex.thread_map",
                "codex.focus",
                "codex.select_thread",
                "codex.send_visible_message",
                "codex.continue_thread",
                "codex.snapshot",
                "codex.inspect",
                "codex.ax_tree",
                "codex.connections.status",
                "codex.app_server.status",
                "codex.app_server.threads",
                "codex.app_server.loaded_threads",
                "codex.app_server.subscribe",
                "codex.app_server.remote_control_status",
                "customer_mac.status",
                "customer_mac.capabilities",
                "customer_mac.control_status",
                "customer_mac.control_start",
                "customer_mac.control_stop",
                "customer_mac.control_kill_switch",
                "customer_mac.desktop_see",
                "customer_mac.desktop_click",
                "customer_mac.desktop_type",
                "customer_mac.desktop_set_value",
                "customer_mac.desktop_scroll",
                "customer_mac.desktop_drag",
                "customer_mac.desktop_hotkey",
                "customer_mac.desktop_focus_app",
                "customer_mac.desktop_window",
                "customer_mac.desktop_menu",
                "customer_mac.desktop_browser_action",
                "customer_mac.snapshot",
                "customer_mac.ax_tree",
                "customer_mac.app_focus",
                "customer_mac.local_site_open",
                "customer_mac.local_site_action",
                "customer_mac.iphone_mirroring_status",
                "customer_mac.iphone_see",
                "customer_mac.iphone_tap",
                "customer_mac.iphone_swipe",
                "customer_mac.iphone_type",
                "customer_mac.iphone_mirroring_focus",
                "customer_mac.iphone_mirroring_home",
                "customer_mac.iphone_mirroring_app_switcher",
                "customer_mac.iphone_mirroring_spotlight",
                "customer_mac.iphone_mirroring_type_spotlight",
                "customer_mac.iphone_mirroring_open_app",
                "customer_mac.iphone_mirroring_tap_named_target",
                "customer_mac.iphone_mirroring_scroll",
                "customer_mac.iphone_mirroring_swipe_left",
                "customer_mac.iphone_mirroring_swipe_right",
                "customer_mac.iphone_mirroring_swipe_up",
                "customer_mac.iphone_mirroring_swipe_down",
                "customer_mac.iphone_mirroring_type_approved_text",
                "customer_mac.iphone_mirroring_send_approved_message",
                "customer_mac.screen_sharing_status",
            ]
        ],
        "guarded_prompt_or_message_commands": ["codex.send_visible_message"],
        "forbidden": [
            "unguarded_send_prompts_or_messages",
            "type_into_codex",
            "click_codex_controls",
            "call_codex_internal_mutation_rpc",
            "hijack_stdio_or_file_descriptors",
            "read_session_databases_wholesale",
            "expose_tokens_auth_files_or_full_home_paths",
            "customer_mac_generic_remote_desktop",
            "public_mac_ports",
            "hidden_shell_or_applescript_passthrough",
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


def _prime_permission(permission: str) -> CommandResult:
    normalized = "screen_recording" if permission == "screen-recording" else permission
    if sys.platform != "darwin":
        return CommandResult(
            ok=False,
            data={"permission": normalized, "status": "unsupported", "target": "evaOS Workbench"},
            errors=[
                make_error(
                    code="permission_platform_unsupported",
                    message="macOS permissions can only be requested on macOS.",
                    guidance="Run this from the Mac that will be paired with evaOS.",
                )
            ],
        )

    permission_name = "Screen Recording" if normalized == "screen_recording" else "Accessibility"
    peekaboo_path = _peekaboo_binary_path()
    if not peekaboo_path:
        _open_privacy_pane(normalized)
        return CommandResult(
            ok=False,
            data={
                "permission": normalized,
                "status": "unavailable",
                "target": "evaOS Workbench",
                "permission_holder": "evaOS Workbench",
            },
            errors=[
                make_error(
                    code="peekaboo_permission_helper_missing",
                    message="Peekaboo is required to check Mac control permissions without prompting for Python.",
                    guidance="Reinstall evaOS Workbench so the bundled Peekaboo helper is available, then approve evaOS Workbench or the Peekaboo helper shown by macOS.",
                    permission=normalized,
                )
            ],
        )

    grant_result = _run_peekaboo_permissions(peekaboo_path, ["grant", "--json"])
    status_result = _run_peekaboo_permissions(peekaboo_path, ["status", "--json"])
    event_result: dict[str, object] | None = None
    if normalized == "accessibility":
        event_result = _run_peekaboo_permissions(peekaboo_path, ["request-event-synthesizing", "--json"])
        status_result = _run_peekaboo_permissions(peekaboo_path, ["status", "--json"])

    trusted = _peekaboo_permission_granted(status_result, permission_name)
    if trusted is not True:
        _open_privacy_pane(normalized)

    return CommandResult(
        ok=True,
        data={
            "permission": normalized,
            "status": "granted" if trusted is True else "requested",
            "target": "Peekaboo automation helper",
            "executable": peekaboo_path,
            "permission_holder": _peekaboo_permission_source(status_result),
            "grant": grant_result,
            "event_synthesizing": event_result,
            "guidance": "Approve evaOS Workbench, Peekaboo, or the selected Peekaboo Bridge host shown by macOS. Python should not be the permission target for this flow.",
        },
    )


def _peekaboo_binary_path() -> str | None:
    for candidate in (*bundled_bridge_bin_candidates(("peekaboo", "evaos-connector-helper")), *PEEKABOO_BIN_CANDIDATES):
        if "/" in candidate:
            if Path(candidate).exists():
                return candidate
        else:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return None


def _run_peekaboo_permissions(peekaboo_path: str, args: list[str]) -> dict[str, object]:
    command = [peekaboo_path, "permissions", *args]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=12,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "command": command[:3], "error": str(exc)}
    try:
        payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "ok": completed.returncode == 0,
        "command": command[:3],
        "returncode": completed.returncode,
        "payload": payload if isinstance(payload, dict) else {},
        "stderr": completed.stderr[-1200:],
    }


def _peekaboo_permission_granted(status_result: dict[str, object], permission_name: str) -> bool | None:
    payload = status_result.get("payload")
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    permissions: object
    if isinstance(data, dict):
        permissions = data.get("permissions")
    else:
        permissions = data
    if not isinstance(permissions, list):
        return None
    for item in permissions:
        if isinstance(item, dict) and item.get("name") == permission_name:
            return bool(item.get("isGranted"))
    return None


def _peekaboo_permission_source(status_result: dict[str, object]) -> str:
    payload = status_result.get("payload")
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            source = data.get("source")
            if isinstance(source, str) and source:
                return f"Peekaboo {source}"
    return "Peekaboo Bridge host or bundled Peekaboo CLI"


def _open_privacy_pane(permission: str) -> None:
    pane = "Privacy_ScreenCapture" if permission == "screen_recording" else "Privacy_Accessibility"
    try:
        subprocess.run(
            ["open", f"x-apple.systempreferences:com.apple.preference.security?{pane}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except Exception:
        return


def _target_for_command(command: str) -> str:
    if command.startswith("customer_mac."):
        return "customer_mac"
    if command.startswith("codex."):
        return "codex"
    if command.startswith("queue."):
        return "queue"
    if command.startswith("helper."):
        return "computer_use_helper"
    return "desktop"


DEFAULT_CONNECTOR_LABEL = "com.electricsheep.evaos-desktop-bridge"


def _connector_label_from_env(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    raw_label = str(env.get("EVAOS_DESKTOP_BRIDGE_CONNECTOR_LABEL") or DEFAULT_CONNECTOR_LABEL).strip()
    if not raw_label:
        return DEFAULT_CONNECTOR_LABEL
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_")
    if any(char not in allowed for char in raw_label) or "/" in raw_label:
        return DEFAULT_CONNECTOR_LABEL
    return raw_label


CONNECTOR_LABEL = _connector_label_from_env()
CONNECTOR_PORT = 8765
CONNECTOR_SYSTEM_PLIST = Path(f"/Library/LaunchAgents/{CONNECTOR_LABEL}.plist")
CONNECTOR_USER_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{CONNECTOR_LABEL}.plist"
PEEKABOO_BIN_CANDIDATES = (
    "peekaboo",
    "evaos-connector-helper",
    "/opt/homebrew/bin/peekaboo",
    "/usr/local/bin/peekaboo",
)


def _complete_connector_service_enrollment(args: argparse.Namespace, *, state_dir: Path | None = None) -> dict[str, object]:
    enrollment_code = str(getattr(args, "enrollment_code", "") or "").strip()
    customer_id = str(getattr(args, "customer_id", "") or "").strip()
    device_name = str(getattr(args, "device_name", "") or "").strip() or socket.gethostname() or "Customer Mac"
    if not enrollment_code or not customer_id:
        return {
            "ok": False,
            "action": "complete-enrollment",
            "error": "enrollment_code_and_customer_id_required",
        }

    status = _connector_service_status(state_dir=state_dir)
    health = status.get("health") if isinstance(status.get("health"), dict) else {}
    host_result = _connector_registration_host(status)
    host = str(host_result.get("host") or "").strip()
    if status.get("ok") is not True:
        return {
            "ok": False,
            "action": "complete-enrollment",
            "error": "connector_service_not_ready",
            "status": status,
        }
    if not host:
        return {
            "ok": False,
            "action": "complete-enrollment",
            "error": str(host_result.get("error") or "secure_network_link_required"),
            "message": str(
                host_result.get("message")
                or "A secure tailnet or private connector host is required before pairing an agent to this Mac."
            ),
            "tailnet_available": bool(status.get("tailnet_ip")),
            "health_reachable": bool(health.get("reachable")),
            "health_host_kind": _connector_host_kind(str(health.get("host") or "")),
        }

    try:
        connector_token = read_token(None, state_dir=state_dir, auto_create=False)
    except Exception as exc:
        return {
            "ok": False,
            "action": "complete-enrollment",
            "error": "connector_token_unavailable",
            "message": str(exc),
        }
    if not connector_token:
        return {
            "ok": False,
            "action": "complete-enrollment",
            "error": "connector_token_unavailable",
        }

    try:
        result = complete_enrollment_via_control(
            enrollment_code=enrollment_code,
            connector_url=f"http://{_connector_url_host(host)}:{CONNECTOR_PORT}",
            connector_token=connector_token,
            device_name=device_name,
            device_identifier=socket.gethostname(),
        )
    except Exception as exc:
        return {
            "ok": False,
            "action": "complete-enrollment",
            "error": "broker_complete_enrollment_failed",
            "message": str(exc),
        }

    device = result.get("device") if isinstance(result.get("device"), dict) else {}
    headscale = result.get("headscale") if isinstance(result.get("headscale"), dict) else None
    public_headscale = None
    if headscale is not None:
        public_headscale = {
            key: value
            for key, value in headscale.items()
            if key not in {"preauth_key", "auth_key", "token", "secret"}
        }
        if any(key in headscale for key in ("preauth_key", "auth_key", "token", "secret")):
            public_headscale["secret_material_returned"] = False
    return {
        "ok": bool(device.get("id")) or result.get("ok") is True,
        "action": "complete-enrollment",
        "customer_id": customer_id,
        "device_id": device.get("id"),
        "connector_registered": True,
        "connector_token_last4": connector_token[-4:],
        "headscale": public_headscale,
        "raw_secrets_returned": False,
    }


def _build_cli_ready_payload(*, token: str | None, token_file: str | None = None, state_dir: Path | None = None) -> dict[str, object]:
    payload = dict(build_ready_payload(token=token, state_dir=state_dir))
    service_status = _connector_service_status(token=token, token_file=token_file, state_dir=state_dir)
    health = service_status.get("health") if isinstance(service_status.get("health"), dict) else {}
    blockers = list(payload.get("blockers") if isinstance(payload.get("blockers"), list) else [])

    if service_status.get("ready") is not True:
        code = "connector_service_unreachable" if health.get("reachable") is not True else "connector_service_not_ready"
        blockers.append(
            {
                "code": code,
                "message": "Connector service is not ready; Workbench must start the signed bridge before Mac control is ready.",
                "host_kind": _connector_host_kind(str(health.get("host") or "")),
            }
        )

    if blockers:
        payload["ok"] = False
        payload["ready"] = False
        payload["blockers"] = blockers

    payload["connector_service"] = _public_ready_connector_service_status(service_status)
    return payload


def _build_cli_diagnostics_payload(*, token: str | None, token_file: str | None = None, state_dir: Path | None = None) -> dict[str, object]:
    service_status = _connector_service_status(token=token, token_file=token_file, state_dir=state_dir)
    return build_diagnostics_payload(
        token=token,
        state_dir=state_dir,
        owner=_public_bridge_owner_from_status(service_status),
    )


def _connector_http_owner_summary() -> dict[str, object]:
    return _bridge_owner_summary(
        label=CONNECTOR_LABEL,
        plist_path=_connector_plist_path(),
        program_arguments=None,
        ready=True,
        active_program_path=_current_connector_program_path(),
    )


def _current_connector_program_path() -> Path | None:
    candidates: list[Path] = []
    argv0 = str(sys.argv[0] or "").strip()
    if argv0:
        candidates.append(Path(argv0).expanduser())
    process_path = _process_program_path(os.getpid())
    if process_path is not None:
        candidates.append(process_path)
    if sys.executable:
        candidates.append(Path(sys.executable).expanduser())

    preferred: tuple[int, Path] | None = None
    classification_rank = {"workbench_bundle": 0, "legacy_bundle": 1, "global_cli": 2}
    for candidate in candidates:
        classification = _classify_bridge_owner(program_path=candidate, app_path=_owner_app_path(candidate), ready=True)
        rank = classification_rank.get(classification)
        if rank is None:
            continue
        if preferred is None or rank < preferred[0]:
            preferred = (rank, candidate)
    if preferred is not None:
        return preferred[1]
    return candidates[0] if candidates else None


def _public_ready_connector_service_status(status: dict[str, object]) -> dict[str, object]:
    health = status.get("health") if isinstance(status.get("health"), dict) else {}
    return {
        "ok": status.get("ok") is True,
        "ready": status.get("ready") is True,
        "managed_by": status.get("managed_by") if isinstance(status.get("managed_by"), str) else "unknown",
        "token_present": status.get("token_present") is True,
        "loaded": status.get("loaded") is True,
        "running": status.get("running") is True,
        "owner": _public_bridge_owner_from_status(status),
        "health": {
            "reachable": health.get("reachable") is True,
            "ready": health.get("ready") is True,
            "authenticated": health.get("authenticated") is True,
            "host_kind": _connector_host_kind(str(health.get("host") or "")),
        },
    }


def _read_connector_token_optional(token_file: str | None, *, state_dir: Path | None = None) -> str | None:
    try:
        return read_token(token_file, state_dir=state_dir, auto_create=False)
    except (FileNotFoundError, ValueError):
        return None


def _connector_token_path(token_file: str | None, *, state_dir: Path | None = None) -> Path:
    if token_file:
        return Path(token_file).expanduser()
    return (state_dir or default_state_dir()) / "connector.token"


def _connector_token_value(token_file: str | None, *, token: str | None = None, state_dir: Path | None = None) -> str | None:
    if isinstance(token, str) and token.strip():
        return token
    try:
        return read_token(token_file, state_dir=state_dir, auto_create=False)
    except (FileNotFoundError, IsADirectoryError, PermissionError, UnicodeDecodeError, ValueError):
        return None


def _connector_registration_host(status: dict[str, object]) -> dict[str, object]:
    tailnet_ip = str(status.get("tailnet_ip") or "").strip()
    if _is_safe_connector_registration_host(tailnet_ip):
        return {"ok": True, "host": tailnet_ip, "source": "tailnet_ip"}

    health = status.get("health") if isinstance(status.get("health"), dict) else {}
    health_host = str(health.get("host") or "").strip()
    if health.get("reachable") is True and _is_safe_connector_registration_host(health_host):
        return {"ok": True, "host": health_host, "source": "health_host"}

    return {
        "ok": False,
        "error": "tailnet_ip_required" if not tailnet_ip else "secure_network_link_required",
        "message": (
            "A secure tailnet or private connector host is required before pairing an agent to this Mac. "
            "Loopback, reserved, public, or unreachable connector health hosts are not registered with evaOS."
        ),
    }


def _is_safe_connector_registration_host(value: str) -> bool:
    host = _normalized_connector_host(value)
    if not host:
        return False
    lowered = host.lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return False
    if lowered.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip.is_link_local:
        return False
    return _looks_like_tailnet_ipv4(host) or ip.is_private


def _connector_host_kind(value: str) -> str:
    host = _normalized_connector_host(value)
    if not host:
        return "missing"
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return "loopback"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host.lower().endswith(".local"):
            return "local"
        return "hostname"
    if ip.is_loopback:
        return "loopback"
    if ip.is_unspecified:
        return "unspecified"
    if _looks_like_tailnet_ipv4(host):
        return "tailnet"
    if ip.is_private:
        return "private"
    return "public"


def _normalized_connector_host(value: str) -> str:
    raw_host = str(value or "").strip()
    if not raw_host or any(separator in raw_host for separator in ("/", "?", "#", "@")):
        return ""
    bracketed_host = raw_host.startswith("[") and raw_host.endswith("]")
    host = raw_host[1:-1] if bracketed_host else raw_host
    if not host:
        return ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if ":" in host:
            return ""
    return host


def _connector_url_host(host: str) -> str:
    normalized = _normalized_connector_host(host)
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized
    return f"[{normalized}]" if ip.version == 6 else normalized


def _run_connector_service(action: str, *, state_dir: Path | None = None) -> dict[str, object]:
    if action not in {"status", "start", "stop"}:
        return {"ok": False, "error": "unsupported_connector_service_action", "action": action}

    if action == "start":
        start_result = _launchctl_start()
        status = _wait_for_connector_service(state_dir=state_dir)
        return {"ok": status["ok"], "action": action, "launchctl": start_result, "status": status}

    if action == "stop":
        stop_result = _launchctl_stop()
        status = _connector_service_status(state_dir=state_dir)
        return {"ok": True, "action": action, "launchctl": stop_result, "status": status}

    return _connector_service_status(state_dir=state_dir)


def _public_connector_service_result(result: dict[str, object]) -> dict[str, object]:
    nested_status = result.get("status")
    if isinstance(nested_status, dict):
        public: dict[str, object] = {
            "ok": result.get("ok") is True,
            "action": result.get("action") if isinstance(result.get("action"), str) else "connector-service",
            "status": _public_connector_service_status(nested_status),
        }
        launchctl = result.get("launchctl")
        if isinstance(launchctl, dict):
            public["launchctl"] = _public_launchctl_result(launchctl)
        return public
    if "health" in result or "managed_by" in result or "permission_target" in result:
        return _public_connector_service_status(result)
    return result


def _public_launchctl_result(result: dict[str, object]) -> dict[str, object]:
    if "returncode" in result:
        return {
            "returncode": result.get("returncode"),
            "stdout_present": bool(result.get("stdout")),
            "stderr_present": bool(result.get("stderr")),
        }
    return {key: _public_launchctl_result(value) for key, value in result.items() if isinstance(key, str) and isinstance(value, dict)}


def _public_connector_service_status(status: dict[str, object]) -> dict[str, object]:
    health = status.get("health") if isinstance(status.get("health"), dict) else {}
    public: dict[str, object] = {
        "ok": status.get("ok") is True,
        "ready": status.get("ready") is True,
        "label": status.get("label") if isinstance(status.get("label"), str) else CONNECTOR_LABEL,
        "domain": status.get("domain") if isinstance(status.get("domain"), str) else _launchctl_domain(),
        "managed_by": status.get("managed_by") if isinstance(status.get("managed_by"), str) else "unknown",
        "plist_path": _public_path(status.get("plist_path")) if status.get("plist_path") else None,
        "plist_installed": status.get("plist_installed") is True,
        "token_path": _public_path(status.get("token_path")) if status.get("token_path") else None,
        "token_present": status.get("token_present") is True,
        "loaded": status.get("loaded") is True,
        "running": status.get("running") is True,
        "tailnet_available": bool(status.get("tailnet_ip")),
        "health": {
            "reachable": health.get("reachable") is True,
            "ready": health.get("ready") is True,
            "authenticated": health.get("authenticated") is True,
            "host_kind": _connector_host_kind(str(health.get("host") or "")),
        },
        "owner": _public_bridge_owner_from_status(status),
        "guidance": _public_connector_guidance(status),
    }
    permission_target = status.get("permission_target")
    if isinstance(permission_target, dict):
        public["permission_target"] = redact_value(permission_target)
    return public


def _public_bridge_owner_from_status(status: dict[str, object]) -> dict[str, object]:
    owner = status.get("owner")
    if isinstance(owner, dict):
        return owner
    program_arguments = status.get("program_arguments") if isinstance(status.get("program_arguments"), list) else None
    plist_path = Path(status["plist_path"]) if isinstance(status.get("plist_path"), str) else None
    return _bridge_owner_summary(
        label=str(status.get("label") or CONNECTOR_LABEL),
        plist_path=plist_path,
        program_arguments=program_arguments,
        ready=status.get("ready") is True,
    )


def _bridge_owner_summary(
    *,
    label: str,
    plist_path: Path | None,
    program_arguments: list[str] | None,
    ready: bool,
    active_program_path: Path | None = None,
) -> dict[str, object]:
    program_path = active_program_path or (Path(program_arguments[0]).expanduser() if program_arguments else None)
    app_path = _owner_app_path(program_path)
    manifest_path = _owner_manifest_path(program_path, app_path)
    manifest = _read_owner_manifest(manifest_path)
    return {
        "label": label,
        "plist_path": _typed_public_path(plist_path),
        "program_path": _typed_public_path(program_path),
        "app_path": _typed_public_path(app_path),
        "source_commit": _owner_source_commit(manifest),
        "manifest_path": _typed_public_path(manifest_path),
        "bundle_id": _owner_bundle_id(app_path),
        "classification": _classify_bridge_owner(program_path=program_path, app_path=app_path, ready=ready),
    }


def _typed_public_path(path: Path | str | None) -> dict[str, object]:
    if path is None:
        return {"kind": "unknown"}
    public_path = _public_path(path)
    if not public_path:
        return {"kind": "unknown"}
    return {"kind": "path", "value": public_path}


def _public_path(path: Path | str | object | None) -> str | None:
    if path is None:
        return None
    return str(redact_value(str(path)))


def _owner_app_path(program_path: Path | None) -> Path | None:
    if program_path is None:
        return None
    for candidate in (program_path, *program_path.parents):
        if candidate.suffix == ".app":
            return candidate
    return None


def _owner_manifest_path(program_path: Path | None, app_path: Path | None) -> Path | None:
    candidates: list[Path] = []
    if program_path is not None:
        candidates.append(program_path.parent / "manifest.json")
    if app_path is not None:
        candidates.append(app_path / "Contents" / "Resources" / "Bridge" / "manifest.json")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_owner_manifest(manifest_path: Path | None) -> dict[str, object]:
    if manifest_path is None:
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _owner_source_commit(manifest: dict[str, object]) -> str | None:
    for key in ("source_commit", "bridge_ref", "commit_ref", "commit", "git_sha", "sha"):
        value = manifest.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _owner_bundle_id(app_path: Path | None) -> str | None:
    if app_path is None:
        return None
    info_plist = app_path / "Contents" / "Info.plist"
    try:
        payload = plistlib.loads(info_plist.read_bytes())
    except Exception:
        return None
    bundle_id = payload.get("CFBundleIdentifier") if isinstance(payload, dict) else None
    return bundle_id if isinstance(bundle_id, str) and bundle_id.strip() else None


def _classify_bridge_owner(*, program_path: Path | None, app_path: Path | None, ready: bool) -> str:
    if program_path is None:
        return "unknown" if ready else "not_running"
    app_name = app_path.name.lower() if app_path is not None else ""
    if app_name == "evaos workbench.app":
        return "workbench_bundle"
    if app_name == "evaos.app":
        return "legacy_bundle"
    program_text = str(program_path)
    if program_text == "evaos-desktop-bridge" or program_text.startswith(("/opt/homebrew/bin/", "/usr/local/bin/")):
        return "global_cli"
    return "unknown"


def _public_connector_guidance(status: dict[str, object]) -> list[object]:
    guidance = status.get("guidance")
    if not isinstance(guidance, list):
        return []
    return [_redact_connector_transport_text(str(item)) for item in guidance if isinstance(item, str)]


def _redact_connector_transport_text(value: str) -> str:
    redacted = str(redact_value(value))
    redacted = re.sub(r"https?://[^\s)>\"]+", "<redacted-url>", redacted, flags=re.IGNORECASE)
    redacted = re.sub(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?::\d{1,5})?\b",
        "<redacted-ip>",
        redacted,
    )
    return re.sub(r"\b8765\b", "<redacted-port>", redacted)


def _connector_service_status(*, token: str | None = None, token_file: str | None = None, state_dir: Path | None = None) -> dict[str, object]:
    domain = _launchctl_domain()
    print_result = _run_launchctl(["print", f"{domain}/{CONNECTOR_LABEL}"])
    connector_token = _connector_token_value(token_file, token=token, state_dir=state_dir)
    health = _connector_loopback_health(connector_token=connector_token)
    token_path = _connector_token_path(token_file, state_dir=state_dir)
    plist_path = _connector_plist_path()
    loaded = print_result["returncode"] == 0
    reachable = health["reachable"] is True
    ready = health.get("ready") is True
    running = loaded and ready
    tailnet_ip = _tailscale_ip()
    managed_by = "launchagent" if running else "workbench-or-manual" if ready else "offline"
    program_arguments = _connector_plist_program_arguments(plist_path)
    active_program_path = _active_connector_process_program_path() if reachable else None
    owner = _bridge_owner_summary(
        label=CONNECTOR_LABEL,
        plist_path=plist_path,
        program_arguments=program_arguments,
        ready=ready,
        active_program_path=active_program_path,
    )
    return {
        "ok": bool(connector_token and ready),
        "ready": ready,
        "label": CONNECTOR_LABEL,
        "domain": domain,
        "managed_by": managed_by,
        "plist_path": str(plist_path) if plist_path else None,
        "plist_installed": plist_path is not None,
        "token_path": str(token_path),
        "token_present": bool(connector_token),
        "loaded": loaded,
        "running": running,
        "tailnet_ip": tailnet_ip,
        "health": health,
        "launchctl": print_result,
        "owner": owner,
        "permission_target": _connector_permission_target(managed_by, health, program_arguments),
        "guidance": _connector_service_guidance(plist_path, token_path.exists(), health),
    }


def _wait_for_connector_service(*, state_dir: Path | None = None, timeout_sec: float = 8.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    status = _connector_service_status(state_dir=state_dir)
    while not status["ok"] and time.monotonic() < deadline:
        time.sleep(0.25)
        status = _connector_service_status(state_dir=state_dir)
    return status


def _connector_service_guidance(plist_path: Path | None, token_present: bool, health: dict[str, object]) -> list[str]:
    guidance: list[str] = []
    if plist_path is None:
        guidance.append("Start the connector service once to install the per-user LaunchAgent.")
    if not token_present:
        guidance.append("Start the connector once to mint the per-user connector token.")
    if health.get("reachable") is not True:
        guidance.append("Start the connector service and confirm its health endpoint responds.")
    return guidance


def _active_connector_process_program_path() -> Path | None:
    pid = _active_connector_process_pid()
    if pid is None:
        return None
    return _process_program_path(pid)


def _active_connector_process_pid() -> int | None:
    lsof = shutil.which("lsof") or "/usr/sbin/lsof"
    try:
        completed = subprocess.run(
            [lsof, "-nP", f"-iTCP:{CONNECTOR_PORT}", "-sTCP:LISTEN", "-Fp"],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        if line.startswith("p"):
            try:
                pid = int(line[1:])
            except ValueError:
                continue
            if pid > 0:
                return pid
    return None


def _process_program_path(pid: int) -> Path | None:
    text_path = _process_text_path(pid)
    if text_path is not None:
        return text_path
    try:
        completed = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "comm="],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    path_text = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    return Path(path_text).expanduser() if path_text else None


def _process_text_path(pid: int) -> Path | None:
    lsof = shutil.which("lsof") or "/usr/sbin/lsof"
    try:
        completed = subprocess.run(
            [lsof, "-nP", "-p", str(pid), "-d", "txt", "-Fn"],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        if line.startswith("n"):
            path_text = line[1:].strip()
            if path_text:
                return Path(path_text).expanduser()
    return None


def _launchctl_start() -> dict[str, object]:
    plist_path = _ensure_connector_user_plist()
    domain = _launchctl_domain()
    bootout = _run_launchctl(["bootout", f"{domain}/{CONNECTOR_LABEL}"])
    bootstrap = _run_launchctl(["bootstrap", domain, str(plist_path)])
    kickstart = _run_launchctl(["kickstart", "-k", f"{domain}/{CONNECTOR_LABEL}"])
    return {"bootout": bootout, "bootstrap": bootstrap, "kickstart": kickstart}


def _launchctl_stop() -> dict[str, object]:
    return _run_launchctl(["bootout", f"{_launchctl_domain()}/{CONNECTOR_LABEL}"])


def _run_launchctl(args: list[str]) -> dict[str, object]:
    try:
        completed = subprocess.run(
            ["launchctl", *args],
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    except Exception as exc:
        return {"returncode": 1, "stderr": str(exc)}


def _connector_loopback_health(*, connector_token: str | None = None) -> dict[str, object]:
    plist_path = _connector_plist_path()
    host = _connector_plist_host(plist_path) or _tailscale_ip() or "127.0.0.1"
    try:
        health = _connector_http_get(host, "/health")
        health_json = health.get("json") if isinstance(health.get("json"), dict) else {}
        reachable = health.get("status_code") == 200 and health_json.get("service") == "evaos-desktop-bridge-connector"
        result: dict[str, object] = {
            "reachable": reachable,
            "ready": False,
            "authenticated": False,
            "host": host,
            "port": CONNECTOR_PORT,
            "status_line": health.get("status_line") if isinstance(health.get("status_line"), str) else "",
        }
        if not reachable:
            result["error"] = "connector_identity_unverified"
            return result
        if not connector_token:
            result["error"] = "connector_token_missing"
            return result

        diagnostics = _connector_http_get(host, "/v1/diagnostics", authorization=f"Bearer {connector_token}")
        diagnostics_json = diagnostics.get("json") if isinstance(diagnostics.get("json"), dict) else {}
        connector = diagnostics_json.get("connector") if isinstance(diagnostics_json.get("connector"), dict) else {}
        ready_payload = connector.get("ready") if isinstance(connector.get("ready"), dict) else {}
        authenticated = diagnostics.get("status_code") == 200 and diagnostics_json.get("schema") == "evaos.desktop_bridge.diagnostics.v1"
        ready = (
            authenticated
            and ready_payload.get("schema") == "evaos.desktop_bridge.ready.v1"
            and ready_payload.get("ok") is True
            and ready_payload.get("ready") is True
        )
        result["authenticated"] = authenticated
        result["ready"] = ready
        result["ready_status_line"] = diagnostics.get("status_line") if isinstance(diagnostics.get("status_line"), str) else ""
        if not ready:
            result["error"] = "connector_ready_probe_failed"
        return result
    except Exception as exc:
        return {"reachable": False, "host": host, "port": CONNECTOR_PORT, "error": str(exc)}


def _connector_http_get(host: str, path: str, *, authorization: str | None = None) -> dict[str, object]:
    connect_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    headers = [f"GET {path} HTTP/1.1", f"Host: {host}", "Connection: close"]
    if authorization:
        headers.append(f"Authorization: {authorization}")
    request = ("\r\n".join(headers) + "\r\n\r\n").encode("utf-8")
    with socket.create_connection((connect_host, CONNECTOR_PORT), timeout=1.0) as sock:
        sock.settimeout(1.0)
        sock.sendall(request)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = sock.recv(4096)
            except TimeoutError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            if sum(len(item) for item in chunks) >= 65536:
                break
    data = b"".join(chunks)
    text = data.decode("utf-8", errors="replace")
    status_line = text.splitlines()[0] if text else ""
    status_code = None
    parts = status_line.split()
    if len(parts) >= 2:
        try:
            status_code = int(parts[1])
        except ValueError:
            status_code = None
    _, _, body = text.partition("\r\n\r\n")
    parsed_json: object | None = None
    if body.strip():
        try:
            parsed_json = json.loads(body)
        except json.JSONDecodeError:
            parsed_json = None
    return {"status_code": status_code, "status_line": status_line, "json": parsed_json}


def _connector_permission_target(
    managed_by: str,
    health: dict[str, object],
    program_arguments: list[str] | None,
) -> dict[str, object]:
    launch_program = program_arguments[0] if program_arguments else None
    target_paths = {
        "bridge_executable": launch_program or _connector_program_path(),
        "launch_program": launch_program,
        "permission_holder": "Peekaboo Bridge host or bundled Peekaboo CLI",
        "automation_engine": "Peekaboo",
    }
    if health.get("reachable") is not True:
        return {
            "name": "evaOS Workbench",
            "mode": "not_running",
            **target_paths,
            "guidance": "Start the connector from Workbench, then approve evaOS Workbench or its bridge helper in Accessibility and Screen Recording.",
        }
    if managed_by == "launchagent":
        return {
            "name": "evaOS Connector",
            "mode": "launchagent",
            **target_paths,
            "guidance": "If Accessibility or Screen Recording is missing, approve evaOS Workbench, evaOS Connector, or the selected Peekaboo helper shown in Privacy & Security.",
        }
    return {
        "name": "evaOS Workbench / evaOS Connector",
        "mode": "workbench_managed",
        **target_paths,
        "guidance": "Keep Workbench open and approve evaOS Workbench, evaOS Connector, or the selected Peekaboo helper in Accessibility and Screen Recording.",
    }


def _tailscale_ip() -> str | None:
    interface_ip = _active_tailnet_interface_ip()
    if interface_ip:
        return interface_ip

    status_ip = _online_tailscale_status_ip()
    if status_ip:
        return status_ip

    commands: list[list[str]] = []
    seen: set[str] = set()
    for candidate in [
        shutil.which("tailscale"),
        "/opt/homebrew/bin/tailscale",
        "/usr/local/bin/tailscale",
        "tailscale",
    ]:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        commands.append([candidate, "ip", "-4"])

    for command in commands:
        try:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
        except Exception:
            continue
        if completed.returncode != 0:
            continue
        for line in completed.stdout.splitlines():
            value = line.strip()
            if _looks_like_tailnet_ipv4(value):
                return value
    return None


def _active_tailnet_interface_ip() -> str | None:
    try:
        completed = subprocess.run(
            ["/sbin/ifconfig"],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "inet" and _looks_like_tailnet_ipv4(parts[1]):
            return parts[1]
    return None


def _online_tailscale_status_ip() -> str | None:
    command = shutil.which("tailscale") or "/opt/homebrew/bin/tailscale"
    try:
        completed = subprocess.run(
            [command, "status", "--json"],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    if payload.get("BackendState") != "Running":
        return None
    self_node = payload.get("Self")
    if not isinstance(self_node, dict) or self_node.get("Online") is not True:
        return None
    addresses = self_node.get("TailscaleIPs")
    if not isinstance(addresses, list):
        return None
    for value in addresses:
        if isinstance(value, str) and _looks_like_tailnet_ipv4(value):
            return value
    return None


def _looks_like_tailnet_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if address.version != 4:
        return False
    return address in ipaddress.ip_network("100.64.0.0/10")


def _connector_plist_path() -> Path | None:
    if CONNECTOR_USER_PLIST.exists():
        return CONNECTOR_USER_PLIST
    if CONNECTOR_SYSTEM_PLIST.exists():
        return CONNECTOR_SYSTEM_PLIST
    return None


def _ensure_connector_user_plist() -> Path:
    host = os.environ.get("EVAOS_DESKTOP_BRIDGE_CONNECTOR_HOST") or _tailscale_ip() or "127.0.0.1"
    program = _connector_program_path()
    payload = _connector_plist_payload(program=program, host=host)
    CONNECTOR_USER_PLIST.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, object] | None = None
    if CONNECTOR_USER_PLIST.exists():
        try:
            current = plistlib.loads(CONNECTOR_USER_PLIST.read_bytes())
        except Exception:
            current = None
    if current != payload:
        CONNECTOR_USER_PLIST.write_bytes(plistlib.dumps(payload, sort_keys=False))
    return CONNECTOR_USER_PLIST


def _connector_program_path() -> str:
    argv0 = Path(sys.argv[0]).expanduser()
    if argv0.exists():
        packaged_launcher = argv0.parent.parent.parent / "evaos-desktop-bridge"
        if (
            argv0.name == "cli.py"
            and argv0.parent.name == "evaos_desktop_bridge"
            and argv0.parent.parent.name == "src"
            and packaged_launcher.exists()
        ):
            return str(packaged_launcher.resolve())
        if argv0.name != "cli.py" or os.access(argv0, os.X_OK):
            return str(argv0.resolve())
    resolved = shutil.which("evaos-desktop-bridge")
    if resolved:
        return resolved
    return "evaos-desktop-bridge"


def _connector_plist_payload(*, program: str, host: str) -> dict[str, object]:
    return {
        "Label": CONNECTOR_LABEL,
        "ProgramArguments": [
            program,
            "serve",
            "--host",
            host,
            "--port",
            str(CONNECTOR_PORT),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "EnvironmentVariables": {
            "EVAOS_DESKTOP_BRIDGE_MODE": "customer-mac-connector",
        },
    }


def _connector_plist_host(plist_path: Path | None) -> str | None:
    argv = _connector_plist_program_arguments(plist_path)
    if not argv:
        return None
    try:
        host_index = argv.index("--host") + 1
    except ValueError:
        return None
    if host_index >= len(argv):
        return None
    host = argv[host_index]
    return host if isinstance(host, str) and host else None


def _connector_plist_program_arguments(plist_path: Path | None) -> list[str] | None:
    if plist_path is None:
        return None
    try:
        payload = plistlib.loads(plist_path.read_bytes())
    except Exception:
        return None
    argv = payload.get("ProgramArguments")
    if not isinstance(argv, list):
        return None
    return [item for item in argv if isinstance(item, str)]


def _launchctl_domain() -> str:
    return f"gui/{os.getuid()}"


if __name__ == "__main__":
    entrypoint()
