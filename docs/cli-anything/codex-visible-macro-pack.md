# Codex Desktop visible macro pack

This bridge intentionally controls the **visible Codex Desktop workspace first**. Hidden app-server/session DB paths are fallback research only, not the MVP control lane.

## Source docs checked

This setup follows the local upstream CLI-Anything/OpenClaw docs:

- `/Users/lume/repos/CLI-Anything/openclaw-skill/agent-harness/OPENCLAW.md`
- `/Users/lume/repos/CLI-Anything/openclaw-skill/SKILL.md`

Key requirements carried forward here:

- macros are YAML and inspected via `macro info` before running
- every agent-facing command should emit JSON
- use explicit preconditions/postconditions
- prefer the real backend/native interface before fragile GUI replay
- use `find_namespace_packages(include=["cli_anything.*"])` / console scripts for generated harnesses when building a full harness
- do not remove or break existing harness commands

## Environment

Install bridge GUI dependencies in the repo-local venv:

```bash
./scripts/setup-gui-env.sh
```

This installs the bridge plus GUI extras (`pyobjc-framework-Quartz`, `pyobjc-framework-ApplicationServices`, `pyautogui`, `pynput`) without touching Homebrew Python.

Install the OpenClaw macro harness in its own repo-local/throwaway venv, not Homebrew Python:

```bash
python3 -m venv /tmp/openclaw-harness-venv
/tmp/openclaw-harness-venv/bin/python -m pip install -e /Users/lume/repos/CLI-Anything/openclaw-skill/agent-harness
/tmp/openclaw-harness-venv/bin/python -m cli_anything.openclaw --json backends
```

## CLI-Anything shape

Use CLI-Anything `native_api` to wrap bridge commands. Do **not** expose generic click/type/send in the first macro pack.

Important version note: the current local OpenClaw macro harness supports `macro info` and `macro run`, but **does not expose `macro run --dry-run`** even though some docs imply dry-run behavior. For now, inspect with `macro info` first and use bridge-level dry-run flags where commands support them, such as `codex focus --dry-run`.

Example smoke:

```bash
cp macros/cli-anything/codex-visible/codex_inspect.yaml /Users/lume/repos/CLI-Anything/openclaw-skill/agent-harness/cli_anything/openclaw/macro_definitions/
cd /Users/lume/repos/CLI-Anything/openclaw-skill/agent-harness
/tmp/openclaw-harness-venv/bin/python -m cli_anything.openclaw --json macro info codex_inspect
/tmp/openclaw-harness-venv/bin/python -m cli_anything.openclaw --json macro run codex_inspect
rm cli_anything/openclaw/macro_definitions/codex_inspect.yaml
```

Committed first macro pack lives in `macros/cli-anything/codex-visible/`.

Recommended first macros:

- `bridge_status`
- `codex_frontmost`
- `codex_windows`
- `codex_focus`
- `codex_snapshot`
- `codex_inspect`
- `codex_ax_tree`

`gui_macro` is allowed only as a separate, explicit, layout-strict fallback after a visible preflight proves Codex is frontmost and the expected window is present.

## Safety rules

- Every command emits JSON.
- Run status/frontmost/windows before any visible mutation.
- `focus` and the explicit visible macOS menu action `File → New Chat` are the only allowed mutations in the first hands pack.
- Prefer visible macOS menu actions over duplicate Electron web-button AXPress when a real app menu exists.
- `codex press-control --label "New chat"` is intentionally not the preferred New Chat primitive: live tests showed both duplicate AXButton matches can return `pressed: true` without changing the active conversation. Treat AXPress success as mechanical only until paired with screenshot/inspect verification.
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
  - process_running: Codex

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

agent_hints:
  danger_level: safe
  side_effects: []
  reversible: true
```

## Live New Chat finding (2026-05-03)

Two visible AX buttons named `New chat` were discovered in Codex Desktop. The bridge correctly refused an ambiguous press without `--match-index`. Live tests then showed both `match-index 0` and `match-index 1` could return `pressed: true` while the visible Codex workspace stayed on the existing `Build desktop bridge MVP` conversation.

The safer primitive is the native macOS menu item:

```bash
python -m evaos_desktop_bridge.cli codex menu-action --json --menu File --item 'New Chat' --dry-run
python -m evaos_desktop_bridge.cli codex menu-action --json --menu File --item 'New Chat'
```

Live screenshot verification confirmed `File → New Chat` opens the empty `What should we work on in Codex?` workspace. Do not equate AXPress success with product success; pair future visible mutations with before/after verification.
