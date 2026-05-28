from __future__ import annotations

import json
import select
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..redaction import cap_text, redact_value
from ..schema import make_error
from ..types import CommandResult
from .codex_macos import RunnerResult, run_command

ALLOWED_APP_SERVER_METHODS = frozenset(
    {
        "initialize",
        "remoteControl/status/read",
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
        "remoteControl/enable",
        "remoteControl/disable",
        "remoteControl/approve",
        "remoteControl/deny",
    }
)

APP_BUNDLE_CODEX = Path("/Applications/Codex.app/Contents/Resources/codex")
CONTROL_SOCKET_CANDIDATES = (
    Path.home() / ".codex" / "app-server-control" / "app-server-control.sock",
    Path.home() / ".codex" / "app-server.sock",
)
APP_SERVER_TIMEOUT_SECONDS = 10.0
APP_SERVER_CLIENT_INFO = {
    "name": "evaos-desktop-bridge",
    "title": "evaOS Desktop Bridge",
    "version": "0.6.6",
}


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
        self._custom_rpc_client = rpc_client is not None
        self.rpc_client = rpc_client or self._stdio_rpc

    def status(self) -> CommandResult:
        selected_cli = self._preferred_cli()
        version = self.runner([selected_cli, "--version"], 5.0)
        help_result = self.runner([selected_cli, "app-server", "--help"], 5.0)
        cli_available = version.returncode == 0 and help_result.returncode == 0
        warnings: list[str] = []
        rpc_probe: CommandResult | None = None
        rpc_handshake_ok = False
        if cli_available:
            rpc_probe = self.request("thread/loaded/list", {"limit": 1}, cli=selected_cli)
            rpc_handshake_ok = rpc_probe.ok
            if not rpc_handshake_ok:
                warnings.append("Codex app-server RPC handshake failed.")
        else:
            warnings.append("Codex app-server CLI is unavailable or not on PATH")
        codex_version = redact_value(version.stdout.strip()) if version.returncode == 0 else None
        return CommandResult(
            ok=True,
            data={
                "available": cli_available and rpc_handshake_ok,
                "cli_available": cli_available,
                "rpc_handshake_ok": rpc_handshake_ok,
                "selected_cli": {
                    "path": redact_value(selected_cli),
                    "version": codex_version,
                },
                "codex_version": codex_version,
                "transport": "stdio",
                "allowed_methods": sorted(ALLOWED_APP_SERVER_METHODS),
                "forbidden_methods": sorted(FORBIDDEN_APP_SERVER_METHODS),
                "read_only": True,
                "rpc_probe": {
                    "method": "thread/loaded/list",
                    "ok": rpc_handshake_ok,
                    "errors": rpc_probe.errors if rpc_probe is not None and not rpc_probe.ok else [],
                },
            },
            warnings=warnings,
            provenance={"source": "app_server"},
        )

    def threads(self, *, max_items: int) -> CommandResult:
        response = self.request("thread/list", {"limit": max_items})
        if not response.ok:
            return response
        raw_threads = self._extract_thread_rows(response.data)
        threads = [self._safe_thread(row, index) for index, row in enumerate(raw_threads[:max_items])]
        return CommandResult(
            ok=True,
            data={
                "threads": threads,
                "count": len(threads),
                "max_items": max_items,
                "source": "app_server",
                "thread_state": "active" if threads else "idle",
            },
            warnings=response.warnings,
            provenance={"source": "app_server", "app_server_method": "thread/list"},
        )

    def remote_control_status(self) -> CommandResult:
        preferred_cli = self._preferred_cli()
        system_version = self._command_version(["codex", "--version"])
        app_bundle_version = self._command_version([str(APP_BUNDLE_CODEX), "--version"]) if APP_BUNDLE_CODEX.exists() else None
        remote_help = self.runner([preferred_cli, "remote-control", "--help"], 5.0)
        daemon_version = self.runner([preferred_cli, "app-server", "daemon", "version"], 5.0)
        control_sockets = [
            {"path": redact_value(path), "exists": path.exists()}
            for path in CONTROL_SOCKET_CANDIDATES
        ]
        status_read = self.request("remoteControl/status/read", {}, cli=preferred_cli)
        connections_state = self._connections_state(status_read.data if status_read.ok else None)
        data: dict[str, Any] = {
            "preferred_path": "codex_native_remote_control",
            "connections_state": connections_state,
            "system_cli": {
                "available": system_version is not None,
                "version": system_version,
            },
            "app_bundle_cli": {
                "path": redact_value(APP_BUNDLE_CODEX),
                "exists": APP_BUNDLE_CODEX.exists(),
                "version": app_bundle_version,
            },
            "remote_control_command": {
                "supported": remote_help.returncode == 0,
                "checked_cli": redact_value(preferred_cli),
            },
            "daemon": {
                "version_available": daemon_version.returncode == 0,
                "version_output": redact_value(daemon_version.stdout.strip()) if daemon_version.returncode == 0 else None,
            },
            "control_sockets": control_sockets,
            "remote_control_status_read": {
                "ok": status_read.ok,
                "data": status_read.data if status_read.ok else None,
                "errors": status_read.errors if not status_read.ok else [],
            },
            "safety": {
                "read_only_probe": True,
                "native_remote_control_preferred": True,
                "chatgpt_mediated_connections_status_only": True,
                "generic_app_server_mutations_exposed": False,
            },
        }
        warnings: list[str] = []
        if remote_help.returncode != 0:
            warnings.append("Codex native remote-control command was not detected; visible GUI fallback remains support-only and approval-gated.")
        if not any(item["exists"] for item in control_sockets):
            warnings.append("No Codex remote-control socket candidate is currently present.")
        return CommandResult(
            ok=True,
            data=data,
            warnings=warnings,
            provenance={"source": "codex_native_remote_control", "read_only": True},
        )

    def request(self, method: str, params: dict[str, Any] | None = None, *, cli: str = "codex") -> CommandResult:
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
        rpc = self.rpc_client(method, params or {}) if self._custom_rpc_client else self._stdio_rpc(method, params or {}, cli=cli)
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

    def _command_version(self, command: list[str]) -> str | None:
        result = self.runner(command, 5.0)
        if result.returncode != 0:
            return None
        return str(redact_value(result.stdout.strip())) or None

    def _preferred_cli(self) -> str:
        return str(APP_BUNDLE_CODEX) if APP_BUNDLE_CODEX.exists() else "codex"

    def _stdio_rpc(self, method: str, params: dict[str, Any], *, cli: str = "codex") -> JsonRpcResponse:
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                [cli, "app-server", "--listen", "stdio://"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            initialize = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": APP_SERVER_CLIENT_INFO,
                    "capabilities": {"experimentalApi": True},
                },
            }
            self._write_json_rpc(process, initialize)
            initialize_response = self._read_json_rpc_response(process, expected_id=1, timeout=APP_SERVER_TIMEOUT_SECONDS)
            if not initialize_response.ok:
                return initialize_response

            self._write_json_rpc(process, {"jsonrpc": "2.0", "method": "initialized"})
            if method == "initialize":
                return initialize_response

            request = {"jsonrpc": "2.0", "id": 2, "method": method, "params": params}
            self._write_json_rpc(process, request)
            return self._read_json_rpc_response(process, expected_id=2, timeout=APP_SERVER_TIMEOUT_SECONDS)
        except Exception as exc:
            return JsonRpcResponse(ok=False, error=str(exc))
        finally:
            self._close_stdio_process(process)

    def _write_json_rpc(self, process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
        if process.stdin is None:
            raise RuntimeError("codex app-server stdin is unavailable")
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()

    def _read_json_rpc_response(self, process: subprocess.Popen[str], *, expected_id: int, timeout: float) -> JsonRpcResponse:
        if process.stdout is None:
            return JsonRpcResponse(ok=False, error="codex app-server stdout is unavailable")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([process.stdout], [], [], min(remaining, 0.25))
            if not readable and process.poll() is not None:
                stderr = self._read_stderr(process)
                return JsonRpcResponse(ok=False, error=stderr or "codex app-server exited before returning a JSON-RPC response")
            if not readable:
                continue
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    stderr = self._read_stderr(process)
                    return JsonRpcResponse(ok=False, error=stderr or "codex app-server exited before returning a JSON-RPC response")
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("id") == expected_id:
                if "error" in payload:
                    return JsonRpcResponse(ok=False, error=str(redact_value(payload["error"])))
                return JsonRpcResponse(ok=True, payload=payload.get("result") or payload)
        return JsonRpcResponse(ok=False, error="Timed out waiting for Codex app-server JSON-RPC response")

    def _read_stderr(self, process: subprocess.Popen[str]) -> str:
        if process.stderr is None:
            return ""
        try:
            return str(redact_value(process.stderr.read().strip()))
        except Exception:
            return ""

    def _close_stdio_process(self, process: subprocess.Popen[str] | None) -> None:
        if process is None:
            return
        for stream in (process.stdin, process.stdout):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
        try:
            if process.stderr is not None:
                process.stderr.close()
        except Exception:
            pass

    def _extract_thread_rows(self, payload: dict[str, Any]) -> list[Any]:
        candidates = [
            payload.get("data"),
            payload.get("threads"),
            payload.get("items"),
        ]
        result = payload.get("result")
        if isinstance(result, dict):
            candidates.extend([result.get("data"), result.get("threads"), result.get("items")])
        for candidate in candidates:
            if isinstance(candidate, list):
                return candidate
        return []

    def _connections_state(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return "unavailable"
        raw_state = payload.get("status") or payload.get("state") or payload.get("connectionState")
        if not isinstance(raw_state, str):
            return "unavailable"
        normalized = raw_state.lower().replace("_", "-")
        if normalized in {"disabled", "connecting", "connected", "errored", "unavailable"}:
            return normalized
        return "unavailable"

    def _safe_thread(self, row: Any, index: int) -> dict[str, Any]:
        if not isinstance(row, dict):
            row = {"value": row}
        title = row.get("name") or row.get("title") or row.get("thread_name") or row.get("summary") or f"Thread {index + 1}"
        capped_title, title_truncated = cap_text(redact_value(title), 160)
        thread_id = row.get("id") or row.get("thread_id") or row.get("threadId")
        status = row.get("status") or row.get("state")
        updated_at = row.get("updated_at") or row.get("updatedAt")
        return {
            "index": index,
            "id": redact_value(thread_id),
            "title": capped_title,
            "title_truncated": title_truncated,
            "updated_at": None if updated_at is None else redact_value(str(updated_at)),
            "status": redact_value(status),
            "source": "app_server",
        }
