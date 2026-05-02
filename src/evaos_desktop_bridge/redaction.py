from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._-]{10,}", re.IGNORECASE),
    re.compile(r"(?i)(authorization:\s*)[^\s]+"),
)
GENERIC_HOME_PATTERN = re.compile(r"/Users/[^/\s]+")


def cap_text(text: str | None, max_chars: int) -> tuple[str | None, bool]:
    if text is None:
        return None, False
    if max_chars < 0:
        max_chars = 0
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def redact_string(value: str) -> str:
    redacted = value.replace(str(Path.home()), "~")
    redacted = GENERIC_HOME_PATTERN.sub("~", redacted)
    redacted = SECRET_PATTERNS[0].sub("<redacted-secret>", redacted)
    redacted = SECRET_PATTERNS[1].sub(r"\1<redacted-secret>", redacted)
    redacted = SECRET_PATTERNS[2].sub(r"\1<redacted-secret>", redacted)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, Path):
        return redact_string(str(value))
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    return value
