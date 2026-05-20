from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from ..audit import default_state_dir
from ..redaction import cap_text, redact_value
from ..schema import make_error, timestamp_utc
from ..types import CommandResult
from .codex_macos import (
    ACCESSIBILITY_GUIDANCE,
    SCREEN_RECORDING_GUIDANCE,
    RunnerResult,
    check_accessibility_trusted,
    run_command,
)

IPHONE_MIRRORING_APP = Path("/System/Applications/iPhone Mirroring.app")
SAFE_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
SAFE_BROWSER_APPS = {"Safari", "Google Chrome", "Arc", "Firefox", "Brave Browser"}
SAFE_LOCAL_SITE_ACTIONS = {"reload", "back", "forward"}
SAFE_IPHONE_ACTIONS = {
    "home",
    "app_switcher",
    "spotlight",
    "type_spotlight",
    "open_app",
    "tap_named_target",
}
SUPPORT_CANARY_ENV = "EVAOS_SUPPORT_CANARY_CONTROLS"
SUPPORT_CANARY_IPHONE_ACTIONS = {
    "scroll",
    "swipe_left",
    "swipe_right",
    "swipe_up",
    "swipe_down",
    "type_approved_text",
    "send_approved_message",
}
SUPPORT_CANARY_GESTURE_KEYS = {
    "swipe_left": "123",
    "swipe_right": "124",
    "swipe_up": "126",
    "swipe_down": "125",
}
SCROLL_DIRECTIONS = {"up": "126", "down": "125"}
DISABLED_IPHONE_ACTIONS = {"scroll", "swipe_left", "swipe_right", "swipe_up", "swipe_down", "type_approved_text", "send_approved_message"}
SENSITIVE_APPS = {
    "1Password",
    "App Store",
    "Keychain Access",
    "Password",
    "Passwords",
    "Wallet",
    "FaceTime",
    "Messages",
    "Mail",
    "Signal",
    "Telegram",
    "WhatsApp",
    "Camera",
    "Photo Booth",
    "System Settings",
}
SENSITIVE_IPHONE_APPS = SENSITIVE_APPS | {
    "App Store",
    "Authenticator",
    "Bank",
    "Camera",
    "Contacts",
    "FaceTime",
    "Find My",
    "Health",
    "Home",
    "Keychain",
    "Mail",
    "Messages",
    "Phone",
    "Photos",
    "Safari",
    "Settings",
    "Shortcuts",
    "Wallet",
}
DANGEROUS_IPHONE_TARGET_RE = re.compile(
    r"\b("
    r"allow|approve|authenticate|buy|call|camera|checkout|confirm|continue with apple|"
    r"delete|facetime|log in|login|microphone|pay|purchase|record|send|share|"
    r"sign in|signin|subscribe|transfer|unlock"
    r")\b",
    re.IGNORECASE,
)
SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9 ._+@:/#-]{1,80}$")
APPROVED_TEXT_RE = re.compile(r"^[^\r\n]{1,240}$")


