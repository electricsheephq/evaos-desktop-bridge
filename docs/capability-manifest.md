# evaOS Capability Manifest Contract

Issue: `#143`

The Capability Manifest is the tool-side authorization primitive for evaOS
agents. The broker issues a short-lived HS256 JWT per agent. Workbench,
OpenClaw, and Hermes consume the same claims before a tool call crosses the
runtime boundary.

The current Workbench slice fetches and caches broker-issued manifests from the
authenticated Cortex broker path, but it remains a display/cache client. It does
not embed the broker signing secret, add runtime enforcement, add
OpenClaw/Hermes runtime plugins, submit Approval Center decisions, or enforce
budgets.

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

Destination-constrained Approval Center decisions are not represented as global
`allowed` grants in this claim. Until OpenClaw and Hermes consume destination
fingerprints directly, those policy rows continue to resolve as
`requires_approval` so a durable recipient/URL-specific approval cannot widen
into blanket tool access.

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
the account `capability-manifest`. Cache state is cleared on sign-out, broker
401/403, customer switch, and Workbench broker-client rebuild.

## Workbench Broker Fetch

Workbench requests manifests with the signed-in desktop session:

```http
GET https://cortex-electricsheep.fly.dev/api/v1/capabilities/{agent_id}
Authorization: Bearer <desktop_session>
Accept: application/json
```

The response shape accepted by Workbench is:

```json
{
  "ok": true,
  "agent_id": "openclaw",
  "owner_id": "andrew-main",
  "manifest_jwt": "<signed jwt>",
  "expires_at": "2026-05-30T18:00:00Z",
  "approval_channel": "evaos://approvals/openclaw",
  "grant_count": 3,
  "budget": { "tokens_per_day": 200000, "dollars_per_day": 5.0 },
  "safe_summary": {
    "agent_id": "openclaw",
    "owner_id": "andrew-main",
    "expires_at": "2026-05-30T18:00:00Z",
    "approval_channel": "evaos://approvals/openclaw",
    "budget": { "tokens_per_day": 200000, "dollars_per_day": 5.0 },
    "grants": {
      "allowed": ["gmail.read"],
      "requires_approval": ["gmail.send"],
      "denied": ["drive.write"]
    }
  }
}
```

Workbench validates that the response is successful, has a non-empty token,
agent, owner, approval channel, and non-zero grant count when `grant_count` is
present. The raw `manifest_jwt` is saved to Keychain only and is not rendered.

Workbench renders grant metadata only from `safe_summary`. If the broker returns
a valid token without `safe_summary`, Workbench stores the token and shows
`Cached: summary pending`. This avoids shipping the broker HS256 signing secret
inside the macOS app while still allowing the broker to phase in safe display
metadata.

HTTP 401/403 clears the signed-in Workbench session and manifest cache. HTTP 404
clears the manifest cache and reports `No policy for agent`. Other failures
leave the last Keychain write untouched but clear rendered summary state and
report `Unavailable`.

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
secrets, raw manifest JWTs, raw provider tokens, auth DB paths, or session DB
contents.

## Deferred Slices

- M2a: broker endpoint and Supabase policy rows
- M2b: OpenClaw verifier plugin
- M2c: Hermes verifier plugin
- M2d: Workbench broker fetch/cache integration
- M5: Approval Center decision UI consuming `requires_approval`
- M6: per-agent usage and budget enforcement
