from __future__ import annotations

from evaos_desktop_bridge.pre_canary import AppBundle, ProcessInfo, WorkbenchInventory, evaluate_inventory


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
