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

## Advisory build-attestation preflight

The [build-attestation preflight](build-attestations.md) checks three
independently specified OCI subjects using GitHub CLI signature verification
and exact source, signer and predicate matching. The policy path, verifier,
builder and trust roots require independent administration; a path check
cannot establish that trust. This preflight does not inspect a deployment,
prove a builder's actual checkout or generated inputs, or authorize release.
The cloud failure-injection hard stop remains in force.

## Fixed offline synthetic runner

The [operator-only runner](offline-synthetic-tests.md) builds a separate image
from an explicit source allowlist and executes the canonical native approval
graph with a fixed in-memory synthetic record. The API, application factories,
business actions and browser are outside this image and are never dispatched.
The host verifies actual Docker isolation before start; runtime probes verify
denied network and filesystem operations before the graph. The reviewed source,
local Docker daemon and host remain trusted. This is not a general application
sandbox, human approval, durable recovery or UI manual-test support. Production
separation of duties and disabled studio callbacks remain unchanged.

## Authorized history and activity

The generic history API uses the existing PostgreSQL `wf_cases` fields for
tenant, owner, assigned reviewer, status, decision, and timestamps. Fixed SQL
predicates filter tenant and `(owner_id = caller OR reviewer_id = caller)`
before status filtering and bounded candidate batches; they are only a
coarse prefilter, not the complete application authorization policy. The
service applies the configured `AccessPolicy.authorize_read` to each complete
candidate before adding it to the public page. It continues stable descending
`(created_at, id)` keyset scans until it has an additional authorized record
or exhausts the candidates, with at most 1,000 candidate authorizations over
10 batches of at most 100 per request. If the budget is exhausted while further
candidates remain and the authorized page is not complete, the service raises
`HistoryScanLimitExceeded`; the API returns a generic 503 without a partial
page, count, or cursor. Permitted records are never silently dropped. Public
pages remain capped at 100 rows, contain no counts or
payload/identity/checkpoint fields, and only expose a versioned, status-bound
cursor from the last returned authorized record when another authorized
record exists. Policy input is never converted into SQL.

Per-record activity reads only committed `wf_audit` rows, repeats the same
tenant/owner/reviewer predicate in SQL, and filters to a fixed event allowlist
before pagination. Public activity contains only fixed generic event types
and timestamps. Unknown event names, actor IDs, payloads, request IDs,
checkpoint IDs, prompts, model responses, and tool contents are not
projected. Application audit state and native MAF continuation/checkpoint
state remain separate. Existing single-case reads and decision endpoints
remain unchanged.

The studio separately refreshes an incomplete selected case through the
authorized case-read endpoint at five-second intervals after each completed
read. Switching cases or signing out invalidates late results; read
authorization failures clear the displayed case. Refresh stops on read error,
execution completion or a reported failure; reopening the case retries it.
This is not a deadline on an in-flight read or proof of cloud availability.

### Live activity

The authenticated activity stream sends only fixed refresh signals and
heartbeats, not audit rows. Each tick revalidates the bearer token and case
read policy; it returns its database connection before waiting. The browser
reconciles by rescanning the existing authorized activity pages and replacing
its snapshot. Reconnects do not resume from a presumed commit watermark: an
audit identity or transaction timestamp can be assigned before a later
commit. Concurrent inserts may require another scan before they appear.

