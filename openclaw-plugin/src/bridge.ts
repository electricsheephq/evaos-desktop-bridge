import { execFile } from "node:child_process";
import { createHmac, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile) as (
  file: string,
  args: string[],
  options: Record<string, unknown>,
) => Promise<{ stdout: string }>;
const fsCompat = fs as unknown as {
  mkdtempSync: (prefix: string) => string;
  chmodSync: (path: string, mode: number) => void;
  rmSync: (path: string, options: { recursive: boolean; force: boolean }) => void;
};

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
  | "codexThreadMap"
  | "codexSendVisibleMessage"
  | "codexContinueThread"
  | "codexSelectThread"
  | "codexSnapshot"
  | "codexInspect"
  | "codexAxTree"
  | "codexConnectionsStatus"
  | "codexAppServerStatus"
  | "codexAppServerThreads"
  | "codexAppServerLoadedThreads"
  | "codexLiveStatus"
  | "codexAppServerRemoteControlStatus"
  | "evaosProviderProfiles"
  | "evaosProviderActiveProfile"
  | "evaosProviderCompleteAuth"
  | "evaosSharedBrowserGuidance"
  | "customerMacStatus"
  | "customerMacCompletePairing"
  | "customerMacCapabilities"
  | "customerMacControlStatus"
  | "customerMacControlStart"
  | "customerMacControlStop"
  | "customerMacControlKillSwitch"
  | "desktopSee"
  | "desktopClick"
  | "desktopType"
  | "desktopSetValue"
  | "desktopScroll"
  | "desktopDrag"
  | "desktopHotkey"
  | "desktopFocusApp"
  | "desktopWindow"
  | "desktopMenu"
  | "desktopBrowserAction"
  | "customerMacSnapshot"
  | "customerMacAxTree"
  | "customerMacAppFocus"
  | "customerMacLocalSiteOpen"
  | "customerMacLocalSiteAction"
  | "customerMacIphoneMirroringStatus"
  | "iphoneSee"
  | "iphoneTap"
  | "iphoneSwipe"
  | "iphoneType"
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
  message_file?: string;
  value_file?: string;
  thread_id?: string;
  turn_id?: string;
  title?: string;
  prompt?: string;
  dry_run?: boolean;
  confirm?: boolean;
  duration_ms?: number;
  wait_ms?: number;
  poll_interval_ms?: number;
  app_name?: string;
  url?: string;
  action?: string;
  text?: string;
  value?: string;
  attribute?: string;
  direction?: string;
  recipient_context?: string;
  target_label?: string;
  snapshot_id?: string;
  element_id?: string;
  approval_audit_id?: string;
  connector_url?: string;
  enrollment_code?: string;
  customer_id?: string;
  device_name?: string;
  mode?: string;
  agent_label?: string;
  x?: number;
  y?: number;
  from_x?: number;
  from_y?: number;
  to_x?: number;
  to_y?: number;
  amount?: number;
  keys?: string;
  menu_path?: string;
  identity?: string;
  scopes?: string[];
  expires_at?: string;
  server_secret_ref?: string;
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
    | "codexThreadMap"
    | "codexSendVisibleMessage"
    | "codexContinueThread"
    | "codexSelectThread"
    | "codexAppServerThreads"
    | "codexAppServerLoadedThreads"
    | "codexLiveStatus"
    | "evaosProviderProfiles"
    | "evaosProviderActiveProfile"
    | "evaosProviderCompleteAuth"
    | "evaosSharedBrowserGuidance"
    | "customerMacSnapshot"
    | "customerMacCompletePairing"
    | "customerMacControlStart"
    | "desktopSee"
    | "desktopClick"
    | "desktopType"
    | "desktopSetValue"
    | "desktopScroll"
    | "desktopDrag"
    | "desktopHotkey"
    | "desktopFocusApp"
    | "desktopWindow"
    | "desktopMenu"
    | "desktopBrowserAction"
    | "customerMacAxTree"
    | "customerMacAppFocus"
    | "customerMacLocalSiteOpen"
    | "customerMacLocalSiteAction"
    | "iphoneSee"
    | "iphoneTap"
    | "iphoneSwipe"
    | "iphoneType"
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
  codexConnectionsStatus: ["codex", "connections", "status", "--json"],
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
  if (command === "codexThreadMap") {
    return ["codex", "thread-map", "--json", "--max-items", String(clampInt(params.max_items, 50, 1, 200))];
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
  if (command === "codexSendVisibleMessage") {
    const messageFile = typeof params.message_file === "string" && params.message_file.trim() !== ""
      ? params.message_file.trim()
      : undefined;
    return [
      "codex",
      "send-visible-message",
      "--json",
      "--thread-id",
      requiredString(params.thread_id, "thread_id"),
      ...(messageFile ? ["--message-file", messageFile] : ["--message", requiredString(params.message, "message")]),
      ...(params.dry_run !== false ? ["--dry-run"] : ["--live"]),
      ...(params.confirm === true ? ["--confirm"] : []),
      ...guardedApprovalArg(params),
      ...(params.wait_ms !== undefined ? ["--wait-ms", String(clampInt(params.wait_ms, 0, 0, 120000))] : []),
      ...(params.poll_interval_ms !== undefined ? ["--poll-interval-ms", String(clampInt(params.poll_interval_ms, 2000, 250, 10000))] : []),
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
  if (command === "codexAppServerLoadedThreads") {
    return ["codex", "app-server", "loaded-threads", "--json", "--max-items", String(clampInt(params.max_items, 50, 1, 200))];
  }
  if (command === "codexLiveStatus") {
    return [
      "codex",
      "app-server",
      "subscribe",
      "--json",
      "--thread-id",
      requiredString(params.thread_id, "thread_id"),
      "--duration-ms",
      String(clampInt(params.duration_ms, 1000, 1, 30000)),
    ];
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
      ...optionalStringArg(params.snapshot_id, "--snapshot-id"),
      ...optionalStringArg(params.element_id, "--element-id"),
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
  if (command === "desktopSetValue") {
    const valueFile = typeof params.value_file === "string" && params.value_file.trim() !== ""
      ? params.value_file.trim()
      : undefined;
    if (!valueFile) {
      throw new Error("desktopSetValue value must be materialized before building CLI argv.");
    }
    return [
      "customer-mac",
      "desktop",
      "set-value",
      "--json",
      "--snapshot-id",
      requiredString(params.snapshot_id, "snapshot_id"),
      "--element-id",
      requiredString(params.element_id, "element_id"),
      "--value-file",
      valueFile,
      "--attribute",
      String(params.attribute || "value"),
      ...(params.dry_run !== false ? ["--dry-run"] : []),
      ...guardedApprovalArg(params),
    ];
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
      ...optionalStringArg(params.snapshot_id, "--snapshot-id"),
      ...optionalStringArg(params.element_id, "--element-id"),
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
  return approvalArg(params);
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} is required`);
  }
  return value;
}

function requiredNumberString(value: unknown, name: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} is required`);
  }
  return String(Math.trunc(value));
}

function optionalNumberArg(value: unknown, flag: string): string[] {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return [];
  }
  return [flag, String(Math.trunc(value))];
}

