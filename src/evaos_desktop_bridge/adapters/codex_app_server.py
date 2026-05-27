from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import select
import shutil
import socket
import struct
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

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
CODEX_BIN_ENV = "EVAOS_CODEX_BIN"
TRANSPORT_ENV = "EVAOS_CODEX_APP_SERVER_TRANSPORT"
WS_URL_ENV = "EVAOS_CODEX_APP_SERVER_WS_URL"
SOCKET_PATH_ENV = "EVAOS_CODEX_APP_SERVER_SOCKET"
MESSAGE_MAX_CHARS = 8000
SUBSCRIBE_MAX_DURATION_MS = 30_000
SUBSCRIBE_MAX_EVENTS = 200
NOTIFICATION_METHODS = frozenset(
    {
        "turn/started",
        "item/agentMessage/delta",
        "turn/completed",
        "thread/status/changed",
        "remoteControl/status/changed",
    }
)


class JsonRpcTransport(Protocol):
    def send_json(self, payload: dict[str, Any]) -> None:
        ...

    def read_line(self, deadline: float) -> str | None:
        ...

    def close(self) -> None:
        ...


@dataclass
class JsonRpcResponse:
    ok: bool
    payload: Any = None
    error: str | None = None
    notifications: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class TransportConfig:
    mode: str
    cli: str
    ws_url: str | None = None
    socket_path: Path | None = None
    warnings: tuple[str, ...] = ()


class LineProcessTransport:
    def __init__(self, argv: list[str], *, timeout: float = 10.0) -> None:
        self.argv = argv
        self.process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.timeout = timeout

    def send_json(self, payload: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise RuntimeError("codex app-server stdin is unavailable")
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def read_line(self, deadline: float) -> str | None:
        if self.process.stdout is None:
            return None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            timeout = max(0.0, min(0.05, deadline - time.monotonic()))
            ready, _, _ = select.select([self.process.stdout], [], [], timeout)
            if ready:
                line = self.process.stdout.readline()
                if line:
                    return line.strip()
                break
        return None

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)


