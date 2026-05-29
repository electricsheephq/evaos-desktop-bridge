from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import signal
import stat

import pytest

from evaos_desktop_bridge.audit import append_audit
from evaos_desktop_bridge.adapters.codex_app_server import (
    ALLOWED_APP_SERVER_METHODS,
    FORBIDDEN_APP_SERVER_METHODS,
    CodexAppServerObserver,
    CodexJsonRpcClient,
    JsonRpcResponse,
    TransportConfig,
    WebSocketTransport,
    _build_websocket_frame,
)
from evaos_desktop_bridge.adapters import codex_app_server as codex_app_server_module
from evaos_desktop_bridge.adapters.codex_macos import RunnerResult
from evaos_desktop_bridge.policy import PolicyError, command_metadata, ensure_allowed
from evaos_desktop_bridge.queue import append_queue_event, list_queue_events
from evaos_desktop_bridge.redaction import cap_text, redact_value
from evaos_desktop_bridge.schema import build_envelope, make_error
from evaos_desktop_bridge.state import read_audit_record, read_audit_tail, read_latest, write_latest
from evaos_desktop_bridge.cli import _run_connector_service


def _fake_codex_app_server(tmp_path: Path, *, response_method: str = "thread/list") -> tuple[Path, Path]:
    transcript_path = tmp_path / "app-server-transcript.json"
    script_path = tmp_path / "fake-codex"
    script_path.write_text(
        f"""#!/usr/bin/env python3
import json
import pathlib
import sys

transcript_path = pathlib.Path({str(transcript_path)!r})
messages = []
initialized = False
for line in sys.stdin:
    payload = json.loads(line)
    messages.append(payload.get("method"))
    transcript_path.write_text(json.dumps(messages), encoding="utf-8")
    if payload.get("method") == "initialize":
        capabilities = payload.get("params", {{}}).get("capabilities", {{}})
        if payload.get("params", {{}}).get("clientInfo") and capabilities.get("experimentalApi") is True:
            print(json.dumps({{"id": payload.get("id"), "result": {{"userAgent": "fake-codex", "platformFamily": "macos", "platformOs": "darwin"}}}}), flush=True)
        else:
            print(json.dumps({{"id": payload.get("id"), "error": {{"code": -32600, "message": "bad initialize"}}}}), flush=True)
        continue
    if payload.get("method") == "initialized":
        initialized = True
        continue
    if initialized and payload.get("method") == {response_method!r}:
        print(json.dumps({{"method": "remoteControl/status/changed", "params": {{"status": "disabled", "serverName": "fake", "installationId": "install", "environmentId": None}}}}), flush=True)
        if payload.get("method") == "remoteControl/status/read":
            result = {{"status": "disabled", "serverName": "fake", "installationId": "install", "environmentId": None}}
        else:
            result = {{"data": [{{"id": "thread-1", "name": "Handshake thread", "updatedAt": "2026-05-28T01:20:00Z", "status": {{"state": "idle"}}}}], "nextCursor": None, "backwardsCursor": None}}
        print(json.dumps({{"id": payload.get("id"), "result": result}}), flush=True)
        break
""",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)
    return script_path, transcript_path


def test_build_envelope_has_stable_required_fields() -> None:
    envelope = build_envelope(
        command="status",
        target="desktop",
        ok=True,
        data={"app": {"running": False}},
        warnings=[],
        errors=[],
        audit_id="audit-123",
    )

    assert envelope["schema_version"] == "2026-05-02.mvp1"
    assert envelope["command"] == "status"
    assert envelope["target"] == "desktop"
    assert envelope["ok"] is True
    assert envelope["data"] == {"app": {"running": False}}
    assert envelope["warnings"] == []
    assert envelope["errors"] == []
    assert envelope["audit_id"] == "audit-123"
    assert envelope["timestamp"].endswith("Z")


