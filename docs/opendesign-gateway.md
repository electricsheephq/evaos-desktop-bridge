# OpenDesign Workbench Gateway

This note records the release contract for issues `#20` and `#66`.

## Route Decision

OpenDesign is a first-class brokered Workbench runtime. Workbench does not use a
hard-coded hosted OpenDesign URL, local OpenDesign discovery, or an install
placeholder for eligible customers. It requests a short-lived launch URL from
the desktop runtime broker with:

```json
{
  "action": "runtime_launch",
  "runtime": "opendesign"
}
```

The broker remains the authority for customer eligibility, route availability,
and session lifetime. If the route is missing, disabled, or authorization fails,
Workbench shows the same clean unavailable/sign-in/error state used by the other
brokered gateways.

## Workbench Contract

- `RuntimeKey.openDesign` serializes as `opendesign`.
- `RuntimeDefinition.isBrokeredRuntime(.openDesign)` is true.
- `RuntimeDefinition.externalURL(for: .openDesign)` is nil, so OpenDesign cannot
  silently fall back to a stale public URL.
- OpenDesign is visible to both customer and admin Workbench users through the
  standard gateway list.
- `WorkbenchModel.loadRuntime(_:)` and `openSelectedRuntimeExternally()` call
  the desktop runtime broker for OpenDesign exactly like OpenClaw, Hermes,
  Mission Control, Shared Browser, and Terminal.
- `refreshSessionCenterState()` includes OpenDesign in broker
  `runtime_status` checks and mission-card derivation.
- `RuntimeWebViewDeck` keeps loaded runtime webviews attached and switches
  active gateways by visibility/stacking instead of rebuilding the upstream UI.

## Auth And Availability

OpenDesign uses the same opaque Workbench desktop session and brokered auth
rules as the other customer gateways. Workbench stores only the desktop session
in Keychain. It does not store OpenDesign cookies, VM gateway tokens, service
keys, or backend secrets.

Codex/BYOK provider setup is separate from OpenDesign gateway availability.
Provider readiness belongs in the Provider Hub and Session Center surfaces; it
must not turn the OpenDesign gateway into a placeholder or block brokered
OpenDesign launches.

## Verification

Local smoke coverage:

```bash
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
```

Manual canary checklist:

1. Sign in to Workbench as `admin@100yen.org`.
2. Select Golden.
3. Open OpenDesign from the Gateways list and verify it launches without a
   dashboard detour.
4. Switch to another gateway and back; the OpenDesign page should stay alive
   unless the user explicitly reloads or reconnects.
5. Repeat with one eligible customer canary.
6. Confirm a missing or disabled broker route leaves a clean unavailable/error
   state rather than a stale URL, placeholder, or blank persistent spinner.
