# Agent Blueprints architecture

## Design decision

Create independently usable, technology-specific blueprints. Each owns its
framework runtime, tests, configuration, and deployment assets. Share
contracts and documented engineering patterns where they have demonstrated
value; do not hide MAF, LangGraph, or a harness behind a universal runtime.
Generated projects must not import this repository at runtime.

## MAF modularity foundation and target

The local blueprint and its generated copy now have sibling `backend` and
`frontend` build contexts. The backend separates API composition, use cases,
generic domain ports and policy, native MAF workflow/host, and PostgreSQL and
identity infrastructure. Application factories and transactional-action
interfaces remain the extension boundaries; use canonical module imports.
Requirements, examples, schema and backend tests are owned by `backend`.
The verifier and exact contract bytes remain independent of the runtime.

The longer-term target adds separately reviewed dependency locking and
developer tooling, migrations, privacy-safe telemetry, a Foundry Responses
adapter and host-managed checkpoints, and Foundry-first Bicep/azd for
separately hosted frontend and API services. These are not implemented by
this modularity increment. Hosting the workflow runtime in ACA is a deferred
alternative requiring its own verified checkpoint strategy. Neither topology
is a verified deployment; provisioning requires separate authorization.

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
passed all five checks, including generated checks without skips. PR #12 still
requires its own revision-specific checks. Its documentation changes are
rebased onto the exact foundation tip above; the isolated root suite passed
47 tests with one expected adapter-not-selected skip, and generated-copy/link
plus verifier-pipeline regressions passed. Hosted checks for this dependent
head are pending.
The copied
[project guides](../blueprints/maf/workflow/README.md#project-guide) describe
the current local boundaries and planned deployment/observability designs.
Their [design baseline](../blueprints/maf/workflow/docs/design/architecture.md)
maps requirements to source and evidence; its engineering journal records
verified findings and remaining work. The generated-copy tests include the
design documents and validate local links. Parallel tooling, migrations,
telemetry and Foundry-host work build on the foundation. Reconcile their
interfaces and validate each resulting revision independently. Prepare
inventory, cost and a deployment plan for separate approval before
provisioning or live validation.

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

## First golden path: public-network MAF workflow

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

The public-network choice is not public anonymous access: require Entra-backed
authentication for protected APIs, authorization for sensitive operations,
managed identity where applicable, restrictive CORS, and safe secret handling.
Private networking and self-hosted CI are deferred, not prohibited forever.
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
