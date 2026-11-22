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
`scenarios/order-resolution/golden-cases.json` from draft PR #42 when they are
available, together with `tests/test_order_resolution_contract.py`. It accepts
explicit `--order-resolution-contract`, `--order-resolution-cases`, and
`--order-resolution-test` paths for isolated tests.

Advanced crash-window durability, effects, and migrations are downstream
integration dependencies from draft PR #41. Evaluation and verification assets
are a downstream dependency from draft PR #43. The generator merges #41's
profile-root `backend/` tree and #43's profile-root `backend/` and
`verification/` trees after this overlay, so the stacked result is
deterministic without moving or duplicating reserved files.