Streams end after 30 seconds; a refresh on a stream sustained for 20 seconds
resets the failure budget. Three short or failed attempts lead to ten-second
polling; clients without a stream implementation also use polling. Token
acquisition and connection deadlines are 15 seconds; the idle
deadline is 20 seconds. Cancellation stops awaiting a token and prevents a
late fetch, but cannot cancel MSAL's underlying operation. Scans start at most once per 15
seconds and stop after 50 pages or 60 seconds, surfacing
an error rather than showing a silently truncated snapshot. A supplied
`Last-Event-ID` must be a valid activity cursor but is only a hint, never a
watermark. Switching accounts or cases cancels the stream and reads. Local
tests do not establish live Entra or cloud proxy behavior. SSE does not submit
synchronous callbacks to an executor. Per process, at most four async I/O
operations and 32 streams run, with a five-second cancellation deadline per
operation. Malformed token headers fail before I/O. Async HTTPS reads a bounded
signing-key response, cached for five minutes per application identity. A single
refresh can run at once; unknown-key and failed refreshes are throttled for 30
seconds. Expired keys are never reused on failure. Rotation to an unknown key
during that throttle may temporarily deny a stream, which can fall back to
authorized polling. The existing delegated-token validator still verifies each
token locally on every tick. Separate async
PostgreSQL connections use read-only mode and five-second connection, statement,
and lock deadlines, and never borrow from the synchronous API pool. Each
connection closes before waiting for another tick.

Streaming supports the standard service, PostgreSQL reader, default case policy,
Entra validator, and password-mode database credentials only. Custom
implementations, managed-identity database credentials (which require synchronous
SDK token acquisition), and the Order Resolution service fail closed to polling.
Tests verify async HTTP cleanup, cancellation of a locked database read,
server deadlines, read-only enforcement, capacity recovery, and authorization.
Platform DNS resolution may still use underlying library executor threads;
DNS hangs, TLS/network black holes, and process-wide shutdown are not proven
bounded.

The case, activity, and history GET handlers share a nonblocking, per-store
polling admission limit for PostgreSQL stores, including the generated Order
Resolution store. At the supported minimum pool size of two, one read is
admitted so healthy polling remains available. This is a compatibility
exception, not a two-connection business reservation: a stalled read can
leave only one connection, while the standard local workflow needs one for its
advisory lock and another for a nested transaction. In a disposable PostgreSQL
reproduction, a simulated stalled read caused a business submission to time
out. Configure at least three connections to leave two outside the polling
limit; at sizes of three or more the limit is `min(4, pool_max_size - 2)`.
Those two slots are not exclusively reserved: other traffic can still exhaust
the pool. At capacity reads return 503 after authentication. A slot stays
occupied until the synchronous handler actually exits, even if its caller
stops waiting. Tests exercise repeated stalled reads, rejection, cleanup and
generated Order Resolution with local PostgreSQL; simulated stalls hold
connections but do not reproduce network black holes.
This is containment, not cancellation or an I/O deadline: a stalled worker
and connection can remain occupied indefinitely. Authentication occurs before
admission and can itself stall. Non-PostgreSQL stores remain unchanged; custom
services, stores, policies or connectors may use additional connections or
spawn work, so their isolation is not established. Managed-identity token
acquisition, network black holes, worker shutdown, and multi-process capacity
are unverified. These remain reliability blockers.

An unsupported service receives a 503 from the stream endpoint before stream
authentication; it sends no activity information. The browser then falls back
to the existing activity API, which independently authenticates and
authorizes each polling request. The failure budget and polling behavior are
client-side recovery, not an exemption from authorization. The UI shows
activity updates and access errors, but does not indicate that polling is active.

## Optional protocol context

The studio has opt-in, read-only context integration points. For a selected
case already returned by the authorized case API, it constructs an AG-UI
`Context` entry containing only a fixed description and JSON-encoded
allowlisted status enum. No ID, payload, checkpoint, actor, prompt, model
output, tool content, client, or mutation callback is passed. The user must
explicitly enable each configured integration for that selection; it is
disabled by default and the UI requests cleanup on stop, case change, or
sign-out. An invalid status is rejected. Status itself may be sensitive:
the configured consumer can transmit it to an agent or service on a later run.

