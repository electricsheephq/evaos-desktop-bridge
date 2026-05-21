from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "apps" / "eva-desktop-mac"


def test_beta_packaging_uses_no_developer_id_path() -> None:
    script = (APP_ROOT / "script" / "build_and_run.sh").read_text(encoding="utf-8")

    assert "--package-beta" in script
    assert "evaOS-Workbench-Beta-$VERSION.zip" in script
    assert "Apple Development:" in script
    assert "Beta packaging intentionally excludes Developer ID signing" in script
    assert "not Developer ID signed or\nnotarized yet" in script
    assert "Do not globally disable Gatekeeper" in script


def test_keychain_auth_failures_clear_non_interactively() -> None:
    keychain_store = (APP_ROOT / "Sources" / "EvaDesktopCore" / "Services" / "KeychainSessionStore.swift").read_text(encoding="utf-8")
    model = (APP_ROOT / "Sources" / "EvaDesktop" / "Services" / "WorkbenchModel.swift").read_text(encoding="utf-8")

    assert "errSecInteractionNotAllowed" in keychain_store
    assert "errSecAuthFailed" in keychain_store
    assert "session = try? keychain.load(allowUserInteraction: false)" in model
    assert "func resetLocalSession()" in model
    assert "clearLocalSessionState(allowKeychainInteraction: false)" in model
    assert "keychain.clear(allowUserInteraction: allowKeychainInteraction)" in model


def test_customer_beta_keeps_bridge_status_only_boundary_documented() -> None:
    readme = (APP_ROOT / "README.md").read_text(encoding="utf-8")
    canary = (ROOT / "docs" / "support-vm-mac-iphone-codex-canary.md").read_text(encoding="utf-8")

    assert "does not\nexpose live local-control buttons" in readme
    assert "EVAOS_SUPPORT_CANARY_CONTROLS=1" in canary
    assert "Do not copy it into customer VM images or\nGolden provisioning" in canary


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
    assert 'Text(status.isEmpty ? "Not checked yet." : status)' in bridge_panel
    assert ".font(.callout)" in bridge_panel
    assert ".lineLimit(10)" in bridge_panel
    assert 'design: .monospaced' not in bridge_panel
