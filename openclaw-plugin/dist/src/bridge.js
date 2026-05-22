import { execFile } from "node:child_process";
import { promisify } from "node:util";
const execFileAsync = promisify(execFile);
const FIXED_COMMANDS = {
    status: ["status", "--json"],
    capabilities: ["capabilities", "--json"],
    latest: ["latest", "--json"],
    codexFrontmost: ["codex", "frontmost", "--json"],
    codexWindows: ["codex", "windows", "--json"],
    codexAppServerStatus: ["codex", "app-server", "status", "--json"],
    codexAppServerRemoteControlStatus: ["codex", "app-server", "remote-control-status", "--json"],
    customerMacStatus: ["customer-mac", "status", "--json"],
    customerMacCapabilities: ["customer-mac", "capabilities", "--json"],
    customerMacControlStatus: ["customer-mac", "control", "status", "--json"],
    customerMacControlStop: ["customer-mac", "control", "stop", "--json"],
    customerMacControlKillSwitch: ["customer-mac", "control", "kill-switch", "--json"],
    customerMacIphoneMirroringStatus: ["customer-mac", "iphone-mirroring", "status", "--json"],
    customerMacScreenSharingStatus: ["customer-mac", "screen-sharing", "status", "--json"],
};
export function buildBridgeArgv(command, params = {}) {
    if (command in FIXED_COMMANDS) {
        return FIXED_COMMANDS[command];
    }
    if (command === "auditTail") {
        return ["audit-tail", "--json", "--limit", String(clampInt(params.limit, 20, 1, 100))];
    }
    if (command === "queueList") {
        return ["queue", "list", "--json", "--limit", String(clampInt(params.limit, 20, 1, 100))];
    }
    if (command === "queueAppend") {
        return [
            "queue",
            "append",
            "--json",
            "--kind",
            requiredString(params.kind, "kind"),
            "--source-audit-id",
            requiredString(params.source_audit_id, "source_audit_id"),
            ...(params.message ? ["--message", String(params.message)] : []),
        ];
    }
    if (command === "codexThreads") {
        return ["codex", "threads", "--json", "--max-items", String(clampInt(params.max_items, 50, 1, 200))];
    }
    if (command === "codexSelectThread") {
        return [
            "codex",
            "select-thread",
            "--json",
            "--thread-id",
            requiredString(params.thread_id, "thread_id"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "codexContinueThread") {
        return [
            "codex",
            "continue-thread",
            "--json",
            "--title",
            requiredString(params.title, "title"),
            "--prompt",
            String(params.prompt || "continue"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "codexSnapshot") {
        return ["codex", "snapshot", "--json", "--max-chars", String(clampInt(params.max_chars, 4000, 1, 20000))];
    }
    if (command === "codexInspect") {
        return ["codex", "inspect", "--json", "--max-nodes", String(clampInt(params.max_nodes, 120, 1, 1000))];
    }
    if (command === "codexAxTree") {
        return ["codex", "ax-tree", "--json", "--max-nodes", String(clampInt(params.max_nodes, 200, 1, 1000))];
    }
    if (command === "codexAppServerThreads") {
        return ["codex", "app-server", "threads", "--json", "--max-items", String(clampInt(params.max_items, 50, 1, 200))];
    }
    if (command === "customerMacSnapshot") {
        return ["customer-mac", "snapshot", "--json", "--max-chars", String(clampInt(params.max_chars, 4000, 1, 20000))];
    }
    if (command === "customerMacAxTree") {
        return ["customer-mac", "ax-tree", "--json", "--max-nodes", String(clampInt(params.max_nodes, 200, 1, 1000))];
    }
    if (command === "customerMacControlStart") {
        return [
            "customer-mac",
            "control",
            "start",
            "--json",
            "--mode",
            String(params.mode || "full-access"),
            ...(params.agent_label ? ["--agent-label", String(params.agent_label)] : []),
        ];
    }
    if (command === "desktopSee") {
        return [
            "customer-mac",
            "desktop",
            "see",
            "--json",
            "--max-chars",
            String(clampInt(params.max_chars, 4000, 1, 20000)),
            "--max-nodes",
            String(clampInt(params.max_nodes, 200, 1, 1000)),
        ];
    }
    if (command === "desktopClick") {
        return [
            "customer-mac",
            "desktop",
            "click",
            "--json",
            ...optionalStringArg(params.target_label, "--target-label"),
            ...optionalNumberArg(params.x, "--x"),
            ...optionalNumberArg(params.y, "--y"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "desktopType") {
        return ["customer-mac", "desktop", "type", "--json", "--text", requiredString(params.text, "text"), ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "desktopScroll") {
        return [
            "customer-mac",
            "desktop",
            "scroll",
            "--json",
            "--direction",
            String(params.direction || "down"),
            "--amount",
            String(clampInt(params.amount, 600, 1, 5000)),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "desktopDrag") {
        return [
            "customer-mac",
            "desktop",
            "drag",
            "--json",
            "--from-x",
            requiredNumberString(params.from_x, "from_x"),
            "--from-y",
            requiredNumberString(params.from_y, "from_y"),
            "--to-x",
            requiredNumberString(params.to_x, "to_x"),
            "--to-y",
            requiredNumberString(params.to_y, "to_y"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "desktopHotkey") {
        return ["customer-mac", "desktop", "hotkey", "--json", "--keys", requiredString(params.keys, "keys"), ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "desktopFocusApp") {
        return ["customer-mac", "desktop", "focus-app", "--json", "--app-name", requiredString(params.app_name, "app_name"), ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "desktopWindow") {
        return ["customer-mac", "desktop", "window", "--json", "--action", requiredString(params.action, "action"), ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "desktopMenu") {
        return ["customer-mac", "desktop", "menu", "--json", "--menu-path", requiredString(params.menu_path, "menu_path"), ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "desktopBrowserAction") {
        return [
            "customer-mac",
            "desktop",
            "browser-action",
            "--json",
            "--action",
            requiredString(params.action, "action"),
            ...optionalStringArg(params.url, "--url"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "customerMacAppFocus") {
        return [
            "customer-mac",
            "app-focus",
            "--json",
            "--app-name",
            requiredString(params.app_name, "app_name"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "customerMacLocalSiteOpen") {
        return [
            "customer-mac",
            "local-site",
            "open",
            "--json",
            "--url",
            requiredString(params.url, "url"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "customerMacLocalSiteAction") {
        return [
            "customer-mac",
            "local-site",
            "action",
            "--json",
            "--action",
            requiredString(params.action, "action"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "iphoneSee") {
        return [
            "customer-mac",
            "iphone-mirroring",
            "see",
            "--json",
            "--max-chars",
            String(clampInt(params.max_chars, 4000, 1, 20000)),
            "--max-nodes",
            String(clampInt(params.max_nodes, 200, 1, 1000)),
        ];
    }
    if (command === "iphoneTap") {
        return [
            "customer-mac",
            "iphone-mirroring",
            "tap",
            "--json",
            ...optionalStringArg(params.target_label, "--target-label"),
            ...optionalNumberArg(params.x, "--x"),
            ...optionalNumberArg(params.y, "--y"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "iphoneSwipe") {
        return ["customer-mac", "iphone-mirroring", "swipe", "--json", "--direction", requiredString(params.direction, "direction"), ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "iphoneType") {
        return ["customer-mac", "iphone-mirroring", "type", "--json", "--text", requiredString(params.text, "text"), ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringFocus") {
        return ["customer-mac", "iphone-mirroring", "focus", "--json", ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringHome") {
        return ["customer-mac", "iphone-mirroring", "home", "--json", ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringAppSwitcher") {
        return ["customer-mac", "iphone-mirroring", "app-switcher", "--json", ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringSpotlight") {
        return ["customer-mac", "iphone-mirroring", "spotlight", "--json", ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringTypeSpotlight") {
        return [
            "customer-mac",
            "iphone-mirroring",
            "type-spotlight",
            "--json",
            "--text",
            requiredString(params.text, "text"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "customerMacIphoneMirroringOpenApp") {
        return [
            "customer-mac",
            "iphone-mirroring",
            "open-app",
            "--json",
            "--app-name",
            requiredString(params.app_name, "app_name"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "customerMacIphoneMirroringTapNamedTarget") {
        return [
            "customer-mac",
            "iphone-mirroring",
            "tap-named-target",
            "--json",
            "--target-label",
            requiredString(params.target_label, "target_label"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "customerMacIphoneMirroringScroll") {
        return ["customer-mac", "iphone-mirroring", "scroll", "--json", "--direction", String(params.direction || "down"), ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringSwipeLeft") {
        return ["customer-mac", "iphone-mirroring", "swipe-left", "--json", ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringSwipeRight") {
        return ["customer-mac", "iphone-mirroring", "swipe-right", "--json", ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringSwipeUp") {
        return ["customer-mac", "iphone-mirroring", "swipe-up", "--json", ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringSwipeDown") {
        return ["customer-mac", "iphone-mirroring", "swipe-down", "--json", ...(params.dry_run !== false ? ["--dry-run"] : []), ...guardedApprovalArg(params)];
    }
    if (command === "customerMacIphoneMirroringTypeApprovedText") {
        return [
            "customer-mac",
            "iphone-mirroring",
            "type-approved-text",
            "--json",
            "--text",
            requiredString(params.text, "text"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    if (command === "customerMacIphoneMirroringSendApprovedMessage") {
        return [
            "customer-mac",
            "iphone-mirroring",
            "send-approved-message",
            "--json",
            "--text",
            requiredString(params.text, "text"),
            "--recipient-context",
            requiredString(params.recipient_context, "recipient_context"),
            "--target-label",
            String(params.target_label || "Send"),
            ...(params.dry_run !== false ? ["--dry-run"] : []),
            ...guardedApprovalArg(params),
        ];
    }
    throw new Error(`Unsupported bridge command key: ${String(command)}`);
}
function approvalArg(params) {
    if (typeof params.approval_audit_id !== "string" || params.approval_audit_id.trim() === "") {
        return [];
    }
    return ["--approval-audit-id", params.approval_audit_id.trim()];
}
function guardedApprovalArg(params) {
    if (params.dry_run !== false) {
        return [];
    }
    return approvalArg(params);
}
function requiredString(value, name) {
    if (typeof value !== "string" || value.trim() === "") {
        throw new Error(`${name} is required`);
    }
    return value;
}
function requiredNumberString(value, name) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        throw new Error(`${name} is required`);
    }
    return String(Math.trunc(value));
}
function optionalNumberArg(value, flag) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return [];
    }
    return [flag, String(Math.trunc(value))];
}
function optionalStringArg(value, flag) {
    if (typeof value !== "string" || value.trim() === "") {
        return [];
    }
    return [flag, value.trim()];
}
export async function runBridge(command, params = {}) {
    if (command === "customerMacCompletePairing") {
        return runEnrollmentBridge(params);
    }
    const remoteURL = process.env.EVAOS_DESKTOP_BRIDGE_URL;
    if (remoteURL) {
        return runRemoteBridge(remoteURL, command, params);
    }
    const bin = process.env.EVAOS_DESKTOP_BRIDGE_BIN || "evaos-desktop-bridge";
    const argv = buildBridgeArgv(command, params);
    try {
        const { stdout } = await execFileAsync(bin, argv, {
            shell: false,
            timeout: 10000,
            maxBuffer: 1024 * 1024,
        });
        return JSON.parse(stdout);
    }
    catch (error) {
        const err = error;
        if (err.stdout) {
            try {
                return JSON.parse(err.stdout);
            }
            catch {
                // Fall through to structured wrapper below.
            }
        }
        return {
            ok: false,
            errors: [
                {
                    code: "bridge_cli_failed",
                    message: err.message || "evaos-desktop-bridge command failed",
                    guidance: "Install evaos-desktop-bridge locally and set EVAOS_DESKTOP_BRIDGE_BIN if it is not on PATH.",
                },
            ],
        };
    }
}
async function runEnrollmentBridge(params) {
    const connectorURLString = requiredEnrollmentString(params.connector_url, "connector_url");
    const enrollmentCode = requiredEnrollmentString(params.enrollment_code, "enrollment_code");
    if (!connectorURLString.ok) {
        return connectorURLString.error;
    }
    if (!enrollmentCode.ok) {
        return enrollmentCode.error;
    }
    const connectorURLResult = validateEnrollmentConnectorURL(connectorURLString.value);
    if (!connectorURLResult.ok) {
        return connectorURLResult.error;
    }
    const body = {
        enrollment_code: enrollmentCode.value,
    };
    if (typeof params.customer_id === "string" && params.customer_id.trim() !== "") {
        body.customer_id = params.customer_id.trim();
    }
    if (typeof params.device_name === "string" && params.device_name.trim() !== "") {
        body.device_name = params.device_name.trim();
    }
    const connectorURL = connectorURLResult.url;
    const endpoint = new URL("/v1/enrollment/complete", connectorURL);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            body: JSON.stringify(body),
            signal: controller.signal,
        });
        const text = await response.text();
        try {
            return redactConnectorSecrets(JSON.parse(text));
        }
        catch {
            return {
                ok: false,
                errors: [
                    {
                        code: "bridge_connector_invalid_response",
                        message: text || `Connector returned HTTP ${response.status}`,
                        guidance: "Check the Mac connector enrollment endpoint.",
                    },
                ],
            };
        }
    }
    catch (error) {
        const err = error;
        return {
            ok: false,
            errors: [
                {
                    code: "bridge_connector_failed",
                    message: err.message || "evaos-desktop-bridge enrollment request failed",
                    guidance: "Verify the connector URL, secure network reachability, and enrollment code.",
                },
            ],
        };
    }
    finally {
        clearTimeout(timeout);
    }
}
async function runRemoteBridge(remoteURL, command, params) {
    const endpoint = new URL("/v1/commands", remoteURL);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    const headers = {
        "Content-Type": "application/json",
    };
    const token = process.env.EVAOS_DESKTOP_BRIDGE_TOKEN;
    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }
    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers,
            body: JSON.stringify({ command, params }),
            signal: controller.signal,
        });
        const text = await response.text();
        try {
            return JSON.parse(text);
        }
        catch {
            return {
                ok: false,
                errors: [
                    {
                        code: "bridge_connector_invalid_response",
                        message: text || `Connector returned HTTP ${response.status}`,
                        guidance: "Check the paired Mac connector endpoint and token.",
                    },
                ],
            };
        }
    }
    catch (error) {
        const err = error;
        return {
            ok: false,
            errors: [
                {
                    code: "bridge_connector_failed",
                    message: err.message || "evaos-desktop-bridge connector request failed",
                    guidance: "Verify Headscale reachability, EVAOS_DESKTOP_BRIDGE_URL, and EVAOS_DESKTOP_BRIDGE_TOKEN.",
                },
            ],
        };
    }
    finally {
        clearTimeout(timeout);
    }
}
function validateEnrollmentConnectorURL(rawURL) {
    let parsed;
    try {
        parsed = new URL(rawURL);
    }
    catch {
        return forbiddenConnectorURL("connector_url must be a valid URL.");
    }
    if (parsed.protocol !== "http:") {
        return forbiddenConnectorURL("connector_url must use http.");
    }
    if (parsed.port !== "8765") {
        return forbiddenConnectorURL("connector_url must use port 8765.");
    }
    if (parsed.pathname !== "/" || parsed.search !== "" || parsed.hash !== "") {
        return forbiddenConnectorURL("connector_url must be a base connector URL without a path, query, or fragment.");
    }
    if (parsed.username !== "" || parsed.password !== "") {
        return forbiddenConnectorURL("connector_url must not include credentials.");
    }
    if (!isAllowedEnrollmentHost(parsed.hostname)) {
        return forbiddenConnectorURL("connector_url host must be a private tailnet address or local .local hostname.");
    }
    parsed.pathname = "/";
    return { ok: true, url: parsed };
}
function forbiddenConnectorURL(message) {
    return {
        ok: false,
        error: {
            ok: false,
            errors: [
                {
                    code: "bridge_connector_url_forbidden",
                    message,
                    guidance: "Use the customer Mac Headscale/private connector URL, for example http://100.64.x.y:8765.",
                },
            ],
        },
    };
}
function requiredEnrollmentString(value, name) {
    if (typeof value !== "string" || value.trim() === "") {
        return {
            ok: false,
            error: {
                ok: false,
                errors: [
                    {
                        code: "bridge_enrollment_missing_field",
                        message: `${name} is required`,
                        guidance: "Use the pairing prompt from Workbench and pass the connector_url plus enrollment_code exactly.",
                    },
                ],
            },
        };
    }
    return { ok: true, value: value.trim() };
}
function isAllowedEnrollmentHost(hostname) {
    const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");
    if (host === "localhost" || host.endsWith(".localhost") || host === "::1") {
        return false;
    }
    if (host.endsWith(".local") && host !== "localhost.local") {
        return true;
    }
    const octets = host.split(".").map((part) => Number(part));
    if (octets.length !== 4 || octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
        return false;
    }
    const [a, b] = octets;
    if (a === 127 || a === 0) {
        return false;
    }
    return a === 10 || (a === 100 && b >= 64 && b <= 127) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}
function redactConnectorSecrets(value) {
    if (Array.isArray(value)) {
        return value.map((item) => redactConnectorSecrets(item));
    }
    if (!value || typeof value !== "object") {
        return value;
    }
    const redacted = {};
    for (const [key, nestedValue] of Object.entries(value)) {
        const normalizedKey = key.toLowerCase();
        if (normalizedKey === "token" || normalizedKey.endsWith("_" + "token")) {
            redacted[key] = "[redacted]";
        }
        else {
            redacted[key] = redactConnectorSecrets(nestedValue);
        }
    }
    return redacted;
}
function clampInt(value, fallback, min, max) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return fallback;
    }
    return Math.min(max, Math.max(min, Math.trunc(value)));
}
