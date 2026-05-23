from __future__ import annotations

import json
import os
import plistlib
import subprocess
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
    dist = (PLUGIN / "dist" / "index.js").read_text(encoding="utf-8")

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
        "evaos_provider_profiles",
        "evaos_provider_active_profile",
        "evaos_shared_browser_guidance",
        "customer_mac_status",
        "desktop_control_status",
        "desktop_control_start",
        "desktop_control_stop",
        "desktop_kill_switch",
        "customer_mac_complete_pairing",
        "customer_mac_capabilities",
        "desktop_see",
        "desktop_click",
        "desktop_type",
        "desktop_scroll",
        "desktop_drag",
        "desktop_hotkey",
        "desktop_focus_app",
        "desktop_window",
        "desktop_menu",
        "desktop_browser_action",
        "customer_mac_snapshot",
        "customer_mac_ax_tree",
        "customer_mac_app_focus",
        "customer_mac_local_site_open",
        "customer_mac_local_site_action",
        "iphone_see",
        "iphone_tap",
        "iphone_swipe",
        "iphone_type",
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
        assert tool_name in dist
        assert tool_name in json.loads((PLUGIN / "openclaw.plugin.json").read_text(encoding="utf-8"))["contracts"]["tools"]

    forbidden_tool_names = [
        "desktop_bridge_codex_send",
        "desktop_bridge_codex_type",
        "desktop_bridge_codex_click",
        "desktop_bridge_shell",
        "desktop_bridge_exec",
        "customer_mac_screen_sharing_enable",
    ]
    for tool_name in forbidden_tool_names:
        assert tool_name not in source
        assert tool_name not in dist

    assert "Full Access iPhone action: type and send one exact message" in dist
    assert "Support-only canary action" not in dist
    assert "focus, minimize, maximize, or close" in source
    assert "focus, minimize, maximize, or close" in dist
    assert 'enum: ["focus", "minimize", "maximize", "zoom", "close"]' in dist
    assert "focus, minimize, zoom, or close" not in dist


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
    assert "desktopClick" in source
    assert "iphoneSwipe" in source
    assert "customerMacControlStart" in source
    assert "customerMacIphoneMirroringOpenApp" in source
    assert "customerMacIphoneMirroringSendApprovedMessage" in source
    assert "evaosProviderProfiles" in source
    assert "evaosProviderActiveProfile" in source
    assert "evaosSharedBrowserGuidance" in source
    assert "turn/start" not in source
    assert "session.db" not in source


def test_openclaw_plugin_reports_provider_and_shared_browser_metadata_without_tokens() -> None:
    script = """
        import { runBridge } from './openclaw-plugin/dist/src/bridge.js';
        const profiles = await runBridge('evaosProviderProfiles', {});
        const active = await runBridge('evaosProviderActiveProfile', {});
        const browser = await runBridge('evaosSharedBrowserGuidance', {});
        console.log(JSON.stringify({ profiles, active, browser }));
    """
    env = {
        **os.environ,
        "EVAOS_CUSTOMER_ID": "cust-1",
        "EVAOS_ACTIVE_PROVIDER_KEY": "openai_codex",
        "EVAOS_PROVIDER_PROFILES_JSON": json.dumps({
            "provider_profiles": [
                {
                    "provider_key": "openai_codex",
                    "status": "connected",
                    "active": True,
                    "grant_handle": "epg_fixture",
                    "access_token": "should-redact",
                    "api_key": "sk-should-redact",
                    "client_secret": "client-secret-should-redact",
                    "authorization": "Bearer should-redact",
                    "headers": {"x-api-key": "nested-should-redact"},
                }
            ],
            "active_provider_key": "openai_codex",
        }),
        "EVAOS_PROVIDER_GRANTS_JSON": json.dumps({"openclaw": {"grant_handle": "epg_fixture"}}),
        "EVAOS_SHARED_BROWSER_STATUS_JSON": json.dumps({"status": "ready", "current_url": "https://example.com"}),
    }
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["profiles"]["ok"] is True
    assert payload["profiles"]["data"]["customer_id"] == "cust-1"
    assert payload["profiles"]["data"]["active_provider_key"] == "openai_codex"
    assert payload["profiles"]["data"]["raw_secrets_available"] is False
    assert payload["profiles"]["data"]["raw_secrets_stored_in_workbench"] is False
    assert payload["active"]["data"]["needs_reauth"] is False
    assert payload["active"]["data"]["active_profile"]["provider_key"] == "openai_codex"
    assert payload["browser"]["data"]["shared_browser_preferred_for_cloud_web_tasks"] is True
    assert payload["browser"]["data"]["status"]["status"] == "ready"
    serialized = json.dumps(payload)
    assert "should-redact" not in serialized
    assert "nested-should-redact" not in serialized
    assert "[redacted]" in json.dumps(payload)


