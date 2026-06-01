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
| 0.6.5/0.6.7 release canary | Partial, evidence retained | 0.6.5 Connector/OpenClaw/Hermes all-surface canaries reached 33/44 before harness fixes; 0.6.7 build 47 connector canary passed Codex readiness/status and foreground Mac primitive/scenario rows. The remaining iPhone reds were reclassified as live-run contamination plus image-only evidence parsing, so the canary now retries transient visual mismatches and derives Calculator state from screenshot artifacts. QA canaries are not a substitute for the #136 live Codex controller acceptance. |

## v0.5 One-App OS Expansion Design Gate

Milestone: `P1 v0.5.0 information architecture`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#95` v0.5 information architecture, navigation, and feature-flag matrix | Screen map covers signed-out, signed-in, normal customer, admin customer switch, gateway fallback, Creative Studio, and degraded runtime states. Feature flag table includes default, owner, rollout criteria, rollback action, and public copy. Existing gateway tabs remain stable and no lane assumes new local Mac/iPhone control behavior. | `docs/evaos-workbench-v050-one-app-expansion.md` now defines the Workbench IA map, sidebar/settings/workspace ownership, degradation behavior, and the full flag matrix. `WorkbenchFeatureFlagKey` exposes typed descriptors for `providers_hub`, `shared_browser_2`, `session_center`, and `creative_studio`, with Swift smoke coverage for defaults, dashboard env keys, rollout/rollback copy, and stable gateway behavior. |
| `#101` Creative Studio hosted/configured ComfyUI design gate | ADR chooses hosted/configured URL first; customer journey covers login, persistence, configured URL, unavailable state, and support recovery; API lane describes grants, revocation, job submission, polling, output retrieval, and disabled states; VM-local path is explicitly deferred with graduation criteria. | `docs/creative-studio-hosted-comfyui-design-gate.md` records the hosted Comfy-first ADR, Workbench customer journey, API grant lane, disabled behavior, and VM-local graduation criteria. `RuntimeKey.creativeStudio` is non-brokered and non-bundled in the macOS app; issue `#102` is the implementation epic for the hosted Creative Studio product surface. |
| `#102` Creative Studio / Hosted ComfyUI-first first implementation slice | Creative Studio opens the hosted Comfy web surface without bundling ComfyUI, GPU workers, model storage, or workflow automation. | In progress: Workbench opens `https://www.comfy.org/cloud` directly in the Creative Studio runtime WebView from the Gateway list, and the dashboard route embeds the same hosted surface. VM-local/proxy ComfyUI is not a blocker for this slice. |

Verification:

```bash
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
swift build
cd ../..
python3 -m pytest tests/test_cli.py tests/test_openclaw_plugin.py -q
git diff --check
```

## Approval Center Contract

