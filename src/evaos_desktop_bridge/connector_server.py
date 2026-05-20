from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .schema import build_envelope, make_error

CommandRunner = Callable[[list[str]], tuple[int, str]]

GUARDED_REMOTE_COMMANDS = frozenset(
    {
        "codexSelectThread",
        "customerMacAppFocus",
        "customerMacLocalSiteOpen",
        "customerMacLocalSiteAction",
        "customerMacIphoneMirroringFocus",
        "customerMacIphoneMirroringHome",
        "customerMacIphoneMirroringAppSwitcher",
        "customerMacIphoneMirroringSpotlight",
        "customerMacIphoneMirroringTypeSpotlight",
        "customerMacIphoneMirroringOpenApp",
        "customerMacIphoneMirroringTapNamedTarget",
        "customerMacIphoneMirroringScroll",
    }
)


def build_bridge_argv(command: str, params: dict[str, Any] | None = None) -> list[str]:
    params = params or {}
    fixed: dict[str, list[str]] = {
        "status": ["status", "--json"],
        "capabilities": ["capabilities", "--json"],
        "latest": ["latest", "--json"],
        "codexFrontmost": ["codex", "frontmost", "--json"],
        "codexWindows": ["codex", "windows", "--json"],
        "codexAppServerStatus": ["codex", "app-server", "status", "--json"],
        "customerMacStatus": ["customer-mac", "status", "--json"],
        "customerMacCapabilities": ["customer-mac", "capabilities", "--json"],
        "customerMacIphoneMirroringStatus": ["customer-mac", "iphone-mirroring", "status", "--json"],
        "customerMacScreenSharingStatus": ["customer-mac", "screen-sharing", "status", "--json"],
    }
    if command in fixed:
        return fixed[command]
    if command == "auditTail":
        return ["audit-tail", "--json", "--limit", str(_clamp_int(params.get("limit"), 20, 1, 100))]
    if command == "queueList":
        return ["queue", "list", "--json", "--limit", str(_clamp_int(params.get("limit"), 20, 1, 100))]
    if command == "queueAppend":
        argv = [
            "queue",
            "append",
            "--json",
            "--kind",
            _required_string(params, "kind"),
            "--source-audit-id",
            _required_string(params, "source_audit_id"),
        ]
        if params.get("message"):
            argv.extend(["--message", str(params["message"])])
        return argv
    if command == "codexThreads":
        return ["codex", "threads", "--json", "--max-items", str(_clamp_int(params.get("max_items"), 50, 1, 200))]
    if command == "codexSelectThread":
        return [
            "codex",
            "select-thread",
            "--json",
            "--thread-id",
            _required_string(params, "thread_id"),
            *_dry_run_arg(params),
            *_approval_arg(params),
        ]
    if command == "codexSnapshot":
        return ["codex", "snapshot", "--json", "--max-chars", str(_clamp_int(params.get("max_chars"), 4000, 1, 20000))]
    if command == "codexInspect":
        return ["codex", "inspect", "--json", "--max-nodes", str(_clamp_int(params.get("max_nodes"), 120, 1, 1000))]
    if command == "codexAxTree":
        return ["codex", "ax-tree", "--json", "--max-nodes", str(_clamp_int(params.get("max_nodes"), 200, 1, 1000))]
    if command == "codexAppServerThreads":
        return ["codex", "app-server", "threads", "--json", "--max-items", str(_clamp_int(params.get("max_items"), 50, 1, 200))]
    if command == "customerMacSnapshot":
        return ["customer-mac", "snapshot", "--json", "--max-chars", str(_clamp_int(params.get("max_chars"), 4000, 1, 20000))]
    if command == "customerMacAxTree":
        return ["customer-mac", "ax-tree", "--json", "--max-nodes", str(_clamp_int(params.get("max_nodes"), 200, 1, 1000))]
    if command == "customerMacAppFocus":
        return ["customer-mac", "app-focus", "--json", "--app-name", _required_string(params, "app_name"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacLocalSiteOpen":
        return ["customer-mac", "local-site", "open", "--json", "--url", _required_string(params, "url"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacLocalSiteAction":
        return ["customer-mac", "local-site", "action", "--json", "--action", _required_string(params, "action"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringFocus":
        return ["customer-mac", "iphone-mirroring", "focus", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringHome":
        return ["customer-mac", "iphone-mirroring", "home", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringAppSwitcher":
        return ["customer-mac", "iphone-mirroring", "app-switcher", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSpotlight":
        return ["customer-mac", "iphone-mirroring", "spotlight", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringTypeSpotlight":
        return ["customer-mac", "iphone-mirroring", "type-spotlight", "--json", "--text", _required_string(params, "text"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringOpenApp":
        return ["customer-mac", "iphone-mirroring", "open-app", "--json", "--app-name", _required_string(params, "app_name"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringTapNamedTarget":
        return [
            "customer-mac",
            "iphone-mirroring",
            "tap-named-target",
            "--json",
            "--target-label",
            _required_string(params, "target_label"),
            *_dry_run_arg(params),
            *_approval_arg(params),
        ]
    if command == "customerMacIphoneMirroringScroll":
        return ["customer-mac", "iphone-mirroring", "scroll", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    raise ValueError(f"Unsupported connector command: {command}")


def run_connector_server(
    *,
    host: str,
    port: int,
    token: str | None,
    command_runner: CommandRunner,
) -> None:
    handler = _make_handler(token=token, command_runner=command_runner)
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever()


def read_token(path: str | None) -> str | None:
    if not path:
        return None
    token_path = Path(path).expanduser()
    if not token_path.exists():
        return None
    token = token_path.read_text(encoding="utf-8").strip()
    return token or None


def _make_handler(*, token: str | None, command_runner: CommandRunner) -> type[BaseHTTPRequestHandler]:
    class ConnectorHandler(BaseHTTPRequestHandler):
        server_version = "evaos-desktop-bridge-connector/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._write_json(200, {"ok": True, "service": "evaos-desktop-bridge-connector"})
                return
            self._write_json(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/v1/commands":
                self._write_json(404, {"ok": False, "error": "not_found"})
                return
            if not self._authorized():
                self._write_json(401, _error_envelope("connector.unauthorized", "connector", "connector_unauthorized", "Missing or invalid connector token."))
                return
            try:
                payload = self._read_json()
                command = str(payload.get("command") or "")
                params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
                if _live_guarded_without_approval(command, params):
                    self._write_json(
                        403,
                        _error_envelope(
                            command or "connector.command",
                            "customer_mac" if command.startswith("customerMac") else "desktop",
                            "approval_audit_required",
                            "Live remote control actions require a prior dry-run and approval_audit_id.",
                        ),
                    )
                    return
                argv = build_bridge_argv(command, params)
                exit_code, output = command_runner(argv)
                try:
                    response = json.loads(output)
                except json.JSONDecodeError:
                    response = _error_envelope(command, "desktop", "bridge_output_invalid", output[:500])
                status = 200 if exit_code == 0 else 422
                self._write_json(status, response)
            except Exception as exc:
                self._write_json(400, _error_envelope("connector.command", "desktop", "connector_bad_request", str(exc)))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _authorized(self) -> bool:
            if token is None and self.client_address[0] in {"127.0.0.1", "::1"}:
                return True
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return False
            supplied = header.removeprefix("Bearer ").strip()
            return bool(token) and secrets.compare_digest(supplied, token)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 65536:
                raise ValueError("request body too large")
            data = self.rfile.read(length)
            parsed = json.loads(data.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("request body must be a JSON object")
            return parsed

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ConnectorHandler


def _live_guarded_without_approval(command: str, params: dict[str, Any]) -> bool:
    if command not in GUARDED_REMOTE_COMMANDS:
        return False
    if params.get("dry_run") is not False:
        return False
    approval = params.get("approval_audit_id")
    return not isinstance(approval, str) or not approval.strip()


def _dry_run_arg(params: dict[str, Any]) -> list[str]:
    return ["--dry-run"] if params.get("dry_run") is not False else []


def _approval_arg(params: dict[str, Any]) -> list[str]:
    approval = params.get("approval_audit_id")
    if not isinstance(approval, str) or not approval.strip():
        return []
    return ["--approval-audit-id", approval.strip()]


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _required_string(params: dict[str, Any], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _error_envelope(command: str, target: str, code: str, message: str) -> dict[str, Any]:
    return build_envelope(
        command=command,
        target=target,
        ok=False,
        data={},
        warnings=[],
        errors=[make_error(code=code, message=message, guidance="Check connector pairing, command shape, and approval state.")],
        audit_id="connector-rejected",
    )