class WebSocketTransport:
    def __init__(self, url: str, *, timeout: float = 10.0) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "ws" or not _is_loopback_host(parsed.hostname):
            raise ValueError("Codex app-server websocket URLs must be loopback ws:// endpoints")
        if parsed.path not in {"", "/"}:
            raise ValueError("Codex app-server websocket URL must not include a path")
        port = parsed.port
        if port is None:
            raise ValueError("Codex app-server websocket URL must include a port")
        self.timeout = timeout
        self.sock = socket.create_connection((parsed.hostname or "127.0.0.1", port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._handshake(parsed.hostname or "127.0.0.1", port)

    def _handshake(self, host: str, port: int) -> None:
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096).decode("latin1", errors="replace")
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if " 101 " not in response or expected_accept not in response:
            raise RuntimeError("Codex app-server websocket handshake failed")

    def send_json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.sock.sendall(_build_websocket_frame(encoded, opcode=0x1))

    def read_line(self, deadline: float) -> str | None:
        while time.monotonic() < deadline:
            try:
                message = self._read_message(deadline)
            except TimeoutError:
                return None
            if message is not None:
                return message
        return None

    def _read_message(self, deadline: float) -> str | None:
        header = self._recv_exact(2, deadline)
        if header is None:
            raise TimeoutError
        first, second = header
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            extended = self._recv_exact(2, deadline)
            if extended is None:
                raise TimeoutError
            length = struct.unpack("!H", extended)[0]
        elif length == 127:
            extended = self._recv_exact(8, deadline)
            if extended is None:
                raise TimeoutError
            length = struct.unpack("!Q", extended)[0]
        mask_key = self._recv_exact(4, deadline) if masked else None
        payload = self._recv_exact(length, deadline) if length else b""
        if payload is None:
            raise TimeoutError
        if mask_key:
            payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            return None
        if opcode == 0x9:
            self.sock.sendall(_build_websocket_frame(payload, opcode=0xA))
            return None
        if opcode not in {0x1, 0x0}:
            return None
        return payload.decode("utf-8", errors="replace")

    def _recv_exact(self, size: int, deadline: float) -> bytes | None:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0 and time.monotonic() < deadline:
            self.sock.settimeout(max(0.01, deadline - time.monotonic()))
            chunk = self.sock.recv(remaining)
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining:
            return None
        return b"".join(chunks)

    def close(self) -> None:
        try:
            self.sock.sendall(_build_websocket_frame(b"", opcode=0x8))
        except OSError:
            pass
        self.sock.close()


def _build_websocket_frame(payload: bytes, *, opcode: int = 0x1, mask_key: bytes | None = None) -> bytes:
    key = mask_key or secrets.token_bytes(4)
    if len(key) != 4:
        raise ValueError("websocket mask key must be 4 bytes")
    first = 0x80 | (opcode & 0x0F)
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", first, 0x80 | length)
    elif length <= 0xFFFF:
        header = struct.pack("!BBH", first, 0x80 | 126, length)
    else:
        header = struct.pack("!BBQ", first, 0x80 | 127, length)
    masked = bytes(byte ^ key[index % 4] for index, byte in enumerate(payload))
    return header + key + masked


class CodexJsonRpcClient:
    def __init__(self, transport_factory: Callable[[], JsonRpcTransport], *, timeout: float = 10.0) -> None:
        self.transport_factory = transport_factory
        self.timeout = timeout
        self.transport: JsonRpcTransport | None = None
        self._next_id = 1
        self.notifications: list[dict[str, Any]] = []
        self.initialize_payload: Any = None

    def __enter__(self) -> CodexJsonRpcClient:
        self.transport = self.transport_factory()
        init_response = self._request_raw(
            "initialize",
            {
                "clientInfo": {"name": "evaos-desktop-bridge", "title": "evaOS Desktop Bridge", "version": "0.6.5"},
                "capabilities": {
                    "experimentalApi": True,
                    "requestAttestation": False,
                    "optOutNotificationMethods": [],
                },
            },
        )
        if not init_response.ok:
            raise RuntimeError(init_response.error or "Codex app-server initialize failed")
        self.initialize_payload = init_response.payload
        self._send_notification("initialized")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    def request(self, method: str, params: dict[str, Any] | None = None) -> JsonRpcResponse:
        return self._request_raw(method, params or {})

    def collect_notifications(self, *, duration_ms: int, max_events: int) -> list[dict[str, Any]]:
        if self.transport is None:
            raise RuntimeError("Codex JSON-RPC client is not connected")
        deadline = time.monotonic() + max(0, duration_ms) / 1000
        events: list[dict[str, Any]] = []
        while time.monotonic() < deadline and len(events) < max_events:
            line = self.transport.read_line(deadline)
            if line is None:
                continue
            payload = self._parse_payload(line)
            if payload is None:
                continue
            notification = self._notification_from_payload(payload)
            if notification is not None:
                self.notifications.append(notification)
                events.append(notification)
        return events

    def _send_notification(self, method: str) -> None:
        if self.transport is None:
            raise RuntimeError("Codex JSON-RPC client is not connected")
        self.transport.send_json({"jsonrpc": "2.0", "method": method})

    def _request_raw(self, method: str, params: dict[str, Any]) -> JsonRpcResponse:
        if self.transport is None:
            raise RuntimeError("Codex JSON-RPC client is not connected")
        request_id = self._next_id
        self._next_id += 1
        self.transport.send_json({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            line = self.transport.read_line(deadline)
            if line is None:
                continue
            payload = self._parse_payload(line)
            if payload is None:
                continue
            notification = self._notification_from_payload(payload)
            if notification is not None:
                self.notifications.append(notification)
                continue
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                return JsonRpcResponse(ok=False, error=str(redact_value(payload["error"])), notifications=list(self.notifications))
            if "result" in payload:
                return JsonRpcResponse(ok=True, payload=payload["result"], notifications=list(self.notifications))
            return JsonRpcResponse(ok=True, payload=payload, notifications=list(self.notifications))
        return JsonRpcResponse(ok=False, error=f"Timed out waiting for {method}", notifications=list(self.notifications))

    def _parse_payload(self, line: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _notification_from_payload(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        method = payload.get("method")
        if not isinstance(method, str) or "id" in payload:
            return None
        params = payload.get("params")
        return {
            "method": method,
            "params": params if isinstance(params, dict) else {},
        }


class CodexAppServerObserver:
    def __init__(
        self,
        *,
        runner: Callable[[list[str], float], RunnerResult] = run_command,
        rpc_client: Callable[[str, dict[str, Any]], JsonRpcResponse] | None = None,
    ) -> None:
        self.runner = runner
        self._custom_rpc_client = rpc_client is not None
        self.rpc_client = rpc_client

    def status(self) -> CommandResult:
        config = self._transport_config()
        version = self._run([config.cli, "--version"], 5.0)
        help_result = self._run([config.cli, "app-server", "--help"], 5.0)
        available = version.returncode == 0 and help_result.returncode == 0
        warnings = list(config.warnings)
        if not available:
            warnings.append("Codex app-server CLI is unavailable or not executable.")
        return CommandResult(
            ok=True,
            data={
                "available": available,
                "codex_version": redact_value(version.stdout.strip()) if version.returncode == 0 else None,
                "transport": config.mode,
                "websocket_url": redact_value(config.ws_url),
                "socket_path": redact_value(config.socket_path) if config.socket_path is not None else None,
                "allowed_methods": sorted(ALLOWED_APP_SERVER_METHODS),
                "controller_methods": sorted(CONTROLLER_APP_SERVER_METHODS),
                "forbidden_methods": sorted(FORBIDDEN_APP_SERVER_METHODS),
                "read_only": True,
            },
            warnings=warnings,
            provenance={"source": "app_server"},
        )

    def connections_status(self) -> CommandResult:
        config = self._transport_config()
        system_version = self._command_version(["codex", "--version"])
        app_bundle_version = self._command_version([str(APP_BUNDLE_CODEX), "--version"]) if APP_BUNDLE_CODEX.exists() else None
        remote_help = self._run([config.cli, "remote-control", "--help"], 5.0)
        daemon_version = self._run([config.cli, "app-server", "daemon", "version"], 5.0)
        control_sockets = [{"path": redact_value(path), "exists": path.exists()} for path in CONTROL_SOCKET_CANDIDATES]
        transport_status = self._probe_app_server(config)
        remote_status = self.request("remoteControl/status/read", {}, cli=config.cli)
        handshake_ok = transport_status.ok
        warnings = list(config.warnings)
        if remote_help.returncode != 0:
            warnings.append("Codex native remote-control command was not detected.")
        if config.mode == "websocket" and config.ws_url is None:
            warnings.append("Websocket transport selected but no loopback websocket URL is configured.")
        return CommandResult(
            ok=True,
            data={
                "desktop": {
                    "app_bundle_cli": {
                        "path": redact_value(APP_BUNDLE_CODEX),
                        "exists": APP_BUNDLE_CODEX.exists(),
                        "version": app_bundle_version,
                    },
                    "system_cli": {"available": system_version is not None, "version": system_version},
                },
                "app_server": {
                    "available": handshake_ok,
                    "preferred_cli": redact_value(config.cli),
                    "transport": config.mode,
                    "handshake": "ok" if handshake_ok else "unavailable",
                    "initialize": transport_status.data if transport_status.ok else None,
                    "error": transport_status.errors[0]["message"] if transport_status.errors else None,
                },
                "remote_control": {
                    "supported": remote_help.returncode == 0,
                    "status": remote_status.data if remote_status.ok else None,
                    "available": remote_status.ok,
                    "errors": remote_status.errors,
                },
                "remote_control_command": {
                    "supported": remote_help.returncode == 0,
                    "checked_cli": redact_value(config.cli),
                },
                "daemon": {
                    "version_available": daemon_version.returncode == 0,
                    "version_output": redact_value(daemon_version.stdout.strip()) if daemon_version.returncode == 0 else None,
                },
                "control_sockets": control_sockets,
                "websocket": {
                    "configured": config.ws_url is not None,
                    "url": redact_value(config.ws_url),
                    "loopback_only": True,
                    "ready": handshake_ok and config.mode == "websocket",
                },
                "live_notifications": {
                    "supported": True,
                    "methods": sorted(NOTIFICATION_METHODS),
                },
                "safety": {
                    "read_only_default": True,
                    "controller_requires_confirmation": True,
                    "controller_requires_source_audit_id": True,
                    "generic_app_server_passthrough": False,
                    "session_db_reads": False,
                },
            },
            warnings=warnings,
            provenance={"source": "app_server", "app_server_method": "initialize,remoteControl/status/read"},
        )

    def threads(self, *, max_items: int) -> CommandResult:
        response = self.request("thread/list", {"limit": max_items})
        if not response.ok:
            return response
        raw_threads = _extract_result_array(response.data, keys=("threads", "items", "data"))
        threads = [self._safe_thread(row, index) for index, row in enumerate(raw_threads[:max_items])]
        return CommandResult(
            ok=True,
            data={"threads": threads, "count": len(threads), "max_items": max_items, "source": "app_server"},
            warnings=response.warnings,
            provenance={"source": "app_server", "app_server_method": "thread/list"},
        )

    def loaded_threads(self, *, max_items: int) -> CommandResult:
        response = self.request("thread/loaded/list", {"limit": max_items})
        if not response.ok:
            return response
        raw_threads = _extract_result_array(response.data, keys=("threads", "items", "data"))
        threads = [
            {
                "index": index,
                "id": redact_value(_thread_id_from_loaded_row(row)),
                "source": "app_server_loaded",
            }
            for index, row in enumerate(raw_threads[:max_items])
        ]
        return CommandResult(
            ok=True,
            data={"threads": threads, "count": len(threads), "max_items": max_items, "source": "app_server"},
            warnings=response.warnings,
            provenance={"source": "app_server", "app_server_method": "thread/loaded/list"},
        )

    def subscribe(self, *, thread_id: str, duration_ms: int, max_chars: int = 4000) -> CommandResult:
        validation_error = self._validate_identifier("thread_id", thread_id)
        if validation_error is not None:
            return validation_error
        duration_ms = min(max(duration_ms, 1), SUBSCRIBE_MAX_DURATION_MS)
        if self._custom_rpc_client and self.rpc_client is not None:
            read_response = self.request("thread/read", {"threadId": thread_id, "includeTurns": False})
            if not read_response.ok:
                return read_response
            return CommandResult(
                ok=True,
                data={
                    "thread_id": redact_value(thread_id),
                    "duration_ms": duration_ms,
                    "events": [],
                    "event_count": 0,
                    "max_chars": max_chars,
                    "source": "app_server_read",
                },
                provenance={"source": "app_server", "app_server_method": "thread/read"},
            )
        config = self._transport_config()
        try:
            with self._json_rpc_client(config) as client:
                read_response = client.request("thread/read", {"threadId": thread_id, "includeTurns": False})
                if not read_response.ok:
                    return self._rpc_error_result("thread/read", read_response)
                events = client.collect_notifications(duration_ms=duration_ms, max_events=SUBSCRIBE_MAX_EVENTS)
        except Exception as exc:
            return self._exception_result("thread/read", exc)
        safe_events = [self._safe_event(event, max_chars=max_chars) for event in events]
        return CommandResult(
            ok=True,
            data={
                "thread_id": redact_value(thread_id),
                "duration_ms": duration_ms,
                "events": safe_events,
                "event_count": len(safe_events),
                "max_chars": max_chars,
                "source": "app_server_read",
            },
            provenance={"source": "app_server", "app_server_method": "thread/read"},
        )

    def remote_control_status(self) -> CommandResult:
        connections = self.connections_status()
        data = {
            "preferred_path": "codex_native_remote_control",
            **connections.data,
            "remote_control_status_read": {
                "ok": connections.data.get("remote_control", {}).get("available") is True,
                "data": connections.data.get("remote_control", {}).get("status"),
                "errors": connections.data.get("remote_control", {}).get("errors", []),
            },
            "safety": {
                **connections.data.get("safety", {}),
                "read_only_probe": True,
                "native_remote_control_preferred": True,
                "generic_app_server_mutations_exposed": False,
            },
        }
        return CommandResult(
            ok=True,
            data=data,
            warnings=connections.warnings,
            provenance={"source": "codex_native_remote_control", "read_only": True},
        )

    def request(self, method: str, params: dict[str, Any] | None = None, *, cli: str | None = None) -> CommandResult:
        if method not in ALLOWED_APP_SERVER_METHODS:
            return self._method_not_allowed_result(method)
        rpc = self._rpc(method, params or {}, cli=cli)
        if not rpc.ok:
            return self._rpc_error_result(method, rpc)
        return CommandResult(
            ok=True,
            data=redact_value(rpc.payload if isinstance(rpc.payload, dict) else {"result": rpc.payload}),
            provenance={"source": "app_server", "app_server_method": method},
        )

    def start_turn(
        self,
        *,
        thread_id: str,
        message: str,
        dry_run: bool,
        confirmed: bool,
        source_audit_id: str | None,
    ) -> CommandResult:
        params = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": message, "text_elements": []}],
        }
        return self._controller_request(
            method="turn/start",
            thread_id=thread_id,
            turn_id=None,
            message=message,
            params=params,
            dry_run=dry_run,
            confirmed=confirmed,
            source_audit_id=source_audit_id,
        )

    def steer_turn(
        self,
        *,
        thread_id: str,
        turn_id: str,
        message: str,
        dry_run: bool,
        confirmed: bool,
        source_audit_id: str | None,
    ) -> CommandResult:
        params = {
            "threadId": thread_id,
            "expectedTurnId": turn_id,
            "input": [{"type": "text", "text": message, "text_elements": []}],
        }
        return self._controller_request(
            method="turn/steer",
            thread_id=thread_id,
            turn_id=turn_id,
            message=message,
            params=params,
            dry_run=dry_run,
            confirmed=confirmed,
            source_audit_id=source_audit_id,
        )

    def interrupt_turn(
        self,
        *,
        thread_id: str,
        turn_id: str,
        dry_run: bool,
        confirmed: bool,
        source_audit_id: str | None,
    ) -> CommandResult:
        params = {"threadId": thread_id, "turnId": turn_id}
        return self._controller_request(
            method="turn/interrupt",
            thread_id=thread_id,
            turn_id=turn_id,
            message=None,
            params=params,
            dry_run=dry_run,
            confirmed=confirmed,
            source_audit_id=source_audit_id,
        )

    def _controller_request(
        self,
        *,
        method: str,
        thread_id: str,
        turn_id: str | None,
        message: str | None,
        params: dict[str, Any],
        dry_run: bool,
        confirmed: bool,
        source_audit_id: str | None,
    ) -> CommandResult:
        if method not in CONTROLLER_APP_SERVER_METHODS:
            return self._method_not_allowed_result(method)
        for field, value in [("thread_id", thread_id), ("turn_id", turn_id)]:
            if field == "turn_id" and method == "turn/start":
                continue
            validation_error = self._validate_identifier(field, value)
            if validation_error is not None:
                return validation_error
        message_preview: str | None = None
        message_truncated = False
        if message is not None:
            if not message.strip():
                return self._simple_error(
                    "message_required",
                    "Codex remote-control turn messages must be non-empty.",
                    "Pass an explicit --message value.",
                )
            message_preview, message_truncated = cap_text(redact_value(message), MESSAGE_MAX_CHARS)
            if message_truncated:
                return self._simple_error(
                    "message_too_long",
                    f"Codex remote-control messages are capped at {MESSAGE_MAX_CHARS} characters.",
                    "Shorten the message and retry.",
                )
        preview = {
            "method": method,
            "thread_id": redact_value(thread_id),
            "turn_id": redact_value(turn_id),
            "message_preview": message_preview,
            "dry_run": dry_run,
            "would_send": method in {"turn/start", "turn/steer"} and dry_run,
            "would_interrupt": method == "turn/interrupt" and dry_run,
            "sent": False,
            "interrupted": False,
            "source_audit_id": redact_value(source_audit_id),
        }
        if dry_run:
            return CommandResult(
                ok=True,
                data=preview,
                provenance={"source": "app_server", "app_server_method": method, "dry_run": True, "source_audit_id": source_audit_id},
            )
        gate_error = self._live_gate_error(confirmed=confirmed, source_audit_id=source_audit_id)
        if gate_error is not None:
            return gate_error
        loaded_error = self._loaded_thread_error(thread_id)
        if loaded_error is not None:
            return loaded_error
        rpc = self._rpc(method, params)
        if not rpc.ok:
            return self._rpc_error_result(method, rpc)
        return CommandResult(
            ok=True,
            data={
                **preview,
                "dry_run": False,
                "would_send": False,
                "would_interrupt": False,
                "sent": method in {"turn/start", "turn/steer"},
                "interrupted": method == "turn/interrupt",
                "response": redact_value(rpc.payload if isinstance(rpc.payload, dict) else {"result": rpc.payload}),
            },
            provenance={"source": "app_server", "app_server_method": method, "dry_run": False, "source_audit_id": source_audit_id},
        )

    def _rpc(self, method: str, params: dict[str, Any], *, cli: str | None = None) -> JsonRpcResponse:
        if self._custom_rpc_client and self.rpc_client is not None:
            return self.rpc_client(method, params)
        config = self._transport_config(cli=cli)
        try:
            with self._json_rpc_client(config) as client:
                return client.request(method, params)
        except Exception as exc:
            return JsonRpcResponse(ok=False, error=str(exc))

    def _probe_app_server(self, config: TransportConfig) -> CommandResult:
        if self._custom_rpc_client and self.rpc_client is not None:
            rpc = self.rpc_client("initialize", {})
            if not rpc.ok:
                return self._rpc_error_result("initialize", rpc)
            payload = rpc.payload if isinstance(rpc.payload, dict) else {"result": rpc.payload}
            return CommandResult(ok=True, data=redact_value(payload), provenance={"source": "app_server", "app_server_method": "initialize"})
        try:
            with self._json_rpc_client(config) as client:
                payload = client.initialize_payload if isinstance(client.initialize_payload, dict) else {"result": client.initialize_payload}
                return CommandResult(ok=True, data=redact_value(payload), provenance={"source": "app_server", "app_server_method": "initialize"})
        except Exception as exc:
            return self._rpc_error_result("initialize", JsonRpcResponse(ok=False, error=str(exc)))

    def _json_rpc_client(self, config: TransportConfig) -> CodexJsonRpcClient:
        return CodexJsonRpcClient(lambda: self._transport(config), timeout=10.0)

    def _transport(self, config: TransportConfig) -> JsonRpcTransport:
        if config.mode == "websocket":
            if config.ws_url is None:
                raise RuntimeError("No Codex app-server websocket URL configured")
            return WebSocketTransport(config.ws_url)
        if config.mode == "proxy":
            return LineProcessTransport([config.cli, "app-server", "proxy"])
        return LineProcessTransport([config.cli, "app-server", "--listen", "stdio://"])

    def _transport_config(self, *, cli: str | None = None) -> TransportConfig:
        warnings: list[str] = []
        preferred_cli = cli or self._resolve_codex_bin()
        mode = os.environ.get(TRANSPORT_ENV, "").strip().lower()
        ws_url = os.environ.get(WS_URL_ENV, "").strip() or None
        socket_value = os.environ.get(SOCKET_PATH_ENV, "").strip() or None
        socket_path = Path(socket_value).expanduser() if socket_value else None
        if mode and mode not in {"stdio", "proxy", "websocket"}:
            warnings.append(f"Ignoring invalid {TRANSPORT_ENV}={mode!r}; expected stdio, proxy, or websocket.")
            mode = ""
        if not mode:
            if ws_url:
                mode = "websocket"
            elif socket_path is not None:
                mode = "proxy"
            else:
                mode = "stdio"
        if ws_url is not None and not self._valid_loopback_ws_url(ws_url):
            warnings.append(f"Ignoring non-loopback {WS_URL_ENV}; only ws://127.0.0.1:PORT or ws://localhost:PORT is allowed.")
            ws_url = None
            if mode == "websocket":
                mode = "stdio"
        return TransportConfig(mode=mode, cli=preferred_cli, ws_url=ws_url, socket_path=socket_path, warnings=tuple(warnings))

    def _resolve_codex_bin(self) -> str:
        env_bin = os.environ.get(CODEX_BIN_ENV, "").strip()
        if env_bin:
            return env_bin
        if APP_BUNDLE_CODEX.exists():
            return str(APP_BUNDLE_CODEX)
        return shutil.which("codex") or "codex"

    def _command_version(self, command: list[str]) -> str | None:
        result = self._run(command, 5.0)
        if result.returncode != 0:
            return None
        return str(redact_value(result.stdout.strip())) or None

    def _run(self, command: list[str], timeout: float) -> RunnerResult:
        try:
            return self.runner(command, timeout)
        except FileNotFoundError as exc:
            return RunnerResult(returncode=127, stdout="", stderr=str(exc))

    def _safe_thread(self, row: Any, index: int) -> dict[str, Any]:
        if not isinstance(row, dict):
            row = {"value": row}
        title = row.get("name") or row.get("title") or row.get("thread_name") or row.get("summary") or row.get("preview") or f"Thread {index + 1}"
        capped_title, title_truncated = cap_text(str(redact_value(title)), 160)
        thread_id = row.get("id") or row.get("thread_id") or row.get("threadId")
        return {
            "index": index,
            "id": redact_value(thread_id),
            "title": capped_title,
            "title_truncated": title_truncated,
            "updated_at": redact_value(row.get("updated_at") or row.get("updatedAt")),
            "status": redact_value(row.get("status")),
            "source": "app_server",
        }

    def _safe_event(self, event: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
        params = redact_value(event.get("params", {}))
        text = json.dumps(params, sort_keys=True, default=str)
        capped, truncated = cap_text(text, max_chars)
        return {
            "method": redact_value(event.get("method")),
            "params_json": capped,
            "params_truncated": truncated,
            "source": "app_server_notification",
        }

    def _loaded_thread_error(self, thread_id: str) -> CommandResult | None:
        result = self.loaded_threads(max_items=500)
        if not result.ok:
            return CommandResult(
                ok=False,
                data={"thread_id": redact_value(thread_id)},
                errors=[
                    make_error(
                        code="codex_loaded_threads_unavailable",
                        message="Unable to verify the target Codex Desktop thread is currently loaded.",
                        guidance="Open the target thread in Codex Desktop and retry after a fresh connections status check.",
                    )
                ],
                provenance={"source": "app_server", "app_server_method": "thread/loaded/list"},
            )
        loaded_ids = {str(item.get("id")) for item in result.data.get("threads", []) if isinstance(item, dict)}
        if thread_id not in loaded_ids:
            return CommandResult(
                ok=False,
                data={"thread_id": redact_value(thread_id), "loaded_count": len(loaded_ids)},
                errors=[
                    make_error(
                        code="codex_thread_not_loaded",
                        message="The target thread is not in Codex Desktop's loaded-thread set.",
                        guidance="Open or select the thread visibly in Codex Desktop, then rerun the dry-run before live control.",
                    )
                ],
                provenance={"source": "app_server", "app_server_method": "thread/loaded/list"},
            )
        return None

    def _live_gate_error(self, *, confirmed: bool, source_audit_id: str | None) -> CommandResult | None:
        if not confirmed:
            return self._simple_error(
                "remote_control_confirmation_required",
                "Live Codex remote-control actions require --confirm.",
                "Rerun with --live --confirm --source-audit-id from a recent evidence or dry-run record.",
            )
        if not isinstance(source_audit_id, str) or not source_audit_id.strip().startswith("audit-"):
            return self._simple_error(
                "source_audit_id_required",
                "Live Codex remote-control actions require a source audit id.",
                "Run a read-only status/loaded-threads/dry-run command first, then pass its audit_id as --source-audit-id.",
            )
        return None

    def _validate_identifier(self, field: str, value: str | None) -> CommandResult | None:
        if not isinstance(value, str) or not value.strip():
            return self._simple_error(
                f"{field}_required",
                f"Codex remote-control requires an explicit {field.replace('_', ' ')}.",
                f"Pass --{field.replace('_', '-')} from a current Codex app-server observation.",
            )
        if len(value) > 240 or any(char.isspace() for char in value):
            return self._simple_error(
                f"{field}_invalid",
                f"Codex remote-control {field.replace('_', ' ')} is malformed.",
                "Use the exact id returned by loaded-threads or live notifications.",
            )
        return None

    def _method_not_allowed_result(self, method: str) -> CommandResult:
        return CommandResult(
            ok=False,
            errors=[
                make_error(
                    code="app_server_method_not_allowed",
                    message=f"Codex app-server method '{method}' is outside the read-only allowlist.",
                    guidance="Use only named bridge commands; generic app-server RPC passthrough is disabled.",
                )
            ],
            provenance={"source": "app_server", "app_server_method": method},
        )

    def _rpc_error_result(self, method: str, rpc: JsonRpcResponse) -> CommandResult:
        return CommandResult(
            ok=False,
            data={"method": method},
            errors=[
                make_error(
                    code="app_server_unavailable",
                    message=rpc.error or "Unable to read from Codex app-server.",
                    guidance="Ensure Codex Desktop is running and the selected app-server transport is reachable.",
                )
            ],
            provenance={"source": "app_server", "app_server_method": method},
        )

    def _exception_result(self, method: str, exc: Exception) -> CommandResult:
        return self._rpc_error_result(method, JsonRpcResponse(ok=False, error=str(exc)))

    def _simple_error(self, code: str, message: str, guidance: str) -> CommandResult:
        return CommandResult(ok=False, errors=[make_error(code=code, message=message, guidance=guidance)])

    def _valid_loopback_ws_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme == "ws" and parsed.port is not None and _is_loopback_host(parsed.hostname) and parsed.path in {"", "/"}


def _extract_result_array(payload: dict[str, Any], *, keys: tuple[str, ...]) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    result = payload.get("result")
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if isinstance(value, list):
                return value
    if isinstance(result, list):
        return result
    return []


def _thread_id_from_loaded_row(row: Any) -> Any:
    if isinstance(row, dict):
        return row.get("id") or row.get("thread_id") or row.get("threadId")
    return row


def _is_loopback_host(host: str | None) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return socket.gethostbyname(host or "") == "127.0.0.1"
    except OSError:
        return False