def test_policy_allows_only_mvp_commands() -> None:
    assert ensure_allowed("status") == "status"
    assert ensure_allowed("codex.focus") == "codex.focus"
    assert ensure_allowed("codex.threads") == "codex.threads"
    assert ensure_allowed("codex.select_thread") == "codex.select_thread"
    assert ensure_allowed("codex.continue_thread") == "codex.continue_thread"
    assert ensure_allowed("codex.app_server.status") == "codex.app_server.status"
    assert ensure_allowed("codex.app_server.threads") == "codex.app_server.threads"
    assert ensure_allowed("codex.app_server.loaded_threads") == "codex.app_server.loaded_threads"
    assert ensure_allowed("codex.app_server.subscribe") == "codex.app_server.subscribe"
    assert ensure_allowed("codex.app_server.remote_control_status") == "codex.app_server.remote_control_status"
    assert ensure_allowed("codex.connections.status") == "codex.connections.status"
    assert ensure_allowed("codex.snapshot") == "codex.snapshot"
    assert ensure_allowed("codex.ax_tree") == "codex.ax_tree"
    assert ensure_allowed("customer_mac.status") == "customer_mac.status"
    assert ensure_allowed("customer_mac.iphone_mirroring_home") == "customer_mac.iphone_mirroring_home"
    assert ensure_allowed("customer_mac.iphone_mirroring_swipe_left") == "customer_mac.iphone_mirroring_swipe_left"
    assert ensure_allowed("customer_mac.screen_sharing_status") == "customer_mac.screen_sharing_status"

    with pytest.raises(PolicyError) as exc:
        ensure_allowed("codex.send_message")

    assert exc.value.error["code"] == "command_not_allowed"
    assert "allowlist" in exc.value.error["message"]
    for command in [
        "codex.app_server.rpc",
        "codex.app_server.start_turn",
        "codex.app_server.steer_turn",
        "codex.app_server.interrupt_turn",
    ]:
        with pytest.raises(PolicyError):
            ensure_allowed(command)


def test_command_metadata_marks_guarded_actions() -> None:
    assert command_metadata("codex.select_thread")["mode"] == "guarded_visible_action"
    assert command_metadata("codex.app_server.status")["source"] == "app_server"
    assert command_metadata("codex.app_server.threads")["source"] == "app_server"
    assert command_metadata("codex.continue_thread")["support_only"] is True
    assert command_metadata("customer_mac.iphone_mirroring_open_app")["requires_active_control_session"] is True
    assert command_metadata("customer_mac.iphone_mirroring_send_approved_message")["mode"] == "full_access_control"
    assert command_metadata("customer_mac.iphone_mirroring_send_approved_message")["high_impact_in_ask_permission"] is True
    assert command_metadata("customer_mac.screen_sharing_status")["bridge_can_enable"] is False


def test_redaction_removes_home_paths_and_secret_like_tokens() -> None:
    raw = {
        "path": f"{Path.home()}/Library/Application Support/Codex/session.json",
        "text": "prefix sk-1234567890abcdef suffix",
        "nested": ["Authorization: Bearer abcdef1234567890"],
    }

    redacted = redact_value(raw)

    assert str(Path.home()) not in json.dumps(redacted)
    assert redacted["path"].startswith("~/Library/")
    assert "sk-1234567890abcdef" not in redacted["text"]
    assert "<redacted-secret>" in redacted["text"]
    assert "<redacted-secret>" in redacted["nested"][0]


def test_cap_text_reports_truncation_without_leaking_tail() -> None:
    capped, truncated = cap_text("abcdef", 4)

    assert capped == "abcd"
    assert truncated is True


def test_append_audit_writes_redacted_jsonl(tmp_path: Path) -> None:
    audit_id = append_audit(
        command="codex.snapshot",
        target="codex",
        args={"max_chars": 4000, "path": f"{Path.home()}/secret.txt"},
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )

    audit_path = tmp_path / "audit.jsonl"
    line = audit_path.read_text(encoding="utf-8").strip()
    record = json.loads(line)

    assert audit_id == record["audit_id"]
    assert record["command"] == "codex.snapshot"
    assert record["target"] == "codex"
    assert record["ok"] is True
    assert record["provenance"] == {}
    assert str(Path.home()) not in line
    assert record["args"]["path"] == "~/secret.txt"


