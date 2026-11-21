# Architecture and extensions

This project is independently owned. Its local prototype is a React/MSAL
client, an authenticated FastAPI service, a native Microsoft Agent Framework
(MAF) workflow, and PostgreSQL. [Setup](setup.md) describes the local stack.
The included synthetic application is explicitly selected; it is not a
fallback for a failed model or tool call.

The browser sends bearer tokens to the API. The API validates identity and
authorizes each case, while the use case coordinates policy, the native
workflow, and persistence. The local host uses MAF file checkpoints on a
private single-host volume. PostgreSQL separately holds business records,
decisions, audit records, and the action ledger. A per-case database lock
coordinates transitions; checkpoint and database writes are not one atomic
transaction. Recovery reconciles them. Neither a conversation nor a
checkpoint is a human approval.

## Typed MAF extension patterns

The contracts in `backend/app/extensions/` compose MAF-native components;
they are not a second runtime or a guarantee that a provider is configured.

- **Model selection:** `ModelSelection` requires an explicit provider ID and
  model ID. `select_chat_client` resolves only an application-registered
  `ModelClientFactory` and requires its result to satisfy MAF's
  `SupportsChatGetResponse` contract. Provider factories own endpoints, credentials, client
  lifetime, and provider-specific options. No default provider or fake
  response is installed.
- **Prompt assets and agent construction:** `PromptAsset` is loaded from an
  application-owned, explicitly versioned file. Its SHA-256 content digest
  identifies bytes for reproducibility; it is not a signature, approval, or
  trust proof. `AgentDefinition` binds a prompt name/version and
  `build_chat_agent` constructs MAF `Agent` with its typed chat client
  and registered tools. Prompts are instructions, not authorization.
  Principal-bound agents are request-scoped and must not be shared across
  callers.
- **Tools and authorization:** `ToolRegistry` binds typed MAF
  `FunctionTool` implementations to a trusted, authenticated `Principal` and
  an application-owned `ToolAuthorization`. Each tool must reauthorize the
  principal and model-supplied resource identifiers inside its handler before
  reading protected data or causing an effect. The synthetic tool in
  [synthetic_application.py](../backend/examples/synthetic_application.py)
  demonstrates a scope- and resource-gated read-only call. This example does
  not authorize business decisions or external effects. `ToolRegistry` is
  registration and request-scoped binding convenience only: it does not force
  handlers to authorize, sandbox Python, or provide idempotency. Consequential
  remote effects remain blocked pending the authorization, idempotency/outbox,
  reconciliation, and fault-injection evidence required by [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32).
- **Executor/workflow composition:** implement the existing
  `WorkflowFactory` signature with MAF `Executor` and `WorkflowBuilder`;
  receive the checkpoint provider selected by the host. Keep workflow name,
  executor identity, pending request IDs, response contract, and checkpoint
  ownership stable for the local host. The generated synthetic example uses
  the native approval workflow factory; no generic orchestration layer is
  added. Foundry-managed hosting/checkpoints and recovery remain unverified
  under [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19),
  [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20), and
  [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22).

The generated synthetic application constructs a MAF `Agent` from an
application-supplied MAF client, prompt asset, and authorization-bound tool,
but it does not call a model. No real provider credentials or model response
are available as test evidence. Model input and tool arguments remain
untrusted; API authorization, persisted human decisions, recovery, idempotency,
and readiness gates remain outside the model. Consequential external effects
remain blocked by [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32).

## Application and UI extension recipes

1. Implement application-owned rules, access policy, transactional action,
   optional initialization, and optionally a workflow factory. Return
   `ApplicationComponents` from a no-argument factory; see
   [synthetic_application.py](../backend/examples/synthetic_application.py)
   and [application.py](../backend/app/application.py). Select it using
   `BLUEPRINT_APPLICATION=module:function`. Add application-owned files to
   the backend image build context and Dockerfile; the supplied Dockerfile
   copies only `app` and `examples`.
2. The default local host expects a workflow producing a request with
   `case_id` and a matching outcome. Keep this contract or supply a suitable
   native MAF host. Preserve per-case authorization, durable decisions,
   locking and crash recovery when replacing state or host adapters.
3. Compose the UI with `WorkflowWorkspace`, a `WorkflowClient`, and a
   `renderCase` function; see [workspace.tsx](../frontend/src/workspace.tsx)
   and [api.ts](../frontend/src/api.ts). Do not put credentials in the
   browser or treat client-provided identity as authoritative.
4. A database action and ledger entry can commit together in one PostgreSQL
   transaction. The transaction callback is arbitrary application code, not a
   sandbox; it can make external calls that the database ledger cannot roll
   back or deduplicate. Do not put consequential remote effects in that path.
   Keep them blocked until #32 is independently verified. The local ledger
   proves neither external idempotency nor a general exactly-once guarantee.

The [testing guide](testing.md) describes the synthetic evidence and its
limits. Foundry-managed checkpoints and hosting are planned and unverified;
they must not be conflated with local file storage.

The [staged infrastructure](../infra/README.md) defines a Foundry
account/project with public data-plane access disabled, a private PostgreSQL
server, and monitoring resources with public ingestion/query disabled, plus
optional separate API/UI Container Apps and an authenticated registry. It
does not provide working Foundry or monitoring private connectivity, API database
token authentication, or the hosted-agent service. A project-wide agent-consumer
grant is opt-in and disabled; its eventual scope and inherited grants require
review. Offline compilation is not cloud integration evidence.