Milestone: `#144 P0 Epic: M5 Approval Center`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#144` Approval Center contract slice | Define the Workbench-local approval request model and destination-preview rules. Rows must show actual recipients/URLs/paths/scopes, not display names or summaries. Missing destinations fail closed as not actionable. Keep broker endpoints and live decision submission deferred. | `WorkbenchApprovalRequest` and `WorkbenchApprovalPreviewBuilder` derive spoof-resistant actual-destination previews for email, message, URL, file, purchase, secret, budget, and permission actions. `ApprovalCenterView` is feature-flagged by `approval_center` and renders read-only cards with disabled decision buttons until broker endpoints land. `docs/approval-center-contract.md` documents the no-display-name-only boundary and deferred runtime/broker wiring. |
| `#144` Approval Center live broker + notification slices | Poll production broker approvals from signed-in Workbench, submit guarded human decisions, and alert the operator when new pending approvals arrive while away from the Approval Center. | Workbench polls the authenticated broker path, submits `allow-once` / `deny`, clears stale rows on session reset, and uses `WorkbenchApprovalNotificationPlanner` plus `ApprovalCenterNotificationService` to emit one local notification per new away-from-view pending approval without body/payload leakage. |
| `#144` Destination-constrained durable decisions | Let the operator choose `allow-always` only when the broker can constrain the durable policy to the actual destination, and ensure constrained rows do not become global tool grants. | Workbench exposes `allow-always` only for current rows with broker `allow_always_supported` evidence and no warning/redacted destination evidence. Backend PR `electricsheephq/electric-sheep#2069` provides the Cortex destination kind/fingerprint/summary write and keeps constrained policy rows at `requires_approval` until OpenClaw/Hermes runtime enforcement supports destination matching. |
| `#241` Approval runtime resolution | Approval rows include actual destination proof before decision. Allow-once and deny resolve the real runtime pending action. Allow-always writes only destination-constrained policy rows. Spoofed recipient/URL payloads fail closed. Audit/provenance links request, decision, and runtime result. | `WorkbenchApprovalDestinationProof` is derived only from strict actual-destination previews, preserved after raw payload stripping, and attached to broker decision payloads with source/audit pointers. Workbench blocks allow decisions without proof, keeps deny available for malformed rows, decodes optional broker `runtime_result` evidence after decisions, and smoke tests spoofed preview/payload handling plus legacy decision response compatibility. |

Verification:

```bash
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
swift build
```

## Capability Manifest Contract

Milestone: `#143 P0 Epic: M2 Capability Manifest`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#143` Capability Manifest contract slice | Define signed manifest shape, verify HS256 locally, fail closed on missing/invalid tool grants, expose only safe summaries to Workbench/agents, and preserve existing OpenClaw/Hermes approval seams for follow-up runtime plugins. | `src/evaos_desktop_bridge/capability_manifest.py` and `WorkbenchCapabilityManifestVerifier` verify the shared JWT contract with issuer/audience/expiry/signature checks. Missing tools return `denied`; summaries contain agent/owner/expiry/approval channel/budget/grouped tools only. `WorkbenchCapabilityManifestStore` caches signed manifest tokens in the reserved Workbench Keychain service. `docs/capability-manifest.md` maps OpenClaw/Hermes/Workbench follow-up slices without adding a live approval or broker surface yet. |
| `#143` M2d Workbench broker fetch/cache slice | Workbench fetches capability manifests from the broker using the signed-in desktop session, caches only the raw signed token, renders only broker-provided safe grant metadata, clears stale state on session/customer/client-boundary changes, and does not add OpenClaw/Hermes enforcement or live approval decisions. | `RuntimeSessionBrokerClient.capabilityManifest` calls the authenticated Cortex `GET /api/v1/capabilities/{agent_id}` path. `WorkbenchModel.refreshCapabilityManifest` runs from the Providers surface and provider lifecycle refreshes, saves validated tokens to Keychain, renders safe summaries when present, reports summary-pending when only a valid token is returned, and fails closed on 401/403/404. `CapabilityManifestPanel` shows safe metadata only. Swift smoke locks fetch-response parsing, summary mapping, stale-cache reset hooks, source safety, and absence of raw manifest JWT rendering. |

Verification:

