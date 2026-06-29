from __future__ import annotations

import io
import json
import os
import plistlib
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from evaos_desktop_bridge import cli as bridge_cli
from evaos_desktop_bridge.cli import main
from evaos_desktop_bridge.helper_ipc import make_capability_token, run_helper_server
from evaos_desktop_bridge.state import kill_control_session, start_control_session, write_control_session
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
    codex_frontmost: bool = True

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
        return CommandResult(
            ok=True,
            data={
                "frontmost_app": "Codex" if self.codex_frontmost else "WorldOSApp",
                "window_title": "Codex" if self.codex_frontmost else None,
                "codex_frontmost": self.codex_frontmost,
            },
        )

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

    def send_visible_message(
        self,
        *,
        thread_id: str,
        message: str,
        dry_run: bool = True,
        confirmed: bool = False,
        wait_ms: int = 0,
        poll_interval_ms: int = 2000,
    ) -> CommandResult:
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
                "post_send": {
                    "state": "idle" if wait_ms else "submitted_waiting",
                    "wait_ms": wait_ms,
                    "poll_interval_ms": poll_interval_ms,
                    "read_only_after_submit": True,
                },
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
        return CommandResult(
            ok=True,
            data={
                "engine": "fallback",
                "frontmost_app": "Safari",
                "max_chars": max_chars,
                "max_nodes": max_nodes,
                "snapshot_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "screenshot": {
                    "screenshot": {
                        "artifact_id": "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "artifact_url": "/v1/artifacts/snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
                        "artifact_path": "~/Library/Application Support/evaos-desktop-bridge/artifacts/snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
                        "mime_type": "image/png",
                        "sha256": "0" * 64,
                        "byte_count": 3,
                        "width": 1,
                        "height": 1,
                        "bytes_base64": "Zm9v",
                    }
                },
            },
        )

    def desktop_click(self, *, target_label: str | None = None, x: int | None = None, y: int | None = None, snapshot_id: str | None = None, element_id: str | None = None, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"clicked": not dry_run, "would_click": dry_run, "target_label": target_label, "snapshot_id": snapshot_id, "element_id": element_id, "point": {"x": x, "y": y} if x is not None and y is not None else None})

    def desktop_type(self, *, text: str, dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"typed": not dry_run, "would_type": dry_run, "text_preview": text})

    def desktop_set_value(self, *, snapshot_id: str, element_id: str, value: str, attribute: str = "value", dry_run: bool = False) -> CommandResult:
        return CommandResult(ok=True, data={"set": not dry_run, "would_set": dry_run, "snapshot_id": snapshot_id, "element_id": element_id, "attribute": attribute, "value_sha256": bridge_cli._short_hash(value)})

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
        return CommandResult(
            ok=True,
            data={
                "target": "iphone_mirroring",
                "max_chars": max_chars,
                "max_nodes": max_nodes,
                "snapshot_id": "snap-iphone-mirroring-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "screenshot": {
                    "screenshot": {
                        "artifact_id": "snap-iphone-mirroring-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        "artifact_url": "/v1/artifacts/snap-iphone-mirroring-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png",
                        "artifact_path": "~/Library/Application Support/evaos-desktop-bridge/artifacts/snap-iphone-mirroring-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png",
                        "mime_type": "image/png",
                        "sha256": "1" * 64,
                        "byte_count": 3,
                        "width": 1,
                        "height": 1,
                        "bytes_base64": "YmFy",
                    }
                },
            },
        )

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


def short_socket_path() -> Path:
    return Path("/tmp") / f"evaos-cli-helper-{uuid.uuid4().hex}.sock"


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
    helper_entry = next(command for command in payload["data"]["commands"] if command["id"] == "helper.ping")
    assert helper_entry["target"] == "computer_use_helper"


def test_helper_ping_cli_round_trips_local_unix_socket(tmp_path: Path) -> None:
    token = make_capability_token()
    token_file = tmp_path / "helper.token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    socket_path = short_socket_path()
    ready = threading.Event()
    thread = threading.Thread(
        target=run_helper_server,
        kwargs={
            "socket_path": socket_path,
            "token": token,
            "expected_uid": os.getuid(),
            "ready": ready,
            "max_requests": 1,
            "peer_uid_getter": lambda _sock: os.getuid(),
        },
        daemon=True,
    )
    thread.start()
    assert ready.wait(timeout=2)

    stdout = io.StringIO()
    code = main(
        ["helper", "ping", "--json", "--socket-path", str(socket_path), "--token-file", str(token_file)],
        observer_factory=lambda: FakeObserver(),
        customer_mac_factory=lambda: FakeCustomerMac(),
        app_server_factory=lambda: FakeAppServer(),
        stdout=stdout,
        state_dir=tmp_path,
    )

    thread.join(timeout=2)
    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["command"] == "helper.ping"
    assert payload["target"] == "computer_use_helper"
    assert payload["ok"] is True
    assert payload["data"]["command"] == "ping"


def test_helper_ping_cli_missing_token_file_fails_closed(tmp_path: Path) -> None:
    stdout = io.StringIO()

    code = main(
        ["helper", "ping", "--json", "--socket-path", str(short_socket_path()), "--token-file", str(tmp_path / "missing.token")],
        observer_factory=lambda: FakeObserver(),
        customer_mac_factory=lambda: FakeCustomerMac(),
        app_server_factory=lambda: FakeAppServer(),
        stdout=stdout,
        state_dir=tmp_path,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 2
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "helper_token_missing"


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


def test_thread_map_json_reports_frontmost_state_for_visible_send_readiness(tmp_path: Path) -> None:
    payload = run_cli(["codex", "thread-map", "--json", "--max-items", "5"], FakeObserver(codex_frontmost=False), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["data"]["frontmost"]["codex_frontmost"] is False
    assert payload["data"]["visible_send_ready"] is False
    assert any("not frontmost" in warning for warning in payload["warnings"])


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


def test_send_visible_message_live_accepts_wait_state_options(tmp_path: Path) -> None:
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
            "--wait-ms",
            "3000",
            "--poll-interval-ms",
            "1000",
        ],
        FakeObserver(),
        tmp_path,
    )

    assert approved["_exit_code"] == 0
    assert approved["data"]["post_send"]["state"] == "idle"
    assert approved["data"]["post_send"]["wait_ms"] == 3000
    assert approved["data"]["post_send"]["poll_interval_ms"] == 1000


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


