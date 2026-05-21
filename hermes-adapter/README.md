# evaOS Desktop Bridge Hermes Adapter

Hermes uses the same customer Mac connector contract as OpenClaw. This adapter
is intentionally tiny: it does not create a second control backend, and it does
not expose generic shell, AppleScript, coordinates, or app-server mutation.

## Runtime contract

Set these on the customer VM after the Mac is paired. The wrapper automatically
sources `/root/.openclaw/evaos-desktop-bridge.env` when the variables are not
already present, so OpenClaw, Hermes, and direct support smokes all use the same
connector contract.

```bash
export EVAOS_DESKTOP_BRIDGE_URL="http://<mac-headscale-ip>:8765"
export EVAOS_DESKTOP_BRIDGE_TOKEN="<connector-token>"
```

Hermes tools should call `bin/evaos-desktop-bridge-command` with one of the
fixed connector command names supported by `/v1/commands`, for example:

```bash
hermes-adapter/bin/evaos-desktop-bridge-command customerMacStatus '{}'
hermes-adapter/bin/evaos-desktop-bridge-command customerMacIphoneMirroringStatus '{}'
hermes-adapter/bin/evaos-desktop-bridge-command customerMacAppFocus '{"app_name":"Safari"}'
```

Guarded commands default to dry-run at the connector layer. Live guarded actions
must include `{"dry_run":false,"approval_audit_id":"..."}` and must match a
prior local dry-run audit record on the Mac connector.

The wrapper returns connector JSON on stdout even for structured denials such as
blocked sensitive apps or missing approval ids. Network failures and malformed
responses still fail as hard command errors.

## Boundary

- OpenClaw remains the first native plugin path.
- Hermes uses this command wrapper or an MCP/tool config that shells to it.
- The command wrapper only posts fixed JSON to the paired connector URL.
- Customer-facing iPhone live gestures/messages require the same dry-run,
  approval, and matching audit-id contract as OpenClaw.
