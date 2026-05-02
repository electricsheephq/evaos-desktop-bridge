from __future__ import annotations

import ctypes
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
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
    AX_TREE_SCRIPT = """
on walkElements(elementsToWalk, rows)
  repeat with elementItem in elementsToWalk
    set elementRole to ""
    set elementName to ""
    try
      set elementRole to role of elementItem as text
    end try
    try
      set elementName to name of elementItem as text
    end try
    set end of rows to elementRole & tab & elementName
    try
      set rows to my walkElements(UI elements of elementItem, rows)
    end try
  end repeat
  return rows
end walkElements

tell application "System Events"
  tell process "Codex"
    set rows to {}
    set rows to my walkElements(UI elements, rows)
    set AppleScript's text item delimiters to linefeed
    return rows as text
  end tell
end tell
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
        result = self.runner(["osascript", "-e", self.AX_TREE_SCRIPT], 10.0)
        if result.returncode != 0:
            return CommandResult(
                ok=False,
                data={"nodes": [], "truncated": False},
                errors=[
                    make_error(
                        code="ax_tree_unavailable",
                        message="Unable to read the visible Codex Accessibility tree.",
                        guidance=ACCESSIBILITY_GUIDANCE,
                        permission="accessibility",
                    )
                ],
                warnings=[str(redact_value(result.stderr.strip()))] if result.stderr.strip() else [],
            )
        nodes = self._parse_ax_tree(result.stdout)
        capped = nodes[:max_nodes]
        truncated = len(nodes) > max_nodes
        warnings = [f"AX tree truncated at {max_nodes} nodes"] if truncated else []
        return CommandResult(
            ok=True,
            data={"nodes": capped, "truncated": truncated, "max_nodes": max_nodes},
            warnings=warnings,
        )

    def _visible_app_paths(self) -> list[Path]:
        if self._explicit_app_paths:
            return self.app_paths
        return [path for path in self.app_paths if path.exists()]

    def _codex_pid(self) -> int | None:
        result = self.runner(["pgrep", "-x", "Codex"], 3.0)
        if result.returncode != 0:
            return None
        first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
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

    def _parse_ax_tree(self, output: str) -> list[dict[str, str | None]]:
        nodes: list[dict[str, str | None]] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            role, _, name = line.partition("\t")
            safe_role, _ = cap_text(str(redact_value(role.strip() or "unknown")), 80)
            safe_name, _ = cap_text(str(redact_value(name.strip())) if name.strip() else None, 160)
            nodes.append({"role": safe_role, "name": safe_name})
        return nodes
