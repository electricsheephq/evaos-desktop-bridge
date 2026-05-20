type HookEvent = {
  toolName?: string;
  name?: string;
  args?: unknown;
  input?: unknown;
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

const SAFE_TOOL_PREFIXES = ["desktop_bridge_", "customer_mac_"];
const APPROVAL_GATED_TOOL_PREFIXES = [
  "customer_mac_app_focus",
  "customer_mac_local_site_",
  "customer_mac_iphone_mirroring_focus",
  "customer_mac_iphone_mirroring_home",
  "customer_mac_iphone_mirroring_app_switcher",
  "customer_mac_iphone_mirroring_spotlight",
  "customer_mac_iphone_mirroring_type_spotlight",
  "customer_mac_iphone_mirroring_open_app",
  "customer_mac_iphone_mirroring_tap_named_target",
  "customer_mac_iphone_mirroring_scroll",
];

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
    args: event.args,
    input: event.input,
    parameters: event.parameters,
  }).toLowerCase();
  const matchedPattern = FORBIDDEN_ARGUMENT_PATTERNS.find((pattern) => haystack.includes(pattern.toLowerCase()));
  if (SAFE_TOOL_PREFIXES.some((prefix) => toolName.startsWith(prefix))) {
    if (matchedPattern) {
      return {
        block: true,
        blockReason:
          `desktop-bridge firewall blocked ${toolName}: ${matchedPattern} is outside the customer Mac safety boundary.`,
      };
    }
    if (APPROVAL_GATED_TOOL_PREFIXES.some((prefix) => toolName.startsWith(prefix))) {
      const params = ((event.args || event.input || event.parameters || {}) as Record<string, unknown>);
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
