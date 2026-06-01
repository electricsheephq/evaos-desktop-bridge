---
title: "ADR: SMB Command Center V1"
status: proposed
created: 2026-06-01
owners: "Workbench, Dashboard, Broker, Cortex, OpenClaw"
primary_issues:
  - "evaos-desktop-bridge#100"
  - "evaos-desktop-bridge#97"
  - "electric-sheep-website-dashboard-6158a244#219"
---

# ADR: SMB Command Center V1

## Decision

evaOS Workbench becomes an SMB-first AI command center by keeping the native
SwiftUI shell and brokered WebView runtime model, while moving account, member,
billing, and permission truth into the Dashboard/Supabase account policy layer.

The command center must help a small-business owner answer five questions
without seeing runtime jargon:

1. What can Eva do for me today?
2. Which apps are connected?
3. Who on my team can use which agents and workspaces?
4. What needs my approval or login?
5. Where do I resume work?

This ADR rejects replacing Workbench with AionUi or ClickClack. AionUi is a
reference for agent/team UX. ClickClack is a later chat substrate. Neither owns
evaOS identity, billing, provider grants, runtime authorization, approvals, or
audit.

## Research Basis

Five read-only scout lanes converged on this shape:

- Workbench already has the right native architecture: SwiftUI shell,
  persistent `WKWebView` runtime tabs, Keychain desktop session, brokered
  runtime launch/status/provider/approval APIs, and local bridge evidence.
- Dashboard already has real `customer_accounts`,
  `customer_account_memberships`, invitations, and `plan_entitlements`, but
  runtime access, Cortex scope, billing, and navigation still contain
  user-level assumptions.
- AionUi is Apache-2.0 and useful for agent/team cards, assistant catalogs,
  task launchers, MCP/provider UX, and pending permission badges. It should not
  be embedded as the Workbench shell because its Electron runtime, local secret
  model, and full-auto defaults do not match evaOS trust boundaries.
- ClickClack is viable as chat infrastructure. It has workspaces, channels,
  DMs, threads, bot users, bot tokens, realtime events, and an OpenClaw channel
  extension. It still needs evaOS provisioning, private-channel policy,
  customer SSO, cursor durability, and audit binding before customer rollout.
- The highest-risk failure mode is permission theater: hiding a sidebar item is
  not authorization. Supabase RLS, edge functions, broker actions, Cortex
  proxy, runtime launch, billing portal, and Workbench navigation must all use
  the same account policy vocabulary.

## Source Of Truth

| Domain | Authority | Consumers | Notes |
| --- | --- | --- | --- |
| Customer account, plan, seats | Dashboard/Supabase | Workbench, Broker, Dashboard | `customer_accounts` and `plan_entitlements` are the base. |
| User membership | Dashboard/Supabase | Workbench, Broker, Dashboard | `customer_account_memberships` is the base. |
| Permission scopes | Dashboard/Supabase | Workbench, Broker, Dashboard, Cortex proxy | Add a versioned policy contract and RPC. |
| Runtime launch/status | Broker | Workbench, Dashboard, OpenClaw, Hermes | Broker remains the only runtime URL/session minting authority. |
| Provider grants | Broker/Cortex plus provider backend | Workbench, Dashboard, OpenClaw, Hermes | Store grant handles and secret refs, never raw tokens in Workbench. |
| Approvals | Broker/runtime approval queue | Workbench, Dashboard, OpenClaw, Hermes | Decisions must include destination proof and audit. |
| Company Brain | Cortex via account-scoped proxy | Dashboard, Workbench | Read MVP first; no broad writes in V1. |
| Local Mac/iPhone control | Desktop Bridge/Workbench | Workbench, OpenClaw tools | Remains separate from account policy and provider grants. |
| Team chat | evaOS policy plus ClickClack later | Workbench, Dashboard, OpenClaw | ClickClack stores chat state only. |

## Product Information Architecture

