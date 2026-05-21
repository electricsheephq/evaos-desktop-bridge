---
title: "evaOS Workbench Customer Install And Update"
status: active
created: 2026-05-22
---

# evaOS Workbench Customer Install And Update

## Purpose

This is the support-facing runbook for helping customers install, sign in,
update, or recover evaOS Workbench.

## Install

1. Send the customer to the install page:
   `https://www.electricsheephq.com/evaos-workbench`
2. Have them download the current ZIP shown on the page.
3. Have them unzip it and drag `evaOS.app` to Applications.
4. If macOS blocks a non-notarized friendly beta, right-click `evaOS.app` and
   choose Open. Do not disable Gatekeeper globally.
5. Confirm the version shown near Sign In/Sign Out matches the install page.

## Sign-In Recovery

If browser auth opens but never returns to the app:

- Use the manual callback/open-in-app button when present.
- If the build supports device-code login, use it instead of browser callback.
- Paste only the browser page's **Backup code** into Workbench. Do not paste
  the URL's `fresh=` value; that value is only a cache-busting id and the app
  will reject it.
- If both fail, reset the local session from the Workbench sign-in screen and
  try again.
- If the user is stuck on a dashboard spinner, sign out of the browser
  dashboard session, reopen Workbench, and retry.

Do not ask the customer to paste raw desktop session tokens into chat.

## Update Recovery

Sparkle-enabled builds should install and relaunch from the update prompt. Older
or broken builds may only discover a download and still require manual reinstall.

Manual reinstall is required when:

- the app cannot launch;
- the user has a known broken build such as `0.2.0`;
- the user has `0.2.1` and login or Mac pairing looks stale;
- Sparkle framework/rpath is missing;
- the app predates Sparkle.

Customer copy:

```text
This build cannot update itself. Please delete the old app, download the latest
Workbench from the install page, unzip it, and drag evaOS.app to Applications.
```

## Quick Support Checks

Ask for:

- visible app version/build;
- whether the app launches;
- whether Sign In opens a browser and returns;
- whether OpenClaw, Hermes, Mission Control, OpenDesign, Shared Browser, and
  Terminal open;
- whether Settings -> Mac & iPhone shows Ready, Needs permission, Not paired,
  or Blocked.

## Self-Serve Pairing Check

For Workbench `0.2.2+`, the customer should not need hidden support commands:

1. In Settings -> Mac & iPhone, create a pairing code.
2. Click Copy Agent Prompt.
3. Paste that prompt into Eva/OpenClaw.
4. Confirm the agent uses `customer_mac_complete_pairing` or the Hermes
   `completeEnrollment` wrapper.
5. Confirm the agent reports Mac status, iPhone status, and audit-tail
   readiness without asking for secrets in chat.

If the app crashes, ask for the first lines of the crash report. The Sparkle
rpath crash includes `Library not loaded: @rpath/Sparkle.framework`.
