from __future__ import annotations

import json
import os
import socket
import threading
import uuid
from pathlib import Path

import pytest

from evaos_desktop_bridge.helper_ipc import (
    HELPER_IPC_ALLOWED_COMMANDS,
    HELPER_IPC_MAX_BYTES,
    HELPER_IPC_SCHEMA_VERSION,
    HelperIpcError,
    UnixSocketHelperClient,
    build_helper_request,
    decode_frame,
    default_helper_socket_path,
    encode_frame,
    handle_helper_request,
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


def test_helper_ipc_contract_exposes_health_and_narrow_mouse_action_only() -> None:
    assert HELPER_IPC_ALLOWED_COMMANDS == frozenset({"ping", "mouse_action"})


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
                "engine": "helper_quartz",
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
    assert response["data"]["engine"] == "helper_quartz"
    assert response["warnings"] == ["warm helper path"]
    assert calls == [("mouse_action", {"action": "click", "x": 10, "y": 20})]
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
