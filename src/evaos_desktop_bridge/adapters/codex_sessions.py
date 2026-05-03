from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..redaction import cap_text, redact_value
from ..schema import make_error
from ..types import CommandResult
from .codex_macos import RunnerResult, run_command

CODEX_HOME = Path.home() / ".codex"
SESSION_INDEX = CODEX_HOME / "session_index.jsonl"
SESSIONS_ROOT = CODEX_HOME / "sessions"


@dataclass
class CodexSessionObserver:
    runner: Callable[[list[str], float], RunnerResult] = run_command
    session_index: Path = SESSION_INDEX
    sessions_root: Path = SESSIONS_ROOT

    def indexed_threads(self, *, max_items: int = 50) -> CommandResult:
        if not self.session_index.exists():
            return CommandResult(ok=False, errors=[make_error(code="codex_session_index_missing", message="Codex session_index.jsonl was not found.", guidance="Open Codex Desktop or create a persisted interactive session first.")])
        rows = []
        with self.session_index.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        rows = rows[-max_items:]
        rows.reverse()
        threads = [self._safe_index_row(row, index) for index, row in enumerate(rows)]
        return CommandResult(ok=True, data={"threads": threads, "count": len(threads), "max_items": max_items, "source": "session_index"}, provenance={"source": "session_index"})

    def read_thread_tail(self, *, thread_id: str, max_events: int = 40, max_chars: int = 12000) -> CommandResult:
        rollout = self._rollout_for_thread(thread_id)
        if rollout is None:
            return CommandResult(ok=False, data={"thread_id": thread_id}, errors=[make_error(code="thread_rollout_not_found", message="No Codex rollout file was found for this thread id.", guidance="Use codex indexed-threads or verify the thread id exists under ~/.codex/sessions.")], provenance={"source": "rollout_file", "thread_id": thread_id})
        events: list[dict[str, Any]] = []
        with rollout.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                safe = self._safe_rollout_event(row)
                if safe is not None:
                    events.append(safe)
        events = events[-max_events:]
        text = json.dumps(events, ensure_ascii=False)
        capped, truncated = cap_text(text, max_chars)
        if truncated:
            events = json.loads(capped.rsplit("}", 1)[0] + "}") if False else events
        return CommandResult(ok=True, data={"thread_id": thread_id, "rollout_file": str(rollout), "events": events, "count": len(events), "max_events": max_events, "truncated": truncated}, provenance={"source": "rollout_file", "thread_id": thread_id})

    def open_thread(self, *, thread_id: str, dry_run: bool = False) -> CommandResult:
        url = f"codex://threads/{thread_id}"
        if dry_run:
            return CommandResult(ok=True, data={"would_open": True, "opened": False, "thread_id": thread_id, "url": url}, provenance={"source": "deep_link", "dry_run": True})
        result = self.runner(["open", url], 5.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"opened": False, "thread_id": thread_id, "url": url}, errors=[make_error(code="thread_open_failed", message="Unable to open Codex Desktop deep link.", guidance="Ensure Codex.app is installed and codex:// URL handling is registered.")], warnings=[str(redact_value(result.stderr.strip()))] if result.stderr.strip() else [], provenance={"source": "deep_link", "dry_run": False})
        return CommandResult(ok=True, data={"opened": True, "thread_id": thread_id, "url": url}, provenance={"source": "deep_link", "dry_run": False})

    def _safe_index_row(self, row: dict[str, Any], index: int) -> dict[str, Any]:
        title, title_truncated = cap_text(redact_value(row.get("thread_name") or row.get("title") or "Untitled"), 180)
        return {"index": index, "id": redact_value(row.get("id")), "title": title, "title_truncated": title_truncated, "updated_at": redact_value(row.get("updated_at")), "source": "session_index"}

    def _rollout_for_thread(self, thread_id: str) -> Path | None:
        if not self.sessions_root.exists():
            return None
        matches = sorted(self.sessions_root.glob(f"**/*{thread_id}*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
        return matches[0] if matches else None

    def _safe_rollout_event(self, row: dict[str, Any]) -> dict[str, Any] | None:
        timestamp = redact_value(row.get("timestamp"))
        row_type = row.get("type")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if row_type == "session_meta":
            return {"timestamp": timestamp, "type": "session_meta", "id": redact_value(payload.get("id")), "source": redact_value(payload.get("source") or payload.get("originator")), "cwd": redact_value(payload.get("cwd"))}
        if row_type != "event_msg":
            return None
        event_type = payload.get("type")
        if event_type in {"user_message", "agent_message", "background_event"}:
            message, truncated = cap_text(redact_value(payload.get("message") or ""), 1200)
            return {"timestamp": timestamp, "type": event_type, "message": message, "truncated": truncated, "phase": redact_value(payload.get("phase"))}
        if event_type in {"exec_command_begin", "exec_command_end"}:
            return {"timestamp": timestamp, "type": event_type, "command": redact_value(payload.get("command")), "status": redact_value(payload.get("status")), "exit_code": redact_value(payload.get("exit_code"))}
        if event_type == "task_complete":
            message, truncated = cap_text(redact_value(payload.get("last_agent_message") or ""), 1200)
            return {"timestamp": timestamp, "type": "task_complete", "last_agent_message": message, "truncated": truncated, "duration_ms": redact_value(payload.get("duration_ms"))}
        return {"timestamp": timestamp, "type": redact_value(event_type)}
