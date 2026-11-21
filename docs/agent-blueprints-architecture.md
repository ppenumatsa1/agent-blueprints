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
developer tooling, migrations, privacy-safe telemetry, and a Foundry Responses
adapter and host-managed checkpoints; those are not established by this
infrastructure increment. Staged Foundry-first Bicep/azd now describes
separately hosted frontend and API services and has credential-free static
checks, but does not implement a hosted agent or a working cloud integration.
Hosting the workflow runtime in ACA is a deferred alternative requiring its own
verified checkpoint strategy. Neither topology is a verified deployment;
provisioning requires separate authorization.

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
records remain separate from host-managed workflow state. The Python hosting
integration is documented as prerelease; package versions and the complete
hosted approval/recovery path must be validated in P1-12 before claiming
hosted durability.

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
The staged PostgreSQL server selects major 16 while local Compose and the
parallel migration baseline use 17. A separate migration revision passed 12
local PostgreSQL 16.15 tests, including upgrade and drift; the combined
application and Azure target remain unverified. The
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
authorization. Fixture-formatted explanations and hints are not agent
evaluation or browser end-to-end evidence, so those checks remain unverified.
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
