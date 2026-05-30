from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import signal
import stat
import sys
import time

import pytest

from evaos_desktop_bridge.audit import append_audit
from evaos_desktop_bridge.adapters.codex_app_server import (
    ALLOWED_APP_SERVER_METHODS,
    FORBIDDEN_APP_SERVER_METHODS,
    CodexAppServerObserver,
    CodexJsonRpcClient,
    JsonRpcResponse,
    LineProcessTransport,
    TransportConfig,
    WebSocketTransport,
    _build_websocket_frame,
)
from evaos_desktop_bridge.adapters import codex_app_server as codex_app_server_module
from evaos_desktop_bridge.adapters.codex_macos import MacOSCodexObserver, RunnerResult
from evaos_desktop_bridge.policy import PolicyError, command_metadata, ensure_allowed
from evaos_desktop_bridge.queue import append_queue_event, list_queue_events
from evaos_desktop_bridge.redaction import cap_text, redact_value
from evaos_desktop_bridge.schema import build_envelope, make_error
from evaos_desktop_bridge.state import read_audit_record, read_audit_tail, read_latest, write_latest
from evaos_desktop_bridge.cli import _run_connector_service
from evaos_desktop_bridge.types import CommandResult


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
    assert command_metadata("codex.thread_map")["mode"] == "read_only"
    assert command_metadata("codex.send_visible_message")["mode"] == "guarded_visible_message_action"
    assert command_metadata("codex.send_visible_message")["requires_approval"] is True
    assert command_metadata("codex.app_server.status")["source"] == "app_server"
    assert command_metadata("codex.app_server.threads")["source"] == "app_server"
    assert command_metadata("codex.continue_thread")["support_only"] is True
    assert command_metadata("customer_mac.iphone_mirroring_open_app")["requires_active_control_session"] is True
    assert command_metadata("customer_mac.iphone_mirroring_send_approved_message")["mode"] == "full_access_control"
    assert command_metadata("customer_mac.iphone_mirroring_send_approved_message")["high_impact_in_ask_permission"] is True
    assert command_metadata("customer_mac.screen_sharing_status")["bridge_can_enable"] is False
    assert command_metadata("customer_mac.desktop_see")["sensitive_app_block"] is True
    assert command_metadata("customer_mac.snapshot")["sensitive_app_block"] is True
    assert command_metadata("customer_mac.ax_tree")["sensitive_app_block"] is True


def test_visible_thread_candidates_filter_controls_and_extract_status_project(tmp_path: Path) -> None:
    observer = MacOSCodexObserver(
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
    )
    payload = {
        "nodes": [
            {"role": "AXButton", "name": "Archive chat", "window_index": 0, "bounds": {"x": 1, "y": 1, "width": 20, "height": 20}},
            {"role": "AXStaticText", "name": "Projects", "window_index": 0},
            {"role": "AXStaticText", "name": "Codex", "window_index": 0},
            {"role": "AXButton", "name": "I found ... Awaiting response", "window_index": 0, "bounds": {"x": 20, "y": 120, "width": 240, "height": 36}},
            {"role": "AXButton", "name": "Unpin chat Archive chat 13h", "window_index": 0, "bounds": {"x": 20, "y": 160, "width": 240, "height": 36}},
            {"role": "AXButton", "name": "need to review ram and mem... 55m", "window_index": 0, "bounds": {"x": 20, "y": 200, "width": 260, "height": 36}},
            {"role": "AXButton", "name": "Send", "window_index": 0, "bounds": {"x": 520, "y": 720, "width": 32, "height": 32}},
        ]
    }

    threads = observer._visible_threads_from_payload(payload, max_items=10)

    assert [thread["title"] for thread in threads] == ["I found ...", "need to review ram and mem..."]
    assert threads[0]["project"] == "Codex"
    assert threads[0]["status"] == "Awaiting response"
    assert threads[0]["confidence"] == "high"
    assert threads[0]["center"] == {"x": 140, "y": 138}
    assert threads[1]["updated_label"] == "55m"
    assert all("Archive chat" not in thread["raw_title"] for thread in threads)


