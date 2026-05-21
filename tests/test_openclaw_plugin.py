from __future__ import annotations

import json
import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "openclaw-plugin"


def test_openclaw_plugin_manifest_points_to_entrypoint() -> None:
    package = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
    manifest = json.loads((PLUGIN / "openclaw.plugin.json").read_text(encoding="utf-8"))

    assert package["openclaw"]["extensions"] == ["./dist/index.js"]
    assert package["exports"]["."] == "./dist/index.js"
    assert "openclaw.plugin.json" in package["files"]
    assert (PLUGIN / "dist" / "index.js").exists()
    assert package["type"] == "module"
    assert manifest["id"] == "evaos-desktop-bridge"
    assert manifest["main"] == "dist/index.js"
    assert manifest["configSchema"] == {"type": "object", "additionalProperties": False, "properties": {}}
    assert manifest["contracts"]["tools"]
    assert package["openclaw"]["contracts"]["tools"] == manifest["contracts"]["tools"]


def test_openclaw_plugin_registers_read_only_tools_only() -> None:
    source = (PLUGIN / "index.ts").read_text(encoding="utf-8")

    expected_tools = [
        "desktop_bridge_status",
        "desktop_bridge_capabilities",
        "desktop_bridge_latest",
        "desktop_bridge_audit_tail",
        "desktop_bridge_queue_list",
        "desktop_bridge_queue_append",
        "desktop_bridge_codex_frontmost",
        "desktop_bridge_codex_windows",
        "desktop_bridge_codex_threads",
        "desktop_bridge_codex_continue_thread",
        "desktop_bridge_codex_select_thread",
        "desktop_bridge_codex_snapshot",
        "desktop_bridge_codex_inspect",
        "desktop_bridge_codex_ax_tree",
        "desktop_bridge_codex_app_server_status",
        "desktop_bridge_codex_app_server_remote_control_status",
        "desktop_bridge_codex_app_server_threads",
        "customer_mac_status",
        "customer_mac_capabilities",
        "customer_mac_snapshot",
        "customer_mac_ax_tree",
        "customer_mac_app_focus",
        "customer_mac_local_site_open",
        "customer_mac_local_site_action",
        "customer_mac_iphone_mirroring_status",
        "customer_mac_iphone_mirroring_home",
        "customer_mac_iphone_mirroring_app_switcher",
        "customer_mac_iphone_mirroring_spotlight",
        "customer_mac_iphone_mirroring_type_spotlight",
        "customer_mac_iphone_mirroring_open_app",
        "customer_mac_iphone_mirroring_tap_named_target",
        "customer_mac_iphone_mirroring_scroll",
        "customer_mac_iphone_mirroring_swipe_left",
        "customer_mac_iphone_mirroring_swipe_right",
        "customer_mac_iphone_mirroring_swipe_up",
        "customer_mac_iphone_mirroring_swipe_down",
        "customer_mac_iphone_mirroring_type_approved_text",
        "customer_mac_iphone_mirroring_send_approved_message",
        "customer_mac_screen_sharing_status",
    ]
    for tool_name in expected_tools:
        assert tool_name in source
        assert tool_name in json.loads((PLUGIN / "openclaw.plugin.json").read_text(encoding="utf-8"))["contracts"]["tools"]

    forbidden_tool_names = [
        "desktop_bridge_codex_send",
        "desktop_bridge_codex_type",
        "desktop_bridge_codex_click",
        "desktop_bridge_shell",
        "desktop_bridge_exec",
        "customer_mac_generic_coordinates",
        "customer_mac_screen_sharing_enable",
    ]
    for tool_name in forbidden_tool_names:
        assert tool_name not in source


