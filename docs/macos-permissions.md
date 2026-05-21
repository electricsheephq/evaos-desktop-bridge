---
title: "macOS Permissions for evaOS Desktop Bridge"
doc_id: "doc-guide-macos-permissions"
doc_type: "guide"
status: "active"
canonical: true
created_at: "2026-05-02T00:00:00Z"
updated_at: "2026-05-02T00:00:00Z"
revision_count: 1
last_updated_by_agent: "codex"
last_updated_by_session: "codex-desktop-passive-observer-mvp"
tags:
  - evaos
  - desktop-bridge
  - macos
  - permissions
---

# macOS Permissions for evaOS Desktop Bridge

## Summary

`evaos-desktop-bridge` uses macOS-visible GUI primitives only. The MVP needs Accessibility for focus, Accessibility-tree reads, and named iPhone Mirroring actions. Screen Recording is needed for screenshots.

## Current Status

Active for MVP issue `100yenadmin/evaos-desktop-bridge#7`.

## Last Update

- Updated At: 2026-05-02T00:00:00Z
- Agent: codex
- Session: codex-desktop-passive-observer-mvp
- Revision Count: 1

## Change Log

- 2026-05-21T00:00:00Z - Added Workbench connector/LaunchAgent TCC caveat from
  support VM canary.
- 2026-05-02T00:00:00Z - Initial TCC setup guide for passive Codex Desktop observation.

## Required Permissions

### Accessibility

Required for:

- `evaos-desktop-bridge codex focus --json`
- `evaos-desktop-bridge codex threads --json --max-items 50`
- `evaos-desktop-bridge codex select-thread --json --thread-id visible-... --dry-run`
- `evaos-desktop-bridge codex continue-thread --json --title "SDK Docs" --dry-run` for the Codex fallback canary.
- `evaos-desktop-bridge codex ax-tree --json --max-nodes 200`
- `evaos-desktop-bridge customer-mac ax-tree --json --max-nodes 200`
- `evaos-desktop-bridge customer-mac local-site action --json --action reload --dry-run`
- `evaos-desktop-bridge customer-mac iphone-mirroring home --json --dry-run`
- `evaos-desktop-bridge customer-mac iphone-mirroring swipe-left --json --dry-run`.
- `evaos-desktop-bridge customer-mac iphone-mirroring send-approved-message --json ... --dry-run`.
- Reading front window titles through System Events.

Setup:

1. Open System Settings.
2. Go to Privacy & Security.
3. Open Accessibility.
4. Enable the exact process identity that runs `evaos-desktop-bridge`.
   - For interactive local tests, this is usually Codex, Terminal, or the
     wrapper app that launched the command.
   - For `connector-service start`, macOS may require approving the Python app
     or packaged helper used by the LaunchAgent, not only Workbench itself.
5. Restart the terminal session if macOS does not apply the grant immediately.

Graceful failure shape:

```json
{
  "ok": false,
  "errors": [
    {
      "code": "permission_missing",
      "message": "Accessibility permission is required to focus Codex Desktop.",
      "guidance": "Open System Settings > Privacy & Security > Accessibility ...",
      "permission": "accessibility"
    }
  ]
}
```

### Screen Recording

Required for:

- `evaos-desktop-bridge codex snapshot --json --max-chars 4000` when a screenshot artifact is desired.
- `evaos-desktop-bridge customer-mac snapshot --json --max-chars 4000` when a screenshot artifact is desired.

Setup:

1. Open System Settings.
2. Go to Privacy & Security.
3. Open Screen Recording.
4. Enable the exact process identity that runs `evaos-desktop-bridge`.
   - macOS may not automatically show the process in this pane after the first
     click. If it does not appear, use the add button and choose the actual app
     or helper executable being used for the connector.
5. Restart the terminal session if macOS does not apply the grant immediately.

If Screen Recording is missing, snapshot still returns visible text fields when available and includes a warning that screenshot capture failed.

## Manual Checks

```bash
evaos-desktop-bridge status --json
evaos-desktop-bridge codex focus --json --dry-run
evaos-desktop-bridge codex threads --json --max-items 20
evaos-desktop-bridge codex snapshot --json --max-chars 4000
evaos-desktop-bridge codex ax-tree --json --max-nodes 20
evaos-desktop-bridge codex app-server remote-control-status --json
evaos-desktop-bridge customer-mac status --json
evaos-desktop-bridge customer-mac iphone-mirroring status --json
evaos-desktop-bridge customer-mac screen-sharing status --json
```

Expected behavior:

- Commands return valid JSON.
- Permission failures use structured `errors`.
- Missing screenshot permission is reported as a warning.
- No generic command sends text to Codex Desktop; the fallback is fixed to exact
  `continue`.
- The Codex fallback is fixed to exact `continue` and requires approval before
  live use.
- `select-thread --dry-run` reports the target without clicking.
- Customer Mac and iPhone Mirroring guarded actions default to dry-run.
- iPhone gestures/messages require matching audit approval before live use.
- Screen Sharing status never enables Screen Sharing.

## Troubleshooting

- If `status` reports Accessibility as `missing`, grant Accessibility to the exact app that launches the bridge.
- If `status` reports Accessibility as `granted` interactively but `missing`
  through the VM connector, the LaunchAgent/helper process has a different TCC
  identity than the interactive shell. Approve that exact helper or run the
  support canary connector interactively until the app-owned helper path is
  shipped.
- If `snapshot` returns `screenshot_path: null`, grant Screen Recording and rerun the terminal.
- If `ax-tree` returns `ax_tree_unavailable`, confirm Codex Desktop is running and visible, then recheck Accessibility.
- If `ax-tree`, `windows`, or `threads` returns `ax_dependency_missing`, install the GUI extras with `python3 -m pip install -e '.[gui]'` in the bridge environment.
- If macOS still denies access after toggling a permission, remove and re-add the terminal app in the relevant privacy pane.

## Data Location

The default local state directory is:

```text
~/Library/Application Support/evaos-desktop-bridge/
```

It contains:

- `audit.jsonl`
- `screenshots/*.png` when screenshot capture succeeds.

Set `EVAOS_DESKTOP_BRIDGE_STATE_DIR` to use a different local state directory during tests.
