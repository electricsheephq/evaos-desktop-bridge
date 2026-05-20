---
title: "Next Phase: Supervised Mac And iPhone Control"
status: active-canary
created: 2026-05-20
---

# Next Phase: Supervised Mac And iPhone Control

## Principle

Workbench first becomes a trusted cockpit. Local Mac and iPhone control now
enter canary through the customer-Mac connector: named, audited tools only,
with the Workbench UI showing status/revocation rather than live control
buttons.

The control layer should use named, allowlisted actions with audit evidence. It
should not expose a generic shell, generic AppleScript runner, or silent
Accessibility control surface.

## Recommended Sequence

1. **Signing and notarization**
   - Developer ID signed, hardened runtime, notarized app.
   - Prompt-free Keychain behavior proven across updates.

2. **Read-only customer canary**
   - Workbench opens live gateways for one friendly customer.
   - WebView isolation and sign-out behavior verified.
   - Bridge panel shows connector/iPhone status and audit tail.

3. **Guarded Mac control canary**
   - Add explicit permissions onboarding for Accessibility and Screen Recording.
   - Expose small named tools: observe screen, list windows, focus app,
     screenshot, local-site open/reload/back/forward, and iPhone Mirroring
     named actions.
   - Require dry-run previews and audit logging for actions.

4. **Remote agent control contract**
   - Define how OpenClaw/Hermes agents request local actions.
   - Require human-visible consent for sensitive actions.
   - Store action evidence locally and in the support/audit trail.

5. **iPhone Mirroring pilot**
   - Treat iPhone control as control of a visible Mac window, not as a hidden
     mobile-device automation channel.
   - Start with observe/screenshot/click/type on the mirrored window.
   - Keep iMessage/send/payment/account actions behind same-turn approval gates.

## Candidate Libraries And Tools

- `Peekaboo`: screen observation and screenshots.
- `AXorcist`: Accessibility-tree reads and focused UI actions.
- Existing `evaos-desktop-bridge`: local audit queue, permissions checks,
  command boundary, and token-gated connector server.
- OpenClaw plugin wrapper: route agent requests into the local bridge CLI or a
  paired Mac connector over Headscale.

## Remaining Issues Before Broad Rollout

1. **Headscale Device Records And ACLs**
   - Pair one customer VM to one customer Mac and prove no cross-customer reachability.

2. **Permissions And Onboarding**
   - Native onboarding for Accessibility, Screen Recording, and future Apple
     Events if needed.

3. **Connector Token Lifecycle**
   - Provision, rotate, revoke, and audit connector tokens.

4. **iPhone Mirroring Canary Spec**
   - Expand only after status/snapshot/focus/open-safe-app smoke is proven.

## Non-Goals For The First Control Sprint

- No arbitrary shell execution.
- No hidden iMessage automation.
- No background iPhone control.
- No credential collection in chat.
- No control actions without local audit records.
