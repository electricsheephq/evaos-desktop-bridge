from __future__ import annotations

import json
import hashlib
import os
import secrets
import socket
import tempfile
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .audit import default_state_dir
from .schema import build_envelope, make_error
from .state import approval_audit_freshness_error, read_audit_record, read_control_session

CommandRunner = Callable[[list[str]], tuple[int, str]]

CUSTOMER_MAC_CONTROL_URL = os.environ.get(
    "EVAOS_CUSTOMER_MAC_CONTROL_URL",
    "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/customer-mac-control",
)

GUARDED_REMOTE_COMMANDS = frozenset(
    {
        "codexSelectThread",
        "codexSendVisibleMessage",
        "codexContinueThread",
        "customerMacAppFocus",
        "customerMacLocalSiteOpen",
        "customerMacLocalSiteAction",
        "customerMacIphoneMirroringFocus",
        "customerMacIphoneMirroringHome",
        "customerMacIphoneMirroringAppSwitcher",
        "customerMacIphoneMirroringSpotlight",
        "customerMacIphoneMirroringTypeSpotlight",
        "customerMacIphoneMirroringOpenApp",
        "customerMacIphoneMirroringTapNamedTarget",
        "customerMacIphoneMirroringScroll",
        "customerMacIphoneMirroringSwipeLeft",
        "customerMacIphoneMirroringSwipeRight",
        "customerMacIphoneMirroringSwipeUp",
        "customerMacIphoneMirroringSwipeDown",
        "customerMacIphoneMirroringTypeApprovedText",
        "customerMacIphoneMirroringSendApprovedMessage",
    }
)

CODEX_REMOTE_CONTROL_COMMANDS = frozenset()

CODEX_REMOTE_CONTROL_APPROVAL: dict[str, tuple[str, tuple[str, ...]]] = {}

CONTROLLED_REMOTE_COMMANDS = frozenset(
    {
        "customerMacIphoneMirroringFocus",
        "customerMacIphoneMirroringHome",
        "customerMacIphoneMirroringAppSwitcher",
        "customerMacIphoneMirroringSpotlight",
        "customerMacIphoneMirroringTypeSpotlight",
        "customerMacIphoneMirroringOpenApp",
        "customerMacIphoneMirroringTapNamedTarget",
        "customerMacIphoneMirroringScroll",
        "customerMacIphoneMirroringSwipeLeft",
        "customerMacIphoneMirroringSwipeRight",
        "customerMacIphoneMirroringSwipeUp",
        "customerMacIphoneMirroringSwipeDown",
        "customerMacIphoneMirroringTypeApprovedText",
        "customerMacIphoneMirroringSendApprovedMessage",
        "desktopClick",
        "desktopType",
        "desktopSetValue",
        "desktopScroll",
        "desktopDrag",
        "desktopHotkey",
        "desktopFocusApp",
        "desktopWindow",
        "desktopMenu",
        "desktopBrowserAction",
        "iphoneTap",
        "iphoneSwipe",
        "iphoneType",
    }
)

TAKEOVER_WARNING_REMOTE_COMMANDS = CONTROLLED_REMOTE_COMMANDS | frozenset(
    {
        "customerMacAppFocus",
        "customerMacLocalSiteOpen",
        "customerMacLocalSiteAction",
    }
)

GUARDED_REMOTE_COMMANDS = GUARDED_REMOTE_COMMANDS | CONTROLLED_REMOTE_COMMANDS

KILL_SWITCH_REMOTE_COMMAND_ALLOWLIST = frozenset(
    {
        "customerMacControlStatus",
        "customerMacControlKillSwitch",
    }
)

