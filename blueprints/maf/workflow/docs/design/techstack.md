# Technology stack

This is the checked-in local-prototype baseline. Python dependencies are
locked with artifact hashes; versions below are source configuration, not a
claim about a deployed environment.

## Runtime and dependencies

| Area | Current choice | Rationale and alternatives |
| --- | --- | --- |
| Python | Python 3.12; `python:3.12-slim` backend image | Matches the source and GitHub Actions runtime. A different Python minor requires package and CI verification. |
| Agent workflow | `agent-framework-core==1.26.0` | Uses MAF `WorkflowBuilder`, `Executor`, `WorkflowContext`, and `CheckpointStorage` natively. LangGraph or an SDK harness would be a separate blueprint, not a hidden runtime switch. |
| API | FastAPI `0.162.7`, Uvicorn `0.54.0` | Typed HTTP boundary, dependency-based bearer auth, and an ASGI server. |
| Observability | OpenTelemetry SDK `1.45.2`, Azure Monitor exporter `1.0.0b59` | Manual traces and metrics, explicit Azure export; local mode exports nothing. Hosted ingestion remains unverified. |
| Persistence | PostgreSQL `17-alpine`, Psycopg binary `3.3.9` | Relational transactions and uniqueness constraints support the decision/action ledger; MAF file checkpoints remain separate. |
| Identity | MSAL `1.39.0`, PyJWT crypto `2.15.1` | MSAL is used in the browser; the API verifies Entra v2 access tokens, scopes, roles, and record access. Test identities are isolated to tests. |
| API models | Pydantic provided by the pinned FastAPI graph | Request/response parsing rejects extra fields. A separate direct version pin is not currently declared. |
| Frontend | React/React DOM `19.3.1`, TypeScript `7.0.2`, Vite `8.3.8` | Component UI, static typing, and a production build; a different UI framework would need its own client contract and tests. |
| Browser auth | `@azure/msal-browser` `5.29.1`, `@azure/msal-react` `5.8.2` | Browser obtains scoped delegated access tokens. Secrets and OBO credentials remain server-side. |
| Frontend tests | Vitest `5.1.0`, Testing Library, jsdom `31.0.1`, axe-core `4.14.0` | Exercise UI and API client behavior. Automated accessibility checks do not assess color contrast. |
| Developer tooling | uv `0.9.26`, Ruff `0.14.13`, Node 22, VS Code tasks | Locked backend installs and consistent lint/format checks; editor debugging remains unverified. |
| Packaging | Docker Compose; sibling `backend` and `frontend` build contexts | The checked-in topology is local and loopback-bound. Kubernetes, ACA, and Foundry hosting are not current alternatives selected by configuration. |

The Python direct dependencies are in
[`backend/pyproject.toml`](../../backend/pyproject.toml), with the resolved
graph and hashes in [`backend/uv.lock`](../../backend/uv.lock); the
frontend's direct dependency manifest and lock are
[`frontend/package.json`](../../frontend/package.json) and
[`frontend/package-lock.json`](../../frontend/package-lock.json).
Compose declares the PostgreSQL image in
[`compose.yaml`](../../compose.yaml). The source repository's
`.github/workflows/ci.yml` pins GitHub Actions revisions; that CI file is
not copied into a generated project.

## State and identity choices

- **MAF checkpoint:** `FileCheckpointStorage` in a private local directory,
  scoped by case. Single-host only.
- **Business state:** PostgreSQL stores cases, decisions, audit events, and
  action ledger. A per-case PostgreSQL advisory lock coordinates workflow and
  database transitions; it does not make file and SQL writes atomic.
- **Identity:** Entra v2 delegated access tokens for interactive API calls.
  A synthetic principal is a test dependency, never an interactive fallback.
- **Application extension:** `ApplicationComponents` provides rules, policy,
  action, optional initialization, and a native workflow factory. The
  blueprint does not own application-specific business behavior.

## Dependency and alternative status

The backend image exports the lock and verifies artifact hashes during install.
Migrations, Foundry host integration, managed identity deployment,
Bicep, and azd remain planned; no version or command
should be inferred for them. The current local image uses tags rather than
immutable image digests, so supply-chain hardening is still an acceptance
concern. See [deployment flow](deployment-flow.md) and
the source repository's `docs/engineering-standards.md`.

The **open** developer-tooling change is PR
[#13](https://github.com/ppenumatsa1/agent-blueprints/pull/13), head
`edfd5727e99c256f2c0267c5af614e566e2a12b5`. Its hosted
[run 44931514554](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44931514554)
passed five checks for that exact revision, not this combined revision. The
workstream reports Windows and Linux Compose verification with an approved
package mirror after public TLS failures; public-only local downloads, macOS
and interactive debugger verification remain unverified. See the
[journal](issues-changes-fixes.md).

## Official references

- [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Microsoft identity platform and MSAL](https://learn.microsoft.com/en-us/entra/identity-platform/msal-overview)
- [PostgreSQL documentation](https://www.postgresql.org/docs/)
- [Docker Compose documentation](https://docs.docker.com/compose/)
- [React documentation](https://react.dev/learn)
- [Vite documentation](https://vite.dev/guide/)
- [uv documentation](https://docs.astral.sh/uv/)
- [Ruff documentation](https://docs.astral.sh/ruff/)

These references describe upstream products, not proof that an unimplemented
hosting or telemetry integration works.
