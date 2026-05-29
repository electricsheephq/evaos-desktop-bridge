from __future__ import annotations

from pathlib import Path
from typing import Any

from evaos_desktop_bridge.behavior_harness import (
    BehaviorCommandResult,
    Issue130Surface,
    run_issue130_invariants,
    write_issue130_report,
)


class ScriptedIssue130Surface(Issue130Surface):
    def __init__(
        self,
        *,
        mutate_denied: bool = False,
        non_policy_denied: bool = False,
        sensitive_ok: bool = False,
        cursor_warp: bool = False,
        cursor_starts_at_action: bool = False,
        occluded_capture_ok: bool = True,
    ) -> None:
        self.counter = 0
        self.denied_text = ""
        self.mutate_denied = mutate_denied
        self.non_policy_denied = non_policy_denied
        self.sensitive_ok = sensitive_ok
        self.cursor_warp = cursor_warp
        self.cursor_starts_at_action = cursor_starts_at_action
        self.occluded_capture_ok = occluded_capture_ok

    def open_scratch_app(self) -> None:
        return None

    def close_scratch_app(self) -> None:
        return None

    def scratch_state(self) -> dict[str, Any]:
        return {"counter": self.counter, "denied_text": self.denied_text}

    def frontmost_app(self) -> str | None:
        return "Issue130ScratchApp"

    def cursor_position(self) -> dict[str, int] | None:
        if self.cursor_starts_at_action:
            return {"x": 640, "y": 480}
        if self.cursor_warp:
            return {"x": 640, "y": 480}
        return {"x": 12, "y": 34}

    def perform_increment(self) -> BehaviorCommandResult:
        self.counter += 1
        return BehaviorCommandResult(ok=True, data={"action_point": {"x": 640, "y": 480}}, errors=[])

    def perform_denied_text(self) -> BehaviorCommandResult:
        if self.mutate_denied:
            self.denied_text = "ISSUE130_DENIED_MUTATION"
        code = "runtime_failure" if self.non_policy_denied else "approval_audit_required"
        return BehaviorCommandResult(
            ok=False,
            data={},
            errors=[{"code": code, "message": "dry-run audit required"}],
        )

    def capture_occluded_target(self) -> BehaviorCommandResult:
        return BehaviorCommandResult(
            ok=self.occluded_capture_ok,
            data={
                "target_window": "issue130-target",
                "visible_marker": "ISSUE130_TARGET_PIXELS" if self.occluded_capture_ok else "ISSUE130_OCCLUDER",
            },
            errors=[] if self.occluded_capture_ok else [{"code": "occluded_capture_failed"}],
        )

    def observe_sensitive_surface(self, surface: str) -> BehaviorCommandResult:
        return BehaviorCommandResult(
            ok=self.sensitive_ok,
            data={"surface": surface, "artifact_path": "/tmp/leak.png" if self.sensitive_ok else None},
            errors=[] if self.sensitive_ok else [{"code": "sensitive_app_blocked", "message": "blocked"}],
        )


def test_issue130_invariants_pass_for_clean_surface() -> None:
    report = run_issue130_invariants(ScriptedIssue130Surface())

    assert report.ok is True
    assert report.summary == {"failed": 0, "passed": 6, "skipped": 0, "total": 6}
    assert {check.id for check in report.checks} == {
        "intended_effect",
        "frontmost_unchanged",
        "cursor_not_warped",
        "occluded_capture_target_pixels",
        "policy_denied_zero_effect",
        "sensitive_denylist_all_observation_paths",
    }


def test_issue130_invariants_catch_denied_mutation() -> None:
    report = run_issue130_invariants(ScriptedIssue130Surface(mutate_denied=True))

    failed = {check.id: check for check in report.checks if check.status == "failed"}
    assert report.ok is False
    assert "policy_denied_zero_effect" in failed
    assert failed["policy_denied_zero_effect"].errors[0]["code"] == "issue130_denied_mutated_state"


def test_issue130_invariants_require_policy_denial_reason() -> None:
    report = run_issue130_invariants(ScriptedIssue130Surface(non_policy_denied=True))

    failed = {check.id: check for check in report.checks if check.status == "failed"}
    assert report.ok is False
    assert "policy_denied_zero_effect" in failed
    assert failed["policy_denied_zero_effect"].errors[0]["code"] == "issue130_denied_reason_unverified"


def test_issue130_cursor_check_allows_starting_at_action_point() -> None:
    report = run_issue130_invariants(ScriptedIssue130Surface(cursor_starts_at_action=True))

    statuses = {check.id: check.status for check in report.checks}
    assert report.ok is True
    assert statuses.get("cursor_not_warped") == "passed"


def test_issue130_invariants_catch_sensitive_observation_leak() -> None:
    report = run_issue130_invariants(ScriptedIssue130Surface(sensitive_ok=True))

    failed = {check.id: check for check in report.checks if check.status == "failed"}
    assert report.ok is False
    assert "sensitive_denylist_all_observation_paths" in failed
    assert failed["sensitive_denylist_all_observation_paths"].errors[0]["code"] == "issue130_sensitive_surface_not_blocked"


def test_issue130_report_writes_json_and_markdown(tmp_path: Path) -> None:
    report = run_issue130_invariants(ScriptedIssue130Surface())
    paths = write_issue130_report(report, artifact_dir=tmp_path)

    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert "policy_denied_zero_effect" in paths["markdown"].read_text(encoding="utf-8")
