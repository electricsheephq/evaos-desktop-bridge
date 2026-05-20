from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaos_desktop_bridge.audit import append_audit
from evaos_desktop_bridge.adapters.codex_app_server import (
    ALLOWED_APP_SERVER_METHODS,
    CONTROLLER_APP_SERVER_METHODS,
    EXPECTED_APP_SERVER_NOTIFICATIONS,
    FORBIDDEN_APP_SERVER_METHODS,
    CodexAppServerObserver,
    CodexJsonRpcClient,
    JsonRpcResponse,
    JsonRpcTransport,
    LoopbackWebSocketTransport,
    classify_app_server_method,
    extract_generated_protocol_methods,
)
from evaos_desktop_bridge.policy import PolicyError, command_metadata, ensure_allowed
from evaos_desktop_bridge.queue import append_queue_event, list_queue_events
from evaos_desktop_bridge.redaction import cap_text, redact_value
from evaos_desktop_bridge.schema import build_envelope, make_error
from evaos_desktop_bridge.state import read_audit_tail, read_latest, write_latest


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
    assert ensure_allowed("codex.app_server.threads") == "codex.app_server.threads"
    assert ensure_allowed("codex.snapshot") == "codex.snapshot"
    assert ensure_allowed("codex.ax_tree") == "codex.ax_tree"

    with pytest.raises(PolicyError) as exc:
        ensure_allowed("codex.send_message")

    assert exc.value.error["code"] == "command_not_allowed"
    assert "allowlist" in exc.value.error["message"]


def test_command_metadata_marks_guarded_actions() -> None:
    assert command_metadata("codex.select_thread")["mode"] == "guarded_visible_action"
    assert command_metadata("codex.app_server.threads")["source"] == "app_server"


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
    result = observer.request("turn/start", {})

    assert result.ok is False
    assert result.errors[0]["code"] == "app_server_method_not_allowed"


def test_app_server_protocol_methods_are_classified() -> None:
    assert classify_app_server_method("thread/read") == "read_only"
    assert classify_app_server_method("turn/start") == "guarded_controller"
    assert classify_app_server_method("fs/writeFile") == "forbidden"
    assert classify_app_server_method("unknown/method") == "unknown"

    assert {"turn/start", "turn/steer", "turn/interrupt"} <= CONTROLLER_APP_SERVER_METHODS
    assert {"fs/writeFile", "config/batchWrite", "plugin/install"} <= FORBIDDEN_APP_SERVER_METHODS
    assert "remoteControl/status/changed" in EXPECTED_APP_SERVER_NOTIFICATIONS


def test_extract_generated_protocol_methods_from_typescript_fixture() -> None:
    source = '''
export type ClientRequest =
  { "method": "initialize", id: RequestId, params: InitializeParams, } |
  { "method": "thread/read", id: RequestId, params: ThreadReadParams, } |
  { "method": "turn/start", id: RequestId, params: TurnStartParams, };
export type ServerNotification =
  { "method": "turn/started", "params": TurnStartedNotification } |
  { "method": "remoteControl/status/changed", "params": RemoteControlStatusChangedNotification };
'''

    methods = extract_generated_protocol_methods(source)

    assert methods == {
        "initialize",
        "thread/read",
        "turn/start",
        "turn/started",
        "remoteControl/status/changed",
    }


class FakeTransport(JsonRpcTransport):
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.sent: list[dict] = []
        self.closed = False

    def send(self, payload: dict) -> None:
        self.sent.append(payload)

    def recv(self, timeout: float) -> dict | None:
        if not self.responses:
            return None
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def test_json_rpc_client_serializes_requests_and_buffers_notifications() -> None:
    transport = FakeTransport(
        [
            {"method": "turn/started", "params": {"threadId": "thread-1"}},
            {"id": 1, "result": {"ok": True}},
            {"method": "turn/completed", "params": {"threadId": "thread-1"}},
        ]
    )

    with CodexJsonRpcClient(transport_factory=lambda: transport, request_timeout=0.1) as client:
        response = client.request("thread/list", {"limit": 1})
        events = client.collect_notifications(duration_ms=10, max_events=5)

    assert response.ok is True
    assert transport.sent[0]["id"] == 1
    assert transport.sent[0]["method"] == "thread/list"
    assert response.notifications == [{"method": "turn/started", "params": {"threadId": "thread-1"}}]
    assert events == [{"method": "turn/completed", "params": {"threadId": "thread-1"}}]
    assert transport.closed is True


def test_json_rpc_client_preserves_empty_result_payload() -> None:
    transport = FakeTransport([{"id": 1, "result": {}}])

    with CodexJsonRpcClient(transport_factory=lambda: transport, request_timeout=0.1) as client:
        response = client.request("thread/list", {"limit": 1})

    assert response.ok is True
    assert response.payload == {}
    assert transport.closed is True


