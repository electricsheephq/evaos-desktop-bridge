#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { runBridge } from "../dist/src/bridge.js";
import { desktopBridgeFirewall } from "../dist/src/firewall.js";

const [, , command, paramsArgument = "{}"] = process.argv;

if (!command) {
  console.error("usage: qa-run-bridge.mjs <bridge-command> [params-json]");
  process.exit(2);
}

let params;
try {
  const paramsJSON = paramsArgument === "-" ? await readStdin() : paramsArgument;
  params = JSON.parse(paramsJSON);
} catch (error) {
  console.error(`invalid params JSON: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(2);
}

const toolMap = await loadRegisteredToolMap();
const bridgeCommand = toolMap.get(command) || command;
const firewallDecision = desktopBridgeFirewall({
  toolName: command,
  args: params,
});

if (firewallDecision?.block) {
  console.log(
    JSON.stringify({
      ok: false,
      errors: [
        {
          code: "qa_openclaw_firewall_blocked",
          message: firewallDecision.blockReason || "OpenClaw desktop bridge firewall blocked this tool call.",
          guidance: "Use only the registered desktop bridge tools and audited connector command contract.",
        },
      ],
    }),
  );
  process.exit(0);
}

if (firewallDecision?.requireApproval) {
  console.log(
    JSON.stringify({
      ok: false,
      errors: [
        {
          code: "qa_openclaw_firewall_approval_required",
          message: firewallDecision.requireApproval.description,
          guidance: "Run the dry-run first, collect approval, then rerun with matching approval evidence.",
        },
      ],
    }),
  );
  process.exit(0);
}

if (!toolMap.has(command) && command.includes("_")) {
  console.log(
    JSON.stringify({
      ok: false,
      errors: [
        {
          code: "qa_openclaw_tool_not_registered",
          message: `${command} is not registered by the built OpenClaw plugin entrypoint.`,
          guidance: "Rebuild the OpenClaw plugin and verify openclaw-plugin/dist/index.js.",
        },
      ],
    }),
  );
  process.exit(0);
}

try {
  const result = await runBridge(bridgeCommand, params);
  console.log(JSON.stringify(result));
} catch (error) {
  console.log(
    JSON.stringify({
      ok: false,
      errors: [
        {
          code: "qa_run_bridge_failed",
          message: error instanceof Error ? error.message : String(error),
          guidance: "Build the OpenClaw plugin and verify the bridge command shape.",
        },
      ],
    }),
  );
  process.exit(0);
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8") || "{}";
}

async function loadRegisteredToolMap() {
  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const distIndex = join(scriptDir, "../dist/index.js");
  const source = await readFile(distIndex, "utf8");
  const map = new Map();
  const toolCallPattern = /tool\(\s*"([^"]+)"[\s\S]*?,\s*"([A-Za-z0-9]+)"(?:\s*,|\s*\))/g;
  let match;
  while ((match = toolCallPattern.exec(source)) !== null) {
    map.set(match[1], match[2]);
  }
  return map;
}
