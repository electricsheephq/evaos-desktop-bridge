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

`evaos-desktop-bridge` uses macOS-visible GUI primitives only. The MVP needs Accessibility for focus and Accessibility-tree reads, and Screen Recording for screenshots.

## Current Status

Active for MVP issue `100yenadmin/evaos-desktop-bridge#7`.

## Last Update

- Updated At: 2026-05-02T00:00:00Z
- Agent: codex
- Session: codex-desktop-passive-observer-mvp
- Revision Count: 1

## Change Log

- 2026-05-02T00:00:00Z - Initial TCC setup guide for passive Codex Desktop observation.

## Required Permissions

### Accessibility

Required for:

- `evaos-desktop-bridge codex focus --json`
- `evaos-desktop-bridge codex ax-tree --json --max-nodes 200`
- Reading front window titles through System Events.

Setup:

1. Open System Settings.
2. Go to Privacy & Security.
3. Open Accessibility.
4. Enable the terminal app or wrapper app that runs `evaos-desktop-bridge`.
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

Setup:

1. Open System Settings.
2. Go to Privacy & Security.
3. Open Screen Recording.
4. Enable the terminal app or wrapper app that runs `evaos-desktop-bridge`.
5. Restart the terminal session if macOS does not apply the grant immediately.

If Screen Recording is missing, snapshot still returns visible text fields when available and includes a warning that screenshot capture failed.

## Manual Checks

```bash
evaos-desktop-bridge status --json
evaos-desktop-bridge codex focus --json --dry-run
evaos-desktop-bridge codex snapshot --json --max-chars 4000
evaos-desktop-bridge codex ax-tree --json --max-nodes 20
```

Expected behavior:

- Commands return valid JSON.
- Permission failures use structured `errors`.
- Missing screenshot permission is reported as a warning.
- No command sends text to Codex Desktop.

## Troubleshooting

- If `status` reports Accessibility as `missing`, grant Accessibility to the exact app that launches the bridge.
- If `snapshot` returns `screenshot_path: null`, grant Screen Recording and rerun the terminal.
- If `ax-tree` returns `ax_tree_unavailable`, confirm Codex Desktop is running and visible, then recheck Accessibility.
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
