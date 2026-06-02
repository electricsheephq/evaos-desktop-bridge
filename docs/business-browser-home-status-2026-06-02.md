# Business Browser Home Status Slice

Issue: #97

## Why This Slice Exists

The Business Browser controller contract already normalizes broker status into
`evaos.browser_status.v1`, but Home still exposed a generic "Open business
browser" quick action. That made the first screen look less capable than the
runtime detail page and hid useful status evidence from SMB users.

## Current-State Inventory

- Existing: Workbench has a brokered Business Browser runtime, status refresh,
  start/attach, reload/reconnect, open, and stop actions.
- Existing: `WorkbenchModel.businessBrowserStatus` carries sanitized room,
  current site, last activity, sign-in, and CAPTCHA evidence.
- Existing: Home/Today can already derive browser-related next actions.
- Gap fixed here: Home did not render the browser readiness evidence directly.
- Gap fixed here: local browser detach no longer lets stale broker readiness
  metadata continue to render on Home.
- Still follow-up: signed-in acceptance should verify that a production broker
  status response updates the new Home card after Business Browser opens.

## User-Facing Behavior

Home now shows a Business Browser card that can say:

- `Sign in first` when Workbench has no desktop session.
- `CAPTCHA` when the broker reports a CAPTCHA blocker.
- `Needs sign-in` when a page needs user login.
- `Ready` for active/loaded/running browser status.
- `Unavailable` when the browser is stopped, degraded, offline, or expired.

When available, the card shows room, site, and last activity without exposing
raw URLs, tokens, proxy errors, or backend runtime details.

## Guardrails

- This does not add a new control surface.
- This does not expose raw provider tokens or browser URLs with query strings.
- This does not change broker authorization.
- This does not add generic Mac/browser automation.

## Follow-Up Issues

- #97: Verify production broker status drives the Home card in signed-in app
  acceptance.
- #97: Keep aligning Dashboard and Workbench around the same normalized browser
  status contract.
- #100: Continue replacing technical Home evidence with business-readable next
  actions.
