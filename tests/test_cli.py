from __future__ import annotations

import io
import json
import plistlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from evaos_desktop_bridge import cli as bridge_cli
from evaos_desktop_bridge.cli import main
from evaos_desktop_bridge.state import kill_control_session, start_control_session
from evaos_desktop_bridge.types import CommandResult


def rewrite_audit_timestamp(state_dir: Path, audit_id: str, timestamp: str) -> None:
    audit_path = state_dir / "audit.jsonl"
    updated: list[str] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("audit_id") == audit_id:
            record["timestamp"] = timestamp
        updated.append(json.dumps(record, sort_keys=True, separators=(",", ":")))
    audit_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


@dataclass
class FakeObserver:
    mode: str = "ok"
    title_hidden: bool = False

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
        thread = {
            "visible_id": "visible-0-abc",
            "index": 0,
            "title": "Implement bridge",
            "role": "AXStaticText",
            "bounds": {"x": 10, "y": 20, "width": 100, "height": 40},
            "center": {"x": 60, "y": 40},
            "confidence": "medium",
            "source": "ax",
        }
        if self.title_hidden:
            thread.update(
                {
                    "title": "Visible thread row 1 (title unavailable)",
                    "raw_title": "title_unavailable",
                    "title_available": False,
                    "selection_only": True,
                    "updated_label": "1m",
                    "confidence": "low",
                }
            )
        return CommandResult(
            ok=True,
            data={
                "threads": [thread][:max_items],
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

    def send_visible_message(self, *, thread_id: str, message: str, dry_run: bool = True, confirmed: bool = False) -> CommandResult:
        if thread_id != "visible-0-abc":
            return CommandResult(ok=False, data={"submitted": False}, errors=[{"code": "visible_thread_not_found", "message": "missing", "guidance": "rerun threads"}])
        if not dry_run and not confirmed:
            return CommandResult(ok=False, data={"submitted": False}, errors=[{"code": "visible_message_confirmation_required", "message": "confirm required", "guidance": "pass --confirm"}])
        digest = bridge_cli._short_hash(message.strip())
        return CommandResult(
            ok=True,
            data={
                "thread_id": thread_id,
                "target": self.threads(max_items=1).data["threads"][0],
                "would_submit": dry_run,
                "submitted": not dry_run,
                "message_preview": message.strip(),
                "message_hash": digest,
                "provenance": {"source": "codex_visible_gui"},
            },
            provenance={"source": "codex_visible_gui", "dry_run": dry_run, "selected_visible_target_id": thread_id, "message_hash": digest},
        )

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
                "safety": {"full_access_allows_coordinates": True, "kill_switch_available": True},
            },
        )

    def capabilities(self) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "supported_targets": ["mac", "local_site", "iphone_mirroring", "screen_sharing_status"],
                "forbidden": ["public_mac_ports", "hidden_shell", "credential_collection", "security_bypass"],
                "approval_gates": {"screen_sharing_enablement": "explicit approval required"},
            },
        )

    def control_status(self) -> CommandResult:
        return CommandResult(ok=True, data={"active": False, "mode": "ask_permission", "kill_switch": False})

    def control_start(self, *, mode: str, agent_label: str | None = None) -> CommandResult:
        return CommandResult(ok=True, data={"started": True, "session": {"active": True, "mode": mode.replace("-", "_"), "agent_label": agent_label}})

    def control_stop(self) -> CommandResult:
        return CommandResult(ok=True, data={"stopped": True, "session": {"active": False, "mode": "ask_permission"}})

    def control_kill_switch(self) -> CommandResult:
        return CommandResult(ok=True, data={"killed": True, "session": {"active": False, "kill_switch": True}})

    def desktop_see(self, *, max_chars: int, max_nodes: int) -> CommandResult:
        return CommandResult(ok=True, data={"engine": "fallback", "frontmost_app": "Safari", "max_chars": max_chars, "max_nodes": max_nodes})

    def desktop_click(self, *, target_label: str | None = None, x: int | None = None, y: int | None = None, snapshot_id: str | None = None, element_id: str | None = None, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"clicked": not dry_run, "would_click": dry_run, "target_label": target_label, "snapshot_id": snapshot_id, "element_id": element_id, "point": {"x": x, "y": y} if x is not None and y is not None else None})

    def desktop_type(self, *, text: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"typed": not dry_run, "would_type": dry_run, "text_preview": text})

    def desktop_scroll(self, *, direction: str, amount: int, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"scrolled": not dry_run, "would_scroll": dry_run, "direction": direction, "amount": amount})

    def desktop_drag(self, *, from_x: int, from_y: int, to_x: int, to_y: int, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"dragged": not dry_run, "would_drag": dry_run, "from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}})

    def desktop_hotkey(self, *, keys: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"pressed": not dry_run, "would_press": dry_run, "keys": keys})

    def desktop_focus_app(self, *, app_name: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"focused": not dry_run, "would_focus": dry_run, "app_name": app_name})

    def desktop_window(self, *, action: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"performed": not dry_run, "would_perform": dry_run, "action": action})

    def desktop_menu(self, *, menu_path: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"performed": not dry_run, "would_perform": dry_run, "menu_path": menu_path})

    def desktop_browser_action(self, *, action: str, url: str | None = None, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"performed": not dry_run, "would_perform": dry_run, "action": action, "url": url})

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

    def iphone_see(self, *, max_chars: int, max_nodes: int) -> CommandResult:
        return CommandResult(ok=True, data={"target": "iphone_mirroring", "max_chars": max_chars, "max_nodes": max_nodes})

    def iphone_tap(self, *, target_label: str | None = None, x: int | None = None, y: int | None = None, snapshot_id: str | None = None, element_id: str | None = None, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"performed": not dry_run, "would_tap": dry_run, "target_label": target_label, "snapshot_id": snapshot_id, "element_id": element_id})

    def iphone_swipe(self, *, direction: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"performed": not dry_run, "would_perform": dry_run, "direction": direction})

    def iphone_type(self, *, text: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"performed": not dry_run, "would_type": dry_run, "text_preview": text})

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
        return CommandResult(
            ok=True,
            data={
                "available": self.mode == "ok",
                "cli_available": True,
                "rpc_handshake_ok": self.mode == "ok",
                "selected_cli": {"path": "codex", "version": "codex-cli test"},
                "allowed_methods": ["thread/list"],
                "read_only": True,
            },
        )

    def connections_status(self) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "app_server": {"available": self.mode == "ok", "transport": "stdio"},
                "remote_control": {"supported": True},
                "safety": {"read_only_default": True, "controller_requires_confirmation": True},
            },
        )

    def threads(self, *, max_items: int) -> CommandResult:
        if self.mode != "ok":
            return CommandResult(ok=False, errors=[{"code": "app_server_unavailable", "message": "offline", "guidance": "start app-server"}])
        return CommandResult(ok=True, data={"threads": [{"index": 0, "id": "t1", "title": "Implement bridge", "source": "app_server"}][:max_items], "count": 1, "max_items": max_items, "thread_state": "active"})

    def loaded_threads(self, *, max_items: int) -> CommandResult:
        return CommandResult(ok=True, data={"threads": [{"index": 0, "id": "t1", "source": "app_server_loaded"}][:max_items], "count": 1, "max_items": max_items})

    def subscribe(self, *, thread_id: str, duration_ms: int, max_chars: int) -> CommandResult:
        return CommandResult(ok=True, data={"thread_id": thread_id, "duration_ms": duration_ms, "events": [{"method": "turn/started"}]})

    def remote_control_status(self) -> CommandResult:
        return CommandResult(ok=True, data={"preferred_path": "codex_native_remote_control", "connections_state": "disabled", "safety": {"read_only_probe": True}})

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
    assert "unguarded_send_prompts_or_messages" in payload["data"]["forbidden"]
    assert payload["data"]["guarded_prompt_or_message_commands"] == ["codex.send_visible_message"]
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


