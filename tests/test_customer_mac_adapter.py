from __future__ import annotations

import json
import os
import struct
import sys
import threading
import uuid
from pathlib import Path

from evaos_desktop_bridge.adapters import customer_mac
from evaos_desktop_bridge.adapters.codex_macos import RunnerResult
from evaos_desktop_bridge.adapters.customer_mac import CustomerMacObserver
from evaos_desktop_bridge.helper_ipc import make_capability_token, run_helper_server
from evaos_desktop_bridge.types import CommandResult


class FakeRunner:
    def __init__(self, outputs: dict[tuple[str, ...], RunnerResult] | None = None) -> None:
        self.outputs = outputs or {}
        self.commands: list[tuple[str, ...]] = []
        self.timeouts: dict[tuple[str, ...], float] = {}

    def __call__(self, command: list[str], timeout: float = 5.0) -> RunnerResult:
        key = tuple(command)
        self.commands.append(key)
        self.timeouts[key] = timeout
        if key in self.outputs:
            return self.outputs[key]
        for prefix, result in self.outputs.items():
            if key[: len(prefix)] == prefix:
                return result
        return RunnerResult(returncode=1, stdout="", stderr="")


class FakeHelperClient:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, object], str | None]] = []

    def dispatch(self, command: str, payload: dict[str, object], *, audit_id: str | None = None) -> CommandResult:
        self.calls.append((command, payload, audit_id))
        return self.result


class AuditCheckingHelperClient(FakeHelperClient):
    def __init__(self, result: CommandResult, *, state_dir: Path) -> None:
        super().__init__(result)
        self.state_dir = state_dir
        self.audit_seen_before_dispatch = False

    def dispatch(self, command: str, payload: dict[str, object], *, audit_id: str | None = None) -> CommandResult:
        assert audit_id
        records = [json.loads(line) for line in (self.state_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.audit_seen_before_dispatch = any(record.get("audit_id") == audit_id for record in records)
        return super().dispatch(command, payload, audit_id=audit_id)


def png_header(width: int = 4, height: int = 4) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", width, height) + b"\x00" * 16


def installed_mirroring(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "iPhone Mirroring.app"
    app.mkdir()
    monkeypatch.setattr(customer_mac, "IPHONE_MIRRORING_APP", app)


def assert_no_mutation_commands(commands: list[tuple[str, ...]]) -> None:
    blocked = {"open", "osascript", "cliclick"}
    assert not any(command and command[0] in blocked for command in commands)


def assert_no_keystroke_commands(commands: list[tuple[str, ...]]) -> None:
    assert not any(command[0] == "osascript" and "keystroke" in " ".join(command) for command in commands)


def short_socket_path() -> Path:
    return Path("/tmp") / f"evaos-customer-helper-{uuid.uuid4().hex}.sock"


FRONTMOST_SCRIPT = 'tell application "System Events" to get name of first application process whose frontmost is true'
FINDER_TARGET = {"pid": 4242, "app_name": "Finder", "process_name": "Finder", "path": []}


def frontmost_process_outputs(app_name: str = "Finder", pid: int = 4242, process_name: str = "Finder") -> dict[tuple[str, ...], RunnerResult]:
    return {
        ("osascript", "-e", FRONTMOST_SCRIPT): RunnerResult(returncode=0, stdout=f"{app_name}\n", stderr=""),
        ("pgrep", "-x", app_name): RunnerResult(returncode=0, stdout=f"{pid}\n", stderr=""),
        ("/bin/ps", "-p", str(pid), "-o", "comm="): RunnerResult(returncode=0, stdout=f"/System/Applications/{process_name}.app/Contents/MacOS/{process_name}\n", stderr=""),
    }


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
    assert result.data["safety"]["full_access_allows_sensitive_apps"] is False
    assert result.data["safety"]["sensitive_apps_blocked"] is True


def test_control_status_prefers_bundled_peekaboo_before_connector_helper_alias(monkeypatch, tmp_path: Path) -> None:
    bridge_executable = tmp_path / "Bridge" / "evaos-desktop-bridge"
    bundled_helper = bridge_executable.parent / "bin" / "evaos-connector-helper"
    bundled_peekaboo = bridge_executable.parent / "bin" / "peekaboo"
    bundled_helper.parent.mkdir(parents=True)
    bridge_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    bundled_helper.write_text("#!/bin/sh\n", encoding="utf-8")
    bundled_peekaboo.write_text("#!/bin/sh\n", encoding="utf-8")
    bridge_executable.chmod(0o755)
    bundled_helper.chmod(0o755)
    bundled_peekaboo.chmod(0o755)

    monkeypatch.setattr(customer_mac.sys, "executable", str(bridge_executable))
    monkeypatch.setattr(customer_mac.sys, "argv", [str(bridge_executable)])
    monkeypatch.setattr(customer_mac, "PEEKABOO_BIN_CANDIDATES", ("peekaboo",))
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/opt/homebrew/bin/peekaboo" if name == "peekaboo" else None)

    runner = FakeRunner(
        {
            (str(bundled_peekaboo), "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2 bundled\n", stderr=""),
            (str(bundled_helper), "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2 bundled\n", stderr=""),
            ("/opt/homebrew/bin/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2 homebrew\n", stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin")

    status = observer.control_status()

    assert status.data["peekaboo"]["available"] is True
    assert status.data["peekaboo"]["path"] == str(bundled_peekaboo)
    assert (str(bundled_peekaboo), "--version") in runner.commands
    assert (str(bundled_helper), "--version") not in runner.commands
    assert ("/opt/homebrew/bin/peekaboo", "--version") not in runner.commands


def test_control_status_prefers_path_peekaboo_before_connector_helper_alias(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(customer_mac, "PEEKABOO_BIN_CANDIDATES", ("peekaboo", "evaos-connector-helper"))
    monkeypatch.setattr(
        customer_mac.shutil,
        "which",
        lambda name: f"/opt/homebrew/bin/{name}" if name in {"peekaboo", "evaos-connector-helper"} else None,
    )

    runner = FakeRunner(
        {
            ("/opt/homebrew/bin/peekaboo", "--version"): RunnerResult(
                returncode=0,
                stdout="Peekaboo 3.2.2 homebrew\n",
                stderr="",
            ),
            ("/opt/homebrew/bin/evaos-connector-helper", "--version"): RunnerResult(
                returncode=0,
                stdout="Peekaboo 3.2.2 helper alias\n",
                stderr="",
            ),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin")

    status = observer.control_status()

    assert status.data["peekaboo"]["available"] is True
    assert status.data["peekaboo"]["path"] == "/opt/homebrew/bin/peekaboo"
    assert ("/opt/homebrew/bin/peekaboo", "--version") in runner.commands
    assert ("/opt/homebrew/bin/evaos-connector-helper", "--version") not in runner.commands


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


def test_control_session_start_sets_takeover_warning_countdown(tmp_path: Path) -> None:
    runner = FakeRunner({("osascript", "-e"): RunnerResult(returncode=0, stdout="", stderr="")})
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin")

    started = observer.control_start(mode="full-access", agent_label="Aurelius")
    status = observer.control_status()

    assert started.ok is True
    assert started.data["ready"] is False
    assert started.data["takeover_warning"]["active"] is True
    assert started.data["takeover_warning"]["seconds"] == 10
    assert started.data["session"]["takeover_warning_started_at"]
    assert started.data["session"]["takeover_warning_until"]
    assert status.data["ready"] is False
    assert status.data["takeover_warning"]["active"] is True
    assert status.data["takeover_warning"]["remaining_seconds"] >= 1
    assert any(command[:2] == ("osascript", "-e") and "Taking over screen" in command[2] for command in runner.commands)
    assert any(command[:2] == ("osascript", "-e") and "repeat 6 times" in command[2] and "delay 0.35" in command[2] for command in runner.commands)
    signal_status = started.data["takeover_warning"]["signal_status"]
    assert signal_status["notification"]["available"] is True
    assert signal_status["beep_loop"]["available"] is True
    assert status.data["takeover_warning"]["signal_status"]["beep_loop"]["available"] is True


def test_control_session_repeated_start_does_not_extend_or_rebuzz_warning(tmp_path: Path) -> None:
    runner = FakeRunner()
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin")

    first = observer.control_start(mode="full-access", agent_label="Aurelius")
    warning_commands = [command for command in runner.commands if command and command[0] in {"osascript", "afplay"}]
    second = observer.control_start(mode="full-access", agent_label="Aurelius")
    repeated_warning_commands = [command for command in runner.commands if command and command[0] in {"osascript", "afplay"}]

    assert second.data["session"]["takeover_warning_until"] == first.data["session"]["takeover_warning_until"]
    assert second.data["takeover_warning_reused"] is True
    assert repeated_warning_commands == warning_commands


def test_desktop_click_dry_run_allows_coordinate_fallback_without_mutation(tmp_path: Path) -> None:
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_click(x=10, y=20, dry_run=True)

    assert result.ok is True
    assert result.data["would_click"] is True
    assert result.data["point"] == {"x": 10, "y": 20}
    assert_no_mutation_commands(observer.runner.commands)


def test_desktop_click_routes_post_to_pid_fallback_through_helper_without_python_spawn(tmp_path: Path) -> None:
    runner = FakeRunner(frontmost_process_outputs())
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "click", "clicked": True, "point": {"x": 10, "y": 20}, "engine": "helper_post_to_pid"},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=runner,
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(x=10, y=20, dry_run=False)

    assert result.ok is True
    assert result.data["clicked"] is True
    assert result.data["engine"] == "helper_post_to_pid"
    assert result.provenance["source"] == "computer_use_helper"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "click", "target": FINDER_TARGET, "x": 10, "y": 20})
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_click_helper_dispatch_writes_actuation_audit_record(tmp_path: Path) -> None:
    helper = AuditCheckingHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "click", "clicked": True, "point": {"x": 10, "y": 20}, "engine": "helper_post_to_pid"},
            provenance={"source": "computer_use_helper"},
        ),
        state_dir=tmp_path,
    )
    observer = CustomerMacObserver(
        runner=FakeRunner(frontmost_process_outputs()),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(x=10, y=20, dry_run=False)

    assert result.ok is True
    helper_audit_id = helper.calls[0][2]
    assert helper_audit_id and helper_audit_id.startswith("audit-helper-")
    assert helper.audit_seen_before_dispatch is True
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    attempt = next(record for record in records if record["audit_id"] == helper_audit_id)
    completion = next(record for record in records if record["provenance"].get("audit_phase") == "completion")
    assert attempt["command"] == "helper.mouse_action"
    assert attempt["target"] == "computer_use_helper"
    assert attempt["ok"] is True
    assert attempt["args"]["payload"] == {"action": "click", "target": FINDER_TARGET, "x": 10, "y": 20}
    assert attempt["provenance"]["source"] == "computer_use_helper"
    assert attempt["provenance"]["helper_command"] == "mouse_action"
    assert attempt["provenance"]["audit_phase"] == "authorized_dispatch"
    assert completion["ok"] is True
    assert completion["provenance"]["helper_audit_id"] == helper_audit_id


def test_desktop_click_routes_ax_snapshot_target_through_helper_without_python_spawn(tmp_path: Path) -> None:
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "press", "clicked": True, "engine": "helper_ax"},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    snapshot_id = f"snap-desktop-{uuid.uuid4().hex}"
    ax_target = {
        "pid": 1234,
        "process_name": "TestApp",
        "path": [
            {"role": "AXWindow", "index": 0},
            {"role": "AXButton", "name": "OK", "identifier": "ok-button", "index": 2},
        ],
    }
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "el-0001",
                "snapshot_id": snapshot_id,
                "label": "OK",
                "role": "AXButton",
                "bounds": {"x": 10, "y": 20, "width": 80, "height": 30},
                "center": {"x": 50, "y": 35},
                "actions": ["AXPress"],
                "engine": "ax_fallback",
                "ax_target": ax_target,
            }
        ],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, element_id="el-0001", dry_run=False)

    assert result.ok is True
    assert result.data["engine"] == "helper_ax"
    assert helper.calls[0][0] == "ax_action"
    assert helper.calls[0][1] == {"action": "press", "target": ax_target}
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in observer.runner.commands)


