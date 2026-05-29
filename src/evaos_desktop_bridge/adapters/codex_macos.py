from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..audit import default_state_dir
from ..redaction import cap_text, redact_value
from ..schema import make_error, timestamp_utc
from ..types import CommandResult

ACCESSIBILITY_GUIDANCE = (
    "Open System Settings > Privacy & Security > Accessibility and enable the terminal "
    "or app running evaos-desktop-bridge, then rerun the command."
)
SCREEN_RECORDING_GUIDANCE = (
    "Open System Settings > Privacy & Security > Screen Recording and enable the terminal "
    "or app running evaos-desktop-bridge, then rerun the command."
)
SUPPORT_CANARY_ENV = "EVAOS_SUPPORT_CANARY_CONTROLS"
VISIBLE_MESSAGE_MAX_CHARS = 4000
VISIBLE_MESSAGE_WAIT_MAX_MS = 120_000
VISIBLE_MESSAGE_WAIT_POLL_MIN_MS = 250
VISIBLE_MESSAGE_WAIT_POLL_MAX_MS = 10_000
VISIBLE_MESSAGE_WAIT_OBSERVATION_MAX = 25
VISIBLE_MESSAGE_AX_MAX_NODES = 2500
VISIBLE_MESSAGE_ACTIVE_TOKENS = (
    "awaiting response",
    "thinking",
    "working",
    "running",
    "generating",
    "responding",
    "stop generating",
    "stop response",
)
VISIBLE_MESSAGE_DONE_TOKENS = ("done", "completed", "response complete")
VISIBLE_MESSAGE_ERROR_TOKENS = ("failed", "error")
THREAD_STATUS_LABELS = (
    "Awaiting response",
    "Running",
    "Working",
    "Thinking",
    "Needs approval",
    "Approval needed",
    "Queued",
    "Done",
    "Failed",
    "Error",
)
THREAD_SECTION_LABELS = {"pinned", "projects", "chats", "recent", "show more"}
THREAD_CONTROL_LABELS = {
    "archive chat",
    "automation folders",
    "automations",
    "unarchive chat",
    "pin chat",
    "unpin chat",
    "copy",
    "copy message",
    "new chat",
    "new thread",
    "search",
    "settings",
    "send",
    "plugins",
}
THREAD_CONTROL_PREFIX_LABELS = {
    "archive chat",
    "automation folders",
    "automations",
    "pin chat",
    "unarchive chat",
    "unpin chat",
}
THREAD_TIME_RE = re.compile(r"^(?:now|yesterday|\d+\s?(?:s|m|h|d|w|mo|y))$", re.IGNORECASE)


@dataclass
class RunnerResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(command: list[str], timeout: float = 5.0) -> RunnerResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        display = command[:3] + ["..."] if len(command) > 3 else command
        return RunnerResult(
            returncode=124,
            stdout="",
            stderr=f"command timed out after {timeout:.1f}s: {display}",
        )
    return RunnerResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def check_accessibility_trusted() -> bool | None:
    if platform.system() != "Darwin":
        return None
    try:
        app_services = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        app_services.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(app_services.AXIsProcessTrusted())
    except Exception:
        return None


def check_screen_recording_trusted() -> bool | None:
    if platform.system() != "Darwin":
        return None
    try:
        core_graphics = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        core_graphics.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        return bool(core_graphics.CGPreflightScreenCaptureAccess())
    except Exception:
        return None


