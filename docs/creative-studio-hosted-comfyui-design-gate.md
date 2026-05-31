# Creative Studio Hosted ComfyUI Design Gate

Issue: `#101`

## ADR: Hosted/configured ComfyUI first

Creative Studio starts as a hosted ComfyUI route or customer-configured ComfyUI URL. The
Workbench app opens a brokered `creative_studio` route when the customer is
enabled, or falls back to the public ComfyUI Cloud entry while the brokered
route is dark. The macOS app does not bundle ComfyUI, model weights, custom
nodes, GPU workers, or workflow execution.

This keeps the first product slice honest: Creative Studio is the customer's
creative workflow surface, not a hidden local GPU platform. Local or VM-hosted
ComfyUI can graduate later when GPU capacity, model storage, custom-node
governance, auth, cost, and support recovery have proven paths.

## Customer Journey

1. A signed-in customer sees Creative Studio only when
   `creative_studio`/`VITE_EVAOS_CREATIVE_STUDIO` is enabled.
2. Workbench opens the `creative_studio` runtime like the other gateway rows.
   Enabled customers should receive a brokered hosted or customer-configured
   ComfyUI URL.
3. If the broker has no configured URL yet, Workbench uses the documented
   external ComfyUI Cloud route so the lane is visible but not fake.
4. Comfy handles its own login, workflow canvas, queue state, account recovery,
   and hosted GPU state.
5. Disabled or unconfigured customers see a clean unavailable/degraded state
   and can recover by configuring a customer ComfyUI URL or disabling the flag.

## API Lane

Automated workflow submission remains disabled until the customer has a valid
Comfy Cloud/API grant or evaOS-managed server grant. When enabled, the broker
owns:

- grant discovery and revocation;
- job submission with the customer-scoped Comfy endpoint;
- polling queue/job status;
- output retrieval through signed or brokered URLs;
- disabled, expired, revoked, and unavailable states.

Workbench must not expose raw Comfy API keys, provider tokens, model paths, or
workflow secrets. Provider/Auth Hub and Capability Manifest grants should be
the source of truth for whether an agent may submit or retrieve work.

## Deferred VM-Local Path

VM-local ComfyUI is deferred until all of these are true:

- GPU worker capacity and cost controls are proven;
- model and custom-node storage have lifecycle policy;
- customer-scoped auth blocks cross-customer access;
- workflow queue and output retention are auditable;
- support recovery can reset a broken node/model install without corrupting
  customer data;
- one support VM and one friendly customer canary queue a simple workflow.

Until then, VM-local ComfyUI is not a release blocker for Creative Studio.

## Verification

- `RuntimeKey.creativeStudio` serializes as `creative_studio`.
- Creative Studio remains feature-flagged off by default.
- Workbench copy says hosted ComfyUI/ComfyUI Cloud and does not claim local GPU
  execution.
- The macOS app does not embed ComfyUI, GPU workers, model storage, or workflow
  automation.
- Issue `#102` remains the implementation epic for the real broker/proxy
  runtime and live ComfyUI canary.