def test_customer_mac_complete_pairing_validates_connector_urls() -> None:
    script = """
        import { runBridge } from './openclaw-plugin/dist/src/bridge.js';
        const cases = [
          'https://100.64.1.10:8765',
          'http://100.64.1.10',
          'http://127.0.0.1:8765',
          'http://localhost:8765',
          'http://8.8.8.8:8765',
          'http://100.64.1.10:8765/v1/commands',
        ];
        const results = [];
        for (const connector_url of cases) {
          results.push(await runBridge('customerMacCompletePairing', {
            connector_url,
            enrollment_code: 'PAIR123',
          }));
        }
        console.log(JSON.stringify(results));
    """
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    results = json.loads(completed.stdout)

    assert len(results) == 6
    for result in results:
        assert result["ok"] is False
        assert result["errors"][0]["code"] == "bridge_connector_url_forbidden"


def test_customer_mac_complete_pairing_requires_enrollment_code() -> None:
    script = """
        import { runBridge } from './openclaw-plugin/dist/src/bridge.js';
        const result = await runBridge('customerMacCompletePairing', {
          connector_url: 'http://100.64.1.10:8765',
        });
        console.log(JSON.stringify(result));
    """
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["ok"] is False
    assert result["errors"][0]["code"] == "bridge_enrollment_missing_field"
    assert "enrollment_code" in result["errors"][0]["message"]


def test_customer_mac_complete_pairing_posts_to_enrollment_endpoint_without_token() -> None:
    source = (PLUGIN / "src" / "bridge.ts").read_text(encoding="utf-8")
    dist = (PLUGIN / "dist" / "src" / "bridge.js").read_text(encoding="utf-8")

    for text in [source, dist]:
        assert "customerMacCompletePairing" in text
        assert "/v1/enrollment/complete" in text
        assert "enrollment_code" in text
        assert "connector_token" not in text

    assert 'new URL("/v1/commands", remoteURL)' in source
    assert 'new URL("/v1/enrollment/complete", connectorURL)' in source

    script = """
        import { runBridge } from './openclaw-plugin/dist/src/bridge.js';
        let captured = null;
        globalThis.fetch = async (url, options) => {
          captured = {
            url: String(url),
            body: JSON.parse(options.body),
            hasAuthorization: Boolean(options.headers.Authorization || options.headers.authorization),
          };
          return {
            async text() {
              return JSON.stringify({ ok: true, data: { connector_token: 'secret', device_id: 'device-1' } });
            },
          };
        };
        const result = await runBridge('customerMacCompletePairing', {
          connector_url: 'http://100.64.1.10:8765',
          enrollment_code: 'PAIR123',
          customer_id: 'david-poku',
          device_name: 'Customer Mac',
        });
        console.log(JSON.stringify({ captured, result }));
    """
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["captured"]["url"] == "http://100.64.1.10:8765/v1/enrollment/complete"
    assert payload["captured"]["body"] == {
        "enrollment_code": "PAIR123",
        "customer_id": "david-poku",
        "device_name": "Customer Mac",
    }
    assert payload["captured"]["hasAuthorization"] is False
    assert payload["result"]["ok"] is True
    assert payload["result"]["data"]["connector_token"] == "[redacted]"


