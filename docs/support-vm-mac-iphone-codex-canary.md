# Support VM Mac/iPhone/Codex Canary Runbook

Status: support-only canary.

This runbook is for the internal support VM paired to an operator Mac through
Headscale. It is not a customer rollout path.

## 2026-05-21 Support Canary Notes

Live support proof on 2026-05-21 reached:

- Mac joined Headscale as `eva-kira-support` on `100.64.0.4`.
- Support VM joined the same Headscale server as `evaos-support` on `100.64.0.9`.
- Headscale public route is `https://headscale.ecs.electricsheephq.com`.
- Headscale policy must be written with `headscale policy set -f ...` when
  `policy.mode` is database-backed. Editing `/etc/headscale/acl.yaml` alone is
  not enough.
- Support-only tags used for this canary:
  - support VM: `tag:customer`, `tag:support-vm`
  - operator Mac: `tag:support-mac`
- Narrow ACL used for the support canary:
  - `tag:support-vm` to `tag:support-mac:8765`, `:5900`, `:3283`
- After both nodes appeared in each other's netmap, one `tailscale ping` from
  the Mac to the VM warmed the direct path; then VM to Mac TCP `8765` worked.

Validated support VM commands:

- `customerMacStatus` returned `ok:true` with Accessibility and Screen Recording
  granted after the connector was restarted on the updated bridge code.
- `customerMacSnapshot` wrote a screenshot artifact under the local bridge
  state directory.
- `customerMacIphoneMirroringFocus` dry-run returned an audit id; rerunning
  with `dry_run:false` and the matching `approval_audit_id` focused iPhone
  Mirroring.
- The VM wrapper at `/usr/local/bin/evaos-desktop-bridge-command` sources
  `/root/.openclaw/evaos-desktop-bridge.env` when needed, so direct Hermes-style
  calls and OpenClaw service calls use the same connector URL/token contract.
- Golden cross-customer proof: `golden` could not `tailscale ping` or TCP connect
  to the support Mac connector at `100.64.0.4:8765`; `evaos-support` could.

Open release blocker found:

- TCC identity is now a v0.5.1 certification gate. macOS should show evaOS
  Workbench, evaOS Connector, or the bundled Peekaboo helper for Accessibility
  and Screen Recording. If it asks for Python, stop the customer canary and fix
  the helper/launch path before calling the build certified.
- Workbench beta now prefers a Workbench-managed connector process for normal
  setup. That path avoids the manual `screen` workaround and puts the signed
  bundled Peekaboo helper first on `PATH`. The LaunchAgent path remains for
  background/restart testing.
- OpenClaw support-agent proof is blocked by the support VM's expired
  `openai-codex` OAuth refresh. The plugin and connector path are installed, but
  the real agent turn fails before tool execution until the support VM auth is
  refreshed or a release-smoke model route is authorized.

## Boundary

- Pair only the support VM to the operator Mac.
- Keep customer VMs out of this canary.
- The `EVAOS_SUPPORT_CANARY_CONTROLS=1` flag is only for the Codex visible
  `continue` fallback. iPhone gestures now run through the same Workbench
  Full Access / Ask Permission control session as other customer tools.
- Prefer Codex native remote-control readiness first. Use visible GUI fallback
  only if native remote-control is unavailable.
- In Full Access mode, the new `desktop_*` / `iphone_*` tools can operate
  continuously. In Ask Permission mode, risky taps, swipes, typing, sends, and
  other high-impact actions require exact same-turn approval.

Apple documents iPhone Mirroring as a visible Mac app where the Mac can tap,
swipe, type, and use keyboard shortcuts while the iPhone is locked nearby. Apple
also documents that access can be revoked from the iPhone or Mac. Those user
controls are part of this canary boundary.

## Mac Setup

Grant permissions to the app or terminal that runs `evaos-desktop-bridge`:

- Accessibility
- Screen Recording if screenshots are needed

Start the connector on the Headscale interface:

```bash
evaos-desktop-bridge serve --host <mac-headscale-ip> --port 8765
```

Workbench can start the beta connector from the app. This is the recommended
friendly beta path: open Workbench, use **Turn On Mac Access**, then grant
Accessibility/Screen Recording to evaOS Workbench, evaOS Connector, or the
Peekaboo helper macOS shows in Privacy & Security.

Workbench can also test the LaunchAgent-backed connector:

```bash
evaos-desktop-bridge connector-service start --json
evaos-desktop-bridge connector-service status --json
```

Use the LaunchAgent path for service/restart testing. Use the Workbench-managed
connector for v0.5.1 certification so the active control path uses the packaged
evaOS/Peekaboo helper instead of a raw Python permission owner.

If the operator Mac is on a different tailnet than the support VM, keep the
connector loopback-only and use a temporary SSH reverse tunnel from the Mac to
the support VM instead:

