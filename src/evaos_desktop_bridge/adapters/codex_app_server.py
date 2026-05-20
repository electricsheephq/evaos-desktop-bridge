from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import select
import socket
import subprocess
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable
from urllib.parse import urlparse

from ..redaction import cap_text, redact_value
from ..schema import make_error
from ..types import CommandResult
from .codex_macos import RunnerResult, run_command

APP_SERVER_WS_ENV = "EVAOS_DESKTOP_BRIDGE_CODEX_APP_SERVER_WS"
APP_SERVER_CLIENT_INFO = {"name": "evaos-desktop-bridge", "version": "0.1.0"}

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

CONTROLLER_APP_SERVER_METHODS = frozenset({"turn/start", "turn/steer", "turn/interrupt"})

FORBIDDEN_APP_SERVER_METHODS = frozenset(
    {
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

EXPECTED_APP_SERVER_NOTIFICATIONS = frozenset(
    {
        "thread/status/changed",
        "turn/started",
        "turn/completed",
        "item/agentMessage/delta",
        "serverRequest/resolved",
        "remoteControl/status/changed",
    }
)


@dataclass
class JsonRpcResponse:
    ok: bool
    payload: Any | None = None
    error: str | None = None
    notifications: list[dict[str, Any]] | None = None


def extract_generated_protocol_methods(source: str) -> set[str]:
    return set(re.findall(r'"method"\s*:\s*"([^"]+)"', source))


def classify_app_server_method(method: str) -> str:
    if method in ALLOWED_APP_SERVER_METHODS:
        return "read_only"
    if method in CONTROLLER_APP_SERVER_METHODS:
        return "guarded_controller"
    if method in FORBIDDEN_APP_SERVER_METHODS:
        return "forbidden"
    return "unknown"


class JsonRpcTransport:
    def send(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    def recv(self, timeout: float) -> dict[str, Any] | None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class LineProcessTransport(JsonRpcTransport):
    def __init__(self, argv: list[str] | None = None) -> None:
        self.process = subprocess.Popen(
            argv or ["codex", "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def send(self, payload: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise RuntimeError("Codex app-server stdin is closed")
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def recv(self, timeout: float) -> dict[str, Any] | None:
        if self.process.stdout is None:
            return None
        ready, _, _ = select.select([self.process.stdout], [], [], max(timeout, 0.0))
        if not ready:
            return None
        line = self.process.stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"method": "warning", "params": {"message": line.strip()}}

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()


class LoopbackWebSocketTransport(JsonRpcTransport):
    def __init__(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "ws":
            raise ValueError("Only ws:// loopback app-server URLs are supported by this bridge lane.")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Only loopback websocket app-server URLs are allowed.")
        self.url = url
        self.socket = socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=5)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        host = parsed.netloc
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        response = self._read_http_response()
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
        if b" 101 " not in response or accept.encode("ascii") not in response:
            raise RuntimeError("Codex app-server websocket handshake failed")

    def send(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.socket.sendall(self._client_text_frame(body))

    def recv(self, timeout: float) -> dict[str, Any] | None:
        self.socket.settimeout(max(timeout, 0.001))
        try:
            opcode, body = self._read_frame()
        except socket.timeout:
            return None
        if opcode == 0x8:
            return None
        if opcode == 0x9:
            self.socket.sendall(bytes([0x8A, len(body)]) + body)
            return None
        if opcode != 0x1:
            return None
        return json.loads(body.decode("utf-8"))

    def close(self) -> None:
        try:
            self.socket.close()
        except OSError:
            pass

    def _read_http_response(self) -> bytes:
        chunks: list[bytes] = []
        while b"\r\n\r\n" not in b"".join(chunks):
            chunk = self.socket.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def _read_exact(self, length: int) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            chunk = self.socket.recv(remaining)
            if not chunk:
                raise RuntimeError("websocket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_frame(self) -> tuple[int, bytes]:
        header = self._read_exact(2)
        opcode = header[0] & 0x0F
        masked = (header[1] & 0x80) != 0
        length = header[1] & 0x7F
        if length == 126:
            length = int.from_bytes(self._read_exact(2), "big")
        elif length == 127:
            length = int.from_bytes(self._read_exact(8), "big")
        mask = self._read_exact(4) if masked else b""
        body = self._read_exact(length)
        if masked:
            body = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
        return opcode, body

    def _client_text_frame(self, body: bytes) -> bytes:
        mask = secrets.token_bytes(4)
        length = len(body)
        if length < 126:
            header = bytes([0x81, 0x80 | length])
        elif length < 65536:
            header = bytes([0x81, 0x80 | 126]) + length.to_bytes(2, "big")
        else:
            header = bytes([0x81, 0x80 | 127]) + length.to_bytes(8, "big")
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
        return header + mask + masked


class CodexJsonRpcClient:
    def __init__(
        self,
        *,
        transport_factory: Callable[[], JsonRpcTransport],
        request_timeout: float = 10.0,
        client_info: dict[str, str] | None = None,
    ) -> None:
        self.transport_factory = transport_factory
        self.request_timeout = request_timeout
        self.client_info = client_info or APP_SERVER_CLIENT_INFO
        self.transport: JsonRpcTransport | None = None
        self.next_id = 1

    def __enter__(self) -> "CodexJsonRpcClient":
        self.transport = self.transport_factory()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    def initialize(self) -> JsonRpcResponse:
        response = self.request(
            "initialize",
            {"clientInfo": self.client_info, "capabilities": {"experimentalApi": True}},
        )
        if response.ok:
            self.notify("initialized")
        return response

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self.transport is None:
            raise RuntimeError("Codex app-server client is not open")
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self.transport.send(payload)

    def request(self, method: str, params: dict[str, Any] | None = None, *, timeout: float | None = None) -> JsonRpcResponse:
        if self.transport is None:
            raise RuntimeError("Codex app-server client is not open")
        request_id = self.next_id
        self.next_id += 1
        self.transport.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        return self._wait_for_response(request_id, timeout or self.request_timeout)

    def collect_notifications(self, *, duration_ms: int, max_events: int) -> list[dict[str, Any]]:
        if self.transport is None:
            raise RuntimeError("Codex app-server client is not open")
        deadline = monotonic() + (duration_ms / 1000)
        events: list[dict[str, Any]] = []
        while monotonic() < deadline and len(events) < max_events:
            payload = self.transport.recv(min(0.2, max(deadline - monotonic(), 0.001)))
            if payload and "method" in payload and "id" not in payload:
                events.append(payload)
        return events

    def _wait_for_response(self, request_id: int, timeout: float) -> JsonRpcResponse:
        deadline = monotonic() + timeout
        notifications: list[dict[str, Any]] = []
        while monotonic() < deadline:
            if self.transport is None:
                return JsonRpcResponse(ok=False, error="Codex app-server transport closed")
            payload = self.transport.recv(min(0.2, max(deadline - monotonic(), 0.001)))
            if payload is None:
                continue
            if payload.get("id") == request_id:
                if "error" in payload:
                    return JsonRpcResponse(ok=False, error=str(redact_value(payload["error"])), notifications=notifications)
                result_payload = payload["result"] if "result" in payload else payload
                return JsonRpcResponse(ok=True, payload=result_payload, notifications=notifications)
            if "method" in payload and "id" not in payload:
                notifications.append(payload)
        return JsonRpcResponse(ok=False, error="Timed out waiting for Codex app-server response", notifications=notifications)


class CodexAppServerObserver:
    def __init__(
        self,
        *,
        runner: Callable[[list[str], float], RunnerResult] = run_command,
        rpc_client: Callable[[str, dict[str, Any]], JsonRpcResponse] | None = None,
        subscription_client: Callable[[str, int, int, int], JsonRpcResponse] | None = None,
    ) -> None:
        self.runner = runner
        self.rpc_client = rpc_client or self._client_rpc
        self.subscription_client = subscription_client or self._client_subscribe

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
                "controller_methods": sorted(CONTROLLER_APP_SERVER_METHODS),
                "forbidden_methods": sorted(FORBIDDEN_APP_SERVER_METHODS),
                "read_only": True,
            },
            warnings=warnings,
            provenance={"source": "app_server"},
        )

    def connections_status(self, *, desktop_status: CommandResult | None = None) -> CommandResult:
        status = self.status()
        features = self.runner(["codex", "features", "list"], 5.0)
        desktop = self.runner(["pgrep", "-x", "Codex"], 5.0)
        help_text = json.dumps(status.data)
        feature_state = self._feature_state(features.stdout, "remote_control") if features.returncode == 0 else None
        websocket_env = os.environ.get(APP_SERVER_WS_ENV)
        desktop_data = desktop_status.data.get("app") if desktop_status is not None and desktop_status.ok else None
        data = {
            "desktop": {
                "installed": desktop_data.get("installed") if isinstance(desktop_data, dict) else None,
                "running": desktop_data.get("running") if isinstance(desktop_data, dict) else desktop.returncode == 0,
                "pid": desktop_data.get("pid") if isinstance(desktop_data, dict) else None,
                "pid_count": len([line for line in desktop.stdout.splitlines() if line.strip()]) if desktop.returncode == 0 else 0,
            },
            "app_server": {
                "available": bool(status.data.get("available")),
                "codex_version": status.data.get("codex_version"),
                "stdio_supported": True,
                "websocket_listen_supported": "ws://IP:PORT" in (self.runner(["codex", "app-server", "--help"], 5.0).stdout),
                "loopback_websocket_configured": bool(websocket_env),
                "loopback_websocket_url": redact_value(websocket_env) if websocket_env else None,
                "allowlist_size": len(ALLOWED_APP_SERVER_METHODS),
                "controller_size": len(CONTROLLER_APP_SERVER_METHODS),
            },
            "remote_control": {
                "feature_state": feature_state,
                "enabled": feature_state.get("enabled") if isinstance(feature_state, dict) else False,
                "notification_method": "remoteControl/status/changed",
            },
            "live_notifications": {
                "expected_methods": sorted(EXPECTED_APP_SERVER_NOTIFICATIONS),
                "subscribe_command": "codex.app_server.subscribe",
            },
            "safety": {
                "default_mode": "read_only",
                "controller_requires_confirmation": True,
                "generic_rpc_passthrough": False,
            },
        }
        return CommandResult(
            ok=status.ok,
            data=redact_value(data),
            warnings=status.warnings,
            errors=status.errors,
            provenance={"source": "app_server_connections", "feature_probe": features.returncode == 0, "status_probe": help_text is not None},
        )

    def threads(self, *, max_items: int) -> CommandResult:
        response = self.request("thread/list", {"limit": max_items})
        if not response.ok:
            return response
        raw_threads = (
            response.data.get("threads")
            or response.data.get("items")
            or response.data.get("data")
            or response.data.get("result", {}).get("threads")
            or response.data.get("result", {}).get("data")
            or []
        )
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
            warnings=[self._notification_warning(rpc.notifications)] if rpc.notifications else [],
            provenance={"source": "app_server", "app_server_method": method},
        )

    def subscribe(self, *, thread_id: str, duration_ms: int, max_events: int = 40, max_chars: int = 4000) -> CommandResult:
        rpc = self.subscription_client(thread_id, duration_ms, max_events, max_chars)
        if not rpc.ok:
            return CommandResult(
                ok=False,
                data={"thread_id": thread_id, "duration_ms": duration_ms},
                errors=[make_error(code="app_server_subscribe_failed", message=rpc.error or "Unable to subscribe to Codex app-server notifications.", guidance="Check Codex app-server availability and retry with a short duration.")],
                provenance={"source": "app_server_notifications", "app_server_method": "thread/read"},
            )
        raw_events = (rpc.payload or {}).get("events") or []
        events = [self._safe_event(event, max_chars=max_chars) for event in raw_events[:max_events]]
        return CommandResult(
            ok=True,
            data={"thread_id": thread_id, "duration_ms": duration_ms, "events": events, "count": len(events), "max_events": max_events},
            provenance={"source": "app_server_notifications", "app_server_method": "thread/read"},
        )

    def start_turn(
        self,
        *,
        thread_id: str,
        message: str,
        dry_run: bool,
        source_audit_id: str | None = None,
        confirmed: bool = False,
        max_chars: int = 4000,
    ) -> CommandResult:
        preview, truncated = cap_text(redact_value(message), max_chars)
        params = self._turn_input_params(thread_id=thread_id, message=message, source_audit_id=source_audit_id)
        if dry_run:
            return CommandResult(
                ok=True,
                data={"would_start_turn": True, "started": False, "thread_id": thread_id, "method": "turn/start", "params_preview": redact_value(params), "message_preview": preview, "message_truncated": truncated},
                provenance={"source": "app_server_controller", "app_server_method": "turn/start", "dry_run": True, "thread_id": thread_id, "source_audit_id": source_audit_id},
            )
        gate = self._controller_gate(source_audit_id=source_audit_id, confirmed=confirmed)
        if gate is not None:
            return gate
        rpc = self.rpc_client("turn/start", params)
        if not rpc.ok:
            return self._controller_error(method="turn/start", thread_id=thread_id, error=rpc.error)
        return CommandResult(
            ok=True,
            data={"would_start_turn": False, "started": True, "thread_id": thread_id, "method": "turn/start", "response": redact_value(rpc.payload or {}), "message_preview": preview, "message_truncated": truncated, "notifications": [self._safe_event(event, max_chars=max_chars) for event in (rpc.notifications or [])]},
            provenance={"source": "app_server_controller", "app_server_method": "turn/start", "dry_run": False, "thread_id": thread_id, "source_audit_id": source_audit_id},
        )

    def steer_turn(
        self,
        *,
        thread_id: str,
        turn_id: str | None,
        message: str,
        dry_run: bool,
        source_audit_id: str | None = None,
        confirmed: bool = False,
        max_chars: int = 4000,
    ) -> CommandResult:
        preview, truncated = cap_text(redact_value(message), max_chars)
        params = {**self._turn_input_params(thread_id=thread_id, message=message, source_audit_id=source_audit_id), "expectedTurnId": turn_id or ""}
        if dry_run:
            return CommandResult(
                ok=True,
                data={"would_steer_turn": True, "steered": False, "thread_id": thread_id, "turn_id": turn_id, "method": "turn/steer", "params_preview": redact_value(params), "message_preview": preview, "message_truncated": truncated},
                provenance={"source": "app_server_controller", "app_server_method": "turn/steer", "dry_run": True, "thread_id": thread_id, "turn_id": turn_id, "source_audit_id": source_audit_id},
            )
        gate = self._controller_gate(source_audit_id=source_audit_id, confirmed=confirmed, turn_id=turn_id or "")
        if gate is not None:
            return gate
        rpc = self.rpc_client("turn/steer", params)
        if not rpc.ok:
            return self._controller_error(method="turn/steer", thread_id=thread_id, turn_id=turn_id, error=rpc.error)
        return CommandResult(
            ok=True,
            data={"would_steer_turn": False, "steered": True, "thread_id": thread_id, "turn_id": turn_id, "method": "turn/steer", "response": redact_value(rpc.payload or {}), "message_preview": preview, "message_truncated": truncated, "notifications": [self._safe_event(event, max_chars=max_chars) for event in (rpc.notifications or [])]},
            provenance={"source": "app_server_controller", "app_server_method": "turn/steer", "dry_run": False, "thread_id": thread_id, "turn_id": turn_id, "source_audit_id": source_audit_id},
        )

    def interrupt_turn(
        self,
        *,
        thread_id: str,
        turn_id: str | None,
        dry_run: bool,
        source_audit_id: str | None = None,
        confirmed: bool = False,
    ) -> CommandResult:
        params = {"threadId": thread_id, "turnId": turn_id or ""}
        if dry_run:
            return CommandResult(
                ok=True,
                data={"would_interrupt_turn": True, "interrupted": False, "thread_id": thread_id, "turn_id": turn_id, "method": "turn/interrupt", "params_preview": redact_value(params)},
                provenance={"source": "app_server_controller", "app_server_method": "turn/interrupt", "dry_run": True, "thread_id": thread_id, "turn_id": turn_id, "source_audit_id": source_audit_id},
            )
        gate = self._controller_gate(source_audit_id=source_audit_id, confirmed=confirmed, turn_id=turn_id or "")
        if gate is not None:
            return gate
        rpc = self.rpc_client("turn/interrupt", params)
        if not rpc.ok:
            return self._controller_error(method="turn/interrupt", thread_id=thread_id, turn_id=turn_id, error=rpc.error)
        return CommandResult(
            ok=True,
            data={"would_interrupt_turn": False, "interrupted": True, "thread_id": thread_id, "turn_id": turn_id, "method": "turn/interrupt", "response": redact_value(rpc.payload or {}), "notifications": [self._safe_event(event, max_chars=4000) for event in (rpc.notifications or [])]},
            provenance={"source": "app_server_controller", "app_server_method": "turn/interrupt", "dry_run": False, "thread_id": thread_id, "turn_id": turn_id, "source_audit_id": source_audit_id},
        )

    def _client_rpc(self, method: str, params: dict[str, Any]) -> JsonRpcResponse:
        try:
            with CodexJsonRpcClient(transport_factory=self._transport_factory) as client:
                if method == "initialize":
                    return client.initialize()
                init = client.initialize()
                if not init.ok:
                    return init
                return client.request(method, params)
        except Exception as exc:
            return JsonRpcResponse(ok=False, error=str(exc))

    def _client_subscribe(self, thread_id: str, duration_ms: int, max_events: int, max_chars: int) -> JsonRpcResponse:
        try:
            with CodexJsonRpcClient(transport_factory=self._transport_factory) as client:
                init = client.initialize()
                if not init.ok:
                    return init
                read = client.request("thread/read", {"threadId": thread_id})
                events = list(init.notifications or []) + list(read.notifications or [])
                events.extend(client.collect_notifications(duration_ms=duration_ms, max_events=max_events))
                return JsonRpcResponse(ok=True, payload={"initial": read.payload, "events": events[:max_events]}, notifications=events[:max_events])
        except Exception as exc:
            return JsonRpcResponse(ok=False, error=str(exc))

    def _transport_factory(self) -> JsonRpcTransport:
        websocket_url = os.environ.get(APP_SERVER_WS_ENV)
        if websocket_url:
            return LoopbackWebSocketTransport(websocket_url)
        return LineProcessTransport()

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

    def _safe_event(self, event: Any, *, max_chars: int) -> dict[str, Any]:
        if not isinstance(event, dict):
            event = {"method": "unknown", "params": {"value": event}}
        method = str(event.get("method") or "unknown")
        params, truncated = self._cap_payload_strings(redact_value(event.get("params") or {}), max_chars=max_chars)
        return {"method": method, "params": params, "expected": method in EXPECTED_APP_SERVER_NOTIFICATIONS, "truncated": truncated}

    def _cap_payload_strings(self, value: Any, *, max_chars: int) -> tuple[Any, bool]:
        if isinstance(value, str):
            capped, truncated = cap_text(value, max_chars)
            return capped, truncated
        if isinstance(value, list):
            capped_items = []
            truncated_any = False
            for item in value:
                capped, truncated = self._cap_payload_strings(item, max_chars=max_chars)
                capped_items.append(capped)
                truncated_any = truncated_any or truncated
            return capped_items, truncated_any
        if isinstance(value, dict):
            capped_dict: dict[str, Any] = {}
            truncated_any = False
            for key, item in value.items():
                capped, truncated = self._cap_payload_strings(item, max_chars=max_chars)
                capped_dict[str(key)] = capped
                truncated_any = truncated_any or truncated
            return capped_dict, truncated_any
        return value, False

    def _turn_input_params(self, *, thread_id: str, message: str, source_audit_id: str | None) -> dict[str, Any]:
        metadata = {"source": "evaos-desktop-bridge"}
        if source_audit_id:
            metadata["source_audit_id"] = source_audit_id
        return {
            "threadId": thread_id,
            "input": [{"type": "text", "text": message, "text_elements": []}],
            "responsesapiClientMetadata": metadata,
        }

    def _controller_gate(self, *, source_audit_id: str | None, confirmed: bool, turn_id: str | None = None) -> CommandResult | None:
        if not confirmed or not source_audit_id:
            return CommandResult(
                ok=False,
                errors=[
                    make_error(
                        code="controller_confirmation_required",
                        message="Live Codex app-server controller actions require --confirm and --source-audit-id.",
                        guidance="Run the same command with --dry-run first, then retry live with an audit id and explicit confirmation.",
                    )
                ],
                provenance={"source": "app_server_controller", "dry_run": False, "source_audit_id": source_audit_id},
            )
        if not source_audit_id.startswith("audit-"):
            return CommandResult(
                ok=False,
                errors=[
                    make_error(
                        code="invalid_source_audit_id",
                        message="source_audit_id must reference an existing bridge audit id.",
                        guidance="Use an audit id returned by a prior dry-run or observer command.",
                    )
                ],
                provenance={"source": "app_server_controller", "dry_run": False, "source_audit_id": source_audit_id},
            )
        if turn_id is not None and (not isinstance(turn_id, str) or not turn_id.strip()):
            return CommandResult(
                ok=False,
                errors=[
                    make_error(
                        code="active_turn_required",
                        message="This controller action requires the active Codex turn id.",
                        guidance="Use live-status/subscribe to identify the active turn before retrying.",
                    )
                ],
                provenance={"source": "app_server_controller", "dry_run": False, "source_audit_id": source_audit_id},
            )
        return None

    def _controller_error(self, *, method: str, thread_id: str, error: str | None, turn_id: str | None = None) -> CommandResult:
        return CommandResult(
            ok=False,
            data={"thread_id": thread_id, "turn_id": turn_id, "method": method},
            errors=[
                make_error(
                    code="app_server_controller_failed",
                    message=error or f"Codex app-server controller method {method} failed.",
                    guidance="Check Codex Desktop/app-server connection status and retry from a fresh dry-run.",
                )
            ],
            provenance={"source": "app_server_controller", "app_server_method": method, "dry_run": False, "thread_id": thread_id, "turn_id": turn_id},
        )

    def _feature_state(self, output: str, feature: str) -> dict[str, Any] | None:
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == feature:
                return {"name": parts[0], "stage": " ".join(parts[1:-1]), "enabled": parts[-1].lower() == "true", "raw": redact_value(line)}
        return None

    def _notification_warning(self, notifications: list[dict[str, Any]] | None) -> str:
        return f"Codex app-server returned {len(notifications or [])} notification(s) before the requested response."
