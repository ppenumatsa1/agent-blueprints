# Product requirements: MAF workflow blueprint

## Problem and objective

Application teams need a reusable, framework-native starting point for a
workflow that pauses for a durable human decision and resumes without
duplicating an authorized database action. They also need to generate and own
a separate project rather than depend on this repository at runtime.

The objective is a locally runnable React/MSAL, FastAPI, Microsoft Agent
Framework (MAF), PostgreSQL, and Docker Compose blueprint. It demonstrates
separation of workflow checkpoints from business state, server-side
authentication and authorization, idempotent application-owned effects, and
independent project generation. The included action and acceptance scenario
are synthetic fixtures, not a business application.

## Users and needs

| User | Need |
| --- | --- |
| Blueprint adopter | Generate a self-contained project, configure an application factory, and understand the local boundaries. |
| Request owner | Submit a request and inspect only records authorized to them. |
| Assigned reviewer | Review and approve or reject a pending request under server-enforced policy. |
| Operator | Start the local stack, diagnose failures without exposing tokens or payloads, and protect persistent volumes. |
| Maintainer | Tie requirements to source, regression evidence, generated-copy checks, and revision-specific CI. |

## Functional requirements

| ID | Requirement |
| --- | --- |
| FR-01 | Generate a new project outside the repository with its own backend, frontend, Docker contexts, documentation, and independent verification assets. |
| FR-02 | Authenticate API calls with validated Entra bearer tokens; authorize submission, record reads, and decisions on the server. |
| FR-03 | Persist requests, decisions, audit events, and database-action ledger entries in PostgreSQL. |
| FR-04 | Run a native MAF workflow that issues one case-bound approval request and emits one matching outcome. |
| FR-05 | Require a different, assigned reviewer and persist their decision before resuming the workflow. |
| FR-06 | Use an idempotency key and transactional database ledger for same-transaction effects; surface failures rather than fabricating a result. |
| FR-07 | Recover local work across the tested decision-persistence and action-commit crash windows using private local checkpoints and database reconciliation. |
| FR-08 | Provide a React/MSAL UI for sign-in, request submission, record reads, decisions, and visible failure states. |
| FR-09 | Include independently generated documentation, tests, exact contract bytes, and readiness verification without repository imports or bind mounts. |

## Non-functional requirements

- **Security:** Protected endpoints require authentication and authorization.
  Treat request/model/tool inputs as untrusted. Do not place secrets in browser
  configuration, source, images, logs, or generated examples.
- **Durability:** Keep MAF checkpoint state distinct from PostgreSQL business,
  decision, audit, and action-ledger state. Local file checkpoints are
  single-host and are not a hosted recovery mechanism.
- **Privacy:** Do not log access tokens, authorization codes, secrets, or
  business payloads. Keep API failures safe and actionable.
- **Independence:** Generated output owns its runtime and verification files;
  it does not import or mount this source repository.
- **Evidence:** Keep failed and unverified outcomes distinct from passing
  checks. Schema validity or a synthetic approval is not release authorization.
- **Maintainability:** Maintain one canonical implementation, direct imports,
  and design documents copied with the blueprint. Remove legacy forwarding
  modules and obsolete files before PR approval.

## Scope and exclusions

**Current scope:** local single-host prototype, selected application factory,
Entra integration points, PostgreSQL records and action ledger, MAF native
workflow with `FileCheckpointStorage`, React/MSAL client, Compose packaging,
generated project, and local/hosted regression tests.

**Not implemented or verified:** live Entra sign-in and OBO, production
secrets management, external side-effect exactly-once behavior, versioned
database migrations, cloud telemetry export, Foundry-hosted execution and
managed checkpoint recovery, ACA recovery, Bicep/azd provisioning, and a
production deployment. Azure resource creation and permanent repository
creation require separate approval.

## Acceptance criteria

1. A generated copy contains the blueprint guides and all eight `docs/design`
   documents byte-for-byte; local Markdown links resolve in that copy.
2. Tests cover authorization boundaries, idempotent decisions/actions, and
   both documented worker-crash windows.
3. Independent generated verification exercises the actual test adapter and
   reports synthetic approval/recovery observations separately from unverified
   explanation/hint and trust claims.
4. Compose runs the UI on loopback, keeps API/database ports unpublished, and
   protects `/api/` with authentication; this does not prove live Entra use.
5. CI results are checked on the actual PR head revision. No PR is finalized
   with compatibility shims, forwarding modules, unused dependencies, or
   obsolete configuration still present.

## Workflow at a glance

```mermaid
flowchart LR
    A[Authorized submitter] --> B[Authenticated API and case policy]
    B --> C[PostgreSQL request and audit]
    C --> D[Native MAF workflow]
    D --> E[Private local checkpoint]
    E --> F[Assigned reviewer decision]
    F --> G[Persist decision before resume]
    G --> H{Decision}
    H -->|Approved| I[Idempotent database action and ledger]
    H -->|Rejected| J[No action]
    I --> K[Recoverable terminal result]
    J --> K
```

See [specifications](specs.md) for implementation and verification mapping,
and [user flow](userflow.md) for the detailed authorization and failure paths.
