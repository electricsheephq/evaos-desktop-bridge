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
  if (toolName.startsWith(READ_ONLY_TOOL_PREFIX)) {
    return undefined;
  }

  const haystack = JSON.stringify({
    toolName,
    args: event.args,
    input: event.input,
    parameters: event.parameters,
  });
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
