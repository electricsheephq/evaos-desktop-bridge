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
  | "codexSelectThread"
  | "codexSnapshot"
  | "codexInspect"
  | "codexAxTree"
  | "codexConnectionsStatus"
  | "codexAppServerStatus"
  | "codexAppServerThreads"
  | "codexAppServerLoadedThreads"
  | "codexAppServerSubscribe"
  | "codexAppServerStartTurn"
  | "codexAppServerSteerTurn"
  | "codexAppServerInterruptTurn";

export type BridgeParams = {
  max_chars?: number;
  max_nodes?: number;
  max_items?: number;
  limit?: number;
  kind?: string;
  source_audit_id?: string;
  message?: string;
  thread_id?: string;
  turn_id?: string;
  dry_run?: boolean;
  confirmed?: boolean;
  duration_ms?: number;
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
    | "codexSelectThread"
    | "codexAppServerThreads"
    | "codexAppServerLoadedThreads"
    | "codexAppServerSubscribe"
    | "codexAppServerStartTurn"
    | "codexAppServerSteerTurn"
    | "codexAppServerInterruptTurn"
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
  if (command === "codexAppServerSubscribe") {
    return [
      "codex",
      "app-server",
      "subscribe",
      "--json",
      "--thread-id",
      requiredString(params.thread_id, "thread_id"),
      "--duration-ms",
      String(clampInt(params.duration_ms, 1000, 100, 10000)),
      "--max-events",
      String(clampInt(params.limit, 40, 1, 200)),
      "--max-chars",
      String(clampInt(params.max_chars, 4000, 1, 20000)),
    ];
  }
  if (command === "codexAppServerStartTurn") {
    return [
      "codex",
      "app-server",
      "start-turn",
      "--json",
      "--thread-id",
      requiredString(params.thread_id, "thread_id"),
      "--message",
      requiredString(params.message, "message"),
      ...controllerFlags(params),
      "--max-chars",
      String(clampInt(params.max_chars, 4000, 1, 20000)),
    ];
  }
  if (command === "codexAppServerSteerTurn") {
    return [
      "codex",
      "app-server",
      "steer-turn",
      "--json",
      "--thread-id",
      requiredString(params.thread_id, "thread_id"),
      ...(params.turn_id ? ["--turn-id", String(params.turn_id)] : []),
      "--message",
      requiredString(params.message, "message"),
      ...controllerFlags(params),
      "--max-chars",
      String(clampInt(params.max_chars, 4000, 1, 20000)),
    ];
  }
  if (command === "codexAppServerInterruptTurn") {
    return [
      "codex",
      "app-server",
      "interrupt-turn",
      "--json",
      "--thread-id",
      requiredString(params.thread_id, "thread_id"),
      ...(params.turn_id ? ["--turn-id", String(params.turn_id)] : []),
      ...controllerFlags(params),
    ];
  }
  throw new Error(`Unsupported bridge command key: ${String(command)}`);
}

function controllerFlags(params: BridgeParams): string[] {
  if (params.dry_run !== false) {
    return ["--dry-run"];
  }
  if (params.confirmed !== true) {
    throw new Error("confirmed=true is required when dry_run is false");
  }
  return [
    "--live",
    "--confirm",
    "--source-audit-id",
    requiredString(params.source_audit_id, "source_audit_id"),
  ];
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} is required`);
  }
  return value;
}

export async function runBridge(command: BridgeCommandKey, params: BridgeParams = {}): Promise<unknown> {
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

function clampInt(value: unknown, fallback: number, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(value)));
}