def test_thread_map_json_merges_visible_and_app_server_candidates(tmp_path: Path) -> None:
    payload = run_cli(["codex", "thread-map", "--json", "--max-items", "5"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.thread_map"
    assert payload["data"]["visible_threads"][0]["visible_id"] == "visible-0-abc"
    assert payload["data"]["app_server_threads"][0]["id"] == "t1"
    assert payload["data"]["matches"][0]["visible_id"] == "visible-0-abc"
    assert payload["data"]["matches"][0]["app_server_id"] == "t1"


def test_thread_map_json_order_matches_title_hidden_visible_rows(tmp_path: Path) -> None:
    payload = run_cli(["codex", "thread-map", "--json", "--max-items", "5"], FakeObserver(title_hidden=True), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["data"]["matches"][0]["visible_id"] == "visible-0-abc"
    assert payload["data"]["matches"][0]["app_server_id"] == "t1"
    assert payload["data"]["matches"][0]["match_reason"] == "visible_order_title_hidden"


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


def test_send_visible_message_requires_matching_dry_run_message_hash(tmp_path: Path) -> None:
    rejected = run_cli(
        ["codex", "send-visible-message", "--json", "--thread-id", "visible-0-abc", "--message", "hello", "--live", "--confirm"],
        FakeObserver(),
        tmp_path,
    )

    assert rejected["_exit_code"] == 2
    assert rejected["errors"][0]["code"] == "approval_audit_required"
    assert rejected["data"]["required_fields"] == ["thread_id", "message_hash"]

    dry_run = run_cli(
        ["codex", "send-visible-message", "--json", "--thread-id", "visible-0-abc", "--message", "hello", "--dry-run"],
        FakeObserver(),
        tmp_path,
    )
    approved = run_cli(
        [
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
            dry_run["audit_id"],
        ],
        FakeObserver(),
        tmp_path,
    )
    mismatch = run_cli(
        [
            "codex",
            "send-visible-message",
            "--json",
            "--thread-id",
            "visible-0-abc",
            "--message",
            "different",
            "--live",
            "--confirm",
            "--approval-audit-id",
            dry_run["audit_id"],
        ],
        FakeObserver(),
        tmp_path,
    )

    assert dry_run["_exit_code"] == 0
    assert dry_run["data"]["would_submit"] is True
    assert approved["_exit_code"] == 0
    assert approved["data"]["submitted"] is True
    assert mismatch["_exit_code"] == 2
    assert "message_hash" in mismatch["errors"][0]["message"]

    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    for record in records:
        assert "message" not in record["args"]
        assert "message_hash" in record["args"]
    assert any("message_preview" in record["args"] for record in records)


def test_send_visible_message_live_requires_confirm_even_with_approval(tmp_path: Path) -> None:
    dry_run = run_cli(
        ["codex", "send-visible-message", "--json", "--thread-id", "visible-0-abc", "--message", "hello", "--dry-run"],
        FakeObserver(),
        tmp_path,
    )
    rejected = run_cli(
        ["codex", "send-visible-message", "--json", "--thread-id", "visible-0-abc", "--message", "hello", "--live", "--approval-audit-id", dry_run["audit_id"]],
        FakeObserver(),
        tmp_path,
    )

    assert rejected["_exit_code"] == 2
    assert rejected["errors"][0]["code"] == "visible_message_confirmation_required"


def test_send_visible_message_accepts_message_file_without_auditing_path_or_raw_message(tmp_path: Path) -> None:
    message_file = tmp_path / "approved-message.txt"
    message_file.write_text("hello from file", encoding="utf-8")

    payload = run_cli(
        ["codex", "send-visible-message", "--json", "--thread-id", "visible-0-abc", "--message-file", str(message_file), "--dry-run"],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "message_file" not in records[-1]["args"]
    assert "message" not in records[-1]["args"]
    assert records[-1]["args"]["message_preview"] == "hello from file"
    assert str(message_file) not in (tmp_path / "audit.jsonl").read_text(encoding="utf-8")


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
    assert payload["data"]["cli_available"] is True
    assert payload["data"]["rpc_handshake_ok"] is True


def test_codex_connections_status_json_reports_safety(tmp_path: Path) -> None:
    payload = run_cli(["codex", "connections", "status", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.connections.status"
    assert payload["data"]["safety"]["read_only_default"] is True


def test_app_server_threads_json_is_capped(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "threads", "--json", "--max-items", "1"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.threads"
    assert payload["data"]["threads"][0]["source"] == "app_server"
    assert payload["data"]["thread_state"] == "active"


def test_app_server_loaded_threads_json_is_capped(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "loaded-threads", "--json", "--max-items", "1"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.loaded_threads"
    assert payload["data"]["threads"][0]["source"] == "app_server_loaded"


def test_app_server_subscribe_json_buffers_events(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "subscribe", "--json", "--thread-id", "t1", "--duration-ms", "25"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.subscribe"
    assert payload["data"]["events"][0]["method"] == "turn/started"


def test_app_server_live_controller_cli_commands_are_not_registered(tmp_path: Path) -> None:
    assert _run_cli_argparse_error(["codex", "app-server", "start-turn", "--json"], tmp_path) == 2
    assert _run_cli_argparse_error(["codex", "app-server", "steer-turn", "--json"], tmp_path) == 2
    assert _run_cli_argparse_error(["codex", "app-server", "interrupt-turn", "--json"], tmp_path) == 2


def _run_cli_argparse_error(argv: list[str], tmp_path: Path) -> int:
    stdout = io.StringIO()
    try:
        return main(
            argv,
            observer_factory=lambda: FakeObserver(),
            customer_mac_factory=lambda: FakeCustomerMac(),
            app_server_factory=lambda: FakeAppServer(),
            stdout=stdout,
            state_dir=tmp_path,
        )
    except SystemExit as exc:
        return int(exc.code)
    return 0


def test_app_server_remote_control_status_is_read_only(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "remote-control-status", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.remote_control_status"
    assert payload["data"]["connections_state"] == "disabled"
    assert payload["data"]["safety"]["read_only_probe"] is True


def test_customer_mac_status_reports_device_and_safety(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "status", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "customer_mac.status"
    assert payload["target"] == "customer_mac"
    assert payload["data"]["device"]["id"] == "mac-test"
    assert payload["data"]["safety"]["full_access_allows_coordinates"] is True
    assert payload["data"]["safety"]["kill_switch_available"] is True


def test_customer_mac_capabilities_names_supported_surfaces(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "capabilities", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert "iphone_mirroring" in payload["data"]["supported_targets"]
    assert "hidden_shell" in payload["data"]["forbidden"]


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


def test_customer_mac_full_access_session_allows_live_desktop_actions_without_approval(tmp_path: Path) -> None:
    start_control_session(mode="full_access", agent_label="Aurelius", state_dir=tmp_path)
    payload = run_cli(["customer-mac", "desktop", "type", "--json", "--text", "hello"], FakeObserver(), tmp_path)
    legacy = run_cli(["codex", "continue-thread", "--json", "--title", "SDK Docs"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "customer_mac.desktop_type"
    assert payload["data"]["typed"] is True
    assert legacy["_exit_code"] == 2
    assert legacy["errors"][0]["code"] == "approval_audit_required"


def test_customer_mac_ask_permission_allows_navigation_but_gates_text(tmp_path: Path) -> None:
    start_control_session(mode="ask_permission", agent_label="Hermes", state_dir=tmp_path)

    scroll = run_cli(["customer-mac", "desktop", "scroll", "--json", "--direction", "down"], FakeObserver(), tmp_path)
    safe_click = run_cli(["customer-mac", "desktop", "click", "--json", "--target-label", "Continue"], FakeObserver(), tmp_path)
    risky_click = run_cli(["customer-mac", "desktop", "click", "--json", "--target-label", "Send"], FakeObserver(), tmp_path)
    coordinate_click = run_cli(["customer-mac", "desktop", "click", "--json", "--x", "10", "--y", "20"], FakeObserver(), tmp_path)
    safe_hotkey = run_cli(["customer-mac", "desktop", "hotkey", "--json", "--keys", "cmd+r"], FakeObserver(), tmp_path)
    risky_hotkey = run_cli(["customer-mac", "desktop", "hotkey", "--json", "--keys", "return"], FakeObserver(), tmp_path)
    typed = run_cli(["customer-mac", "desktop", "type", "--json", "--text", "hello"], FakeObserver(), tmp_path)

    assert scroll["_exit_code"] == 0
    assert scroll["data"]["scrolled"] is True
    assert safe_click["_exit_code"] == 0
    assert risky_click["_exit_code"] == 2
    assert coordinate_click["_exit_code"] == 2
    assert safe_hotkey["_exit_code"] == 0
    assert risky_hotkey["_exit_code"] == 2
    assert typed["_exit_code"] == 2
    assert typed["errors"][0]["code"] == "approval_audit_required"


def test_customer_mac_kill_switch_blocks_live_control(tmp_path: Path) -> None:
    start_control_session(mode="full_access", agent_label="Aurelius", state_dir=tmp_path)
    kill_control_session(tmp_path)

    payload = run_cli(["customer-mac", "desktop", "scroll", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 2
    assert payload["errors"][0]["code"] == "control_kill_switch_active"


def test_customer_mac_live_approval_audit_expires(tmp_path: Path) -> None:
    dry_run = run_cli(["customer-mac", "app-focus", "--json", "--app-name", "Safari", "--dry-run"], FakeObserver(), tmp_path)
    old_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=20)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rewrite_audit_timestamp(tmp_path, dry_run["audit_id"], old_timestamp)

    rejected = run_cli(["customer-mac", "app-focus", "--json", "--app-name", "Safari", "--approval-audit-id", dry_run["audit_id"]], FakeObserver(), tmp_path)

    assert rejected["_exit_code"] == 2
    assert rejected["errors"][0]["code"] == "approval_audit_required"
    assert "older than 15 minutes" in rejected["errors"][0]["message"]


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


def test_full_access_allows_legacy_iphone_message_without_approval(tmp_path: Path) -> None:
    start_control_session(mode="full_access", agent_label="Aurelius", state_dir=tmp_path)

    payload = run_cli(
        ["customer-mac", "iphone-mirroring", "send-approved-message", "--json", "--text", "Hello", "--recipient-context", "Bumble canary profile"],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["data"]["action"] == "send_approved_message"


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

    for args in [
        ["codex", "app-server", "start-turn", "--json"],
        ["codex", "app-server", "steer-turn", "--json"],
        ["codex", "app-server", "interrupt-turn", "--json"],
        ["codex", "app-server", "rpc", "--json"],
    ]:
        assert main(args, observer_factory=FakeObserver, stdout=io.StringIO(), stderr=io.StringIO(), state_dir=tmp_path) == 2


def test_connector_start_autoinstalls_user_launchagent(monkeypatch, tmp_path: Path) -> None:
    plist_path = tmp_path / "Library" / "LaunchAgents" / "com.electricsheep.evaos-desktop-bridge.plist"
    launchctl_calls: list[list[str]] = []

    monkeypatch.setattr(bridge_cli, "CONNECTOR_USER_PLIST", plist_path)
    monkeypatch.setattr(bridge_cli, "CONNECTOR_SYSTEM_PLIST", tmp_path / "system.plist")
    monkeypatch.setattr(bridge_cli, "_tailscale_ip", lambda: "100.64.0.42")
    monkeypatch.setattr(bridge_cli, "_connector_program_path", lambda: "/opt/homebrew/bin/evaos-desktop-bridge")
    monkeypatch.setattr(bridge_cli, "_launchctl_domain", lambda: "gui/501")
    monkeypatch.setattr(
        bridge_cli,
        "_run_launchctl",
        lambda args: launchctl_calls.append(args) or {"returncode": 0, "stdout": "", "stderr": ""},
    )

    result = bridge_cli._launchctl_start()
    payload = plistlib.loads(plist_path.read_bytes())

    assert result["bootstrap"]["returncode"] == 0
    assert payload["ProgramArguments"] == [
        "/opt/homebrew/bin/evaos-desktop-bridge",
        "serve",
        "--host",
        "100.64.0.42",
        "--port",
        "8765",
    ]
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert ["bootout", "gui/501/com.electricsheep.evaos-desktop-bridge"] in launchctl_calls
    assert ["bootstrap", "gui/501", str(plist_path)] in launchctl_calls
    assert ["kickstart", "-k", "gui/501/com.electricsheep.evaos-desktop-bridge"] in launchctl_calls


def test_tailscale_ip_uses_homebrew_path_when_gui_path_is_minimal(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: None)

    def fake_run(command: list[str], **kwargs: object):
        calls.append(command)
        if command[0] == "/sbin/ifconfig":
            return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="missing")
        if command == ["/opt/homebrew/bin/tailscale", "status", "--json"]:
            return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="not running")
        if command[0] == "/opt/homebrew/bin/tailscale":
            return bridge_cli.subprocess.CompletedProcess(command, 0, stdout="100.64.0.42\n", stderr="")
        return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="missing")

    monkeypatch.setattr(bridge_cli.subprocess, "run", fake_run)

    assert bridge_cli._tailscale_ip() == "100.64.0.42"
    assert ["/opt/homebrew/bin/tailscale", "ip", "-4"] in calls


def test_tailscale_ip_prefers_active_interface_over_stale_tailscale_cli(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/opt/homebrew/bin/tailscale")

    def fake_run(command: list[str], **kwargs: object):
        calls.append(command)
        if command[0] == "/sbin/ifconfig":
            return bridge_cli.subprocess.CompletedProcess(
                command,
                0,
                stdout="utun0: flags=8051<UP,POINTOPOINT,RUNNING>\n\tinet 100.64.0.4 --> 100.64.0.4 netmask 0xffffffff\n",
                stderr="",
            )
        if command == ["/opt/homebrew/bin/tailscale", "ip", "-4"]:
            return bridge_cli.subprocess.CompletedProcess(command, 0, stdout="100.107.14.6\n", stderr="")
        return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="")

    monkeypatch.setattr(bridge_cli.subprocess, "run", fake_run)

    assert bridge_cli._tailscale_ip() == "100.64.0.4"
    assert calls == [["/sbin/ifconfig"]]


def test_tailscale_ip_uses_online_status_before_stale_ip_command(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/opt/homebrew/bin/tailscale")

    def fake_run(command: list[str], **kwargs: object):
        calls.append(command)
        if command[0] == "/sbin/ifconfig":
            return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="missing")
        if command == ["/opt/homebrew/bin/tailscale", "status", "--json"]:
            return bridge_cli.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "BackendState": "Running",
                        "Self": {"Online": True, "TailscaleIPs": ["100.64.0.5", "fd7a:115c:a1e0::5"]},
                    }
                ),
                stderr="",
            )
        if command == ["/opt/homebrew/bin/tailscale", "ip", "-4"]:
            return bridge_cli.subprocess.CompletedProcess(command, 0, stdout="100.107.14.6\n", stderr="")
        return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="")

    monkeypatch.setattr(bridge_cli.subprocess, "run", fake_run)

    assert bridge_cli._tailscale_ip() == "100.64.0.5"
    assert ["/opt/homebrew/bin/tailscale", "ip", "-4"] not in calls


def test_connector_program_path_prefers_packaged_executable(monkeypatch, tmp_path: Path) -> None:
    packaged_bridge = tmp_path / "evaOS.app" / "Contents" / "Resources" / "Bridge" / "evaos-desktop-bridge"
    packaged_bridge.parent.mkdir(parents=True)
    packaged_bridge.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(bridge_cli.sys, "argv", [str(packaged_bridge)])
    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/opt/homebrew/bin/evaos-desktop-bridge")

    assert bridge_cli._connector_program_path() == str(packaged_bridge)


def test_connector_program_path_resolves_packaged_module_to_launcher(monkeypatch, tmp_path: Path) -> None:
    packaged_bridge = tmp_path / "evaOS.app" / "Contents" / "Resources" / "Bridge" / "evaos-desktop-bridge"
    packaged_module = packaged_bridge.parent / "src" / "evaos_desktop_bridge" / "cli.py"
    packaged_module.parent.mkdir(parents=True)
    packaged_bridge.write_text("#!/bin/sh\n", encoding="utf-8")
    packaged_module.write_text("print('cli')\n", encoding="utf-8")

    monkeypatch.setattr(bridge_cli.sys, "argv", [str(packaged_module)])
    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/opt/homebrew/bin/evaos-desktop-bridge")

    assert bridge_cli._connector_program_path() == str(packaged_bridge)


def test_connector_program_path_skips_non_executable_source_module(monkeypatch, tmp_path: Path) -> None:
    source_module = tmp_path / "src" / "evaos_desktop_bridge" / "cli.py"
    source_module.parent.mkdir(parents=True)
    source_module.write_text("print('cli')\n", encoding="utf-8")

    monkeypatch.setattr(bridge_cli.sys, "argv", [str(source_module)])
    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/opt/homebrew/bin/evaos-desktop-bridge")

    assert bridge_cli._connector_program_path() == "/opt/homebrew/bin/evaos-desktop-bridge"


def test_connector_start_host_can_be_overridden(monkeypatch, tmp_path: Path) -> None:
    plist_path = tmp_path / "agent.plist"

    monkeypatch.setenv("EVAOS_DESKTOP_BRIDGE_CONNECTOR_HOST", "127.0.0.1")
    monkeypatch.setattr(bridge_cli, "CONNECTOR_USER_PLIST", plist_path)
    monkeypatch.setattr(bridge_cli, "CONNECTOR_SYSTEM_PLIST", tmp_path / "system.plist")
    monkeypatch.setattr(bridge_cli, "_tailscale_ip", lambda: "100.64.0.42")
    monkeypatch.setattr(bridge_cli, "_connector_program_path", lambda: "evaos-desktop-bridge")

    created = bridge_cli._ensure_connector_user_plist()
    payload = plistlib.loads(created.read_bytes())

    assert bridge_cli._connector_plist_host(created) == "127.0.0.1"
    assert payload["ProgramArguments"][payload["ProgramArguments"].index("--host") + 1] == "127.0.0.1"


def test_connector_status_accepts_workbench_managed_health_without_launchagent(monkeypatch, tmp_path: Path) -> None:
    token_path = tmp_path / "connector.token"
    token_path.write_text("fixture-token\n", encoding="utf-8")

    monkeypatch.setattr(bridge_cli, "CONNECTOR_USER_PLIST", tmp_path / "missing-user.plist")
    monkeypatch.setattr(bridge_cli, "CONNECTOR_SYSTEM_PLIST", tmp_path / "missing-system.plist")
    monkeypatch.setattr(
        bridge_cli,
        "_run_launchctl",
        lambda args: {"returncode": 113, "stdout": "", "stderr": "not loaded"},
    )
    monkeypatch.setattr(
        bridge_cli,
        "_connector_loopback_health",
        lambda: {"reachable": True, "host": "100.64.0.4", "port": 8765, "status_line": "HTTP/1.0 200 OK"},
    )

    payload = bridge_cli._connector_service_status(state_dir=tmp_path)

    assert payload["ok"] is True
    assert payload["managed_by"] == "workbench-or-manual"
    assert payload["loaded"] is False
    assert payload["running"] is False
    assert payload["permission_target"]["mode"] == "workbench_managed"
    assert payload["permission_target"]["bridge_executable"]
    assert payload["permission_target"]["permission_holder"] == "Peekaboo Bridge host or bundled Peekaboo CLI"
    assert "python_executable" not in payload["permission_target"]


def test_connector_status_reports_launchagent_program_as_permission_target(monkeypatch, tmp_path: Path) -> None:
    token_path = tmp_path / "connector.token"
    token_path.write_text("fixture-token\n", encoding="utf-8")
    plist_path = tmp_path / "com.electricsheep.evaos-desktop-bridge.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.electricsheep.evaos-desktop-bridge",
                "ProgramArguments": ["/opt/evaos/helper/evaos-desktop-bridge", "serve", "--host", "100.64.0.4", "--port", "8765"],
            }
        )
    )

    monkeypatch.setattr(bridge_cli, "CONNECTOR_USER_PLIST", plist_path)
    monkeypatch.setattr(bridge_cli, "CONNECTOR_SYSTEM_PLIST", tmp_path / "missing-system.plist")
    monkeypatch.setattr(
        bridge_cli,
        "_run_launchctl",
        lambda args: {"returncode": 0, "stdout": "loaded", "stderr": ""},
    )
    monkeypatch.setattr(
        bridge_cli,
        "_connector_loopback_health",
        lambda: {"reachable": True, "host": "100.64.0.4", "port": 8765, "status_line": "HTTP/1.0 200 OK"},
    )

    payload = bridge_cli._connector_service_status(state_dir=tmp_path)

    assert payload["managed_by"] == "launchagent"
    assert payload["permission_target"]["bridge_executable"] == "/opt/evaos/helper/evaos-desktop-bridge"
    assert payload["permission_target"]["launch_program"] == "/opt/evaos/helper/evaos-desktop-bridge"


def test_permission_prime_uses_peekaboo_not_python_tcc(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(bridge_cli.sys, "platform", "darwin")
    monkeypatch.setattr(bridge_cli, "PEEKABOO_BIN_CANDIDATES", ("peekaboo",))
    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    monkeypatch.setattr(bridge_cli, "_open_privacy_pane", lambda permission: None)

    def fake_run(command: list[str], **kwargs: object):
        calls.append(command)
        if command[:3] == ["/test/peekaboo", "permissions", "grant"]:
            return bridge_cli.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"success": True, "data": [{"name": "Accessibility", "isGranted": True}]}),
                stderr="",
            )
        if command[:3] == ["/test/peekaboo", "permissions", "request-event-synthesizing"]:
            return bridge_cli.subprocess.CompletedProcess(command, 0, stdout=json.dumps({"success": True}), stderr="")
        if command[:3] == ["/test/peekaboo", "permissions", "status"]:
            return bridge_cli.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "success": True,
                        "data": {
                            "source": "local",
                            "permissions": [
                                {"name": "Accessibility", "isGranted": True},
                                {"name": "Screen Recording", "isGranted": True},
                            ],
                        },
                    }
                ),
                stderr="",
            )
        return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected")

    monkeypatch.setattr(bridge_cli.subprocess, "run", fake_run)

    payload = run_cli(["permissions", "prime", "--json", "--permission", "accessibility"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["data"]["target"] == "Peekaboo automation helper"
    assert payload["data"]["executable"] == "/test/peekaboo"
    assert payload["data"]["permission_holder"] == "Peekaboo local"
    assert all(command[0] == "/test/peekaboo" for command in calls)
