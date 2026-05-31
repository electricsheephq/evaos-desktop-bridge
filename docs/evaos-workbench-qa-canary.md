# evaOS Workbench QA Canary Harness

The QA canary harness certifies the same connector contract used by customer
OpenClaw and Hermes agents. It is not a separate control backend; it exercises
the direct connector HTTP surface, the OpenClaw `runBridge(...)` wrapper, or the
Hermes shell adapter and writes pass/fail evidence for release gates.

Run artifacts live under:

```bash
/Volumes/LEXAR/Codex/evaos-workbench-qa-runs/<run-id>/
```

## Pre-Canary Guard

Before any signed-in Workbench GUI canary, verify the local Mac will not open a
stale Workbench build. This is intentionally lightweight and should run before
manual OAuth, Shared Browser, Session Center, Creative Studio, or Codex visible
GUI acceptance:

```bash
PYTHONPATH=src python3 -m evaos_desktop_bridge.pre_canary \
  --json \
  --expected-version "<version>" \
  --expected-build "<build>"
```

Installed environments can use:

```bash
evaos-workbench-pre-canary --json --expected-version "<version>" --expected-build "<build>"
```

If the canary will use the bridge's own Peekaboo-backed
`customer-mac desktop ...` commands instead of Codex's model-visible
`mcp__computer_use` tools, mark that explicitly:

```bash
evaos-workbench-pre-canary \
  --json \
  --expected-version "<version>" \
  --expected-build "<build>" \
  --control-surface bridge-peekaboo
```

The guard fails closed when:

- the canonical `/Applications/evaOS.app` is missing or the wrong version/build;
- Spotlight registers another app with bundle id
  `com.electricsheephq.EvaDesktop`;
- an old `EvaDesktop.app` exists in known Lexar canary artifact directories
  where macOS app-name lookup can still find it;
- a non-canonical or translocated `EvaDesktop.app` is running;
- too many `SkyComputerUseClient mcp` helper processes are present for a
  Codex-MCP canary.

For `--control-surface bridge-peekaboo`, a high Codex MCP helper count is a
warning instead of a failure because the canary is not using
`mcp__computer_use`. Continue only with the audited bridge/Peekaboo commands;
do not mix in Codex Computer Use calls until a separate `list_apps` health check
passes.

Set `EVAOS_CANARY_ARTIFACT_ROOTS` with `:`-separated paths, or pass repeated
`--canary-artifact-root PATH`, when a canary machine stores old Workbench app
artifacts outside the default Lexar locations.

If the guard fails, quarantine or quit the duplicate app/process first. Do not
collect signed-in canary screenshots from a contaminated environment.

Do not focus Workbench by the process name `EvaDesktop` or through
`open -a EvaDesktop`. The current supported app path is
`/Applications/evaOS.app`; app-name lookup can select deprecated beta artifacts
with the same bundle id/name.

Do not blindly `pkill` `SkyComputerUseClient mcp` helpers from the same Codex
thread that will run the GUI canary. Those helpers can be the live Computer Use
transport for the current agent, and killing them can leave subsequent
`mcp__computer_use` calls with `Transport closed`. If the helper herd check
fails, prefer a fresh Codex turn/tool-host restart, then re-run a read-only
Computer Use health check such as `list_apps` before any visible action.

Each run writes:

- `qa-report.json`
- `qa-report.md`
- downloaded screenshot artifacts under `evidence/` when the connector returns
  visual artifacts

## Inputs

```bash
export EVAOS_DESKTOP_BRIDGE_TOKEN="<paired connector token>"
export VERSION_UNDER_TEST="<exact-version-build>"

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "http://<mac-tailnet-ip>:8765" \
  --surface connector \
  --suite all \
  --operator-ack-live-control \
  --version-under-test "$VERSION_UNDER_TEST"
```

When running from an uninstalled checkout, prefix commands with
`PYTHONPATH=src`. Installed support VM environments do not need that prefix.
If `--version-under-test` is omitted, the report uses `local-dev`; release
certification must always pass the exact version/build candidate.
For `openclaw` or `hermes` surface runs from outside the repo checkout, pass
`--repo-root /Volumes/LEXAR/repos/evaos-desktop-bridge` or set
`EVAOS_DESKTOP_BRIDGE_QA_REPO_ROOT` so the harness can find the plugin and
adapter files.

