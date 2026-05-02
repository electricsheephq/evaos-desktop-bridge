# Eva/OpenClaw Announcement Queue

The bridge writes local JSONL announcement events for Eva/OpenClaw to consume. This is the local contract for the future brain/relay layer; it is not a hosted push service.

## Kinds

- `idle`: Codex appears idle or ready.
- `approval_needed`: visible/app-server state indicates operator review may be needed.
- `done`: a watched task appears completed.
- `error`: bridge or desktop state indicates an error.
- `attention`: general operator attention is useful.

## Commands

```bash
evaos-desktop-bridge queue append --json --kind attention --source-audit-id audit-...
evaos-desktop-bridge queue list --json --limit 20
```

Each event references a bridge `audit_id` so an agent can trace the observation or action that produced it.

## Event Shape

```json
{
  "schema_version": "2026-05-02.mvp1",
  "queue_id": "queue-...",
  "timestamp": "2026-05-03T00:00:00Z",
  "kind": "attention",
  "source_audit_id": "audit-...",
  "message": "Check Codex",
  "payload": {},
  "status": "pending"
}
```

All queue payloads are redacted before writing.
