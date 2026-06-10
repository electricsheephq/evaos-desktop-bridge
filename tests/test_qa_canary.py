from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from evaos_desktop_bridge import qa_canary
from evaos_desktop_bridge.qa_canary import (
    CanaryStep,
    ConnectorSurface,
    HermesSurface,
    OpenClawSurface,
    SurfaceResponse,
    build_scenarios,
    classify_status,
    main,
    redact_for_report,
    run_steps,
    timeout_for_command,
    write_reports,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeConnectorHandler(BaseHTTPRequestHandler):
    responses: dict[str, dict[str, Any]] = {}
    seen_authorization: str | None = None
    seen_payloads: list[dict[str, Any]] = []

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/artifacts/snap-test.png":
            if self.headers.get("Authorization") != "Bearer secret-token":
                self.send_response(401)
                self.end_headers()
                return
            body = b"\x89PNG\r\n\x1a\nfake"
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        FakeConnectorHandler.seen_authorization = self.headers.get("Authorization")
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        FakeConnectorHandler.seen_payloads.append(payload)
        command = payload["command"]
        response = self.responses.get(command)
        if response is None:
            response = {
                "ok": False,
                "command": command,
                "errors": [{"code": "unknown_command", "message": "unknown", "guidance": "test"}],
                "warnings": [],
                "data": {},
                "audit_id": "audit-unknown",
            }
        status = 200 if response.get("ok") else 422
        body = json.dumps(response).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def serve_fake_connector(responses: dict[str, dict[str, Any]]) -> tuple[str, ThreadingHTTPServer]:
    FakeConnectorHandler.responses = responses
    FakeConnectorHandler.seen_authorization = None
    FakeConnectorHandler.seen_payloads = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeConnectorHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return f"http://{host}:{port}", server


def envelope(command: str, *, ok: bool = True, data: dict[str, Any] | None = None, errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "2026-05-02.mvp1",
        "command": command,
        "target": "customer_mac",
        "timestamp": "2026-05-23T00:00:00Z",
        "ok": ok,
        "data": data or {},
        "warnings": [],
        "errors": errors or [],
        "audit_id": f"audit-{command}",
    }


def visual_envelope(command: str, *, snapshot_id: str = "snap-test", text: str = "Calculator 0 1 2 3", app: str = "Calculator") -> dict[str, Any]:
    return envelope(
        command,
        data={
            "engine": "peekaboo",
            "snapshot_id": snapshot_id,
            "frontmost_app": app,
            "elements": [
                {"element_id": "el-one", "label": text, "bounds": {"x": 10, "y": 20, "width": 40, "height": 40}},
            ],
            "image": {
                "artifact_url": "/v1/artifacts/snap-test.png",
                "snapshot_id": snapshot_id,
            },
        },
    )


class SequencedSurface:
    def __init__(self, responses: list[dict[str, Any]], *, artifact_path: str | None = None) -> None:
        self.responses = list(responses)
        self.artifact_path = artifact_path
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, command: str, params: dict[str, Any]) -> SurfaceResponse:
        self.calls.append((command, params))
        if self.responses:
            return SurfaceResponse.from_payload(self.responses.pop(0), artifact_path=self.artifact_path)
        return SurfaceResponse.from_payload(envelope(command), artifact_path=self.artifact_path)


def test_connector_surface_runs_fake_command_and_materializes_artifact(tmp_path: Path) -> None:
    connector_url, server = serve_fake_connector(
        {
            "desktop_see": envelope(
                "desktop_see",
                data={
                    "engine": "peekaboo",
                    "snapshot_id": "snap-test",
                    "screenshot": {
                        "screenshot": {
                            "artifact_url": "/v1/artifacts/snap-test.png",
                            "snapshot_id": "snap-test",
                        },
                    },
                },
            )
        }
    )
    try:
        surface = ConnectorSurface(connector_url=connector_url, token="secret-token", artifact_dir=tmp_path)
        response = surface.run("desktop_see", {"max_chars": 10})
    finally:
        server.shutdown()

    assert FakeConnectorHandler.seen_authorization == "Bearer secret-token"
    assert FakeConnectorHandler.seen_payloads == [{"command": "desktop_see", "params": {"max_chars": 10}}]
    assert response.ok is True
    assert response.audit_id == "audit-desktop_see"
    assert response.engine == "peekaboo"
    assert response.snapshot_id == "snap-test"
    assert response.artifact_path is not None
    assert Path(response.artifact_path).read_bytes().startswith(b"\x89PNG")


