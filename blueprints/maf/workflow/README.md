# MAF workflow blueprint

This local blueprint combines a native Microsoft Agent Framework (MAF)
workflow, FastAPI, React/MSAL, PostgreSQL, and Docker Compose. Applications
select their own workflow, policy, rules, and transactional action; the
included synthetic action is an explicit example, not a customer scenario
or a replacement for a failed model or tool call.

## Project guide

These guides are copied into generated projects and describe the current
local prototype, not a production deployment:

- [Architecture and extension recipes](docs/architecture.md)
- [Setup and configuration](docs/setup.md)
- [Development and debugging](docs/development.md)
- [Testing and evidence](docs/testing.md)
- [Deployment design](docs/deployment.md)
- [Observability design and troubleshooting](docs/operations.md)

The design baseline is in [docs/design](docs/design/architecture.md):
[PRD](docs/design/prd.md),
[technology stack](docs/design/techstack.md),
[specifications](docs/design/specs.md),
[architecture](docs/design/architecture.md),
[project structure](docs/design/projectstructure.md),
[user flow](docs/design/userflow.md),
[deployment flow](docs/design/deployment-flow.md), and the cumulative
[engineering journal](docs/design/issues-changes-fixes.md). These documents
are maintained with the implementation and copied into every generated
project; planned hosting and cloud behavior remain unverified.

The local host uses MAF `FileCheckpointStorage` on a private, persistent
single-host volume. PostgreSQL separately holds business records, decisions,
audit events, and the action ledger. A per-case database lock coordinates
file and database transitions. Database effects committed with the ledger
can be replayed safely; external effects need their own idempotency contract
or a transactional outbox.

The Foundry Responses adapter and Foundry-managed checkpoint storage and
recovery are deferred to P1-12. The local store is not a shared-store or
hosted-recovery solution. Do not mount a local checkpoint provider into a
future host that supplies its own provider.

The [Foundry-first infrastructure](infra/README.md) is staged for
credential-free Bicep compilation and security checks only. Its hosted-agent
service and end-to-end cloud integration are not implemented or verified;
it is not authorization to provision or deploy.

## Local stack

Use Docker Compose and existing, authorized Microsoft Entra SPA and API
registrations. The API registration must issue v2 access tokens, expose
delegated `workflow.read`, `workflow.write`, and `workflow.approve` scopes,
and define the `Workflow.Approver` application role. Assign that role to
reviewers and grant appropriate delegated permissions. Register the SPA
redirect URI `http://localhost:8080` (or the selected loopback port).
These instructions do not create registrations, grant consent, or assign
roles. Interactive sign-in and OBO require separate live verification.

Set the following environment variables in your shell; do not commit them:

| Variable | Purpose |
| --- | --- |
| `ENTRA_TENANT_ID` | Existing tenant UUID. |
| `ENTRA_API_CLIENT_ID` | Existing API application/client UUID; the access-token audience. |
| `ENTRA_SPA_CLIENT_ID` | Existing SPA application/client UUID. |
| `ENTRA_API_APP_ID_URI` | API application ID URI, for example `api://<api-client-id>`. |
| `POSTGRES_PASSWORD` | A newly generated URL-safe password, such as a random hexadecimal string. |
| `BLUEPRINT_APPLICATION` | Application factory, such as `examples.synthetic_application:build_application`. |
| `BLUEPRINT_PORT` | Optional loopback port; defaults to `8080`. |
| `NPM_REGISTRY` | Optional approved npm-compatible registry used only while building the frontend. |
| `PYTHON_PACKAGE_INDEX` | Optional approved Python package index used only while building the API; do not include credentials. |

For example, after supplying the four Entra values in PowerShell:

```powershell
$env:POSTGRES_PASSWORD = [Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).ToLowerInvariant()
$env:BLUEPRINT_APPLICATION = "examples.synthetic_application:build_application"
docker compose build api
docker compose run --rm api python -m app.infrastructure.migrations upgrade
docker compose run --rm api python -m examples.synthetic_application
docker compose up --build --wait
```

Open `http://localhost:8080`. The frontend receives only public SPA
configuration at build time; rebuild it after changing Entra settings. The
API and database are not published to the host. The unauthenticated
`/healthz` endpoint contains no business data; `/api/` requires a validated
bearer token and per-record authorization. The sample reviewer must be
different from the submitter. The web server disables access logs to avoid
logging authorization-code query strings. The stack is a local prototype:
loopback HTTP and its default security controls are not a production
deployment configuration.