def test_visible_thread_candidates_fallback_to_selection_only_rows_when_titles_hidden(tmp_path: Path) -> None:
    observer = MacOSCodexObserver(
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
    )
    payload = {
        "nodes": [
            {"role": "AXButton", "name": "Unpin chat Archive chat 13h", "window_index": 0, "bounds": {"x": 20, "y": 120, "width": 240, "height": 36}},
            {"role": "AXButton", "name": "Unpin chat", "window_index": 0, "bounds": {"x": 220, "y": 128, "width": 21, "height": 20}},
            {"role": "AXButton", "name": "Archive chat", "window_index": 0, "bounds": {"x": 250, "y": 128, "width": 21, "height": 20}},
        ]
    }

    threads = observer._visible_threads_from_payload(payload, max_items=10)

    assert len(threads) == 1
    assert threads[0]["title"] == "Visible thread row 1 (title unavailable)"
    assert threads[0]["raw_title"] == "title_unavailable"
    assert threads[0]["selection_only"] is True
    assert threads[0]["updated_label"] == "13h"
    assert threads[0]["center"] == {"x": 140, "y": 138}


def test_visible_thread_candidates_keep_title_hidden_sidebar_rows_ahead_of_body_text(tmp_path: Path) -> None:
    observer = MacOSCodexObserver(
        state_dir=tmp_path,
        platform_name="Darwin",
        accessibility_checker=lambda: True,
        screen_recording_checker=lambda: True,
    )
    payload = {
        "nodes": [
            {"role": "AXButton", "name": "Unpin chat Archive chat 13h", "window_index": 0, "bounds": {"x": 20, "y": 120, "width": 240, "height": 36}},
            {"role": "AXStaticText", "name": "Body response text that is not a sidebar thread", "window_index": 0, "bounds": {"x": 450, "y": 200, "width": 500, "height": 30}},
        ]
    }

    compact = observer._visible_threads_from_payload(payload, max_items=1)
    expanded = observer._visible_threads_from_payload(payload, max_items=50)

    assert compact[0]["selection_only"] is True
    assert expanded[0]["visible_id"] == compact[0]["visible_id"]
    assert expanded[0]["selection_only"] is True
    assert expanded[0]["updated_label"] == "13h"


