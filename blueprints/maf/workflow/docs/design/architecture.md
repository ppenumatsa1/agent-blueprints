# Architecture

## Purpose and status

This is the source map for the local MAF workflow blueprint. The implemented
topology is React/MSAL, FastAPI, a native MAF workflow, PostgreSQL, private
local file checkpoints, and Docker Compose. The synthetic application is an
explicit example. Foundry hosting, cloud telemetry, and Azure deployment are
planned and unverified. Staged Bicep/azd resource definitions and offline
checks exist, but CI or local tests do not prove a live deployment.

## Component view

```mermaid
flowchart LR
    User[Submitter or assigned reviewer]
    UI[React workspace and MSAL]
    API[FastAPI routes and Entra validation]
    UC[WorkflowService and application policy]
    WF[Native MAF workflow]
    Host[LocalWorkflowHost]
    CP[(Private per-case file checkpoint)]
    Store[PostgresStore]
    DB[(Cases, decisions, audit, action ledger)]
    Action[Application-owned transactional action]

    User --> UI
    UI -->|Bearer token and JSON| API
    API --> UC
    UC --> WF
    WF --> Host
    Host --> CP
    UC --> Store
    Host --> Store
    Store --> DB
    Store --> Action
```

The browser is not authoritative for identity or permission. FastAPI validates
the token and derives the principal; application policy controls record access
and decisions. Workflow checkpoints preserve framework continuation state;
PostgreSQL owns business records, decision/audit history, and the action
ledger. These stores are separate and do not share an atomic transaction.

## Decision and persistence sequence

```mermaid
sequenceDiagram
    actor Owner
    actor Reviewer
    participant UI as React/MSAL
    participant API as FastAPI
    participant S as WorkflowService
    participant DB as PostgreSQL
    participant MAF as Native MAF
    participant CP as Local checkpoint

    Owner->>UI: Sign in and submit request
    UI->>API: POST /api/cases + Idempotency-Key
    API->>API: Validate token, scope, and reviewer policy
    API->>DB: Create case and audit event
    API->>MAF: Start case workflow
    MAF->>CP: Save pending request checkpoint
    MAF->>DB: Persist checkpoint/request reference
    API-->>UI: Pending case
    Reviewer->>UI: Approve or reject
    UI->>API: POST /api/cases/{id}/decision
    API->>API: Validate identity, scope, role, and case assignment
    API->>DB: Persist decision
    API->>MAF: Resume matching pending request
    MAF->>DB: Apply matching transactional action once
    MAF->>CP: Save terminal checkpoint
    API-->>UI: Outcome or explicit failure
```

The per-case PostgreSQL advisory lock serializes host operations across
checkpoint and SQL transitions. It does not make checkpoint writes atomic with
database commits; startup recovery reconciles durable records and checkpoints.
The same-transaction action ledger applies only to database effects performed
through the supplied transaction. External side effects require downstream
idempotency or a transactional outbox.

For an interrupted start, the local host asks the MAF file provider for the
latest checkpoint after validating every file; the provider accounts for
lineage when timestamps tie. After running a workflow, the host uses that
workflow instance's last persisted checkpoint instead of sorting by wall
clock time. It checks the pending request before recording it and requires a
terminal checkpoint with no pending requests or queued messages before
marking execution complete or accepting a completed replay. A missing or
incomplete checkpoint remains an explicit recovery error; a committed
database action is protected by the action ledger on retry.

## Trust and extension boundaries

- `ApplicationComponents` supplies application-owned business rules, access
  policy, transactional action, optional initialization, and optionally a
  workflow factory.
- `StateRepository` and `WorkflowHost` are narrow domain boundaries. Replacing
  either requires preserving identity isolation, decision ordering,
  idempotency, recovery, and failure semantics.
- MAF input and application payloads are untrusted. A model/tool response is
  not authorization; no model recommendation can approve an action.
- Entra identities are validated by the API. Test providers and signing keys
  are not runtime authentication modes.
- Optional OBO is server-side, explicitly configured and scope-allowlisted;
  the included synthetic application makes no downstream call.
- Logs and correlation identifiers are potentially sensitive. Do not record
  bearer tokens, authorization codes, secrets, or payloads.

## Hosting boundary

`LocalWorkflowHost` constructs per-case `FileCheckpointStorage` under a
private single-host directory. PostgreSQL is not a checkpoint store. A future
Foundry host must use its supported host-managed checkpoint provider and a
request-aware factory; it must not attach the local provider as a second
checkpoint authority. ACA would require its own selected and verified
multi-replica-safe strategy. Neither hosting path is implemented here.

## Staged Foundry-first infrastructure

```mermaid
flowchart LR
    Browser[Browser] -. access path not wired .-> UI[Optional internal ACA UI]
    UI -. proxy not wired .-> API[Optional internal ACA API]
    API -. agent contract not verified .-> Project[Foundry account and project]
    Project -. no hosted service declared .-> Workflow[Future native MAF host]
    API -. Entra token flow not implemented .-> DB[Private PostgreSQL]
    API -. export and private path not implemented .-> Monitor[App Insights and Log Analytics]
    Registry[Optional authenticated registry] -. scoped image pull .-> API
    Registry -. scoped image pull .-> UI
```

The optional model, project-wide API agent-consumer grant, registry and
Container Apps default off. Foundry public
access and monitoring public ingestion/query are disabled, but this increment
does not provide their private endpoints or verify any runtime connection.
PostgreSQL uses a delegated subnet, private DNS and Entra-only authentication;
the existing API does not acquire a database token. The staged server selects
PostgreSQL 16, whereas local Compose and the parallel migration tests use 17;
migration and application compatibility with the chosen Azure target are
unverified. Container Apps platform
auth is a separately applied resource; application-level authentication and
record authorization remain mandatory even if it fails. The optional registry
is publicly network-reachable but disallows anonymous and admin access.
The eventual agent-scoped caller binding and inherited role assignments still
need review; no endpoint caller exclusivity is established. ACA internal
ingress is environment-scoped, so the UI is not directly reachable by a
browser elsewhere on the VNet.
See the [infrastructure guide](../../infra/README.md) for all limitations.

For code responsibilities, see [project structure](projectstructure.md); for
service and operator guidance, see the [project guide](../architecture.md).
