# evaOS Approval Center Contract

Issue: `#144`

Approval Center is the human-in-the-loop surface for risky agent actions after a
Capability Manifest grant returns `requires_approval`. It is separate from Mac
TCC permissions and customer Full Access / Ask Permission desktop control.

The Workbench slice consumes authenticated broker pending approvals, submits
`allow-once` / `deny` decisions, can notify the operator when new pending
approvals arrive away from the Approval Center, and may submit `allow-always`
only when the row has durable destination evidence. Broker rows include an
`expires_at` deadline; Workbench renders that deadline and emits a separate
expiring notification for already-surfaced rows when the operator is away.

Issue `#241` adds the runtime-resolution leg: Workbench decisions carry a
normalized destination proof, source pointer, and audit pointer back to the
broker so OpenClaw/Hermes can resolve the matching pending action and return a
runtime-result record.

## Required Preview

Every approval row must show the actual destination before a human can decide.
Display names, model summaries, and branded labels are not sufficient.

Examples:

- email: actual recipient email, subject, and capped body excerpt
- message: actual channel or recipient id plus capped message excerpt
- URL/fetch: actual URL and host
- file/delete/export: actual file path or export destination
- purchase/payment: merchant or payment target plus amount
- secret access: secret name or id, never the secret value
- budget or permission change: actual cap/scope/permission

If the runtime omits the actual destination, Workbench marks the row as not
actionable and tells the runtime to resubmit with the missing destination
fields.

## Workbench Types

`WorkbenchApprovalRequest` captures:

- `id`
- `owner_id`
- `agent_id`
- `tool_name`
- `risk_class`
- `action_payload`
- `destination_preview`
- optional `destination_proof`
- `allow_always_supported`
- `created_at`
- optional `expires_at`
- `source_pointer`
- optional `audit_id`

`WorkbenchApprovalPreviewBuilder` derives destination previews from allowlisted
payload keys. It intentionally ignores display-only fields such as
`display_name` and `display_url` when choosing the primary destination.
Workbench also derives decoded broker-shaped rows from `action_payload` instead
of trusting a supplied `destination_preview`.

`WorkbenchApprovalDestinationProof` is the decision-safe proof object. It
includes `kind`, `fingerprint`, `summary`, `source`, and optional
`source_pointer`. Workbench derives this proof only from the strict
actual-destination preview, never from display-only names or UI labels. Rows
with missing, redacted, or malformed destinations have no proof. `deny` remains
available for those rows; `allow-once` and `allow-always` fail closed. If the
broker supplies a proof object that does not match the preview-derived
fingerprint, Workbench replaces it with its own proof before submitting a
decision. Fingerprints are kind-aware: URL scheme/host are canonicalized while
path/query case stays exact; email domains are canonicalized while local parts
stay exact; file paths, secret names, permission scopes, and message targets
stay exact.

The initial allowlist is intentionally strict:

- email uses `recipient_email` or `actual_recipient_email` and requires a single
  parseable email address;
- message uses `recipient_id`, `channel_id`, `actual_recipient_id`, or
  `actual_channel_id`;
- URL/fetch uses `url`, `target_url`, or `actual_url` and requires an absolute
  `http`/`https` URL with a host.

`WorkbenchApprovalCenterSummary` reports empty/pending state for the Workbench
shell.

## Workbench UI

`ApprovalCenterView` is feature-flagged by `approval_center`, default off. It
renders pending approval request cards with:

- risk class;
- agent id and tool name;
- actual destination preview;
- capped body/message excerpt when present;
- deadline when the broker includes `expires_at`;
- provenance pointer and created timestamp;
- `allow-once` and `deny` decision buttons when the row has actual destination
  evidence.
- `allow-always` only when the broker can write a destination-constrained
  durable policy (`allow_always_supported: true`), and the preview has no
  warning or redacted destination fields and has a destination proof. Older
  brokers that omit the flag fail closed and keep the durable button hidden.

The paired broker change for this Workbench contract is
`electricsheephq/electric-sheep#2069`. That backend is responsible for deriving
a destination kind, fingerprint, and summary from the server-side approval
payload before resolving the request. Credential-bearing or otherwise redacted
URLs fail closed and remain one-call-only.

## Runtime Resolution

When the operator decides an approval, Workbench posts to
`/api/v1/approvals/{approval_id}/decide` with:

- `decision`
- `scope`
- `destination_proof`
- `request_source_pointer`
- `request_audit_id`

The broker/runtime response may include a `runtime_result` object with status,
runtime, message, source pointer, and audit id. Workbench uses that result to
show the operator that the pending OpenClaw/Hermes action resolved instead of
only hiding the row.

Live runtime consumption rules:

- `allow-once` resolves only the matching pending request.
- `deny` resolves or rejects the matching pending request even when destination
  proof is missing.
- `allow-always` may write only a destination-constrained policy row matching
  the proof fingerprint and request provenance.
- spoofed display names, supplied `destination_preview` fields, or mismatched
  proof objects do not widen the allowed destination.

## Local Notifications

When signed in and the feature flag is enabled, Workbench keeps a model-owned
broker polling loop active. The loop polls every 5 seconds while Approval Center
is visible and every 15 seconds while the operator is elsewhere in the app.

If a new pending approval appears while Approval Center is not visible,
Workbench requests local notification authorization if needed and emits one
notification for that approval id. Notification text includes only the tool
name, risk class, and actual destination. It intentionally omits message body
excerpts and raw payload values so macOS notification banners do not leak full
approval payloads.

Rows seen while Approval Center is visible are marked as already surfaced, and
resolved or disappeared rows are pruned from pending notification state to avoid
duplicate banners.

If a previously surfaced row remains pending and its `expires_at` deadline is
within the local warning window, Workbench emits one additional
`Approval expiring` notification. The expiring notification uses a separate
dedupe id from the initial `Approval needed` banner, includes only the remaining
time plus the same provenance pointers, and does not include raw payload values.

## Deferred Slices

- final manual spoofed-recipient QA against live runtime payloads
