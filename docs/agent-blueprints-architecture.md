# Agent Blueprints architecture

## Design decision

Create independently usable, technology-specific blueprints. Each owns its
framework runtime, tests, configuration, and deployment assets. Share
contracts and documented engineering patterns where they have demonstrated
value; do not hide MAF, LangGraph, or a harness behind a universal runtime.
Generated projects must not import this repository at runtime.

## Optional protocol context

Layer 5 exposes explicitly activated, typed read-only context registration for
AG-UI and CopilotKit. Only a fixed description and validated selected-case
status are supplied; adapters receive no workflow client or mutation
capability. Registration code is trusted, not sandboxed. The configured
consumer may disclose this status during a later agent run and is responsible
for cleanup, authorization, privacy, and avoiding automatic calls. This is
an AG-UI context input, not an event stream or a protocol-conformance claim.
See the [generated blueprint architecture](../blueprints/maf/workflow/docs/architecture.md#optional-protocol-context)
for supported boundaries and limitations.

## Optional studio projections

Layer 4 adds opt-in, application-owned typed evidence and synthetic-test
adapters. Evidence is rendered as text after authorized case selection;
the application must allowlist safe fields and must not return raw model,
tool, checkpoint, actor or sensitive payload data. The shell performs no
additional fetch and cannot verify that application-supplied values are safe.
Application-supplied manual-test execution is disabled in all environments.
This interim control is not an isolated synthetic execution capability:
application code is trusted rather than sandboxed, and a build flag or
omitting the workflow client cannot prevent network access or real effects.
A future implementation requires a separately verified isolation boundary.
Evidence projections are not authorization, artifact verification, or
evidence of production readiness.

The hosted failure runner validates and preserves optional HTTP status and
hosted phase metadata in correlation evidence for the independent App Insights
consumer. This shape compatibility is not evidence that live telemetry exists
or matches. Acceptance fault controls remain default-off and role- and
revision-bound, but a non-production environment boundary is not enforced.

## Live activity reconciliation

The Layer 3 stream is an authenticated, case-authorized invalidation channel,
not an event log or a commit-order cursor. It emits only a fixed refresh signal
and heartbeat; each tick revalidates the bearer token and the case read
policy, and the database connection is returned before the wait. The browser
uses bearer `fetch`, rescans the existing authorized activity projection, and
atomically replaces its snapshot instead of appending or guessing a commit
watermark. Audit identity values and transaction-start timestamps can precede
commit, so late commits require subsequent full scans. A scan concurrent with
inserts may be incomplete until a later scan; this is eventual reconciliation,
not a point-in-time or exactly-once feed.

Streams are limited to 30 seconds; a valid refresh on a stream sustained for
20 seconds resets the failure budget. Short or failed streams count toward
three failures, followed by ten-second polling; clients without a stream
implementation also poll. Token acquisition and
connection establishment have 15-second deadlines; idle reads have a
20-second deadline. Cancellation stops waiting for token acquisition and
prevents a late request, but cannot cancel MSAL's underlying token operation.
The server no longer submits synchronous identity or database calls to an SSE
executor. At most four async I/O operations and 32 streams run per process.
Each operation has a five-second cancellation deadline. Malformed token
headers are rejected before network I/O. Signing keys are read using async
HTTPS with a bounded response and cached for five minutes per application
identity; unknown-key and failed refreshes are throttled to once per 30 seconds,
with one fetch in flight. Expired keys are never a failure fallback. The existing
delegated-token validator runs locally on every tick. PostgreSQL uses separate async, read-only connections
with five-second connection, statement, and lock timeouts, never the API pool.
Each connection closes before the next tick. Managed-identity database
credentials and custom service/store/policy/identity implementations fall back
to authorized polling rather than invoking synchronous callbacks on this path.
This intentionally narrows streaming support; the Order Resolution profile
also polls.

Local regressions verify stalled HTTP cancellation/cleanup, cancellation of an
actual locked PostgreSQL read, server statement deadlines, read-only mode,
capacity recovery, token expiry, and policy revocation. These do not prove
platform DNS resolver cancellation, TLS/network black-hole recovery, or cloud
proxy behavior. The underlying async libraries may use executor-backed DNS.
Polling requests still use synchronous database work and client cancellation
does not stop that work on the server; repeated stalls can exhaust shared
capacity. End-to-end shutdown/network resilience and polling I/O deadlines
remain reliability blockers, not production-scale tuning.
Scans start no more often than every 15 seconds and are limited to 50 pages
and 60 seconds;
exceeding either limit surfaces an error instead of silently truncating.
Reconnection begins a fresh scan, and selection/account teardown aborts
in-flight work. The existing activity pagination cursor is validated but is
never treated as a stream watermark. No workflow effects or raw payloads are
sent. Local tests do not establish cloud proxy behavior, live Entra consent,
or production-scale limits.

## Locally integrated Azure/Foundry boundary

The [local integration acceptance](master-checklist.md#local-azurefoundry-integration-acceptance)
preserves three distinct stores: native MAF local checkpoints,
Foundry-managed hosted workflow state, and PostgreSQL business state.
Hosted execution calls the protected API with its service identity; only the
API identity accesses PostgreSQL. Opaque platform session/user/call context
does not grant human authority. Authenticated API prebinding and durable
decision intent remain required, including authorized terminal replay without
new Responses dispatch. There is no private SDK monkeypatch, invented hosted
checkpoint ID, shared runtime dependency, or public Foundry-to-database route.

The canonical API image owns its system-CA path through `SSL_CERT_FILE`.
Deployment cannot override that trust contract. A disposable PostgreSQL 17
fixture proves normal hosted application startup with `verify-full` and system
trust, and rejection of both hostname mismatch and an untrusted CA. This
proves local composition and TLS enforcement, not Azure identity issuance,
live Foundry checkpoint/recovery behavior, or production readiness.
The preserved original architecture HTML is not revised by this integration.

## Live acceptance boundary

The 2026-11-23 acceptance attempt verified the deployed immutable API/web
revisions, public HTTP boundaries, managed-identity database connection, active
hosted version, and exact-scoped RBAC. It did not verify a human-authorized
hosted workflow. Delegated API consent, authenticated browser state, reviewed
provider/result factories, and bounded live fault controls were unavailable.
Application Insights also identified the runtime as agent `0.1.0` and
deployment `local-unversioned`, so its rows cannot satisfy exact hosted
revision correlation. These are explicit blocked/failed evidence boundaries,
not reasons to collapse Foundry state, business state, authentication, or
approval into a shared runtime.

The remediation preserves those boundaries. Telemetry now binds the active
hosted agent version and immutable deployment revision and exposes only
privacy-safe W3C correlation identifiers. Synthetic fault controls are a
separate, default-disabled acceptance surface requiring delegated
`Acceptance.Operator`, an exact revision match, and hosted mode. They can
inject a PostgreSQL transient or one-shot hosted decision/effect
acknowledgement loss, but cannot create a refund or shipment outside the
existing synthetic destination. Because the controls are process-local,
live fault execution must pin the API to one replica; restart scenarios rely
only on durable business/hosted state after the process-local control is gone.

Positive approval and rejection evidence requires two distinct delegated
Entra users: an owner with `workflow.write` and a reviewer with
`workflow.approve` plus `Workflow.Approver`. The operator role does not weaken
owner/reviewer separation, and workload identities cannot substitute for a
human delegated token. Missing second-user credentials therefore remain an
external blocked prerequisite rather than an authorization bypass.

Live remediation confirmed that privacy-safe correlation and deployment
normalization do not require a shared runtime or broader identity. App Insights
corroborated an exact HTTP request ID, business case ID, W3C trace ID, hosted
agent version, and deployment revision without prompt or identity content.
Azure reconciliation independently bound the active immutable API/web images,
hosted `order-resolution:1`, and exact-agent RBAC scope. Hosted completion is
represented by the durable `hosted_workflow_finished` audit event; acceptance
normalization counts that event as the single terminal outcome while leaving
Foundry checkpoints external and PostgreSQL business state independent.

Deployment preserves the PostgreSQL `verify-full` connection string as one
opaque Azure CLI argument. On Windows, API updates bypass the `az.cmd` wrapper
and invoke the packaged Azure CLI Python module so the `&sslrootcert=system`
suffix cannot be reinterpreted by `cmd.exe`; this changes orchestration only
and does not weaken database TLS or identity boundaries.

Infrastructure and application rollout are also separated by an immutable
image guard. Subscription Bicep has no placeholder image defaults: callers
must provide both images. The guarded orchestrator reuses an existing
digest-pinned template, permits the bootstrap placeholder only before any
immutable revision exists, and refuses a placeholder template when immutable
application history proves that a live workload has already been deployed.

The hosted process relies on AgentServer's supported constructor-time
observability initialization. Application and MAF construction is lazy, so the
single Azure Monitor provider and supported HTTP instrumentation exist before
native MAF objects are created. Raw message capture remains disabled; durable
resume creates a new trace with an explicit link rather than fabricating a
cross-boundary parent.

### Accepted version-9 runtime boundary

The immutable rollout from
`a302e939810283bce47867b8fa088374f3d204ad`, validated by all seven jobs in
CI run `45275635199`, establishes the deployed runtime boundary without
collapsing its stores or identities. Active hosted `order-resolution:9` owns
Foundry execution and checkpoints. API revision
`aborsfoundpv2n45-api--a302e939` owns authorization and PostgreSQL business
state and uses only its managed identity for a `verify-full` TLS 1.3 database
connection. The unchanged web revision remains a separate public client. The
API and web image digests, hosted archive/publication digests, exact-scoped
roles, version binding, health, and protected `401` boundary are retained in
the deployment evidence; 32/32 deployment checks passed.

The two-case version-9 signal comparison passed 16/16 checks while preserving
the same architecture. The automatic trace completed with one database-only
synthetic effect and no real or external effect. The approval-required trace
stopped durably at `workflow.hitl_waiting` with no decision or effect and was
not resumed. Stable `workflow.run`, authorization, policy, proposal, approval,
effect, persistence, resolution-submit, and HITL-wait stages now describe the
business trajectory without raw content. Normal pooled borrows no longer emit
`database.connect`; physical connection creation and failure visibility remain.
Foundry, MSI, Azure SDK, and HTTP dependencies remain visible. Both trace
graphs resolve internally except for the expected external caller and
AgentServer platform-parent boundaries.

Network hardening remains a separate operational boundary. PostgreSQL public
network access is still enabled. Retained read-only evidence records the broad
temporary E2E rule, five existing single-address Container Apps rules, and 407
advertised environment outbound addresses. The repository's supported
migration tooling creates and removes a temporary exact-IP operator rule, but
that operator path and a sufficient API allowlist have not been jointly
validated with the broad rule absent. Firewall hardening is therefore
deferred, not silently treated as complete. No firewall or network mutation
was made. Human resume remains separately blocked until a distinct delegated
reviewer can prove approval and the durable trace link without weakening
authorization.

### Post-deployment hosted durability correction

The source branch now closes two local durability gaps; these corrections are
not present in the deployed `a302e939` artifacts. First, the transition to
pending, hosted binding update, audit record, and native decision-handle
binding share one PostgreSQL transaction. A failure during handle binding
therefore rolls the case and binding back instead of leaving an unbound
pending proposal. Replay locks the same rows and verifies or repairs an exact
legacy handle/channel binding before returning it.

Second, the hosted Responses client acquires its workload authorization token
before creating a fresh durable operation claim. A credential failure before
the request boundary now sends no POST and leaves no ambiguous claim; a later
retry may claim and submit exactly once. Once a request may have been sent,
the existing lost-ack rule remains fail-closed and requires reconciliation.

Focused PostgreSQL crash-window and durable-journal regressions, 63 source
hosted tests, 166 independently generated PostgreSQL/backend tests, 63
generated hosted tests, nine canonical ORS contract tests, and 105 repository
contract/readiness tests passed locally. The generated backend retained one
explicit provider-opt-in skip and the repository suite retained two documented
adapter-selection skips. This evidence changes no cloud state and does not
authorize deployment; a green exact-head CI run and a separately authorized
immutable rollout remain prerequisites.

## Open architecture and verification gaps

The engineering foundation is not a deployment-readiness claim. Open work
includes [hosted caller binding #22](https://github.com/ppenumatsa1/agent-blueprints/issues/22),
[native hosting and checkpoints #19](https://github.com/ppenumatsa1/agent-blueprints/issues/19),
[hosted recovery #20](https://github.com/ppenumatsa1/agent-blueprints/issues/20),
[external effects #32](https://github.com/ppenumatsa1/agent-blueprints/issues/32),
[independent trust #21](https://github.com/ppenumatsa1/agent-blueprints/issues/21),
[agent evaluation and browser evidence #25](https://github.com/ppenumatsa1/agent-blueprints/issues/25),
and [deployment integration #18](https://github.com/ppenumatsa1/agent-blueprints/issues/18).
Reusable MAF extension contracts for model, agent, prompt, tool, and executor
patterns are tracked in [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35).
The permanent standalone reference application is a P1 deliverable with
separate repository authorization [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30);
consequential external effects are P0-blocked pending authorization and
idempotency evidence [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32).
See the [master checklist](master-checklist.md#reconciled-engineering-backlog)
for the complete issue-linked backlog, including live identity, telemetry,
database operations, evaluations, and separately authorized alternatives.
The dated [issue and fix journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---issue-and-fix-status)
distinguishes local and draft-PR evidence from merged or hosted capabilities.
Do not conflate an approved engineering merge with verified hosted execution,
human approval, or production readiness.
Merged [PR #40](https://github.com/ppenumatsa1/agent-blueprints/pull/40)
defines Order Resolution terminology and requirements. The separate
[versioned executable fixture](../scenarios/order-resolution/README.md)
encodes its normalized business outcomes and keeps framework/runtime execution
assertions distinct. It is not this blueprint's business implementation;
order-adjustment remains an independent legacy fixture.

## Azure/Foundry Workstream C

The cloud application architecture keeps framework and identity concerns at
narrow composition boundaries. `WorkflowHost` remains the use-case port.
Local mode selects the existing MAF/FileCheckpointStorage host. Hosted mode
loads Agent A's API-only bridge/client copied into the generated backend; the
API does not import the sibling hosted runtime or hosting SDK. Without that
backend-native adapter the API fails closed. No generic `/runs` transport or
second hosted orchestration path is supplied. Foundry SDK types do not enter
API, policy, service, or persistence modules.

FastAPI validates and authorizes the end user before hosted dispatch.
Foundry calls use an explicit `ManagedIdentityCredential` for the configured
API UAMI; PostgreSQL token acquisition remains constrained to that UAMI. That identity calls Agent A and is the
sole runtime principal allowed to acquire an Azure PostgreSQL token, but it
cannot authorize a user action. Agent A's hosted execution identity remains
separate, owns hosted checkpoint/session state, and calls only the protected
FastAPI hosted-state API with the fixed `Hosted.Workflow.Invoke` app role. It
receives no database configuration or role. Order Resolution's synthetic
downstream identity is application-owned and receives no user, API, or hosted
credential.

PostgreSQL stores business state plus opaque operation/execution/request
correlation, never MAF checkpoint bytes. Dispatch is claimed before send.
The API container installs the Debian CA bundle and exports
`SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`; this is a trust-store
discovery hint for bundled libpq/OpenSSL, not a TLS-policy override.
`PGSSLROOTCERT=system` and `verify-full` remain the application contract.
Ambiguous acknowledgments remain unknown and are reconciled by operation ID
after restart rather than replayed. The native hosted workflow owns action invocation; PostgreSQL verifies and
projects the idempotent business outcome, preserving the action ledger and
proposal/action/destination binding. See the
[security and configuration contract](azure-foundry/application-security.md).
Hosted approvals use a separate business projection: an opaque request ID,
case/conversation binding and decision channel are durable, but
local `checkpoint_id` and `terminal_checkpoint_id` remain null because Foundry
owns native checkpoint/session state.
The binding is established only by an authenticated human API command after
the server selects the conversation. Service-MI binding routes verify that
existing owner/reviewer authority and cannot manufacture it. Resume persists
a hashed, expiring, proposal-bound human decision intent before dispatch; only
an exactly matching hosted callback records the business decision.
Hosted platform user, session, and call values remain opaque workload
correlation. They never identify the human principal; changing a platform call
ID does not change or conflict with an otherwise identical durable business
operation.
An identical approved or rejected human command after terminal projection still
passes through the bridge: C reauthorizes the durable reviewer binding and
exact intent, then Agent A's journal returns the acknowledged Responses result
without another network dispatch or effect. Changed principals, conversations,
channels, or decision commands fail closed.
The internal base `/api/internal/hosted/v1` exposes only case-bound
start/resume, read/proposal, approval/decision, effect-projection, and
completion operations. App-only tenant/issuer/audience/principal/role checks,
exact binding checks, and durable case-bound idempotency keys protect that
surface. Agent A's native `ResponsesClient` uses C's narrow
`PostgresOperationJournal` inside the API process; there is no generic `/runs`
transport and no hosted-to-PostgreSQL connection.
The topology is implemented and locally tested, but Azure identity, RBAC,
networking, managed PostgreSQL, hosted execution, and telemetry remain
unverified until an authorized integrated deployment.

## Azure/Foundry Workstream B

The prepared Azure topology preserves the application/runtime boundaries:

```text
Public React Container App
  -> Entra-protected public FastAPI Container App
  -> Foundry project and explicit model deployment

FastAPI -> PostgreSQL Flexible Server: business state and approval/effect data
Foundry Hosted Agent -> framework-owned hosted execution/checkpoints
All services -> workspace-based Application Insights and Log Analytics
```

East US 2 is the selected single region. Public networking is deliberate for
this milestone, with TLS, API platform authentication, managed identities,
least-privilege roles, Key Vault references, and exact-IP PostgreSQL firewall
configuration. No VNet, private endpoint, private DNS, or private runner is
included. A failure of deployment-specific capacity in East US 2 stops the
deployment; it does not authorize an implicit cross-region topology.

The infrastructure exposes typed deployment outputs to the independent
runtime, application, and evidence workstreams; it does not add a shared
runtime. The supported Azure CLI route generates a new independent Order
Resolution project, publishes its Agent A hosted source, and builds its Agent C
API/frontend contexts. It never deploys the source blueprint. The generated
Agent A's generator owns a byte-identical API-side Responses client/bridge copy
inside the backend context; B validates rather than creates that boundary.
Hosted source remains separately publishable, and the API does not import the
full hosted runtime or rely on a sibling `PYTHONPATH`.
The generated frontend's Compose upstream is replaced only in the temporary
generated copy with the exact API HTTPS FQDN. Exact deployment, trace,
evaluation, and browser
evidence remains with Agent D. Conversation state, hosted framework
checkpoints, PostgreSQL business state, and human approval remain separate.

The deployment plan is `Validated`, not deployed or production ready.
Validation used the active authorized Azure CLI context and passed live
identity, provider, region, quota, capacity, policy, subscription deployment,
and what-if checks. The current azd account and tenant still differ from Azure
CLI; Azure CLI mode reports that mismatch and explicit azd mode fails closed.
PostgreSQL Flexible Server accepts one control-plane child operation at a time
during provisioning. The module therefore serializes Entra administrator, TLS
configuration, database creation, and optional firewall rules; this ordering
does not merge checkpoint state with business state or grant the hosted
identity database access.
Cloud configuration requires hosted
workflow mode, managed-identity PostgreSQL with TLS verification, an explicit
adapter endpoint, and agent-scoped API access. `BLUEPRINT_APPLICATION`,
`CHECKPOINT_ROOT`, and local workflow hosting are excluded.
Hosted publication is staged after the protected API business-state boundary
is deployed. The platform identity receives only a dedicated API application
role before active readiness polling; it receives no PostgreSQL URL, role, or
firewall access. Only API Container App outbound IPs are allowlisted. Agent
Consumer assignment uses the official exact agent scope derived from validated
project output and the fixed publisher name; parent or another-agent scopes are
rejected.
The hosted application role establishes service identity only. Human authority
remains server-bound to the exact principal/case, server-selected conversation,
and channel before any Responses dispatch. Foundry user/session/call values are
opaque platform correlation and continuity, not human authority; the API bridge
sends no caller-selected session or actor metadata.
See the
[infrastructure evidence and operator contract](azure-foundry/infrastructure.md).

## MAF modularity foundation and target

The local blueprint and its generated copy now have sibling `backend` and
`frontend` build contexts. The backend separates API composition, use cases,
generic domain ports and policy, native MAF workflow/host, and PostgreSQL and
identity infrastructure. Application factories and transactional-action
interfaces remain the extension boundaries; use canonical module imports.
Python project metadata, lock, examples, migrations and backend tests are owned by
`backend`.
The verifier and exact contract bytes remain independent of the runtime.

UX stack Layer 1 keeps the frontend independently deployable and adds no
shared runtime. A generation-time `WorkflowStudioProfile` supplies generic
titles, descriptions, labels, disabled capability flags, safe payload
projection/rendering, and optional application-owned decision binding.
`StudioShell`, `RequestComposer`, `CaseSummaryPanel`, `ApprovalPanel`, and
`CaseMetadataPanel` reuse the existing protected `WorkflowClient` contract.
MSAL token acquisition, delegated scopes, API paths, server-authoritative
record authorization, reviewer UUID validation, secure idempotency reuse,
approval/rejection, and recovery remain outside profile control. UX Layer 2
adds versioned generic history and activity projections over the existing
`wf_cases` and `wf_audit` tables. Fixed list SQL constrains tenant, owner, and
assigned reviewer for candidate selection; the configured application read
policy is then applied to each complete candidate before public pagination
and cursor metadata are derived, with a budget of 1,000 candidates over 10
batches of at most 100. Budget exhaustion before the authorized page is
complete returns a generic 503 rather than partial history or a cursor.
Activity repeats record authorization and maps only committed allowlisted event
names. Both projections omit
payloads, actor IDs, request/checkpoint IDs, and model/tool content. The
profile-driven sidebar and timeline use the same delegated read client and
discard stale responses. Evidence, manual tests, AG-UI, and CopilotKit remain
disabled flags. The generated repository owns all profile/component source
and has no runtime or source dependency on this repository or the reference
repository.

The tooling branch adds a Python 3.12 uv lock, Ruff, portable development
commands and editor configurations. CI uses the public lock; container
installation exports its exact hashes and may use an operator-selected index.
The copied project owns the same lock and does not import the source checkout.
Local Windows and Linux-container checks do not prove macOS. Hosted
[run 44940616666](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44940616666)
passed all five checks for tooling head `b78634b`, not this combined revision.
Security-hardened PR #11 merged to `main` as
`587e6cc1abc23a67845c8193d486cc65c8b52854`. Its MAF core approval guard is
integrated with the canonical uv lock: source and generated installations
reject the compromised `agent-framework` umbrella distribution and verify the
approved core wheel digest against the lock and downloaded artifact before
installation. The lock remains the sole dependency graph. PR #17 is merged
into `main` at `0c1297cc8e93c62f69d61d0eb3bdabf3c27c683d`; exact-main
[run 45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271)
passed all six jobs for that baseline. PRs #36, #37 and #40 are now merged;
current `main` is `49932ee0cd61ee653a5f86be0f43873cec197ff9`, with exact-head
run [45041465032](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45041465032)
passing all six jobs. PR #39 is being reconciled directly onto this baseline;
its exact-head CI is required independently. Earlier PR #17 head and
merge-ref checks are historical snapshots; changes on top of this baseline
require fresh validation. Local evidence is recorded in the
[integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---main-reconciliation-and-local-validation);

Revision-bound release evidence has a stricter source boundary than ordinary
pull-request merge validation. The `maf-independent` evidence producer checks
out the pull-request head explicitly before generating and hashing artifacts;
the manual cloud workflow then requires that same source revision plus the
immutable deployment revision. A merge-ref artifact cannot be relabeled as the
deployed head and must remain unusable until regenerated.

The longer-term target adds a Foundry Responses adapter and host-managed
checkpoints, neither of which is implemented. Staged Foundry-first Bicep/azd describes
separately hosted frontend and API services and has credential-free static
checks, but does not implement a hosted agent or a working cloud integration.
Hosting the workflow runtime in ACA is a deferred alternative requiring its own
verified checkpoint strategy. Neither topology is a verified deployment;
provisioning requires separate authorization.

[PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11) and PR #17
are merged to `main`. The cleaned foundation commit `9efeef0` removes the compatibility aliases and
uses canonical imports. Follow-up foundation commit `d0e1727` fixes propagation
of generated-verifier failures through CI's `tee` pipeline and adds regression
coverage for failure, skipped, expected-failure, and success outputs; its
[actual-head run 44939172266](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44939172266)
passed all five checks on that exact commit. These are CI results, not a merge
or live hosting result. PR #11 subsequently split API composition, assembly,
routes, schemas, dependencies, middleware/errors, and lifecycle into canonical
modules at `44ee18b`; its `contracts` run failed on the now-deleted
`backend/app/api.py` documentation link while the other four jobs passed.
The source map was corrected in the PR #11 follow-up at
`814491811eac457826108b70fc213fdc564af0e5`; the owner reports root tests
passed 47/47 on that tip. Actual-head run
[44945419570](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44945419570)
passed all five checks, including generated checks without skips. PR #12
based on that foundation passed all five jobs on exact head
`c247bf737acabe47e7af0023eaebf69c0b393fdf` in
[run 44946550709](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44946550709).
The copied
[project guides](../blueprints/maf/workflow/README.md#project-guide) describe
the current local boundaries and staged deployment design.
Their [design baseline](../blueprints/maf/workflow/docs/design/architecture.md)
maps requirements to source and evidence; its engineering journal records
verified findings and remaining work. The generated-copy tests include the
design documents and validate local links. Parallel tooling, migrations,
telemetry and Foundry-host work build on the foundation. Validate each
resulting revision independently. Prepare
inventory, cost and a deployment plan for separate approval before
provisioning or live validation.

The observability increment adds independently owned OTel trace and metric providers
in the MAF backend, JSON operational signals, incoming W3C trace context, and
explicit Azure Monitor trace and metric export configuration. Metrics have only
allowlisted operation/outcome dimensions and no exemplars. Missing or invalid
hosted exporter configuration fails startup; transient export failure is
reported without changing workflow outcomes. It does not export locally
by default, configure cloud resources, or establish hosted ingestion. Browser
requests create a trace context without exporting a browser span. Outbound and
Foundry-host propagation remain unverified; operational logs are
not business audit or authorization evidence. See the [blueprint guidance](../blueprints/maf/workflow/README.md#operational-telemetry).

The migration increment adds an Alembic `0001` baseline for PostgreSQL
business tables. An explicit schema-owner migration initializes empty schemas
or adopts exact unversioned baselines, then upgrades to head. A catalog
manifest per revision detects drift before and after the upgrade, and the API
validates head without DDL. Migration and validation coordinate through
transaction-scoped advisory locks; manual DDL and running old binaries still
require operational quiescence. Identity requirements, backup and rollback limits,
and scope of drift detection are in the [blueprint](../blueprints/maf/workflow/README.md#business-database-migrations).
These migrations do not own MAF checkpoints or independently authorize
business approvals. The migration PR is stacked on the modularity foundation;
live operational recovery remains unverified. A deterministic
checkpoint timestamp-tie defect was fixed in foundation `9efeef0`; the exact
causes of earlier intermittent evidence failures remain unproven. Local
source and generated tests passed on PostgreSQL 16.15 and 17.12 at `7cd99ac`;
this does not verify Azure database configuration or live restoration.

The #35 MAF extension patterns keep only application-owned model-selection
configuration, explicitly versioned prompt assets, and request-scoped
authorization around direct MAF `Agent`, `@tool`, `Executor`, and
`WorkflowBuilder` APIs. Redundant `ModelClientFactory`, `AgentDefinition`,
`build_chat_agent`, and `ToolRegistry` wrappers are removed; the host retains
workflow identity, response contract, and `FileCheckpointStorage`. The
generated synthetic fixture exercises construction, affirmative authorization,
approval/rejection, restart and crash recovery without a model call or
fabricated response. Arbitrary trusted Python callbacks are not sandboxed, so
absolute non-bypass remains unverified. Provider credentials and behavior,
live hosted identity and recovery, trusted readiness evidence, and consequential
external effects remain unverified or blocked; see the
[MAF extension guidance](../blueprints/maf/workflow/docs/architecture.md#typed-maf-extension-patterns).
Evaluation stays separate from #37; downstream evaluation uses native MAF
`Evaluator`, `LocalEvaluator`, `@evaluator`, and `evaluate_agent()` APIs.

The local #25 follow-on adds application-owned, versioned evaluation dataset
and rubric contracts, explicit score thresholds, and trace mapping to existing
readiness check IDs. Callers must supply the unique IDs from the selected
readiness contract before mapping or unavailable-result reporting; the set
establishes consistency, not trusted authorization. Unknown matching
dataset/rubric IDs are rejected before native evaluator invocation.
Applications invoke the standard MAF evaluation APIs directly; this extension
owns no evaluator protocol or orchestration wrapper. Missing observations and
unavailable native results remain unverified, while invalid, unknown,
duplicate, malformed, or below-threshold observations cannot pass. Oversized
integer thresholds are rejected and oversized scores fail closed. Evaluator,
provider, and tool exceptions propagate without synthetic fallback. Trace
references are not evidence bytes or authenticated provenance. Source and
generated tests exercise MAF's native local evaluator with explicitly
synthetic responses; they do not represent live model quality, a browser
end-to-end run, independent evidence trust, or hosted validation.

Local PostgreSQL container initialization can briefly accept Unix socket
connections before the final TCP server starts. Issue [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38)
records this on disposable PostgreSQL 16.15 and 17, including a failed initial
`createdb` and a successful 72/72 source/generated retry at historical head
`8b3c357`. CI startup loops and Compose health checks use bounded loopback TCP
probes; these remain in current `main` at
`49932ee0cd61ee653a5f86be0f43873cec197ff9`, whose exact-main run
[45041465032](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45041465032)
passed all six jobs. This does not establish managed PostgreSQL readiness.

The local integration at `af3955a` combined the engineering layers. Source and
independently generated backends each passed 68 tests on PostgreSQL 16.15 and
17.12, generated verification passed 44 without skips, and both Compose stacks
and offline infrastructure checks passed. The unsigned independent readiness
report remained unverified. See the [integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---combined-engineering-layer-integration)
for failed attempts and scope. These are historical local results; current
merged-main CI and the separate #37 validation are recorded independently.

| Layer | Responsibility | Examples |
| --- | --- | --- |
| Agent definition | Instructions, goal, tools, skills, permissions | A bounded diagnostic agent |
| Framework | Native agent and workflow primitives | MAF, LangGraph, Copilot SDK |
| Execution strategy | How the work proceeds | Single agent, explicit workflow, harness |
| Runtime | Sessions, execution state, isolation, recovery | Framework or hosted runtime |
| Hosting | Where the runtime and adjacent services execute | Foundry Hosted Agents, Container Apps |
| Application | Business policy, authorization, durable records, verified side effects | FastAPI and PostgreSQL |

Do not treat conversation history, workflow checkpoints, and business records
as interchangeable. A model recommendation or remembered conversation is not
human authorization.

## Cross-framework business specification

The [Order Resolution specification proposal](order-resolution-specification-proposal.md)
defines a framework-neutral triage, policy retrieval, deterministic resolution,
human decision, idempotency, recovery, and evaluation contract. It standardizes
business invariants and evidence expectations, not runtime APIs or checkpoint
bytes.

The executable `order-resolution-spec/0.1.0` acceptance fixture carries exactly
`ORS-001` through `ORS-009`. It fixes the synthetic policy arithmetic and
business outcomes while leaving native checkpoint identity and implementation
evidence to each framework mapping. Merged
[PR #42](https://github.com/ppenumatsa1/agent-blueprints/pull/42) carries the
fixture and root acceptance tests. Passing those tests validates the contract
encoding only; it does not prove a blueprint implementation, authorization,
side effects, or readiness.

Merged [PR #44](https://github.com/ppenumatsa1/agent-blueprints/pull/44) maps
that contract to one explicit MAF generation profile without adding a registry,
template compiler, plugin runtime, or source-repository dependency. The
generated application owns deterministic rules, authenticated FastAPI routes,
PostgreSQL business state, native `Executor`/`WorkflowBuilder` composition,
host-owned file checkpoints, and React rendering. Local generated-project
tests execute the canonical fixture through the real API, workflow, and
database.

Merged [PR #41](https://github.com/ppenumatsa1/agent-blueprints/pull/41) adds
the application-owned durability layer without changing MAF checkpoint
ownership. PostgreSQL stores request claims, versioned proposals, bound
decisions, effect status, authorization audit records, action projections, and
the synthetic downstream result. The effect key is derived from case,
proposal version, action, and destination. One bounded deadline covers
observation and send; timeout or termination after send is `UNKNOWN` until an
authoritative observation proves `APPLIED` or `ABSENT`. This is a verified
synthetic pattern, not a claim about a real payment or fulfillment service.

Draft [PR #43](https://github.com/ppenumatsa1/agent-blueprints/pull/43)
integrates evaluation and readiness into the independently generated project.
It uses the native MAF `Evaluator`, `LocalEvaluator`, `@evaluator`, and
`evaluate_agent()` path plus the merged #39 result mapper. A versioned dataset
references all nine canonical scenario IDs and derives expected outcomes from
the generated golden cases. The evidence producer records exact deterministic
business and technical results, while real model quality, browser execution,
and independently trusted provenance remain separate and unverified.

Every future implementation must use its selected framework's native workflow
and checkpoint provider. PostgreSQL is application-owned persistence for
business records, decisions, action ledgers, and audit projections; it is not a
universal/custom checkpointer. A framework may select a supported PostgreSQL
checkpoint provider, but that framework-owned state remains logically separate
from the application schema and lifecycle.

## First golden path: Foundry-first MAF workflow

This is a **design**, not a verified deployment:

```text
Browser / React
  -> authenticated and authorized FastAPI boundary
  -> Foundry Hosted Agent: native MAF workflow via Responses
  -> Foundry workflow checkpoint/session store

FastAPI / workflow -> PostgreSQL: business state, approval, action ledger
                   -> OpenTelemetry / Application Insights
```

The application validates inputs and authorization, persists the approval
decision, and only then permits a consequential, idempotent action. A pause
returns control rather than keeping a model call open. Approval identity,
business state, workflow continuation, and side-effect verification must be
correlated without making a model or client-supplied identity authoritative.

For Foundry's native Python workflow host, follow the current
[hosting guidance](https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent):
use a request-aware workflow factory, stable workflow/executor identities, and
the host's checkpoint provider. Do not also configure an independent workflow
checkpoint store for host-managed recovery. Application-owned PostgreSQL
records remain separate from host-managed workflow state. The PR #15
workstream owner reports the documented Responses-host pattern uses
`ResponsesServerOptions(resilient_background=True)` with Requests
`store=true, background=true`; this is design guidance, not an implemented
host in this repository. No Responses service/dependency, workload networking,
or hosted lifecycle is present, and package/API compatibility requires
verification before claiming durability.

The proposed caller-binding direction requires the authenticated API to
authorize the caller and send Foundry workload Authorization plus an opaque
app-supplied `x-ms-user-identity` scoping value derived from the validated
principal. The hosted container receives a different, platform-injected header,
`x-agent-user-id`; protocol 2.0.0 exposes that platform identity as
`get_request_context().user_id`. Neither header establishes authorization,
and their equivalence or mapping to the validated principal is unsupported and
unverified. A trusted application must authorize each principal's session,
map callers to distinct sessions and reject unchecked client session IDs.
The caller needs Foundry Agent Consumer and custom
`UserIdentityImpersonation/action` authorization. Do not persist end-user
bearer/OBO tokens in business state, checkpoints or logs. The identity bridge,
session binding and role assignment are not implemented or live verified;
track [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22).

Hosted response recovery remains blocked: a visible matching metadata record
may reveal `response.id`, but an empty paged conversation list has no
documented bounded read-after-write visibility and cannot prove creation
failed. Conversation creation has the same lost-ack ambiguity, and a lock
cannot make remote creation atomic with the application database. No
Responses-create idempotency key or safe unambiguous recovery contract is
documented. Local business idempotency does not solve hosted response identity
recovery; do not silently retry. See the [hosted blocker
journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---hosted-caller-binding-and-lost-responses).

### Azure/Foundry Workstream A

The Order Resolution profile now generates a separate native MAF Responses
host and deterministic source bundle. The host uses a request-aware workflow
factory and the standard Foundry checkpoint provider; it never attaches local
filesystem checkpoints or writes whole workflow state to PostgreSQL. The
application still owns human authorization, decisions, effects, and business
records behind its protected API.

The authenticated API creates the server-selected Responses conversation and
prebinds the validated owner or reviewer to the exact case, conversation, and
channel before dispatch. Requests omit caller-selected `agent_session_id`;
Foundry associates the conversation with its stable hosted session. Platform
user, session, and call values are retained only as opaque workload
correlation and cannot mint a human principal or role. The hosted container
resolves the pre-established conversation binding and never receives
PostgreSQL connectivity.

Responses and hosted-version creates use application operation journals. An
acknowledged identical terminal resume is reauthorized against the exact
stored intent and returns through the existing operation without another
Responses dispatch; conflicting content and unauthorized actors fail closed.
Lost acknowledgments become `unknown` and are not replayed; only an
authoritative unique remote match may reconcile them. Exact local A/C
compatibility and its limits are documented in
[the hosting report](azure-foundry/hosting.md). Live hosted identity,
checkpoint recovery, model calls, telemetry and networking remain unverified
and cannot support production readiness.

The fallback hosts the framework runtime in Azure Container Apps and selects a
tested framework-compatible checkpoint strategy. Do not assume that its
checkpoint mechanism is identical to Foundry's. React, FastAPI, and PostgreSQL
remain independent components. Local development uses explicit local services
and synthetic data; an offline scripted mode must be selected explicitly, never
used as a silent replacement for a failed model call.

The staged resource graph chooses restrictive defaults rather than enabling
the earlier public-network design: optional ACA UI/API ingress is internal,
Foundry public access and monitoring public ingestion/query are disabled,
and PostgreSQL uses private networking and Entra-only authentication.
Foundry and monitoring private paths, application database token support,
and the hosted-agent binding are missing; these services are not a connected,
working topology. The optional registry remains publicly network-reachable
with anonymous and admin access disabled. The API's project-wide
agent-consumer grant is optional and disabled by default; review narrower
agent scope, inherited grants, and actual caller restrictions.
The staged PostgreSQL server selects major 16 while local Compose uses 17.
A separate migration revision passed 12 local PostgreSQL 16.15 tests,
including upgrade and drift; the Azure target remains unverified. The
[version-gap review](../blueprints/maf/workflow/infra/README.md#open-postgresql-version-gap)
does not claim live Azure support.
Any future public API still requires Entra-backed authentication,
application authorization, restrictive CORS, and safe secret handling.
See the [infrastructure guide](../blueprints/maf/workflow/infra/README.md).
No Azure provisioning is authorized by this design.

## Blueprint-to-application boundary

The Phase 1 deliverable is a reusable, independently runnable MAF workflow
blueprint, not a customer-specific application. A generated project owns its
application, framework runtime, dependencies, tests, configuration, and a
copied independent readiness validator and contracts. It must build and run
without importing or mounting this repository. The order-adjustment scenario is
only a synthetic test fixture; business rules and tools are application-owned.

The local design uses MAF's native `FileCheckpointStorage` on a persistent
single-host volume and keeps business records, decisions, audit history, and
idempotency in PostgreSQL. Local checkpoints and database transactions are
not atomic; recovery must reconcile them without unauthorized or duplicate
actions. The future Foundry host owns its own checkpoint provider and must
not attach the local store. The Foundry adapter and managed recovery remain
unverified P1-12 work; ACA checkpoint selection is separate.

The [local core](../blueprints/maf/workflow/) now constructs a fresh native
workflow per case and restores its recorded pending request before delivering
a PostgreSQL-backed decision. A per-case PostgreSQL advisory lock spans the
file/database boundary; a transaction commits the application-owned
database action together with its unique ledger entry. Tests terminate and
restart real workers at both specified commit windows. This applies only to
database effects in the same transaction, not arbitrary external services.
The local host uses MAF's lineage-aware latest selection during interrupted
start recovery and the executing workflow's last persisted checkpoint after
a run, rather than assuming timestamps are unique. It rejects incomplete
terminal checkpoints at completion and replay. Missing or corrupt checkpoints
fail visibly. The application increment adds the Entra API, MSAL UI, and a
loopback-only Compose stack with a non-root API and a private persistent
checkpoint volume. Local HTTP smoke checks are not live identity verification.

The [generator](../scripts/instantiate_maf.py) copies the blueprint, license,
independent verifier, contract bytes, and synthetic acceptance fixtures into a
new directory outside the source checkout. The copy owns its dependencies,
build contexts, framework host, application extension points, and verification
assets; it does not install a shared factory runtime. A test-only adapter
drives the actual API and native workflow. Its evidence producer retains
per-case results and both worker-kill outcomes, but its unsigned output and
synthetic approval records do not establish trusted provenance or human
authorization. The generated-verifier CI step propagates failures through
its evidence-capture pipeline and rejects skips; see the
[pipeline regression](../tests/test_ci_workflow.py). Fixture-formatted
explanations and hints are not agent evaluation or browser end-to-end
evidence, so those checks remain unverified.
The temporary generated copy builds, runs, and tests locally without source
imports or bind mounts; live identity and browser end-to-end verification
remain in progress.

Interactive local and hosted access uses Microsoft Entra ID: React uses MSAL,
and FastAPI validates access tokens, scopes, roles, and record-level access.
Synthetic identities are confined to automated tests. Existing registrations
and authorized sign-in are prerequisites for interactive use; no registration
or Azure resource is created by this blueprint. The frontend receives public
configuration at build time; secrets and optional OBO token exchange remain
server-side. The supplied synthetic action is selected explicitly and can be
replaced without importing the source repository.

## Shared versus framework-specific

| Candidate | Decision |
| --- | --- |
| Requirement IDs, schema and readiness vocabulary | Share as versioned contracts |
| Auth, telemetry, tests, documentation and deployment conventions | Share guidance and, later, small composable templates when justified |
| Workflow graph, interrupts, checkpointing and recovery | Keep framework- and host-specific |
| Model/tool loop, skills and session lifecycle | Use the selected framework or SDK natively |
| Business policy, approvals and side effects | Share the [Order Resolution invariants](order-resolution-specification-proposal.md) where applicable; keep concrete policy and enforcement in the generated application, not prompts or a shared agent runtime |

The reference projects contain reusable patterns but also scenario-specific
logic and settings. See the [evidence inventory](reference-repository-analysis.md)
before copying anything; preserve any applicable license notices.

## Proposed future structure

Documentation, contracts, a synthetic scenario, an independent readiness
validator, tests, CI, and the in-progress MAF workflow blueprint currently exist.
Other blueprint directories below remain proposed:

```text
agent-blueprints/
  docs/                    # architecture, standards, catalog, backlog
  contracts/               # proposed manifests, verification and readiness
  readiness/               # independent local verification CLI
  scenarios/               # synthetic contract and acceptance fixtures
  blueprints/
    maf/workflow/          # in-progress local workflow blueprint
    maf/harness/
    foundry-sdk/agent/
    langgraph/workflow/
    deep-agents/harness/
    copilot-sdk/harness/
  components/              # only proven framework-neutral material
  templates/               # composable local, deployment, CI and docs assets
  examples/                # synthetic, independently usable examples
  scripts/                 # blueprint instantiation utilities
  .github/                 # Copilot instructions and GitHub-hosted CI
```

Phase 1 will copy the selected blueprint and verification assets into an
independently buildable project. Specification Studio integration remains
Phase 6 work.

## Azure/Foundry Workstream D

The observability boundary uses one process-global OpenTelemetry provider per
runtime. AgentServer configures its supported Azure Monitor exporter and HTTP,
HTTPX, urllib, and Azure SDK instrumentation before native MAF instrumentation
is enabled on that provider. The API reuses its process-global provider and
injects W3C context into the Foundry request. A request UUID starts at the API;
a case UUID is added only after the application has established it. W3C
trace/span IDs, conversation ID, hosted agent version, and deployment revision
bind technical evidence, but none authorizes a user, approval, case, or side
effect. Technical status and business outcome remain separate.

Native MAF instrumentation is enabled only with sensitive-data and message
capture disabled. The hosted `invoke_agent` root, native workflow/executor and
message spans, and application workflow-stage spans share the global provider.
Durable HITL resume starts under its new hosted root and carries an explicit
OpenTelemetry link to the persisted start span; it does not fabricate a parent
chain across the durable boundary. Model usage is required only when the real
production path invokes a model. Prompts, completions, credentials, SQL,
exception messages, arbitrary baggage, and business payloads remain excluded.
The local Order Resolution host validates the complete persisted request
identity—case plus deterministic local conversation—when it first observes and
later restores a checkpoint, so adding durable correlation metadata cannot
silently disable recovery or weaken the checkpoint binding.
Application Insights verification requires a connected OperationId/ParentId
tree, conversation continuity, deployment metadata, restart links, privacy
checks, and matching Foundry trajectory trace IDs.

Hosted request finalization uses AgentServer's supported awaited async flush.
The default background flush is not sufficient for a hosted sandbox that can
suspend immediately after returning a response: a live version-2 trace retained
W3C identifiers in downstream API callbacks while every hosted parent span was
absent. Publication therefore fixes `AGENTSERVER_FLUSH_MODE=async` rather than
adding another provider, exporter, telemetry framework, or manually recreated
MAF spans. This preserves one process-wide pipeline and native semantic spans;
the only application-owned spans are bounded business anchors and the only
durable-boundary relationship is an explicit OpenTelemetry link.

Application Insights has local authentication disabled, so the hosted
publisher also fixes AgentServer's supported
`APPLICATIONINSIGHTS_AUTH_MODE=entra` environment selection. The pinned
AgentServer path creates `ManagedIdentityCredential()` and supplies it to the
Azure Monitor distro; the deployment orchestrator grants that hosted-version
identity only `Monitoring Metrics Publisher` at the exact Application Insights
component resource ID. No subscription- or resource-group-scope telemetry role
is permitted. API telemetry metadata prefers the deployment-bound
`HOSTED_AGENT_VERSION` over the compatibility `AGENT_VERSION` value so an
immutable hosted publication and the API trace label cannot silently diverge
after the coordinated deployment completes. Sensitive and message-content
capture remain disabled.

Release evidence is a separate architecture layer, not runtime state. Its
manifest is diagnostic and non-authorizing: it validates immutable files and
divides readiness into implementation, Azure runtime, and production
dimensions while permanently blocking production authorization. Cloud evidence
must match one exact source revision, environment, and immutable deployment
revision. Implementation evidence cannot establish Azure runtime readiness.
Deployment preflight accepts only identity, subscription, tenant, user, and
region inputs; directory object IDs remain scoped to the later Entra
configuration operation instead of broadening the preflight contract.
Generated deployment work is required to live outside the blueprint repository
so the independent-project guard remains meaningful; callers supply a durable
evidence root rather than falling back to an operating-system temporary path.
PostgreSQL principal and firewall configuration is a separately selectable
deployment stage so an immutable application-only rollout does not replay
one-time database administration; skipping that stage does not relax runtime
TLS, managed identity, or post-deployment health verification.
Production authorization remains solely with the baseline-pinned trust
validator, signed result attestations, and scoped, unexpired risk decisions;
self-authored review files cannot waive critical or security-critical gates.

The manual cloud workflow does not provision, deploy, change traffic, retry an
ambiguous business operation, roll back, or change PostgreSQL firewall rules.
Its destructive hosted failure adapter is opt-in and defaults off, with a
hard stop before Azure authentication or adapter execution until a trusted
source-to-image/hosted provenance verifier exists. Its planned target checks
require an exact active revision and a configured synthetic-nonproduction
Container App target under a dedicated protected GitHub environment and scoped
OIDC identity. The deployment evidence run must match a configured trusted
workflow path; no in-repository workflow currently produces that artifact.
These declarations do not prove isolation: required environment reviewers, the
deployment producer, federated identity/RBAC scope, and the adapter's actual
target behavior must be independently configured and verified before
dispatch. Agent A supplies native hosted
lifecycle and reconciliation semantics; Agent B supplies immutable
revision/resource evidence and telemetry endpoints; Agent C supplies
authenticated application/database behavior and bounded synthetic fault
controls. See the
[Workstream D readiness guide](azure-foundry/readiness.md) for executable gates
and the current blocked/unverified matrix.
