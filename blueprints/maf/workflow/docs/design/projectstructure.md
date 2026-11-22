# Project structure

## Canonical blueprint tree

The tree below describes the intended single-source layout. The generator
copies the complete blueprint directory into a new project, then adds a
separate `verification/` tree. It is not a shared runtime dependency.

```text
maf-workflow/
├── README.md
├── compose.yaml
├── .dockerignore
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── examples/
│   │   └── synthetic_application.py
│   ├── app/
│   │   ├── api/
│   │   │   ├── app.py
│   │   │   ├── dependencies.py
│   │   │   ├── errors.py
│   │   │   ├── middleware.py
│   │   │   ├── schemas.py
│   │   │   └── routes/
│   │   │       ├── cases.py
│   │   │       └── health.py
│   │   ├── application.py
│   │   ├── composition.py
│   │   ├── config.py
│   │   ├── lifecycle.py
│   │   ├── main.py
│   │   ├── domain/
│   │   ├── usecases/
│   │   ├── workflows/
│   │   └── infrastructure/
│   ├── migrations/
│   │   ├── baseline.sql
│   │   ├── manifests/
│   │   └── versions/
│   └── tests/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── package-lock.json
│   └── src/
│       ├── authenticated-app.tsx
│       ├── api.ts
│       ├── workspace.tsx
│       └── test/
└── docs/
    ├── architecture.md
    ├── setup.md
    ├── development.md
    ├── testing.md
    ├── deployment.md
    ├── operations.md
    └── design/
        ├── prd.md
        ├── techstack.md
        ├── specs.md
        ├── architecture.md
        ├── projectstructure.md
        ├── userflow.md
        ├── deployment-flow.md
        └── issues-changes-fixes.md
```

Generated-only verification assets are produced by the source repository's
`scripts/instantiate_maf.py` and include
`verification/readiness`, `verification/contracts`,
`verification/scenarios`, `verification/tests`, and `verification/docs`.
Their tests and contract bytes are copied from source but their execution
occurs in the generated directory.

## Component responsibilities

| Path | Responsibility | Extension rule |
| --- | --- | --- |
| `backend/app/main.py` | Minimal process entrypoint that loads settings and the selected application before calling the composition root. | Keep runtime selection explicit; never silently replace a failed integration with synthetic behavior. |
| `backend/app/api/app.py` | Construct the FastAPI application, configure bounded CORS, install middleware and exception handlers, and include routers. | Keep transport assembly separate from business rules and workflow construction. |
| `backend/app/api/routes/` | Health and protected case endpoints. | Add routes only with explicit authentication, authorization, validation, and failure tests. |
| `backend/app/api/schemas.py` | Typed HTTP request and response models. | Keep transport models bounded and validate untrusted input before use. |
| `backend/app/api/dependencies.py` | Resolve authenticated request identity and the composed workflow service. | Do not treat caller-supplied identity or data as authorization. |
| `backend/app/api/middleware.py` | Add request correlation and privacy-safe unexpected-error handling. | Log error type and correlation only; do not disclose tokens or payloads. |
| `backend/app/api/errors.py` | Map domain and validation failures to stable, safe HTTP responses. | Preserve explicit failure classes; do not return success-shaped fallbacks. |
| `backend/app/application.py` | Load `module:function` factory and compose application components. | Supply app-owned rules, policy, action, setup and optional native workflow factory. |
| `backend/app/composition.py` | Compose the repository, identity provider, native local workflow host, use-case service, lifespan and API. | Keep this as the application composition root; do not add a general-purpose orchestration layer. |
| `backend/app/lifecycle.py` | Initialize storage and application state, then reconcile recoverable cases through the native workflow host at startup. | Preserve explicit recovery failures and idempotent restart semantics. |
| `backend/app/domain/` | Generic principals, cases, errors, state/action/workflow protocols and policy. | Keep domain-agnostic; do not move scenario business rules into the generic layer. |
| `backend/app/usecases/` | Coordinate authorization-approved request, decision, and workflow operations. | Preserve decision-before-resume and idempotent semantics. |
| `backend/app/workflows/` | Native MAF executor/workflow and local host/checkpoint recovery. | Preserve pending request identity and matching terminal outcome; host adapters own their provider. |
| `backend/app/infrastructure/` | PostgreSQL schema/store, Entra identity, and optional OBO adapter. | Keep credentials private; schema and checkpoint stores remain distinct. |
| `backend/migrations/` | Reviewed Alembic revisions and version-specific schema manifests. | Run explicit owner upgrades; runtime validates without DDL. |
| `backend/examples/` | Explicitly selected synthetic application. | Never treat as a production fallback or customer example. |
| `backend/tests/` | PostgreSQL integration, security, crash recovery, and synthetic evidence tests. | Use isolated test DB and test-only identity providers. |
| `frontend/src/` | MSAL app, typed API client, reusable workspace and UI tests. | Keep access tokens transient and do not embed service secrets. |
| `docs/` | Maintainer, adopter, operator, design, and journal documentation. | Update affected docs with each meaningful implementation change. |
| Generated `verification/` | Independent readiness contracts, verifier, tests, and fixture evidence. | Never import the source checkout or claim unsigned fixtures authorize release. |

## Canonical source and cleanup

The directory tree is the canonical target; compatibility forwarding modules,
legacy import aliases, duplicate code, obsolete directories, unused
dependencies, and stale configuration are not extension points. Before PR
approval, use direct imports and update tests, Dockerfiles, CI, docs, and
instantiation scripts together when removing an old path. Backward
compatibility with previous internal layouts is unnecessary for this
greenfield blueprint.

See [architecture](architecture.md) for dependency directions and
[specifications](specs.md) for implementation-to-test mapping.
