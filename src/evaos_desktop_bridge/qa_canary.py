from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

DEFAULT_RUN_ROOT = Path("/Volumes/LEXAR/Codex/evaos-workbench-qa-runs")
REAL_WORLD_ENV_KEYS = (
    "QA_BUMBLE_TEXT",
    "QA_SMS_CONTACT",
    "QA_SMS_TEXT",
    "QA_SOCIAL_APP",
    "QA_SOCIAL_TEXT",
)
UNAVAILABLE_CODES = (
    "iphone_mirroring_not_running",
    "iphone_mirroring_not_installed",
    "permission_missing",
    "screen_recording_missing",
    "accessibility_missing",
    "app_not_found",
    "window_not_found",
    "artifact_not_found",
    "not_found",
)


@dataclass(frozen=True)
class CanaryStep:
    id: str
    suite: str
    command: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    skip_on_unavailable: bool = False
    expect_error_code: str | None = None
    skip_if_unresolved: bool = False
    env_required: tuple[str, ...] = ()
    requires_visual_evidence: bool = False


@dataclass
class SurfaceResponse:
    payload: dict[str, Any]
    ok: bool
    audit_id: str | None
    engine: str | None
    snapshot_id: str | None
    artifact_path: str | None
    errors: list[dict[str, Any]]
    warnings: list[Any]

    @classmethod
    def from_payload(cls, payload: dict[str, Any], artifact_path: str | None = None) -> "SurfaceResponse":
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
        warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
        return cls(
            payload=payload,
            ok=payload.get("ok") is True,
            audit_id=payload.get("audit_id") if isinstance(payload.get("audit_id"), str) else None,
            engine=_extract_string(data, ("engine", "screenshot.engine", "screenshot.screenshot.engine", "image.engine")),
            snapshot_id=_extract_string(data, ("snapshot_id", "screenshot.snapshot_id", "screenshot.screenshot.snapshot_id", "image.snapshot_id", "screenshot.image.snapshot_id")),
            artifact_path=artifact_path
            or _extract_string(data, ("vm_visual_artifact_path", "screenshot.vm_artifact_path", "screenshot.screenshot.vm_artifact_path", "image.vm_artifact_path")),
            errors=[error for error in errors if isinstance(error, dict)],
            warnings=warnings,
        )


@dataclass
class CanaryResult:
    id: str
    suite: str
    command: str
    params_redacted: dict[str, Any]
    ok: bool
    status: str
    audit_id: str | None
    engine: str | None
    snapshot_id: str | None
    artifact_path: str | None
    duration_ms: int
    errors: list[dict[str, Any]]
    warnings: list[Any]
    payload: dict[str, Any] = field(repr=False, default_factory=dict)

    def to_report_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "suite": self.suite,
            "command": self.command,
            "params_redacted": redact_for_report(self.params_redacted),
            "ok": self.ok,
            "status": self.status,
            "audit_id": self.audit_id,
            "engine": self.engine,
            "snapshot_id": self.snapshot_id,
            "artifact_path": self.artifact_path,
            "duration_ms": self.duration_ms,
            "errors": redact_for_report(self.errors),
            "warnings": redact_for_report(self.warnings),
        }


class CanarySurface(Protocol):
    def run(self, command: str, params: dict[str, Any]) -> SurfaceResponse:
        ...


