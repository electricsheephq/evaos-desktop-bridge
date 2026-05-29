from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


DEFAULT_ARTIFACT_ROOT = Path("/Volumes/LEXAR/Codex/evaos-desktop-bridge-issue130-runs")
SCRATCH_APP_TITLE = "Issue130ScratchApp"
SCRATCH_APP_PACKAGE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "macos" / "Issue130ScratchApp"
TARGET_MARKER = "ISSUE130_TARGET_PIXELS"
OCCLUDER_MARKER = "ISSUE130_OCCLUDER"
DENIED_TEXT = "ISSUE130_DENIED_MUTATION"
SENSITIVE_OBSERVATION_SURFACES = ("desktop_see", "snapshot", "ax_tree")


@dataclass(frozen=True)
class BehaviorCommandResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)
    audit_id: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class BehaviorCheck:
    id: str
    description: str
    status: str
    evidence: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class BehaviorReport:
    run_id: str
    started_at: str
    suite: str
    ok: bool
    summary: dict[str, int]
    checks: list[BehaviorCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "suite": self.suite,
            "ok": self.ok,
            "summary": self.summary,
            "checks": [asdict(check) for check in self.checks],
        }


class Issue130Surface(Protocol):
    def open_scratch_app(self) -> None:
        ...

    def close_scratch_app(self) -> None:
        ...

    def scratch_state(self) -> dict[str, Any]:
        ...

    def frontmost_app(self) -> str | None:
        ...

    def cursor_position(self) -> dict[str, int] | None:
        ...

    def perform_increment(self) -> BehaviorCommandResult:
        ...

    def perform_denied_text(self) -> BehaviorCommandResult:
        ...

    def capture_occluded_target(self) -> BehaviorCommandResult:
        ...

    def observe_sensitive_surface(self, surface: str) -> BehaviorCommandResult:
        ...


def run_issue130_invariants(surface: Issue130Surface, *, run_id: str | None = None) -> BehaviorReport:
    started_at = _timestamp()
    checks: list[BehaviorCheck] = []
    run_id = run_id or f"issue130-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    try:
        surface.open_scratch_app()
        before_state = _safe_state(surface)
        before_frontmost = _safe_frontmost(surface)
        before_cursor = _safe_cursor(surface)
        increment = surface.perform_increment()
        after_state = _safe_state(surface)
        after_frontmost = _safe_frontmost(surface)
        after_cursor = _safe_cursor(surface)
        checks.append(_check_intended_effect(before_state, after_state, increment))
        checks.append(_check_frontmost_unchanged(before_frontmost, after_frontmost))
        checks.append(_check_cursor_not_warped(before_cursor, after_cursor, increment))
        checks.append(_check_occluded_capture(surface.capture_occluded_target()))
        denied_before = _safe_state(surface)
        denied = surface.perform_denied_text()
        denied_after = _safe_state(surface)
        checks.append(_check_policy_denied_zero_effect(denied_before, denied_after, denied))
        checks.append(_check_sensitive_denylist(surface))
    except Exception as exc:  # noqa: BLE001 - reports setup/runtime failure as harness data.
        checks.append(
            BehaviorCheck(
                id="issue130_harness_runtime",
                description="The Issue #130 behavior harness must start and finish cleanly.",
                status="failed",
                errors=[_error("issue130_harness_exception", str(exc), "Inspect the local harness report and scratch app logs.")],
            )
        )
    finally:
        try:
            surface.close_scratch_app()
        except Exception:
            pass
    return _report(run_id=run_id, started_at=started_at, checks=checks)