Default customer surfaces:

- `Home` / `Today`: next actions, recent work, agent status, approval needs,
  connected-app needs, and Business Browser needs.
- `My Agents`: assigned agents, task templates, current status, allowed apps,
  budget/approval posture, and pause/stop affordances.
- `Connected Apps`: Google Workspace, Pipedream-backed apps, Codex, GitHub,
  Slack, Notion, Linear, and future integrations.
- `People & Access`: team members, roles, seat usage, agent assignments, and
  workspace/app access.
- `Business Browser`: product name for the existing brokered Shared Browser.
- `Creative Studio`: hosted Comfy Cloud entry, not local ComfyUI.
- `Company Brain`: source health, query, brief, and exception queue.
- `Needs Your Okay`: approval inbox with destination proof.
- `Team Chat`: deferred ClickClack-backed chat surface.

Advanced/admin surfaces:

- OpenClaw full dashboard.
- Hermes full dashboard.
- Mission Control technical view.
- Terminal.
- Raw runtime status.
- Bridge diagnostics.
- Release/support diagnostics.

Advanced surfaces must be hidden from ordinary members and denied server-side
when reached directly.

## Account Policy Contract

Schema version: `evaos.account_policy.v1`

The Dashboard/Supabase layer should expose a policy snapshot for the active
customer account. A future implementation can expose it with
`current_customer_account_permissions()`.

```json
{
  "schema_version": "evaos.account_policy.v1",
  "customer_account_id": "acct_123",
  "selected_customer_id": "david-poku",
  "membership_id": "mem_123",
  "membership_role": "admin",
  "plan_code": "biz",
  "seat_limit": 3,
  "active_seats": 2,
  "invited_seats": 1,
  "scopes": [
    "manage_members",
    "manage_integrations",
    "approve_actions",
    "open_business_browser",
    "view_company_brain"
  ],
  "advanced_surfaces": {
    "openclaw_dashboard": false,
    "hermes_dashboard": false,
    "terminal": false,
    "technical_diagnostics": false
  },
  "updated_at": "2026-06-01T00:00:00Z"
}
```

Initial roles:

- `owner`: account creator and final authority.
- `admin`: can manage team, agents, apps, and approvals except billing unless
  granted billing scope.
- `billing_admin`: can manage billing and seats but not technical dashboards by
  default.
- `technical_admin`: can access OpenClaw/Hermes full dashboards, Terminal, and
  diagnostics.
- `manager`: can manage assigned agents and approvals for their team.
- `member`: can use assigned agents and allowed workspaces.
- `agent_only`: sees only assigned agent workspace plus explicitly allowed
  Browser/Creative/Design surfaces.
- `support`: Electric Sheep support role, audited and account-scoped.

Initial scopes:

- `manage_members`
- `manage_billing`
- `manage_integrations`
- `approve_actions`
- `open_business_browser`
- `use_creative_studio`
- `use_design_workspace`
- `view_company_brain`
- `manage_company_brain`
- `assign_agents`
- `access_openclaw_dashboard`
- `access_hermes_dashboard`
- `access_terminal`
- `access_technical_diagnostics`

Plan defaults:

- `solo`: one user, owner only.
- `biz`: three included users.
- `cobrain`: ten included users, seat blocks of ten unless billing source says
  otherwise.

The plan source must be the backend entitlement table or backend policy RPC.
Frontend constants can exist only as display fallbacks.

## Agent Assignment Contract

Schema version: `evaos.agent_assignment.v1`

