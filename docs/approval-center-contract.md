# evaOS Approval Center Contract

Issue: `#144`

Approval Center is the human-in-the-loop surface for risky agent actions after a
Capability Manifest grant returns `requires_approval`. It is separate from Mac
TCC permissions and customer Full Access / Ask Permission desktop control.

This slice defines the Workbench-local contract and UI surface only. It does not
add broker approval endpoints, runtime resolution callbacks, policy-row writes,
notifications, or live allow/deny submission.

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
- disabled decision buttons until broker decision endpoints land.

## Deferred Slices

- broker `POST /api/v1/approvals/request`
- broker `GET /api/v1/approvals/pending`
- broker `POST /api/v1/approvals/{id}/decide`
- OpenClaw `requireApproval` resolution wiring
- Hermes `_ApprovalEntry` resolution wiring
- `allow-always` policy-row writes
- local notifications for pending or timed-out approvals
- manual spoofed-recipient QA against live broker/runtime payloads
