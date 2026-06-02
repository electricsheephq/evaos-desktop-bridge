# Actionable Task Launcher Slice

Issue anchor: [#100 Session Center and Agent Workspace](https://github.com/electricsheephq/evaos-desktop-bridge/issues/100)

Date: 2026-06-02

## Purpose

Make Home feel more capable without adding a new unsafe execution surface. The
old Aion-inspired task launcher was visually useful but behaved like a preview.
This slice turns the starter tasks into safe routes to surfaces Workbench
already owns:

- Email follow-up opens Connected Apps so Gmail/Google Workspace can be linked.
- Sales research opens Business Browser.
- Admin inbox opens Approvals.
- Creative brief opens hosted Creative Studio.

## Guardrails

- No new generic Mac control.
- No raw provider tokens in Workbench or WebView renderers.
- No generic agent prompt runner.
- No live app-server mutation.
- No backend execution is started from these cards.
- Disabled rows stay visible and explain whether sign-in or admin-granted
  access is required.
- Hosted Creative Studio stays directly launchable because it is an external
  workspace entry, not a brokered provider/action flow.

## Sign-In Resilience Fix

During signed-in visual acceptance, an admin user could appear to sign in
and immediately sign out. Code inspection found another session-clear path:
after auth, Workbench may load or refresh the selected brokered workspace. A
runtime-specific broker `401` previously cleared the whole desktop session.

The new behavior keeps the app signed in and marks only the affected workspace
as account-permissions unavailable. Users can refresh or sign out/back in, but a
single gateway failure no longer erases the whole Workbench shell.

## Fast Iteration

Use the Vite dashboard checkout for local browser testing of Dashboard,
onboarding, Connected Apps pages, and embedded WebView surfaces. The native
SwiftUI Workbench shell is not browser-hostable; use Swift previews, focused
smoke tests, and the prompt-free Agent QA app for Home/sidebar/native changes.
Package/sign/notarize only for sprint release acceptance.
