from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .audit import default_state_dir
from .redaction import redact_value
from .schema import SCHEMA_VERSION, make_error, timestamp_utc
from .types import CommandResult

QUEUE_FILE = "queue.jsonl"
ALLOWED_QUEUE_KINDS = frozenset({"idle", "approval_needed", "done", "error", "attention"})


def append_queue_event(
    *,
    kind: str,
    source_audit_id: str,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    state_dir: Path | None = None,
) -> CommandResult:
    if kind not in ALLOWED_QUEUE_KINDS:
        return CommandResult(
            ok=False,
            errors=[
                make_error(
                    code="queue_kind_not_allowed",
                    message=f"Queue kind '{kind}' is not allowlisted.",
                    guidance=f"Use one of: {', '.join(sorted(ALLOWED_QUEUE_KINDS))}.",
                )
            ],
            provenance={"source": "queue"},
        )
    if not source_audit_id.startswith("audit-"):
        return CommandResult(
            ok=False,
            errors=[
                make_error(
                    code="invalid_source_audit_id",
                    message="Queue events must reference a bridge audit id.",
                    guidance="Pass --source-audit-id with an audit-... value from a prior bridge command.",
                )
            ],
            provenance={"source": "queue"},
        )

    root = state_dir or default_state_dir()
    root.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": SCHEMA_VERSION,
        "queue_id": f"queue-{uuid.uuid4().hex}",
        "timestamp": timestamp_utc(),
        "kind": kind,
        "source_audit_id": source_audit_id,
        "message": message,
        "payload": redact_value(payload or {}),
        "status": "pending",
    }
    with (root / QUEUE_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact_value(record), sort_keys=True, separators=(",", ":")) + "\n")
    return CommandResult(ok=True, data={"event": record}, provenance={"source": "queue", "source_audit_id": source_audit_id})


def list_queue_events(*, limit: int = 20, state_dir: Path | None = None) -> CommandResult:
    root = state_dir or default_state_dir()
    path = root / QUEUE_FILE
    if not path.exists():
        return CommandResult(ok=True, data={"events": [], "count": 0, "limit": limit}, provenance={"source": "queue"})
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        events.append(redact_value(json.loads(line)))
    return CommandResult(ok=True, data={"events": events, "count": len(events), "limit": limit}, provenance={"source": "queue"})
