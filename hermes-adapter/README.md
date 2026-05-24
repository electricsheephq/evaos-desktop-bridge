# evaOS Desktop Bridge Hermes Adapter

Hermes uses the same customer Mac connector contract as OpenClaw. This adapter
is intentionally tiny: it does not create a second control backend, and it does
not expose generic shell, hidden AppleScript, public Mac ports, or app-server
mutation.

## Runtime contract

Set these on the customer VM after the Mac is paired. The wrapper automatically
sources `/root/.openclaw/evaos-desktop-bridge.env` when the variables are not
already present, so OpenClaw, Hermes, and direct support smokes all use the same
connector contract.

```bash
export EVAOS_DESKTOP_BRIDGE_URL="http://<mac-headscale-ip>:8765"
export EVAOS_DESKTOP_BRIDGE_TOKEN="<connector-token>"
```

Before the VM has a connector token, Hermes can complete enrollment by posting
the one-time code directly to the Mac connector:

```bash
hermes-adapter/bin/evaos-desktop-bridge-command completeEnrollment '{"connector_url":"http://100.64.1.10:8765","enrollment_code":"PAIR123","device_name":"Customer Mac"}'
```

That pre-pairing mode calls `/v1/enrollment/complete`, requires an `http://`
base connector URL on port `8765`, and only allows private/tailnet-shaped hosts
or local `.local` names. It does not require or send
`EVAOS_DESKTOP_BRIDGE_TOKEN`.

Hermes tools should call `bin/evaos-desktop-bridge-command` with one of the
fixed connector command names supported by `/v1/commands`, for example:

```bash
hermes-adapter/bin/evaos-desktop-bridge-command customerMacStatus '{}'
hermes-adapter/bin/evaos-desktop-bridge-command customerMacControlStart '{"mode":"full-access","agent_label":"Hermes"}'
hermes-adapter/bin/evaos-desktop-bridge-command desktopSee '{}'
hermes-adapter/bin/evaos-desktop-bridge-command desktopClick '{"target_label":"Continue","dry_run":false}'
hermes-adapter/bin/evaos-desktop-bridge-command customerMacIphoneMirroringStatus '{}'
hermes-adapter/bin/evaos-desktop-bridge-command iphoneSwipe '{"direction":"up","dry_run":false}'
hermes-adapter/bin/evaos-desktop-bridge-command evaosProviderProfiles '{}'
hermes-adapter/bin/evaos-desktop-bridge-command evaosProviderCompleteAuth '{"identity":"admin@100yen.org"}'
hermes-adapter/bin/evaos-desktop-bridge-command evaosSharedBrowserGuidance '{}'
```

Provider/Auth Hub and Shared Browser guidance commands read optional
`EVAOS_PROVIDER_PROFILES_JSON`, `EVAOS_PROVIDER_GRANTS_JSON`,
`EVAOS_ACTIVE_PROVIDER_KEY`, `EVAOS_SHARED_BROWSER_STATUS_JSON`, and
`EVAOS_CUSTOMER_ID` environment values. They return metadata and opaque grant
handles only, never raw provider credentials.

Provider auth completion uses the dashboard broker endpoint from
`EVAOS_PROVIDER_DISCOVERY_URL` or `EVAOS_DESKTOP_RUNTIME_SESSION_URL`, signs
metadata proof with `EVAOS_PROVIDER_AUTH_PROOF_SECRET`, and sends only identity,
scopes, expiry, and `EVAOS_PROVIDER_SERVER_SECRET_REF`. When the broker mints a
Hermes grant, the wrapper caches that opaque handle in
`EVAOS_PROVIDER_GRANT_CACHE_FILE` or `~/.openclaw/evaos-provider-grants.json`
so later provider discovery works without pasting raw provider secrets.

Full Access mode allows live desktop/iPhone commands without per-action
approval. Ask Permission mode gates risky clicks, taps, hotkeys, typing,
sends, and other high-impact actions with
`{"dry_run":false,"approval_audit_id":"..."}`. The kill switch blocks future
live connector commands immediately.

The wrapper returns connector JSON on stdout even for structured denials such as
blocked sensitive apps or missing approval ids. Network failures and malformed
responses still fail as hard command errors.

## Boundary

- OpenClaw remains the first native plugin path.
- Hermes uses this command wrapper or an MCP/tool config that shells to it.
- The command wrapper only posts fixed JSON to the paired connector URL.
- Customer-facing Mac/iPhone control uses the same Full Access / Ask Permission
  session contract as OpenClaw.
