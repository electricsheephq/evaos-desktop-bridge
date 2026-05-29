from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import select
import signal
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
CODEX_BIN_ENV = "EVAOS_CODEX_BIN"
TRANSPORT_ENV = "EVAOS_CODEX_APP_SERVER_TRANSPORT"
WS_URL_ENV = "EVAOS_CODEX_APP_SERVER_WS_URL"
SOCKET_PATH_ENV = "EVAOS_CODEX_APP_SERVER_SOCKET"
IDENTIFIER_MAX_CHARS = 240
STATUS_MAX_CHARS = 1000
EVENT_METHOD_MAX_CHARS = 160
SUBSCRIBE_MAX_DURATION_MS = 30_000
SUBSCRIBE_MAX_EVENTS = 200
APP_SERVER_TIMEOUT_SECONDS = 10.0
APP_SERVER_CLIENT_INFO = {
    "name": "evaos-desktop-bridge",
    "title": "evaOS Desktop Bridge",
    "version": "0.6.6",
}
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
            start_new_session=True,
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
            timeout = max(0.0, min(0.05, deadline - time.monotonic()))
            ready, _, _ = select.select([self.process.stdout], [], [], timeout)
            if ready:
                line = self.process.stdout.readline()
                if line:
                    return line.strip()
                break
            if self.process.poll() is not None:
                break
        return None

    def close(self) -> None:
        _close_process_group(self.process)


class ProxyWebSocketProcessTransport:
    def __init__(self, argv: list[str], *, timeout: float = 10.0) -> None:
        self.argv = argv
        self.process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            bufsize=0,
            start_new_session=True,
        )
        self.timeout = timeout
        self._buffer = b""
        try:
            self._handshake()
        except Exception:
            self.close()
            raise

    def _handshake(self) -> None:
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            "GET / HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).encode("ascii")
        self._write_raw(request)
        response = self._recv_until(b"\r\n\r\n", time.monotonic() + self.timeout).decode(
            "latin1",
            errors="replace",
        )
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if " 101 " not in response or expected_accept not in response:
            raise RuntimeError("Codex app-server proxy websocket handshake failed")

    def send_json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._write_raw(_build_websocket_frame(encoded, opcode=0x1))

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
            self._write_raw(_build_websocket_frame(payload, opcode=0xA))
            return None
        if opcode not in {0x1, 0x0}:
            return None
        return payload.decode("utf-8", errors="replace")

    def _recv_until(self, marker: bytes, deadline: float) -> bytes:
        while marker not in self._buffer and time.monotonic() < deadline:
            chunk = self._read_available(deadline)
            if not chunk:
                break
            self._buffer += chunk
        if marker not in self._buffer:
            raise TimeoutError("Timed out waiting for Codex app-server proxy websocket handshake")
        end = self._buffer.index(marker) + len(marker)
        payload = self._buffer[:end]
        self._buffer = self._buffer[end:]
        return payload

    def _recv_exact(self, size: int, deadline: float) -> bytes | None:
        while len(self._buffer) < size and time.monotonic() < deadline:
            chunk = self._read_available(deadline)
            if not chunk:
                break
            self._buffer += chunk
        if len(self._buffer) < size:
            return None
        payload = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return payload

    def _read_available(self, deadline: float) -> bytes:
        if self.process.stdout is None:
            return b""
        if self.process.poll() is not None:
            return b""
        timeout = max(0.0, min(0.05, deadline - time.monotonic()))
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            return b""
        try:
            return os.read(self.process.stdout.fileno(), 4096)
        except OSError:
            return b""

    def _write_raw(self, payload: bytes) -> None:
        if self.process.stdin is None:
            raise RuntimeError("codex app-server proxy stdin is unavailable")
        self.process.stdin.write(payload)
        self.process.stdin.flush()

    def close(self) -> None:
        try:
            self._write_raw(_build_websocket_frame(b"", opcode=0x8))
        except (BrokenPipeError, OSError, RuntimeError):
            pass
        _close_process_group(self.process)


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
        self._buffer = b""
        self.sock = socket.create_connection((parsed.hostname or "127.0.0.1", port), timeout=timeout)
        try:
            self.sock.settimeout(timeout)
            self._handshake(parsed.hostname or "127.0.0.1", port)
        except Exception:
            try:
                self.sock.close()
            except OSError:
                pass
            raise

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
        response_bytes = b""
        deadline = time.monotonic() + self.timeout
        while b"\r\n\r\n" not in response_bytes and time.monotonic() < deadline:
            self.sock.settimeout(max(0.01, deadline - time.monotonic()))
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response_bytes += chunk
        header, separator, extra = response_bytes.partition(b"\r\n\r\n")
        if not separator:
            raise RuntimeError("Codex app-server websocket handshake failed")
        self._buffer = extra
        response = header.decode("latin1", errors="replace")
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
        while len(self._buffer) < size and time.monotonic() < deadline:
            self.sock.settimeout(max(0.01, deadline - time.monotonic()))
            chunk = self.sock.recv(size - len(self._buffer))
            if not chunk:
                return None
            self._buffer += chunk
        if len(self._buffer) < size:
            return None
        payload = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return payload

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


