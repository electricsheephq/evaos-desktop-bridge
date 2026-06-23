# Computer-Use Helper IPC Contract

Issue: `#163`
Parents: `#121`, `#129`, `#134`

This is the local helper seam for moving narrow, high-frequency visible Mac
actions out of per-action Python subprocesses and into a resident process. It
starts with the authenticated IPC contract from `#163` and adds the first `#121`
live route: helper-owned per-process mouse actions for the existing
`customer_mac.desktop_click`/scroll/drag fallback path when explicitly enabled.
Issue `#123` adds the first semantic Accessibility action lane for native Mac
controls already present in a fresh desktop snapshot. AX routing is still
fixed-name only; it is not raw Accessibility passthrough.
Issue `#124` retires the previous global event-tap fallback: `mouse_action`
now requires an audited target process identity and posts mouse/scroll events
with `CGEventPostToPid`.
Issue `#122` adds the Workbench-owned launch/preflight contract so the beta path
does not ask customers or test agents to approve a raw Python or terminal TCC
identity. The helper accepts the Workbench identity only when the claimed
bundle/app marker matches and the helper's parent process path is inside that
app bundle.

It is still not VNC, SSH, AppleScript passthrough, generic computer-use,
generic shell, Codex app-server mutation, or an OpenClaw control socket.

## Contract

- Schema version: `evaos.helper_ipc.v1`
- Framing: four-byte big-endian payload length followed by UTF-8 JSON.
- Maximum payload: 64 KiB.
- Authorization: per-launch capability token plus peer-uid match.
- Allowed commands in this slice:
  - `ping`
  - `mouse_action` with action `click`, `scroll`, or `drag`
  - `ax_action` with fixed actions `press`, `set_value`,
    `set_selected_text`, or `menu`
- Request envelope: `request_id` must be a non-empty string and `payload`
  must be a JSON object. `mouse_action` and `ax_action` additionally require an
  `audit_id` from the bridge actuation path; `ping` may omit it.

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
    "helper_mode": "resident_local",
    "actuation_enabled": true,
    "permission_preflight": {
      "ok": true,
      "enforced": true,
      "identity": {
        "expected_bundle_ids": [
          "com.electricsheephq.EvaDesktop",
          "com.evaos.workbench"
        ],
        "responsible_bundle_id": "com.evaos.workbench",
        "status": "workbench_signed_app"
      },
      "permissions": {
        "accessibility": {
          "status": "granted"
        },
        "screen_recording": {
          "status": "granted"
        }
      }
    }
  },
  "warnings": [],
  "errors": []
}
```

Responses must not echo the capability token.

Mouse action requests are deliberately structured. The bridge sends only an
audited target `pid`/`process_name` plus the action-specific coordinates,
scroll direction/amount, or drag endpoints needed by the existing Mac fallback
primitives. The helper rejects missing audit ids, missing or stale target
process identity, browser web-content targets, unknown actions, and malformed
numeric payloads before posting per-process events.

AX action requests are also deliberately structured. The bridge sends a target
`pid` plus a semantic role/name/identifier/index path from the latest AX
snapshot. The helper resolves that path inside the target app and performs only
the fixed action requested. It refuses raw AX action names or attributes,
returns browser `AXWebArea` targets as inert, blocks secure and non-text roles,
checks text attributes are settable when the platform exposes that signal, caps
value writes, returns hashes instead of raw values, and rechecks the target
process name when the snapshot supplied one.

## Local Run And Opt-In

The customer beta path is Workbench-owned: click **Turn On Mac Access** in
evaOS Workbench. Workbench starts `helper run` from the signed app bundle,
passes `EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID`,
`EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH`, and
`EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS=1`, then starts the connector
with `EVAOS_DESKTOP_BRIDGE_USE_HELPER=1` plus the managed socket/token paths.
The helper also checks its parent process path; a terminal cannot become a
trusted Workbench helper merely by setting those environment variables.

For diagnostics only, a developer can still start a local helper with a short
private Unix socket path and rotated per-launch token file. The default socket
lives under `/tmp` to stay below macOS `AF_UNIX` pathname limits; the token
remains in the bridge state directory unless overridden.

```bash
evaos-desktop-bridge helper run
```

Health check:

```bash
evaos-desktop-bridge helper ping --json
```

The customer Mac adapter only uses the helper when explicitly opted in:

```bash
export EVAOS_DESKTOP_BRIDGE_USE_HELPER=1
export EVAOS_DESKTOP_BRIDGE_HELPER_SOCKET="/tmp/evaos-helper-$(id -u).sock"
export EVAOS_DESKTOP_BRIDGE_HELPER_TOKEN_FILE="$HOME/Library/Application Support/evaos-desktop-bridge/computer-use-helper.token"
```

If helper opt-in is enabled but the socket/token is unavailable, stale, or
unsafe to read, live mouse actions fail closed instead of silently falling back
to per-action Python.

If enforced preflight is enabled and macOS reports missing or unknown
Accessibility/Screen Recording grants, `mouse_action` returns
`permission_missing` with System Settings deep-links. If the helper was not
launched by Workbench's signed app identity, it returns
`helper_identity_unverified`. In both cases no process event is posted.

## Safety Boundary

The helper remains dumb hands. Policy, redaction, approval, sensitive-app blocks, customer control mode, and audit decisions stay above the seam in the bridge process.

For this foundation slice, the helper enforces the local socket boundary:
rotated private token file, peer-uid match, strict framing, exact command
allowlist, and a required bridge-provided audit id before `mouse_action`.
Accepted helper sockets have read timeouts so a stalled local peer cannot wedge
later helper actions.

Issue `#129` closes the current audited command-envelope requirement for
helper-owned actuation routes: the bridge writes a durable `helper.mouse_action`
or `helper.ax_action` record with `audit_phase = authorized_dispatch` before it
sends the IPC frame, passes that exact `audit_id` in the helper request, then
writes a separate completion record with `audit_phase = completion` after the
helper returns or fails. If the bridge process dies during dispatch, the
authorized helper request is still present in the append-only audit log. The
helper itself remains dumb hands and does not duplicate policy, approval, or
redaction logic.

This slice deliberately rejects broad actuation and escape hatches, including
raw AX primitive passthrough, iPhone tap/type, shell, Python, AppleScript, Codex
app-server mutation, or generic computer-use requests. Future #121/#129 work
must keep the same direction: authenticate the sender first, check policy
before the seam, then audit every actuation request before a helper can touch
the Mac.

The signed-identity track is intentionally narrow. Workbench may launch the
resident helper and connector, but the helper still does not accept generic
desktop control. CLI-launched helpers remain useful for diagnostics, not release
certification.

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
- exact allowed-command lock of `{"ping", "mouse_action", "ax_action"}`;
- unsafe token-file rejection, per-launch token rotation, and regular-file
  socket path refusal;
- local Unix-socket server/client ping, bad-token failure, required audit id
  for `mouse_action`, and helper-routed desktop click/scroll/drag behavior
  with no per-action Python fallback;
- helper permission preflight identity/grant reporting, fail-closed
  `permission_missing`, fail-closed `helper_identity_unverified`, and no
  process-event execution when enforced preflight fails.
- bridge-side helper actuation audit records for both authorized dispatch and
  completion/failure, with the dispatch audit id sent through the helper IPC
  envelope.
- semantic AX dispatch that requires an audit id, avoids token echo, blocks raw
  AX/web/secure-field bypasses, and routes desktop click/set-value through the
  helper without Python fallback.
- per-process mouse dispatch that requires target pid/process identity,
  rejects browser web-content targets as inert, and avoids global event taps.
