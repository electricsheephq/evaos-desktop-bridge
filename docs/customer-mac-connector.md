---
title: "Customer Mac Connector V1"
status: active-canary
created: 2026-05-20
---

# Customer Mac Connector V1

## Purpose

The connector lets a paired customer VM ask the customer's Mac for small,
audited desktop observations and named visible actions. It is not VNC, SSH,
Screen Sharing enablement, AppleScript passthrough, or a generic remote desktop.

The intended production path is:

```text
OpenClaw tool on customer VM
  -> Headscale ACL to paired Mac
  -> evaos-desktop-bridge connector
  -> allowlisted local CLI command
  -> redacted JSON envelope + local audit record
```

The VM never receives public VNC, SSH, CDP, or generic shell access to the Mac.

Support-only canary note: live iPhone gestures and approved message sends are
disabled unless the Mac connector process is launched with
`EVAOS_SUPPORT_CANARY_CONTROLS=1`. Customer connectors must leave that variable
unset.

## Local Connector Server

Run locally for development:

```bash
evaos-desktop-bridge serve --host 127.0.0.1 --port 8765
```

On first start, the connector creates a per-user bearer token at:

```text
~/Library/Application Support/evaos-desktop-bridge/connector.token
```

Run for a paired tailnet interface only after Headscale ACLs are configured:

```bash
evaos-desktop-bridge serve \
  --host <mac-headscale-ip> \
  --port 8765
```

Health check:

```bash
curl http://127.0.0.1:8765/health
```

Command endpoint:

```bash
TOKEN="$(cat "$HOME/Library/Application Support/evaos-desktop-bridge/connector.token")"
curl -sS http://127.0.0.1:8765/v1/commands \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacStatus","params":{}}'
```

All command requests require:

```text
Authorization: Bearer <connector-token>
```

## OpenClaw Plugin Remote Mode

The OpenClaw plugin can call either a local bridge CLI or a remote connector.

Local mode:

```bash
export EVAOS_DESKTOP_BRIDGE_BIN=/usr/local/bin/evaos-desktop-bridge
```

Remote paired-Mac mode:

```bash
export EVAOS_DESKTOP_BRIDGE_URL=http://<mac-headscale-ip>:8765
export EVAOS_DESKTOP_BRIDGE_TOKEN="$(cat "$HOME/Library/Application Support/evaos-desktop-bridge/connector.token")"
```

The plugin still sends fixed command keys. The connector converts those keys to
fixed CLI argv lists and rejects unknown commands.

## Safety Contract

Read tools:

- `customer_mac_status`
- `customer_mac_capabilities`
- `customer_mac_snapshot`
- `customer_mac_ax_tree`
- `customer_mac_iphone_mirroring_status`
- `customer_mac_screen_sharing_status`
- `desktop_bridge_audit_tail`

Guarded actions:

- focus a non-sensitive app;
- open a localhost, loopback, or `.local` website;
- browser reload/back/forward;
- focus iPhone Mirroring;
- iPhone Home, App Switcher, Spotlight;
- open a non-sensitive iPhone app;
- tap an exact visible iPhone Mirroring target label.
- support-only iPhone scroll/swipe gestures when
  `EVAOS_SUPPORT_CANARY_CONTROLS=1`;
- support-only exact approved text entry and one-message send when the human has
  approved the recipient/context and exact text in the same flow.

Rules:

- Dry-run defaults on for guarded tools.
- Remote live actions require `dry_run=false` plus `approval_audit_id`.
- The OpenClaw plugin requests approval for live actions.
- Sensitive Mac/iPhone apps and dangerous target labels are blocked.
- Generic coordinates, arbitrary shell, AppleScript passthrough, Screen Sharing
  enablement, and app-server mutation passthrough are blocked.
- Support-only gesture/message commands also require `approval_audit_id`; without
  `EVAOS_SUPPORT_CANARY_CONTROLS=1` they fail closed even for dry-runs.

## Support VM Live Canary Commands

Start the connector on the Mac for the support VM only:

```bash
EVAOS_SUPPORT_CANARY_CONTROLS=1 \
  evaos-desktop-bridge serve --host <mac-headscale-ip> --port 8765
```

If the Mac is not joined to the same Headscale mesh as the support VM, use a
temporary reverse SSH tunnel for the canary instead of changing the Mac's active
VPN profile:

```bash
EVAOS_SUPPORT_CANARY_CONTROLS=1 \
  .venv/bin/python -m evaos_desktop_bridge.cli serve --host 127.0.0.1 --port 8766

ssh -N -R 127.0.0.1:8766:127.0.0.1:8766 root@<support-vm-public-ip>
```

Then set `EVAOS_DESKTOP_BRIDGE_URL=http://127.0.0.1:8766` on the support VM.
The connector CLI commands are local-first; remote support-shell tests should
use `/v1/commands` directly or the OpenClaw plugin remote mode.

Recommended smoke order:

```bash
curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${EVAOS_DESKTOP_BRIDGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacStatus","params":{}}'

curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${EVAOS_DESKTOP_BRIDGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"codexAppServerRemoteControlStatus","params":{}}'

curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${EVAOS_DESKTOP_BRIDGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacIphoneMirroringStatus","params":{}}'

curl -sS "${EVAOS_DESKTOP_BRIDGE_URL}/v1/commands" \
  -H "Authorization: Bearer ${EVAOS_DESKTOP_BRIDGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command":"customerMacIphoneMirroringOpenApp","params":{"app_name":"Bumble","dry_run":true}}'
```

For any live action, rerun the exact same command with `dry_run=false` implied
by omitting `--dry-run` and add the matching `--approval-audit-id`. Never send a
message unless the human approved the recipient/context and exact message text
inside the same test flow.

## Workbench Surface

`evaOS Workbench` shows connector status, iPhone Mirroring status, Screen Sharing
status, capabilities, and audit tail in the Desktop Bridge panel. It does not
expose live local-control buttons in the canary UI. The local kill switch for
the current desktop session is the Workbench `Revoke Session` action; paired
connector revocation remains a support/control-plane action tied to Headscale
ACLs and connector-token rotation.

## Follow-Ups

- Support/control-plane device records for paired Macs.
- Headscale ACL provisioning and revocation runbook.
- Friendly external Mac canary with token rotation evidence.
- Codex Desktop remote-control lane after the generic Mac connector is stable.
- Promote support-only iPhone controls only after repeated audited canaries; do
  not include them in customer provisioning by default.
