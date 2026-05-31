type HookEvent = {
  toolName?: string;
  name?: string;
  args?: unknown;
  input?: unknown;
  params?: unknown;
  parameters?: unknown;
};

type HookDecision =
  | void
  | {
      block?: boolean;
      blockReason?: string;
      requireApproval?: {
        title: string;
        description: string;
        severity?: "info" | "warning" | "critical";
        timeoutBehavior?: "allow" | "deny";
        allowedDecisions?: Array<"allow-once" | "allow-always" | "deny">;
      };
    };

const SAFE_TOOL_PREFIXES = ["desktop_bridge_", "customer_mac_", "desktop_", "iphone_", "evaos_"];
const FULL_ACCESS_TOOL_PREFIXES = ["desktop_", "iphone_", "customer_mac_iphone_mirroring_"];
const APPROVAL_GATED_TOOL_PREFIXES = [
  "desktop_bridge_codex_select_thread",
  "desktop_bridge_codex_continue_thread",
  "desktop_bridge_codex_send_visible_message",
  "customer_mac_app_focus",
  "customer_mac_local_site_",
];

const IPHONE_GESTURE_TOOL_NAMES = new Set([
  "customer_mac_iphone_mirroring_swipe_left",
  "customer_mac_iphone_mirroring_swipe_right",
  "customer_mac_iphone_mirroring_swipe_up",
  "customer_mac_iphone_mirroring_swipe_down",
]);

const IPHONE_GESTURE_ALLOWED_MATCHES = new Set(["swipe"]);
const FULL_ACCESS_ALLOWED_MATCHES = new Set([
  "generic coordinates",
  "coordinate",
  "mouseDown",
  "mouseUp",
  "drag",
  "swipe",
  "typewrite",
  "send_message",
  "submit_prompt",
  "messages",
  "call",
  "purchase",
  "camera",
  "microphone",
]);

const DANGEROUS_TOOL_NAMES = [
  "exec",
  "shell",
  "bash",
  "terminal",
  "computer",
  "computer_use",
  "run_command",
  "write",
  "edit",
];

const FORBIDDEN_ARGUMENT_PATTERNS = [
  "osascript",
  "screencapture",
  "cliclick",
  "pyautogui",
  "pynput",
  "AXUIElement",
  "AXUIElementPerformAction",
  "AXUIElementSetAttributeValue",
  "AXPress",
  "AXSetValue",
  "AXShowMenu",
  "AXSelectedText",
  "System Events",
  "Codex.app",
  "open -a Codex",
  "codex app-server",
  "app-server",
  "internal mutation rpc",
  "turn/start",
  "turn/steer",
  "turn/interrupt",
  "thread/inject_items",
  "thread/start",
  "thread/resume",
  "thread/fork",
  "thread/rollback",
  "thread/compact/start",
  "command/exec",
  "fs/writeFile",
  "fs/remove",
  "config/value/write",
  "config/batchWrite",
  "plugin/install",
  "plugin/uninstall",
  "remoteControl/enable",
  "remoteControl/disable",
  "remoteControl/approve",
  "remoteControl/deny",
  "session.db",
  "state.db",
  "sqlite",
  ".codex",
  "auth.json",
  "token",
  "Authorization",
  "Bearer ",
  "send_message",
  "submit_prompt",
  "typewrite",
  "generic coordinates",
  "coordinate",
  "mouseDown",
  "mouseUp",
  "drag",
  "swipe",
  "Screen Sharing enable",
  "Remote Management enable",
  "kickstart -activate",
  "messages",
  "call",
  "purchase",
  "camera",
  "microphone",
];

export function desktopBridgeFirewall(event: HookEvent): HookDecision {
  const toolName = String(event.toolName || event.name || "");
  const haystack = JSON.stringify({
    toolName,
    args: firewallPayload(toolName, event.args),
    input: firewallPayload(toolName, event.input),
    params: firewallPayload(toolName, event.params),
    parameters: firewallPayload(toolName, event.parameters),
  }).toLowerCase();
  const matchedPattern = FORBIDDEN_ARGUMENT_PATTERNS.find((pattern) => haystack.includes(pattern.toLowerCase()));
  if (SAFE_TOOL_PREFIXES.some((prefix) => toolName.startsWith(prefix))) {
    const allowedFullAccessMatch =
      matchedPattern !== undefined &&
      FULL_ACCESS_TOOL_PREFIXES.some((prefix) => toolName.startsWith(prefix)) &&
      FULL_ACCESS_ALLOWED_MATCHES.has(matchedPattern);
    const allowedSupportCanaryMatch =
      matchedPattern !== undefined &&
      IPHONE_GESTURE_TOOL_NAMES.has(toolName) &&
      IPHONE_GESTURE_ALLOWED_MATCHES.has(matchedPattern);
    if (matchedPattern && !allowedSupportCanaryMatch && !allowedFullAccessMatch) {
      return {
        block: true,
        blockReason:
          `desktop-bridge firewall blocked ${toolName}: ${matchedPattern} must go through the connector's audited control contract.`,
      };
    }
    if (APPROVAL_GATED_TOOL_PREFIXES.some((prefix) => toolName.startsWith(prefix))) {
      const params = ((event.args || event.input || event.params || event.parameters || {}) as Record<string, unknown>);
      if (params.dry_run !== false) {
        return undefined;
      }
      return {
        requireApproval: {
          title: "Approve customer Mac action",
          description:
            `${toolName} is a live customer Mac named action. Approval is required and the bridge will audit the command.`,
          severity: "warning",
          timeoutBehavior: "deny",
          allowedDecisions: ["allow-once", "deny"],
        },
      };
    }
    return undefined;
  }

  const suspiciousTool = DANGEROUS_TOOL_NAMES.some((name) => toolName.toLowerCase().includes(name));

  if (suspiciousTool && matchedPattern) {
    return {
      block: true,
      blockReason:
        `desktop-bridge firewall blocked ${toolName}: ${matchedPattern} is outside the read-only passive observer boundary.`,
    };
  }

  return undefined;
}

function firewallPayload(toolName: string, value: unknown): unknown {
  if (toolName !== "desktop_bridge_codex_send_visible_message" || !isRecord(value)) {
    return value;
  }
  const clone = { ...value };
  if (typeof clone.message === "string") {
    clone.message = "<approved-message-redacted-for-firewall-scan>";
  }
  return clone;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
