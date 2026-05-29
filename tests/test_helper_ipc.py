from __future__ import annotations

import json

import pytest

from evaos_desktop_bridge.helper_ipc import (
    HELPER_IPC_ALLOWED_COMMANDS,
    HELPER_IPC_MAX_BYTES,
    HELPER_IPC_SCHEMA_VERSION,
    HelperIpcError,
    build_helper_request,
    decode_frame,
    encode_frame,
    handle_helper_request,
    make_capability_token,
)


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
    serialized = json.dumps(response)
    assert serialized
    assert token not in serialized


def test_helper_ipc_contract_skeleton_exposes_only_ping() -> None:
    assert HELPER_IPC_ALLOWED_COMMANDS == frozenset({"ping"})


def test_helper_ipc_rejects_wrong_schema_version() -> None:
    token = "correct-token"
    request = build_helper_request(command="ping", token=token, request_id="req-schema")
    request["schema_version"] = "evaos.helper_ipc.v0"

    with pytest.raises(HelperIpcError) as exc:
        handle_helper_request(request, expected_token=token, expected_uid=501, peer_uid=501)

    assert exc.value.code == "helper_ipc_bad_schema"


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


def test_helper_ipc_rejects_malformed_frame_before_json_parse() -> None:
    with pytest.raises(HelperIpcError) as exc:
        decode_frame((HELPER_IPC_MAX_BYTES + 1).to_bytes(4, "big") + b"not-json")

    assert exc.value.code == "helper_ipc_payload_too_large"
