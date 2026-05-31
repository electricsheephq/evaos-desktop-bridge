from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import secrets
import socket
import stat
import struct
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from errno import ELOOP
from pathlib import Path
from typing import Any

from .audit import default_state_dir
from .schema import make_error, timestamp_utc
from .types import CommandResult

HELPER_IPC_SCHEMA_VERSION = "evaos.helper_ipc.v1"
HELPER_IPC_MAX_BYTES = 64 * 1024
HELPER_IPC_ALLOWED_COMMANDS = frozenset({"ping", "mouse_action", "ax_action"})
HELPER_USE_ENV = "EVAOS_DESKTOP_BRIDGE_USE_HELPER"
HELPER_SOCKET_ENV = "EVAOS_DESKTOP_BRIDGE_HELPER_SOCKET"
HELPER_TOKEN_FILE_ENV = "EVAOS_DESKTOP_BRIDGE_HELPER_TOKEN_FILE"
HELPER_RESPONSIBLE_BUNDLE_ID_ENV = "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_BUNDLE_ID"
HELPER_RESPONSIBLE_APP_PATH_ENV = "EVAOS_DESKTOP_BRIDGE_HELPER_RESPONSIBLE_APP_PATH"
HELPER_ENFORCE_PERMISSIONS_ENV = "EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS"
EVAOS_WORKBENCH_BUNDLE_ID = "com.electricsheephq.EvaDesktop"
ACCESSIBILITY_DEEP_LINK = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
SCREEN_RECORDING_DEEP_LINK = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


