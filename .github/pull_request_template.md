# Pull Request

## Summary

<!-- Describe the user/operator-facing outcome and the repo surface touched. -->

## Linked Work

<!-- Use "Closes #123" or "Fixes #123" only when this PR completes the issue. Link trackers without closing unless complete. -->

- Closes/Fixes:
- Tracker/milestone:
- Evidence path:

## Type of Change

- [ ] Bug fix
- [ ] Feature
- [ ] Security/privacy boundary
- [ ] Documentation update
- [ ] Policy/template-only update
- [ ] Release/cadence update

## PR Lifecycle

- [ ] Current-head review threads queried: `total=`, `currentActionable=`, `outdated=`
- [ ] Top-level bot comments, skipped-review/rate-limit notices, and check annotations reviewed separately from review threads
- [ ] CI/checks reviewed:
- [ ] Review bot status reviewed:
- [ ] All P0-P2 actionable review threads fixed, proven false-positive, or explicitly escalated
- [ ] P3/advisory review threads have terminal disposition

## Release Notes And Changelog

- Release-note impact:
  - [ ] Human-readable `CHANGELOG.md` entry added
  - [ ] Draft GitHub release-note entry included below
  - [ ] No release-note impact; rationale:
- Release-proof tier:
  - [ ] Not release-affecting
  - [ ] Dev proof
  - [ ] Staging artifact proof
  - [ ] Release proof
- Workbench release gates:
  - [ ] No signing/notarization/appcast/customer distribution touched
  - [ ] Existing Workbench runbooks/checklists remain applicable
  - [ ] TCC/helper identity and GUI canary gates are unchanged or explicitly validated

### Draft Release Note

<!-- Human-readable first: opening outcome summary, grouped highlights/changes/fixes, then compact verification/evidence. Link operator packets instead of pasting command dumps. -->

## Validation

- [ ] `git diff --check`
- [ ] Focused tests/smoke:
- [ ] GitHub Actions:
- [ ] Docs/template-only change; local Swift build, signing, notarization, appcast, GUI canary, and installed-app proof not required

## Risk And Rollout

<!-- Include release boundaries, rollback notes, customer/runtime safety boundaries, or "not runtime/release-affecting". -->

## Next-Agent Notes

<!-- Handoff-quality notes: exact next action, blockers, deferred threads, release boundaries, evidence links. -->
