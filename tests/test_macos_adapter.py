from __future__ import annotations

from pathlib import Path
import sys

from evaos_desktop_bridge.adapters.codex_macos import MacOSCodexObserver, RunnerResult


class FakeRunner:
    def __init__(self, outputs: dict[tuple[str, ...], RunnerResult]) -> None:
        self.outputs = outputs
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: list[str], timeout: float = 5.0) -> RunnerResult:
        key = tuple(command)
        self.commands.append(key)
        if key in self.outputs:
            return self.outputs[key]
        for prefix, result in self.outputs.items():
            if key[: len(prefix)] == prefix:
                return result
        return RunnerResult(returncode=1, stdout="", stderr="missing")


def test_status_redacts_install_paths_and_reports_pid(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            ("pgrep", "-x", "Codex"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
        }
    )
    observer = MacOSCodexObserver(
        runner=runner,
        app_paths=[Path.home() / "Applications" / "Codex.app"],
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.status()

    assert result.ok is True
    assert result.data["app"]["running"] is True
    assert result.data["app"]["pid"] == 123
    assert str(Path.home()) not in str(result.data)
    assert result.data["app"]["paths"] == ["~/Applications/Codex.app"]


def test_focus_refuses_when_accessibility_missing(tmp_path: Path) -> None:
    observer = MacOSCodexObserver(
        runner=FakeRunner({}),
        app_paths=[],
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: False,
    )

    result = observer.focus()

    assert result.ok is False
    assert result.errors[0]["code"] == "permission_missing"
    assert result.errors[0]["permission"] == "accessibility"


def test_snapshot_caps_title_and_redacts_screenshot_path_when_codex_frontmost(tmp_path: Path) -> None:
    title = f"Project {Path.home()}/private " + ("x" * 50)
    runner = FakeRunner(
        {
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="Codex\n", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to tell first application process whose frontmost is true to get name of front window',
            ): RunnerResult(returncode=0, stdout=title + "\n", stderr=""),
            ("screencapture", "-x"): RunnerResult(returncode=0, stdout="", stderr=""),
        }
    )
    observer = MacOSCodexObserver(
        runner=runner,
        app_paths=[],
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        now=lambda: "2026-05-02T00:00:00Z",
    )

    result = observer.snapshot(max_chars=24)

    assert result.ok is True
    assert result.data["frontmost_app"] == "Codex"
    assert result.data["codex_frontmost"] is True
    assert len(result.data["window_title"]) <= 24
    assert str(Path.home()) not in str(result.data)
    assert result.data["screenshot_path"].endswith(".png")
    assert "screenshots" in result.data["screenshot_path"]
    assert result.warnings == ["window title truncated"]


def test_snapshot_skips_screenshot_when_codex_is_not_frontmost(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="Telegram\n", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to tell first application process whose frontmost is true to get name of front window',
            ): RunnerResult(returncode=0, stdout="Private chat\n", stderr=""),
        }
    )
    observer = MacOSCodexObserver(
        runner=runner,
        app_paths=[],
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        now=lambda: "2026-05-02T00:00:00Z",
    )

    result = observer.snapshot(max_chars=4000)

    assert result.ok is True
    assert result.data["frontmost_app"] == "Telegram"
    assert result.data["codex_frontmost"] is False
    assert result.data["window_title"] is None
    assert result.data["screenshot_path"] is None
    assert any("screenshot skipped" in warning for warning in result.warnings)
    assert not any(command[0] == "screencapture" for command in runner.commands)


def test_windows_returns_redacted_visible_window_metadata(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            ("pgrep", "-x", "Codex"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            (sys.executable, "-c"): RunnerResult(
                returncode=0,
                stdout='{"ok": true, "windows": [{"index": 0, "title": "/Users/lume/private Codex", "role": "AXWindow", "bounds": {"x": 1, "y": 2, "width": 3, "height": 4}, "codex_frontmost": true}], "nodes": [], "truncated": false}',
                stderr="",
            ),
        }
    )
    observer = MacOSCodexObserver(
        runner=runner,
        app_paths=[],
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.windows()

    assert result.ok is True
    assert result.data["count"] == 1
    assert result.data["windows"][0]["title"] == "~/private Codex"
    assert result.data["windows"][0]["bounds"] == {"x": 1, "y": 2, "width": 3, "height": 4}


def test_ax_tree_returns_roles_names_only_and_truncates(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            ("pgrep", "-x", "Codex"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            (sys.executable, "-c"): RunnerResult(
                returncode=0,
                stdout='{"ok": true, "windows": [], "nodes": [{"role": "AXWindow", "name": "Codex", "depth": 0, "window_index": null}, {"role": "AXStaticText", "name": "/Users/lume/secret project", "depth": 1, "window_index": null}], "truncated": true}',
                stderr="",
            ),
        }
    )
    observer = MacOSCodexObserver(
        runner=runner,
        app_paths=[],
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.ax_tree(max_nodes=2)

    assert result.ok is True
    assert result.data["nodes"] == [
        {"role": "AXWindow", "name": "Codex", "depth": 0, "window_index": None},
        {"role": "AXStaticText", "name": "~/secret project", "depth": 1, "window_index": None},
    ]
    assert result.data["truncated"] is True
    assert result.warnings == ["AX tree truncated at 2 nodes"]
