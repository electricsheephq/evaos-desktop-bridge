# evaOS Workbench

evaOS Workbench is the downloadable macOS cockpit for evaOS runtimes. It wraps the
existing runtime UIs instead of rewriting them:

- evaOS / OpenClaw
- evaOS / Hermes
- Mission Control
- OpenDesign
- Live Browser
- Terminal

The MVP uses SwiftUI and `WKWebView` tabs. Local Mac control and iPhone
Mirroring are surfaced as connector status in the canary, but the app does not
expose live local-control buttons, iMessage, voice, shell execution, or broad
Accessibility/Screen Recording prompts in the Workbench UI.

The visible app name and native shell use ElectricSheep branding, while the
internal executable and bundle id remain `EvaDesktop` /
`com.electricsheephq.EvaDesktop` so existing Keychain sessions and URL-scheme
callbacks keep working.

## Run Locally

```bash
./script/build_and_run.sh
```

Useful modes:

```bash
./script/build_and_run.sh --verify
./script/build_and_run.sh --logs
./script/build_and_run.sh --telemetry
```

## Validate

```bash
swift build
swift run EvaDesktopCoreSmoke
./script/build_and_run.sh --verify
```

## Branding Contract

Visible product copy is centralized in `Sources/EvaDesktopCore/Models/AppBrand.swift`.
Use `evaOS Workbench` for the Mac app name and `Gateways` for the runtime
launcher group. Keep the internal executable name and bundle identifier as
`EvaDesktop` / `com.electricsheephq.EvaDesktop`; changing those breaks the
existing URL scheme and Keychain namespace.

The sidebar intentionally shows the ElectricSheep wordmark once. Do not add a
second app title in the split-view sidebar or top toolbar. Runtime rows should
stay terse: icon plus runtime name, with no explanatory subtext unless a runtime
is unavailable.

## Resource Packaging

Runtime assets live in `Resources/`:

- `AppIcon.icns` for Finder, Dock, and app switcher branding.
- `electric-sheep-wordmark.png` for the restrained sidebar brand mark.

`script/build_and_run.sh` copies those resources into the app bundle, writes the
bundle metadata, and signs the final `.app` after `Info.plist` and resources are
in place. If `EVA_DESKTOP_CODESIGN_IDENTITY` or `CODESIGN_IDENTITY` is set, that
identity is used. Otherwise the script uses ad-hoc signing for local development.

## Keychain And Signing

The app reads Keychain non-interactively at launch. If macOS cannot trust the
current local build to access an older desktop session item, the app treats that
as signed out instead of showing a Keychain prompt during normal startup.

Repeated Keychain prompts are a signing problem, not an authentication feature.
For a durable local or release build, sign the finished app bundle with a stable
Apple Development or Developer ID identity. Ad-hoc SwiftPM rebuilds can change
the code identity and make macOS ask whether the new build may access the old
Keychain item.

If a development machine already has a stale prompt-causing item, clear just the
desktop session item and sign in again:

```bash
security delete-generic-password \
  -s com.electricsheephq.EvaDesktop.session \
  -a desktop-session
```

## Session Model

The app uses `ASWebAuthenticationSession` and Keychain for desktop login state.
Desktop login opens `https://www.electricsheephq.com/desktop-auth` in a secure
system popup, then returns an opaque `desktop_session` through the
`evaos://auth/callback` URL scheme. Runtime launch URLs come from the Supabase
Edge Function broker at
`https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/desktop-runtime-session`.
If no desktop session is present, runtime tabs show a native sign-in prompt
instead of loading public website or dashboard routes inside the workbench.

For local auth testing, launch the bundled app with `./script/build_and_run.sh`.
The raw `swift run EvaDesktop` executable does not register the `evaos://` URL
scheme with Launch Services, so the browser callback cannot reliably return to
the app in that mode.

The app does not store raw VM secrets, runtime backend tokens, auth headers, or
cookies in app model state.

Desktop login must return a broker-minted `desktop_session` with explicit
expiry. Generic OAuth authorization codes or provider `access_token` values are
not accepted as durable desktop sessions.

Admin and customer-service desktop sessions can request a safe customer target
list from the broker. The app renders that as an admin-only picker in the
gateway toolbar. Switching customers clears loaded gateway WebViews and reloads
the selected gateway through the broker, preserving the same server-side access
checks used by the web dashboard.

Sign-out clears Keychain and best-effort revokes the opaque desktop session in
Supabase. VM runtime cookies are still minted by `evaos-ws-proxy`; they are not
stored in Keychain or app model state.

## Bridge Model

The `Desktop Bridge` panel is a status and revocation surface in the canary. It
can show bridge status, customer Mac status, iPhone Mirroring status, Screen
Sharing status, capabilities, and audit tail by calling fixed
`evaos-desktop-bridge` commands after the user clicks refresh. It does not expose
local-control action buttons or a generic command runner.

## OpenDesign

OpenDesign is configurable before the permanent route is locked. Add an
OpenDesign URL in Settings and the OpenDesign gateway will load it directly in a
persistent WebView. If the URL is blank, the tab stays in a clean unavailable
state instead of detouring through the dashboard.
