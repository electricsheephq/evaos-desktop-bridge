from __future__ import annotations

import json
import secrets
from typing import Any

from .schema import timestamp_utc

HELPER_IPC_SCHEMA_VERSION = "evaos.helper_ipc.v1"
HELPER_IPC_MAX_BYTES = 64 * 1024
HELPER_IPC_ALLOWED_COMMANDS = frozenset({"ping"})


class HelperIpcError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def make_capability_token() -> str:
    return secrets.token_urlsafe(48)


def build_helper_request(
    *,
    command: str,
    token: str,
    request_id: str,
    audit_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": HELPER_IPC_SCHEMA_VERSION,
        "request_id": request_id,
        "command": command,
        "capability_token": token,
        "payload": payload or {},
    }
    if audit_id is not None:
        request["audit_id"] = audit_id
    return request


def handle_helper_request(
    request: dict[str, Any],
    *,
    expected_token: str,
    expected_uid: int | None,
    peer_uid: int | None,
) -> dict[str, Any]:
    _authorize_request(request, expected_token=expected_token, expected_uid=expected_uid, peer_uid=peer_uid)
    if request.get("schema_version") != HELPER_IPC_SCHEMA_VERSION:
        raise HelperIpcError("helper_ipc_bad_schema", "Helper IPC request has an unsupported schema version.")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise HelperIpcError("helper_ipc_bad_request_id", "Helper IPC request id must be a non-empty string.")
    command = request.get("command")
    if not isinstance(command, str) or command not in HELPER_IPC_ALLOWED_COMMANDS:
        raise HelperIpcError("helper_ipc_command_not_allowed", "Helper IPC command is not allowed in the contract skeleton.")
    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise HelperIpcError("helper_ipc_bad_payload", "Helper IPC request payload must be a JSON object.")
    audit_id = request.get("audit_id")
    if audit_id is not None and (not isinstance(audit_id, str) or not audit_id):
        raise HelperIpcError("helper_ipc_bad_audit_id", "Helper IPC audit id must be a non-empty string when present.")
    return {
        "schema_version": HELPER_IPC_SCHEMA_VERSION,
        "request_id": request_id,
        "ok": True,
        "timestamp": timestamp_utc(),
        "data": {
            "command": command,
            "helper_mode": "contract_only",
            "actuation_enabled": False,
        },
        "warnings": [],
        "errors": [],
    }


def encode_frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > HELPER_IPC_MAX_BYTES:
        raise HelperIpcError("helper_ipc_payload_too_large", "Helper IPC payload exceeds the maximum frame size.")
    return len(body).to_bytes(4, "big") + body


def decode_frame(frame: bytes) -> dict[str, Any]:
    if len(frame) < 4:
        raise HelperIpcError("helper_ipc_frame_truncated", "Helper IPC frame is missing its length prefix.")
    length = int.from_bytes(frame[:4], "big")
    if length > HELPER_IPC_MAX_BYTES:
        raise HelperIpcError("helper_ipc_payload_too_large", "Helper IPC payload exceeds the maximum frame size.")
    body = frame[4:]
    if len(body) != length:
        raise HelperIpcError("helper_ipc_frame_truncated", "Helper IPC frame length does not match its payload.")
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HelperIpcError("helper_ipc_bad_json", "Helper IPC frame payload is not valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise HelperIpcError("helper_ipc_bad_payload", "Helper IPC frame payload must be a JSON object.")
    return decoded


def _authorize_request(
    request: dict[str, Any],
    *,
    expected_token: str,
    expected_uid: int | None,
    peer_uid: int | None,
) -> None:
    if type(expected_uid) is not int or expected_uid < 0:
        raise HelperIpcError("helper_ipc_missing_peer_policy", "Helper IPC expected peer uid is not configured.")
    supplied_token = request.get("capability_token")
    if not isinstance(supplied_token, str) or not supplied_token:
        raise HelperIpcError("helper_ipc_missing_token", "Helper IPC request is missing its capability token.")
    if not expected_token or not secrets.compare_digest(supplied_token, expected_token):
        raise HelperIpcError("helper_ipc_bad_token", "Helper IPC request has an invalid capability token.")
    if peer_uid != expected_uid:
        raise HelperIpcError("helper_ipc_bad_peer", "Helper IPC peer uid is not authorized.")
