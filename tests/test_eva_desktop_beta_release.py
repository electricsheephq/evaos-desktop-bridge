from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "apps" / "eva-desktop-mac"


def test_beta_packaging_uses_no_developer_id_path() -> None:
    script = (APP_ROOT / "script" / "build_and_run.sh").read_text(encoding="utf-8")
    app_brand = (APP_ROOT / "Sources" / "EvaDesktopCore" / "Models" / "AppBrand.swift").read_text(encoding="utf-8")

    assert "--package-beta" in script
    assert 'VERSION="0.4.0"' in script
    assert 'BUILD_NUMBER="10"' in script
    assert 'version = "0.4.0"' in app_brand
    assert 'buildNumber = "10"' in app_brand
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
    assert "Full Access" in release
    assert "Ask Permission" in release


def test_workbench_setup_uses_clean_status_formatter_and_app_managed_connector() -> None:
    app_brand = (APP_ROOT / "Sources" / "EvaDesktopCore" / "Models" / "AppBrand.swift").read_text(encoding="utf-8")
    model = (APP_ROOT / "Sources" / "EvaDesktop" / "Services" / "WorkbenchModel.swift").read_text(encoding="utf-8")
    bridge_panel = (APP_ROOT / "Sources" / "EvaDesktop" / "Views" / "BridgePanelView.swift").read_text(encoding="utf-8")
    content_view = (APP_ROOT / "Sources" / "EvaDesktop" / "Views" / "ContentView.swift").read_text(encoding="utf-8")

    assert "WorkbenchConnectorProcessManager" in model
    assert "bundledBridgeExecutable()" in model
    assert 'appendingPathComponent("Bridge", isDirectory: true)' in model
    assert 'appendingPathComponent("evaos-desktop-bridge")' in model
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
    assert 'bridgeSectionTitle = "Settings"' in app_brand
    assert 'macAndIPhoneTitle = "Mac & iPhone"' in app_brand
    assert 'Text("Settings")' in bridge_panel
    assert 'SectionEyebrow("Readiness")' in bridge_panel
    assert "Turn On Mac Access" in bridge_panel
    assert "Allow Screen & Control" in bridge_panel
    assert "Link to evaOS" in bridge_panel
    assert "Check Setup" in bridge_panel
    assert "agentAccessTestText" in model
    assert "model.agentAccessTestText" in bridge_panel
    assert "Sign out clears this app login" in bridge_panel
    assert "Disconnect This Mac" in bridge_panel
    assert "Recent Activity" in bridge_panel
    assert "Support Details" in bridge_panel
    assert ".help(" in bridge_panel
    assert 'lower.contains("not running")' in bridge_panel
    assert "ReadinessTile" in bridge_panel
    assert "StatusTile" not in bridge_panel
    assert "Download" in bridge_panel
    assert ".font(.callout)" in bridge_panel
    assert 'design: .monospaced' in bridge_panel


def test_release_package_bundles_matching_bridge_helper() -> None:
    script = (APP_ROOT / "script" / "build_and_run.sh").read_text(encoding="utf-8")
    model = (APP_ROOT / "Sources" / "EvaDesktop" / "Services" / "WorkbenchModel.swift").read_text(encoding="utf-8")

    assert "copy_bridge_helper" in script
    assert 'cp -R "$REPO_ROOT/src/evaos_desktop_bridge" "$bridge_dir/src/"' in script
    assert "copy_peekaboo_helper" in script
    assert 'export PATH="$BRIDGE_DIR/bin:$PATH"' in script
    assert "/opt/homebrew/bin/peekaboo /usr/local/bin/peekaboo" in script
    assert "/usr/local/bin/peekaboo peekaboo" not in script
    assert 'exec "$PYTHON_BIN" -m evaos_desktop_bridge.cli "$@"' in script
    assert "customer-mac\", \"control\", \"status\", \"--json" in model
    assert "customer-mac\", \"control\", \"stop\", \"--json" in model
    assert "customer-mac\", \"control\", \"kill-switch\", \"--json" in model
    assert "full-access" in model
    assert "ask-permission" in model


def test_workbench_pairing_prompt_is_customer_safe_and_self_serve() -> None:
    model = (APP_ROOT / "Sources" / "EvaDesktop" / "Services" / "WorkbenchModel.swift").read_text(encoding="utf-8")
    bridge_panel = (APP_ROOT / "Sources" / "EvaDesktop" / "Views" / "BridgePanelView.swift").read_text(encoding="utf-8")
    runtime_detail = (APP_ROOT / "Sources" / "EvaDesktop" / "Views" / "RuntimeDetailView.swift").read_text(encoding="utf-8")

    assert "David's" not in model
    assert "David's" not in bridge_panel
    assert "customer_mac_complete_pairing" in model
    assert "customer_mac_status" in model
    assert "customer_mac_iphone_mirroring_status" in model
    assert "desktop_bridge_audit_tail" in model
    assert "Success criteria" in model
    assert "Do not perform live Mac or iPhone actions" in model
    assert "Copy Agent Prompt" in bridge_panel
    assert "Complete Here" not in bridge_panel
    assert "Backup code from browser" in runtime_detail
    assert "prefilled code if the browser never shows one" in runtime_detail
    assert "wait a few seconds and press Use Code" in model
    assert "signIn(fallbackCode: fallbackCode)" in model


def test_workbench_setup_primary_badges_use_approved_state_labels() -> None:
    bridge_panel = (APP_ROOT / "Sources" / "EvaDesktop" / "Views" / "BridgePanelView.swift").read_text(encoding="utf-8")

    approved_states = {"Ready", "Needs permission", "Not paired", "Blocked", "Unchecked"}
    forbidden_primary_states = ["Review", "Optional", "Needs setup", "Needs app", "Needs attention", "Linked"]

    for state in approved_states:
        assert f'"{state}"' in bridge_panel

    for state in forbidden_primary_states:
        assert f'return "{state}"' not in bridge_panel
        assert f'badge: "{state}"' not in bridge_panel
