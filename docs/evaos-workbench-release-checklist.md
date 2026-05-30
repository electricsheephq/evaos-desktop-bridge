---
title: "evaOS Workbench Release Checklist"
status: active
created: 2026-05-22
---

# evaOS Workbench Release Checklist

## Purpose

This is the canonical release checklist for Workbench source, GitHub releases,
dashboard-hosted artifacts, Sparkle appcasts, Lovable publishing, and live
download verification.

## Release Gates

A release is not ready to send to testers until all of these are true:

- Source changes are merged in `electricsheephq/evaos-desktop-bridge`.
- GitHub Release `evaos-workbench-vX.Y.Z` exists with ZIP, `updates.json`, and
  `appcast.xml`.
- Dashboard artifact PR is merged in
  `electricsheephq/electric-sheep-website-dashboard-6158a244`.
- Lovable has been published with `Publish -> Update`.
- Live `updates.json`, `appcast.xml`, and ZIP are fetched from
  `https://www.electricsheephq.com/evaos-workbench/`.
- The live ZIP has been downloaded, unzipped, rpath-checked, codesign-checked,
  and launch-smoked.
- Agent launch smoke uses `./script/build_and_run.sh --verify-agent-qa` or an
  app copied to the internal disk, not `dist/evaOS.app` launched directly from
  `/Volumes/LEXAR`.
- Stale public ZIP paths for broken or stale builds are removed or aliased to
  the current fixed ZIP.
- For Workbench `0.2.3+`, Copy Agent Prompt is verified to use
  `customer_mac_complete_pairing`, not support-only shell steps.

## Source Build

Use a clean Lexar-backed worktree:

```bash
cd /Volumes/LEXAR/repos/evaos-desktop-bridge
git status -sb
git fetch origin
git worktree add -b codex/workbench-X.Y.Z \
  /Volumes/LEXAR/repos/worktrees/evaos-desktop-bridge-X.Y.Z origin/main
cd /Volumes/LEXAR/repos/worktrees/evaos-desktop-bridge-X.Y.Z/apps/eva-desktop-mac
```

Run focused validation:

```bash
swift build
swift run EvaDesktopCoreSmoke
```

Build a Developer ID release:

```bash
EVA_DESKTOP_CODESIGN_IDENTITY='Developer ID Application: Andrew Ryan (TC6MS3T6NN)' \
  ./script/build_and_run.sh --package-release
```

Check Sparkle packaging before publishing:

```bash
test -d dist/evaOS.app/Contents/Frameworks/Sparkle.framework
otool -l dist/evaOS.app/Contents/MacOS/EvaDesktop | grep -A2 LC_RPATH
codesign --verify --deep --strict dist/evaOS.app
```

The executable must include `@executable_path/../Frameworks`. This check exists
because Workbench `0.2.0` shipped with Sparkle linked but not loadable.

## Notarization

Submit notarization with bounded waits only. Do not block an agent terminal for
hours waiting on Apple.

```bash
EVA_DESKTOP_CODESIGN_IDENTITY='Developer ID Application: Andrew Ryan (TC6MS3T6NN)' \
EVA_DESKTOP_NOTARY_PROFILE='evaos-workbench-notary' \
  ./script/build_and_run.sh --notarize-release
```

If Apple returns `In Progress`, save the submission id, artifact SHA, and path,
then poll through a heartbeat or separate follow-up. If accepted, staple,
rebuild the ZIP, regenerate `updates.json` and `appcast.xml`, and republish the
dashboard artifact.

GA requires:

```bash
xcrun stapler validate dist/evaOS.app
spctl --assess --type execute dist/evaOS.app
```

Friendly beta may ship before notarization only when the release notes and
install page call out the non-stapled state.

## Agent Launch Smoke

macOS can prompt for both Keychain item access and removable-volume access while
agents are testing locally. Do not spend autonomous test loops on those prompts.
For non-authenticated visible UI smoke, run:

```bash
cd apps/eva-desktop-mac
./script/build_and_run.sh --run-agent-qa
```

For process-only launch smoke, run:

```bash
cd apps/eva-desktop-mac
./script/build_and_run.sh --verify-agent-qa
```

Both paths copy the app bundle to `~/Applications` and disable Workbench
Keychain reads/writes for the launched process. The default `run` path routes
`dist/evaOS.app` launches from `/Volumes/LEXAR` through the same prompt-free
agent-QA copy unless
`EVAOS_WORKBENCH_ALLOW_REMOVABLE_LAUNCH=1` is set for a human-approved run. For
real signed-in acceptance, install the Developer ID signed build on the internal
disk and use a stable signing identity; if an old beta item still prompts, clear
only the Workbench `com.electricsheephq.EvaDesktop.session` and
`com.electricsheephq.EvaDesktop.capabilities` generic-password items before
signing in again.

## Dashboard Artifact And Lovable

Use a clean dashboard worktree:

```bash
git -C /Volumes/LEXAR/repos/electric-sheep-website-dashboard-6158a244 fetch origin
git -C /Volumes/LEXAR/repos/electric-sheep-website-dashboard-6158a244 worktree add \
  -b codex/workbench-X.Y.Z-artifact \
  /Volumes/LEXAR/repos/worktrees/electric-sheep-dashboard-workbench-X.Y.Z origin/main
```

Copy:

Upload the ZIP to the GitHub Release named `evaos-workbench-vX.Y.Z`. Do not
commit new Workbench ZIP binaries into the dashboard repo. The dashboard only
publishes customer copy plus update metadata that points Sparkle and legacy
clients at the GitHub-hosted asset.

```bash
cp /Volumes/LEXAR/repos/worktrees/evaos-desktop-bridge-X.Y.Z/apps/eva-desktop-mac/dist/updates.json \
  public/evaos-workbench/updates.json
cp /Volumes/LEXAR/repos/worktrees/evaos-desktop-bridge-X.Y.Z/apps/eva-desktop-mac/dist/appcast.xml \
  public/evaos-workbench/appcast.xml
```

Update the install page and route test, open a PR, wait for Build & Typecheck,
CodeRabbit, and Socket, then merge.

After merge, open Lovable project
`https://lovable.dev/projects/b1e45b7c-aec5-4d96-9dc8-c7b20df68856` and click
`Publish -> Update`. GitHub merge alone is not production.

## Live Verification

Verify production after Lovable:

```bash
curl -fsSL 'https://www.electricsheephq.com/evaos-workbench/updates.json?cb=<merge_sha>'
curl -fsSL 'https://www.electricsheephq.com/evaos-workbench/appcast.xml?cb=<merge_sha>'
curl -fsSI 'https://github.com/electricsheephq/evaos-workbench-releases/releases/download/evaos-workbench-vX.Y.Z/evaOS-Workbench-X.Y.Z.zip'
```

Download and launch-smoke the live artifact:

```bash
mkdir -p /Volumes/LEXAR/Codex/workbench-live-smoke-X.Y.Z
cd /Volumes/LEXAR/Codex/workbench-live-smoke-X.Y.Z
curl -fsSLO 'https://github.com/electricsheephq/evaos-workbench-releases/releases/download/evaos-workbench-vX.Y.Z/evaOS-Workbench-X.Y.Z.zip'
unzip -q evaOS-Workbench-X.Y.Z.zip
test -d evaOS.app/Contents/Frameworks/Sparkle.framework
otool -l evaOS.app/Contents/MacOS/EvaDesktop | grep -A2 LC_RPATH
codesign --verify --deep --strict evaOS.app
open evaOS.app
```

Only after this can the direct download link be sent to a tester.
