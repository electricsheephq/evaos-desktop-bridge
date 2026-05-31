from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

from ..audit import append_audit, default_state_dir
from ..helper_ipc import helper_client_from_environment
from ..redaction import cap_text, redact_value
from ..schema import make_error, timestamp_utc
from ..state import kill_control_session, read_control_session, start_control_session, stop_control_session
from ..types import CommandResult
from .codex_macos import (
    ACCESSIBILITY_GUIDANCE,
    SCREEN_RECORDING_GUIDANCE,
    RunnerResult,
    check_accessibility_trusted,
    check_screen_recording_trusted,
    run_command,
)

IPHONE_MIRRORING_APP = Path("/System/Applications/iPhone Mirroring.app")
SAFE_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
SAFE_BROWSER_APPS = {"Safari", "Google Chrome", "Arc", "Firefox", "Brave Browser"}
SAFE_LOCAL_SITE_ACTIONS = {"reload", "back", "forward"}
CONTROL_MODES = {"full_access", "ask_permission"}
AX_EDITABLE_VALUE_ROLES = {"AXTextField", "AXTextArea", "AXComboBox"}
PEEKABOO_BIN_CANDIDATES = (
    "evaos-connector-helper",
    "peekaboo",
    "/opt/homebrew/bin/peekaboo",
    "/usr/local/bin/peekaboo",
)
SAFE_IPHONE_ACTIONS = {
    "home",
    "app_switcher",
    "spotlight",
    "type_spotlight",
    "open_app",
    "tap_named_target",
}
GUARDED_IPHONE_ACTIONS = {
    "scroll",
    "swipe_left",
    "swipe_right",
    "swipe_up",
    "swipe_down",
    "type_approved_text",
    "send_approved_message",
}
GUARDED_GESTURE_KEYS = {
    "swipe_left": "123",
    "swipe_right": "124",
    "swipe_up": "126",
    "swipe_down": "125",
}
SCROLL_DIRECTIONS = {"up": "126", "down": "125"}
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
SNAPSHOT_MAX_AGE_SECONDS = 15 * 60
SNAPSHOT_INLINE_MAX_BYTES = int(os.environ.get("EVAOS_DESKTOP_BRIDGE_INLINE_IMAGE_MAX_BYTES", str(3 * 1024 * 1024)))


class CustomerMacHelperClient(Protocol):
    def dispatch(self, command: str, payload: dict[str, object], *, audit_id: str | None = None) -> CommandResult:
        ...


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
        _, point = AS.AXValueGetValue(pos, AS.kAXValueCGPointType, None)
        _, dimensions = AS.AXValueGetValue(size, AS.kAXValueCGSizeType, None)
        return {"x": int(point.x), "y": int(point.y), "width": int(dimensions.width), "height": int(dimensions.height)}
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