def test_loopback_websocket_transport_rejects_non_loopback_urls() -> None:
    with pytest.raises(ValueError):
        LoopbackWebSocketTransport("ws://example.com:9999")


def test_app_server_controller_dry_run_does_not_call_rpc() -> None:
    def fail_rpc(method: str, params: dict) -> JsonRpcResponse:
        raise AssertionError(f"unexpected rpc call: {method}")

    observer = CodexAppServerObserver(rpc_client=fail_rpc)
    result = observer.start_turn(
        thread_id="thread-1",
        message="continue",
        dry_run=True,
        source_audit_id=None,
        confirmed=False,
    )

    assert result.ok is True
    assert result.data["would_start_turn"] is True
    assert result.data["method"] == "turn/start"
    assert result.provenance["dry_run"] is True


def test_app_server_controller_live_requires_confirmation_and_source_audit() -> None:
    observer = CodexAppServerObserver(rpc_client=lambda method, params: JsonRpcResponse(ok=True, payload={"ok": True}))

    result = observer.start_turn(
        thread_id="thread-1",
        message="continue",
        dry_run=False,
        source_audit_id=None,
        confirmed=False,
    )

    assert result.ok is False
    assert result.errors[0]["code"] == "controller_confirmation_required"


def test_app_server_controller_live_calls_guarded_method_with_capped_message() -> None:
    calls: list[tuple[str, dict]] = []

    def capture_rpc(method: str, params: dict) -> JsonRpcResponse:
        calls.append((method, params))
        return JsonRpcResponse(ok=True, payload={"turnId": "turn-1"})

    observer = CodexAppServerObserver(rpc_client=capture_rpc)
    result = observer.start_turn(
        thread_id="thread-1",
        message=f"{Path.home()}/secret " + ("x" * 50),
        dry_run=False,
        source_audit_id="audit-123",
        confirmed=True,
        max_chars=20,
    )

    assert result.ok is True
    assert calls[0][0] == "turn/start"
    assert calls[0][1]["threadId"] == "thread-1"
    assert calls[0][1]["input"][0]["text"].startswith(str(Path.home()))
    assert str(Path.home()) not in json.dumps(result.data)
    assert result.data["message_truncated"] is True


def test_app_server_steer_and_interrupt_live_require_turn_id() -> None:
    def fail_rpc(method: str, params: dict) -> JsonRpcResponse:
        raise AssertionError(f"unexpected rpc call: {method}")

    observer = CodexAppServerObserver(rpc_client=fail_rpc)
    steer = observer.steer_turn(
        thread_id="thread-1",
        turn_id=None,
        message="adjust",
        dry_run=False,
        source_audit_id="audit-123",
        confirmed=True,
    )
    interrupt = observer.interrupt_turn(
        thread_id="thread-1",
        turn_id=None,
        dry_run=False,
        source_audit_id="audit-123",
        confirmed=True,
    )

    assert steer.ok is False
    assert steer.errors[0]["code"] == "active_turn_required"
    assert interrupt.ok is False
    assert interrupt.errors[0]["code"] == "active_turn_required"


def test_app_server_subscribe_sanitizes_notifications() -> None:
    observer = CodexAppServerObserver(
        subscription_client=lambda thread_id, duration_ms, max_events, max_chars: JsonRpcResponse(
            ok=True,
            payload={
                "events": [
                    {
                        "method": "item/agentMessage/delta",
                        "params": {"delta": f"{Path.home()}/project " + ("x" * 40)},
                    },
                    {"method": "fs/changed", "params": {"path": f"{Path.home()}/secret.txt"}},
                ]
            },
        )
    )

    result = observer.subscribe(thread_id="thread-1", duration_ms=100, max_events=5, max_chars=20)

    assert result.ok is True
    assert result.data["events"][0]["params"]["delta"].startswith("~/")
    assert result.data["events"][0]["truncated"] is True
    assert result.data["events"][1]["method"] == "fs/changed"


def test_app_server_threads_sanitizes_response() -> None:
    observer = CodexAppServerObserver(
        rpc_client=lambda method, params: JsonRpcResponse(
            ok=True,
            payload={"threads": [{"id": "thread-1", "title": f"{Path.home()}/project " + ("x" * 200), "updated_at": "now"}]},
        )
    )

    result = observer.threads(max_items=1)

    assert result.ok is True
    assert result.data["threads"][0]["id"] == "thread-1"
    assert str(Path.home()) not in json.dumps(result.data)
    assert result.data["threads"][0]["title_truncated"] is True


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
