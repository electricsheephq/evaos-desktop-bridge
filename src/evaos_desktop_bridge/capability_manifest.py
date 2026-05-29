from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

CapabilityDecision = Literal["allowed", "requires_approval", "denied"]
ALLOWED_DECISIONS: set[str] = {"allowed", "requires_approval", "denied"}
EXPECTED_ALGORITHM = "HS256"
EXPECTED_ISSUER = "evaos-broker"
EXPECTED_AUDIENCE = "evaos-runtime"


class CapabilityManifestError(ValueError):
    """Raised when a capability manifest cannot be trusted or parsed."""


@dataclass(frozen=True)
class CapabilityBudget:
    tokens_per_day: int | None = None
    dollars_per_day: float | None = None


@dataclass(frozen=True)
class CapabilityManifest:
    agent_id: str
    owner_id: str
    issued_at: datetime
    expires_at: datetime
    grants: dict[str, CapabilityDecision]
    budget: CapabilityBudget
    approval_channel: str
    issuer: str
    audience: str


def verify_hs256_manifest(
    token: str,
    secret: bytes | str,
    *,
    now: datetime | None = None,
    issuer: str = EXPECTED_ISSUER,
    audience: str = EXPECTED_AUDIENCE,
) -> CapabilityManifest:
    """Verify and parse a signed evaOS Capability Manifest JWT."""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if not secret:
        raise CapabilityManifestError("capability manifest secret is required")
    parts = token.split(".")
    if len(parts) != 3 or any(not part for part in parts):
        raise CapabilityManifestError("capability manifest must be a three-part JWT")
    header = _loads_json_object(_base64url_decode(parts[0]), "header")
    if header.get("alg") != EXPECTED_ALGORITHM:
        raise CapabilityManifestError("capability manifest algorithm must be HS256")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected_signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    actual_signature = _base64url_decode(parts[2])
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise CapabilityManifestError("capability manifest signature is invalid")
    payload = _loads_json_object(_base64url_decode(parts[1]), "payload")
    manifest = _manifest_from_payload(payload)
    if manifest.issuer != issuer:
        raise CapabilityManifestError("capability manifest issuer is invalid")
    if manifest.audience != audience:
        raise CapabilityManifestError("capability manifest audience is invalid")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if current_time > manifest.expires_at:
        raise CapabilityManifestError("capability manifest expired")
    if current_time < manifest.issued_at:
        raise CapabilityManifestError("capability manifest is not yet valid")
    return manifest


def decision_for_tool(manifest: CapabilityManifest, tool_name: str) -> CapabilityDecision:
    return manifest.grants.get(tool_name, "denied")


def grant_summary(manifest: CapabilityManifest) -> dict[str, Any]:
    grants: dict[str, list[str]] = {decision: [] for decision in sorted(ALLOWED_DECISIONS)}
    for tool_name, decision in sorted(manifest.grants.items()):
        grants[decision].append(tool_name)
    return {
        "agent_id": manifest.agent_id,
        "owner_id": manifest.owner_id,
        "expires_at": _format_utc(manifest.expires_at),
        "approval_channel": manifest.approval_channel,
        "budget": {
            "tokens_per_day": manifest.budget.tokens_per_day,
            "dollars_per_day": manifest.budget.dollars_per_day,
        },
        "grants": grants,
    }


def _manifest_from_payload(payload: dict[str, Any]) -> CapabilityManifest:
    agent_id = _required_string(payload, "agent_id")
    owner_id = _required_string(payload, "owner_id")
    issued_at = _parse_instant(_required_string(payload, "issued_at"), "issued_at")
    expires_at = _parse_instant(_required_string(payload, "expires_at"), "expires_at")
    approval_channel = _required_string(payload, "approval_channel")
    issuer = _required_string(payload, "iss")
    audience = _required_string(payload, "aud")
    raw_grants = payload.get("grants")
    if not isinstance(raw_grants, dict) or not raw_grants:
        raise CapabilityManifestError("capability manifest grants must be a non-empty object")
    grants: dict[str, CapabilityDecision] = {}
    for tool_name, decision in raw_grants.items():
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise CapabilityManifestError("capability manifest grant tool names must be non-empty strings")
        if decision not in ALLOWED_DECISIONS:
            raise CapabilityManifestError(f"capability manifest grant decision is invalid for {tool_name}")
        grants[tool_name.strip()] = decision
    budget = _budget_from_payload(payload.get("budget"))
    if expires_at <= issued_at:
        raise CapabilityManifestError("capability manifest expires_at must be after issued_at")
    return CapabilityManifest(
        agent_id=agent_id,
        owner_id=owner_id,
        issued_at=issued_at,
        expires_at=expires_at,
        grants=grants,
        budget=budget,
        approval_channel=approval_channel,
        issuer=issuer,
        audience=audience,
    )


def _budget_from_payload(value: Any) -> CapabilityBudget:
    if value is None:
        return CapabilityBudget()
    if not isinstance(value, dict):
        raise CapabilityManifestError("capability manifest budget must be an object")
    tokens = value.get("tokens_per_day")
    dollars = value.get("dollars_per_day")
    if tokens is not None and (not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0):
        raise CapabilityManifestError("capability manifest budget.tokens_per_day must be a non-negative integer")
    if dollars is not None and (not isinstance(dollars, (int, float)) or isinstance(dollars, bool) or float(dollars) < 0):
        raise CapabilityManifestError("capability manifest budget.dollars_per_day must be a non-negative number")
    return CapabilityBudget(tokens_per_day=tokens, dollars_per_day=float(dollars) if dollars is not None else None)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityManifestError(f"capability manifest {key} is required")
    return value.strip()


def _parse_instant(value: str, key: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CapabilityManifestError(f"capability manifest {key} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _base64url_decode(value: str) -> bytes:
    try:
        padded = value + ("=" * (-len(value) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise CapabilityManifestError("capability manifest base64url segment is invalid") from exc


def _loads_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CapabilityManifestError(f"capability manifest {label} is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise CapabilityManifestError(f"capability manifest {label} must be an object")
    return parsed
