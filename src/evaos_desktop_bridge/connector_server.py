from __future__ import annotations

import json
import os
import secrets
import socket
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .audit import default_state_dir
from .schema import build_envelope, make_error
from .state import approval_audit_freshness_error, read_audit_record

CommandRunner = Callable[[list[str]], tuple[int, str]]

CUSTOMER_MAC_CONTROL_URL = os.environ.get(
    "EVAOS_CUSTOMER_MAC_CONTROL_URL",
    "https://rhfojelkgtwcxnrfhtlj.supabase.co/functions/v1/customer-mac-control",
)

GUARDED_REMOTE_COMMANDS = frozenset(
    {
        "codexSelectThread",
        "codexContinueThread",
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
        "customerMacIphoneMirroringSwipeLeft",
        "customerMacIphoneMirroringSwipeRight",
        "customerMacIphoneMirroringSwipeUp",
        "customerMacIphoneMirroringSwipeDown",
        "customerMacIphoneMirroringTypeApprovedText",
        "customerMacIphoneMirroringSendApprovedMessage",
    }
)

CONNECTOR_COMMAND_APPROVAL: dict[str, tuple[str, tuple[str, ...]]] = {
    "codexSelectThread": ("codex.select_thread", ("thread_id",)),
    "codexContinueThread": ("codex.continue_thread", ("title", "prompt")),
    "customerMacAppFocus": ("customer_mac.app_focus", ("app_name",)),
    "customerMacLocalSiteOpen": ("customer_mac.local_site_open", ("url",)),
    "customerMacLocalSiteAction": ("customer_mac.local_site_action", ("action",)),
    "customerMacIphoneMirroringFocus": ("customer_mac.iphone_mirroring_focus", ()),
    "customerMacIphoneMirroringHome": ("customer_mac.iphone_mirroring_home", ()),
    "customerMacIphoneMirroringAppSwitcher": ("customer_mac.iphone_mirroring_app_switcher", ()),
    "customerMacIphoneMirroringSpotlight": ("customer_mac.iphone_mirroring_spotlight", ()),
    "customerMacIphoneMirroringTypeSpotlight": ("customer_mac.iphone_mirroring_type_spotlight", ("text",)),
    "customerMacIphoneMirroringOpenApp": ("customer_mac.iphone_mirroring_open_app", ("app_name",)),
    "customerMacIphoneMirroringTapNamedTarget": ("customer_mac.iphone_mirroring_tap_named_target", ("target_label",)),
    "customerMacIphoneMirroringScroll": ("customer_mac.iphone_mirroring_scroll", ("direction",)),
    "customerMacIphoneMirroringSwipeLeft": ("customer_mac.iphone_mirroring_swipe_left", ()),
    "customerMacIphoneMirroringSwipeRight": ("customer_mac.iphone_mirroring_swipe_right", ()),
    "customerMacIphoneMirroringSwipeUp": ("customer_mac.iphone_mirroring_swipe_up", ()),
    "customerMacIphoneMirroringSwipeDown": ("customer_mac.iphone_mirroring_swipe_down", ()),
    "customerMacIphoneMirroringTypeApprovedText": ("customer_mac.iphone_mirroring_type_approved_text", ("text",)),
    "customerMacIphoneMirroringSendApprovedMessage": ("customer_mac.iphone_mirroring_send_approved_message", ("text", "recipient_context", "target_label")),
}


