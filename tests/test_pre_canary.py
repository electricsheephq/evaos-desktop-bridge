from __future__ import annotations

from evaos_desktop_bridge.pre_canary import (
    BRIDGE_PEEKABOO_SURFACE,
    DEFAULT_ARTIFACT_ROOTS,
    AppBundle,
    ProcessInfo,
    WorkbenchInventory,
    _is_computer_use_mcp_helper,
    evaluate_inventory,
)


def test_clean_canonical_workbench_inventory_passes() -> None:
    inventory = WorkbenchInventory(
        registered_paths=("/Applications/evaOS.app",),
        app_bundles=(
            AppBundle(
                path="/Applications/evaOS.app",
                bundle_id="com.electricsheephq.EvaDesktop",
                version="0.6.18",
                build="58",
                team_id="TC6MS3T6NN",
            ),
        ),
        processes=(
            ProcessInfo(
                pid=94733,
                command="/Applications/evaOS.app/Contents/MacOS/EvaDesktop",
                path="/Applications/evaOS.app",
                kind="workbench",
            ),
            ProcessInfo(
                pid=68900,
                command="python -m evaos_desktop_bridge.cli serve --host 100.64.0.4 --port 8765",
                kind="desktop_bridge",
            ),
        ),
    )

    report = evaluate_inventory(inventory, expected_version="0.6.18", expected_build="58")

    assert report.ok is True
    assert [check.code for check in report.checks if check.status == "fail"] == []
    assert report.summary["canonical_path"] == "/Applications/evaOS.app"
    assert report.summary["registered_count"] == 1


def test_duplicate_registered_and_translocated_workbench_fail_closed() -> None:
    inventory = WorkbenchInventory(
        registered_paths=(
            "/Applications/evaOS.app",
            "/Users/lume/Downloads/evaOS-Workbench-Beta-0.1.0/EvaDesktop.app",
        ),
        app_bundles=(
            AppBundle(path="/Applications/evaOS.app", bundle_id="com.electricsheephq.EvaDesktop", version="0.6.18", build="58"),
            AppBundle(
                path="/Users/lume/Downloads/evaOS-Workbench-Beta-0.1.0/EvaDesktop.app",
                bundle_id="com.electricsheephq.EvaDesktop",
                version="0.1.0",
                build="1",
            ),
        ),
        processes=(
            ProcessInfo(
                pid=94733,
                command="/Applications/evaOS.app/Contents/MacOS/EvaDesktop",
                path="/Applications/evaOS.app",
                kind="workbench",
            ),
            ProcessInfo(
                pid=19891,
                command="/private/var/folders/.../AppTranslocation/ABC/d/EvaDesktop.app/Contents/MacOS/EvaDesktop",
                path="/private/var/folders/.../AppTranslocation/ABC/d/EvaDesktop.app",
                kind="workbench",
            ),
        ),
    )

    report = evaluate_inventory(inventory)

    assert report.ok is False
    failed = {check.code: check for check in report.checks if check.status == "fail"}
    assert "duplicate_registered_workbench_app" in failed
    assert "duplicate_running_workbench_app" in failed
    assert "translocated_workbench_running" in failed
    assert "/Users/lume/Downloads/evaOS-Workbench-Beta-0.1.0/EvaDesktop.app" in failed["duplicate_registered_workbench_app"].evidence
    assert "19891" in failed["translocated_workbench_running"].evidence


def test_stale_artifact_workbench_bundle_fails_even_when_not_registered() -> None:
    inventory = WorkbenchInventory(
        registered_paths=("/Applications/evaOS.app",),
        app_bundles=(
            AppBundle(path="/Applications/evaOS.app", bundle_id="com.electricsheephq.EvaDesktop", version="0.6.18", build="58"),
            AppBundle(
                path="/Volumes/LEXAR/Codex/artifacts/evaos-workbench-beta-canary-20260521/EvaDesktop.app",
                bundle_id="com.electricsheephq.EvaDesktop",
                version="0.1.0",
                build="1",
            ),
        ),
        processes=(
            ProcessInfo(
                pid=94733,
                command="/Applications/evaOS.app/Contents/MacOS/EvaDesktop",
                path="/Applications/evaOS.app",
                kind="workbench",
            ),
        ),
    )

    report = evaluate_inventory(inventory)

    assert report.ok is False
    failed = {check.code: check for check in report.checks if check.status == "fail"}
    assert "stale_workbench_app_bundle_present" in failed
    assert "0.1.0" in failed["stale_workbench_app_bundle_present"].evidence


def test_default_artifact_roots_cover_legacy_worktree_dist_apps() -> None:
    assert "/Volumes/LEXAR/repos/evaos-desktop-bridge-worktrees" in DEFAULT_ARTIFACT_ROOTS
    assert "/Volumes/LEXAR/repos/worktrees" in DEFAULT_ARTIFACT_ROOTS


