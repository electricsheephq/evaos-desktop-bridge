from __future__ import annotations

import json
import os
import socket
import threading
import uuid
from pathlib import Path

import pytest

from evaos_desktop_bridge.helper_ipc import (
    AxActionExecutor,
    HELPER_IPC_ALLOWED_COMMANDS,
    HELPER_IPC_MAX_BYTES,
    HELPER_IPC_SCHEMA_VERSION,
    HelperIpcError,
    QuartzMouseActionExecutor,
    UnixSocketHelperClient,
    build_helper_request,
    decode_frame,
    default_helper_socket_path,
    encode_frame,
    handle_helper_request,
    helper_permission_preflight,
    helper_permission_preflight_errors,
    make_capability_token,
    read_helper_token,
    run_helper_server,
    _send_frame_best_effort,
)


def short_socket_path() -> Path:
    return Path("/tmp") / f"evaos-helper-{uuid.uuid4().hex}.sock"


def read_raw_frame(sock: socket.socket) -> dict[str, object]:
    prefix = sock.recv(4)
    assert len(prefix) == 4
    length = int.from_bytes(prefix, "big")
    chunks: list[bytes] = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        assert chunk
        chunks.append(chunk)
        remaining -= len(chunk)
    return decode_frame(prefix + b"".join(chunks))


def test_helper_ipc_ping_accepts_authorized_request_without_echoing_token() -> None:
    token = make_capability_token()
    request = build_helper_request(
        command="ping",
        token=token,
        request_id="req-1",
        audit_id="audit-safe",
        payload={"client": "bridge"},
    )

    response = handle_helper_request(request, expected_token=token, expected_uid=501, peer_uid=501)

    assert response["ok"] is True
    assert response["schema_version"] == HELPER_IPC_SCHEMA_VERSION
    assert response["request_id"] == "req-1"
    assert response["data"]["command"] == "ping"
    assert response["data"]["helper_mode"] == "contract_only"
    assert response["data"]["actuation_enabled"] is False
    serialized = json.dumps(response)
    assert serialized
    assert token not in serialized


def test_helper_ipc_contract_exposes_health_mouse_and_semantic_ax_actions_only() -> None:
    assert HELPER_IPC_ALLOWED_COMMANDS == frozenset({"ping", "mouse_action", "ax_action"})


def test_default_helper_socket_path_stays_under_macos_unix_socket_limit() -> None:
    assert str(default_helper_socket_path()).startswith("/tmp/")
    assert len(str(default_helper_socket_path())) < 104


