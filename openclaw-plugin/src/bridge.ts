import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export type BridgeCommandKey =
  | "status"
  | "capabilities"
  | "latest"
  | "auditTail"
  | "queueList"
  | "queueAppend"
  | "codexFrontmost"
  | "codexWindows"
  | "codexThreads"
  | "codexContinueThread"
  | "codexSelectThread"
  | "codexSnapshot"
  | "codexInspect"
  | "codexAxTree"
  | "codexAppServerStatus"
  | "codexAppServerThreads"
  | "codexAppServerRemoteControlStatus"
  | "customerMacStatus"
  | "customerMacCapabilities"
  | "customerMacSnapshot"
  | "customerMacAxTree"
  | "customerMacAppFocus"
  | "customerMacLocalSiteOpen"
  | "customerMacLocalSiteAction"
  | "customerMacIphoneMirroringStatus"
  | "customerMacIphoneMirroringFocus"
  | "customerMacIphoneMirroringHome"
  | "customerMacIphoneMirroringAppSwitcher"
  | "customerMacIphoneMirroringSpotlight"
  | "customerMacIphoneMirroringTypeSpotlight"
  | "customerMacIphoneMirroringOpenApp"
  | "customerMacIphoneMirroringTapNamedTarget"
  | "customerMacIphoneMirroringScroll"
  | "customerMacIphoneMirroringSwipeLeft"
  | "customerMacIphoneMirroringSwipeRight"
  | "customerMacIphoneMirroringSwipeUp"
  | "customerMacIphoneMirroringSwipeDown"
  | "customerMacIphoneMirroringTypeApprovedText"
  | "customerMacIphoneMirroringSendApprovedMessage"
  | "customerMacScreenSharingStatus";

export type BridgeParams = {
  max_chars?: number;
  max_nodes?: number;
  max_items?: number;
  limit?: number;
  kind?: string;
  source_audit_id?: string;
  message?: string;
  thread_id?: string;
  title?: string;
  prompt?: string;
  dry_run?: boolean;
  app_name?: string;
  url?: string;
  action?: string;
  text?: string;
  direction?: string;
  recipient_context?: string;
  target_label?: string;
  approval_audit_id?: string;
};

const FIXED_COMMANDS: Record<
  Exclude<
    BridgeCommandKey,
    | "codexSnapshot"
    | "codexInspect"
    | "codexAxTree"
    | "auditTail"
    | "queueList"
    | "queueAppend"
    | "codexThreads"
    | "codexContinueThread"
    | "codexSelectThread"
    | "codexAppServerThreads"
    | "customerMacSnapshot"
    | "customerMacAxTree"
    | "customerMacAppFocus"
    | "customerMacLocalSiteOpen"
    | "customerMacLocalSiteAction"
    | "customerMacIphoneMirroringFocus"
    | "customerMacIphoneMirroringHome"
    | "customerMacIphoneMirroringAppSwitcher"
    | "customerMacIphoneMirroringSpotlight"
    | "customerMacIphoneMirroringTypeSpotlight"
    | "customerMacIphoneMirroringOpenApp"
    | "customerMacIphoneMirroringTapNamedTarget"
    | "customerMacIphoneMirroringScroll"
    | "customerMacIphoneMirroringSwipeLeft"
    | "customerMacIphoneMirroringSwipeRight"
    | "customerMacIphoneMirroringSwipeUp"
    | "customerMacIphoneMirroringSwipeDown"
    | "customerMacIphoneMirroringTypeApprovedText"
    | "customerMacIphoneMirroringSendApprovedMessage"
  >,
  string[]
> = {
  status: ["status", "--json"],
  capabilities: ["capabilities", "--json"],
  latest: ["latest", "--json"],
  codexFrontmost: ["codex", "frontmost", "--json"],
  codexWindows: ["codex", "windows", "--json"],
  codexAppServerStatus: ["codex", "app-server", "status", "--json"],
  codexAppServerRemoteControlStatus: ["codex", "app-server", "remote-control-status", "--json"],
  customerMacStatus: ["customer-mac", "status", "--json"],
  customerMacCapabilities: ["customer-mac", "capabilities", "--json"],
  customerMacIphoneMirroringStatus: ["customer-mac", "iphone-mirroring", "status", "--json"],
  customerMacScreenSharingStatus: ["customer-mac", "screen-sharing", "status", "--json"],
};

export function buildBridgeArgv(command: BridgeCommandKey, params: BridgeParams = {}): string[] {
  if (command in FIXED_COMMANDS) {
    return FIXED_COMMANDS[command as keyof typeof FIXED_COMMANDS];
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

function approvalArg(params: BridgeParams): string[] {
  if (typeof params.approval_audit_id !== "string" || params.approval_audit_id.trim() === "") {
    return [];
  }
  return ["--approval-audit-id", params.approval_audit_id.trim()];
}

function guardedApprovalArg(params: BridgeParams): string[] {
  if (params.dry_run !== false) {
    return [];
  }
  const argv = approvalArg(params);
  if (argv.length === 0) {
    throw new Error("approval_audit_id is required when dry_run=false");
  }
  return argv;
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} is required`);
  }
  return value;
}

export async function runBridge(command: BridgeCommandKey, params: BridgeParams = {}): Promise<unknown> {
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
  } catch (error: unknown) {
    const err = error as { stdout?: string; message?: string };
    if (err.stdout) {
      try {
        return JSON.parse(err.stdout);
      } catch {
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

async function runRemoteBridge(remoteURL: string, command: BridgeCommandKey, params: BridgeParams): Promise<unknown> {
  const endpoint = new URL("/v1/commands", remoteURL);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  const headers: Record<string, string> = {
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
    } catch {
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
  } catch (error: unknown) {
    const err = error as { message?: string };
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
  } finally {
    clearTimeout(timeout);
  }
}

function clampInt(value: unknown, fallback: number, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(value)));
}
