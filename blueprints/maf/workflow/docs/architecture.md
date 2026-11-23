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

## Authorized history and activity

The generic history API uses the existing PostgreSQL `wf_cases` fields for
tenant, owner, assigned reviewer, status, decision, and timestamps. Its SQL
filters tenant and `(owner_id = caller OR reviewer_id = caller)` before
status filtering, descending `(created_at, id)` keyset pagination, and a
maximum 100-row page. It returns no counts or payload/identity/checkpoint
columns. Cursors carry the last authorized sort position, are versioned, and
are bound to the selected status filter.

Per-record activity reads only committed `wf_audit` rows, repeats the same
tenant/owner/reviewer predicate in SQL, and filters to a fixed event allowlist
before pagination. Public activity contains only fixed generic event types
and timestamps. Unknown event names, actor IDs, payloads, request IDs,
checkpoint IDs, prompts, model responses, and tool contents are not
projected. Application audit state and native MAF continuation/checkpoint
state remain separate. Existing single-case reads and decision endpoints
remain unchanged.

## Typed MAF extension patterns

Hosted composition is a separate infrastructure adapter, not a second
application framework. The composition root accepts only an integrated Agent
A `WorkflowHost` adapter and fails closed when it is absent. This project does
not invent `/runs` routes or duplicate the native Responses workflow in the
API. The adapter may use the API UAMI, but it never carries the user's bearer
token. Agent A owns hosted execution, checkpoint/session bytes, and native
action invocation; PostgreSQL owns business state, opaque correlation, and
effect idempotency.

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
- **Evaluation contracts (#25):** applications define versioned
  `EvaluationDataset` cases and an `EvaluationRubric` with explicit finite
  score thresholds. The application invokes MAF's native `Evaluator`,
  `LocalEvaluator`, `@evaluator`, and `evaluate_agent()` APIs; this extension
  owns no evaluator protocol or orchestration wrapper. Before mapping or
  reporting unavailable results, the application passes the unique readiness
  check IDs from its selected contract to `validate_for`,
  `map_evaluation_results`, or `unavailable_assessment`. This list is a
  consistency input, not trusted authorization or a substitute for the
  independent validator. Unknown, malformed, or duplicate configured check
  IDs reject before the application invokes the native evaluator.
  `map_evaluation_results` normalizes native per-item scores to one
  `CheckEvaluation` per readiness check ID. Scores for a criterion not mapped
  to that case are rejected rather than ignored. Missing observations or
  unavailable native results remain unverified; below-threshold, duplicate,
  unknown, or malformed observations fail. Invalid thresholds, including oversized
  integers, reject before evaluation; invalid observation scores fail closed.
  Exceptions from the native evaluator/provider/tool propagate without
  synthetic fallback. Trace references and scores are not evidence bytes,
  digests, or authenticated provenance, and do not change the independent
  readiness validator. The explicitly named synthetic fixture exercises
  native local evaluation with synthetic responses and result mapping only;
  no live model quality or browser end-to-end hint was verified. See
  [evaluation.py](../backend/app/extensions/evaluation.py) and the
  [evaluation tests](testing.md#evaluation-extension-tests).

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
3. Compose the UI with `StudioShell`, a `WorkflowClient`, and a
   generation-time `WorkflowStudioProfile`; see
   [studio-shell.tsx](../frontend/src/components/studio-shell.tsx),
   [studio-profile.tsx](../frontend/src/studio-profile.tsx), and
   [api.ts](../frontend/src/api.ts). Profiles may supply labels, safe payload
   projections/rendering, disabled capability flags, and an application-owned
   decision binding. They cannot change endpoints, token scopes, record
   authorization, reviewer validation, idempotency, or recovery behavior. Do
   not put credentials in the browser or treat client-provided identity as
   authoritative.
4. A database action and ledger entry can commit together in one PostgreSQL
   transaction; this does not prevent an application callback from making
   remote calls. The callback is arbitrary trusted Python, not a sandbox, and
   the database ledger cannot roll back or deduplicate a remote effect. Do not
   put consequential remote effects in that path. Such effects require
   service-specific authorization, verified downstream
   idempotency and authoritative reconciliation; otherwise fail closed and
   use manual resolution rather than retrying an ambiguous effect. The opt-in
   [external-effect pattern](../backend/examples/external_effect_boundary.py)
   checks application-supplied authorization for the approved case and exact
   request before reconciliation or sending, and uses
   the key `case:{case.id}:action` for the current single immutable action
   per case, plus a digest of the case, tenant, owner, reviewer,
   operation, destination identity and payload. The application must pin the
   actual destination, operation and encoding across the full recovery horizon;
   an identifier cannot prevent a trusted adapter from switching services.
   This narrow key does not represent proposal versions. A future Order
   Resolution implementation must derive its server-side action identity from
   the case, proposal version, action and intended destination, as specified
   by [the merged #40 proposal](https://github.com/ppenumatsa1/agent-blueprints/blob/main/docs/order-resolution-specification-proposal.md);
   this blueprint does not add proposal-version machinery.
   A trusted destination must atomically bind the key and digest to
   the effect, reject conflicting reuse, retain that binding for the entire
   retry/recovery horizon, and provide authoritative request-bound
   reconciliation. `UNKNOWN`, a conflict, or an unverifiable acknowledgment
   fails visibly; an empty or eventually consistent search is not proof of
   absence. A lost send response is reconciled on the next attempt, not
   assumed successful. A transactional outbox only persists intent; it cannot
   deduplicate an external effect after a lost acknowledgment.

   This pattern runs inside the existing action transaction and holds the
   case row lock during remote calls; it is not an outbox or a worker queue.
   It gives all downstream `observe`/`send` calls one shared five-second
   monotonic deadline and passes each adapter the remaining budget. The
   synthetic SQLite adapter applies that budget to lock waits. A real adapter
   must enforce a bounded transport/request timeout within the supplied budget;
   this synchronous pattern cannot preempt arbitrary Python that ignores it.
   Keep the budget within the database lock/transaction operational limits.
   A timeout is an unknown outcome, never proof the effect was not applied:
   the PostgreSQL transaction rolls back, and recovery must reauthorize and
   reconcile the same key and digest. Only authoritative `APPLIED` permits
   ledger completion; proven `ABSENT` may send, while `UNKNOWN` remains
   blocked for operator resolution. Never blindly retry after timeout.
   The application must validate identity, approval, effect-specific authority,
   immutable intent, destination guarantees, retention and safe
   operational recovery. Its authorizer and destination adapters are trusted
   code, not a sandbox: arbitrary Python can bypass this pattern or falsely
   report a guarantee. A changed or revoked authorization blocks even
   reconciliation; operators must resolve ambiguous outcomes without blindly
   retrying. No arbitrary service, hosted behavior, or exactly-once guarantee
   is established. Consequential remote actions remain P0-blocked by
   [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32) pending
   independent, service-specific evidence. Model and tool input remain untrusted.

The [testing guide](testing.md) describes the synthetic evidence and its
limits. Foundry-managed checkpoints and hosting are planned and unverified;
they must not be conflated with local file storage.

## Explicit generation profiles

The repository generator may copy this framework-native project and then apply
the named `order-resolution` overlay. That overlay is application source, not a
registry, plugin framework, template compiler, or dependency on the blueprint
repository. It selects concrete Order Resolution rules, database-only effects,
native `WorkflowBuilder` composition, and UI rendering while retaining this
project's FastAPI, React, PostgreSQL, Compose, lock files, and local MAF host.
The default generator path applies no profile and remains byte-for-byte
compatible with the base copy.

The profile copies the authoritative
`scenarios/order-resolution/acceptance-contract.json` and
`scenarios/order-resolution/golden-cases.json` from merged
[#42](https://github.com/ppenumatsa1/agent-blueprints/pull/42) into the generated
verification tree, together with `tests/test_order_resolution_contract.py`.
The generated runtime does not read those assets or this repository. Explicit
asset overrides exist only for isolated generator tests; they do not replace
the canonical generated assets.

The base frontend includes a generic `WorkflowStudioProfile` with no
Order Resolution vocabulary. UX Layer 2 adds reusable profile-owned history
and activity labels, status-filtered navigation, and a safe timeline over the
generic API. The named overlay replaces that profile with application labels,
payload projection, and proposal decision binding while retaining the same
protected API and MSAL client; its history UI reuses the generic labels and
does not add order-specific event content. Evidence, manual tests, AG-UI, and
CopilotKit remain disabled flags and belong to later layers.

The profile keeps framework and application state distinct. Low-risk proposals
run through a concrete MAF `Executor` and `WorkflowBuilder` to a terminal native
checkpoint. Approval-required proposals persist a native pause before an
authorized decision can resume the same workflow. Missing, conflicting, or
invalid policy evidence persists a terminal application failure without
creating a proposal or checkpoint. PostgreSQL records the synthetic
database-only action and action claim; it is not the MAF checkpoint provider
and does not establish remote exactly-once effects.

Optional profile-root `backend/` and `verification/` trees merge after the
explicit overlay. This is the deterministic integration seam for the reserved
durability/effect/migration and evaluation/readiness implementations. The
generated Order Resolution application owns those merged files and does not
read the source repository at runtime.

The evaluation overlay uses MAF's native `Evaluator`, `LocalEvaluator`,
`@evaluator`, and `evaluate_agent()` APIs and the existing application-owned
readiness mapper. Its versioned dataset references `ORS-001` through `ORS-009`
and derives expected values from the copied canonical golden cases rather than
re-encoding them. The evidence runner keeps deterministic business and
technical results separate from real model quality, browser evidence, and
trusted provenance. Local result files and digests are not independently
attested evidence.

The [staged infrastructure](../infra/README.md) defines a Foundry
account/project with public data-plane access disabled, a private PostgreSQL
server, and monitoring resources with public ingestion/query disabled, plus
optional separate API/UI Container Apps and an authenticated registry. It
does not provide working Foundry or monitoring private connectivity, API database
token authentication, or the hosted-agent service. A project-wide agent-consumer
grant is opt-in and disabled; its eventual scope and inherited grants require
review. Offline compilation is not cloud integration evidence.