Options:

- `--surface connector|openclaw|hermes`
- `--suite readiness|primitive|desktop_scenario|iphone_scenario|full_access|ask_permission|kill_switch|real_world_optional|all`
- `--artifact-dir /Volumes/LEXAR/Codex/evaos-workbench-qa-runs/<custom-run>`
- `--token-env <ENV_NAME>` if the connector token is not in
  `EVAOS_DESKTOP_BRIDGE_TOKEN`
- `--operator-ack-live-control` is required for suites that can move the
  mouse, type, click, scroll, or operate iPhone Mirroring
- `--allow-real-world-actions` to enable the optional app scenarios
- `--allow-skips` to permit skipped rows while iterating locally. Do not use
  this for release certification.
- `--repo-root <path>` for OpenClaw/Hermes adapter-surface runs from an
  installed Python environment

## Required Release Surfaces

Run all three surfaces before marking a release candidate certified:

```bash
export VERSION_UNDER_TEST="<exact-version-build>"

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface connector \
  --suite all \
  --operator-ack-live-control \
  --version-under-test "$VERSION_UNDER_TEST"

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface openclaw \
  --suite all \
  --operator-ack-live-control \
  --version-under-test "$VERSION_UNDER_TEST"

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface hermes \
  --suite all \
  --operator-ack-live-control \
  --version-under-test "$VERSION_UNDER_TEST"
```

Then run the destructive kill-switch proof once, after the other surfaces are
complete. A successful kill-switch run intentionally blocks future remote
control commands until Workbench starts a new control session:

```bash
python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface connector \
  --suite kill_switch \
  --operator-ack-live-control \
  --version-under-test "$VERSION_UNDER_TEST"
```

The OpenClaw path shells through `openclaw-plugin/scripts/qa-run-bridge.mjs`,
which reads the registered tools from `openclaw-plugin/dist/index.js`, runs the
desktop bridge firewall, then calls the same `runBridge(...)` wrapper.
The Hermes path shells through
`hermes-adapter/bin/evaos-desktop-bridge-command`. The direct connector path
posts to `/v1/commands`.

## Suites

- `readiness`: bridge status, customer Mac status, capabilities, control status,
  audit tail, and iPhone Mirroring status.
- `full_access`: starts Full Access and proves live scroll/hotkey do not require
  approval.
- `primitive`: safe-surface capability checks for desktop and iPhone control
  primitives. This proves the engine can click/type/scroll/drag/tap, but it is
  not scenario certification.
- `desktop_scenario`: captures an initial visual snapshot, opens a known
  browser page only from that verified state, captures a new snapshot, asserts
  the expected state, then performs follow-up actions from the verified page.
- `iphone_scenario`: focuses iPhone Mirroring, captures a pre-action iPhone
  snapshot, opens Calculator only from that verified state, verifies the screen,
  enters `1+1+1=`, captures another snapshot, then navigates Home, Spotlight,
  and App Switcher only after a verified iPhone state. The iPhone visual gate
  may use screenshot-derived app state because iPhone Mirroring exposes the
  phone contents as pixels, not normal Mac AX text.
- `ask_permission`: starts Ask Permission, proves a high-impact live type is
  denied without approval, then proves the dry-run audit id can approve the
  matching action.
- `kill_switch`: activates the kill switch and proves future live control fails
  closed. Run this last because it intentionally changes connector state.
- `real_world_optional`: Bumble, SMS, and social-post style workflows. These are
  never enabled unless `--allow-real-world-actions` is set and local environment
  variables provide exact text/contact/app values.

## Issue #130 Behavior Invariants

The issue #130 harness is separate from the connector/OpenClaw/Hermes canary
matrix because it starts a local native scratch app and verifies behavior, not
just connector argv shape. It is the release gate for sensitive-app denylist and
background-control safety regressions:

```bash
PYTHONPATH=src python3 -m evaos_desktop_bridge.behavior_harness \
  --suite issue130 \
  --repo-root /Volumes/LEXAR/repos/evaos-desktop-bridge \
  --artifact-dir /Volumes/LEXAR/Codex/evaos-desktop-bridge-issue130-runs/<run-id> \
  --sensitive-app "System Settings" \
  --operator-ack-live-control
```