The optional `createAgUiContextAdapter(register)` registers this entry with
an application-owned local consumer, whose returned function unregisters it.
It is the `Context` input shape from [AG-UI 1.0](https://docs.ag-ui.com/sdk/js/core/types),
not an event stream, transport, agent run, or claim of protocol conformance.
No events are fabricated. For CopilotKit v2, an application that explicitly
installs and configures its provider can pass the documented
[`useAgentContext`](https://docs.copilotkit.ai/reference/v2/hooks/useAgentContext)
to `createCopilotKitContextAdapter`; the hook registers the context until
unmount. No optional package is needed by the default application.

For example, after explicitly installing and configuring CopilotKit v2 and
its provider, the application composition root can import
`useAgentContext` from `@copilotkit/react-core` and set
`protocolAdapters.copilotKit = createCopilotKitContextAdapter(useAgentContext)`,
alongside `capabilities.copilotKit = true`. The AG-UI registration receives
the `{ description, value }` context entry and must return a cleanup function;
its consumer decides how to use that entry in a future separately authorized
run. The adapters themselves have no run or transport interface.
The installed `@copilotkit/react-core@2.0.0-rc.53` prerelease exports this
hook from its package root; despite current documentation, that release does
not export the `/v2` subpath. Check the actual package exports when upgrading.

Adapter and provider code is trusted application code, not a sandbox. Owners
must ensure the provider and registration/cleanup do not cause automatic
network or model calls, retain data after revocation, register tools, or
perform mutations. Cleanup is requested, not verifiably enforced; removal
failure is logged generically. Configure an independently authorized endpoint
and data handling before any later run. A protocol integration does not grant
case access, verify authorization, or replace the normal approval workflow.
The application root reports caught component errors generically without
logging exception text or component stacks.
Local verification used `@ag-ui/core@1.0.4`'s `ContextSchema` and the real
`@copilotkit/react-core@2.0.0-rc.53` hook against a synthetic in-process
consumer. This does not establish real provider configuration, remote
service, model, event-stream, or production compatibility.

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
does not add order-specific event content. Evidence and manual tests are
disabled by default; AG-UI and CopilotKit remain reserved flags.

Applications may opt in to `projectEvidence` and return a text-only
`EvidenceProjection` from a selected, already authorized case. Explicitly
allowlist safe fields; never return raw payloads, model/tool/checkpoint/actor
data, or sensitive identifiers. The shell makes no evidence request and does
not verify that the application projection is safe. Projection errors are
reported locally without stopping approval.

The studio never executes `syntheticManualTests` callbacks, even in
development. A browser build flag or omission of a workflow client cannot
prevent trusted application code from accessing real systems. The legacy
configuration remains typed for compatibility but cannot enable execution.
This only disables the studio's manual-test execution path; it does not
sandbox other trusted profile code or ordinary workflow actions. Neither
adapter establishes release evidence or changes authentication, idempotency,
or business state. This is an interim control, not isolated synthetic
execution. A fixed in-process synthetic test would need its entire call graph
and operating boundary audited for effects; restricting one callback
interface does not sandbox the authenticated origin.

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

## Live acceptance credential boundary

The opt-in live browser harness confines session storage to a separately
authorized HTTPS origin and rejects supplied cookies or foreign-origin storage
state. The Order Resolution live acceptance client validates the same kind of
origin before reading auth material and refuses redirects. The model evaluator
requires a separate authorized HTTPS origin and refuses redirects. The operator
must independently authorize and trust that origin and the network path; this does
not verify Entra authentication, deployment provenance, or a compromised
authorized page.
Protected browser API/stream requests and hosted Responses POSTs reject
redirects. A potentially applied hosted POST remains unknown, not retried.
These controls do not constrain top-level navigation or establish trust in
custom factories, configured endpoints, the host, or its proxy.

Case refreshes abort a stalled read and retry transient failures; access
revocation clears the displayed case instead of retrying it. Account changes
and sign-out remount the workspace, discarding the previous account's state.

The hosted failure runner blocks its interruption scenario before invoking an
adapter because its current interface does not verify native continuation.
The Order Resolution live adapter also refuses reconciliation rather than
clearing unknown/interrupted markers on an ordinary case read. This is not a
verified recovery mechanism.
