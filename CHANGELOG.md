# Changelog

All notable repo release changes should be recorded here before a release branch or PR is handed off.

## Unreleased

- Add read-only Session Center mission cards derived from broker runtime status, bridge queue/audit events, and Codex app-server readiness/thread summaries for issue #137.
- Add repo changelog hygiene so future evaOS Workbench/Desktop Bridge releases keep an in-repo record for agents and maintainers.

## 0.6.6 - 2026-05-28

- Fix OpenClaw reconnect failures caused by stale embedded dashboard state pointing at the root public WSS route.
- Reset the embedded OpenClaw runtime webview on forced reload/reconnect so fresh broker connection details replace cached UI state.
- Preserve the signed Sparkle update path, Mac and iPhone controls, private pairing, audited controls, and Workbench kill switch behavior.
