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

Optional server-side OBO requires `OBO_ENABLED=true`, an existing
`ENTRA_API_CLIENT_SECRET`, and comma-separated `OBO_ALLOWED_SCOPES`.
Never put that secret in a frontend build argument or browser configuration.
Only explicitly allowlisted downstream scopes may be requested; the supplied
example does not call a downstream service. Use an appropriate secret manager
and deployment identity in a real environment.

## Application extension points

The project has sibling `backend` and `frontend` directories. The backend
contains API composition (`app/api.py`), application coordination
(`app/application.py` and `app/usecases`), generic domain types and policy
(`app/domain`), native MAF workflow and local host (`app/workflows`), and
PostgreSQL and identity adapters (`app/infrastructure`). Existing `app.*`
module paths remain compatibility aliases for application extensions.

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

## Tests

Use Python 3.12 and an isolated PostgreSQL database. Install
`backend/requirements-dev.txt` in a virtual environment, set
`MAF_TEST_DATABASE_URL` to the test database, and run from `backend`:

```text
python -m unittest -v tests.test_core tests.test_security tests.test_evidence_runner tests.test_modularity
```

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

## Independent project and verification

The source repository's `scripts/instantiate_maf.py` copies this blueprint,
its license, and independent verification assets into a **new directory
outside** that repository. The copy owns its runtime, frontend, Docker build
contexts, contracts, test fixtures, and readiness CLI; it does not import or
mount the original checkout. It is an initial project, not a synchronization
mechanism: maintain and review subsequent changes in the copied project.

In the generated project, install both `backend/requirements-dev.txt` and
`verification/requirements-dev.txt` in an isolated Python environment. Set
`MAF_TEST_DATABASE_URL` to an isolated PostgreSQL database and select the
test-only adapter. For example, in PowerShell:

```powershell
$env:SCENARIO_ADAPTER = (Resolve-Path .\backend\tests\order_adjustment_adapter.py).Path
Set-Location .\verification
python -m unittest discover -s tests -v
Set-Location ..\backend
python -m unittest -v tests.test_core tests.test_security tests.test_evidence_runner tests.test_modularity
```

The golden adapter exercises the API, local MAF host, and synthetic database
action. The two worker-kill tests cover crashes after decision persistence
and after action commit. Use a disposable database: the tests create and drop
their own isolated schemas. Frontend and Compose instructions above also
apply to the copy.

To retain per-case observations, both crash results, normalized check
results, and an unsigned readiness input, run from the generated project's
`backend` directory:

```powershell
python -m tests.evidence_runner --verification-root ..\verification --output ..\verification\evidence\run --revision <source-revision> --environment local-synthetic
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
