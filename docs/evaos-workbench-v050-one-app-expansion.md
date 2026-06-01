# evaOS Workbench v0.5 One-App Expansion

This release train keeps the existing Workbench workspaces stable while the native shell becomes an SMB command center. Incomplete lanes must stay dark-launched until their canary gates pass.

## Information Architecture

The v0.5 expansion keeps the first screen operational and business-readable: customers land on Home, see the next useful action, and can still open the existing workspace WebViews without learning broker/runtime names.

| State | Sidebar / Settings | Detail Behavior | Degraded Behavior |
| --- | --- | --- | --- |
| Signed out | Home, Workspace list, Mac & iPhone, sign-in affordance | Brokered workspaces show the existing sign-in panel and store only an opaque desktop session after login | No provider, session, or runtime truth is inferred from cached UI state |
| Signed in, normal customer | Home first; Workspaces; Connected Apps under Settings; Approvals under Home | Workspace tabs load broker-issued launch URLs in isolated WebViews; Home reads broker/bridge evidence and recent launches | Errors stay on the affected card/tab and do not hide other workspaces |
| Signed in, admin/support customer switch | Same normal-customer layout plus customer-target switcher in the sidebar footer | Switching customer resets loaded runtime URLs and WebView identity to the selected customer | Wrong-customer cookies are discarded through per-customer non-persistent WebView stores |
| Existing workspace fallback | Eva Workspace, Agent Workspace, Mission Control, Design Workspace, Business Browser, and admin-only Terminal remain direct entries | Existing launch/reconnect/reload/open behavior stays stable regardless of command-center surfaces | Feature rollback disables only the new surface; direct workspace launch remains available |
| Creative Studio | Creative Studio appears in Workspaces | Opens the hosted Comfy Cloud workspace; the macOS app does not bundle ComfyUI, GPUs, or workflows | Remove the hosted route if the vendor surface is unavailable; brokered runtimes are unaffected |

Surface ownership:

- Sidebar `Home`: command-center front door and approvals.
- Sidebar `Workspaces`: business-labeled WebView workspaces plus hosted Creative Studio.
- Sidebar `Mac & iPhone`: local bridge readiness and named local-control surfaces only.
- Settings-style surface `Connected Apps`: app connection state, connect/disconnect, and no raw app secrets.
- Home: read-only session records, attention states, queue/audit/Codex evidence, and jump-back routes.
- Approvals / `Needs Your Okay`: human approval requests with actual destination previews.

## Feature Flags

Flags are read from `UserDefaults` on app launch. Customer-facing command-center surfaces default on; `shared_browser_2` stays off because the base Business Browser is already visible.

| Flag | UserDefaults key | Dashboard env | Default | Owner | Primary issue | Surface / Placement | Rollout criteria | Rollback action | Public copy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `providers_hub` | `EvaDesktop.feature.providers_hub` | `VITE_EVAOS_PROVIDERS_HUB` | On | Workbench + Broker | `#96` | Connected Apps / Settings | Broker app-profile proof, connect/disconnect canary, agent access discovery, rollback runbook | Disable flag and keep existing workspace tabs unchanged | Connect business apps once so Eva can use approved access without storing passwords or tokens in Workbench. |
| `shared_browser_2` | `EvaDesktop.feature.shared_browser_2` | `VITE_EVAOS_SHARED_BROWSER_2` | Off | Workbench + Dashboard + ws-proxy | `#97` | Business Browser / Workspace metadata | Runtime-status health proof, KasmVNC/noVNC canary, app handoff canary, customer rollback proof | Hide enhanced metadata while leaving the base Business Browser workspace visible | Use one shared business browser for sign-in, CAPTCHA, and collaborative web tasks. |
| `session_center` | `EvaDesktop.feature.session_center` | `VITE_EVAOS_SESSION_CENTER` | On | Workbench + Dashboard | `#100` | Home / Home | Runtime/session truth, queue/audit/Codex evidence, relaunch restore, dashboard parity, signed-in Workbench canary | Disable flag and keep direct workspace launch paths available | See what Eva can do, what needs review, and where to jump back in. |
| `approval_center` | `EvaDesktop.feature.approval_center` | `VITE_EVAOS_APPROVAL_CENTER` | On | Workbench + Broker | `#144` | Approvals / Home | Destination preview proof, broker pending-approval endpoint, deny/allow decision canary, spoofed-recipient manual QA | Disable flag and keep approval decisions blocked in the broker/runtime layer | Review risky agent actions with the actual destination, payload preview, and risk class before anything proceeds. |
| `creative_studio` | `EvaDesktop.feature.creative_studio` | `VITE_EVAOS_CREATIVE_STUDIO` | On | Workbench + Creative Studio | `#102` | Creative Studio / Workspaces | Hosted Comfy path, login/embedded-page proof, no local GPU dependency | Hide dashboard route if needed; Workbench remains a hosted web link unless the product surface is retired | Open the hosted creative workflow studio from Workbench. |

