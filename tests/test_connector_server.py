from __future__ import annotations

import json
import hashlib
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
    _prepare_connector_params,
    _remote_kill_switch_error,
    build_diagnostics_payload,
    build_ready_payload,
    build_bridge_argv,
    normalize_connector_command,
    read_token,
    record_service_event,
)
from evaos_desktop_bridge.state import kill_control_session, start_control_session, write_control_session


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
    assert build_bridge_argv("codexConnectionsStatus") == ["codex", "connections", "status", "--json"]


def test_connector_accepts_openclaw_tool_name_aliases() -> None:
    assert normalize_connector_command("customer_mac_status") == "customerMacStatus"
    assert normalize_connector_command("desktop_see") == "desktopSee"
    assert normalize_connector_command("iphone_swipe") == "iphoneSwipe"
    assert normalize_connector_command("desktop_bridge_audit_tail") == "auditTail"
    assert normalize_connector_command("desktop_bridge_codex_thread_map") == "codexThreadMap"
    assert normalize_connector_command("desktop_bridge_codex_send_visible_message") == "codexSendVisibleMessage"
    assert build_bridge_argv("customer_mac_status") == ["customer-mac", "status", "--json"]
    assert build_bridge_argv("desktop_see", {"max_chars": 800, "max_nodes": 40}) == [
        "customer-mac",
        "desktop",
        "see",
        "--json",
        "--max-chars",
        "800",
        "--max-nodes",
        "40",
    ]


def test_connector_builds_codex_read_only_app_server_argv() -> None:
    assert build_bridge_argv("codexThreadMap", {"max_items": 3}) == [
        "codex",
        "thread-map",
        "--json",
        "--max-items",
        "3",
    ]
    assert build_bridge_argv("codexAppServerLoadedThreads", {"max_items": 3}) == [
        "codex",
        "app-server",
        "loaded-threads",
        "--json",
        "--max-items",
        "3",
    ]
    assert build_bridge_argv("codexLiveStatus", {"thread_id": "thread-1", "duration_ms": 25}) == [
        "codex",
        "app-server",
        "subscribe",
        "--json",
        "--thread-id",
        "thread-1",
        "--duration-ms",
        "25",
    ]
    try:
        build_bridge_argv("codexRemoteStartTurn", {"thread_id": "thread-1", "message": "continue"})
    except ValueError as exc:
        assert "Unsupported connector command" in str(exc)
    else:
        raise AssertionError("expected Codex remote start to stay unexposed")
    assert build_bridge_argv("codexSendVisibleMessage", {"thread_id": "visible-0-abc", "message": "hello"}) == [
        "codex",
        "send-visible-message",
        "--json",
        "--thread-id",
        "visible-0-abc",
        "--message",
        "hello",
        "--dry-run",
    ]
    assert build_bridge_argv("codexSendVisibleMessage", {"thread_id": "visible-0-abc", "message": "hello", "dry_run": False, "confirm": True, "approval_audit_id": "audit-1"}) == [
        "codex",
        "send-visible-message",
        "--json",
        "--thread-id",
        "visible-0-abc",
        "--message",
        "hello",
        "--live",
        "--confirm",
        "--approval-audit-id",
        "audit-1",
    ]
    assert build_bridge_argv(
        "codexSendVisibleMessage",
        {
            "thread_id": "visible-0-abc",
            "message": "hello",
            "dry_run": False,
            "confirm": True,
            "approval_audit_id": "audit-1",
            "wait_ms": 3000,
            "poll_interval_ms": 1000,
        },
    ) == [
        "codex",
        "send-visible-message",
        "--json",
        "--thread-id",
        "visible-0-abc",
        "--message",
        "hello",
        "--live",
        "--confirm",
        "--approval-audit-id",
        "audit-1",
        "--wait-ms",
        "3000",
        "--poll-interval-ms",
        "1000",
    ]
    try:
        build_bridge_argv("codexSendVisibleMessage", {"thread_id": "visible-0-abc", "message_file": "/tmp/message.txt"})
    except ValueError as exc:
        assert "message_file is reserved" in str(exc)
    else:
        raise AssertionError("expected client-supplied message_file to fail closed")
    assert build_bridge_argv(
        "codexSendVisibleMessage",
        {"thread_id": "visible-0-abc", "message_file": "/tmp/message.txt", "_prepared_message_file": True},
    ) == [
        "codex",
        "send-visible-message",
        "--json",
        "--thread-id",
        "visible-0-abc",
        "--message-file",
        "/tmp/message.txt",
        "--dry-run",
    ]
    assert build_bridge_argv("iphone_swipe", {"direction": "left", "dry_run": False}) == [
        "customer-mac",
        "iphone-mirroring",
        "swipe",
        "--json",
        "--direction",
        "left",
    ]