def test_latest_state_is_redacted(tmp_path: Path) -> None:
    envelope = build_envelope(
        command="codex.snapshot",
        target="codex",
        ok=True,
        data={"screenshot_path": f"{Path.home()}/Library/Application Support/evaos-desktop-bridge/test.png"},
        warnings=[],
        errors=[],
        audit_id="audit-123",
    )

    write_latest(envelope, state_dir=tmp_path)
    latest = read_latest(state_dir=tmp_path)

    assert latest is not None
    assert latest["data"]["screenshot_path"].startswith("~/Library/")
    assert str(Path.home()) not in json.dumps(latest)


def test_read_audit_tail_caps_records(tmp_path: Path) -> None:
    append_audit(command="status", target="desktop", args={}, ok=True, warnings=[], errors=[], state_dir=tmp_path)
    append_audit(command="codex.snapshot", target="codex", args={}, ok=True, warnings=[], errors=[], state_dir=tmp_path)
    append_audit(command="codex.ax_tree", target="codex", args={}, ok=True, warnings=[], errors=[], state_dir=tmp_path)

    records = read_audit_tail(limit=2, state_dir=tmp_path)

    assert [record["command"] for record in records] == ["codex.snapshot", "codex.ax_tree"]


def test_read_audit_record_returns_matching_record(tmp_path: Path) -> None:
    audit_id = append_audit(command="customer_mac.app_focus", target="customer_mac", args={"app_name": "Safari"}, ok=True, warnings=[], errors=[], state_dir=tmp_path)
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(audit_path.read_text(encoding="utf-8") + "{bad json\n", encoding="utf-8")

    record = read_audit_record(audit_id, state_dir=tmp_path)

    assert record is not None
    assert record["audit_id"] == audit_id
    assert record["command"] == "customer_mac.app_focus"
    assert read_audit_record("audit-missing", state_dir=tmp_path) is None
    assert read_audit_record(123, state_dir=tmp_path) is None  # type: ignore[arg-type]


def test_queue_append_and_list_redacts_payload(tmp_path: Path) -> None:
    result = append_queue_event(
        kind="approval_needed",
        source_audit_id="audit-123",
        message="Review bridge state",
        payload={"path": f"{Path.home()}/secret"},
        state_dir=tmp_path,
    )
    listed = list_queue_events(state_dir=tmp_path)

    assert result.ok is True
    assert listed.data["count"] == 1
    assert listed.data["events"][0]["payload"]["path"] == "~/secret"


def test_queue_rejects_unknown_kind(tmp_path: Path) -> None:
    result = append_queue_event(kind="mutate", source_audit_id="audit-123", state_dir=tmp_path)

    assert result.ok is False
    assert result.errors[0]["code"] == "queue_kind_not_allowed"


def test_app_server_method_allowlist_blocks_mutations() -> None:
    observer = CodexAppServerObserver(rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"threads": []}))

    assert "thread/list" in ALLOWED_APP_SERVER_METHODS
    assert "turn/start" not in ALLOWED_APP_SERVER_METHODS
    assert "turn/start" in FORBIDDEN_APP_SERVER_METHODS
    result = observer.request("turn/start", {})

    assert result.ok is False
    assert result.errors[0]["code"] == "app_server_method_not_allowed"


class FakeTransport:
    def __init__(self, lines: list[dict[str, object]]) -> None:
        self.lines = [json.dumps(line) for line in lines]
        self.sent: list[dict[str, object]] = []
        self.closed = False

    def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)

    def read_line(self, deadline: float) -> str | None:
        if not self.lines:
            return None
        return self.lines.pop(0)

    def close(self) -> None:
        self.closed = True


def test_app_server_json_rpc_client_initializes_before_request() -> None:
    transport = FakeTransport(
        [
            {"jsonrpc": "2.0", "method": "remoteControl/status/changed", "params": {"status": "ready"}},
            {"jsonrpc": "2.0", "id": 1, "result": {"codexHome": f"{Path.home()}/.codex"}},
            {"jsonrpc": "2.0", "id": 2, "result": {"data": [{"id": "thread-1", "name": "SDK Docs"}]}},
        ]
    )
    client = CodexJsonRpcClient(lambda: transport, timeout=0.1)

    with client:
        response = client.request("thread/list", {"limit": 1})

    assert response.ok is True
    assert response.payload == {"data": [{"id": "thread-1", "name": "SDK Docs"}]}
    assert response.notifications[0]["method"] == "remoteControl/status/changed"
    assert [item.get("method") for item in transport.sent] == ["initialize", "initialized", "thread/list"]
    assert transport.sent[0]["params"]["clientInfo"]["name"] == "evaos-desktop-bridge"
    assert transport.closed is True