class FakeVisibleCodexObserver(MacOSCodexObserver):
    def __init__(
        self,
        tmp_path: Path,
        *,
        composer: bool = True,
        frontmost_ok: bool = True,
        stale: bool = False,
        selected_after_select: bool = True,
        selection_only: bool = False,
        title_hidden_updated_label: str | None = None,
        wait_states: list[str | dict[str, object]] | None = None,
    ) -> None:
        self.commands: list[list[str]] = []
        self.sleep_calls: list[float] = []
        self._composer = composer
        self._frontmost_ok = frontmost_ok
        self._stale = stale
        self._selected_after_select = selected_after_select
        self._selection_only = selection_only
        self._title_hidden_updated_label = title_hidden_updated_label
        self._wait_states = list(wait_states or [])
        self._did_select = False
        super().__init__(
            runner=self._run,
            state_dir=tmp_path,
            platform_name="Darwin",
            accessibility_checker=lambda: True,
            screen_recording_checker=lambda: True,
            now=lambda: "2026-05-29T10:00:00Z",
        )

    def _run(self, command: list[str], timeout: float = 5.0) -> RunnerResult:
        self.commands.append(command)
        return RunnerResult(returncode=0, stdout="", stderr="")

    def threads(self, *, max_items: int) -> CommandResult:
        threads = []
        if not self._stale:
            threads.append(
                {
                    "visible_id": "visible-0-abc",
                    "index": 0,
                    "title": "Visible thread row 1 (title unavailable)" if self._selection_only else "Implement bridge",
                    "raw_title": "Implement bridge Awaiting response",
                    "title_hash": "title-hash",
                    "role": "AXButton",
                    "title_available": False if self._selection_only else True,
                    "updated_label": self._title_hidden_updated_label,
                    "bounds": {"x": 10, "y": 20, "width": 100, "height": 40},
                    "window_bounds": {"x": 0, "y": 0, "width": 800, "height": 800},
                    "center": {"x": 60, "y": 40},
                    "selected": self._did_select and self._selected_after_select,
                    "focused": False,
                    "confidence": "low" if self._selection_only else "high",
                    "source": "ax",
                    "selection_only": self._selection_only,
                }
            )
        return CommandResult(ok=True, data={"threads": threads[:max_items], "count": len(threads[:max_items]), "max_items": max_items, "source": "ax"})

    def frontmost(self) -> CommandResult:
        return CommandResult(ok=True, data={"frontmost_app": "Codex" if self._frontmost_ok else "Safari", "codex_frontmost": self._frontmost_ok})

    def ax_tree(self, *, max_nodes: int) -> CommandResult:
        nodes = []
        if self._composer:
            nodes.append({"role": "AXTextArea", "name": "Message Codex", "bounds": {"x": 200, "y": 700, "width": 500, "height": 80}})
        return CommandResult(ok=True, data={"nodes": nodes, "truncated": False, "max_nodes": max_nodes})

    def snapshot(self, *, max_chars: int) -> CommandResult:
        return CommandResult(ok=True, data={"screenshot_path": str(self.state_dir / "screenshots" / "before.png"), "max_chars": max_chars})

    def select_thread(self, *, thread_id: str, dry_run: bool = False, max_items: int = 200) -> CommandResult:
        if self._stale or thread_id != "visible-0-abc":
            return CommandResult(ok=False, data={"selected": False}, errors=[make_error(code="visible_thread_not_found", message="missing", guidance="rerun threads")])
        self._did_select = not dry_run
        return CommandResult(ok=True, data={"selected": not dry_run, "would_select": dry_run, "thread_id": thread_id, "target": self.threads(max_items=1).data["threads"][0]})

    def _visible_message_wait_observation(self, *, max_chars: int = 1000) -> dict[str, object]:
        next_state = self._wait_states.pop(0) if self._wait_states else "submitted_waiting"
        if isinstance(next_state, dict):
            observation = dict(next_state)
            observation.setdefault("timestamp", self.now())
            observation.setdefault("codex_frontmost", True)
            observation.setdefault("composer_visible", observation.get("state") == "idle")
            observation.setdefault("active_indicators", ["Awaiting response"] if observation.get("state") == "submitted_waiting" else [])
            observation.setdefault("screenshot_path", str(self.state_dir / "screenshots" / f"{observation.get('state', 'unknown')}.png"))
            observation.setdefault("max_chars", max_chars)
            return observation
        state = str(next_state)
        return {
            "timestamp": self.now(),
            "state": state,
            "idle_confidence": "explicit" if state == "idle" else None,
            "codex_frontmost": True,
            "composer_visible": state == "idle",
            "active_indicators": ["Awaiting response"] if state == "submitted_waiting" else [],
            "screenshot_path": str(self.state_dir / "screenshots" / f"{state}.png"),
            "max_chars": max_chars,
        }

    def _sleep_for_visible_message_poll(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)


def test_send_visible_message_dry_run_preflights_without_typing(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path)

    result = observer.send_visible_message(thread_id="visible-0-abc", message="Continue from the visible GUI.", dry_run=True)

    assert result.ok is True
    assert result.data["would_submit"] is True
    assert result.data["submitted"] is False
    assert result.data["message_hash"]
    assert result.data["message_preview"] == "Continue from the visible GUI."
    assert result.provenance["source"] == "codex_visible_gui"
    assert observer.commands == []


