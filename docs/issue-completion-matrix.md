# Issue Completion Matrix

Milestone: `MVP: Codex Desktop visible harness`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#1` Bootstrap shared snapshot schema and policy core | Schema docs, types, redaction/cap tests | JSON envelope, command metadata, policy allowlist, redaction/cap tests, schema docs |
| `#2` Codex passive observer status/snapshot | `status`, `focus`, `snapshot`, `ax-tree`, capped JSON | CLI commands plus `frontmost`, `windows`, `inspect`; graceful TCC errors |
| `#3` Visible thread inventory | Compare output to UI, cap output, redact paths | `codex threads --json --max-items`, deterministic `visible_id`, AX-only inventory |
| `#4` Guarded visible thread focus action | dry-run and audit, no typing/sending | `codex select-thread --thread-id ... --dry-run`, stale-target checks, provenance audit |
| `#5` Eva announcement queue contract | sample payloads and routing policy | local JSONL queue, `queue append/list`, docs and sample event schema |
| `#6` Audit/provenance | timestamp, target app, source, action/dry-run, result | append-only audit JSONL with command metadata and provenance fields |
| `#7` macOS TCC docs and threat model | setup guide and threat model | `docs/macos-permissions.md`, `docs/threat-model.md`, README safety posture |
| `#8` Claude Desktop spike | research note, no implementation | `docs/claude-desktop-spike.md` |

## Verification

```bash
python3 -m pytest -q
git diff --check
evaos-desktop-bridge --help
evaos-desktop-bridge codex --help
```

Manual macOS checks remain optional and depend on Codex Desktop being running/frontmost with TCC permissions granted.

## CI Cost Control

Milestone: `Repository validation hygiene`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#159` Swift CodeQL cost control | Docs/Python/plugin-only PRs do not start Swift CodeQL. Swift/app PRs keep the fast Workbench build/smoke gate but do not block on Swift CodeQL. Main pushes, version tags, GitHub releases, scheduled scans, and manual dispatch retain Swift CodeQL. Superseded PR pushes cancel in-progress PR runs. Default setup is disabled before advanced workflow SARIF upload validation. | `.github/workflows/codeql.yml` runs Actions/JavaScript/Python analysis on Linux for relevant PR paths plus main/schedule/manual. `.github/workflows/codeql-swift.yml` runs macOS Swift analysis only on main, version tags, published releases, schedule, or manual dispatch, using a manual `swift build --package-path apps/eva-desktop-mac --product EvaDesktop --arch arm64`. `.github/workflows/eva-desktop-workbench.yml` keeps the Swift build/smoke PR gate and cancels superseded PR pushes. `docs/codeql-ci-policy.md` records the default-setup migration step. |

Verification:

```bash
ruby -e 'require "yaml"; %w[.github/workflows/codeql.yml .github/workflows/codeql-swift.yml .github/workflows/eva-desktop-workbench.yml].each { |p| YAML.load_file(p); puts p }'
swift build --package-path apps/eva-desktop-mac --product EvaDesktop --arch arm64
gh api repos/electricsheephq/evaos-desktop-bridge/code-scanning/default-setup -H "Accept: application/vnd.github+json"
git diff --check
```

## 0.6.5 Deep Release Delta

Milestone: `Codex Desktop App-Server Control`

| Area | Status | Evidence |
| --- | --- | --- |
| Fresh app-server protocol handshake | Implemented | `CodexJsonRpcClient` sends `initialize`, waits for result, sends `initialized`, preserves notifications and empty results |
| Transport support | Implemented | stdio default, explicit loopback websocket, explicit proxy; non-loopback websocket URLs are rejected |
| Read-only connection status | Implemented | `codex connections status --json` reports Desktop CLI, app-server handshake, daemon, control sockets, websocket, live notifications, and safety flags |
| Loaded threads/live notifications | Implemented, live acceptance pending | `loaded-threads` and `subscribe` commands with caps/redaction; issue #136 still requires a non-empty `thread/loaded/list` result from a visible Codex Desktop thread plus streamed turn events |
| Guarded remote control | Withheld from public surface | `turn/start`, `turn/steer`, and `turn/interrupt` remain forbidden and CLI/OpenClaw tools are not registered until #136 passes |
| #136 live Codex controller gate | Blocked by local Codex loaded-thread state | Current Codex CLI 0.133.0 proxy smoke returned `thread/loaded/list` count 0 even after remote-control daemon connection, so live controller tools remain unmerged |
| OpenClaw wrapper tools | Implemented status/readiness slice | fixed named tools for connections, live status, loaded threads, and read-only app-server status; still no generic app-server RPC or live controller passthrough |
| Workbench status formatter | Implemented | Workbench reads `codex connections status` and the current `remote_control_command`, `daemon`, and `control_sockets` shape |
| 0.6.5 release canary | Partial, evidence retained | Connector/OpenClaw/Hermes all-surface canaries reached 33/44 before harness fix; desktop scenario rerun passed 5/5; iPhone Calculator launch remains a tuning issue; kill-switch final passed 3/3; QA canaries are not a substitute for the #136 live Codex controller acceptance |

## v0.5 One-App OS Expansion Design Gate

