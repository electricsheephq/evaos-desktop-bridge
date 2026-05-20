import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

import { type BridgeCommandKey, type BridgeParams, runBridge } from "./src/bridge.js";
import { desktopBridgeFirewall } from "./src/firewall.js";

type ToolDefinition = {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  execute: (params: BridgeParams) => Promise<unknown>;
};

export default definePluginEntry({
  id: "evaos-desktop-bridge",
  name: "EvaOS Desktop Bridge",
  description:
    "Bridge from OpenClaw to visible Codex Desktop state with guarded queue appends, visible selection, and remote turn-control tools.",
  kind: "tool",
  register(api: any) {
    for (const bridgeTool of bridgeTools()) {
      api.registerTool(() => bridgeTool, { names: [bridgeTool.name] });
    }

    api.registerHook?.("before_tool_call", desktopBridgeFirewall, {
      name: "evaos-desktop-bridge-firewall",
    });
  },
});

function bridgeTools(): ToolDefinition[] {
  return [
    tool("desktop_bridge_status", "Read Codex Desktop installation, running, permission, and safety status.", "status"),
    tool("desktop_bridge_capabilities", "Read the bridge command capability surface and hard safety boundaries.", "capabilities"),
    tool("desktop_bridge_latest", "Read the last redacted bridge observation envelope from local state.", "latest"),
    tool(
      "desktop_bridge_audit_tail",
      "Read a redacted tail of the append-only local bridge audit log.",
      "auditTail",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          limit: { type: "integer", minimum: 1, maximum: 100, default: 20 },
        },
      },
    ),
    tool("desktop_bridge_codex_frontmost", "Read whether Codex Desktop is the current frontmost app.", "codexFrontmost"),
    tool("desktop_bridge_codex_windows", "Read visible Codex Desktop window metadata through Accessibility.", "codexWindows"),
    tool(
      "desktop_bridge_queue_list",
      "Read capped Eva/OpenClaw announcement queue events.",
      "queueList",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          limit: { type: "integer", minimum: 1, maximum: 100, default: 20 },
        },
      },
    ),
    tool(
      "desktop_bridge_queue_append",
      "Append a local Eva/OpenClaw announcement queue event with source audit provenance.",
      "queueAppend",
      {
        type: "object",
        additionalProperties: false,
        required: ["kind", "source_audit_id"],
        properties: {
          kind: { type: "string", enum: ["idle", "approval_needed", "done", "error", "attention"] },
          source_audit_id: { type: "string" },
          message: { type: "string" },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_threads",
      "Read visible Codex Desktop thread candidates from GUI state.",
      "codexThreads",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          max_items: { type: "integer", minimum: 1, maximum: 200, default: 50 },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_select_thread",
      "Guarded visible action: select an already-visible Codex thread by visible_id. Dry-run defaults on.",
      "codexSelectThread",
      {
        type: "object",
        additionalProperties: false,
        required: ["thread_id"],
        properties: {
          thread_id: { type: "string" },
          dry_run: { type: "boolean", default: true },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_snapshot",
      "Read a capped visible Codex Desktop snapshot; screenshots are skipped unless Codex is frontmost.",
      "codexSnapshot",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          max_chars: { type: "integer", minimum: 1, maximum: 20000, default: 4000 },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_inspect",
      "Read a compact Codex Desktop page map with visible windows, controls, and text summaries.",
      "codexInspect",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          max_nodes: { type: "integer", minimum: 1, maximum: 1000, default: 120 },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_ax_tree",
      "Read a capped Codex Desktop Accessibility tree summary with roles and names only.",
      "codexAxTree",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          max_nodes: { type: "integer", minimum: 1, maximum: 1000, default: 200 },
        },
      },
    ),
    tool("desktop_bridge_codex_connections_status", "Read Codex Desktop connection and remote-control readiness.", "codexConnectionsStatus"),
    tool("desktop_bridge_codex_app_server_status", "Read Codex app-server availability and read-only method allowlist.", "codexAppServerStatus"),
    tool(
      "desktop_bridge_codex_app_server_threads",
      "Read capped Codex thread summaries through the app-server read allowlist.",
      "codexAppServerThreads",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          max_items: { type: "integer", minimum: 1, maximum: 200, default: 50 },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_live_status",
      "Read a short live Codex app-server notification window for a thread.",
      "codexAppServerSubscribe",
      {
        type: "object",
        additionalProperties: false,
        required: ["thread_id"],
        properties: {
          thread_id: { type: "string" },
          duration_ms: { type: "integer", minimum: 100, maximum: 10000, default: 1000 },
          limit: { type: "integer", minimum: 1, maximum: 200, default: 40 },
          max_chars: { type: "integer", minimum: 1, maximum: 20000, default: 4000 },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_remote_start_turn",
      "Guarded remote-control action: start a Codex Desktop turn through app-server. Dry-run defaults on.",
      "codexAppServerStartTurn",
      {
        type: "object",
        additionalProperties: false,
        required: ["thread_id", "message"],
        properties: {
          thread_id: { type: "string" },
          message: { type: "string" },
          dry_run: { type: "boolean", default: true },
          confirmed: { type: "boolean", default: false },
          source_audit_id: { type: "string" },
          max_chars: { type: "integer", minimum: 1, maximum: 20000, default: 4000 },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_remote_steer_turn",
      "Guarded remote-control action: steer an active Codex Desktop turn through app-server. Dry-run defaults on.",
      "codexAppServerSteerTurn",
      {
        type: "object",
        additionalProperties: false,
        required: ["thread_id", "message"],
        properties: {
          thread_id: { type: "string" },
          turn_id: { type: "string" },
          message: { type: "string" },
          dry_run: { type: "boolean", default: true },
          confirmed: { type: "boolean", default: false },
          source_audit_id: { type: "string" },
          max_chars: { type: "integer", minimum: 1, maximum: 20000, default: 4000 },
        },
      },
    ),
    tool(
      "desktop_bridge_codex_remote_interrupt_turn",
      "Guarded remote-control action: interrupt an active Codex Desktop turn through app-server. Dry-run defaults on.",
      "codexAppServerInterruptTurn",
      {
        type: "object",
        additionalProperties: false,
        required: ["thread_id"],
        properties: {
          thread_id: { type: "string" },
          turn_id: { type: "string" },
          dry_run: { type: "boolean", default: true },
          confirmed: { type: "boolean", default: false },
          source_audit_id: { type: "string" },
        },
      },
    ),
  ];
}

function tool(
  name: string,
  description: string,
  command: BridgeCommandKey,
  parameters: Record<string, unknown> = { type: "object", additionalProperties: false, properties: {} },
): ToolDefinition {
  return {
    name,
    description,
    parameters,
    execute: (params: BridgeParams = {}) => runBridge(command, params),
  };
}
