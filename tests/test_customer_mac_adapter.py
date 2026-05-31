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


def test_desktop_click_routes_quartz_fallback_through_helper_without_python_spawn(tmp_path: Path) -> None:
    runner = FakeRunner()
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "click", "clicked": True, "point": {"x": 10, "y": 20}, "engine": "helper_quartz"},
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
    assert result.data["engine"] == "helper_quartz"
    assert result.provenance["source"] == "computer_use_helper"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "click", "x": 10, "y": 20})
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_click_helper_error_fails_closed_without_python_fallback(tmp_path: Path) -> None:
    runner = FakeRunner({(sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "action": "click"}), stderr="")})
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
    assert helper.calls[0][:2] == ("mouse_action", {"action": "click", "x": 10, "y": 20})
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_scroll_routes_quartz_fallback_through_helper_without_python_spawn(tmp_path: Path) -> None:
    runner = FakeRunner()
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "scroll", "scrolled": True, "direction": "down", "amount": 600, "engine": "helper_quartz"},
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
    assert result.data["engine"] == "helper_quartz"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "scroll", "direction": "down", "amount": 600})
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_drag_routes_quartz_fallback_through_helper_without_python_spawn(tmp_path: Path) -> None:
    runner = FakeRunner()
    helper = FakeHelperClient(
        CommandResult(
            ok=True,
            data={"performed": True, "action": "drag", "dragged": True, "from": {"x": 1, "y": 2}, "to": {"x": 3, "y": 4}, "engine": "helper_quartz"},
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
    assert result.data["engine"] == "helper_quartz"
    assert helper.calls[0][:2] == ("mouse_action", {"action": "drag", "from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4})
    assert helper.calls[0][2] and helper.calls[0][2].startswith("audit-helper-")
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_scroll_helper_error_fails_closed_without_python_fallback(tmp_path: Path) -> None:
    runner = FakeRunner({(sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "action": "scroll"}), stderr="")})
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
    assert helper.calls[0][:2] == ("mouse_action", {"action": "scroll", "direction": "down", "amount": 600})
    assert not any(command and command[0] == sys.executable for command in runner.commands)


def test_desktop_drag_helper_error_fails_closed_without_python_fallback(tmp_path: Path) -> None:
    runner = FakeRunner({(sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "action": "drag"}), stderr="")})
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
    assert helper.calls[0][:2] == ("mouse_action", {"action": "drag", "from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4})
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
            "data": {"performed": True, "action": "click", "clicked": True, "point": {"x": payload["x"], "y": payload["y"]}, "engine": "helper_quartz"},
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
    runner = FakeRunner()
    observer = CustomerMacObserver(
        runner=runner,
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
    )

    result = observer.desktop_click(x=10, y=20, dry_run=False)

    thread.join(timeout=2)
    assert result.ok is True
    assert result.data["engine"] == "helper_quartz"
    assert calls == [("mouse_action", {"action": "click", "x": 10, "y": 20})]
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


def test_iphone_type_prefers_system_events_for_exact_mirrored_text(monkeypatch, tmp_path: Path) -> None:
    installed_mirroring(monkeypatch, tmp_path)
    runner = FakeRunner(
        {
            ("pgrep", "-x", "iPhone Mirroring"): RunnerResult(returncode=0, stdout="123\n", stderr=""),
            ("osascript", "-e", 'tell application "iPhone Mirroring" to activate'): RunnerResult(returncode=0, stdout="", stderr=""),
            ("osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'): RunnerResult(returncode=0, stdout="iPhone Mirroring\n", stderr=""),
            ("osascript", "-e", 'tell application "System Events" to keystroke "Hello?"'): RunnerResult(returncode=0, stdout="", stderr=""),
        }
    )
    observer = CustomerMacObserver(runner=runner, state_dir=tmp_path, platform_name="Darwin", accessibility_checker=lambda: True)

    result = observer.iphone_type(text="Hello?")

    assert result.ok is True
    assert result.data["engine"] == "system_events"
    assert result.provenance == {"source": "system_events", "customer_control": True, "reason": "iphone_mirroring_exact_text"}
    assert ("osascript", "-e", 'tell application "System Events" to keystroke "Hello?"') in runner.commands


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


def test_desktop_click_uses_peekaboo_global_coordinates_before_quartz(monkeypatch, tmp_path: Path) -> None:
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
            (sys.executable, "-c"): RunnerResult(returncode=0, stdout=json.dumps({"ok": True, "action": "drag"}), stderr=""),
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
    assert result.data["gesture"] == "drag"
    assert result.data["from"] == {"x": 346, "y": 550}
    assert result.data["to"] == {"x": 154, "y": 550}
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
