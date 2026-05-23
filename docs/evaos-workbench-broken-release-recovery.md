---
title: "evaOS Workbench Broken Release Recovery"
status: active
created: 2026-05-22
---

# evaOS Workbench Broken Release Recovery

## Purpose

Use this when a released Workbench build is stale, cannot launch, cannot
self-update, or remains reachable through an old public URL.

## 0.2.0 Incident Pattern

Workbench `0.2.0` linked Sparkle but the app executable could not find the
bundled framework at runtime. The crash showed:

```text
Library not loaded: @rpath/Sparkle.framework/Versions/B/Sparkle
```

The fix was a new release with the Sparkle framework bundled under
`Contents/Frameworks` and an executable rpath of
`@executable_path/../Frameworks`.

Because `0.2.0` could not launch, it could not self-update. Users on that build
needed a manual reinstall.

## Recovery Steps

1. Stop recommending the broken direct ZIP URL.
2. Mark the broken GitHub Release as superseded or prerelease.
3. Remove the broken asset from the GitHub Release when possible.
4. Publish a fixed release.
5. Update the dashboard install page with a visible recovery note.
6. If the old public static path remains reachable, replace it with a byte-copy
   of the fixed ZIP and verify the old and new SHA match.
7. Tell affected users to delete the broken app and install the fixed build.

## Verification

For the fixed artifact:

```bash
curl -fsSLO 'https://github.com/electricsheephq/evaos-desktop-bridge/releases/download/evaos-workbench-vX.Y.Z/evaOS-Workbench-X.Y.Z.zip'
unzip -q evaOS-Workbench-X.Y.Z.zip -d fixed
test -d fixed/evaOS.app/Contents/Frameworks/Sparkle.framework
otool -l fixed/evaOS.app/Contents/MacOS/EvaDesktop | grep -A2 LC_RPATH
codesign --verify --deep --strict fixed/evaOS.app
```

For old-path aliasing:

```bash
curl -fsSLO 'https://github.com/electricsheephq/evaos-desktop-bridge/releases/download/evaos-workbench-vOLD/evaOS-Workbench-OLD.zip'
curl -fsSLO 'https://github.com/electricsheephq/evaos-desktop-bridge/releases/download/evaos-workbench-vX.Y.Z/evaOS-Workbench-X.Y.Z.zip'
shasum -a 256 evaOS-Workbench-OLD.zip evaOS-Workbench-X.Y.Z.zip
```

The SHAs must match if the old path is intentionally kept alive as a safe alias.

## Customer Copy

Use concise customer-facing language:

```text
The earlier Workbench build could not open, so it cannot update itself. Delete
the broken app, download the latest Workbench from the install page, unzip it,
and drag evaOS.app to Applications.
```

Do not ask customers to disable Gatekeeper globally.