```json
{
  "schema_version": "evaos.agent_assignment.v1",
  "assignment_id": "assign_123",
  "customer_account_id": "acct_123",
  "assigned_user_id": "usr_123",
  "agent_id": "agent_sales_followup",
  "agent_display_name": "Sales Follow-up",
  "runtime": "openclaw",
  "allowed_provider_grants": ["grant_google_workspace_sales"],
  "allowed_surfaces": ["today", "business_browser", "creative_studio"],
  "approval_policy": {
    "default": "ask",
    "allow_always_fingerprints": []
  },
  "budget": {
    "daily_usd": 5,
    "daily_tokens": 200000
  },
  "schedule": {
    "enabled": false
  },
  "kill_switch": {
    "enabled": true,
    "state": "running"
  },
  "source_pointer": "dashboard:agent_assignment:assign_123",
  "audit_id": "audit_123"
}
```

V1 must support one assigned agent per user before supporting multi-agent teams.
The assignment is not just a UI card. It controls allowed apps, approvals,
budget, pause/stop state, and Today status.

## Provider Grant Contract

Schema version: `evaos.provider_grant.v1`

```json
{
  "schema_version": "evaos.provider_grant.v1",
  "grant_id": "grant_google_workspace_sales",
  "customer_account_id": "acct_123",
  "provider": "google_workspace",
  "owner_kind": "user",
  "owner_user_id": "usr_123",
  "status": "connected",
  "scopes": ["gmail.readonly", "calendar.readonly"],
  "expires_at": "2026-07-01T00:00:00Z",
  "grant_handle": "broker-grant-opaque",
  "revoke_handle": "broker-revoke-opaque",
  "display": {
    "account_label": "sales@example.com",
    "last_checked_at": "2026-06-01T00:00:00Z"
  },
  "source_pointer": "broker:provider_grant:grant_google_workspace_sales",
  "audit_id": "audit_123"
}
```

Rules:

- Workbench and Dashboard may display account labels, scopes, status, and
  expiry.
- Raw OAuth tokens, refresh tokens, API keys, cookies, and provider secrets
  never return to Workbench renderers or dashboard browser renderers.
- Revocation must invalidate the grant for OpenClaw, Hermes, Broker, Cortex,
  and Today status.
- Pipedream is an integration engine behind Connected Apps, not the product
  surface itself.

## Browser Status Contract

Schema version: `evaos.browser_status.v1`

Business Browser is the customer-facing name for the existing Shared Browser.

```json
{
  "schema_version": "evaos.browser_status.v1",
  "customer_account_id": "acct_123",
  "customer_id": "david-poku",
  "runtime": "browser",
  "status": "ready",
  "room_id": "shared-browser:david-poku",
  "owner": "david-poku",
  "current_url": {
    "host": "accounts.google.com",
    "path": "/signin",
    "query_redacted": true
  },
  "last_activity_at": "2026-06-01T00:00:00Z",
  "needs_auth": true,
  "needs_captcha": false,
  "actions": ["start_attach", "refresh_status", "stop_browser"],
  "source_pointer": "broker:runtime_status:browser",
  "audit_id": "audit_123"
}
```

Rules:

- No generic browser automation action is added by this contract.
- Start/attach and stop are named broker actions.
- URL query strings, fragments, cookies, tokens, and form values are redacted.
- Cross-customer browser evidence must be cleared on customer switch and denied
  at broker/proxy layers.

## Today Item Contract

Schema version: `evaos.today_item.v1`

```json
{
  "schema_version": "evaos.today_item.v1",
  "id": "today_123",
  "kind": "connected_app_needed",
  "title": "Connect Google Workspace",
  "status": "needs_input",
  "next_action": "Open Connected Apps and approve Google Workspace access.",
  "assigned_agent_id": "agent_sales_followup",
  "assigned_user_id": "usr_123",
  "source_pointer": "broker:provider_grant:google_workspace",
  "audit_id": "audit_123",
  "updated_at": "2026-06-01T00:00:00Z"
}
```

Initial `kind` values:

- `connected_app_needed`
- `approval_needed`
- `browser_login_needed`
- `agent_running`
- `agent_done`
- `agent_blocked`
- `company_brain_source_needed`
- `recent_work`
- `system_attention`

