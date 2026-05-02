from __future__ import annotations

from typing import Any

from .schema import make_error

ALLOWED_COMMANDS = frozenset(
    {
        "status",
        "codex.focus",
        "codex.snapshot",
        "codex.ax_tree",
    }
)


class PolicyError(RuntimeError):
    def __init__(self, command: str) -> None:
        self.command = command
        self.error: dict[str, Any] = make_error(
            code="command_not_allowed",
            message=f"Command '{command}' is outside the Desktop Bridge MVP allowlist.",
            guidance="Use one of: status, codex focus, codex snapshot, codex ax-tree.",
        )
        super().__init__(self.error["message"])


def ensure_allowed(command: str) -> str:
    if command not in ALLOWED_COMMANDS:
        raise PolicyError(command)
    return command