def test_send_visible_message_fails_closed_without_composer(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path, composer=False)

    result = observer.send_visible_message(thread_id="visible-0-abc", message="hello", dry_run=True)

    assert result.ok is False
    assert result.errors[0]["code"] == "codex_visible_composer_not_found"


def test_send_visible_message_live_requires_confirmation(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path)

    result = observer.send_visible_message(thread_id="visible-0-abc", message="hello", dry_run=False, confirmed=False)

    assert result.ok is False
    assert result.errors[0]["code"] == "visible_message_confirmation_required"
    assert observer.commands == []


def test_send_visible_message_live_selects_composer_and_submits(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path)

    result = observer.send_visible_message(thread_id="visible-0-abc", message="hello", dry_run=False, confirmed=True)

    assert result.ok is True
    assert result.data["submitted"] is True
    assert result.provenance["dry_run"] is False
    assert result.provenance["selected_visible_target_id"] == "visible-0-abc"
    assert any("click at {450, 740}" in " ".join(command) for command in observer.commands)
    assert any("keystroke" in " ".join(command) and "key code 36" in " ".join(command) for command in observer.commands)


def test_send_visible_message_current_thread_does_not_select_sidebar_row(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path)

    result = observer.send_visible_message(thread_id="current", message="hello", dry_run=False, confirmed=True)

    assert result.ok is True
    assert result.data["submitted"] is True
    assert result.data["target"]["visible_id"] == "current"
    assert not observer._did_select
    assert any("keystroke" in " ".join(command) and "key code 36" in " ".join(command) for command in observer.commands)


def test_send_visible_message_live_reports_wait_state_until_idle(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path, wait_states=["submitted_waiting", "idle"])

    result = observer.send_visible_message(
        thread_id="visible-0-abc",
        message="hello",
        dry_run=False,
        confirmed=True,
        wait_ms=3000,
        poll_interval_ms=1000,
    )

    assert result.ok is True
    assert result.data["submitted"] is True
    assert result.data["post_send"]["state"] == "idle"
    assert result.data["post_send"]["read_only_after_submit"] is True
    assert result.data["post_send"]["observation_count"] == 2
    assert result.data["post_send"]["observations"][0]["state"] == "submitted_waiting"
    assert result.data["post_send"]["observations"][1]["state"] == "idle"
    assert result.provenance["post_send_state"] == "idle"
    assert observer.sleep_calls == [1.0]
    assert sum(1 for command in observer.commands if "keystroke" in " ".join(command)) == 1


