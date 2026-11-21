# Observability design and troubleshooting

## Current signals

Use the local process output or `docker compose logs api` and
`docker compose logs web` from the project root. The API assigns an
`X-Correlation-ID` per request; case responses also contain a case correlation
identifier. These are different identifiers. Recovery logs identify a case
and failure class. The web server disables access logs to avoid logging
authorization-code query strings. Treat identifiers and logs as potentially
sensitive, restrict access and retention, and avoid logging tokens, prompts,
model/tool payloads, secrets, or customer data.

**Planned, not implemented:** structured end-to-end telemetry, OpenTelemetry
traces, propagation across boundaries, and configurable Azure Monitor
export. Design must avoid double instrumentation and sensitive or
high-cardinality attributes, test redaction and exporter failure behavior,
and verify actual cloud delivery separately. Local logs do not establish
distributed tracing or cloud observability.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Compose reports a missing variable | Review [setup](setup.md), especially required Entra IDs, factory and URL-safe database password. |
| API does not start | Check PostgreSQL reachability, private checkpoint directory, factory import and validated settings. For existing volumes, the supplied password must match the one already stored; changing the variable is not rotation. |
| Browser configuration or sign-in fails | Rebuild after public configuration changes; check UUIDs, API URI, redirect origin, registration permissions and consent. Live sign-in remains unverified. |
| Protected request returns 401 or 403 | Check token audience, tenant, delegated scope, approver role, and case authorization; never paste tokens into logs. |
| Recovery or action returns 503 | Inspect privacy-safe API logs and checkpoint/database health. Do not delete state or retry external effects blindly; investigate reconciliation and downstream idempotency first. |
| Test database is unavailable | Set `MAF_TEST_DATABASE_URL` to an isolated reachable PostgreSQL database. Tests fail instead of skipping. |
| Readiness is unverified | Review evidence freshness, actual test results and independently administered trust and approval; do not convert an unknown to a pass. |

Volume deletion is destructive; follow the operator's data and backup policy.
The current initialization is not a versioned migration system; migration and
schema-drift adoption are planned work.
