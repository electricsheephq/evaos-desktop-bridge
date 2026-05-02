from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, TextIO

from .adapters.codex_macos import MacOSCodexObserver
from .audit import append_audit
from .policy import PolicyError, ensure_allowed
from .schema import build_envelope
from .types import CommandResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaos-desktop-bridge",
        description="Safe read-only bridge for visible desktop agent surfaces.",
    )
    subparsers = parser.add_subparsers(dest="scope")

    status_parser = subparsers.add_parser("status", help="Report desktop bridge and Codex Desktop status.")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    status_parser.set_defaults(command_id="status", target="desktop")

    codex_parser = subparsers.add_parser("codex", help="Codex Desktop passive observer commands.")
    codex_subparsers = codex_parser.add_subparsers(dest="codex_command")

    frontmost_parser = codex_subparsers.add_parser("frontmost", help="Report the current frontmost app without capturing screenshots.")
    frontmost_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    frontmost_parser.set_defaults(command_id="codex.frontmost", target="codex")

    windows_parser = codex_subparsers.add_parser("windows", help="List visible Codex Desktop windows via Accessibility.")
    windows_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    windows_parser.set_defaults(command_id="codex.windows", target="codex")

    focus_parser = codex_subparsers.add_parser("focus", help="Focus the visible Codex Desktop app.")
    focus_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    focus_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without focusing.")
    focus_parser.set_defaults(command_id="codex.focus", target="codex")

    snapshot_parser = codex_subparsers.add_parser("snapshot", help="Capture safe visible Codex Desktop state.")
    snapshot_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    snapshot_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum visible text chars.")
    snapshot_parser.set_defaults(command_id="codex.snapshot", target="codex")

    ax_parser = codex_subparsers.add_parser("ax-tree", help="Capture a capped Accessibility tree summary.")
    ax_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    ax_parser.add_argument("--max-nodes", type=_positive_int, default=200, help="Maximum AX nodes to return.")
    ax_parser.set_defaults(command_id="codex.ax_tree", target="codex")

    return parser


def main(
    argv: list[str] | None = None,
    *,
    observer_factory: Callable[[], MacOSCodexObserver] | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    state_dir: Path | None = None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if not hasattr(args, "command_id"):
        parser.print_help(stdout)
        return 0

    command_id = args.command_id
    target = args.target
    try:
        ensure_allowed(command_id)
        observer = observer_factory() if observer_factory is not None else MacOSCodexObserver(state_dir=state_dir)
        result = _run_command(command_id, observer, args)
    except PolicyError as exc:
        result = CommandResult(ok=False, errors=[exc.error])
    except Exception as exc:
        result = CommandResult(
            ok=False,
            errors=[
                {
                    "code": "command_failed",
                    "message": str(exc),
                    "guidance": "Rerun with the same command after checking local macOS permissions and bridge logs.",
                }
            ],
        )

    audit_id = append_audit(
        command=command_id,
        target=target,
        args={key: value for key, value in vars(args).items() if key not in {"command_id", "target"}},
        ok=result.ok,
        warnings=result.warnings,
        errors=result.errors,
        state_dir=state_dir,
    )
    envelope = build_envelope(
        command=command_id,
        target=target,
        ok=result.ok,
        data=result.data,
        warnings=result.warnings,
        errors=result.errors,
        audit_id=audit_id,
    )
    stdout.write(json.dumps(envelope, sort_keys=True) + "\n")
    return 0 if result.ok else 2


def entrypoint() -> None:
    raise SystemExit(main())


def _run_command(command_id: str, observer: MacOSCodexObserver, args: argparse.Namespace) -> CommandResult:
    if command_id == "status":
        return observer.status()
    if command_id == "codex.frontmost":
        return observer.frontmost()
    if command_id == "codex.windows":
        return observer.windows()
    if command_id == "codex.focus":
        return observer.focus(dry_run=args.dry_run)
    if command_id == "codex.snapshot":
        return observer.snapshot(max_chars=args.max_chars)
    if command_id == "codex.ax_tree":
        return observer.ax_tree(max_nodes=args.max_nodes)
    raise PolicyError(command_id)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


if __name__ == "__main__":
    entrypoint()
