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

- **Model selection:** `ModelSelection` is a small application-owned
  configuration value with explicit provider and model IDs; it is not a
  replacement for MAF's client protocol. The application resolves its selected
  provider-specific client and passes the MAF `SupportsChatGetResponse`
  directly to `Agent`. The synthetic fixture accepts a provider mapping only
  to test that selection; it adds no reusable provider registry or factory
  protocol. No default provider or fake response is installed.
- **Prompt assets and agent construction:** `PromptAsset` is loaded from an
  application-owned, explicitly versioned file. Its SHA-256 content digest
  identifies bytes for reproducibility; it is not a signature, approval, or
  trust proof. The app supplies `PromptAsset.instructions`, its configured
  client, and tools directly to MAF `Agent`; the SDK already owns agent
  construction. Prompts are instructions, not authorization. Principal-bound
  agents are request-scoped and must not be shared across callers.
- **Tools and authorization:** The synthetic fixture uses MAF's native
  `@tool` decorator and gives the resulting `FunctionTool` directly to
  `Agent`. It binds the authenticated `Principal` in a request-scoped closure.
  The only custom boundary is application-owned `ToolAuthorization`, because
  MAF tool registration does not authorize application resources. Each handler
  must reauthorize the principal and model-supplied resource identifiers before
  reading protected data or causing an effect; the callback must return exactly
  `True`, and the example rejects `False` or `None`. The example demonstrates a
  scope- and resource-gated read-only call; it does not authorize business
  decisions or external effects. No generic tool registry is needed, and direct
  registration does not sandbox Python or provide idempotency. Consequential
  remote effects remain blocked pending service-specific authorization,
  verified downstream idempotency, authoritative reconciliation, and
  fault-injection evidence required by [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32).
  An outbox persists intent but cannot deduplicate a downstream effect after a
  lost acknowledgment; without verified idempotency and reconciliation, fail
  closed and use manual resolution.
- **Reference alignment:** At pinned `foundry-public` revision
  [`4543075`](https://github.com/ppenumatsa1/maf-monorepo/tree/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/underwriting/foundry-public/backend),
  `create_foundry_maf_client` constructs the configured provider client,
  `build_underwriting_workflow` composes concrete `Executor` instances with
  `WorkflowBuilder` and host-provided checkpoint storage, and prompt content
  is built by a direct application function. This blueprint follows those
  native composition seams rather than copying the reference's separate
  wrappers. Its model client's synthetic fallback is deliberately not reused;
  failed or unavailable model calls must not become fabricated output.
- **Extension limits:** Typed contracts and fixture tests do not sandbox
  arbitrary trusted Python callbacks or prove that every possible extension
  cannot bypass authorization, approval, recovery, idempotency, or readiness.
  That absolute non-bypass acceptance criterion remains unverified; adopters
  must review and test each callback and keep consequential effects blocked.
- **Executor/workflow composition:** implement the existing
  `WorkflowFactory` signature with MAF `Executor` and `WorkflowBuilder`;
  receive the checkpoint provider selected by the host. Keep workflow name,
  executor identity, pending request IDs, response contract, and checkpoint
  ownership stable for the local host. The generated synthetic example uses
  an application-owned `SyntheticApprovalExecutor` and workflow factory while
  preserving the host-required workflow name, executor ID, request/response
  shape, and host-supplied checkpoint provider. Its source/generated
  integration tests exercise approval, rejection, restart, and both local
  crash-recovery windows. No generic orchestration layer is added.
  Foundry-managed hosting/checkpoints and recovery remain unverified
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
   Such effects require service-specific authorization, verified downstream
   idempotency and authoritative reconciliation; otherwise fail closed and
   use manual resolution instead of retrying an ambiguous effect. A transactional
   outbox only persists intent; it cannot deduplicate an external effect after
   a lost acknowledgment. Test retries and recovery windows; no general
   exactly-once guarantee is implied. Model and tool input remain untrusted.

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
