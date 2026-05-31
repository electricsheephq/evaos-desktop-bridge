# evaOS Workbench v0.5 One-App Expansion

This release train keeps the existing Workbench gateways stable while new OS-level surfaces are built behind flags. Incomplete lanes must stay dark-launched until their canary gates pass.

## Information Architecture

The v0.5 expansion keeps the first screen operational: customers land in the gateway workspace, not a marketing page or placeholder dashboard. New OS surfaces appear only when their flags are enabled and their evidence path is real.

| State | Sidebar / Settings | Detail Behavior | Degraded Behavior |
| --- | --- | --- | --- |
| Signed out | Gateway list, Mac & iPhone, sign-in affordance | Brokered gateways show the existing sign-in panel and store only an opaque desktop session after login | No provider, session, or runtime truth is inferred from cached UI state |
| Signed in, normal customer | Gateway list; Providers under Settings when enabled; Session Center under Workspace when enabled | Runtime tabs load broker-issued launch URLs in isolated WebViews; Session Center reads broker/bridge evidence | Runtime errors stay on the affected card/tab and do not hide other gateways |
| Signed in, admin/support customer switch | Same normal-customer layout plus customer-target switcher in the sidebar footer | Switching customer resets loaded runtime URLs and WebView identity to the selected customer | Wrong-customer cookies are discarded through per-customer non-persistent WebView stores |
| Existing gateway fallback | OpenClaw, Hermes, Mission Control, OpenDesign, Shared Browser, and Terminal remain direct gateway entries | Existing launch/reconnect/reload/open behavior stays stable regardless of dark-launched surfaces | Feature rollback disables only the new surface; direct gateway launch remains available |
| Creative Studio enabled | Creative Studio appears in Gateways | Opens the brokered hosted/customer ComfyUI route; the macOS app does not bundle ComfyUI, GPUs, or workflows | Disable the flag to remove the entry without affecting brokered runtimes |

Surface ownership:

- Sidebar `Gateways`: brokered runtimes plus hosted Creative Studio when enabled.
- Sidebar `Mac & iPhone`: local bridge readiness and named local-control surfaces only.
- Settings-style surface `Providers`: provider metadata, connect/revoke/switch/grant actions, and no raw provider secrets.
- Workspace `Session Center`: read-only session records, attention states, queue/audit/Codex evidence, and jump-back routes.

## Feature Flags

All flags default to `false` and are read from `UserDefaults` on app launch.

| Flag | UserDefaults key | Dashboard env | Default | Owner | Primary issue | Surface / Placement | Rollout criteria | Rollback action | Public copy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `providers_hub` | `EvaDesktop.feature.providers_hub` | `VITE_EVAOS_PROVIDERS_HUB` | Off | Workbench + Broker | `#96` | Providers / Settings | Broker provider-profile proof, provider connect/revoke canary, OpenClaw/Hermes grant discovery, rollback runbook | Disable flag and keep existing gateway tabs unchanged | Connect provider accounts once so Eva agents can reuse brokered access without raw secrets in Workbench. |
| `shared_browser_2` | `EvaDesktop.feature.shared_browser_2` | `VITE_EVAOS_SHARED_BROWSER_2` | Off | Workbench + Dashboard + ws-proxy | `#97` | Shared Browser / Gateway metadata | Runtime-status health proof, KasmVNC/noVNC canary, provider handoff canary, customer rollback proof | Hide enhanced metadata while leaving the base Shared Browser gateway visible | Use one shared VM browser for sign-in, CAPTCHA, and collaborative web tasks. |
| `session_center` | `EvaDesktop.feature.session_center` | `VITE_EVAOS_SESSION_CENTER` | Off | Workbench + Dashboard | `#100` | Session Center / Workspace | Runtime/session truth, queue/audit/Codex evidence, relaunch restore, dashboard parity, signed-in Workbench canary | Disable flag and keep direct gateway launch paths available | See active Eva sessions, attention states, and where to jump back in. |
| `creative_studio` | `EvaDesktop.feature.creative_studio` | `VITE_EVAOS_CREATIVE_STUDIO` | Off | Workbench + Creative Studio | `#102` | Creative Studio / Gateways | Hosted ComfyUI path, login/degraded-state proof, support canary, no local GPU dependency | Disable flag and remove Creative Studio from the gateway list | Open the hosted creative workflow studio from Workbench. |

Enable locally with:

```bash
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.providers_hub -bool true
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.shared_browser_2 -bool true
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.session_center -bool true
defaults write com.electricsheephq.EvaDesktop EvaDesktop.feature.creative_studio -bool true
```

Then relaunch Workbench. Disable with `defaults delete ... <key>` or set the key to `false`.

The dashboard uses matching build-time env flags, also defaulting to off:

```bash
VITE_EVAOS_PROVIDERS_HUB=true
VITE_EVAOS_SHARED_BROWSER_2=true
VITE_EVAOS_SESSION_CENTER=true
VITE_EVAOS_CREATIVE_STUDIO=true
```

When these are absent, the dashboard routes/sidebar entries remain dark even though the code can ship in the same release train.

## Current Scope

- Existing gateway runtime order and persistent WebViews are unchanged.
- Shared Browser remains the existing brokered `browser` runtime; customer-facing copy stays `Shared Browser`, while infrastructure may still use `Live Browser`.
- Creative Studio is a first-class brokered `creative_studio` runtime. Enabled customers land in the hosted ComfyUI gateway; ComfyUI is not bundled in the macOS app.
- Providers stores no raw provider secrets in this slice. Connected state requires server-side proof metadata; stale metadata is shown as needing login rather than connected.
- Session Center is a native dark-launch registry for real gateway state and attention summaries.
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
| `runtime_status` | Read safe runtime status metadata for Workbench feature surfaces such as Session Center and the existing Shared Browser gateway. |

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
- `EVAOS_SHARED_BROWSER_STATUS_JSON`
- `EVAOS_CUSTOMER_ID`

These commands intentionally return `raw_secrets_available: false`. Agents should use `evaosSharedBrowserGuidance` to prefer Shared Browser for cloud web tasks that need persistent VM browser state, auth/CAPTCHA handoff, or human-visible browser collaboration.

## Release Gate

Do not turn a flag on for customers until the matching issue has:

- focused local or CI validation;
- one support canary;
- one friendly customer canary where applicable;
- rollback notes;
- no regressions to sign-in, existing gateways, Mac/iPhone pairing, or Sparkle update.
