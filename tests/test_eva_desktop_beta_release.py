from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "apps" / "eva-desktop-mac"


def test_beta_packaging_uses_no_developer_id_path() -> None:
    script = (APP_ROOT / "script" / "build_and_run.sh").read_text(encoding="utf-8")
    app_brand = (APP_ROOT / "Sources" / "EvaDesktopCore" / "Models" / "AppBrand.swift").read_text(encoding="utf-8")

    assert "--package-beta" in script
    script_version = re.search(r'^VERSION="([^"]+)"$', script, re.MULTILINE)
    script_build = re.search(r'^BUILD_NUMBER="([^"]+)"$', script, re.MULTILINE)
    app_version = re.search(r'public static let version = "([^"]+)"', app_brand)
    app_build = re.search(r'public static let buildNumber = "([^"]+)"', app_brand)
    assert script_version is not None
    assert script_build is not None
    assert app_version is not None
    assert app_build is not None
    assert script_version.group(1) == app_version.group(1)
    assert script_build.group(1) == app_build.group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+", script_version.group(1))
    assert script_build.group(1).isdigit()
    assert 'REQUIRED_PEEKABOO_VERSION="${EVAOS_REQUIRED_PEEKABOO_VERSION:-3.2.2 or newer}"' in script
    assert 'STRICT_PEEKABOO_CHECK="${EVAOS_STRICT_PEEKABOO_CHECK:-1}"' in script
    assert 'STRICT_PEEKABOO_CHECK="${EVAOS_STRICT_PEEKABOO_CHECK:-0}"' in script
    assert "REQUIRED_PEEKABOO_VERSION_RE" in script
    assert 'grep -Eq "$REQUIRED_PEEKABOO_VERSION_RE"' in script
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
    script = (APP_ROOT / "script" / "build_and_run.sh").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "evaos-workbench-build-release-runbook.md").read_text(encoding="utf-8")

    assert "errSecInteractionNotAllowed" in keychain_store
    assert "errSecAuthFailed" in keychain_store
    assert "EVAOS_WORKBENCH_DISABLE_KEYCHAIN" in model
    assert "EVA_DESKTOP_DISABLE_KEYCHAIN" in model
    assert "keychainDisabledForAgentQA" in model
    assert re.search(
        r"if\s+!keychainDisabledForAgentQA\s*\{\s*session\s*=\s*try\?\s*keychain\.load\(allowUserInteraction:\s*false\)",
        model,
        re.MULTILINE,
    )
    assert re.search(
        r"if\s+!keychainDisabledForAgentQA\s*\{\s*try\s+keychain\.save\(newSession\)",
        model,
        re.MULTILINE,
    )
    assert "try capabilityManifestStore.saveToken(token)" in model
    assert "if clearCache && !keychainDisabledForAgentQA" in model
    assert "session = try? keychain.load(allowUserInteraction: false)" in model
    assert "func resetLocalSession()" in model
    assert "clearLocalSessionState(allowKeychainInteraction: false)" in model
    assert "keychain.clear(allowUserInteraction: allowKeychainInteraction)" in model
    assert "--verify-agent-qa" in script
    assert "EvaDesktop.disableKeychainForAgentQA" in script
    assert "EVAOS_WORKBENCH_DISABLE_KEYCHAIN" in script
    assert "$HOME/Applications/evaOS Workbench Agent QA.app" in script
    assert "do not launch `dist/evaOS.app` directly" in runbook
    assert "from `/Volumes/LEXAR`" in runbook
    assert "pairedDevices = []" in model


def test_customer_beta_documents_guarded_agent_control_boundary() -> None:
    readme = (APP_ROOT / "README.md").read_text(encoding="utf-8")
    release = (ROOT / "docs" / "evaos-workbench-beta-release.md").read_text(encoding="utf-8")
    connector = (ROOT / "docs" / "customer-mac-connector.md").read_text(encoding="utf-8")
    control_engine = (ROOT / "docs" / "desktop-control-engine-v2.md").read_text(encoding="utf-8")
    plugin = (ROOT / "openclaw-plugin" / "index.ts").read_text(encoding="utf-8")

    assert "Mac and iPhone actions run through" in readme
    assert "audited OpenClaw/Hermes tools" in readme
    assert "customer-facing Mac and iPhone control" in release
    assert "Full Access" in release
    assert "Ask Permission" in release
    assert "10-second takeover warning" in readme
    assert "control_takeover_warning_active" in readme
    assert "10-second operator takeover warning" in connector
    assert "control_takeover_warning_active" in connector
    assert "Live actions wait for the 10-second operator takeover warning" in plugin
    assert "Starting Agent Control shows the 10-second takeover warning" in control_engine


