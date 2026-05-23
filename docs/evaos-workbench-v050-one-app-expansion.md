# evaOS Workbench v0.5 One-App Expansion

This release train keeps the existing Workbench gateways stable while new OS-level surfaces are built behind flags. Incomplete lanes must stay dark-launched until their canary gates pass.

## Feature Flags

All flags default to `false` and are read from `UserDefaults` on app launch.

| Flag | UserDefaults key | Primary issue | Surface |
| --- | --- | --- | --- |
| `providers_hub` | `EvaDesktop.feature.providers_hub` | `#96` | Native Providers & Auth Hub metadata surface |
| `shared_browser_2` | `EvaDesktop.feature.shared_browser_2` | `#97` | Enhanced metadata on the existing Shared Browser gateway |
| `session_center` | `EvaDesktop.feature.session_center` | `#100` | Native Session Center registry surface |
| `creative_studio` | `EvaDesktop.feature.creative_studio` | `#102` | Hosted Creative Studio gateway surface |

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
- Provider/Auth Hub stores no raw provider secrets in this slice. Connected state requires server-side proof metadata; stale metadata is shown as needing login rather than connected.
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
