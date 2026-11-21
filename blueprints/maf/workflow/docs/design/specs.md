# Technical specifications

These specifications define the current local blueprint's observable
contracts. Each row points to source and a verification boundary; a green
test is evidence only for the behavior it exercises.

| ID | Requirement | Implementation | Verification and limit |
| --- | --- | --- | --- |
| SPEC-01 | Generated project is independent and refuses unsafe destinations. | The source repository's `scripts/instantiate_maf.py` copies the blueprint, license, contracts, verifier, and synthetic fixture. | The source repository's `tests/test_instantiation.py` verifies outside-repository generation, import isolation, byte-identical contracts/docs, and refusal of existing/repository destinations. |
| SPEC-02 | Protected API calls authenticate an Entra v2 bearer token and authorize each operation. | [`backend/app/infrastructure/identity.py`](../../backend/app/infrastructure/identity.py), [`backend/app/domain/policy.py`](../../backend/app/domain/policy.py), [`backend/app/api.py`](../../backend/app/api.py). | `backend/tests/test_security.py`; synthetic identities do not prove live Entra sign-in, role assignment, or OBO. |
| SPEC-03 | Requests and reviewer decisions are persisted before workflow continuation. | [`backend/app/usecases/service.py`](../../backend/app/usecases/service.py), [`backend/app/infrastructure/store.py`](../../backend/app/infrastructure/store.py), [`backend/app/infrastructure/schema.sql`](../../backend/app/infrastructure/schema.sql). | `backend/tests/test_core.py`; tests use isolated PostgreSQL, not a production database. |
| SPEC-04 | Workflow uses MAF-native request/response and host-owned local checkpoint provider. | [`backend/app/workflows/workflow.py`](../../backend/app/workflows/workflow.py), [`backend/app/workflows/host.py`](../../backend/app/workflows/host.py). | `backend/tests/test_core.py` checks request restoration, outcomes, and checkpoint failures. Foundry-managed checkpoint behavior is unverified. |
| SPEC-05 | Database effects and action ledger commit together; repeated application is safe for the same database transaction. | [`backend/app/infrastructure/store.py`](../../backend/app/infrastructure/store.py), `wf_action_ledger` in `schema.sql`. | Crash-after-action-commit test in `backend/tests/test_core.py`. External APIs require their own idempotency contract or outbox; no universal exactly-once promise. |
| SPEC-06 | Recovery reconciles separate file checkpoints and SQL records across tested crash windows. | `LocalWorkflowHost`, `PostgresStore.recoverable`, `resume`, and `finish`. | Worker-termination tests in `backend/tests/test_core.py`; these do not test multi-host failover or hosted recovery. |
| SPEC-07 | Browser uses MSAL scopes and does not receive service credentials. | [`frontend/src/authenticated-app.tsx`](../../frontend/src/authenticated-app.tsx), [`frontend/src/api.ts`](../../frontend/src/api.ts), [`frontend/src/config.ts`](../../frontend/src/config.ts). | `frontend/src/test/`; Compose CI checks public SPA configuration, health status, protected API 401, and container permissions. Interactive sign-in remains unverified. |
| SPEC-08 | Local Compose exposure is restricted to loopback UI; API/database are internal services. | [`compose.yaml`](../../compose.yaml), frontend `nginx.conf`, backend Dockerfile. | `maf-compose` CI smoke. It is not a production security or Azure deployment assessment. |
| SPEC-09 | Synthetic verification distinguishes passing observations from unverified evidence. | Generated `verification/`, `backend/tests/evidence_runner.py`, and `readiness/`. | `maf-independent` CI job checks expected approval/recovery observations and unverified explanation/hint outcomes. Its empty trust store cannot authorize release. |
| SPEC-10 | The eight design documents and local guides are copied into every generated project and remain navigable. | This `docs/` tree is copied by the source repository's `scripts/instantiate_maf.py`. | The source repository's `tests/test_instantiation.py` compares source and generated Markdown bytes and validates local links. |
| SPEC-11 | No PR is finalized with shims, obsolete paths, unused dependencies, or stale configuration. | The source repository's cross-cutting acceptance gate is in `docs/implementation-plan.md`. | Review source, tests, Dockerfiles, CI, docs, and generator together; add regression tests for changed behavior and inspect CI on the exact PR head. |

## Change-control rules

1. Keep one canonical implementation and use direct imports. Remove forwarding
   modules, aliases, and obsolete directories; backward compatibility with
   prior internal paths is not a requirement for this greenfield blueprint.
2. When a source boundary changes, update dependent tests, Docker build
   contexts, CI, documentation, and instantiation behavior in the same
   coherent change.
3. Map each significant acceptance claim to its source and a focused
   verification. Mark unavailable evidence **unverified**; do not lower or
   relabel a failed or security-critical check.
4. Update the PRD/specifications/architecture/structure/flow/deployment docs
   affected by each meaningful implementation change and append its decision,
   issue, fix, evidence, and reusable lesson to the journal.
5. Verify the generated copy and run applicable regression, security,
   durability, and independent verification checks. Confirm hosted CI belongs
   to the exact proposed PR revision before requesting approval.

The policy is not proof that every current implementation item is complete.
See the [cumulative journal](issues-changes-fixes.md) for known open work and
the [deployment flow](deployment-flow.md) for unverified hosting boundaries.
