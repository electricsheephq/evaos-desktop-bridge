# evaOS Workbench QA Canary Harness

The QA canary harness certifies the same connector contract used by customer
OpenClaw and Hermes agents. It is not a separate control backend; it exercises
the direct connector HTTP surface, the OpenClaw `runBridge(...)` wrapper, or the
Hermes shell adapter and writes pass/fail evidence for release gates.

Run artifacts live under:

```bash
/Volumes/LEXAR/Codex/evaos-workbench-qa-runs/<run-id>/
```

Each run writes:

- `qa-report.json`
- `qa-report.md`
- downloaded screenshot artifacts under `evidence/` when the connector returns
  visual artifacts

## Inputs

```bash
export EVAOS_DESKTOP_BRIDGE_TOKEN="<paired connector token>"

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "http://<mac-tailnet-ip>:8765" \
  --surface connector \
  --suite all \
  --operator-ack-live-control \
  --version-under-test 0.6.2
```

When running from an uninstalled checkout, prefix commands with
`PYTHONPATH=src`. Installed support VM environments do not need that prefix.
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
python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface connector \
  --suite all \
  --operator-ack-live-control \
  --version-under-test 0.6.2

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface openclaw \
  --suite all \
  --operator-ack-live-control \
  --version-under-test 0.6.2

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface hermes \
  --suite all \
  --operator-ack-live-control \
  --version-under-test 0.6.2
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
  --version-under-test 0.6.2
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
  and App Switcher only after a verified iPhone state.
- `ask_permission`: starts Ask Permission, proves a high-impact live type is
  denied without approval, then proves the dry-run audit id can approve the
  matching action.
- `kill_switch`: activates the kill switch and proves future live control fails
  closed. Run this last because it intentionally changes connector state.
- `real_world_optional`: Bumble, SMS, and social-post style workflows. These are
  never enabled unless `--allow-real-world-actions` is set and local environment
  variables provide exact text/contact/app values.

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