def test_app_server_json_rpc_client_preserves_empty_result() -> None:
    transport = FakeTransport(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {}},
            {"jsonrpc": "2.0", "id": 2, "result": {}},
        ]
    )
    client = CodexJsonRpcClient(lambda: transport, timeout=0.1)

    with client:
        response = client.request("remoteControl/status/read", {})

    assert response.ok is True
    assert response.payload == {}


def test_app_server_json_rpc_client_closes_transport_when_initialize_fails() -> None:
    transport = FakeTransport([{"jsonrpc": "2.0", "id": 1, "error": {"message": "bad initialize"}}])
    client = CodexJsonRpcClient(lambda: transport, timeout=0.1)

    with pytest.raises(RuntimeError):
        client.__enter__()

    assert transport.closed is True
    assert client.transport is None


def test_websocket_client_frames_are_masked() -> None:
    frame = _build_websocket_frame(b'{"jsonrpc":"2.0"}', opcode=0x1, mask_key=b"abcd")

    assert frame[0] == 0x81
    assert frame[1] & 0x80 == 0x80
    assert b"abcd" in frame


class FakeSocket:
    def __init__(self, chunks: list[bytes] | None = None) -> None:
        self.chunks = chunks or []
        self.sent: list[bytes] = []
        self.closed = False
        self.timeout_values: list[float] = []

    def settimeout(self, timeout: float) -> None:
        self.timeout_values.append(timeout)

    def sendall(self, payload: bytes) -> None:
        self.sent.append(payload)
        if payload.startswith(b"GET ") and not self.chunks:
            request = payload.decode("ascii")
            key = next(line.split(":", 1)[1].strip() for line in request.split("\r\n") if line.lower().startswith("sec-websocket-key:"))
            accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest())
            response = b"HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n"
            self.chunks = [response[:9], response[9:]]

    def recv(self, size: int) -> bytes:
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) > size:
            self.chunks.insert(0, chunk[size:])
            return chunk[:size]
        return chunk

    def close(self) -> None:
        self.closed = True


def test_websocket_transport_handles_split_handshake(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket()
    monkeypatch.setattr(codex_app_server_module.socket, "create_connection", lambda *args, **kwargs: fake)

    transport = WebSocketTransport("ws://127.0.0.1:9777", timeout=0.1)

    assert fake.closed is False
    assert fake.sent[0].startswith(b"GET / HTTP/1.1")
    transport.close()
    assert fake.closed is True


def test_websocket_transport_closes_socket_when_handshake_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket([b"HTTP/1.1 302 Found\r\n\r\n"])
    monkeypatch.setattr(codex_app_server_module.socket, "create_connection", lambda *args, **kwargs: fake)

    with pytest.raises(RuntimeError):
        WebSocketTransport("ws://127.0.0.1:9777", timeout=0.1)

    assert fake.closed is True


def test_app_server_threads_sanitizes_response() -> None:
    observer = CodexAppServerObserver(
        rpc_client=lambda method, params: JsonRpcResponse(
            ok=True,
            payload={"data": [{"id": "thread-1", "title": f"{Path.home()}/project " + ("x" * 200), "updated_at": 1779992752, "status": {"type": "notLoaded"}}]},
        )
    )

    result = observer.threads(max_items=1)

    assert result.ok is True
    assert result.data["threads"][0]["id"] == "thread-1"
    assert str(Path.home()) not in json.dumps(result.data)
    assert result.data["threads"][0]["title_truncated"] is True
    assert result.data["threads"][0]["updated_at"] == "1779992752"
    assert result.data["threads"][0]["status"] == {"type": "notLoaded"}
    assert result.data["thread_state"] == "active"


def test_app_server_threads_caps_redacted_identifiers_and_status() -> None:
    long_value = "thread-" + ("x" * 10_000)
    observer = CodexAppServerObserver(
        rpc_client=lambda method, params: JsonRpcResponse(
            ok=True,
            payload={"data": [{"id": long_value, "title": "safe", "status": {"state": long_value}}]},
        )
    )

    result = observer.threads(max_items=1)
    serialized = json.dumps(result.data)

    assert result.ok is True
    assert len(result.data["threads"][0]["id"]) <= 240
    assert len(result.data["threads"][0]["status"]["state"]) <= 1000
    assert long_value not in serialized


def test_app_server_loaded_threads_caps_redacted_ids() -> None:
    long_value = "thread-" + ("x" * 10_000)
    observer = CodexAppServerObserver(
        rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"data": [long_value]}),
    )

    result = observer.loaded_threads(max_items=1)

    assert result.ok is True
    assert len(result.data["threads"][0]["id"]) <= 240
    assert long_value not in json.dumps(result.data)


