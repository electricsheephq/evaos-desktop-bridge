from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from evaos_desktop_bridge.cli import main
from evaos_desktop_bridge.types import CommandResult


@dataclass
class FakeObserver:
    mode: str = "ok"

    def status(self) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "app": {
                    "installed": self.mode != "absent",
                    "running": self.mode != "absent",
                    "pid": 123 if self.mode != "absent" else None,
                },
                "permissions": {
                    "accessibility": {"status": "granted"},
                    "screen_recording": {"status": "unknown"},
                },
            },
        )

    def frontmost(self) -> CommandResult:
        return CommandResult(ok=True, data={"frontmost_app": "Codex", "window_title": "Codex", "codex_frontmost": True})

    def windows(self) -> CommandResult:
        return CommandResult(ok=True, data={"windows": [{"index": 0, "title": "Codex", "role": "AXWindow", "bounds": {"x": 1, "y": 2, "width": 3, "height": 4}, "codex_frontmost": True}], "count": 1})

    def threads(self, *, max_items: int) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "threads": [
                    {
                        "visible_id": "visible-0-abc",
                        "index": 0,
                        "title": "Implement bridge",
                        "role": "AXStaticText",
                        "bounds": {"x": 10, "y": 20, "width": 100, "height": 40},
                        "center": {"x": 60, "y": 40},
                        "confidence": "medium",
                        "source": "ax",
                    }
                ][:max_items],
                "count": min(max_items, 1),
                "max_items": max_items,
                "source": "ax",
            },
        )

    def focus(self, *, dry_run: bool = False) -> CommandResult:
        if dry_run:
            return CommandResult(ok=True, data={"would_focus": True, "focused": False})
        if self.mode == "missing_permission":
            return CommandResult(
                ok=False,
                data={"focused": False},
                errors=[
                    {
                        "code": "permission_missing",
                        "message": "Accessibility permission is required.",
                        "guidance": "Enable Accessibility for the terminal running evaos-desktop-bridge.",
                        "permission": "accessibility",
                    }
                ],
            )
        return CommandResult(ok=True, data={"focused": True})

    def select_thread(self, *, thread_id: str, dry_run: bool = False) -> CommandResult:
        if thread_id != "visible-0-abc":
            return CommandResult(ok=False, data={"selected": False}, errors=[{"code": "visible_thread_not_found", "message": "missing", "guidance": "rerun threads"}])
        if dry_run:
            return CommandResult(ok=True, data={"selected": False, "would_select": True, "thread_id": thread_id})
        return CommandResult(ok=True, data={"selected": True, "thread_id": thread_id})

    def continue_thread(self, *, title: str, prompt: str = "continue", dry_run: bool = False) -> CommandResult:
        if title != "SDK Docs":
            return CommandResult(ok=False, data={"submitted": False}, errors=[{"code": "codex_thread_title_not_unique", "message": "missing", "guidance": "rerun threads"}])
        return CommandResult(ok=True, data={"submitted": not dry_run, "would_submit": dry_run, "title": title, "prompt_preview": prompt})

    def snapshot(self, *, max_chars: int) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "frontmost_app": "Codex",
                "window_title": "Codex",
                "screenshot_path": "~/Library/Application Support/evaos-desktop-bridge/screenshots/test.png",
                "max_chars": max_chars,
            },
        )

    def inspect(self, *, max_nodes: int) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "frontmost": {"codex_frontmost": True},
                "windows": [{"index": 0, "title": "Codex"}],
                "ax": {"nodes": [{"role": "AXButton", "name": "New chat", "depth": 0, "window_index": 0}], "truncated": False, "max_nodes": max_nodes},
                "summary": {"window_count": 1, "codex_frontmost": True, "visible_buttons": [{"role": "AXButton", "name": "New chat", "depth": 0, "window_index": 0}], "visible_text": []},
            },
        )

    def ax_tree(self, *, max_nodes: int) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "nodes": [
                    {"role": "AXWindow", "name": "Codex"},
                    {"role": "AXButton", "name": "New Chat"},
                ][:max_nodes],
                "truncated": max_nodes < 2,
            },
            warnings=["AX tree truncated"] if max_nodes < 2 else [],
        )