def walk(element, rows, depth=0, window_index=None, path=None, sibling_index=0):
    if len(rows) >= max_nodes:
        return True
    role = text_value(ax_value(element, AS.kAXRoleAttribute)) or "unknown"
    name = text_value(ax_value(element, AS.kAXTitleAttribute)) or text_value(ax_value(element, AS.kAXDescriptionAttribute))
    identifier = text_value(ax_value(element, getattr(AS, "kAXIdentifierAttribute", "AXIdentifier")))
    segment = {"role": role, "index": int(sibling_index)}
    if name:
        segment["name"] = name
    if identifier:
        segment["identifier"] = identifier
    ax_path = list(path or []) + [segment]
    rows.append({
        "role": role,
        "name": name,
        "identifier": identifier,
        "depth": depth,
        "window_index": window_index,
        "bounds": rect_value(element),
        "actions": actions(element),
        "ax_path": ax_path,
    })
    children = ax_value(element, AS.kAXChildrenAttribute) or []
    try:
        child_iter = list(children)
    except Exception:
        child_iter = []
    for child_index, child in enumerate(child_iter):
        if walk(child, rows, depth + 1, window_index, ax_path, child_index):
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
    truncated = walk(window, nodes, 0, idx, [], idx) or truncated

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

    def __init__(
        self,
        *,
        runner: Callable[[list[str], float], RunnerResult] = run_command,
        state_dir: Path | None = None,
        platform_name: str | None = None,
        accessibility_checker: Callable[[], bool | None] = check_accessibility_trusted,
        screen_recording_checker: Callable[[], bool | None] = check_screen_recording_trusted,
        now: Callable[[], str] = timestamp_utc,
        helper_client: CustomerMacHelperClient | None = None,
    ) -> None:
        self.runner = runner
        self.state_dir = state_dir or default_state_dir()
        self.platform_name = platform_name or platform.system()
        self.accessibility_checker = accessibility_checker
        self.screen_recording_checker = screen_recording_checker
        self.now = now
        self.helper_client = helper_client if helper_client is not None else helper_client_from_environment(state_dir=self.state_dir)

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
                    "screen_recording": self._permission_status("screen_recording"),
                },
                "iphone_mirroring": mirroring_status.data,
                "screen_sharing": screen_sharing.data,
                "safety": self._safety_summary(),
            },
            warnings=mirroring_status.warnings + screen_sharing.warnings,
        )

    def capabilities(self) -> CommandResult:
        peekaboo = self._peekaboo_status()
        return CommandResult(
            ok=True,
            data={
                "supported_targets": ["mac", "desktop", "browser", "local_site", "iphone_mirroring", "screen_sharing_status"],
                "actions": {
                    "mac": ["status", "capabilities", "snapshot", "ax_tree", "app_focus"],
                    "control_session": ["status", "start", "stop", "kill_switch"],
                    "desktop": ["see", "click", "type", "scroll", "drag", "hotkey", "focus_app", "window", "menu", "browser_action"],
                    "local_site": ["open", "reload", "back", "forward"],
                    "iphone_mirroring": sorted(SAFE_IPHONE_ACTIONS | GUARDED_IPHONE_ACTIONS | {"see", "tap", "swipe", "type"}),
                    "screen_sharing": ["status"],
                },
                "engines": {"peekaboo": peekaboo, "fallbacks": ["accessibility", "post_to_pid_helper", "system_events"]},
                "control_modes": {
                    "full_access": "Customer-granted session: live clicks, typing, scrolling, dragging, app/window/menu/browser, and iPhone Mirroring actions do not require per-action approval, but sensitive apps remain blocked.",
                    "ask_permission": "Same surface, but high-impact text/send-style actions require approval evidence.",
                },
                "forbidden": ["public_mac_ports", "hidden_shell", "credential_collection", "security_bypass"],
                "approval_gates": {
                    "full_access": "No per-action approval once the customer starts a Full Access control session.",
                    "ask_permission": "High-impact actions require approval; low-level navigation stays continuous.",
                    "screen_sharing_enablement": "The bridge reports status only; private overlay pairing remains the release path.",
                },
            },
        )

    def control_status(self) -> CommandResult:
        session = read_control_session(self.state_dir)
        return CommandResult(
            ok=True,
            data={
                "session": session,
                "mode": session.get("mode"),
                "active": bool(session.get("active")),
                "kill_switch": bool(session.get("kill_switch")),
                "current_agent": session.get("agent_label"),
                "current_app": redact_value(self._frontmost_app()),
                "peekaboo": self._peekaboo_status(),
                "permissions": {
                    "accessibility": self._permission_status("accessibility"),
                    "screen_recording": self._permission_status("screen_recording"),
                },
            },
        )

    def control_start(self, *, mode: str, agent_label: str | None = None) -> CommandResult:
        normalized = mode.replace("-", "_")
        if normalized not in CONTROL_MODES:
            return CommandResult(
                ok=False,
                data={"active": False, "mode": normalized},
                errors=[make_error(code="control_mode_invalid", message="Control mode must be full_access or ask_permission.", guidance="Start a customer-granted control session with --mode full-access or --mode ask-permission.")],
            )
        session = start_control_session(mode=normalized, agent_label=agent_label, state_dir=self.state_dir)
        return CommandResult(ok=True, data={"started": True, "session": session, "peekaboo": self._peekaboo_status()}, provenance={"source": "control_session"})

    def control_stop(self) -> CommandResult:
        session = stop_control_session(self.state_dir)
        return CommandResult(ok=True, data={"stopped": True, "session": session}, provenance={"source": "control_session"})

    def control_kill_switch(self) -> CommandResult:
        session = kill_control_session(self.state_dir)
        return CommandResult(ok=True, data={"killed": True, "session": session}, provenance={"source": "control_session", "kill_switch": True})

    def desktop_see(self, *, max_chars: int = 4000, max_nodes: int = 200) -> CommandResult:
        frontmost = self._frontmost_app()
        sensitive_block = self._sensitive_app_observation_block(frontmost=frontmost, surface="desktop_see")
        if sensitive_block is not None:
            return sensitive_block
        peekaboo = self._peekaboo_status()
        warnings: list[str] = []
        if peekaboo.get("available"):
            peekaboo_seen = self._peekaboo_see(peekaboo=peekaboo, target="desktop", max_chars=max_chars, max_nodes=max_nodes)
            if peekaboo_seen.ok:
                return peekaboo_seen
            warnings.extend(peekaboo_seen.warnings)
            warnings.extend(str(error.get("message") or error.get("code") or "Peekaboo see failed") for error in peekaboo_seen.errors)
        screenshot = self.snapshot(max_chars=max_chars)
        ax = self.ax_tree(max_nodes=max_nodes)
        snapshot_id = screenshot.data.get("snapshot_id") if screenshot.ok else None
        elements = self._elements_from_ax(ax.data.get("nodes", []) if ax.ok else [], snapshot_id=snapshot_id)
        if snapshot_id and elements:
            self._write_snapshot_index(snapshot_id=snapshot_id, target="desktop", elements=elements, engine="ax_fallback")
        return CommandResult(
            ok=screenshot.ok or ax.ok,
            data={
                "engine": "fallback",
                "frontmost_app": redact_value(frontmost),
                "snapshot_id": snapshot_id,
                "peekaboo": peekaboo,
                "peekaboo_output": None,
                "peekaboo_truncated": False,
                "screenshot": screenshot.data if screenshot.ok else None,
                "ax": ax.data if ax.ok else None,
                "elements": elements,
            },
            warnings=warnings + screenshot.warnings + ax.warnings + ([] if peekaboo.get("available") else ["Peekaboo not installed; used built-in fallback."]),
            errors=[] if screenshot.ok or ax.ok else screenshot.errors + ax.errors,
            provenance={"source": "peekaboo_fallback"},
        )

    def desktop_click(
        self,
        *,
        target_label: str | None = None,
        x: int | None = None,
        y: int | None = None,
        snapshot_id: str | None = None,
        element_id: str | None = None,
        dry_run: bool = False,
    ) -> CommandResult:
        resolved_label = target_label
        resolved_engine = None
        resolved_peekaboo_snapshot_id = None
        resolved_peekaboo_element_id = None
        resolved_ax_target: dict[str, Any] | None = None
        require_snapshot_target = False
        resolved_actions: list[Any] = []
        if snapshot_id and element_id is None and target_label is None and x is not None and y is not None:
            resolved_point = self._resolve_snapshot_coordinates(snapshot_id=snapshot_id, x=x, y=y, expected_target="desktop")
            if not resolved_point.ok:
                return resolved_point
            point = resolved_point.data["point"]
            x = int(point["x"])
            y = int(point["y"])
            resolved_ax_target = resolved_point.data.get("ax_target") if isinstance(resolved_point.data.get("ax_target"), dict) else None
            require_snapshot_target = True
        else:
            resolved = self._resolve_snapshot_target(snapshot_id=snapshot_id, element_id=element_id, target_label=target_label)
            if not resolved.ok:
                return resolved
            resolved_engine = resolved.data.get("engine")
            resolved_peekaboo_snapshot_id = resolved.data.get("peekaboo_snapshot_id")
            resolved_peekaboo_element_id = resolved.data.get("peekaboo_element_id")
            resolved_ax_target = resolved.data.get("ax_target") if isinstance(resolved.data.get("ax_target"), dict) else None
            resolved_actions = resolved.data.get("actions") if isinstance(resolved.data.get("actions"), list) else []
            if resolved.data.get("point"):
                point = resolved.data["point"]
                x = int(point["x"])
                y = int(point["y"])
                resolved_label = str(resolved.data.get("target_label") or target_label or element_id or "")
                target_label = None
        if dry_run:
            return CommandResult(
                ok=True,
                data={
                    "clicked": False,
                    "would_click": True,
                    "target_label": resolved_label,
                    "snapshot_id": snapshot_id,
                    "element_id": element_id,
                    "point": self._point(x, y),
                },
            )
        sensitive_block = self._sensitive_app_action_block(frontmost=self._frontmost_app(), action="click")
        if sensitive_block is not None:
            return sensitive_block
        if resolved_ax_target is not None:
            target_block = self._sensitive_ax_target_action_block(ax_target=resolved_ax_target, action="press")
            if target_block is not None:
                return target_block
            inert_block = self._inert_ax_target_action_block(ax_target=resolved_ax_target, action="press")
            if inert_block is not None:
                return inert_block
            if "AXPress" in {str(item) for item in resolved_actions}:
                pressed = self._helper_ax_action(
                    action="press",
                    target=resolved_ax_target,
                    fallback_data={
                        "clicked": False,
                        "target_label": resolved_label,
                        "snapshot_id": snapshot_id,
                        "element_id": element_id,
                        "point": self._point(x, y),
                    },
                )
                if pressed.ok:
                    pressed.data.update({"clicked": True, "target_label": resolved_label, "snapshot_id": snapshot_id, "element_id": element_id, "point": self._point(x, y)})
                return pressed
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            if resolved_engine == "peekaboo" and resolved_peekaboo_snapshot_id and resolved_peekaboo_element_id:
                result = self.runner(
                    [
                        str(peekaboo["path"]),
                        "click",
                        "--snapshot",
                        str(resolved_peekaboo_snapshot_id),
                        "--on",
                        str(resolved_peekaboo_element_id),
                        "--json",
                        "--no-remote",
                    ],
                    5.0,
                )
                if result.returncode == 0:
                    return CommandResult(
                        ok=True,
                        data={
                            "clicked": True,
                            "target_label": resolved_label,
                            "snapshot_id": snapshot_id,
                            "element_id": element_id,
                            "peekaboo_snapshot_id": redact_value(resolved_peekaboo_snapshot_id),
                            "peekaboo_element_id": resolved_peekaboo_element_id,
                            "point": self._point(x, y),
                            "engine": "peekaboo",
                        },
                        warnings=self._stderr_warning(result),
                        provenance={"source": "peekaboo"},
                    )
            if target_label:
                result = self.runner([str(peekaboo["path"]), "click", target_label, "--json", "--no-remote"], 15.0)
                if result.returncode == 0:
                    return CommandResult(ok=True, data={"clicked": True, "target_label": target_label, "snapshot_id": snapshot_id, "element_id": element_id, "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})
            elif x is not None and y is not None:
                result = self.runner([str(peekaboo["path"]), "click", "--coords", f"{x},{y}", "--global-coords", "--json", "--no-remote"], 15.0)
                if result.returncode == 0:
                    return CommandResult(ok=True, data={"clicked": True, "target_label": resolved_label, "snapshot_id": snapshot_id, "element_id": element_id, "point": self._point(x, y), "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})
        if target_label:
            pressed = self._press_frontmost_target(target_label=target_label)
            if pressed.ok:
                pressed.data["engine"] = "ax_fallback"
                pressed.provenance = {"source": "ax_fallback"}
            return pressed
        if x is None or y is None:
            return CommandResult(ok=False, data={"clicked": False}, errors=[make_error(code="desktop_click_target_required", message="desktop_click requires target_label or x/y.", guidance="Prefer a visible target label from desktop_see; use coordinates only when labels are unavailable.")])
        return self._mouse_action("click", x=x, y=y, target=resolved_ax_target, require_target=require_snapshot_target)

    def desktop_set_value(
        self,
        *,
        snapshot_id: str,
        element_id: str,
        value: str,
        attribute: str = "value",
        dry_run: bool = False,
    ) -> CommandResult:
        if attribute not in {"value", "selected_text"}:
            return CommandResult(ok=False, data={"set": False, "attribute": attribute}, errors=[make_error(code="desktop_set_value_attribute_invalid", message="desktop_set_value attribute must be value or selected_text.", guidance="Use the fixed AXValue or AXSelectedText setter only.")])
        if not isinstance(value, str) or value == "":
            return CommandResult(ok=False, data={"set": False}, errors=[make_error(code="desktop_set_value_required", message="desktop_set_value requires non-empty text.", guidance="Pass exact approved text for the selected native field.")])
        if len(value) > 4000:
            return CommandResult(ok=False, data={"set": False, "value_sha256": self._text_hash(value)}, errors=[make_error(code="desktop_set_value_too_long", message="desktop_set_value is capped at 4000 characters.", guidance="Split longer content or use an app-specific import path.")])
        if self._looks_like_secret(value):
            return CommandResult(ok=False, data={"set": False, "value_sha256": self._text_hash(value)}, errors=[make_error(code="desktop_set_value_secret_blocked", message="desktop_set_value refuses token-like or password-like content.", guidance="Do not send credentials or secrets through agent desktop control.")])
        resolved = self._resolve_snapshot_target(snapshot_id=snapshot_id, element_id=element_id, target_label=None)
        if not resolved.ok:
            return resolved
        ax_target = resolved.data.get("ax_target") if isinstance(resolved.data.get("ax_target"), dict) else None
        if ax_target is None:
            return CommandResult(ok=False, data={"set": False, "snapshot_id": snapshot_id, "element_id": element_id}, errors=[make_error(code="desktop_set_value_ax_target_required", message="desktop_set_value requires an Accessibility-backed snapshot element.", guidance="Run desktop_see with the built-in AX fallback or choose a native AX text field from the latest snapshot.")])
        role = str(resolved.data.get("role") or "")
        if role == "AXSecureTextField" or re.search(r"password|passcode|token|secret", str(resolved.data.get("target_label") or ""), re.IGNORECASE):
            return CommandResult(ok=False, data={"set": False, "role": role, "value_sha256": self._text_hash(value)}, errors=[make_error(code="desktop_set_value_secure_field_blocked", message="desktop_set_value is blocked for secure or credential-like fields.", guidance="Do not use desktop control to enter credentials or secrets.")])
        if role not in AX_EDITABLE_VALUE_ROLES:
            return CommandResult(ok=False, data={"set": False, "role": role, "value_sha256": self._text_hash(value)}, errors=[make_error(code="desktop_set_value_non_text_field_blocked", message="desktop_set_value is blocked for non-text Accessibility roles.", guidance="Choose a native editable AXTextField, AXTextArea, or AXComboBox element from a fresh desktop_see snapshot.")])
        data = {
            "set": False,
            "would_set": dry_run,
            "snapshot_id": snapshot_id,
            "element_id": element_id,
            "target_label": resolved.data.get("target_label"),
            "role": role,
            "attribute": "AXSelectedText" if attribute == "selected_text" else "AXValue",
            "value_sha256": self._text_hash(value),
        }
        if dry_run:
            return CommandResult(ok=True, data=data)
        sensitive_block = self._sensitive_app_action_block(frontmost=self._frontmost_app(), action="set_value")
        if sensitive_block is not None:
            return sensitive_block
        target_block = self._sensitive_ax_target_action_block(ax_target=ax_target, action="set_value")
        if target_block is not None:
            return target_block
        inert_block = self._inert_ax_target_action_block(ax_target=ax_target, action="set_value")
        if inert_block is not None:
            return inert_block
        action = "set_selected_text" if attribute == "selected_text" else "set_value"
        result = self._helper_ax_action(action=action, target=ax_target, value=value, attribute=data["attribute"], fallback_data=data)
        if result.ok:
            result.data.update({**data, "set": True, "would_set": False, "engine": result.data.get("engine", "helper_ax")})
        return result

    def desktop_type(self, *, text: str, dry_run: bool = False) -> CommandResult:
        if not isinstance(text, str) or text == "":
            return CommandResult(ok=False, data={"typed": False}, errors=[make_error(code="desktop_text_required", message="desktop_type requires non-empty text.", guidance="Pass exact text to type into the focused field.")])
        if dry_run:
            return CommandResult(ok=True, data={"typed": False, "would_type": True, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text)})
        sensitive_block = self._sensitive_app_action_block(frontmost=self._frontmost_app(), action="type")
        if sensitive_block is not None:
            return sensitive_block
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            result = self.runner([str(peekaboo["path"]), "paste", "--text", text, "--json", "--no-remote"], 20.0)
            if result.returncode == 0:
                return CommandResult(
                    ok=True,
                    data={
                        "typed": True,
                        "text_preview": self._safe_preview(text),
                        "text_sha256": self._text_hash(text),
                        "engine": "peekaboo",
                        "input_method": "paste",
                    },
                    warnings=self._stderr_warning(result),
                    provenance={"source": "peekaboo_paste"},
                )
            result = self.runner([str(peekaboo["path"]), "type", "--text", text, "--profile", "linear", "--json", "--no-remote"], 20.0)
            if result.returncode == 0:
                return CommandResult(
                    ok=True,
                    data={
                        "typed": True,
                        "text_preview": self._safe_preview(text),
                        "text_sha256": self._text_hash(text),
                        "engine": "peekaboo",
                        "input_method": "type",
                    },
                    warnings=self._stderr_warning(result),
                    provenance={"source": "peekaboo_type"},
                )
        return self._keystroke_arbitrary_text(text)

    def desktop_scroll(self, *, direction: str = "down", amount: int = 600, dry_run: bool = False) -> CommandResult:
        if direction not in {"up", "down", "left", "right"}:
            return CommandResult(ok=False, data={"scrolled": False, "direction": direction}, errors=[make_error(code="desktop_scroll_direction_invalid", message="desktop_scroll direction must be up, down, left, or right.", guidance="Use a named scroll direction.")])
        amount = max(1, min(int(amount), 5000))
        if dry_run:
            return CommandResult(ok=True, data={"scrolled": False, "would_scroll": True, "direction": direction, "amount": amount})
        sensitive_block = self._sensitive_app_action_block(frontmost=self._frontmost_app(), action="scroll")
        if sensitive_block is not None:
            return sensitive_block
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            result = self.runner([str(peekaboo["path"]), "scroll", "--direction", direction, "--amount", str(amount), "--json"], 10.0)
            if result.returncode == 0:
                return CommandResult(ok=True, data={"scrolled": True, "direction": direction, "amount": amount, "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})
        return self._mouse_action("scroll", direction=direction, amount=amount)

    def desktop_drag(self, *, from_x: int, from_y: int, to_x: int, to_y: int, dry_run: bool = False) -> CommandResult:
        if dry_run:
            return CommandResult(ok=True, data={"dragged": False, "would_drag": True, "from": self._point(from_x, from_y), "to": self._point(to_x, to_y)})
        sensitive_block = self._sensitive_app_action_block(frontmost=self._frontmost_app(), action="drag")
        if sensitive_block is not None:
            return sensitive_block
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            result = self.runner(
                [
                    str(peekaboo["path"]),
                    "drag",
                    "--from-coords",
                    f"{from_x},{from_y}",
                    "--to-coords",
                    f"{to_x},{to_y}",
                    "--profile",
                    "human",
                    "--json",
                    "--no-remote",
                ],
                20.0,
            )
            if result.returncode == 0:
                return CommandResult(ok=True, data={"dragged": True, "from": self._point(from_x, from_y), "to": self._point(to_x, to_y), "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})
        return self._mouse_action("drag", from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y)

    def desktop_hotkey(self, *, keys: str, dry_run: bool = False) -> CommandResult:
        normalized = self._normalize_hotkey(keys)
        if not normalized:
            return CommandResult(ok=False, data={"pressed": False}, errors=[make_error(code="desktop_hotkey_required", message="desktop_hotkey requires keys like cmd+l or cmd+shift+4.", guidance="Use a plus-delimited hotkey string.")])
        if dry_run:
            return CommandResult(ok=True, data={"pressed": False, "would_press": True, "keys": normalized})
        sensitive_block = self._sensitive_app_action_block(frontmost=self._frontmost_app(), action="hotkey")
        if sensitive_block is not None:
            return sensitive_block
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            result = self.runner([str(peekaboo["path"]), "hotkey", "--keys", normalized, "--json", "--no-remote"], 10.0)
            if result.returncode == 0:
                return CommandResult(ok=True, data={"pressed": True, "keys": normalized, "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})
        return self._osascript_hotkey(normalized)

    def desktop_focus_app(self, *, app_name: str, dry_run: bool = False) -> CommandResult:
        if not self._safe_app_name(app_name):
            return CommandResult(ok=False, data={"focused": False}, errors=[make_error(code="app_name_not_allowed", message="App name is outside the supported character set.", guidance="Use a visible macOS app name.")])
        if self._is_sensitive_app(app_name):
            return CommandResult(ok=False, data={"focused": False, "would_focus": dry_run, "app_name": app_name}, errors=[make_error(code="sensitive_app_blocked", message="This app is on the sensitive-app denylist.", guidance="Only request named actions against non-sensitive apps.")])
        if dry_run:
            return CommandResult(ok=True, data={"focused": False, "would_focus": True, "app_name": app_name})
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            result = self.runner([str(peekaboo["path"]), "app", "switch", "--to", app_name, "--no-remote"], 10.0)
            if result.returncode == 0:
                return CommandResult(ok=True, data={"focused": True, "app_name": app_name, "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})
        result = self.runner(["open", "-a", app_name], 10.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"focused": False, "app_name": app_name}, errors=[make_error(code="app_focus_failed", message="macOS refused to open or focus the requested app.", guidance="Verify the app is installed and visible.")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"focused": True, "app_name": app_name, "engine": "macos_open"})

    def desktop_window(self, *, action: str, dry_run: bool = False) -> CommandResult:
        if action not in {"focus", "minimize", "maximize", "zoom", "close"}:
            return CommandResult(ok=False, data={"performed": False, "action": action}, errors=[make_error(code="desktop_window_action_invalid", message="desktop_window action must be focus, minimize, maximize, or close.", guidance="Use a named window action.")])
        if dry_run:
            return CommandResult(ok=True, data={"performed": False, "would_perform": True, "action": action})
        sensitive_block = self._sensitive_app_action_block(frontmost=self._frontmost_app(), action=f"window_{action}")
        if sensitive_block is not None:
            return sensitive_block
        peekaboo_action = "maximize" if action == "zoom" else action
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            result = self.runner([str(peekaboo["path"]), "window", peekaboo_action, "--json", "--no-remote"], 20.0)
            if result.returncode == 0:
                return CommandResult(ok=True, data={"performed": True, "action": action, "peekaboo_action": peekaboo_action, "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})
        key = {"close": "w", "minimize": "m", "maximize": "f", "zoom": "f", "focus": "`"}[action]
        combo = "cmd+" + key if action not in {"maximize", "zoom"} else "ctrl+cmd+f"
        return self._osascript_hotkey(combo)

    def desktop_menu(self, *, menu_path: str, dry_run: bool = False) -> CommandResult:
        if not isinstance(menu_path, str) or not menu_path.strip() or len(menu_path) > 240:
            return CommandResult(ok=False, data={"performed": False}, errors=[make_error(code="desktop_menu_path_required", message="desktop_menu requires a menu path such as File > New Tab.", guidance="Use the visible app menu path.")])
        if dry_run:
            return CommandResult(ok=True, data={"performed": False, "would_perform": True, "menu_path": menu_path})
        sensitive_block = self._sensitive_app_action_block(frontmost=self._frontmost_app(), action="menu")
        if sensitive_block is not None:
            return sensitive_block
        frontmost = self._frontmost_app()
        pid = self._pid_for_app(frontmost)
        if pid is not None and self.helper_client is not None:
            result = self._helper_ax_action(
                action="menu",
                target={"pid": pid, "app_name": frontmost, "process_name": self._process_name_for_pid(pid), "path": []},
                menu_path=menu_path,
                fallback_data={"performed": False, "menu_path": menu_path},
            )
            if result.ok:
                result.data.update({"performed": True, "menu_path": menu_path, "engine": result.data.get("engine", "helper_ax")})
                return result
            if result.errors and result.errors[0].get("code") not in {"helper_ax_menu_not_found", "helper_ax_menu_failed"}:
                return result
        peekaboo = self._peekaboo_status()
        if not peekaboo.get("available"):
            return CommandResult(ok=False, data={"performed": False, "menu_path": menu_path}, errors=[make_error(code="peekaboo_required", message="desktop_menu requires Peekaboo for reliable menu traversal.", guidance="Install Peekaboo with brew install steipete/tap/peekaboo and approve Workbench permissions.")])
        result = self.runner([str(peekaboo["path"]), "menu", "click", "--path", menu_path, "--json", "--no-remote"], 20.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"performed": False, "menu_path": menu_path}, errors=[make_error(code="desktop_menu_failed", message="Peekaboo could not perform the requested menu path.", guidance="Run desktop_see, verify the app is focused, then retry.")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"performed": True, "menu_path": menu_path, "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})

    def desktop_browser_action(self, *, action: str, url: str | None = None, dry_run: bool = False) -> CommandResult:
        if action not in {"reload", "back", "forward", "new_tab", "open_url"}:
            return CommandResult(ok=False, data={"performed": False, "action": action}, errors=[make_error(code="browser_action_invalid", message="desktop_browser_action action must be reload, back, forward, new_tab, or open_url.", guidance="Use one of the named browser actions.")])
        if action == "open_url" and (not url or urlparse(url).scheme not in {"http", "https"}):
            return CommandResult(ok=False, data={"performed": False, "action": action, "url": redact_value(url)}, errors=[make_error(code="browser_url_invalid", message="open_url requires an http(s) URL.", guidance="Pass a normal website URL.")])
        if dry_run:
            return CommandResult(ok=True, data={"performed": False, "would_perform": True, "action": action, "url": redact_value(url)})
        if action == "open_url":
            peekaboo = self._peekaboo_status()
            if peekaboo.get("available"):
                result = self.runner([str(peekaboo["path"]), "open", str(url), "--wait-until-ready", "--json", "--no-remote"], 20.0)
                if result.returncode == 0:
                    return CommandResult(ok=True, data={"performed": True, "action": action, "url": redact_value(url), "engine": "peekaboo"}, warnings=self._stderr_warning(result), provenance={"source": "peekaboo"})
            result = self.runner(["open", url], 10.0)
            if result.returncode != 0:
                return CommandResult(ok=False, data={"performed": False, "action": action, "url": redact_value(url)}, errors=[make_error(code="browser_open_url_failed", message="macOS could not open the URL.", guidance="Verify the URL and default browser.")], warnings=self._stderr_warning(result))
            return CommandResult(ok=True, data={"performed": True, "action": action, "url": redact_value(url), "engine": "macos_open"})
        hotkeys = {"reload": "cmd+r", "back": "cmd+[", "forward": "cmd+]", "new_tab": "cmd+t"}
        return self.desktop_hotkey(keys=hotkeys[action], dry_run=False)

    def iphone_see(self, *, max_chars: int = 4000, max_nodes: int = 200) -> CommandResult:
        status = self.iphone_mirroring_status()
        if not status.data.get("running"):
            return status
        if status.data.get("frontmost") is not True:
            if self._full_access_active():
                focus = self.iphone_mirroring_focus(dry_run=False)
                if focus.ok:
                    status = self.iphone_mirroring_status()
            if status.data.get("frontmost") is not True:
                return CommandResult(
                    ok=False,
                    data={"target": "iphone_mirroring", "running": True, "frontmost": False},
                    errors=[
                        make_error(
                            code="iphone_mirroring_not_frontmost",
                            message="iPhone Mirroring is running but is not the visible frontmost app.",
                            guidance="Focus iPhone Mirroring from Workbench or an active control session, then rerun iphone_see.",
                        )
                    ],
                )
        peekaboo = self._peekaboo_status()
        warnings: list[str] = []
        if peekaboo.get("available"):
            seen = self._peekaboo_iphone_region_see(peekaboo=peekaboo)
            if seen.ok:
                return seen
            warnings.extend(seen.warnings)
            warnings.extend(str(error.get("message") or error.get("code") or "Peekaboo iPhone capture failed") for error in seen.errors)
        seen = self.desktop_see(max_chars=max_chars, max_nodes=max_nodes)
        seen.data["target"] = "iphone_mirroring"
        seen.warnings = warnings + seen.warnings
        return seen

    def iphone_tap(
        self,
        *,
        target_label: str | None = None,
        x: int | None = None,
        y: int | None = None,
        snapshot_id: str | None = None,
        element_id: str | None = None,
        dry_run: bool = False,
    ) -> CommandResult:
        if dry_run:
            resolved_label = target_label
            if snapshot_id and element_id is None and target_label is None and x is not None and y is not None:
                resolved_point = self._resolve_snapshot_coordinates(snapshot_id=snapshot_id, x=x, y=y, expected_target="iphone_mirroring")
                if not resolved_point.ok:
                    return resolved_point
                point = resolved_point.data["point"]
                x = int(point["x"])
                y = int(point["y"])
            else:
                resolved = self._resolve_snapshot_target(snapshot_id=snapshot_id, element_id=element_id, target_label=target_label)
                if not resolved.ok:
                    return resolved
                if resolved.data.get("point"):
                    point = resolved.data["point"]
                    x = int(point["x"])
                    y = int(point["y"])
                    resolved_label = str(resolved.data.get("target_label") or target_label or element_id or "")
            return CommandResult(ok=True, data={"performed": False, "would_tap": True, "target_label": resolved_label, "snapshot_id": snapshot_id, "element_id": element_id, "point": self._point(x, y)})
        focus = self.iphone_mirroring_focus(dry_run=False)
        if not focus.ok:
            return focus
        if snapshot_id and element_id is None and target_label is None and x is not None and y is not None:
            resolved_point = self._resolve_snapshot_coordinates(snapshot_id=snapshot_id, x=x, y=y, expected_target="iphone_mirroring")
            if not resolved_point.ok:
                return resolved_point
            point = resolved_point.data["point"]
            x = int(point["x"])
            y = int(point["y"])
            snapshot_id = None
        return self.desktop_click(target_label=target_label, x=x, y=y, snapshot_id=snapshot_id, element_id=element_id, dry_run=False)

    def iphone_swipe(self, *, direction: str, dry_run: bool = False) -> CommandResult:
        mapping = {
            "left": "swipe_left",
            "right": "swipe_right",
            "up": "swipe_up",
            "down": "swipe_down",
        }
        action = mapping.get(direction)
        if action is None:
            return CommandResult(ok=False, data={"performed": False, "direction": direction}, errors=[make_error(code="iphone_swipe_direction_invalid", message="iphone_swipe direction must be left, right, up, or down.", guidance="Use a named direction.")])
        return self.iphone_mirroring_action(action=action, dry_run=dry_run)

    def iphone_type(self, *, text: str, dry_run: bool = False) -> CommandResult:
        if dry_run:
            return CommandResult(ok=True, data={"performed": False, "would_type": True, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text)})
        focus = self.iphone_mirroring_focus(dry_run=False)
        if not focus.ok:
            return focus
        typed = self._keystroke_arbitrary_text(text)
        if typed.ok:
            typed.provenance = {"source": "system_events", "customer_control": True, "reason": "iphone_mirroring_exact_text"}
            return typed
        fallback = self.desktop_type(text=text, dry_run=False)
        fallback.warnings = typed.warnings + ["System Events exact iPhone typing failed; used desktop text fallback."] + fallback.warnings
        return fallback

    def snapshot(self, *, max_chars: int) -> CommandResult:
        frontmost = self._frontmost_app()
        sensitive_block = self._sensitive_app_observation_block(frontmost=frontmost, surface="screenshot")
        if sensitive_block is not None:
            return sensitive_block
        screenshot_path = self._capture_screenshot([])
        title = self._front_window_title()
        capped_title, title_truncated = cap_text(redact_value(title), max_chars)
        warnings = ["window title truncated"] if title_truncated else []
        snapshot_id = self._new_snapshot_id("desktop")
        image = self._image_artifact(screenshot_path, snapshot_id=snapshot_id) if screenshot_path else None
        return CommandResult(
            ok=screenshot_path is not None,
            data={
                "snapshot_id": snapshot_id if screenshot_path else None,
                "timestamp": self.now(),
                "frontmost_app": redact_value(frontmost),
                "window_title": capped_title,
                "screenshot_path": redact_value(screenshot_path) if screenshot_path else None,
                "screenshot": image,
                "max_chars": max_chars,
            },
            warnings=warnings if screenshot_path else warnings + ["screenshot unavailable; Screen Recording permission may be missing"],
        )

    def ax_tree(self, *, max_nodes: int) -> CommandResult:
        frontmost = self._frontmost_app()
        sensitive_block = self._sensitive_app_observation_block(frontmost=frontmost, surface="ax_tree")
        if sensitive_block is not None:
            return sensitive_block
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
        process_name = self._process_name_for_pid(pid)
        raw_nodes: list[Any] = []
        for row in payload.get("nodes", [])[:max_nodes]:
            if isinstance(row, dict):
                row = dict(row)
                path = row.get("ax_path")
                if isinstance(path, list):
                    row["ax_target"] = {"pid": pid, "app_name": frontmost, "process_name": process_name, "path": path}
            raw_nodes.append(row)
        nodes = [self._safe_node(row) for row in raw_nodes][:max_nodes]
        truncated = bool(payload.get("truncated"))
        if truncated:
            warnings.append(f"AX tree truncated at {max_nodes} nodes")
        return CommandResult(ok=True, data={"frontmost_app": redact_value(frontmost), "pid": pid, "nodes": nodes, "truncated": truncated, "max_nodes": max_nodes}, warnings=warnings)

    def app_focus(self, *, app_name: str, dry_run: bool = False) -> CommandResult:
        if not self._safe_app_name(app_name):
            return CommandResult(ok=False, data={"focused": False, "would_focus": dry_run}, errors=[make_error(code="app_name_not_allowed", message="App name is outside the safe named-action character set.", guidance="Use a visible macOS app name with letters, numbers, spaces, dots, underscores, plus, at-sign, slash, colon, hash, or hyphen.")])
        if self._is_sensitive_app(app_name):
            return CommandResult(ok=False, data={"focused": False, "would_focus": dry_run, "app_name": app_name}, errors=[make_error(code="sensitive_app_blocked", message="This app is on the sensitive-app denylist.", guidance="Only request named actions against non-sensitive apps.")])
        if dry_run:
            return CommandResult(ok=True, data={"focused": False, "would_focus": True, "app_name": app_name})
        warnings: list[str] = []
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            result = self.runner([str(peekaboo["path"]), "app", "switch", "--to", app_name, "--no-remote"], 10.0)
            warnings.extend(self._stderr_warning(result))
            if result.returncode == 0 and self._wait_for_frontmost(app_name, timeout_seconds=2.0):
                return CommandResult(ok=True, data={"focused": True, "app_name": app_name, "engine": "peekaboo", "frontmost": True}, warnings=warnings, provenance={"source": "peekaboo"})
        self._activate_app(app_name)
        if self._wait_for_frontmost(app_name, timeout_seconds=2.0):
            return CommandResult(ok=True, data={"focused": True, "app_name": app_name, "engine": "system_events", "frontmost": True}, warnings=warnings, provenance={"source": "system_events"})
        result = self.runner(["open", "-a", app_name], 10.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"focused": False, "app_name": app_name}, errors=[make_error(code="app_focus_failed", message="macOS refused to open or focus the requested app.", guidance="Verify the app is installed and visible.")], warnings=self._stderr_warning(result))
        warnings.extend(self._stderr_warning(result))
        if self._wait_for_frontmost(app_name, timeout_seconds=3.0):
            return CommandResult(ok=True, data={"focused": True, "app_name": app_name, "engine": "macos_open", "frontmost": True}, warnings=warnings, provenance={"source": "macos_open"})
        return CommandResult(
            ok=False,
            data={"focused": False, "app_name": app_name, "frontmost_app": redact_value(self._frontmost_app())},
            errors=[make_error(code="app_focus_not_frontmost", message="macOS opened the app, but it did not become the frontmost app.", guidance="Click the target app once or retry after closing competing modal windows.")],
            warnings=warnings,
        )

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
                "supported_actions": sorted(SAFE_IPHONE_ACTIONS | GUARDED_IPHONE_ACTIONS),
                "guarded_actions": sorted(GUARDED_IPHONE_ACTIONS),
                "safety": {
                    "full_access_allows_customer_granted_control": True,
                    "ask_permission_gates_high_impact_actions": True,
                    "hidden_shell_public_ports_and_token_exfiltration_blocked": True,
                    "kill_switch_available": True,
                },
            },
        )

    def iphone_mirroring_focus(self, *, dry_run: bool = False) -> CommandResult:
        focused = self.app_focus(app_name="iPhone Mirroring", dry_run=dry_run)
        if dry_run or focused.ok:
            return focused
        bounds = self._iphone_window_bounds()
        if bounds is not None:
            x, y, width, _height = bounds
            click_focus = self._mouse_action("click", x=x + max(24, width // 2), y=y + 16)
            if click_focus.ok and self._wait_for_frontmost("iPhone Mirroring", timeout_seconds=2.0):
                return CommandResult(
                    ok=True,
                    data={"focused": True, "app_name": "iPhone Mirroring", "engine": "window_click", "frontmost": True},
                    warnings=focused.warnings + ["Clicked the iPhone Mirroring window chrome to recover focus."],
                    provenance={"source": "window_click"},
                )
        return focused

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
        if action not in SAFE_IPHONE_ACTIONS:
            if action not in GUARDED_IPHONE_ACTIONS:
                return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action}, errors=[make_error(code="iphone_action_not_allowed", message="This iPhone Mirroring action is not allowlisted.", guidance=f"Allowed actions: {', '.join(sorted(SAFE_IPHONE_ACTIONS | GUARDED_IPHONE_ACTIONS))}.")])
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
                return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "target_label": target_label}, errors=[make_error(code="send_target_label_not_allowed", message="Approved message sends may only press a visible Send control.", guidance="Use target label 'Send' or 'Send message'; do not route this through arbitrary visible labels.")])
        if action == "open_app" and (not app_name or not self._safe_app_name(app_name) or self._is_iphone_sensitive_app(app_name)):
            return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "app_name": app_name}, errors=[make_error(code="iphone_app_name_not_allowed", message="The requested iPhone app name is not allowed for this named action.", guidance="Use a non-sensitive app name with safe characters, for example Calculator or Notes.")])
        if action == "tap_named_target" and (not target_label or not self._safe_app_name(target_label) or (self._is_dangerous_iphone_target(target_label) and not self._full_access_active())):
            return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "target_label": target_label}, errors=[make_error(code="target_label_not_allowed", message="The requested visible target label is not safe.", guidance="Use an exact non-sensitive visible AX label; sends, calls, purchases, auth prompts, camera, microphone, and generic coordinates are blocked.")])
        if action == "scroll" and direction not in SCROLL_DIRECTIONS:
            return CommandResult(ok=False, data={"performed": False, "would_perform": dry_run, "action": action, "direction": direction}, errors=[make_error(code="scroll_direction_required", message="iPhone scroll requires direction 'up' or 'down'.", guidance="Use a named direction only; generic coordinates are blocked.")])
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
                    "guarded": action in GUARDED_IPHONE_ACTIONS,
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
        if action in GUARDED_GESTURE_KEYS:
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
            return CommandResult(ok=True, data={"performed": True, "action": action, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text)}, provenance={"source": "iphone_mirroring", "customer_control": True})
        if action == "send_approved_message":
            typed = self._keystroke_approved_text(text)
            if not typed.ok:
                return typed
            pressed = self._press_iphone_target(target_label=target_label, allow_approved_send=True, action=action)
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
                provenance={"source": "iphone_mirroring_ax", "customer_control": True},
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

    def _peekaboo_see(self, *, peekaboo: dict[str, Any], target: str, max_chars: int, max_nodes: int) -> CommandResult:
        snapshot_id = self._new_snapshot_id(target)
        screenshot_dir = self.state_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{snapshot_id}.png"
        result = self.runner(
            [
                str(peekaboo["path"]),
                "see",
                "--json",
                "--mode",
                "frontmost",
                "--capture-engine",
                "classic",
                "--no-remote",
                "--path",
                str(screenshot_path),
                "--timeout-seconds",
                "30",
            ],
            40.0,
        )
        warnings = self._stderr_warning(result)
        if result.returncode != 0:
            return CommandResult(
                ok=False,
                data={"engine": "peekaboo", "snapshot_id": None, "elements": []},
                warnings=warnings,
                errors=[make_error(code="peekaboo_see_failed", message="Peekaboo could not capture visual evidence.", guidance="Check Peekaboo readiness, Accessibility, and Screen Recording permissions.")],
            )
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return CommandResult(
                ok=False,
                data={"engine": "peekaboo", "snapshot_id": None, "elements": []},
                warnings=warnings,
                errors=[make_error(code="peekaboo_see_parse_failed", message="Peekaboo returned non-JSON visual evidence.", guidance="Run Peekaboo permissions/status from Workbench and retry.")],
            )
        if payload.get("success") is not True:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            return CommandResult(
                ok=False,
                data={"engine": "peekaboo", "snapshot_id": None, "elements": []},
                warnings=warnings,
                errors=[
                    make_error(
                        code=str(error.get("code") or "peekaboo_see_unsuccessful"),
                        message=str(redact_value(error.get("message") or "Peekaboo did not return a successful visual observation.")),
                        guidance="Check Peekaboo readiness, Accessibility, and Screen Recording permissions.",
                    )
                ],
            )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        raw_path = data.get("screenshot_raw")
        image_path = Path(str(raw_path)).expanduser() if raw_path else screenshot_path
        image = self._image_artifact(image_path, snapshot_id=snapshot_id) if image_path.exists() else None
        peekaboo_snapshot_id = str(data.get("snapshot_id") or "")
        elements = self._elements_from_peekaboo(data.get("ui_elements", []), snapshot_id=snapshot_id, max_nodes=max_nodes)
        if elements:
            self._write_snapshot_index(snapshot_id=snapshot_id, target=target, elements=elements, engine="peekaboo", peekaboo_snapshot_id=peekaboo_snapshot_id or None)
        observation = data.get("observation") if isinstance(data.get("observation"), dict) else {}
        target_info = observation.get("target") if isinstance(observation.get("target"), dict) else {}
        truncation = data.get("truncation") if isinstance(data.get("truncation"), dict) else None
        if truncation and truncation.get("warning"):
            warning, _ = cap_text(str(redact_value(truncation["warning"])), 240)
            warnings.append(warning)
        if len(elements) >= max_nodes and int(data.get("element_count") or 0) > max_nodes:
            warnings.append(f"Peekaboo elements capped at {max_nodes}; rerun with a higher max_nodes value if needed.")
        return CommandResult(
            ok=image is not None or bool(elements),
            data={
                "engine": "peekaboo",
                "frontmost_app": redact_value(data.get("application_name") or self._frontmost_app()),
                "window_title": redact_value(data.get("window_title")),
                "snapshot_id": snapshot_id,
                "peekaboo_snapshot_id": redact_value(peekaboo_snapshot_id) if peekaboo_snapshot_id else None,
                "peekaboo": peekaboo,
                "peekaboo_output": None,
                "peekaboo_truncated": False,
                "screenshot": {"screenshot": image} if image else None,
                "ax": {
                    "source": "peekaboo",
                    "element_count": data.get("element_count"),
                    "interactable_count": data.get("interactable_count"),
                    "ui_map": redact_value(data.get("ui_map")),
                },
                "elements": elements,
                "capture": {
                    "mode": data.get("capture_mode"),
                    "target": redact_value(target_info),
                    "execution_time": data.get("execution_time"),
                },
            },
            warnings=warnings,
            errors=[] if image is not None or elements else [make_error(code="peekaboo_see_empty", message="Peekaboo succeeded but returned no screenshot or elements.", guidance="Bring a normal app window to the front and retry.")],
            provenance={"source": "peekaboo_visual"},
        )

    def _peekaboo_iphone_region_see(self, *, peekaboo: dict[str, Any]) -> CommandResult:
        bounds = self._peekaboo_iphone_window_bounds(peekaboo=peekaboo) or self._iphone_window_bounds()
        if bounds is None:
            return CommandResult(
                ok=False,
                data={"target": "iphone_mirroring", "engine": "peekaboo", "snapshot_id": None, "elements": []},
                errors=[make_error(code="iphone_mirroring_window_not_found", message="Could not resolve the visible iPhone Mirroring window.", guidance="Open iPhone Mirroring, keep it visible, and retry.")],
            )
        x, y, width, height = bounds
        snapshot_id = self._new_snapshot_id("iphone_mirroring")
        screenshot_dir = self.state_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{snapshot_id}.png"
        result = self.runner(
            [
                str(peekaboo["path"]),
                "image",
                "--mode",
                "area",
                "--region",
                f"{x},{y},{width},{height}",
                "--path",
                str(screenshot_path),
                "--json",
                "--no-remote",
            ],
            20.0,
        )
        warnings = self._stderr_warning(result)
        if result.returncode != 0 or not screenshot_path.exists():
            return CommandResult(
                ok=False,
                data={"target": "iphone_mirroring", "engine": "peekaboo", "snapshot_id": None, "elements": []},
                warnings=warnings,
                errors=[make_error(code="iphone_mirroring_region_capture_failed", message="Peekaboo could not capture the visible iPhone Mirroring region.", guidance="Verify Screen Recording permission and keep iPhone Mirroring visible.")],
            )
        image = self._image_artifact(screenshot_path, snapshot_id=snapshot_id)
        elements = [
            {
                "element_id": "iphone-mirroring-window",
                "snapshot_id": snapshot_id,
                "label": "iPhone Mirroring window",
                "role": "window",
                "bounds": {"x": x, "y": y, "width": width, "height": height},
                "center": {"x": x + width // 2, "y": y + height // 2},
                "actions": ["click"],
                "engine": "peekaboo_region",
            }
        ]
        image_width = image.get("width") if image else None
        image_height = image.get("height") if image else None
        coordinate_space = {
            "type": "window_region",
            "origin": {"x": x, "y": y},
            "size": {"width": width, "height": height},
            "image_size": {"width": image_width, "height": image_height},
            "scale": {"x": (float(image_width) / float(width)) if image_width and width else 1.0, "y": (float(image_height) / float(height)) if image_height and height else 1.0},
            "tap_coordinates": "Pass x/y relative to this iPhone screenshot together with snapshot_id; the connector translates them to global screen coordinates.",
        }
        self._write_snapshot_index(
            snapshot_id=snapshot_id,
            target="iphone_mirroring",
            elements=elements,
            engine="peekaboo_region",
            coordinate_space=coordinate_space,
        )
        return CommandResult(
            ok=image is not None,
            data={
                "target": "iphone_mirroring",
                "engine": "peekaboo",
                "capture_engine": "peekaboo_region",
                "frontmost_app": "iPhone Mirroring",
                "window_title": "iPhone Mirroring",
                "snapshot_id": snapshot_id,
                "screenshot": {"screenshot": image} if image else None,
                "coordinate_space": coordinate_space,
                "elements": elements,
            },
            warnings=warnings,
            errors=[] if image is not None else [make_error(code="iphone_mirroring_artifact_failed", message="The iPhone screenshot was captured but could not be recorded as an artifact.", guidance="Retry iphone_see.")],
            provenance={"source": "peekaboo_region", "customer_control": True},
        )

    def _peekaboo_iphone_window_bounds(self, *, peekaboo: dict[str, Any]) -> tuple[int, int, int, int] | None:
        result = self.runner([str(peekaboo["path"]), "window", "list", "--app", "iPhone Mirroring", "--json", "--no-remote"], 10.0)
        if result.returncode != 0:
            return None
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return None
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        windows = data.get("windows") if isinstance(data.get("windows"), list) else []
        candidates: list[tuple[int, int, int, int]] = []
        for item in windows:
            if not isinstance(item, dict) or item.get("is_on_screen") is not True:
                continue
            title = str(item.get("window_title") or "")
            if title != "iPhone Mirroring":
                continue
            bounds = item.get("bounds")
            if not isinstance(bounds, dict):
                continue
            try:
                x = int(bounds["x"])
                y = int(bounds["y"])
                width = int(bounds["width"])
                height = int(bounds["height"])
            except (KeyError, TypeError, ValueError):
                continue
            if width > 0 and height > 0:
                candidates.append((x, y, width, height))
        if not candidates:
            return None
        return max(candidates, key=lambda row: row[2] * row[3])

    def _peekaboo_status(self) -> dict[str, Any]:
        path: str | None = None
        for candidate in PEEKABOO_BIN_CANDIDATES:
            if "/" in candidate:
                if Path(candidate).exists():
                    path = candidate
                    break
            else:
                found = shutil.which(candidate)
                if found:
                    path = found
                    break
        if not path:
            return {
                "available": False,
                "install": "brew install steipete/tap/peekaboo",
                "guidance": "Peekaboo gives agents the best Mac computer-control parity. Built-in Accessibility and PostToPid helper fallbacks remain available for core actions.",
            }
        result = self.runner([path, "--version"], 3.0)
        version = result.stdout.strip() or result.stderr.strip() or None
        return {"available": result.returncode == 0, "path": path, "version": redact_value(version)}

    def _peekaboo_permission_status(self, permission: str) -> bool | None:
        peekaboo = self._peekaboo_status()
        if not peekaboo.get("available"):
            return None
        commands = (
            [str(peekaboo["path"]), "permissions", "status", "--json", "--no-remote"],
            [str(peekaboo["path"]), "permissions", "--json", "--no-remote"],
            [str(peekaboo["path"]), "list", "permissions", "--json"],
        )
        wanted = "Screen Recording" if permission == "screen_recording" else "Accessibility"
        for command in commands:
            result = self.runner(command, 10.0)
            if result.returncode != 0:
                continue
            try:
                payload = json.loads(result.stdout.strip() or "{}")
            except json.JSONDecodeError:
                continue
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            permissions = data.get("permissions") if isinstance(data.get("permissions"), list) else []
            for item in permissions:
                if isinstance(item, dict) and item.get("name") == wanted:
                    return bool(item.get("isGranted"))
        return None

    def _press_frontmost_target(self, *, target_label: str) -> CommandResult:
        if self.accessibility_checker() is False:
            return CommandResult(ok=False, data={"clicked": False, "target_label": target_label}, errors=[self._permission_error("accessibility", "click a visible target")])
        frontmost = self._frontmost_app()
        pid = self._pid_for_app(frontmost)
        if pid is None:
            return CommandResult(ok=False, data={"clicked": False, "target_label": target_label, "frontmost_app": redact_value(frontmost)}, errors=[make_error(code="frontmost_pid_not_found", message="Could not resolve a frontmost app PID.", guidance="Focus the target app and rerun desktop_see.")])
        result = self.runner([sys.executable, "-c", self.AX_PRESS_LABEL_SCRIPT, str(pid), target_label, "700", "1"], 20.0)
        warnings = self._stderr_warning(result)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"clicked": False, "target_label": target_label}, errors=[make_error(code="desktop_target_lookup_unavailable", message="Unable to inspect visible targets.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=warnings)
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return CommandResult(ok=False, data={"clicked": False, "target_label": target_label}, errors=[make_error(code="desktop_target_lookup_parse_failed", message="Unable to parse target lookup output.", guidance="Check pyobjc GUI dependencies in the bridge environment.")], warnings=warnings)
        if not payload.get("ok"):
            return CommandResult(
                ok=False,
                data={"clicked": False, "target_label": target_label, "matches": [self._safe_node(row) for row in payload.get("matches", [])]},
                errors=[make_error(code=str(payload.get("error") or "desktop_target_click_failed").split(":", 1)[0], message="The visible target could not be clicked.", guidance="Run desktop_see and use a unique visible label, or use coordinates as a fallback.")],
                warnings=warnings,
            )
        return CommandResult(ok=True, data={"clicked": True, "target_label": target_label, "matches": [self._safe_node(row) for row in payload.get("matches", [])]}, warnings=warnings, provenance={"source": "accessibility"})

    def _mouse_action(self, action: str, **kwargs: Any) -> CommandResult:
        if self.accessibility_checker() is False:
            return CommandResult(ok=False, data={"performed": False, "action": action}, errors=[self._permission_error("accessibility", f"perform desktop {action}")])
        data: dict[str, Any] = {"performed": False, "action": action}
        if action == "click":
            data["point"] = self._point(kwargs["x"], kwargs["y"])
        elif action == "scroll":
            data["direction"] = kwargs["direction"]
            data["amount"] = kwargs["amount"]
        elif action == "drag":
            data["from"] = self._point(kwargs["from_x"], kwargs["from_y"])
            data["to"] = self._point(kwargs["to_x"], kwargs["to_y"])
        target = kwargs.get("target") if isinstance(kwargs.get("target"), dict) else None
        require_target = kwargs.get("require_target") is True
        if target is None and not require_target:
            frontmost = self._frontmost_app()
            pid = self._pid_for_app(frontmost)
            process_name = self._process_name_for_pid(pid)
            if pid is not None and process_name:
                target = {
                    "pid": int(pid),
                    "app_name": frontmost,
                    "process_name": process_name,
                    "path": [],
                }
        if target is None:
            return CommandResult(
                ok=False,
                data=data,
                errors=[
                    make_error(
                        code="post_to_pid_target_required",
                        message=f"desktop {action} requires a visible process target for per-process posting.",
                        guidance="Run desktop_see and choose a target element, or focus a non-sensitive app whose process identity can be resolved.",
                    )
                ],
            )
        target_block = self._sensitive_ax_target_action_block(ax_target=target, action=action)
        if target_block is not None:
            return target_block
        identity_block = self._ax_target_process_identity_block(ax_target=target, action=action)
        if identity_block is not None:
            return identity_block
        browser_block = self._post_to_pid_browser_target_block(ax_target=target, action=action)
        if browser_block is not None:
            return browser_block
        inert_block = self._inert_ax_target_action_block(ax_target=target, action=action)
        if inert_block is not None:
            return inert_block
        if self.helper_client is None:
            return CommandResult(
                ok=False,
                data={**data, "target": self._safe_ax_target(target)},
                errors=[
                    make_error(
                        code="helper_required_for_post_to_pid",
                        message=f"desktop {action} requires the resident helper for CGEventPostToPid dispatch.",
                        guidance="Start the evaOS computer-use helper from Workbench before using Tier-2 desktop actuation.",
                    )
                ],
            )

        helper_audit_id = f"audit-helper-{uuid.uuid4().hex}"
        payload: dict[str, object] = {"action": action, "target": target}
        if action == "click":
            payload.update({"x": int(kwargs["x"]), "y": int(kwargs["y"])})
        elif action == "scroll":
            payload.update({"direction": str(kwargs["direction"]), "amount": int(kwargs["amount"])})
        elif action == "drag":
            payload.update(
                {
                    "from_x": int(kwargs["from_x"]),
                    "from_y": int(kwargs["from_y"]),
                    "to_x": int(kwargs["to_x"]),
                    "to_y": int(kwargs["to_y"]),
                }
            )
        self._append_helper_actuation_attempt(helper_audit_id=helper_audit_id, helper_command="mouse_action", payload=payload)
        try:
            result = self.helper_client.dispatch("mouse_action", payload, audit_id=helper_audit_id)
            result.provenance.setdefault("helper_audit_id", helper_audit_id)
            self._append_helper_actuation_result(
                helper_audit_id=helper_audit_id,
                helper_command="mouse_action",
                payload=payload,
                result=result,
            )
            return result
        except Exception as exc:
            result = CommandResult(
                ok=False,
                data=data,
                errors=[
                    make_error(
                        code="helper_unavailable",
                        message=f"Persistent computer-use helper failed before performing desktop {action}.",
                        guidance="Restart the evaOS helper before using Tier-2 desktop actuation.",
                    )
                ],
                warnings=[str(redact_value(exc))],
                provenance={"source": "computer_use_helper"},
            )
            self._append_helper_actuation_result(
                helper_audit_id=helper_audit_id,
                helper_command="mouse_action",
                payload=payload,
                result=result,
            )
            return result

    def _helper_ax_action(
        self,
        *,
        action: str,
        target: dict[str, Any],
        fallback_data: dict[str, Any],
        value: str | None = None,
        attribute: str | None = None,
        menu_path: str | None = None,
    ) -> CommandResult:
        identity_block = self._ax_target_process_identity_block(ax_target=target, action=action)
        if identity_block is not None:
            return identity_block
        payload: dict[str, object] = {"action": action, "target": target}
        if value is not None:
            payload["value"] = value
        if attribute is not None:
            payload["attribute"] = attribute
        if menu_path is not None:
            payload["menu_path"] = menu_path
        if self.helper_client is None:
            return CommandResult(
                ok=False,
                data=fallback_data,
                errors=[
                    make_error(
                        code="helper_required_for_ax_action",
                        message="Tier-1 AX actions require the Workbench-managed computer-use helper.",
                        guidance="Start Mac Access from evaOS Workbench so semantic AX actions run under the signed helper identity.",
                    )
                ],
                provenance={"source": "computer_use_helper"},
            )
        helper_audit_id = f"audit-helper-{uuid.uuid4().hex}"
        audit_payload = dict(payload)
        if value is not None:
            audit_payload["value"] = "<redacted>"
            audit_payload["value_sha256"] = self._text_hash(value)
        self._append_helper_actuation_attempt(helper_audit_id=helper_audit_id, helper_command="ax_action", payload=audit_payload)
        try:
            result = self.helper_client.dispatch("ax_action", payload, audit_id=helper_audit_id)
            result.provenance.setdefault("helper_audit_id", helper_audit_id)
            self._append_helper_actuation_result(
                helper_audit_id=helper_audit_id,
                helper_command="ax_action",
                payload=audit_payload,
                result=result,
            )
            return result
        except Exception as exc:
            result = CommandResult(
                ok=False,
                data=fallback_data,
                errors=[
                    make_error(
                        code="helper_unavailable",
                        message=f"Persistent computer-use helper failed before performing AX {action}.",
                        guidance="Restart the evaOS helper or rerun after Mac Access reports ready.",
                    )
                ],
                warnings=[str(redact_value(exc))],
                provenance={"source": "computer_use_helper"},
            )
            self._append_helper_actuation_result(
                helper_audit_id=helper_audit_id,
                helper_command="ax_action",
                payload=audit_payload,
                result=result,
            )
            return result

    def _append_helper_actuation_attempt(
        self,
        *,
        helper_audit_id: str,
        helper_command: str = "mouse_action",
        payload: dict[str, object],
    ) -> None:
        append_audit(
            command=f"helper.{helper_command}",
            target="computer_use_helper",
            args={"payload": payload},
            ok=True,
            warnings=["helper actuation request authorized and recorded before IPC dispatch"],
            errors=[],
            provenance={
                "source": "computer_use_helper",
                "helper_command": helper_command,
                "helper_audit_id": helper_audit_id,
                "audit_phase": "authorized_dispatch",
            },
            state_dir=self.state_dir,
            audit_id=helper_audit_id,
        )

    def _append_helper_actuation_result(
        self,
        *,
        helper_audit_id: str,
        helper_command: str = "mouse_action",
        payload: dict[str, object],
        result: CommandResult,
    ) -> None:
        append_audit(
            command=f"helper.{helper_command}",
            target="computer_use_helper",
            args={"payload": payload},
            ok=result.ok,
            warnings=result.warnings,
            errors=result.errors,
            provenance={
                **result.provenance,
                "source": "computer_use_helper",
                "helper_command": helper_command,
                "helper_audit_id": helper_audit_id,
                "audit_phase": "completion",
            },
            state_dir=self.state_dir,
        )

    def _keystroke_arbitrary_text(self, text: str) -> CommandResult:
        if len(text) > 4000:
            return CommandResult(ok=False, data={"typed": False, "text_sha256": self._text_hash(text)}, errors=[make_error(code="desktop_text_too_long", message="desktop_type text is capped at 4000 characters per action.", guidance="Split longer text into smaller typed chunks.")])
        script = f'tell application "System Events" to keystroke "{self._escape_applescript(text)}"'
        result = self.runner(["osascript", "-e", script], 20.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"typed": False, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text)}, errors=[make_error(code="desktop_text_entry_failed", message="macOS refused desktop text entry.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"typed": True, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text), "engine": "system_events"}, provenance={"source": "system_events"})

    def _normalize_hotkey(self, keys: str) -> str | None:
        if not isinstance(keys, str):
            return None
        parts = [part.strip().lower() for part in re.split(r"[+ ]+", keys) if part.strip()]
        aliases = {"command": "cmd", "control": "ctrl", "option": "opt", "alt": "opt", "escape": "esc", "return": "enter"}
        normalized = [aliases.get(part, part) for part in parts]
        if not normalized or any(not re.fullmatch(r"[a-z0-9_\-\[\]`=,./;']+", part) for part in normalized):
            return None
        return "+".join(normalized)

    def _osascript_hotkey(self, keys: str) -> CommandResult:
        parts = keys.split("+")
        key = parts[-1]
        modifiers = parts[:-1]
        modifier_map = {"cmd": "command down", "shift": "shift down", "ctrl": "control down", "opt": "option down"}
        using = [modifier_map[item] for item in modifiers if item in modifier_map]
        special_key_codes = {"enter": "36", "esc": "53", "tab": "48", "space": "49", "left": "123", "right": "124", "down": "125", "up": "126"}
        if key in special_key_codes:
            script = f'tell application "System Events" to key code {special_key_codes[key]}'
        elif len(key) == 1 or key in {"[", "]", "`", "-", "=", ",", ".", "/", ";", "'"}:
            script = f'tell application "System Events" to keystroke "{self._escape_applescript(key)}"'
        else:
            return CommandResult(ok=False, data={"pressed": False, "keys": keys}, errors=[make_error(code="desktop_hotkey_key_unsupported", message="The fallback hotkey engine does not know that key.", guidance="Install Peekaboo for broader hotkey support.")])
        if using:
            script += " using {" + ", ".join(using) + "}"
        result = self.runner(["osascript", "-e", script], 5.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"pressed": False, "keys": keys}, errors=[make_error(code="desktop_hotkey_failed", message="macOS refused the hotkey.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
        return CommandResult(ok=True, data={"pressed": True, "keys": keys, "engine": "system_events"}, provenance={"source": "system_events"})

    def _point(self, x: int | None, y: int | None) -> dict[str, int] | None:
        if x is None or y is None:
            return None
        return {"x": int(x), "y": int(y)}

    def _iphone_keyboard_action(self, action: str, key_code: str, *, customer_control: bool = False, direction: str | None = None) -> CommandResult:
        key_label = {"18": "1", "19": "2", "20": "3", "36": "enter"}.get(key_code)
        peekaboo = self._peekaboo_status()
        if key_label and peekaboo.get("available"):
            keys = key_label if customer_control else f"cmd+{key_label}"
            argv = [str(peekaboo["path"]), "hotkey", "--keys", keys, "--json", "--no-remote"]
            result = self.runner(argv, 10.0)
            if result.returncode == 0:
                data: dict[str, Any] = {"performed": True, "action": action, "engine": "peekaboo", "keys": keys}
                if direction:
                    data["direction"] = direction
                return CommandResult(ok=True, data=data, warnings=self._stderr_warning(result), provenance={"source": "peekaboo", "customer_control": customer_control})
        script = f'tell application "System Events" to key code {key_code}' if customer_control else f'tell application "System Events" to key code {key_code} using command down'
        result = self.runner(["osascript", "-e", script], 12.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"performed": False, "action": action}, errors=[make_error(code="iphone_keyboard_action_failed", message="macOS refused the iPhone Mirroring keyboard shortcut.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
        warnings = ["This live iPhone action uses the safest keyboard-equivalent lane; verify behavior in the iPhone Mirroring window."] if customer_control else []
        data: dict[str, Any] = {"performed": True, "action": action}
        if direction:
            data["direction"] = direction
        return CommandResult(ok=True, data=data, warnings=warnings, provenance={"source": "iphone_mirroring", "customer_control": customer_control})

    def _iphone_scroll_gesture(self, action: str, *, dx: int, dy: int, direction: str | None = None) -> CommandResult:
        if self.accessibility_checker() is False:
            return CommandResult(ok=False, data={"performed": False, "action": action, "direction": direction}, errors=[self._permission_error("accessibility", "send a named iPhone Mirroring gesture")])
        focus = self.iphone_mirroring_focus(dry_run=False)
        if not focus.ok:
            return focus
        bounds = self._iphone_window_bounds()
        if bounds is None:
            return CommandResult(ok=False, data={"performed": False, "action": action, "direction": direction}, errors=[make_error(code="iphone_mirroring_not_running", message="iPhone Mirroring is not currently running.", guidance="Open iPhone Mirroring and rerun the named action.")])
        x, y, width, height = bounds
        margin_x = max(32, int(width * 0.18))
        margin_y = max(64, int(height * 0.20))
        center_x = x + width // 2
        center_y = y + height // 2
        if dx < 0:
            start = (x + width - margin_x, center_y)
            end = (x + margin_x, center_y)
        elif dx > 0:
            start = (x + margin_x, center_y)
            end = (x + width - margin_x, center_y)
        elif dy > 0:
            start = (center_x, y + height - margin_y)
            end = (center_x, y + margin_y)
        else:
            start = (center_x, y + margin_y)
            end = (center_x, y + height - margin_y)
        peekaboo = self._peekaboo_status()
        if peekaboo.get("available"):
            result = self.runner(
                [
                    str(peekaboo["path"]),
                    "swipe",
                    "--from-coords",
                    f"{start[0]},{start[1]}",
                    "--to-coords",
                    f"{end[0]},{end[1]}",
                    "--duration",
                    "700",
                    "--profile",
                    "human",
                    "--json",
                    "--no-remote",
                ],
                20.0,
            )
            if result.returncode == 0:
                data: dict[str, Any] = {"performed": True, "action": action, "gesture": "swipe", "from": self._point(*start), "to": self._point(*end), "engine": "peekaboo"}
                if direction:
                    data["direction"] = direction
                return CommandResult(ok=True, data=data, warnings=self._stderr_warning(result), provenance={"source": "peekaboo", "customer_control": True})
        pid = self._pid_for_app("iPhone Mirroring")
        process_name = self._process_name_for_pid(pid)
        target = {"pid": int(pid), "app_name": "iPhone Mirroring", "process_name": process_name, "path": []} if pid is not None and process_name else None
        dragged = self._mouse_action("drag", from_x=start[0], from_y=start[1], to_x=end[0], to_y=end[1], target=target)
        if not dragged.ok:
            return CommandResult(ok=False, data={"performed": False, "action": action, "direction": direction, "from": self._point(*start), "to": self._point(*end)}, errors=dragged.errors, warnings=dragged.warnings)
        data: dict[str, Any] = {"performed": True, "action": action, "gesture": "drag", "from": self._point(*start), "to": self._point(*end)}
        if direction:
            data["direction"] = direction
        return CommandResult(
            ok=True,
            data=data,
            warnings=dragged.warnings + ["Live iPhone gesture drags inside the visible iPhone Mirroring window; verify behavior before repeating."],
            provenance={"source": "iphone_mirroring_drag", "customer_control": True},
        )

    def _press_iphone_target(self, *, target_label: str, allow_approved_send: bool = False, action: str = "tap_named_target") -> CommandResult:
        if self.accessibility_checker() is False:
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label}, errors=[self._permission_error("accessibility", "tap a named iPhone Mirroring target")])
        pid = self._pid_for_app("iPhone Mirroring")
        if pid is None:
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label}, errors=[make_error(code="iphone_mirroring_not_running", message="iPhone Mirroring is not currently running.", guidance="Open iPhone Mirroring and rerun the named action.")])
        if self._is_dangerous_iphone_target(target_label) and not self._full_access_active() and not (allow_approved_send and target_label.strip().lower() in {"send", "send message"}):
            return CommandResult(ok=False, data={"performed": False, "action": action, "target_label": target_label}, errors=[make_error(code="target_label_not_allowed", message="The requested visible target label is not safe.", guidance="Only the approved-message action may press a Send target after same-turn approval.")])
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
        return CommandResult(ok=True, data={"performed": True, "action": action, "target_label": target_label, "matches": [self._safe_node(row) for row in payload.get("matches", [])]}, warnings=warnings, provenance={"source": "iphone_mirroring_ax", "customer_control": allow_approved_send})

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
            return CommandResult(ok=False, data={"typed": False, "text_preview": self._safe_preview(text), "text_sha256": self._text_hash(text)}, errors=[make_error(code="approved_text_entry_failed", message="macOS refused approved text entry.", guidance=ACCESSIBILITY_GUIDANCE, permission="accessibility")], warnings=self._stderr_warning(result))
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

    def _process_name_for_pid(self, pid: int | None) -> str | None:
        if type(pid) is not int or pid <= 0:
            return None
        result = self.runner(["/bin/ps", "-p", str(pid), "-o", "comm="], 1.0)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return Path(result.stdout.strip().splitlines()[0]).name

    def _activate_app(self, app_name: str) -> bool:
        if self.platform_name != "Darwin":
            return False
        result = self.runner(["osascript", "-e", f'tell application "{self._escape_applescript(app_name)}" to activate'], 5.0)
        return result.returncode == 0

    def _wait_for_frontmost(self, app_name: str, *, timeout_seconds: float) -> bool:
        if self.platform_name != "Darwin":
            return False
        deadline = datetime.now(timezone.utc).timestamp() + max(0.1, timeout_seconds)
        while datetime.now(timezone.utc).timestamp() < deadline:
            if self._frontmost_app() == app_name:
                return True
            time.sleep(0.2)
        return self._frontmost_app() == app_name

    def _iphone_window_bounds(self) -> tuple[int, int, int, int] | None:
        if self.platform_name != "Darwin":
            return None
        result = self.runner(
            [
                "osascript",
                "-e",
                'tell application "System Events" to tell process "iPhone Mirroring" to get {position, size} of front window',
            ],
            5.0,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        parts = [part.strip() for part in result.stdout.replace("\n", ",").split(",") if part.strip()]
        if len(parts) < 4:
            return None
        try:
            x, y, width, height = (int(float(part)) for part in parts[:4])
        except ValueError:
            return None
        if width <= 0 or height <= 0:
            return None
        return x, y, width, height

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
            trusted = self._peekaboo_permission_status(permission)
            if trusted is None:
                trusted = self.accessibility_checker()
            if trusted is True:
                return {"status": "granted", "guidance": ACCESSIBILITY_GUIDANCE, "source": "peekaboo_or_bridge"}
            if trusted is False:
                return {"status": "missing", "guidance": ACCESSIBILITY_GUIDANCE, "source": "peekaboo_or_bridge"}
            return {"status": "unknown", "guidance": ACCESSIBILITY_GUIDANCE, "source": "peekaboo_or_bridge"}
        if permission == "screen_recording":
            trusted = self._peekaboo_permission_status(permission)
            if trusted is None:
                trusted = self.screen_recording_checker()
            if trusted is True:
                return {"status": "granted", "guidance": SCREEN_RECORDING_GUIDANCE, "source": "peekaboo_or_bridge"}
            if trusted is False:
                return {"status": "missing", "guidance": SCREEN_RECORDING_GUIDANCE, "source": "peekaboo_or_bridge"}
            return {"status": "unknown", "guidance": SCREEN_RECORDING_GUIDANCE, "source": "peekaboo_or_bridge"}
        return {"status": "unknown", "guidance": ACCESSIBILITY_GUIDANCE, "source": "peekaboo_or_bridge"}

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

    def _new_snapshot_id(self, target: str) -> str:
        safe_target = re.sub(r"[^a-z0-9_-]+", "-", target.lower()).strip("-") or "desktop"
        return f"snap-{safe_target}-{uuid.uuid4().hex}"

    def _image_artifact(self, path: Path, *, snapshot_id: str) -> dict[str, Any] | None:
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        sha256 = hashlib.sha256(raw).hexdigest()
        width, height = self._png_dimensions(raw)
        artifact_dir = self.state_dir / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{snapshot_id}.png"
        if path != artifact_path:
            try:
                shutil.copyfile(path, artifact_path)
            except OSError:
                artifact_path = path
        image: dict[str, Any] = {
            "artifact_id": snapshot_id,
            "artifact_url": f"/v1/artifacts/{snapshot_id}.png",
            "artifact_path": redact_value(artifact_path),
            "mime_type": "image/png",
            "sha256": sha256,
            "byte_count": len(raw),
            "width": width,
            "height": height,
        }
        if len(raw) <= SNAPSHOT_INLINE_MAX_BYTES:
            image["bytes_base64"] = base64.b64encode(raw).decode("ascii")
        else:
            image["bytes_base64_omitted"] = True
            image["bytes_base64_omitted_reason"] = f"image exceeds {SNAPSHOT_INLINE_MAX_BYTES} byte inline limit"
        return image

    @staticmethod
    def _png_dimensions(raw: bytes) -> tuple[int | None, int | None]:
        if len(raw) >= 24 and raw.startswith(b"\x89PNG\r\n\x1a\n"):
            try:
                width, height = struct.unpack(">II", raw[16:24])
                return int(width), int(height)
            except struct.error:
                return None, None
        return None, None

    def _elements_from_ax(self, nodes: list[Any], *, snapshot_id: str | None) -> list[dict[str, Any]]:
        elements: list[dict[str, Any]] = []
        if not snapshot_id:
            return elements
        for index, item in enumerate(nodes):
            if not isinstance(item, dict):
                continue
            bounds = item.get("bounds")
            label = item.get("name") or item.get("role")
            if not isinstance(bounds, dict) or not label:
                continue
            try:
                x = int(bounds.get("x"))
                y = int(bounds.get("y"))
                width = int(bounds.get("width"))
                height = int(bounds.get("height"))
            except (TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue
            label_text, _ = cap_text(str(redact_value(label)), 160)
            elements.append(
                {
                    "element_id": f"el-{index + 1:04d}",
                    "snapshot_id": snapshot_id,
                    "label": label_text,
                    "role": item.get("role"),
                    "bounds": {"x": x, "y": y, "width": width, "height": height},
                    "center": {"x": x + width // 2, "y": y + height // 2},
                    "actions": item.get("actions", []),
                    "engine": "ax_fallback",
                    "ax_target": item.get("ax_target") if isinstance(item.get("ax_target"), dict) else None,
                }
            )
        return elements

    def _elements_from_peekaboo(self, nodes: Any, *, snapshot_id: str, max_nodes: int) -> list[dict[str, Any]]:
        elements: list[dict[str, Any]] = []
        if not isinstance(nodes, list):
            return elements
        for index, item in enumerate(nodes):
            if len(elements) >= max_nodes:
                break
            if not isinstance(item, dict):
                continue
            bounds = item.get("bounds")
            label = item.get("label") or item.get("title") or item.get("description") or item.get("role")
            if not isinstance(bounds, dict) or not label:
                continue
            try:
                x = int(round(float(bounds.get("x"))))
                y = int(round(float(bounds.get("y"))))
                width = int(round(float(bounds.get("width"))))
                height = int(round(float(bounds.get("height"))))
            except (TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue
            label_text, _ = cap_text(str(redact_value(label)), 160)
            role_text, _ = cap_text(str(redact_value(item.get("role") or "unknown")), 80)
            actions: list[str] = []
            if item.get("is_actionable") is True:
                actions.append("click")
            element_id = str(item.get("id") or f"peekaboo-{index + 1:04d}")
            elements.append(
                {
                    "element_id": element_id,
                    "peekaboo_element_id": element_id,
                    "snapshot_id": snapshot_id,
                    "label": label_text,
                    "role": role_text,
                    "bounds": {"x": x, "y": y, "width": width, "height": height},
                    "center": {"x": x + width // 2, "y": y + height // 2},
                    "actions": actions,
                    "engine": "peekaboo",
                }
            )
        return elements

    def _write_snapshot_index(
        self,
        *,
        snapshot_id: str,
        target: str,
        elements: list[dict[str, Any]],
        engine: str,
        peekaboo_snapshot_id: str | None = None,
        coordinate_space: dict[str, Any] | None = None,
    ) -> None:
        snapshot_dir = self.state_dir / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "snapshot_id": snapshot_id,
            "target": target,
            "engine": engine,
            "peekaboo_snapshot_id": peekaboo_snapshot_id,
            "coordinate_space": coordinate_space,
            "timestamp": timestamp_utc(),
            "elements": elements[:1000],
        }
        (snapshot_dir / f"{snapshot_id}.json").write_text(json.dumps(redact_value(payload), sort_keys=True) + "\n", encoding="utf-8")

    def _read_snapshot_payload(self, snapshot_id: str) -> CommandResult:
        if not re.fullmatch(r"snap-[a-z0-9_-]+-[a-f0-9]{32}", snapshot_id):
            return CommandResult(
                ok=False,
                data={"resolved": False, "snapshot_id": snapshot_id},
                errors=[make_error(code="snapshot_id_invalid", message="snapshot_id is not a valid evaOS visual snapshot id.", guidance="Use the snapshot_id exactly as returned by desktop_see or iphone_see.")],
            )
        path = self.state_dir / "snapshots" / f"{snapshot_id}.json"
        if not path.exists():
            return CommandResult(
                ok=False,
                data={"resolved": False, "snapshot_id": snapshot_id},
                errors=[make_error(code="snapshot_not_found", message="The requested visual snapshot is no longer available.", guidance="Run desktop_see or iphone_see again, then retry with the fresh snapshot_id.")],
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return CommandResult(
                ok=False,
                data={"resolved": False, "snapshot_id": snapshot_id},
                errors=[make_error(code="snapshot_unreadable", message="The requested visual snapshot could not be read.", guidance="Run desktop_see or iphone_see again, then retry with the fresh snapshot_id.")],
            )
        if self._snapshot_stale(payload.get("timestamp")):
            return CommandResult(
                ok=False,
                data={"resolved": False, "snapshot_id": snapshot_id},
                errors=[make_error(code="snapshot_stale", message="The requested visual snapshot is stale.", guidance="Run desktop_see or iphone_see again so the agent acts on the current screen.")],
            )
        return CommandResult(ok=True, data={"resolved": True, "snapshot_id": snapshot_id, "payload": payload})

    def _resolve_snapshot_coordinates(self, *, snapshot_id: str, x: int, y: int, expected_target: str | None = None) -> CommandResult:
        payload_result = self._read_snapshot_payload(snapshot_id)
        if not payload_result.ok:
            return payload_result
        payload = payload_result.data["payload"]
        if expected_target and payload.get("target") != expected_target:
            return CommandResult(
                ok=False,
                data={"resolved": False, "snapshot_id": snapshot_id, "target": payload.get("target")},
                errors=[make_error(code="snapshot_target_mismatch", message="The snapshot target does not match this action.", guidance=f"Run {expected_target}_see again and use that fresh snapshot_id.")],
            )
        coordinate_space = payload.get("coordinate_space") if isinstance(payload.get("coordinate_space"), dict) else {}
        origin = coordinate_space.get("origin") if isinstance(coordinate_space.get("origin"), dict) else {}
        logical_x = int(x)
        logical_y = int(y)
        if coordinate_space.get("type") == "window_region":
            image_size = coordinate_space.get("image_size") if isinstance(coordinate_space.get("image_size"), dict) else {}
            size = coordinate_space.get("size") if isinstance(coordinate_space.get("size"), dict) else {}
            try:
                image_width = float(image_size.get("width") or 0)
                image_height = float(image_size.get("height") or 0)
                width = float(size.get("width") or 0)
                height = float(size.get("height") or 0)
            except (TypeError, ValueError):
                image_width = image_height = width = height = 0
            if image_width > 0 and width > 0:
                logical_x = int(round(float(x) * width / image_width))
            if image_height > 0 and height > 0:
                logical_y = int(round(float(y) * height / image_height))
        global_x = logical_x + int(origin.get("x") or 0)
        global_y = logical_y + int(origin.get("y") or 0)
        ax_target = self._ax_target_for_snapshot_point(payload, x=global_x, y=global_y)
        return CommandResult(
            ok=True,
            data={
                "resolved": True,
                "snapshot_id": snapshot_id,
                "point": {"x": global_x, "y": global_y},
                "input_point": {"x": int(x), "y": int(y)},
                "logical_point": {"x": logical_x, "y": logical_y},
                "coordinate_space": coordinate_space or {"type": "global"},
                **({"ax_target": ax_target} if ax_target is not None else {}),
            },
        )

    def _ax_target_for_snapshot_point(self, payload: dict[str, Any], *, x: int, y: int) -> dict[str, Any] | None:
        elements = payload.get("elements") if isinstance(payload.get("elements"), list) else []
        candidates: list[tuple[int, dict[str, Any]]] = []
        for item in elements:
            if not isinstance(item, dict):
                continue
            ax_target = item.get("ax_target")
            bounds = item.get("bounds")
            if not isinstance(ax_target, dict) or not isinstance(bounds, dict):
                continue
            try:
                bx = int(bounds.get("x"))
                by = int(bounds.get("y"))
                width = int(bounds.get("width"))
                height = int(bounds.get("height"))
            except (TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue
            if bx <= x < bx + width and by <= y < by + height:
                candidates.append((width * height, ax_target))
        if not candidates:
            return None
        candidates.sort(key=lambda row: row[0])
        return candidates[0][1]

    def _resolve_snapshot_target(self, *, snapshot_id: str | None, element_id: str | None, target_label: str | None) -> CommandResult:
        if not snapshot_id and not element_id:
            return CommandResult(ok=True)
        if not snapshot_id:
            return CommandResult(
                ok=False,
                data={"resolved": False, "element_id": element_id},
                errors=[make_error(code="snapshot_id_required", message="element_id clicks require the matching snapshot_id.", guidance="Run desktop_see or iphone_see and pass both snapshot_id and element_id from that result.")],
            )
        payload_result = self._read_snapshot_payload(snapshot_id)
        if not payload_result.ok:
            return payload_result
        payload = payload_result.data["payload"]
        elements = payload.get("elements") if isinstance(payload.get("elements"), list) else []
        match: dict[str, Any] | None = None
        if element_id:
            for item in elements:
                if isinstance(item, dict) and item.get("element_id") == element_id:
                    match = item
                    break
        elif target_label:
            normalized = target_label.strip().lower()
            matches = [item for item in elements if isinstance(item, dict) and str(item.get("label") or "").strip().lower() == normalized]
            if len(matches) == 1:
                match = matches[0]
            elif len(matches) > 1:
                return CommandResult(
                    ok=False,
                    data={"resolved": False, "snapshot_id": snapshot_id, "target_label": target_label, "matches": matches[:10]},
                    errors=[make_error(code="snapshot_target_ambiguous", message="Multiple snapshot elements match that label.", guidance="Use the element_id from desktop_see or iphone_see.")],
                )
        if match is None:
            return CommandResult(
                ok=False,
                data={"resolved": False, "snapshot_id": snapshot_id, "element_id": element_id, "target_label": target_label},
                errors=[make_error(code="snapshot_target_not_found", message="No element in that snapshot matched the requested target.", guidance="Use an element_id or target_label from the latest desktop_see or iphone_see result.")],
            )
        point = match.get("center")
        if not isinstance(point, dict):
            bounds = match.get("bounds")
            if not isinstance(bounds, dict):
                return CommandResult(
                    ok=False,
                    data={"resolved": False, "snapshot_id": snapshot_id, "element_id": element_id},
                    errors=[make_error(code="snapshot_target_missing_bounds", message="The matched element has no usable bounds.", guidance="Use x/y coordinates from the screenshot as a fallback.")],
                )
            point = {"x": int(bounds["x"]) + int(bounds["width"]) // 2, "y": int(bounds["y"]) + int(bounds["height"]) // 2}
        return CommandResult(
            ok=True,
            data={
                "resolved": True,
                "snapshot_id": snapshot_id,
                "element_id": match.get("element_id"),
                "peekaboo_element_id": match.get("peekaboo_element_id"),
                "target_label": match.get("label"),
                "role": match.get("role"),
                "actions": match.get("actions") if isinstance(match.get("actions"), list) else [],
                "ax_target": match.get("ax_target") if isinstance(match.get("ax_target"), dict) else None,
                "engine": match.get("engine") or payload.get("engine"),
                "peekaboo_snapshot_id": payload.get("peekaboo_snapshot_id"),
                "point": {"x": int(point["x"]), "y": int(point["y"])},
            },
        )

    @staticmethod
    def _snapshot_stale(timestamp: Any) -> bool:
        if not isinstance(timestamp, str):
            return True
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() > SNAPSHOT_MAX_AGE_SECONDS

    def _full_access_active(self) -> bool:
        session = read_control_session(self.state_dir)
        return session.get("active") is True and session.get("mode") == "full_access" and session.get("kill_switch") is not True

    def _safe_node(self, row: dict[str, Any]) -> dict[str, Any]:
        role, _ = cap_text(str(redact_value(row.get("role") or "unknown")), 80)
        name, _ = cap_text(str(redact_value(row.get("name"))) if row.get("name") else None, 160)
        node: dict[str, Any] = {"role": role, "name": name, "depth": int(row.get("depth") or 0), "window_index": row.get("window_index")}
        bounds = row.get("bounds")
        if isinstance(bounds, dict):
            try:
                node["bounds"] = {
                    "x": int(bounds.get("x")),
                    "y": int(bounds.get("y")),
                    "width": int(bounds.get("width")),
                    "height": int(bounds.get("height")),
                }
            except (TypeError, ValueError):
                pass
        actions = row.get("actions")
        if isinstance(actions, list):
            node["actions"] = [str(redact_value(item)) for item in actions[:20]]
        identifier = row.get("identifier")
        if isinstance(identifier, str) and identifier:
            node["identifier"] = str(redact_value(identifier))[:160]
        ax_target = row.get("ax_target")
        if isinstance(ax_target, dict):
            node["ax_target"] = self._safe_ax_target(ax_target)
        return node

    def _safe_ax_target(self, target: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        pid = target.get("pid")
        if type(pid) is int and pid > 0:
            safe["pid"] = pid
        app_name = target.get("app_name")
        if isinstance(app_name, str) and app_name:
            safe["app_name"] = redact_value(app_name)
        process_name = target.get("process_name")
        if isinstance(process_name, str) and process_name:
            safe["process_name"] = redact_value(process_name)
        path = target.get("path")
        if isinstance(path, list):
            safe_path: list[dict[str, Any]] = []
            for segment in path[:24]:
                if not isinstance(segment, dict):
                    continue
                safe_segment: dict[str, Any] = {}
                role = segment.get("role")
                if isinstance(role, str) and role.startswith("AX"):
                    safe_segment["role"] = role[:80]
                name = segment.get("name")
                if isinstance(name, str) and name:
                    safe_segment["name"] = str(redact_value(name))[:160]
                identifier = segment.get("identifier")
                if isinstance(identifier, str) and identifier:
                    safe_segment["identifier"] = str(redact_value(identifier))[:160]
                index = segment.get("index")
                if type(index) is int and index >= 0:
                    safe_segment["index"] = index
                if safe_segment:
                    safe_path.append(safe_segment)
            safe["path"] = safe_path
            safe["path_hash"] = hashlib.sha256(json.dumps(safe_path, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        return safe

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

    def _sensitive_app_observation_block(self, *, frontmost: str | None, surface: str) -> CommandResult | None:
        if not self._is_sensitive_app(frontmost):
            return None
        data: dict[str, Any] = {"frontmost_app": redact_value(frontmost)}
        if surface == "screenshot":
            data["screenshot_path"] = None
            message = "The frontmost app is on the sensitive-app denylist; screenshot capture was blocked."
        elif surface == "ax_tree":
            data.update({"nodes": [], "truncated": False})
            message = "The frontmost app is on the sensitive-app denylist; AX tree capture was blocked."
        else:
            data.update({"engine": None, "snapshot_id": None, "elements": []})
            message = "The frontmost app is on the sensitive-app denylist; desktop visual observation was blocked."
        return CommandResult(
            ok=False,
            data=data,
            errors=[
                make_error(
                    code="sensitive_app_blocked",
                    message=message,
                    guidance="Move focus to a non-sensitive app and rerun the named observation command.",
                )
            ],
        )

    def _sensitive_app_action_block(self, *, frontmost: str | None, action: str) -> CommandResult | None:
        if not self._is_sensitive_app(frontmost):
            return None
        return CommandResult(
            ok=False,
            data={"performed": False, "action": action, "frontmost_app": redact_value(frontmost)},
            errors=[
                make_error(
                    code="sensitive_app_blocked",
                    message="The frontmost app is on the sensitive-app denylist; live desktop control was blocked.",
                    guidance="Move focus to a non-sensitive app and rerun the named control command.",
                )
            ],
        )

    def _sensitive_ax_target_action_block(self, *, ax_target: dict[str, Any], action: str) -> CommandResult | None:
        app_name = ax_target.get("app_name")
        if not isinstance(app_name, str) or not self._is_sensitive_app(app_name):
            return None
        return CommandResult(
            ok=False,
            data={"performed": False, "action": action, "target_app": redact_value(app_name), "target_pid": ax_target.get("pid")},
            errors=[
                make_error(
                    code="sensitive_app_blocked",
                    message="The target app is on the sensitive-app denylist; background AX control was blocked.",
                    guidance="Use customer-visible non-sensitive apps only. Background AX target identity is checked separately from the frontmost app.",
                )
            ],
        )

    def _ax_target_process_identity_block(self, *, ax_target: dict[str, Any], action: str) -> CommandResult | None:
        pid = ax_target.get("pid")
        process_name = ax_target.get("process_name")
        if type(pid) is int and pid > 0 and isinstance(process_name, str) and process_name.strip():
            return None
        return CommandResult(
            ok=False,
            data={"performed": False, "action": action, "target_pid": ax_target.get("pid")},
            errors=[
                make_error(
                    code="ax_target_process_identity_required",
                    message="AX action target process identity is missing; live action was blocked.",
                    guidance="Run desktop_see again so the snapshot includes process identity before dispatch.",
                )
            ],
        )

    def _post_to_pid_browser_target_block(self, *, ax_target: dict[str, Any], action: str) -> CommandResult | None:
        path = ax_target.get("path")
        if isinstance(path, list) and path:
            return None
        app_name = ax_target.get("app_name")
        process_name = ax_target.get("process_name")
        names = {name for name in (app_name, process_name) if isinstance(name, str)}
        if not any(name in SAFE_BROWSER_APPS or Path(name).name in SAFE_BROWSER_APPS for name in names):
            return None
        return CommandResult(
            ok=False,
            data={"performed": False, "action": action, "target_pid": ax_target.get("pid"), "target_app": redact_value(app_name)},
            errors=[
                make_error(
                    code="post_to_pid_browser_target_ambiguous",
                    message="Browser coordinate targets are not safe for Tier-2 per-process posting.",
                    guidance="Use browser/CDP/Playwright or a native Accessibility target with a fresh AX path; browser web content is treated as inert for PostToPid.",
                )
            ],
        )

    def _inert_ax_target_action_block(self, *, ax_target: dict[str, Any], action: str) -> CommandResult | None:
        path = ax_target.get("path")
        if not isinstance(path, list):
            return None
        if not any(isinstance(segment, dict) and segment.get("role") == "AXWebArea" for segment in path):
            return None
        return CommandResult(
            ok=False,
            data={"performed": False, "action": action, "target_pid": ax_target.get("pid")},
            errors=[
                make_error(
                    code="ax_web_content_inert",
                    message="AX actions against browser web content are treated as inert and are not reported as success.",
                    guidance="Use the browser/CDP/Playwright strategy for web content instead of Tier-1 AX.",
                )
            ],
        )

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

    def _looks_like_secret(self, text: str) -> bool:
        normalized = text.strip()
        if re.search(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]", normalized):
            return True
        if re.search(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{16,}", normalized):
            return True
        if re.search(r"\b(?:sk|pk|rk|ghp|gho|github_pat|xox[baprs])[_-][A-Za-z0-9_=-]{16,}", normalized):
            return True
        compact = re.sub(r"\s+", "", normalized)
        return len(compact) >= 48 and bool(re.fullmatch(r"[A-Za-z0-9_./+=:-]+", compact))

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
            errors=[make_error(code="approved_text_required", message="Approved text entry requires non-empty same-turn-approved text capped at 240 characters.", guidance="Do not type secrets. For messages, get exact human approval for the recipient/context and exact text first.")],
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
            "full_access_allows_customer_granted_control": True,
            "full_access_allows_coordinates": True,
            "full_access_allows_typing": True,
            "full_access_allows_sensitive_apps": False,
            "sensitive_apps_blocked": True,
            "hidden_shell_public_ports_and_token_exfiltration_blocked": True,
            "append_only_audit_log": True,
            "kill_switch_available": True,
        }
