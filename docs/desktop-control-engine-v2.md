---
title: "Desktop Control Engine V2"
---

# Desktop Control Engine V2

V2 reframes Workbench from guarded one-off actions into customer-granted Mac and
iPhone computer control. The architecture stays the same:

1. The customer signs in to evaOS Workbench on their Mac.
2. Workbench runs the local connector and pairs it to the customer's evaOS VM
   over the private overlay.
3. OpenClaw and Hermes call the same connector command contract from the VM.
4. The customer starts a visible control session from Workbench.

No public VNC, SSH, CDP, or raw Mac port is exposed.

## Control Modes

- `Full Access`: live `desktop_*` and `iphone_*` tools can click, type, scroll,
  drag, use hotkeys, focus apps, operate browser windows, and control iPhone
  Mirroring without per-action prompts, except sensitive Mac/iPhone apps remain
  blocked.
- `Ask Permission`: same control surface, but risky clicks, taps, hotkeys,
  typing, sends, and other high-impact actions require a matching approval audit
  id.
- `Kill Switch`: immediately stops the session and blocks future live connector
  commands until the customer starts a new control session.

## Automation Engine

Peekaboo is the preferred engine when installed:

```bash
brew install steipete/tap/peekaboo
```

The bridge detects Peekaboo through `customer-mac control status --json` and
falls back to built-in macOS Accessibility, the per-process PostToPid helper,
and System Events for core actions. Fallback remains intentional, but audit
evidence must say whether an action ran through `peekaboo`,
`helper_post_to_pid`, `system_events`, or `ax_fallback`.

For `0.4.10`, release parity means the app bundle contains Peekaboo `3.2.2` and
uses the native command surface first: snapshot element clicks, global
coordinate clicks, coordinate drags/swipes, menu paths, window commands, and
browser URL opens should try Peekaboo before falling back.

## Agent Tools

OpenClaw exposes these first-class tools:

- `desktop_control_status`, `desktop_control_start`, `desktop_control_stop`,
  `desktop_kill_switch`
- `desktop_see`, `desktop_click`, `desktop_type`, `desktop_set_value`,
  `desktop_scroll`, `desktop_drag`, `desktop_hotkey`, `desktop_focus_app`,
  `desktop_window`, `desktop_menu`, `desktop_browser_action`
- `iphone_see`, `iphone_tap`, `iphone_swipe`, `iphone_type`

`desktop_see` and `iphone_see` return Codex-style visual grounding:
`snapshot_id`, screenshot metadata, short-lived connector artifact URL, image
bytes when small enough, active app/window context, and clickable elements with
labels and bounds. `desktop_click` and `iphone_tap` can target an `element_id`
from that latest snapshot, a unique `target_label`, or explicit coordinates.
`desktop_see` refuses sensitive frontmost apps before invoking Peekaboo or
fallback screenshot/AX capture. `desktop_set_value` is narrower than generic
typing: it requires a fresh AX-backed `snapshot_id`/`element_id`, blocks secure
or credential-like fields, and sends only a fixed helper `ax_action` after the
bridge has written approval/audit provenance.

Hermes should call the same connector command keys through its existing wrapper
instead of creating a second backend.

## Operator Pattern

Agents should begin with:

```text
desktop_control_status
desktop_see
```

If no active session exists, ask the customer to open Workbench -> Settings ->
Mac & iPhone -> Agent Control and choose Full Access or Ask Permission. Once the
session is active, operate normally and watch audit feedback. If the kill switch
is active, stop and tell the customer they need to start a new session.

## Release Gates

- The Workbench UI shows Agent Control state and the kill switch.
- Connector auth and token checks remain required for `/v1/commands`.
- Full Access mode does not require per-action approval.
- Ask Permission mode gates risky clicks, taps, hotkeys, typing, sends, and
  other high-impact actions.
- Sensitive-app denylist holds across Full Access and Ask Permission for
  observation and live desktop control.
- Kill switch blocks live desktop and iPhone commands.
- OpenClaw and Hermes use the same command contract.
- Issue #130 behavior harness passes against the local scratch app before
  certifying background-control safety claims.

Run the issue #130 harness locally from the repo root:

```bash
PYTHONPATH=src python3 -m evaos_desktop_bridge.behavior_harness \
  --suite issue130 \
  --repo-root /Volumes/LEXAR/repos/evaos-desktop-bridge \
  --artifact-dir /Volumes/LEXAR/Codex/evaos-desktop-bridge-issue130-runs/<run-id> \
  --sensitive-app "System Settings" \
  --operator-ack-live-control
```

It opens `tests/fixtures/macos/Issue130ScratchApp`, then records JSON/Markdown
evidence for the six invariants that previously had only argv-level coverage:
intended effect, frontmost unchanged, cursor not warped, occluded target pixels,
policy-denied zero effect, and sensitive observation blocks for `desktop see`,
`snapshot`, and `ax-tree`.
