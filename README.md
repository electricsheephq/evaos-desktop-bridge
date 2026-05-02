# evaOS Desktop Bridge

Safe bridge between Eva/OpenClaw and visible human desktop agent surfaces.

## First target

Codex Desktop on macOS.

## Architecture

- **Eyes:** read-only state adapters that expose safe structured desktop/session metadata.
- **Hands:** CLI-Anything-style GUI harnesses that operate visible desktop apps through macOS Accessibility/screenshot/AppleScript primitives.
- **Brain:** Eva/OpenClaw policy, approvals, audit logging, and announcement queue.

## Safety posture

No full internal control socket. No hidden mutation backdoor. Start read-only, then add supervised visible actions only after explicit review.

Initial visible desktop concurrency cap: 1 session, 2 maximum after measurement.
