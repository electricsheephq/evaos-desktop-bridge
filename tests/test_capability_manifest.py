from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest

from evaos_desktop_bridge.capability_manifest import (
    CapabilityManifestError,
    decision_for_tool,
    grant_summary,
    verify_hs256_manifest,
)


SECRET = b"capability-manifest-test-secret"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _jwt(payload: dict[str, object], *, secret: bytes = SECRET, header: dict[str, object] | None = None) -> str:
    encoded_header = _b64url(json.dumps(header or {"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_id": "email-sorter-2026-05",
        "owner_id": "andrew-main",
        "issued_at": "2026-05-29T18:00:00Z",
        "expires_at": "2026-05-30T18:00:00Z",
        "grants": {
            "gmail.read": "allowed",
            "gmail.send": "requires_approval",
            "drive.write": "denied",
        },
        "budget": {"tokens_per_day": 200000, "dollars_per_day": 5.0},
        "approval_channel": "evaos://approvals/email-sorter-2026-05",
        "iss": "evaos-broker",
        "aud": "evaos-runtime",
    }
    payload.update(overrides)
    return payload


def test_capability_manifest_verifies_hs256_and_maps_decisions() -> None:
    manifest = verify_hs256_manifest(
        _jwt(_payload()),
        SECRET,
        now=datetime(2026, 5, 29, 19, 0, tzinfo=timezone.utc),
    )

    assert manifest.agent_id == "email-sorter-2026-05"
    assert manifest.owner_id == "andrew-main"
    assert manifest.budget.tokens_per_day == 200000
    assert manifest.budget.dollars_per_day == 5.0
    assert manifest.approval_channel == "evaos://approvals/email-sorter-2026-05"
    assert decision_for_tool(manifest, "gmail.read") == "allowed"
    assert decision_for_tool(manifest, "gmail.send") == "requires_approval"
    assert decision_for_tool(manifest, "drive.write") == "denied"
    assert decision_for_tool(manifest, "slack.post") == "denied"


def test_capability_manifest_rejects_bad_signature_algorithm_and_expiry() -> None:
    good_token = _jwt(_payload())
    bad_signature = good_token.rsplit(".", 1)[0] + "." + _b64url(b"bad-signature")
    with pytest.raises(CapabilityManifestError, match="signature"):
        verify_hs256_manifest(bad_signature, SECRET, now=datetime(2026, 5, 29, 19, 0, tzinfo=timezone.utc))

    with pytest.raises(CapabilityManifestError, match="algorithm"):
        verify_hs256_manifest(
            _jwt(_payload(), header={"alg": "none", "typ": "JWT"}),
            SECRET,
            now=datetime(2026, 5, 29, 19, 0, tzinfo=timezone.utc),
        )

    with pytest.raises(CapabilityManifestError, match="expired"):
        verify_hs256_manifest(_jwt(_payload()), SECRET, now=datetime(2026, 5, 31, tzinfo=timezone.utc))


def test_capability_manifest_rejects_non_ascii_segments_as_manifest_errors() -> None:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())

    with pytest.raises(CapabilityManifestError, match="base64url segment"):
        verify_hs256_manifest(f"{header}.é.invalid", SECRET)


def test_capability_manifest_rejects_invalid_claims() -> None:
    with pytest.raises(CapabilityManifestError, match="issuer"):
        verify_hs256_manifest(
            _jwt(_payload(iss="evil-broker")),
            SECRET,
            now=datetime(2026, 5, 29, 19, 0, tzinfo=timezone.utc),
        )
    with pytest.raises(CapabilityManifestError, match="audience"):
        verify_hs256_manifest(
            _jwt(_payload(aud="wrong-runtime")),
            SECRET,
            now=datetime(2026, 5, 29, 19, 0, tzinfo=timezone.utc),
        )
    with pytest.raises(CapabilityManifestError, match="grant"):
        verify_hs256_manifest(
            _jwt(_payload(grants={"gmail.send": "maybe"})),
            SECRET,
            now=datetime(2026, 5, 29, 19, 0, tzinfo=timezone.utc),
        )


def test_capability_manifest_summary_is_safe_for_workbench_and_agents() -> None:
    manifest = verify_hs256_manifest(
        _jwt(_payload()),
        SECRET,
        now=datetime(2026, 5, 29, 19, 0, tzinfo=timezone.utc),
    )

    summary = grant_summary(manifest)

    assert summary == {
        "agent_id": "email-sorter-2026-05",
        "owner_id": "andrew-main",
        "expires_at": "2026-05-30T18:00:00Z",
        "approval_channel": "evaos://approvals/email-sorter-2026-05",
        "budget": {"tokens_per_day": 200000, "dollars_per_day": 5.0},
        "grants": {
            "allowed": ["gmail.read"],
            "requires_approval": ["gmail.send"],
            "denied": ["drive.write"],
        },
    }
    assert "secret" not in json.dumps(summary).lower()