class MacOSCodexObserver:
    AX_SNAPSHOT_SCRIPT = """
import json
import subprocess
import sys

pid = int(sys.argv[1])
max_nodes = int(sys.argv[2])
include_nodes = sys.argv[3] == "1"

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


def text_value(value):
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def bool_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        return bool(value)
    except Exception:
        return None


def rect_value(element):
    pos = ax_value(element, AS.kAXPositionAttribute)
    size = ax_value(element, AS.kAXSizeAttribute)
    try:
        ok_pos, point = AS.AXValueGetValue(pos, AS.kAXValueCGPointType, None)
        ok_size, size_value = AS.AXValueGetValue(size, AS.kAXValueCGSizeType, None)
        if ok_pos and ok_size:
            return {
                "x": int(point.x),
                "y": int(point.y),
                "width": int(size_value.width),
                "height": int(size_value.height),
            }
    except Exception:
        pass
    try:
        x, y = pos.x, pos.y
        w, h = size.width, size.height
        return {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
    except Exception:
        return None


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
        "selected": bool_value(ax_value(element, AS.kAXSelectedAttribute)),
        "focused": bool_value(ax_value(element, AS.kAXFocusedAttribute)),
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

frontmost = None
try:
    frontmost = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout.strip() or None
except Exception:
    pass

app = AS.AXUIElementCreateApplication(pid)
windows = ax_value(app, AS.kAXWindowsAttribute) or []
try:
    windows_list = list(windows)
except Exception:
    windows_list = []

window_rows = []
node_rows = []
truncated = False
for idx, window in enumerate(windows_list):
    title = text_value(ax_value(window, AS.kAXTitleAttribute))
    role = text_value(ax_value(window, AS.kAXRoleAttribute))
    window_rows.append({
        "index": idx,
        "title": title,
        "role": role,
        "bounds": rect_value(window),
        "frontmost_app": frontmost,
        "codex_frontmost": frontmost == "Codex",
    })
    if include_nodes:
        truncated = walk(window, node_rows, 0, idx) or truncated

print(json.dumps({"ok": True, "windows": window_rows, "nodes": node_rows, "truncated": truncated}))
""".strip()

    def __init__(
        self,
        *,
        runner: Callable[[list[str], float], RunnerResult] = run_command,
        app_paths: list[Path] | None = None,
        state_dir: Path | None = None,
        platform_name: str | None = None,
        accessibility_checker: Callable[[], bool | None] = check_accessibility_trusted,
        screen_recording_checker: Callable[[], bool | None] = check_screen_recording_trusted,
        now: Callable[[], str] = timestamp_utc,
    ) -> None:
        self.runner = runner
        self._explicit_app_paths = app_paths is not None
        self.app_paths = app_paths or [
            Path("/Applications/Codex.app"),
            Path.home() / "Applications" / "Codex.app",
        ]
        self.state_dir = state_dir or default_state_dir()
        self.platform_name = platform_name or platform.system()
        self.accessibility_checker = accessibility_checker
        self.screen_recording_checker = screen_recording_checker
        self.now = now

    def status(self) -> CommandResult:
        app_paths = self._visible_app_paths()
        pid = self._codex_pid()
        accessibility = self._permission_status("accessibility")
        warnings: list[str] = []
        if self.platform_name != "Darwin":
            warnings.append("macOS-only live desktop inspection is unavailable on this platform")
        return CommandResult(
            ok=True,
            data={
                "platform": self.platform_name,
                "app": {
                    "name": "Codex Desktop",
                    "process_name": "Codex",
                    "installed": bool(app_paths),
                    "running": pid is not None,
                    "pid": pid,
                    "paths": [redact_value(path) for path in app_paths],
                },
                "permissions": {
                    "accessibility": accessibility,
                    "screen_recording": self._permission_status("screen_recording"),
                },
                "safety": {
                    "read_only": True,
                    "sends_prompts": False,
                    "uses_internal_mutation_rpc": False,
                    "reads_session_databases": False,
                },
            },
            warnings=warnings,
        )

    def focus(self, *, dry_run: bool = False) -> CommandResult:
        if dry_run:
            return CommandResult(ok=True, data={"would_focus": True, "focused": False})
        if self.platform_name != "Darwin":
            return CommandResult(
                ok=False,
                data={"focused": False},
                errors=[
                    make_error(
                        code="unsupported_platform",
                        message="Codex Desktop focus is only supported on macOS.",
                        guidance="Run this command on the macOS desktop host running Codex Desktop.",
                    )
                ],
            )
        if self.accessibility_checker() is False:
            return CommandResult(
                ok=False,
                data={"focused": False},
                errors=[
                    make_error(
                        code="permission_missing",
                        message="Accessibility permission is required to focus Codex Desktop.",
                        guidance=ACCESSIBILITY_GUIDANCE,
                        permission="accessibility",
                    )
                ],
            )
        if self._codex_pid() is None:
            return CommandResult(
                ok=False,
                data={"focused": False},
                errors=[
                    make_error(
                        code="codex_not_running",
                        message="Codex Desktop is not currently running.",
                        guidance="Open Codex Desktop manually, then rerun the focus command.",
                    )
                ],
            )
        result = self.runner(
            [
                "osascript",
                "-e",
                'tell application "System Events" to set frontmost of process "Codex" to true',
            ],
            5.0,
        )
        if result.returncode != 0:
            return CommandResult(
                ok=False,
                data={"focused": False},
                errors=[
                    make_error(
                        code="focus_failed",
                        message="macOS refused to focus the visible Codex Desktop process.",
                        guidance=ACCESSIBILITY_GUIDANCE,
                        permission="accessibility",
                    )
                ],
                warnings=[str(redact_value(result.stderr.strip()))] if result.stderr.strip() else [],
            )
        return CommandResult(ok=True, data={"focused": True})

    def snapshot(self, *, max_chars: int) -> CommandResult:
        warnings: list[str] = []
        frontmost_app = self._osascript_value(
            'tell application "System Events" to get name of first application process whose frontmost is true'
        )
        window_title = self._osascript_value(
            'tell application "System Events" to tell first application process whose frontmost is true to get name of front window'
        )
        if frontmost_app is None:
            warnings.append("frontmost app unavailable; Accessibility or Automation permission may be missing")
        if window_title is None:
            warnings.append("window title unavailable; Accessibility or Automation permission may be missing")

        capped_title, title_truncated = cap_text(redact_value(window_title), max_chars)
        if title_truncated:
            warnings.append("window title truncated")
        capped_frontmost, frontmost_truncated = cap_text(redact_value(frontmost_app), max_chars)
        if frontmost_truncated:
            warnings.append("frontmost app truncated")

        codex_frontmost = frontmost_app == "Codex"
        screenshot_path = None
        if codex_frontmost:
            screenshot_path = self._capture_screenshot(warnings)
        else:
            warnings.append("Codex Desktop is not frontmost; screenshot skipped to avoid capturing another app")

        return CommandResult(
            ok=True,
            data={
                "timestamp": self.now(),
                "frontmost_app": capped_frontmost,
                "window_title": capped_title if codex_frontmost else None,
                "codex_frontmost": codex_frontmost,
                "screenshot_path": redact_value(screenshot_path) if screenshot_path else None,
                "max_chars": max_chars,
            },
            warnings=warnings,
        )

    def frontmost(self) -> CommandResult:
        frontmost_app = self._osascript_value(
            'tell application "System Events" to get name of first application process whose frontmost is true'
        )
        window_title = self._osascript_value(
            'tell application "System Events" to tell first application process whose frontmost is true to get name of front window'
        )
        return CommandResult(
            ok=True,
            data={
                "frontmost_app": redact_value(frontmost_app),
                "window_title": redact_value(window_title) if frontmost_app == "Codex" else None,
                "codex_frontmost": frontmost_app == "Codex",
            },
            warnings=[] if frontmost_app else ["frontmost app unavailable; Accessibility or Automation permission may be missing"],
        )

    def windows(self, *, max_nodes: int = 1) -> CommandResult:
        pid = self._codex_pid()
        if pid is None:
            return CommandResult(
                ok=False,
                data={"windows": []},
                errors=[
                    make_error(
                        code="codex_not_running",
                        message="Codex Desktop is not currently running.",
                        guidance="Open Codex Desktop manually, then rerun the windows command.",
                    )
                ],
            )
        payload, errors, warnings = self._ax_snapshot(pid=pid, max_nodes=max_nodes, include_nodes=False)
        if payload is None:
            return CommandResult(ok=False, data={"windows": []}, errors=errors, warnings=warnings)
        windows = [self._safe_window(row) for row in payload.get("windows", [])]
        return CommandResult(ok=True, data={"windows": windows, "count": len(windows)}, warnings=warnings)

    def threads(self, *, max_items: int) -> CommandResult:
        pid = self._codex_pid()
        if pid is None:
            return CommandResult(
                ok=False,
                data={"threads": [], "count": 0, "max_items": max_items},
                errors=[
                    make_error(
                        code="codex_not_running",
                        message="Codex Desktop is not currently running.",
                        guidance="Open Codex Desktop manually, then rerun the threads command.",
                    )
                ],
                provenance={"source": "ax"},
            )
        payload, errors, warnings = self._ax_snapshot(pid=pid, max_nodes=max(max_items * 8, 80), include_nodes=True)
        if payload is None:
            return CommandResult(ok=False, data={"threads": [], "count": 0, "max_items": max_items}, errors=errors, warnings=warnings, provenance={"source": "ax"})
        threads = self._visible_threads_from_payload(payload, max_items=max_items)
        return CommandResult(
            ok=True,
            data={"threads": threads, "count": len(threads), "max_items": max_items, "source": "ax"},
            warnings=warnings,
            provenance={"source": "ax"},
        )

    def select_thread(self, *, thread_id: str, dry_run: bool = False, max_items: int = 50) -> CommandResult:
        if self.platform_name != "Darwin":
            return CommandResult(
                ok=False,
                data={"selected": False, "would_select": dry_run},
                errors=[
                    make_error(
                        code="unsupported_platform",
                        message="Codex Desktop visible thread selection is only supported on macOS.",
                        guidance="Run this command on the macOS desktop host running Codex Desktop.",
                    )
                ],
                provenance={"source": "ax", "dry_run": dry_run, "selected_visible_target_id": thread_id},
            )
        if self.accessibility_checker() is False:
            return CommandResult(
                ok=False,
                data={"selected": False, "would_select": dry_run},
                errors=[
                    make_error(
                        code="permission_missing",
                        message="Accessibility permission is required to select a visible Codex thread.",
                        guidance=ACCESSIBILITY_GUIDANCE,
                        permission="accessibility",
                    )
                ],
                provenance={"source": "ax", "dry_run": dry_run, "selected_visible_target_id": thread_id},
            )
        inventory = self.threads(max_items=max_items)
        if not inventory.ok:
            inventory.provenance.update({"dry_run": dry_run, "selected_visible_target_id": thread_id})
            return inventory
        target = next((item for item in inventory.data.get("threads", []) if item.get("visible_id") == thread_id), None)
        if target is None:
            return CommandResult(
                ok=False,
                data={"selected": False, "would_select": dry_run, "thread_id": thread_id},
                errors=[
                    make_error(
                        code="visible_thread_not_found",
                        message="The requested visible Codex thread id is not present in the current GUI inventory.",
                        guidance="Rerun `evaos-desktop-bridge codex threads --json` and choose a current visible_id.",
                    )
                ],
                provenance={"source": "ax", "dry_run": dry_run, "selected_visible_target_id": thread_id},
            )
        center = target.get("center")
        if not isinstance(center, dict) or center.get("x") is None or center.get("y") is None:
            return CommandResult(
                ok=False,
                data={"selected": False, "would_select": dry_run, "thread_id": thread_id, "target": target},
                errors=[
                    make_error(
                        code="visible_thread_not_selectable",
                        message="The visible thread candidate does not have safe screen coordinates.",
                        guidance="Use a candidate with bounds from the current AX inventory.",
                    )
                ],
                provenance={"source": "ax", "dry_run": dry_run, "selected_visible_target_id": thread_id},
            )
        if dry_run:
            return CommandResult(
                ok=True,
                data={"selected": False, "would_select": True, "thread_id": thread_id, "target": target},
                provenance={"source": "ax", "dry_run": True, "selected_visible_target_id": thread_id},
            )
        focus = self.focus(dry_run=False)
        if not focus.ok:
            focus.provenance.update({"dry_run": dry_run, "selected_visible_target_id": thread_id})
            return focus
        result = self.runner(
            ["osascript", "-e", f'tell application "System Events" to click at {{{int(center["x"])}, {int(center["y"])}}}'],
            5.0,
        )
        if result.returncode != 0:
            return CommandResult(
                ok=False,
                data={"selected": False, "thread_id": thread_id, "target": target},
                errors=[
                    make_error(
                        code="visible_thread_select_failed",
                        message="macOS refused to select the visible Codex thread candidate.",
                        guidance=ACCESSIBILITY_GUIDANCE,
                        permission="accessibility",
                    )
                ],
                warnings=[str(redact_value(result.stderr.strip()))] if result.stderr.strip() else [],
                provenance={"source": "ax", "dry_run": False, "selected_visible_target_id": thread_id},
            )
        return CommandResult(
            ok=True,
            data={"selected": True, "thread_id": thread_id, "target": target},
            provenance={"source": "ax", "dry_run": False, "selected_visible_target_id": thread_id},
        )

    def send_visible_message(
        self,
        *,
        thread_id: str,
        message: str,
        dry_run: bool = True,
        confirmed: bool = False,
        wait_ms: int = 0,
        poll_interval_ms: int = 2000,
    ) -> CommandResult:
        message = message.strip()
        message_preview = self._safe_message_preview(message)
        message_hash = self._short_hash(message)
        wait_ms = max(0, min(VISIBLE_MESSAGE_WAIT_MAX_MS, int(wait_ms or 0)))
        poll_interval_ms = max(
            VISIBLE_MESSAGE_WAIT_POLL_MIN_MS,
            min(VISIBLE_MESSAGE_WAIT_POLL_MAX_MS, int(poll_interval_ms or 2000)),
        )
        provenance = {
            "source": "codex_visible_gui",
            "dry_run": dry_run,
            "selected_visible_target_id": thread_id,
            "message_hash": message_hash,
            "wait_ms": wait_ms,
            "poll_interval_ms": poll_interval_ms,
        }
        if not message:
            return CommandResult(
                ok=False,
                data={"submitted": False, "would_submit": dry_run, "thread_id": thread_id, "message_preview": message_preview, "message_hash": message_hash},
                errors=[
                    make_error(
                        code="visible_message_empty",
                        message="Codex visible GUI message cannot be empty.",
                        guidance="Pass a non-empty --message value.",
                    )
                ],
                provenance=provenance,
            )
        if len(message) > VISIBLE_MESSAGE_MAX_CHARS:
            return CommandResult(
                ok=False,
                data={"submitted": False, "would_submit": dry_run, "thread_id": thread_id, "message_preview": message_preview, "message_hash": message_hash, "max_chars": VISIBLE_MESSAGE_MAX_CHARS},
                errors=[
                    make_error(
                        code="visible_message_too_long",
                        message=f"Codex visible GUI message is capped at {VISIBLE_MESSAGE_MAX_CHARS} characters.",
                        guidance="Shorten the message, then rerun the dry-run approval flow.",
                    )
                ],
                provenance=provenance,
            )
        if self.platform_name != "Darwin":
            return CommandResult(
                ok=False,
                data={"submitted": False, "would_submit": dry_run, "thread_id": thread_id, "message_preview": message_preview, "message_hash": message_hash},
                errors=[
                    make_error(
                        code="unsupported_platform",
                        message="Codex Desktop visible GUI messaging is only supported on macOS.",
                        guidance="Run this command on the macOS desktop host running Codex Desktop.",
                    )
                ],
                provenance=provenance,
            )
        if self.accessibility_checker() is False:
            return CommandResult(
                ok=False,
                data={"submitted": False, "would_submit": dry_run, "thread_id": thread_id, "message_preview": message_preview, "message_hash": message_hash},
                errors=[
                    make_error(
                        code="permission_missing",
                        message="Accessibility permission is required to send a visible Codex GUI message.",
                        guidance=ACCESSIBILITY_GUIDANCE,
                        permission="accessibility",
                    )
                ],
                provenance=provenance,
            )
        if not dry_run and not confirmed:
            return CommandResult(
                ok=False,
                data={"submitted": False, "would_submit": False, "thread_id": thread_id, "message_preview": message_preview, "message_hash": message_hash},
                errors=[
                    make_error(
                        code="visible_message_confirmation_required",
                        message="Live Codex visible GUI messaging requires --confirm after a matching dry-run audit.",
                        guidance="Run the command with --dry-run first, then rerun with --live --confirm --approval-audit-id.",
                    )
                ],
                provenance=provenance,
            )
        current_thread = thread_id.strip().lower() in {"current", "visible-current", "current-visible"}
        target: dict[str, Any] = {
            "visible_id": "current",
            "title": "Current visible Codex thread",
            "source": "codex_visible_gui",
            "selection_mode": "current_visible_thread",
        }
        if not current_thread:
            inventory = self.threads(max_items=50)
            if not inventory.ok:
                inventory.provenance.update(provenance)
                return inventory
            found = next((item for item in inventory.data.get("threads", []) if item.get("visible_id") == thread_id), None)
            if found is None:
                return CommandResult(
                    ok=False,
                    data={"submitted": False, "would_submit": dry_run, "thread_id": thread_id, "message_preview": message_preview, "message_hash": message_hash},
                    errors=[
                        make_error(
                            code="visible_thread_not_found",
                            message="The requested visible Codex thread id is not present in the current GUI inventory.",
                            guidance="Rerun `evaos-desktop-bridge codex threads --json` and choose a current visible_id.",
                        )
                    ],
                    provenance=provenance,
                )
            target = found
            center = target.get("center")
            if not isinstance(center, dict) or center.get("x") is None or center.get("y") is None:
                return CommandResult(
                    ok=False,
                    data={"submitted": False, "would_submit": dry_run, "thread_id": thread_id, "target": target, "message_preview": message_preview, "message_hash": message_hash},
                    errors=[
                        make_error(
                            code="visible_thread_not_selectable",
                            message="The visible thread candidate does not have safe screen coordinates.",
                            guidance="Use a candidate with bounds from the current AX inventory.",
                        )
                    ],
                    provenance=provenance,
                )
            target_safety_error = self._visible_message_target_safety_error(target=target, live=not dry_run)
            if target_safety_error is not None:
                return CommandResult(
                    ok=False,
                    data={"submitted": False, "would_submit": dry_run, "thread_id": thread_id, "target": target, "message_preview": message_preview, "message_hash": message_hash},
                    errors=[target_safety_error],
                    provenance=provenance,
                )
        preflight = self._visible_message_preflight()
        if not preflight.ok:
            preflight.provenance.update(provenance)
            preflight.data.update({"thread_id": thread_id, "target": target, "message_preview": message_preview, "message_hash": message_hash})
            return preflight
        composer = preflight.data.get("composer")
        if dry_run:
            return CommandResult(
                ok=True,
                data={
                    "thread_id": thread_id,
                    "target": target,
                    "composer": composer,
                    "would_select": not current_thread,
                    "would_focus_composer": True,
                    "would_submit": True,
                    "would_poll_after_submit": wait_ms > 0,
                    "wait_ms": wait_ms,
                    "poll_interval_ms": poll_interval_ms,
                    "submitted": False,
                    "message_preview": message_preview,
                    "message_hash": message_hash,
                    "max_chars": VISIBLE_MESSAGE_MAX_CHARS,
                },
                provenance=provenance,
            )
        if not current_thread:
            selected = self.select_thread(thread_id=thread_id, dry_run=False)
            if not selected.ok:
                selected.provenance.update(provenance)
                return selected
            verified = self._verify_selected_visible_thread(target)
            if not verified.ok:
                verified.provenance.update(provenance)
                verified.data.update({"thread_id": thread_id, "target": target, "message_preview": message_preview, "message_hash": message_hash})
                return verified
        after_select_preflight = self._visible_message_preflight()
        if not after_select_preflight.ok:
            after_select_preflight.provenance.update(provenance)
            after_select_preflight.data.update({"thread_id": thread_id, "target": target, "message_preview": message_preview, "message_hash": message_hash})
            return after_select_preflight
        composer = after_select_preflight.data.get("composer")
        before_snapshot = self.snapshot(max_chars=1000)
        composer_center = composer.get("center") if isinstance(composer, dict) else None
        click_command = None
        if isinstance(composer_center, dict) and composer_center.get("x") is not None and composer_center.get("y") is not None:
            click_command = self.runner(
                ["osascript", "-e", f'tell application "System Events" to click at {{{int(composer_center["x"])}, {int(composer_center["y"])}}}'],
                5.0,
            )
            if click_command.returncode != 0:
                return CommandResult(
                    ok=False,
                    data={"submitted": False, "thread_id": thread_id, "target": target, "composer": composer, "message_preview": message_preview, "message_hash": message_hash},
                    errors=[
                        make_error(
                            code="codex_visible_composer_focus_failed",
                            message="macOS refused to focus the visible Codex composer.",
                            guidance=ACCESSIBILITY_GUIDANCE,
                            permission="accessibility",
                        )
                    ],
                    warnings=[str(redact_value(click_command.stderr.strip()))] if click_command.stderr.strip() else [],
                    provenance=provenance,
                )
        type_result = self.runner(
            [
                "osascript",
                "-e",
                f'tell application "System Events" to keystroke {self._applescript_string_expr(message)}',
                "-e",
                'tell application "System Events" to key code 36',
            ],
            10.0,
        )
        if type_result.returncode != 0:
            return CommandResult(
                ok=False,
                data={"submitted": False, "thread_id": thread_id, "target": target, "composer": composer, "message_preview": message_preview, "message_hash": message_hash},
                errors=[
                    make_error(
                        code="codex_visible_message_submit_failed",
                        message="macOS refused the visible Codex GUI message submission.",
                        guidance=ACCESSIBILITY_GUIDANCE,
                        permission="accessibility",
                    )
                ],
                warnings=[str(redact_value(type_result.stderr.strip()))] if type_result.stderr.strip() else [],
                provenance=provenance,
            )
        after_snapshot = self.snapshot(max_chars=1000)
        before_snapshot_path = before_snapshot.data.get("screenshot_path") if before_snapshot.ok else None
        after_snapshot_path = after_snapshot.data.get("screenshot_path") if after_snapshot.ok else None
        post_send, post_send_warnings = self._visible_message_post_send_status(wait_ms=wait_ms, poll_interval_ms=poll_interval_ms)
        return CommandResult(
            ok=True,
            data={
                "thread_id": thread_id,
                "target": target,
                "composer": composer,
                "would_submit": False,
                "submitted": True,
                "message_preview": message_preview,
                "message_hash": message_hash,
                "before_snapshot": before_snapshot_path,
                "after_snapshot": after_snapshot_path,
                "post_send": post_send,
            },
            warnings=before_snapshot.warnings + after_snapshot.warnings + post_send_warnings,
            provenance={
                **provenance,
                "before_snapshot_id": before_snapshot_path,
                "after_snapshot_id": after_snapshot_path,
                "post_send_state": post_send.get("state"),
                "post_send_observation_count": post_send.get("observation_count"),
                "selected_title_hash": target.get("title_hash"),
                "current_visible_thread": current_thread,
            },
        )

    def continue_thread(self, *, title: str, prompt: str = "continue", dry_run: bool = False) -> CommandResult:
        if not self._support_canary_enabled():
            return CommandResult(
                ok=False,
                data={"would_submit": dry_run, "submitted": False, "title": redact_value(title)},
                errors=[
                    make_error(
                        code="support_canary_controls_not_enabled",
                        message="Codex visible continue fallback is support-VM-only and is disabled on this host.",
                        guidance=f"Enable {SUPPORT_CANARY_ENV}=1 only on the support canary Mac connector.",
                    )
                ],
                provenance={"source": "codex_visible_fallback", "dry_run": dry_run, "support_only": True},
            )
        if prompt.strip().lower() != "continue":
            return CommandResult(
                ok=False,
                data={"would_submit": dry_run, "submitted": False, "title": redact_value(title), "prompt_preview": self._safe_prompt_preview(prompt)},
                errors=[
                    make_error(
                        code="codex_continue_prompt_not_allowed",
                        message="The support canary Codex fallback only allows the exact prompt 'continue'.",
                        guidance="Use Codex native remote-control for richer thread steering; do not expose generic prompt submission through this bridge.",
                    )
                ],
                provenance={"source": "codex_visible_fallback", "dry_run": dry_run, "support_only": True},
            )
        inventory = self.threads(max_items=50)
        if not inventory.ok:
            inventory.provenance.update({"source": "codex_visible_fallback", "dry_run": dry_run, "support_only": True})
            return inventory
        query = title.strip().lower()
        matches = [
            item
            for item in inventory.data.get("threads", [])
            if query and query in str(item.get("title") or "").strip().lower()
        ]
        if len(matches) != 1:
            return CommandResult(
                ok=False,
                data={"would_submit": dry_run, "submitted": False, "title": redact_value(title), "match_count": len(matches), "matches": matches[:10]},
                errors=[
                    make_error(
                        code="codex_thread_title_not_unique",
                        message="The requested Codex thread title did not resolve to exactly one visible thread.",
                        guidance="Use `codex threads --json` to get current visible candidates, then narrow the title.",
                    )
                ],
                provenance={"source": "codex_visible_fallback", "dry_run": dry_run, "support_only": True},
            )
        target = matches[0]
        if dry_run:
            delegated = self.send_visible_message(thread_id=str(target["visible_id"]), message=prompt.strip(), dry_run=True)
        else:
            delegated = self.send_visible_message(thread_id=str(target["visible_id"]), message=prompt.strip(), dry_run=False, confirmed=True)
        delegated.data.update({"title": redact_value(title), "prompt_preview": self._safe_prompt_preview(prompt), "target": target})
        delegated.provenance.update({"source": "codex_visible_fallback", "support_only": True})
        return delegated

    def inspect(self, *, max_nodes: int) -> CommandResult:
        status = self.status()
        frontmost = self.frontmost()
        windows = self.windows()
        ax = self.ax_tree(max_nodes=max_nodes)
        warnings = status.warnings + frontmost.warnings + windows.warnings + ax.warnings
        errors = windows.errors + ax.errors
        nodes = ax.data.get("nodes", []) if ax.ok else []
        buttons = [node for node in nodes if node.get("role") == "AXButton" and node.get("name")]
        text_items = [node for node in nodes if node.get("name") and node.get("role") in {"AXStaticText", "AXTextField", "AXWebArea", "AXGroup"}]
        return CommandResult(
            ok=status.ok and frontmost.ok and windows.ok and ax.ok,
            data={
                "status": status.data,
                "frontmost": frontmost.data,
                "windows": windows.data.get("windows", []),
                "ax": {
                    "nodes": nodes,
                    "truncated": ax.data.get("truncated", False),
                    "max_nodes": max_nodes,
                },
                "summary": {
                    "window_count": windows.data.get("count", 0),
                    "codex_frontmost": frontmost.data.get("codex_frontmost", False),
                    "visible_buttons": buttons[:20],
                    "visible_text": text_items[:20],
                },
            },
            warnings=warnings,
            errors=errors,
        )

    def ax_tree(self, *, max_nodes: int) -> CommandResult:
        if self.platform_name != "Darwin":
            return CommandResult(
                ok=False,
                data={"nodes": [], "truncated": False},
                errors=[
                    make_error(
                        code="unsupported_platform",
                        message="Codex Desktop Accessibility tree inspection is only supported on macOS.",
                        guidance="Run this command on the macOS desktop host running Codex Desktop.",
                    )
                ],
            )
        if self.accessibility_checker() is False:
            return CommandResult(
                ok=False,
                data={"nodes": [], "truncated": False},
                errors=[
                    make_error(
                        code="permission_missing",
                        message="Accessibility permission is required to read the visible Codex AX tree.",
                        guidance=ACCESSIBILITY_GUIDANCE,
                        permission="accessibility",
                    )
                ],
            )
        pid = self._codex_pid()
        if pid is None:
            return CommandResult(
                ok=False,
                data={"nodes": [], "truncated": False},
                errors=[
                    make_error(
                        code="codex_not_running",
                        message="Codex Desktop is not currently running.",
                        guidance="Open Codex Desktop manually, then rerun the ax-tree command.",
                    )
                ],
            )
        payload, errors, warnings = self._ax_snapshot(pid=pid, max_nodes=max_nodes, include_nodes=True)
        if payload is None:
            return CommandResult(ok=False, data={"nodes": [], "truncated": False}, errors=errors, warnings=warnings)
        nodes = [self._safe_node(row) for row in payload.get("nodes", [])][:max_nodes]
        truncated = bool(payload.get("truncated"))
        if truncated:
            warnings.append(f"AX tree truncated at {max_nodes} nodes")
        return CommandResult(
            ok=True,
            data={"nodes": nodes, "truncated": truncated, "max_nodes": max_nodes},
            warnings=warnings,
        )

    def _visible_app_paths(self) -> list[Path]:
        if self._explicit_app_paths:
            return self.app_paths
        return [path for path in self.app_paths if path.exists()]

    def _codex_pid(self) -> int | None:
        result = self.runner(["pgrep", "-x", "Codex"], 3.0)
        if result.returncode == 0:
            first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            try:
                return int(first)
            except ValueError:
                pass
        if self.platform_name != "Darwin":
            return None
        fallback = self.runner(
            ["osascript", "-e", 'tell application "System Events" to get unix id of first application process whose name is "Codex"'],
            5.0,
        )
        if fallback.returncode != 0:
            return None
        first = fallback.stdout.strip().splitlines()[0] if fallback.stdout.strip() else ""
        try:
            return int(first)
        except ValueError:
            return None

    def _permission_status(self, permission: str) -> dict[str, str]:
        if permission == "accessibility":
            trusted = self.accessibility_checker()
            if trusted is True:
                return {"status": "granted", "guidance": ACCESSIBILITY_GUIDANCE}
            if trusted is False:
                return {"status": "missing", "guidance": ACCESSIBILITY_GUIDANCE}
            return {"status": "unknown", "guidance": ACCESSIBILITY_GUIDANCE}
        if permission == "screen_recording":
            trusted = self.screen_recording_checker()
            if trusted is True:
                return {"status": "granted", "guidance": SCREEN_RECORDING_GUIDANCE}
            if trusted is False:
                return {"status": "missing", "guidance": SCREEN_RECORDING_GUIDANCE}
            return {"status": "unknown", "guidance": SCREEN_RECORDING_GUIDANCE}
        return {"status": "unknown", "guidance": ACCESSIBILITY_GUIDANCE}

    def _osascript_value(self, script: str) -> str | None:
        if self.platform_name != "Darwin":
            return None
        result = self.runner(["osascript", "-e", script], 5.0)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _capture_screenshot(self, warnings: list[str]) -> Path | None:
        if self.platform_name != "Darwin":
            warnings.append("screenshot unavailable outside macOS")
            return None
        screenshot_dir = self.state_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = self.now().replace(":", "").replace("-", "").replace("Z", "Z") + ".png"
        screenshot_path = screenshot_dir / filename
        result = self.runner(["screencapture", "-x", str(screenshot_path)], 10.0)
        if result.returncode != 0:
            warnings.append("screenshot unavailable; Screen Recording permission may be missing")
            return None
        return screenshot_path

    def _ax_snapshot(self, *, pid: int, max_nodes: int, include_nodes: bool) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
        result = self.runner(
            [sys.executable, "-c", self.AX_SNAPSHOT_SCRIPT, str(pid), str(max_nodes), "1" if include_nodes else "0"],
            20.0,
        )
        warnings = [str(redact_value(result.stderr.strip()))] if result.stderr.strip() else []
        if result.returncode != 0:
            return None, [
                make_error(
                    code="ax_tree_unavailable",
                    message="Unable to read the visible Codex Accessibility tree.",
                    guidance=ACCESSIBILITY_GUIDANCE,
                    permission="accessibility",
                )
            ], warnings
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return None, [
                make_error(
                    code="ax_snapshot_parse_failed",
                    message="Unable to parse Codex Accessibility snapshot output.",
                    guidance="Check that pyobjc is installed in the Python environment running evaos-desktop-bridge.",
                )
            ], warnings
        if not payload.get("ok"):
            return None, [
                make_error(
                    code="ax_dependency_missing",
                    message=str(redact_value(payload.get("error") or "Accessibility snapshot dependency missing.")),
                    guidance="Install pyobjc-framework-Quartz and pyobjc-framework-ApplicationServices in the bridge environment.",
                )
            ], warnings
        return payload, [], warnings

    def _safe_window(self, row: dict[str, Any]) -> dict[str, Any]:
        title, _ = cap_text(redact_value(row.get("title")), 160)
        role, _ = cap_text(str(redact_value(row.get("role") or "unknown")), 80)
        return {
            "index": row.get("index"),
            "title": title,
            "role": role,
            "bounds": row.get("bounds"),
            "codex_frontmost": bool(row.get("codex_frontmost")),
        }

    def _safe_node(self, row: dict[str, Any]) -> dict[str, Any]:
        role, _ = cap_text(str(redact_value(row.get("role") or "unknown")), 80)
        name, _ = cap_text(str(redact_value(row.get("name"))) if row.get("name") else None, 160)
        node = {
            "role": role,
            "name": name,
            "depth": int(row.get("depth") or 0),
            "window_index": row.get("window_index"),
        }
        if row.get("bounds") is not None:
            node["bounds"] = row.get("bounds")
        if row.get("selected") is not None:
            node["selected"] = bool(row.get("selected"))
        if row.get("focused") is not None:
            node["focused"] = bool(row.get("focused"))
        return node

    def _visible_threads_from_payload(self, payload: dict[str, Any], *, max_items: int) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        fallback_candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        fallback_seen: set[str] = set()
        current_project: str | None = None
        in_projects = False
        window_bounds_by_index = {
            row.get("index"): row.get("bounds")
            for row in payload.get("windows", [])
            if isinstance(row, dict)
        }
        for row in payload.get("nodes", []):
            node = self._safe_node(row)
            role = str(node.get("role") or "")
            name = node.get("name")
            if not name or role not in {"AXButton", "AXStaticText", "AXTextField", "AXGroup", "AXRow", "AXLink"}:
                continue
            raw_name = str(name).strip()
            lowered = raw_name.lower()
            if self._is_thread_section_label(lowered):
                in_projects = lowered == "projects" or in_projects
                continue
            if in_projects and role == "AXStaticText" and self._looks_like_project_header(raw_name):
                current_project = str(redact_value(raw_name))
                continue
            if self._is_action_only_thread_row(lowered, node) and len(fallback_candidates) < max_items:
                fallback_key = json.dumps(node.get("bounds"), sort_keys=True)
                if fallback_key in fallback_seen:
                    continue
                fallback_seen.add(fallback_key)
                fallback = self._unknown_thread_row(index=len(fallback_candidates), node=node, raw_name=raw_name, project=current_project)
                if fallback["visible_id"] not in seen:
                    fallback_candidates.append(fallback)
                    seen.add(str(fallback["visible_id"]))
            if self._is_thread_control_label(lowered):
                continue
            title, status, updated_label = self._split_thread_title_status(raw_name)
            if not title or self._is_thread_control_label(title.lower()):
                continue
            if len(title) < 3 or title.lower() in {"codex", "vantage"}:
                continue
            visible_id = self._visible_thread_id(index=len(candidates), title=str(name), window_index=node.get("window_index"))
            if visible_id in seen:
                continue
            seen.add(visible_id)
            bounds = node.get("bounds")
            center = None
            if isinstance(bounds, dict):
                try:
                    center = {
                        "x": int(bounds["x"]) + int(bounds["width"]) // 2,
                        "y": int(bounds["y"]) + int(bounds["height"]) // 2,
                    }
                except Exception:
                    center = None
            candidates.append(
                {
                    "visible_id": visible_id,
                    "index": len(candidates),
                    "title": title,
                    "raw_title": raw_name,
                    "project": current_project,
                    "status": status,
                    "updated_label": updated_label,
                    "title_hash": self._short_hash(title),
                    "role": role,
                    "window_index": node.get("window_index"),
                    "bounds": bounds,
                    "window_bounds": window_bounds_by_index.get(node.get("window_index")),
                    "center": center,
                    "selected": bool(node.get("selected")) if node.get("selected") is not None else None,
                    "focused": bool(node.get("focused")) if node.get("focused") is not None else None,
                    "confidence": self._thread_confidence(role=role, center=center, status=status, updated_label=updated_label, project=current_project),
                    "source": "ax",
                }
            )
            if len(candidates) >= max_items:
                break
        if fallback_candidates:
            fallback_right = 0
            for fallback in fallback_candidates:
                bounds = fallback.get("bounds")
                if isinstance(bounds, dict):
                    try:
                        fallback_right = max(fallback_right, int(bounds.get("x") or 0) + int(bounds.get("width") or 0))
                    except Exception:
                        pass
            sidebar_titled_candidates = []
            for candidate in candidates:
                center = candidate.get("center")
                try:
                    center_x = int(center.get("x")) if isinstance(center, dict) else None
                except Exception:
                    center_x = None
                if center_x is not None and center_x <= fallback_right + 120:
                    sidebar_titled_candidates.append(candidate)
            if sidebar_titled_candidates:
                return sidebar_titled_candidates[:max_items]
            merged = fallback_candidates + candidates
            return merged[:max_items]
        return candidates[:max_items]

    def _visible_thread_id(self, *, index: int, title: str, window_index: Any) -> str:
        digest = hashlib.sha256(f"{window_index}:{index}:{title}".encode("utf-8")).hexdigest()[:12]
        return f"visible-{index}-{digest}"

    def _support_canary_enabled(self) -> bool:
        return os.environ.get(SUPPORT_CANARY_ENV, "").strip().lower() in {"1", "true", "yes", "support"}

    def _safe_prompt_preview(self, prompt: str) -> str:
        capped, _ = cap_text(redact_value(prompt.strip()), 80)
        return capped or ""

    def _safe_message_preview(self, message: str) -> str:
        capped, _ = cap_text(redact_value(message.strip()), 240)
        return capped or ""

    def _short_hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    def _applescript_string_expr(self, value: str) -> str:
        parts: list[str] = []
        literal: list[str] = []

        def flush_literal() -> None:
            if not literal:
                return
            escaped = "".join(literal).replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'"{escaped}"')
            literal.clear()

        index = 0
        while index < len(value):
            if value.startswith("\r\n", index):
                flush_literal()
                parts.append("return")
                index += 2
                continue
            char = value[index]
            if char in {"\n", "\r"}:
                flush_literal()
                parts.append("return")
            elif char == "\t":
                flush_literal()
                parts.append("tab")
            elif ord(char) < 32 or ord(char) == 127:
                flush_literal()
                parts.append(f"(ASCII character {ord(char)})")
            else:
                literal.append(char)
            index += 1

        flush_literal()
        return " & ".join(parts) if parts else '""'

    def _visible_message_preflight(self) -> CommandResult:
        frontmost = self.frontmost()
        if not frontmost.ok or frontmost.data.get("codex_frontmost") is not True:
            return CommandResult(
                ok=False,
                data={"composer": None, "codex_frontmost": frontmost.data.get("codex_frontmost", False)},
                errors=[
                    make_error(
                        code="codex_not_frontmost",
                        message="Codex Desktop must be frontmost before sending a visible GUI message.",
                        guidance="Focus Codex Desktop and make sure the target thread is visible, then rerun the dry-run.",
                    )
                ],
                warnings=frontmost.warnings,
                provenance={"source": "codex_visible_gui"},
            )
        ax = self.ax_tree(max_nodes=VISIBLE_MESSAGE_AX_MAX_NODES)
        if not ax.ok:
            return ax
        composer = self._find_visible_composer(ax.data.get("nodes", []))
        if composer is None:
            return CommandResult(
                ok=False,
                data={"composer": None, "codex_frontmost": True},
                errors=[
                    make_error(
                        code="codex_visible_composer_not_found",
                        message="No visible Codex composer was found in the current Accessibility tree.",
                        guidance="Open a loaded Codex thread with the message composer visible, then rerun the dry-run.",
                    )
                ],
                warnings=ax.warnings,
                provenance={"source": "codex_visible_gui"},
            )
        return CommandResult(ok=True, data={"composer": composer, "codex_frontmost": True}, warnings=ax.warnings, provenance={"source": "codex_visible_gui"})

    def _visible_message_post_send_status(self, *, wait_ms: int, poll_interval_ms: int) -> tuple[dict[str, Any], list[str]]:
        base = {
            "state": "submitted_waiting",
            "wait_ms": wait_ms,
            "poll_interval_ms": poll_interval_ms,
            "read_only_after_submit": True,
            "observations": [],
            "observation_count": 0,
        }
        if wait_ms <= 0:
            return base, []

        warnings: list[str] = []
        observations: list[dict[str, Any]] = []
        total_observations = 0
        elapsed_ms = 0
        last_state = "unknown"
        while True:
            observation = self._visible_message_wait_observation(max_chars=1000)
            observation["index"] = total_observations
            total_observations += 1
            if len(observations) < VISIBLE_MESSAGE_WAIT_OBSERVATION_MAX:
                observations.append(observation)
            state = str(observation.get("state") or "unknown")
            last_state = state
            explicit_idle = state == "idle" and observation.get("idle_confidence") == "explicit"
            if state in {"done", "error", "unavailable"} or explicit_idle:
                return {
                    **base,
                    "state": state,
                    "last_observed_state": state,
                    "observations": observations,
                    "observation_count": total_observations,
                    "observations_truncated": total_observations > len(observations),
                }, warnings
            if elapsed_ms >= wait_ms:
                break
            sleep_ms = min(poll_interval_ms, wait_ms - elapsed_ms)
            if sleep_ms <= 0:
                break
            self._sleep_for_visible_message_poll(sleep_ms / 1000.0)
            elapsed_ms += sleep_ms

        return {
            **base,
            "state": "timeout",
            "last_observed_state": last_state,
            "observations": observations,
            "observation_count": total_observations,
            "observations_truncated": total_observations > len(observations),
        }, warnings

    def _visible_message_wait_observation(self, *, max_chars: int = 1000) -> dict[str, Any]:
        timestamp = self.now()
        frontmost = self.frontmost()
        if not frontmost.ok or frontmost.data.get("codex_frontmost") is not True:
            return {
                "timestamp": timestamp,
                "state": "unavailable",
                "codex_frontmost": bool(frontmost.data.get("codex_frontmost")),
                "composer_visible": False,
                "active_indicators": [],
                "max_chars": max_chars,
            }

        ax = self.ax_tree(max_nodes=VISIBLE_MESSAGE_AX_MAX_NODES)
        if not ax.ok:
            return {
                "timestamp": timestamp,
                "state": "unavailable",
                "codex_frontmost": True,
                "composer_visible": False,
                "active_indicators": [],
                "max_chars": max_chars,
            }

        nodes = ax.data.get("nodes", [])
        composer_visible = self._find_visible_composer(nodes) is not None if isinstance(nodes, list) else False
        active_indicators: list[str] = []
        done = False
        error = False
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                name = str(node.get("name") or "")
                lowered = name.lower()
                if any(token in lowered for token in VISIBLE_MESSAGE_ERROR_TOKENS):
                    error = True
                if any(token in lowered for token in VISIBLE_MESSAGE_DONE_TOKENS):
                    done = True
                if any(token in lowered for token in VISIBLE_MESSAGE_ACTIVE_TOKENS):
                    capped, _ = cap_text(redact_value(name), 120)
                    if capped and capped not in active_indicators and len(active_indicators) < 5:
                        active_indicators.append(capped)

        if error:
            state = "error"
        elif done:
            state = "done"
        elif active_indicators:
            state = "submitted_waiting"
        elif composer_visible:
            state = "idle"
        else:
            state = "submitted_waiting"

        snapshot = self.snapshot(max_chars=max_chars)
        screenshot_path = snapshot.data.get("screenshot_path") if snapshot.ok else None
        return {
            "timestamp": timestamp,
            "state": state,
            "idle_confidence": "implicit_composer_visible" if state == "idle" else None,
            "codex_frontmost": True,
            "composer_visible": composer_visible,
            "active_indicators": active_indicators,
            "screenshot_path": screenshot_path,
            "max_chars": max_chars,
        }

    def _sleep_for_visible_message_poll(self, seconds: float) -> None:
        time.sleep(seconds)

    def _visible_message_target_safety_error(self, *, target: dict[str, Any], live: bool) -> dict[str, Any] | None:
        bounds = target.get("bounds")
        center = target.get("center")
        if not self._bounds_have_positive_size(bounds) or not isinstance(center, dict):
            return make_error(
                code="visible_thread_not_selectable",
                message="The visible thread candidate does not have positive on-screen bounds.",
                guidance="Use a candidate with positive bounds from the current AX inventory.",
            )
        window_bounds = target.get("window_bounds")
        if isinstance(window_bounds, dict) and not self._point_inside_bounds(center, window_bounds):
            return make_error(
                code="visible_thread_offscreen",
                message="The visible thread candidate center is outside the Codex window bounds.",
                guidance="Rerun the thread inventory with the target row visible in the Codex window.",
            )
        if live and target.get("selection_only") is True:
            return make_error(
                code="visible_thread_identity_not_verifiable",
                message="Live visible GUI messaging requires a titled target row or the explicit current visible thread sentinel.",
                guidance="Select the intended Codex thread first, then use --thread-id current, or use a visible titled medium-or-better candidate.",
            )
        if live and target.get("selection_only") is not True and target.get("confidence") == "low":
            return make_error(
                code="visible_thread_identity_not_verifiable",
                message="Live visible GUI messaging requires a titled, medium-or-better confidence thread candidate.",
                guidance="Use a visible row with title/status evidence, or use dry-run/read-only mapping until Codex exposes enough AX identity.",
            )
        return None

    def _verify_selected_visible_thread(self, target: dict[str, Any]) -> CommandResult:
        inventory = self.threads(max_items=50)
        if not inventory.ok:
            inventory.provenance.update({"source": "codex_visible_gui"})
            return inventory
        current = next((item for item in inventory.data.get("threads", []) if item.get("visible_id") == target.get("visible_id")), None)
        if current is None:
            return CommandResult(
                ok=False,
                data={"selection_verified": False},
                errors=[
                    make_error(
                        code="visible_thread_not_found_after_select",
                        message="The target visible Codex thread disappeared after selection.",
                        guidance="Rerun thread-map and dry-run approval against the current visible UI.",
                    )
                ],
                provenance={"source": "codex_visible_gui"},
            )
        if current.get("selected") is True or current.get("focused") is True:
            return CommandResult(ok=True, data={"selection_verified": True, "selected_thread": current}, provenance={"source": "codex_visible_gui"})
        return CommandResult(
            ok=False,
            data={"selection_verified": False, "selected_thread": current},
            errors=[
                make_error(
                    code="visible_thread_selection_not_verified",
                    message="Codex did not expose the requested visible thread as selected after the click.",
                    guidance="Do not submit a live GUI message until AX confirms the selected target. Rerun thread-map after focusing the intended thread.",
                )
            ],
            provenance={"source": "codex_visible_gui"},
        )

    def _find_visible_composer(self, nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
        for node in reversed(nodes):
            role = str(node.get("role") or "")
            if role not in {"AXTextArea", "AXTextField", "AXTextView", "AXComboBox"}:
                continue
            bounds = node.get("bounds")
            center = None
            if isinstance(bounds, dict):
                try:
                    width = int(bounds.get("width") or 0)
                    height = int(bounds.get("height") or 0)
                    if width <= 0 or height <= 0:
                        continue
                    center = {"x": int(bounds["x"]) + width // 2, "y": int(bounds["y"]) + height // 2}
                except Exception:
                    continue
            if center is None:
                continue
            name = str(node.get("name") or "")
            name_lower = name.lower()
            if name_lower and not any(token in name_lower for token in ("message", "ask", "prompt", "codex", "input", "chat")):
                continue
            safe_name, _ = cap_text(redact_value(name), 120)
            return {"role": role, "name": safe_name, "bounds": bounds, "center": center}
        return None

    def _bounds_have_positive_size(self, bounds: Any) -> bool:
        if not isinstance(bounds, dict):
            return False
        try:
            return int(bounds.get("width") or 0) > 0 and int(bounds.get("height") or 0) > 0
        except Exception:
            return False

    def _point_inside_bounds(self, point: dict[str, Any], bounds: dict[str, Any]) -> bool:
        try:
            x = int(point["x"])
            y = int(point["y"])
            bx = int(bounds["x"])
            by = int(bounds["y"])
            bw = int(bounds["width"])
            bh = int(bounds["height"])
        except Exception:
            return False
        return bx <= x <= bx + bw and by <= y <= by + bh

    def _is_thread_section_label(self, lowered: str) -> bool:
        return lowered in THREAD_SECTION_LABELS

    def _is_thread_control_label(self, lowered: str) -> bool:
        if lowered in THREAD_CONTROL_LABELS:
            return True
        for control in THREAD_CONTROL_PREFIX_LABELS:
            if lowered.startswith(f"{control} ") or lowered.startswith(control):
                return True
        return any(control in lowered for control in ("archive chat", "unpin chat", "pin chat"))

    def _looks_like_project_header(self, name: str) -> bool:
        if not name or len(name) > 80:
            return False
        lowered = name.strip().lower()
        if self._is_thread_section_label(lowered) or self._is_thread_control_label(lowered):
            return False
        if THREAD_TIME_RE.match(lowered):
            return False
        return True

    def _split_thread_title_status(self, raw_name: str) -> tuple[str, str | None, str | None]:
        parts = raw_name.strip().split()
        updated_label = None
        if parts and THREAD_TIME_RE.match(parts[-1]):
            updated_label = parts[-1]
            raw_name = " ".join(parts[:-1]).strip()
        status = None
        for label in THREAD_STATUS_LABELS:
            suffix = f" {label}".lower()
            if raw_name.lower().endswith(suffix):
                status = label
                raw_name = raw_name[: -len(label)].strip()
                break
        title, _ = cap_text(str(redact_value(raw_name.strip())), 160)
        return title or "", status, updated_label

    def _thread_confidence(self, *, role: str, center: dict[str, int] | None, status: str | None, updated_label: str | None, project: str | None) -> str:
        score = 0
        if center:
            score += 2
        if role in {"AXButton", "AXRow", "AXGroup"}:
            score += 1
        if status or updated_label:
            score += 1
        if project:
            score += 1
        if score >= 4:
            return "high"
        if score >= 2:
            return "medium"
        return "low"

    def _is_action_only_thread_row(self, lowered: str, node: dict[str, Any]) -> bool:
        if "archive chat" not in lowered or ("unpin chat" not in lowered and "pin chat" not in lowered):
            return False
        bounds = node.get("bounds")
        if not isinstance(bounds, dict):
            return False
        try:
            width = int(bounds.get("width") or 0)
            height = int(bounds.get("height") or 0)
        except Exception:
            return False
        return width >= 120 and height > 0

    def _unknown_thread_row(self, *, index: int, node: dict[str, Any], raw_name: str, project: str | None) -> dict[str, Any]:
        bounds = node.get("bounds")
        center = None
        if isinstance(bounds, dict):
            try:
                center = {
                    "x": int(bounds["x"]) + int(bounds["width"]) // 2,
                    "y": int(bounds["y"]) + int(bounds["height"]) // 2,
                }
            except Exception:
                center = None
        _, _, updated_label = self._split_thread_title_status(raw_name)
        title = f"Visible thread row {index + 1} (title unavailable)"
        visible_id = self._visible_thread_id(index=index, title=f"title-unavailable:{updated_label or ''}:{bounds}", window_index=node.get("window_index"))
        return {
            "visible_id": visible_id,
            "index": index,
            "title": title,
            "raw_title": "title_unavailable",
            "project": project,
            "status": None,
            "updated_label": updated_label,
            "title_hash": self._short_hash(title),
            "role": str(node.get("role") or ""),
            "window_index": node.get("window_index"),
            "bounds": bounds,
            "window_bounds": None,
            "center": center,
            "selected": bool(node.get("selected")) if node.get("selected") is not None else None,
            "focused": bool(node.get("focused")) if node.get("focused") is not None else None,
            "confidence": "low",
            "source": "ax",
            "title_available": False,
            "selection_only": True,
        }

    def _selection_only_live_target_allowed(self, target: dict[str, Any]) -> bool:
        if target.get("title_available") is not False or target.get("selection_only") is not True:
            return False
        if not str(target.get("updated_label") or "").strip():
            return False
        if not self._bounds_have_positive_size(target.get("bounds")):
            return False
        center = target.get("center")
        if not isinstance(center, dict):
            return False
        window_bounds = target.get("window_bounds")
        return not isinstance(window_bounds, dict) or self._point_inside_bounds(center, window_bounds)