Milestone: `P1 v0.5.0 information architecture`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#95` v0.5 information architecture, navigation, and feature-flag matrix | Screen map covers signed-out, signed-in, normal customer, admin customer switch, gateway fallback, Creative Studio, and degraded runtime states. Feature flag table includes default, owner, rollout criteria, rollback action, and public copy. Existing gateway tabs remain stable and no lane assumes new local Mac/iPhone control behavior. | `docs/evaos-workbench-v050-one-app-expansion.md` now defines the Workbench IA map, sidebar/settings/workspace ownership, degradation behavior, and the full flag matrix. `WorkbenchFeatureFlagKey` exposes typed descriptors for `providers_hub`, `shared_browser_2`, `session_center`, and `creative_studio`, with Swift smoke coverage for defaults, dashboard env keys, rollout/rollback copy, and stable gateway behavior. |

Verification:

```bash
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
swift build
cd ../..
python3 -m pytest tests/test_cli.py tests/test_openclaw_plugin.py -q
git diff --check
```

## Workbench OpenDesign Gateway

Milestone: `Eva Desktop Workbench MVP`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#20` OpenDesign tab spike | Choose hosted/local/placeholder route; safe unavailable state; document expandable choice | Chosen route is the brokered `opendesign` runtime. No hard-coded hosted URL or local discovery is used. Signed-out, authorization, and broker failures use the standard gateway unavailable/error states. Contract is documented in `docs/opendesign-gateway.md`. |
| `#66` OpenDesign first-class Workbench gateway | Brokered launch, no placeholder for eligible customers, persistent WebView, runtime health/readiness, auth parity, Codex/BYOK split | `RuntimeKey.openDesign` serializes as `opendesign`, is a brokered visible runtime, has no external fallback URL, participates in broker `runtime_status` checks, and is loaded through the persistent `RuntimeWebViewDeck`. Codex/BYOK readiness stays separate in Provider Hub/Session Center. |

Verification:

```bash
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
swift build
```

## Eva Desktop Workbench MVP

Milestone: `Eva Desktop Workbench MVP`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#12` Workbench MVP epic | Child issues linked, MVP excludes broad local control, app launches locally with runtime tabs | MVP source, docs, and CI live in `apps/eva-desktop-mac/`; the app launches as `evaOS Workbench`, keeps upstream runtime UIs in `WKWebView`, and the Bridge/Mac/iPhone surfaces keep local control named, gated, and audited. Deferred supervised local Mac control remains tracked separately in `#22`. |
| `#16` Desktop login and Keychain session | Sign in/out, restart persistence, local revoke, no runtime secrets outside session layer, recoverable failure states | `ASWebAuthenticationSession` sign-in, backup device-code claim, non-interactive startup Keychain reads, Keychain-backed opaque desktop sessions, sign-out revoke, reset-local-session, 401/session-expiry cleanup, and explicit user-facing failure states are implemented. Runtime cookies/tokens are not stored in app model state. |
| `#17` Runtime session broker client | Customer/runtime request, server-side short-lived launch URL, no raw runtime tokens in local storage/model, route keys represented | `RuntimeSessionBrokerClient` posts typed `runtime_launch` and `runtime_status` requests to the backend with bearer desktop-session auth; runtime keys are serialized by `RuntimeKey` and launch responses are loaded directly into runtime WebViews without exposing raw runtime secrets. |
| `#18` WebView isolation and cookie safety | Customer/runtime isolation, admin switching cannot reuse wrong cookies, tabs keep separate auth state, two-target smoke coverage | `WebViewStore` keys `WKWebView` instances by `customerId::runtime`, uses a non-persistent website data store, resets webviews on sign-in/sign-out/client rebuild, and forces reload when switching customer targets. Live Workbench canary for `#66` covered an admin/customer switch from David Poku to Golden with OpenDesign reload evidence. |
| `#21` Packaging and notarization track | Developer ID, hardened runtime, notarization/artifact flow, minimal entitlements, local archive validation, OpenClaw lessons borrowed | Packaging docs and `build_and_run.sh` cover beta, Developer ID release, hardened runtime signing, Sparkle appcast generation, bounded notarization, stapling, `codesign`, `spctl`, and live download verification. GA notarization/trust proof continues under `#67`. |

Verification:

```bash
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
swift build
./script/build_and_run.sh --verify
```

## Session Center And Agent Workspace

Milestone: `P1 Session Center product contract`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#99` Session Center and Agent Workspace product contract | Canonical session object and attention states; reconnect contract avoids guessing UI state; dashboard and Workbench can point at the same session record; no arbitrary local shell/control capability | `WorkbenchSessionRecord` and `WorkbenchSessionContract` define `evaos.session_center.v1` with typed `resume_route` values. `docs/session-center-agent-workspace-contract.md` documents canonical fields, attention mapping, Workbench/dashboard ownership, reconnect rules, and the no-generic-control boundary. `EvaDesktopCoreSmoke` covers runtime, queue, audit, Codex, malformed bridge evidence, schema version, and route derivation. |
| `#161` Session Center typed records in Workbench | Workbench renders typed session records, keeps mission-card evidence read-only, opens only broker-runtime records, leaves queue/audit/Codex evidence records non-control, and clears stale records on sign-out/session reset. | `WorkbenchModel.refreshSessionCenterState()` now publishes `sessionRecords` from `WorkbenchSessionContract.records(...)` while preserving mission cards for compatibility. `SessionCenterView` renders `WorkbenchSessionRecord` values and gates Jump/Open through `brokerRuntimeToOpen`. Reset paths clear records alongside runtime status and mission cards. Swift smoke covers record derivation, route kinds, next-action propagation, broker-only open routing, source checks, and stale-record clearing. |

Verification:

```bash
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
swift build
```
