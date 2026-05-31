from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

DEFAULT_CANONICAL_PATH = "/Applications/evaOS.app"
DEFAULT_BUNDLE_ID = "com.electricsheephq.EvaDesktop"
DEFAULT_TEAM_ID = "TC6MS3T6NN"
COMPUTER_USE_CLIENT_SUFFIX = "SkyComputerUseClient mcp"
# Optional developer/canary artifact locations. Missing roots are ignored, and
# callers can override them with --canary-artifact-root or
# EVAOS_CANARY_ARTIFACT_ROOTS.
DEFAULT_ARTIFACT_ROOTS = (
    "/Volumes/LEXAR/Codex/artifacts",
    "/Volumes/LEXAR/Codex/evaos-provider-auth-96-canary",
)
CODEX_MCP_SURFACE = "codex-mcp"
BRIDGE_PEEKABOO_SURFACE = "bridge-peekaboo"
CONTROL_SURFACES = (CODEX_MCP_SURFACE, BRIDGE_PEEKABOO_SURFACE)


@dataclass(frozen=True)
class AppBundle:
    path: str
    bundle_id: str | None = None
    version: str | None = None
    build: str | None = None
    team_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "bundle_id": self.bundle_id,
            "version": self.version,
            "build": self.build,
            "team_id": self.team_id,
        }


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    command: str
    path: str | None = None
    kind: str = "other"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "command": self.command,
            "path": self.path,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class WorkbenchInventory:
    registered_paths: tuple[str, ...] = ()
    app_bundles: tuple[AppBundle, ...] = ()
    processes: tuple[ProcessInfo, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "registered_paths": list(self.registered_paths),
            "app_bundles": [bundle.to_dict() for bundle in self.app_bundles],
            "processes": [process.to_dict() for process in self.processes],
        }


@dataclass(frozen=True)
class PreCanaryCheck:
    code: str
    status: str
    message: str
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "status": self.status,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class PreCanaryReport:
    ok: bool
    checks: tuple[PreCanaryCheck, ...]
    summary: dict[str, Any] = field(default_factory=dict)
    inventory: WorkbenchInventory = field(default_factory=WorkbenchInventory)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "checks": [check.to_dict() for check in self.checks],
            "inventory": self.inventory.to_dict(),
        }


