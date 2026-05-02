from __future__ import annotations

import json
import os
import platform
import uuid
from pathlib import Path
from typing import Any

from .redaction import redact_value
from .schema import SCHEMA_VERSION, timestamp_utc

STATE_DIR_ENV = "EVAOS_DESKTOP_BRIDGE_STATE_DIR"


def default_state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "evaos-desktop-bridge"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "evaos-desktop-bridge"


def append_audit(
    *,
    command: str,
    target: str,
    args: dict[str, Any],
    ok: bool,
    warnings: list[str],
    errors: list[dict[str, Any]],
    state_dir: Path | None = None,
) -> str:
    audit_id = f"audit-{uuid.uuid4().hex}"
    root = state_dir or default_state_dir()
    root.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": audit_id,
        "timestamp": timestamp_utc(),
        "command": command,
        "target": target,
        "args": redact_value(args),
        "ok": ok,
        "warnings": redact_value(warnings),
        "errors": redact_value(errors),
    }
    with (root / "audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return audit_id
