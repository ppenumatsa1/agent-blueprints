# Agent Blueprints architecture

## Design decision

Create independently usable, technology-specific blueprints. Each owns its
framework runtime, tests, configuration, and deployment assets. Share
contracts and documented engineering patterns where they have demonstrated
value; do not hide MAF, LangGraph, or a harness behind a universal runtime.
Generated projects must not import this repository at runtime.

## Open architecture and verification gaps

The engineering foundation is not a deployment-readiness claim. Open work
includes [hosted caller binding #22](https://github.com/ppenumatsa1/agent-blueprints/issues/22),
[native hosting and checkpoints #19](https://github.com/ppenumatsa1/agent-blueprints/issues/19),
[hosted recovery #20](https://github.com/ppenumatsa1/agent-blueprints/issues/20),
[external effects #32](https://github.com/ppenumatsa1/agent-blueprints/issues/32),
[independent trust #21](https://github.com/ppenumatsa1/agent-blueprints/issues/21),
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
Do not conflate an approved engineering merge with verified hosted execution,
human approval, or production readiness.

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

The longer-term target adds a Foundry Responses adapter and host-managed
checkpoints, neither of which is implemented. Staged Foundry-first Bicep/azd describes
separately hosted frontend and API services and has credential-free static
checks, but does not implement a hosted agent or a working cloud integration.
Hosting the workflow runtime in ACA is a deferred alternative requiring its own
verified checkpoint strategy. Neither topology is a verified deployment;
provisioning requires separate authorization.

[PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11) remains open.
Its cleaned foundation commit `9efeef0` removes the compatibility aliases and
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

The #35 MAF extension pattern work adds typed model selection, versioned
prompt assets, native MAF `Agent` construction, authorization-bound tools,
and the existing MAF-native executor/workflow factory seam under
`blueprints/maf/workflow/backend/app/extensions/`. The synthetic generated
fixture exercises these construction and denial boundaries without a model
call or fake response. Provider credentials and behavior, live hosted identity
and recovery, trusted readiness evidence, and consequential external effects
remain unverified or blocked; see the [MAF extension guidance](../blueprints/maf/workflow/docs/architecture.md#typed-maf-extension-patterns).

The local integration at `af3955a` combined the engineering layers. Source and
independently generated backends each passed 68 tests on PostgreSQL 16.15 and
17.12, generated verification passed 44 without skips, and both Compose stacks
and offline infrastructure checks passed. The unsigned independent readiness
report remained unverified. See the [integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---combined-engineering-layer-integration)
for failed attempts and scope. Final combined-revision CI and cloud behavior
remain separate checks; the individual PRs are still open.

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

The documented caller-binding direction is for the authenticated API to
authorize the caller and send Foundry workload Authorization plus
`x-ms-user-identity` populated from the trusted user OID. The hosted container
receives platform-injected `x-agent-user-id`; protocol 2.0.0 exposes that
identity as `get_request_context().user_id`. The caller needs Foundry Agent
Consumer and custom `UserIdentityImpersonation/action` authorization. This
avoids forwarding or persisting an end-user bearer/OBO token when no
downstream API call as the user is needed. The identity bridge and role
assignment are not implemented or live verified.

Hosted response recovery remains blocked: a visible matching metadata record
may reveal `response.id`, but an empty paged conversation list has no
documented bounded read-after-write visibility and cannot prove creation
failed. Conversation creation has the same lost-ack ambiguity, and a lock
cannot make remote creation atomic with the application database. No
Responses-create idempotency key or safe unambiguous recovery contract is
documented. Local business idempotency does not solve hosted response identity
recovery; do not silently retry. See the [hosted blocker
journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---hosted-caller-binding-and-lost-responses).

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
| Business policy, approvals and side effects | Keep in the generated application, not prompts or a shared agent runtime |

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
