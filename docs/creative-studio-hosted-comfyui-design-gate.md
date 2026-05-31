# Creative Studio Hosted ComfyUI Design Gate

Issue: `#101`

## ADR: Hosted/configured ComfyUI first

Creative Studio starts as the hosted Comfy web surface. The Workbench app opens
`https://www.comfy.org/cloud` inside its runtime WebView, and the dashboard
Creative Studio page embeds the same hosted site for signed-in users.
The macOS app does not bundle ComfyUI, model weights, custom nodes, GPU workers,
or workflow execution.

This keeps the first product slice honest: Creative Studio is the customer's
creative workflow surface, not a hidden local GPU platform. Local or VM-hosted
ComfyUI can graduate later when GPU capacity, model storage, custom-node
governance, auth, cost, and support recovery have proven paths.

## Customer Journey

1. A signed-in customer sees Creative Studio only when
   `creative_studio`/`VITE_EVAOS_CREATIVE_STUDIO` is enabled.
2. Workbench opens the hosted Comfy Cloud page directly inside the Creative
   Studio runtime view.
3. The dashboard `/dashboard/creative-studio` route embeds the same hosted page
   and provides a new-tab escape hatch for browser policies or login flows.
4. Comfy handles its own login, workflow canvas, queue state, account recovery,
   and hosted GPU state.
5. Disabled customers can hide the feature flag without affecting brokered
   evaOS runtimes.

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
- `RuntimeDefinition.isBrokeredRuntime(.creativeStudio)` is false.
- `RuntimeDefinition.externalURL(for: .creativeStudio)` is
  `https://www.comfy.org/cloud`.
- Creative Studio remains feature-flagged off by default.
- Workbench copy says hosted Comfy and does not claim local GPU execution.
- The macOS app does not embed ComfyUI, GPU workers, model storage, or workflow
  automation.
- Issue `#102` remains the implementation epic for the hosted Creative Studio
  product surface; VM-local/proxy canaries are future graduation criteria.