def test_failed_and_unavailable_commands_are_reported_explicitly(tmp_path: Path) -> None:
    connector_url, server = serve_fake_connector(
        {
            "iphone_see": envelope(
                "iphone_see",
                ok=False,
                errors=[{"code": "iphone_mirroring_not_running", "message": "not running", "guidance": "open iPhone Mirroring"}],
            ),
            "desktop_click": envelope(
                "desktop_click",
                ok=False,
                errors=[{"code": "approval_audit_required", "message": "approval required", "guidance": "dry run first"}],
            ),
        }
    )
    try:
        surface = ConnectorSurface(connector_url=connector_url, token="secret-token", artifact_dir=tmp_path)
        results = run_steps(
            [
                CanaryStep(id="iphone.see", suite="iphone", command="iphone_see", skip_on_unavailable=True),
                CanaryStep(id="desktop.click", suite="desktop", command="desktop_click"),
            ],
            surface,
        )
    finally:
        server.shutdown()

    assert [result.status for result in results] == ["skipped", "failed"]
    assert results[0].errors[0]["code"] == "iphone_mirroring_not_running"
    assert results[1].errors[0]["code"] == "approval_audit_required"


def test_report_redacts_tokens_contacts_and_real_world_text(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("QA_SMS_CONTACT", "Ze Barrow")
    monkeypatch.setenv("QA_SMS_TEXT", "hello from private test")
    monkeypatch.setenv("QA_BUMBLE_TEXT", "Hello?")
    monkeypatch.setenv("EVAOS_DESKTOP_BRIDGE_TOKEN", "super-secret-token")
    monkeypatch.setenv("QA_CONNECTOR_TOKEN", "custom-secret-token")

    redacted = redact_for_report(
        {
            "connector_url": "http://100.64.10.12:8765",
            "token": "super-secret-token",
            "recipient_context": "Ze Barrow",
            "text": "hello from private test",
            "nested": ["Hello?", "custom-secret-token", "safe"],
        }
    )

    serialized = json.dumps(redacted)
    assert "super-secret-token" not in serialized
    assert "custom-secret-token" not in serialized
    assert "Ze Barrow" not in serialized
    assert "hello from private test" not in serialized
    assert "Hello?" not in serialized
    assert "[redacted]" in serialized

    report_paths = write_reports(
        artifact_dir=tmp_path,
        run_id="qa-test",
        started_at="2026-05-23T00:00:00Z",
        version_under_test="candidate-version",
        surface="connector",
        connector_url="http://100.64.10.12:8765",
        results=[],
    )
    assert report_paths["json"].exists()
    assert report_paths["markdown"].exists()
    assert "100.64.10.12" not in report_paths["markdown"].read_text(encoding="utf-8")
    assert "http://100.64." in report_paths["markdown"].read_text(encoding="utf-8")


def test_write_reports_sanitizes_existing_artifact_files(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("QA_CONNECTOR_TOKEN", "artifact-secret-token")
    env_file = tmp_path / "env.sh"
    env_file.write_text(
        "export EVAOS_DESKTOP_BRIDGE_TOKEN=artifact-secret-token\n"
        "export EVAOS_CONNECTOR_URL=http://100.64.10.12:8765\n",
        encoding="utf-8",
    )

    write_reports(
        artifact_dir=tmp_path,
        run_id="qa-test",
        started_at="2026-05-23T00:00:00Z",
        version_under_test="candidate-version",
        surface="connector",
        connector_url="http://100.64.10.12:8765",
        results=[],
    )

    assert "artifact-secret-token" not in env_file.read_text(encoding="utf-8")
    assert "[redacted]" in env_file.read_text(encoding="utf-8")


def test_openclaw_surface_calls_runbridge_helper(monkeypatch: Any, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        captured["input"] = kwargs["input"]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(envelope("desktopSee")), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    surface = OpenClawSurface(connector_url="http://100.64.10.12:8765", token="secret-token", artifact_dir=tmp_path, repo_root=ROOT)
    response = surface.run("desktop_see", {"max_chars": 10})

    assert response.ok is True
    assert captured["args"][0] == "node"
    assert captured["args"][-2:] == ["desktop_see", "-"]
    assert str(ROOT / "openclaw-plugin" / "scripts" / "qa-run-bridge.mjs") in captured["args"]
    assert "secret private text" not in " ".join(captured["args"])
    assert captured["input"] == '{"max_chars":10}'
    assert captured["env"]["EVAOS_DESKTOP_BRIDGE_URL"] == "http://100.64.10.12:8765"
    assert captured["env"]["EVAOS_DESKTOP_BRIDGE_TOKEN"] == "secret-token"
    assert captured["env"]["EVAOS_DESKTOP_BRIDGE_ARTIFACT_DIR"] == str(tmp_path)


def test_openclaw_helper_runs_real_runbridge_against_fake_connector(tmp_path: Path) -> None:
    connector_url, server = serve_fake_connector({"status": envelope("status")})
    try:
        completed = subprocess.run(
            ["node", str(ROOT / "openclaw-plugin" / "scripts" / "qa-run-bridge.mjs"), "desktop_bridge_status", "-"],
            cwd=ROOT,
            env={
                **os.environ,
                "EVAOS_DESKTOP_BRIDGE_URL": connector_url,
                "EVAOS_DESKTOP_BRIDGE_TOKEN": "secret-token",
                "EVAOS_DESKTOP_BRIDGE_ARTIFACT_DIR": str(tmp_path),
            },
            input="{}",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=True,
        )
    finally:
        server.shutdown()

    assert json.loads(completed.stdout)["ok"] is True
    assert FakeConnectorHandler.seen_payloads[-1] == {"command": "status", "params": {}}


def test_hermes_surface_calls_adapter_script(monkeypatch: Any, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        captured["input"] = kwargs["input"]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(envelope("customer_mac_status")), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    surface = HermesSurface(connector_url="http://100.64.10.12:8765", token="secret-token", artifact_dir=tmp_path, repo_root=ROOT)
    response = surface.run("customer_mac_status", {})

    assert response.ok is True
    assert captured["args"][0] == str(ROOT / "hermes-adapter" / "bin" / "evaos-desktop-bridge-command")
    assert captured["args"][1:] == ["customer_mac_status", "-"]
    assert captured["input"] == "{}"
    assert captured["env"]["EVAOS_DESKTOP_BRIDGE_URL"] == "http://100.64.10.12:8765"
    assert captured["env"]["EVAOS_DESKTOP_BRIDGE_TOKEN"] == "secret-token"


def test_hermes_adapter_materializes_visual_evidence_against_fake_connector(tmp_path: Path) -> None:
    connector_url, server = serve_fake_connector(
        {
            "desktop_see": envelope(
                "desktop_see",
                data={
                    "engine": "peekaboo",
                    "snapshot_id": "snap-test",
                    "image": {
                        "artifact_url": "/v1/artifacts/snap-test.png",
                        "snapshot_id": "snap-test",
                    },
                },
            )
        }
    )
    try:
        surface = HermesSurface(connector_url=connector_url, token="secret-token", artifact_dir=tmp_path, repo_root=ROOT)
        response = surface.run("desktop_see", {"max_chars": 10})
    finally:
        server.shutdown()

    assert response.ok is True
    assert response.engine == "peekaboo"
    assert response.snapshot_id == "snap-test"
    assert response.artifact_path is not None
    assert Path(response.artifact_path).read_bytes().startswith(b"\x89PNG")
    assert FakeConnectorHandler.seen_payloads[-1] == {"command": "desktop_see", "params": {"max_chars": 10}}


def test_scenario_catalog_is_explicit_and_real_world_config_is_local_only() -> None:
    all_steps = build_scenarios("all", allow_real_world_actions=False)
    suites = {step.suite for step in all_steps}
    steps_by_id = {step.id: step for step in all_steps}

    assert {"readiness", "codex", "primitive", "desktop_scenario", "iphone_scenario", "full_access", "ask_permission"}.issubset(suites)
    assert "kill_switch" not in suites
    assert "real_world_optional" not in suites
    assert any(step.lane == "primitive" for step in all_steps)
    assert any(step.lane == "scenario" for step in all_steps)
    assert steps_by_id["primitive.desktop_click_coordinates"].params["y"] <= 20
    assert steps_by_id["full.scroll_no_approval"].delay_before_seconds >= 10.0
    assert steps_by_id["ask.high_impact_denied"].delay_before_seconds >= 10.0
    assert all(step.id and step.command for step in all_steps)
    for step in all_steps:
        if step.lane == "scenario" and step.command in {
            "desktop_browser_action",
            "desktop_click",
            "desktop_drag",
            "desktop_focus_app",
            "desktop_hotkey",
            "desktop_menu",
            "desktop_scroll",
            "desktop_type",
            "desktop_window",
            "iphone_swipe",
            "iphone_tap",
            "iphone_type",
            "customer_mac_iphone_mirroring_app_switcher",
            "customer_mac_iphone_mirroring_home",
            "customer_mac_iphone_mirroring_open_app",
            "customer_mac_iphone_mirroring_spotlight",
        }:
            assert step.assert_from_step is not None
    assert classify_status(envelope("desktop_see")) == "passed"
    assert classify_status(envelope("iphone_see", ok=False, errors=[{"code": "not_found", "message": "missing", "guidance": "test"}]), skip_on_unavailable=True) == "skipped"

    real_world_steps = build_scenarios("real_world_optional", allow_real_world_actions=True)
    assert {step.suite for step in real_world_steps} == {"real_world_optional"}
    serialized = json.dumps([step.params for step in real_world_steps])
    assert "David" not in serialized
    assert "Ze Barrow" not in serialized
    assert "Johnny" not in serialized


def test_timeout_mapping_separates_command_and_scenario_budgets() -> None:
    assert timeout_for_command("desktop_see") == 60
    assert timeout_for_command("iphone_see") == 60
    assert timeout_for_command("desktop_click") == 30
    assert timeout_for_command("iphone_tap") == 30
    assert timeout_for_command("iphone_swipe") == 20
    assert timeout_for_command("desktop_type") == 15
    assert timeout_for_command("unknown_future_command") == 10


def test_scenario_action_requires_fresh_visual_assertion(tmp_path: Path) -> None:
    connector_url, server = serve_fake_connector(
        {
            "iphone_see": visual_envelope("iphone_see", text="Home Screen", app="iPhone Mirroring"),
            "iphone_tap": envelope("iphone_tap"),
        }
    )
    try:
        surface = ConnectorSurface(connector_url=connector_url, token="secret-token", artifact_dir=tmp_path)
        results = run_steps(
            [
                CanaryStep(
                    id="iphone.see_home",
                    suite="iphone_scenario",
                    lane="scenario",
                    command="iphone_see",
                    requires_visual_evidence=True,
                    visual_assert={"expected_visible_text": "Calculator"},
                ),
                CanaryStep(
                    id="iphone.tap_after_unknown_state",
                    suite="iphone_scenario",
                    lane="scenario",
                    command="iphone_tap",
                    params={"snapshot_id": "${iphone.see_home.snapshot_id}", "x": 100, "y": 100, "dry_run": False},
                    assert_from_step="iphone.see_home",
                ),
            ],
            surface,
        )
    finally:
        server.shutdown()

    assert results[0].status == "failed"
    assert results[0].errors[0]["code"] == "qa_visual_assertion_failed"
    assert results[1].status == "failed"
    assert results[1].errors[0]["code"] == "qa_required_visual_state_failed"
    assert FakeConnectorHandler.seen_payloads == [{"command": "iphone_see", "params": {}}]


def test_scenario_action_runs_after_visual_assertion_passes(tmp_path: Path) -> None:
    connector_url, server = serve_fake_connector(
        {
            "iphone_see": visual_envelope("iphone_see", text="Calculator 1 2 3", app="Calculator"),
            "iphone_tap": envelope("iphone_tap"),
        }
    )
    try:
        surface = ConnectorSurface(connector_url=connector_url, token="secret-token", artifact_dir=tmp_path)
        results = run_steps(
            [
                CanaryStep(
                    id="iphone.see_calculator",
                    suite="iphone_scenario",
                    lane="scenario",
                    command="iphone_see",
                    requires_visual_evidence=True,
                    visual_assert={"expected_app": "Calculator", "expected_visible_text": "Calculator"},
                ),
                CanaryStep(
                    id="iphone.tap_calculator",
                    suite="iphone_scenario",
                    lane="scenario",
                    command="iphone_tap",
                    params={"snapshot_id": "${iphone.see_calculator.snapshot_id}", "x": 100, "y": 100, "dry_run": False},
                    assert_from_step="iphone.see_calculator",
                ),
            ],
            surface,
        )
    finally:
        server.shutdown()

    assert [result.status for result in results] == ["passed", "passed"]
    assert FakeConnectorHandler.seen_payloads[-1] == {"command": "iphone_tap", "params": {"snapshot_id": "snap-test", "x": 100, "y": 100, "dry_run": False}}


def test_visual_assertion_retries_transient_overlay_before_scenario_action(tmp_path: Path) -> None:
    artifact = tmp_path / "iphone-frame.png"
    artifact.write_bytes(b"fake png bytes")
    surface = SequencedSurface(
        [
            visual_envelope("iphone_see", snapshot_id="snap-overlay", text="Notification Center", app="iPhone Mirroring"),
            visual_envelope("iphone_see", snapshot_id="snap-calculator", text="Calculator", app="iPhone Mirroring"),
            envelope("iphone_tap"),
        ],
        artifact_path=str(artifact),
    )

    results = run_steps(
        [
            CanaryStep(
                id="iphone.see_calculator",
                suite="iphone_scenario",
                lane="scenario",
                command="iphone_see",
                requires_visual_evidence=True,
                visual_assert={"expected_visible_text": "Calculator"},
                visual_assert_retries=1,
                visual_retry_delay_seconds=0,
            ),
            CanaryStep(
                id="iphone.tap_calculator",
                suite="iphone_scenario",
                lane="scenario",
                command="iphone_tap",
                params={"snapshot_id": "${iphone.see_calculator.snapshot_id}", "x": 100, "y": 100, "dry_run": False},
                assert_from_step="iphone.see_calculator",
            ),
        ],
        surface,
    )

    assert results[0].status == "passed"
    assert results[0].snapshot_id == "snap-calculator"
    assert results[1].status == "passed"
    assert surface.calls == [
        ("iphone_see", {}),
        ("iphone_see", {}),
        ("iphone_tap", {"snapshot_id": "snap-calculator", "x": 100, "y": 100, "dry_run": False}),
    ]


def test_visual_assertion_retry_does_not_repeat_mutating_commands(tmp_path: Path) -> None:
    artifact = tmp_path / "iphone-frame.png"
    artifact.write_bytes(b"fake png bytes")
    surface = SequencedSurface(
        [
            visual_envelope("iphone_type", snapshot_id="snap-type", text="Wrong app", app="iPhone Mirroring"),
            visual_envelope("iphone_type", snapshot_id="snap-type-retry", text="Calculator", app="iPhone Mirroring"),
        ],
        artifact_path=str(artifact),
    )

    results = run_steps(
        [
            CanaryStep(
                id="iphone.type",
                suite="iphone_scenario",
                lane="primitive",
                command="iphone_type",
                requires_visual_evidence=True,
                visual_assert={"expected_visible_text": "Calculator"},
                visual_assert_retries=1,
                visual_retry_delay_seconds=0,
            )
        ],
        surface,
    )

    assert results[0].status == "failed"
    assert results[0].errors[0]["code"] == "qa_visual_assertion_failed"
    assert surface.calls == [("iphone_type", {})]


def test_iphone_visual_assertion_can_use_artifact_state(monkeypatch: Any, tmp_path: Path) -> None:
    artifact = tmp_path / "iphone-calculator.png"
    artifact.write_bytes(b"fake png bytes")
    monkeypatch.setattr(qa_canary, "_visual_artifact_states", lambda _path: {"calculator", "iphone_calculator"})
    surface = SequencedSurface(
        [
            envelope(
                "iphone_see",
                data={
                    "engine": "peekaboo",
                    "snapshot_id": "snap-image-only",
                    "frontmost_app": "iPhone Mirroring",
                    "elements": [{"element_id": "iphone-mirroring-window", "label": "iPhone Mirroring window"}],
                    "image": {"artifact_url": "/v1/artifacts/snap-image-only.png", "snapshot_id": "snap-image-only"},
                },
            )
        ],
        artifact_path=str(artifact),
    )

    results = run_steps(
        [
            CanaryStep(
                id="iphone.see_calculator",
                suite="iphone_scenario",
                lane="scenario",
                command="iphone_see",
                requires_visual_evidence=True,
                visual_assert={"expected_visible_text": "Calculator", "expected_image_state": "iphone_calculator"},
            )
        ],
        surface,
    )

    assert results[0].status == "passed"


def test_malformed_png_artifact_state_fails_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "malformed.png"
    artifact.write_bytes(b"\x89PNG\r\n\x1a\n" + (1).to_bytes(4, "big") + b"IHDR" + b"x" + b"\x00\x00\x00\x00")

    assert qa_canary._visual_artifact_states(str(artifact)) == set()


def test_live_cli_requires_operator_ack_for_moving_suites(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    connector_url, server = serve_fake_connector({"desktop_control_start": envelope("desktop_control_start")})
    monkeypatch.setenv("QA_CONNECTOR_TOKEN", "secret-token")
    try:
        exit_code = main(
            [
                "--connector-url",
                connector_url,
                "--token-env",
                "QA_CONNECTOR_TOKEN",
                "--surface",
                "connector",
                "--suite",
                "full_access",
                "--artifact-dir",
                str(tmp_path),
            ]
        )
    finally:
        server.shutdown()

    assert exit_code == 2
    assert "operator acknowledgement" in capsys.readouterr().err


def test_visual_see_requires_snapshot_and_artifact(tmp_path: Path) -> None:
    connector_url, server = serve_fake_connector({"desktop_see": envelope("desktop_see", data={"engine": "peekaboo"})})
    try:
        surface = ConnectorSurface(connector_url=connector_url, token="secret-token", artifact_dir=tmp_path)
        results = run_steps(
            [CanaryStep(id="desktop.see", suite="desktop", command="desktop_see", requires_visual_evidence=True)],
            surface,
        )
    finally:
        server.shutdown()

    assert results[0].status == "failed"
    assert results[0].errors[0]["code"] == "qa_visual_evidence_missing"


def test_cli_runs_readiness_suite_and_writes_reports(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    readiness_commands = [
        "desktop_bridge_status",
        "customer_mac_status",
        "customer_mac_capabilities",
        "desktop_control_status",
        "desktop_bridge_audit_tail",
        "customer_mac_iphone_mirroring_status",
    ]
    connector_url, server = serve_fake_connector({command: envelope(command) for command in readiness_commands})
    monkeypatch.setenv("QA_CONNECTOR_TOKEN", "secret-token")
    try:
        exit_code = main(
            [
                "--connector-url",
                connector_url,
                "--token-env",
                "QA_CONNECTOR_TOKEN",
                "--surface",
                "connector",
                "--suite",
                "readiness",
                "--artifact-dir",
                str(tmp_path),
            ]
        )
    finally:
        server.shutdown()

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["ok"] is True
    assert stdout["summary"] == {"failed": 0, "passed": 6, "skipped": 0, "total": 6}
    assert (tmp_path / "qa-report.json").exists()
    assert (tmp_path / "qa-report.md").exists()
    report = json.loads((tmp_path / "qa-report.json").read_text(encoding="utf-8"))
    assert report["version_under_test"] == "local-dev"


def test_cli_returns_nonzero_when_required_suite_skips(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    readiness_commands = [
        "desktop_bridge_status",
        "customer_mac_status",
        "customer_mac_capabilities",
        "desktop_control_status",
        "desktop_bridge_audit_tail",
    ]
    responses = {command: envelope(command) for command in readiness_commands}
    responses["customer_mac_iphone_mirroring_status"] = envelope(
        "customer_mac_iphone_mirroring_status",
        ok=False,
        errors=[{"code": "iphone_mirroring_not_running", "message": "not running", "guidance": "open iPhone Mirroring"}],
    )
    connector_url, server = serve_fake_connector(responses)
    monkeypatch.setenv("QA_CONNECTOR_TOKEN", "secret-token")
    try:
        exit_code = main(
            [
                "--connector-url",
                connector_url,
                "--token-env",
                "QA_CONNECTOR_TOKEN",
                "--surface",
                "connector",
                "--suite",
                "readiness",
                "--artifact-dir",
                str(tmp_path),
            ]
        )
    finally:
        server.shutdown()

    assert exit_code == 1
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["ok"] is False
    assert stdout["summary"] == {"failed": 0, "passed": 5, "skipped": 1, "total": 6}
