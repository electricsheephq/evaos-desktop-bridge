# Eva Desktop Mac Workbench

Eva Desktop is the downloadable macOS cockpit for evaOS runtimes. It wraps the
existing runtime UIs instead of rewriting them:

- evaOS / OpenClaw
- evaOS / Hermes
- Mission Control
- OpenDesign
- Live Browser
- Terminal

The MVP uses SwiftUI and `WKWebView` tabs. Local Mac control, iPhone Mirroring,
iMessage, voice, shell execution, and broad Accessibility/Screen Recording
permissions are intentionally out of scope for the first workbench sprint.

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
```

## Session Model

The app uses `ASWebAuthenticationSession` and Keychain for desktop login state.
Runtime launch URLs should come from the Electric Sheep backend session broker.
If no desktop session is present, the app uses the existing public runtime host
patterns as a preview/fallback so the shell remains usable during development.

The app does not store raw VM secrets, runtime backend tokens, auth headers, or
cookies in app model state.

Desktop login must return a broker-minted `desktop_session` with explicit
expiry. Generic OAuth authorization codes or provider `access_token` values are
not accepted as durable desktop sessions.

## Bridge Model

The `Desktop Bridge` panel is read-only in MVP. It can show bridge status,
capabilities, and audit tail by calling fixed `evaos-desktop-bridge` commands
after the user clicks refresh, but it does not expose local-control actions or a
generic command runner.
