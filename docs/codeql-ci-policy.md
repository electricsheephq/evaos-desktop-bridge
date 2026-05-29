# CodeQL CI Policy

The repository uses advanced CodeQL workflows instead of GitHub CodeQL default setup so CI can keep security coverage without running macOS Swift analysis on every PR push.

## Policy

- Pull requests that touch Python, JavaScript/TypeScript, OpenClaw plugin, tests, or workflow files run `CodeQL Core` on Linux.
- Pull requests do not run Swift CodeQL; the existing `Eva Desktop Workbench` PR workflow remains the fast Swift compile/smoke gate.
- Swift CodeQL runs on every push to `main`, version tag push, published GitHub release, daily schedule, and manual dispatch.
- The existing `Eva Desktop Workbench` PR workflow remains the fast compile/smoke gate for Swift changes.
- PR runs use `concurrency.cancel-in-progress` so superseded pushes stop burning runner minutes.

## Repository Setting Migration

GitHub rejects advanced CodeQL SARIF uploads while CodeQL default setup is enabled. Disable default setup when migrating to these advanced workflows:

```bash
gh api \
  -X PATCH \
  repos/electricsheephq/evaos-desktop-bridge/code-scanning/default-setup \
  -H "Accept: application/vnd.github+json" \
  -f state=not-configured
```

Verify the state:

```bash
gh api repos/electricsheephq/evaos-desktop-bridge/code-scanning/default-setup \
  -H "Accept: application/vnd.github+json"
```

Expected migration state: `not-configured`.

## Rationale

GitHub's Swift CodeQL analysis uses macOS runners. GitHub recommends building only the code you want to analyze because GitHub-hosted macOS runners cost more than Linux and Windows runners. Swift CodeQL supports `autobuild` or `manual`, and `swift build --arch arm64` is a supported targeted build pattern. This repo's Swift app lives under `apps/eva-desktop-mac`, so the advanced Swift workflow builds the `EvaDesktop` product for one architecture only when the repository is cutting or validating a release stream.
