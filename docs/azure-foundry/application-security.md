# Azure/Foundry application security

This document defines the cloud application boundary for the generated MAF
FastAPI and Order Resolution profile. It does not provision Azure resources,
grant roles, deploy a hosted agent, or establish live readiness.

## Identity and authorization matrix

| Identity | Credential boundary | Authorized purpose | Validation and binding |
| --- | --- | --- | --- |
| Authenticated end user | Delegated Entra v2 bearer token presented only to FastAPI | Submit, read, or decide a case | Validate RS256 signature, tenant, v2 issuer, API audience, lifetime, `tid`, UUID `oid`, non-empty `sub`, delegated scopes, and string roles. Then enforce case tenant, owner/reviewer assignment, `workflow.read`/`write`/`approve`, and `Workflow.Approver`. |
| API managed identity | Explicit `ManagedIdentityCredential` for Foundry calls and the configured API UAMI for PostgreSQL token acquisition | Call the hosted workflow and acquire the Azure PostgreSQL token | It is the only runtime PostgreSQL principal. It requests only the Foundry caller or PostgreSQL scope, never substitutes for end-user authorization, and never forwards the user bearer token. |
| Hosted execution identity | Agent A-owned hosted runtime identity | Execute the native workflow and call the protected FastAPI hosted-state API | FastAPI validates an app-only token for the API audience, exact hosted service-principal object ID, and the fixed `Hosted.Workflow.Invoke` app role. The token must not contain delegated `scp`. The hosted runtime receives no PostgreSQL URL, TLS setting, password, or database role. |
| Synthetic downstream tool identity | `order-resolution-synthetic-tool-v1`, with proposal destination identity | Apply and reconcile PostgreSQL-only synthetic effects | Bind case, proposal version, action, destination, effect key, request digest, and body. It receives no user token, API managed-identity token, or hosted execution credential. |

Authorization is fail-closed. A valid API token is not sufficient by itself:
submission, read, and decision policy checks remain application-owned. Order
Resolution additionally binds decisions to the current proposal version,
action, destination, hashed expiring opaque handle, reviewer, tenant, scope,
role, and channel. Stale, duplicate-conflicting, cross-case, or cross-actor
decisions fail without applying an effect.

## Agent A compatibility ports

The generated FastAPI backend imports the API-only Agent A
`order_resolution_hosted.bridge` and `client` modules copied into that backend.
It does not import the sibling hosted-agent runtime or hosting SDK. Missing
bridge packaging fails closed. The aligned adapter uses the Foundry Responses contract
directly: create a conversation as a separate durable operation,
submit the exact `{"case_id": "<uuid>"}` start input with explicit
conversation and no caller-selected agent session ID, and submit resume input as structured
`function_call_output`. Both start and resume set `store=true` and
`background=true`; resume uses the fixed `foundry-responses` channel. The API
UAMI requests `https://ai.azure.com/.default` and requires `Foundry Agent
Consumer` on the specific hosted agent. No user bearer token is forwarded.

Workstream C supplies two narrow integration adapters:

- `PostgresHostedAuthorityBindings` accepts only an already authenticated
  application `Principal`. Start persists the server-selected
  case/conversation/channel binding before Responses dispatch. Resume loads
  that exact conversation binding, revalidates the reviewer, proposal, hashed expiring
  handle, channel, and command, then atomically persists decision intent before
  `function_call_output` dispatch. It does not record the business decision.
- `PostgresOperationJournal` is instantiated inside the API process beside
  Agent A's `ResponsesClient`. It converts PostgreSQL rows to Agent A's exact
  `OperationRecord`, `OperationStatus`, and
  `OperationClaim(record=..., acquired=...)` types. Only the transaction that
  inserts a pending operation acquires send ownership; existing operations
  never reacquire.
- Agent A's hosted runtime uses `HttpHostedBusinessStore` to call the
  application-owned HTTPS contract below. It never imports PostgreSQL
  configuration or opens a database connection.
- `OrderResolutionStore.prepare_hosted_approval` persists a deterministic,
  opaque hosted request ID and hashed expiring decision binding while leaving
  `checkpoint_id` null.
- `OrderResolutionStore.claim_hosted_decision` accepts only a callback that
  exactly matches the pre-established decision intent and atomically records
  one structured decision without requiring a local checkpoint.
- `OrderResolutionStore.finish_hosted` marks only a matching automatic,
  approved, or rejected business outcome complete while leaving
  `terminal_checkpoint_id` null.

Agent A must call `prepare_hosted_approval` before native
`ctx.request_info`, route resume through `claim_hosted_decision`, and call
`finish_hosted` after the native output/action commits. Agent A's native workflow owns action invocation. The API does not replay it
or apply the action after receiving a synthetic hosted result. The application
journal claims each Responses create before network send; a lost
acknowledgment becomes `unknown` and is reconciled authoritatively rather than
replayed. PostgreSQL projects the verified business outcome, while hosted
`checkpoint_id` and `terminal_checkpoint_id` remain null.

