# Visible SMB Feature Restoration Inventory

Issue anchors: [#100 Session Center and Agent Workspace](https://github.com/electricsheephq/evaos-desktop-bridge/issues/100) and [#97 Business Browser / Shared Browser](https://github.com/electricsheephq/evaos-desktop-bridge/issues/97).

Date: 2026-06-02

## Current-State Audit

| Surface | Current state on main | Visible concern | Sprint action |
| --- | --- | --- | --- |
| Home / Today | Present as the default Workbench front door. | Useful, but still easy to miss which surfaces are real actions versus evidence. | Keep Home first; no backend changes in this slice. |
| Connected Apps / Providers | Present as Connected Apps. | Moved under Settings, which made a core SMB setup action feel secondary. | Move into Business Admin when the user's role can manage app connections. |
| People & Access | Implemented in the dashboard at `/dashboard/invites`. | No native Workbench entry point, so member management looked missing. | Add a People & Access sidebar action for owner/admin users. |
| Business Browser / Shared Browser | Present as Business Browser with start/attach/stop support. | Still shares space with technical dashboards, so its purpose can blur. | Keep in customer Workspaces, not Technical Dashboards. |
| Creative Studio / hosted Comfy Cloud | Present as Creative Studio runtime, loading hosted Comfy Cloud. | Valuable user-facing feature, but can look buried if workspaces are noisy. | Keep in customer Workspaces and Home quick actions. |
| Approvals | Present as Approvals and Home quick action. | Label is clearer than Approval Center; manager access needed to stay visible. | Keep role-gated by visible surface policy. |
| OpenClaw, Hermes, Mission Control, Terminal | Present as runtime entries with some SMB-renamed labels. | Power-user/admin dashboards became ambiguous or visible to the wrong audience. | Move to Technical Dashboards for owner/admin/technical/support users and restore recognizable names. |
| OpenDesign | Present as Design Workspace. | It is both a design product surface and a technical dashboard in some contexts. | Keep visible as a customer workspace because assigned/nested users need design access. |
| Company Brain | Dashboard exists at `/dashboard/company-brain`; Home can route from Today items. | No persistent native Workbench row, so it looked absent. | Add a Company Brain sidebar action for roles with Company Brain read access. |
| Assigned agents / task launcher | Present as Home preview/cards. | Still preview-like, not a full launcher. | Leave as visible Home value; follow up with task-launcher issue. |
| Gateway/runtime status | Present via runtime status, Home records, and technical activity. | Raw evidence can still feel IT-oriented. | Keep collapsed; do not expand invisible hardening in this slice. |
| Desktop sign-in resilience | Login callback can save a desktop session, then passive broker refreshes run immediately. | A temporary `401`/permission miss from account policy, Connected Apps, approvals, usage, or capability evidence could erase the fresh session and look like instant sign-out. | Keep the signed-in shell visible and degrade the affected cards/status text; explicit runtime launches still fail closed. |

## Post-Change Navigation Shape

- Home
- Workspaces: Business Browser, Design Workspace, Creative Studio, Team Chat when enabled
- Business Admin: Connected Apps, People & Access, Company Brain when permitted
- Technical Dashboards: OpenClaw Dashboard, Hermes Dashboard, Mission Control, Terminal when permitted
- Settings: Mac & iPhone

## Fast Iteration Rule

The native SwiftUI Workbench shell is not browser-hostable. Use the browser/local
dev server for Dashboard, onboarding, provider pages, and embedded web surfaces.
Use Swift previews, focused smoke checks, and the prompt-free Agent QA app for
native Workbench sidebar/Home/Settings changes. Package, sign, notarize, and run
full signed-in acceptance only when cutting or validating a release.

## Follow-Up Issues To Keep Visible

- #100: Make the assigned-agent/task launcher less preview-like and more directly usable.
- #97: Finish normalized Business Browser status and shared guidance across Workbench, dashboard, OpenClaw, and Hermes.
- #102: Keep Creative Studio hosted-flow acceptance visible in signed-in release screenshots.
- #144: Continue turning approvals into a plain operator inbox with concrete destination and consequence.
- Future dashboard issue: mirror the Workbench sidebar split in the web dashboard so SMB and admin users see the same information architecture.
