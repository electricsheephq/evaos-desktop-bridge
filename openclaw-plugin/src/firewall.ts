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
      requireApproval?: boolean;
      approvalReason?: string;
    };

const READ_ONLY_TOOL_PREFIX = "desktop_bridge_";

const CONTROLLER_TOOL_NAMES = new Set([
  "desktop_bridge_codex_remote_start_turn",
  "desktop_bridge_codex_remote_steer_turn",
  "desktop_bridge_codex_remote_interrupt_turn",
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
];

export function desktopBridgeFirewall(event: HookEvent): HookDecision {
  const toolName = String(event.toolName || event.name || "");
  const haystack = JSON.stringify({
    toolName,
    args: event.args,
    input: event.input,
    parameters: event.parameters,
  });
  const parsedArgs = normalizeArgs(event.args ?? event.input ?? event.parameters);
  if (CONTROLLER_TOOL_NAMES.has(toolName) && parsedArgs.dry_run === false) {
    return {
      requireApproval: true,
      approvalReason: "Live Codex Desktop remote-control actions can start, steer, or interrupt a Desktop-owned turn.",
    };
  }
  if (toolName.startsWith(READ_ONLY_TOOL_PREFIX)) {
    return undefined;
  }

  const suspiciousTool = DANGEROUS_TOOL_NAMES.some((name) => toolName.toLowerCase().includes(name));
  const matchedPattern = FORBIDDEN_ARGUMENT_PATTERNS.find((pattern) => haystack.includes(pattern));

  if (suspiciousTool && matchedPattern) {
    return {
      block: true,
      blockReason:
        `desktop-bridge firewall blocked ${toolName}: ${matchedPattern} is outside the read-only passive observer boundary.`,
    };
  }

  return undefined;
}

function normalizeArgs(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}