`docker compose down` stops the services but preserves the PostgreSQL and
checkpoint volumes. Back up, protect, and delete application data according
to the operator's policy. Retain the same database password securely when
restarting existing volumes; changing the environment variable does not
rotate a password already stored in PostgreSQL. The API runs as a non-root
service account and its
checkpoint directory must remain private to that account. On Windows outside
the container, enforce equivalent filesystem ACLs. MAF's restricted
checkpoint deserialization remains enabled.

## Business database migrations

`backend/migrations` contains Alembic revisions, immutable baseline SQL and
revision-specific catalog manifests. **Run migrations explicitly before
starting the API**, using `python -m app.infrastructure.migrations upgrade`
from `backend` with `DATABASE_URL` set to the intended database. This is a
controlled schema-owner operation; it creates an empty baseline or adopts an
unversioned database only if its business tables exactly match revision
`0001` by recording that validated revision with Alembic, then upgrades to head.
Fresh schemas execute the baseline revision normally. Existing rows, including
decisions, audit and action ledger, are not rewritten by the baseline.

API startup validates the recorded revision and its manifest without DDL or
stamping. It fails if the database is unversioned, outdated or divergent;
unknown revisions and changed baseline/manifest bytes also fail visibly.
Migrations and startup validation take exclusive and shared PostgreSQL
advisory transaction locks respectively. A migration failure rolls back the
DDL and version update.