def test_app_server_events_cap_method_names() -> None:
    long_method = "item/agentMessage/delta/" + ("x" * 10_000)
    observer = CodexAppServerObserver(rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={}))

    event = observer._safe_event({"method": long_method, "params": {"text": "ok"}}, max_chars=4000)

    assert len(event["method"]) <= 160
    assert long_method not in json.dumps(event)


def test_app_server_threads_empty_result_data_is_idle() -> None:
    observer = CodexAppServerObserver(
        rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"data": [], "nextCursor": None})
    )

    result = observer.threads(max_items=5)

    assert result.ok is True
    assert result.data["threads"] == []
    assert result.data["count"] == 0
    assert result.data["thread_state"] == "idle"


def test_app_server_stdio_rpc_initializes_and_ignores_notifications(tmp_path: Path) -> None:
    fake_codex, transcript = _fake_codex_app_server(tmp_path)
    observer = CodexAppServerObserver()

    response = observer._stdio_rpc("thread/list", {"limit": 1}, cli=str(fake_codex))

    assert response.ok is True
    assert response.payload is not None
    assert response.payload["data"][0]["id"] == "thread-1"
    assert json.loads(transcript.read_text(encoding="utf-8")) == ["initialize", "initialized", "thread/list"]


def test_app_server_remote_status_stdio_rpc_uses_experimental_initialize(tmp_path: Path) -> None:
    fake_codex, transcript = _fake_codex_app_server(tmp_path, response_method="remoteControl/status/read")
    observer = CodexAppServerObserver()

    response = observer._stdio_rpc("remoteControl/status/read", {}, cli=str(fake_codex))

    assert response.ok is True
    assert response.payload == {"status": "disabled", "serverName": "fake", "installationId": "install", "environmentId": None}
    assert json.loads(transcript.read_text(encoding="utf-8")) == ["initialize", "initialized", "remoteControl/status/read"]


def test_app_server_close_stdio_process_signals_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    signals: list[tuple[int, signal.Signals]] = []

    class Closeable:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        pid = 4242
        stdin = Closeable()
        stdout = Closeable()
        stderr = Closeable()

        def __init__(self) -> None:
            self.waited = False

        def poll(self) -> int | None:
            return 0 if self.waited else None

        def wait(self, timeout: float | None = None) -> int:
            self.waited = True
            return 0

        def send_signal(self, sig: signal.Signals) -> None:
            signals.append((self.pid, sig))

    def fake_killpg(pid: int, sig: signal.Signals) -> None:
        signals.append((pid, sig))

    observer = CodexAppServerObserver()
    process = FakeProcess()

    monkeypatch.setattr("evaos_desktop_bridge.adapters.codex_app_server.os.killpg", fake_killpg)
    observer._close_stdio_process(process)  # type: ignore[arg-type]

    assert signals == [(4242, signal.SIGTERM)]
    assert process.waited is True
    assert process.stdin.closed is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True


