from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

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
class FakeAppServer:
    mode: str = "ok"

    def status(self) -> CommandResult:
        return CommandResult(ok=True, data={"available": self.mode == "ok", "allowed_methods": ["thread/list"], "read_only": True})

    def connections_status(self, *, desktop_status: CommandResult | None = None) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "desktop": {"running": True},
                "app_server": {"available": True, "websocket_listen_supported": True},
                "remote_control": {"feature_state": "under development false"},
                "live_notifications": {"expected_methods": ["turn/started", "turn/completed"]},
            },
        )

    def threads(self, *, max_items: int) -> CommandResult:
        if self.mode != "ok":
            return CommandResult(ok=False, errors=[{"code": "app_server_unavailable", "message": "offline", "guidance": "start app-server"}])
        return CommandResult(ok=True, data={"threads": [{"index": 0, "id": "t1", "title": "Thread 1", "source": "app_server"}][:max_items], "count": 1, "max_items": max_items})

    def subscribe(self, *, thread_id: str, duration_ms: int, max_events: int = 40, max_chars: int = 4000) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "thread_id": thread_id,
                "duration_ms": duration_ms,
                "events": [{"method": "turn/started", "params": {"threadId": thread_id}}],
                "count": 1,
            },
        )

    def start_turn(
        self,
        *,
        thread_id: str,
        message: str,
        dry_run: bool,
        source_audit_id: str | None = None,
        confirmed: bool = False,
        max_chars: int = 4000,
    ) -> CommandResult:
        if dry_run:
            return CommandResult(ok=True, data={"would_start_turn": True, "started": False, "thread_id": thread_id, "message_preview": message[:max_chars]})
        if not confirmed or not source_audit_id:
            return CommandResult(ok=False, errors=[{"code": "controller_confirmation_required", "message": "confirm", "guidance": "dry-run first"}])
        return CommandResult(ok=True, data={"would_start_turn": False, "started": True, "thread_id": thread_id, "turn_id": "turn-1"})

    def steer_turn(
        self,
        *,
        thread_id: str,
        turn_id: str | None,
        message: str,
        dry_run: bool,
        source_audit_id: str | None = None,
        confirmed: bool = False,
        max_chars: int = 4000,
    ) -> CommandResult:
        if dry_run:
            return CommandResult(ok=True, data={"would_steer_turn": True, "steered": False, "thread_id": thread_id, "turn_id": turn_id})
        if not confirmed or not source_audit_id or not turn_id:
            return CommandResult(ok=False, errors=[{"code": "controller_confirmation_required", "message": "confirm", "guidance": "dry-run first"}])
        return CommandResult(ok=True, data={"would_steer_turn": False, "steered": True, "thread_id": thread_id, "turn_id": turn_id})

    def interrupt_turn(
        self,
        *,
        thread_id: str,
        turn_id: str | None,
        dry_run: bool,
        source_audit_id: str | None = None,
        confirmed: bool = False,
    ) -> CommandResult:
        if dry_run:
            return CommandResult(ok=True, data={"would_interrupt_turn": True, "interrupted": False, "thread_id": thread_id, "turn_id": turn_id})
        if not confirmed or not source_audit_id or not turn_id:
            return CommandResult(ok=False, errors=[{"code": "controller_confirmation_required", "message": "confirm", "guidance": "dry-run first"}])
        return CommandResult(ok=True, data={"would_interrupt_turn": False, "interrupted": True, "thread_id": thread_id, "turn_id": turn_id})


def run_cli(argv: list[str], observer: FakeObserver, tmp_path: Path) -> dict:
    stdout = io.StringIO()
    exit_code = main(
        argv,
        observer_factory=lambda: observer,
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


def test_connections_status_json_reports_remote_control_capability(tmp_path: Path) -> None:
    payload = run_cli(["codex", "connections", "status", "--json"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.connections.status"
    assert payload["data"]["app_server"]["websocket_listen_supported"] is True
    assert "turn/started" in payload["data"]["live_notifications"]["expected_methods"]


def test_app_server_threads_json_is_capped(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "threads", "--json", "--max-items", "1"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.threads"
    assert payload["data"]["threads"][0]["source"] == "app_server"


def test_app_server_subscribe_json_reads_live_events(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "subscribe", "--json", "--thread-id", "thread-1", "--duration-ms", "100"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.subscribe"
    assert payload["data"]["events"][0]["method"] == "turn/started"


def test_app_server_start_turn_dry_run_defaults_safe(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "start-turn", "--json", "--thread-id", "thread-1", "--message", "continue", "--dry-run"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 0
    assert payload["command"] == "codex.app_server.start_turn"
    assert payload["data"]["would_start_turn"] is True
    assert payload["data"]["started"] is False


def test_app_server_start_turn_live_requires_confirmation(tmp_path: Path) -> None:
    payload = run_cli(["codex", "app-server", "start-turn", "--json", "--thread-id", "thread-1", "--message", "continue", "--live"], FakeObserver(), tmp_path)

    assert payload["_exit_code"] == 2
    assert payload["command"] == "codex.app_server.start_turn"
    assert payload["errors"][0]["code"] == "controller_confirmation_required"


def test_app_server_controller_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    stdout = io.StringIO()
    exit_code = main(
        [
            "codex",
            "app-server",
            "start-turn",
            "--json",
            "--thread-id",
            "thread-1",
            "--message",
            "continue",
            "--dry-run",
            "--live",
        ],
        observer_factory=lambda: FakeObserver(),
        app_server_factory=lambda: FakeAppServer(),
        stdout=stdout,
        state_dir=tmp_path,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""


def test_app_server_start_turn_live_with_confirmation(tmp_path: Path) -> None:
    payload = run_cli(
        [
            "codex",
            "app-server",
            "start-turn",
            "--json",
            "--thread-id",
            "thread-1",
            "--message",
            "continue",
            "--live",
            "--confirm",
            "--source-audit-id",
            "audit-123",
        ],
        FakeObserver(),
        tmp_path,
    )

    assert payload["_exit_code"] == 0
    assert payload["data"]["started"] is True
    assert payload["data"]["turn_id"] == "turn-1"


def test_app_server_steer_and_interrupt_dry_run(tmp_path: Path) -> None:
    steer = run_cli(
        ["codex", "app-server", "steer-turn", "--json", "--thread-id", "thread-1", "--turn-id", "turn-1", "--message", "adjust", "--dry-run"],
        FakeObserver(),
        tmp_path,
    )
    interrupt = run_cli(
        ["codex", "app-server", "interrupt-turn", "--json", "--thread-id", "thread-1", "--turn-id", "turn-1", "--dry-run"],
        FakeObserver(),
        tmp_path,
    )

    assert steer["_exit_code"] == 0
    assert steer["data"]["would_steer_turn"] is True
    assert interrupt["_exit_code"] == 0
    assert interrupt["data"]["would_interrupt_turn"] is True


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