The harness writes `issue130-behavior-report.json` and
`issue130-behavior-report.md`. Required checks:

- `intended_effect`: a live scratch-app action increments exactly once.
- `frontmost_unchanged`: the live action does not steal focus away from the
  target app.
- `cursor_not_warped`: the user's cursor does not jump to the action point.
- `occluded_capture_target_pixels`: occluded capture returns the target marker,
  not the covering window marker.
- `policy_denied_zero_effect`: a denied live command has no scratch-state
  effect.
- `sensitive_denylist_all_observation_paths`: `desktop see`, `snapshot`, and
  `ax-tree` all fail closed with `sensitive_app_blocked`.

`primitive` and `scenario` lanes are both required. Primitive rows prove the
transport and automation engine; scenario rows prove the agent-style loop. Real
task canaries must use a fresh `iphone_see` or `desktop_see` before live
scenario actions, run one action only from that visual evidence, then capture
another `see` result to prove the intended state changed. Do not use blind
swipes or coordinates for scenario certification.

Known 0.6.5 release-reality result from the 2026-05-27 fresh canary:

- Connector/OpenClaw/Hermes `--suite all` each passed 33/44 rows before the
  harness bootstrap fix.
- Foreground Mac and iPhone primitive rows passed, including desktop see/click/
  type/scroll/drag/hotkey and iPhone focus/open-app/see/tap/type.
- Desktop scenario passed 5/5 after adding the initial visual bootstrap.
- iPhone scenario still has a product/tuning gap: `open Calculator` can return
  ok while the visible phone remains in the previous app.
- Codex app-server rows failed in the installed 0.6.5 LaunchAgent because that
  packaged helper could not find `codex` on `PATH`; the source bridge now
  prefers the Codex app bundle CLI to close that gap.

Known 0.6.7 release-reality result from the 2026-05-29 fresh canary:

- The correctly packaged `/Applications/evaOS.app` 0.6.7 build 47 connector
  passed Codex readiness/status and foreground Mac primitive/scenario rows.
- The remaining iPhone rows were traced to live-run contamination and harness
  evidence parsing, not a confirmed product-control regression: a transient
  Spotlight/notification overlay covered one frame, and `iphone_see` returned
  the phone contents as a screenshot artifact with only an iPhone Mirroring
  window AX element.
- The harness now retries transient visual assertion mismatches and can derive
  Calculator state from the materialized screenshot artifact before allowing
  the next live scenario action.

Live GUI-control rows are only valid when the operator has yielded the screen.
For Codex Desktop visible-message tests in particular, notification banners,
Focus/Spotlight overlays, permission prompts, lock-screen transitions, or manual
operator interaction can hide the composer or selected row while the bridge is
acting. Mark those rows `contaminated` or `inconclusive`, keep the screenshot as
evidence, and rerun in a quiet window; do not treat them as product failures.

The command timeout is per primitive command, not a task budget. A multi-minute
agent task is expected to issue many bounded commands. Current defaults are 60s
for visual `see` commands, 30s for click/tap, 20s for drag/swipe/browser/menu
style actions, 15s for type/hotkey, and 10s for unknown future commands.

## Real-World Optional Config

These values are local-only. Do not commit them, paste them into PR bodies, or
copy the full values into release notes.

```bash
export QA_BUMBLE_TEXT="..."
export QA_SMS_CONTACT="..."
export QA_SMS_TEXT="..."
export QA_SOCIAL_APP="..."
export QA_SOCIAL_TEXT="..."

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface openclaw \
  --suite real_world_optional \
  --operator-ack-live-control \
  --allow-real-world-actions
```

The JSON and Markdown reports redact tokens, contact names, and configured
message text. For OpenClaw and Hermes surfaces, the exact configured text is
passed through stdin instead of process argv so it is not exposed in process
listings while the QA process is running.

## Certification Rule

No release is marked ready unless the QA folder contains explicit rows for every
required suite and the CLI exits `0` without `--allow-skips`. Skipped rows in
required suites are treated as a non-green run because they mean a capability
was not proven. If the harness finds product bugs, fix the app/connector and
rerun the full harness before packaging the next release. If all required suites
pass against the live release, record the run folder as the certification
artifact for that version.
