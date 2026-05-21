from __future__ import annotations

from typing import Any

from .schema import make_error

ALLOWED_COMMANDS = frozenset(
    {
        "status",
        "capabilities",
        "latest",
        "audit_tail",
        "queue.list",
        "queue.append",
        "codex.frontmost",
        "codex.windows",
        "codex.threads",
        "codex.focus",
        "codex.select_thread",
        "codex.continue_thread",
        "codex.snapshot",
        "codex.inspect",
        "codex.ax_tree",
        "codex.app_server.status",
        "codex.app_server.threads",
        "codex.app_server.remote_control_status",
        "customer_mac.status",
        "customer_mac.capabilities",
        "customer_mac.snapshot",
        "customer_mac.ax_tree",
        "customer_mac.app_focus",
        "customer_mac.local_site_open",
        "customer_mac.local_site_action",
        "customer_mac.iphone_mirroring_status",
        "customer_mac.iphone_mirroring_focus",
        "customer_mac.iphone_mirroring_home",
        "customer_mac.iphone_mirroring_app_switcher",
        "customer_mac.iphone_mirroring_spotlight",
        "customer_mac.iphone_mirroring_type_spotlight",
        "customer_mac.iphone_mirroring_open_app",
        "customer_mac.iphone_mirroring_tap_named_target",
        "customer_mac.iphone_mirroring_scroll",
        "customer_mac.iphone_mirroring_swipe_left",
        "customer_mac.iphone_mirroring_swipe_right",
        "customer_mac.iphone_mirroring_swipe_up",
        "customer_mac.iphone_mirroring_swipe_down",
        "customer_mac.iphone_mirroring_type_approved_text",
        "customer_mac.iphone_mirroring_send_approved_message",
        "customer_mac.screen_sharing_status",
    }
)

