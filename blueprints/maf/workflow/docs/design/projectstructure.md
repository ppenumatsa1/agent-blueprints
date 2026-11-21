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
│   │   ├── api.py
│   │   ├── application.py
│   │   ├── config.py
│   │   ├── domain/
│   │   ├── usecases/
│   │   ├── workflows/
│   │   └── infrastructure/
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
| `backend/app/api.py` | HTTP routes, request models, auth dependency, safe API errors. | Add routes only with explicit authentication, authorization, validation, and failure tests. |
| `backend/app/application.py` | Load `module:function` factory and compose application components. | Supply app-owned rules, policy, action, setup and optional native workflow factory. |
| `backend/app/domain/` | Generic principals, cases, errors, state/action/workflow protocols and policy. | Keep domain-agnostic; do not move scenario business rules into the generic layer. |
| `backend/app/usecases/` | Coordinate authorization-approved request, decision, and workflow operations. | Preserve decision-before-resume and idempotent semantics. |
| `backend/app/workflows/` | Native MAF executor/workflow and local host/checkpoint recovery. | Preserve pending request identity and matching terminal outcome; host adapters own their provider. |
| `backend/app/infrastructure/` | PostgreSQL schema/store, Entra identity, and optional OBO adapter. | Keep credentials private; schema and checkpoint stores remain distinct. |
| `backend/app/infrastructure/telemetry.py` | Manual privacy-safe traces, metrics, and structured operational logs. | Keep signal fields allowlisted; do not capture payloads, identities, or secrets. |
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
