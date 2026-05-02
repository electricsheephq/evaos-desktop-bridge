from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from ..redaction import cap_text, redact_value
from ..schema import make_error
from ..types import CommandResult
from .codex_macos import RunnerResult, run_command

ALLOWED_APP_SERVER_METHODS = frozenset(
    {
        "initialize",
        "thread/list",
        "thread/loaded/list",
        "thread/read",
        "thread/turns/list",
        "getConversationSummary",
    }
)

FORBIDDEN_APP_SERVER_METHODS = frozenset(
    {
        "turn/start",
        "turn/steer",
        "turn/interrupt",
        "thread/inject_items",
        "thread/start",
        "thread/resume",
        "thread/fork",
        "thread/rollback",
        "thread/compact/start",
        "thread/shellCommand",
        "command/exec",
        "command/exec/write",
        "command/exec/terminate",
        "fs/writeFile",
        "fs/remove",
        "config/value/write",
        "config/batchWrite",
        "plugin/install",
        "plugin/uninstall",
        "account/login/start",
        "account/logout",
    }
)


@dataclass
class JsonRpcResponse:
    ok: bool
    payload: dict[str, Any] | None = None
    error: str | None = None


class CodexAppServerObserver:
    def __init__(
        self,
        *,
        runner: Callable[[list[str], float], RunnerResult] = run_command,
        rpc_client: Callable[[str, dict[str, Any]], JsonRpcResponse] | None = None,
    ) -> None:
        self.runner = runner
        self.rpc_client = rpc_client or self._stdio_rpc

    def status(self) -> CommandResult:
        version = self.runner(["codex", "--version"], 5.0)
        help_result = self.runner(["codex", "app-server", "--help"], 5.0)
        available = version.returncode == 0 and help_result.returncode == 0
        warnings: list[str] = []
        if not available:
            warnings.append("Codex app-server CLI is unavailable or not on PATH")
        return CommandResult(
            ok=True,
            data={
                "available": available,
                "codex_version": redact_value(version.stdout.strip()) if version.returncode == 0 else None,
                "transport": "stdio",
                "allowed_methods": sorted(ALLOWED_APP_SERVER_METHODS),
                "forbidden_methods": sorted(FORBIDDEN_APP_SERVER_METHODS),
                "read_only": True,
            },
            warnings=warnings,
            provenance={"source": "app_server"},
        )

    def threads(self, *, max_items: int) -> CommandResult:
        response = self.request("thread/list", {"limit": max_items})
        if not response.ok:
            return response
        raw_threads = response.data.get("threads") or response.data.get("items") or response.data.get("result", {}).get("threads") or []
        threads = [self._safe_thread(row, index) for index, row in enumerate(raw_threads[:max_items])]
        return CommandResult(
            ok=True,
            data={"threads": threads, "count": len(threads), "max_items": max_items, "source": "app_server"},
            warnings=response.warnings,
            provenance={"source": "app_server", "app_server_method": "thread/list"},
        )

    def request(self, method: str, params: dict[str, Any] | None = None) -> CommandResult:
        if method not in ALLOWED_APP_SERVER_METHODS:
            return CommandResult(
                ok=False,
                errors=[
                    make_error(
                        code="app_server_method_not_allowed",
                        message=f"Codex app-server method '{method}' is outside the read-only allowlist.",
                        guidance="Use only read-only app-server methods exposed by evaos-desktop-bridge.",
                    )
                ],
                provenance={"source": "app_server", "app_server_method": method},
            )
        rpc = self.rpc_client(method, params or {})
        if not rpc.ok:
            return CommandResult(
                ok=False,
                data={"method": method},
                errors=[
                    make_error(
                        code="app_server_unavailable",
                        message=rpc.error or "Unable to read from Codex app-server.",
                        guidance="Ensure the installed codex CLI supports `codex app-server --listen stdio://`; live attach remains read-only.",
                    )
                ],
                provenance={"source": "app_server", "app_server_method": method},
            )
        return CommandResult(
            ok=True,
            data=redact_value(rpc.payload or {}),
            provenance={"source": "app_server", "app_server_method": method},
        )

    def _stdio_rpc(self, method: str, params: dict[str, Any]) -> JsonRpcResponse:
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        try:
            completed = subprocess.run(
                ["codex", "app-server", "--listen", "stdio://"],
                input=json.dumps(request) + "\n",
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as exc:
            return JsonRpcResponse(ok=False, error=str(exc))
        if completed.returncode != 0:
            return JsonRpcResponse(ok=False, error=completed.stderr.strip() or "codex app-server exited non-zero")
        for line in completed.stdout.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("id") == 1:
                if "error" in payload:
                    return JsonRpcResponse(ok=False, error=str(redact_value(payload["error"])))
                return JsonRpcResponse(ok=True, payload=payload.get("result") or payload)
        return JsonRpcResponse(ok=False, error="No JSON-RPC response returned by codex app-server")

    def _safe_thread(self, row: Any, index: int) -> dict[str, Any]:
        if not isinstance(row, dict):
            row = {"value": row}
        title = row.get("name") or row.get("title") or row.get("thread_name") or row.get("summary") or f"Thread {index + 1}"
        capped_title, title_truncated = cap_text(redact_value(title), 160)
        thread_id = row.get("id") or row.get("thread_id") or row.get("threadId")
        return {
            "index": index,
            "id": redact_value(thread_id),
            "title": capped_title,
            "title_truncated": title_truncated,
            "updated_at": redact_value(row.get("updated_at") or row.get("updatedAt")),
            "source": "app_server",
        }