class ConnectorSurface:
    def __init__(self, *, connector_url: str, token: str, artifact_dir: Path) -> None:
        self.connector_url = connector_url.rstrip("/")
        self.token = token
        self.artifact_dir = artifact_dir

    def run(self, command: str, params: dict[str, Any]) -> SurfaceResponse:
        payload = self._post_json("/v1/commands", {"command": command, "params": params})
        artifact_path = self._materialize_visual_artifact(payload)
        return SurfaceResponse.from_payload(payload, artifact_path=artifact_path)

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.connector_url + path,
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - operator-supplied private connector URL.
                return _loads_json_response(response.read())
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read()
            try:
                return _loads_json_response(body_bytes)
            except ValueError:
                return _error_payload(command=str(body.get("command") or "connector.command"), code="connector_http_error", message=body_bytes.decode("utf-8", errors="replace") or f"HTTP {exc.code}")

    def _materialize_visual_artifact(self, payload: dict[str, Any]) -> str | None:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        artifact_url = _extract_string(data, ("image.artifact_url", "screenshot.artifact_url", "screenshot.screenshot.artifact_url", "screenshot.image.artifact_url"))
        if not artifact_url:
            return None
        endpoint = urllib.parse.urljoin(self.connector_url + "/", artifact_url)
        parsed_endpoint = urllib.parse.urlparse(endpoint)
        parsed_connector = urllib.parse.urlparse(self.connector_url)
        if parsed_endpoint.netloc != parsed_connector.netloc or not parsed_endpoint.path.startswith("/v1/artifacts/"):
            payload.setdefault("warnings", []).append("Connector returned an artifact URL outside the paired connector.")
            return None
        request = urllib.request.Request(endpoint, method="GET", headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - validated same-origin connector artifact URL.
                content = response.read()
        except Exception as exc:  # noqa: BLE001 - report evidence fetch failure without hiding command result.
            payload.setdefault("warnings", []).append(f"Unable to fetch connector artifact: {exc}")
            return None
        snapshot_id = _extract_string(data, ("snapshot_id", "screenshot.snapshot_id", "screenshot.screenshot.snapshot_id", "image.artifact_id")) or Path(parsed_endpoint.path).stem
        output_dir = self.artifact_dir / "evidence"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{_safe_filename(snapshot_id)}.png"
        output_path.write_bytes(content)
        return str(output_path)


class OpenClawSurface:
    def __init__(self, *, connector_url: str, token: str, artifact_dir: Path, repo_root: Path | None = None) -> None:
        self.connector_url = connector_url
        self.token = token
        self.artifact_dir = artifact_dir
        self.repo_root = repo_root or _resolve_repo_root()

    def run(self, command: str, params: dict[str, Any]) -> SurfaceResponse:
        helper = self.repo_root / "openclaw-plugin" / "scripts" / "qa-run-bridge.mjs"
        env = os.environ.copy()
        env.update(
            {
                "EVAOS_DESKTOP_BRIDGE_URL": self.connector_url,
                "EVAOS_DESKTOP_BRIDGE_TOKEN": self.token,
                "EVAOS_DESKTOP_BRIDGE_ARTIFACT_DIR": str(self.artifact_dir),
            }
        )
        params_json = json.dumps(params, separators=(",", ":"))
        completed = subprocess.run(
            ["node", str(helper), command, "-"],
            cwd=self.repo_root,
            env=env,
            input=params_json,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
        )
        payload = _payload_from_completed_process(completed, command)
        return SurfaceResponse.from_payload(payload)


class HermesSurface:
    def __init__(self, *, connector_url: str, token: str, artifact_dir: Path, repo_root: Path | None = None) -> None:
        self.connector_url = connector_url
        self.token = token
        self.artifact_dir = artifact_dir
        self.repo_root = repo_root or _resolve_repo_root()

    def run(self, command: str, params: dict[str, Any]) -> SurfaceResponse:
        env = os.environ.copy()
        env.update(
            {
                "EVAOS_DESKTOP_BRIDGE_URL": self.connector_url,
                "EVAOS_DESKTOP_BRIDGE_TOKEN": self.token,
                "EVAOS_DESKTOP_BRIDGE_ARTIFACT_DIR": str(self.artifact_dir),
            }
        )
        adapter = self.repo_root / "hermes-adapter" / "bin" / "evaos-desktop-bridge-command"
        params_json = json.dumps(params, separators=(",", ":"))
        completed = subprocess.run(
            [str(adapter), command, "-"],
            cwd=self.repo_root,
            env=env,
            input=params_json,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
        )
        payload = _payload_from_completed_process(completed, command)
        return SurfaceResponse.from_payload(payload)


def run_steps(steps: list[CanaryStep], surface: CanarySurface) -> list[CanaryResult]:
    results: list[CanaryResult] = []
    context: dict[str, CanaryResult] = {}
    for step in steps:
        missing_env = [key for key in step.env_required if not os.environ.get(key)]
        if missing_env:
            result = _skipped_result(step, f"Missing local-only QA env: {', '.join(missing_env)}")
            results.append(result)
            context[step.id] = result
            continue
        try:
            params = _resolve_params(step.params, context)
        except _UnresolvedPlaceholder as exc:
            result = _skipped_result(step, str(exc)) if step.skip_if_unresolved else _failed_result(step, str(exc))
            results.append(result)
            context[step.id] = result
            continue
        started = time.monotonic()
        try:
            response = surface.run(step.command, params)
            duration_ms = int((time.monotonic() - started) * 1000)
            status = classify_status(response.payload, skip_on_unavailable=step.skip_on_unavailable, expect_error_code=step.expect_error_code)
            errors = list(response.errors)
            warnings = list(response.warnings)
            if status == "passed" and step.requires_visual_evidence and (not response.snapshot_id or not response.artifact_path):
                status = "failed"
                errors.append(
                    {
                        "code": "qa_visual_evidence_missing",
                        "message": "Visual see command returned ok:true without a snapshot id and materialized screenshot artifact.",
                        "guidance": "Fix screenshot artifact return/materialization before certifying this release.",
                    }
                )
            result = CanaryResult(
                id=step.id,
                suite=step.suite,
                command=step.command,
                params_redacted=params,
                ok=response.ok,
                status=status,
                audit_id=response.audit_id,
                engine=response.engine,
                snapshot_id=response.snapshot_id,
                artifact_path=response.artifact_path,
                duration_ms=duration_ms,
                errors=errors,
                warnings=warnings,
                payload=response.payload,
            )
        except Exception as exc:  # noqa: BLE001 - canary reports failures as data.
            duration_ms = int((time.monotonic() - started) * 1000)
            result = CanaryResult(
                id=step.id,
                suite=step.suite,
                command=step.command,
                params_redacted=params,
                ok=False,
                status="failed",
                audit_id=None,
                engine=None,
                snapshot_id=None,
                artifact_path=None,
                duration_ms=duration_ms,
                errors=[{"code": "qa_step_exception", "message": str(exc), "guidance": "Inspect the QA canary report and connector logs."}],
                warnings=[],
                payload={},
            )
        results.append(result)
        context[step.id] = result
    return results


def classify_status(payload: dict[str, Any], *, skip_on_unavailable: bool = False, expect_error_code: str | None = None) -> str:
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    error_codes = {str(error.get("code") or "") for error in errors if isinstance(error, dict)}
    if expect_error_code:
        return "passed" if payload.get("ok") is not True and expect_error_code in error_codes else "failed"
    if payload.get("ok") is True:
        return "passed"
    if skip_on_unavailable and (error_codes & set(UNAVAILABLE_CODES)):
        return "skipped"
    return "failed"


def build_scenarios(suite: str, *, allow_real_world_actions: bool) -> list[CanaryStep]:
    normalized = "full_access" if suite == "full" else suite
    suites: dict[str, list[CanaryStep]] = {
        "readiness": _readiness_steps(),
        "codex": _codex_steps(),
        "full_access": _full_access_steps(),
        "desktop": _desktop_steps(),
        "iphone": _iphone_steps(),
        "ask_permission": _ask_permission_steps(),
        "kill_switch": _kill_switch_steps(),
        "real_world_optional": _real_world_steps() if allow_real_world_actions else [],
    }
    if normalized == "all":
        ordered = ["readiness", "codex", "full_access", "desktop", "iphone", "ask_permission"]
        if allow_real_world_actions:
            ordered.append("real_world_optional")
        return [step for name in ordered for step in suites[name]]
    if normalized not in suites:
        raise ValueError(f"unknown QA suite: {suite}")
    return suites[normalized]


def write_reports(
    *,
    artifact_dir: Path,
    run_id: str,
    started_at: str,
    version_under_test: str,
    surface: str,
    connector_url: str,
    results: list[CanaryResult],
) -> dict[str, Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summary = _summary(results)
    report = {
        "run_id": run_id,
        "started_at": started_at,
        "version_under_test": version_under_test,
        "surface": surface,
        "connector_url_redacted": redact_connector_url(connector_url),
        "summary": summary,
        "results": [result.to_report_dict() for result in results],
    }
    json_path = artifact_dir / "qa-report.json"
    markdown_path = artifact_dir / "qa-report.md"
    json_path.write_text(json.dumps(redact_for_report(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown_report(redact_for_report(report)), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def redact_for_report(value: Any) -> Any:
    secrets = _secret_values()
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            lowered = str(key).lower()
            if "token" in lowered or "secret" in lowered or lowered in {"authorization", "recipient_context", "text"}:
                redacted[key] = "[redacted]"
            elif lowered.endswith("url") and isinstance(nested, str):
                redacted[key] = redact_connector_url(nested)
            else:
                redacted[key] = redact_for_report(nested)
        return redacted
    if isinstance(value, list):
        return [redact_for_report(item) for item in value]
    if isinstance(value, str):
        redacted_string = value
        for secret in secrets:
            redacted_string = redacted_string.replace(secret, "[redacted]")
        return redacted_string
    return value


def redact_connector_url(raw_url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(raw_url)
    except Exception:
        return raw_url
    host = parsed.hostname or ""
    redacted_host = host
    parts = host.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        redacted_host = f"{parts[0]}.{parts[1]}.x.x"
    netloc = redacted_host
    if parsed.port:
        netloc += f":{parsed.port}"
    return urllib.parse.urlunparse((parsed.scheme, netloc, "", "", "", ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run evaOS Workbench connector QA canaries.")
    parser.add_argument("--connector-url", required=True)
    parser.add_argument("--token-env", default="EVAOS_DESKTOP_BRIDGE_TOKEN")
    parser.add_argument("--surface", choices=("connector", "openclaw", "hermes"), default="connector")
    parser.add_argument("--suite", choices=("readiness", "codex", "desktop", "iphone", "full", "full_access", "ask_permission", "kill_switch", "real_world_optional", "all"), default="readiness")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--allow-real-world-actions", action="store_true")
    parser.add_argument("--allow-skips", action="store_true", help="Exit 0 when required suites contain skipped rows; release certification should not use this.")
    parser.add_argument("--repo-root", type=Path, help="Repository root containing openclaw-plugin/ and hermes-adapter/ for adapter surfaces.")
    parser.add_argument("--version-under-test", default="0.5.0")
    args = parser.parse_args(argv)

    token = os.environ.get(args.token_env)
    if not token:
        parser.error(f"{args.token_env} is required")
    run_id = f"qa-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    artifact_dir = args.artifact_dir or DEFAULT_RUN_ROOT / run_id
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if args.repo_root:
        os.environ["EVAOS_DESKTOP_BRIDGE_QA_REPO_ROOT"] = str(args.repo_root)
    surface = _surface_for_name(args.surface, connector_url=args.connector_url, token=token, artifact_dir=artifact_dir)
    steps = build_scenarios(args.suite, allow_real_world_actions=args.allow_real_world_actions)
    results = run_steps(steps, surface)
    report_paths = write_reports(
        artifact_dir=artifact_dir,
        run_id=run_id,
        started_at=started_at,
        version_under_test=args.version_under_test,
        surface=args.surface,
        connector_url=args.connector_url,
        results=results,
    )
    ok = _run_successful(results, allow_skips=args.allow_skips)
    print(json.dumps({"ok": ok, "run_id": run_id, "artifact_dir": str(artifact_dir), "reports": {key: str(path) for key, path in report_paths.items()}, "summary": _summary(results)}, sort_keys=True))
    return 0 if ok else 1


def _surface_for_name(name: str, *, connector_url: str, token: str, artifact_dir: Path) -> CanarySurface:
    if name == "connector":
        return ConnectorSurface(connector_url=connector_url, token=token, artifact_dir=artifact_dir)
    if name == "openclaw":
        return OpenClawSurface(connector_url=connector_url, token=token, artifact_dir=artifact_dir)
    if name == "hermes":
        return HermesSurface(connector_url=connector_url, token=token, artifact_dir=artifact_dir)
    raise ValueError(f"unknown surface: {name}")


def _readiness_steps() -> list[CanaryStep]:
    return [
        CanaryStep(id="readiness.bridge_status", suite="readiness", command="desktop_bridge_status"),
        CanaryStep(id="readiness.customer_mac_status", suite="readiness", command="customer_mac_status"),
        CanaryStep(id="readiness.customer_mac_capabilities", suite="readiness", command="customer_mac_capabilities"),
        CanaryStep(id="readiness.control_status", suite="readiness", command="desktop_control_status"),
        CanaryStep(id="readiness.audit_tail", suite="readiness", command="desktop_bridge_audit_tail", params={"limit": 20}),
        CanaryStep(id="readiness.iphone_status", suite="readiness", command="customer_mac_iphone_mirroring_status", skip_on_unavailable=True),
    ]


def _codex_steps() -> list[CanaryStep]:
    return [
        CanaryStep(id="codex.frontmost", suite="codex", command="desktop_bridge_codex_frontmost", skip_on_unavailable=True),
        CanaryStep(id="codex.windows", suite="codex", command="desktop_bridge_codex_windows", skip_on_unavailable=True),
        CanaryStep(id="codex.threads", suite="codex", command="desktop_bridge_codex_threads", params={"max_items": 20}, skip_on_unavailable=True),
        CanaryStep(id="codex.app_server_status", suite="codex", command="desktop_bridge_codex_app_server_status", skip_on_unavailable=True),
        CanaryStep(id="codex.remote_control_status", suite="codex", command="desktop_bridge_codex_app_server_remote_control_status", skip_on_unavailable=True),
    ]


def _full_access_steps() -> list[CanaryStep]:
    return [
        CanaryStep(id="full.start", suite="full_access", command="desktop_control_start", params={"mode": "full-access", "agent_label": "evaOS QA Canary"}),
        CanaryStep(id="full.status", suite="full_access", command="desktop_control_status"),
        CanaryStep(id="full.scroll_no_approval", suite="full_access", command="desktop_scroll", params={"direction": "down", "amount": 200, "dry_run": False}),
        CanaryStep(id="full.hotkey_no_approval", suite="full_access", command="desktop_hotkey", params={"keys": "escape", "dry_run": False}),
    ]


def _desktop_steps() -> list[CanaryStep]:
    return [
        CanaryStep(id="desktop.see", suite="desktop", command="desktop_see", params={"max_chars": 4000, "max_nodes": 200}, requires_visual_evidence=True),
        CanaryStep(
            id="desktop.click_element",
            suite="desktop",
            command="desktop_click",
            params={"snapshot_id": "${desktop.see.snapshot_id}", "element_id": "${desktop.see.first_element_id}", "dry_run": False},
            skip_on_unavailable=True,
        ),
        CanaryStep(id="desktop.click_coordinates", suite="desktop", command="desktop_click", params={"snapshot_id": "${desktop.see.snapshot_id}", "x": 100, "y": 100, "dry_run": False}),
        CanaryStep(id="desktop.type", suite="desktop", command="desktop_type", params={"text": "evaOS QA smoke", "dry_run": False}),
        CanaryStep(id="desktop.scroll", suite="desktop", command="desktop_scroll", params={"direction": "down", "amount": 400, "dry_run": False}),
        CanaryStep(id="desktop.drag", suite="desktop", command="desktop_drag", params={"from_x": 180, "from_y": 180, "to_x": 260, "to_y": 260, "dry_run": False}),
        CanaryStep(id="desktop.hotkey", suite="desktop", command="desktop_hotkey", params={"keys": "escape", "dry_run": False}),
        CanaryStep(id="desktop.focus_app", suite="desktop", command="desktop_focus_app", params={"app_name": "Finder", "dry_run": False}),
        CanaryStep(id="desktop.window_focus", suite="desktop", command="desktop_window", params={"action": "focus", "dry_run": False}),
        CanaryStep(id="desktop.menu_probe", suite="desktop", command="desktop_menu", params={"menu_path": "Window", "dry_run": True}, skip_on_unavailable=True),
        CanaryStep(id="desktop.browser_open", suite="desktop", command="desktop_browser_action", params={"action": "open_url", "url": "https://example.com", "dry_run": False}),
    ]


def _iphone_steps() -> list[CanaryStep]:
    return [
        CanaryStep(id="iphone.focus", suite="iphone", command="customer_mac_iphone_mirroring_focus", params={"dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.see", suite="iphone", command="iphone_see", params={"max_chars": 4000, "max_nodes": 200}, skip_on_unavailable=True, requires_visual_evidence=True),
        CanaryStep(id="iphone.tap_coordinates", suite="iphone", command="iphone_tap", params={"snapshot_id": "${iphone.see.snapshot_id}", "x": 140, "y": 140, "dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.swipe_left", suite="iphone", command="iphone_swipe", params={"direction": "left", "dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.swipe_right", suite="iphone", command="iphone_swipe", params={"direction": "right", "dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.type", suite="iphone", command="iphone_type", params={"text": "evaOS QA", "dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.home", suite="iphone", command="customer_mac_iphone_mirroring_home", params={"dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.app_switcher", suite="iphone", command="customer_mac_iphone_mirroring_app_switcher", params={"dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.spotlight", suite="iphone", command="customer_mac_iphone_mirroring_spotlight", params={"dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.open_calculator", suite="iphone", command="customer_mac_iphone_mirroring_open_app", params={"app_name": "Calculator", "dry_run": False}, skip_on_unavailable=True),
        CanaryStep(id="iphone.calculator_smoke", suite="iphone", command="iphone_type", params={"text": "1+1+1=", "dry_run": False}, skip_on_unavailable=True),
    ]


def _ask_permission_steps() -> list[CanaryStep]:
    return [
        CanaryStep(id="ask.start", suite="ask_permission", command="desktop_control_start", params={"mode": "ask-permission", "agent_label": "evaOS QA Canary"}),
        CanaryStep(id="ask.high_impact_denied", suite="ask_permission", command="desktop_type", params={"text": "evaOS QA ask permission", "dry_run": False}, expect_error_code="approval_audit_required"),
        CanaryStep(id="ask.high_impact_dry_run", suite="ask_permission", command="desktop_type", params={"text": "evaOS QA ask permission", "dry_run": True}),
        CanaryStep(id="ask.high_impact_approved", suite="ask_permission", command="desktop_type", params={"text": "evaOS QA ask permission", "dry_run": False, "approval_audit_id": "${ask.high_impact_dry_run.audit_id}"}, skip_if_unresolved=True),
    ]


def _kill_switch_steps() -> list[CanaryStep]:
    return [
        CanaryStep(id="kill.activate", suite="kill_switch", command="desktop_kill_switch"),
        CanaryStep(id="kill.status", suite="kill_switch", command="desktop_control_status"),
        CanaryStep(id="kill.blocks_control", suite="kill_switch", command="desktop_scroll", params={"direction": "down", "amount": 100, "dry_run": False}, expect_error_code="control_kill_switch_active"),
    ]


def _real_world_steps() -> list[CanaryStep]:
    return [
        CanaryStep(id="real.bumble_open", suite="real_world_optional", command="customer_mac_iphone_mirroring_open_app", params={"app_name": "Bumble", "dry_run": False}, env_required=("QA_BUMBLE_TEXT",), skip_on_unavailable=True),
        CanaryStep(id="real.bumble_swipe_left", suite="real_world_optional", command="iphone_swipe", params={"direction": "left", "dry_run": False}, env_required=("QA_BUMBLE_TEXT",), skip_on_unavailable=True),
        CanaryStep(id="real.bumble_text", suite="real_world_optional", command="iphone_type", params={"text": "${env.QA_BUMBLE_TEXT}", "dry_run": False}, env_required=("QA_BUMBLE_TEXT",), skip_on_unavailable=True),
        CanaryStep(id="real.sms_text", suite="real_world_optional", command="iphone_type", params={"text": "${env.QA_SMS_TEXT}", "dry_run": False}, env_required=("QA_SMS_CONTACT", "QA_SMS_TEXT"), skip_on_unavailable=True),
        CanaryStep(id="real.social_open", suite="real_world_optional", command="customer_mac_iphone_mirroring_open_app", params={"app_name": "${env.QA_SOCIAL_APP}", "dry_run": False}, env_required=("QA_SOCIAL_APP", "QA_SOCIAL_TEXT"), skip_on_unavailable=True),
        CanaryStep(id="real.social_text", suite="real_world_optional", command="iphone_type", params={"text": "${env.QA_SOCIAL_TEXT}", "dry_run": False}, env_required=("QA_SOCIAL_APP", "QA_SOCIAL_TEXT"), skip_on_unavailable=True),
    ]


def _resolve_params(params: dict[str, Any], context: dict[str, CanaryResult]) -> dict[str, Any]:
    return {key: _resolve_value(value, context) for key, value in params.items()}


def _resolve_value(value: Any, context: dict[str, CanaryResult]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_value(nested, context) for key, nested in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, context) for item in value]
    if not isinstance(value, str) or not value.startswith("${") or not value.endswith("}"):
        return value
    expression = value[2:-1]
    if expression.startswith("env."):
        env_key = expression.removeprefix("env.")
        env_value = os.environ.get(env_key)
        if not env_value:
            raise _UnresolvedPlaceholder(f"{env_key} is not set")
        return env_value
    if expression.endswith(".audit_id"):
        step_id = expression.removesuffix(".audit_id")
        result = context.get(step_id)
        if not result or not result.audit_id:
            raise _UnresolvedPlaceholder(f"{step_id} did not produce an audit id")
        return result.audit_id
    if expression.endswith(".snapshot_id"):
        step_id = expression.removesuffix(".snapshot_id")
        result = context.get(step_id)
        if not result or not result.snapshot_id:
            raise _UnresolvedPlaceholder(f"{step_id} did not produce a snapshot id")
        return result.snapshot_id
    if expression.endswith(".first_element_id"):
        step_id = expression.removesuffix(".first_element_id")
        result = context.get(step_id)
        element_id = _find_first_element_id(result.payload if result else {})
        if not element_id:
            raise _UnresolvedPlaceholder(f"{step_id} did not expose an element id")
        return element_id
    raise _UnresolvedPlaceholder(f"unknown QA placeholder: {value}")


def _find_first_element_id(payload: dict[str, Any]) -> str | None:
    candidates: list[Any] = []
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("elements", "items", "nodes"):
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(value)
        screenshot = data.get("screenshot")
        if isinstance(screenshot, dict):
            for key in ("elements", "items", "nodes"):
                value = screenshot.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("element_id", "id"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


class _UnresolvedPlaceholder(ValueError):
    pass


def _skipped_result(step: CanaryStep, message: str) -> CanaryResult:
    return CanaryResult(
        id=step.id,
        suite=step.suite,
        command=step.command,
        params_redacted=step.params,
        ok=False,
        status="skipped",
        audit_id=None,
        engine=None,
        snapshot_id=None,
        artifact_path=None,
        duration_ms=0,
        errors=[],
        warnings=[message],
        payload={},
    )


def _failed_result(step: CanaryStep, message: str) -> CanaryResult:
    return CanaryResult(
        id=step.id,
        suite=step.suite,
        command=step.command,
        params_redacted=step.params,
        ok=False,
        status="failed",
        audit_id=None,
        engine=None,
        snapshot_id=None,
        artifact_path=None,
        duration_ms=0,
        errors=[{"code": "qa_placeholder_unresolved", "message": message, "guidance": "Inspect previous canary steps."}],
        warnings=[],
        payload={},
    )


def _summary(results: list[CanaryResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "passed": sum(1 for result in results if result.status == "passed"),
        "failed": sum(1 for result in results if result.status == "failed"),
        "skipped": sum(1 for result in results if result.status == "skipped"),
    }


def _run_successful(results: list[CanaryResult], *, allow_skips: bool) -> bool:
    if any(result.status == "failed" for result in results):
        return False
    if allow_skips:
        return True
    return not any(result.status == "skipped" and result.suite != "real_world_optional" for result in results)


def _markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# evaOS Workbench QA Canary Report",
        "",
        f"- Run: `{report['run_id']}`",
        f"- Version under test: `{report['version_under_test']}`",
        f"- Surface: `{report['surface']}`",
        f"- Connector: `{report['connector_url_redacted']}`",
        f"- Summary: {summary['passed']} passed, {summary['failed']} failed, {summary['skipped']} skipped, {summary['total']} total",
        "",
        "| Status | Suite | Step | Command | Audit | Engine | Snapshot | Artifact | Duration |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in report["results"]:
        lines.append(
            "| {status} | {suite} | `{id}` | `{command}` | `{audit}` | `{engine}` | `{snapshot}` | `{artifact}` | {duration}ms |".format(
                status=result["status"],
                suite=result["suite"],
                id=result["id"],
                command=result["command"],
                audit=result.get("audit_id") or "",
                engine=result.get("engine") or "",
                snapshot=result.get("snapshot_id") or "",
                artifact=result.get("artifact_path") or "",
                duration=result.get("duration_ms") or 0,
            )
        )
    lines.append("")
    return "\n".join(lines)


def _payload_from_completed_process(completed: subprocess.CompletedProcess[str], command: str) -> dict[str, Any]:
    stdout = (completed.stdout or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    message = (completed.stderr or stdout or f"adapter exited {completed.returncode}").strip()
    return _error_payload(command=command, code="qa_adapter_failed", message=message)


def _loads_json_response(body: bytes) -> dict[str, Any]:
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("response body must be a JSON object")
    return parsed


def _error_payload(*, command: str, code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": "2026-05-02.mvp1",
        "command": command,
        "target": "customer_mac",
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ok": False,
        "data": {},
        "warnings": [],
        "errors": [{"code": code, "message": message, "guidance": "Inspect the QA canary report and connector logs."}],
        "audit_id": "qa-adapter-failed",
    }


def _extract_string(source: dict[str, Any], paths: tuple[str, ...]) -> str | None:
    for path in paths:
        value: Any = source
        for part in path.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value)[:160] or "artifact"


def _resolve_repo_root() -> Path:
    candidates: list[Path] = []
    env_root = os.environ.get("EVAOS_DESKTOP_BRIDGE_QA_REPO_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.append(Path.cwd())
    candidates.extend(Path.cwd().parents)
    module_path = Path(__file__).resolve()
    candidates.extend(module_path.parents)
    for candidate in candidates:
        if (candidate / "openclaw-plugin" / "dist" / "index.js").exists() and (candidate / "hermes-adapter" / "bin" / "evaos-desktop-bridge-command").exists():
            return candidate
    return Path.cwd()


def _secret_values() -> list[str]:
    values = []
    for key, value in os.environ.items():
        lowered = key.lower()
        if value and ("token" in lowered or "secret" in lowered or key in REAL_WORLD_ENV_KEYS):
            values.append(value)
    return values


if __name__ == "__main__":
    raise SystemExit(main())