def evaluate_inventory(
    inventory: WorkbenchInventory,
    *,
    canonical_path: str = DEFAULT_CANONICAL_PATH,
    bundle_id: str = DEFAULT_BUNDLE_ID,
    expected_version: str | None = None,
    expected_build: str | None = None,
    expected_team_id: str | None = DEFAULT_TEAM_ID,
    max_computer_use_helpers: int = 2,
    control_surface: str = CODEX_MCP_SURFACE,
) -> PreCanaryReport:
    checks: list[PreCanaryCheck] = []
    canonical = _bundle_by_path(inventory.app_bundles, canonical_path)
    registered_duplicates = tuple(path for path in inventory.registered_paths if path != canonical_path)
    stale_artifact_bundles = tuple(
        bundle
        for bundle in inventory.app_bundles
        if bundle.path != canonical_path
        and (
            bundle.bundle_id == bundle_id
            or Path(bundle.path).name == "EvaDesktop.app"
        )
    )
    running_workbench = tuple(process for process in inventory.processes if process.kind == "workbench")
    running_duplicates = tuple(process for process in running_workbench if process.path != canonical_path)
    translocated = tuple(process for process in running_workbench if "AppTranslocation" in process.command or (process.path and "AppTranslocation" in process.path))
    computer_use_helpers = tuple(process for process in inventory.processes if process.kind == "computer_use_helper")

    if canonical is None:
        checks.append(_fail("canonical_workbench_missing", "Canonical Workbench app is missing.", canonical_path))
    else:
        checks.append(_pass("canonical_workbench_present", "Canonical Workbench app is present.", _bundle_evidence(canonical)))
        if canonical.bundle_id is None:
            checks.append(_fail("canonical_bundle_id_unverifiable", "Canonical Workbench bundle id could not be verified.", f"expected {bundle_id}, found unknown"))
        elif canonical.bundle_id != bundle_id:
            checks.append(_fail("canonical_bundle_id_mismatch", "Canonical Workbench has the wrong bundle id.", f"expected {bundle_id}, found {canonical.bundle_id}"))
        if expected_version:
            if canonical.version is None:
                checks.append(_fail("canonical_version_unverifiable", "Canonical Workbench version could not be verified.", f"expected {expected_version}, found unknown"))
            elif canonical.version != expected_version:
                checks.append(_fail("canonical_version_mismatch", "Canonical Workbench version does not match the requested canary.", f"expected {expected_version}, found {canonical.version}"))
        if expected_build:
            if canonical.build is None:
                checks.append(_fail("canonical_build_unverifiable", "Canonical Workbench build could not be verified.", f"expected {expected_build}, found unknown"))
            elif canonical.build != expected_build:
                checks.append(_fail("canonical_build_mismatch", "Canonical Workbench build does not match the requested canary.", f"expected {expected_build}, found {canonical.build}"))
        if expected_team_id:
            if canonical.team_id is None:
                checks.append(_fail("canonical_team_id_unverifiable", "Canonical Workbench signing team could not be verified.", f"expected {expected_team_id}, found unknown"))
            elif canonical.team_id != expected_team_id:
                checks.append(_fail("canonical_team_id_mismatch", "Canonical Workbench is signed by an unexpected team.", f"expected {expected_team_id}, found {canonical.team_id}"))

    if registered_duplicates:
        checks.append(
            _fail(
                "duplicate_registered_workbench_app",
                "Duplicate registered Workbench app bundles can make macOS open the wrong build.",
                "\n".join(registered_duplicates),
            )
        )
    else:
        checks.append(_pass("registered_workbench_unique", "Only the canonical Workbench app is registered.", canonical_path))

    if stale_artifact_bundles:
        checks.append(
            _fail(
                "stale_workbench_app_bundle_present",
                "Stale Workbench app bundles can be selected by macOS app-name lookup.",
                "\n".join(_bundle_evidence(bundle) for bundle in stale_artifact_bundles),
            )
        )

    canonical_running = tuple(process for process in running_workbench if process.path == canonical_path)
    if not canonical_running:
        checks.append(_warn("canonical_workbench_not_running", "Canonical Workbench is not running yet.", canonical_path))
    else:
        checks.append(_pass("canonical_workbench_running", "Canonical Workbench is running.", _pid_list(canonical_running)))

    if running_duplicates:
        checks.append(
            _fail(
                "duplicate_running_workbench_app",
                "A non-canonical Workbench app is running and can contaminate GUI evidence.",
                _process_evidence(running_duplicates),
            )
        )
    if translocated:
        checks.append(
            _fail(
                "translocated_workbench_running",
                "A translocated Workbench app is running from a quarantined/download location.",
                _process_evidence(translocated),
            )
        )

    if len(computer_use_helpers) > max_computer_use_helpers and control_surface == BRIDGE_PEEKABOO_SURFACE:
        checks.append(
            _warn(
                "codex_mcp_helper_count_high",
                "Codex Computer Use MCP helpers are above the normal limit; continue only with the bridge/Peekaboo surface and do not rely on mcp__computer_use.",
                f"{len(computer_use_helpers)} helpers running: {_pid_list(computer_use_helpers)}",
            )
        )
    elif len(computer_use_helpers) > max_computer_use_helpers:
        checks.append(
            _fail(
                "stale_computer_use_helpers",
                "Too many Computer Use helper processes are running; restart/cleanup before GUI canary.",
                f"{len(computer_use_helpers)} helpers running: {_pid_list(computer_use_helpers)}",
            )
        )
    else:
        checks.append(
            _pass(
                "computer_use_helper_count_ok",
                "Computer Use helper process count is within the pre-canary limit.",
                f"{len(computer_use_helpers)} helpers running",
            )
        )

    ok = all(check.status != "fail" for check in checks)
    summary = {
        "canonical_path": canonical_path,
        "bundle_id": bundle_id,
        "control_surface": control_surface,
        "registered_count": len(inventory.registered_paths),
        "running_workbench_count": len(running_workbench),
        "computer_use_helper_count": len(computer_use_helpers),
    }
    return PreCanaryReport(ok=ok, checks=tuple(checks), summary=summary, inventory=inventory)