def test_send_visible_message_audit_preview_redacts_secret_like_text(tmp_path: Path) -> None:
    secret = "please use sk-1234567890abcdef for the check"  # noqa: S105 - intentional redaction fixture

    payload = run_cli(
        ["codex", "send-visible-message", "--json", "--thread-id", "visible-0-abc", "--message", secret, "--dry-run"],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    audit_log = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    records = [json.loads(line) for line in audit_log.splitlines()]
    assert "sk-1234567890abcdef" not in audit_log
    assert records[-1]["args"]["message_preview"] == "please use <redacted-secret> for the check"


def test_public_connector_service_result_redacts_raw_failure_payload() -> None:
    payload = bridge_cli._public_connector_service_result(
        {
            "ok": False,
            "action": "status",
            "error": "http://100.64.0.4:8765/token/Bearer abcdef1234567890",
            "token": "Bearer abcdef1234567890",  # noqa: S105 - intentional redaction fixture
            "path": f"{Path.home()}/Library/secret",
        }
    )

    assert payload == {
        "action": "status",
        "error": "connector_service_failed",
        "ok": False,
        "raw_output_returned": False,
    }
    serialized = json.dumps(payload, sort_keys=True)
    assert "abcdef1234567890" not in serialized
    assert str(Path.home()) not in serialized


def test_connector_service_json_output_uses_public_runner(monkeypatch, tmp_path: Path) -> None:
    def fail_raw_runner(action: str, *, state_dir: Path | None = None) -> dict[str, object]:
        raise AssertionError(f"raw connector service runner should not serve public JSON for {action}")

    def fake_run_public_connector_service(action: str, *, state_dir: Path | None = None) -> dict[str, object]:
        return {
            "ok": False,
            "action": action,
            "error": "connector_service_failed",
            "raw_output_returned": False,
        }

    monkeypatch.setattr(bridge_cli, "_run_connector_service", fail_raw_runner)
    monkeypatch.setattr(bridge_cli, "_run_public_connector_service", fake_run_public_connector_service)

    output = io.StringIO()
    exit_code = main(["connector-service", "status", "--json"], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())

    assert exit_code == 2
    assert payload == {
        "action": "status",
        "error": "connector_service_failed",
        "ok": False,
        "raw_output_returned": False,
    }
    assert "abcdef1234567890" not in output.getvalue()
    assert str(Path.home()) not in output.getvalue()


def test_connector_service_status_cli_reports_redacted_workbench_owner(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "fixture-token"  # noqa: S105 - intentional readiness fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")
    app_path, program_path = _write_owner_app_fixture(
        tmp_path,
        app_name="evaOS Workbench.app",
        bundle_id="com.evaos.workbench",
        manifest={
            "source_commit": "ff00f606d5d4c3edf9bf97642ce9088bee645e7b",
            "bridge_ref": "ff00f606d5d4c3edf9bf97642ce9088bee645e7b",
        },
    )
    plist_path = _write_owner_plist(tmp_path, program_path)
    _patch_connector_owner_probe(monkeypatch, tmp_path, plist_path, token_fixture=token_fixture)
    monkeypatch.setattr(
        bridge_cli,
        "_connector_service_guidance",
        lambda *_args: ["Confirm http://100.64.0.4:8765/health responds."],
    )

    output = io.StringIO()
    exit_code = main(["connector-service", "status", "--json"], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())
    owner = payload["owner"]

    assert exit_code == 0
    assert owner["classification"] == "workbench_bundle"
    assert owner["label"] == "com.electricsheep.evaos-desktop-bridge"
    assert owner["plist_path"] == {"kind": "path", "value": str(plist_path)}
    assert owner["program_path"] == {"kind": "path", "value": str(program_path)}
    assert owner["app_path"] == {"kind": "path", "value": str(app_path)}
    assert owner["bundle_id"] == "com.evaos.workbench"
    assert owner["source_commit"] == "ff00f606d5d4c3edf9bf97642ce9088bee645e7b"
    assert owner["manifest_path"] == {"kind": "path", "value": str(program_path.parent / "manifest.json")}
    assert payload["health"]["host_kind"] == "tailnet"
    assert payload["tailnet_available"] is True
    assert "tailnet_ip" not in payload
    assert payload["guidance"] == ["Confirm <redacted-url> responds."]
    assert "100.64.0.4" not in output.getvalue()
    assert "8765" not in output.getvalue()
    assert "fixture-token" not in output.getvalue()


def test_diagnostics_cli_reports_missing_token_without_minting_secret(tmp_path: Path) -> None:
    output = io.StringIO()
    exit_code = main(["diagnostics", "--json"], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert payload["schema"] == "evaos.desktop_bridge.diagnostics.v1"
    assert payload["connector"]["token_state"] == "missing"
    assert payload["connector"]["ready"]["ok"] is False
    assert payload["connector"]["ready"]["blockers"][0]["code"] == "token_missing"
    assert not (tmp_path / "connector.token").exists()


def test_diagnostics_cli_includes_redacted_owner_summary(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "secret-token-abcdef1234567890"  # noqa: S105 - intentional redaction fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")

    def fake_connector_service_status(*, token: str | None = None, token_file: str | None = None, state_dir: Path | None = None) -> dict[str, object]:
        assert token == token_fixture
        assert token_file is None
        assert state_dir == tmp_path
        return {
            "ok": True,
            "ready": True,
            "managed_by": "workbench-or-manual",
            "token_present": True,
            "loaded": False,
            "running": False,
            "owner": {
                "classification": "workbench_bundle",
                "label": "com.electricsheep.evaos-desktop-bridge",
                "plist_path": {"kind": "unknown"},
                "program_path": {"kind": "path", "value": str(tmp_path / "evaOS Workbench.app" / "Contents" / "Resources" / "Bridge" / "evaos-desktop-bridge")},
                "app_path": {"kind": "path", "value": str(tmp_path / "evaOS Workbench.app")},
                "bundle_id": "com.evaos.workbench",
                "source_commit": "ff00f606d5d4c3edf9bf97642ce9088bee645e7b",
                "manifest_path": {"kind": "path", "value": str(tmp_path / "evaOS Workbench.app" / "Contents" / "Resources" / "Bridge" / "manifest.json")},
            },
            "health": {
                "reachable": True,
                "ready": True,
                "authenticated": True,
                "host": "100.64.0.4",
                "port": 8765,
                "status_line": "HTTP/1.0 200 OK",
            },
            "guidance": ["Confirm http://100.64.0.4:8765/health responds."],
        }

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_service_status)

    output = io.StringIO()
    exit_code = main(["diagnostics", "--json"], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())
    owner = payload["connector"]["owner"]

    assert exit_code == 0
    assert owner["classification"] == "workbench_bundle"
    assert owner["bundle_id"] == "com.evaos.workbench"
    assert owner["plist_path"] == {"kind": "unknown"}
    assert "100.64.0.4" not in output.getvalue()
    assert "8765" not in output.getvalue()
    assert token_fixture not in output.getvalue()


def test_diagnostics_cli_has_human_output_without_json_flag(tmp_path: Path) -> None:
    output = io.StringIO()
    exit_code = main(["diagnostics"], stdout=output, state_dir=tmp_path)

    assert exit_code == 0
    assert "evaOS desktop bridge diagnostics: not ready" in output.getvalue()
    assert "token_missing" in output.getvalue()
    assert not (tmp_path / "connector.token").exists()


def test_ready_cli_reports_missing_token_without_minting_secret(tmp_path: Path) -> None:
    output = io.StringIO()
    exit_code = main(["ready", "--json"], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())

    assert exit_code == 2
    assert payload["schema"] == "evaos.desktop_bridge.ready.v1"
    assert payload["ok"] is False
    assert payload["ready"] is False
    assert payload["token_state"] == "missing"  # noqa: S105 - readiness state, not a secret
    assert payload["blockers"][0]["code"] == "token_missing"
    assert not (tmp_path / "connector.token").exists()


def test_ready_cli_fails_when_stale_token_exists_but_connector_is_offline(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "secret-token-abcdef1234567890"  # noqa: S105 - intentional readiness fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")

    def fake_connector_service_status(*, token: str | None = None, token_file: str | None = None, state_dir: Path | None = None) -> dict[str, object]:
        assert token == token_fixture
        assert token_file is None
        assert state_dir == tmp_path
        return {
            "ok": False,
            "ready": False,
            "managed_by": "offline",
            "token_present": True,
            "loaded": False,
            "running": False,
            "health": {
                "reachable": False,
                "host": "100.64.1.23",
                "port": 8765,
                "error": "connection refused",
            },
            "guidance": ["Start the connector service and confirm health responds."],
        }

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_service_status)

    output = io.StringIO()
    exit_code = main(["ready", "--json"], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())

    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["ready"] is False
    assert payload["token_state"] == "present"  # noqa: S105 - readiness state, not a secret
    assert [blocker["code"] for blocker in payload["blockers"]] == ["connector_service_unreachable"]
    assert "port" not in payload["blockers"][0]
    assert payload["connector_service"]["health"]["reachable"] is False
    assert payload["connector_service"]["health"]["host_kind"] == "tailnet"
    assert "port" not in payload["connector_service"]["health"]
    assert "status_line" not in payload["connector_service"]["health"]
    assert "100.64.1.23" not in output.getvalue()
    assert "8765" not in output.getvalue()


def test_ready_cli_uses_custom_token_file_for_connector_service_status(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "secret-token-abcdef1234567890"  # noqa: S105 - intentional readiness fixture
    token_path = tmp_path / "custom-connector.token"
    token_path.write_text(token_fixture + "\n", encoding="utf-8")

    def fake_connector_service_status(*, token: str | None = None, token_file: str | None = None, state_dir: Path | None = None) -> dict[str, object]:
        assert token == token_fixture
        assert token_file == str(token_path)
        assert state_dir == tmp_path
        return {
            "ok": True,
            "ready": True,
            "managed_by": "launchagent",
            "token_present": True,
            "loaded": True,
            "running": True,
            "owner": {
                "classification": "global_cli",
                "label": "com.electricsheep.evaos-desktop-bridge",
                "plist_path": {"kind": "path", "value": "/tmp/bridge.plist"},
                "program_path": {"kind": "path", "value": "/opt/homebrew/bin/evaos-desktop-bridge"},
                "app_path": {"kind": "unknown"},
                "bundle_id": None,
                "source_commit": None,
                "manifest_path": {"kind": "unknown"},
            },
            "health": {
                "reachable": True,
                "ready": True,
                "authenticated": True,
                "host": "127.0.0.1",
                "port": 8765,
                "status_line": "HTTP/1.0 200 OK",
            },
            "guidance": [],
        }

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_service_status)

    output = io.StringIO()
    exit_code = main(["ready", "--json", "--token-file", str(token_path)], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["ready"] is True
    assert payload["token_state"] == "present"  # noqa: S105 - readiness state, not a secret
    assert payload["connector_service"]["token_present"] is True
    assert payload["connector_service"]["ready"] is True
    assert payload["connector_service"]["owner"]["classification"] == "global_cli"
    assert payload["connector_service"]["owner"]["program_path"] == {
        "kind": "path",
        "value": "/opt/homebrew/bin/evaos-desktop-bridge",
    }
    assert payload["connector_service"]["health"]["authenticated"] is True
    assert "port" not in payload["connector_service"]["health"]
    assert "status_line" not in payload["connector_service"]["health"]
    assert not (tmp_path / "connector.token").exists()
    assert "secret-token" not in output.getvalue()
    assert "8765" not in output.getvalue()


def test_ready_cli_rejects_unauthenticated_health_200_listener(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "secret-token-abcdef1234567890"  # noqa: S105 - intentional readiness fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")
    calls: list[dict[str, str | None]] = []

    monkeypatch.setattr(bridge_cli, "_connector_plist_path", lambda: None)
    monkeypatch.setattr(bridge_cli, "_tailscale_ip", lambda: None)
    monkeypatch.setattr(
        bridge_cli,
        "_run_launchctl",
        lambda _args: {"returncode": 113, "stdout": "", "stderr": "not loaded"},
    )

    def fake_connector_http_get(host: str, request_path: str, *, authorization: str | None = None) -> dict[str, object]:
        calls.append({"host": host, "path": request_path, "authorization": authorization})
        return {
            "status_code": 200,
            "status_line": "HTTP/1.1 200 OK",
            "json": {"ok": True, "service": "not-evaos"},
        }

    monkeypatch.setattr(bridge_cli, "_connector_http_get", fake_connector_http_get)

    output = io.StringIO()
    exit_code = main(["ready", "--json"], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())

    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["ready"] is False
    assert payload["connector_service"]["ok"] is False
    assert payload["connector_service"]["ready"] is False
    assert payload["connector_service"]["health"]["reachable"] is False
    assert payload["connector_service"]["health"]["authenticated"] is False
    assert [blocker["code"] for blocker in payload["blockers"]] == ["connector_service_unreachable"]
    assert calls == [{"host": "127.0.0.1", "path": "/health", "authorization": None}]
    assert "secret-token" not in output.getvalue()


def test_ready_cli_reports_present_token_without_exposing_secret(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "secret-token-abcdef1234567890"  # noqa: S105 - intentional redaction fixture
    bearer_secret = "Bearer abcdef1234567890"  # noqa: S105 - intentional redaction fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")

    def fake_build_ready_payload(*, token: str | None, state_dir: Path | None = None) -> dict[str, object]:
        return {
            "ok": True,
            "schema": "evaos.desktop_bridge.ready.v1",
            "service": "evaos-desktop-bridge-connector",
            "ready": True,
            "token_state": "present",
            "blockers": [],
            "control_session": {
                "active": False,
                "token_echo": bearer_secret,
            },
            "service_events": [
                {
                    "message": f"authorization failed with {bearer_secret}",
                }
            ],
        }

    def fake_connector_service_status(*, token: str | None = None, token_file: str | None = None, state_dir: Path | None = None) -> dict[str, object]:
        assert token == token_fixture
        assert token_file is None
        assert state_dir == tmp_path
        return {
            "ok": True,
            "ready": True,
            "managed_by": "launchagent",
            "token_present": True,
            "loaded": True,
            "running": True,
            "health": {
                "reachable": True,
                "ready": True,
                "authenticated": True,
                "host": "127.0.0.1",
                "port": 8765,
                "status_line": "HTTP/1.0 200 OK",
            },
            "guidance": [],
        }

    monkeypatch.setattr(bridge_cli, "build_ready_payload", fake_build_ready_payload)
    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_service_status)

    output = io.StringIO()
    exit_code = main(["ready", "--json"], stdout=output, state_dir=tmp_path)
    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert payload["schema"] == "evaos.desktop_bridge.ready.v1"
    assert payload["ok"] is True
    assert payload["ready"] is True
    assert payload["token_state"] == "present"  # noqa: S105 - readiness state, not a secret
    assert payload["blockers"] == []
    assert payload["connector_service"]["running"] is True
    connector_health = payload["connector_service"]["health"]
    assert connector_health["host_kind"] == "loopback"
    assert "host" not in connector_health
    assert "port" not in connector_health
    assert "status_line" not in connector_health
    assert token_fixture not in output.getvalue()
    assert bearer_secret not in output.getvalue()
    assert "127.0.0.1" not in output.getvalue()
    assert "localhost" not in output.getvalue()
    assert "8765" not in output.getvalue()
    assert payload["control_session"]["token_echo"] == "Bearer <redacted-secret>"
    assert payload["service_events"][0]["message"] == "authorization failed with Bearer <redacted-secret>"


def test_ready_cli_has_human_output_without_json_flag(tmp_path: Path) -> None:
    output = io.StringIO()
    exit_code = main(["ready"], stdout=output, state_dir=tmp_path)

    assert exit_code == 2
    assert "evaOS desktop bridge connector: not ready" in output.getvalue()
    assert "token_missing" in output.getvalue()
    assert not (tmp_path / "connector.token").exists()


def test_connector_service_complete_enrollment_registers_privately(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_connector_status(*, state_dir: Path | None = None) -> dict[str, object]:
        assert state_dir == tmp_path
        return {
            "ok": True,
            "tailnet_ip": "100.64.1.10",
            "health": {"host": "100.64.1.10", "reachable": True},
        }

    def fake_read_token(token_file: str | None, *, state_dir: Path | None = None, auto_create: bool = False) -> str:
        assert token_file is None
        assert state_dir == tmp_path
        assert auto_create is False
        return "secret-token-abcdef1234567890"

    def fake_complete_enrollment_via_control(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "ok": True,
            "device": {"id": "device-1"},
            "headscale": {
                "ok": True,
                "node": "benjamin-mac",
                "preauth_key": "cf2e354d8f1598b4b30abdb191b43be174735d51f6dd00be",
            },
        }

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_status)
    monkeypatch.setattr(bridge_cli, "read_token", fake_read_token)
    monkeypatch.setattr(bridge_cli, "complete_enrollment_via_control", fake_complete_enrollment_via_control)

    output = io.StringIO()
    exit_code = main(
        [
            "connector-service",
            "complete-enrollment",
            "--json",
            "--enrollment-code",
            "PAIR123",
            "--customer-id",
            "benjamin-kennedy",
            "--device-name",
            "Benjamin Mac",
        ],
        stdout=output,
        state_dir=tmp_path,
    )
    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert captured["enrollment_code"] == "PAIR123"
    assert captured["connector_url"] == "http://100.64.1.10:8765"
    assert captured["connector_token"] == "secret-token-abcdef1234567890"
    assert captured["device_name"] == "Benjamin Mac"
    assert payload["ok"] is True
    assert payload["customer_id"] == "benjamin-kennedy"
    assert payload["device_id"] == "device-1"
    assert payload["connector_registered"] is True
    assert payload["connector_token_last4"] == "7890"
    assert payload["headscale"] == {
        "ok": True,
        "node": "benjamin-mac",
        "secret_material_returned": False,
    }
    assert payload["raw_secrets_returned"] is False
    assert "100.64.1.10" not in output.getvalue()
    assert "secret-token" not in output.getvalue()
    assert "cf2e354d8" not in output.getvalue()


def test_connector_service_complete_enrollment_prefers_tailnet_over_loopback_health(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_connector_status(*, state_dir: Path | None = None) -> dict[str, object]:
        assert state_dir == tmp_path
        return {
            "ok": True,
            "tailnet_ip": "100.64.1.10",
            "health": {"host": "127.0.0.1", "reachable": True},
        }

    def fake_read_token(token_file: str | None, *, state_dir: Path | None = None, auto_create: bool = False) -> str:
        assert token_file is None
        assert state_dir == tmp_path
        assert auto_create is False
        return "secret-token-abcdef1234567890"

    def fake_complete_enrollment_via_control(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True, "device": {"id": "device-1"}}

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_status)
    monkeypatch.setattr(bridge_cli, "read_token", fake_read_token)
    monkeypatch.setattr(bridge_cli, "complete_enrollment_via_control", fake_complete_enrollment_via_control)

    output = io.StringIO()
    exit_code = main(
        [
            "connector-service",
            "complete-enrollment",
            "--json",
            "--enrollment-code",
            "PAIR123",
            "--customer-id",
            "benjamin-kennedy",
        ],
        stdout=output,
        state_dir=tmp_path,
    )
    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert captured["connector_url"] == "http://100.64.1.10:8765"
    assert payload["ok"] is True
    assert "100.64.1.10" not in output.getvalue()
    assert "127.0.0.1" not in output.getvalue()


def test_connector_service_complete_enrollment_formats_ipv6_tailnet_host(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_connector_status(*, state_dir: Path | None = None) -> dict[str, object]:
        assert state_dir == tmp_path
        return {
            "ok": True,
            "tailnet_ip": "fd7a:115c:a1e0::42",
            "health": {"host": "127.0.0.1", "reachable": True},
        }

    def fake_read_token(token_file: str | None, *, state_dir: Path | None = None, auto_create: bool = False) -> str:
        assert token_file is None
        assert state_dir == tmp_path
        assert auto_create is False
        return "secret-token-abcdef1234567890"

    def fake_complete_enrollment_via_control(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True, "device": {"id": "device-1"}}

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_status)
    monkeypatch.setattr(bridge_cli, "read_token", fake_read_token)
    monkeypatch.setattr(bridge_cli, "complete_enrollment_via_control", fake_complete_enrollment_via_control)

    output = io.StringIO()
    exit_code = main(
        [
            "connector-service",
            "complete-enrollment",
            "--json",
            "--enrollment-code",
            "PAIR123",
            "--customer-id",
            "benjamin-kennedy",
        ],
        stdout=output,
        state_dir=tmp_path,
    )
    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert captured["connector_url"] == "http://[fd7a:115c:a1e0::42]:8765"
    assert payload["ok"] is True
    assert "fd7a:115c:a1e0::42" not in output.getvalue()
    assert "secret-token" not in output.getvalue()


def test_connector_service_complete_enrollment_rejects_loopback_without_tailnet(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_connector_status(*, state_dir: Path | None = None) -> dict[str, object]:
        assert state_dir == tmp_path
        return {
            "ok": True,
            "tailnet_ip": None,
            "health": {"host": "127.0.0.1", "reachable": True},
        }

    def fail_read_token(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("connector token must not be read when no secure connector host exists")

    def fail_complete_enrollment(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("broker complete_enrollment must not run with loopback-only host")

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_status)
    monkeypatch.setattr(bridge_cli, "read_token", fail_read_token)
    monkeypatch.setattr(bridge_cli, "complete_enrollment_via_control", fail_complete_enrollment)

    output = io.StringIO()
    exit_code = main(
        [
            "connector-service",
            "complete-enrollment",
            "--json",
            "--enrollment-code",
            "PAIR123",
            "--customer-id",
            "benjamin-kennedy",
        ],
        stdout=output,
        state_dir=tmp_path,
    )
    payload = json.loads(output.getvalue())

    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["error"] == "tailnet_ip_required"
    assert payload["health_host_kind"] == "loopback"
    assert payload["health_reachable"] is True
    assert "127.0.0.1" not in output.getvalue()


def test_connector_service_complete_enrollment_rejects_public_100_host(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_connector_status(*, state_dir: Path | None = None) -> dict[str, object]:
        assert state_dir == tmp_path
        return {
            "ok": True,
            "tailnet_ip": "100.1.2.3",
            "health": {"host": "100.1.2.3", "reachable": True},
        }

    def fail_read_token(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("connector token must not be read for public 100.0.0.0/8 host")

    def fail_complete_enrollment(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("broker complete_enrollment must not run with public non-tailnet host")

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_status)
    monkeypatch.setattr(bridge_cli, "read_token", fail_read_token)
    monkeypatch.setattr(bridge_cli, "complete_enrollment_via_control", fail_complete_enrollment)

    output = io.StringIO()
    exit_code = main(
        [
            "connector-service",
            "complete-enrollment",
            "--json",
            "--enrollment-code",
            "PAIR123",
            "--customer-id",
            "benjamin-kennedy",
        ],
        stdout=output,
        state_dir=tmp_path,
    )
    payload = json.loads(output.getvalue())

    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["error"] == "secure_network_link_required"
    assert payload["health_host_kind"] == "public"
    assert "100.1.2.3" not in output.getvalue()


def test_tailnet_ipv4_detection_uses_cgnat_boundaries() -> None:
    assert bridge_cli._looks_like_tailnet_ipv4("100.64.0.0") is True
    assert bridge_cli._looks_like_tailnet_ipv4("100.127.255.255") is True
    assert bridge_cli._looks_like_tailnet_ipv4("100.63.255.255") is False
    assert bridge_cli._looks_like_tailnet_ipv4("100.128.0.0") is False


def test_connector_service_complete_enrollment_allows_private_health_host(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_connector_status(*, state_dir: Path | None = None) -> dict[str, object]:
        assert state_dir == tmp_path
        return {
            "ok": True,
            "tailnet_ip": None,
            "health": {"host": "192.168.40.12", "reachable": True},
        }

    def fake_read_token(token_file: str | None, *, state_dir: Path | None = None, auto_create: bool = False) -> str:
        return "secret-token-abcdef1234567890"

    def fake_complete_enrollment_via_control(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True, "device": {"id": "device-1"}}

    monkeypatch.setattr(bridge_cli, "_connector_service_status", fake_connector_status)
    monkeypatch.setattr(bridge_cli, "read_token", fake_read_token)
    monkeypatch.setattr(bridge_cli, "complete_enrollment_via_control", fake_complete_enrollment_via_control)

    output = io.StringIO()
    exit_code = main(
        [
            "connector-service",
            "complete-enrollment",
            "--json",
            "--enrollment-code",
            "PAIR123",
            "--customer-id",
            "benjamin-kennedy",
        ],
        stdout=output,
        state_dir=tmp_path,
    )

    assert exit_code == 0
    assert captured["connector_url"] == "http://192.168.40.12:8765"
    assert "192.168.40.12" not in output.getvalue()


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


def test_customer_mac_visual_json_omits_screenshot_bytes_by_default(tmp_path: Path) -> None:
    desktop_payload = run_cli(["customer-mac", "desktop", "see", "--json"], FakeObserver(), tmp_path)
    iphone_payload = run_cli(["customer-mac", "iphone-mirroring", "see", "--json"], FakeObserver(), tmp_path)

    serialized = json.dumps({"desktop": desktop_payload, "iphone": iphone_payload})
    assert desktop_payload["_exit_code"] == 0
    assert iphone_payload["_exit_code"] == 0
    assert "bytes_base64" not in serialized
    desktop_screenshot = desktop_payload["data"]["screenshot"]["screenshot"]
    iphone_screenshot = iphone_payload["data"]["screenshot"]["screenshot"]
    assert desktop_screenshot["artifact_url"] == "/v1/artifacts/snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png"
    assert iphone_screenshot["artifact_url"] == "/v1/artifacts/snap-iphone-mirroring-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png"
    assert desktop_screenshot["inline_screenshot_bytes_omitted"] is True
    assert iphone_screenshot["inline_screenshot_bytes_omitted"] is True


def test_customer_mac_visual_json_can_include_screenshot_bytes_explicitly(tmp_path: Path) -> None:
    payload = run_cli(["customer-mac", "desktop", "see", "--json", "--include-screenshot-bytes"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    screenshot = payload["data"]["screenshot"]["screenshot"]
    assert screenshot["bytes_base64"] == "Zm9v"
    assert "bytes_base64_omitted" not in screenshot


def test_latest_keeps_visual_screenshot_bytes_omitted(tmp_path: Path) -> None:
    desktop_payload = run_cli(["customer-mac", "desktop", "see", "--json"], FakeObserver(), tmp_path)
    latest_payload = run_cli(["latest", "--json"], FakeObserver(), tmp_path)

    serialized = json.dumps(latest_payload)
    assert desktop_payload["_exit_code"] == 0
    assert latest_payload["_exit_code"] == 0
    assert latest_payload["data"]["latest"]["audit_id"] == desktop_payload["audit_id"]
    assert "bytes_base64" not in serialized
    assert latest_payload["data"]["latest"]["data"]["screenshot"]["screenshot"]["inline_screenshot_bytes_omitted"] is True


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
    write_control_session({"active": True, "mode": "full_access", "takeover_warning_until": "2000-01-01T00:00:00Z"}, state_dir=tmp_path)
    payload = run_cli(["customer-mac", "desktop", "type", "--json", "--text", "hello"], FakeObserver(), tmp_path)
    set_value = run_cli(["customer-mac", "desktop", "set-value", "--json", "--snapshot-id", "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--element-id", "el-0001", "--value", "hello"], FakeObserver(), tmp_path)
    legacy = run_cli(["codex", "continue-thread", "--json", "--title", "SDK Docs"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "customer_mac.desktop_type"
    assert payload["data"]["typed"] is True
    assert set_value["_exit_code"] == 0
    assert set_value["command"] == "customer_mac.desktop_set_value"
    assert set_value["data"]["set"] is True
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    set_value_record = next(record for record in records if record["audit_id"] == set_value["audit_id"])
    assert "value" not in set_value_record["args"]
    assert "value_preview" not in set_value_record["args"]
    assert set_value_record["args"]["value_hash"]
    assert legacy["_exit_code"] == 2
    assert legacy["errors"][0]["code"] == "approval_audit_required"


def test_customer_mac_live_actions_wait_for_takeover_warning_countdown(tmp_path: Path) -> None:
    start_control_session(mode="full_access", agent_label="Aurelius", state_dir=tmp_path)

    rejected = run_cli(["customer-mac", "desktop", "scroll", "--json", "--direction", "down"], FakeObserver(), tmp_path)
    status = run_cli(["customer-mac", "control", "status", "--json"], FakeObserver(), tmp_path)

    assert rejected["_exit_code"] == 2
    assert rejected["errors"][0]["code"] == "control_takeover_warning_active"
    assert rejected["data"]["takeover_warning"]["active"] is True
    assert status["_exit_code"] == 0


def test_customer_mac_legacy_live_actions_wait_for_takeover_warning_countdown(tmp_path: Path) -> None:
    cases = [
        (
            ["customer-mac", "app-focus", "--json", "--app-name", "Safari"],
            ["customer-mac", "app-focus", "--json", "--app-name", "Safari", "--dry-run"],
        ),
        (
            ["customer-mac", "local-site", "open", "--json", "--url", "http://127.0.0.1:8080"],
            ["customer-mac", "local-site", "open", "--json", "--url", "http://127.0.0.1:8080", "--dry-run"],
        ),
        (
            ["customer-mac", "local-site", "action", "--json", "--action", "reload"],
            ["customer-mac", "local-site", "action", "--json", "--action", "reload", "--dry-run"],
        ),
    ]

    approvals = [run_cli(dry_run_argv, FakeObserver(), tmp_path)["audit_id"] for _live_argv, dry_run_argv in cases]
    start_control_session(mode="full_access", agent_label="Aurelius", state_dir=tmp_path)

    for (live_argv, _dry_run_argv), approval_audit_id in zip(cases, approvals, strict=True):
        rejected = run_cli([*live_argv, "--approval-audit-id", approval_audit_id], FakeObserver(), tmp_path)
        assert rejected["_exit_code"] == 2
        assert rejected["errors"][0]["code"] == "control_takeover_warning_active"


def test_customer_mac_ask_permission_allows_navigation_but_gates_text(tmp_path: Path) -> None:
    start_control_session(mode="ask_permission", agent_label="Hermes", state_dir=tmp_path)
    write_control_session({"active": True, "mode": "ask_permission", "takeover_warning_until": "2000-01-01T00:00:00Z"}, state_dir=tmp_path)

    scroll = run_cli(["customer-mac", "desktop", "scroll", "--json", "--direction", "down"], FakeObserver(), tmp_path)
    safe_click = run_cli(["customer-mac", "desktop", "click", "--json", "--target-label", "Continue"], FakeObserver(), tmp_path)
    risky_click = run_cli(["customer-mac", "desktop", "click", "--json", "--target-label", "Send"], FakeObserver(), tmp_path)
    coordinate_click = run_cli(["customer-mac", "desktop", "click", "--json", "--x", "10", "--y", "20"], FakeObserver(), tmp_path)
    safe_hotkey = run_cli(["customer-mac", "desktop", "hotkey", "--json", "--keys", "cmd+r"], FakeObserver(), tmp_path)
    risky_hotkey = run_cli(["customer-mac", "desktop", "hotkey", "--json", "--keys", "return"], FakeObserver(), tmp_path)
    typed = run_cli(["customer-mac", "desktop", "type", "--json", "--text", "hello"], FakeObserver(), tmp_path)
    set_value = run_cli(["customer-mac", "desktop", "set-value", "--json", "--snapshot-id", "snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--element-id", "el-0001", "--value", "hello"], FakeObserver(), tmp_path)

    assert scroll["_exit_code"] == 0
    assert scroll["data"]["scrolled"] is True
    assert safe_click["_exit_code"] == 0
    assert risky_click["_exit_code"] == 2
    assert coordinate_click["_exit_code"] == 2
    assert safe_hotkey["_exit_code"] == 0
    assert risky_hotkey["_exit_code"] == 2
    assert typed["_exit_code"] == 2
    assert typed["errors"][0]["code"] == "approval_audit_required"
    assert set_value["_exit_code"] == 2
    assert set_value["errors"][0]["code"] == "approval_audit_required"


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
    write_control_session({"active": True, "mode": "full_access", "takeover_warning_until": "2000-01-01T00:00:00Z"}, state_dir=tmp_path)

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


def test_connector_serve_supplies_http_owner_provider(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    workbench_program = Path("/Applications/evaOS Workbench.app/Contents/Resources/Bridge/evaos-desktop-bridge")

    monkeypatch.setattr(bridge_cli, "read_token", lambda *_args, **_kwargs: "secret-token-abcdef1234567890")
    monkeypatch.setattr(bridge_cli, "_connector_plist_path", lambda: None)
    monkeypatch.setattr(bridge_cli, "_current_connector_program_path", lambda: workbench_program)

    def fake_run_connector_server(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(bridge_cli, "run_connector_server", fake_run_connector_server)

    assert (
        main(
            ["serve", "--host", "127.0.0.1", "--port", "8765"],
            observer_factory=FakeObserver,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            state_dir=tmp_path,
        )
        == 0
    )

    owner_provider = captured["owner_provider"]
    assert callable(owner_provider)
    owner = owner_provider()
    assert owner["classification"] == "workbench_bundle"
    assert owner["program_path"] == {"kind": "path", "value": str(workbench_program)}
    assert captured["token"] == "secret-token-abcdef1234567890"


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


def test_connector_label_can_be_overridden_for_staging_without_path_injection() -> None:
    assert (
        bridge_cli._connector_label_from_env(
            {"EVAOS_DESKTOP_BRIDGE_CONNECTOR_LABEL": "com.electricsheep.evaos-desktop-bridge.staging-097f6d2"}
        )
        == "com.electricsheep.evaos-desktop-bridge.staging-097f6d2"
    )
    assert (
        bridge_cli._connector_label_from_env({"EVAOS_DESKTOP_BRIDGE_CONNECTOR_LABEL": "../bad-label"})
        == bridge_cli.DEFAULT_CONNECTOR_LABEL
    )
    assert (
        bridge_cli._connector_label_from_env({"EVAOS_DESKTOP_BRIDGE_CONNECTOR_LABEL": ""})
        == bridge_cli.DEFAULT_CONNECTOR_LABEL
    )


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
    token_fixture = "fixture-token"  # noqa: S105 - intentional readiness fixture
    token_path = tmp_path / "connector.token"
    token_path.write_text(token_fixture + "\n", encoding="utf-8")

    monkeypatch.setattr(bridge_cli, "CONNECTOR_USER_PLIST", tmp_path / "missing-user.plist")
    monkeypatch.setattr(bridge_cli, "CONNECTOR_SYSTEM_PLIST", tmp_path / "missing-system.plist")
    monkeypatch.setattr(
        bridge_cli,
        "_run_launchctl",
        lambda _args: {"returncode": 113, "stdout": "", "stderr": "not loaded"},
    )
    def fake_connector_loopback_health(*, connector_token: str | None = None) -> dict[str, object]:
        assert connector_token == token_fixture
        return {
            "reachable": True,
            "ready": True,
            "authenticated": True,
            "host": "100.64.0.4",
            "port": 8765,
            "status_line": "HTTP/1.0 200 OK",
        }

    monkeypatch.setattr(bridge_cli, "_connector_loopback_health", fake_connector_loopback_health)

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
    token_fixture = "fixture-token"  # noqa: S105 - intentional readiness fixture
    token_path = tmp_path / "connector.token"
    token_path.write_text(token_fixture + "\n", encoding="utf-8")
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
        lambda _args: {"returncode": 0, "stdout": "loaded", "stderr": ""},
    )
    def fake_connector_loopback_health(*, connector_token: str | None = None) -> dict[str, object]:
        assert connector_token == token_fixture
        return {
            "reachable": True,
            "ready": True,
            "authenticated": True,
            "host": "100.64.0.4",
            "port": 8765,
            "status_line": "HTTP/1.0 200 OK",
        }

    monkeypatch.setattr(bridge_cli, "_connector_loopback_health", fake_connector_loopback_health)

    payload = bridge_cli._connector_service_status(state_dir=tmp_path)

    assert payload["managed_by"] == "launchagent"
    assert payload["permission_target"]["bridge_executable"] == "/opt/evaos/helper/evaos-desktop-bridge"
    assert payload["permission_target"]["launch_program"] == "/opt/evaos/helper/evaos-desktop-bridge"


def test_connector_owner_summary_classifies_workbench_legacy_global_unknown_and_not_running(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "fixture-token"  # noqa: S105 - intentional readiness fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")

    packaged_workbench_app, packaged_workbench_program = _write_owner_app_fixture(
        tmp_path,
        app_name="evaOS.app",
        bundle_id="com.electricsheephq.EvaDesktop",
    )
    packaged_workbench_plist = _write_owner_plist(tmp_path, packaged_workbench_program)
    _patch_connector_owner_probe(monkeypatch, tmp_path, packaged_workbench_plist, token_fixture=token_fixture)
    packaged_workbench_status = bridge_cli._connector_service_status(state_dir=tmp_path)
    assert packaged_workbench_status["owner"]["classification"] == "workbench_bundle"
    assert packaged_workbench_status["owner"]["app_path"] == {"kind": "path", "value": str(packaged_workbench_app)}
    assert packaged_workbench_status["owner"]["bundle_id"] == "com.electricsheephq.EvaDesktop"

    legacy_app, legacy_program = _write_owner_app_fixture(
        tmp_path,
        app_name="legacy/evaOS.app",
        bundle_id="com.evaos.legacy",
    )
    legacy_plist = _write_owner_plist(tmp_path, legacy_program)
    _patch_connector_owner_probe(monkeypatch, tmp_path, legacy_plist, token_fixture=token_fixture)
    legacy_status = bridge_cli._connector_service_status(state_dir=tmp_path)
    assert legacy_status["owner"]["classification"] == "legacy_bundle"
    assert legacy_status["owner"]["app_path"] == {"kind": "path", "value": str(legacy_app)}
    assert legacy_status["owner"]["bundle_id"] == "com.evaos.legacy"

    homebrew_plist = _write_owner_plist(tmp_path, Path("/opt/homebrew/bin/evaos-desktop-bridge"))
    _patch_connector_owner_probe(monkeypatch, tmp_path, homebrew_plist, token_fixture=token_fixture)
    homebrew_status = bridge_cli._connector_service_status(state_dir=tmp_path)
    assert homebrew_status["owner"]["classification"] == "global_cli"
    assert homebrew_status["owner"]["app_path"] == {"kind": "unknown"}

    unknown_plist = _write_owner_plist(tmp_path, Path("/custom/evaos/bridge/evaos-desktop-bridge"))
    _patch_connector_owner_probe(monkeypatch, tmp_path, unknown_plist, token_fixture=token_fixture)
    unknown_status = bridge_cli._connector_service_status(state_dir=tmp_path)
    assert unknown_status["owner"]["classification"] == "unknown"
    assert unknown_status["owner"]["program_path"] == {
        "kind": "path",
        "value": "/custom/evaos/bridge/evaos-desktop-bridge",
    }

    missing_plist = tmp_path / "missing-owner.plist"
    _patch_connector_owner_probe(monkeypatch, tmp_path, missing_plist, token_fixture=token_fixture, loaded=False, ready=False)
    not_running_status = bridge_cli._connector_service_status(state_dir=tmp_path)
    assert not_running_status["owner"]["classification"] == "not_running"
    assert not_running_status["owner"]["program_path"] == {"kind": "unknown"}


def test_connector_owner_summary_prefers_configured_launcher_when_active_process_is_python(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "fixture-token"  # noqa: S105 - intentional readiness fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")
    app_path, program_path = _write_owner_app_fixture(
        tmp_path,
        app_name="evaOS.app",
        bundle_id="com.electricsheephq.EvaDesktop",
        manifest={"source_commit": "ff00f606d5d4c3edf9bf97642ce9088bee645e7b"},
    )
    plist_path = _write_owner_plist(tmp_path, program_path)
    _patch_connector_owner_probe(monkeypatch, tmp_path, plist_path, token_fixture=token_fixture, loaded=True, ready=True)
    monkeypatch.setattr(bridge_cli, "_active_connector_process_program_path", lambda: Path("/opt/homebrew/bin/python3"), raising=False)

    status = bridge_cli._connector_service_status(state_dir=tmp_path)
    owner = status["owner"]

    assert owner["classification"] == "workbench_bundle"
    assert owner["program_path"] == {"kind": "path", "value": str(program_path)}
    assert owner["app_path"] == {"kind": "path", "value": str(app_path)}
    assert owner["bundle_id"] == "com.electricsheephq.EvaDesktop"


def test_connector_owner_summary_uses_active_workbench_process_without_plist(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "fixture-token"  # noqa: S105 - intentional readiness fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")
    app_path, program_path = _write_owner_app_fixture(
        tmp_path,
        app_name="evaOS Workbench.app",
        bundle_id="com.evaos.workbench",
        manifest={"source_commit": "ff00f606d5d4c3edf9bf97642ce9088bee645e7b"},
    )
    missing_plist = tmp_path / "missing-owner.plist"
    _patch_connector_owner_probe(monkeypatch, tmp_path, missing_plist, token_fixture=token_fixture, loaded=False, ready=True)
    monkeypatch.setattr(bridge_cli, "_active_connector_process_program_path", lambda: program_path, raising=False)

    status = bridge_cli._connector_service_status(state_dir=tmp_path)
    owner = status["owner"]

    assert status["managed_by"] == "workbench-or-manual"
    assert owner["classification"] == "workbench_bundle"
    assert owner["plist_path"] == {"kind": "unknown"}
    assert owner["program_path"] == {"kind": "path", "value": str(program_path)}
    assert owner["app_path"] == {"kind": "path", "value": str(app_path)}
    assert owner["bundle_id"] == "com.evaos.workbench"
    assert owner["source_commit"] == "ff00f606d5d4c3edf9bf97642ce9088bee645e7b"


def test_connector_owner_summary_prefers_active_workbench_process_over_stale_legacy_plist(monkeypatch, tmp_path: Path) -> None:
    token_fixture = "fixture-token"  # noqa: S105 - intentional readiness fixture
    (tmp_path / "connector.token").write_text(token_fixture + "\n", encoding="utf-8")
    legacy_app, legacy_program = _write_owner_app_fixture(
        tmp_path,
        app_name="evaOS.app",
        bundle_id="com.electricsheephq.EvaDesktop",
    )
    workbench_app, workbench_program = _write_owner_app_fixture(
        tmp_path,
        app_name="evaOS Workbench.app",
        bundle_id="com.evaos.workbench",
        manifest={"source_commit": "ff00f606d5d4c3edf9bf97642ce9088bee645e7b"},
    )
    legacy_plist = _write_owner_plist(tmp_path, legacy_program)
    _patch_connector_owner_probe(monkeypatch, tmp_path, legacy_plist, token_fixture=token_fixture, loaded=True, ready=True)
    monkeypatch.setattr(bridge_cli, "_active_connector_process_program_path", lambda: workbench_program, raising=False)

    status = bridge_cli._connector_service_status(state_dir=tmp_path)
    owner = status["owner"]

    assert legacy_app.name == "evaOS.app"
    assert owner["classification"] == "workbench_bundle"
    assert owner["plist_path"] == {"kind": "path", "value": str(legacy_plist)}
    assert owner["program_path"] == {"kind": "path", "value": str(workbench_program)}
    assert owner["app_path"] == {"kind": "path", "value": str(workbench_app)}
    assert owner["bundle_id"] == "com.evaos.workbench"


def test_owner_metadata_reads_are_bounded(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{" + '"source_commit":"' + ("a" * (64 * 1024)) + '"}', encoding="utf-8")
    app_path = tmp_path / "evaOS Workbench.app"
    info_dir = app_path / "Contents"
    info_dir.mkdir(parents=True)
    (info_dir / "Info.plist").write_bytes(b"0" * (256 * 1024 + 1))

    assert bridge_cli._read_owner_manifest(manifest_path) == {}
    assert bridge_cli._owner_bundle_id(app_path) is None


def test_active_connector_process_program_path_reads_listener_text_path(monkeypatch, tmp_path: Path) -> None:
    _app_path, program_path = _write_owner_app_fixture(
        tmp_path,
        app_name="evaOS Workbench.app",
        bundle_id="com.evaos.workbench",
    )
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        if "-iTCP:8765" in command:
            return bridge_cli.subprocess.CompletedProcess(command, 0, stdout="p4242\n", stderr="")
        if command[:2] == ["/usr/sbin/lsof", "-nP"] and "-d" in command and "txt" in command:
            return bridge_cli.subprocess.CompletedProcess(command, 0, stdout=f"n{program_path}\n", stderr="")
        if command[:2] == ["/bin/ps", "-p"]:
            raise AssertionError("ps fallback should not run when lsof txt returns an executable path")
        return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected")

    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/usr/sbin/lsof" if name == "lsof" else None)
    monkeypatch.setattr(bridge_cli.subprocess, "run", fake_run)

    assert bridge_cli._active_connector_process_program_path() == program_path
    assert calls[0] == ["/usr/sbin/lsof", "-nP", "-iTCP:8765", "-sTCP:LISTEN", "-Fp"]


def _write_owner_app_fixture(
    tmp_path: Path,
    *,
    app_name: str,
    bundle_id: str,
    manifest: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    app_path = tmp_path / app_name
    bridge_dir = app_path / "Contents" / "Resources" / "Bridge"
    bridge_dir.mkdir(parents=True)
    (app_path / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": bundle_id}))
    if manifest is not None:
        (bridge_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    program_path = bridge_dir / "evaos-desktop-bridge"
    program_path.write_text("#!/bin/sh\n", encoding="utf-8")
    return app_path, program_path


def _write_owner_plist(tmp_path: Path, program_path: Path) -> Path:
    plist_path = tmp_path / "com.electricsheep.evaos-desktop-bridge.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.electricsheep.evaos-desktop-bridge",
                "ProgramArguments": [str(program_path), "serve", "--host", "100.64.0.4", "--port", "8765"],
            }
        )
    )
    return plist_path


def _patch_connector_owner_probe(
    monkeypatch,
    tmp_path: Path,
    plist_path: Path,
    *,
    token_fixture: str,
    loaded: bool = True,
    ready: bool = True,
) -> None:
    monkeypatch.setattr(bridge_cli, "CONNECTOR_USER_PLIST", plist_path)
    monkeypatch.setattr(bridge_cli, "CONNECTOR_SYSTEM_PLIST", tmp_path / "missing-system.plist")
    monkeypatch.setattr(bridge_cli, "_active_connector_process_program_path", lambda: None)
    monkeypatch.setattr(bridge_cli, "_tailscale_ip", lambda: "100.64.0.4" if ready else None)
    monkeypatch.setattr(
        bridge_cli,
        "_run_launchctl",
        lambda _args: {"returncode": 0 if loaded else 113, "stdout": "loaded" if loaded else "", "stderr": "" if loaded else "not loaded"},
    )

    def fake_connector_loopback_health(*, connector_token: str | None = None) -> dict[str, object]:
        assert connector_token == token_fixture
        return {
            "reachable": ready,
            "ready": ready,
            "authenticated": ready,
            "host": "100.64.0.4",
            "port": 8765,
            "status_line": "HTTP/1.0 200 OK" if ready else "",
        }

    monkeypatch.setattr(bridge_cli, "_connector_loopback_health", fake_connector_loopback_health)

    def fake_connector_public_loopback_health() -> dict[str, object]:
        return {
            "reachable": ready,
            "ready": ready,
            "authenticated": False,
            "host": "100.64.0.4",
            "port": 8765,
            "status_line": "HTTP/1.0 200 OK" if ready else "",
        }

    monkeypatch.setattr(bridge_cli, "_connector_public_loopback_health", fake_connector_public_loopback_health)


def test_permission_prime_uses_peekaboo_not_python_tcc(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(bridge_cli.sys, "platform", "darwin")
    monkeypatch.setattr(bridge_cli, "PEEKABOO_BIN_CANDIDATES", ("peekaboo",))
    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/test/peekaboo" if name == "peekaboo" else None)
    monkeypatch.setattr(bridge_cli, "_open_privacy_pane", lambda _permission: None)

    def fake_run(command: list[str], **_kwargs: object) -> object:
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


def test_permission_prime_prefers_bundled_peekaboo_before_connector_helper_alias(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    bridge_executable = tmp_path / "Bridge" / "evaos-desktop-bridge"
    bundled_helper = bridge_executable.parent / "bin" / "evaos-connector-helper"
    bundled_peekaboo = bridge_executable.parent / "bin" / "peekaboo"
    bundled_helper.parent.mkdir(parents=True)
    bridge_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    bundled_helper.write_text("#!/bin/sh\n", encoding="utf-8")
    bundled_peekaboo.write_text("#!/bin/sh\n", encoding="utf-8")
    bridge_executable.chmod(0o755)
    bundled_helper.chmod(0o755)
    bundled_peekaboo.chmod(0o755)

    monkeypatch.setattr(bridge_cli.sys, "platform", "darwin")
    monkeypatch.setattr(bridge_cli.sys, "executable", str(bridge_executable))
    monkeypatch.setattr(bridge_cli.sys, "argv", [str(bridge_executable)])
    monkeypatch.setattr(bridge_cli, "PEEKABOO_BIN_CANDIDATES", ("peekaboo",))
    monkeypatch.setattr(bridge_cli.shutil, "which", lambda name: "/opt/homebrew/bin/peekaboo" if name == "peekaboo" else None)
    monkeypatch.setattr(bridge_cli, "_open_privacy_pane", lambda permission: None)

    def fake_run(command: list[str], **kwargs: object):
        calls.append(command)
        if command[0] != str(bundled_peekaboo):
            return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected peekaboo path")
        if command[1:3] == ["permissions", "grant"]:
            return bridge_cli.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"success": True, "data": [{"name": "Accessibility", "isGranted": True}]}),
                stderr="",
            )
        if command[1:3] == ["permissions", "request-event-synthesizing"]:
            return bridge_cli.subprocess.CompletedProcess(command, 0, stdout=json.dumps({"success": True}), stderr="")
        if command[1:3] == ["permissions", "status"]:
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
    assert payload["data"]["executable"] == str(bundled_peekaboo)
    assert payload["data"]["permission_holder"] == "Peekaboo local"
    assert all(command[0] == str(bundled_peekaboo) for command in calls)


def test_permission_prime_prefers_path_peekaboo_before_connector_helper_alias(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(bridge_cli.sys, "platform", "darwin")
    monkeypatch.setattr(bridge_cli, "PEEKABOO_BIN_CANDIDATES", ("peekaboo", "evaos-connector-helper"))
    monkeypatch.setattr(
        bridge_cli.shutil,
        "which",
        lambda name: f"/opt/homebrew/bin/{name}" if name in {"peekaboo", "evaos-connector-helper"} else None,
    )
    monkeypatch.setattr(bridge_cli, "_open_privacy_pane", lambda permission: None)

    def fake_run(command: list[str], **kwargs: object):
        calls.append(command)
        if command[0] != "/opt/homebrew/bin/peekaboo":
            return bridge_cli.subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected helper alias path")
        if command[1:3] == ["permissions", "grant"]:
            return bridge_cli.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"success": True, "data": [{"name": "Accessibility", "isGranted": True}]}),
                stderr="",
            )
        if command[1:3] == ["permissions", "request-event-synthesizing"]:
            return bridge_cli.subprocess.CompletedProcess(command, 0, stdout=json.dumps({"success": True}), stderr="")
        if command[1:3] == ["permissions", "status"]:
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
    assert payload["data"]["executable"] == "/opt/homebrew/bin/peekaboo"
    assert all(command[0] == "/opt/homebrew/bin/peekaboo" for command in calls)