Today cards must be written in business language. Raw `provider`, `manifest`,
`grant`, `runtime`, `OpenClaw`, `Hermes`, and `app-server` language belongs in
collapsed technical detail, not the default path.

## AionUi Reference Boundary

Use AionUi for:

- agent and team cards
- leader/member pane patterns
- assistant catalog source labels
- task card layouts
- provider/MCP configuration readability
- pending permission badges

Do not use AionUi for:

- Workbench shell replacement
- account authority
- secret storage
- renderer-visible provider keys
- YOLO/full-auto default posture
- bundled subprocess/MCP trust without evaOS broker policy
- release/update infrastructure

Any AionUi-inspired implementation must be native evaOS code and pass evaOS
redaction, approval, audit, and permission tests.

## ClickClack Reference Boundary

Use ClickClack later as a wrapped Team Chat runtime:

- one ClickClack workspace per `customer_account`
- human members mirrored from evaOS users
- service bots or user-owned bots for assigned agents
- channels such as `today`, `ops`, `approvals`, `agents`, and `support`
- DMs for human-agent direct work
- OpenClaw ClickClack channel extension for agent participation

Required before customer rollout:

- evaOS chat binding tables or equivalent control-plane state
- customer SSO/session broker
- member provisioning API
- private channel ACLs for sensitive rooms
- bot token rotation/revoke
- cursor durability in OpenClaw gateway usage
- embedded Workbench/Dashboard smoke
- upload security and retention policy

ClickClack stores chat state. It does not own billing, account membership,
provider grants, agent assignment, or permission policy.

## Milestone

Create coordinating milestone in both affected repos:

`SMB Command Center V1: Account Policy And First Agent Loop`

Bridge anchors:

- `#100` Session Center / Agent Workspace
- `#97` Business Browser / Shared Browser
- `#148` Google Workspace OAuth paperwork
- `#144` Approval Center
- `#102` Creative Studio

Dashboard anchors:

- `#219` Corporate Dashboard Biz + CoBrain Activation
- `#220` org model
- `#221` RLS/members/seats
- `#222` gateway auth
- `#223` members UX
- `#224` permission-aware navigation
- `#225` / `#226` Company Brain
- `#227` E2E acceptance
- `#228` entitlements

Deferred:

- `#136` Codex app-server live control
- `#134` background/parallel Mac control

## Child Issue Map

1. `ADR: SMB Command Center ownership and IA`
   - Defines boundaries, IA, and first happy path.
2. `Account Policy Contract`
   - Adds role/scope matrix, permission RPC, account selector rules, and
     server-side denial behavior.
3. `Runtime/Cortex/Billing Authority Cleanup`
   - Removes user-only assumptions from customer VM, Cortex owner scope,
     billing portal, and subscription access.
4. `Permission-Aware Navigation`
   - Dashboard sidebar, mobile nav, command palette, Workbench sidebar, and
     direct routes use the same scopes.
5. `PR #235 Visual Acceptance And Release`
   - Signed-in Workbench pass proves Home, Connected Apps, Business Browser,
     Creative Studio, and Approvals are understandable.
6. `Connected Apps V1`
   - Google Workspace first; Pipedream and Codex represented as brokered
     connection/status surfaces.
7. `Business Browser Controller Contract`
   - Shared status/actions consumed by Workbench, Dashboard, OpenClaw, and
     Hermes.
8. `Approval Runtime Resolution`
   - Approval decisions unblock or deny actual OpenClaw/Hermes actions with
     destination proof.
9. `Assigned Agent Model`
   - One agent assigned to one user with allowed apps, budget, approvals, and
     Today status.
10. `Home/Today V1`
   - Replaces backend-looking mission cards with business-readable next
     actions and recent work.
11. `Company Brain Read MVP`
   - Org-scoped source health, query, brief, and exception queue.
12. `AionUi Reference Spike`
   - Native evaOS mock/spike using AionUi patterns only.