Enable locally with:

```bash
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.providers_hub -bool true
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.shared_browser_2 -bool true
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.session_center -bool true
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.approval_center -bool true
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.creative_studio -bool true
```

Then relaunch Workbench. Disable with `defaults delete ... <key>` or set the key to `false`.

The dashboard uses matching build-time env flags, also defaulting to off:

```bash
VITE_EVAOS_PROVIDERS_HUB=true
VITE_EVAOS_SHARED_BROWSER_2=true
VITE_EVAOS_SESSION_CENTER=true
VITE_EVAOS_APPROVAL_CENTER=true
VITE_EVAOS_CREATIVE_STUDIO=true
```

When these are absent, the dashboard routes/sidebar entries remain dark even though the code can ship in the same release train.

## Current Scope

- Existing workspace order and persistent WebViews are unchanged.
- Business Browser remains the existing brokered `browser` runtime; infrastructure may still use `Shared Browser` or `Live Browser`.
- Creative Studio is a hosted WebView. Customers land on the hosted Comfy Cloud
  workspace; ComfyUI is not bundled in the macOS app.
- Connected Apps stores no raw app secrets in this slice. Connected state requires server-side proof metadata; stale metadata is shown as needing login rather than connected.
- Home is a native command-center registry for real workspace state, attention summaries, and recent work.
- No `cmux`, `cc-switch`, or ComfyUI dependency is embedded in the macOS app.

## Broker Actions

The Workbench macOS app talks to the existing `desktop-runtime-session` Supabase function with the desktop session token. The v0.5 additions are:

| Action | Purpose |
| --- | --- |
| `provider_profiles` | Read metadata-only provider profiles for the customer VM owner/admin target. |
| `provider_connect` | Mark a provider connected only when the control plane supplies signed provider-auth proof with identity, scopes, expiry, and a server-side secret reference. |
| `provider_switch` | Make an already connected provider active. |
| `provider_revoke` | Revoke the provider metadata profile and associated opaque agent grants. |
| `provider_mint_grant` | Mint or refresh an opaque grant handle for `openclaw` or `hermes`. |
| `runtime_status` | Read safe runtime status metadata for Workbench feature surfaces such as Home and the existing Business Browser workspace. |

Provider rows live in `customer_provider_profiles`; agent grants live in `customer_provider_agent_grants`. Both are RLS-enabled. Grant handles are broker handles only and must never be treated as raw provider credentials.

## Agent Metadata

OpenClaw and Hermes can discover v0.5 metadata without connector-token access:

```bash
evaosProviderProfiles
evaosProviderActiveProfile
evaosSharedBrowserGuidance
```

The VM environment may provide:

- `EVAOS_PROVIDER_DISCOVERY_URL` or `EVAOS_DESKTOP_RUNTIME_SESSION_URL`
- `EVAOS_PROVIDER_GRANT_HANDLE`
- `EVAOS_PROVIDER_PROFILES_JSON`
- `EVAOS_PROVIDER_GRANTS_JSON`
- `EVAOS_ACTIVE_PROVIDER_KEY`
- `EVAOS_SHARED_BROWSER_STATUS_JSON` using the `evaos.browser_status.v1`
  Business Browser contract when available
- `EVAOS_CUSTOMER_ID`

These commands intentionally return `raw_secrets_available: false`. Agents should use `evaosSharedBrowserGuidance` to prefer Business Browser for cloud web tasks that need persistent VM browser state, auth/CAPTCHA handoff, or human-visible browser collaboration.

## Release Gate

Do not turn a flag on for customers until the matching issue has:

- focused local or CI validation;
- one support canary;
- one friendly customer canary where applicable;
- rollback notes;
- no regressions to sign-in, existing workspaces, Mac/iPhone pairing, or Sparkle update.