def test_send_visible_message_wait_exits_after_stable_implicit_idle(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(
        tmp_path,
        wait_states=[
            "submitted_waiting",
            {"state": "idle", "idle_confidence": "implicit_composer_visible", "composer_visible": True},
            {"state": "idle", "idle_confidence": "implicit_composer_visible", "composer_visible": True},
        ],
    )

    result = observer.send_visible_message(
        thread_id="visible-0-abc",
        message="hello",
        dry_run=False,
        confirmed=True,
        wait_ms=5000,
        poll_interval_ms=1000,
    )

    assert result.ok is True
    assert result.data["post_send"]["state"] == "idle"
    assert result.data["post_send"]["idle_confidence"] == "stable_implicit_composer_visible"
    assert result.data["post_send"]["observation_count"] == 3
    assert result.provenance["post_send_state"] == "idle"
    assert observer.sleep_calls == [1.0, 1.0]
    assert sum(1 for command in observer.commands if "keystroke" in " ".join(command)) == 1


def test_send_visible_message_wait_reports_inconclusive_contamination(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(
        tmp_path,
        wait_states=[
            "submitted_waiting",
            {
                "state": "inconclusive",
                "contamination_reason": "codex_not_frontmost",
                "codex_frontmost": False,
                "composer_visible": False,
            },
        ],
    )

    result = observer.send_visible_message(
        thread_id="visible-0-abc",
        message="hello",
        dry_run=False,
        confirmed=True,
        wait_ms=5000,
        poll_interval_ms=1000,
    )

    assert result.ok is True
    assert result.data["post_send"]["state"] == "inconclusive"
    assert result.data["post_send"]["contamination_reason"] == "codex_not_frontmost"
    assert result.data["post_send"]["read_only_after_submit"] is True
    assert result.provenance["post_send_state"] == "inconclusive"
    assert observer.sleep_calls == [1.0]
    assert sum(1 for command in observer.commands if "keystroke" in " ".join(command)) == 1


def test_send_visible_message_live_wait_timeout_keeps_progress_evidence(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path, wait_states=["submitted_waiting", "submitted_waiting"])

    result = observer.send_visible_message(
        thread_id="visible-0-abc",
        message="hello",
        dry_run=False,
        confirmed=True,
        wait_ms=1500,
        poll_interval_ms=1000,
    )

    assert result.ok is True
    assert result.data["post_send"]["state"] == "timeout"
    assert result.data["post_send"]["last_observed_state"] == "submitted_waiting"
    assert result.data["post_send"]["observation_count"] >= 1
    assert result.data["post_send"]["read_only_after_submit"] is True
    assert result.provenance["post_send_state"] == "timeout"
    assert sum(1 for command in observer.commands if "keystroke" in " ".join(command)) == 1


def test_send_visible_message_wait_caps_returned_observations_without_shortening_wait(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path, wait_states=["submitted_waiting"] * 40)

    result = observer.send_visible_message(
        thread_id="visible-0-abc",
        message="hello",
        dry_run=False,
        confirmed=True,
        wait_ms=8000,
        poll_interval_ms=250,
    )

    assert result.ok is True
    assert result.data["post_send"]["state"] == "timeout"
    assert result.data["post_send"]["observation_count"] == 33
    assert len(result.data["post_send"]["observations"]) == 25
    assert result.data["post_send"]["observations_truncated"] is True
    assert len(observer.sleep_calls) == 32


def test_visible_message_wait_observation_marks_frontmost_loss_inconclusive(tmp_path: Path) -> None:
    class FrontmostLostObserver(MacOSCodexObserver):
        def __init__(self, state_dir: Path) -> None:
            super().__init__(
                runner=lambda command, timeout=5.0: RunnerResult(returncode=0, stdout="", stderr=""),
                state_dir=state_dir,
                platform_name="Darwin",
                accessibility_checker=lambda: True,
                screen_recording_checker=lambda: True,
                now=lambda: "2026-05-29T10:00:00Z",
            )

        def frontmost(self) -> CommandResult:
            return CommandResult(ok=True, data={"frontmost_app": "Notification Center", "codex_frontmost": False})

    observer = FrontmostLostObserver(tmp_path)

    observation = observer._visible_message_wait_observation()

    assert observation["state"] == "inconclusive"
    assert observation["contamination_reason"] == "codex_not_frontmost"
    assert observation["codex_frontmost"] is False


def test_visible_message_wait_observation_marks_ax_loss_inconclusive(tmp_path: Path) -> None:
    class AxUnavailableObserver(MacOSCodexObserver):
        def __init__(self, state_dir: Path) -> None:
            super().__init__(
                runner=lambda command, timeout=5.0: RunnerResult(returncode=0, stdout="", stderr=""),
                state_dir=state_dir,
                platform_name="Darwin",
                accessibility_checker=lambda: True,
                screen_recording_checker=lambda: True,
                now=lambda: "2026-05-29T10:00:00Z",
            )

        def frontmost(self) -> CommandResult:
            return CommandResult(ok=True, data={"frontmost_app": "Codex", "codex_frontmost": True})

        def ax_tree(self, *, max_nodes: int) -> CommandResult:
            return CommandResult(ok=False, data={"nodes": []}, errors=[make_error(code="ax_tree_unavailable", message="missing", guidance="check permissions")])

    observer = AxUnavailableObserver(tmp_path)

    observation = observer._visible_message_wait_observation()

    assert observation["state"] == "inconclusive"
    assert observation["contamination_reason"] == "ax_unavailable"
    assert observation["codex_frontmost"] is True


def test_visible_message_wait_observation_scans_done_after_active_indicator_cap(tmp_path: Path) -> None:
    class DoneAfterActiveObserver(MacOSCodexObserver):
        def __init__(self, state_dir: Path) -> None:
            super().__init__(
                runner=lambda command, timeout=5.0: RunnerResult(returncode=0, stdout="", stderr=""),
                state_dir=state_dir,
                platform_name="Darwin",
                accessibility_checker=lambda: True,
                screen_recording_checker=lambda: True,
                now=lambda: "2026-05-29T10:00:00Z",
            )

        def frontmost(self) -> CommandResult:
            return CommandResult(ok=True, data={"frontmost_app": "Codex", "codex_frontmost": True})

        def ax_tree(self, *, max_nodes: int) -> CommandResult:
            nodes = [
                {"role": "AXStaticText", "name": f"Thinking {index}", "bounds": {"x": 1, "y": index, "width": 10, "height": 10}}
                for index in range(10)
            ]
            nodes.append({"role": "AXStaticText", "name": "Done", "bounds": {"x": 1, "y": 20, "width": 10, "height": 10}})
            return CommandResult(ok=True, data={"nodes": nodes, "truncated": False, "max_nodes": max_nodes})

        def snapshot(self, *, max_chars: int) -> CommandResult:
            return CommandResult(ok=True, data={"screenshot_path": str(self.state_dir / "done.png"), "max_chars": max_chars})

    observer = DoneAfterActiveObserver(tmp_path)

    observation = observer._visible_message_wait_observation()

    assert observation["state"] == "done"
    assert len(observation["active_indicators"]) == 5


def test_codex_visible_message_applescript_expr_handles_multiline_controls(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path)

    expr = observer._applescript_string_expr('hello "there"\\next\nline\r\nnext\tstop\x01')

    assert "\n" not in expr
    assert '"hello \\"there\\"\\\\next"' in expr
    assert "return" in expr
    assert "tab" in expr
    assert "(ASCII character 1)" in expr


def test_send_visible_message_live_fails_if_selection_not_verified(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path, selected_after_select=False)

    result = observer.send_visible_message(thread_id="visible-0-abc", message="hello", dry_run=False, confirmed=True)

    assert result.ok is False
    assert result.errors[0]["code"] == "visible_thread_selection_not_verified"
    assert not any("keystroke" in " ".join(command) for command in observer.commands)


def test_send_visible_message_live_rejects_selection_only_rows(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path, selection_only=True)

    result = observer.send_visible_message(thread_id="visible-0-abc", message="hello", dry_run=False, confirmed=True)

    assert result.ok is False
    assert result.errors[0]["code"] == "visible_thread_identity_not_verifiable"
    assert observer.commands == []


def test_send_visible_message_live_rejects_title_hidden_row_even_with_stable_evidence(tmp_path: Path) -> None:
    observer = FakeVisibleCodexObserver(tmp_path, selection_only=True, title_hidden_updated_label="1m")

    result = observer.send_visible_message(thread_id="visible-0-abc", message="hello", dry_run=False, confirmed=True)

    assert result.ok is False
    assert result.errors[0]["code"] == "visible_thread_identity_not_verifiable"
    assert not any("keystroke" in " ".join(command) for command in observer.commands)


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


def test_line_process_transport_reads_buffered_line_after_process_exits(tmp_path: Path) -> None:
    script_path = tmp_path / "print-and-exit.py"
    script_path.write_text(
        "import json\nprint(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'ok': True}}), flush=True)\n",
        encoding="utf-8",
    )
    transport = LineProcessTransport([sys.executable, str(script_path)], timeout=0.2)

    try:
        transport.process.wait(timeout=2.0)
        line = transport.read_line(time.monotonic() + 1.0)
    finally:
        transport.close()

    assert line is not None
    assert json.loads(line)["result"] == {"ok": True}


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
