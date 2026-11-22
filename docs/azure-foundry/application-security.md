# Azure/Foundry application security

This document defines the cloud application boundary for the generated MAF
FastAPI and Order Resolution profile. It does not provision Azure resources,
grant roles, deploy a hosted agent, or establish live readiness.

## Identity and authorization matrix

| Identity | Credential boundary | Authorized purpose | Validation and binding |
| --- | --- | --- | --- |
| Authenticated end user | Delegated Entra v2 bearer token presented only to FastAPI | Submit, read, or decide a case | Validate RS256 signature, tenant, v2 issuer, API audience, lifetime, `tid`, UUID `oid`, non-empty `sub`, delegated scopes, and string roles. Then enforce case tenant, owner/reviewer assignment, `workflow.read`/`write`/`approve`, and `Workflow.Approver`. |
| API managed identity | `DefaultAzureCredential` constrained to the configured API UAMI client ID | Call the hosted workflow and, when selected, acquire an Azure PostgreSQL token | Request only the configured hosted caller `.default` scope or Azure PostgreSQL scope. It never substitutes for end-user authorization and the user bearer token is never forwarded. |
| Hosted execution identity | Agent A-owned hosted runtime identity | Execute the native hosted workflow and access only its approved model/tool resources | Agent A must authenticate the API managed identity and caller scope before accepting a request. The application stores only opaque operation, execution, and request correlation; Foundry owns hosted checkpoint/session bytes. |
| Synthetic downstream tool identity | `order-resolution-synthetic-tool-v1`, with proposal destination identity | Apply and reconcile PostgreSQL-only synthetic effects | Bind case, proposal version, action, destination, effect key, request digest, and body. It receives no user token, API managed-identity token, or hosted execution credential. |

Authorization is fail-closed. A valid API token is not sufficient by itself:
submission, read, and decision policy checks remain application-owned. Order
Resolution additionally binds decisions to the current proposal version,
action, destination, hashed expiring opaque handle, reviewer, tenant, scope,
role, and channel. Stale, duplicate-conflicting, cross-case, or cross-actor
decisions fail without applying an effect.

## Agent A compatibility port

The application depends on `HostedWorkflowClient`, not Foundry SDK types.
Agent A draft PR #45 at reviewed head `565f0d3` uses the Foundry Responses
contract directly: create a conversation as a separate durable operation,
submit the exact `{"case_id": "<uuid>"}` start input with explicit
conversation and agent session IDs, and submit resume input as structured
`function_call_output`. Both start and resume set `store=true` and
`background=true`; resume uses the fixed `foundry-responses` channel. The API
UAMI requests `https://ai.azure.com/.default` and requires `Foundry Agent
Consumer` on the specific hosted agent. No user bearer token is forwarded.

Workstream C supplies the application-owned integration components Agent A
must inject:

- `PostgresHostedIdentityBindings.resolve_principal`, `bind_start`, and
  `authorize_resume` map the authenticated API-UAMI caller plus Foundry
  session/conversation to the previously authorized application principal.
- `PostgresOperationJournal.claim`, `update`, and `get` atomically bind a
  case-scoped operation ID to its digest and preserve pending, acknowledged,
  rejected, or unknown outcomes for operator reconciliation.
- `OrderResolutionStore.prepare_hosted_approval` persists a deterministic,
  opaque hosted request ID and hashed expiring decision binding while leaving
  `checkpoint_id` null.
- `OrderResolutionStore.claim_hosted_decision` atomically records one
  structured decision without requiring a local checkpoint.
- `OrderResolutionStore.finish_hosted` marks only a matching automatic,
  approved, or rejected business outcome complete while leaving
  `terminal_checkpoint_id` null.

Agent A must call `prepare_hosted_approval` before native
`ctx.request_info`, route resume through `claim_hosted_decision`, and call
`finish_hosted` after the native output/action commits. Agent A still needs an
authoritative Responses status/result adapter that extracts the pending
framework request ID and terminal result for the FastAPI `WorkflowHost` port;
the reviewed #45 head returns only the remote response ID. That cross-PR gap
is explicit and must not be hidden with a synthetic success or replay.

The application claims dispatch in PostgreSQL before a network call. A lost
acknowledgment is recorded as `hosted_outcome_unknown`; restart queries the
operation status instead of replaying the dispatch. A returned outcome must
match the locally recorded decision before the application applies its
transactional synthetic action. Hosted checkpoint bytes are never stored in
PostgreSQL.