def test_desktop_click_blocks_sensitive_background_ax_target_before_helper_dispatch(tmp_path: Path) -> None:
    helper = FakeHelperClient(CommandResult(ok=True, data={"performed": True, "action": "press", "clicked": True, "engine": "helper_ax"}))
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    snapshot_id = f"snap-desktop-{uuid.uuid4().hex}"
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "el-0001",
                "snapshot_id": snapshot_id,
                "label": "Send",
                "role": "AXButton",
                "bounds": {"x": 10, "y": 20, "width": 80, "height": 30},
                "center": {"x": 50, "y": 35},
                "actions": ["AXPress"],
                "engine": "ax_fallback",
                "ax_target": {"pid": 1234, "app_name": "Mail", "path": [{"role": "AXButton", "name": "Send", "index": 0}]},
            }
        ],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, element_id="el-0001", dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "sensitive_app_blocked"
    assert helper.calls == []


def test_desktop_click_treats_ax_web_content_as_inert_without_helper_dispatch(tmp_path: Path) -> None:
    helper = FakeHelperClient(CommandResult(ok=True, data={"performed": True, "action": "press", "clicked": True, "engine": "helper_ax"}))
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    snapshot_id = f"snap-desktop-{uuid.uuid4().hex}"
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "el-0001",
                "snapshot_id": snapshot_id,
                "label": "Submit",
                "role": "AXButton",
                "bounds": {"x": 10, "y": 20, "width": 80, "height": 30},
                "center": {"x": 50, "y": 35},
                "actions": ["AXPress"],
                "engine": "ax_fallback",
                "ax_target": {
                    "pid": 1234,
                    "app_name": "Google Chrome",
                    "path": [{"role": "AXWindow", "index": 0}, {"role": "AXWebArea", "index": 0}, {"role": "AXButton", "name": "Submit", "index": 4}],
                },
            }
        ],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, element_id="el-0001", dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "ax_web_content_inert"
    assert helper.calls == []


def test_desktop_set_value_routes_ax_snapshot_target_through_helper_without_typing(tmp_path: Path) -> None:
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "set_value", "engine": "helper_ax", "value_sha256": "placeholder"},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    snapshot_id = f"snap-desktop-{uuid.uuid4().hex}"
    ax_target = {
        "pid": 1234,
        "process_name": "TestApp",
        "path": [
            {"role": "AXWindow", "index": 0},
            {"role": "AXTextField", "name": "Search", "identifier": "search-field", "index": 1},
        ],
    }
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "el-0002",
                "snapshot_id": snapshot_id,
                "label": "Search",
                "role": "AXTextField",
                "bounds": {"x": 10, "y": 20, "width": 200, "height": 30},
                "center": {"x": 110, "y": 35},
                "actions": [],
                "engine": "ax_fallback",
                "ax_target": ax_target,
            }
        ],
    )

    result = observer.desktop_set_value(snapshot_id=snapshot_id, element_id="el-0002", value="hello", dry_run=False)

    assert result.ok is True
    assert result.data["engine"] == "helper_ax"
    assert helper.calls[0][0] == "ax_action"
    assert helper.calls[0][1] == {"action": "set_value", "target": ax_target, "value": "hello", "attribute": "AXValue"}
    assert helper.calls[0][2]
    assert str(helper.calls[0][2]).startswith("audit-helper-")
    assert not any(command and command[0] == "osascript" and "keystroke" in " ".join(command) for command in observer.runner.commands)