def test_connector_defaults_guarded_commands_to_dry_run() -> None:
    assert build_bridge_argv("customerMacAppFocus", {"app_name": "Safari"}) == [
        "customer-mac",
        "app-focus",
        "--json",
        "--app-name",
        "Safari",
        "--dry-run",
    ]


def test_connector_builds_desktop_control_argv(tmp_path: Path) -> None:
    value_file = tmp_path / "value.txt"
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
    assert "--snapshot-id" in build_bridge_argv("desktopClick", {"snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "element_id": "el-0001"})
    assert build_bridge_argv(
        "desktopSetValue",
        {
            "snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element_id": "el-0001",
            "value_file": str(value_file),
            "_prepared_value_file": True,
        },
    ) == [
        "customer-mac",
        "desktop",
        "set-value",
        "--json",
        "--snapshot-id",
        "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "--element-id",
        "el-0001",
        "--value-file",
        str(value_file),
        "--attribute",
        "value",
        "--dry-run",
    ]
    assert "--element-id" in build_bridge_argv("iphoneTap", {"snapshot_id": "snap-iphone-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "element_id": "el-0001"})
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
    write_control_session({"active": True, "mode": "full_access", "takeover_warning_until": "2000-01-01T00:00:00Z"}, state_dir=tmp_path)

    assert _live_guarded_approval_error("desktopType", {"text": "hello", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error(
        "desktopSetValue",
        {
            "snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element_id": "el-0001",
            "value": "hello",
            "dry_run": False,
        },
        state_dir=tmp_path,
    ) is None
    assert _live_guarded_approval_error("iphoneSwipe", {"direction": "left", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("codexContinueThread", {"title": "SDK Docs", "prompt": "continue", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("codexSendVisibleMessage", {"thread_id": "visible-0-abc", "message": "hello", "dry_run": False, "confirm": True}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("customerMacIphoneMirroringSendApprovedMessage", {"text": "hello", "recipient_context": "test", "dry_run": False}, state_dir=tmp_path) is None


def test_connector_blocks_live_remote_control_during_takeover_warning(tmp_path: Path) -> None:
    start_control_session(mode="full_access", agent_label="Aurelius", state_dir=tmp_path)
    app_focus_audit = append_audit(
        command="customer_mac.app_focus",
        target="customer_mac",
        args={"app_name": "Safari", "dry_run": True, "json": True, "approval_audit_id": None},
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )
    local_site_open_audit = append_audit(
        command="customer_mac.local_site_open",
        target="customer_mac",
        args={"url": "http://127.0.0.1:8080", "dry_run": True, "json": True, "approval_audit_id": None},
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )
    local_site_action_audit = append_audit(
        command="customer_mac.local_site_action",
        target="customer_mac",
        args={"action": "reload", "dry_run": True, "json": True, "approval_audit_id": None},
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )

    assert _live_guarded_approval_error("desktopScroll", {"direction": "down", "dry_run": False}, state_dir=tmp_path) == "Agent control is starting; live actions are blocked until the 10-second takeover warning finishes."
    assert _live_guarded_approval_error("customerMacAppFocus", {"app_name": "Safari", "dry_run": False, "approval_audit_id": app_focus_audit}, state_dir=tmp_path) == "Agent control is starting; live actions are blocked until the 10-second takeover warning finishes."
    assert _live_guarded_approval_error("customerMacLocalSiteOpen", {"url": "http://127.0.0.1:8080", "dry_run": False, "approval_audit_id": local_site_open_audit}, state_dir=tmp_path) == "Agent control is starting; live actions are blocked until the 10-second takeover warning finishes."
    assert _live_guarded_approval_error("customerMacLocalSiteAction", {"action": "reload", "dry_run": False, "approval_audit_id": local_site_action_audit}, state_dir=tmp_path) == "Agent control is starting; live actions are blocked until the 10-second takeover warning finishes."
    assert _live_guarded_approval_error("customerMacControlStatus", {}, state_dir=tmp_path) is None


def test_connector_ask_permission_allows_navigation_but_gates_high_impact(tmp_path: Path) -> None:
    start_control_session(mode="ask_permission", agent_label="Hermes", state_dir=tmp_path)
    write_control_session({"active": True, "mode": "ask_permission", "takeover_warning_until": "2000-01-01T00:00:00Z"}, state_dir=tmp_path)

    assert _live_guarded_approval_error("desktopScroll", {"direction": "down", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("desktopClick", {"target_label": "Continue", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("desktopHotkey", {"keys": "cmd+r", "dry_run": False}, state_dir=tmp_path) is None
    assert _live_guarded_approval_error("desktopClick", {"target_label": "Send", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("desktopClick", {"x": 10, "y": 20, "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("desktopHotkey", {"keys": "return", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error("desktopType", {"text": "hello", "dry_run": False}, state_dir=tmp_path) == "Live remote control actions require a prior dry-run and approval_audit_id."
    assert _live_guarded_approval_error(
        "desktopSetValue",
        {
            "snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element_id": "el-0001",
            "value": "hello",
            "dry_run": False,
        },
        state_dir=tmp_path,
    ) == "Live remote control actions require a prior dry-run and approval_audit_id."


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


def test_connector_codex_visible_message_requires_matching_hash_and_confirm(tmp_path: Path) -> None:
    message_hash = hashlib.sha256("hello".encode("utf-8")).hexdigest()[:16]
    dry_run_audit = append_audit(
        command="codex.send_visible_message",
        target="codex",
        args={"thread_id": "visible-0-abc", "message_hash": message_hash, "dry_run": True, "json": True, "approval_audit_id": None},
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )

    assert _live_guarded_without_approval("codexSendVisibleMessage", {"thread_id": "visible-0-abc", "message": "hello", "dry_run": False, "confirm": True}) is True
    assert _live_guarded_approval_error(
        "codexSendVisibleMessage",
        {"thread_id": "visible-0-abc", "message": "hello", "dry_run": False, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) == "Live Codex visible message actions require confirm=true."
    assert _live_guarded_approval_error(
        "codexSendVisibleMessage",
        {"thread_id": "visible-0-abc", "message": "hello", "dry_run": False, "confirm": True, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) is None
    assert _live_guarded_approval_error(
        "codexSendVisibleMessage",
        {"thread_id": "visible-0-abc", "message": "different", "dry_run": False, "confirm": True, "approval_audit_id": dry_run_audit},
        state_dir=tmp_path,
    ) == "approval_audit_id does not match message_hash."


def test_connector_desktop_set_value_requires_matching_value_hash(tmp_path: Path) -> None:
    value_hash = hashlib.sha256(b"hello").hexdigest()[:16]
    dry_run_audit = append_audit(
        command="customer_mac.desktop_set_value",
        target="customer_mac",
        args={
            "snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element_id": "el-0001",
            "attribute": "value",
            "value_hash": value_hash,
            "dry_run": True,
            "json": True,
            "approval_audit_id": None,
        },
        ok=True,
        warnings=[],
        errors=[],
        state_dir=tmp_path,
    )

    assert _live_guarded_approval_error(
        "desktopSetValue",
        {
            "snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element_id": "el-0001",
            "attribute": "value",
            "value": "hello",
            "dry_run": False,
            "approval_audit_id": dry_run_audit,
        },
        state_dir=tmp_path,
    ) is None
    assert _live_guarded_approval_error(
        "desktopSetValue",
        {
            "snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element_id": "el-0001",
            "attribute": "value",
            "value": "different",
            "dry_run": False,
            "approval_audit_id": dry_run_audit,
        },
        state_dir=tmp_path,
    ) == "approval_audit_id does not match value_hash."


def test_connector_desktop_set_value_materializes_value_file_for_local_argv(tmp_path: Path) -> None:
    prepared, temp_paths = _prepare_connector_params(
        "desktopSetValue",
        {
            "snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element_id": "el-0001",
            "value": "private text",
            "dry_run": True,
        },
        state_dir=tmp_path,
    )

    assert "value" not in prepared
    assert prepared.get("_prepared_value_file") is True
    argv = build_bridge_argv("desktopSetValue", prepared)

    assert "--value-file" in argv
    assert "--value" not in argv
    assert "private text" not in argv
    assert temp_paths and temp_paths[0].read_text(encoding="utf-8") == "private text"
    assert temp_paths[0].stat().st_mode & 0o777 == 0o600
    for path in temp_paths:
        path.unlink(missing_ok=True)


def test_connector_codex_visible_message_moves_raw_message_to_temp_file(tmp_path: Path) -> None:
    prepared, temp_paths = _prepare_connector_params(
        "codexSendVisibleMessage",
        {"thread_id": "visible-0-abc", "message": "secret prompt"},
        state_dir=tmp_path,
    )

    assert "message" not in prepared
    assert prepared["message_file"].startswith(str(tmp_path))
    assert prepared["_prepared_message_file"] is True
    assert temp_paths == [Path(prepared["message_file"])]
    assert temp_paths[0].read_text(encoding="utf-8") == "secret prompt"
    argv = build_bridge_argv("codexSendVisibleMessage", prepared)
    assert "--message-file" in argv
    assert "secret prompt" not in argv
    temp_paths[0].unlink()


def test_connector_rejects_client_supplied_codex_visible_message_file(tmp_path: Path) -> None:
    try:
        _prepare_connector_params(
            "codexSendVisibleMessage",
            {"thread_id": "visible-0-abc", "message_file": "/etc/passwd"},
            state_dir=tmp_path,
        )
    except ValueError as exc:
        assert "message_file is reserved" in str(exc)
    else:
        raise AssertionError("expected connector to reject client-supplied message_file")


def test_connector_cleans_temp_message_file_if_write_fails(tmp_path: Path, monkeypatch) -> None:
    def fail_write(_fd: int, _payload: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr("evaos_desktop_bridge.connector_server.os.write", fail_write)

    try:
        _prepare_connector_params(
            "codexSendVisibleMessage",
            {"thread_id": "visible-0-abc", "message": "secret prompt"},
            state_dir=tmp_path,
        )
    except OSError as exc:
        assert "disk full" in str(exc)
    else:
        raise AssertionError("expected failing temp write to propagate")
    assert list((tmp_path / "tmp").glob("codex-visible-message-*")) == []


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


def test_connector_rejects_removed_codex_remote_tool_before_runner(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        return 0, json.dumps({"ok": True})

    handler = _make_handler(token="secret-token", command_runner=runner, state_dir=tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request(
            "POST",
            "/v1/commands",
            body=json.dumps(
                {
                    "command": "desktop_bridge_codex_remote_start_turn",
                    "params": {
                        "thread_id": "thread-1",
                        "message": "continue",
                        "dry_run": False,
                        "confirm": True,
                        "source_audit_id": "audit-forged",
                    },
                }
            ),
            headers={"Content-Type": "application/json", "Authorization": "Bearer secret-token"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 400
        assert calls == []
        assert payload["target"] == "desktop"
        assert payload["errors"][0]["code"] == "connector_bad_request"
        assert "Unsupported connector command" in payload["errors"][0]["message"]
    finally:
        server.shutdown()
        thread.join(timeout=2)


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


def test_connector_token_reads_existing_per_user_default(tmp_path: Path) -> None:
    token_path = tmp_path / "connector.token"
    token_path.write_text("secret-token\n", encoding="utf-8")

    assert read_token(None, state_dir=tmp_path, auto_create=False) == "secret-token"


def test_connector_health_liveness_differs_from_ready_without_token(tmp_path: Path) -> None:
    handler = _make_handler(token=None, command_runner=lambda _argv: (0, "{}"), state_dir=tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request("GET", "/health")
        health_response = conn.getresponse()
        health_payload = json.loads(health_response.read().decode("utf-8"))

        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request("GET", "/ready")
        ready_response = conn.getresponse()
        ready_payload = json.loads(ready_response.read().decode("utf-8"))

        assert health_response.status == 200
        assert health_payload["ok"] is True
        assert ready_response.status == 503
        assert ready_payload["ok"] is False
        assert ready_payload["schema"] == "evaos.desktop_bridge.ready.v1"
        assert ready_payload["blockers"][0]["code"] == "token_missing"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_connector_ready_and_diagnostics_are_redacted(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "secret-token-abcdef1234567890"  # noqa: S105 - intentional redaction fixture
    api_key_fixture = "api-key-abcdef1234567890"  # noqa: S105 - intentional redaction fixture
    monkeypatch.setenv(
        "EVAOS_DESKTOP_BRIDGE_MODE",
        f"support http://100.64.1.10:8765/bootstrap?token={token_fixture}",
    )
    record_service_event(
        "bind_failed",
        "blocker",
        f"failed to bind http://100.64.1.10:8765 with token={token_fixture} and Authorization: Bearer {api_key_fixture}",
        state_dir=tmp_path,
        details={
            "apiKey": api_key_fixture,
            "api-key": api_key_fixture,
            "host": "127.0.0.1",
            "connector_url": "http://100.64.1.10:8765",
            "refreshToken": token_fixture,
            "tailnet_ip": "100.64.1.10",
            "connector_token": token_fixture,
            "port": 8765,
        },
    )

    ready = build_ready_payload(token=token_fixture, state_dir=tmp_path)
    diagnostics = build_diagnostics_payload(token=token_fixture, state_dir=tmp_path)
    serialized = json.dumps(diagnostics, sort_keys=True)

    assert ready["ok"] is True
    assert ready["token_state"] == "present"
    assert diagnostics["schema"] == "evaos.desktop_bridge.diagnostics.v1"
    assert diagnostics["connector"]["token_state"] == "present"
    assert token_fixture not in serialized
    assert api_key_fixture not in serialized
    assert "100.64.1.10" not in serialized
    assert "127.0.0.1" not in serialized
    assert "http://100.64.1.10:8765" not in serialized
    assert diagnostics["bridge"]["mode"] == "support <redacted-url>"
    assert diagnostics["service_events"][0]["message"] == "failed to bind <redacted-url> with <redacted-secret> and Authorization: <redacted-secret>"
    assert diagnostics["service_events"][0]["details"]["apiKey"] == "<redacted>"
    assert diagnostics["service_events"][0]["details"]["api-key"] == "<redacted>"
    assert diagnostics["service_events"][0]["details"]["connector_token"] == "<redacted>"
    assert diagnostics["service_events"][0]["details"]["host"] == "<redacted>"
    assert diagnostics["service_events"][0]["details"]["refreshToken"] == "<redacted>"
    assert diagnostics["service_events"][0]["details"]["tailnet_ip"] == "<redacted>"


def test_connector_http_diagnostics_route_is_redacted(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "secret-token-abcdef1234567890"  # noqa: S105 - intentional redaction fixture
    monkeypatch.setenv(
        "EVAOS_DESKTOP_BRIDGE_MODE",
        f"support http://100.64.1.10:8765/bootstrap?token={token_fixture}",
    )
    record_service_event(
        "port_in_use",
        "blocker",
        f"existing listener at 100.64.1.10:8765 used token={token_fixture}",
        state_dir=tmp_path,
        details={"host": "100.64.1.10", "connector_token": token_fixture},
    )
    handler = _make_handler(token=token_fixture, command_runner=lambda _argv: (0, "{}"), state_dir=tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request("GET", "/v1/diagnostics")
        unauthorized_response = conn.getresponse()
        assert unauthorized_response.status == 401
        unauthorized_response.read()

        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request("GET", "/v1/diagnostics", headers={"Authorization": f"Bearer {token_fixture}"})
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        payload = json.loads(body)

        assert response.status == 200
        assert payload["schema"] == "evaos.desktop_bridge.diagnostics.v1"
        assert payload["connector"]["token_state"] == "present"
        assert token_fixture not in body
        assert "100.64.1.10" not in body
        assert "127.0.0.1" not in body
        assert "http://100.64.1.10:8765" not in body
        assert payload["service_events"][0]["details"]["host"] == "<redacted>"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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


def test_connector_removed_codex_remote_rejection_is_bad_request(tmp_path: Path) -> None:
    handler = _make_handler(token="secret-token", command_runner=lambda _argv: (0, "{}"), state_dir=tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request(
            "POST",
            "/v1/commands",
            body=json.dumps(
                {
                    "command": "desktop_bridge_codex_remote_start_turn",
                    "params": {"thread_id": "thread-1", "message": "continue", "dry_run": False},
                }
            ),
            headers={"Content-Type": "application/json", "Authorization": "Bearer secret-token"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 400
        assert payload["target"] == "desktop"
        assert payload["errors"][0]["code"] == "connector_bad_request"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_connector_serves_visual_artifacts_with_token(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    artifact_dir.joinpath("snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png").write_bytes(b"\x89PNG\r\n\x1a\nartifact")
    handler = _make_handler(token="secret-token", command_runner=lambda _argv: (0, "{}"), state_dir=tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request(
            "GET",
            "/v1/artifacts/snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
            headers={"Authorization": "Bearer secret-token"},
        )
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "image/png"
        assert response.read().startswith(b"\x89PNG")
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