function optionalStringArg(value: unknown, flag: string): string[] {
  if (typeof value !== "string" || value.trim() === "") {
    return [];
  }
  return [flag, value.trim()];
}

export async function runBridge(command: BridgeCommandKey, params: BridgeParams = {}): Promise<unknown> {
  if (command === "evaosProviderProfiles") {
    return await providerProfilesPayload();
  }
  if (command === "evaosProviderActiveProfile") {
    return await providerActiveProfilePayload();
  }
  if (command === "evaosProviderCompleteAuth") {
    return await providerCompleteAuthPayload(params);
  }
  if (command === "evaosSharedBrowserGuidance") {
    return sharedBrowserGuidancePayload();
  }
  if (command === "customerMacCompletePairing") {
    return runEnrollmentBridge(params);
  }

  const remoteURL = process.env.EVAOS_DESKTOP_BRIDGE_URL;
  if (remoteURL) {
    return runRemoteBridge(remoteURL, command, params);
  }

  return withLocalMessagePayload(command, params, async (safeParams) => {
    const bin = process.env.EVAOS_DESKTOP_BRIDGE_BIN || "evaos-desktop-bridge";
    const argv = buildBridgeArgv(command, safeParams);
    try {
      const { stdout } = await execFileAsync(bin, argv, {
        shell: false,
        timeout: timeoutForCommand(command),
        maxBuffer: 8 * 1024 * 1024,
      });
      return materializeVisualEvidence(command, JSON.parse(stdout));
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
            message: safeBridgeErrorMessage(command, err.message),
            guidance: "Install evaos-desktop-bridge locally and set EVAOS_DESKTOP_BRIDGE_BIN if it is not on PATH.",
          },
        ],
      };
    }
  });
}

