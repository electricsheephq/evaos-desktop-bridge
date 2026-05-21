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

Workbench's `Start Connector` button starts a Workbench-managed connector
process for the beta. Keep Workbench open while the connector is paired to the
VM. This is the recommended beta path because macOS permissions are easier to
reason about when the visible Workbench app starts the helper.

The CLI still supports a LaunchAgent-backed background connector:

```bash
evaos-desktop-bridge connector-service start --json
```

`connector-service start` auto-installs or refreshes the per-user LaunchAgent at
`~/Library/LaunchAgents/com.electricsheep.evaos-desktop-bridge.plist`. The
LaunchAgent binds to the current Tailscale/Headscale IPv4 address when one is
available, otherwise it falls back to `127.0.0.1`. Set
`EVAOS_DESKTOP_BRIDGE_CONNECTOR_HOST=127.0.0.1` before starting when you need a
loopback-only debug run.

If agent tools report Accessibility missing through the VM while local terminal
commands show it granted, the connector is running under a different macOS TCC
identity. For beta, restart from Workbench and approve Workbench or the bridge
helper macOS displays in Privacy & Security. The future GA path is a stable
Developer ID signed helper.

`connector-service status --json` reports the permission target plus the bridge
and Python helper paths. Use those paths when macOS does not show a toggle after
opening Privacy & Security and you need to add the helper manually.

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

Hermes and other shell-tool adapters should call
`evaos-desktop-bridge-command`. The wrapper sources
`/root/.openclaw/evaos-desktop-bridge.env` by default and returns structured
connector JSON on stdout, including structured denials, so agents can see the
reason a command was blocked.

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
- Remote live actions require `dry_run=false` plus `approval_audit_id`. Omitting
  `dry_run` from a connector HTTP request remains a dry-run by design.
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
in CLI form or explicit `"dry_run":false` in connector HTTP form, and add the
matching approval audit id. Never send a message unless the human approved the
recipient/context and exact message text inside the same test flow.

## Headscale Notes

For current Tailscale clients, Headscale must be reachable at a valid HTTPS
`server_url`. The support canary route is:

```text
https://headscale.ecs.electricsheephq.com
```

The public Traefik route points to the control host's internal Headscale
listener at `http://host.docker.internal:8080`. Headscale still listens without
TLS locally, but clients should enroll through the HTTPS route.

If `acl.policy_mode` is database-backed, update ACLs with:

```bash
headscale policy set -f /etc/headscale/acl.yaml --force
```

Do not rely on editing the file plus restarting Headscale; `headscale policy
get` is the source of truth in DB policy mode.

For the support VM canary, keep access narrow:

```json
{
  "action": "accept",
  "src": ["tag:support-vm"],
  "dst": ["tag:support-mac:8765", "tag:support-mac:5900", "tag:support-mac:3283"]
}
```

Customer rollout should use per-customer tags and must prove cross-customer
reachability fails before enabling agent tools.

## Workbench Surface

`evaOS Workbench` owns the customer-facing setup loop:

1. **Connect This Mac** starts or checks the LaunchAgent-backed connector.
2. **Enable Permissions** opens Accessibility and Screen Recording settings.
3. **Pair with evaOS VM** creates a short-lived dashboard/Supabase pairing grant
   and completes the Mac device record after the connector and Headscale client
   are ready. Completion also sends the connector URL and local connector token
   to the service-role-only grant secret table so support-control can configure
   the paired VM without exposing the token to the browser UI.
4. **Connect iPhone** opens iPhone Mirroring and refreshes readiness.
5. **Test Agent Access** runs local connector/status smokes and points support
   to the VM-side `evaos-support mac-connector smoke` proof.
6. **Revoke / Disconnect** signs out the app or revokes the paired Mac grant.

The Workbench customer UI still does not expose live local-control buttons in
V1. Live actions run through OpenClaw/Hermes agent tools so approvals and audit
ids remain attached to the agent turn. The local kill switch for the current
desktop session is the Workbench `Revoke Session` action; paired connector
revocation is represented in Supabase and completed operationally by Headscale
ACL/token revocation.

After Workbench reports the Mac is paired, support runs:

```bash
evaos-support mac-connector configure-vm --targets <customer> --apply --approval-id <id>
evaos-support mac-connector smoke --targets <customer> --json
```

`configure-vm` writes `/root/.openclaw/evaos-desktop-bridge.env` on the paired
VM and restarts `openclaw-gateway`. It redacts connector tokens from stdout and
JSONL evidence.

## Follow-Ups

- Friendly external Mac canary with token rotation evidence.
- Codex Desktop remote-control lane after the generic Mac connector is stable.
- Promote support-only iPhone controls only after repeated audited canaries; do
  not include them in customer provisioning by default.
