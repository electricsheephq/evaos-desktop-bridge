from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