def test_desktop_set_value_blocks_non_text_ax_roles_before_helper_dispatch(tmp_path: Path) -> None:
    helper = FakeHelperClient(CommandResult(ok=True, data={"performed": True, "action": "set_value", "engine": "helper_ax"}))
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    snapshot_id = f"snap-desktop-{uuid.uuid4().hex}"
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "el-0003",
                "snapshot_id": snapshot_id,
                "label": "Volume",
                "role": "AXSlider",
                "bounds": {"x": 10, "y": 20, "width": 200, "height": 30},
                "center": {"x": 110, "y": 35},
                "actions": [],
                "engine": "ax_fallback",
                "ax_target": {
                    "pid": 1234,
                    "process_name": "TestApp",
                    "path": [
                        {"role": "AXWindow", "index": 0},
                        {"role": "AXSlider", "name": "Volume", "index": 1},
                    ],
                },
            }
        ],
    )

    result = observer.desktop_set_value(snapshot_id=snapshot_id, element_id="el-0003", value="75", dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "desktop_set_value_non_text_field_blocked"
    assert helper.calls == []


def test_desktop_click_blocks_ax_target_without_process_identity_before_helper_dispatch(tmp_path: Path) -> None:
    helper = FakeHelperClient(CommandResult(ok=True, data={"performed": True, "action": "press", "clicked": True, "engine": "helper_ax"}))
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    snapshot_id = f"snap-desktop-{uuid.uuid4().hex}"
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "el-0004",
                "snapshot_id": snapshot_id,
                "label": "OK",
                "role": "AXButton",
                "bounds": {"x": 10, "y": 20, "width": 80, "height": 30},
                "center": {"x": 50, "y": 35},
                "actions": ["AXPress"],
                "engine": "ax_fallback",
                "ax_target": {"pid": 1234, "path": [{"role": "AXButton", "name": "OK", "index": 0}]},
            }
        ],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, element_id="el-0004", dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "ax_target_process_identity_required"
    assert helper.calls == []


def test_desktop_click_helper_error_fails_closed_without_python_fallback(tmp_path: Path) -> None:
    runner = FakeRunner({**frontmost_process_outputs(), (sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "action": "click"}), stderr="")})
    helper = FakeHelperClient(
        CommandResult(
            ok=False,
            data={"performed": False, "action": "click"},
            errors=[{"code": "helper_unavailable", "message": "helper unavailable", "guidance": "restart helper"}],
        )
    )
    observer = CustomerMacObserver(
        runner=runner,
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(x=10, y=20, dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "helper_unavailable"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "click", "target": FINDER_TARGET, "x": 10, "y": 20})
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_click_helper_failure_writes_failed_actuation_audit_record(tmp_path: Path) -> None:
    helper = FakeHelperClient(
        CommandResult(
            ok=False,
            data={"performed": False, "action": "click"},
            errors=[{"code": "helper_unavailable", "message": "helper unavailable", "guidance": "restart helper"}],
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=FakeRunner(frontmost_process_outputs()),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(x=10, y=20, dry_run=False)

    assert result.ok is False
    helper_audit_id = helper.calls[0][2]
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    attempt = next(record for record in records if record["audit_id"] == helper_audit_id)
    completion = next(record for record in records if record["provenance"].get("audit_phase") == "completion")
    assert attempt["ok"] is True
    assert attempt["provenance"]["audit_phase"] == "authorized_dispatch"
    assert completion["ok"] is False
    assert completion["errors"][0]["code"] == "helper_unavailable"
    assert completion["provenance"]["helper_audit_id"] == helper_audit_id


def test_desktop_click_sensitive_frontmost_blocks_before_helper_audit_or_dispatch(tmp_path: Path) -> None:
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "click", "clicked": True},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=FakeRunner(
            {
                (
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ): RunnerResult(returncode=0, stdout="Messages\n", stderr=""),
            }
        ),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(x=10, y=20, dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "sensitive_app_blocked"
    assert helper.calls == []
    assert not (tmp_path / "audit.jsonl").exists()


def test_desktop_scroll_routes_post_to_pid_fallback_through_helper_without_python_spawn(tmp_path: Path) -> None:
    runner = FakeRunner(frontmost_process_outputs())
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "scroll", "scrolled": True, "direction": "down", "amount": 600, "engine": "helper_post_to_pid"},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=runner,
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_scroll(direction="down", amount=600, dry_run=False)

    assert result.ok is True
    assert result.data["engine"] == "helper_post_to_pid"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "scroll", "target": FINDER_TARGET, "direction": "down", "amount": 600})
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_drag_routes_post_to_pid_fallback_through_helper_without_python_spawn(tmp_path: Path) -> None:
    runner = FakeRunner(frontmost_process_outputs())
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "drag", "dragged": True, "from": {"x": 1, "y": 2}, "to": {"x": 3, "y": 4}, "engine": "helper_post_to_pid"},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=runner,
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_drag(from_x=1, from_y=2, to_x=3, to_y=4, dry_run=False)

    assert result.ok is True
    assert result.data["engine"] == "helper_post_to_pid"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "drag", "target": FINDER_TARGET, "from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4})
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_click_routes_ax_gap_snapshot_target_through_post_to_pid_helper(tmp_path: Path) -> None:
    snapshot_id = "snap-desktop-cccccccccccccccccccccccccccccccc"
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots" / f"{snapshot_id}.json").write_text(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "target": "desktop",
                "engine": "ax_fallback",
                "timestamp": "2999-01-01T00:00:00Z",
                "elements": [
                    {
                        "element_id": "finder-row",
                        "label": "Documents",
                        "role": "AXRow",
                        "bounds": {"x": 100, "y": 200, "width": 180, "height": 32},
                        "center": {"x": 190, "y": 216},
                        "actions": [],
                        "engine": "ax_fallback",
                        "ax_target": {
                            "pid": 4242,
                            "app_name": "Finder",
                            "process_name": "Finder",
                            "path": [{"role": "AXWindow", "index": 0}, {"role": "AXRow", "name": "Documents", "index": 3}],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "click", "clicked": True, "point": {"x": 190, "y": 216}, "engine": "helper_post_to_pid"},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, element_id="finder-row", dry_run=False)

    assert result.ok is True
    assert result.data["engine"] == "helper_post_to_pid"
    assert helper.calls[0][0] == "mouse_action"
    assert helper.calls[0][1] == {
        "action": "click",
        "x": 190,
        "y": 216,
        "target": {
            "pid": 4242,
            "app_name": "Finder",
            "process_name": "Finder",
            "path": [{"role": "AXWindow", "index": 0}, {"role": "AXRow", "name": "Documents", "index": 3}],
        },
    }
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in observer.runner.commands)


