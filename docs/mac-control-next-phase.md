---
title: "Next Phase: Supervised Mac And iPhone Control"
status: proposed
created: 2026-05-20
---

# Next Phase: Supervised Mac And iPhone Control

## Principle

Workbench first becomes a trusted cockpit. Local Mac and iPhone control come
after signing, auth, and gateway launching are stable.

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
   - Bridge panel remains read-only.

3. **Guarded Mac control canary**
   - Add explicit permissions onboarding for Accessibility and Screen Recording.
   - Expose small named tools: observe screen, list windows, focus app,
     screenshot, click, type, paste.
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
- Existing `evaos-desktop-bridge`: local audit queue, permissions checks, and
  command boundary.
- OpenClaw plugin wrapper: route agent requests into the bridge once the safety
  contract is ready.

## Issues To File Before Implementation

1. **Threat Model And Safety Gates**
   - Define permissions, audit, dry-run, and approval rules.

2. **Permissions And Onboarding**
   - Native onboarding for Accessibility, Screen Recording, and future Apple
     Events if needed.

3. **Connector API And Control Plane Contract**
   - Typed action schema for observe/click/type/paste/focus with evidence.

4. **iPhone Mirroring Canary Spec**
   - Boundaries for mirrored-window control, approval gates, and blocked actions.

## Non-Goals For The First Control Sprint

- No arbitrary shell execution.
- No hidden iMessage automation.
- No background iPhone control.
- No credential collection in chat.
- No control actions without local audit records.