def test_app_server_status_reports_cli_and_rpc_handshake() -> None:
    observer = CodexAppServerObserver(
        runner=lambda command, timeout=5.0: RunnerResult(returncode=0, stdout="codex-cli 0.133.0\n", stderr=""),
        rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"data": []}),
    )

    result = observer.status()

    assert result.ok is True
    assert result.data["cli_available"] is True
    assert result.data["rpc_handshake_ok"] is True
    assert result.data["available"] is True
    assert result.data["selected_cli"]["version"] == "codex-cli 0.133.0"


def test_app_server_status_reports_path_cli_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_app_codex = tmp_path / "Codex.app" / "Contents" / "Resources" / "codex"
    fake_app_codex.parent.mkdir(parents=True)
    fake_app_codex.write_text("#!/bin/sh\n", encoding="utf-8")

    def runner(command: list[str], timeout: float = 5.0) -> RunnerResult:
        if command == ["codex", "--version"]:
            return RunnerResult(returncode=0, stdout="codex-cli 0.128.0\n", stderr="")
        if command == [str(fake_app_codex), "--version"]:
            return RunnerResult(returncode=0, stdout="codex-cli 0.133.0\n", stderr="")
        return RunnerResult(returncode=0, stdout="help\n", stderr="")

    monkeypatch.setattr(codex_app_server_module, "APP_BUNDLE_CODEX", fake_app_codex)
    monkeypatch.setattr(codex_app_server_module.shutil, "which", lambda name: "/opt/homebrew/bin/codex")
    observer = CodexAppServerObserver(
        runner=runner,
        rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"data": []}),
    )

    result = observer.status()

    assert result.ok is True
    assert result.data["selected_cli"]["path"] == str(fake_app_codex)
    assert result.data["cli_alignment"]["path_mismatch"] is True
    assert result.data["cli_alignment"]["version_mismatch"] is True
    assert any("System codex differs" in warning for warning in result.warnings)


def test_app_server_loaded_threads_reads_data_array() -> None:
    observer = CodexAppServerObserver(
        rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"data": ["thread-1", f"{Path.home()}/thread-2"]}),
    )

    result = observer.loaded_threads(max_items=1)

    assert result.ok is True
    assert result.data["threads"] == [{"index": 0, "id": "thread-1", "source": "app_server_loaded"}]
    assert result.data["transport"] == "stdio"
    assert result.data["loaded_thread_scope"] == "per_app_server_process_memory"
    assert str(Path.home()) not in json.dumps(result.data)


def test_app_server_loaded_threads_accepts_alternate_id_keys() -> None:
    observer = CodexAppServerObserver(
        rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"data": [{"threadId": "thread-1"}, {"thread_id": "thread-2"}]}),
    )

    result = observer.loaded_threads(max_items=2)

    assert result.ok is True
    assert [thread["id"] for thread in result.data["threads"]] == ["thread-1", "thread-2"]


def test_app_server_loaded_threads_warns_for_isolated_stdio() -> None:
    observer = CodexAppServerObserver(
        rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"data": []}),
    )

    result = observer.loaded_threads(max_items=5)

    assert result.ok is True
    assert result.data["stdio_isolated"] is True
    assert any("isolated stdio app-server" in warning for warning in result.warnings)


def test_connections_status_splits_transport_from_remote_control_status() -> None:
    def rpc(method: str, params: dict[str, object]) -> JsonRpcResponse:
        if method == "initialize":
            return JsonRpcResponse(ok=True, payload={"protocolVersion": "0.1"})
        if method == "remoteControl/status/read":
            return JsonRpcResponse(ok=False, error="unsupported")
        raise AssertionError(f"unexpected method {method}")

    observer = CodexAppServerObserver(
        runner=lambda command, timeout=5.0: RunnerResult(returncode=0, stdout="codex-cli 0.133.0", stderr=""),
        rpc_client=rpc,
    )

    result = observer.connections_status()

    assert result.ok is True
    assert result.data["app_server"]["available"] is True
    assert result.data["app_server"]["handshake"] == "ok"
    assert result.data["remote_control"]["available"] is False
    assert result.data["remote_control"]["errors"][0]["message"] == "unsupported"


