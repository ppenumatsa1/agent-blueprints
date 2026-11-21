# Architecture

## Purpose and status

This is the source map for the local MAF workflow blueprint. The implemented
topology is React/MSAL, FastAPI, a native MAF workflow, PostgreSQL, private
local file checkpoints, and Docker Compose. The synthetic application is an
explicit example. Manual telemetry and opt-in Azure exporters are implemented;
hosted ingestion, Foundry hosting, and Azure deployment remain unverified.
CI or local tests do not prove a live deployment.

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

## Telemetry boundary

```mermaid
flowchart LR
    Browser[Browser request with optional traceparent] --> API[HTTP and workflow operations]
    API --> Signals[Allowlisted spans, metrics and JSON logs]
    Signals --> Local[Local logs only]
    Signals -->|Explicit Azure mode| Export[Azure trace and metric exporters]
    Export -.->|Ingestion unverified| AI[Existing Application Insights]
```

Only allowlisted operation/outcome dimensions are recorded in metrics, with
no exemplars. Identifiers, payloads and exception details are excluded from
telemetry; static device and instance values prevent host-name fallback.
No collector is provisioned. Export failures are sanitized and do not alter
workflow outcomes; configuration or initialization failures stop startup.

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

For code responsibilities, see [project structure](projectstructure.md); for
service and operator guidance, see the [project guide](../architecture.md).
