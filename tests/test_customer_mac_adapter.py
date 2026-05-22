from __future__ import annotations

import json
import sys
from pathlib import Path

from evaos_desktop_bridge.adapters import customer_mac
from evaos_desktop_bridge.adapters.codex_macos import RunnerResult
from evaos_desktop_bridge.adapters.customer_mac import CustomerMacObserver


class FakeRunner:
    def __init__(self, outputs: dict[tuple[str, ...], RunnerResult] | None = None) -> None:
        self.outputs = outputs or {}
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: list[str], timeout: float = 5.0) -> RunnerResult:
        key = tuple(command)
        self.commands.append(key)
        if key in self.outputs:
            return self.outputs[key]
        for prefix, result in self.outputs.items():
            if key[: len(prefix)] == prefix:
                return result
        return RunnerResult(returncode=1, stdout="", stderr="")


def installed_mirroring(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "iPhone Mirroring.app"
    app.mkdir()
    monkeypatch.setattr(customer_mac, "IPHONE_MIRRORING_APP", app)


def assert_no_mutation_commands(commands: list[tuple[str, ...]]) -> None:
    blocked = {"open", "osascript", "cliclick"}
    assert not any(command and command[0] in blocked for command in commands)


def assert_no_keystroke_commands(commands: list[tuple[str, ...]]) -> None:
    assert not any(command[0] == "osascript" and "keystroke" in " ".join(command) for command in commands)


def test_iphone_open_app_blocks_sensitive_ios_apps_during_dry_run(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    observer = CustomerMacObserver(
        runner=FakeRunner({("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr="")}),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_mirroring_action(action="open_app", app_name="Phone", dry_run=True)

    assert result.ok is False
    assert result.errors[0]["code"] == "iphone_app_name_not_allowed"
    assert_no_mutation_commands(observer.runner.commands)


def test_status_reports_screen_recording_preflight(tmp_path: Path) -> None:
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
    )

    result = observer.status()

    assert result.ok is True
    assert result.data["permissions"]["accessibility"]["status"] == "granted"
    assert result.data["permissions"]["screen_recording"]["status"] == "granted"


def test_control_session_start_stop_and_kill_switch(tmp_path: Path) -> None:
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin")

    started = observer.control_start(mode="full-access", agent_label="Aurelius")
    status = observer.control_status()
    stopped = observer.control_stop()
    killed = observer.control_kill_switch()

    assert started.ok is True
    assert started.data["session"]["active"] is True
    assert started.data["session"]["mode"] == "full_access"
    assert status.data["active"] is True
    assert stopped.data["session"]["active"] is False
    assert killed.data["session"]["kill_switch"] is True


def test_desktop_click_dry_run_allows_coordinate_fallback_without_mutation(tmp_path: Path) -> None:
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_click(x=10, y=20, dry_run=True)

    assert result.ok is True
    assert result.data["would_click"] is True
    assert result.data["point"] == {"x": 10, "y": 20}
    assert_no_mutation_commands(observer.runner.commands)


def test_desktop_type_dry_run_records_hash_without_typing(tmp_path: Path) -> None:
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_type(text="hello world", dry_run=True)

    assert result.ok is True
    assert result.data["would_type"] is True
    assert result.data["text_sha256"]
    assert_no_keystroke_commands(observer.runner.commands)


def test_iphone_see_does_not_focus_mirroring_as_read_only(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    runner = FakeRunner(
        {
            ("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="Safari\n", stderr=""),
        }
    )
    observer = CustomerMacObserver(
        runner=runner,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_see()

    assert result.ok is False
    assert result.errors[0]["code"] == "iphone_mirroring_not_frontmost"
    assert ("open", "-a", "iPhone Mirroring") not in runner.commands


def test_iphone_tap_named_target_blocks_dangerous_labels_during_dry_run(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    observer = CustomerMacObserver(
        runner=FakeRunner({("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr="")}),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_mirroring_action(action="tap_named_target", target_label="Send", dry_run=True)

    assert result.ok is False
    assert result.errors[0]["code"] == "target_label_not_allowed"
    assert_no_mutation_commands(observer.runner.commands)


def test_iphone_swipe_dry_run_is_customer_available_without_env(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    monkeypatch.delenv("EVAOS_SUPPORT_CANARY_CONTROLS", raising=False)
    observer = CustomerMacObserver(
        runner=FakeRunner({("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr="")}),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_mirroring_action(action="swipe_left", dry_run=True)

    assert result.ok is True
    assert result.data["would_perform"] is True
    assert result.data["guarded"] is True
    assert_no_mutation_commands(observer.runner.commands)


def test_iphone_swipe_dry_run_is_named_and_non_mutating(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    observer = CustomerMacObserver(
        runner=FakeRunner({("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr="")}),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_mirroring_action(action="swipe_left", dry_run=True)

    assert result.ok is True
    assert result.data["would_perform"] is True
    assert result.data["guarded"] is True
    assert_no_mutation_commands(observer.runner.commands)


def test_iphone_approved_message_requires_recipient_context(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    observer = CustomerMacObserver(
        runner=FakeRunner({("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr="")}),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_mirroring_action(action="send_approved_message", text="hello", dry_run=True)

    assert result.ok is False
    assert result.errors[0]["code"] == "recipient_context_required"
    assert_no_mutation_commands(observer.runner.commands)


def test_iphone_live_swipe_uses_internal_gesture_not_generic_coordinates(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    runner = FakeRunner(
        {
            ("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            ("open", "-a", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="", stderr=""),
            (sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "vector": {"dx": -900, "dy": 0}}), stderr=""),
        }
    )
    observer = CustomerMacObserver(
        runner=runner,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_mirroring_action(action="swipe_left", dry_run=False)

    assert result.ok is True
    assert result.data["gesture"] == "scroll_wheel"
    assert result.data["vector"] == {"dx": -900, "dy": 0}
    assert_no_keystroke_commands(runner.commands)


def test_iphone_safe_open_app_dry_run_stays_named_and_non_mutating(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    observer = CustomerMacObserver(
        runner=FakeRunner({("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr="")}),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_mirroring_action(action="open_app", app_name="Calculator", dry_run=True)

    assert result.ok is True
    assert result.data["would_perform"] is True
    assert result.data["app_name"] == "Calculator"
    assert_no_mutation_commands(observer.runner.commands)


def test_safe_ax_node_does_not_export_raw_bounds(tmp_path: Path) -> None:
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin")

    node = observer._safe_node(
        {
            "role": "AXButton",
            "name": "Continue",
            "depth": 1,
            "window_index": 0,
            "bounds": {"x": 10, "y": 20, "width": 30, "height": 40},
            "actions": ["AXPress"],
        }
    )

    assert "bounds" not in node
    assert node["role"] == "AXButton"
    assert node["actions"] == ["AXPress"]


def test_local_site_action_dry_run_requires_local_browser_url(tmp_path: Path) -> None:
    observer = CustomerMacObserver(
        runner=FakeRunner(
            {
                (
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ): RunnerResult(returncode=0, stdout="Safari\n", stderr=""),
                ("osascript", "-e", 'tell application "Safari" to get URL of front document'): RunnerResult(returncode=0, stdout="https://example.com\n", stderr=""),
            }
        ),
        state_dir=tmp_path,
        platform_name="Darwin",
    )

    result = observer.local_site_action(action="reload", dry_run=True)

    assert result.ok is False
    assert result.errors[0]["code"] == "local_site_url_not_allowed"
    assert_no_keystroke_commands(observer.runner.commands)


def test_local_site_action_dry_run_allows_loopback_browser_url(tmp_path: Path) -> None:
    observer = CustomerMacObserver(
        runner=FakeRunner(
            {
                (
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ): RunnerResult(returncode=0, stdout="Safari\n", stderr=""),
                ("osascript", "-e", 'tell application "Safari" to get URL of front document'): RunnerResult(returncode=0, stdout="http://127.0.0.1:3000\n", stderr=""),
            }
        ),
        state_dir=tmp_path,
        platform_name="Darwin",
    )

    result = observer.local_site_action(action="reload", dry_run=True)

    assert result.ok is True
    assert result.data["would_perform"] is True
    assert result.data["current_url"] == "http://127.0.0.1:3000"
    assert_no_keystroke_commands(observer.runner.commands)