```bash
.venv/bin/python -m evaos_desktop_bridge.cli serve --host 127.0.0.1 --port 8766

ssh -N \
  -o ExitOnForwardFailure=yes \
  -R 127.0.0.1:8766:127.0.0.1:8766 \
  root@<support-vm-public-ip>
```

The reverse tunnel requires `AllowTcpForwarding yes` on the support VM. Keep it
limited to the support canary and restore the previous sshd setting afterward if
the VM should not retain tunnel support.

Token:

```bash
cat "$HOME/Library/Application Support/evaos-desktop-bridge/connector.token"
```

Put only that token on the support VM. Do not copy it into customer VM images or
Golden provisioning.

## Support VM Environment

```bash
export EVAOS_DESKTOP_BRIDGE_URL=http://<mac-headscale-ip>:8765
export EVAOS_DESKTOP_BRIDGE_TOKEN=<connector-token>
```

For release certification, prefer the repo-native QA harness instead of manual
one-off curls. It stores pass/fail/skipped rows, audit ids, engine provenance,
snapshot ids, and screenshot evidence under the Lexar QA run folder:

```bash
python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface connector \
  --suite all \
  --version-under-test 0.5.1

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface openclaw \
  --suite all \
  --version-under-test 0.5.1

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface hermes \
  --suite all \
  --version-under-test 0.5.1
```

Run the kill-switch suite once at the end of the certification pass, after the
connector/OpenClaw/Hermes `all` suites. It intentionally leaves remote control
blocked until Workbench starts a new control session:

```bash
python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface connector \
  --suite kill_switch \
  --version-under-test 0.5.1
```

See `docs/evaos-workbench-qa-canary.md` for optional real-world app scenarios
and the release certification rule.

The OpenClaw plugin reads those environment variables directly. The bridge CLI
itself is local-first; when testing from a bare support shell, call the
connector HTTP endpoint:

```bash
TOKEN="$(cat /root/.evaos-desktop-bridge-connector.token)"
curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacStatus","params":{}}'
```

Readiness:

```bash
curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacStatus","params":{}}'

curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"codexAppServerRemoteControlStatus","params":{}}'

curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacIphoneMirroringStatus","params":{}}'
```

The Workbench Bridge panel should show:

- Desktop Bridge
- Customer Mac
- iPhone Mirroring
- Codex Remote Control
- Screen Sharing
- capabilities
- audit tail

## Codex “SDK Docs” Continue Test

Preferred path:

1. Check native remote-control status:

   ```bash
   evaos-desktop-bridge codex app-server remote-control-status --json
   ```

2. If native remote-control is available, use the native Codex remote-control
   workflow to continue the `SDK Docs` thread.

Fallback path:

```bash
curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"codexContinueThread","params":{"title":"SDK Docs","dry_run":true}}'
```

If the dry-run identifies exactly one visible thread and the human approves,
rerun the exact command without `--dry-run` and with
`--approval-audit-id <dry-run-audit-id>`.

The fallback only accepts the exact prompt `continue`.

## iPhone Mirroring/Bumble Canary

Start iPhone Mirroring on the Mac. Unlock/authenticate through the visible Mac
flow if prompted.

Dry-run open Bumble:

```bash
curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacIphoneMirroringOpenApp","params":{"app_name":"Bumble","dry_run":true}}'
```

Dry-run gestures:

```bash
curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacIphoneMirroringSwipeLeft","params":{"dry_run":true}}'

curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacIphoneMirroringSwipeRight","params":{"dry_run":true}}'

curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacIphoneMirroringScroll","params":{"direction":"down","dry_run":true}}'
```

Live legacy gesture: rerun the same command without `--dry-run` and include the
matching approval id. For connector HTTP calls, live guarded actions must set
`"dry_run": false`; omitting `dry_run` intentionally defaults back to dry-run.
For the new `iphone_swipe` tool, Full Access mode does not require approval;
Ask Permission mode does.

Approved message send:

```bash
curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacIphoneMirroringSendApprovedMessage","params":{"text":"exact same-turn-approved message","recipient_context":"exact same-turn-approved Bumble recipient/context","dry_run":true}}'
```

Only after the human approves the exact recipient/context and exact text, rerun
without `--dry-run` and with the matching `--approval-audit-id`.

Blocked without separate approval:

- messages/calls outside this exact canary command
- purchases/payments
- account/security settings
- camera/mic
- coordinates outside the audited Workbench connector tools
- generic AppleScript/shell/desktop passthrough

## Evidence To Collect

Save the final audit tail:

```bash
curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"auditTail","params":{"limit":30}}'
```

Evidence must include:

- command
- target app/action
- dry-run audit id
- approval id
- timestamp
- redacted warnings/errors

## Stop/Revoke

- Use Workbench `Sign Out` to clear the app session.
- Stop the connector process.
- Remove the support VM environment variables.
- Revoke iPhone Mirroring access from the Mac or iPhone if the test is complete.
- Rotate/remove the connector token if the support VM pairing is no longer
  needed.
