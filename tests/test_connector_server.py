from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from evaos_desktop_bridge.audit import append_audit
from evaos_desktop_bridge.connector_server import (
    _live_guarded_approval_error,
    _live_guarded_without_approval,
    _make_handler,
    _remote_kill_switch_error,
    build_bridge_argv,
    read_token,
)
from evaos_desktop_bridge.state import kill_control_session, start_control_session


def rewrite_audit_timestamp(state_dir: Path, audit_id: str, timestamp: str) -> None:
    audit_path = state_dir / "audit.jsonl"
    updated: list[str] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("audit_id") == audit_id:
            record["timestamp"] = timestamp
        updated.append(json.dumps(record, sort_keys=True, separators=(",", ":")))
    audit_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def test_connector_builds_fixed_status_argv() -> None:
    assert build_bridge_argv("customerMacStatus") == ["customer-mac", "status", "--json"]
    assert build_bridge_argv("customerMacIphoneMirroringStatus") == ["customer-mac", "iphone-mirroring", "status", "--json"]
    assert build_bridge_argv("codexAppServerRemoteControlStatus") == ["codex", "app-server", "remote-control-status", "--json"]


def test_connector_defaults_guarded_commands_to_dry_run() -> None:
    assert build_bridge_argv("customerMacAppFocus", {"app_name": "Safari"}) == [
        "customer-mac",
        "app-focus",
        "--json",
        "--app-name",
        "Safari",
        "--dry-run",
    ]


def test_connector_builds_desktop_control_argv() -> None:
    assert build_bridge_argv("customerMacControlStart", {"mode": "full-access", "agent_label": "Aurelius"}) == [
        "customer-mac",
        "control",
        "start",
        "--json",
        "--mode",
        "full-access",
        "--agent-label",
        "Aurelius",
    ]
    assert build_bridge_argv("desktopClick", {"target_label": "Continue"}) == [
        "customer-mac",
        "desktop",
        "click",
        "--json",
        "--dry-run",
        "--target-label",
        "Continue",
    ]
    assert build_bridge_argv("iphoneSwipe", {"direction": "left", "dry_run": False}) == [
        "customer-mac",
        "iphone-mirroring",
        "swipe",
        "--json",
        "--direction",
        "left",
    ]


def test_connector_allows_live_argv_only_when_requested_by_server_policy() -> None:
    assert build_bridge_argv("customerMacAppFocus", {"app_name": "Safari", "dry_run": False}) == [
        "customer-mac",
        "app-focus",
        "--json",
        "--app-name",
        "Safari",
    ]
    assert build_bridge_argv("customerMacIphoneMirroringSwipeLeft", {"dry_run": False}) == [
        "customer-mac",
        "iphone-mirroring",
        "swipe-left",
        "--json",
    ]


def test_connector_clamps_caps_and_rejects_missing_required_values() -> None:
    assert build_bridge_argv("customerMacSnapshot", {"max_chars": 999999})[-1] == "20000"

    try:
        build_bridge_argv("customerMacLocalSiteOpen", {})
    except ValueError as exc:
        assert "url is required" in str(exc)
    else:
        raise AssertionError("expected missing url to be rejected")


def test_connector_live_guarded_remote_actions_require_approval_audit_id() -> None:
    assert _live_guarded_without_approval("customerMacAppFocus", {"app_name": "Safari", "dry_run": False}) is True
    assert _live_guarded_without_approval("customerMacIphoneMirroringSwipeLeft", {"dry_run": False}) is True
    assert _live_guarded_without_approval("customerMacAppFocus", {"app_name": "Safari", "dry_run": True}) is False
    assert _live_guarded_without_approval("customerMacAppFocus", {"app_name": "Safari", "dry_run": False, "approval_audit_id": "audit-1"}) is False
    assert _live_guarded_without_approval("customerMacStatus", {}) is False
    argv = build_bridge_argv("customerMacAppFocus", {"app_name": "Safari", "dry_run": False, "approval_audit_id": "audit-1"})
    assert "--approval-audit-id" in argv
    assert "audit-1" in argv


