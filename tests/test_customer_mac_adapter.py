from __future__ import annotations

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