def test_helper_ipc_mouse_action_dispatches_authorized_executor_without_echoing_token() -> None:
    token = make_capability_token()
    calls: list[tuple[str, dict[str, object]]] = []

    def executor(command: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((command, payload))
        return {
            "ok": True,
            "data": {
                "performed": True,
                "action": payload["action"],
                "point": {"x": payload["x"], "y": payload["y"]},
                "engine": "helper_post_to_pid",
            },
            "warnings": ["warm helper path"],
            "errors": [],
        }

    request = build_helper_request(
        command="mouse_action",
        token=token,
        request_id="req-mouse",
        audit_id="audit-mouse",
        payload={"action": "click", "x": 10, "y": 20},
    )

    response = handle_helper_request(
        request,
        expected_token=token,
        expected_uid=501,
        peer_uid=501,
        command_executor=executor,
    )

    assert response["ok"] is True
    assert response["request_id"] == "req-mouse"
    assert response["data"]["performed"] is True
    assert response["data"]["action"] == "click"
    assert response["data"]["engine"] == "helper_post_to_pid"
    assert response["warnings"] == ["warm helper path"]
    assert calls == [("mouse_action", {"action": "click", "x": 10, "y": 20})]
    assert token not in json.dumps(response)


def test_helper_ipc_ax_action_dispatches_authorized_executor_without_echoing_token() -> None:
    token = make_capability_token()
    calls: list[tuple[str, dict[str, object]]] = []
    target = {
        "pid": 1234,
        "process_name": "TestApp",
        "path": [
            {"role": "AXWindow", "index": 0},
            {"role": "AXButton", "name": "OK", "identifier": "ok-button", "index": 2},
        ],
    }

    def executor(command: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((command, payload))
        return {
            "ok": True,
            "data": {
                "performed": True,
                "action": payload["action"],
                "target": payload["target"],
                "engine": "helper_ax",
            },
            "warnings": [],
            "errors": [],
        }

    request = build_helper_request(
        command="ax_action",
        token=token,
        request_id="req-ax",
        audit_id="audit-ax",
        payload={"action": "press", "target": target},
    )

    response = handle_helper_request(
        request,
        expected_token=token,
        expected_uid=501,
        peer_uid=501,
        command_executor=executor,
    )

    assert response["ok"] is True
    assert response["request_id"] == "req-ax"
    assert response["data"]["performed"] is True
    assert response["data"]["action"] == "press"
    assert response["data"]["engine"] == "helper_ax"
    assert calls == [("ax_action", {"action": "press", "target": target})]
    assert token not in json.dumps(response)


def test_helper_ipc_mouse_action_requires_audit_id() -> None:
    token = make_capability_token()
    request = build_helper_request(
        command="mouse_action",
        token=token,
        request_id="req-mouse",
        payload={"action": "click", "x": 10, "y": 20},
    )

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(
            request,
            expected_token=token,
            expected_uid=501,
            peer_uid=501,
            command_executor=lambda _command, _payload: {"ok": True, "data": {}, "warnings": [], "errors": []},
        )

    assert exc.value.code == "helper_ipc_audit_required"


def test_helper_ipc_ax_action_requires_audit_id() -> None:
    token = make_capability_token()
    request = build_helper_request(
        command="ax_action",
        token=token,
        request_id="req-ax",
        payload={"action": "press", "target": {"pid": 1234, "process_name": "TestApp", "path": [{"role": "AXButton", "index": 0}]}},
    )

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(
            request,
            expected_token=token,
            expected_uid=501,
            peer_uid=501,
            command_executor=lambda _command, _payload: {"ok": True, "data": {}, "warnings": [], "errors": []},
        )

    assert exc.value.code == "helper_ipc_audit_required"


class FakeQuartzPostToPid:
    kCGEventSourceStateCombinedSessionState = 1
    kCGEventMouseMoved = 2
    kCGEventLeftMouseDown = 3
    kCGEventLeftMouseUp = 4
    kCGEventLeftMouseDragged = 5
    kCGScrollEventUnitPixel = 6
    kCGMouseButtonLeft = 7

    def __init__(self) -> None:
        self.posted_to_pid: list[tuple[int, dict[str, object]]] = []

    def CGEventSourceCreate(self, state: int) -> dict[str, int]:
        return {"state": state}

    def CGEventCreateMouseEvent(self, _source: object, kind: int, point: tuple[int, int], button: int) -> dict[str, object]:
        return {"kind": kind, "point": point, "button": button}

    def CGEventCreateScrollWheelEvent(self, _source: object, unit: int, wheels: int, dy: int, dx: int) -> dict[str, object]:
        return {"unit": unit, "wheels": wheels, "dy": dy, "dx": dx}

    def CGEventPostToPid(self, pid: int, event: dict[str, object]) -> None:
        self.posted_to_pid.append((pid, event))


def test_quartz_mouse_action_posts_click_to_target_pid_without_global_hid(monkeypatch: pytest.MonkeyPatch) -> None:
    quartz = FakeQuartzPostToPid()
    executor = QuartzMouseActionExecutor()
    executor._quartz = quartz
    monkeypatch.setattr(QuartzMouseActionExecutor, "_process_name_for_pid", staticmethod(lambda _pid: "Finder"))

    response = executor(
        "mouse_action",
        {
            "action": "click",
            "x": 10,
            "y": 20,
            "target": {"pid": 123, "process_name": "Finder", "app_name": "Finder"},
        },
    )

    assert response["ok"] is True
    assert response["data"]["engine"] == "helper_post_to_pid"
    assert response["data"]["target"]["pid"] == 123
    assert [event["kind"] for _pid, event in quartz.posted_to_pid] == [
        quartz.kCGEventMouseMoved,
        quartz.kCGEventLeftMouseDown,
        quartz.kCGEventLeftMouseUp,
    ]
    assert {pid for pid, _event in quartz.posted_to_pid} == {123}


def test_quartz_mouse_action_requires_pid_target_identity() -> None:
    executor = QuartzMouseActionExecutor()

    with pytest.raises(HelperIpcError) as exc:
        executor("mouse_action", {"action": "click", "x": 10, "y": 20})

    assert exc.value.code == "helper_ipc_bad_payload"


def test_source_retired_global_hid_event_tap() -> None:
    needle = "kCG" + "HIDEventTap"
    root = Path("src/evaos_desktop_bridge")
    offenders = [path for path in root.rglob("*.py") if needle in path.read_text(encoding="utf-8")]

    assert offenders == []


def test_ax_action_executor_blocks_non_text_set_value(monkeypatch: pytest.MonkeyPatch) -> None:
    app = {"role": "AXApplication"}
    window = {"role": "AXWindow", "children": []}
    button = {"role": "AXButton", "name": "OK", "children": []}
    app["windows"] = [window]
    window["children"] = [button]

    class FakeApplicationServices:
        def AXUIElementCreateApplication(self, pid: int) -> dict[str, object]:
            assert pid == 1234
            return app

        def AXUIElementCopyAttributeValue(self, element: dict[str, object], attr: str, out: object) -> tuple[int, object | None]:
            if attr == "AXWindows":
                return 0, element.get("windows")
            if attr == "AXChildren":
                return 0, element.get("children")
            if attr == "AXRole":
                return 0, element.get("role")
            if attr == "AXTitle":
                return 0, element.get("name")
            if attr in {"AXDescription", "AXValue", "AXIdentifier"}:
                return 0, None
            return 1, None

        def AXUIElementSetAttributeValue(self, element: dict[str, object], attr: str, value: str) -> int:
            raise AssertionError("non-text roles must not reach AXUIElementSetAttributeValue")

    executor = AxActionExecutor()
    executor._as = FakeApplicationServices()
    monkeypatch.setattr(executor, "_process_name_for_pid", lambda pid: "TestApp")

    response = executor(
        "ax_action",
        {
            "action": "set_value",
            "value": "hello",
            "target": {
                "pid": 1234,
                "process_name": "TestApp",
                "path": [
                    {"role": "AXWindow", "index": 0},
                    {"role": "AXButton", "name": "OK", "index": 0},
                ],
            },
        },
    )

    assert response["ok"] is False
    assert response["errors"][0]["code"] == "helper_ax_non_text_field_blocked"


def test_ax_action_executor_blocks_process_identity_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = AxActionExecutor()
    monkeypatch.setattr(executor, "_process_name_for_pid", lambda pid: "OtherApp")

    response = executor._target_identity_error("press", {"pid": 1234, "process_name": "Safari"})

    assert response is not None
    assert response["errors"][0]["code"] == "helper_ax_target_process_mismatch"


def test_helper_ipc_ax_action_requires_process_identity() -> None:
    token = make_capability_token()
    request = build_helper_request(
        command="ax_action",
        token=token,
        request_id="req-ax",
        audit_id="audit-ax",
        payload={"action": "press", "target": {"pid": 1234, "path": [{"role": "AXButton", "index": 0}]}},
    )

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(
            request,
            expected_token=token,
            expected_uid=501,
            peer_uid=501,
            command_executor=AxActionExecutor(),
        )

    assert exc.value.code == "helper_ipc_bad_payload"


def test_helper_permission_preflight_reports_workbench_identity_and_grants() -> None:
    preflight = helper_permission_preflight(
        env={
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID": "com.electricsheephq.EvaDesktop",
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH": "/Applications/evaOS.app",
            "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1",
        },
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
        parent_process_path="/Applications/evaOS.app/Contents/MacOS/EvaDesktop",
    )

    assert preflight["ok"] is True
    assert preflight["enforced"] is True
    assert preflight["identity"]["status"] == "workbench_signed_app"
    assert preflight["identity"]["responsible_bundle_id"] == "com.electricsheephq.EvaDesktop"
    assert preflight["identity"]["parent_status"] == "matched_responsible_app"
    assert preflight["permissions"]["accessibility"]["status"] == "granted"
    assert preflight["permissions"]["screen_recording"]["status"] == "granted"
    assert helper_permission_preflight_errors(preflight) == []


def test_helper_permission_preflight_accepts_stable_workbench_identity() -> None:
    preflight = helper_permission_preflight(
        env={
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID": "com.evaos.workbench",
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH": "/Applications/evaOS Workbench.app",
            "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1",
        },
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
        parent_process_path="/Applications/evaOS Workbench.app/Contents/MacOS/evaOS Workbench",
    )

    assert preflight["ok"] is True
    assert preflight["identity"]["status"] == "workbench_signed_app"
    assert preflight["identity"]["responsible_bundle_id"] == "com.evaos.workbench"
    assert "com.evaos.workbench" in preflight["identity"]["expected_bundle_ids"]
    assert "com.evaos.workbench.beta" not in preflight["identity"]["expected_bundle_ids"]
    assert "expected_bundle_id" not in preflight["identity"]
    assert helper_permission_preflight_errors(preflight) == []


def test_helper_permission_preflight_rejects_beta_workbench_identity() -> None:
    preflight = helper_permission_preflight(
        env={
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID": "com.evaos.workbench.beta",
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH": "/Applications/evaOS Workbench Beta.app",
            "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1",
        },
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
        parent_process_path="/Applications/evaOS Workbench Beta.app/Contents/MacOS/evaOS Workbench Beta",
    )

    assert preflight["ok"] is False
    assert preflight["identity"]["status"] == "mismatch"
    assert "com.evaos.workbench.beta" not in preflight["identity"]["expected_bundle_ids"]
    assert [error["code"] for error in helper_permission_preflight_errors(preflight)] == ["helper_identity_unverified"]


def test_helper_permission_preflight_fails_closed_for_missing_grants() -> None:
    preflight = helper_permission_preflight(
        env={
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID": "com.electricsheephq.EvaDesktop",
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH": "/Applications/evaOS.app",
            "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1",
        },
        platform_name="Darwin",
        accessibility_checker=lambda: False,
        screen_recording_checker=lambda: True,
        parent_process_path="/Applications/evaOS.app/Contents/MacOS/EvaDesktop",
    )

    errors = helper_permission_preflight_errors(preflight)

    assert preflight["ok"] is False
    assert errors[0]["code"] == "permission_missing"
    assert errors[0]["permission"] == "accessibility"
    assert "Privacy_Accessibility" in errors[0]["guidance"]


def test_helper_permission_preflight_fails_closed_for_unknown_grants() -> None:
    preflight = helper_permission_preflight(
        env={
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID": "com.electricsheephq.EvaDesktop",
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH": "/Applications/evaOS.app",
            "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1",
        },
        platform_name="Darwin",
        accessibility_checker=lambda: None,
        screen_recording_checker=lambda: True,
        parent_process_path="/Applications/evaOS.app/Contents/MacOS/EvaDesktop",
    )

    errors = helper_permission_preflight_errors(preflight)

    assert preflight["ok"] is False
    assert preflight["permissions"]["accessibility"]["status"] == "unknown"
    assert errors[0]["code"] == "permission_missing"
    assert errors[0]["permission"] == "accessibility"


def test_helper_permission_preflight_rejects_spoofed_workbench_env_parent() -> None:
    preflight = helper_permission_preflight(
        env={
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID": "com.electricsheephq.EvaDesktop",
            "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH": "/Applications/evaOS.app",
            "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1",
        },
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
        parent_process_path="/bin/zsh",
    )

    errors = helper_permission_preflight_errors(preflight)

    assert preflight["ok"] is False
    assert preflight["identity"]["status"] == "parent_unverified"
    assert preflight["identity"]["parent_status"] == "mismatch"
    assert errors[0]["code"] == "helper_identity_unverified"


def test_helper_permission_preflight_fails_closed_for_unattributed_identity() -> None:
    preflight = helper_permission_preflight(
        env={"EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1"},
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
    )

    errors = helper_permission_preflight_errors(preflight)

    assert preflight["ok"] is False
    assert preflight["identity"]["status"] == "unattributed_cli"
    assert errors[0]["code"] == "helper_identity_unverified"


def test_helper_mouse_action_fails_closed_when_enforced_preflight_missing() -> None:
    token = make_capability_token()
    request = build_helper_request(
        command="mouse_action",
        token=token,
        request_id="req-permission-missing",
        audit_id="audit-helper-test",
        payload={"action": "click", "x": 10, "y": 20},
    )
    calls = 0

    def executor(_command: str, _payload: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"ok": True, "data": {}, "warnings": [], "errors": []}

    response = handle_helper_request(
        request,
        expected_token=token,
        expected_uid=501,
        peer_uid=501,
        command_executor=executor,
        permission_checker=lambda: helper_permission_preflight(
            env={
                "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID": "com.electricsheephq.EvaDesktop",
                "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH": "/Applications/evaOS.app",
                "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1",
            },
            platform_name="Darwin",
            accessibility_checker=lambda: True,
            screen_recording_checker=lambda: False,
            parent_process_path="/Applications/evaOS.app/Contents/MacOS/EvaDesktop",
        ),
    )

    assert response["ok"] is False
    assert response["errors"][0]["code"] == "permission_missing"
    assert response["data"]["performed"] is False
    assert calls == 0


def test_helper_mouse_action_runs_when_enforced_preflight_is_granted() -> None:
    token = make_capability_token()
    request = build_helper_request(
        command="mouse_action",
        token=token,
        request_id="req-permission-granted",
        audit_id="audit-helper-test",
        payload={"action": "click", "x": 10, "y": 20},
    )
    calls = 0

    def executor(command: str, payload: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "ok": True,
            "data": {"performed": True, "action": payload["action"], "engine": "helper_post_to_pid"},
            "warnings": [],
            "errors": [],
        }

    response = handle_helper_request(
        request,
        expected_token=token,
        expected_uid=501,
        peer_uid=501,
        command_executor=executor,
        permission_checker=lambda: helper_permission_preflight(
            env={
                "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID": "com.electricsheephq.EvaDesktop",
                "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH": "/Applications/evaOS.app",
                "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS": "1",
            },
            platform_name="Darwin",
            accessibility_checker=lambda: True,
            screen_recording_checker=lambda: True,
            parent_process_path="/Applications/evaOS.app/Contents/MacOS/EvaDesktop",
        ),
    )

    assert response["ok"] is True
    assert response["data"]["performed"] is True
    assert response["data"]["permission_preflight"]["ok"] is True
    assert response["data"]["permission_preflight"]["identity"]["status"] == "workbench_signed_app"
    assert calls == 1


def test_helper_token_auto_create_rotates_and_writes_private_file(tmp_path: Path) -> None:
    token_file = tmp_path / "helper.token"
    token_file.write_text("old-token\n", encoding="utf-8")
    token_file.chmod(0o600)

    first = read_helper_token(token_file=token_file, auto_create=True)
    second = read_helper_token(token_file=token_file, auto_create=True)

    assert first != "old-token"
    assert second != first
    assert token_file.read_text(encoding="utf-8").strip() == second
    assert token_file.stat().st_mode & 0o077 == 0


def test_helper_token_rejects_group_or_world_readable_file(tmp_path: Path) -> None:
    token_file = tmp_path / "helper.token"
    token_file.write_text("token\n", encoding="utf-8")
    token_file.chmod(0o644)

    with pytest.raises(HelperIpcError) as exc:
        read_helper_token(token_file=token_file)

    assert exc.value.code == "helper_token_unsafe"


def test_helper_token_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real-token"
    target.write_text("token\n", encoding="utf-8")
    target.chmod(0o600)
    token_file = tmp_path / "helper.token"
    token_file.symlink_to(target)

    with pytest.raises(HelperIpcError) as exc:
        read_helper_token(token_file=token_file)

    assert exc.value.code == "helper_token_unsafe"


def test_run_helper_server_refuses_to_unlink_regular_file_socket_path(tmp_path: Path) -> None:
    socket_path = tmp_path / "not-a-socket"
    socket_path.write_text("keep me\n", encoding="utf-8")

    with pytest.raises(HelperIpcError) as exc:
        run_helper_server(socket_path=socket_path, token=make_capability_token(), max_requests=1)

    assert exc.value.code == "helper_socket_path_not_socket"
    assert socket_path.read_text(encoding="utf-8") == "keep me\n"


def test_run_helper_server_times_out_stalled_client() -> None:
    token = make_capability_token()
    socket_path = short_socket_path()
    ready = threading.Event()
    thread = threading.Thread(
        target=run_helper_server,
        kwargs={
            "socket_path": socket_path,
            "token": token,
            "expected_uid": os.getuid(),
            "ready": ready,
            "max_requests": 1,
            "peer_uid_getter": lambda _sock: os.getuid(),
            "connection_timeout": 0.05,
        },
        daemon=True,
    )
    thread.start()
    assert ready.wait(timeout=2)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(socket_path))
        response = read_raw_frame(client)

    thread.join(timeout=2)
    assert response["ok"] is False
    assert response["errors"][0]["code"] == "helper_ipc_timeout"


def test_helper_server_response_write_failure_is_best_effort() -> None:
    class ClosedConnection:
        def sendall(self, _frame: bytes) -> None:
            raise BrokenPipeError("closed")

    response = {"schema_version": HELPER_IPC_SCHEMA_VERSION, "ok": True, "data": {}, "errors": [], "warnings": []}

    assert _send_frame_best_effort(ClosedConnection(), response) is False  # type: ignore[arg-type]


def test_helper_server_response_encode_failure_sends_safe_error() -> None:
    class RecordingConnection:
        def __init__(self) -> None:
            self.frame = b""

        def sendall(self, frame: bytes) -> None:
            self.frame = frame

    connection = RecordingConnection()
    response = {
        "schema_version": HELPER_IPC_SCHEMA_VERSION,
        "request_id": "req",
        "ok": True,
        "data": {"oversized": "x" * (HELPER_IPC_MAX_BYTES + 1)},
        "errors": [],
        "warnings": [],
    }

    assert _send_frame_best_effort(connection, response) is True  # type: ignore[arg-type]
    decoded = decode_frame(connection.frame)
    assert decoded["ok"] is False
    assert decoded["request_id"] == "unknown"
    assert decoded["errors"][0]["code"] == "helper_ipc_server_error"
    assert "could not be encoded" in decoded["errors"][0]["message"]


def test_unix_socket_helper_client_round_trips_ping(tmp_path: Path) -> None:
    token = make_capability_token()
    socket_path = short_socket_path()
    ready = threading.Event()

    thread = threading.Thread(
        target=run_helper_server,
        kwargs={
            "socket_path": socket_path,
            "token": token,
            "expected_uid": os.getuid(),
            "ready": ready,
            "max_requests": 1,
            "peer_uid_getter": lambda _sock: os.getuid(),
        },
        daemon=True,
    )
    thread.start()
    assert ready.wait(timeout=2)

    response = UnixSocketHelperClient(socket_path=socket_path, token=token).dispatch("ping", {"client": "test"})

    thread.join(timeout=2)
    assert response.ok is True
    assert response.data["command"] == "ping"
    assert response.data["helper_mode"] == "resident_local"
    assert response.data["actuation_enabled"] is True


def test_unix_socket_helper_client_bad_token_fails_closed(tmp_path: Path) -> None:
    token = make_capability_token()
    socket_path = short_socket_path()
    ready = threading.Event()

    thread = threading.Thread(
        target=run_helper_server,
        kwargs={
            "socket_path": socket_path,
            "token": token,
            "expected_uid": os.getuid(),
            "ready": ready,
            "max_requests": 1,
            "peer_uid_getter": lambda _sock: os.getuid(),
        },
        daemon=True,
    )
    thread.start()
    assert ready.wait(timeout=2)

    response = UnixSocketHelperClient(socket_path=socket_path, token="wrong").dispatch("ping", {"client": "test"})

    thread.join(timeout=2)
    assert response.ok is False
    assert response.errors[0]["code"] == "helper_ipc_bad_token"
    assert token not in json.dumps(response.data)
    assert token not in json.dumps(response.errors)


def test_helper_ipc_rejects_wrong_schema_version() -> None:
    token = "correct-token"
    request = build_helper_request(command="ping", token=token, request_id="req-schema")
    request["schema_version"] = "evaos.helper_ipc.v0"

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(request, expected_token=token, expected_uid=501, peer_uid=501)

    assert exc.value.code == "helper_ipc_bad_schema"


@pytest.mark.parametrize("expected_uid", [None, -1, "501", True])
def test_helper_ipc_rejects_missing_or_invalid_expected_uid(expected_uid: object) -> None:
    token = "correct-token"
    request = build_helper_request(command="ping", token=token, request_id="req-uid")

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(request, expected_token=token, expected_uid=expected_uid, peer_uid=501)

    assert exc.value.code == "helper_ipc_missing_peer_policy"


@pytest.mark.parametrize("peer_uid", [None, -1, "501", True, False])
def test_helper_ipc_rejects_missing_or_invalid_peer_uid(peer_uid: object) -> None:
    token = "correct-token"
    request = build_helper_request(command="ping", token=token, request_id="req-peer")

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(request, expected_token=token, expected_uid=501, peer_uid=peer_uid)

    assert exc.value.code == "helper_ipc_bad_peer"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("request_id", {"bad": "shape"}, "helper_ipc_bad_request_id"),
        ("request_id", "", "helper_ipc_bad_request_id"),
        ("payload", "not-object", "helper_ipc_bad_payload"),
        ("audit_id", {"bad": "shape"}, "helper_ipc_bad_audit_id"),
    ],
)
def test_helper_ipc_rejects_malformed_authorized_envelope(field: str, value: object, code: str) -> None:
    token = "correct-token"
    request = build_helper_request(command="ping", token=token, request_id="req-shape")
    request[field] = value

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(request, expected_token=token, expected_uid=501, peer_uid=501)

    assert exc.value.code == code


