from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from evaos_desktop_bridge.qa_canary import (
    CanaryStep,
    ConnectorSurface,
    HermesSurface,
    OpenClawSurface,
    build_scenarios,
    classify_status,
    main,
    redact_for_report,
    run_steps,
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


def test_connector_surface_runs_fake_command_and_materializes_artifact(tmp_path: Path) -> None:
    connector_url, server = serve_fake_connector(
        {
            "desktop_see": envelope(
                "desktop_see",
                data={
                    "engine": "peekaboo",
                    "snapshot_id": "snap-test",
                    "screenshot": {
                        "artifact_url": "/v1/artifacts/snap-test.png",
                        "snapshot_id": "snap-test",
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
        version_under_test="0.4.11",
        surface="connector",
        connector_url="http://100.64.10.12:8765",
        results=[],
    )
    assert report_paths["json"].exists()
    assert report_paths["markdown"].exists()
    assert "100.64.10.12" not in report_paths["markdown"].read_text(encoding="utf-8")
    assert "http://100.64." in report_paths["markdown"].read_text(encoding="utf-8")


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


def test_scenario_catalog_is_explicit_and_real_world_config_is_local_only() -> None:
    all_steps = build_scenarios("all", allow_real_world_actions=False)
    suites = {step.suite for step in all_steps}

    assert {"readiness", "codex", "desktop", "iphone", "full_access", "ask_permission"}.issubset(suites)
    assert "kill_switch" not in suites
    assert "real_world_optional" not in suites
    assert all(step.id and step.command for step in all_steps)
    assert classify_status(envelope("desktop_see")) == "passed"
    assert classify_status(envelope("iphone_see", ok=False, errors=[{"code": "not_found", "message": "missing", "guidance": "test"}]), skip_on_unavailable=True) == "skipped"

    real_world_steps = build_scenarios("real_world_optional", allow_real_world_actions=True)
    assert {step.suite for step in real_world_steps} == {"real_world_optional"}
    serialized = json.dumps([step.params for step in real_world_steps])
    assert "David" not in serialized
    assert "Ze Barrow" not in serialized
    assert "Johnny" not in serialized


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
                "--version-under-test",
                "0.4.11",
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