def test_desktop_click_snapshot_coordinates_keep_snapshot_target_when_frontmost_changes(tmp_path: Path) -> None:
    snapshot_id = "snap-desktop-dddddddddddddddddddddddddddddddd"
    observer = CustomerMacObserver(
        runner=FakeRunner(
            {
                ("osascript", "-e", FRONTMOST_SCRIPT): RunnerResult(returncode=0, stdout="TextEdit\n", stderr=""),
            }
        ),
        helper_client=FakeHelperClient(
            CommandResult(
                ok=True,
                data={"performed": True, "action": "click", "clicked": True, "point": {"x": 190, "y": 216}, "engine": "helper_post_to_pid"},
                provenance={"source": "computer_use_helper"},
            )
        ),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    ax_target = {
        "pid": 4242,
        "app_name": "Finder",
        "process_name": "Finder",
        "path": [{"role": "AXWindow", "index": 0}, {"role": "AXRow", "name": "Documents", "index": 3}],
    }
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "finder-row",
                "label": "Documents",
                "role": "AXRow",
                "bounds": {"x": 100, "y": 200, "width": 180, "height": 32},
                "center": {"x": 190, "y": 216},
                "actions": [],
                "engine": "ax_fallback",
                "ax_target": ax_target,
            }
        ],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, x=190, y=216, dry_run=False)

    assert result.ok is True
    helper = observer.helper_client
    assert isinstance(helper, FakeHelperClient)
    assert helper.calls[0][1]["target"] == ax_target
    assert ("pgrep", "-x", "TextEdit") not in observer.runner.commands


def test_desktop_click_snapshot_coordinate_hit_test_uses_half_open_bounds(tmp_path: Path) -> None:
    snapshot_id = "snap-desktop-abababababababababababababababab"
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "click", "clicked": True, "point": {"x": 200, "y": 220}, "engine": "helper_post_to_pid"},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    left_target = {"pid": 4242, "app_name": "Finder", "process_name": "Finder", "path": [{"role": "AXRow", "name": "Left", "index": 0}]}
    right_target = {"pid": 4343, "app_name": "Finder", "process_name": "Finder", "path": [{"role": "AXRow", "name": "Right", "index": 1}]}
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "left-row",
                "label": "Left",
                "role": "AXRow",
                "bounds": {"x": 100, "y": 200, "width": 100, "height": 40},
                "center": {"x": 150, "y": 220},
                "actions": [],
                "engine": "ax_fallback",
                "ax_target": left_target,
            },
            {
                "element_id": "right-row",
                "label": "Right",
                "role": "AXRow",
                "bounds": {"x": 200, "y": 200, "width": 100, "height": 40},
                "center": {"x": 250, "y": 220},
                "actions": [],
                "engine": "ax_fallback",
                "ax_target": right_target,
            },
        ],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, x=200, y=220, dry_run=False)

    assert result.ok is True
    assert helper.calls[0][1]["target"] == right_target


def test_desktop_click_snapshot_coordinates_without_ax_target_fail_closed_before_frontmost_retarget(tmp_path: Path) -> None:
    snapshot_id = "snap-desktop-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    helper = FakeHelperClient(CommandResult(ok=True, data={"performed": True, "action": "click"}))
    observer = CustomerMacObserver(
        runner=FakeRunner(frontmost_process_outputs(app_name="TextEdit", process_name="TextEdit")),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="peekaboo",
        elements=[],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, x=10, y=20, dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "post_to_pid_target_required"
    assert helper.calls == []
    assert ("pgrep", "-x", "TextEdit") not in observer.runner.commands


def test_desktop_click_ax_gap_target_with_invalid_pid_fails_before_helper_dispatch(tmp_path: Path) -> None:
    snapshot_id = "snap-desktop-acacacacacacacacacacacacacacacac"
    helper = FakeHelperClient(CommandResult(ok=True, data={"performed": True, "action": "click"}))
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "bad-row",
                "label": "Bad",
                "role": "AXRow",
                "bounds": {"x": 100, "y": 200, "width": 100, "height": 40},
                "center": {"x": 150, "y": 220},
                "actions": [],
                "engine": "ax_fallback",
                "ax_target": {"pid": "4242", "app_name": "Finder", "process_name": "Finder", "path": [{"role": "AXRow", "name": "Bad", "index": 0}]},
            }
        ],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, element_id="bad-row", dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "ax_target_process_identity_required"
    assert helper.calls == []