class CustomerMacObserver:
    AX_TREE_SCRIPT = """
import json
import sys

pid = int(sys.argv[1])
max_nodes = int(sys.argv[2])

try:
    import ApplicationServices as AS
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"pyobjc_missing: {exc}"}))
    raise SystemExit(0)


def ax_value(element, attr):
    try:
        err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    except Exception:
        return None
    if err != 0:
        return None
    return value


def text_value(value):
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def rect_value(element):
    pos = ax_value(element, AS.kAXPositionAttribute)
    size = ax_value(element, AS.kAXSizeAttribute)
    try:
        return {"x": int(pos.x), "y": int(pos.y), "width": int(size.width), "height": int(size.height)}
    except Exception:
        return None


def actions(element):
    try:
        err, names = AS.AXUIElementCopyActionNames(element, None)
    except Exception:
        return []
    if err != 0:
        return []
    try:
        return [str(item) for item in list(names)]
    except Exception:
        return []


def walk(element, rows, depth=0, window_index=None):
    if len(rows) >= max_nodes:
        return True
    role = text_value(ax_value(element, AS.kAXRoleAttribute)) or "unknown"
    name = text_value(ax_value(element, AS.kAXTitleAttribute)) or text_value(ax_value(element, AS.kAXDescriptionAttribute))
    rows.append({
        "role": role,
        "name": name,
        "depth": depth,
        "window_index": window_index,
        "bounds": rect_value(element),
        "actions": actions(element),
    })
    children = ax_value(element, AS.kAXChildrenAttribute) or []
    try:
        child_iter = list(children)
    except Exception:
        child_iter = []
    for child in child_iter:
        if walk(child, rows, depth + 1, window_index):
            return True
    return False


app = AS.AXUIElementCreateApplication(pid)
windows = ax_value(app, AS.kAXWindowsAttribute) or []
try:
    windows_list = list(windows)
except Exception:
    windows_list = []

nodes = []
truncated = False
for idx, window in enumerate(windows_list):
    truncated = walk(window, nodes, 0, idx) or truncated

print(json.dumps({"ok": True, "nodes": nodes, "truncated": truncated}))
""".strip()

    AX_PRESS_LABEL_SCRIPT = """
import json
import sys

pid = int(sys.argv[1])
label = sys.argv[2]
max_nodes = int(sys.argv[3])
press = sys.argv[4] == "1"

try:
    import ApplicationServices as AS
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"pyobjc_missing: {exc}"}))
    raise SystemExit(0)


def ax_value(element, attr):
    try:
        err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    except Exception:
        return None
    if err != 0:
        return None
    return value


def text_value(value):
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def rect_value(element):
    pos = ax_value(element, AS.kAXPositionAttribute)
    size = ax_value(element, AS.kAXSizeAttribute)
    try:
        return {"x": int(pos.x), "y": int(pos.y), "width": int(size.width), "height": int(size.height)}
    except Exception:
        return None


def action_names(element):
    try:
        err, names = AS.AXUIElementCopyActionNames(element, None)
    except Exception:
        return []
    if err != 0:
        return []
    try:
        return [str(item) for item in list(names)]
    except Exception:
        return []


def walk(element, rows, depth=0, window_index=None):
    if len(rows) >= max_nodes:
        return
    role = text_value(ax_value(element, AS.kAXRoleAttribute)) or "unknown"
    name = text_value(ax_value(element, AS.kAXTitleAttribute)) or text_value(ax_value(element, AS.kAXDescriptionAttribute))
    row = {"role": role, "name": name, "depth": depth, "window_index": window_index, "bounds": rect_value(element), "actions": action_names(element)}
    if name == label:
        rows.append((row, element))
    children = ax_value(element, AS.kAXChildrenAttribute) or []
    try:
        child_iter = list(children)
    except Exception:
        child_iter = []
    for child in child_iter:
        walk(child, rows, depth + 1, window_index)


app = AS.AXUIElementCreateApplication(pid)
windows = ax_value(app, AS.kAXWindowsAttribute) or []
try:
    windows_list = list(windows)
except Exception:
    windows_list = []

matches = []
for idx, window in enumerate(windows_list):
    walk(window, matches, 0, idx)

safe_matches = [row for row, _ in matches]
if press:
    if len(matches) != 1:
        print(json.dumps({"ok": False, "error": "target_label_not_unique", "matches": safe_matches}))
        raise SystemExit(0)
    row, element = matches[0]
    if "AXPress" not in row.get("actions", []):
        print(json.dumps({"ok": False, "error": "target_not_pressable", "matches": safe_matches}))
        raise SystemExit(0)
    err = AS.AXUIElementPerformAction(element, "AXPress")
    if err != 0:
        print(json.dumps({"ok": False, "error": f"ax_press_failed:{err}", "matches": safe_matches}))
        raise SystemExit(0)

print(json.dumps({"ok": True, "matches": safe_matches, "count": len(safe_matches), "pressed": press}))
""".strip()

    IPHONE_SCROLL_GESTURE_SCRIPT = """
import json
import sys

pid = int(sys.argv[1])
dx = int(sys.argv[2])
dy = int(sys.argv[3])

try:
    import ApplicationServices as AS
    import Quartz
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"pyobjc_missing: {exc}"}))
    raise SystemExit(0)


def ax_value(element, attr):
    try:
        err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    except Exception:
        return None
    if err != 0:
        return None
    return value


app = AS.AXUIElementCreateApplication(pid)
windows = ax_value(app, AS.kAXWindowsAttribute) or []
try:
    window = list(windows)[0]
except Exception:
    print(json.dumps({"ok": False, "error": "iphone_mirroring_window_not_found"}))
    raise SystemExit(0)

pos = ax_value(window, AS.kAXPositionAttribute)
size = ax_value(window, AS.kAXSizeAttribute)
try:
    x = int(pos.x + size.width / 2)
    y = int(pos.y + size.height / 2)
except Exception:
    print(json.dumps({"ok": False, "error": "iphone_mirroring_window_bounds_unavailable"}))
    raise SystemExit(0)

source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateCombinedSessionState)
move = Quartz.CGEventCreateMouseEvent(source, Quartz.kCGEventMouseMoved, (x, y), Quartz.kCGMouseButtonLeft)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
event = Quartz.CGEventCreateScrollWheelEvent(source, Quartz.kCGScrollEventUnitPixel, 2, dy, dx)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
print(json.dumps({"ok": True, "posted": True, "vector": {"dx": dx, "dy": dy}}))
""".strip()

    def __init__(
        self,
        *,
        runner: Callable[[list[str], float], RunnerResult] = run_command,
        state_dir: Path | None = None,
        platform_name: str | None = None,
        accessibility_checker: Callable[[], bool | None] = check_accessibility_trusted,
        now: Callable[[], str] = timestamp_utc,
    ) -> None:
        self.runner = runner
        self.state_dir = state_dir or default_state_dir()
        self.platform_name = platform_name or platform.system()
        self.accessibility_checker = accessibility_checker
        self.now = now

    def status(self) -> CommandResult:
        frontmost = self._frontmost_app()
        mirroring_status = self.iphone_mirroring_status()
        screen_sharing = self.screen_sharing_status()
        return CommandResult(
            ok=True,
            data={
                "platform": self.platform_name,
                "device": self._device_identity(),
                "frontmost_app": redact_value(frontmost),
                "permissions": {
                    "accessibility": self._permission_status("accessibility"),
                    "screen_recording": {"status": "unknown", "guidance": SCREEN_RECORDING_GUIDANCE},
                },
                "iphone_mirroring": mirroring_status.data,
                "screen_sharing": screen_sharing.data,
                "safety": self._safety_summary(),
            },
            warnings=mirroring_status.warnings + screen_sharing.warnings,
        )

    def capabilities(self) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "supported_targets": ["mac", "local_site", "iphone_mirroring", "screen_sharing_status"],
                "actions": {
                    "mac": ["status", "capabilities", "snapshot", "ax_tree", "app_focus"],
                    "local_site": ["open", "reload", "back", "forward"],
                    "iphone_mirroring": sorted(SAFE_IPHONE_ACTIONS),
                    "iphone_mirroring_support_canary": sorted(SUPPORT_CANARY_IPHONE_ACTIONS),
                    "screen_sharing": ["status"],
                },
                "experimental_or_disabled": {
                    "iphone_mirroring": sorted(DISABLED_IPHONE_ACTIONS),
                    "reason": f"Live gesture and approved-message actions require {SUPPORT_CANARY_ENV}=1 on the support canary connector.",
                },
                "forbidden": [
                    "generic_remote_desktop_passthrough",
                    "generic_coordinates",
                    "arbitrary_text_entry",
                    "messages_or_calls",
                    "purchases",
                    "auth_bypass",
                    "camera_or_microphone",
                    "sensitive_app_control",
                ],
                "approval_gates": {
                    "mutating_named_actions": "OpenClaw tools must require approval before live execution.",
                    "screen_sharing_enablement": "The bridge reports status only; enabling Screen Sharing requires explicit customer/admin approval outside this CLI.",
                    "support_canary_live_iphone": f"Support-only iPhone gestures/messages require {SUPPORT_CANARY_ENV}=1 plus a matching dry-run audit id.",
                },
            },
        )

    def snapshot(self, *, max_chars: int) -> CommandResult:
        frontmost = self._frontmost_app()
        if self._is_sensitive_app(frontmost):
            return CommandResult(
                ok=False,
                data={"screenshot_path": None, "frontmost_app": redact_value(frontmost)},
                errors=[
                    make_error(
                        code="sensitive_app_blocked",
                        message="The frontmost app is on the sensitive-app denylist; screenshot capture was blocked.",
                        guidance="Move focus to a non-sensitive app and rerun the named observation command.",
                    )
                ],
            )
        screenshot_path = self._capture_screenshot([])
        title = self._front_window_title()
        capped_title, title_truncated = cap_text(redact_value(title), max_chars)
        warnings = ["window title truncated"] if title_truncated else []
        return CommandResult(
            ok=screenshot_path is not None,
            data={
                "timestamp": self.now(),
                "frontmost_app": redact_value(frontmost),
                "window_title": capped_title,
                "screenshot_path": redact_value(screenshot_path) if screenshot_path else None,
                "max_chars": max_chars,
            },
            warnings=warnings if screenshot_path else warnings + ["screenshot unavailable; Screen Recording permission may be missing"],
        )

    def ax_tree(self, *, max_nodes: int) -> CommandResult:
        frontmost = self._frontmost_app()
        if self._is_sensitive_app(frontmost):
            return CommandResult(
                ok=False,
                data={"nodes": [], "truncated": False, "frontmost_app": redact_value(frontmost)},
                errors=[
                    make_error(
                        code="sensitive_app_blocked",
                        message="The frontmost app is on the sensitive-app denylist; AX tree capture was blocked.",
                        guidance="Move focus to a non-sensitive app and rerun the named observation command.",
                    )
                ],
            )
        if self.accessibility_checker() is False:
            return CommandResult(ok=False, data={"nodes": [], "truncated": False}, errors=[self._permission_error("accessibility", "read the Mac Accessibility tree")])
        pid = self._pid_for_app(frontmost) if frontmost else None
        if pid is None:
            return CommandResult(
                ok=False,
                data={"nodes": [], "truncated": False, "frontmost_app": redact_value(frontmost)},
                errors=[make_error(code="frontmost_pid_not_found", message="Could not resolve a frontmost app PID.", guidance="Ensure the target app is visible and rerun status.")],
            )
        payload, errors, warnings = self._ax_snapshot(pid=pid, max_nodes=max_nodes)
        if payload is None:
            return CommandResult(ok=False, data={"nodes": [], "truncated": False}, errors=errors, warnings=warnings)
        nodes = [self._safe_node(row) for row in payload.get("nodes", [])][:max_nodes]
        truncated = bool(payload.get("truncated"))
        if truncated:
            warnings.append(f"AX tree truncated at {max_nodes} nodes")
        return CommandResult(ok=True, data={"frontmost_app": redact_value(frontmost), "nodes": nodes, "truncated": truncated, "max_nodes": max_nodes}, warnings=warnings)

    def app_focus(self, *, app_name: str, dry_run: bool = False) -> CommandResult:
        if not self._safe_app_name(app_name):
            return CommandResult(ok=False, data={"focused": False, "would_focus": dry_run}, errors=[make_error(code="app_name_not_allowed", message="App name is outside the safe named-action character set.", guidance="Use a visible macOS app name with letters, numbers, spaces, dots, underscores, plus, at-sign, slash, colon, hash, or hyphen.")])
        if dry_run:
            return CommandResult(ok=True, data={"focused": False, "would_focus": True, "app_name": app_name})
        if self._is_sensitive_app(app_name):
            return CommandResult(ok=False, data={"focused": False, "app_name": app_name}, errors=[make_error(code="sensitive_app_blocked", message="This app is on the sensitive-app denylist.", guidance="Only request named actions against non-sensitive apps.")])
        result = self.runner(["open", "-a", app_name], 10.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"focused": False, "app_name": app_name}, errors=[make_error(code="app_focus_failed", message="macOS refused to open or focus the requested app.", guidance="Verify the app is installed and visible.")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"focused": True, "app_name": app_name})

    def local_site_open(self, *, url: str, dry_run: bool = False) -> CommandResult:
        if not self._safe_local_url(url):
            return CommandResult(ok=False, data={"opened": False, "would_open": dry_run, "url": redact_value(url)}, errors=[make_error(code="local_site_url_not_allowed", message="Only localhost, loopback, and .local http(s) URLs are allowed.", guidance="Use a customer-local website URL such as http://localhost:3000.")])
        if dry_run:
            return CommandResult(ok=True, data={"opened": False, "would_open": True, "url": redact_value(url)})
        result = self.runner(["open", url], 10.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"opened": False, "url": redact_value(url)}, errors=[make_error(code="local_site_open_failed", message="macOS refused to open the local website.", guidance="Verify the URL is reachable from the customer Mac.")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"opened": True, "url": redact_value(url)})

    def local_site_action(self, *, action: str, dry_run: bool = False) -> CommandResult:
        if action not in SAFE_LOCAL_SITE_ACTIONS:
            return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action}, errors=[make_error(code="local_site_action_not_allowed", message="This local-site action is not allowlisted.", guidance=f"Allowed actions: {', '.join(sorted(SAFE_LOCAL_SITE_ACTIONS))}.")])
        frontmost = self._frontmost_app()
        if frontmost not in SAFE_BROWSER_APPS:
            return CommandResult(ok=False, data={"performed": False, "action": action, "frontmost_app": redact_value(frontmost)}, errors=[make_error(code="browser_not_frontmost", message="A supported browser must be frontmost for local-site actions.", guidance="Open the local site first, then rerun the named browser action.")])
        current_url = self._front_browser_url(frontmost)
        if not current_url or not self._safe_local_url(current_url):
            return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "frontmost_app": frontmost, "current_url": redact_value(current_url)}, errors=[make_error(code="local_site_url_not_allowed", message="Local-site actions require the frontmost browser tab to be localhost, loopback, or .local.", guidance="Open the customer-local site first, then rerun the named browser action.")])
        if dry_run:
            return CommandResult(ok=True, data={"performed": False, "would_perform": True, "action": action, "frontmost_app": frontmost, "current_url": redact_value(current_url)})
        key = {"reload": "r", "back": "[", "forward": "]"}[action]
        result = self.runner(["osascript", "-e", f'tell application "System Events" to keystroke "{key}" using command down'], 5.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"performed": False, "action": action}, errors=[make_error(code="local_site_action_failed", message="macOS refused the named browser action.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"performed": True, "action": action, "frontmost_app": frontmost, "current_url": redact_value(current_url)})

    def iphone_mirroring_status(self) -> CommandResult:
        pid = self._pid_for_app("iPhone Mirroring")
        frontmost = self._frontmost_app()
        return CommandResult(
            ok=True,
            data={
                "installed": IPHONE_MIRRORING_APP.exists(),
                "running": pid is not None,
                "pid": pid,
                "frontmost": frontmost == "iPhone Mirroring",
                "window_title": redact_value(self._front_window_title()) if frontmost == "iPhone Mirroring" else None,
                "supported_actions": sorted(SAFE_IPHONE_ACTIONS),
                "support_canary_actions": sorted(SUPPORT_CANARY_IPHONE_ACTIONS),
                "disabled_actions": [] if self._support_canary_controls_enabled() else sorted(DISABLED_IPHONE_ACTIONS),
                "support_canary": {
                    "env_var": SUPPORT_CANARY_ENV,
                    "enabled": self._support_canary_controls_enabled(),
                    "scope": "support_vm_only",
                },
                "safety": {
                    "messages_calls_purchases_auth_camera_mic_blocked": True,
                    "generic_coordinates_blocked": True,
                    "arbitrary_text_blocked": True,
                    "approved_messages_support_only": True,
                },
            },
        )

    def iphone_mirroring_focus(self, *, dry_run: bool = False) -> CommandResult:
        return self.app_focus(app_name="iPhone Mirroring", dry_run=dry_run)

    def iphone_mirroring_action(
        self,
        *,
        action: str,
        text: str | None = None,
        app_name: str | None = None,
        target_label: str | None = None,
        direction: str | None = None,
        recipient_context: str | None = None,
        dry_run: bool = False,
    ) -> CommandResult:
        if action in SUPPORT_CANARY_IPHONE_ACTIONS and not self._support_canary_controls_enabled():
            return self._support_canary_required_error(action, dry_run=dry_run)
        if action not in SAFE_IPHONE_ACTIONS:
            if action not in SUPPORT_CANARY_IPHONE_ACTIONS:
                return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action}, errors=[make_error(code="iphone_action_not_allowed", message="This iPhone Mirroring action is not allowlisted.", guidance=f"Allowed actions: {', '.join(sorted(SAFE_IPHONE_ACTIONS | SUPPORT_CANARY_IPHONE_ACTIONS))}.")])
        if not IPHONE_MIRRORING_APP.exists():
            return CommandResult(ok=False, data={"performed": False, "action": action}, errors=[make_error(code="iphone_mirroring_not_installed", message="iPhone Mirroring.app is not installed on this Mac.", guidance="Use a supported macOS/iPhone pairing before enabling these tools.")])
        if action == "type_spotlight" and (not text or not SAFE_TEXT_RE.match(text)):
            return self._unsafe_text_error(action, dry_run=dry_run)
        if action == "type_approved_text" and (not text or not APPROVED_TEXT_RE.match(text)):
            return self._approved_text_error(action, dry_run=dry_run)
        if action == "send_approved_message":
            if not text or not APPROVED_TEXT_RE.match(text):
                return self._approved_text_error(action, dry_run=dry_run)
            if not recipient_context or len(recipient_context.strip()) > 160:
                return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action}, errors=[make_error(code="recipient_context_required", message="Approved message sends require the exact same-turn recipient/context description.", guidance="Provide a short human-approved recipient/context string for audit evidence.")])
            if target_label is None:
                target_label = "Send"
            if target_label.strip().lower() not in {"send", "send message"}:
                return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "target_label": target_label}, errors=[make_error(code="send_target_label_not_allowed", message="Approved support-canary message sends may only press a visible Send control.", guidance="Use target label 'Send' or 'Send message'; do not route this through arbitrary visible labels.")])
        if action == "open_app" and (not app_name or not self._safe_app_name(app_name) or self._is_iphone_sensitive_app(app_name)):
            return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "app_name": app_name}, errors=[make_error(code="iphone_app_name_not_allowed", message="The requested iPhone app name is not allowed for this named action.", guidance="Use a non-sensitive app name with safe characters, for example Calculator or Notes.")])
        if action == "tap_named_target" and (not target_label or not self._safe_app_name(target_label) or self._is_dangerous_iphone_target(target_label)):
            return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "target_label": target_label}, errors=[make_error(code="target_label_not_allowed", message="The requested visible target label is not safe.", guidance="Use an exact non-sensitive visible AX label; sends, calls, purchases, auth prompts, camera, microphone, and generic coordinates are blocked.")])
        if action == "scroll" and direction not in SCROLL_DIRECTIONS:
            return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "direction": direction}, errors=[make_error(code="scroll_direction_required", message="Support canary scroll requires direction 'up' or 'down'.", guidance="Use a named direction only; generic coordinates are blocked.")])
        if dry_run:
            return CommandResult(
                ok=True,
                data={
                    "performed": False,
                    "would_perform": True,
                    "action": action,
                    "text_preview": self._safe_preview(text),
                    "text_sha256": self._text_hash(text) if text else None,
                    "app_name": app_name,
                    "target_label": target_label,
                    "direction": direction,
                    "recipient_context": self._safe_preview(recipient_context),
                    "support_canary": action in SUPPORT_CANARY_IPHONE_ACTIONS,
                },
            )
        status = self.iphone_mirroring_status()
        if not status.data.get("installed"):
            return CommandResult(ok=False, data={"performed": False, "action": action}, errors=[make_error(code="iphone_mirroring_not_installed", message="iPhone Mirroring.app is not installed on this Mac.", guidance="Use a supported macOS/iPhone pairing before enabling these tools.")])
        focus = self.iphone_mirroring_focus(dry_run=False)
        if not focus.ok:
            return focus
        if action == "home":
            return self._iphone_keyboard_action(action, "18")
        if action == "app_switcher":
            return self._iphone_keyboard_action(action, "19")
        if action == "spotlight":
            return self._iphone_keyboard_action(action, "20")
        if action == "type_spotlight":
            spotlight = self._iphone_keyboard_action("spotlight", "20")
            if not spotlight.ok:
                return spotlight
            typed = self._keystroke_text(text)
            if not typed.ok:
                return typed
            return CommandResult(ok=True, data={"performed": True, "action": action, "text_preview": self._safe_preview(text)}, provenance={"source": "iphone_mirroring"})
        if action == "open_app":
            spotlight = self._iphone_keyboard_action("spotlight", "20")
            if not spotlight.ok:
                return spotlight
            typed = self._keystroke_text(app_name)
            if not typed.ok:
                return typed
            result = self.runner(["osascript", "-e", 'tell application "System Events" to key code 36'], 5.0)
            if result.returncode != 0:
                return CommandResult(ok=False, data={"performed": False, "action": action, "app_name": app_name}, errors=[make_error(code="iphone_open_app_failed", message="macOS refused the iPhone Mirroring app launch keystroke.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
            return CommandResult(ok=True, data={"performed": True, "action": action, "app_name": app_name}, provenance={"source": "iphone_mirroring"})
        if action == "tap_named_target":
            return self._press_iphone_target(target_label=target_label)
        if action in SUPPORT_CANARY_GESTURE_KEYS:
            vectors = {
                "swipe_left": (-900, 0),
                "swipe_right": (900, 0),
                "swipe_up": (0, 900),
                "swipe_down": (0, -900),
            }
            dx, dy = vectors[action]
            return self._iphone_scroll_gesture(action, dx=dx, dy=dy)
        if action == "scroll":
            dy = 600 if direction == "up" else -600
            return self._iphone_scroll_gesture(action, dx=0, dy=dy, direction=direction)
        if action == "type_approved_text":
            typed = self._keystroke_approved_text(text)
            if not typed.ok:
                return typed
            return CommandResult(ok=True, data={"performed": True, "action": action, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text)}, provenance={"source": "iphone_mirroring", "support_canary": True})
        if action == "send_approved_message":
            typed = self._keystroke_approved_text(text)
            if not typed.ok:
                return typed
            pressed = self._press_iphone_target(target_label=target_label, allow_support_send=True, action=action)
            if not pressed.ok:
                return pressed
            return CommandResult(
                ok=True,
                data={
                    "performed": True,
                    "action": action,
                    "target_label": target_label,
                    "text_preview": self._safe_preview(text),
                    "text_sha256": self._text_hash(text),
                    "recipient_context": self._safe_preview(recipient_context),
                },
                provenance={"source": "iphone_mirroring_ax", "support_canary": True},
            )
        raise AssertionError(f"unhandled iPhone Mirroring action: {action}")

    def screen_sharing_status(self) -> CommandResult:
        disabled = self._launchctl_disabled("com.apple.screensharing")
        vnc_listening = self._tcp_port_listening("5900")
        ard_listening = self._tcp_port_listening("3283")
        enabled = (disabled is False) or vnc_listening or ard_listening
        return CommandResult(
            ok=True,
            data={
                "enabled": enabled,
                "launchctl_disabled": disabled,
                "vnc_5900_listening": vnc_listening,
                "ard_3283_listening": ard_listening,
                "approval_required_to_enable": True,
                "bridge_can_enable": False,
                "recommended_acl": "tailnet-only paired customer VM to Mac connector and approved Screen Sharing ports",
            },
            warnings=[] if enabled else ["Screen Sharing/Remote Management is not enabled; this bridge will not enable it without explicit approval."],
        )

    def _iphone_keyboard_action(self, action: str, key_code: str, *, support_canary: bool = False, direction: str | None = None) -> CommandResult:
        script = f'tell application "System Events" to key code {key_code}' if support_canary else f'tell application "System Events" to key code {key_code} using command down'
        result = self.runner(["osascript", "-e", script], 5.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"performed": False, "action": action}, errors=[make_error(code="iphone_keyboard_action_failed", message="macOS refused the iPhone Mirroring keyboard shortcut.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
        warnings = ["Support-canary gesture uses the safest keyboard-equivalent lane; verify live behavior in the iPhone Mirroring window."] if support_canary else []
        data: dict[str, Any] = {"performed": True, "action": action}
        if direction:
            data["direction"] = direction
        return CommandResult(ok=True, data=data, warnings=warnings, provenance={"source": "iphone_mirroring", "support_canary": support_canary})

    def _iphone_scroll_gesture(self, action: str, *, dx: int, dy: int, direction: str | None = None) -> CommandResult:
        if self.accessibility_checker() is False:
            return CommandResult(ok=False, data={"performed": False, "action": action, "direction": direction}, errors=[self._permission_error("accessibility", "send a named iPhone Mirroring gesture")])
        pid = self._pid_for_app("iPhone Mirroring")
        if pid is None:
            return CommandResult(ok=False, data={"performed": False, "action": action, "direction": direction}, errors=[make_error(code="iphone_mirroring_not_running", message="iPhone Mirroring is not currently running.", guidance="Open iPhone Mirroring and rerun the named action.")])
        result = self.runner([sys.executable, "-c", self.IPHONE_SCROLL_GESTURE_SCRIPT, str(pid), str(dx), str(dy)], 10.0)
        warnings = self._stderr_warning(result)
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            payload = {"ok": False, "error": "iphone_gesture_parse_failed"}
        if result.returncode != 0 or not payload.get("ok"):
            return CommandResult(
                ok=False,
                data={"performed": False, "action": action, "direction": direction},
                errors=[
                    make_error(
                        code=str(payload.get("error") or "iphone_gesture_failed").split(":", 1)[0],
                        message="Unable to post the named iPhone Mirroring gesture.",
                        guidance="Verify Accessibility and pyobjc Quartz/ApplicationServices support; do not fall back to generic coordinates.",
                        permission="accessibility",
                    )
                ],
                warnings=warnings,
            )
        data: dict[str, Any] = {"performed": True, "action": action, "gesture": "scroll_wheel", "vector": payload.get("vector")}
        if direction:
            data["direction"] = direction
        return CommandResult(
            ok=True,
            data=data,
            warnings=warnings + ["Support-canary gesture posts an internal scroll vector to the focused iPhone Mirroring window; verify live behavior before broader use."],
            provenance={"source": "iphone_mirroring_quartz", "support_canary": True},
        )

    def _press_iphone_target(self, *, target_label: str, allow_support_send: bool = False, action: str = "tap_named_target") -> CommandResult:
        if self.accessibility_checker() is False:
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label}, errors=[self._permission_error("accessibility", "tap a named iPhone Mirroring target")])
        pid = self._pid_for_app("iPhone Mirroring")
        if pid is None:
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label}, errors=[make_error(code="iphone_mirroring_not_running", message="iPhone Mirroring is not currently running.", guidance="Open iPhone Mirroring and rerun the named action.")])
        if self._is_dangerous_iphone_target(target_label) and not (allow_support_send and target_label.strip().lower() in {"send", "send message"}):
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label}, errors=[make_error(code="target_label_not_allowed", message="The requested visible target label is not safe.", guidance="Only the support canary approved-message action may press a Send target after same-turn approval.")])
        result = self.runner([sys.executable, "-c", self.AX_PRESS_LABEL_SCRIPT, str(pid), target_label, "500", "1"], 20.0)
        warnings = self._stderr_warning(result)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label}, errors=[make_error(code="iphone_target_lookup_unavailable", message="Unable to inspect iPhone Mirroring targets.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=warnings)
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label}, errors=[make_error(code="iphone_target_lookup_parse_failed", message="Unable to parse iPhone Mirroring target lookup output.", guidance="Check pyobjc GUI dependencies in the bridge environment.")], warnings=warnings)
        if not payload.get("ok"):
            code = str(payload.get("error") or "iphone_target_press_failed").split(":", 1)[0]
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label, "matches": [self._safe_node(row) for row in payload.get("matches", [])]}, errors=[make_error(code=code, message="The named target could not be pressed safely.", guidance="Use exact visible labels only; do not fall back to generic coordinates.")], warnings=warnings)
        return CommandResult(ok=True, data={"performed": True, "action": action, "target_label": target_label, "matches": [self._safe_node(row) for row in payload.get("matches", [])]}, warnings=warnings, provenance={"source": "iphone_mirroring_ax", "support_canary": allow_support_send})

    def _keystroke_text(self, text: str) -> CommandResult:
        if not SAFE_TEXT_RE.match(text):
            return self._unsafe_text_error("keystroke_text", dry_run=False)
        script = f'tell application "System Events" to keystroke "{self._escape_applescript(text)}"'
        result = self.runner(["osascript", "-e", script], 5.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"typed": False, "text_preview": self._safe_preview(text)}, errors=[make_error(code="safe_text_entry_failed", message="macOS refused safe text entry.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"typed": True, "text_preview": self._safe_preview(text)})

    def _keystroke_approved_text(self, text: str) -> CommandResult:
        if not APPROVED_TEXT_RE.match(text):
            return self._approved_text_error("keystroke_approved_text", dry_run=False)
        script = f'tell application "System Events" to keystroke "{self._escape_applescript(text)}"'
        result = self.runner(["osascript", "-e", script], 5.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"typed": False, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text)}, errors=[make_error(code="approved_text_entry_failed", message="macOS refused approved support-canary text entry.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"typed": True, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text)})

    def _ax_snapshot(self, *, pid: int, max_nodes: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
        result = self.runner([sys.executable, "-c", self.AX_TREE_SCRIPT, str(pid), str(max_nodes)], 20.0)
        warnings = self._stderr_warning(result)
        if result.returncode != 0:
            return None, [make_error(code="ax_tree_unavailable", message="Unable to read the frontmost Accessibility tree.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return None, [make_error(code="ax_snapshot_parse_failed", message="Unable to parse Accessibility snapshot output.", guidance="Check pyobjc GUI dependencies in the bridge environment.")], warnings
        if not payload.get("ok"):
            return None, [make_error(code="ax_dependency_missing", message=str(redact_value(payload.get("error") or "Accessibility dependency missing.")), guidance="Install pyobjc-framework-ApplicationServices in the bridge environment.")], warnings
        return payload, [], warnings

    def _capture_screenshot(self, warnings: list[str]) -> Path | None:
        if self.platform_name != "Darwin":
            warnings.append("screenshot unavailable outside macOS")
            return None
        screenshot_dir = self.state_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"customer-mac-{self.now().replace(':', '').replace('-', '')}.png"
        screenshot_path = screenshot_dir / filename
        result = self.runner(["screencapture", "-x", str(screenshot_path)], 10.0)
        if result.returncode != 0:
            warnings.append("screenshot unavailable; Screen Recording permission may be missing")
            return None
        return screenshot_path

    def _frontmost_app(self) -> str | None:
        return self._osascript_value('tell application "System Events" to get name of first application process whose frontmost is true')

    def _front_window_title(self) -> str | None:
        return self._osascript_value('tell application "System Events" to tell first application process whose frontmost is true to get name of front window')

    def _front_browser_url(self, app_name: str | None) -> str | None:
        if not app_name:
            return None
        if app_name == "Safari":
            return self._osascript_value('tell application "Safari" to get URL of front document')
        if app_name in {"Google Chrome", "Arc", "Brave Browser"}:
            return self._osascript_value(f'tell application "{self._escape_applescript(app_name)}" to get URL of active tab of front window')
        return None

    def _pid_for_app(self, app_name: str | None) -> int | None:
        if not app_name:
            return None
        result = self.runner(["pgrep", "-x", app_name], 3.0)
        if result.returncode == 0 and result.stdout.strip():
            try:
                return int(result.stdout.strip().splitlines()[0])
            except ValueError:
                pass
        if self.platform_name != "Darwin":
            return None
        script = f'tell application "System Events" to get unix id of first application process whose name is "{self._escape_applescript(app_name)}"'
        fallback = self.runner(["osascript", "-e", script], 5.0)
        if fallback.returncode != 0 or not fallback.stdout.strip():
            return None
        try:
            return int(fallback.stdout.strip().splitlines()[0])
        except ValueError:
            return None

    def _device_identity(self) -> dict[str, Any]:
        uuid_value = self._ioreg_uuid()
        digest_source = uuid_value or platform.node() or "unknown"
        return {
            "id": "mac-" + hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16],
            "hostname": redact_value(platform.node()),
            "hardware_uuid_present": uuid_value is not None,
            "arch": platform.machine(),
        }

    def _ioreg_uuid(self) -> str | None:
        if self.platform_name != "Darwin":
            return None
        result = self.runner(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], 5.0)
        if result.returncode != 0:
            return None
        match = re.search(r'"IOPlatformUUID" = "([^"]+)"', result.stdout)
        return match.group(1) if match else None

    def _permission_status(self, permission: str) -> dict[str, str]:
        if permission == "accessibility":
            trusted = self.accessibility_checker()
            if trusted is True:
                return {"status": "granted", "guidance": ACCESSIBILITY_GUIDANCE}
            if trusted is False:
                return {"status": "missing", "guidance": ACCESSIBILITY_GUIDANCE}
        return {"status": "unknown", "guidance": ACCESSIBILITY_GUIDANCE}

    def _permission_error(self, permission: str, action: str) -> dict[str, Any]:
        return make_error(code="permission_missing", message=f"Accessibility permission is required to {action}.", guidance=ACCESSIBILITY_GUIDANCE, permission=permission)

    def _osascript_value(self, script: str) -> str | None:
        if self.platform_name != "Darwin":
            return None
        result = self.runner(["osascript", "-e", script], 5.0)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _launchctl_disabled(self, label: str) -> bool | None:
        result = self.runner(["launchctl", "print-disabled", "system"], 5.0)
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if label in line:
                lowered = line.lower()
                if "disabled" in lowered:
                    return True
                if "enabled" in lowered:
                    return False
                if "=> true" in lowered:
                    return True
                if "=> false" in lowered:
                    return False
        return None

    def _tcp_port_listening(self, port: str) -> bool:
        result = self.runner(["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], 5.0)
        if result.returncode == 0 and bool(result.stdout.strip()):
            return True
        fallback = self.runner(["nc", "-z", "127.0.0.1", port], 5.0)
        return fallback.returncode == 0

    def _safe_node(self, row: dict[str, Any]) -> dict[str, Any]:
        role, _ = cap_text(str(redact_value(row.get("role") or "unknown")), 80)
        name, _ = cap_text(str(redact_value(row.get("name"))) if row.get("name") else None, 160)
        node: dict[str, Any] = {"role": role, "name": name, "depth": int(row.get("depth") or 0), "window_index": row.get("window_index")}
        actions = row.get("actions")
        if isinstance(actions, list):
            node["actions"] = [str(redact_value(item)) for item in actions[:20]]
        return node

    def _safe_local_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        if parsed.scheme not in {"http", "https"}:
            return False
        host = parsed.hostname or ""
        return host in SAFE_LOCAL_HOSTS or host.endswith(".local")

    def _safe_app_name(self, value: str | None) -> bool:
        return bool(value and SAFE_TEXT_RE.match(value))

    def _is_sensitive_app(self, app_name: str | None) -> bool:
        if not app_name:
            return False
        return app_name in SENSITIVE_APPS

    def _is_iphone_sensitive_app(self, app_name: str | None) -> bool:
        if not app_name:
            return False
        normalized = app_name.strip().lower()
        return any(normalized == item.lower() for item in SENSITIVE_IPHONE_APPS)

    def _is_dangerous_iphone_target(self, label: str | None) -> bool:
        return bool(label and DANGEROUS_IPHONE_TARGET_RE.search(label.strip()))

    def _safe_preview(self, text: str | None) -> str | None:
        if text is None:
            return None
        capped, _ = cap_text(redact_value(text), 80)
        return capped

    def _unsafe_text_error(self, action: str, *, dry_run: bool) -> CommandResult:
        return CommandResult(
            ok=False,
            data={"performed": False, "would_perform": dry_run, "action": action},
            errors=[make_error(code="safe_text_required", message="Text entry is limited to short disposable/search-style text.", guidance="Use letters, numbers, spaces, and simple punctuation only; do not type secrets, messages, or private data.")],
        )

    def _approved_text_error(self, action: str, *, dry_run: bool) -> CommandResult:
        return CommandResult(
            ok=False,
            data={"performed": False, "would_perform": dry_run, "action": action},
            errors=[make_error(code="approved_text_required", message="Support-canary text entry requires non-empty same-turn-approved text capped at 240 characters.", guidance="Do not type secrets. For messages, get exact human approval for the recipient/context and exact text first.")],
        )

    def _support_canary_controls_enabled(self) -> bool:
        return os.environ.get(SUPPORT_CANARY_ENV, "").strip().lower() in {"1", "true", "yes", "support"}

    def _support_canary_required_error(self, action: str, *, dry_run: bool) -> CommandResult:
        return CommandResult(
            ok=False,
            data={"performed": False, "would_perform": dry_run, "action": action, "support_canary": False},
            errors=[
                make_error(
                    code="support_canary_controls_not_enabled",
                    message="This iPhone Mirroring action is support-VM-only and is disabled on this host.",
                    guidance=f"Enable {SUPPORT_CANARY_ENV}=1 only on the support canary Mac connector; customer connectors should leave it unset.",
                )
            ],
        )

    def _text_hash(self, text: str | None) -> str | None:
        if text is None:
            return None
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _escape_applescript(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _stderr_warning(self, result: RunnerResult) -> list[str]:
        return [str(redact_value(result.stderr.strip()))] if result.stderr.strip() else []

    def _safety_summary(self) -> dict[str, bool]:
        return {
            "named_actions_only": True,
            "generic_coordinates_blocked": True,
            "arbitrary_text_blocked": True,
            "sensitive_apps_blocked": True,
            "screen_sharing_enablement_blocked": True,
            "append_only_audit_log": True,
            "support_canary_controls_enabled": self._support_canary_controls_enabled(),
        }
