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
        "codex.snapshot",
        "codex.inspect",
        "codex.ax_tree",
        "codex.app_server.status",
        "codex.app_server.threads",
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
    "codex.snapshot": {"mode": "read_only", "source": "screenshot", "requires_permission": ["screen_recording"]},
    "codex.inspect": {"mode": "read_only", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.ax_tree": {"mode": "read_only", "source": "ax", "requires_permission": ["accessibility"]},
    "codex.app_server.status": {"mode": "read_only", "source": "app_server", "requires_permission": []},
    "codex.app_server.threads": {"mode": "read_only", "source": "app_server", "requires_permission": []},
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
