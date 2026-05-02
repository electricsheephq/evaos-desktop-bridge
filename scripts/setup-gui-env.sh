#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[gui]'
cat <<MSG
Installed evaos-desktop-bridge GUI environment.
Use: $ROOT/.venv/bin/python -m evaos_desktop_bridge.cli codex status --json
MSG
