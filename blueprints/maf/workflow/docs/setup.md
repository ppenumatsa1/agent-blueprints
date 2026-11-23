# Setup and configuration

## Prerequisites

For the local Compose stack, install Docker with Compose and use existing,
authorized Entra SPA and API registrations. The API needs v2 tokens, delegated
`workflow.read`, `workflow.write`, and `workflow.approve` scopes and the
`Workflow.Approver` role; reviewers need the role and appropriate delegated
permissions. Register the SPA redirect at `http://localhost:8080` or the
selected loopback port. Registration, role assignment, consent, interactive
sign-in and OBO are not performed or verified by this project.

For tests and non-container development, use Python 3.12, uv 0.9.26, Node 22,
and an isolated PostgreSQL database. From `backend`, run:

```text
uv sync --locked
```

From `frontend`, run `npm ci`. The locked backend development environment
also includes the generated verifier's dependencies. For restricted package
downloads, see the approved-mirror instructions in the [README](../README.md).
Alembic migrations run explicitly before startup; the API validates but does
not migrate the schema. See
[migration operations](../README.md#business-database-migrations).

## Compose inputs

Set these in the invoking environment before running Compose from the project
root. Values must be application-owned; never commit secrets.

| Name | Default / purpose | Sensitivity |
| --- | --- | --- |
| `ENTRA_TENANT_ID` | Required tenant UUID | Configuration |
| `ENTRA_API_CLIENT_ID` | Required API client UUID and token audience | Configuration |
| `ENTRA_SPA_CLIENT_ID` | Required SPA client UUID | Public browser configuration |
| `ENTRA_API_APP_ID_URI` | Required API application ID URI, e.g. `api://<api-client-id>` | Public browser configuration |
| `POSTGRES_PASSWORD` | Required URL-safe password; retain securely for existing volumes | Secret |
| `BLUEPRINT_APPLICATION` | Required factory, e.g. `examples.synthetic_application:build_application` | Configuration |
| `BLUEPRINT_PORT` | `8080`, bound to loopback | Configuration |
| `NPM_REGISTRY`, `PYTHON_PACKAGE_INDEX` | Public default registries; optional approved build-time alternatives | No credentials in URLs |
| `OBO_ENABLED` | `false`; optional server-side delegation | Configuration |
| `OBO_ALLOWED_SCOPES` | Empty by default; comma-separated resource-qualified scopes required when OBO is enabled | Configuration |
| `ENTRA_API_CLIENT_SECRET` | Required only when OBO enabled | Secret; never send to browser |

After setting these values, run:

```text
docker compose build api
docker compose run --rm api python -m app.infrastructure.migrations upgrade
docker compose run --rm api python -m examples.synthetic_application
docker compose up --build --wait
```

The third command prepares only the selected synthetic example; applications
own preparation of their own tables. Then open
`http://localhost:8080` (or your selected port). The web build embeds only
public SPA configuration; rebuild after changes. Compose supplies the API
database URL and checkpoint path. `docker compose down` stops services but
preserves database and checkpoint volumes; changing the password input does
not rotate an existing database password.

## Direct backend and frontend inputs

For hosted backend execution, set `WORKFLOW_HOST=hosted` and omit
`CHECKPOINT_ROOT`. Supply `HOSTED_WORKFLOW_ENDPOINT`,
`HOSTED_CONVERSATION_ENDPOINT`,
`HOSTED_WORKFLOW_SCOPE`, and `API_MANAGED_IDENTITY_CLIENT_ID`; all are
required and startup fails closed when any is missing or invalid. Local mode
requires `WORKFLOW_HOST=local` and `CHECKPOINT_ROOT`. The generated standalone
app has no default hosted transport: Agent A integration must inject the native
Responses `WorkflowHost` adapter, otherwise hosted startup fails closed.
For the Order Resolution hosted-state boundary also set
`ENTRA_API_APP_ID_URI`, `HOSTED_SERVICE_PRINCIPAL_ID`, and
`HOSTED_SERVICE_APP_ROLE=Hosted.Workflow.Invoke`. The hosted runtime calls the
generated API with `ORDER_RESOLUTION_API_ENDPOINT` and
`ORDER_RESOLUTION_API_SCOPE=api://<API-client-id>/.default`; do not provide it
with PostgreSQL URLs, TLS settings, credentials, or roles.

For API-owned Azure PostgreSQL, set `DATABASE_TLS_MODE=verify-full`,
`DATABASE_TLS_ROOT_CERT=system` or libpq-compatible `PGSSLROOTCERT=system` (or
the generated container CA bundle at
`/etc/ssl/certs/ca-certificates.crt`), and choose exactly one authentication
mode. `DATABASE_AUTH_MODE=managed-identity` forbids a password and obtains the
PostgreSQL scope only when opening a connection, using
`DATABASE_MANAGED_IDENTITY_CLIENT_ID` or the API UAMI. Password mode accepts
`DATABASE_PASSWORD` from a secret manager. Keep `DATABASE_URL` restricted to
runtime privileges and use `MIGRATION_DATABASE_URL` for explicit schema-owner
migrations. Configure bounded use with `DATABASE_POOL_MIN_SIZE`,
`DATABASE_POOL_MAX_SIZE`, `DATABASE_POOL_TIMEOUT_SECONDS`, and
`DATABASE_CONNECTION_MAX_LIFETIME_SECONDS`.

The backend reads `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`, `DATABASE_URL`,
`CHECKPOINT_ROOT` (private directory), and `BLUEPRINT_APPLICATION`.
`WORKFLOW_HOST` defaults to `local`; hosted mode requires an injected Agent A
adapter. `CORS_ORIGINS` is an optional
comma-separated list of explicit origins; HTTP is accepted only for loopback.
OBO settings above also apply. The frontend reads the public
`VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_SPA_CLIENT_ID`, and
`VITE_ENTRA_API_APP_ID_URI` at build/dev-server time. Compose maps these
from the corresponding non-`VITE_` inputs. Use separate authorized
registrations and never store a secret in a Vite variable.

See [development](development.md), [testing](testing.md), and
[troubleshooting](operations.md). The separate [offline infrastructure
guide](../infra/README.md) describes staged azd/IaC inputs; these do not
configure the local application or establish a working Azure deployment.