13. `ClickClack Chat Binding Spike`
   - evaOS-provisioned workspace, one human, one service bot, one assigned
     agent, one channel, one DM, embedded in Workbench/Dashboard.
14. `End-To-End SMB Acceptance`
   - Owner invites employee, assigns agent, employee sees only allowed
     surfaces, connects/uses app access, and forbidden routes fail closed.

## Sprint Sequence

### Sprint 0: Contract Lock

Deliver:

- this ADR
- GitHub milestone wiring
- child issues and cross-links
- issue comments on existing anchors

Exit criteria:

- another agent can implement without debating Workbench versus AionUi versus
  ClickClack ownership
- role/scope vocabulary is explicit
- source-of-truth table is explicit

### Sprint 1: Ship The Visual Reset

Deliver:

- signed-in Workbench visual acceptance for PR `#235`
- sprint release after acceptance

Exit criteria:

- non-technical SMB user can explain Workbench as an AI office command center
  and identify the next action within five seconds

### Sprint 2: People And Access

Deliver:

- account policy RPC
- billing admin capability
- server-side permission checks
- route/navigation gating in Dashboard and Workbench

Exit criteria:

- invited users see and use only what they are allowed to use

### Sprint 3: First Agent Loop

Deliver:

- Connected Apps Google/Pipedream status
- one assigned agent
- Business Browser auth handoff
- approval resolution
- Today result card

Exit criteria:

- one real business workflow works end to end

### Sprint 4: Company Brain And Creative

Deliver:

- Company Brain read MVP
- Creative Studio hosted-flow polish

Exit criteria:

- business memory is useful and scoped
- Creative Studio is visible and honest about hosted Comfy Cloud

### Sprint 5: Team Chat Pilot

Deliver:

- ClickClack binding/provisioning spike

Exit criteria:

- one customer workspace has human and agent chat without making ClickClack the
  account authority

## Acceptance Tests

Persona acceptance:

- SMB owner explains the app and identifies next action within five seconds.
- Employee sees assigned agent, Business Browser, Creative Studio, and allowed
  work only.
- Billing admin can access billing but not technical dashboards unless granted.
- Agent-only user cannot access Hermes/OpenClaw full dashboards, Terminal,
  billing, members, or another account.

Security acceptance:

- Disabled or removed member loses Dashboard, Workbench, broker, Cortex,
  Company Brain, and browser access.
- Direct route and function calls deny the same actions hidden by UI.
- Provider grants never expose raw tokens to Workbench or browser renderers.
- Cross-customer runtime/session/browser evidence cannot leak.

Product acceptance:

- Owner invites user and user accepts.
- Seat count updates.
- Owner assigns one agent and allowed app access.
- Google/Pipedream app connection shows readable status and revoke path.
- Business Browser handles login/CAPTCHA handoff and returns status.
- Approval shows destination, risk, allow/deny, and audit evidence.
- Today shows completed, blocked, and needs-input work in human language.

## Adversarial Risks

1. Scope collapse: Home, apps, people, agents, browser, studio, brain, chat, and
   dashboards cannot all be one release.
2. Permission theater: UI-only hiding is not authorization.
3. Provider leakage: Connected Apps must not expose raw OAuth/provider secrets
   to Workbench or dashboard renderers.
4. Fake assigned agents: an agent card without allowed apps, budget, approvals,
   pause/stop, and audit is not a usable agent assignment.
5. Business Browser tenant mixups: cookies, room ids, current URL, customer
   target, and stop/reconnect state must remain customer-scoped.
6. Company Brain overexposure: read MVP must prove org-scoped query and source
   authorization before broad access.
7. Copy trap: AionUi and ClickClack are not product authorities.
8. SMB UX overload: runtime catalogs are not command centers.
9. Contract drift: native app, dashboard, Supabase, broker, and VM runtimes must
   use versioned contracts.
10. False release confidence: scenario QA must prove state, action, and result,
    not just screenshots.
