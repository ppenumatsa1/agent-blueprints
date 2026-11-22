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

## Extension recipes

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
   host. Preserve per-case authorization, durable decisions, locking and
   crash recovery when replacing state or host adapters.
3. Compose the UI with `WorkflowWorkspace`, a `WorkflowClient`, and a
   `renderCase` function; see [workspace.tsx](../frontend/src/workspace.tsx)
   and [api.ts](../frontend/src/api.ts). Do not put credentials in the
   browser or treat client-provided identity as authoritative.
4. A database action and ledger entry can commit together; this does not
   prevent the application callback from making remote calls. Consequential
   effects require service-specific authorization, verified downstream
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

The [staged infrastructure](../infra/README.md) defines a Foundry
account/project with public data-plane access disabled, a private PostgreSQL
server, and monitoring resources with public ingestion/query disabled, plus
optional separate API/UI Container Apps and an authenticated registry. It
does not provide working Foundry or monitoring private connectivity, API database
token authentication, or the hosted-agent service. A project-wide agent-consumer
grant is opt-in and disabled; its eventual scope and inherited grants require
review. Offline compilation is not cloud integration evidence.
