# evaOS Workbench v0.5 One-App Expansion

This release train keeps the existing Workbench gateways stable while new OS-level surfaces are built behind flags. Incomplete lanes must stay dark-launched until their canary gates pass.

## Feature Flags

All flags default to `false` and are read from `UserDefaults` on app launch.

| Flag | UserDefaults key | Primary issue | Surface |
| --- | --- | --- | --- |
| `providers_hub` | `EvaDesktop.feature.providers_hub` | `#96` | Native Providers & Auth Hub metadata surface |
| `shared_browser_2` | `EvaDesktop.feature.shared_browser_2` | `#97` | Shared Browser 2.0 status/control preview |
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

## Current Scope

- Existing gateway runtime order and persistent WebViews are unchanged.
- Shared Browser remains the existing brokered `browser` runtime; customer-facing copy stays `Shared Browser`, while infrastructure may still use `Live Browser`.
- Creative Studio is hosted/configured URL first at `<dashboard-base-url>/creative-studio` and opens inside Workbench when the flag is enabled.
- Provider/Auth Hub stores no raw provider secrets in this slice; it exposes provider readiness metadata only.
- Session Center is a native dark-launch registry for current gateway state and attention summaries.
- No `cmux`, `cc-switch`, or ComfyUI dependency is embedded in the macOS app.

## Release Gate

Do not turn a flag on for customers until the matching issue has:

- focused local or CI validation;
- one support canary;
- one friendly customer canary where applicable;
- rollback notes;
- no regressions to sign-in, existing gateways, Mac/iPhone pairing, or Sparkle update.
