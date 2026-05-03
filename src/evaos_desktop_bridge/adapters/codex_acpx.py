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

ACPX_SESSIONS = Path.home() / ".acpx" / "sessions"


@dataclass
class AcpxWorkerObserver:
    runner: Callable[[list[str], float], RunnerResult] = run_command
    sessions_dir: Path = ACPX_SESSIONS
    acpx_command: list[str] | None = None

    def _cmd(self, *args: str) -> list[str]:
        base = self.acpx_command or ["npx", "-y", "acpx@latest"]
        return [*base, *args]

    def list_workers(self, *, max_items: int = 50) -> CommandResult:
        result = self.runner(self._cmd("--format", "json", "codex", "sessions", "list"), 20.0)
        if result.returncode != 0:
            return self._error("acpx_workers_list_failed", "Unable to list acpx Codex workers.", result)
        try:
            rows = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return CommandResult(ok=False, errors=[make_error(code="acpx_json_parse_failed", message="Unable to parse acpx sessions list JSON.", guidance="Run acpx directly with --format json to inspect output.")])
        workers = [self._safe_worker(row) for row in rows[-max_items:]]
        return CommandResult(ok=True, data={"workers": workers, "count": len(workers), "max_items": max_items}, provenance={"source": "acpx_sessions"})

    def show_worker(self, *, name: str | None = None) -> CommandResult:
        args = ["--format", "json", "codex", "sessions", "show"]
        if name:
            args.append(name)
        result = self.runner(self._cmd(*args), 20.0)
        if result.returncode != 0:
            return self._error("acpx_worker_show_failed", "Unable to show acpx Codex worker metadata.", result)
        try:
            row = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return CommandResult(ok=False, errors=[make_error(code="acpx_json_parse_failed", message="Unable to parse acpx sessions show JSON.", guidance="Run acpx directly with --format json to inspect output.")])
        return CommandResult(ok=True, data={"worker": self._safe_worker(row)}, provenance={"source": "acpx_sessions", "name": name})

    def status(self, *, name: str | None = None) -> CommandResult:
        args = ["--format", "json", "codex", "status"]
        if name:
            args.extend(["--session", name])
        result = self.runner(self._cmd(*args), 20.0)
        if result.returncode != 0:
            return self._error("acpx_worker_status_failed", "Unable to read acpx Codex worker status.", result)
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            payload = {"raw": redact_value(result.stdout.strip())}
        return CommandResult(ok=True, data={"status": redact_value(payload)}, provenance={"source": "acpx_status", "name": name})

    def prompt(self, *, message: str, name: str | None = None, no_wait: bool = False, dry_run: bool = False, max_chars: int = 4000) -> CommandResult:
        preview, truncated = cap_text(redact_value(message), max_chars)
        args = ["--format", "json", "codex", "prompt"]
        if name:
            args.extend(["--session", name])
        if no_wait:
            args.append("--no-wait")
        args.extend(["--file", "-"])
        if dry_run:
            return CommandResult(ok=True, data={"would_prompt": True, "prompted": False, "session": name, "no_wait": no_wait, "message_preview": preview, "message_truncated": truncated, "command": self._cmd(*args)}, provenance={"source": "acpx_prompt", "dry_run": True, "name": name})
        try:
            completed = subprocess.run(self._cmd(*args), input=message, check=False, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return CommandResult(ok=False, data={"prompted": False, "session": name, "message_preview": preview}, errors=[make_error(code="acpx_prompt_timeout", message="acpx Codex prompt did not complete before timeout.", guidance="Use --no-wait for busy/long-running workers, then check acpx-worker-status/history.")], provenance={"source": "acpx_prompt", "dry_run": False, "name": name})
        if completed.returncode != 0:
            stderr_preview, stderr_truncated = cap_text(redact_value(completed.stderr.strip()), max_chars)
            return CommandResult(ok=False, data={"prompted": False, "session": name, "message_preview": preview, "stderr_preview": stderr_preview, "stderr_truncated": stderr_truncated}, errors=[make_error(code="acpx_prompt_failed", message="acpx Codex prompt exited non-zero.", guidance="Check stderr_preview and acpx-worker-status before retrying.")], provenance={"source": "acpx_prompt", "dry_run": False, "name": name})
        response = self._parse_json_or_text(completed.stdout)
        return CommandResult(ok=True, data={"prompted": True, "session": name, "no_wait": no_wait, "message_preview": preview, "message_truncated": truncated, "response": response}, provenance={"source": "acpx_prompt", "dry_run": False, "name": name})

    def history(self, *, name: str | None = None, limit: int = 20) -> CommandResult:
        args = ["--format", "json", "codex", "sessions", "history", "--limit", str(limit)]
        if name:
            args.append(name)
        result = self.runner(self._cmd(*args), 20.0)
        if result.returncode != 0:
            return self._error("acpx_history_failed", "Unable to read acpx Codex worker history.", result)
        return CommandResult(ok=True, data={"history": self._parse_json_or_text(result.stdout), "limit": limit, "session": name}, provenance={"source": "acpx_history", "name": name})

    def tail_events(self, *, record_id: str, max_events: int = 40) -> CommandResult:
        stream = self.sessions_dir / f"{record_id}.stream.ndjson"
        if not stream.exists():
            return CommandResult(ok=False, data={"record_id": record_id}, errors=[make_error(code="acpx_stream_missing", message="No acpx event stream was found for this record id.", guidance="Use acpx-worker-list to find acpxRecordId, then retry.")], provenance={"source": "acpx_stream", "record_id": record_id})
        events = []
        with stream.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events.append(self._safe_event(row))
        return CommandResult(ok=True, data={"record_id": record_id, "stream": str(stream), "events": events[-max_events:], "count": min(len(events), max_events), "max_events": max_events}, provenance={"source": "acpx_stream", "record_id": record_id})

    def _parse_json_or_text(self, text: str) -> Any:
        text = text.strip()
        if not text:
            return None
        try:
            return redact_value(json.loads(text))
        except json.JSONDecodeError:
            preview, truncated = cap_text(redact_value(text), 4000)
            return {"text": preview, "truncated": truncated}

    def _safe_worker(self, row: dict[str, Any]) -> dict[str, Any]:
        event_log = row.get("eventLog") if isinstance(row.get("eventLog"), dict) else {}
        return {
            "acpxRecordId": redact_value(row.get("acpxRecordId")),
            "acpSessionId": redact_value(row.get("acpSessionId")),
            "cwd": redact_value(row.get("cwd")),
            "closed": bool(row.get("closed")),
            "pid": redact_value(row.get("pid")),
            "title": redact_value(row.get("title")),
            "createdAt": redact_value(row.get("createdAt")),
            "lastUsedAt": redact_value(row.get("lastUsedAt")),
            "eventLog": {"active_path": redact_value(event_log.get("active_path")), "last_write_at": redact_value(event_log.get("last_write_at"))},
            "worker_kind": "acpx_background",
            "desktop_indexed": False,
        }

    def _safe_event(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        event_type = payload.get("type") or row.get("type")
        safe = {"type": redact_value(event_type), "timestamp": redact_value(row.get("timestamp") or payload.get("timestamp"))}
        for key in ("message", "text", "content"):
            if key in payload and isinstance(payload.get(key), str):
                safe[key], safe[f"{key}_truncated"] = cap_text(redact_value(payload[key]), 1200)
        return safe

    def _error(self, code: str, message: str, result: RunnerResult) -> CommandResult:
        stderr_preview, stderr_truncated = cap_text(redact_value(result.stderr.strip()), 4000)
        return CommandResult(ok=False, data={"stderr_preview": stderr_preview, "stderr_truncated": stderr_truncated}, errors=[make_error(code=code, message=message, guidance="Run the equivalent acpx command directly with --format json for debugging.")], provenance={"source": "acpx"})
