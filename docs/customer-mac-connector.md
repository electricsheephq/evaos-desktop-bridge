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

Customer-facing note: Desktop Control Engine V2 is customer-granted computer
control. Full Access mode allows continuous visible Mac and iPhone operation
through the new `desktop_*` and `iphone_*` tools. Ask Permission mode uses the
same control surface but asks again for risky clicks, taps, hotkeys, typing,
sends, and other high-impact actions. Legacy Codex/message fallback commands
remain dry-run/approval gated.

## Local Connector Server

Workbench's `Turn On Mac Access` button starts a Workbench-managed connector
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
identity. For v0.5.0 certification, restart from Workbench and approve evaOS
Workbench, evaOS Connector, or the bundled Peekaboo helper macOS displays in
Privacy & Security. If macOS asks for Python, treat that as a release blocker
instead of asking the customer to approve it.

`connector-service status --json` reports the permission target plus the bridge,
bundled Peekaboo, and connector helper paths. Use those paths when macOS does
not show a toggle after opening Privacy & Security and you need to add the
helper manually. For v0.5.0 certification, macOS should show evaOS Workbench,
evaOS Connector, or Peekaboo as the permission owner, not Python.

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
- `desktop_control_status`
- `desktop_see`
- `iphone_see`
- `customer_mac_snapshot`
- `customer_mac_ax_tree`
- `customer_mac_iphone_mirroring_status`
- `customer_mac_screen_sharing_status`
- `desktop_bridge_audit_tail`

Control/session actions:

- `desktop_control_start` with `mode=full-access` or `mode=ask-permission`;
- `desktop_control_stop`;
- `desktop_kill_switch`;
- `desktop_click`, `desktop_type`, `desktop_scroll`, `desktop_drag`,
  `desktop_hotkey`, `desktop_focus_app`, `desktop_window`, `desktop_menu`,
  `desktop_browser_action`;
- `iphone_tap`, `iphone_swipe`, `iphone_type`.

Legacy guarded actions:

- focus a non-sensitive app;
- open a localhost, loopback, or `.local` website;
- browser reload/back/forward;
- focus iPhone Mirroring;
- iPhone Home, App Switcher, Spotlight;
- open a non-sensitive iPhone app;
- tap an exact visible iPhone Mirroring target label;
- iPhone scroll/swipe gestures by named direction/action;
- exact approved text entry and one-message send when the human has
  approved the recipient/context and exact text in the same flow.

Rules:

- Full Access mode allows live `desktop_*` and `iphone_*` actions without
  per-action approval until the customer stops or kills the session.
- Ask Permission mode allows navigation continuously but gates risky clicks,
  taps, hotkeys, typing, sends, and other high-impact actions with
  `approval_audit_id`.
- The kill switch immediately blocks future live connector commands. A paired
  VM cannot clear the kill switch; the customer must start a new session from
  the local Workbench app.
- Arbitrary shell, hidden AppleScript passthrough, public VNC/SSH/CDP,
  Screen Sharing enablement, and app-server mutation passthrough are blocked.
- Legacy guarded actions still support dry-run/approval for compatibility.

## Live Connector Commands

Start the connector on the Mac:

```bash
evaos-desktop-bridge serve --host <mac-headscale-ip> --port 8765
```

If the Mac is not joined to the same Headscale mesh as the support VM, use a
temporary reverse SSH tunnel for the canary instead of changing the Mac's active
VPN profile:

```bash
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

For legacy guarded actions, or for high-impact actions while Workbench is in
Ask Permission mode, rerun the exact same command with `dry_run=false` implied
in CLI form or explicit `"dry_run":false` in connector HTTP form, and add the
matching approval audit id. Full Access mode does not require per-action
approval for the new `desktop_*` and `iphone_*` tools. Never send a message
unless the human approved the recipient/context and exact message text inside
the same test flow.

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

1. **Turn On Mac Access** starts or checks the Workbench-managed connector.
2. **Allow Screen & Control** opens Accessibility and Screen Recording settings.
3. **Link to evaOS** creates a short-lived dashboard/Supabase pairing grant
   and completes the Mac device record after the connector and Headscale client
   are ready. Completion also sends the connector URL and local connector token
   to the service-role-only grant secret table so support-control can configure
   the paired VM without exposing the token to the browser UI.
4. **Connect iPhone** opens iPhone Mirroring and refreshes readiness.
5. **Check Setup** runs local connector/status smokes and points support
   to the VM-side `evaos-support mac-connector smoke` proof.
6. **Disconnect This Mac** revokes the paired Mac grant.

The Workbench customer UI shows setup, permission, audit, and revoke state. Live
actions run through OpenClaw/Hermes agent tools so approvals and audit ids remain
attached to the agent turn. The local kill switch for the current desktop
session is the Workbench `Sign Out` action; paired connector
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
- Add richer customer onboarding copy and screenshots once the first external
  canary finishes without engineer hand-holding.