def gather_inventory(
    *,
    canonical_path: str = DEFAULT_CANONICAL_PATH,
    bundle_id: str = DEFAULT_BUNDLE_ID,
    artifact_roots: Sequence[str] | None = None,
) -> WorkbenchInventory:
    registered_paths = tuple(_mdfind_bundle_paths(bundle_id))
    artifact_paths = tuple(_artifact_workbench_bundle_paths(artifact_roots=artifact_roots))
    bundle_paths = _unique_paths((*registered_paths, *artifact_paths, canonical_path))
    app_bundles = tuple(_read_app_bundle(path) for path in bundle_paths if Path(path).exists())
    processes = tuple(_process_inventory())
    return WorkbenchInventory(registered_paths=registered_paths, app_bundles=app_bundles, processes=processes)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-canary guard for evaOS Workbench GUI acceptance runs.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--canonical-path", default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--bundle-id", default=DEFAULT_BUNDLE_ID)
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-build")
    parser.add_argument("--expected-team-id", default=DEFAULT_TEAM_ID)
    parser.add_argument("--max-computer-use-helpers", type=int, default=2)
    parser.add_argument(
        "--control-surface",
        choices=CONTROL_SURFACES,
        default=CODEX_MCP_SURFACE,
        help=(
            "GUI surface being canaried. codex-mcp keeps strict Computer Use helper limits; "
            "bridge-peekaboo allows Codex MCP helper herds as warnings because control uses the bridge/Peekaboo path."
        ),
    )
    parser.add_argument(
        "--canary-artifact-root",
        action="append",
        dest="artifact_roots",
        help="Optional root to scan for stale EvaDesktop.app canary artifacts. Repeatable; overrides EVAOS_CANARY_ARTIFACT_ROOTS/default roots.",
    )
    args = parser.parse_args(argv)

    inventory = gather_inventory(canonical_path=args.canonical_path, bundle_id=args.bundle_id, artifact_roots=args.artifact_roots)
    report = evaluate_inventory(
        inventory,
        canonical_path=args.canonical_path,
        bundle_id=args.bundle_id,
        expected_version=args.expected_version,
        expected_build=args.expected_build,
        expected_team_id=args.expected_team_id,
        max_computer_use_helpers=args.max_computer_use_helpers,
        control_surface=args.control_surface,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report.ok else 2


def _bundle_by_path(bundles: Iterable[AppBundle], path: str) -> AppBundle | None:
    for bundle in bundles:
        if bundle.path == path:
            return bundle
    return None


def _fail(code: str, message: str, evidence: str = "") -> PreCanaryCheck:
    return PreCanaryCheck(code=code, status="fail", message=message, evidence=evidence)


def _pass(code: str, message: str, evidence: str = "") -> PreCanaryCheck:
    return PreCanaryCheck(code=code, status="pass", message=message, evidence=evidence)


def _warn(code: str, message: str, evidence: str = "") -> PreCanaryCheck:
    return PreCanaryCheck(code=code, status="warn", message=message, evidence=evidence)


def _bundle_evidence(bundle: AppBundle) -> str:
    details = [bundle.path]
    if bundle.version or bundle.build:
        details.append(f"version={bundle.version or 'unknown'} build={bundle.build or 'unknown'}")
    if bundle.team_id:
        details.append(f"team={bundle.team_id}")
    return " ".join(details)


def _pid_list(processes: Iterable[ProcessInfo]) -> str:
    return ", ".join(str(process.pid) for process in processes)


def _process_evidence(processes: Iterable[ProcessInfo]) -> str:
    return "\n".join(f"{process.pid} {process.path or process.command}" for process in processes)


def _unique_paths(paths: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return tuple(ordered)


def _run(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0 and not completed.stdout:
        return ""
    return completed.stdout


def _mdfind_bundle_paths(bundle_id: str) -> tuple[str, ...]:
    output = _run(["mdfind", f"kMDItemCFBundleIdentifier == \"{bundle_id}\""])
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def _artifact_workbench_bundle_paths(*, artifact_roots: Sequence[str] | None = None) -> tuple[str, ...]:
    paths: list[str] = []
    roots = tuple(artifact_roots) if artifact_roots is not None else _artifact_roots_from_environment()
    for root in roots:
        if not Path(root).exists():
            continue
        output = _run(["find", root, "-maxdepth", "4", "-type", "d", "-name", "EvaDesktop.app", "-prune", "-print"])
        paths.extend(line.strip() for line in output.splitlines() if line.strip())
    return tuple(paths)


def _artifact_roots_from_environment() -> tuple[str, ...]:
    raw = os.environ.get("EVAOS_CANARY_ARTIFACT_ROOTS")
    if not raw:
        return DEFAULT_ARTIFACT_ROOTS
    return tuple(part.strip() for part in raw.split(os.pathsep) if part.strip())


def _plist_value(app_path: str, key: str) -> str | None:
    output = _run(["/usr/libexec/PlistBuddy", "-c", f"Print :{key}", str(Path(app_path) / "Contents" / "Info.plist")])
    value = output.strip()
    return value or None


def _codesign_team_id(app_path: str) -> str | None:
    try:
        completed = subprocess.run(["codesign", "-dv", app_path], check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    combined = completed.stdout + "\n" + completed.stderr
    match = re.search(r"TeamIdentifier=([A-Z0-9]+)", combined)
    return match.group(1) if match else None


def _read_app_bundle(path: str) -> AppBundle:
    return AppBundle(
        path=path,
        bundle_id=_plist_value(path, "CFBundleIdentifier"),
        version=_plist_value(path, "CFBundleShortVersionString"),
        build=_plist_value(path, "CFBundleVersion"),
        team_id=_codesign_team_id(path),
    )


def _process_inventory() -> tuple[ProcessInfo, ...]:
    output = _run(["ps", "-axo", "pid=,args="])
    processes: list[ProcessInfo] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if "EvaDesktop.app/Contents/MacOS/EvaDesktop" in command or "/evaOS.app/Contents/MacOS/EvaDesktop" in command:
            processes.append(ProcessInfo(pid=pid, command=command, path=_workbench_app_path_from_command(command), kind="workbench"))
        elif _is_computer_use_mcp_helper(command):
            processes.append(ProcessInfo(pid=pid, command=command, kind="computer_use_helper"))
        elif "evaos_desktop_bridge.cli serve" in command or "evaos-desktop-bridge serve" in command:
            processes.append(ProcessInfo(pid=pid, command=command, kind="desktop_bridge"))
    return tuple(processes)


def _is_computer_use_mcp_helper(command: str) -> bool:
    # Avoid false positives from shell commands that mention SkyComputerUseClient
    # while cleaning up or inspecting helpers. Real helpers end with this argv.
    return command.rstrip().endswith(COMPUTER_USE_CLIENT_SUFFIX)


def _workbench_app_path_from_command(command: str) -> str | None:
    marker = ".app/Contents/MacOS/EvaDesktop"
    index = command.find(marker)
    if index == -1:
        return None
    executable_prefix = command[: index + len(".app")]
    start = executable_prefix.rfind(" ")
    return executable_prefix[start + 1 :]


def _print_human_report(report: PreCanaryReport) -> None:
    status = "PASS" if report.ok else "FAIL"
    print(f"evaOS Workbench pre-canary guard: {status}")
    for check in report.checks:
        evidence = f" — {check.evidence}" if check.evidence else ""
        print(f"[{check.status.upper()}] {check.code}: {check.message}{evidence}")


if __name__ == "__main__":
    sys.exit(main())