COMMAND_METADATA: dict[str, dict[str, Any]] = {
    "status": {"mode": "read_only", "source": "process", "requires_permission": []},
    "capabilities": {"mode": "read_only", "source": "policy", "requires_permission": []},
    "latest": {"mode": "read_only", "source": "state", "requires_permission": []},
    "audit_tail": {"mode": "read_only", "source": "audit", "requires_permission": []},
    "queue.list": {"mode": "read_only", "source": "queue", "requires_permission": []},
    "queue.append": {"mode": "read_only", "source": "queue", "requires_permission": []},
    "codex.frontmost": {"mode": "read_only", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.windows": {"mode": "read_only", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.threads": {"mode": "read_only", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.focus": {"mode": "guarded_visible_action", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.select_thread": {"mode": "guarded_visible_action", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.continue_thread": {"mode": "support_canary_guarded_visible_action", "source": "ax", "requires_permission": ["accessibility"], "requires_approval": True, "support_only": True, "prompt_scope": "exact_continue_only"},
    "codex.snapshot": {"mode": "read_only", "source": "screenshot", "requires_permission": ["screen_recording"]},
    "codex.inspect": {"mode": "read_only", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.ax_tree": {"mode": "read_only", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.app_server.status": {"mode": "read_only", "source": "app_server", "requires_permission": []},
    "codex.app_server.threads": {"mode": "read_only", "source": "app_server", "requires_permission": []},
    "codex.app_server.remote_control_status": {"mode": "read_only", "source": "codex_native_remote_control", "requires_permission": []},
    "customer_mac.status": {"mode": "read_only", "source": "macos", "requires_permission": []},
    "customer_mac.capabilities": {"mode": "read_only", "source": "policy", "requires_permission": []},
    "customer_mac.snapshot": {"mode": "read_only", "source": "screenshot", "requires_permission": ["screen_recording"], "sensitive_app_block": True},
    "customer_mac.ax_tree": {"mode": "read_only", "source": "ax", "requires_permission": ["accessibility"], "sensitive_app_block": True},
    "customer_mac.app_focus": {"mode": "guarded_visible_action", "source": "macos_open", "requires_permission": [], "requires_approval": True, "sensitive_app_block": True},
    "customer_mac.local_site_open": {"mode": "guarded_visible_action", "source": "macos_open", "requires_permission": [], "requires_approval": True, "url_scope": "localhost_loopback_local"},
    "customer_mac.local_site_action": {"mode": "guarded_visible_action", "source": "browser_keyboard", "requires_permission": ["accessibility"], "requires_approval": True, "allowlist": ["reload", "back", "forward"]},
    "customer_mac.iphone_mirroring_status": {"mode": "read_only", "source": "macos", "requires_permission": []},
    "customer_mac.iphone_mirroring_focus": {"mode": "guarded_visible_action", "source": "macos_open", "requires_permission": [], "requires_approval": True},
    "customer_mac.iphone_mirroring_home": {"mode": "guarded_visible_action", "source": "iphone_mirroring_keyboard", "requires_permission": ["accessibility"], "requires_approval": True},
    "customer_mac.iphone_mirroring_app_switcher": {"mode": "guarded_visible_action", "source": "iphone_mirroring_keyboard", "requires_permission": ["accessibility"], "requires_approval": True},
    "customer_mac.iphone_mirroring_spotlight": {"mode": "guarded_visible_action", "source": "iphone_mirroring_keyboard", "requires_permission": ["accessibility"], "requires_approval": True},
    "customer_mac.iphone_mirroring_type_spotlight": {"mode": "guarded_visible_action", "source": "iphone_mirroring_keyboard", "requires_permission": ["accessibility"], "requires_approval": True, "text_scope": "short_disposable_search_text"},
    "customer_mac.iphone_mirroring_open_app": {"mode": "guarded_visible_action", "source": "iphone_mirroring_keyboard", "requires_permission": ["accessibility"], "requires_approval": True, "sensitive_app_block": True},
    "customer_mac.iphone_mirroring_tap_named_target": {"mode": "guarded_visible_action", "source": "iphone_mirroring_ax", "requires_permission": ["accessibility"], "requires_approval": True, "generic_coordinates": False},
    "customer_mac.iphone_mirroring_scroll": {"mode": "guarded_visible_action", "source": "iphone_mirroring_quartz", "requires_permission": ["accessibility"], "requires_approval": True, "generic_coordinates": False},
    "customer_mac.iphone_mirroring_swipe_left": {"mode": "guarded_visible_action", "source": "iphone_mirroring_quartz", "requires_permission": ["accessibility"], "requires_approval": True, "generic_coordinates": False},
    "customer_mac.iphone_mirroring_swipe_right": {"mode": "guarded_visible_action", "source": "iphone_mirroring_quartz", "requires_permission": ["accessibility"], "requires_approval": True, "generic_coordinates": False},
    "customer_mac.iphone_mirroring_swipe_up": {"mode": "guarded_visible_action", "source": "iphone_mirroring_quartz", "requires_permission": ["accessibility"], "requires_approval": True, "generic_coordinates": False},
    "customer_mac.iphone_mirroring_swipe_down": {"mode": "guarded_visible_action", "source": "iphone_mirroring_quartz", "requires_permission": ["accessibility"], "requires_approval": True, "generic_coordinates": False},
    "customer_mac.iphone_mirroring_type_approved_text": {"mode": "guarded_visible_action", "source": "iphone_mirroring_keyboard", "requires_permission": ["accessibility"], "requires_approval": True, "text_scope": "same_turn_approved_text"},
    "customer_mac.iphone_mirroring_send_approved_message": {"mode": "guarded_visible_action", "source": "iphone_mirroring_ax", "requires_permission": ["accessibility"], "requires_approval": True, "message_scope": "same_turn_approved_recipient_and_exact_text"},
    "customer_mac.screen_sharing_status": {"mode": "read_only", "source": "launchctl_lsof", "requires_permission": [], "bridge_can_enable": False},
}


class PolicyError(RuntimeError):
    def __init__(self, command: str) -> None:
        self.command = command
        self.error: dict[str, Any] = make_error(
            code="command_not_allowed",
            message=f"Command '{command}' is outside the Desktop Bridge MVP allowlist.",
            guidance="Use one of the allowlisted bridge commands. Run evaos-desktop-bridge capabilities --json for the current surface.",
        )
        super().__init__(self.error["message"])


def ensure_allowed(command: str) -> str:
    if command not in ALLOWED_COMMANDS:
        raise PolicyError(command)
    return command


def command_metadata(command: str) -> dict[str, Any]:
    ensure_allowed(command)
    return dict(COMMAND_METADATA[command])
