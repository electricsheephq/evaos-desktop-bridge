# Codex worker architecture

`evaos-desktop-bridge` deliberately separates two Codex worker identities.

## Desktop-indexed threads

Commands:

- `codex indexed-threads`
- `codex read-thread-tail`
- `codex open-thread`
- `codex steer-thread`

Source of truth:

- `~/.codex/session_index.jsonl`
- rollout files under `~/.codex/sessions/**`
- optional Codex Desktop visualization via `codex://threads/<thread_id>`

Use for:

- human-visible Codex Desktop threads
- long-lived Desktop worker tasks Andrew can inspect after refresh/restart
- guarded thread steering through `codex exec resume <thread_id> -`

Known limitation:

- externally resumed turns can write rollout state without immediate Desktop renderer refresh. The Desktop app may need deep-link reopen, browser reload, or app restart to rehydrate completed turns. Do not equate Desktop visual freshness with worker truth.

## acpx background workers

Commands:

- `codex acpx-worker-list`
- `codex acpx-worker-show`
- `codex acpx-worker-status`
- `codex acpx-worker-prompt`
- `codex acpx-worker-history`
- `codex acpx-worker-tail-events`

Source of truth:

- `~/.acpx/sessions/*.json`
- `~/.acpx/sessions/*.stream.ndjson`
- Codex rollout files when the Codex ACP adapter creates them

Use for:

- background ACP workers with queueing, `--no-wait`, status, cancel/history support from acpx
- non-Desktop-visible long-running workstreams
- future integration where acpx may expose richer queue/session metadata than raw Codex CLI

Known limitation:

- current acpx Codex sessions create Codex rollout files but do not appear in `~/.codex/session_index.jsonl`; classify them as `acpx_background`, not Desktop-visible.

## Rule

Do not blur these lanes. If a command writes to a worker/thread, metadata must say so:

- `codex.steer_thread`: `guarded_thread_action`, writes a Desktop-indexed thread
- `codex.acpx_prompt`: `guarded_worker_action`, writes an acpx background worker

GUI/AX controls remain a fallback/visibility layer, not the primary manager loop.

## Desktop freshness and rehydration

Externally driven Desktop-indexed threads can be truthful in rollout files while stale in the visible Codex Desktop renderer.

Commands:

- `codex desktop-freshness --thread-id <id> --visible-text <text>`
- `codex rehydrate-thread --thread-id <id>`
- `codex rehydrate-thread --thread-id <id> --live`

`desktop-freshness` compares the latest rollout marker against supplied visible text from inspect/OCR/screenshot analysis:

- `fresh`: latest rollout marker is visible
- `stale`: visible text was supplied, but latest rollout marker is absent
- `unknown`: no sufficient visible text/marker exists

`rehydrate-thread` opens `codex://threads/<id>` and asks the Desktop app to re-read the thread. This can expose completed external turns after restart/reload, but it does not guarantee live spinner/progress for a remotely started turn.

Live spinner/progress likely requires starting the turn through Desktop/app-server's own route, not `codex exec resume`.