```bash
python3 -m pytest tests/test_capability_manifest.py -q
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
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
| `#97` Business Browser first-class Workbench workspace | Business Browser exposes broker runtime status and user-facing open/reconnect/reload/status controls without raw proxy errors; stale runtime evidence should be visible as a status/attention state, not a silent broken webview. | `RuntimeDetailView` keeps broker status behind the toolbar `Status` action instead of rendering a duplicate always-on status strip above every workspace page. The runtime toolbar exposes `Status`, `Reconnect`, `Reload`, `Open`, broker-backed `Stop Browser`, and local `Close View` controls. When broker evidence says Business Browser is inactive/unavailable, Workbench labels the brokered launch as `Start / Attach`, tells the user startup can take up to a minute after idle, and Home points to the same start-or-reattach action instead of surfacing raw proxy failure copy. `WorkbenchModel.refreshRuntimeStatus(...)` updates runtime status, Business Browser metadata, and Home records from the same broker `runtime_status` source. The stop path is a fixed `browser_stop` broker action authorized for the target customer/runtime, not a generic proxy or local-process control path. |
| `#100` Home / Session Center | Runtime/session truth should stay synchronized when a user refreshes an individual workspace, not only when Home is open. | Per-runtime status refresh and local close/detach update the relevant `WorkbenchMissionCard` and `WorkbenchSessionRecord` immediately, preserving the same `broker:runtime_status:<runtime>` source pointer that the Session Center contract uses. |
| `#100` Home / Session Center | Workbench should mirror the dashboard recent-launch restore slice without storing stale launch URLs or tokens. | Home now renders a separate Recent launches section from customer-scoped metadata only, records successful brokered launches as restorable runtime records, and reopens them by calling the normal broker launch path to mint a fresh URL. |
| `#100` Session Center and Agent Workspace | Admin/customer switching must not retain stale session/runtime evidence from the previous customer. | `WorkbenchModel.customerId` now clears runtime status, mission cards, session records, Shared Browser room/current URL/last-activity text, and in-flight Shared Browser refresh state before loading customer-scoped recent launch metadata. |
| `#99` Session Center and Agent Workspace product contract | Canonical session object and attention states; reconnect contract avoids guessing UI state; dashboard and Workbench can point at the same session record; no arbitrary local shell/control capability | `WorkbenchSessionRecord` and `WorkbenchSessionContract` define `evaos.session_center.v1` with typed `resume_route` values. `docs/session-center-agent-workspace-contract.md` documents canonical fields, attention mapping, Workbench/dashboard ownership, reconnect rules, and the no-generic-control boundary. `EvaDesktopCoreSmoke` covers runtime, queue, audit, Codex, malformed bridge evidence, schema version, and route derivation. |
| `#161` Session Center typed records in Workbench | Workbench renders typed session records, keeps mission-card evidence read-only, opens only broker-runtime records, leaves queue/audit/Codex evidence records non-control, and clears stale records on sign-out/session reset. | `WorkbenchModel.refreshSessionCenterState()` now publishes `sessionRecords` from `WorkbenchSessionContract.records(...)` while preserving mission cards for compatibility. `SessionCenterView` renders `WorkbenchSessionRecord` values and gates Jump/Open through `brokerRuntimeToOpen`. Reset paths clear records alongside runtime status and mission cards. Swift smoke covers record derivation, route kinds, next-action propagation, broker-only open routing, source checks, and stale-record clearing. |

Verification:

```bash
cd apps/eva-desktop-mac
swift run EvaDesktopCoreSmoke
swift build
```

## Background Computer-Use Helper

Milestone: `0.7 background and parallel Mac control foundation`