class HelperIpcError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class QuartzMouseActionExecutor:
    def __init__(self) -> None:
        self._quartz: Any | None = None

    def __call__(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        if command != "mouse_action":
            raise HelperIpcError("helper_ipc_command_not_allowed", "Helper executor only supports mouse_action.")
        action = payload.get("action")
        if action not in {"click", "scroll", "drag"}:
            raise HelperIpcError("helper_ipc_bad_payload", "mouse_action requires action click, scroll, or drag.")
        target = self._target_from_payload(payload)
        web_content = self._target_path_contains_role(target, "AXWebArea")
        if web_content:
            return {
                "ok": False,
                "data": {"performed": False, "action": action, "target": self._target_summary(target), "engine": "helper_post_to_pid"},
                "warnings": [],
                "errors": [
                    {
                        "code": "helper_post_to_pid_web_content_inert",
                        "message": "CGEventPostToPid events against browser web content are treated as inert and are not reported as success.",
                        "guidance": "Route browser web content through the browser/Playwright strategy instead of Tier-2 process events.",
                    }
                ],
            }
        try:
            quartz = self._load_quartz()
            source = quartz.CGEventSourceCreate(quartz.kCGEventSourceStateCombinedSessionState)
            pid = int(target["pid"])
            if action == "click":
                x = _required_int(payload, "x")
                y = _required_int(payload, "y")
                self._post_mouse(quartz, pid, source, quartz.kCGEventMouseMoved, x, y)
                self._post_mouse(quartz, pid, source, quartz.kCGEventLeftMouseDown, x, y)
                self._post_mouse(quartz, pid, source, quartz.kCGEventLeftMouseUp, x, y)
                return {
                    "ok": True,
                    "data": {"performed": True, "clicked": True, "action": action, "point": {"x": x, "y": y}, "target": self._target_summary(target), "engine": "helper_post_to_pid"},
                    "warnings": [],
                    "errors": [],
                }
            if action == "scroll":
                direction = _required_string(payload, "direction")
                amount = _required_int(payload, "amount")
                if direction not in {"up", "down", "left", "right"}:
                    raise HelperIpcError("helper_ipc_bad_payload", "scroll direction must be up, down, left, or right.")
                dy = amount if direction == "up" else -amount
                dx = amount if direction == "left" else -amount if direction == "right" else 0
                if direction in {"up", "down"}:
                    dx = 0
                else:
                    dy = 0
                event = quartz.CGEventCreateScrollWheelEvent(source, quartz.kCGScrollEventUnitPixel, 2, dy, dx)
                quartz.CGEventPostToPid(pid, event)
                return {
                    "ok": True,
                    "data": {"performed": True, "scrolled": True, "action": action, "direction": direction, "amount": amount, "target": self._target_summary(target), "engine": "helper_post_to_pid"},
                    "warnings": [],
                    "errors": [],
                }
            from_x = _required_int(payload, "from_x")
            from_y = _required_int(payload, "from_y")
            to_x = _required_int(payload, "to_x")
            to_y = _required_int(payload, "to_y")
            self._post_mouse(quartz, pid, source, quartz.kCGEventMouseMoved, from_x, from_y)
            self._post_mouse(quartz, pid, source, quartz.kCGEventLeftMouseDown, from_x, from_y)
            self._post_mouse(quartz, pid, source, quartz.kCGEventLeftMouseDragged, to_x, to_y)
            self._post_mouse(quartz, pid, source, quartz.kCGEventLeftMouseUp, to_x, to_y)
            return {
                "ok": True,
                "data": {
                    "performed": True,
                    "dragged": True,
                    "action": action,
                    "from": {"x": from_x, "y": from_y},
                    "to": {"x": to_x, "y": to_y},
                    "target": self._target_summary(target),
                    "engine": "helper_post_to_pid",
                },
                "warnings": [],
                "errors": [],
            }
        except HelperIpcError:
            raise
        except Exception as exc:
            return {
                "ok": False,
                "data": {"performed": False, "action": action},
                "warnings": [],
                "errors": [
                    {
                        "code": "helper_mouse_action_failed",
                        "message": str(exc),
                        "guidance": "Verify Accessibility permission for the signed helper identity.",
                    }
                ],
            }

    def _load_quartz(self) -> Any:
        if self._quartz is None:
            import Quartz  # type: ignore[import-not-found]

            self._quartz = Quartz
        return self._quartz

    def _target_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = payload.get("target")
        if not isinstance(target, dict):
            raise HelperIpcError("helper_ipc_bad_payload", "mouse_action requires a target with pid and process_name for per-process posting.")
        pid = target.get("pid")
        if type(pid) is not int or pid <= 0:
            raise HelperIpcError("helper_ipc_bad_payload", "mouse_action target pid must be a positive integer.")
        process_name = target.get("process_name")
        if not isinstance(process_name, str) or not process_name.strip():
            raise HelperIpcError("helper_ipc_bad_payload", "mouse_action target process_name is required.")
        actual = self._process_name_for_pid(pid)
        if not actual:
            raise HelperIpcError("helper_post_to_pid_target_unavailable", "mouse_action target process is not currently running.")
        expected_base = Path(process_name.strip()).name
        actual_base = Path(actual).name
        if actual != process_name.strip() and actual_base != expected_base:
            raise HelperIpcError("helper_post_to_pid_process_mismatch", "mouse_action target process no longer matches the audited snapshot.")
        return target

    @staticmethod
    def _process_name_for_pid(pid: int) -> str | None:
        try:
            completed = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "comm="], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=1.0)
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        value = completed.stdout.strip()
        return value or None

    @staticmethod
    def _target_path_contains_role(target: dict[str, Any], role: str) -> bool:
        path = target.get("path")
        return isinstance(path, list) and any(isinstance(segment, dict) and segment.get("role") == role for segment in path)

    @staticmethod
    def _target_summary(target: dict[str, Any]) -> dict[str, Any]:
        path = target.get("path")
        path_hash = None
        if isinstance(path, list):
            path_hash = hashlib.sha256(json.dumps(path, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        return {"pid": target.get("pid"), "path_hash": path_hash}

    @staticmethod
    def _post_mouse(quartz: Any, pid: int, source: Any, kind: int, x: int, y: int) -> None:
        event = quartz.CGEventCreateMouseEvent(source, kind, (x, y), quartz.kCGMouseButtonLeft)
        quartz.CGEventPostToPid(pid, event)


class AxActionExecutor:
    PERFORM_ACTIONS = {
        "press": "AXPress",
    }
    VALUE_ATTRIBUTES = {
        "set_value": "AXValue",
        "set_selected_text": "AXSelectedText",
    }
    EDITABLE_VALUE_ROLES = frozenset({"AXTextField", "AXTextArea", "AXComboBox"})
    ALLOWED_ACTIONS = frozenset((*PERFORM_ACTIONS.keys(), *VALUE_ATTRIBUTES.keys(), "menu"))

    def __init__(self) -> None:
        self._as: Any | None = None

    def __call__(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        if command != "ax_action":
            raise HelperIpcError("helper_ipc_command_not_allowed", "Helper AX executor only supports ax_action.")
        action = _required_string(payload, "action")
        if action not in self.ALLOWED_ACTIONS:
            raise HelperIpcError("helper_ipc_bad_payload", "ax_action action is not allowed.")
        target = _required_ax_target(payload)
        try:
            app_services = self._load_application_services()
            identity_error = self._target_identity_error(action, target)
            if identity_error is not None:
                return identity_error
            if action == "menu":
                menu_path = _required_menu_path(payload)
                self._perform_menu(app_services, target, menu_path)
                return {
                    "ok": True,
                    "data": {"performed": True, "action": action, "menu_path": " > ".join(menu_path), "engine": "helper_ax"},
                    "warnings": [],
                    "errors": [],
                }
            if _target_path_contains_role(target, "AXWebArea"):
                return {
                    "ok": False,
                    "data": {"performed": False, "action": action, "engine": "helper_ax"},
                    "warnings": [],
                    "errors": [
                        {
                            "code": "helper_ax_web_content_inert",
                            "message": "AX actions against browser web content are treated as inert and are not reported as success.",
                            "guidance": "Route browser web content through the browser/Playwright strategy instead of Tier-1 AX.",
                        }
                    ],
                }
            element = self._resolve_target(app_services, target)
            if action in self.PERFORM_ACTIONS:
                native_action = self.PERFORM_ACTIONS[action]
                err = app_services.AXUIElementPerformAction(element, native_action)
                if err != 0:
                    return self._error(action, "helper_ax_action_failed", f"AX action {native_action} failed with code {err}.")
                return {
                    "ok": True,
                    "data": {
                        "performed": True,
                        "action": action,
                        "native_action": native_action,
                        "target": self._target_summary(target),
                        "engine": "helper_ax",
                    },
                    "warnings": [],
                    "errors": [],
                }
            value = _required_ax_value(payload)
            role = self._text_value(self._ax_value(app_services, element, self._constant(app_services, "kAXRoleAttribute", "AXRole")))
            if role == "AXSecureTextField":
                return self._error(action, "helper_ax_secure_field_blocked", "AX value setting is blocked for secure text fields.")
            attribute = self.VALUE_ATTRIBUTES[action]
            if role not in self.EDITABLE_VALUE_ROLES:
                return self._error(action, "helper_ax_non_text_field_blocked", f"AX value setting is blocked for non-text role {role or 'unknown'}.")
            if not self._attribute_settable(app_services, element, attribute):
                return self._error(action, "helper_ax_attribute_not_settable", f"AX attribute {attribute} is not settable on the target element.")
            err = app_services.AXUIElementSetAttributeValue(element, attribute, value)
            if err != 0:
                return self._error(action, "helper_ax_set_value_failed", f"AX attribute {attribute} failed with code {err}.")
            return {
                "ok": True,
                "data": {
                    "performed": True,
                    "action": action,
                    "attribute": attribute,
                    "value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                    "target": self._target_summary(target),
                    "engine": "helper_ax",
                },
                "warnings": [],
                "errors": [],
            }
        except HelperIpcError:
            raise
        except Exception as exc:
            return self._error(action, "helper_ax_action_failed", str(exc))

    def _load_application_services(self) -> Any:
        if self._as is None:
            import ApplicationServices as AS  # type: ignore[import-not-found]

            self._as = AS
        return self._as

    @staticmethod
    def _target_summary(target: dict[str, Any]) -> dict[str, Any]:
        path = target.get("path")
        path_hash = None
        if isinstance(path, list):
            path_hash = hashlib.sha256(json.dumps(path, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        return {"pid": target.get("pid"), "path_hash": path_hash}

    def _target_identity_error(self, action: str, target: dict[str, Any]) -> dict[str, Any] | None:
        expected = target.get("process_name")
        if not isinstance(expected, str) or not expected.strip():
            return None
        actual = self._process_name_for_pid(int(target["pid"]))
        expected_base = Path(expected.strip()).name
        actual_base = Path(actual or "").name if actual else None
        if actual_base == expected.strip() or actual_base == expected_base:
            return None
        return self._error(action, "helper_ax_target_process_mismatch", "AX target process no longer matches the audited snapshot.")

    @staticmethod
    def _process_name_for_pid(pid: int) -> str | None:
        try:
            completed = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "comm="], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=1.0)
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        value = completed.stdout.strip()
        return value or None

    def _resolve_target(self, app_services: Any, target: dict[str, Any]) -> Any:
        pid = int(target["pid"])
        path = target.get("path")
        if not isinstance(path, list) or not path:
            raise HelperIpcError("helper_ipc_bad_payload", "ax_action target requires a non-empty path.")
        current = app_services.AXUIElementCreateApplication(pid)
        for depth, segment in enumerate(path):
            if not isinstance(segment, dict):
                raise HelperIpcError("helper_ipc_bad_payload", "ax_action target path entries must be objects.")
            children = self._segment_children(app_services, current, segment, root=depth == 0)
            current = self._resolve_segment(app_services, children, segment)
        return current

    def _segment_children(self, app_services: Any, current: Any, segment: dict[str, Any], *, root: bool) -> list[Any]:
        role = str(segment.get("role") or "")
        if root and role == "AXWindow":
            value = self._ax_value(app_services, current, self._constant(app_services, "kAXWindowsAttribute", "AXWindows"))
        elif root and role == "AXMenuBar":
            value = self._ax_value(app_services, current, self._constant(app_services, "kAXMenuBarAttribute", "AXMenuBar"))
            return [value] if value is not None else []
        else:
            value = self._ax_value(app_services, current, self._constant(app_services, "kAXChildrenAttribute", "AXChildren"))
        try:
            return list(value or [])
        except Exception:
            return []

    def _resolve_segment(self, app_services: Any, candidates: list[Any], segment: dict[str, Any]) -> Any:
        index = segment.get("index")
        if type(index) is int and 0 <= index < len(candidates) and self._segment_matches(app_services, candidates[index], segment):
            return candidates[index]
        matches = [candidate for candidate in candidates if self._segment_matches(app_services, candidate, segment)]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise HelperIpcError("helper_ax_target_not_found", "AX target path did not resolve to an element.")
        raise HelperIpcError("helper_ax_target_ambiguous", "AX target path resolved to multiple elements.")

    def _segment_matches(self, app_services: Any, element: Any, segment: dict[str, Any]) -> bool:
        expected_role = segment.get("role")
        if isinstance(expected_role, str) and expected_role:
            role = self._text_value(self._ax_value(app_services, element, self._constant(app_services, "kAXRoleAttribute", "AXRole")))
            if role != expected_role:
                return False
        expected_identifier = segment.get("identifier")
        if isinstance(expected_identifier, str) and expected_identifier:
            identifier = self._text_value(self._ax_value(app_services, element, self._constant(app_services, "kAXIdentifierAttribute", "AXIdentifier")))
            if identifier != expected_identifier:
                return False
        expected_name = segment.get("name")
        if isinstance(expected_name, str) and expected_name:
            names = {
                self._text_value(self._ax_value(app_services, element, self._constant(app_services, "kAXTitleAttribute", "AXTitle"))),
                self._text_value(self._ax_value(app_services, element, self._constant(app_services, "kAXDescriptionAttribute", "AXDescription"))),
                self._text_value(self._ax_value(app_services, element, self._constant(app_services, "kAXValueAttribute", "AXValue"))),
            }
            if expected_name not in names:
                return False
        return True

    def _perform_menu(self, app_services: Any, target: dict[str, Any], menu_path: list[str]) -> None:
        app = app_services.AXUIElementCreateApplication(int(target["pid"]))
        menu_bar = self._ax_value(app_services, app, self._constant(app_services, "kAXMenuBarAttribute", "AXMenuBar"))
        if menu_bar is None:
            raise HelperIpcError("helper_ax_menu_not_found", "AX menu bar was not available for the target app.")
        current = menu_bar
        for index, label in enumerate(menu_path):
            children = self._children(app_services, current)
            matches = [child for child in children if self._element_name(app_services, child) == label]
            if len(matches) != 1:
                raise HelperIpcError("helper_ax_menu_not_found", "AX menu path did not resolve uniquely.")
            current = matches[0]
            err = app_services.AXUIElementPerformAction(current, "AXPress")
            if err != 0:
                raise HelperIpcError("helper_ax_menu_failed", f"AX menu action failed with code {err}.")
            if index < len(menu_path) - 1:
                time.sleep(0.05)

    def _children(self, app_services: Any, element: Any) -> list[Any]:
        value = self._ax_value(app_services, element, self._constant(app_services, "kAXChildrenAttribute", "AXChildren"))
        try:
            return list(value or [])
        except Exception:
            return []

    @staticmethod
    def _attribute_settable(app_services: Any, element: Any, attribute: str) -> bool:
        checker = getattr(app_services, "AXUIElementIsAttributeSettable", None)
        if checker is None:
            return True
        try:
            result = checker(element, attribute, None)
        except TypeError:
            try:
                result = checker(element, attribute)
            except Exception:
                return True
        except Exception:
            return True
        if isinstance(result, tuple) and len(result) >= 2:
            err, settable = result[0], result[1]
            return err == 0 and bool(settable)
        if isinstance(result, bool):
            return result
        return True

    def _element_name(self, app_services: Any, element: Any) -> str | None:
        return self._text_value(self._ax_value(app_services, element, self._constant(app_services, "kAXTitleAttribute", "AXTitle"))) or self._text_value(
            self._ax_value(app_services, element, self._constant(app_services, "kAXDescriptionAttribute", "AXDescription"))
        )

    @staticmethod
    def _ax_value(app_services: Any, element: Any, attr: str) -> Any:
        try:
            err, value = app_services.AXUIElementCopyAttributeValue(element, attr, None)
        except Exception:
            return None
        if err != 0:
            return None
        return value

    @staticmethod
    def _text_value(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return str(value)
        except Exception:
            return None

    @staticmethod
    def _constant(app_services: Any, name: str, fallback: str) -> str:
        return str(getattr(app_services, name, fallback))

    @staticmethod
    def _error(action: str, code: str, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "data": {"performed": False, "action": action, "engine": "helper_ax"},
            "warnings": [],
            "errors": [
                {
                    "code": code,
                    "message": message,
                    "guidance": "Verify the target is a supported native Accessibility element and retry from a fresh desktop_see snapshot.",
                }
            ],
        }


class ComputerUseHelperExecutor:
    def __init__(self) -> None:
        self._mouse = QuartzMouseActionExecutor()
        self._ax = AxActionExecutor()

    def __call__(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        if command == "mouse_action":
            return self._mouse(command, payload)
        if command == "ax_action":
            return self._ax(command, payload)
        raise HelperIpcError("helper_ipc_command_not_allowed", "Helper executor does not support this command.")


class UnixSocketHelperClient:
    def __init__(self, *, socket_path: Path | str, token: str, timeout: float = 2.0) -> None:
        self.socket_path = Path(socket_path)
        self.token = token
        self.timeout = timeout

    def dispatch(self, command: str, payload: dict[str, object], *, audit_id: str | None = None) -> CommandResult:
        request = build_helper_request(
            command=command,
            token=self.token,
            request_id=f"req-{uuid.uuid4().hex}",
            audit_id=audit_id,
            payload=dict(payload),
        )
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(str(self.socket_path))
                client.sendall(encode_frame(request))
                response = _recv_frame(client)
        except OSError as exc:
            return CommandResult(
                ok=False,
                data={"helper_socket": str(self.socket_path), "command": command},
                errors=[
                    make_error(
                        code="helper_unavailable",
                        message="Persistent computer-use helper is unavailable.",
                        guidance=f"Start the helper daemon for this user or disable helper mode. Detail: {exc}",
                    )
                ],
                provenance={"source": "computer_use_helper"},
            )
        return _command_result_from_response(response)


class UnavailableHelperClient:
    def __init__(self, *, code: str, message: str) -> None:
        self.code = code
        self.message = message

    def dispatch(self, command: str, payload: dict[str, object], *, audit_id: str | None = None) -> CommandResult:
        return CommandResult(
            ok=False,
            data={"command": command},
            errors=[
                make_error(
                    code=self.code,
                    message=self.message,
                    guidance="Start the local evaOS computer-use helper or unset EVAOS_DESKTOP_BRIDGE_USE_HELPER to use supervised fallback mode.",
                )
            ],
            provenance={"source": "computer_use_helper"},
        )


def make_capability_token() -> str:
    return secrets.token_urlsafe(48)


def default_helper_socket_path(state_dir: Path | None = None) -> Path:
    return Path("/tmp") / f"evaos-helper-{os.getuid()}.sock"


def default_helper_token_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / "computer-use-helper.token"


def read_helper_token(*, token_file: Path | str | None = None, state_dir: Path | None = None, auto_create: bool = False) -> str:
    path = Path(token_file).expanduser() if token_file is not None else default_helper_token_path(state_dir)
    if auto_create:
        return _write_new_helper_token(path)
    try:
        value = _read_helper_token_file(path)
    except FileNotFoundError:
        raise HelperIpcError("helper_token_missing", "Helper token file does not exist.") from None
    if value:
        return value
    raise HelperIpcError("helper_token_missing", "Helper token file is empty.")


def helper_client_from_environment(*, state_dir: Path | None = None) -> UnixSocketHelperClient | UnavailableHelperClient | None:
    if os.environ.get(HELPER_USE_ENV) not in {"1", "true", "TRUE", "yes", "YES"}:
        return None
    socket_path = Path(os.environ.get(HELPER_SOCKET_ENV) or default_helper_socket_path(state_dir)).expanduser()
    token_file = os.environ.get(HELPER_TOKEN_FILE_ENV)
    try:
        token = read_helper_token(token_file=token_file, state_dir=state_dir, auto_create=False)
    except HelperIpcError as exc:
        return UnavailableHelperClient(code=exc.code, message=exc.message)
    return UnixSocketHelperClient(socket_path=socket_path, token=token)


def build_helper_request(
    *,
    command: str,
    token: str,
    request_id: str,
    audit_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": HELPER_IPC_SCHEMA_VERSION,
        "request_id": request_id,
        "command": command,
        "capability_token": token,
        "payload": payload or {},
    }
    if audit_id is not None:
        request["audit_id"] = audit_id
    return request


def handle_helper_request(
    request: dict[str, Any],
    *,
    expected_token: str,
    expected_uid: int | None,
    peer_uid: int | None,
    command_executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    permission_checker: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _authorize_request(request, expected_token=expected_token, expected_uid=expected_uid, peer_uid=peer_uid)
    if request.get("schema_version") != HELPER_IPC_SCHEMA_VERSION:
        raise HelperIpcError("helper_ipc_bad_schema", "Helper IPC request has an unsupported schema version.")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise HelperIpcError("helper_ipc_bad_request_id", "Helper IPC request id must be a non-empty string.")
    command = request.get("command")
    if not isinstance(command, str) or command not in HELPER_IPC_ALLOWED_COMMANDS:
        raise HelperIpcError("helper_ipc_command_not_allowed", "Helper IPC command is not allowed.")
    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise HelperIpcError("helper_ipc_bad_payload", "Helper IPC request payload must be a JSON object.")
    audit_id = request.get("audit_id")
    if audit_id is not None and (not isinstance(audit_id, str) or not audit_id):
        raise HelperIpcError("helper_ipc_bad_audit_id", "Helper IPC audit id must be a non-empty string when present.")
    if command in {"mouse_action", "ax_action"}:
        if not isinstance(audit_id, str) or not audit_id.startswith("audit-"):
            raise HelperIpcError("helper_ipc_audit_required", f"Helper IPC {command} requires an audit id from the bridge actuation path.")
        if command_executor is None:
            raise HelperIpcError("helper_ipc_executor_unavailable", "Helper IPC actuation executor is not configured.")
        permission_preflight = permission_checker() if permission_checker is not None else helper_permission_preflight()
        preflight_errors = helper_permission_preflight_errors(permission_preflight)
        if preflight_errors:
            return {
                "schema_version": HELPER_IPC_SCHEMA_VERSION,
                "request_id": request_id,
                "audit_id": audit_id,
                "ok": False,
                "timestamp": timestamp_utc(),
                "data": {"performed": False, "command": command, "action": payload.get("action"), "permission_preflight": permission_preflight},
                "warnings": [],
                "errors": preflight_errors,
            }
        executed = command_executor(command, payload)
        data = executed.get("data")
        if isinstance(data, dict):
            executed = dict(executed)
            executed["data"] = {**data, "permission_preflight": permission_preflight}
        return _response_from_executor(request_id=request_id, audit_id=audit_id, executed=executed)
    permission_preflight = permission_checker() if permission_checker is not None else helper_permission_preflight()
    return {
        "schema_version": HELPER_IPC_SCHEMA_VERSION,
        "request_id": request_id,
        "ok": True,
        "timestamp": timestamp_utc(),
        "data": {
            "command": command,
            "helper_mode": "resident_local" if command_executor is not None else "contract_only",
            "actuation_enabled": command_executor is not None,
            "permission_preflight": permission_preflight,
        },
        "warnings": [],
        "errors": [],
    }


def _response_from_executor(*, request_id: str, audit_id: str, executed: dict[str, Any]) -> dict[str, Any]:
    ok = executed.get("ok")
    if type(ok) is not bool:
        raise HelperIpcError("helper_ipc_bad_executor_response", "Helper IPC executor response must include ok as a boolean.")
    data = executed.get("data", {})
    warnings = executed.get("warnings", [])
    errors = executed.get("errors", [])
    if not isinstance(data, dict) or not isinstance(warnings, list) or not isinstance(errors, list):
        raise HelperIpcError("helper_ipc_bad_executor_response", "Helper IPC executor response has an invalid shape.")
    return {
        "schema_version": HELPER_IPC_SCHEMA_VERSION,
        "request_id": request_id,
        "audit_id": audit_id,
        "ok": ok,
        "timestamp": timestamp_utc(),
        "data": data,
        "warnings": warnings,
        "errors": errors,
    }


def run_helper_server(
    *,
    socket_path: Path | str,
    token: str,
    expected_uid: int | None = None,
    command_executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    permission_checker: Callable[[], dict[str, Any]] | None = None,
    ready: Any | None = None,
    max_requests: int | None = None,
    peer_uid_getter: Callable[[socket.socket], int | None] | None = None,
    connection_timeout: float = 2.0,
) -> None:
    path = Path(socket_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _unlink_existing_socket(path, missing_ok=True, fail_on_non_socket=True)
    executor = command_executor or ComputerUseHelperExecutor()
    peer_uid = peer_uid_getter or socket_peer_uid
    served = 0
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(path))
        os.chmod(path, 0o600)
        server.listen(8)
        if ready is not None:
            ready.set()
        while max_requests is None or served < max_requests:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(connection_timeout)
                request: dict[str, Any] | None = None
                try:
                    request = _recv_frame(connection)
                    response = handle_helper_request(
                        request,
                        expected_token=token,
                        expected_uid=os.getuid() if expected_uid is None else expected_uid,
                        peer_uid=peer_uid(connection),
                        command_executor=executor,
                        permission_checker=permission_checker,
                    )
                except socket.timeout:
                    response = _error_response(
                        request=request,
                        code="helper_ipc_timeout",
                        message="Helper IPC connection timed out while reading a frame.",
                    )
                except HelperIpcError as exc:
                    response = _error_response(request=request, code=exc.code, message=exc.message)
                except Exception as exc:
                    response = _error_response(request=request, code="helper_ipc_server_error", message=str(exc))
                _send_frame_best_effort(connection, response)
                served += 1
    finally:
        server.close()
        try:
            _unlink_existing_socket(path, missing_ok=True, fail_on_non_socket=True)
        except HelperIpcError:
            pass


def _send_frame_best_effort(connection: socket.socket, response: dict[str, Any]) -> bool:
    try:
        frame = encode_frame(response)
    except (HelperIpcError, TypeError, ValueError, OverflowError):
        try:
            frame = encode_frame(
                _error_response(
                    request=None,
                    code="helper_ipc_server_error",
                    message="Helper IPC response could not be encoded.",
                )
            )
        except (HelperIpcError, TypeError, ValueError, OverflowError):
            return False
    try:
        connection.sendall(frame)
        return True
    except (BrokenPipeError, ConnectionResetError, socket.timeout, OSError):
        return False


def encode_frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > HELPER_IPC_MAX_BYTES:
        raise HelperIpcError("helper_ipc_payload_too_large", "Helper IPC payload exceeds the maximum frame size.")
    return len(body).to_bytes(4, "big") + body


def decode_frame(frame: bytes) -> dict[str, Any]:
    if len(frame) < 4:
        raise HelperIpcError("helper_ipc_frame_truncated", "Helper IPC frame is missing its length prefix.")
    length = int.from_bytes(frame[:4], "big")
    if length > HELPER_IPC_MAX_BYTES:
        raise HelperIpcError("helper_ipc_payload_too_large", "Helper IPC payload exceeds the maximum frame size.")
    body = frame[4:]
    if len(body) != length:
        raise HelperIpcError("helper_ipc_frame_truncated", "Helper IPC frame length does not match its payload.")
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HelperIpcError("helper_ipc_bad_json", "Helper IPC frame payload is not valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise HelperIpcError("helper_ipc_bad_payload", "Helper IPC frame payload must be a JSON object.")
    return decoded


def _recv_frame(sock: socket.socket) -> dict[str, Any]:
    prefix = _recv_exact(sock, 4)
    length = int.from_bytes(prefix, "big")
    if length > HELPER_IPC_MAX_BYTES:
        raise HelperIpcError("helper_ipc_payload_too_large", "Helper IPC payload exceeds the maximum frame size.")
    return decode_frame(prefix + _recv_exact(sock, length))


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise HelperIpcError("helper_ipc_frame_truncated", "Helper IPC frame ended before the expected payload length.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def socket_peer_uid(sock: socket.socket) -> int | None:
    if getattr(socket, "SO_PEERCRED", None) is not None:
        try:
            raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _pid, uid, _gid = struct.unpack("3i", raw)
            return int(uid)
        except OSError:
            pass
    if getattr(socket, "LOCAL_PEERCRED", None) is not None:
        for level in (getattr(socket, "SOL_LOCAL", 0), socket.SOL_SOCKET):
            try:
                raw = sock.getsockopt(level, socket.LOCAL_PEERCRED, 256)
            except OSError:
                continue
            if len(raw) >= 8:
                try:
                    _version, uid = struct.unpack("ii", raw[:8])
                except struct.error:
                    continue
                return int(uid)
    return None


def _command_result_from_response(response: dict[str, Any]) -> CommandResult:
    ok = response.get("ok") is True
    data = response.get("data")
    warnings = response.get("warnings")
    errors = response.get("errors")
    return CommandResult(
        ok=ok,
        data=data if isinstance(data, dict) else {},
        warnings=warnings if isinstance(warnings, list) else [],
        errors=errors if isinstance(errors, list) else [],
        provenance={"source": "computer_use_helper", "request_id": response.get("request_id"), "helper_audit_id": response.get("audit_id")},
    )


def helper_permission_preflight(
    *,
    env: dict[str, str] | None = None,
    platform_name: str | None = None,
    accessibility_checker: Callable[[], bool | None] | None = None,
    screen_recording_checker: Callable[[], bool | None] | None = None,
    parent_process_path: str | None = None,
) -> dict[str, Any]:
    environment = os.environ if env is None else env
    current_platform = platform_name or platform.system()
    expected_bundle_id = EVAOS_WORKBENCH_BUNDLE_ID
    responsible_bundle_id = environment.get(HELPER_RESPONSIBLE_BUNDLE_ID_ENV) or None
    responsible_app_path = environment.get(HELPER_RESPONSIBLE_APP_PATH_ENV) or None
    enforced = environment.get(HELPER_ENFORCE_PERMISSIONS_ENV) in {"1", "true", "TRUE", "yes", "YES"}
    parent_pid = os.getppid()
    resolved_parent_process_path = parent_process_path if parent_process_path is not None else _parent_process_path(parent_pid)
    parent_status = _parent_process_status(responsible_app_path, resolved_parent_process_path)

    if responsible_bundle_id == expected_bundle_id and responsible_app_path and parent_status == "matched_responsible_app":
        identity_status = "workbench_signed_app"
    elif responsible_bundle_id == expected_bundle_id and responsible_app_path:
        identity_status = "parent_unverified"
    elif responsible_bundle_id:
        identity_status = "mismatch"
    else:
        identity_status = "unattributed_cli"

    if current_platform == "Darwin":
        accessibility = _permission_status(accessibility_checker or check_accessibility_trusted)
        screen_recording = _permission_status(screen_recording_checker or check_screen_recording_trusted)
    else:
        accessibility = "unknown"
        screen_recording = "unknown"

    ok = (
        (not enforced or identity_status == "workbench_signed_app")
        and (not enforced or current_platform != "Darwin" or (accessibility == "granted" and screen_recording == "granted"))
    )
    return {
        "ok": ok,
        "enforced": enforced,
        "platform": current_platform,
        "identity": {
            "expected_bundle_id": expected_bundle_id,
            "responsible_bundle_id": responsible_bundle_id,
            "responsible_app_path": responsible_app_path,
            "process_executable": sys.executable,
            "parent_pid": parent_pid,
            "parent_executable": resolved_parent_process_path,
            "parent_status": parent_status,
            "status": identity_status,
        },
        "permissions": {
            "accessibility": {
                "status": accessibility,
                "deep_link": ACCESSIBILITY_DEEP_LINK,
            },
            "screen_recording": {
                "status": screen_recording,
                "deep_link": SCREEN_RECORDING_DEEP_LINK,
            },
        },
    }


def helper_permission_preflight_errors(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    if preflight.get("ok") is True or preflight.get("enforced") is not True:
        return []
    errors: list[dict[str, Any]] = []
    identity = preflight.get("identity") if isinstance(preflight.get("identity"), dict) else {}
    if identity.get("status") != "workbench_signed_app":
        errors.append(
            make_error(
                code="helper_identity_unverified",
                message="Computer-use helper must be launched by the signed evaOS Workbench app before actuation.",
                guidance="Start Mac Access from evaOS Workbench so macOS resolves helper permissions to the evaOS.app identity.",
            )
        )
    permissions = preflight.get("permissions") if isinstance(preflight.get("permissions"), dict) else {}
    missing: list[str] = []
    for key, label in (("accessibility", "Accessibility"), ("screen_recording", "Screen Recording")):
        item = permissions.get(key) if isinstance(permissions.get(key), dict) else {}
        if item.get("status") != "granted":
            missing.append(label)
    if missing:
        noun = "permissions are" if len(missing) > 1 else "permission is"
        errors.append(
            make_error(
                code="permission_missing",
                message=f"{' and '.join(missing)} {noun} required before helper actuation.",
                guidance=(
                    "Open System Settings > Privacy & Security and approve evaOS Workbench for Accessibility and Screen Recording. "
                    f"Accessibility: {ACCESSIBILITY_DEEP_LINK}; Screen Recording: {SCREEN_RECORDING_DEEP_LINK}"
                ),
                permission=",".join(name.lower().replace(" ", "_") for name in missing),
            )
        )
    return errors


def _permission_status(checker: Callable[[], bool | None]) -> str:
    try:
        trusted = checker()
    except Exception:
        return "unknown"
    if trusted is True:
        return "granted"
    if trusted is False:
        return "missing"
    return "unknown"


def _parent_process_path(pid: int) -> str | None:
    if platform.system() != "Darwin":
        return None
    try:
        completed = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "comm="],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _parent_process_status(responsible_app_path: str | None, parent_process_path: str | None) -> str:
    if not responsible_app_path:
        return "missing_responsible_app_path"
    if not parent_process_path:
        return "unknown"
    app_path = str(Path(responsible_app_path).expanduser().resolve(strict=False)).rstrip("/")
    parent_path = str(Path(parent_process_path).expanduser().resolve(strict=False))
    if parent_path == app_path or parent_path.startswith(f"{app_path}/"):
        return "matched_responsible_app"
    return "mismatch"


def check_accessibility_trusted() -> bool | None:
    if platform.system() != "Darwin":
        return None
    try:
        app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        app_services.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(app_services.AXIsProcessTrusted())
    except Exception:
        return None


def check_screen_recording_trusted() -> bool | None:
    if platform.system() != "Darwin":
        return None
    try:
        core_graphics = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        core_graphics.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        return bool(core_graphics.CGPreflightScreenCaptureAccess())
    except Exception:
        return None


def _write_new_helper_token(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    token = make_capability_token()
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return token


def _read_helper_token_file(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno == ELOOP:
            raise HelperIpcError("helper_token_unsafe", "Helper token file must not be a symlink.") from None
        raise
    try:
        info = os.fstat(fd)
        _validate_helper_token_stat(info)
        return os.read(fd, 4096).decode("utf-8").strip()
    finally:
        os.close(fd)


def _validate_helper_token_stat(info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode):
        raise HelperIpcError("helper_token_unsafe", "Helper token file must not be a symlink.")
    if not stat.S_ISREG(info.st_mode):
        raise HelperIpcError("helper_token_unsafe", "Helper token path must be a regular file.")
    if info.st_uid != os.getuid():
        raise HelperIpcError("helper_token_unsafe", "Helper token file must be owned by the current user.")
    if info.st_mode & 0o077:
        raise HelperIpcError("helper_token_unsafe", "Helper token file must not be readable or writable by group/other users.")


def _unlink_existing_socket(path: Path, *, missing_ok: bool, fail_on_non_socket: bool) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    if not stat.S_ISSOCK(info.st_mode):
        if fail_on_non_socket:
            raise HelperIpcError("helper_socket_path_not_socket", "Helper socket path exists but is not a Unix socket.")
        return
    path.unlink()


def _error_response(*, request: dict[str, Any] | None, code: str, message: str) -> dict[str, Any]:
    request_id = request.get("request_id") if isinstance(request, dict) else None
    return {
        "schema_version": HELPER_IPC_SCHEMA_VERSION,
        "request_id": request_id if isinstance(request_id, str) and request_id else "unknown",
        "ok": False,
        "timestamp": timestamp_utc(),
        "data": {},
        "warnings": [],
        "errors": [
            {
                "code": code,
                "message": message,
                "guidance": "Restart the local evaOS computer-use helper and retry through the audited bridge command.",
            }
        ],
    }


def _authorize_request(
    request: dict[str, Any],
    *,
    expected_token: str,
    expected_uid: int | None,
    peer_uid: int | None,
) -> None:
    if type(expected_uid) is not int or expected_uid < 0:
        raise HelperIpcError("helper_ipc_missing_peer_policy", "Helper IPC expected peer uid is not configured.")
    supplied_token = request.get("capability_token")
    if not isinstance(supplied_token, str) or not supplied_token:
        raise HelperIpcError("helper_ipc_missing_token", "Helper IPC request is missing its capability token.")
    if not expected_token or not secrets.compare_digest(supplied_token, expected_token):
        raise HelperIpcError("helper_ipc_bad_token", "Helper IPC request has an invalid capability token.")
    if type(peer_uid) is not int or peer_uid < 0:
        raise HelperIpcError("helper_ipc_bad_peer", "Helper IPC peer uid is not authorized.")
    if peer_uid != expected_uid:
        raise HelperIpcError("helper_ipc_bad_peer", "Helper IPC peer uid is not authorized.")


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise HelperIpcError("helper_ipc_bad_payload", f"mouse_action payload requires integer {key}.")
    return value


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise HelperIpcError("helper_ipc_bad_payload", f"Helper IPC payload requires string {key}.")
    return value


def _required_ax_target(payload: dict[str, Any]) -> dict[str, Any]:
    target = payload.get("target")
    if not isinstance(target, dict):
        raise HelperIpcError("helper_ipc_bad_payload", "ax_action payload requires target object.")
    pid = target.get("pid")
    if type(pid) is not int or pid <= 0:
        raise HelperIpcError("helper_ipc_bad_payload", "ax_action target requires positive integer pid.")
    process_name = target.get("process_name")
    if not isinstance(process_name, str) or not process_name.strip() or len(process_name) > 240:
        raise HelperIpcError("helper_ipc_bad_payload", "ax_action target requires process_name from the audited snapshot.")
    path = target.get("path")
    if path is not None:
        if not isinstance(path, list):
            raise HelperIpcError("helper_ipc_bad_payload", "ax_action target path must be a list.")
        for segment in path:
            if not isinstance(segment, dict):
                raise HelperIpcError("helper_ipc_bad_payload", "ax_action target path entries must be objects.")
            role = segment.get("role")
            if not isinstance(role, str) or not role.startswith("AX") or len(role) > 80:
                raise HelperIpcError("helper_ipc_bad_payload", "ax_action target path entries require AX role strings.")
            for key in ("name", "identifier"):
                value = segment.get(key)
                if value is not None and (not isinstance(value, str) or len(value) > 240):
                    raise HelperIpcError("helper_ipc_bad_payload", f"ax_action target path {key} must be a short string when present.")
            index = segment.get("index")
            if index is not None and (type(index) is not int or index < 0):
                raise HelperIpcError("helper_ipc_bad_payload", "ax_action target path index must be a non-negative integer when present.")
    return target


def _required_ax_value(payload: dict[str, Any]) -> str:
    value = payload.get("value")
    if not isinstance(value, str) or not value:
        raise HelperIpcError("helper_ipc_bad_payload", "ax_action set_value requires a non-empty string value.")
    if len(value) > 4000:
        raise HelperIpcError("helper_ipc_bad_payload", "ax_action set_value is capped at 4000 characters.")
    return value


def _required_menu_path(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("menu_path")
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(">") if part.strip()]
    elif isinstance(raw, list):
        parts = [str(part).strip() for part in raw if isinstance(part, str) and part.strip()]
    else:
        parts = []
    if not parts or len(parts) > 8 or any(len(part) > 80 for part in parts):
        raise HelperIpcError("helper_ipc_bad_payload", "ax_action menu requires a short menu_path.")
    return parts


def _target_path_contains_role(target: dict[str, Any], role: str) -> bool:
    path = target.get("path")
    if not isinstance(path, list):
        return False
    return any(isinstance(segment, dict) and segment.get("role") == role for segment in path)