@dataclass
class FakeCustomerMac:
    mode: str = "ok"

    def status(self) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "platform": "Darwin",
                "device": {"id": "mac-test", "hostname": "test-mac"},
                "permissions": {"accessibility": {"status": "granted"}, "screen_recording": {"status": "unknown"}},
                "iphone_mirroring": {"installed": True, "running": True, "supported_actions": ["home", "spotlight"]},
                "screen_sharing": {"enabled": self.mode == "screen_sharing_enabled", "bridge_can_enable": False},
                "safety": {"named_actions_only": True, "generic_coordinates_blocked": True},
            },
        )

    def capabilities(self) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "supported_targets": ["mac", "local_site", "iphone_mirroring", "screen_sharing_status"],
                "forbidden": ["generic_remote_desktop_passthrough", "generic_coordinates"],
                "approval_gates": {"screen_sharing_enablement": "explicit approval required"},
            },
        )

    def snapshot(self, *, max_chars: int) -> CommandResult:
        return CommandResult(ok=True, data={"frontmost_app": "Safari", "screenshot_path": "~/Library/Application Support/evaos-desktop-bridge/screenshots/customer-mac.png", "max_chars": max_chars})

    def ax_tree(self, *, max_nodes: int) -> CommandResult:
        return CommandResult(ok=True, data={"frontmost_app": "Safari", "nodes": [{"role": "AXButton", "name": "Reload"}][:max_nodes], "truncated": False, "max_nodes": max_nodes})

    def app_focus(self, *, app_name: str, dry_run: bool = False) -> CommandResult:
        if app_name == "Messages":
            return CommandResult(ok=False, data={"focused": False}, errors=[{"code": "sensitive_app_blocked", "message": "blocked", "guidance": "use safe app"}])
        return CommandResult(ok=True, data={"focused": not dry_run, "would_focus": dry_run, "app_name": app_name})

    def local_site_open(self, *, url: str, dry_run: bool = False) -> CommandResult:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return CommandResult(ok=False, data={"opened": False, "url": url}, errors=[{"code": "local_site_url_not_allowed", "message": "blocked", "guidance": "localhost only"}])
        return CommandResult(ok=True, data={"opened": not dry_run, "would_open": dry_run, "url": url})

    def local_site_action(self, *, action: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"performed": not dry_run, "would_perform": dry_run, "action": action})

    def iphone_mirroring_status(self) -> CommandResult:
        return CommandResult(ok=True, data={"installed": True, "running": True, "supported_actions": ["home", "spotlight"], "disabled_actions": ["scroll"]})

    def iphone_mirroring_focus(self, *, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"focused": not dry_run, "would_focus": dry_run, "app_name": "iPhone Mirroring"})

    def iphone_mirroring_action(self, *, action: str, text: str | None = None, app_name: str | None = None, target_label: str | None = None, direction: str | None = None, recipient_context: str | None = None, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"performed": not dry_run, "would_perform": dry_run, "action": action, "text_preview": text, "app_name": app_name, "target_label": target_label, "direction": direction, "recipient_context": recipient_context})

    def screen_sharing_status(self) -> CommandResult:
        return CommandResult(ok=True, data={"enabled": self.mode == "screen_sharing_enabled", "bridge_can_enable": False, "approval_required_to_enable": True})


@dataclass
class FakeAppServer:
    mode: str = "ok"

    def status(self) -> CommandResult:
        return CommandResult(ok=True, data={"available": self.mode == "ok", "allowed_methods": ["thread/list"], "read_only": True})

    def threads(self, *, max_items: int) -> CommandResult:
        if self.mode != "ok":
            return CommandResult(ok=False, errors=[{"code": "app_server_unavailable", "message": "offline", "guidance": "start app-server"}])
        return CommandResult(ok=True, data={"threads": [{"index": 0, "id": "t1", "title": "Thread 1", "source": "app_server"}][:max_items], "count": 1, "max_items": max_items})

    def remote_control_status(self) -> CommandResult:
        return CommandResult(ok=True, data={"preferred_path": "codex_native_remote_control", "safety": {"read_only_probe": True}})


def run_cli(argv: list[str], observer: FakeObserver, tmp_path: Path) -> dict:
    stdout = io.StringIO()
    exit_code = main(
        argv,
        observer_factory=lambda: observer,
        customer_mac_factory=lambda: FakeCustomerMac(),
        app_server_factory=lambda: FakeAppServer(),
        stdout=stdout,
        state_dir=tmp_path,
    )
    payload = json.loads(stdout.getvalue())
    payload["_exit_code"] = exit_code
    return payload