def test_workbench_surfaces_agent_takeover_warning_countdown() -> None:
    model = (APP_ROOT / "Sources" / "EvaDesktop" / "Services" / "WorkbenchModel.swift").read_text(encoding="utf-8")
    bridge_panel = (APP_ROOT / "Sources" / "EvaDesktop" / "Views" / "BridgePanelView.swift").read_text(encoding="utf-8")

    assert 'value(at: ["data", "takeover_warning", "active"]' in model
    assert 'value(at: ["data", "takeover_warning", "remaining_seconds"]' in model
    assert "Taking over screen in \\(remaining)s" in model
    assert "Live agent actions are paused for the operator warning." in model
    assert 'lower.contains("taking over screen")' in bridge_panel
    assert 'return "Starting"' in bridge_panel


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
    assert 'next.arguments = [' in model
    assert '"helper",' in model
    assert '"run",' in model
    assert '"ping",' in model
    assert '"--socket-path",' in model
    assert '"--token-file",' in model
    assert '"EVAOS_DESKTOP_BRIDGE_USE_HELPER": "1"' in model
    assert '"EVAOS_DESKTOP_BRIDGE_HELPER_SOCKET": paths.socket.path' in model
    assert '"EVAOS_DESKTOP_BRIDGE_HELPER_TOKEN_FILE": paths.token.path' in model
    assert 'environment["EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID"]' in model
    assert 'environment["EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH"]' in model
    assert 'environment["EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS"] = "1"' in model
    assert "Mac Access stayed off to avoid a Python or terminal TCC prompt" in model
    assert "Live actions will fail closed until evaOS Workbench has both grants" in model
    assert "deinit" in model
    assert "stopManagedConnectorForAppTermination" in model
    assert "NSApplication.willTerminateNotification" in content_view
    assert "Bridge file:" in model
    assert "Permission holder:" in model
    assert "Python helper:" not in model
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
    assert "evaos-connector-helper" in script
    assert "Local Peekaboo:" in script
    assert "Bundled Peekaboo:" in script
    assert "Peekaboo $REQUIRED_PEEKABOO_VERSION is required for this release" in script
    assert "broker-backed Shared Browser status" in script
    assert "without exposing query strings or fragments" in script
    assert "Session Center records synchronized" in script
    assert "format_datetime(published, usegmt=True)" in script
    assert "published_at" in script
    assert "verify_app_signature" in script
    assert 'codesign --verify --deep --strict "$bundle"' in script
    assert 'verify_app_signature "$APP_BUNDLE"' in script
    assert 'verify_app_signature "$agent_qa_bundle"' in script
    assert "verification skipped for local mode" in script
    assert 'export PATH="$BRIDGE_DIR/bin:$PATH"' in script
    assert "/opt/homebrew/bin/peekaboo /usr/local/bin/peekaboo" in script
    assert "/usr/local/bin/peekaboo peekaboo" not in script
    assert 'exec "$PYTHON_BIN" -m evaos_desktop_bridge.cli "$@"' in script
    assert "https://github.com/electricsheephq/evaos-workbench-releases/releases/download/evaos-workbench-v$VERSION/evaOS-Workbench-$VERSION.zip" in script
    assert "<sparkle:hardwareRequirements>arm64</sparkle:hardwareRequirements>" in script
    assert 'text.replace("            <sparkle:hardwareRequirements>arm64</sparkle:hardwareRequirements>\\n", "")' in script
    assert "customer-mac\", \"control\", \"status\", \"--json" in model
    assert "customer-mac\", \"control\", \"stop\", \"--json" in model
    assert "customer-mac\", \"control\", \"kill-switch\", \"--json" in model
    assert 'bridge.run(arguments: ["codex", "connections", "status", "--json"])' in model
    assert 'bridgeKey(["codex", "connections", "status", "--json"])' in model
    assert "remote_control_command" in model
    assert "control_sockets" in model
    assert "socket_path" not in model
    assert "full-access" in model
    assert "ask-permission" in model


def test_workbench_refreshes_connector_after_app_update() -> None:
    model = (APP_ROOT / "Sources" / "EvaDesktop" / "Services" / "WorkbenchModel.swift").read_text(encoding="utf-8")

    assert "refreshConnectorServiceAfterAppUpdateIfNeeded" in model
    assert "EvaDesktop.lastConnectorRefreshAppBuild" in model
    assert 'bridge.run(arguments: ["connector-service", "status", "--json"])' in model
    assert 'bridge.run(arguments: ["connector-service", "stop", "--json"])' in model
    assert 'bridge.run(arguments: ["connector-service", "start", "--json"])' in model
    assert "connectorServiceIsRunning" in model
    assert "Refreshing Mac Access for this Workbench update" in model
    assert '"/opt/homebrew/bin/tailscale"' in model
    assert '"/usr/local/bin/tailscale"' in model


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
    assert "Open Login Again" in runtime_detail
    assert "Cancel Login" in runtime_detail
    assert "Backup codes must come from the browser page" in model
    assert "session.start()" in model
    assert "DesktopAuthSessionError.couldNotStart" in model
    assert "NSWorkspace.shared.open(authURL)" in model
    assert "finishActiveSignIn" in model
    assert "DesktopAuthSessionError.timedOut" in model
    assert "deviceCodeInput = \"\"" in model
    assert "deviceCodeInput = fallbackCode" not in model
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
