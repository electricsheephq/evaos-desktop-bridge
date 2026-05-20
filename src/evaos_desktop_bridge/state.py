from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .audit import default_state_dir
from .redaction import redact_value

LATEST_FILE = "latest.json"
AUDIT_FILE = "audit.jsonl"


def latest_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / LATEST_FILE


def write_latest(envelope: dict[str, Any], state_dir: Path | None = None) -> Path:
    root = state_dir or default_state_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / LATEST_FILE
    path.write_text(json.dumps(redact_value(envelope), sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_latest(state_dir: Path | None = None) -> dict[str, Any] | None:
    path = latest_path(state_dir)
    if not path.exists():
        return None
    return redact_value(json.loads(path.read_text(encoding="utf-8")))


def read_audit_tail(limit: int = 20, state_dir: Path | None = None) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    root = state_dir or default_state_dir()
    path = root / AUDIT_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        records.append(redact_value(json.loads(line)))
    return records


def read_audit_record(audit_id: str, state_dir: Path | None = None) -> dict[str, Any] | None:
    if not audit_id.startswith("audit-"):
        return None
    root = state_dir or default_state_dir()
    path = root / AUDIT_FILE
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("audit_id") == audit_id:
            return redact_value(record)
    return None