def build_bridge_argv(command: str, params: dict[str, Any] | None = None) -> list[str]:
    params = params or {}
    fixed: dict[str, list[str]] = {
        "status": ["status", "--json"],
        "capabilities": ["capabilities", "--json"],
        "latest": ["latest", "--json"],
        "codexFrontmost": ["codex", "frontmost", "--json"],
        "codexWindows": ["codex", "windows", "--json"],
        "codexAppServerStatus": ["codex", "app-server", "status", "--json"],
        "codexAppServerRemoteControlStatus": ["codex", "app-server", "remote-control-status", "--json"],
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
    if command == "codexContinueThread":
        return [
            "codex",
            "continue-thread",
            "--json",
            "--title",
            _required_string(params, "title"),
            "--prompt",
            str(params.get("prompt") or "continue"),
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
        return ["customer-mac", "iphone-mirroring", "scroll", "--json", "--direction", str(params.get("direction") or "down"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSwipeLeft":
        return ["customer-mac", "iphone-mirroring", "swipe-left", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSwipeRight":
        return ["customer-mac", "iphone-mirroring", "swipe-right", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSwipeUp":
        return ["customer-mac", "iphone-mirroring", "swipe-up", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSwipeDown":
        return ["customer-mac", "iphone-mirroring", "swipe-down", "--json", *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringTypeApprovedText":
        return ["customer-mac", "iphone-mirroring", "type-approved-text", "--json", "--text", _required_string(params, "text"), *_dry_run_arg(params), *_approval_arg(params)]
    if command == "customerMacIphoneMirroringSendApprovedMessage":
        return [
            "customer-mac",
            "iphone-mirroring",
            "send-approved-message",
            "--json",
            "--text",
            _required_string(params, "text"),
            "--recipient-context",
            _required_string(params, "recipient_context"),
            "--target-label",
            str(params.get("target_label") or "Send"),
            *_dry_run_arg(params),
            *_approval_arg(params),
        ]
    raise ValueError(f"Unsupported connector command: {command}")


def run_connector_server(
    *,
    host: str,
    port: int,
    token: str | None,
    command_runner: CommandRunner,
    state_dir: Path | None = None,
) -> None:
    handler = _make_handler(token=token, command_runner=command_runner, state_dir=state_dir)
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever()


def read_token(path: str | None, *, state_dir: Path | None = None, auto_create: bool = False) -> str | None:
    if not path:
        if not auto_create:
            return None
        token_path = (state_dir or default_state_dir()) / "connector.token"
    else:
        token_path = Path(path).expanduser()
    if not token_path.exists():
        if not auto_create:
            raise ValueError(f"connector token file does not exist: {token_path}")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(48)
        token_path.write_text(token + "\n", encoding="utf-8")
        os.chmod(token_path, 0o600)
        return token
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        if not auto_create:
            raise ValueError(f"connector token file is empty: {token_path}")
        token = secrets.token_urlsafe(48)
        token_path.write_text(token + "\n", encoding="utf-8")
        os.chmod(token_path, 0o600)
    return token


def _make_handler(*, token: str | None, command_runner: CommandRunner, state_dir: Path | None = None) -> type[BaseHTTPRequestHandler]:
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
            if parsed.path == "/v1/enrollment/complete":
                self._complete_enrollment()
                return
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
                approval_error = _live_guarded_approval_error(command, params, state_dir=state_dir)
                if approval_error is not None:
                    self._write_json(
                        403,
                        _error_envelope(
                            command or "connector.command",
                            "customer_mac" if command.startswith("customerMac") else "desktop",
                            "approval_audit_required",
                            approval_error,
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

        def _complete_enrollment(self) -> None:
            try:
                payload = self._read_json()
                enrollment_code = str(payload.get("enrollment_code") or "").strip()
                if not enrollment_code:
                    self._write_json(400, {"ok": False, "error": "missing_enrollment_code"})
                    return
                if not token:
                    self._write_json(503, {"ok": False, "error": "connector_token_unavailable"})
                    return
                connector_url = _connector_url_from_request(self)
                response = complete_enrollment_via_control(
                    enrollment_code=enrollment_code,
                    connector_url=connector_url,
                    connector_token=token,
                    device_name=str(payload.get("device_name") or socket.gethostname() or "Customer Mac"),
                    device_identifier=str(payload.get("device_identifier") or ""),
                )
                self._write_json(200, {"ok": True, "data": response})
            except Exception as exc:
                self._write_json(400, {"ok": False, "error": "enrollment_complete_failed", "message": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _authorized(self) -> bool:
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


def complete_enrollment_via_control(
    *,
    enrollment_code: str,
    connector_url: str,
    connector_token: str,
    device_name: str,
    device_identifier: str = "",
) -> dict[str, Any]:
    body = {
        "action": "complete_enrollment",
        "enrollment_code": enrollment_code,
        "device_name": device_name,
        "device_identifier": device_identifier or None,
        "connector_url": connector_url,
        "connector_token": connector_token,
        "tailnet_ip": _host_without_port(connector_url),
        "capabilities": {
            "connector": "evaos-desktop-bridge",
            "openclaw_tools": "enabled",
            "iphone_mirroring": "named_actions",
        },
        "permission_state": {
            "accessibility": "check_required",
            "screen_recording": "check_required",
        },
    }
    request = urllib.request.Request(
        CUSTOMER_MAC_CONTROL_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:  # noqa: S310 - fixed service URL or explicit env override.
        data = response.read()
    parsed = json.loads(data.decode("utf-8"))
    return parsed if isinstance(parsed, dict) else {"response": parsed}


def _connector_url_from_request(handler: BaseHTTPRequestHandler) -> str:
    host = (handler.headers.get("Host") or "").strip()
    if not host:
        server_host, server_port = handler.server.server_address[:2]
        host = f"{server_host}:{server_port}"
    return f"http://{host}"


def _host_without_port(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host or host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return None
    return host


def _live_guarded_without_approval(command: str, params: dict[str, Any]) -> bool:
    return _live_guarded_approval_error(command, params, state_dir=None, require_lookup=False) is not None


def _live_guarded_approval_error(command: str, params: dict[str, Any], *, state_dir: Path | None, require_lookup: bool = True) -> str | None:
    if command not in GUARDED_REMOTE_COMMANDS:
        return None
    if params.get("dry_run") is not False:
        return None
    approval = params.get("approval_audit_id")
    if not isinstance(approval, str) or not approval.strip():
        return "Live remote control actions require a prior dry-run and approval_audit_id."
    if not require_lookup:
        return None
    command_id, fields = CONNECTOR_COMMAND_APPROVAL[command]
    record = read_audit_record(approval.strip(), state_dir=state_dir)
    if record is None:
        return "approval_audit_id was not found in the local audit log."
    if record.get("command") != command_id or record.get("ok") is not True:
        return "approval_audit_id does not reference a successful dry-run for this command."
    record_args = record.get("args")
    if not isinstance(record_args, dict) or record_args.get("dry_run") is not True:
        return "approval_audit_id must reference a dry-run record."
    freshness_error = approval_audit_freshness_error(record)
    if freshness_error is not None:
        return freshness_error
    for field in fields:
        if record_args.get(field) != _approval_field_value(command, params, field):
            return f"approval_audit_id does not match {field}."
    return None


def _approval_field_value(command: str, params: dict[str, Any], field: str) -> Any:
    if field == "prompt" and command == "codexContinueThread":
        return params.get("prompt") or "continue"
    if field == "direction" and command == "customerMacIphoneMirroringScroll":
        return params.get("direction") or "down"
    if field == "target_label" and command == "customerMacIphoneMirroringSendApprovedMessage":
        return params.get("target_label") or "Send"
    return params.get(field)


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
