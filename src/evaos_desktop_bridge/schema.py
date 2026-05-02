from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .redaction import redact_value

SCHEMA_VERSION = "2026-05-02.mvp1"


def timestamp_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_error(
    *,
    code: str,
    message: str,
    guidance: str,
    permission: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "guidance": guidance,
    }
    if permission is not None:
        error["permission"] = permission
    return error


def build_envelope(
    *,
    command: str,
    target: str,
    ok: bool,
    data: dict[str, Any],
    warnings: list[str],
    errors: list[dict[str, Any]],
    audit_id: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "target": target,
        "timestamp": timestamp or timestamp_utc(),
        "ok": ok,
        "data": redact_value(data),
        "warnings": redact_value(warnings),
        "errors": redact_value(errors),
        "audit_id": audit_id,
    }
