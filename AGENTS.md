# AGENTS.md - evaOS Desktop Bridge

## Scope

This repository owns the guarded desktop bridge plus the native evaOS Workbench
Mac app under `apps/eva-desktop-mac/`. Follow the shared owned-repo operating
policy from `100yenadmin/codex-operating-kit`, and keep repo-specific release,
signing, notarization, appcast, TCC, and customer-canary gates in this repo's
runbooks.

## Tracking And PR Lifecycle

- Track meaningful work in GitHub issues before implementation. Use tracker
  issues or milestones when work spans multiple PRs, release gates, customers,
  runtime surfaces, or days.
- Link each PR to its implementation issue and to any tracker/milestone it
  depends on. Update the issue or tracker before pausing, handoff, merge, or
  release.
- Before claiming PR readiness, query current-head `reviewThreads` and report
  `total`, `currentActionable`, and `outdated`. Treat top-level bot comments,
  skipped-review notices, rate-limit notices, and check annotations as separate
  status inputs, not resolvable review threads.
- P0-P2 current actionable review threads block merge, release, and readiness
  claims unless fixed, proven false-positive, or explicitly escalated. P3
  advisory threads still need terminal disposition before closeout.

## Release Notes

- Keep `CHANGELOG.md` human-readable and outcome-first. Release-impacting PRs
  need a user/operator-facing changelog entry or an explicit no-impact
  rationale.
- Visible GitHub releases and prereleases should lead with the human outcome,
  grouped highlights/changes/fixes, and only then a compact verification tail.
  Operator packets, commands, rollback notes, and artifact inventories may be
  linked from the release note, but should not replace the visible narrative.
- Preserve the existing Workbench release cadence in
  `docs/evaos-workbench-build-release-runbook.md`,
  `docs/evaos-workbench-release-checklist.md`, and
  `docs/evaos-workbench-beta-release.md`.

## Validation Boundaries

- For docs, PR-template, issue-comment, changelog, or metadata-only changes,
  use `git diff --check` plus GitHub CI. Do not run local Swift builds,
  signing, notarization, appcast generation, GUI canaries, or installed-app
  proof unless the change touches Swift source, packaging/resource contracts,
  GUI actuation, TCC/helper identity, Keychain/session state, or release
  workflows.
- For Workbench Mac app changes, read `apps/eva-desktop-mac/AGENTS.md` and the
  relevant release runbook before choosing validation or release gates.
- Do not expose arbitrary shell, hidden AppleScript passthrough, password
  capture, generic Codex app-server mutation, public VNC/SSH, or broad local
  Mac control outside the named audited bridge/tool contracts.
