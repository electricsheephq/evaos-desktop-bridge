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
  description: "Read-only bridge from OpenClaw to visible Codex Desktop state.",
  kind: "tool",
  register(api: any) {
    for (const bridgeTool of readOnlyTools()) {
      api.registerTool(() => bridgeTool, { names: [bridgeTool.name] });
    }

    api.registerHook?.("before_tool_call", desktopBridgeFirewall, {
      name: "evaos-desktop-bridge-firewall",
    });
  },
});

function readOnlyTools(): ToolDefinition[] {
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
    tool("customer_mac_status", "Read paired customer Mac connector, iPhone Mirroring, and Screen Sharing readiness.", "customerMacStatus"),
    tool("customer_mac_capabilities", "Read supported named customer Mac actions and hard safety boundaries.", "customerMacCapabilities"),
    tool(
      "customer_mac_snapshot",
      "Read a safe screenshot path for the frontmost non-sensitive app; sensitive apps are blocked.",
      "customerMacSnapshot",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          max_chars: { type: "integer", minimum: 1, maximum: 20000, default: 4000 },
        },
      },
    ),
    tool(
      "customer_mac_ax_tree",
      "Read a capped Accessibility tree for the frontmost non-sensitive app.",
      "customerMacAxTree",
      {
        type: "object",
        additionalProperties: false,
        properties: {
          max_nodes: { type: "integer", minimum: 1, maximum: 1000, default: 200 },
        },
      },
    ),
    tool(
      "customer_mac_app_focus",
      "Approval-gated named action: focus a non-sensitive customer Mac app by name.",
      "customerMacAppFocus",
      {
        type: "object",
        additionalProperties: false,
        required: ["app_name"],
        properties: {
          app_name: { type: "string" },
          dry_run: { type: "boolean", default: true },
        },
      },
    ),
    tool(
      "customer_mac_local_site_open",
      "Approval-gated named action: open a localhost, loopback, or .local website on the customer Mac.",
      "customerMacLocalSiteOpen",
      {
        type: "object",
        additionalProperties: false,
        required: ["url"],
        properties: {
          url: { type: "string" },
          dry_run: { type: "boolean", default: true },
        },
      },
    ),
    tool(
      "customer_mac_local_site_action",
      "Approval-gated named action: run reload, back, or forward in the frontmost supported browser.",
      "customerMacLocalSiteAction",
      {
        type: "object",
        additionalProperties: false,
        required: ["action"],
        properties: {
          action: { type: "string", enum: ["reload", "back", "forward"] },
          dry_run: { type: "boolean", default: true },
        },
      },
    ),
    tool("customer_mac_iphone_mirroring_status", "Read iPhone Mirroring readiness and supported named actions.", "customerMacIphoneMirroringStatus"),
    tool(
      "customer_mac_iphone_mirroring_focus",
      "Approval-gated named action: focus iPhone Mirroring.",
      "customerMacIphoneMirroringFocus",
      { type: "object", additionalProperties: false, properties: { dry_run: { type: "boolean", default: true } } },
    ),
    tool(
      "customer_mac_iphone_mirroring_home",
      "Approval-gated named action: send Home to iPhone Mirroring.",
      "customerMacIphoneMirroringHome",
      { type: "object", additionalProperties: false, properties: { dry_run: { type: "boolean", default: true } } },
    ),
    tool(
      "customer_mac_iphone_mirroring_app_switcher",
      "Approval-gated named action: open the iPhone Mirroring App Switcher.",
      "customerMacIphoneMirroringAppSwitcher",
      { type: "object", additionalProperties: false, properties: { dry_run: { type: "boolean", default: true } } },
    ),
    tool(
      "customer_mac_iphone_mirroring_spotlight",
      "Approval-gated named action: open iPhone Spotlight through iPhone Mirroring.",
      "customerMacIphoneMirroringSpotlight",
      { type: "object", additionalProperties: false, properties: { dry_run: { type: "boolean", default: true } } },
    ),
    tool(
      "customer_mac_iphone_mirroring_type_spotlight",
      "Approval-gated named action: type short disposable/search text into iPhone Spotlight.",
      "customerMacIphoneMirroringTypeSpotlight",
      {
        type: "object",
        additionalProperties: false,
        required: ["text"],
        properties: {
          text: { type: "string", minLength: 1, maxLength: 80 },
          dry_run: { type: "boolean", default: true },
        },
      },
    ),
    tool(
      "customer_mac_iphone_mirroring_open_app",
      "Approval-gated named action: launch a non-sensitive iPhone app through Spotlight.",
      "customerMacIphoneMirroringOpenApp",
      {
        type: "object",
        additionalProperties: false,
        required: ["app_name"],
        properties: {
          app_name: { type: "string", minLength: 1, maxLength: 80 },
          dry_run: { type: "boolean", default: true },
        },
      },
    ),
    tool(
      "customer_mac_iphone_mirroring_tap_named_target",
      "Approval-gated named action: press an exact visible iPhone Mirroring AX label; generic coordinates are blocked.",
      "customerMacIphoneMirroringTapNamedTarget",
      {
        type: "object",
        additionalProperties: false,
        required: ["target_label"],
        properties: {
          target_label: { type: "string", minLength: 1, maxLength: 80 },
          dry_run: { type: "boolean", default: true },
        },
      },
    ),
    tool(
      "customer_mac_iphone_mirroring_scroll",
      "Disabled pending evidence: reports unsupported rather than attempting flaky scroll/swipe control.",
      "customerMacIphoneMirroringScroll",
      { type: "object", additionalProperties: false, properties: { dry_run: { type: "boolean", default: true } } },
    ),
    tool("customer_mac_screen_sharing_status", "Read Screen Sharing/Remote Management status; this tool cannot enable it.", "customerMacScreenSharingStatus"),
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