## Internal hosted-state HTTP contract

The frozen base path is `/api/internal/hosted/v1`. Agent B supplies the full
HTTPS origin plus this path as `ORDER_RESOLUTION_API_ENDPOINT`; Agent A
requests `ORDER_RESOLUTION_API_SCOPE=api://<API-client-id>/.default`.

Every request requires an app-only bearer token with:

- the configured Entra tenant and v2 issuer;
- audience equal to `ENTRA_API_CLIENT_ID` or `ENTRA_API_APP_ID_URI`;
- `oid` equal to `HOSTED_SERVICE_PRINCIPAL_ID`;
- role value exactly `Hosted.Workflow.Invoke`; and
- no delegated `scp` claim.

All request bodies reject unknown fields. The common binding is:

```json
{
  "platform_user_id": "opaque Foundry workload user",
  "platform_session_id": "opaque Foundry session",
  "platform_call_id": "opaque per-invocation call",
  "conversation_id": "opaque Foundry conversation",
  "channel": "foundry-responses"
}
```

The platform user/session/call values are correlation, not authorization
claims. They may change between invocations and never map to the human
principal. These service-MI routes are verification-only and cannot create an
owner/reviewer `Principal`, grant scopes or roles, or infer authority from case
fields. An authenticated human API start command creates the Foundry
conversation and prebinds the case, server-selected conversation, and channel
to the validated owner
before Responses dispatch. An authenticated human API resume command resolves
that exact binding, validates reviewer authority and decision identity, and
persists intent before `function_call_output`. Missing bindings return `404`;
mismatched conversation, channel, or principal kind returns `403`. Every
binding lookup reauthorizes current PostgreSQL state; verification results are
not cached by an idempotency record, so revoked or changed authority fails
closed.
For an approved, rejected, or completed case, an identical authenticated human
resume is accepted only when the stored reviewer principal, conversation,
channel, proposal, handle digest, decision intent, and authoritative decision
all match. The bridge then reaches Agent A's completed operation journal and
returns the recorded Responses result without another dispatch or effect.
Changed principals, conversations, channels, or command content fail closed.

State-changing requests other than the verification-only binding lookups
require a bounded `Idempotency-Key` beginning with
`case:<case-uuid>:`. FastAPI hashes the operation label and canonical JSON
body, persists that digest in PostgreSQL, rejects key reuse with different
content, and safely replays matching business mutations through the existing
idempotent stores and effect ledger. The per-invocation `platform_call_id` is
excluded from this logical digest; authoritative business fields,
conversation/channel, and platform user/session correlation remain bound.

| Route | Request additions | Response |
| --- | --- | --- |
| `POST /cases/{case_id}/bindings/start` | common binding | previously bound owner `PrincipalOutput`; never creates authority |
| `POST /cases/{case_id}/bindings/resume` | common binding | previously bound reviewer `PrincipalOutput`; never creates authority |
| `POST /cases/{case_id}/read` | common binding plus `principal_kind: "owner" \| "reviewer"` | case fields excluding local checkpoint data |
| `POST /cases/{case_id}/proposal/read` | common binding plus `principal_kind` | current `Proposal` |
| `POST /cases/{case_id}/approvals/prepare` | common binding plus `request_id` | prepared `Proposal` |
| `POST /cases/{case_id}/decisions/claim` | common binding plus `proposal_version`, `action`, `destination_id`, `handle`, and `decision` | authoritative `DecisionRecord` |
| `POST /cases/{case_id}/effects/apply` | common binding plus `mode: "automatic" \| "approved" \| "rejected"` | projected case |
| `POST /cases/{case_id}/finish` | common binding plus the same `mode` | completed case |

`PrincipalOutput` contains exactly `tenant_id`, `subject`, `scopes`, and
`roles`. Case output contains exactly `id`, `tenant_id`, `owner_id`,
`reviewer_id`, `payload`, `status`, `decision`, `request_id`,
`execution_complete`, and `failure_code`. Proposal and decision output match
the generated `Proposal` and `DecisionRecord` fields. No route accepts or
returns Foundry checkpoint bytes.

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
- `DATABASE_TLS_ROOT_CERT` or libpq-compatible `PGSSLROOTCERT` must select
  `system` or the generated container CA bundle at
  `/etc/ssl/certs/ca-certificates.crt`; TLS `require` without host verification
  is rejected.
- `DATABASE_POOL_MIN_SIZE`, `DATABASE_POOL_MAX_SIZE`,
  `DATABASE_POOL_TIMEOUT_SECONDS`, and
  `DATABASE_CONNECTION_MAX_LIFETIME_SECONDS` bound connection use and ensure
  managed-identity connections expire before their access token.