| Issue | Acceptance | Implemented |
| --- | --- | --- |
| `#163` Computer-use helper IPC auth contract skeleton | Define a safe helper IPC seam with capability-token and peer-uid checks, malformed envelope/frame rejection, oversized-frame rejection before JSON parsing, no token echo, and no generic actuation passthrough. | `helper_ipc.py` defines `evaos.helper_ipc.v1`, length-prefixed JSON framing, short default socket path, rotated per-launch token generation, atomic token validation/read, unsafe token-file rejection, strict peer uid authorization, accepted-connection timeouts, request envelope validation, and a token-redacted ping response. The current `#121` foundation extends the same seam to the first narrow live route, `mouse_action` click/scroll/drag with required bridge audit id, while still rejecting shell, Python, AppleScript, generic computer-use, iPhone action, and Codex mutation commands. `docs/computer-use-helper-ipc.md` documents the local helper opt-in and dumb-hands boundary. `tests/test_helper_ipc.py` locks the exact helper command surface, token/peer policy rejection, malformed envelope/frame rejection, oversized-frame rejection before JSON parsing, regular-file socket path refusal, stalled-client timeout, and unknown command denial. |
| `#122` Signed helper/TCC identity | Run the helper through the signed evaOS Workbench launch path, report Accessibility/Screen Recording grant preflight under that identity, and fail closed when the helper is unattributed or grants are missing/unknown. | Workbench now starts `helper run` before the customer Mac connector, passes the Workbench bundle id/app path plus `EVAOS_DESKTOP_BRIDGE_HELPER_ENFORCE_PERMISSIONS=1`, verifies the helper parent process is inside the claimed Workbench app bundle, and starts the connector with only that managed helper socket/token. `helper ping` reports identity and grant provenance. Helper `mouse_action` returns structured `helper_identity_unverified` or `permission_missing` errors without touching process events when enforced preflight fails. |
| `#129` IPC-seam safety: dumb-hands helper + sender authorization | Keep policy above the helper seam, authenticate helper senders with peer uid plus a per-launch token, refuse unaudited actuation, and record every helper actuation with provenance. | `helper_ipc.py` remains a dumb-hands contract: it authenticates token and peer uid, rejects all commands except `ping`, structured `mouse_action`, and fixed semantic `ax_action`, requires a bridge-provided `audit-*` id for actuation, and enforces Workbench identity/grant preflight before process events or AX actions. `CustomerMacObserver._mouse_action` writes a durable `helper.mouse_action` authorized-dispatch audit record before IPC, passes that exact helper audit id through the helper request, fails closed with no Python fallback when the helper errors, and writes a completion/failure audit record after the helper returns. Tests cover missing/wrong token, wrong peer uid, missing audit id, no token echo, unknown command denial, helper click/scroll/drag routing, no Python fallback, permission/identity fail-closed behavior, and helper actuation audit records. |
| `#123` Tier-1 AX actions | Add semantic Accessibility actions for native controls by pid+fresh snapshot element without raw AX passthrough, while preserving sensitive-target blocks, dry-run/approval, and audit provenance. | `helper_ipc.py` now allows fixed `ax_action` verbs only. `CustomerMacObserver.desktop_click` routes AX-backed snapshot elements through helper `press`; `desktop_set_value` sets AX value/selected text only for fresh non-sensitive, non-secure, editable native text targets and audits hashes instead of raw values. The connector and OpenClaw plugin expose fixed `desktop_set_value` mappings, materialize values into 0600 temp files instead of subprocess argv, Ask Permission mode gates it as high impact, and the firewall blocks raw AX primitive escape strings. Tests cover helper authorization, AX click/set-value routing, non-text role denial, target-process mismatch, target-sensitive/background blocking, web-content inert handling, CLI redaction, connector approval hash matching, value-file materialization, and plugin fixed-surface/firewall behavior. |
| `#124` Tier-2 PostToPid actions | Replace global event-tap fallback with per-process click/scroll/drag dispatch for AX-gap native apps, fail closed for stale targets, and never report browser web-content clicks as successful. | `QuartzMouseActionExecutor` now requires target `pid` and `process_name`, rechecks the live process before posting, dispatches click/scroll/drag with `CGEventPostToPid`, and treats `AXWebArea` paths as inert/escalated. `CustomerMacObserver.desktop_click` only uses Tier-1 AX when `AXPress` is available; AX-gap snapshot elements and focused-app coordinate fallbacks route through the helper with target identity, fail closed when the helper or target is missing, and no longer run per-action Python/global-event fallback. Tests lock source removal of the old event tap, target-identity requirements, post-to-pid helper payloads, helper audit preservation, and no Python fallback. |

Verification:

```bash
python3 -m pytest tests/test_helper_ipc.py -q
python3 -m pytest tests/test_customer_mac_adapter.py -q
python3 -m pytest tests/test_eva_desktop_beta_release.py -q
git diff --check
```
