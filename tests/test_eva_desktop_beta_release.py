from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "apps" / "eva-desktop-mac"


def test_beta_packaging_uses_no_developer_id_path() -> None:
    script = (APP_ROOT / "script" / "build_and_run.sh").read_text(encoding="utf-8")

    assert "--package-beta" in script
    assert "evaOS-Workbench-Beta-$VERSION.zip" in script
    assert 'BETA_UPDATE_MANIFEST="$DIST_DIR/updates.json"' in script
    assert "evaos-workbench-updates.json" in script
    assert "Apple Development:" in script
    assert "Beta packaging intentionally excludes Developer ID signing" in script
    assert "not Developer ID signed or\nnotarized yet" in script
    assert "Do not globally disable Gatekeeper" in script
    assert "Automatic update checks are enabled" in script


def test_keychain_auth_failures_clear_non_interactively() -> None:
    keychain_store = (APP_ROOT / "Sources" / "EvaDesktopCore" / "Services" / "KeychainSessionStore.swift").read_text(encoding="utf-8")
    model = (APP_ROOT / "Sources" / "EvaDesktop" / "Services" / "WorkbenchModel.swift").read_text(encoding="utf-8")

    assert "errSecInteractionNotAllowed" in keychain_store
    assert "errSecAuthFailed" in keychain_store
    assert "session = try? keychain.load(allowUserInteraction: false)" in model
    assert "func resetLocalSession()" in model
    assert "clearLocalSessionState(allowKeychainInteraction: false)" in model
    assert "keychain.clear(allowUserInteraction: allowKeychainInteraction)" in model
    assert "pairedDevices = []" in model


def test_customer_beta_documents_guarded_agent_control_boundary() -> None:
    readme = (APP_ROOT / "README.md").read_text(encoding="utf-8")
    release = (ROOT / "docs" / "evaos-workbench-beta-release.md").read_text(encoding="utf-8")

    assert "Mac and iPhone actions run through" in readme
    assert "audited OpenClaw/Hermes tools" in readme
    assert "customer-facing Mac and iPhone control" in release
    assert "matching approval audit id" in release


def test_workbench_setup_uses_clean_status_formatter_and_app_managed_connector() -> None:
    model = (APP_ROOT / "Sources" / "EvaDesktop" / "Services" / "WorkbenchModel.swift").read_text(encoding="utf-8")
    bridge_panel = (APP_ROOT / "Sources" / "EvaDesktop" / "Views" / "BridgePanelView.swift").read_text(encoding="utf-8")
    content_view = (APP_ROOT / "Sources" / "EvaDesktop" / "Views" / "ContentView.swift").read_text(encoding="utf-8")

    assert "WorkbenchConnectorProcessManager" in model
    assert "BridgeStatusFormatter.connector(raw:" in model
    assert "BridgeStatusFormatter.customerMac(raw:" in model
    assert "BridgeStatusFormatter.customerMacReady(raw:" in model
    assert "BridgeStatusFormatter.iPhoneReady(raw:" in model
    assert "rawLooksOK(localStatus)" not in model
    assert 'next.arguments = ["serve", "--host", host, "--port", "8765"]' in model
    assert "deinit" in model
    assert "stopManagedConnectorForAppTermination" in model
    assert "NSApplication.willTerminateNotification" in content_view
    assert "Bridge file:" in model
    assert "Python helper:" in model
    assert "Connect Your Mac" in bridge_panel
    assert "Sign out clears this app login" in bridge_panel
    assert "Revoke Mac Access" in bridge_panel
    assert 'lower.contains("not running")' in bridge_panel
    assert "StatusTile" in bridge_panel
    assert "Download Update" in bridge_panel
    assert ".font(.callout)" in bridge_panel
    assert 'design: .monospaced' not in bridge_panel
