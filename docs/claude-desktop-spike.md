# Claude Desktop Adapter Spike

Issue `#8` asks for a spike only. No Claude Desktop implementation is included in this branch.

## Contract Fit

Claude Desktop can use the same eyes/hands/brain contract:

- Eyes: installed/running, frontmost/window title, visible windows, capped AX tree, screenshot only when Claude is frontmost.
- Hands: focus/select visible conversation only, with dry-run and audit.
- Brain: queue events using the shared announcement contract.

## Differences From Codex Desktop

- App-server seam: no Codex-compatible `codex app-server` protocol. Treat any Claude-specific internal socket or database as out of scope until separately threat-modeled.
- Permissions: same macOS TCC classes apply for visible GUI observation: Accessibility, Screen Recording, and possibly Automation.
- Session inventory: start with visible AX/window state only. Do not read Claude local databases or account/auth files.
- Plugin integration: OpenClaw can consume Claude observations through the same command/plugin pattern after an adapter exists.

## Recommendation

Build a `ClaudeDesktopObserver` only after Codex MVP behavior is accepted. Keep it GUI-visible first, share schema/redaction/audit/queue code, and require a separate review before any hidden Claude state seam is considered.
