# Support VM Mac/iPhone/Codex Canary Runbook

Status: support-only canary.

This runbook is for the internal support VM paired to an operator Mac through
Headscale. It is not a customer rollout path.

## Boundary

- Pair only the support VM to the operator Mac.
- Keep customer VMs out of this canary.
- Launch the Mac connector with `EVAOS_SUPPORT_CANARY_CONTROLS=1` only for this
  support test.
- Prefer Codex native remote-control readiness first. Use visible GUI fallback
  only if native remote-control is unavailable.
- iPhone/Bumble live actions are allowed only after exact same-turn approval.
- Every live command must have a matching dry-run audit id.

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
EVAOS_SUPPORT_CANARY_CONTROLS=1 \
  evaos-desktop-bridge serve --host <mac-headscale-ip> --port 8765
```

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

Readiness:

```bash
evaos-desktop-bridge customer-mac status --json
evaos-desktop-bridge codex app-server remote-control-status --json
evaos-desktop-bridge customer-mac iphone-mirroring status --json
evaos-desktop-bridge audit-tail --json --limit 10
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
EVAOS_SUPPORT_CANARY_CONTROLS=1 \
  evaos-desktop-bridge codex continue-thread \
  --json \
  --title "SDK Docs" \
  --dry-run
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
evaos-desktop-bridge customer-mac iphone-mirroring open-app \
  --json \
  --app-name Bumble \
  --dry-run
```

Dry-run gestures:

```bash
EVAOS_SUPPORT_CANARY_CONTROLS=1 \
  evaos-desktop-bridge customer-mac iphone-mirroring swipe-left --json --dry-run

EVAOS_SUPPORT_CANARY_CONTROLS=1 \
  evaos-desktop-bridge customer-mac iphone-mirroring swipe-right --json --dry-run

EVAOS_SUPPORT_CANARY_CONTROLS=1 \
  evaos-desktop-bridge customer-mac iphone-mirroring scroll \
  --json \
  --direction down \
  --dry-run
```

Live gesture: rerun the same command without `--dry-run` and include the
matching `--approval-audit-id`.

Approved message send:

```bash
EVAOS_SUPPORT_CANARY_CONTROLS=1 \
  evaos-desktop-bridge customer-mac iphone-mirroring send-approved-message \
  --json \
  --text "exact same-turn-approved message" \
  --recipient-context "exact same-turn-approved Bumble recipient/context" \
  --dry-run
```

Only after the human approves the exact recipient/context and exact text, rerun
without `--dry-run` and with the matching `--approval-audit-id`.

Blocked without separate approval:

- messages/calls outside this exact canary command
- purchases/payments
- account/security settings
- camera/mic
- arbitrary coordinates
- generic AppleScript/shell/desktop passthrough

## Evidence To Collect

Save the final audit tail:

```bash
evaos-desktop-bridge audit-tail --json --limit 30
```

Evidence must include:

- command
- target app/action
- dry-run audit id
- approval id
- timestamp
- redacted warnings/errors

## Stop/Revoke

- Use Workbench `Revoke Session` to clear the app session.
- Stop the connector process.
- Remove the support VM environment variables.
- Revoke iPhone Mirroring access from the Mac or iPhone if the test is complete.
- Rotate/remove the connector token if the support VM pairing is no longer
  needed.

