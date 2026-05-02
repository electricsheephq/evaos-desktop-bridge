from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

from evaos_desktop_bridge.cli import main
from evaos_desktop_bridge.types import CommandResult


@dataclass
class FakeObserver:
    mode: str = "ok"

    def status(self) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "app": {
                    "installed": self.mode != "absent",
                    "running": self.mode != "absent",
                    "pid": 123 if self.mode != "absent" else None,
                },
                "permissions": {
                    "accessibility": {"status": "granted"},
                    "screen_recording": {"status": "unknown"},
                },
            },
        )

    def frontmost(self) -> CommandResult:
        return CommandResult(ok=True, data={"frontmost_app": "Codex", "window_title": "Codex", "codex_frontmost": True})

    def windows(self) -> CommandResult:
        return CommandResult(ok=True, data={"windows": [{"index": 0, "title": "Codex", "role": "AXWindow", "bounds": {"x": 1, "y": 2, "width": 3, "height": 4}, "codex_frontmost": True}], "count": 1})

    def focus(self, *, dry_run: bool = False) -> CommandResult:
        if dry_run:
            return CommandResult(ok=True, data={"would_focus": True, "focused": False})
        if self.mode == "missing_permission":
            return CommandResult(
                ok=False,
                data={"focused": False},
                errors=[
                    {
                        "code": "permission_missing",
                        "message": "Accessibility permission is required.",
                        "guidance": "Enable Accessibility for the terminal running evaos-desktop-bridge.",
                        "permission": "accessibility",
                    }
                ],
            )
        return CommandResult(ok=True, data={"focused": True})

    def snapshot(self, *, max_chars: int) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "frontmost_app": "Codex",
                "window_title": "Codex",
                "screenshot_path": "~/Library/Application Support/evaos-desktop-bridge/screenshots/test.png",
                "max_chars": max_chars,
            },
        )

    def inspect(self, *, max_nodes: int) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "frontmost": {"codex_frontmost": True},
                "windows": [{"index": 0, "title": "Codex"}],
                "ax": {"nodes": [{"role": "AXButton", "name": "New chat", "depth": 0, "window_index": 0}], "truncated": False, "max_nodes": max_nodes},
                "summary": {"window_count": 1, "codex_frontmost": True, "visible_buttons": [{"role": "AXButton", "name": "New chat", "depth": 0, "window_index": 0}], "visible_text": []},
            },
        )

    def ax_tree(self, *, max_nodes: int) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "nodes": [
                    {"role": "AXWindow", "name": "Codex"},
                    {"role": "AXButton", "name": "New Chat"},
                ][:max_nodes],
                "truncated": max_nodes < 2,
            },
            warnings=["AX tree truncated"] if max_nodes < 2 else [],
        )


def run_cli(argv: list[str], observer: FakeObserver, tmp_path: Path) -> dict:
    stdout = io.StringIO()
    exit_code = main(
        argv,
        observer_factory=lambda: observer,
        stdout=stdout,
        state_dir=tmp_path,
    )
    payload = json.loads(stdout.getvalue())
    payload["_exit_code"] = exit_code
    return payload


def test_status_json_reports_absent_codex_without_error(tmp_path: Path) -> None:
    payload = run_cli(["status", "--json"], FakeObserver(mode="absent"), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["ok"] is True
    assert payload["command"] == "status"
    assert payload["target"] == "desktop"
    assert payload["data"]["app"]["installed"] is False
    assert payload["data"]["app"]["pid"] is None
    assert payload["audit_id"]


def test_frontmost_json_reports_codex_state(tmp_path: Path) -> None:
    payload = run_cli(["codex", "frontmost", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.frontmost"
    assert payload["data"]["codex_frontmost"] is True


def test_windows_json_lists_visible_codex_windows(tmp_path: Path) -> None:
    payload = run_cli(["codex", "windows", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.windows"
    assert payload["data"]["count"] == 1
    assert payload["data"]["windows"][0]["role"] == "AXWindow"


def test_focus_dry_run_does_not_focus_or_require_permission(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "focus", "--json", "--dry-run"],
        FakeObserver(mode="missing_permission"),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.focus"
    assert payload["data"] == {"would_focus": True, "focused": False}


def test_focus_permission_error_is_graceful_json(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "focus", "--json"],
        FakeObserver(mode="missing_permission"),
        tmp_path,
    )

    assert payload["_exit_code"] == 2
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "permission_missing"
    assert payload["errors"][0]["permission"] == "accessibility"
    assert "System Settings" in payload["errors"][0]["guidance"] or "Accessibility" in payload["errors"][0]["guidance"]


def test_snapshot_json_honors_max_chars(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "snapshot", "--json", "--max-chars", "4000"],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.snapshot"
    assert payload["data"]["max_chars"] == 4000
    assert payload["data"]["screenshot_path"].startswith("~/")


def test_inspect_json_returns_page_map(tmp_path: Path) -> None:
    payload = run_cli(["codex", "inspect", "--json", "--max-nodes", "20"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.inspect"
    assert payload["data"]["summary"]["codex_frontmost"] is True
    assert payload["data"]["summary"]["visible_buttons"][0]["name"] == "New chat"


def test_ax_tree_json_honors_max_nodes_and_reports_truncation(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "ax-tree", "--json", "--max-nodes", "1"],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.ax_tree"
    assert len(payload["data"]["nodes"]) == 1
    assert payload["data"]["truncated"] is True
    assert payload["warnings"] == ["AX tree truncated"]


def test_disallowed_command_is_not_registered(tmp_path: Path) -> None:
    stdout = io.StringIO()
    exit_code = main(
        ["codex", "send", "--json"],
        observer_factory=FakeObserver,
        stdout=stdout,
        stderr=io.StringIO(),
        state_dir=tmp_path,
    )

    assert exit_code == 2
