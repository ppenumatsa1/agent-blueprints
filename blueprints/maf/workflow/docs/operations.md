# Observability design and troubleshooting

## Current signals

Use local process output or `docker compose logs api` and `docker compose logs
web`. The backend emits structured JSON operation logs and manual OTel spans
and metrics for HTTP, workflow, selected database operations and OBO. The
web server disables access logs. The request's server-generated
`X-Correlation-ID` matches its log; a case correlation identifier is separate.
Only W3C `traceparent` is accepted from clients; baggage and tracestate are
discarded. Correlation is diagnostic, not authorization. Outbound and Foundry
host propagation remain unimplemented.

`TELEMETRY_MODE=local` is the default: no telemetry is exported and no local
collector is required. Explicit `TELEMETRY_MODE=azure-monitor` requires an
existing `APPLICATIONINSIGHTS_CONNECTION_STRING` from a secret manager.
Missing or invalid configuration or exporter initialization fails startup with
a sanitized error. Once initialized, failed exports or flushes emit fixed
failure signals without changing workflow outcomes; data may be lost.
The periodic metric interval can be set with `OTEL_METRIC_EXPORT_INTERVAL`
in milliseconds.

Span creation, metadata, propagation and closure failures emit the fixed
`telemetry.instrumentation` failure signal. The operation runs once and its
original exception is preserved; diagnostic context can be lost. Partial
telemetry initialization and pre-startup failures attempt resource cleanup.

`blueprint.operations` and `blueprint.operation.duration` have only allowlisted
operation and outcome dimensions; exemplars are disabled. The exporter uses
static non-identifying device and service-instance values rather than host
names. Do not add tokens, claims, prompts, tool inputs or outputs, SQL
parameters, business identifiers, payloads or exception text. Azure SDK
diagnostic logging, Statsbeat, SDK statistics and remote configuration are
disabled as described in the [README](../README.md). Restrict log access and
retention; review any additional instrumentation for privacy and duplication.
Configuration and local in-memory tests do not prove hosted ingestion.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Compose reports a missing variable | Review [setup](setup.md), especially required Entra IDs, factory and URL-safe database password. |
| API does not start | Check PostgreSQL reachability, private checkpoint directory, factory import and validated settings. For existing volumes, the supplied password must match the one already stored; changing the variable is not rotation. |
| Telemetry startup fails | Check the selected mode and connection string without exposing the secret; initialization errors are deliberately sanitized. |
| Telemetry export failure signal | Inspect the hosted export path using approved operational access; failures do not imply workflow failure, and lost telemetry may not be recoverable. Cloud ingestion is unverified. |
| Telemetry instrumentation failure signal | Check SDK health without logging exception details; missing diagnostic context does not imply the operation was retried. |
| Schema validation fails | Run a reviewed migration using the schema-owner identity; investigate drift or an unknown revision rather than stamping or deleting state. See [migration operations](../README.md#business-database-migrations). |
| Browser configuration or sign-in fails | Rebuild after public configuration changes; check UUIDs, API URI, redirect origin, registration permissions and consent. Live sign-in remains unverified. |
| Protected request returns 401 or 403 | Check token audience, tenant, delegated scope, approver role, and case authorization; never paste tokens into logs. |
| Recovery or action returns 503 | Inspect privacy-safe API logs and checkpoint/database health. Do not delete state or retry external effects blindly; investigate reconciliation and downstream idempotency first. |
| Test database is unavailable | Set `MAF_TEST_DATABASE_URL` to an isolated reachable PostgreSQL database. Tests fail instead of skipping. |
| Readiness is unverified | Review evidence freshness, actual test results and independently administered trust and approval; do not convert an unknown to a pass. |

Volume deletion is destructive; follow the operator's data and backup policy.
The baseline has no automatic downgrade; coordinate database and checkpoint
recovery from verified backups.
