# Issue Completion Matrix

Milestone: `MVP: Codex Desktop visible harness`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#1` Bootstrap shared snapshot schema and policy core | Schema docs, types, redaction/cap tests | JSON envelope, command metadata, policy allowlist, redaction/cap tests, schema docs |
| `#2` Codex passive observer status/snapshot | `status`, `focus`, `snapshot`, `ax-tree`, capped JSON | CLI commands plus `frontmost`, `windows`, `inspect`; graceful TCC errors |
| `#3` Visible thread inventory | Compare output to UI, cap output, redact paths | `codex threads --json --max-items`, deterministic `visible_id`, AX-only inventory |
| `#4` Guarded visible thread focus action | dry-run and audit, no typing/sending | `codex select-thread --thread-id ... --dry-run`, stale-target checks, provenance audit |
| `#5` Eva announcement queue contract | sample payloads and routing policy | local JSONL queue, `queue append/list`, docs and sample event schema |
| `#6` Audit/provenance | timestamp, target app, source, action/dry-run, result | append-only audit JSONL with command metadata and provenance fields |
| `#7` macOS TCC docs and threat model | setup guide and threat model | `docs/macos-permissions.md`, `docs/threat-model.md`, README safety posture |
| `#8` Claude Desktop spike | research note, no implementation | `docs/claude-desktop-spike.md` |

## Verification

```bash
python3 -m pytest -q
git diff --check
evaos-desktop-bridge --help
evaos-desktop-bridge codex --help
```

Manual macOS checks remain optional and depend on Codex Desktop being running/frontmost with TCC permissions granted.

## 0.6.5 Deep Release Delta

Milestone: `Codex Desktop App-Server Control`

| Area | Status | Evidence |
| --- | --- | --- |
| Fresh app-server protocol handshake | Implemented | `CodexJsonRpcClient` sends `initialize`, waits for result, sends `initialized`, preserves notifications and empty results |
| Transport support | Implemented | stdio default, explicit loopback websocket, explicit proxy; non-loopback websocket URLs are rejected |
| Read-only connection status | Implemented | `codex connections status --json` reports Desktop CLI, app-server handshake, daemon, control sockets, websocket, live notifications, and safety flags |
| Loaded threads/live notifications | Implemented, live acceptance pending | `loaded-threads` and `subscribe` commands with caps/redaction; issue #136 still requires a non-empty `thread/loaded/list` result from a visible Codex Desktop thread plus streamed turn events |
| Guarded remote control | Implemented, live acceptance pending | `start-turn`, `steer-turn`, `interrupt-turn` default to dry-run; live mode requires `--live --confirm --source-audit-id` from a matching dry-run and loaded-thread verification |
| #136 live Codex controller gate | Blocked by local Codex loaded-thread state | Current Codex CLI 0.133.0 smoke returned `thread/loaded/list` count 0, so PR #135 must not merge until an approved `start-turn` visibly appears in Codex Desktop and `subscribe` observes turn progress |
| OpenClaw wrapper tools | Implemented | fixed named tools for connections, live status, loaded threads, and start/steer/interrupt; still no generic app-server RPC passthrough |
| Workbench status formatter | Implemented | Workbench reads `codex connections status` and the current `remote_control_command`, `daemon`, and `control_sockets` shape |
| 0.6.5 release canary | Partial, evidence retained | Connector/OpenClaw/Hermes all-surface canaries reached 33/44 before harness fix; desktop scenario rerun passed 5/5; iPhone Calculator launch remains a tuning issue; kill-switch final passed 3/3; QA canaries are not a substitute for the #136 live Codex controller acceptance |