def test_desktop_click_browser_coordinate_post_to_pid_fails_closed_without_helper_dispatch(tmp_path: Path) -> None:
    helper = FakeHelperClient(CommandResult(ok=True, data={"performed": True, "action": "click"}))
    observer = CustomerMacObserver(
        runner=FakeRunner(frontmost_process_outputs(app_name="Google Chrome", process_name="Google Chrome")),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(x=10, y=20, dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "post_to_pid_browser_target_ambiguous"
    assert helper.calls == []


def test_desktop_click_snapshot_coordinates_on_browser_web_content_fails_closed(tmp_path: Path) -> None:
    snapshot_id = "snap-desktop-ffffffffffffffffffffffffffffffff"
    helper = FakeHelperClient(CommandResult(ok=True, data={"performed": True, "action": "click"}))
    observer = CustomerMacObserver(
        runner=FakeRunner(),
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="desktop",
        engine="ax_fallback",
        elements=[
            {
                "element_id": "web-area",
                "label": "Page",
                "role": "AXWebArea",
                "bounds": {"x": 0, "y": 0, "width": 400, "height": 400},
                "center": {"x": 200, "y": 200},
                "actions": [],
                "engine": "ax_fallback",
                "ax_target": {
                    "pid": 5151,
                    "app_name": "Google Chrome",
                    "process_name": "Google Chrome",
                    "path": [{"role": "AXWindow", "index": 0}, {"role": "AXWebArea", "index": 0}],
                },
            }
        ],
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, x=200, y=200, dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "ax_web_content_inert"
    assert helper.calls == []


def test_desktop_scroll_helper_error_fails_closed_without_python_fallback(tmp_path: Path) -> None:
    runner = FakeRunner({**frontmost_process_outputs(), (sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "action": "scroll"}), stderr="")})
    helper = FakeHelperClient(CommandResult(ok=False, data={"performed": False, "action": "scroll"}, errors=[{"code": "helper_unavailable", "message": "helper unavailable", "guidance": "restart helper"}]))
    observer = CustomerMacObserver(
        runner=runner,
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_scroll(direction="down", amount=600, dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "helper_unavailable"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "scroll", "target": FINDER_TARGET, "direction": "down", "amount": 600})
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_drag_helper_error_fails_closed_without_python_fallback(tmp_path: Path) -> None:
    runner = FakeRunner({**frontmost_process_outputs(), (sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "action": "drag"}), stderr="")})
    helper = FakeHelperClient(CommandResult(ok=False, data={"performed": False, "action": "drag"}, errors=[{"code": "helper_unavailable", "message": "helper unavailable", "guidance": "restart helper"}]))
    observer = CustomerMacObserver(
        runner=runner,
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_drag(from_x=1, from_y=2, to_x=3, to_y=4, dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "helper_unavailable"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "drag", "target": FINDER_TARGET, "from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4})
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_click_uses_env_configured_unix_helper_without_python_spawn(monkeypatch, tmp_path: Path) -> None:
    token = make_capability_token()
    token_file = tmp_path / "helper.token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    socket_path = short_socket_path()
    ready = threading.Event()
    calls: list[tuple[str, dict[str, object]]] = []

    def executor(command: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((command, payload))
        return {
            "ok": True,
            "data": {"performed": True, "action": "click", "clicked": True, "point": {"x": payload["x"], "y": payload["y"]}, "engine": "helper_post_to_pid"},
            "warnings": [],
            "errors": [],
        }

    thread = threading.Thread(
        target=run_helper_server,
        kwargs={
            "socket_path": socket_path,
            "token": token,
            "expected_uid": os.getuid(),
            "ready": ready,
            "max_requests": 1,
            "peer_uid_getter": lambda _sock: os.getuid(),
            "command_executor": executor,
        },
        daemon=True,
    )
    thread.start()
    assert ready.wait(timeout=2)
    monkeypatch.setenv("EVAOS_DESKTOP_BRIDGE_USE_HELPER", "1")
    monkeypatch.setenv("EVAOS_DESKTOP_BRIDGE_HELPER_SOCKET", str(socket_path))
    monkeypatch.setenv("EVAOS_DESKTOP_BRIDGE_HELPER_TOKEN_FILE", str(token_file))
    runner = FakeRunner(frontmost_process_outputs())
    observer = CustomerMacObserver(
        runner=runner,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(x=10, y=20, dry_run=False)

    thread.join(timeout=2)
    assert result.ok is True
    assert result.data["engine"] == "helper_post_to_pid"
    assert calls == [("mouse_action", {"action": "click", "target": FINDER_TARGET, "x": 10, "y": 20})]
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_type_dry_run_records_hash_without_typing(tmp_path: Path) -> None:
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_type(text="hello world", dry_run=True)

    assert result.ok is True
    assert result.data["would_type"] is True
    assert result.data["text_sha256"]
    assert_no_keystroke_commands(observer.runner.commands)


def test_desktop_type_blocks_sensitive_frontmost_even_in_full_access(tmp_path: Path) -> None:
    observer = CustomerMacObserver(
        runner=FakeRunner(
            {
                (
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ): RunnerResult(returncode=0, stdout="Messages\n", stderr=""),
            }
        ),
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    observer.control_start(mode="full-access", agent_label="Aurelius")

    result = observer.desktop_type(text="hello", dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "sensitive_app_blocked"
    assert result.data["frontmost_app"] == "Messages"
    assert_no_keystroke_commands(observer.runner.commands)
    assert not any(command and command[0] in {"open", "cliclick"} for command in observer.runner.commands)


def test_desktop_focus_app_blocks_sensitive_app_name_before_peekaboo_or_open(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=FakeRunner({("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr="")}), state_dir=tmp_path, platform_name="Darwin")
    observer.control_start(mode="full-access", agent_label="Aurelius")

    result = observer.desktop_focus_app(app_name="Mail", dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "sensitive_app_blocked"
    assert not any(command[:3] == ("/test/peekaboo", "app", "switch") for command in observer.runner.commands)
    assert not any(command[:2] == ("open", "-a") for command in observer.runner.commands)


def test_desktop_focus_workbench_alias_uses_canonical_path_not_app_lookup(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "evaOS.app"
    app.mkdir()
    monkeypatch.setattr(customer_mac, "WORKBENCH_CANONICAL_APP_PATH", app)
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("open", str(app)): RunnerResult(returncode=0, stdout="", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="EvaDesktop\n", stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin")
    observer.control_start(mode="full-access", agent_label="Aurelius")

    result = observer.desktop_focus_app(app_name="EvaDesktop", dry_run=False)

    assert result.ok is True
    assert result.data["frontmost"] is True
    assert result.data["engine"] == "macos_open_path"
    assert result.data["app_path"] == str(app)
    assert ("open", str(app)) in runner.commands
    assert not any(command[:3] == ("/test/peekaboo", "app", "switch") for command in runner.commands)
    assert not any(command[:2] == ("open", "-a") for command in runner.commands)

    dry_run = observer.desktop_focus_app(app_name="EvaDesktop.app", dry_run=True)
    assert dry_run.ok is True
    assert dry_run.data["app_path"] == str(app)


def test_app_focus_workbench_alias_verifies_process_name_without_stale_lookup(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "evaOS.app"
    app.mkdir()
    monkeypatch.setattr(customer_mac, "WORKBENCH_CANONICAL_APP_PATH", app)
    runner = FakeRunner(
        {
            ("open", str(app)): RunnerResult(returncode=0, stdout="", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="EvaDesktop\n", stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin")

    result = observer.app_focus(app_name="evaOS Workbench", dry_run=False)

    assert result.ok is True
    assert result.data["frontmost"] is True
    assert result.data["engine"] == "macos_open_path"
    assert ("open", str(app)) in runner.commands
    assert not any(command[:2] == ("open", "-a") for command in runner.commands)


def test_workbench_alias_missing_canonical_app_fails_without_open_a(monkeypatch, tmp_path: Path) -> None:
    missing_app = tmp_path / "missing-evaOS.app"
    monkeypatch.setattr(customer_mac, "WORKBENCH_CANONICAL_APP_PATH", missing_app)
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin")

    result = observer.app_focus(app_name="EvaDesktop", dry_run=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "workbench_canonical_app_missing"
    assert not any(command[:2] == ("open", "-a") for command in observer.runner.commands)


def test_desktop_type_prefers_peekaboo_paste_for_exact_text(monkeypatch, tmp_path: Path) -> None:
    peekaboo = tmp_path / "peekaboo"
    peekaboo.write_text("#!/bin/sh\n", encoding="utf-8")
    peekaboo.chmod(0o755)
    monkeypatch.setattr(customer_mac, "PEEKABOO_BIN_CANDIDATES", (str(peekaboo),))
    runner = FakeRunner(
        {
            (str(peekaboo), "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            (str(peekaboo), "paste", "--text", "Hello?", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_type(text="Hello?")

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert result.data["input_method"] == "paste"
    assert (str(peekaboo), "paste", "--text", "Hello?", "--json", "--no-remote") in runner.commands
    assert not any(command[:2] == (str(peekaboo), "type") for command in runner.commands)


def test_iphone_type_spotlight_prefers_targeted_peekaboo_type_for_layout_stable_text(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    peekaboo = tmp_path / "peekaboo"
    peekaboo.write_text("#!/bin/sh\n", encoding="utf-8")
    peekaboo.chmod(0o755)
    monkeypatch.setattr(customer_mac, "PEEKABOO_BIN_CANDIDATES", (str(peekaboo),))
    runner = FakeRunner(
        {
            (str(peekaboo), "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            (str(peekaboo), "type", "--text", "Calculator", "--app", "iPhone Mirroring", "--profile", "linear", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
            ("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            ("osascript", "-e", 'tell application "iPhone Mirroring" to activate'): RunnerResult(returncode=0, stdout="", stderr=""),
            ("osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'): RunnerResult(returncode=0, stdout="iPhone Mirroring\n", stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)
    monkeypatch.setattr(observer, "iphone_mirroring_status", lambda: CommandResult(ok=True, data={"installed": True}))
    monkeypatch.setattr(
        observer,
        "iphone_mirroring_focus",
        lambda dry_run=False: CommandResult(ok=True, data={"focused": True, "frontmost": True}),
    )
    monkeypatch.setattr(
        observer,
        "_iphone_keyboard_action",
        lambda action, key_code: CommandResult(ok=True, data={"performed": True, "action": action, "key_code": key_code}),
    )

    result = observer.iphone_mirroring_action(action="type_spotlight", text="Calculator", dry_run=False)

    assert result.ok is True
    assert result.data["action"] == "type_spotlight"
    assert result.data["text_preview"] == "Calculator"
    assert (str(peekaboo), "type", "--text", "Calculator", "--app", "iPhone Mirroring", "--profile", "linear", "--json", "--no-remote") in runner.commands
    assert ("osascript", "-e", 'tell application "System Events" to keystroke "Calculator"') not in runner.commands


def test_desktop_hotkey_accepts_multi_character_keys(tmp_path: Path) -> None:
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    expected = {
        "cmd+n": "cmd+n",
        "command shift 4": "cmd+shift+4",
        "escape": "esc",
        "cmd+space": "cmd+space",
    }

    for keys, normalized in expected.items():
        result = observer.desktop_hotkey(keys=keys, dry_run=True)
        assert result.ok is True
        assert result.data["keys"] == normalized
        assert result.data["would_press"] is True

    invalid = observer.desktop_hotkey(keys="cmd+🚀", dry_run=True)
    assert invalid.ok is False
    assert invalid.errors[0]["code"] == "desktop_hotkey_required"


def test_desktop_hotkey_uses_current_peekaboo_keys_shape(monkeypatch, tmp_path: Path) -> None:
    peekaboo = tmp_path / "peekaboo"
    peekaboo.write_text("#!/bin/sh\n", encoding="utf-8")
    peekaboo.chmod(0o755)
    monkeypatch.setattr(customer_mac, "PEEKABOO_BIN_CANDIDATES", (str(peekaboo),))
    runner = FakeRunner(
        {
            (str(peekaboo), "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            (str(peekaboo), "hotkey", "--keys", "cmd+l", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_hotkey(keys="cmd+l")

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert (str(peekaboo), "hotkey", "--keys", "cmd+l", "--json", "--no-remote") in runner.commands
    assert not any(command[:4] == (str(peekaboo), "hotkey", "cmd", "l") for command in runner.commands)


def test_desktop_scroll_uses_peekaboo_direction_flag(monkeypatch, tmp_path: Path) -> None:
    peekaboo = tmp_path / "peekaboo"
    peekaboo.write_text("#!/bin/sh\n", encoding="utf-8")
    peekaboo.chmod(0o755)
    monkeypatch.setattr(customer_mac, "PEEKABOO_BIN_CANDIDATES", (str(peekaboo),))
    runner = FakeRunner(
        {
            (str(peekaboo), "--version"): RunnerResult(returncode=0, stdout="peekaboo 3.2.2\n", stderr=""),
            (str(peekaboo), "scroll", "--direction", "down", "--amount", "3", "--json"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_scroll(direction="down", amount=3)

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert (str(peekaboo), "scroll", "--direction", "down", "--amount", "3", "--json") in runner.commands
    assert not any(command[:3] == (str(peekaboo), "scroll", "down") for command in runner.commands)


def test_desktop_click_uses_peekaboo_snapshot_element_before_coordinate_fallback(monkeypatch, tmp_path: Path) -> None:
    snapshot_id = "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots" / f"{snapshot_id}.json").write_text(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "target": "desktop",
                "engine": "peekaboo",
                "peekaboo_snapshot_id": "PEEKABOO-SNAPSHOT",
                "timestamp": "2999-01-01T00:00:00Z",
                "elements": [
                    {
                        "element_id": "B1",
                        "peekaboo_element_id": "B1",
                        "label": "Continue",
                        "center": {"x": 10, "y": 20},
                        "engine": "peekaboo",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("/test/peekaboo", "click", "--snapshot", "PEEKABOO-SNAPSHOT", "--on", "B1", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_click(snapshot_id=snapshot_id, element_id="B1")

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    snapshot_click = ("/test/peekaboo", "click", "--snapshot", "PEEKABOO-SNAPSHOT", "--on", "B1", "--json", "--no-remote")
    assert snapshot_click in runner.commands
    assert runner.timeouts[snapshot_click] == 5.0
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_click_uses_peekaboo_global_coordinates_before_post_to_pid(monkeypatch, tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("/test/peekaboo", "click", "--coords", "10,20", "--global-coords", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_click(x=10, y=20)

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert ("/test/peekaboo", "click", "--coords", "10,20", "--global-coords", "--json", "--no-remote") in runner.commands


def test_desktop_click_accepts_snapshot_coordinates_without_element(monkeypatch, tmp_path: Path) -> None:
    snapshot_id = "snap-desktop-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots" / f"{snapshot_id}.json").write_text(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "target": "desktop",
                "engine": "peekaboo",
                "timestamp": "2999-01-01T00:00:00Z",
                "coordinate_space": {"type": "global", "origin": {"x": 100, "y": 200}},
                "elements": [],
            }
        ),
        encoding="utf-8",
    )
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("/test/peekaboo", "click", "--coords", "110,220", "--global-coords", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_click(snapshot_id=snapshot_id, x=10, y=20)

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert result.data["point"] == {"x": 110, "y": 220}
    assert ("/test/peekaboo", "click", "--coords", "110,220", "--global-coords", "--json", "--no-remote") in runner.commands


def test_desktop_drag_uses_current_peekaboo_coordinate_shape(monkeypatch, tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            (
                "/test/peekaboo",
                "drag",
                "--from-coords",
                "10,20",
                "--to-coords",
                "30,40",
                "--profile",
                "human",
                "--json",
                "--no-remote",
            ): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_drag(from_x=10, from_y=20, to_x=30, to_y=40)

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert not any("--from" in command or "--to" in command for command in runner.commands)


def test_desktop_menu_and_window_use_peekaboo_subcommands(monkeypatch, tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("/test/peekaboo", "menu", "click", "--path", "File > New Tab", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
            ("/test/peekaboo", "window", "maximize", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    menu = observer.desktop_menu(menu_path="File > New Tab")
    window = observer.desktop_window(action="maximize")

    assert menu.ok is True
    assert window.ok is True
    assert menu.data["engine"] == "peekaboo"
    assert window.data["peekaboo_action"] == "maximize"


def test_iphone_see_uses_peekaboo_region_capture_when_see_hangs(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)

    class ImageWritingRunner(FakeRunner):
        def __call__(self, command: list[str], timeout: float = 5.0) -> RunnerResult:
            if command[:4] == ["/test/peekaboo", "image", "--mode", "area"]:
                Path(command[command.index("--path") + 1]).write_bytes(png_header(318, 701))
            return super().__call__(command, timeout)

    runner = ImageWritingRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="iPhone Mirroring\n", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to tell first application process whose frontmost is true to get name of front window',
            ): RunnerResult(returncode=0, stdout="iPhone Mirroring\n", stderr=""),
            ("/test/peekaboo", "window", "list", "--app", "iPhone Mirroring", "--json", "--no-remote"): RunnerResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "success": True,
                        "data": {
                            "windows": [
                                {
                                    "window_title": "iPhone Mirroring",
                                    "is_on_screen": True,
                                    "bounds": {"x": 100, "y": 200, "width": 318, "height": 701},
                                }
                            ]
                        },
                    }
                ),
                stderr="",
            ),
            ("/test/peekaboo", "image", "--mode", "area"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.iphone_see()

    assert result.ok is True
    assert result.data["capture_engine"] == "peekaboo_region"
    assert result.data["coordinate_space"]["origin"] == {"x": 100, "y": 200}
    assert result.data["coordinate_space"]["image_size"] == {"width": 318, "height": 701}
    assert result.data["screenshot"]["screenshot"]["width"] == 318
    snapshot = json.loads((tmp_path / "snapshots" / f"{result.data['snapshot_id']}.json").read_text(encoding="utf-8"))
    assert snapshot["target"] == "iphone_mirroring"
    assert snapshot["coordinate_space"]["origin"] == {"x": 100, "y": 200}


def test_iphone_snapshot_coordinates_translate_to_global_point(tmp_path: Path) -> None:
    observer = CustomerMacObserver(runner=FakeRunner(), state_dir=tmp_path, platform_name="Darwin")
    snapshot_id = "snap-iphone-mirroring-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="iphone_mirroring",
        elements=[],
        engine="peekaboo_region",
        coordinate_space={
            "type": "window_region",
            "origin": {"x": 100, "y": 200},
            "size": {"width": 318, "height": 701},
            "image_size": {"width": 636, "height": 1402},
        },
    )

    result = observer._resolve_snapshot_coordinates(snapshot_id=snapshot_id, x=20, y=40, expected_target="iphone_mirroring")

    assert result.ok is True
    assert result.data["point"] == {"x": 110, "y": 220}
    assert result.data["logical_point"] == {"x": 10, "y": 20}


def test_iphone_tap_translates_snapshot_coordinates_before_desktop_click(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("/test/peekaboo", "click", "--coords", "110,220", "--global-coords", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)
    monkeypatch.setattr(observer, "iphone_mirroring_focus", lambda dry_run=False: CommandResult(ok=True, data={"focused": True}))
    snapshot_id = "snap-iphone-mirroring-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    observer._write_snapshot_index(
        snapshot_id=snapshot_id,
        target="iphone_mirroring",
        elements=[],
        engine="peekaboo_region",
        coordinate_space={
            "type": "window_region",
            "origin": {"x": 100, "y": 200},
            "size": {"width": 318, "height": 701},
            "image_size": {"width": 636, "height": 1402},
        },
    )

    result = observer.iphone_tap(snapshot_id=snapshot_id, x=20, y=40)

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert ("/test/peekaboo", "click", "--coords", "110,220", "--global-coords", "--json", "--no-remote") in runner.commands


def test_stale_snapshot_id_is_rejected_before_click(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    runner = FakeRunner({("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr="")})
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)
    snapshot_id = "snap-desktop-cccccccccccccccccccccccccccccccc"
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / f"{snapshot_id}.json").write_text(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "target": "desktop",
                "engine": "peekaboo",
                "peekaboo_snapshot_id": "PEEKABOO-SNAPSHOT",
                "timestamp": "2000-01-01T00:00:00Z",
                "elements": [
                    {
                        "element_id": "B1",
                        "peekaboo_element_id": "B1",
                        "label": "Old button",
                        "bounds": {"x": 10, "y": 20, "width": 30, "height": 40},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = observer.desktop_click(snapshot_id=snapshot_id, element_id="B1")

    assert result.ok is False
    assert result.errors[0]["code"] == "snapshot_stale"
    assert runner.commands == []


def test_iphone_keyboard_action_uses_current_peekaboo_hotkey_shape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("/test/peekaboo", "hotkey", "--keys", "cmd+1", "--json", "--no-remote"): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer._iphone_keyboard_action("home", "18")

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert ("/test/peekaboo", "hotkey", "--keys", "cmd+1", "--json", "--no-remote") in runner.commands


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
            ("osascript", "-e", 'tell application "iPhone Mirroring" to activate'): RunnerResult(returncode=0, stdout="", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="iPhone Mirroring\n", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to tell process "iPhone Mirroring" to get {position, size} of front window',
            ): RunnerResult(returncode=0, stdout="100, 200, 300, 700\n", stderr=""),
            ("open", "-a", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="", stderr=""),
            ("/bin/ps", "-p", "123", "-o", "comm="): RunnerResult(returncode=0, stdout="/System/Applications/iPhone Mirroring.app/Contents/MacOS/iPhone Mirroring\n", stderr=""),
            (sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "action": "drag"}), stderr=""),
        }
    )
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "drag", "dragged": True, "from": {"x": 346, "y": 550}, "to": {"x": 154, "y": 550}, "engine": "helper_post_to_pid"},
            provenance={"source": "computer_use_helper"},
        )
    )
    observer = CustomerMacObserver(
        runner=runner,
        helper_client=helper,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.iphone_mirroring_action(action="swipe_left", dry_run=False)

    assert result.ok is True
    assert result.data["gesture"] == "drag"
    assert result.data["from"] == {"x": 346, "y": 550}
    assert result.data["to"] == {"x": 154, "y": 550}
    assert helper.calls[0][0] == "mouse_action"
    assert helper.calls[0][1]["target"] == {"pid": 123, "app_name": "iPhone Mirroring", "process_name": "iPhone Mirroring", "path": []}
    assert_no_keystroke_commands(runner.commands)


def test_iphone_live_swipe_prefers_peekaboo_swipe(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            ("osascript", "-e", 'tell application "iPhone Mirroring" to activate'): RunnerResult(returncode=0, stdout="", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="iPhone Mirroring\n", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to tell process "iPhone Mirroring" to get {position, size} of front window',
            ): RunnerResult(returncode=0, stdout="100, 200, 300, 700\n", stderr=""),
            (
                "/test/peekaboo",
                "swipe",
                "--from-coords",
                "346,550",
                "--to-coords",
                "154,550",
                "--duration",
                "700",
                "--profile",
                "human",
                "--json",
                "--no-remote",
            ): RunnerResult(returncode=0, stdout='{"success":true}', stderr=""),
        }
    )
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.iphone_mirroring_action(action="swipe_left", dry_run=False)

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert result.data["gesture"] == "swipe"
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_iphone_keyboard_action_prefers_peekaboo_hotkey(monkeypatch, tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            ("/test/peekaboo", "hotkey", "--keys", "cmd+1", "--json", "--no-remote"): RunnerResult(returncode=0, stdout="", stderr=""),
        }
    )
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer._iphone_keyboard_action("home", "18")

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert ("/test/peekaboo", "hotkey", "--keys", "cmd+1", "--json", "--no-remote") in runner.commands
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


def test_iphone_open_app_live_marks_visual_postcondition_unverified(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    runner = FakeRunner(
        {
            ("osascript", "-e", 'tell application "System Events" to key code 36'): RunnerResult(
                returncode=0,
                stdout="",
                stderr="",
            )
        }
    )
    observer = CustomerMacObserver(
        runner=runner,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )
    iphone_actions: list[str] = []
    monkeypatch.setattr(observer, "iphone_mirroring_status", lambda: CommandResult(ok=True, data={"installed": True}))
    monkeypatch.setattr(
        observer,
        "iphone_mirroring_focus",
        lambda dry_run=False: CommandResult(ok=True, data={"focused": True, "frontmost": True}),
    )
    monkeypatch.setattr(
        observer,
        "_iphone_keyboard_action",
        lambda action, key_code: iphone_actions.append(action) or CommandResult(ok=True, data={"performed": True, "action": action, "key_code": key_code}),
    )
    monkeypatch.setattr(
        observer,
        "_keystroke_text",
        lambda text: CommandResult(ok=True, data={"typed": True, "text_preview": text}),
    )

    result = observer.iphone_mirroring_action(action="open_app", app_name="Calculator", dry_run=False)

    assert result.ok is True
    assert result.data["performed"] is True
    assert result.data["action"] == "open_app"
    assert result.data["app_name"] == "Calculator"
    assert result.data["verification_required"] is True
    assert result.data["postcondition"] == "target_app_visible"
    assert result.data["postcondition_verified"] is False
    assert iphone_actions == ["home", "spotlight"]
    assert any("settled visual" in warning.lower() for warning in result.warnings)


def test_safe_ax_node_exports_redacted_bounds_for_visual_grounding(tmp_path: Path) -> None:
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

    assert node["bounds"] == {"x": 10, "y": 20, "width": 30, "height": 40}
    assert node["role"] == "AXButton"
    assert node["actions"] == ["AXPress"]


def test_desktop_see_returns_snapshot_artifact_and_clickable_elements(monkeypatch, tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (640).to_bytes(4, "big") + (480).to_bytes(4, "big") + b"payload"
    screenshot = tmp_path / "screen.png"
    screenshot.write_bytes(png)
    runner = FakeRunner(
        {
            (
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ): RunnerResult(returncode=0, stdout="Safari\n", stderr=""),
            (
                "osascript",
                "-e",
                'tell application "System Events" to tell first application process whose frontmost is true to get name of front window',
            ): RunnerResult(returncode=0, stdout="Example\n", stderr=""),
            ("pgrep", "-x", "Safari"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            (sys.executable, "-c"): RunnerResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "nodes": [
                            {"role": "AXButton", "name": "Continue", "depth": 0, "window_index": 0, "bounds": {"x": 10, "y": 20, "width": 100, "height": 40}, "actions": ["AXPress"]}
                        ],
                        "truncated": False,
                    }
                ),
                stderr="",
            ),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)
    monkeypatch.setattr(observer, "_capture_screenshot", lambda warnings: screenshot)

    result = observer.desktop_see()
    click = observer.desktop_click(snapshot_id=result.data["snapshot_id"], element_id=result.data["elements"][0]["element_id"], dry_run=True)

    assert result.ok is True
    assert result.data["snapshot_id"].startswith("snap-desktop-")
    assert result.data["screenshot"]["screenshot"]["width"] == 640
    assert result.data["screenshot"]["screenshot"]["height"] == 480
    assert result.data["screenshot"]["screenshot"]["bytes_base64"]
    assert result.data["elements"][0]["label"] == "Continue"
    assert click.data["point"] == {"x": 60, "y": 40}


def test_desktop_see_prefers_peekaboo_json_without_python_tcc_fallback(monkeypatch, tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (800).to_bytes(4, "big") + (600).to_bytes(4, "big") + b"payload"
    commands: list[tuple[str, ...]] = []

    def runner(command: list[str], timeout: float = 5.0) -> RunnerResult:
        key = tuple(command)
        commands.append(key)
        if key == ("/test/peekaboo", "--version"):
            return RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr="")
        if key[:2] == ("/test/peekaboo", "see"):
            screenshot_path = Path(command[command.index("--path") + 1])
            screenshot_path.write_bytes(png)
            return RunnerResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "success": True,
                        "data": {
                            "snapshot_id": "PEEKABOO-SNAPSHOT",
                            "application_name": "Safari",
                            "window_title": "Example",
                            "screenshot_raw": str(screenshot_path),
                            "capture_mode": "frontmost",
                            "element_count": 1,
                            "interactable_count": 1,
                            "ui_elements": [
                                {
                                    "id": "elem_123",
                                    "role": "button",
                                    "label": "Continue",
                                    "bounds": {"x": 10, "y": 20, "width": 100, "height": 40},
                                    "is_actionable": True,
                                }
                            ],
                        },
                    }
                ),
                stderr="",
            )
        if key == (
            "osascript",
            "-e",
            'tell application "System Events" to get name of first application process whose frontmost is true',
        ):
            return RunnerResult(returncode=0, stdout="Safari\n", stderr="")
        return RunnerResult(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin")

    result = observer.desktop_see(max_nodes=10)
    click = observer.desktop_click(snapshot_id=result.data["snapshot_id"], element_id="elem_123", dry_run=True)

    assert result.ok is True
    assert result.data["engine"] == "peekaboo"
    assert result.data["snapshot_id"].startswith("snap-desktop-")
    assert result.data["screenshot"]["screenshot"]["width"] == 800
    assert result.data["elements"][0]["element_id"] == "elem_123"
    assert click.data["point"] == {"x": 60, "y": 40}
    see_command = next(command for command in commands if command[:2] == ("/test/peekaboo", "see"))
    assert "--mode" in see_command
    assert see_command[see_command.index("--mode") + 1] == "frontmost"
    assert "--capture-engine" in see_command
    assert see_command[see_command.index("--capture-engine") + 1] == "classic"
    assert "--no-remote" in see_command
    assert not any(command and command[0] == sys.executable for command in commands)
    assert not any(command and command[0] == "screencapture" for command in commands)


def test_desktop_see_blocks_sensitive_frontmost_before_peekaboo_capture(monkeypatch, tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (800).to_bytes(4, "big") + (600).to_bytes(4, "big") + b"payload"
    commands: list[tuple[str, ...]] = []

    def runner(command: list[str], timeout: float = 5.0) -> RunnerResult:
        key = tuple(command)
        commands.append(key)
        if key == ("/test/peekaboo", "--version"):
            return RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr="")
        if key[:2] == ("/test/peekaboo", "see"):
            screenshot_path = Path(command[command.index("--path") + 1])
            screenshot_path.write_bytes(png)
            return RunnerResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "success": True,
                        "data": {
                            "snapshot_id": "PEEKABOO-SNAPSHOT",
                            "application_name": "Messages",
                            "window_title": "Private conversation",
                            "screenshot_raw": str(screenshot_path),
                            "ui_elements": [],
                        },
                    }
                ),
                stderr="",
            )
        if key == (
            "osascript",
            "-e",
            'tell application "System Events" to get name of first application process whose frontmost is true',
        ):
            return RunnerResult(returncode=0, stdout="Messages\n", stderr="")
        return RunnerResult(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin")

    result = observer.desktop_see()

    assert result.ok is False
    assert result.errors[0]["code"] == "sensitive_app_blocked"
    assert result.data["frontmost_app"] == "Messages"
    assert not any(command[:2] == ("/test/peekaboo", "see") for command in commands)
    assert not any(command and command[0] == sys.executable for command in commands)
    assert not any(command and command[0] == "screencapture" for command in commands)


def test_desktop_see_blocks_sensitive_frontmost_before_fallback_capture(monkeypatch, tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []

    def runner(command: list[str], timeout: float = 5.0) -> RunnerResult:
        key = tuple(command)
        commands.append(key)
        if key == (
            "osascript",
            "-e",
            'tell application "System Events" to get name of first application process whose frontmost is true',
        ):
            return RunnerResult(returncode=0, stdout="Mail\n", stderr="")
        return RunnerResult(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.desktop_see()

    assert result.ok is False
    assert result.errors[0]["code"] == "sensitive_app_blocked"
    assert result.data["frontmost_app"] == "Mail"
    assert not any(command and command[0] == "screencapture" for command in commands)
    assert not any(command and command[0] == sys.executable for command in commands)


def test_snapshot_and_ax_tree_block_sensitive_frontmost_even_in_full_access(monkeypatch, tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []

    def runner(command: list[str], timeout: float = 5.0) -> RunnerResult:
        key = tuple(command)
        commands.append(key)
        if key == (
            "osascript",
            "-e",
            'tell application "System Events" to get name of first application process whose frontmost is true',
        ):
            return RunnerResult(returncode=0, stdout="Messages\n", stderr="")
        return RunnerResult(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: None)
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)
    observer.control_start(mode="full-access", agent_label="Aurelius")

    snapshot = observer.snapshot(max_chars=4000)
    ax_tree = observer.ax_tree(max_nodes=200)

    assert snapshot.ok is False
    assert snapshot.errors[0]["code"] == "sensitive_app_blocked"
    assert ax_tree.ok is False
    assert ax_tree.errors[0]["code"] == "sensitive_app_blocked"
    assert not any(command and command[0] == "screencapture" for command in commands)
    assert not any(command and command[0] == sys.executable for command in commands)


def test_status_prefers_peekaboo_bridge_permissions_over_python_probe(monkeypatch, tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            ("/test/peekaboo", "--version"): RunnerResult(returncode=0, stdout="Peekaboo 3.2.2\n", stderr=""),
            (
                "/test/peekaboo",
                "permissions",
                "status",
                "--json",
                "--no-remote",
            ): RunnerResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "success": True,
                        "data": {
                            "permissions": [
                                {"name": "Screen Recording", "isGranted": True},
                                {"name": "Accessibility", "isGranted": True},
                            ]
                        },
                    }
                ),
                stderr="",
            ),
        }
    )
    monkeypatch.setattr(customer_mac.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    observer = CustomerMacObserver(
        runner=runner,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: False,
        screen_recording_checker=lambda: False,
    )

    result = observer.status()

    assert result.data["permissions"]["accessibility"]["status"] == "granted"
    assert result.data["permissions"]["screen_recording"]["status"] == "granted"
    assert ("/test/peekaboo", "permissions", "status", "--json", "--no-remote") in runner.commands


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
