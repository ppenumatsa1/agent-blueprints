# Agent Blueprints architecture

## Design decision

Create independently usable, technology-specific blueprints. Each owns its
framework runtime, tests, configuration, and deployment assets. Share
contracts and documented engineering patterns where they have demonstrated
value; do not hide MAF, LangGraph, or a harness behind a universal runtime.
Generated projects must not import this repository at runtime.

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

The observability boundary is manual and content-free. A request UUID starts
at the API and propagates through the Foundry call, native MAF workflow,
model/tool operations, and PostgreSQL spans. A case UUID is added only after
the application has established it. W3C trace/span IDs, agent version, and
deployment revision bind technical evidence, but none authorizes a user,
approval, case, or side effect. Technical status and business outcome remain
separate.

Automatic MAF content instrumentation stays disabled. Model usage, latency,
retry reason, safe provider/model/tool identifiers, and bounded operation
status are allowlisted; prompts, completions, tokens, SQL, exception messages,
arbitrary baggage, and business payloads are excluded. Application Insights
verification joins only exact correlation tuples from hosted synthetic tests.

Release evidence is a separate architecture layer, not runtime state. Its
manifest is diagnostic and non-authorizing: it validates immutable files and
divides readiness into implementation, Azure runtime, and production
dimensions while permanently blocking production authorization. Cloud evidence
must match one exact source revision, environment, and immutable deployment
revision. Implementation evidence cannot establish Azure runtime readiness.
Production authorization remains solely with the baseline-pinned trust
validator, signed result attestations, and scoped, unexpired risk decisions;
self-authored review files cannot waive critical or security-critical gates.

The manual cloud workflow observes existing resources but never provisions,
deploys, changes traffic, retries an ambiguous business operation, or rolls
back. Agent A supplies native hosted lifecycle and reconciliation semantics;
Agent B supplies immutable revision/resource evidence and telemetry endpoints;
Agent C supplies authenticated application/database behavior and bounded
synthetic fault controls. See the
[Workstream D readiness guide](azure-foundry/readiness.md) for executable gates
and the current blocked/unverified matrix.