def test_status_json_reports_absent_codex_without_error(tmp_path: Path) -> None:
    payload = run_cli(["status", "--json"], FakeObserver(mode="absent"), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["ok"] is True
    assert payload["command"] == "status"
    assert payload["target"] == "desktop"
    assert payload["data"]["app"]["installed"] is False
    assert payload["data"]["app"]["pid"] is None
    assert payload["audit_id"]


def test_capabilities_reports_read_only_surface(tmp_path: Path) -> None:
    payload = run_cli(["capabilities", "--json"], FakeObserver(), tmp_path)

    assert payload["command"] == "capabilities"
    snapshot = next(command for command in payload["data"]["commands"] if command["id"] == "codex.snapshot")
    assert snapshot["target"] == "codex"
    assert snapshot["mode"] == "read_only"
    assert "send_prompts_or_messages" in payload["data"]["forbidden"]
    assert payload["data"]["data_minimization"]["append_only_audit_log"] is True


def test_latest_returns_last_observation_without_overwriting_it(tmp_path: Path) -> None:
    status_payload = run_cli(["status", "--json"], FakeObserver(mode="absent"), tmp_path)
    latest_payload = run_cli(["latest", "--json"], FakeObserver(), tmp_path)

    assert latest_payload["_exit_code"] == 0
    assert latest_payload["command"] == "latest"
    assert latest_payload["data"]["latest"]["audit_id"] == status_payload["audit_id"]
    assert latest_payload["data"]["latest"]["command"] == "status"


def test_latest_missing_is_graceful_json(tmp_path: Path) -> None:
    payload = run_cli(["latest", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 2
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "latest_not_found"


def test_audit_tail_returns_redacted_records(tmp_path: Path) -> None:
    run_cli(["status", "--json"], FakeObserver(), tmp_path)
    run_cli(["codex", "snapshot", "--json", "--max-chars", "20"], FakeObserver(), tmp_path)

    payload = run_cli(["audit-tail", "--json", "--limit", "2"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "audit_tail"
    assert payload["data"]["count"] == 2
    assert [record["command"] for record in payload["data"]["records"]] == ["status", "codex.snapshot"]


def test_frontmost_json_reports_codex_state(tmp_path: Path) -> None:
    payload = run_cli(["codex", "frontmost", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.frontmost"
    assert payload["data"]["codex_frontmost"] is True


def test_windows_json_lists_visible_codex_windows(tmp_path: Path) -> None:
    payload = run_cli(["codex", "windows", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.windows"
    assert payload["data"]["count"] == 1
    assert payload["data"]["windows"][0]["role"] == "AXWindow"


def test_threads_json_lists_visible_thread_candidates(tmp_path: Path) -> None:
    payload = run_cli(["codex", "threads", "--json", "--max-items", "1"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.threads"
    assert payload["data"]["threads"][0]["visible_id"] == "visible-0-abc"
    assert payload["data"]["threads"][0]["source"] == "ax"


def test_focus_dry_run_does_not_focus_or_require_permission(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "focus", "--json", "--dry-run"],
        FakeObserver(mode="missing_permission"),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.focus"
    assert payload["data"] == {"would_focus": True, "focused": False}


def test_select_thread_dry_run_is_audited_visible_action(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "select-thread", "--json", "--thread-id", "visible-0-abc", "--dry-run"],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.select_thread"
    assert payload["data"]["would_select"] is True


def test_continue_thread_support_fallback_requires_matching_dry_run_audit(tmp_path: Path) -> None:
    rejected = run_cli(["codex", "continue-thread", "--json", "--title", "SDK Docs"], FakeObserver(), tmp_path)

    assert rejected["_exit_code"] == 2
    assert rejected["errors"][0]["code"] == "approval_audit_required"

    dry_run = run_cli(["codex", "continue-thread", "--json", "--title", "SDK Docs", "--dry-run"], FakeObserver(), tmp_path)
    approved = run_cli(["codex", "continue-thread", "--json", "--title", "SDK Docs", "--approval-audit-id", dry_run["audit_id"]], FakeObserver(), tmp_path)

    assert approved["_exit_code"] == 0
    assert approved["command"] == "codex.continue_thread"
    assert approved["data"]["submitted"] is True


def test_focus_permission_error_is_graceful_json(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "focus", "--json"],
        FakeObserver(mode="missing_permission"),
        tmp_path,
    )

    assert payload["_exit_code"] == 2
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "permission_missing"
    assert payload["errors"][0]["permission"] == "accessibility"
    assert "System Settings" in payload["errors"][0]["guidance"] or "Accessibility" in payload["errors"][0]["guidance"]


def test_snapshot_json_honors_max_chars(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "snapshot", "--json", "--max-chars", "4000"],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.snapshot"
    assert payload["data"]["max_chars"] == 4000
    assert payload["data"]["screenshot_path"].startswith("~/")


def test_inspect_json_returns_page_map(tmp_path: Path) -> None:
    payload = run_cli(["codex", "inspect", "--json", "--max-nodes", "20"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.inspect"
    assert payload["data"]["summary"]["codex_frontmost"] is True
    assert payload["data"]["summary"]["visible_buttons"][0]["name"] == "New chat"


def test_ax_tree_json_honors_max_nodes_and_reports_truncation(tmp_path: Path) -> None:
    payload = run_cli(
        ["codex", "ax-tree", "--json", "--max-nodes", "1"],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.ax_tree"
    assert len(payload["data"]["nodes"]) == 1
    assert payload["data"]["truncated"] is True
    assert payload["warnings"] == ["AX tree truncated"]


def test_app_server_status_json_reports_allowlist(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "status", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.status"
    assert payload["data"]["read_only"] is True


def test_app_server_threads_json_is_capped(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "threads", "--json", "--max-items", "1"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.threads"
    assert payload["data"]["threads"][0]["source"] == "app_server"


def test_app_server_remote_control_status_is_read_only(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "remote-control-status", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.remote_control_status"
    assert payload["data"]["safety"]["read_only_probe"] is True


def test_customer_mac_status_reports_device_and_safety(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "status", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "customer_mac.status"
    assert payload["target"] == "customer_mac"
    assert payload["data"]["device"]["id"] == "mac-test"
    assert payload["data"]["safety"]["generic_coordinates_blocked"] is True


def test_customer_mac_capabilities_names_supported_surfaces(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "capabilities", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert "iphone_mirroring" in payload["data"]["supported_targets"]
    assert "generic_coordinates" in payload["data"]["forbidden"]


def test_customer_mac_snapshot_is_latest_observation(tmp_path: Path) -> None:
    snapshot_payload = run_cli(["customer-mac", "snapshot", "--json", "--max-chars", "40"], FakeObserver(), tmp_path)
    latest_payload = run_cli(["latest", "--json"], FakeObserver(), tmp_path)

    assert snapshot_payload["_exit_code"] == 0
    assert snapshot_payload["command"] == "customer_mac.snapshot"
    assert latest_payload["data"]["latest"]["command"] == "customer_mac.snapshot"


def test_customer_mac_app_focus_defaults_to_dry_run(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "app-focus", "--json", "--app-name", "Safari", "--dry-run"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["data"]["would_focus"] is True
    assert payload["data"]["focused"] is False


def test_customer_mac_app_focus_live_requires_matching_dry_run_audit(tmp_path: Path) -> None:
    rejected = run_cli(["customer-mac", "app-focus", "--json", "--app-name", "Safari"], FakeObserver(), tmp_path)

    assert rejected["_exit_code"] == 2
    assert rejected["errors"][0]["code"] == "approval_audit_required"

    dry_run = run_cli(["customer-mac", "app-focus", "--json", "--app-name", "Safari", "--dry-run"], FakeObserver(), tmp_path)
    approved = run_cli(["customer-mac", "app-focus", "--json", "--app-name", "Safari", "--approval-audit-id", dry_run["audit_id"]], FakeObserver(), tmp_path)
    mismatch = run_cli(["customer-mac", "app-focus", "--json", "--app-name", "Messages", "--approval-audit-id", dry_run["audit_id"]], FakeObserver(), tmp_path)

    assert approved["_exit_code"] == 0
    assert approved["data"]["focused"] is True
    assert mismatch["_exit_code"] == 2
    assert mismatch["errors"][0]["code"] == "approval_audit_required"
    assert "app_name" in mismatch["errors"][0]["message"]


def test_customer_mac_local_site_rejects_nonlocal_urls(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "local-site", "open", "--json", "--url", "https://example.com", "--dry-run"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 2
    assert payload["errors"][0]["code"] == "local_site_url_not_allowed"


def test_customer_mac_local_site_allows_loopback_ip(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "local-site", "open", "--json", "--url", "http://127.0.0.1:3000", "--dry-run"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["data"]["url"] == "http://127.0.0.1:3000"


def test_customer_mac_local_site_rejects_localhost_prefix_bypass(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "local-site", "open", "--json", "--url", "http://localhost.evil.com", "--dry-run"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 2
    assert payload["errors"][0]["code"] == "local_site_url_not_allowed"


def test_customer_mac_iphone_mirroring_named_actions(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "iphone-mirroring", "open-app", "--json", "--app-name", "Calculator", "--dry-run"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "customer_mac.iphone_mirroring_open_app"
    assert payload["data"]["would_perform"] is True
    assert payload["data"]["app_name"] == "Calculator"


def test_customer_mac_iphone_mirroring_scroll_requires_approval_for_live(tmp_path: Path) -> None:
    rejected = run_cli(["customer-mac", "iphone-mirroring", "scroll", "--json"], FakeObserver(), tmp_path)

    assert rejected["_exit_code"] == 2
    assert rejected["errors"][0]["code"] == "approval_audit_required"

    dry_run = run_cli(["customer-mac", "iphone-mirroring", "scroll", "--json", "--direction", "down", "--dry-run"], FakeObserver(), tmp_path)
    approved = run_cli(["customer-mac", "iphone-mirroring", "scroll", "--json", "--direction", "down", "--approval-audit-id", dry_run["audit_id"]], FakeObserver(), tmp_path)

    assert approved["_exit_code"] == 0
    assert approved["data"]["action"] == "scroll"
    assert approved["data"]["direction"] == "down"


def test_customer_mac_iphone_mirroring_send_approved_message_is_guarded(tmp_path: Path) -> None:
    rejected = run_cli(
        ["customer-mac", "iphone-mirroring", "send-approved-message", "--json", "--text", "Hello", "--recipient-context", "Bumble canary profile"],
        FakeObserver(),
        tmp_path,
    )

    assert rejected["_exit_code"] == 2
    assert rejected["errors"][0]["code"] == "approval_audit_required"

    dry_run = run_cli(
        ["customer-mac", "iphone-mirroring", "send-approved-message", "--json", "--text", "Hello", "--recipient-context", "Bumble canary profile", "--dry-run"],
        FakeObserver(),
        tmp_path,
    )
    approved = run_cli(
        ["customer-mac", "iphone-mirroring", "send-approved-message", "--json", "--text", "Hello", "--recipient-context", "Bumble canary profile", "--approval-audit-id", dry_run["audit_id"]],
        FakeObserver(),
        tmp_path,
    )

    assert approved["_exit_code"] == 0
    assert approved["data"]["action"] == "send_approved_message"
    assert approved["data"]["recipient_context"] == "Bumble canary profile"


def test_customer_mac_screen_sharing_status_cannot_enable(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "screen-sharing", "status", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "customer_mac.screen_sharing_status"
    assert payload["data"]["bridge_can_enable"] is False


def test_queue_append_and_list_json(tmp_path: Path) -> None:
    status_payload = run_cli(["status", "--json"], FakeObserver(), tmp_path)
    append_payload = run_cli(
        ["queue", "append", "--json", "--kind", "attention", "--source-audit-id", status_payload["audit_id"], "--message", "Check Codex"],
        FakeObserver(),
        tmp_path,
    )
    list_payload = run_cli(["queue", "list", "--json"], FakeObserver(), tmp_path)

    assert append_payload["_exit_code"] == 0
    assert append_payload["command"] == "queue.append"
    assert list_payload["data"]["events"][0]["kind"] == "attention"


def test_disallowed_command_is_not_registered(tmp_path: Path) -> None:
    stdout = io.StringIO()
    exit_code = main(
        ["codex", "send", "--json"],
        observer_factory=FakeObserver,
        stdout=stdout,
        stderr=io.StringIO(),
        state_dir=tmp_path,
    )

    assert exit_code == 2