def test_proxy_transport_requires_existing_control_socket(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_socket = tmp_path / "missing.sock"
    monkeypatch.setenv(codex_app_server_module.TRANSPORT_ENV, "proxy")
    monkeypatch.delenv(codex_app_server_module.SOCKET_PATH_ENV, raising=False)
    monkeypatch.setattr(codex_app_server_module, "CONTROL_SOCKET_CANDIDATES", (missing_socket,))
    observer = CodexAppServerObserver()

    config = observer._transport_config(cli="/Applications/Codex.app/Contents/Resources/codex")

    assert config.mode == "proxy"
    assert config.socket_path is None
    assert any("no Codex app-server control socket" in warning for warning in config.warnings)
    with pytest.raises(RuntimeError, match="No Codex app-server control socket"):
        observer._transport(config)


def test_proxy_transport_rejects_missing_explicit_socket(tmp_path: Path) -> None:
    observer = CodexAppServerObserver()
    config = TransportConfig(mode="proxy", cli="/Applications/Codex.app/Contents/Resources/codex", socket_path=tmp_path / "missing.sock")

    with pytest.raises(RuntimeError, match="control socket does not exist"):
        observer._transport(config)


def test_app_server_proxy_transport_uses_websocket_proxy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    created: list[list[str]] = []
    socket_path = tmp_path / "codex.sock"
    socket_path.write_text("", encoding="utf-8")

    class FakeProxyTransport:
        def __init__(self, argv: list[str]) -> None:
            created.append(argv)

    monkeypatch.setattr(codex_app_server_module, "ProxyWebSocketProcessTransport", FakeProxyTransport)

    observer = CodexAppServerObserver()
    transport = observer._transport(
        TransportConfig(
            mode="proxy",
            cli="/Applications/Codex.app/Contents/Resources/codex",
            socket_path=socket_path,
        )
    )

    assert isinstance(transport, FakeProxyTransport)
    assert created == [
        [
            "/Applications/Codex.app/Contents/Resources/codex",
            "app-server",
            "proxy",
            "--sock",
            str(socket_path),
        ]
    ]

def test_app_server_remote_control_status_is_read_only_probe() -> None:
    observer = CodexAppServerObserver(
        runner=lambda command, timeout=5.0: RunnerResult(returncode=1, stdout="", stderr="missing"),
        rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"status": "disabled"}),
    )

    result = observer.remote_control_status()

    assert result.ok is True
    assert result.data["preferred_path"] == "codex_native_remote_control"
    assert result.data["remote_control_status_read"]["ok"] is True
    assert result.data["connections_state"] == "disabled"
    assert result.data["safety"]["generic_app_server_mutations_exposed"] is False


def test_remote_control_status_reports_remote_read_errors() -> None:
    def rpc(method: str, params: dict[str, object]) -> JsonRpcResponse:
        if method == "initialize":
            return JsonRpcResponse(ok=True, payload={"protocolVersion": "0.1"})
        if method == "remoteControl/status/read":
            return JsonRpcResponse(ok=False, error="remote control disabled")
        raise AssertionError(f"unexpected method {method}")

    observer = CodexAppServerObserver(
        runner=lambda command, timeout=5.0: RunnerResult(returncode=0, stdout="ok", stderr=""),
        rpc_client=rpc,
    )

    result = observer.remote_control_status()

    assert result.ok is True
    assert result.data["app_server"]["available"] is True
    assert result.data["remote_control_status_read"]["ok"] is False
    assert result.data["remote_control_status_read"]["errors"][0]["message"] == "remote control disabled"


def test_connector_service_status_is_structured(tmp_path: Path) -> None:
    result = _run_connector_service("status", state_dir=tmp_path)

    assert result["label"] == "com.electricsheep.evaos-desktop-bridge"
    assert result["domain"].startswith("gui/")
    assert result["token_present"] is False
    assert result["health"]["port"] == 8765
    assert isinstance(result["guidance"], list)


def test_make_error_is_structured() -> None:
    error = make_error(
        code="permission_missing",
        message="Accessibility is required.",
        guidance="Open System Settings.",
        permission="accessibility",
    )

    assert error == {
        "code": "permission_missing",
        "message": "Accessibility is required.",
        "guidance": "Open System Settings.",
        "permission": "accessibility",
    }