def _close_process_group(process: subprocess.Popen[Any]) -> None:
    for stream in (process.stdin,):
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass
    if process.poll() is None:
        _signal_process_group(process, signal.SIGTERM)
        if process.poll() is None:
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                _signal_process_group(process, signal.SIGKILL)
                process.wait(timeout=1.0)
    for stream in (process.stdout, process.stderr):
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass


def _signal_process_group(process: subprocess.Popen[Any], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
    except Exception:
        try:
            process.send_signal(sig)
        except Exception:
            pass


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
        try:
            init_response = self._request_raw(
                "initialize",
                {
                    "clientInfo": APP_SERVER_CLIENT_INFO,
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
        except Exception:
            if self.transport is not None:
                try:
                    self.transport.close()
                except Exception:
                    pass
                self.transport = None
            raise
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
        cli_available = version.returncode == 0 and help_result.returncode == 0
        warnings = list(config.warnings)
        cli_alignment = self._cli_alignment(config)
        if cli_alignment["path_mismatch"] or cli_alignment["version_mismatch"]:
            warnings.append("System codex differs from the Codex.app bundled CLI; evaOS Desktop Bridge is using the selected_cli path.")
        rpc_probe: CommandResult | None = None
        rpc_handshake_ok = False
        if cli_available:
            rpc_probe = self._probe_app_server(config)
            rpc_handshake_ok = rpc_probe.ok
            if not rpc_handshake_ok:
                warnings.append("Codex app-server RPC handshake failed.")
        else:
            warnings.append("Codex app-server CLI is unavailable or not executable.")
        codex_version = redact_value(version.stdout.strip()) if version.returncode == 0 else None
        return CommandResult(
            ok=True,
            data={
                "available": cli_available and rpc_handshake_ok,
                "cli_available": cli_available,
                "rpc_handshake_ok": rpc_handshake_ok,
                "selected_cli": {
                    "path": redact_value(config.cli),
                    "version": codex_version,
                },
                "cli_alignment": cli_alignment,
                "codex_version": codex_version,
                "transport": config.mode,
                "websocket_url": redact_value(config.ws_url),
                "socket_path": redact_value(config.socket_path) if config.socket_path is not None else None,
                "allowed_methods": sorted(ALLOWED_APP_SERVER_METHODS),
                "controller_methods": [],
                "forbidden_methods": sorted(FORBIDDEN_APP_SERVER_METHODS),
                "read_only": True,
                "rpc_probe": {
                    "method": "initialize",
                    "ok": rpc_handshake_ok,
                    "errors": rpc_probe.errors if rpc_probe is not None and not rpc_probe.ok else [],
                },
            },
            warnings=warnings,
            provenance={"source": "app_server"},
        )

    def connections_status(self) -> CommandResult:
        config = self._transport_config()
        cli_alignment = self._cli_alignment(config)
        system_cli_path = cli_alignment["system_cli"]["path"]
        system_version = cli_alignment["system_cli"]["version"]
        app_bundle_version = cli_alignment["app_bundle_cli"]["version"]
        remote_help = self._run([config.cli, "remote-control", "--help"], 5.0)
        daemon_version = self._run([config.cli, "app-server", "daemon", "version"], 5.0)
        control_sockets = [{"path": redact_value(path), "exists": path.exists()} for path in CONTROL_SOCKET_CANDIDATES]
        control_socket_ready = any(item["exists"] for item in control_sockets)
        transport_status = self._probe_app_server(config)
        remote_status = self.request("remoteControl/status/read", {}, cli=config.cli)
        handshake_ok = transport_status.ok
        connections_state = self._connections_state(remote_status.data if remote_status.ok else None)
        warnings = list(config.warnings)
        if cli_alignment["path_mismatch"] or cli_alignment["version_mismatch"]:
            warnings.append("System codex differs from the Codex.app bundled CLI; evaOS Desktop Bridge is using the selected_cli path.")
        if config.mode == "stdio":
            warnings.append("Default stdio transport starts an isolated app-server process; loaded-thread results do not prove Codex Desktop UI attachment.")
        if config.mode == "proxy" and not control_socket_ready:
            warnings.append("Proxy transport was selected but no Codex app-server control socket is present.")
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
                    "system_cli": {"available": system_version is not None, "path": system_cli_path, "version": system_version},
                    "cli_alignment": cli_alignment,
                },
                "app_server": {
                    "available": handshake_ok,
                    "preferred_cli": redact_value(config.cli),
                    "transport": config.mode,
                    "socket_path": redact_value(config.socket_path) if config.socket_path is not None else None,
                    "handshake": "ok" if handshake_ok else "unavailable",
                    "initialize": transport_status.data if transport_status.ok else None,
                    "error": transport_status.errors[0]["message"] if transport_status.errors else None,
                    "loaded_thread_scope": "per_app_server_process_memory",
                    "stdio_isolated": config.mode == "stdio",
                },
                "remote_control": {
                    "supported": remote_help.returncode == 0,
                    "status": remote_status.data if remote_status.ok else None,
                    "available": remote_status.ok,
                    "connections_state": connections_state,
                    "errors": remote_status.errors,
                },
                "connections_state": connections_state,
                "remote_control_command": {
                    "supported": remote_help.returncode == 0,
                    "checked_cli": redact_value(config.cli),
                },
                "daemon": {
                    "version_available": daemon_version.returncode == 0,
                    "version_output": redact_value(daemon_version.stdout.strip()) if daemon_version.returncode == 0 else None,
                    "control_socket_ready": control_socket_ready,
                    "ready": daemon_version.returncode == 0 and control_socket_ready,
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

    def loaded_threads(self, *, max_items: int) -> CommandResult:
        config = self._transport_config()
        response = self.request("thread/loaded/list", {"limit": max_items})
        if not response.ok:
            return response
        warnings = list(response.warnings)
        if config.mode == "stdio":
            warnings.append("Loaded-thread inventory is scoped to the bridge's isolated stdio app-server process, not necessarily Codex Desktop's visible UI process.")
        raw_threads = _extract_result_array(response.data, keys=("threads", "items", "data"))
        threads = [
            {
                "index": index,
                "id": _cap_redacted_scalar(_thread_id_from_loaded_row(row), IDENTIFIER_MAX_CHARS),
                "source": "app_server_loaded",
            }
            for index, row in enumerate(raw_threads[:max_items])
        ]
        return CommandResult(
            ok=True,
            data={
                "threads": threads,
                "count": len(threads),
                "max_items": max_items,
                "source": "app_server",
                "thread_state": "active" if threads else "idle",
                "transport": config.mode,
                "socket_path": redact_value(config.socket_path) if config.socket_path is not None else None,
                "loaded_thread_scope": "per_app_server_process_memory",
                "stdio_isolated": config.mode == "stdio",
            },
            warnings=warnings,
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
                    "thread_id": _cap_redacted_scalar(thread_id, IDENTIFIER_MAX_CHARS),
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
                "thread_id": _cap_redacted_scalar(thread_id, IDENTIFIER_MAX_CHARS),
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
            if config.socket_path is None:
                raise RuntimeError("No Codex app-server control socket configured or found for proxy transport")
            if not config.socket_path.exists():
                raise RuntimeError(f"Codex app-server control socket does not exist: {config.socket_path}")
            argv = [config.cli, "app-server", "proxy"]
            argv.extend(["--sock", str(config.socket_path)])
            return ProxyWebSocketProcessTransport(argv)
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
        if mode == "proxy" and socket_path is None:
            socket_path = next((candidate for candidate in CONTROL_SOCKET_CANDIDATES if candidate.exists()), None)
            if socket_path is None:
                warnings.append("Proxy transport selected but no Codex app-server control socket was configured or found.")
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

    def _cli_alignment(self, config: TransportConfig) -> dict[str, Any]:
        system_cli_path = shutil.which("codex")
        system_version = self._command_version(["codex", "--version"]) if system_cli_path is not None else None
        app_bundle_exists = APP_BUNDLE_CODEX.exists()
        app_bundle_version = self._command_version([str(APP_BUNDLE_CODEX), "--version"]) if app_bundle_exists else None
        selected_path = config.cli
        return {
            "selected_cli": {
                "path": redact_value(selected_path),
                "is_app_bundle": selected_path == str(APP_BUNDLE_CODEX),
            },
            "app_bundle_cli": {
                "path": redact_value(APP_BUNDLE_CODEX),
                "exists": app_bundle_exists,
                "version": app_bundle_version,
            },
            "system_cli": {
                "available": system_cli_path is not None,
                "path": redact_value(system_cli_path) if system_cli_path is not None else None,
                "version": system_version,
            },
            "path_mismatch": bool(app_bundle_exists and system_cli_path and system_cli_path != str(APP_BUNDLE_CODEX)),
            "version_mismatch": bool(system_version and app_bundle_version and system_version != app_bundle_version),
            "bridge_prefers_app_bundle": APP_BUNDLE_CODEX.exists() and not os.environ.get(CODEX_BIN_ENV, "").strip(),
        }

    def _stdio_rpc(self, method: str, params: dict[str, Any], *, cli: str = "codex") -> JsonRpcResponse:
        try:
            with self._json_rpc_client(TransportConfig(mode="stdio", cli=cli)) as client:
                if method == "initialize":
                    return JsonRpcResponse(ok=True, payload=client.initialize_payload, notifications=list(client.notifications))
                return client.request(method, params)
        except Exception as exc:
            return JsonRpcResponse(ok=False, error=str(exc))

    def _close_stdio_process(self, process: subprocess.Popen[Any] | None) -> None:
        if process is None:
            return
        _close_process_group(process)

    def _signal_process_group(self, process: subprocess.Popen[Any], sig: signal.Signals) -> None:
        _signal_process_group(process, sig)

    def _run(self, command: list[str], timeout: float) -> RunnerResult:
        try:
            return self.runner(command, timeout)
        except FileNotFoundError as exc:
            return RunnerResult(returncode=127, stdout="", stderr=str(exc))

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
        title = row.get("name") or row.get("title") or row.get("thread_name") or row.get("summary") or row.get("preview") or f"Thread {index + 1}"
        capped_title, title_truncated = cap_text(str(redact_value(title)), 160)
        thread_id = row.get("id") or row.get("thread_id") or row.get("threadId")
        updated_at = row.get("updated_at") or row.get("updatedAt")
        status = row.get("status") or row.get("state")
        return {
            "index": index,
            "id": _cap_redacted_scalar(thread_id, IDENTIFIER_MAX_CHARS),
            "title": capped_title,
            "title_truncated": title_truncated,
            "updated_at": None if updated_at is None else redact_value(str(updated_at)),
            "status": _cap_redacted_value(status, STATUS_MAX_CHARS),
            "source": "app_server",
        }

    def _safe_event(self, event: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
        params = redact_value(event.get("params", {}))
        text = json.dumps(params, sort_keys=True, default=str)
        capped, truncated = cap_text(text, max_chars)
        return {
            "method": _cap_redacted_scalar(event.get("method"), EVENT_METHOD_MAX_CHARS),
            "params_json": capped,
            "params_truncated": truncated,
            "source": "app_server_notification",
        }

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


def _cap_redacted_scalar(value: Any, max_chars: int) -> str | None:
    if value is None:
        return None
    capped, _ = cap_text(str(redact_value(value)), max_chars)
    return capped


def _cap_redacted_value(value: Any, max_chars: int) -> Any:
    redacted = redact_value(value)
    if isinstance(redacted, str):
        capped, _ = cap_text(redacted, max_chars)
        return capped
    if isinstance(redacted, dict):
        capped_dict: dict[str, Any] = {}
        for key, item in list(redacted.items())[:50]:
            capped_key, _ = cap_text(str(redact_value(key)), IDENTIFIER_MAX_CHARS)
            capped_dict[capped_key] = _cap_redacted_value(item, max_chars)
        return capped_dict
    if isinstance(redacted, list):
        return [_cap_redacted_value(item, max_chars) for item in redacted[:50]]
    return redacted


def _is_loopback_host(host: str | None) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return socket.gethostbyname(host or "") == "127.0.0.1"
    except OSError:
        return False
