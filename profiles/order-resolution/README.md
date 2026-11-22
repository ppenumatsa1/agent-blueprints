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

The profile-root evaluation layer consumes the copied canonical golden cases;
it does not duplicate them. It runs deterministic business and technical
comparisons through MAF's native `Evaluator`, `LocalEvaluator`, `@evaluator`,
and `evaluate_agent()` APIs, then passes native results to the merged #39
readiness mapper. The generated evidence runner executes all nine scenarios,
writes revision-bound local artifacts, and invokes the independent readiness
validator. Deterministic results may pass locally while model quality, browser
evidence, and trusted producer provenance remain unverified.