ASK_PERMISSION_HIGH_IMPACT_REMOTE_COMMANDS = frozenset(
    {
        "customerMacIphoneMirroringSwipeLeft",
        "customerMacIphoneMirroringSwipeRight",
        "customerMacIphoneMirroringSwipeUp",
        "customerMacIphoneMirroringSwipeDown",
        "customerMacIphoneMirroringTypeApprovedText",
        "customerMacIphoneMirroringSendApprovedMessage",
        "desktopSetValue",
        "desktopType",
        "iphoneSwipe",
        "iphoneType",
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

CONNECTOR_COMMAND_ALIASES = {
    "desktop_bridge_status": "status",
    "desktop_bridge_capabilities": "capabilities",
    "desktop_bridge_latest": "latest",
    "desktop_bridge_audit_tail": "auditTail",
    "desktop_bridge_queue_list": "queueList",
    "desktop_bridge_queue_append": "queueAppend",
    "desktop_bridge_codex_frontmost": "codexFrontmost",
    "desktop_bridge_codex_windows": "codexWindows",
    "desktop_bridge_codex_threads": "codexThreads",
    "desktop_bridge_codex_thread_map": "codexThreadMap",
    "desktop_bridge_codex_send_visible_message": "codexSendVisibleMessage",
    "desktop_bridge_codex_continue_thread": "codexContinueThread",
    "desktop_bridge_codex_select_thread": "codexSelectThread",
    "desktop_bridge_codex_snapshot": "codexSnapshot",
    "desktop_bridge_codex_inspect": "codexInspect",
    "desktop_bridge_codex_ax_tree": "codexAxTree",
    "desktop_bridge_codex_app_server_status": "codexAppServerStatus",
    "desktop_bridge_codex_app_server_remote_control_status": "codexAppServerRemoteControlStatus",
    "desktop_bridge_codex_app_server_threads": "codexAppServerThreads",
    "desktop_bridge_codex_connections_status": "codexConnectionsStatus",
    "desktop_bridge_codex_app_server_loaded_threads": "codexAppServerLoadedThreads",
    "desktop_bridge_codex_live_status": "codexLiveStatus",
    "customer_mac_status": "customerMacStatus",
    "customer_mac_capabilities": "customerMacCapabilities",
    "customer_mac_snapshot": "customerMacSnapshot",
    "customer_mac_ax_tree": "customerMacAxTree",
    "customer_mac_app_focus": "customerMacAppFocus",
    "customer_mac_local_site_open": "customerMacLocalSiteOpen",
    "customer_mac_local_site_action": "customerMacLocalSiteAction",
    "customer_mac_iphone_mirroring_status": "customerMacIphoneMirroringStatus",
    "customer_mac_iphone_mirroring_focus": "customerMacIphoneMirroringFocus",
    "customer_mac_iphone_mirroring_home": "customerMacIphoneMirroringHome",
    "customer_mac_iphone_mirroring_app_switcher": "customerMacIphoneMirroringAppSwitcher",
    "customer_mac_iphone_mirroring_spotlight": "customerMacIphoneMirroringSpotlight",
    "customer_mac_iphone_mirroring_type_spotlight": "customerMacIphoneMirroringTypeSpotlight",
    "customer_mac_iphone_mirroring_open_app": "customerMacIphoneMirroringOpenApp",
    "customer_mac_iphone_mirroring_tap_named_target": "customerMacIphoneMirroringTapNamedTarget",
    "customer_mac_iphone_mirroring_scroll": "customerMacIphoneMirroringScroll",
    "customer_mac_iphone_mirroring_swipe_left": "customerMacIphoneMirroringSwipeLeft",
    "customer_mac_iphone_mirroring_swipe_right": "customerMacIphoneMirroringSwipeRight",
    "customer_mac_iphone_mirroring_swipe_up": "customerMacIphoneMirroringSwipeUp",
    "customer_mac_iphone_mirroring_swipe_down": "customerMacIphoneMirroringSwipeDown",
    "customer_mac_iphone_mirroring_type_approved_text": "customerMacIphoneMirroringTypeApprovedText",
    "customer_mac_iphone_mirroring_send_approved_message": "customerMacIphoneMirroringSendApprovedMessage",
    "customer_mac_screen_sharing_status": "customerMacScreenSharingStatus",
    "desktop_control_status": "customerMacControlStatus",
    "desktop_control_start": "customerMacControlStart",
    "desktop_control_stop": "customerMacControlStop",
    "desktop_kill_switch": "customerMacControlKillSwitch",
    "desktop_see": "desktopSee",
    "desktop_click": "desktopClick",
    "desktop_type": "desktopType",
    "desktop_set_value": "desktopSetValue",
    "desktop_scroll": "desktopScroll",
    "desktop_drag": "desktopDrag",
    "desktop_hotkey": "desktopHotkey",
    "desktop_focus_app": "desktopFocusApp",
    "desktop_window": "desktopWindow",
    "desktop_menu": "desktopMenu",
    "desktop_browser_action": "desktopBrowserAction",
    "iphone_see": "iphoneSee",
    "iphone_tap": "iphoneTap",
    "iphone_swipe": "iphoneSwipe",
    "iphone_type": "iphoneType",
}


def normalize_connector_command(command: str) -> str:
    return CONNECTOR_COMMAND_ALIASES.get(command, command)


CONNECTOR_COMMAND_APPROVAL: dict[str, tuple[str, tuple[str, ...]]] = {
    "codexSelectThread": ("codex.select_thread", ("thread_id",)),
    "codexSendVisibleMessage": ("codex.send_visible_message", ("thread_id", "message_hash")),
    "codexContinueThread": ("codex.continue_thread", ("title", "prompt")),
    "customerMacAppFocus": ("customer_mac.app_focus", ("app_name",)),
    "customerMacLocalSiteOpen": ("customer_mac.local_site_open", ("url",)),
    "customerMacLocalSiteAction": ("customer_mac.local_site_action", ("action",)),
    "customerMacIphoneMirroringFocus": ("customer_mac.iphone_mirroring_focus", ()),
    "customerMacIphoneMirroringHome": ("customer_mac.iphone_mirroring_home", ()),
    "customerMacIphoneMirroringAppSwitcher": ("customer_mac.iphone_mirroring_app_switcher", ()),
    "customerMacIphoneMirroringSpotlight": ("customer_mac.iphone_mirroring_spotlight", ()),
    "customerMacIphoneMirroringTypeSpotlight": ("customer_mac.iphone_mirroring_type_spotlight", ("text",)),
    "customerMacIphoneMirroringOpenApp": ("customer_mac.iphone_mirroring_open_app", ("app_name",)),
    "customerMacIphoneMirroringTapNamedTarget": ("customer_mac.iphone_mirroring_tap_named_target", ("target_label",)),
    "customerMacIphoneMirroringScroll": ("customer_mac.iphone_mirroring_scroll", ("direction",)),
    "customerMacIphoneMirroringSwipeLeft": ("customer_mac.iphone_mirroring_swipe_left", ()),
    "customerMacIphoneMirroringSwipeRight": ("customer_mac.iphone_mirroring_swipe_right", ()),
    "customerMacIphoneMirroringSwipeUp": ("customer_mac.iphone_mirroring_swipe_up", ()),
    "customerMacIphoneMirroringSwipeDown": ("customer_mac.iphone_mirroring_swipe_down", ()),
    "customerMacIphoneMirroringTypeApprovedText": ("customer_mac.iphone_mirroring_type_approved_text", ("text",)),
    "customerMacIphoneMirroringSendApprovedMessage": ("customer_mac.iphone_mirroring_send_approved_message", ("text", "recipient_context", "target_label")),
    "desktopClick": ("customer_mac.desktop_click", ("snapshot_id", "element_id", "target_label", "x", "y")),
    "desktopType": ("customer_mac.desktop_type", ("text",)),
    "desktopSetValue": ("customer_mac.desktop_set_value", ("snapshot_id", "element_id", "attribute", "value_hash")),
    "desktopScroll": ("customer_mac.desktop_scroll", ("direction", "amount")),
    "desktopDrag": ("customer_mac.desktop_drag", ("from_x", "from_y", "to_x", "to_y")),
    "desktopHotkey": ("customer_mac.desktop_hotkey", ("keys",)),
    "desktopFocusApp": ("customer_mac.desktop_focus_app", ("app_name",)),
    "desktopWindow": ("customer_mac.desktop_window", ("action",)),
    "desktopMenu": ("customer_mac.desktop_menu", ("menu_path",)),
    "desktopBrowserAction": ("customer_mac.desktop_browser_action", ("action", "url")),
    "iphoneTap": ("customer_mac.iphone_tap", ("snapshot_id", "element_id", "target_label", "x", "y")),
    "iphoneSwipe": ("customer_mac.iphone_swipe", ("direction",)),
    "iphoneType": ("customer_mac.iphone_type", ("text",)),
}


def build_bridge_argv(command: str, params: dict[str, Any] | None = None) -> list[str]:
    command = normalize_connector_command(command)
    params = params or {}
    fixed: dict[str, list[str]] = {
        "status": ["status", "--json"],
        "capabilities": ["capabilities", "--json"],
        "latest": ["latest", "--json"],
        "codexFrontmost": ["codex", "frontmost", "--json"],
        "codexWindows": ["codex", "windows", "--json"],
        "codexConnectionsStatus": ["codex", "connections", "status", "--json"],
        "codexAppServerStatus": ["codex", "app-server", "status", "--json"],
        "codexAppServerRemoteControlStatus": ["codex", "app-server", "remote-control-status", "--json"],
        "customerMacStatus": ["customer-mac", "status", "--json"],
        "customerMacCapabilities": ["customer-mac", "capabilities", "--json"],
        "customerMacControlStatus": ["customer-mac", "control", "status", "--json"],
        "customerMacControlStop": ["customer-mac", "control", "stop", "--json"],
        "customerMacControlKillSwitch": ["customer-mac", "control", "kill-switch", "--json"],
        "customerMacIphoneMirroringStatus": ["customer-mac", "iphone-mirroring", "status", "--json"],
        "customerMacScreenSharingStatus": ["customer-mac", "screen-sharing", "status", "--json"],
    }
    if command in fixed:
        return fixed[command]
    if command == "auditTail":
        return ["audit-tail", "--json", "--limit", str(_clamp_int(params.get("limit"), 20, 1, 100))]
    if command == "queueList":
        return ["queue", "list", "--json", "--limit", str(_clamp_int(params.get("limit"), 20, 1, 100))]
    if command == "queueAppend":
        argv = [
            "queue",
            "append",
            "--json",
            "--kind",
            _required_string(params, "kind"),
            "--source-audit-id",
            _required_string(params, "source_audit_id"),
        ]
        if params.get("message"):
            argv.extend(["--message", str(params["message"])])
        return argv
    if command == "codexThreads":
        return ["codex", "threads", "--json", "--max-items", str(_clamp_int(params.get("max_items"), 50, 1, 200))]
    if command == "codexThreadMap":
        return ["codex", "thread-map", "--json", "--max-items", str(_clamp_int(params.get("max_items"), 50, 1, 200))]
    if command == "codexSelectThread":
        return [
            "codex",
            "select-thread",
            "--json",
            "--thread-id",
            _required_string(params, "thread_id"),
            *_dry_run_arg(params),
            *_approval_arg(params),
        ]
    if command == "codexContinueThread":
        return [
            "codex",
            "continue-thread",
            "--json",
            "--title",
            _required_string(params, "title"),
            "--prompt",
            str(params.get("prompt") or "continue"),
            *_dry_run_arg(params),
            *_approval_arg(params),
        ]
    if command == "codexSendVisibleMessage":
        argv = [
            "codex",
            "send-visible-message",
            "--json",
            "--thread-id",
            _required_string(params, "thread_id"),
        ]
        message_file = params.get("message_file")
        if isinstance(message_file, str) and message_file.strip():
            if params.get("_prepared_message_file") is not True:
                raise ValueError("message_file is reserved for connector internals; provide message.")
            argv.extend(["--message-file", message_file.strip()])
        else:
            argv.extend(["--message", _required_string(params, "message")])
        if params.get("dry_run") is False:
            argv.append("--live")
            if params.get("confirm") is True:
                argv.append("--confirm")
        else:
            argv.append("--dry-run")
        argv.extend(_approval_arg(params))
        if params.get("wait_ms") is not None:
            argv.extend(["--wait-ms", str(_clamp_int(params.get("wait_ms"), 0, 0, 120_000))])
        if params.get("poll_interval_ms") is not None:
            argv.extend(["--poll-interval-ms", str(_clamp_int(params.get("poll_interval_ms"), 2000, 250, 10_000))])
        return argv
    if command == "codexSnapshot":
        return ["codex", "snapshot", "--json", "--max-chars", str(_clamp_int(params.get("max_chars"), 4000, 1, 20000))]
    if command == "codexInspect":
        return ["codex", "inspect", "--json", "--max-nodes", str(_clamp_int(params.get("max_nodes"), 120, 1, 1000))]
    if command == "codexAxTree":
        return ["codex", "ax-tree", "--json", "--max-nodes", str(_clamp_int(params.get("max_nodes"), 200, 1, 1000))]
    if command == "codexAppServerThreads":
        return ["codex", "app-server", "threads", "--json", "--max-items", str(_clamp_int(params.get("max_items"), 50, 1, 200))]
    if command == "codexAppServerLoadedThreads":
        return ["codex", "app-server", "loaded-threads", "--json", "--max-items", str(_clamp_int(params.get("max_items"), 50, 1, 200))]
    if command == "codexLiveStatus":
        return [
            "codex",
            "app-server",
            "subscribe",
            "--json",
            "--thread-id",
            _required_string(params, "thread_id"),
            "--duration-ms",
            str(_clamp_int(params.get("duration_ms"), 1000, 1, 30000)),
        ]
    if command == "customerMacSnapshot":
        return ["customer-mac", "snapshot", "--json", "--max-chars", str(_clamp_int(params.get("max_chars"), 4000, 1, 20000))]
    if command == "customerMacAxTree":
        return ["customer-mac", "ax-tree", "--json", "--max-nodes", str(_clamp_int(params.get("max_nodes"), 200, 1, 1000))]
    if command == "customerMacControlStart":
        return ["customer-mac", "control", "start", "--json", "--mode", str(params.get("mode") or "full-access"), *(_optional_string_arg(params, "agent_label", "--agent-label"))]
    if command == "desktopSee":
        return [
            "customer-mac",
            "desktop",
            "see",
            "--json",
            "--max-chars",
            str(_clamp_int(params.get("max_chars"), 4000, 1, 20000)),
            "--max-nodes",
            str(_clamp_int(params.get("max_nodes"), 200, 1, 1000)),
        ]
    if command == "desktopClick":
        argv = ["customer-mac", "desktop", "click", "--json", *_dry_run_arg(params), *_approval_arg(params)]
        argv.extend(_optional_string_arg(params, "snapshot_id", "--snapshot-id"))
        argv.extend(_optional_string_arg(params, "element_id", "--element-id"))
        argv.extend(_optional_string_arg(params, "target_label", "--target-label"))
        argv.extend(_optional_int_arg(params, "x", "--x"))
        argv.extend(_optional_int_arg(params, "y", "--y"))
        return argv
    if command == "desktopType":
        return ["customer-mac", "desktop", "type", "--json", "--text", _required_string(params, "text"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "desktopSetValue":
        argv = [
            "customer-mac",
            "desktop",
            "set-value",
            "--json",
            "--snapshot-id",
            _required_string(params, "snapshot_id"),
            "--element-id",
            _required_string(params, "element_id"),
        ]
        value_file = params.get("value_file")
        if isinstance(value_file, str) and value_file.strip():
            if params.get("_prepared_value_file") is not True:
                raise ValueError("value_file is reserved for connector internals; provide value.")
            argv.extend(["--value-file", value_file.strip()])
        else:
            raise ValueError("desktopSetValue value must be materialized before building CLI argv.")
        argv.extend(["--attribute", str(params.get("attribute") or "value")])
        argv.extend(_dry_run_arg(params))
        argv.extend(_approval_arg(params))
        return argv
    if command == "desktopScroll":
        return ["customer-mac", "desktop", "scroll", "--json", "--direction", str(params.get("direction") or "down"), "--amount", str(_clamp_int(params.get("amount"), 600, 1, 5000)), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "desktopDrag":
        return [
            "customer-mac",
            "desktop",
            "drag",
            "--json",
            "--from-x",
            str(_required_int(params, "from_x")),
            "--from-y",
            str(_required_int(params, "from_y")),
            "--to-x",
            str(_required_int(params, "to_x")),
            "--to-y",
            str(_required_int(params, "to_y")),
            *_dry_run_arg(params),
            *_approval_arg(params),
        ]
    if command == "desktopHotkey":
        return ["customer-mac", "desktop", "hotkey", "--json", "--keys", _required_string(params, "keys"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "desktopFocusApp":
        return ["customer-mac", "desktop", "focus-app", "--json", "--app-name", _required_string(params, "app_name"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "desktopWindow":
        return ["customer-mac", "desktop", "window", "--json", "--action", _required_string(params, "action"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "desktopMenu":
        return ["customer-mac", "desktop", "menu", "--json", "--menu-path", _required_string(params, "menu_path"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "desktopBrowserAction":
        argv = ["customer-mac", "desktop", "browser-action", "--json", "--action", _required_string(params, "action"), *_dry_run_arg(params), *_approval_arg(params)]
        argv.extend(_optional_string_arg(params, "url", "--url"))
        return argv
    if command == "customerMacAppFocus":
        return ["customer-mac", "app-focus", "--json", "--app-name", _required_string(params, "app_name"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacLocalSiteOpen":
        return ["customer-mac", "local-site", "open", "--json", "--url", _required_string(params, "url"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacLocalSiteAction":
        return ["customer-mac", "local-site", "action", "--json", "--action", _required_string(params, "action"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringFocus":
        return ["customer-mac", "iphone-mirroring", "focus", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "iphoneSee":
        return [
            "customer-mac",
            "iphone-mirroring",
            "see",
            "--json",
            "--max-chars",
            str(_clamp_int(params.get("max_chars"), 4000, 1, 20000)),
            "--max-nodes",
            str(_clamp_int(params.get("max_nodes"), 200, 1, 1000)),
        ]
    if command == "iphoneTap":
        argv = ["customer-mac", "iphone-mirroring", "tap", "--json", *_dry_run_arg(params), *_approval_arg(params)]
        argv.extend(_optional_string_arg(params, "snapshot_id", "--snapshot-id"))
        argv.extend(_optional_string_arg(params, "element_id", "--element-id"))
        argv.extend(_optional_string_arg(params, "target_label", "--target-label"))
        argv.extend(_optional_int_arg(params, "x", "--x"))
        argv.extend(_optional_int_arg(params, "y", "--y"))
        return argv
    if command == "iphoneSwipe":
        return ["customer-mac", "iphone-mirroring", "swipe", "--json", "--direction", _required_string(params, "direction"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "iphoneType":
        return ["customer-mac", "iphone-mirroring", "type", "--json", "--text", _required_string(params, "text"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringHome":
        return ["customer-mac", "iphone-mirroring", "home", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringAppSwitcher":
        return ["customer-mac", "iphone-mirroring", "app-switcher", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSpotlight":
        return ["customer-mac", "iphone-mirroring", "spotlight", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringTypeSpotlight":
        return ["customer-mac", "iphone-mirroring", "type-spotlight", "--json", "--text", _required_string(params, "text"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringOpenApp":
        return ["customer-mac", "iphone-mirroring", "open-app", "--json", "--app-name", _required_string(params, "app_name"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringTapNamedTarget":
        return [
            "customer-mac",
            "iphone-mirroring",
            "tap-named-target",
            "--json",
            "--target-label",
            _required_string(params, "target_label"),
            *_dry_run_arg(params),
            *_approval_arg(params),
        ]
    if command == "customerMacIphoneMirroringScroll":
        return ["customer-mac", "iphone-mirroring", "scroll", "--json", "--direction", str(params.get("direction") or "down"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSwipeLeft":
        return ["customer-mac", "iphone-mirroring", "swipe-left", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSwipeRight":
        return ["customer-mac", "iphone-mirroring", "swipe-right", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSwipeUp":
        return ["customer-mac", "iphone-mirroring", "swipe-up", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSwipeDown":
        return ["customer-mac", "iphone-mirroring", "swipe-down", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringTypeApprovedText":
        return ["customer-mac", "iphone-mirroring", "type-approved-text", "--json", "--text", _required_string(params, "text"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSendApprovedMessage":
        return [
            "customer-mac",
            "iphone-mirroring",
            "send-approved-message",
            "--json",
            "--text",
            _required_string(params, "text"),
            "--recipient-context",
            _required_string(params, "recipient_context"),
            "--target-label",
            str(params.get("target_label") or "Send"),
            *_dry_run_arg(params),
            *_approval_arg(params),
        ]
    raise ValueError(f"Unsupported connector command: {command}")


def _prepare_connector_params(command: str, params: dict[str, Any], *, state_dir: Path | None) -> tuple[dict[str, Any], list[Path]]:
    command = normalize_connector_command(command)
    if command not in {"codexSendVisibleMessage", "desktopSetValue"}:
        return params, []
    if command == "codexSendVisibleMessage":
        if isinstance(params.get("message_file"), str) and params.get("message_file", "").strip():
            raise ValueError("message_file is reserved for connector internals; provide message.")
        if not isinstance(params.get("message"), str):
            raise ValueError("message is required")
        payload_key = "message"
        file_key = "message_file"
        prepared_flag = "_prepared_message_file"
        prefix = "codex-visible-message-"
    else:
        if isinstance(params.get("value_file"), str) and params.get("value_file", "").strip():
            raise ValueError("value_file is reserved for connector internals; provide value.")
        if not isinstance(params.get("value"), str):
            raise ValueError("value is required")
        payload_key = "value"
        file_key = "value_file"
        prepared_flag = "_prepared_value_file"
        prefix = "desktop-set-value-"
    root = (state_dir or default_state_dir()) / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    fd, path_text = tempfile.mkstemp(prefix=prefix, suffix=".txt", dir=str(root), text=True)
    path = Path(path_text)
    try:
        try:
            os.write(fd, str(params[payload_key]).encode("utf-8"))
        finally:
            os.close(fd)
        os.chmod(path, 0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    prepared = dict(params)
    prepared.pop(payload_key, None)
    prepared[file_key] = str(path)
    prepared[prepared_flag] = True
    return prepared, [path]


def run_connector_server(
    *,
    host: str,
    port: int,
    token: str | None,
    command_runner: CommandRunner,
    state_dir: Path | None = None,
) -> None:
    handler = _make_handler(token=token, command_runner=command_runner, state_dir=state_dir)
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever()


def read_token(path: str | None, *, state_dir: Path | None = None, auto_create: bool = False) -> str | None:
    if not path:
        if not auto_create:
            return None
        token_path = (state_dir or default_state_dir()) / "connector.token"
    else:
        token_path = Path(path).expanduser()
    if not token_path.exists():
        if not auto_create:
            raise ValueError(f"connector token file does not exist: {token_path}")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(48)
        token_path.write_text(token + "\n", encoding="utf-8")
        os.chmod(token_path, 0o600)
        return token
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        if not auto_create:
            raise ValueError(f"connector token file is empty: {token_path}")
        token = secrets.token_urlsafe(48)
        token_path.write_text(token + "\n", encoding="utf-8")
        os.chmod(token_path, 0o600)
    return token


def _make_handler(*, token: str | None, command_runner: CommandRunner, state_dir: Path | None = None) -> type[BaseHTTPRequestHandler]:
    class ConnectorHandler(BaseHTTPRequestHandler):
        server_version = "evaos-desktop-bridge-connector/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._write_json(200, {"ok": True, "service": "evaos-desktop-bridge-connector"})
                return
            if parsed.path.startswith("/v1/artifacts/"):
                self._serve_artifact(parsed.path.removeprefix("/v1/artifacts/"))
                return
            self._write_json(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/v1/enrollment/complete":
                self._complete_enrollment()
                return
            if parsed.path != "/v1/commands":
                self._write_json(404, {"ok": False, "error": "not_found"})
                return
            if not self._authorized():
                self._write_json(401, _error_envelope("connector.unauthorized", "connector", "connector_unauthorized", "Missing or invalid connector token."))
                return
            try:
                payload = self._read_json()
                command = normalize_connector_command(str(payload.get("command") or ""))
                params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
                kill_switch_error = _remote_kill_switch_error(command, state_dir=state_dir)
                if kill_switch_error is not None:
                    self._write_json(
                        403,
                        _error_envelope(
                            command or "connector.command",
                            "customer_mac",
                            "control_kill_switch_active",
                            kill_switch_error,
                        ),
                    )
                    return
                approval_error = _live_guarded_approval_error(command, params, state_dir=state_dir)
                if approval_error is not None:
                    if "kill switch" in approval_error.lower():
                        error_code = "control_kill_switch_active"
                    elif "takeover warning" in approval_error.lower():
                        error_code = "control_takeover_warning_active"
                    else:
                        error_code = "approval_audit_required"
                    self._write_json(
                        403,
                        _error_envelope(
                            command or "connector.command",
                            _target_for_connector_command(command),
                            error_code,
                            approval_error,
                        ),
                    )
                    return
                prepared_params, temp_paths = _prepare_connector_params(command, params, state_dir=state_dir)
                try:
                    argv = build_bridge_argv(command, prepared_params)
                    exit_code, output = command_runner(argv)
                finally:
                    for temp_path in temp_paths:
                        try:
                            temp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                try:
                    response = json.loads(output)
                except json.JSONDecodeError:
                    response = _error_envelope(command, "desktop", "bridge_output_invalid", output[:500])
                status = 200 if exit_code == 0 else 422
                self._write_json(status, response)
            except Exception as exc:
                self._write_json(400, _error_envelope("connector.command", "desktop", "connector_bad_request", str(exc)))

        def _complete_enrollment(self) -> None:
            try:
                payload = self._read_json()
                enrollment_code = str(payload.get("enrollment_code") or "").strip()
                if not enrollment_code:
                    self._write_json(400, {"ok": False, "error": "missing_enrollment_code"})
                    return
                if not token:
                    self._write_json(503, {"ok": False, "error": "connector_token_unavailable"})
                    return
                connector_url = _connector_url_from_request(self)
                response = complete_enrollment_via_control(
                    enrollment_code=enrollment_code,
                    connector_url=connector_url,
                    connector_token=token,
                    device_name=str(payload.get("device_name") or socket.gethostname() or "Customer Mac"),
                    device_identifier=str(payload.get("device_identifier") or ""),
                )
                self._write_json(200, {"ok": True, "data": response})
            except Exception as exc:
                self._write_json(400, {"ok": False, "error": "enrollment_complete_failed", "message": str(exc)})

        def _serve_artifact(self, artifact_name: str) -> None:
            if not self._authorized():
                self._write_json(401, _error_envelope("connector.artifact", "customer_mac", "connector_unauthorized", "Missing or invalid connector token."))
                return
            artifact_id = artifact_name.removesuffix(".png")
            if not artifact_id.startswith("snap-") or "/" in artifact_id or ".." in artifact_id:
                self._write_json(404, {"ok": False, "error": "artifact_not_found"})
                return
            root = state_dir or default_state_dir()
            path = root / "artifacts" / f"{artifact_id}.png"
            if not path.exists():
                self._write_json(404, {"ok": False, "error": "artifact_not_found"})
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return False
            supplied = header.removeprefix("Bearer ").strip()
            return bool(token) and secrets.compare_digest(supplied, token)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 65536:
                raise ValueError("request body too large")
            data = self.rfile.read(length)
            parsed = json.loads(data.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("request body must be a JSON object")
            return parsed

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ConnectorHandler


def complete_enrollment_via_control(
    *,
    enrollment_code: str,
    connector_url: str,
    connector_token: str,
    device_name: str,
    device_identifier: str = "",
) -> dict[str, Any]:
    body = {
        "action": "complete_enrollment",
        "enrollment_code": enrollment_code,
        "device_name": device_name,
        "device_identifier": device_identifier or None,
        "connector_url": connector_url,
        "connector_token": connector_token,
        "tailnet_ip": _host_without_port(connector_url),
        "capabilities": {
            "connector": "evaos-desktop-bridge",
            "openclaw_tools": "enabled",
            "desktop_control": "full_access_or_ask_permission",
            "iphone_mirroring": "visible_control_surface",
        },
        "permission_state": {
            "accessibility": "check_required",
            "screen_recording": "check_required",
        },
    }
    request = urllib.request.Request(
        CUSTOMER_MAC_CONTROL_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:  # noqa: S310 - fixed service URL or explicit env override.
        data = response.read()
    parsed = json.loads(data.decode("utf-8"))
    return parsed if isinstance(parsed, dict) else {"response": parsed}


def _connector_url_from_request(handler: BaseHTTPRequestHandler) -> str:
    host = (handler.headers.get("Host") or "").strip()
    if not host:
        server_host, server_port = handler.server.server_address[:2]
        host = f"{server_host}:{server_port}"
    return f"http://{host}"


def _host_without_port(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host or host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return None
    return host


def _live_guarded_without_approval(command: str, params: dict[str, Any]) -> bool:
    command = normalize_connector_command(command)
    if command not in GUARDED_REMOTE_COMMANDS:
        return False
    if params.get("dry_run") is not False:
        return False
    if command in CODEX_REMOTE_CONTROL_COMMANDS:
        source = params.get("source_audit_id")
        return params.get("confirm") is not True or not isinstance(source, str) or not source.strip().startswith("audit-")
    approval = params.get("approval_audit_id")
    return not isinstance(approval, str) or not approval.strip()


def _live_guarded_approval_error(command: str, params: dict[str, Any], *, state_dir: Path | None, require_lookup: bool = True) -> str | None:
    command = normalize_connector_command(command)
    if command in TAKEOVER_WARNING_REMOTE_COMMANDS and params.get("dry_run") is False:
        session = read_control_session(state_dir)
        if session.get("kill_switch") is True:
            return "The customer Mac kill switch is active; live agent control commands are blocked."
        warning = session.get("takeover_warning") if isinstance(session.get("takeover_warning"), dict) else {}
        if session.get("active") is True and warning.get("active") is True:
            seconds = warning.get("seconds") if isinstance(warning.get("seconds"), int) else 10
            return f"Agent control is starting; live actions are blocked until the {seconds}-second takeover warning finishes."
        if command in CONTROLLED_REMOTE_COMMANDS and session.get("active") is True:
            if session.get("mode") == "full_access":
                return None
            if session.get("mode") == "ask_permission" and not _ask_permission_requires_approval(command, params):
                return None

    if command not in GUARDED_REMOTE_COMMANDS:
        return None
    if params.get("dry_run") is not False:
        return None
    if command == "codexSendVisibleMessage" and params.get("confirm") is not True:
        return "Live Codex visible message actions require confirm=true."
    if command in CODEX_REMOTE_CONTROL_COMMANDS:
        source = params.get("source_audit_id")
        if params.get("confirm") is not True:
            return "Live Codex remote-control actions require confirm=true."
        if not isinstance(source, str) or not source.strip().startswith("audit-"):
            return "Live Codex remote-control actions require source_audit_id from a dry-run or evidence command."
        command_id, fields = CODEX_REMOTE_CONTROL_APPROVAL[command]
        record = read_audit_record(source.strip(), state_dir=state_dir)
        if record is None:
            return "source_audit_id was not found in the local audit log."
        if record.get("command") != command_id or record.get("ok") is not True:
            return "source_audit_id does not reference a successful dry-run for this command."
        record_args = record.get("args")
        if not isinstance(record_args, dict) or record_args.get("dry_run") is not True:
            return "source_audit_id must reference a dry-run record."
        freshness_error = approval_audit_freshness_error(record)
        if freshness_error is not None:
            return freshness_error.replace("approval_audit_id", "source_audit_id")
        for field in fields:
            if record_args.get(field) != _approval_field_value(command, params, field):
                return f"source_audit_id does not match {field}."
        return None
    approval = params.get("approval_audit_id")
    if not isinstance(approval, str) or not approval.strip():
        return "Live remote control actions require a prior dry-run and approval_audit_id."
    if not require_lookup:
        return None
    command_id, fields = CONNECTOR_COMMAND_APPROVAL[command]
    record = read_audit_record(approval.strip(), state_dir=state_dir)
    if record is None:
        return "approval_audit_id was not found in the local audit log."
    if record.get("command") != command_id or record.get("ok") is not True:
        return "approval_audit_id does not reference a successful dry-run for this command."
    record_args = record.get("args")
    if not isinstance(record_args, dict) or record_args.get("dry_run") is not True:
        return "approval_audit_id must reference a dry-run record."
    freshness_error = approval_audit_freshness_error(record)
    if freshness_error is not None:
        return freshness_error
    for field in fields:
        if record_args.get(field) != _approval_field_value(command, params, field):
            return f"approval_audit_id does not match {field}."
    return None


def _remote_kill_switch_error(command: str, *, state_dir: Path | None) -> str | None:
    command = normalize_connector_command(command)
    if command in KILL_SWITCH_REMOTE_COMMAND_ALLOWLIST:
        return None
    session = read_control_session(state_dir)
    if session.get("kill_switch") is not True:
        return None
    if command == "customerMacControlStart":
        return "The customer Mac kill switch is active; only the local Workbench app can start a new control session."
    return "The customer Mac kill switch is active; remote connector commands are blocked until the local Workbench app starts a new control session."


def _ask_permission_requires_approval(command: str, params: dict[str, Any]) -> bool:
    command = normalize_connector_command(command)
    if command in ASK_PERMISSION_HIGH_IMPACT_REMOTE_COMMANDS:
        return True
    if command in {"desktopClick", "iphoneTap"}:
        label = params.get("target_label")
        if not isinstance(label, str) or not label.strip():
            return True
        return _contains_risk_word(label)
    if command == "desktopHotkey":
        keys = str(params.get("keys") or "").strip().lower().replace("command", "cmd").replace(" ", "")
        return keys not in ASK_PERMISSION_SAFE_HOTKEYS
    if command == "desktopWindow":
        return str(params.get("action") or "").strip().lower() == "close"
    if command == "desktopBrowserAction":
        return str(params.get("action") or "").strip().lower() in {"open_url"}
    if command == "desktopMenu":
        return _contains_risk_word(str(params.get("menu_path") or ""))
    return False


def _contains_risk_word(value: str) -> bool:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in value)
    words = set(normalized.split())
    return any(word in words for word in ASK_PERMISSION_RISK_WORDS)


def _approval_field_value(command: str, params: dict[str, Any], field: str) -> Any:
    if field == "prompt" and command == "codexContinueThread":
        return params.get("prompt") or "continue"
    if field == "message_hash" and command == "codexSendVisibleMessage":
        return hashlib.sha256(str(params.get("message") or "").strip().encode("utf-8")).hexdigest()[:16]
    if field == "value_hash" and command == "desktopSetValue":
        return hashlib.sha256(str(params.get("value") or "").encode("utf-8")).hexdigest()[:16]
    if field == "direction" and command == "customerMacIphoneMirroringScroll":
        return params.get("direction") or "down"
    if field == "target_label" and command == "customerMacIphoneMirroringSendApprovedMessage":
        return params.get("target_label") or "Send"
    return params.get(field)


def _optional_string_arg(params: dict[str, Any], name: str, flag: str) -> list[str]:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        return []
    return [flag, value.strip()]


def _optional_int_arg(params: dict[str, Any], name: str, flag: str) -> list[str]:
    value = params.get(name)
    if value is None:
        return []
    return [flag, str(_required_int(params, name))]


def _required_int(params: dict[str, Any], name: str) -> int:
    value = params.get(name)
    if isinstance(value, bool):
        raise ValueError(f"{name} is required")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} is required") from None


def _dry_run_arg(params: dict[str, Any]) -> list[str]:
    return ["--dry-run"] if params.get("dry_run") is not False else []


def _approval_arg(params: dict[str, Any]) -> list[str]:
    approval = params.get("approval_audit_id")
    if not isinstance(approval, str) or not approval.strip():
        return []
    return ["--approval-audit-id", approval.strip()]


def _codex_remote_control_args(params: dict[str, Any]) -> list[str]:
    if params.get("dry_run") is not False:
        return ["--dry-run"]
    argv = ["--live"]
    if params.get("confirm") is True:
        argv.append("--confirm")
    source = params.get("source_audit_id")
    if isinstance(source, str) and source.strip():
        argv.extend(["--source-audit-id", source.strip()])
    return argv


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _required_string(params: dict[str, Any], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _error_envelope(command: str, target: str, code: str, message: str) -> dict[str, Any]:
    return build_envelope(
        command=command,
        target=target,
        ok=False,
        data={},
        warnings=[],
        errors=[make_error(code=code, message=message, guidance="Check connector pairing, command shape, and approval state.")],
        audit_id="connector-rejected",
    )


def _target_for_connector_command(command: str | None) -> str:
    if isinstance(command, str):
        if command.startswith("customerMac"):
            return "customer_mac"
        if command.startswith("codex"):
            return "codex"
    return "desktop"