def write_issue130_report(report: BehaviorReport, *, artifact_dir: Path) -> dict[str, Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    json_path = artifact_dir / "issue130-behavior-report.json"
    markdown_path = artifact_dir / "issue130-behavior-report.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


class BridgeCliIssue130Surface:
    def __init__(
        self,
        *,
        artifact_dir: Path,
        state_dir: Path,
        repo_root: Path | None = None,
        python_executable: str = sys.executable,
        sensitive_app: str | None = None,
        cursor_tolerance_px: int = 3,
    ) -> None:
        self.artifact_dir = artifact_dir
        self.state_dir = state_dir
        self.repo_root = repo_root or Path.cwd()
        self.python_executable = python_executable
        self.sensitive_app = sensitive_app
        self.cursor_tolerance_px = cursor_tolerance_px
        self.scratch = ScratchAppProcess(artifact_dir=artifact_dir, package_dir=_scratch_package_path(self.repo_root))

    def open_scratch_app(self) -> None:
        self.scratch.start()
        self._run_cli(["customer-mac", "control", "start", "--mode", "full-access", "--agent-label", "Issue130 Behavior Harness", "--json"])

    def close_scratch_app(self) -> None:
        self._run_cli(["customer-mac", "control", "stop", "--json"], check=False)
        self.scratch.stop()

    def scratch_state(self) -> dict[str, Any]:
        return self.scratch.state()

    def frontmost_app(self) -> str | None:
        payload = self._run_cli(["customer-mac", "status", "--json"], check=False).raw or {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        value = data.get("frontmost_app")
        return value if isinstance(value, str) else None

    def cursor_position(self) -> dict[str, int] | None:
        script = (
            "import json\n"
            "try:\n"
            "    import Quartz\n"
            "    loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))\n"
            "    print(json.dumps({'x': int(loc.x), 'y': int(loc.y)}))\n"
            "except Exception as exc:\n"
            "    print(json.dumps({'error': str(exc)}))\n"
        )
        completed = subprocess.run([self.python_executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
        try:
            payload = json.loads(completed.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return None
        if isinstance(payload.get("x"), int) and isinstance(payload.get("y"), int):
            return {"x": payload["x"], "y": payload["y"]}
        return None

    def perform_increment(self) -> BehaviorCommandResult:
        self.scratch.hide_occluder()
        self._activate_scratch()
        return self._run_cli(["customer-mac", "desktop", "click", "--target-label", "Issue130 Increment", "--json"])

    def perform_denied_text(self) -> BehaviorCommandResult:
        self._activate_scratch()
        self._run_cli(["customer-mac", "control", "stop", "--json"], check=False)
        return self._run_cli(["customer-mac", "desktop", "type", "--text", DENIED_TEXT, "--json"], check=False)

    def capture_occluded_target(self) -> BehaviorCommandResult:
        self.scratch.show_occluder()
        self._activate_scratch()
        result = self._run_cli(["customer-mac", "desktop", "see", "--json", "--max-chars", "4000", "--max-nodes", "200"], check=False)
        text = _visible_text(result.data)
        result.data.setdefault("target_window", "issue130-target")
        result.data.setdefault("visible_marker", TARGET_MARKER if TARGET_MARKER in text else text[:200])
        return result

    def observe_sensitive_surface(self, surface: str) -> BehaviorCommandResult:
        if not self.sensitive_app:
            return BehaviorCommandResult(
                ok=False,
                data={"surface": surface},
                errors=[_error("issue130_sensitive_probe_not_configured", "No sensitive app was configured for the live denylist probe.", "Pass --sensitive-app 'System Settings' or another safe-to-open denylisted app for local acceptance.")],
            )
        self._activate_app(self.sensitive_app)
        command = {
            "desktop_see": ["customer-mac", "desktop", "see", "--json"],
            "snapshot": ["customer-mac", "snapshot", "--json"],
            "ax_tree": ["customer-mac", "ax-tree", "--json"],
        }[surface]
        return self._run_cli(command, check=False)

    def _activate_scratch(self) -> None:
        self._activate_app(SCRATCH_APP_TITLE)

    def _activate_app(self, app_name: str) -> None:
        subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if self.frontmost_app() == app_name:
                return
            time.sleep(0.15)

    def _run_cli(self, argv: list[str], *, check: bool = True) -> BehaviorCommandResult:
        env = os.environ.copy()
        env["EVAOS_DESKTOP_BRIDGE_STATE_DIR"] = str(self.state_dir)
        src_path = str(self.repo_root / "src")
        env["PYTHONPATH"] = src_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        completed = subprocess.run(
            [self.python_executable, "-m", "evaos_desktop_bridge.cli", *argv],
            cwd=self.repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=75,
            check=False,
        )
        try:
            payload = json.loads(completed.stdout.strip() or "{}")
        except json.JSONDecodeError:
            payload = {
                "ok": False,
                "data": {},
                "warnings": [],
                "errors": [_error("issue130_cli_non_json", completed.stderr or completed.stdout or "bridge command returned non-JSON", "Inspect the harness command output.")],
            }
        if check and payload.get("ok") is not True:
            raise RuntimeError(f"bridge command failed: {' '.join(argv)}: {payload.get('errors')}")
        return _command_result(payload)


class ScratchAppProcess:
    def __init__(self, *, artifact_dir: Path, package_dir: Path) -> None:
        self.artifact_dir = artifact_dir
        self.package_dir = package_dir
        self.state_path = artifact_dir / "scratch-state.json"
        self.ready_path = artifact_dir / "scratch-ready.json"
        self.command_path = artifact_dir / "scratch-command.json"
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        for path in (self.state_path, self.ready_path, self.command_path):
            path.unlink(missing_ok=True)
        if not self.package_dir.exists():
            raise RuntimeError(f"Issue130 scratch app package not found: {self.package_dir}")
        self.process = subprocess.Popen(
            ["swift", "run", "Issue130ScratchApp", "--state", str(self.state_path), "--ready", str(self.ready_path), "--command", str(self.command_path)],
            cwd=self.package_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"Issue130 scratch app exited early with {self.process.returncode}.")
            if self.ready_path.exists() and self.state_path.exists():
                return
            time.sleep(0.2)
        raise RuntimeError("Issue130 scratch app did not become ready before timeout.")

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None

    def state(self) -> dict[str, Any]:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(0.1)
        raise RuntimeError("Issue130 scratch app state file is unavailable.")

    def show_occluder(self) -> None:
        self._write_command("show_occluder")

    def hide_occluder(self) -> None:
        self._write_command("hide_occluder")

    def _write_command(self, command: str) -> None:
        self.command_path.write_text(json.dumps({"command": command, "nonce": uuid.uuid4().hex}), encoding="utf-8")
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            state = self.state()
            if bool(state.get("occluder_visible")) == (command == "show_occluder"):
                return
            time.sleep(0.1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run evaOS issue #130 behavior/invariant harness.")
    parser.add_argument("--suite", choices=("issue130",), default="issue130")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--sensitive-app", default=None, help="Optional denylisted app to focus for live sensitive-observation probes, for example System Settings.")
    parser.add_argument("--operator-ack-live-control", action="store_true", help="Required because this harness opens a scratch app and may click/type through the bridge.")
    args = parser.parse_args(argv)
    if not args.operator_ack_live_control:
        print("Refusing to run issue #130 live behavior harness without --operator-ack-live-control.", file=sys.stderr)
        return 2
    run_root = args.artifact_dir or DEFAULT_ARTIFACT_ROOT / f"issue130-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    state_dir = args.state_dir or run_root / "state"
    surface = BridgeCliIssue130Surface(artifact_dir=run_root, state_dir=state_dir, repo_root=args.repo_root, sensitive_app=args.sensitive_app)
    report = run_issue130_invariants(surface)
    paths = write_issue130_report(report, artifact_dir=run_root)
    print(json.dumps({"ok": report.ok, "summary": report.summary, "artifact_dir": str(run_root), "reports": {key: str(path) for key, path in paths.items()}}, sort_keys=True))
    return 0 if report.ok else 1


def _check_intended_effect(before: dict[str, Any], after: dict[str, Any], command: BehaviorCommandResult) -> BehaviorCheck:
    before_counter = _int_value(before.get("counter"))
    after_counter = _int_value(after.get("counter"))
    passed = command.ok and before_counter is not None and after_counter == before_counter + 1
    return _check(
        "intended_effect",
        "A live scratch-app action must produce the intended effect.",
        passed,
        evidence={"before_counter": before_counter, "after_counter": after_counter, "command_ok": command.ok, "audit_id": command.audit_id},
        errors=[] if passed else [_error("issue130_intended_effect_missing", "The live action did not increment the scratch counter exactly once.", "Inspect target resolution and actuation behavior.")],
        warnings=command.warnings,
    )


def _check_frontmost_unchanged(before: str | None, after: str | None) -> BehaviorCheck:
    passed = bool(before) and before == after
    return _check(
        "frontmost_unchanged",
        "A live scratch-app action must not steal focus away from the target app.",
        passed,
        evidence={"before_frontmost": before, "after_frontmost": after},
        errors=[] if passed else [_error("issue130_frontmost_changed", "The frontmost app changed during the live action.", "Use pid/window-targeted actuation that preserves focus.")],
    )


def _check_cursor_not_warped(before: dict[str, int] | None, after: dict[str, int] | None, command: BehaviorCommandResult) -> BehaviorCheck:
    action_point = command.data.get("action_point") if isinstance(command.data.get("action_point"), dict) else command.data.get("point")
    distance = _point_distance(before, after)
    warped_to_action = isinstance(action_point, dict) and after == {"x": action_point.get("x"), "y": action_point.get("y")}
    passed = before is not None and after is not None and distance is not None and distance <= 3 and not warped_to_action
    return _check(
        "cursor_not_warped",
        "A live scratch-app action must not move the user's cursor to the action point.",
        passed,
        evidence={"before_cursor": before, "after_cursor": after, "distance_px": distance, "action_point": action_point},
        errors=[] if passed else [_error("issue130_cursor_warped", "The cursor moved during actuation or landed on the action point.", "Prefer AX/pid-targeted actuation over global CGHID mouse warping.")],
    )


def _check_occluded_capture(command: BehaviorCommandResult) -> BehaviorCheck:
    marker = str(command.data.get("visible_marker") or "")
    passed = command.ok and TARGET_MARKER in marker and OCCLUDER_MARKER not in marker
    return _check(
        "occluded_capture_target_pixels",
        "Occluded capture must return the target window's pixels, not the covering window.",
        passed,
        evidence={"command_ok": command.ok, "target_window": command.data.get("target_window"), "visible_marker": marker[:240], "audit_id": command.audit_id},
        errors=[] if passed else [_error("issue130_occluded_target_pixels_missing", "The occluded capture did not expose the target-window marker.", "Implement or route through a target-window capture path before certifying background control.")],
        warnings=command.warnings,
    )


def _check_policy_denied_zero_effect(before: dict[str, Any], after: dict[str, Any], command: BehaviorCommandResult) -> BehaviorCheck:
    unchanged = before == after
    denied = command.ok is False
    passed = unchanged and denied
    errors: list[dict[str, Any]] = []
    if not denied:
        errors.append(_error("issue130_denied_command_succeeded", "A policy-denied live command returned ok:true.", "Live guarded commands must fail closed without approval/control."))
    if not unchanged:
        errors.append(_error("issue130_denied_mutated_state", "A policy-denied live command changed scratch-app state.", "Denied operations must have zero effect."))
    return _check(
        "policy_denied_zero_effect",
        "A policy-denied operation must have zero effect on scratch-app state.",
        passed,
        evidence={"before_state": before, "after_state": after, "command_ok": command.ok, "error_codes": _error_codes(command.errors)},
        errors=errors,
        warnings=command.warnings,
    )


def _check_sensitive_denylist(surface: Issue130Surface) -> BehaviorCheck:
    observations = {name: surface.observe_sensitive_surface(name) for name in SENSITIVE_OBSERVATION_SURFACES}
    leaks: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}
    for name, result in observations.items():
        codes = _error_codes(result.errors)
        evidence[name] = {"ok": result.ok, "error_codes": codes, "audit_id": result.audit_id}
        artifact = result.data.get("artifact_path") or result.data.get("screenshot_path") or result.data.get("screenshot")
        if result.ok or "sensitive_app_blocked" not in codes or artifact:
            leaks.append(_error("issue130_sensitive_surface_not_blocked", f"{name} did not fail closed with sensitive_app_blocked.", "Keep every observation path behind the shared sensitive-app denylist."))
    return _check(
        "sensitive_denylist_all_observation_paths",
        "The sensitive-app denylist must hold for desktop see, snapshot, and AX tree observation paths.",
        not leaks,
        evidence=evidence,
        errors=leaks,
    )


def _report(*, run_id: str, started_at: str, checks: list[BehaviorCheck]) -> BehaviorReport:
    summary = {
        "total": len(checks),
        "passed": sum(1 for check in checks if check.status == "passed"),
        "failed": sum(1 for check in checks if check.status == "failed"),
        "skipped": sum(1 for check in checks if check.status == "skipped"),
    }
    return BehaviorReport(run_id=run_id, started_at=started_at, suite="issue130", ok=summary["failed"] == 0 and summary["skipped"] == 0, summary=summary, checks=checks)


def _check(id: str, description: str, passed: bool, *, evidence: dict[str, Any], errors: list[dict[str, Any]], warnings: list[Any] | None = None) -> BehaviorCheck:
    return BehaviorCheck(id=id, description=description, status="passed" if passed else "failed", evidence=evidence, errors=errors, warnings=warnings or [])


def _command_result(payload: dict[str, Any]) -> BehaviorCommandResult:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    return BehaviorCommandResult(ok=payload.get("ok") is True, data=data, errors=[error for error in errors if isinstance(error, dict)], warnings=warnings, audit_id=payload.get("audit_id") if isinstance(payload.get("audit_id"), str) else None, raw=payload)


def _safe_state(surface: Issue130Surface) -> dict[str, Any]:
    state = surface.scratch_state()
    return state if isinstance(state, dict) else {}


def _safe_frontmost(surface: Issue130Surface) -> str | None:
    value = surface.frontmost_app()
    return value if isinstance(value, str) and value.strip() else None


def _safe_cursor(surface: Issue130Surface) -> dict[str, int] | None:
    value = surface.cursor_position()
    if isinstance(value, dict) and isinstance(value.get("x"), int) and isinstance(value.get("y"), int):
        return {"x": value["x"], "y": value["y"]}
    return None


def _point_distance(before: dict[str, int] | None, after: dict[str, int] | None) -> float | None:
    if before is None or after is None:
        return None
    return math.hypot(after["x"] - before["x"], after["y"] - before["y"])


def _int_value(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _error_codes(errors: list[dict[str, Any]]) -> list[str]:
    return [str(error.get("code")) for error in errors if isinstance(error, dict) and error.get("code")]


def _error(code: str, message: str, guidance: str) -> dict[str, str]:
    return {"code": code, "message": message, "guidance": guidance}


def _visible_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for key in ("label", "title", "text", "value", "name", "description", "window_title", "frontmost_app"):
                nested = value.get(key)
                if isinstance(nested, str):
                    chunks.append(nested)
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    collect(nested)

    collect(data)
    return " ".join(chunks)


def _markdown_report(report: BehaviorReport) -> str:
    lines = [
        "# Issue #130 Behavior Harness Report",
        "",
        f"- Run: `{report.run_id}`",
        f"- Started: `{report.started_at}`",
        f"- Suite: `{report.suite}`",
        f"- OK: `{str(report.ok).lower()}`",
        f"- Summary: {report.summary['passed']} passed, {report.summary['failed']} failed, {report.summary['skipped']} skipped, {report.summary['total']} total",
        "",
        "| Status | Check | Description |",
        "| --- | --- | --- |",
    ]
    for check in report.checks:
        lines.append(f"| {check.status} | `{check.id}` | {check.description} |")
    lines.append("")
    return "\n".join(lines)


def _scratch_package_path(repo_root: Path) -> Path:
    candidate = repo_root / "tests" / "fixtures" / "macos" / "Issue130ScratchApp"
    if candidate.exists():
        return candidate
    return SCRATCH_APP_PACKAGE


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