Store and operation-journal factories are lazy: they do not instantiate
`DefaultAzureCredential`, acquire a database token, open a connection, or run
schema checks during composition. Credential and token acquisition occurs only
when the API opens its first connection. The hosted runtime has no database
factory or database configuration.

Migrations remain explicit, including the hosted decision-intent table. API startup validates the exact migration head
without DDL, then application initialization validates profile tables.
Recovery uses PostgreSQL advisory locks and compare-and-set state transitions.
RequestStore, proposal, decision, EffectLedger, action projection, and
destination binding remain atomic. Unknown synthetic acknowledgments require
authoritative observation; they are never silently retried. Verified effects
and action-ledger claims prevent duplicates across concurrent requests,
approval races, worker failure, and restart.
Hosted startup does not redispatch recoverable work without an authenticated
human command. Durable operation claims and decision intent remain available
for an authorized retry and callback reconciliation; there is no local or
synthetic fallback.

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
  separately configured SPA values; `ENTRA_API_APP_ID_URI` when an app-ID URI
  is used.
- `WORKFLOW_HOST=hosted`, `HOSTED_WORKFLOW_ENDPOINT`,
  `HOSTED_CONVERSATION_ENDPOINT`,
  `HOSTED_WORKFLOW_SCOPE=https://ai.azure.com/.default`,
  `API_MANAGED_IDENTITY_CLIENT_ID`, the API UAMI object identity, the specific
  hosted-agent resource ID, Responses/conversation
  endpoints, Foundry project endpoint, model deployment, and
  `Foundry Agent Consumer` assignment.
- `HOSTED_SERVICE_PRINCIPAL_ID` set to the hosted runtime managed-identity
  object ID and `HOSTED_SERVICE_APP_ROLE=Hosted.Workflow.Invoke`, with that
  application role assigned only to the authorized hosted principal.
- Hosted-runtime `ORDER_RESOLUTION_API_ENDPOINT` and
  `ORDER_RESOLUTION_API_SCOPE=api://<API-client-id>/.default`. The hosted
  runtime must not receive `DATABASE_URL`, `MIGRATION_DATABASE_URL`,
  `PGSSLROOTCERT`, database credentials, or PostgreSQL roles.
- Runtime `DATABASE_URL`, separate `MIGRATION_DATABASE_URL`,
  `DATABASE_AUTH_MODE`, `DATABASE_TLS_MODE=verify-full`,
  `DATABASE_TLS_ROOT_CERT=system` or `PGSSLROOTCERT=system`, optional
  `DATABASE_MANAGED_IDENTITY_CLIENT_ID`, and a secret reference for
  `DATABASE_PASSWORD` only when password authentication is selected.
- Pool bounds, `TELEMETRY_MODE=azure-monitor`, and an Application Insights
  connection-string secret reference.

## Evidence and remaining live checks

Local evidence covers token validation, identity separation, explicit host
selection, managed-identity token acquisition boundaries, hosted client
adapter absence failing closed, claim-before-send, restart reconciliation without replay,
conflicting outcomes, PostgreSQL migrations, bounded connections, concurrent
duplicates, approval races, unknown acknowledgments, and real-PostgreSQL
hosted pending/approved/rejected/automatic transitions across a restarted
store without local checkpoint IDs. A real PostgreSQL 17 plus loopback HTTP
test composes Agent A's live `HttpHostedBusinessStore`, `ResponsesClient`, and
C's `PostgresOperationJournal`: service-token validation, start/resume
binding, native `/conversations?api-version=v1`, native
`/responses?api-version=v1`, structured `function_call_output`, exact Agent A
journal types, and duplicate/restarted acknowledged operations without a
second POST all pass with one decision and one effect. Repeated verification
with changed platform call IDs reauthorizes current binding state; revoked
owner authority and changed decision intent fail. Business replay with a
changed platform call ID returns the authoritative existing outcome after
restart, while a changed decision command conflicts. Exact approved and
rejected post-terminal human retries return through Agent A's acknowledged
journal without a second `/responses` call; unauthorized and conflicting
retries fail. It also covers all ORS-001..009 scenarios,
frontend tests/build, and generated-project independence.

Live-only checks remain unverified: API UAMI token issuance, `Foundry Agent
Consumer`, the exact caller identity exposed to AgentServer, Agent A
status/result adaptation, hosted API app-role issuance, Azure PostgreSQL
Entra login and TLS certificate verification, migration/runtime grants,
networking, Foundry pause/resume semantics, actual restart/revision behavior,
Application Insights ingestion, backup/restore, failover, quota, cost, and
deployed browser/evaluation evidence.