def test_stale_artifact_detected_by_name_when_bundle_id_missing() -> None:
    inventory = WorkbenchInventory(
        registered_paths=("/Applications/evaOS.app",),
        app_bundles=(
            AppBundle(path="/Applications/evaOS.app", bundle_id="com.electricsheephq.EvaDesktop", version="0.6.18", build="58"),
            AppBundle(
                path="/Volumes/LEXAR/Codex/artifacts/corrupted/EvaDesktop.app",
                bundle_id=None,
                version="0.1.0",
                build="1",
            ),
        ),
        processes=(),
    )

    report = evaluate_inventory(inventory)

    assert report.ok is False
    failed = {check.code: check for check in report.checks if check.status == "fail"}
    assert "stale_workbench_app_bundle_present" in failed
    assert "corrupted/EvaDesktop.app" in failed["stale_workbench_app_bundle_present"].evidence


def test_expected_version_or_build_mismatch_fails() -> None:
    inventory = WorkbenchInventory(
        registered_paths=("/Applications/evaOS.app",),
        app_bundles=(
            AppBundle(
                path="/Applications/evaOS.app",
                bundle_id="com.electricsheephq.EvaDesktop",
                version="0.6.17",
                build="57",
                team_id="TC6MS3T6NN",
            ),
        ),
        processes=(),
    )

    report = evaluate_inventory(inventory, expected_version="0.6.18", expected_build="58")

    assert report.ok is False
    failed = {check.code: check for check in report.checks if check.status == "fail"}
    assert failed["canonical_version_mismatch"].evidence == "expected 0.6.18, found 0.6.17"
    assert failed["canonical_build_mismatch"].evidence == "expected 58, found 57"


def test_expected_identity_fields_must_be_verifiable() -> None:
    inventory = WorkbenchInventory(
        registered_paths=("/Applications/evaOS.app",),
        app_bundles=(AppBundle(path="/Applications/evaOS.app"),),
        processes=(),
    )

    report = evaluate_inventory(inventory, expected_version="0.6.18", expected_build="58")

    assert report.ok is False
    failed = {check.code: check for check in report.checks if check.status == "fail"}
    assert failed["canonical_bundle_id_unverifiable"].evidence == "expected com.electricsheephq.EvaDesktop, found unknown"
    assert failed["canonical_version_unverifiable"].evidence == "expected 0.6.18, found unknown"
    assert failed["canonical_build_unverifiable"].evidence == "expected 58, found unknown"
    assert failed["canonical_team_id_unverifiable"].evidence == "expected TC6MS3T6NN, found unknown"


def test_stale_computer_use_helper_herd_fails_with_pids() -> None:
    inventory = WorkbenchInventory(
        registered_paths=("/Applications/evaOS.app",),
        app_bundles=(AppBundle(path="/Applications/evaOS.app", bundle_id="com.electricsheephq.EvaDesktop", version="0.6.18", build="58"),),
        processes=(
            ProcessInfo(pid=101, command="SkyComputerUseClient mcp", kind="computer_use_helper"),
            ProcessInfo(pid=102, command="SkyComputerUseClient mcp", kind="computer_use_helper"),
            ProcessInfo(pid=103, command="SkyComputerUseClient mcp", kind="computer_use_helper"),
        ),
    )

    report = evaluate_inventory(inventory, max_computer_use_helpers=1)

    assert report.ok is False
    failed = {check.code: check for check in report.checks if check.status == "fail"}
    assert failed["stale_computer_use_helpers"].evidence == "3 helpers running: 101, 102, 103"


def test_bridge_peekaboo_surface_warns_on_codex_mcp_helper_herd() -> None:
    inventory = WorkbenchInventory(
        registered_paths=("/Applications/evaOS.app",),
        app_bundles=(
            AppBundle(
                path="/Applications/evaOS.app",
                bundle_id="com.electricsheephq.EvaDesktop",
                version="0.6.19",
                build="59",
                team_id="TC6MS3T6NN",
            ),
        ),
        processes=(
            ProcessInfo(pid=101, command="SkyComputerUseClient mcp", kind="computer_use_helper"),
            ProcessInfo(pid=102, command="SkyComputerUseClient mcp", kind="computer_use_helper"),
            ProcessInfo(pid=103, command="SkyComputerUseClient mcp", kind="computer_use_helper"),
        ),
    )

    report = evaluate_inventory(inventory, max_computer_use_helpers=1, control_surface=BRIDGE_PEEKABOO_SURFACE)

    assert report.ok is True
    warnings = {check.code: check for check in report.checks if check.status == "warn"}
    assert warnings["codex_mcp_helper_count_high"].evidence == "3 helpers running: 101, 102, 103"
    assert report.summary["control_surface"] == "bridge-peekaboo"


def test_computer_use_helper_detection_ignores_shell_cleanup_commands() -> None:
    assert _is_computer_use_mcp_helper("./Codex Computer Use.app/Contents/SharedSupport/SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient mcp")
    assert not _is_computer_use_mcp_helper("/bin/zsh -c pkill -TERM -f 'SkyComputerUseClient.* mcp' || true")
    assert not _is_computer_use_mcp_helper("rg SkyComputerUseClient mcp /Users/lume/.codex/log")
