---
title: "evaOS Workbench Mac And iPhone Pairing"
status: active
created: 2026-05-22
---

# evaOS Workbench Mac And iPhone Pairing

## Purpose

This runbook describes the customer-facing pairing loop that lets OpenClaw and
Hermes agents use audited Mac and iPhone tools through Workbench.

## Architecture

```text
Workbench on customer Mac
  -> local desktop bridge connector
  -> Headscale/Tailscale overlay
  -> paired customer VM
  -> OpenClaw plugin or Hermes adapter
  -> named audited command
```

The customer VM never gets public VNC, SSH, CDP, raw Screen Sharing, generic
shell, or hidden AppleScript access to the Mac.

## Customer Flow

1. Open Workbench.
2. Go to Settings -> Mac & iPhone.
3. Turn on Mac access.
4. Approve Accessibility and Screen Recording for the app/helper macOS shows.
5. Create a pairing code.
6. Copy the generated code-only prompt to Eva/OpenClaw or Hermes.
7. Let the agent complete VM-side pairing with `customer_mac_complete_pairing`
   or the Hermes `completeEnrollment` wrapper, then run the smoke.
8. Confirm Workbench shows paired/ready state.

## Prompt For The User's Agent

Workbench should generate a prompt with this shape:

```text
Please pair my Mac to my evaOS VM.
Customer: <customer_id>
Pairing code: <pairing_code>

Expected result:
- run `customer_mac_complete_pairing` with the pairing code, customer id, and
  optional device name;
- confirm the pairing response is ok and returns only redacted status/audit IDs;
- confirm Mac status, iPhone status, and audit tail are reachable;
- do not perform any live Mac or iPhone action yet.

Do not ask me for connector URLs, IP addresses, ports, SSH, VNC, CDP, tokens, or
secrets in chat.
```

## VM-Side Completion

`customer_mac_complete_pairing` claims the one-time enrollment code from the
broker using the VM's provider-proof secret. The broker returns connector
material only to a verified VM/plugin call, and the plugin writes it privately
to `/root/.openclaw/evaos-desktop-bridge.env`. Pairing code alone must never
return connector secrets.

After pairing, OpenClaw and Hermes use the same desktop bridge contract. Support
tools should redact connector values in stdout, logs, and JSONL evidence.

Run:

```bash
evaos-support mac-connector smoke --targets <customer> --json
```

Success means:

- paired VM reaches the paired Mac connector;
- connector commands require token auth;
- Mac status is readable;
- iPhone Mirroring status is readable when available;
- audit tail is readable;
- cross-customer access is denied or not routable;
- revoke blocks future connector commands.

## macOS Permission Caveat

macOS sometimes does not automatically add a toggle entry for Screen Recording
or Accessibility. In that case, add the app/helper macOS is actually running.
The connector status should show the permission target path so support can guide
the user without guessing.
