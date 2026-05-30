# evaOS Approval Center Contract

Issue: `#144`

Approval Center is the human-in-the-loop surface for risky agent actions after a
Capability Manifest grant returns `requires_approval`. It is separate from Mac
TCC permissions and customer Full Access / Ask Permission desktop control.

The Workbench slice consumes authenticated broker pending approvals, submits
`allow-once` / `deny` decisions, and can notify the operator when new pending
approvals arrive away from the Approval Center. It does not add runtime
resolution callbacks or durable `allow-always` policy-row writes.

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
- `created_at`
- `source_pointer`
- optional `audit_id`

`WorkbenchApprovalPreviewBuilder` derives destination previews from allowlisted
payload keys. It intentionally ignores display-only fields such as
`display_name` and `display_url` when choosing the primary destination.
Workbench also derives decoded broker-shaped rows from `action_payload` instead
of trusting a supplied `destination_preview`.

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
- provenance pointer and created timestamp;
- `allow-once` and `deny` decision buttons when the row has actual destination
  evidence.

`allow-always` remains visible but withheld until policy rows are
destination-constrained enough for recipient-bearing tools.

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

## Deferred Slices

- OpenClaw `requireApproval` resolution wiring
- Hermes `_ApprovalEntry` resolution wiring
- destination-constrained `allow-always` policy-row writes
- timed-out approval notifications
- final manual spoofed-recipient QA against live runtime payloads