def test_connector_full_access_allows_live_remote_control_without_approval(tmp_path: Path) -> None:
    start_control_session(mode="full_access", agent_label="Aurelius", state_dir=tmp_path)

    assert _live_guarded_approval_error("desktopType", {"text": "hello", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("iphoneSwipe", {"direction": "left", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("codexContinueThread", {"title": "SDK Docs", "prompt": "continue", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("customerMacIphoneMirroringSendApprovedMessage", {"text": "hello", "recipient_context": "test", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."


def test_connector_ask_permission_allows_navigation_but_gates_high_impact(tmp_path: Path) -> None:
    start_control_session(mode="ask_permission", agent_label="Hermes", state_dir=tmp_path)

    assert _live_guarded_approval_error("desktopScroll", {"direction": "down", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("desktopClick", {"target_label": "Continue", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("desktopHotkey", {"keys": "cmd+r", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("desktopClick", {"target_label": "Send", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("desktopClick", {"x": 10, "y": 20, "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("desktopHotkey", {"keys": "return", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("desktopType", {"text": "hello", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."


def test_connector_kill_switch_blocks_remote_control(tmp_path: Path) -> None:
    start_control_session(mode="full_access", agent_label="Aurelius", state_dir=tmp_path)
    kill_control_session(tmp_path)

    assert _live_guarded_approval_error("desktopScroll", {"direction": "down", "dry_run": False}, state_dir=tmp_path) == "The customer Mac kill switch is active; live agent control commands are blocked."
    assert _remote_kill_switch_error("desktopSee", state_dir=tmp_path) == "The customer Mac kill switch is active; remote connector commands are blocked until the local Workbench app starts a new control session."
    assert _remote_kill_switch_error("customerMacStatus", state_dir=tmp_path) == "The customer Mac kill switch is active; remote connector commands are blocked until the local Workbench app starts a new control session."
    assert _remote_kill_switch_error("customerMacControlStart", state_dir=tmp_path) == "The customer Mac kill switch is active; only the local Workbench app can start a new control session."
    assert _remote_kill_switch_error("customerMacControlStatus", state_dir=tmp_path) is None


def test_connector_approved_message_requires_matching_dry_run_audit(tmp_path: Path) -> None:
    dry_run_audit = append_audit(
        command="customer_mac.iphone_mirroring_send_approved_message",
        target="customer_mac",
        args={"text": "Hello", "recipient_context": "Bumble canary", "target_label": "Send", "dry_run": True, "json": True, "approval_audit_id": None},
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )

    assert _live_guarded_approval_error(
        "customerMacIphoneMirroringSendApprovedMessage",
        {"text": "Hello", "recipient_context": "Bumble canary", "target_label": "Send", "dry_run": False, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) is None
    assert _live_guarded_approval_error(
        "customerMacIphoneMirroringSendApprovedMessage",
        {"text": "Hello", "recipient_context": "Bumble canary", "dry_run": False, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) is None
    assert _live_guarded_approval_error(
        "customerMacIphoneMirroringScroll",
        {"direction": "down", "dry_run": False, "approval_audit_id": append_audit(command="customer_mac.iphone_mirroring_scroll", target="customer_mac", args={"direction": "down", "dry_run": True, "json": True, "approval_audit_id": None}, ok=True, warnings=[], errors=[], state_dir=tmp_path)},
        state_dir=tmp_path,
    ) is None
    assert _live_guarded_approval_error(
        "customerMacIphoneMirroringSendApprovedMessage",
        {"text": "Different", "recipient_context": "Bumble canary", "target_label": "Send", "dry_run": False, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) == "approval_audit_id does not match text."


def test_connector_approval_audit_expires(tmp_path: Path) -> None:
    dry_run_audit = append_audit(
        command="customer_mac.app_focus",
        target="customer_mac",
        args={"app_name": "Safari", "dry_run": True, "json": True, "approval_audit_id": None},
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )
    old_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=20)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rewrite_audit_timestamp(tmp_path, dry_run_audit, old_timestamp)

    assert _live_guarded_approval_error(
        "customerMacAppFocus",
        {"app_name": "Safari", "dry_run": False, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) == "approval_audit_id is older than 15 minutes; run a new dry-run."


def test_connector_live_guarded_remote_actions_require_matching_dry_run_audit(tmp_path: Path) -> None:
    dry_run_audit = append_audit(
        command="customer_mac.app_focus",
        target="customer_mac",
        args={"app_name": "Safari", "dry_run": True, "json": True, "approval_audit_id": None},
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )

    assert _live_guarded_approval_error(
        "customerMacAppFocus",
        {"app_name": "Safari", "dry_run": False, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) is None
    assert _live_guarded_approval_error(
        "customerMacAppFocus",
        {"app_name": "Messages", "dry_run": False, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) == "approval_audit_id does not match app_name."
    assert _live_guarded_approval_error(
        "customerMacAppFocus",
        {"app_name": "Safari", "dry_run": False, "approval_audit_id": "audit-missing"},
        state_dir=tmp_path,
    ) == "approval_audit_id was not found in the local audit log."


def test_connector_token_file_must_exist_when_configured(tmp_path: Path) -> None:
    try:
        read_token(str(tmp_path / "missing.token"))
    except ValueError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("expected missing configured token file to fail closed")

    token_path = tmp_path / "connector.token"
    token_path.write_text("secret-token\n", encoding="utf-8")
    assert read_token(str(token_path)) == "secret-token"


def test_connector_token_autocreates_per_user_default(tmp_path: Path) -> None:
    token = read_token(None, state_dir=tmp_path, auto_create=True)
    token_path = tmp_path / "connector.token"

    assert token
    assert token_path.exists()
    assert token_path.read_text(encoding="utf-8").strip() == token
    assert oct(token_path.stat().st_mode & 0o777) == "0o600"
    assert read_token(None, state_dir=tmp_path, auto_create=True) == token


def test_connector_token_autocreates_empty_configured_file(tmp_path: Path) -> None:
    token_path = tmp_path / "connector.token"
    token_path.write_text("\n", encoding="utf-8")

    token = read_token(str(token_path), auto_create=True)

    assert token
    assert token_path.read_text(encoding="utf-8").strip() == token
    assert oct(token_path.stat().st_mode & 0o777) == "0o600"


def test_connector_rejects_post_without_token_even_on_loopback(tmp_path: Path) -> None:
    handler = _make_handler(token=None, command_runner=lambda _argv: (0, "{}"), state_dir=tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request(
            "POST",
            "/v1/commands",
            body=json.dumps({"command": "customerMacStatus", "params": {}}),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 401
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_connector_enrollment_complete_posts_local_connector_context(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return {"device_id": "device-1"}

    monkeypatch.setattr("evaos_desktop_bridge.connector_server.complete_enrollment_via_control", fake_complete)
    handler = _make_handler(token="secret-token", command_runner=lambda _argv: (0, "{}"), state_dir=tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request(
            "POST",
            "/v1/enrollment/complete",
            body=json.dumps({"enrollment_code": "PAIR123", "device_name": "Customer Mac"}),
            headers={"Content-Type": "application/json", "Host": f"100.64.1.10:{server.server_port}"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert payload["ok"] is True
        assert captured["enrollment_code"] == "PAIR123"
        assert captured["connector_url"] == f"http://100.64.1.10:{server.server_port}"
        assert captured["connector_token"] == "secret-token"
        assert captured["device_name"] == "Customer Mac"
    finally:
        server.shutdown()
        thread.join(timeout=2)
