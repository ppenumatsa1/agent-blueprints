# Cross-framework Order Resolution specification proposal

## Status and scope

This Phase 0 document proposes business behavior and conformance requirements
for future Order Resolution blueprints. It is not a runnable template, shared
runtime, deployment authorization, release gate, or claim that any framework
implementation currently conforms.

The proposal was informed by the public MAF Order Resolution reference at
[`45430753c5f3e75716ea3822d2b2b52fbb4f1c34`](https://github.com/ppenumatsa1/maf-monorepo/tree/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/order-resolution/foundry-public).
Only architectural behavior and public synthetic examples were considered.
No reference source, customer data, tenant settings, credentials, deployment
configuration, or private evidence is copied here.

Normative terms such as **MUST**, **MUST NOT**, **SHOULD**, and **MAY** describe
the proposed requirements for a future conforming blueprint. They do not
describe functionality already implemented in this repository.

## Goals and non-goals

The specification defines one framework-neutral Order Resolution journey:

1. authenticate and authorize the actor;
2. triage a request into bounded business inputs;
3. retrieve applicable policy and evidence;
4. calculate a deterministic proposed resolution;
5. require an authorized human decision when policy demands it;
6. apply an approved or low-risk action idempotently;
7. recover safely after a crash or restart; and
8. evaluate the behavior with traceable deterministic, security, recovery,
   and agent-quality checks.

Each blueprint MUST remain independently deployable and MUST implement the
journey with its selected framework's native workflow, interrupt, continuation,
and checkpoint facilities. This proposal does not define a universal workflow
API, a custom cross-framework checkpointer, compatibility shims, Azure
resources, or customer-specific rules.

## Responsibility and state boundaries

| Concern | Authority | Proposed invariant |
| --- | --- | --- |
| Authentication | Application/API identity boundary | Derive the actor from a validated identity, never request text or model output. |
| Authorization | Application policy | Check case access, reviewer permissions, and action permissions server-side on every consequential request. |
| Triage assistance | Selected framework/model, within bounded output | Treat output as untrusted input and validate it before business use. |
| Policy retrieval | Application-owned policy source and retrieval adapters | Return versioned policy evidence with stable identifiers and applicability metadata. |
| Resolution decision | Deterministic application policy | The model may explain a result but MUST NOT choose or override the authoritative action or approval requirement. |
| Workflow continuation | Selected framework and host | Use the framework's native workflow/checkpoint provider and stable execution identity. |
| Business state | Application-owned persistence | Persist cases, proposed actions, decisions, action ledger entries, and audit projections independently of framework state. |
| Human decision | Authorized reviewer through the application boundary | Bind the decision to the exact pending action, actor, scope, version, and validity window. |
| Side effect | Application service or bounded tool | Execute only after authorization and any required approval, using an idempotency key. |
| Evaluation evidence | Project-owned test/evaluation pipeline | Record revision-specific results and artifacts; schema validity alone is not evidence of conformance. |

Conversation history, framework checkpoints, business records, approval
records, and audit projections MUST remain distinct even when they share a
physical database service.

### PostgreSQL boundary

PostgreSQL is proposed as **application-owned persistence** for business cases,
policy evidence references, approval decisions, action/idempotency records, and
audit projections. It is not the universal or custom checkpointer for every
framework.

A framework MAY use PostgreSQL when its native, supported checkpoint provider
selects PostgreSQL. That framework-owned checkpoint state MUST remain logically
separate from the application-owned schema and lifecycle. A managed host MAY
own the checkpoint provider instead. A blueprint MUST NOT replace either
framework-native or host-managed checkpoint semantics with a repository-wide
abstraction merely to make implementations look alike.

## Proposed business flow

```text
authorized intake
  -> triage
  -> policy retrieval
  -> deterministic resolution
  -> approval required?
       no  -> idempotent action -> completed
       yes -> native pause/checkpoint -> authorized approve or reject
                approve -> native resume -> idempotent action -> completed
                reject  -> no action -> escalated/rejected
```

The stable cross-framework contract is the meaning and ordering of the
business stages, not framework event classes, checkpoint bytes, graph nodes,
executor types, or hosting protocols.

## Proposed lifecycle

| State | Meaning | Permitted next states |
| --- | --- | --- |
| `received` | An authenticated actor submitted a bounded request. | `triaging`, `failed` |
| `triaging` | Inputs are being classified and validated. | `retrieving_policy`, `failed` |
| `retrieving_policy` | Applicable policy and evidence are being resolved. | `resolution_proposed`, `failed` |
| `resolution_proposed` | A deterministic action and approval requirement are recorded. | `awaiting_approval`, `applying`, `failed` |
| `awaiting_approval` | A native workflow pause exists and no gated action has run. | `approved`, `rejected`, `failed` |
| `approved` | One authorized approval is durably bound to the proposal. | `applying`, `failed` |
| `rejected` | One authorized rejection is durably bound to the proposal. | `escalated` |
| `applying` | The application is reconciling or executing the idempotent action. | `completed`, `failed` |
| `completed` | One verified action result is recorded. | none |
| `escalated` | No gated action ran; human handling is required. | none |
| `failed` | The workflow stopped with an explicit actionable error. | implementation-defined recovery path |

Transitions MUST be monotonic for one proposal version. Retrying a command MUST
return the existing outcome or continue recovery; it MUST NOT create a second
approval, rejection, or side effect.

## Stage requirements

### 1. Authorized intake

- Protected endpoints MUST authenticate callers and enforce record-level
  authorization.
- The server MUST assign the case, workflow, request, and idempotency
  identifiers. Client-supplied identity or workflow origin MUST NOT be
  authoritative.
- Input, retrieved content, model output, and tool output MUST be treated as
  untrusted and bounded by size, type, timeout, and allowed operation.
- Synthetic examples MUST contain no customer or tenant data.

### 2. Triage

- Triage MUST produce a validated business input containing, at minimum, a case
  reference, issue category, relevant order reference, confidence or validation
  status, and a traceable source.
- A model MAY summarize or classify the request. Invalid, missing, ambiguous,
  or out-of-scope output MUST fail explicitly or route to a defined human
  handling path; it MUST NOT silently become a default business fact.
- Deterministic parsing MAY be selected explicitly for synthetic tests. It MUST
  NOT silently replace a failed configured model call.

### 3. Policy retrieval

- Retrieval MUST return the policy version, applicability, evidence identifiers,
  and retrieval timestamp needed to reproduce the decision.
- Retrieval adapters MAY use local policy, search, MCP, RAG, or another bounded
  read-only source. Retrieved instructions MUST NOT change authorization,
  system policy, evaluation criteria, or the allowed tool set.
- Missing, conflicting, stale, or unauthorized policy evidence MUST fail
  explicitly or require human review according to application policy.
- Privacy-safe projections MAY expose evidence identifiers and status; raw
  sensitive policy or order data MUST remain behind the authorized boundary.

### 4. Deterministic resolution

- The application MUST calculate the proposed action and whether approval is
  required from validated business inputs and versioned policy.
- The calculation MUST be deterministic for the same normalized inputs and
  policy version.
- The recorded proposal MUST include its input digest, policy version, action,
  approval requirement, reason codes, and proposal version.
- Model output MAY provide a user-facing explanation but MUST NOT authorize,
  execute, or alter the deterministic result.
- Any material input or policy change MUST create a new proposal version and
  invalidate an unresolved decision for the prior version.

### 5. Human approval or rejection

- Before requesting a decision, the workflow MUST persist the exact proposed
  action in application state and create a recoverable native pause/checkpoint.
- The decision command MUST identify the pending proposal through an opaque,
  server-bound handle. Free-form words such as "approve" or "yes" MUST NOT be
  sufficient to resume a gated action.
- The application MUST reauthenticate and reauthorize the reviewer, including
  case access, reviewer role, decision scope, proposal version, and expiry.
- Approval and rejection MUST be mutually exclusive and atomically claimed.
  Duplicate, concurrent, expired, wrong-user, wrong-case, wrong-channel, and
  cross-tenant decisions MUST NOT resume the workflow.
- Approval permits the proposed action; it does not prove that the action
  succeeded. Rejection MUST produce no gated side effect and MUST end in a
  defined rejected or escalated outcome.
- Reviewer identity, decision, scope, reason/comment policy, and timestamps
  MUST be written to privacy-safe audit history.

### 6. Idempotent action

- Each side effect MUST use a server-generated key derived from the case,
  proposal version, action type, and intended target.
- The application MUST durably record claim, execution, and verified outcome.
- Blind retries of side effects are prohibited. A retry MUST reconcile the
  ledger and downstream operation using a supported idempotency or lookup
  contract.
- Only a current low-risk proposal or an approved current proposal may enter
  `applying`.
- Terminal success MUST require a verified action result, not a model statement
  or an emitted success-shaped event.

## Framework-native workflow and checkpoint requirement

A conforming framework blueprint MUST:

1. express triage, retrieval, resolution, pause, decision, and resume with the
   selected framework's native workflow or graph primitives;
2. use the native checkpoint provider selected for that framework and host;
3. preserve a stable execution/thread identity across pause, restart, and
   resume;
4. correlate native continuation state with application case, proposal,
   decision, and action-ledger identifiers;
5. fail visibly when required native checkpoint state is missing, corrupt, or
   incompatible; and
6. document checkpoint ownership, retention, concurrency, and migration for
   each supported host.

Examples of valid mappings include a MAF workflow with its selected host's
checkpoint provider or a LangGraph graph with a supported LangGraph
checkpointer. Their checkpoint schemas and resume commands are intentionally
different. A future implementation MUST test its mapping rather than adding a
compatibility layer that emulates another framework.

## Crash and restart recovery

Recovery MUST reconcile two authorities: framework-native continuation state
and application-owned business records. The implementation MUST not assume
that writes across them are one atomic transaction.

| Interruption window | Required recovery outcome |
| --- | --- |
| Before a native pause or proposal is durable | Retry from the last native state without creating a second proposal or action. |
| Native pause durable, decision absent | Restore `awaiting_approval`; do not execute the gated action. |
| Decision committed, native resume not acknowledged | Reauthorize the stored decision's continuing validity, resume once, and preserve the original decision audit. |
| Action claim recorded, downstream outcome unknown | Reconcile by idempotency key or supported downstream lookup before any retry. |
| Action committed, terminal projection absent | Rebuild the projection from the ledger/result without repeating the action. |
| Rejection committed, terminal projection absent | Rebuild the rejected/escalated projection without invoking the action. |
| Native checkpoint missing or corrupt | Fail visibly and require an operator-controlled recovery path; never synthesize success or approval. |

At startup and before a resume, a future implementation SHOULD run bounded
reconciliation for non-terminal cases. Recovery MUST be safe under concurrent
workers and repeated client requests. Tests MUST terminate real worker
processes at the decision and action commit boundaries instead of exercising
only in-process exception handling.

## Evaluation proposal

Each implementation MUST define versioned synthetic cases, expected outcomes,
and thresholds before accepting results. At minimum, evidence should cover:

| Evaluation area | Minimum proposed cases |
| --- | --- |
| Triage | supported categories, ambiguous input, malformed identifiers, prompt-injection content, and model failure without silent fallback |
| Policy retrieval | exact policy/evidence IDs, missing or stale policy, conflicting evidence, unauthorized retrieval, and bounded timeouts |
| Resolution | deterministic repeatability, boundary values, approval-rule coverage, policy-version changes, and prohibited model overrides |
| Human decision | approve, reject, duplicate, concurrent race, expiry, revoked access, wrong case/user/channel/tenant, and changed proposal |
| Idempotency | repeated start/resume/action commands, downstream timeout with reconciliation, and one verified side effect |
| Recovery | process termination before/after decision commit and before/after action commit, missing checkpoint, and projection rebuild |
| Authorization | unauthenticated access, insufficient role/scope, record isolation, and forged actor fields |
| Agent quality | grounded explanation, cited policy factors, no fabricated completion, privacy-safe output, and declared rubric/threshold |
| Observability | correlation across case/workflow/checkpoint/decision/action, redaction, actionable failure signals, and verified export where claimed |

Deterministic contract, security, and recovery checks MUST be evaluated
separately from probabilistic explanation quality. A model-quality score MUST
NOT compensate for a failed authorization, approval, idempotency, or recovery
check. Results must identify the source revision, framework and package
versions, host, checkpoint provider, dataset version, policy version, and
environment.

## Future conformance evidence

A future implementation may claim conformance only when revision-specific
evidence demonstrates:

- the complete lifecycle and negative transitions;
- framework-native checkpoint creation and resume on each supported host;
- PostgreSQL application records remain separate from framework checkpoint
  ownership;
- authenticated and authorized approvals and rejections;
- one idempotent verified action across repeated commands and crash windows;
- visible failure for missing or corrupt state;
- deterministic and agent evaluations with predeclared thresholds; and
- privacy-safe correlation without customer data or secrets in evidence.

The readiness contract may record these outcomes, but schema validation alone
cannot establish conformance, authorization, execution, or release readiness.

## Assumptions and limitations

- Concrete issue categories, thresholds, policy text, and actions are
  application-owned and intentionally unspecified.
- The referenced MAF implementation demonstrates useful public design patterns
  but is not cross-framework proof. Its PostgreSQL checkpoint adapter is an
  implementation choice, not a requirement for other frameworks or hosts.
- Framework and hosting compatibility, package versions, checkpoint semantics,
  identity integration, telemetry export, and deployment security remain to be
  verified per blueprint.
- This proposal adds no runtime code, schema, compatibility adapter, Azure
  resource, deployment asset, customer approval, or production-readiness claim.
