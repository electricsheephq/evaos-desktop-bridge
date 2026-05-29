# Computer-Use Helper IPC Contract

Issue: `#163`
Parents: `#121`, `#129`, `#134`

This is the contract-only first slice for the future persistent computer-use helper. It does not start a daemon, route Mac/iPhone actions, replace foreground controls, or expose a new OpenClaw control surface.

## Contract

- Schema version: `evaos.helper_ipc.v1`
- Framing: four-byte big-endian payload length followed by UTF-8 JSON.
- Maximum payload: 64 KiB.
- Authorization: per-launch capability token plus peer-uid match.
- Allowed command in this slice: `ping`.
- Request envelope: `request_id` must be a non-empty string, `payload`
  must be a JSON object, and `audit_id` must be a non-empty string when
  present.

Example request:

```json
{
  "schema_version": "evaos.helper_ipc.v1",
  "request_id": "req-1",
  "command": "ping",
  "capability_token": "<per-launch-token>",
  "audit_id": "audit-safe",
  "payload": {
    "client": "bridge"
  }
}
```

Example response:

```json
{
  "schema_version": "evaos.helper_ipc.v1",
  "request_id": "req-1",
  "ok": true,
  "timestamp": "2026-05-29T00:00:00Z",
  "data": {
    "command": "ping",
    "helper_mode": "contract_only",
    "actuation_enabled": false
  },
  "warnings": [],
  "errors": []
}
```

Responses must not echo the capability token.

## Safety Boundary

The helper remains dumb hands. Policy, redaction, approval, sensitive-app blocks, customer control mode, and audit decisions stay above the seam in the bridge process.

This slice deliberately rejects every actuation-like command, including desktop click/type, iPhone tap/type, shell, Python, AppleScript, Codex app-server mutation, or generic computer-use requests. Future #121/#129 work must keep the same direction: authenticate the sender first, check policy before the seam, then audit every actuation request before a helper can touch the Mac.

## Tests

`tests/test_helper_ipc.py` covers:

- successful authorized `ping`;
- no token echo in responses;
- schema-version rejection;
- malformed request envelope rejection;
- missing/wrong capability token rejection;
- missing/invalid peer policy rejection;
- wrong peer uid rejection;
- oversized frame rejection before JSON parsing;
- malformed in-bounds frame rejection, including short prefix, length mismatch,
  invalid JSON, and non-object JSON payloads;
- unknown/actuation-like command rejection;
- exact allowed-command lock of `{"ping"}`.
