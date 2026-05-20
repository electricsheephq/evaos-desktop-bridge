from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "openclaw-plugin"


def test_openclaw_plugin_manifest_points_to_entrypoint() -> None:
    manifest = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))

    assert manifest["openclaw"]["extensions"] == ["./index.ts"]
    assert manifest["type"] == "module"


def test_openclaw_plugin_registers_named_tools_only() -> None:
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
        "desktop_bridge_codex_select_thread",
        "desktop_bridge_codex_snapshot",
        "desktop_bridge_codex_inspect",
        "desktop_bridge_codex_ax_tree",
        "desktop_bridge_codex_app_server_status",
        "desktop_bridge_codex_app_server_threads",
        "desktop_bridge_codex_connections_status",
        "desktop_bridge_codex_live_status",
        "desktop_bridge_codex_remote_start_turn",
        "desktop_bridge_codex_remote_steer_turn",
        "desktop_bridge_codex_remote_interrupt_turn",
    ]
    for tool_name in expected_tools:
        assert tool_name in source

    forbidden_tool_names = [
        "desktop_bridge_codex_send",
        "desktop_bridge_codex_type",
        "desktop_bridge_codex_click",
        "desktop_bridge_shell",
        "desktop_bridge_exec",
    ]
    for tool_name in forbidden_tool_names:
        assert tool_name not in source


def test_openclaw_plugin_uses_fixed_cli_allowlist_without_shell() -> None:
    source = (PLUGIN / "src" / "bridge.ts").read_text(encoding="utf-8")

    assert "FIXED_COMMANDS" in source
    assert "shell: false" in source
    assert "execFile" in source
    assert '"app-server"' in source
    assert "turn/start" not in source
    assert "session.db" not in source
    assert "codexAppServerStartTurn" in source
    assert "codexAppServerSteerTurn" in source
    assert "codexAppServerInterruptTurn" in source


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
    ]:
        assert pattern in source

    assert "block: true" in source
    assert "requireApproval: true" in source
    assert "desktop_bridge_codex_remote_start_turn" in source
    assert "before_tool_call" in (PLUGIN / "index.ts").read_text(encoding="utf-8")
