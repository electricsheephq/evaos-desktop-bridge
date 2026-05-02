# Codex Desktop visible macro pack

This bridge intentionally controls the **visible Codex Desktop workspace first**. Hidden app-server/session DB paths are fallback research only, not the MVP control lane.

## Environment

Install bridge GUI dependencies in the repo-local venv:

```bash
./scripts/setup-gui-env.sh
```

This installs the bridge plus GUI extras (`pyobjc-framework-Quartz`, `pyobjc-framework-ApplicationServices`, `pyautogui`, `pynput`) without touching Homebrew Python.

## CLI-Anything shape

Use CLI-Anything `native_api` to wrap bridge commands. Do **not** expose generic click/type/send in the first macro pack.

Recommended first macros:

- `codex_status`
- `codex_frontmost`
- `codex_windows`
- `codex_focus`
- `codex_snapshot`
- `codex_ax_tree`

`gui_macro` is allowed only as a separate, explicit, layout-strict fallback after a visible preflight proves Codex is frontmost and the expected window is present.

## Safety rules

- Every command emits JSON.
- Run status/frontmost/windows before any visible mutation.
- `focus` is the only allowed mutation in the first pack.
- No hidden app-server attach.
- No session DB reads.
- No prompt typing, send, approve, or generic click actions.
- Keep audit logs enabled.

## Example macro skeleton

```yaml
name: codex_windows
version: "1.0"
description: List visible Codex Desktop windows through evaos-desktop-bridge.
tags: [codex, desktop, visible, read-only]

parameters: {}
preconditions:
  - file_exists: /ABS/PATH/TO/evaos-desktop-bridge/.venv/bin/python

steps:
  - id: list_windows
    backend: native_api
    action: run_command
    params:
      command:
        - /ABS/PATH/TO/evaos-desktop-bridge/.venv/bin/python
        - -m
        - evaos_desktop_bridge.cli
        - codex
        - windows
        - --json
      capture_stdout: true
    timeout_ms: 30000
    on_failure: fail

postconditions:
  - always: true
```