def test_openclaw_plugin_uses_fixed_cli_allowlist_without_shell() -> None:
    source = (PLUGIN / "src" / "bridge.ts").read_text(encoding="utf-8")

    assert "FIXED_COMMANDS" in source
    assert "shell: false" in source
    assert "execFile" in source
    assert "EVAOS_DESKTOP_BRIDGE_URL" in source
    assert "/v1/commands" in source
    assert "EVAOS_DESKTOP_BRIDGE_TOKEN" in source
    assert '"app-server"' in source
    assert '"customer-mac"' in source
    assert "customerMacIphoneMirroringOpenApp" in source
    assert "customerMacIphoneMirroringSendApprovedMessage" in source
    assert "turn/start" not in source
    assert "session.db" not in source


def test_openclaw_plugin_registers_tool_objects_for_runtime_discovery() -> None:
    source = (PLUGIN / "index.ts").read_text(encoding="utf-8")

    assert "api.registerTool(bridgeTool);" in source
    assert "api.registerTool(() => bridgeTool" not in source


def test_openclaw_plugin_execute_preserves_tool_arguments() -> None:
    source = (PLUGIN / "index.ts").read_text(encoding="utf-8")

    assert "execute: (_toolCallId: string, params: BridgeParams = {}) => runBridge(command, params)" in source
    assert "execute: (params: BridgeParams = {}) =>" not in source


def test_openclaw_plugin_firewall_blocks_escape_hatches() -> None:
    source = (PLUGIN / "src" / "firewall.ts").read_text(encoding="utf-8")

    for pattern in [
        "osascript",
        "screencapture",
        "codex app-server",
        "session.db",
        "cliclick",
        "pyautogui",
        "send_message",
        "submit_prompt",
        "turn/start",
        "thread/inject_items",
        "config/batchWrite",
        "plugin/install",
        "generic coordinates",
        "kickstart -activate",
        "camera",
        "microphone",
    ]:
        assert pattern in source

    assert "block: true" in source
    assert "requireApproval: {" in source
    assert "title: \"Approve customer Mac action\"" in source
    assert "timeoutBehavior: \"deny\"" in source
    assert "allowedDecisions: [\"allow-once\", \"deny\"]" in source
    assert "approval_audit_id" in (PLUGIN / "index.ts").read_text(encoding="utf-8")
    assert "requireApproval: true" not in source
    assert "before_tool_call" in (PLUGIN / "index.ts").read_text(encoding="utf-8")


def test_launch_agent_uses_launchd_logging_and_loopback_connector() -> None:
    plist_path = ROOT / "packaging" / "LaunchAgents" / "com.electricsheep.evaos-desktop-bridge.plist"
    plist = plistlib.loads(plist_path.read_bytes())
    build_script = (ROOT / "scripts" / "build-mac-connector-pkg.sh").read_text(encoding="utf-8")

    assert "StandardOutPath" not in plist
    assert "StandardErrorPath" not in plist

    assert "serve" in plist["ProgramArguments"]
    assert "127.0.0.1" in plist["ProgramArguments"]
    assert "--token-file" not in plist["ProgramArguments"]
    assert plist["KeepAlive"] is True
    assert "StartInterval" not in plist
    assert "pkgutil --check-signature" in build_script
    assert "|| true" not in build_script


def test_hermes_adapter_uses_same_connector_contract() -> None:
    adapter = (ROOT / "hermes-adapter" / "bin" / "evaos-desktop-bridge-command").read_text(encoding="utf-8")
    readme = (ROOT / "hermes-adapter" / "README.md").read_text(encoding="utf-8")

    assert "/v1/commands" in adapter
    assert "EVAOS_DESKTOP_BRIDGE_URL" in adapter
    assert "EVAOS_DESKTOP_BRIDGE_TOKEN" in adapter
    assert 'params_json="${2:-{}}"' not in adapter
    assert 'params_json="{}"' in adapter
    assert "/root/.openclaw/evaos-desktop-bridge.env" in adapter
    assert "EVAOS_DESKTOP_BRIDGE_ENV_FILE" in adapter
    assert "urllib.request" in adapter
    assert "error_body.strip().startswith(\"{\")" in adapter
    assert "customerMacStatus" in readme
    assert "OpenClaw remains the first native plugin path" in readme
    assert "structured denials" in readme
    assert "generic shell" in readme
