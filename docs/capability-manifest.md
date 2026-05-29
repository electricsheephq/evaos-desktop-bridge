# evaOS Capability Manifest Contract

Issue: `#143`

The Capability Manifest is the tool-side authorization primitive for evaOS
agents. The broker issues a short-lived HS256 JWT per agent. Workbench,
OpenClaw, and Hermes consume the same claims before a tool call crosses the
runtime boundary.

This slice defines and verifies the local contract only. It does not add
broker endpoints, OpenClaw/Hermes runtime plugins, Approval Center decisions,
or budget enforcement.

## JWT Claims

```json
{
  "agent_id": "email-sorter-2026-05",
  "owner_id": "andrew-main",
  "issued_at": "2026-05-29T18:00:00Z",
  "expires_at": "2026-05-30T18:00:00Z",
  "grants": {
    "gmail.read": "allowed",
    "gmail.send": "requires_approval",
    "calendar.create": "allowed",
    "drive.write": "denied",
    "slack.post": "requires_approval"
  },
  "budget": {
    "tokens_per_day": 200000,
    "dollars_per_day": 5.0
  },
  "approval_channel": "evaos://approvals/email-sorter-2026-05",
  "iss": "evaos-broker",
  "aud": "evaos-runtime"
}
```

Allowed grant decisions are exactly:

- `allowed`
- `requires_approval`
- `denied`

Missing tool grants fail closed as `denied`.

## Local Verifiers

Python bridge code exposes `verify_hs256_manifest`, `decision_for_tool`, and
`grant_summary` in `evaos_desktop_bridge.capability_manifest`.

Workbench core exposes `WorkbenchCapabilityManifestVerifier` and
`WorkbenchCapabilityManifestClaims`. The verifier checks:

- three-part JWT shape
- `alg == HS256`
- HMAC-SHA256 signature
- issuer `evaos-broker`
- audience `evaos-runtime`
- non-empty `agent_id`, `owner_id`, `approval_channel`, and grants
- `issued_at <= now <= expires_at`

`WorkbenchCapabilityManifestStore` caches the signed manifest token in the
Workbench Keychain service `com.electricsheephq.EvaDesktop.capabilities`, using
the account `capability-manifest`. This PR does not add the future live broker
fetch/refresh path yet.

## Runtime Fit

OpenClaw should map decisions into the existing trusted-tool-policy hook:

- `allowed`: proceed
- `requires_approval`: return `requireApproval` with `allow-once`,
  `allow-always`, and `deny`
- `denied`: block before the provider/tool call

Hermes should map decisions into its existing `pre_tool_call` hook:

- `allowed`: proceed
- `requires_approval`: enqueue the existing gateway approval entry
- `denied`: return a block result before `_invoke_tool`

Workbench should render safe summaries only: agent id, owner id, expiry,
approval channel, budget, and grouped tool names. It must not render signing
secrets, raw provider tokens, auth DB paths, or session DB contents.

## Deferred Slices

- M2a: broker endpoint and Supabase policy rows
- M2b: OpenClaw verifier plugin
- M2c: Hermes verifier plugin
- M2d: Workbench broker fetch/cache integration
- M5: Approval Center decision UI consuming `requires_approval`
- M6: per-agent usage and budget enforcement