def test_remote_visual_artifact_is_materialized_on_vm(tmp_path: Path) -> None:
    script = """
        import { runBridge } from './openclaw-plugin/dist/src/bridge.js';
        import { readFile } from 'node:fs/promises';

        const calls = [];
        globalThis.fetch = async (url, options) => {
          calls.push({
            url: String(url),
            auth: options.headers.Authorization || options.headers.authorization || null,
          });
          if (String(url).endsWith('/v1/commands')) {
            return {
              ok: true,
              status: 200,
              async text() {
                return JSON.stringify({
                  ok: true,
                  audit_id: 'audit-1',
                  data: {
                    snapshot_id: 'snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    screenshot: {
                      artifact_id: 'snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                      artifact_url: '/v1/artifacts/snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png',
                      mime_type: 'image/png'
                    }
                  }
                });
              },
            };
          }
          if (String(url).includes('/v1/artifacts/')) {
            return {
              ok: true,
              status: 200,
              async arrayBuffer() {
                return new Uint8Array([137, 80, 78, 71]).buffer;
              },
            };
          }
          throw new Error('unexpected URL ' + String(url));
        };

        const result = await runBridge('desktopSee', {});
        const bytes = Array.from(await readFile(result.data.vm_visual_artifact_path));
        console.log(JSON.stringify({ calls, result, bytes }));
    """
    env = {
        **os.environ,
        "EVAOS_DESKTOP_BRIDGE_URL": "http://100.64.1.10:8765",
        "EVAOS_DESKTOP_BRIDGE_TOKEN": "connector-token",
        "EVAOS_DESKTOP_BRIDGE_ARTIFACT_DIR": str(tmp_path),
    }
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["calls"] == [
        {"url": "http://100.64.1.10:8765/v1/commands", "auth": "Bearer connector-token"},
        {
            "url": "http://100.64.1.10:8765/v1/artifacts/snap-desktop-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
            "auth": "Bearer connector-token",
        },
    ]
    assert payload["bytes"] == [137, 80, 78, 71]
    assert payload["result"]["data"]["screenshot"]["vm_artifact_source"] == "connector_artifact"
    assert str(tmp_path) in payload["result"]["data"]["vm_visual_artifact_path"]
    assert "bytes_base64" not in payload["result"]["data"]["screenshot"]


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


def test_hermes_adapter_supports_pre_token_complete_enrollment() -> None:
    adapter = (ROOT / "hermes-adapter" / "bin" / "evaos-desktop-bridge-command").read_text(encoding="utf-8")
    readme = (ROOT / "hermes-adapter" / "README.md").read_text(encoding="utf-8")

    assert "completeEnrollment" in adapter
    assert "/v1/enrollment/complete" in adapter
    assert "EVAOS_DESKTOP_BRIDGE_TOKEN is required" in adapter
    assert "connector_url" in adapter
    assert "enrollment_code" in adapter
    assert "connector_token" not in adapter
    assert "completeEnrollment" in readme
    assert "/v1/enrollment/complete" in readme


def test_hermes_adapter_reports_provider_and_shared_browser_metadata_before_connector_token() -> None:
    adapter = ROOT / "hermes-adapter" / "bin" / "evaos-desktop-bridge-command"
    env = {
        **os.environ,
        "EVAOS_CUSTOMER_ID": "cust-1",
        "EVAOS_ACTIVE_PROVIDER_KEY": "openai_codex",
        "EVAOS_PROVIDER_PROFILES_JSON": json.dumps({
            "provider_profiles": [
                {
                    "provider_key": "openai_codex",
                    "status": "connected",
                    "active": True,
                    "access_token": "should-redact",
                    "api_key": "sk-should-redact",
                    "client_secret": "client-secret-should-redact",
                    "authorization": "Bearer should-redact",
                    "headers": {"x-api-key": "nested-should-redact"},
                }
            ],
            "active_provider_key": "openai_codex",
        }),
        "EVAOS_SHARED_BROWSER_STATUS_JSON": json.dumps({"status": "ready"}),
    }
    completed = subprocess.run(
        [str(adapter), "evaosProviderActiveProfile"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    active_payload = json.loads(completed.stdout)
    browser_completed = subprocess.run(
        [str(adapter), "evaosSharedBrowserGuidance"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    browser_payload = json.loads(browser_completed.stdout)

    assert active_payload["ok"] is True
    assert active_payload["data"]["active_provider_key"] == "openai_codex"
    assert active_payload["data"]["needs_reauth"] is False
    assert active_payload["data"]["active_profile"]["access_token"] == "[redacted]"
    assert active_payload["data"]["active_profile"]["api_key"] == "[redacted]"
    assert active_payload["data"]["active_profile"]["client_secret"] == "[redacted]"
    assert active_payload["data"]["active_profile"]["authorization"] == "[redacted]"
    assert active_payload["data"]["active_profile"]["headers"] == "[redacted]"
    assert browser_payload["data"]["shared_browser_preferred_for_cloud_web_tasks"] is True
    assert browser_payload["data"]["status"]["status"] == "ready"