@pytest.mark.parametrize(
    ("request_token", "peer_uid", "code"),
    [
        ("", 501, "helper_ipc_missing_token"),
        ("wrong-token", 501, "helper_ipc_bad_token"),
        ("correct-token", 502, "helper_ipc_bad_peer"),
    ],
)
def test_helper_ipc_rejects_missing_wrong_token_and_wrong_peer(
    request_token: str,
    peer_uid: int,
    code: str,
) -> None:
    expected_token = "correct-token"
    request = build_helper_request(command="ping", token=request_token, request_id="req-2")

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(request, expected_token=expected_token, expected_uid=501, peer_uid=peer_uid)

    assert exc.value.code == code
    assert expected_token not in str(exc.value)


@pytest.mark.parametrize("command", ["desktop_click", "customer_mac.desktop_type", "shell", "python"])
def test_helper_ipc_rejects_unknown_or_actuation_like_commands(command: str) -> None:
    token = "correct-token"
    request = build_helper_request(command=command, token=token, request_id="req-3")

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(request, expected_token=token, expected_uid=501, peer_uid=501)

    assert exc.value.code == "helper_ipc_command_not_allowed"
    assert command not in HELPER_IPC_ALLOWED_COMMANDS


def test_helper_ipc_framing_round_trips_and_rejects_oversized_messages() -> None:
    payload = {"schema_version": HELPER_IPC_SCHEMA_VERSION, "command": "ping"}
    frame = encode_frame(payload)

    assert decode_frame(frame) == payload

    too_large = b"\x00\x00\x00\x01" + b"{}"
    oversized_prefix = (HELPER_IPC_MAX_BYTES + 1).to_bytes(4, "big")
    with pytest.raises(HelperIpcError) as exc:
        decode_frame(oversized_prefix + too_large[4:])

    assert exc.value.code == "helper_ipc_payload_too_large"


def test_helper_ipc_rejects_oversized_frame_before_json_parse() -> None:
    with pytest.raises(HelperIpcError) as exc:
        decode_frame((HELPER_IPC_MAX_BYTES + 1).to_bytes(4, "big") + b"not-json")

    assert exc.value.code == "helper_ipc_payload_too_large"


@pytest.mark.parametrize(
    ("frame", "code"),
    [
        (b"\x00\x00\x00", "helper_ipc_frame_truncated"),
        ((2).to_bytes(4, "big") + b"[]", "helper_ipc_bad_payload"),
        ((10).to_bytes(4, "big") + b"{}", "helper_ipc_frame_truncated"),
        ((8).to_bytes(4, "big") + b"not-json", "helper_ipc_bad_json"),
    ],
)
def test_helper_ipc_rejects_malformed_in_bounds_frames(frame: bytes, code: str) -> None:
    with pytest.raises(HelperIpcError) as exc:
        decode_frame(frame)

    assert exc.value.code == code
