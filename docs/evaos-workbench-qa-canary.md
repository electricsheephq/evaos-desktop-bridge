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
  --version-under-test 0.5.0
```

When running from an uninstalled checkout, prefix commands with
`PYTHONPATH=src`. Installed support VM environments do not need that prefix.
For `openclaw` or `hermes` surface runs from outside the repo checkout, pass
`--repo-root /Volumes/LEXAR/repos/evaos-desktop-bridge` or set
`EVAOS_DESKTOP_BRIDGE_QA_REPO_ROOT` so the harness can find the plugin and
adapter files.

Options:

- `--surface connector|openclaw|hermes`
- `--suite readiness|desktop|iphone|full_access|ask_permission|kill_switch|real_world_optional|all`
- `--artifact-dir /Volumes/LEXAR/Codex/evaos-workbench-qa-runs/<custom-run>`
- `--token-env <ENV_NAME>` if the connector token is not in
  `EVAOS_DESKTOP_BRIDGE_TOKEN`
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
  --version-under-test 0.5.0

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface openclaw \
  --suite all \
  --version-under-test 0.5.0

python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface hermes \
  --suite all \
  --version-under-test 0.5.0
```

Then run the destructive kill-switch proof once, after the other surfaces are
complete. A successful kill-switch run intentionally blocks future remote
control commands until Workbench starts a new control session:

```bash
python3 -m evaos_desktop_bridge.qa_canary \
  --connector-url "$EVAOS_DESKTOP_BRIDGE_URL" \
  --surface connector \
  --suite kill_switch \
  --version-under-test 0.5.0
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
- `desktop`: visual see, element click when an element id is available,
  coordinate click, type, scroll, drag, hotkey, focus app, window, menu, and
  browser open.
- `iphone`: focus iPhone Mirroring, see, tap, swipe, type, Home, App Switcher,
  Spotlight, and Calculator `1+1+1=` smoke.
- `ask_permission`: starts Ask Permission, proves a high-impact live type is
  denied without approval, then proves the dry-run audit id can approve the
  matching action.
- `kill_switch`: activates the kill switch and proves future live control fails
  closed. Run this last because it intentionally changes connector state.
- `real_world_optional`: Bumble, SMS, and social-post style workflows. These are
  never enabled unless `--allow-real-world-actions` is set and local environment
  variables provide exact text/contact/app values.

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
