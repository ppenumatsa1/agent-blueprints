# Order Resolution generation overlay

This explicit profile is copied over the independently owned MAF workflow
blueprint by `scripts/instantiate_maf.py --profile order-resolution`.
It is application source, not a registry, plugin system, specification
compiler, or shared runtime dependency.

The overlay adds deterministic Order Resolution validation and proposal rules,
database-owned action records, a native `WorkflowBuilder` workflow that
auto-completes low-risk proposals and pauses approval-required proposals, and a
profile-specific React renderer. It reuses the copied FastAPI, PostgreSQL,
Compose, authentication, authorization, checkpoint, and lock-file
infrastructure.

The canonical nine-case fixture is intentionally not duplicated here. The
generator copies `scenarios/order-resolution/acceptance-contract.json` and
`scenarios/order-resolution/golden-cases.json` from merged PR #42, together
with `tests/test_order_resolution_contract.py`. Explicit
`--order-resolution-contract`, `--order-resolution-cases`, and
`--order-resolution-test` paths remain available for isolated generator tests.

The generated integration tests exercise the real FastAPI boundary, native MAF
workflow/checkpoint host, and PostgreSQL state. The runtime adapter executes
canonical `ORS-001` through `ORS-009` from the generated verification assets
and derives separate business and technical results from API, checkpoint, and
database observations rather than fixture expectations.

The profile-root backend adds an explicit PostgreSQL migration, request and
proposal stores, atomic decision persistence, an effect ledger, authorization
audit records, and a synthetic downstream destination. Consequential effect
identity binds case, proposal version, action, and destination. Native MAF
continues to own workflow checkpoints.

Hosted generation adds a protected FastAPI service boundary at
`/api/internal/hosted/v1`. The hosted runtime authenticates with its managed
identity for the API audience and the fixed `Hosted.Workflow.Invoke` app role,
then uses case-bound start/resume, read/proposal, approval/decision,
effect-projection, and completion routes. Opaque hosted
caller/session/conversation values are bound to authoritative case principals,
and every mutation requires a durable case-bound idempotency key. The API UAMI
is the sole PostgreSQL runtime principal; the hosted runtime receives no
database URL, TLS setting, credential, or role. Foundry owns hosted
conversation/checkpoint state, so hosted case checkpoint columns remain null.

The profile-root evaluation layer consumes the copied canonical golden cases;
it does not duplicate them. It runs deterministic business and technical
comparisons through MAF's native `Evaluator`, `LocalEvaluator`, `@evaluator`,
and `evaluate_agent()` APIs, then passes native results to the merged #39
readiness mapper. The generated evidence runner executes all nine scenarios,
writes revision-bound local artifacts, and invokes the independent readiness
validator. Deterministic results may pass locally while model quality, browser
evidence, and trusted producer provenance remain unverified.

The generated `hosted-agent` package is a separate Foundry Responses entry
point. It hosts a fresh native MAF workflow per request, uses the public
Foundry hosting checkpoint provider, and never attaches the API's local
`FileCheckpointStorage`. The authenticated API/integration layer must supply
the documented caller and conversation binding adapter before the hosted
entry point starts. The application-owned PostgreSQL store supplies the narrow
`HostedBusinessStore` lifecycle: stable opaque hosted request correlation,
hosted decision claim, and business completion. Foundry still owns native
checkpoint state; the database does not store or fabricate hosted checkpoint
IDs. The copied
`scripts/foundry/publish_order_resolution_hosted.py` packages the generated
backend and hosted package for source-code deployment; it does not provision
resources or assign RBAC. Publishing requires an explicit Foundry project
endpoint and resource ID. Its journal identity binds that target, agent name,
archive, runtime, protocol, entry point, model deployment, and hosted
configuration; a different reuse fails before create. Responses journals must
atomically distinguish a newly acquired claim from an existing pending record,
which is never replayed after restart or concurrency.
