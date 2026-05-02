---
title: CLI-Anything durable install note
type: research
tags: [cli-anything, install, tools]
created: 2026-05-02
status: done
---

Installed a durable clone of `HKUDS/CLI-Anything` at `/Users/lume/repos/CLI-Anything` from upstream commit `eb573e99ff2d4b26dbf9fa7e4ba3dffb653a0e11`.

Upstream docs checked first:
- `README.md` quick start says Python 3.10+ is required.
- Repo install guidance now emphasizes `cli-hub` (`pip install cli-anything-hub`) and repo-local skills under `skills/` / `openclaw-skill/`.
- The only packaged Python entrypoint in-repo is `cli-hub` under `cli-hub/setup.py`.

Commands run:
```bash
git clone https://github.com/HKUDS/CLI-Anything /Users/lume/repos/CLI-Anything
cd /Users/lume/repos/CLI-Anything && git rev-parse HEAD
python3 -m pip install -e /Users/lume/repos/CLI-Anything/cli-hub --break-system-packages
cli-hub --help
cli-hub list | head -n 40
```

Verification:
- `cli-hub --help` succeeded and exposed commands: `info`, `install`, `launch`, `list`, `previews`, `search`, `uninstall`, `update`.
- `cli-hub list` succeeded and returned registry entries (for example `blender`, `freecad`, `drawio`, `zoom`, `n8n`).
- Repo contains both `skills/` and `openclaw-skill/` for agent skill installation paths.

Notes:
- The top-level repo itself is not a single pip package; the installable component is `cli-hub/`.
- No pre-existing durable clone or local changes were present, so a fresh clone was safe.
- Existing workspace note claiming 11 prebuilt harnesses in `/tmp/CLI-Anything/` is currently stale on this machine; `/tmp/CLI-Anything` was absent.

Next command to generate or install a harness:
```bash
cli-hub install blender
```
For OpenClaw skill installation from the durable clone, the repo README points at copying `openclaw-skill/SKILL.md` (or using `npx skills add HKUDS/CLI-Anything --skill <skill-name> -g -y` for repo-root skills).
