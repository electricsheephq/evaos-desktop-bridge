from __future__ import annotations

from evaos_desktop_bridge.connector_server import _live_guarded_without_approval, build_bridge_argv


def test_connector_builds_fixed_status_argv() -> None:
    assert build_bridge_argv("customerMacStatus") == ["customer-mac", "status", "--json"]
    assert build_bridge_argv("customerMacIphoneMirroringStatus") == ["customer-mac", "iphone-mirroring", "status", "--json"]


def test_connector_defaults_guarded_commands_to_dry_run() -> None:
    assert build_bridge_argv("customerMacAppFocus", {"app_name": "Safari"}) == [
        "customer-mac",
        "app-focus",
        "--json",
        "--app-name",
        "Safari",
        "--dry-run",
    ]


def test_connector_allows_live_argv_only_when_requested_by_server_policy() -> None:
    assert build_bridge_argv("customerMacAppFocus", {"app_name": "Safari", "dry_run": False}) == [
        "customer-mac",
        "app-focus",
        "--json",
        "--app-name",
        "Safari",
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
    assert _live_guarded_without_approval("customerMacAppFocus", {"app_name": "Safari", "dry_run": True}) is False
    assert _live_guarded_without_approval("customerMacAppFocus", {"app_name": "Safari", "dry_run": False, "approval_audit_id": "audit-1"}) is False
    assert _live_guarded_without_approval("customerMacStatus", {}) is False
    argv = build_bridge_argv("customerMacAppFocus", {"app_name": "Safari", "dry_run": False, "approval_audit_id": "audit-1"})
    assert "--approval-audit-id" in argv
    assert "audit-1" in argv
