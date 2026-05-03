from __future__ import annotations

import json
import subprocess
import tempfile
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



    def desktop_freshness(self, *, thread_id: str, visible_text: str = "", max_events: int = 20) -> CommandResult:
        tail = self.read_thread_tail(thread_id=thread_id, max_events=max_events)
        if not tail.ok:
            return tail
        events = tail.data.get("events", []) if isinstance(tail.data, dict) else []
        latest = self._latest_visible_marker(events)
        marker = latest.get("marker") if latest else ""
        visible = visible_text.lower()
        marker_text = str(marker or "")
        marker_visible = bool(marker_text and marker_text.lower()[:160] in visible)
        if marker_text and marker_visible:
            desktop_state = "fresh"
            recommended_action = "no_action"
        elif marker_text and visible_text:
            desktop_state = "stale"
            recommended_action = "rehydrate_thread"
        else:
            desktop_state = "unknown"
            recommended_action = "open_thread_then_inspect"
        return CommandResult(
            ok=True,
            data={
                "thread_id": thread_id,
                "desktop_state": desktop_state,
                "latest_session_turn_hint": latest,
                "visible_turn_hint_present": marker_visible,
                "recommended_action": recommended_action,
                "source": "rollout_vs_visible_text",
            },
            provenance={"source": "freshness_heuristic", "thread_id": thread_id},
        )

    def rehydrate_thread(self, *, thread_id: str, dry_run: bool = True, wait_ms: int = 1500) -> CommandResult:
        url = f"codex://threads/{thread_id}"
        if dry_run:
            return CommandResult(
                ok=True,
                data={"would_rehydrate": True, "rehydrated": False, "thread_id": thread_id, "url": url, "wait_ms": wait_ms},
                provenance={"source": "deep_link_rehydrate", "dry_run": True, "thread_id": thread_id},
            )
        result = self.runner(["open", url], 5.0)
        if result.returncode != 0:
            return CommandResult(ok=False, data={"rehydrated": False, "thread_id": thread_id, "url": url}, errors=[make_error(code="rehydrate_thread_open_failed", message="Unable to open Codex Desktop thread deep link for rehydration.", guidance="Ensure Codex.app is installed and codex:// URL handling is registered.")], warnings=[str(redact_value(result.stderr.strip()))] if result.stderr.strip() else [], provenance={"source": "deep_link_rehydrate", "dry_run": False, "thread_id": thread_id})
        return CommandResult(
            ok=True,
            data={"would_rehydrate": False, "rehydrated": True, "thread_id": thread_id, "url": url, "wait_ms": wait_ms, "verification_required": True},
            warnings=["rehydrate opens the thread but does not guarantee Desktop renderer freshness; run desktop-freshness with visible text/snapshot after wait"],
            provenance={"source": "deep_link_rehydrate", "dry_run": False, "thread_id": thread_id},
        )

    def steer_thread(
        self,
        *,
        thread_id: str,
        message: str,
        dry_run: bool = False,
        timeout_seconds: int = 120,
        max_chars: int = 4000,
    ) -> CommandResult:
        preview, preview_truncated = cap_text(redact_value(message), max_chars)
        if not thread_id:
            return CommandResult(ok=False, errors=[make_error(code="thread_id_required", message="A Codex thread id is required.", guidance="Use codex indexed-threads to choose a Desktop-visible thread.")])
        if dry_run:
            return CommandResult(
                ok=True,
                data={
                    "would_steer": True,
                    "steered": False,
                    "thread_id": thread_id,
                    "message_preview": preview,
                    "message_truncated": preview_truncated,
                    "command": ["codex", "exec", "resume", thread_id, "-", "--json"],
                },
                provenance={"source": "codex_exec_resume", "dry_run": True, "thread_id": thread_id},
            )
        with tempfile.TemporaryDirectory(prefix="evaos-codex-steer-") as tmpdir:
            output_path = Path(tmpdir) / "last-message.txt"
            try:
                completed = subprocess.run(
                    ["codex", "exec", "resume", thread_id, "-", "--json", "--output-last-message", str(output_path)],
                    input=message,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                return CommandResult(
                    ok=False,
                    data={"steered": False, "thread_id": thread_id, "message_preview": preview},
                    errors=[make_error(code="steer_thread_timeout", message="Codex CLI resume did not complete before the timeout.", guidance="Use read-thread-tail to monitor the thread; for long-running workers prefer external background launch support.")],
                    provenance={"source": "codex_exec_resume", "dry_run": False, "thread_id": thread_id},
                )
            events = []
            for line in completed.stdout.splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = self._safe_exec_event(row)
                if event is not None:
                    events.append(event)
            last_message = ""
            if output_path.exists():
                last_message = output_path.read_text(encoding="utf-8", errors="replace")
            last_message_preview, last_message_truncated = cap_text(redact_value(last_message), max_chars)
            if completed.returncode != 0:
                stderr_preview, stderr_truncated = cap_text(redact_value(completed.stderr.strip()), max_chars)
                return CommandResult(
                    ok=False,
                    data={
                        "steered": False,
                        "thread_id": thread_id,
                        "message_preview": preview,
                        "events": events[-20:],
                        "stderr_preview": stderr_preview,
                        "stderr_truncated": stderr_truncated,
                    },
                    errors=[make_error(code="steer_thread_failed", message="Codex CLI resume exited non-zero.", guidance="Check stderr_preview and read-thread-tail before retrying.")],
                    provenance={"source": "codex_exec_resume", "dry_run": False, "thread_id": thread_id},
                )
            return CommandResult(
                ok=True,
                data={
                    "steered": True,
                    "thread_id": thread_id,
                    "message_preview": preview,
                    "message_truncated": preview_truncated,
                    "last_message_preview": last_message_preview,
                    "last_message_truncated": last_message_truncated,
                    "events": events[-20:],
                    "returncode": completed.returncode,
                },
                provenance={"source": "codex_exec_resume", "dry_run": False, "thread_id": thread_id},
            )


    def _latest_visible_marker(self, events: list[dict[str, Any]]) -> dict[str, Any] | None:
        for event in reversed(events):
            text = event.get("last_agent_message") or event.get("message")
            if isinstance(text, str) and text.strip():
                marker, truncated = cap_text(text.strip(), 500)
                return {"type": event.get("type"), "timestamp": event.get("timestamp"), "marker": marker, "marker_truncated": truncated}
            if event.get("type") == "task_complete":
                return {"type": "task_complete", "timestamp": event.get("timestamp"), "marker": "task_complete", "marker_truncated": False}
        return None

    def _safe_index_row(self, row: dict[str, Any], index: int) -> dict[str, Any]:
        title, title_truncated = cap_text(redact_value(row.get("thread_name") or row.get("title") or "Untitled"), 180)
        return {"index": index, "id": redact_value(row.get("id")), "title": title, "title_truncated": title_truncated, "updated_at": redact_value(row.get("updated_at")), "source": "session_index"}

    def _rollout_for_thread(self, thread_id: str) -> Path | None:
        if not self.sessions_root.exists():
            return None
        matches = sorted(self.sessions_root.glob(f"**/*{thread_id}*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
        return matches[0] if matches else None


    def _safe_exec_event(self, row: dict[str, Any]) -> dict[str, Any] | None:
        event_type = row.get("type")
        if event_type == "thread.started":
            return {"type": event_type, "thread_id": redact_value(row.get("thread_id"))}
        if event_type in {"turn.started", "turn.completed", "turn.failed", "error"}:
            safe = {"type": event_type}
            if "error" in row:
                safe["error"] = redact_value(row.get("error"))
            if "message" in row:
                message, truncated = cap_text(redact_value(row.get("message")), 1200)
                safe["message"] = message
                safe["truncated"] = truncated
            return safe
        if event_type in {"item.started", "item.completed"} and isinstance(row.get("item"), dict):
            item = row["item"]
            item_type = item.get("type")
            safe = {"type": event_type, "item_type": redact_value(item_type)}
            if item_type == "agent_message":
                text, truncated = cap_text(redact_value(item.get("text") or ""), 1200)
                safe["text"] = text
                safe["truncated"] = truncated
            if item_type == "command_execution":
                safe["command"] = redact_value(item.get("command"))
                safe["status"] = redact_value(item.get("status"))
                safe["exit_code"] = redact_value(item.get("exit_code"))
            return safe
        return None

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
