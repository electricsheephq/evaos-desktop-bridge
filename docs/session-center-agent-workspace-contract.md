# Session Center And Agent Workspace Contract

Issue: `#99`
Schema version: `evaos.session_center.v1`

## Purpose

Session Center is the shared place where Workbench, dashboard, and agents can agree on what needs attention. It is not a new local-control backend. It collects read-only evidence from broker runtime state, Desktop Bridge queue/audit records, and Codex readiness summaries, then presents a canonical session record that another surface can deep-link or render.

## Canonical Session Record

```json
{
  "schema_version": "evaos.session_center.v1",
  "id": "runtime-browser",
  "surface": "broker",
  "runtime": "browser",
  "customer_id": "david-poku",
  "title": "Shared Browser",
  "status": "Loaded",
  "attention_state": "active",
  "last_actor": "broker",
  "updated_at": "2026-05-29T16:00:00Z",
  "next_action": "Gateway is loaded in Workbench.",
  "details": [
    "Room: room-1",
    "Current URL: example.com/workspace",
    "Last activity: 2026-05-29T16:00:00Z"
  ],
  "resume_route": {
    "kind": "broker_runtime",
    "runtime": "browser",
    "target_id": "browser",
    "source_pointer": "broker:runtime_status:browser"
  },
  "source_pointer": "broker:runtime_status:browser",
  "audit_id": null
}
```

Fields:

- `schema_version`: stable contract version for Workbench/dashboard parsing.
- `id`: deterministic per evidence source. It should be stable enough for UI diffing, not a secret.
- `surface`: one of `broker`, `queue`, `audit`, `codex`, `bridge`,
  `connected_apps`, `assigned_agent`, or `unknown`.
- `runtime`: brokered runtime key when the record maps to an existing Workbench runtime.
- `customer_id`: sanitized customer/target id when known by the surface.
- `title`: concise display label.
- `status`: source-specific short status.
- `attention_state`: `needs_attention`, `active`, `done`, `idle`, or `unknown`.
- `last_actor`: source owner such as `broker`, `bridge_queue`, `desktop_bridge`, or `codex_app_server`.
- `updated_at`: source timestamp when present.
- `next_action`: concise human-readable next step. Readers should tolerate it missing on early `evaos.session_center.v1` records and use a local fallback.
- `details`: optional bounded, display-only evidence lines such as broker room id, sanitized current URL, or last activity. Readers should tolerate it missing on early `evaos.session_center.v1` records and must not treat it as an authorization source.
- `resume_route`: typed route for reconnect/open behavior.
- `source_pointer`: provenance pointer that a support agent can use to fetch the source evidence.
- `audit_id`: bridge audit id when one exists.

Surface and actor names are related but not interchangeable. `surface` names
the record family; `last_actor` names the producing component. In v1, `queue`
means Desktop Bridge announcement queue evidence and maps to
`last_actor = bridge_queue`; `bridge` means bridge-service failure or fallback
evidence and maps to `last_actor = desktop_bridge`; `audit` maps to
`desktop_bridge`; `broker` maps to `broker`; `codex` maps to
`codex_app_server`; `connected_apps` maps to `connected_apps`; and
`assigned_agent` maps to `agent_assignment`.

Resume route kinds are exhaustive for `evaos.session_center.v1`:

- `broker_runtime`: open/reconnect an existing brokered Workbench runtime for the selected customer target.
- `queue_event`: evidence route to queue-event details.
- `audit_record`: evidence route to bridge audit details.
- `codex_evidence`: evidence route to Codex readiness or thread summary details.
- `evidence_only`: render source evidence without opening a runtime.

## Attention States

| State | Meaning |
| --- | --- |
| `needs_attention` | Auth, CAPTCHA, disabled/degraded/error/unavailable runtime, waiting-on-user runtime, update-available runtime, queue approval/attention/error, bridge command failure, or unavailable Codex readiness. |
| `active` | Broker runtime is enabled/loaded, an active control session is reported, or recent Codex thread evidence exists. |
| `done` | Queue/audit evidence says the work completed or a read-only audit succeeded. |
| `idle` | No active work was reported by queue, Codex threads, or runtime status. |
| `unknown` | Optional evidence is missing or malformed but the source did not prove a failure. |

## Resume And Reconnect

`resume_route.kind = broker_runtime` is the only route that opens an existing Workbench runtime directly. Workbench resolves it by using the already signed-in desktop session and calling the brokered runtime launch/status path for the selected `customer_id` and `runtime`. Dashboard can link to this same route, but it should not infer local WebView state or read local cookies.

`queue_event`, `audit_record`, and `codex_evidence` routes are evidence routes. They open a details view or source evidence, not a hidden control channel. If a Codex record needs visible GUI action, it must go through the separate guarded Codex visible-message lane with dry-run and approval.

When reconnecting after app restart, Workbench must prefer broker/runtime state and source pointers over stale visible UI state. A runtime can be shown as recently loaded only after the broker or current Workbench WebView store confirms it for the current customer target.

Refreshing a single gateway status is allowed to update the corresponding Session Center record immediately. The record must still keep `source_pointer = broker:runtime_status:<runtime>` and must not infer health from the local WebView alone. Closing a local Workbench runtime view may clear the local loaded state, but it is not a broker-side stop.

Shared Browser is the first brokered runtime with an explicit stop action. Workbench and dashboard must use the named `browser_stop` broker action for customer-facing Stop Browser controls; they must not simulate stop by clearing a local WebView, killing local Mac processes, or calling arbitrary runtime URLs. The broker authorizes `browser_stop` with the same owner/admin/customer-service runtime authorization used by `runtime_status` and `browser_open_url`, then forwards only to the fixed Shared Browser controller stop endpoint.

## Recent Launch Metadata

Workbench may keep a small customer-scoped recent-launch list so Session Center can offer a restore affordance after app relaunch. These records are local metadata only: runtime key, sanitized customer id, title, last-opened timestamp, bounded display details, and `source_pointer = broker:runtime_status:<runtime>`.

Recent-launch storage must not store broker launch URLs, query strings, fragments, cookies, gateway tokens, provider tokens, or desktop-session payloads. Reopening a recent launch must call the normal broker runtime launch path with the current signed-in desktop session and mint a fresh broker URL. It must not replay a saved URL or infer runtime health from the recent-launch row.

## Workbench And Dashboard Fit

Workbench owns native rendering, local Keychain session, brokered runtime open/reconnect, and Desktop Bridge evidence collection. The dashboard can render the same session record shape from backend evidence and can link users back into Workbench using the `resume_route`, but it should not depend on macOS Accessibility state, local WebView cookies, or Codex session files.

## No Generic Control Surface

This contract does not add shell execution, arbitrary Desktop control, generic app-server RPC, Codex/Claude session database reads, raw provider token reads, AppleScript, or unapproved message sending. It is a read-only coordination shape plus typed resume hints for already brokered runtimes.