## PostgreSQL configuration and recovery

Runtime and migration identities are separate configuration surfaces:

- `DATABASE_URL` is the runtime connection and must select the intended
  database/schema.
- `MIGRATION_DATABASE_URL` is used by explicit migration commands and should
  carry schema-owner privileges. It falls back to `DATABASE_URL` only for
  local compatibility.
- `DATABASE_AUTH_MODE` is `managed-identity` or `password`.
- Managed identity mode acquires
  `https://ossrdbms-aad.database.windows.net/.default` on demand and forbids a
  configured password.
- Password mode may receive `DATABASE_PASSWORD` from a secret manager; do not
  put it in frontend configuration or source control.
- Hosted mode requires `DATABASE_TLS_MODE=verify-full`.
- `DATABASE_POOL_MIN_SIZE`, `DATABASE_POOL_MAX_SIZE`,
  `DATABASE_POOL_TIMEOUT_SECONDS`, and
  `DATABASE_CONNECTION_MAX_LIFETIME_SECONDS` bound connection use and ensure
  managed-identity connections expire before their access token.

Migrations remain explicit. API startup validates the exact migration head
without DDL, then application initialization validates profile tables.
Recovery uses PostgreSQL advisory locks and compare-and-set state transitions.
RequestStore, proposal, decision, EffectLedger, action projection, and
destination binding remain atomic. Unknown synthetic acknowledgments require
authoritative observation; they are never silently retried. Verified effects
and action-ledger claims prevent duplicates across concurrent requests,
approval races, worker failure, and restart.

## OBO decision

OBO is not required for this workstream. Hosted workflow calls are
application-to-application calls made with the API managed identity, and the
only downstream effect is synthetic PostgreSQL state owned by the application.
There is no verified user-delegated downstream operation. The pre-existing
optional OBO component remains disabled and allowlist-gated; enabling it would
require a separately reviewed downstream user-delegation requirement and live
consent verification.

## Agent B configuration outputs

The application expects Agent B to provide names/values or secret references
for:

- `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`, allowed CORS origins, and the
  separately configured SPA values.
- `WORKFLOW_HOST=hosted`, `HOSTED_WORKFLOW_ENDPOINT`,
  `HOSTED_WORKFLOW_SCOPE=https://ai.azure.com/.default`,
  `API_MANAGED_IDENTITY_CLIENT_ID`, the API UAMI object/caller identity exposed
  by Foundry, the specific hosted-agent resource ID, Responses/conversation
  endpoints, Foundry project endpoint, model deployment, and
  `Foundry Agent Consumer` assignment.
- `ORDER_RESOLUTION_HOSTED_IDENTITY_BINDINGS=app.order_resolution.hosted_bindings:build_hosted_identity_bindings`
  and
  `ORDER_RESOLUTION_OPERATION_JOURNAL=app.order_resolution.hosted_bindings:build_operation_journal`.
- Runtime `DATABASE_URL`, separate `MIGRATION_DATABASE_URL`,
  `DATABASE_AUTH_MODE`, `DATABASE_TLS_MODE=verify-full`, optional
  `DATABASE_MANAGED_IDENTITY_CLIENT_ID`, and a secret reference for
  `DATABASE_PASSWORD` only when password authentication is selected.
- Pool bounds, `TELEMETRY_MODE=azure-monitor`, and an Application Insights
  connection-string secret reference.

## Evidence and remaining live checks

Local evidence covers token validation, identity separation, explicit host
selection, managed-identity token acquisition boundaries, hosted client
failures, claim-before-send, restart reconciliation without replay,
conflicting outcomes, PostgreSQL migrations, bounded connections, concurrent
duplicates, approval races, unknown acknowledgments, and real-PostgreSQL
hosted pending/approved/rejected/automatic transitions across a restarted
store without local checkpoint IDs. It also covers all ORS-001..009 scenarios,
frontend tests/build, and generated-project independence.

Live-only checks remain unverified: API UAMI token issuance, `Foundry Agent
Consumer`, the exact caller identity exposed to AgentServer, Agent A
status/result adaptation, hosted execution identity/RBAC, Azure PostgreSQL
Entra login and TLS certificate verification, migration/runtime grants,
networking, Foundry pause/resume semantics, actual restart/revision behavior,
Application Insights ingestion, backup/restore, failover, quota, cost, and
deployed browser/evaluation evidence.