async function withLocalMessagePayload<T>(
  command: BridgeCommandKey,
  params: BridgeParams,
  callback: (params: BridgeParams) => Promise<T>,
): Promise<T> {
  const isCodexMessage = command === "codexSendVisibleMessage" && typeof params.message === "string";
  const isDesktopSetValue = command === "desktopSetValue" && typeof params.value === "string";
  if (!isCodexMessage && !isDesktopSetValue) {
    return callback(params);
  }
  const dir = fsCompat.mkdtempSync(path.join(process.env.TMPDIR || "/tmp", isCodexMessage ? "evaos-codex-visible-message-" : "evaos-desktop-set-value-"));
  const payloadFile = path.join(dir, isCodexMessage ? "message.txt" : "value.txt");
  try {
    await writeFile(payloadFile, isCodexMessage ? String(params.message) : String(params.value), { encoding: "utf8", mode: 0o600 });
    try {
      fsCompat.chmodSync(payloadFile, 0o600);
    } catch {
      // Best-effort on platforms that do not support chmod.
    }
    const safeParams = isCodexMessage
      ? { ...params, message: undefined, message_file: payloadFile }
      : { ...params, value: undefined, value_file: payloadFile };
    return await callback(safeParams);
  } finally {
    try {
      fsCompat.rmSync(dir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup; the file is 0600 and contains only the approved message.
    }
  }
}

function safeBridgeErrorMessage(command: BridgeCommandKey, message?: string): string {
  if (command === "codexSendVisibleMessage") {
    return "evaos-desktop-bridge guarded Codex visible message command failed";
  }
  return message || "evaos-desktop-bridge command failed";
}

async function providerProfilesPayload(): Promise<unknown> {
  const brokerProfile = await providerAgentDiscoveryPayload("openclaw");
  if (brokerProfile) {
    return brokerProfile.profilesPayload;
  }

  const profilesPayload = readJSONEnv("EVAOS_PROVIDER_PROFILES_JSON");
  const providerProfiles = Array.isArray(profilesPayload)
    ? profilesPayload
    : isRecord(profilesPayload) && Array.isArray(profilesPayload.provider_profiles)
      ? profilesPayload.provider_profiles
      : [];
  const grantsPayload = readJSONEnv("EVAOS_PROVIDER_GRANTS_JSON");
  return redactConnectorSecrets({
    ok: true,
    data: {
      customer_id: process.env.EVAOS_CUSTOMER_ID || null,
      provider_profiles: providerProfiles,
      provider_grants: grantsPayload || null,
      active_provider_key:
        process.env.EVAOS_ACTIVE_PROVIDER_KEY ||
        (isRecord(profilesPayload) && typeof profilesPayload.active_provider_key === "string" ? profilesPayload.active_provider_key : null),
      raw_secrets_available: false,
      raw_secrets_stored_in_workbench: false,
    },
    warnings: providerProfiles.length === 0 ? ["Provider profiles are not configured on this VM yet."] : [],
  });
}

async function providerCompleteAuthPayload(params: BridgeParams): Promise<unknown> {
  const endpoint = providerDiscoveryEndpoint();
  const customerID = process.env.EVAOS_CUSTOMER_ID?.trim();
  const proofSecret = process.env.EVAOS_PROVIDER_AUTH_PROOF_SECRET?.trim() || process.env.EVAOS_PROVIDER_PROOF_SECRET?.trim();
  const identity = requiredProviderIdentity(params.identity);
  const scopes = normalizeProviderScopes(params.scopes);
  const expiresAt = normalizeProviderProofExpiry(params.expires_at);
  const serverSecretRef = normalizeServerSecretRef(params.server_secret_ref, customerID);

  if (!endpoint || !customerID || !proofSecret || !identity || !serverSecretRef) {
    return {
      ok: false,
      errors: [
        {
          code: "provider_auth_proof_not_configured",
          message: "Provider auth proof completion requires broker endpoint, customer id, proof secret, identity, and server secret reference.",
          guidance:
            "Set EVAOS_PROVIDER_DISCOVERY_URL, EVAOS_CUSTOMER_ID, EVAOS_PROVIDER_AUTH_PROOF_SECRET, EVAOS_PROVIDER_AUTH_IDENTITY, and EVAOS_PROVIDER_SERVER_SECRET_REF on the VM.",
        },
      ],
    };
  }

  const providerKey = "openai_codex";
  const proofID = providerProofID();
  const proofPayload = {
    customer_id: customerID,
    provider_key: providerKey,
    purpose: "provider_auth_complete",
    agent_runtime: "openclaw",
    proof_id: proofID,
    identity,
    scopes,
    expires_at: expiresAt,
    server_secret_ref: serverSecretRef,
  };
  const signature = createHmac("sha256", proofSecret)
    .update(JSON.stringify(proofPayload))
    .digest("hex");
  const requestBody = {
    action: "provider_auth_complete",
    customer_id: customerID,
    provider_key: providerKey,
    agent_runtime: "openclaw",
    provider_auth_proof: {
      purpose: "provider_auth_complete",
      agent_runtime: "openclaw",
      proof_id: proofID,
      identity,
      scopes,
      expires_at: expiresAt,
      server_secret_ref: serverSecretRef,
      signature,
    },
  };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Evaos-Provider-Proof": "signed-v1",
      },
      body: JSON.stringify(requestBody),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      return {
        ok: false,
        errors: [
          {
            code: "provider_auth_complete_failed",
            message: isRecord(payload) && typeof payload.error === "string" ? payload.error : `Provider auth completion failed with HTTP ${response.status}.`,
          },
        ],
      };
    }
    const cachedGrant = await cacheProviderGrantFromBroker("openclaw", providerKey, payload);
    return redactConnectorSecrets({
      ok: true,
      data: {
        connected: isRecord(payload) ? payload.connected === true || payload.status === "connected" : true,
        provider_key: providerKey,
        grant_cached: cachedGrant,
        response: payload,
        raw_provider_token_returned: false,
      },
    });
  } catch (error: unknown) {
    return {
      ok: false,
      errors: [
        {
          code: "provider_auth_complete_unreachable",
          message: error instanceof Error ? error.message : "Provider auth completion broker was unreachable.",
        },
      ],
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function providerActiveProfilePayload(): Promise<unknown> {
  const brokerProfile = await providerAgentDiscoveryPayload("openclaw");
  if (brokerProfile) {
    return brokerProfile.activePayload;
  }

  const profiles = await providerProfilesPayload() as Record<string, unknown>;
  const data = isRecord(profiles.data) ? profiles.data : {};
  const providerProfiles = Array.isArray(data.provider_profiles) ? data.provider_profiles : [];
  const activeProviderKey = typeof data.active_provider_key === "string" ? data.active_provider_key : null;
  const activeProfile = providerProfiles.find((profile) => isRecord(profile) && profile.provider_key === activeProviderKey) ?? null;
  const providerGrants = isRecord(data.provider_grants) ? data.provider_grants : {};
  const openClawGrant = isRecord(providerGrants.openclaw) ? providerGrants.openclaw : null;
  const hasConnectionProof =
    isRecord(activeProfile) &&
    activeProfile.status === "connected" &&
    typeof activeProfile.last_validated_at === "string" &&
    Boolean(openClawGrant && typeof openClawGrant.grant_handle === "string");
  return redactConnectorSecrets({
    ok: true,
    data: {
      customer_id: process.env.EVAOS_CUSTOMER_ID || null,
      active_provider_key: activeProviderKey,
      active_profile: activeProfile,
      needs_reauth: !hasConnectionProof,
      raw_secrets_available: false,
    },
    warnings: hasConnectionProof ? [] : ["No verified active provider grant is available. Ask the customer to connect or re-auth the provider in evaOS Workbench."],
  });
}

function requiredProviderIdentity(value: unknown): string | null {
  const fromParam = typeof value === "string" ? value.trim() : "";
  if (fromParam) return fromParam;
  const fromEnv = process.env.EVAOS_PROVIDER_AUTH_IDENTITY?.trim() || process.env.EVAOS_PROVIDER_IDENTITY?.trim() || "";
  return fromEnv || null;
}

function normalizeProviderScopes(value: unknown): string[] {
  const scopes = Array.isArray(value)
    ? value.map((scope) => String(scope).trim()).filter(Boolean)
    : [];
  if (scopes.length > 0) return [...new Set(scopes)];
  const fromEnv = process.env.EVAOS_PROVIDER_AUTH_SCOPES?.split(",").map((scope) => scope.trim()).filter(Boolean) ?? [];
  return fromEnv.length > 0 ? [...new Set(fromEnv)] : ["codex", "offline_access"];
}

function normalizeProviderProofExpiry(value: unknown): string {
  const candidate = typeof value === "string" ? value.trim() : process.env.EVAOS_PROVIDER_AUTH_EXPIRES_AT?.trim() || "";
  if (candidate && Number.isFinite(Date.parse(candidate)) && Date.parse(candidate) > Date.now()) {
    return new Date(candidate).toISOString();
  }
  return new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
}

function normalizeServerSecretRef(value: unknown, customerID: string | undefined): string | null {
  const candidate = typeof value === "string" ? value.trim() : process.env.EVAOS_PROVIDER_SERVER_SECRET_REF?.trim() || "";
  if (candidate.startsWith("provider://")) return candidate;
  if (!customerID) return null;
  return `provider://openai_codex/${encodeURIComponent(customerID)}/openclaw`;
}

function providerProofID(): string {
  return `eap_${randomUUID().replace(/-/g, "")}`;
}

type ProviderDiscoveryPayload = {
  profilesPayload: unknown;
  activePayload: unknown;
};

async function providerAgentDiscoveryPayload(agentRuntime: "openclaw" | "hermes"): Promise<ProviderDiscoveryPayload | null> {
  const endpoint = providerDiscoveryEndpoint();
  const customerID = process.env.EVAOS_CUSTOMER_ID?.trim();
  const grantHandle = providerGrantHandleFor(agentRuntime);
  if (!endpoint || !customerID || !grantHandle) {
    return null;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Evaos-Provider-Grant": grantHandle,
      },
      body: JSON.stringify({
        action: "provider_agent_discovery",
        customer_id: customerID,
        agent_runtime: agentRuntime,
      }),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || !isRecord(payload)) {
      return null;
    }
    const activeProfile = isRecord(payload.provider_profile) ? payload.provider_profile : null;
    const activeProviderKey = typeof payload.active_provider_key === "string" ? payload.active_provider_key : null;
    const providerProfiles = activeProfile ? [activeProfile] : [];
    const grantStatus = typeof payload.grant_status === "string" ? payload.grant_status : "unknown";
    const grantExpiresAt = typeof payload.grant_expires_at === "string" ? payload.grant_expires_at : null;

    return {
      profilesPayload: redactConnectorSecrets({
        ok: true,
        data: {
          customer_id: customerID,
          provider_profiles: providerProfiles,
          provider_grants: {
            [agentRuntime]: {
              grant_handle: grantHandle,
              status: grantStatus,
              expires_at: grantExpiresAt,
            },
          },
          active_provider_key: activeProviderKey,
          raw_secrets_available: false,
          raw_secrets_stored_in_workbench: false,
          raw_provider_token_returned: false,
          source: "broker",
        },
        warnings: providerProfiles.length === 0 ? ["No active provider profile is available from the broker."] : [],
      }),
      activePayload: redactConnectorSecrets({
        ok: true,
        data: {
          customer_id: customerID,
          active_provider_key: activeProviderKey,
          active_profile: activeProfile,
          provider_identity: typeof payload.provider_identity === "string" ? payload.provider_identity : null,
          provider_scopes: Array.isArray(payload.provider_scopes) ? payload.provider_scopes.map(String) : [],
          grant_status: grantStatus,
          grant_expires_at: grantExpiresAt,
          needs_reauth: payload.reauth_needed === true || !activeProfile,
          raw_secrets_available: false,
          raw_provider_token_returned: false,
          source: "broker",
        },
        warnings: activeProfile ? [] : ["No verified active provider grant is available. Ask the customer to connect or re-auth the provider in evaOS Workbench."],
      }),
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function providerDiscoveryEndpoint(): string | null {
  const explicit = process.env.EVAOS_PROVIDER_DISCOVERY_URL?.trim();
  if (explicit) return explicit;
  const broker = process.env.EVAOS_DESKTOP_RUNTIME_SESSION_URL?.trim();
  if (broker) return broker;
  return null;
}

function providerGrantHandleFor(agentRuntime: "openclaw" | "hermes"): string | null {
  const direct = process.env.EVAOS_PROVIDER_GRANT_HANDLE?.trim();
  if (direct) return direct;
  const grantsPayload = readJSONEnv("EVAOS_PROVIDER_GRANTS_JSON");
  const runtimeGrant = isRecord(grantsPayload) ? grantsPayload[agentRuntime] : null;
  if (isRecord(runtimeGrant) && typeof runtimeGrant.grant_handle === "string" && runtimeGrant.grant_handle.trim() !== "") {
    return runtimeGrant.grant_handle.trim();
  }
  const cachePayload = readProviderGrantCache();
  const cachedRuntimeGrant = isRecord(cachePayload) ? cachePayload[agentRuntime] : null;
  if (isRecord(cachedRuntimeGrant) && typeof cachedRuntimeGrant.grant_handle === "string" && cachedRuntimeGrant.grant_handle.trim() !== "") {
    return cachedRuntimeGrant.grant_handle.trim();
  }
  return null;
}

async function cacheProviderGrantFromBroker(agentRuntime: "openclaw" | "hermes", providerKey: string, payload: unknown): Promise<boolean> {
  if (!isRecord(payload) || !isRecord(payload.agent_grant)) return false;
  const grant = payload.agent_grant;
  if (grant.provider_key !== providerKey || grant.agent_runtime !== agentRuntime || typeof grant.grant_handle !== "string" || !grant.grant_handle.trim()) {
    return false;
  }
  const cachePath = providerGrantCachePath();
  if (!cachePath) return false;
  const existing = isRecord(readProviderGrantCache()) ? readProviderGrantCache() as Record<string, unknown> : {};
  const next = {
    ...existing,
    [agentRuntime]: {
      provider_key: providerKey,
      agent_runtime: agentRuntime,
      grant_handle: grant.grant_handle.trim(),
      expires_at: typeof grant.expires_at === "string" ? grant.expires_at : null,
      cached_at: new Date().toISOString(),
    },
  };
  try {
    await mkdir(path.dirname(cachePath), { recursive: true });
    await writeFile(cachePath, JSON.stringify(next, null, 2), { encoding: "utf8", mode: 0o600 });
    return true;
  } catch {
    return false;
  }
}

function readProviderGrantCache(): unknown {
  const cachePath = providerGrantCachePath();
  if (!cachePath) return null;
  try {
    return JSON.parse(fs.readFileSync(cachePath, "utf8"));
  } catch {
    return null;
  }
}

function providerGrantCachePath(): string | null {
  const explicit = process.env.EVAOS_PROVIDER_GRANT_CACHE_FILE?.trim();
  if (explicit) return explicit;
  const home = process.env.HOME?.trim();
  if (!home) return null;
  return path.join(home, ".openclaw", "evaos-provider-grants.json");
}

function sharedBrowserGuidancePayload(): unknown {
  const status = readJSONEnv("EVAOS_SHARED_BROWSER_STATUS_JSON");
  return redactConnectorSecrets({
    ok: true,
    data: {
      schema_version: "evaos.browser_status.v1",
      customer_id: process.env.EVAOS_CUSTOMER_ID || null,
      business_browser_preferred_for_cloud_web_tasks: true,
      shared_browser_preferred_for_cloud_web_tasks: true,
      instructions:
        "Use Business Browser for cloud web tasks that need a persistent VM browser, user auth/CAPTCHA handoff, or human-visible browsing state. Use local Mac browser tools only when the task explicitly needs the customer's Mac browser.",
      status: status || null,
    },
    warnings: status ? [] : ["Business Browser live status is not configured in this VM environment yet."],
  });
}

function readJSONEnv(name: string): unknown {
  const raw = process.env[name];
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function runEnrollmentBridge(params: BridgeParams): Promise<unknown> {
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

  const body: Record<string, string> = {
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
    } catch {
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
  } catch (error: unknown) {
    const err = error as { message?: string };
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
  } finally {
    clearTimeout(timeout);
  }
}

async function runRemoteBridge(remoteURL: string, command: BridgeCommandKey, params: BridgeParams): Promise<unknown> {
  const endpoint = new URL("/v1/commands", remoteURL);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutForCommand(command));
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
      return await materializeVisualEvidence(command, JSON.parse(text), remoteURL, headers.Authorization);
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

function timeoutForCommand(command: BridgeCommandKey): number {
  if (command === "codexLiveStatus") {
    return 35_000;
  }
  if (command === "desktopSee" || command === "iphoneSee" || command === "customerMacSnapshot" || command === "customerMacAxTree") {
    return 60_000;
  }
  if (
    command === "desktopDrag" ||
    command === "desktopScroll" ||
    command === "iphoneSwipe" ||
    command === "customerMacIphoneMirroringScroll" ||
    command === "customerMacIphoneMirroringSwipeLeft" ||
    command === "customerMacIphoneMirroringSwipeRight" ||
    command === "customerMacIphoneMirroringSwipeUp" ||
    command === "customerMacIphoneMirroringSwipeDown"
  ) {
    return 20_000;
  }
  if (
    command === "desktopMenu" ||
    command === "desktopWindow" ||
    command === "desktopBrowserAction" ||
    command === "desktopFocusApp" ||
    command === "customerMacIphoneMirroringOpenApp"
  ) {
    return 20_000;
  }
  if (
    command === "desktopClick" ||
    command === "iphoneTap"
  ) {
    return 30_000;
  }
  if (
    command === "desktopSetValue" ||
    command === "desktopType" ||
    command === "desktopHotkey" ||
    command === "iphoneType" ||
    command === "customerMacIphoneMirroringTypeApprovedText" ||
    command === "customerMacIphoneMirroringSendApprovedMessage"
  ) {
    return 15_000;
  }
  return 10_000;
}

async function materializeVisualEvidence(
  command: BridgeCommandKey,
  payload: unknown,
  remoteURL?: string,
  authHeader?: string,
): Promise<unknown> {
  if (!isRecord(payload)) {
    return payload;
  }
  const data = payload.data;
  if (!isRecord(data)) {
    return payload;
  }
  const image = findVisualImage(data);
  if (!image) {
    return payload;
  }
  let imageBytes: unknown;
  let materializedFrom = "inline";
  if (typeof image.bytes_base64 === "string") {
    imageBytes = Buffer.from(image.bytes_base64, "base64");
  } else if (typeof image.artifact_url === "string" && remoteURL) {
    const fetched = await fetchVisualArtifact(remoteURL, image.artifact_url, authHeader);
    if (!fetched.ok) {
      const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
      warnings.push(fetched.warning);
      payload.warnings = warnings;
      return payload;
    }
    imageBytes = fetched.bytes;
    materializedFrom = "connector_artifact";
  } else {
    return payload;
  }
  const snapshotId =
    (typeof data.snapshot_id === "string" && data.snapshot_id) ||
    (isRecord(data.screenshot) && typeof data.screenshot.snapshot_id === "string" && data.screenshot.snapshot_id) ||
    (typeof image.artifact_id === "string" && image.artifact_id) ||
    (typeof payload.audit_id === "string" && payload.audit_id) ||
    command;
  const artifactDir = process.env.EVAOS_DESKTOP_BRIDGE_ARTIFACT_DIR || "/root/agent-files/downloads/desktop-bridge";
  const safeName = snapshotId.replace(/[^A-Za-z0-9_.-]+/g, "-").slice(0, 160);
  const artifactPath = path.join(artifactDir, `${safeName}.png`);
  try {
    await mkdir(artifactDir, { recursive: true });
    await writeFile(artifactPath, imageBytes);
    image.vm_artifact_path = artifactPath;
    image.bytes_base64_present = true;
    image.vm_artifact_source = materializedFrom;
    delete image.bytes_base64;
    data.vm_visual_artifact_path = artifactPath;
  } catch (error: unknown) {
    const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
    warnings.push(`Unable to write VM visual artifact: ${(error as { message?: string }).message || "unknown error"}`);
    payload.warnings = warnings;
  }
  return payload;
}

function findVisualImage(data: Record<string, unknown>): Record<string, unknown> | undefined {
  const direct = data.image;
  if (isRecord(direct) && hasImageMaterial(direct)) {
    return direct;
  }
  const screenshot = data.screenshot;
  if (isRecord(screenshot)) {
    const screenshotRecord: Record<string, unknown> = screenshot;
    if (hasImageMaterial(screenshotRecord)) {
      return screenshotRecord;
    }
    const screenshotImage = screenshotRecord.screenshot;
    if (isRecord(screenshotImage) && hasImageMaterial(screenshotImage)) {
      return screenshotImage;
    }
    const image = screenshotRecord.image;
    if (isRecord(image) && hasImageMaterial(image)) {
      return image;
    }
  }
  return undefined;
}

function hasImageMaterial(value: Record<string, unknown>): boolean {
  return typeof value.bytes_base64 === "string" || typeof value.artifact_url === "string";
}

async function fetchVisualArtifact(
  remoteURL: string,
  artifactURL: string,
  authHeader?: string,
): Promise<{ ok: true; bytes: unknown } | { ok: false; warning: string }> {
  let endpoint: URL;
  try {
    endpoint = new URL(artifactURL, remoteURL);
  } catch {
    return { ok: false, warning: "Unable to fetch VM visual artifact: connector returned an invalid artifact URL" };
  }
  const base = new URL(remoteURL);
  if (endpoint.origin !== base.origin || !endpoint.pathname.startsWith("/v1/artifacts/")) {
    return { ok: false, warning: "Unable to fetch VM visual artifact: connector artifact URL was outside the paired connector" };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const headers: Record<string, string> = {};
    if (authHeader) {
      headers.Authorization = authHeader;
    }
    const response = await fetch(endpoint, {
      method: "GET",
      headers,
      signal: controller.signal,
    });
    if (!response.ok) {
      return { ok: false, warning: `Unable to fetch VM visual artifact: connector returned HTTP ${response.status}` };
    }
    return { ok: true, bytes: Buffer.from(await response.arrayBuffer()) };
  } catch (error: unknown) {
    return {
      ok: false,
      warning: `Unable to fetch VM visual artifact: ${(error as { message?: string }).message || "unknown error"}`,
    };
  } finally {
    clearTimeout(timeout);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

type ConnectorURLResult = { ok: true; url: URL } | { ok: false; error: unknown };

function validateEnrollmentConnectorURL(rawURL: string): ConnectorURLResult {
  let parsed: URL;
  try {
    parsed = new URL(rawURL);
  } catch {
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

function forbiddenConnectorURL(message: string): ConnectorURLResult {
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

type EnrollmentStringResult = { ok: true; value: string } | { ok: false; error: unknown };

function requiredEnrollmentString(value: unknown, name: string): EnrollmentStringResult {
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

function isAllowedEnrollmentHost(hostname: string): boolean {
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

function redactConnectorSecrets(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => redactConnectorSecrets(item));
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  const redacted: Record<string, unknown> = {};
  for (const [key, nestedValue] of Object.entries(value)) {
    if (isSecretMetadataKey(key)) {
      redacted[key] = "[redacted]";
    } else {
      redacted[key] = redactConnectorSecrets(nestedValue);
    }
  }
  return redacted;
}

function isSecretMetadataKey(key: string): boolean {
  const compactKey = key.toLowerCase().replace(/[^a-z0-9]/g, "");
  return (
    compactKey === "token" ||
    compactKey.endsWith("token") ||
    compactKey === "authorization" ||
    compactKey.endsWith("authorization") ||
    compactKey === "header" ||
    compactKey === "headers" ||
    compactKey.endsWith("header") ||
    compactKey.endsWith("headers") ||
    compactKey === "password" ||
    compactKey.endsWith("password") ||
    compactKey === "credential" ||
    compactKey === "credentials" ||
    compactKey.endsWith("credential") ||
    compactKey.endsWith("credentials") ||
    compactKey === "secret" ||
    compactKey.endsWith("secret") ||
    compactKey.includes("apikey") ||
    compactKey.includes("clientsecret") ||
    compactKey.includes("privatekey") ||
    compactKey.includes("secretkey") ||
    compactKey.includes("accesskey")
  );
}

function clampInt(value: unknown, fallback: number, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(value)));
}
