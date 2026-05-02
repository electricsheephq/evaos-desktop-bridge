from __future__ import annotations

import ctypes
import hashlib
import json
import platform
import subprocess
import sys
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


def rect_value(element):
    pos = ax_value(element, AS.kAXPositionAttribute)
    size = ax_value(element, AS.kAXSizeAttribute)
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
    rows.append({"role": role, "name": name, "depth": depth, "window_index": window_index, "bounds": rect_value(element)})
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
                    "screen_recording": {
                        "status": "unknown",
                        "guidance": SCREEN_RECORDING_GUIDANCE,
                    },
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

    def select_thread(self, *, thread_id: str, dry_run: bool = False, max_items: int = 200) -> CommandResult:
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
        return node

    def _visible_threads_from_payload(self, payload: dict[str, Any], *, max_items: int) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in payload.get("nodes", []):
            node = self._safe_node(row)
            role = str(node.get("role") or "")
            name = node.get("name")
            if not name or role not in {"AXButton", "AXStaticText", "AXTextField", "AXGroup", "AXRow", "AXLink"}:
                continue
            lowered = str(name).strip().lower()
            if lowered in {"codex", "new chat", "new thread", "settings", "search", "send"}:
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
                    "title": name,
                    "role": role,
                    "window_index": node.get("window_index"),
                    "bounds": bounds,
                    "center": center,
                    "confidence": "medium" if center else "low",
                    "source": "ax",
                }
            )
            if len(candidates) >= max_items:
                break
        return candidates

    def _visible_thread_id(self, *, index: int, title: str, window_index: Any) -> str:
        digest = hashlib.sha256(f"{window_index}:{index}:{title}".encode("utf-8")).hexdigest()[:12]
        return f"visible-{index}-{digest}"
