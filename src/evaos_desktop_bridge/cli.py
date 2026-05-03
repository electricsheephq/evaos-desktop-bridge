from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, TextIO

from .adapters.codex_app_server import CodexAppServerObserver
from .adapters.codex_macos import MacOSCodexObserver
from .adapters.codex_sessions import CodexSessionObserver
from .audit import append_audit
from .policy import PolicyError, command_metadata, ensure_allowed
from .queue import append_queue_event, list_queue_events
from .schema import build_envelope
from .state import read_audit_tail, read_latest, write_latest
from .types import CommandResult

LATEST_OBSERVATION_COMMANDS = frozenset(
    {
        "status",
        "capabilities",
        "codex.frontmost",
        "codex.windows",
        "codex.threads",
        "codex.indexed_threads",
        "codex.read_thread_tail",
        "codex.open_thread",
        "codex.menu_action",
        "codex.find_control",
        "codex.snapshot",
        "codex.inspect",
        "codex.ax_tree",
        "codex.app_server.status",
        "codex.app_server.threads",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaos-desktop-bridge",
        description="Safe read-only bridge for visible desktop agent surfaces.",
    )
    subparsers = parser.add_subparsers(dest="scope")

    status_parser = subparsers.add_parser("status", help="Report desktop bridge and Codex Desktop status.")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    status_parser.set_defaults(command_id="status", target="desktop")

    capabilities_parser = subparsers.add_parser("capabilities", help="Report the safe bridge capability surface.")
    capabilities_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    capabilities_parser.set_defaults(command_id="capabilities", target="desktop")

    latest_parser = subparsers.add_parser("latest", help="Return the last observed bridge envelope.")
    latest_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    latest_parser.set_defaults(command_id="latest", target="desktop")

    audit_parser = subparsers.add_parser("audit-tail", help="Return a redacted tail of the local audit log.")
    audit_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    audit_parser.add_argument("--limit", type=_positive_int, default=20, help="Maximum audit records to return.")
    audit_parser.set_defaults(command_id="audit_tail", target="desktop")

    queue_parser = subparsers.add_parser("queue", help="Eva/OpenClaw announcement queue commands.")
    queue_subparsers = queue_parser.add_subparsers(dest="queue_command")

    queue_list_parser = queue_subparsers.add_parser("list", help="List local announcement queue events.")
    queue_list_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    queue_list_parser.add_argument("--limit", type=_positive_int, default=20, help="Maximum queue events to return.")
    queue_list_parser.set_defaults(command_id="queue.list", target="queue")

    queue_append_parser = queue_subparsers.add_parser("append", help="Append an Eva/OpenClaw announcement queue event.")
    queue_append_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    queue_append_parser.add_argument("--kind", required=True, help="Queue kind: idle, approval_needed, done, error, attention.")
    queue_append_parser.add_argument("--source-audit-id", required=True, help="Source audit id for provenance.")
    queue_append_parser.add_argument("--message", default=None, help="Optional capped announcement message.")
    queue_append_parser.set_defaults(command_id="queue.append", target="queue")

    codex_parser = subparsers.add_parser("codex", help="Codex Desktop passive observer commands.")
    codex_subparsers = codex_parser.add_subparsers(dest="codex_command")

    frontmost_parser = codex_subparsers.add_parser("frontmost", help="Report the current frontmost app without capturing screenshots.")
    frontmost_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    frontmost_parser.set_defaults(command_id="codex.frontmost", target="codex")

    windows_parser = codex_subparsers.add_parser("windows", help="List visible Codex Desktop windows via Accessibility.")
    windows_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    windows_parser.set_defaults(command_id="codex.windows", target="codex")

    threads_parser = codex_subparsers.add_parser("threads", help="List visible Codex Desktop thread candidates from GUI state.")
    threads_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    threads_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum visible thread candidates to return.")
    threads_parser.set_defaults(command_id="codex.threads", target="codex")

    indexed_threads_parser = codex_subparsers.add_parser("indexed-threads", help="List persisted Codex Desktop/interactive threads from session_index.jsonl.")
    indexed_threads_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    indexed_threads_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum indexed threads to return.")
    indexed_threads_parser.set_defaults(command_id="codex.indexed_threads", target="codex")

    read_tail_parser = codex_subparsers.add_parser("read-thread-tail", help="Read a redacted tail from a Codex rollout file by thread id.")
    read_tail_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    read_tail_parser.add_argument("--thread-id", required=True, help="Codex thread id.")
    read_tail_parser.add_argument("--max-events", type=_positive_int, default=40, help="Maximum relevant rollout events to return.")
    read_tail_parser.add_argument("--max-chars", type=_positive_int, default=12000, help="Maximum chars per included text field / output budget hint.")
    read_tail_parser.set_defaults(command_id="codex.read_thread_tail", target="codex")

    open_thread_parser = codex_subparsers.add_parser("open-thread", help="Open a Codex Desktop thread by codex:// deep link.")
    open_thread_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    open_thread_parser.add_argument("--thread-id", required=True, help="Codex thread id.")
    open_thread_parser.add_argument("--dry-run", action="store_true", help="Report URL without opening Codex Desktop.")
    open_thread_parser.set_defaults(command_id="codex.open_thread", target="codex")

    focus_parser = codex_subparsers.add_parser("focus", help="Focus the visible Codex Desktop app.")
    focus_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    focus_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without focusing.")
    focus_parser.set_defaults(command_id="codex.focus", target="codex")

    menu_action_parser = codex_subparsers.add_parser("menu-action", help="Invoke one allowlisted visible Codex menu action.")
    menu_action_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    menu_action_parser.add_argument("--menu", required=True, help="Menu name, e.g. File.")
    menu_action_parser.add_argument("--item", required=True, help="Menu item name, e.g. New Chat.")
    menu_action_parser.add_argument("--dry-run", action="store_true", help="Verify the visible menu action without clicking it.")
    menu_action_parser.set_defaults(command_id="codex.menu_action", target="codex")

    find_control_parser = codex_subparsers.add_parser("find-control", help="Find exact visible Codex controls by AX label without pressing them.")
    find_control_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    find_control_parser.add_argument("--label", required=True, help="Exact AX label to find, e.g. 'New chat'.")
    find_control_parser.add_argument("--max-nodes", type=_positive_int, default=500, help="Maximum AX nodes to inspect.")
    find_control_parser.set_defaults(command_id="codex.find_control", target="codex")

    press_control_parser = codex_subparsers.add_parser("press-control", help="Press an allowlisted visible Codex control via AXPress.")
    press_control_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    press_control_parser.add_argument("--label", required=True, help="Exact allowlisted AX label to press, e.g. 'New chat'.")
    press_control_parser.add_argument("--dry-run", action="store_true", help="Report the target without pressing.")
    press_control_parser.add_argument("--match-index", type=int, default=None, help="Specific match index from find-control when a label is not unique.")
    press_control_parser.add_argument("--max-nodes", type=_positive_int, default=500, help="Maximum AX nodes to inspect.")
    press_control_parser.set_defaults(command_id="codex.press_control", target="codex")

    select_parser = codex_subparsers.add_parser("select-thread", help="Select an already-visible Codex Desktop thread candidate.")
    select_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    select_parser.add_argument("--thread-id", required=True, help="Visible thread id from codex threads output.")
    select_parser.add_argument("--dry-run", action="store_true", help="Report what would happen without clicking/selecting.")
    select_parser.set_defaults(command_id="codex.select_thread", target="codex")

    snapshot_parser = codex_subparsers.add_parser("snapshot", help="Capture safe visible Codex Desktop state.")
    snapshot_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    snapshot_parser.add_argument("--max-chars", type=_positive_int, default=4000, help="Maximum visible text chars.")
    snapshot_parser.set_defaults(command_id="codex.snapshot", target="codex")

    inspect_parser = codex_subparsers.add_parser("inspect", help="Return a compact page map of visible Codex Desktop state.")
    inspect_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    inspect_parser.add_argument("--max-nodes", type=_positive_int, default=120, help="Maximum AX nodes to include.")
    inspect_parser.set_defaults(command_id="codex.inspect", target="codex")

    ax_parser = codex_subparsers.add_parser("ax-tree", help="Capture a capped Accessibility tree summary.")
    ax_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    ax_parser.add_argument("--max-nodes", type=_positive_int, default=200, help="Maximum AX nodes to return.")
    ax_parser.set_defaults(command_id="codex.ax_tree", target="codex")

    app_server_parser = codex_subparsers.add_parser("app-server", help="Read-only Codex app-server seam commands.")
    app_server_subparsers = app_server_parser.add_subparsers(dest="app_server_command")

    app_server_status_parser = app_server_subparsers.add_parser("status", help="Report read-only app-server availability and allowlist.")
    app_server_status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_status_parser.set_defaults(command_id="codex.app_server.status", target="codex")

    app_server_threads_parser = app_server_subparsers.add_parser("threads", help="Read Codex threads through the app-server read allowlist.")
    app_server_threads_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    app_server_threads_parser.add_argument("--max-items", type=_positive_int, default=50, help="Maximum app-server thread summaries to return.")
    app_server_threads_parser.set_defaults(command_id="codex.app_server.threads", target="codex")

    return parser


def main(
    argv: list[str] | None = None,
    *,
    observer_factory: Callable[[], MacOSCodexObserver] | None = None,
    app_server_factory: Callable[[], CodexAppServerObserver] | None = None,
    session_factory: Callable[[], CodexSessionObserver] | None = None,
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
    args.state_dir = state_dir
    try:
        ensure_allowed(command_id)
        observer = observer_factory() if observer_factory is not None else MacOSCodexObserver(state_dir=state_dir)
        app_server = app_server_factory() if app_server_factory is not None else CodexAppServerObserver()
        sessions = session_factory() if session_factory is not None else CodexSessionObserver()
        result = _run_command(command_id, observer, app_server, sessions, args)
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
        args={key: value for key, value in vars(args).items() if key not in {"command_id", "target", "state_dir"}},
        ok=result.ok,
        warnings=result.warnings,
        errors=result.errors,
        provenance={
            **command_metadata(command_id),
            **result.provenance,
            "dry_run": getattr(args, "dry_run", None),
            "selected_visible_target_id": getattr(args, "thread_id", None),
            "source_audit_id": getattr(args, "source_audit_id", None),
        },
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
    if command_id in LATEST_OBSERVATION_COMMANDS:
        write_latest(envelope, state_dir=state_dir)
    stdout.write(json.dumps(envelope, sort_keys=True) + "\n")
    return 0 if result.ok else 2


def entrypoint() -> None:
    raise SystemExit(main())


def _run_command(command_id: str, observer: MacOSCodexObserver, app_server: CodexAppServerObserver, sessions: CodexSessionObserver, args: argparse.Namespace) -> CommandResult:
    if command_id == "status":
        return observer.status()
    if command_id == "capabilities":
        return CommandResult(ok=True, data=_capabilities())
    if command_id == "latest":
        latest = read_latest(getattr(args, "state_dir", None))
        if latest is None:
            return CommandResult(
                ok=False,
                errors=[
                    {
                        "code": "latest_not_found",
                        "message": "No latest observation has been recorded yet.",
                        "guidance": "Run evaos-desktop-bridge status --json or a codex observer command first.",
                    }
                ],
            )
        return CommandResult(ok=True, data={"latest": latest})
    if command_id == "audit_tail":
        records = read_audit_tail(limit=args.limit, state_dir=getattr(args, "state_dir", None))
        return CommandResult(ok=True, data={"records": records, "count": len(records), "limit": args.limit}, provenance={"source": "audit"})
    if command_id == "queue.list":
        return list_queue_events(limit=args.limit, state_dir=getattr(args, "state_dir", None))
    if command_id == "queue.append":
        return append_queue_event(
            kind=args.kind,
            source_audit_id=args.source_audit_id,
            message=args.message,
            state_dir=getattr(args, "state_dir", None),
        )
    if command_id == "codex.frontmost":
        return observer.frontmost()
    if command_id == "codex.windows":
        return observer.windows()
    if command_id == "codex.threads":
        return observer.threads(max_items=args.max_items)
    if command_id == "codex.indexed_threads":
        return sessions.indexed_threads(max_items=args.max_items)
    if command_id == "codex.read_thread_tail":
        return sessions.read_thread_tail(thread_id=args.thread_id, max_events=args.max_events, max_chars=args.max_chars)
    if command_id == "codex.open_thread":
        return sessions.open_thread(thread_id=args.thread_id, dry_run=args.dry_run)
    if command_id == "codex.focus":
        return observer.focus(dry_run=args.dry_run)
    if command_id == "codex.menu_action":
        return observer.menu_action(menu=args.menu, item=args.item, dry_run=args.dry_run)
    if command_id == "codex.find_control":
        return observer.find_control(label=args.label, max_nodes=args.max_nodes)
    if command_id == "codex.press_control":
        return observer.press_control(label=args.label, dry_run=args.dry_run, max_nodes=args.max_nodes, match_index=args.match_index)
    if command_id == "codex.select_thread":
        return observer.select_thread(thread_id=args.thread_id, dry_run=args.dry_run)
    if command_id == "codex.snapshot":
        return observer.snapshot(max_chars=args.max_chars)
    if command_id == "codex.inspect":
        return observer.inspect(max_nodes=args.max_nodes)
    if command_id == "codex.ax_tree":
        return observer.ax_tree(max_nodes=args.max_nodes)
    if command_id == "codex.app_server.status":
        return app_server.status()
    if command_id == "codex.app_server.threads":
        return app_server.threads(max_items=args.max_items)
    raise PolicyError(command_id)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def _capabilities() -> dict[str, object]:
    return {
        "modes": {
            "eyes": "Read-only visible desktop observation with redaction and caps.",
            "hands": "Guarded visible focus/select only; no typing, send controls, prompt sending, or session mutation.",
            "brain": "Local Eva/OpenClaw announcement queue contract with external relay left to future sinks.",
        },
        "commands": [
            {"id": command, "target": _target_for_command(command), **command_metadata(command)}
            for command in [
                "status",
                "capabilities",
                "latest",
                "audit_tail",
                "queue.list",
                "queue.append",
                "codex.frontmost",
                "codex.windows",
                "codex.threads",
                "codex.indexed_threads",
                "codex.read_thread_tail",
                "codex.open_thread",
                "codex.focus",
                "codex.menu_action",
                "codex.find_control",
                "codex.press_control",
                "codex.select_thread",
                "codex.snapshot",
                "codex.inspect",
                "codex.ax_tree",
                "codex.app_server.status",
                "codex.app_server.threads",
            ]
        ],
        "forbidden": [
            "send_prompts_or_messages",
            "type_into_codex",
            "click_codex_controls",
            "call_codex_internal_mutation_rpc",
            "hijack_stdio_or_file_descriptors",
            "read_session_databases_wholesale",
            "expose_tokens_auth_files_or_full_home_paths",
        ],
        "data_minimization": {
            "redacts_home_paths": True,
            "redacts_secret_like_values": True,
            "caps_visible_text": True,
            "caps_ax_nodes": True,
            "skips_non_codex_screenshots": True,
            "append_only_audit_log": True,
        },
    }


def _target_for_command(command: str) -> str:
    if command.startswith("codex."):
        return "codex"
    if command.startswith("queue."):
        return "queue"
    return "desktop"


if __name__ == "__main__":
    entrypoint()