The comparison covers table/column shape, defaults, constraints, indexes,
triggers, rules, policies, inheritance and identity-sequence settings, not
ownership, grants, other tables, data correctness, or external dependencies.
Manifests list all migration-owned tables; application-owned tables remain
outside the baseline. PostgreSQL 16.15 and 17.12 have local test evidence on
earlier revisions. An independent local PostgreSQL 16.14 run passed 72 backend
tests without skips on integration head `fcd8f6f4f5cf48d537b9183aefa35b6b079feb76`
([evidence](https://github.com/ppenumatsa1/agent-blueprints/issues/24#issuecomment-7070316677)).
This is not Azure managed PostgreSQL evidence; managed-service configurations,
backup/restore, identity and high availability remain unverified. Other versions
and configurations may fail comparison.
Tables owned by a different known revision must not pre-exist; adoption of an
application-owned table requires a separate reviewed migration design.

The configured search path must select the intended business schema first.
The migration identity needs ownership or DDL rights in that schema and rights
to manage the version table; no database-level `CREATE SCHEMA` is needed.
The runtime identity needs schema `USAGE`, read access to `alembic_version`
and the application's ordinary data privileges, but not schema/database
creation privileges for baseline validation. The synthetic example has its
own explicit preparation command above; a custom application's initializer and
tables need separately reviewed provisioning and permissions. Local Compose
uses the same PostgreSQL account for migration and runtime for convenience,
not as a production least-privilege model. Production operators must supply
separate identities and protect their connection settings.

Before upgrading, quiesce old application versions and writers and take a
verified, consistent database and checkpoint backup. The advisory lock only
coordinates cooperating migration and startup checks; it does not protect
against manual DDL, ongoing requests or old binaries. Review drift, then
restore or explicitly repair under change control and retry; never stamp an
unknown revision to bypass checks. Recover database and native checkpoints as
a coordinated pair and reconcile external effects separately.

There is **no automatic downgrade** from the baseline; restore a verified
compatible backup if recovery requires reverting. For each future revision,
add a reviewed manifest named `manifests/<revision>.json` and its UTF-8
newline-normalized SHA-256 as `schema_manifest_sha256` on the revision.
Produce and review the manifest from a clean, disposable PostgreSQL 17 schema
after applying that revision: capture `_snapshot(connection, schema, tables)`
with the complete migration-owned table list, serialize
`{"tables": [...], "snapshot": ...}` as JSON, and hash the exact file.
Never derive it from a production database or auto-accept observed drift.
Review the migration and manifest together and test fresh, previous-revision,
drift, recovery, privilege and rollback behavior. The test-only second
revision under `backend/tests/migration_fixtures` demonstrates the contract.
Alembic versions business tables, not MAF checkpoints or human authorization.

Optional server-side OBO requires `OBO_ENABLED=true`, an existing
`ENTRA_API_CLIENT_SECRET`, and comma-separated `OBO_ALLOWED_SCOPES`.
Never put that secret in a frontend build argument or browser configuration.
Only explicitly allowlisted downstream scopes may be requested; the supplied
example does not call a downstream service. Use an appropriate secret manager
and deployment identity in a real environment.

## Operational telemetry

The backend uses manual OpenTelemetry tracing and metrics for HTTP requests, workflow
start/resume, selected PostgreSQL operations and OBO exchange. The
`blueprint.telemetry` logger emits JSON operations with outcome, duration,
trace/span IDs and a server-generated request correlation ID. It does not
inspect payloads, tokens, claims, SQL, URLs, exception text or tool/model
inputs and outputs. No auto-instrumentation or local telemetry stack is enabled.
These operational logs are not approval or audit evidence.

`TELEMETRY_MODE=local` is the default: local structured logs are emitted and
cloud export is explicitly disabled. For a hosted service, explicitly set
`TELEMETRY_MODE=azure-monitor` and supply an existing
`APPLICATIONINSIGHTS_CONNECTION_STRING` through a secret manager. The
prerelease Azure Monitor trace and metric exporters use batching and no offline
disk storage. Missing or invalid configuration or exporter initialization
fails startup with a sanitized error. Once initialized, trace or metric
export/flush failures produce fixed, non-sensitive signals and do not change
workflow outcomes. Configuration is not proof of successful ingestion.
Export failure can lose spans or metrics; monitor signals and validate the
hosted pipeline separately.

Span creation, metadata, context extraction and closure failures also emit a
fixed `telemetry.instrumentation` failure signal without retrying the
instrumented operation or replacing its exception. Initialization and
pre-startup failures release created providers and exporters where possible.
If the operational logger itself fails, a fixed `telemetry.log` failure event
is written directly to stderr as a best-effort fallback; neither the logger
exception nor application data is included. A stderr write failure is ignored
so it cannot replace a workflow outcome or exception.

The `blueprint.operations` counter and `blueprint.operation.duration`
histogram measure each instrumented operation independently of trace sampling.
Their only dimensions are allowlisted operation and outcome; they contain no
business identifiers or payloads. Metric exemplars are disabled. The hosted
metric reader exports periodically (SDK default 60 seconds; configurable via
`OTEL_METRIC_EXPORT_INTERVAL` in milliseconds); local mode has no metric
exporter. The pinned Azure exporter uses its preferred aggregation temporality.
If the Azure SDK configuration disables custom metric export, startup fails
rather than claiming metrics are enabled.
Azure exporter and Azure core pipeline log propagation is suppressed in this
mode because SDK exception logs can contain endpoints or other sensitive data;
the exporter wrapper instead reports a fixed failure signal.
Azure exporter Statsbeat, SDK statistics and remote configuration are disabled
process-wide; static non-identifying device and service-instance values prevent
the exporter from defaulting to the host name.

Only valid W3C `traceparent` is accepted from clients; baggage and tracestate
are discarded. The header is untrusted and never authorizes operations. The
response's `X-Correlation-ID` is newly generated, is not a business ID, and
matches the request log. The browser sends a random `traceparent` for each API
request without exporting a browser span; if secure randomness is unavailable,
the request proceeds without it. Outbound propagation and Foundry-host
correlation are not yet implemented or verified. Recovery outside a request
starts a new trace. Span sampling follows
the SDK's parent-based default. Configure retention, access, ingestion region,
and appropriate sampling in the hosted environment; none is verified here.
Applications and deployment agents must not turn on additional automatic
instrumentation or unrestricted SDK logging without a privacy review.

## Application extension points

The project has sibling `backend` and `frontend` directories. The backend
contains API composition (`app/api/app.py`), application coordination
(`app/application.py` and `app/usecases`), generic domain types and policy
(`app/domain`), native MAF workflow and local host (`app/workflows`), and
PostgreSQL and identity adapters (`app/infrastructure`). Import these
canonical modules directly when implementing application extensions.

- Supply `ApplicationComponents` from a `module:function` factory: replace
  `BusinessRules`, `AccessPolicy`, `TransactionalAction`, initialization,
  or the native workflow factory. Include application-owned modules in the
  generated project's image instead of importing this repository.
- `StateRepository` and `WorkflowHost` define the core state and hosting
  boundaries. The supplied API uses `PostgresStore`; replacements must
  preserve transactional decision, locking, action, and recovery invariants.
- `create_app` accepts an `IdentityProvider` and a store for application
  integration and isolated tests. The default deployable identity is Entra;
  test identities and signing keys are not an interactive authentication mode.
- `WorkflowWorkspace` accepts a `WorkflowClient` and `renderCase` for UI
  composition. Applications own any domain-specific views and evaluation
  fixtures; the order-adjustment scenario belongs only in tests.

The native local host expects a workflow producing one request with `case_id`
and one matching outcome. A different graph must preserve that contract or
provide its own host. Keep conversation, workflow checkpoints, business
records, and human decisions separate.

## Development and tests

Install Python 3.12, uv 0.9.26, Node 22 and Docker Compose. From `backend`,
the same commands work in PowerShell, macOS and Linux shells:

```text
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest -v tests.test_core tests.test_security tests.test_evidence_runner tests.test_telemetry tests.test_migrations
```

Set `MAF_TEST_DATABASE_URL` to an isolated PostgreSQL database first. Its test
identity must be able to create and drop schemas and roles; the restricted-role
startup test requires `CREATEROLE`. Never use production credentials or data.
The lock uses public PyPI and includes the verifier test dependencies. If direct
artifact downloads are blocked, use an approved mirror per command without
changing the committed lock: run `uv venv`, then `uv export --locked
--no-emit-project --output-file dev-locked.txt`, followed by `uv pip sync
--python .venv --require-hashes --default-index <approved-index-url>
dev-locked.txt`. Delete `dev-locked.txt` afterwards. A mirror must supply
the exact locked hashes. Do not put credentials in the index URL.

These tests fail rather than skip if the database is unavailable. They use
test-only identities and terminate real worker processes after decision
persistence and after the synthetic database action commits. They do not
establish live Entra/OBO or Foundry-hosted recovery. The local application
increment ran 26 backend tests successfully.

For the frontend, use Node 22 and run from `frontend`:

```text
npm ci
npm test
npm run build
npm run check-csp
```

Configure npm to use an approved registry when direct access is restricted.
The local run passed 8 frontend tests, the build, and the CSP check. The basic
automated accessibility check does not assess color contrast. The CSP check
binds the inline theme script to the reverse-proxy policy.

For interactive development, configure a local PostgreSQL connection,
`CHECKPOINT_ROOT`, `BLUEPRINT_APPLICATION`, `ENTRA_TENANT_ID` and
`ENTRA_API_CLIENT_ID` in the environment. From `backend`, run
`uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
--no-access-log`. From `frontend`, set `VITE_ENTRA_TENANT_ID`,
`VITE_ENTRA_SPA_CLIENT_ID` and `VITE_ENTRA_API_APP_ID_URI`, then run
`npm run dev`; the dev server proxies `/api` to the backend. Register the
actual local redirect URI separately with Entra. These interactive paths
require real registrations and authorized identities; automated synthetic
tests do not. No test identity is enabled in the application.

Open the blueprint or generated project root as a VS Code workspace, install
the Python and Python Debugger extensions, run the locked sync task and select
`backend/.venv` as the Python interpreter. Put backend variables in an
untracked root `.env` file and frontend `VITE_` variables in the terminal
environment (or an untracked `frontend/.env.local`). Use **Backend: FastAPI**
for breakpoints, and **Frontend: Chrome** to start Vite and debug the browser.
The backend debugger does not reload automatically. Keep secrets out of
version control and browser settings. Database connection, private checkpoint
permissions and authentication remain required; debugger configuration does
not bypass them.

## Independent project and verification

The source repository's `scripts/instantiate_maf.py` copies this blueprint,
its license, and independent verification assets into a **new directory
outside** that repository. The copy owns its runtime, frontend, Docker build
contexts, contracts, test fixtures, and readiness CLI; it does not import or
mount the original checkout. It is an initial project, not a synchronization
mechanism: maintain and review subsequent changes in the copied project.

In the generated project, run `uv sync --locked` in `backend`. Set
`MAF_TEST_DATABASE_URL` to an isolated PostgreSQL database and select the
test-only adapter. From the generated `verification` directory:

```text
uv run --locked --project ../backend python -c "import os,pathlib,unittest,sys; os.environ['SCENARIO_ADAPTER']=str(pathlib.Path('../backend/tests/order_adjustment_adapter.py').resolve()); sys.exit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests')).wasSuccessful())"
```

From `backend`, run the locked backend suite shown above, including telemetry
and migrations.

The golden adapter exercises the API, local MAF host, and synthetic database
action. The two worker-kill tests cover crashes after decision persistence
and after action commit. Use a disposable database: the tests create and drop
their own isolated schemas. Frontend and Compose instructions above also
apply to the copy.

To retain per-case observations, both crash results, normalized check
results, and an unsigned readiness input, run from the generated project's
`backend` directory:

```text
uv run --locked python -m tests.evidence_runner --verification-root ../verification --output ../verification/evidence/run --revision <source-revision> --environment local-synthetic
```

Replace `<source-revision>` with the actual generated-project revision; use a
new output directory for each run. Run the independent CLI against those
files as described in `verification/docs/readiness-validator.md`. The local
producer, timestamps, and revision are not independently attested; its
synthetic approval observations are not human contract approval. The included
empty trust store must yield **unverified**, not a release authorization.
The fixture formats its own explanation and hint from recorded case data; it
does not exercise an agent-generated explanation or a browser hint end to
end. Those contract checks remain **unverified**, even if the fixture's
deterministic comparisons pass. Runner exit 0 means the executable fixture
and crash tests completed without unexpected failures; it is not a readiness
pass.
