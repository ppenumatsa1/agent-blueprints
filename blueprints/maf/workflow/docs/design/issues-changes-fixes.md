# Engineering issues, changes, and fixes

## Evidence rule

This journal records engineering decisions and evidence that can be tied to a
source revision, test, or PR. A merged PR or passing local test is not a
deployment claim. Keep **implemented**, **verified**, **planned**, and
**unverified** separate. Add entries as work lands; do not rewrite earlier
entries to hide failed attempts or gaps.

## 2026-11-21 - Generated-project design baseline

- **Issue / cause:** Blueprint implementation and operator guides existed,
  but generated projects had no single set of product requirements, stack,
  implementation mapping, project structure, user journey, deployment flow,
  or cumulative journal.
- **Change / decision:** Add eight `docs/design` files, keep the six existing
  adopter/operator guides, link both sets from the generated README, and make
  the complete blueprint documentation part of the independent copy check.
- **Evidence:** `tests/test_instantiation.py` compares copied documentation
  bytes and checks relative Markdown links. After adding this design set to
  the working tree based on `57d404c`, both focused instantiation tests passed
  locally. This is not yet hosted verification for the updated PR revision.
- **Limit:** This is documentation and test coverage; it does not implement
  migrations, telemetry export, Foundry hosting, cloud deployment, or live
  identity verification.

## Prior implementation evidence

### 2026-11-21 - Local checkpoint timestamp ties

- **Observed issue:** During migration acceptance, an intermittent submission
  failed with `CheckpointError` while restoring the pending request. The
  original failing checkpoint files were not retained, so their exact cause is
  unverified.
- **Reproduction and cause:** Independently forcing the native MAF entry and
  pending checkpoints to have the same timestamp and listing the entry first
  deterministically reproduced the same error. The host selected checkpoints
  with `max(timestamp)`, which did not account for the framework's lineage
  when timestamps were equal. Equal timestamps could also select an earlier,
  non-terminal checkpoint after a decision.
- **Fix / decision:** Use the MAF file provider's lineage-aware latest
  selection for interrupted starts, and the active workflow instance's last
  persisted checkpoint after execution. Verify the pending request and reject
  a nonterminal checkpoint both on completion and replay. Keep the existing
  file-validation, case lock and transactional action ledger.
- **Evidence:** On the working tree for
  [PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11),
  four focused test methods failed against the earlier host, including two
  nonterminal replay subtests. With the fix, source and generated
  `python -m unittest -v tests.test_core tests.test_security tests.test_evidence_runner`
  passed 36 tests each using isolated PostgreSQL 17. The source root suite
  passed 46 with the synthetic adapter selected; the generated verification
  suite passed 44 without skips. The generated evidence producer recorded
  approval and recovery as passed and explanation and hint as unverified;
  the independent validator returned the expected exit 1 and `unverified`.
  Tests include failed terminal saves and both real worker-kill windows.
- **Next action:** Confirm CI for the pushed PR revision and reconcile
  dependent branches. Earlier migration evidence failures remain recorded;
  a later pass does not establish their original cause.
- **Lesson:** Wall-clock timestamps are not unique checkpoint identifiers.
  A successful later run alone does not explain an earlier intermittent
  failure, and a committed database effect must remain idempotent on retry.

### 2026-11-21 - Hosted caller binding and lost responses

- **Issue:** A hosted bridge needs to bind each request to the authorized API
  caller and safely reconcile a successful remote request whose response ID
  was lost. Neither guarantee has been established.
- **Investigation:** In `azure-ai-agentserver-responses==2.4.0`, resilient
  execution can serialize forwarded `x-client-*` headers even for foreground
  `store=true` requests when resilient or steering features are enabled.
  Offline middleware tests rejected unauthorized requests and stripped a
  header before SDK context creation for `store=false`; gateway retention
  for stored requests remains unknown. The
  [hosted-agent contract](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-contract)
  documents trusted but opaque platform identities and drops caller headers
  outside its allowlist. The
  [list responses API](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/list-responses)
  filters by agent or conversation, not operation metadata; its consistency
  and suitability for this recovery path remain unverified.
- **Decision / next action:** No hosted adapter was implemented. Establish
  supported caller binding and unambiguous recovery before implementing the
  bridge, and validate the actual service only with separate authorization.
  Do not persist bearer credentials or silently retry ambiguous side effects.

### 2026-11-21 - Intermittent synthetic evidence failures

- **Observed:** Two generated evidence runs at `f9b83ae` failed: the
  `unauthorized` case in the first and `approved` in the second each exited
  1 as a `CalledProcessError`. The recorder retained neither subprocess stdout
  nor stderr, so the exact original underlying exceptions cannot be recovered.
  Their approval and explanation checks were failed, not unverified or passed.
- **Investigation:** On a new isolated PostgreSQL 17 database, a bounded
  subprocess run reproduced exit 1 with empty stdout and `AssertionError:
  Submission returned HTTP 503` for `optional-hint`. A separate subprocess
  run instrumenting the HTTP handler then reproduced exit 1 for `pending`
  after 27 cases passed: `CheckpointError: The pending request could not be
  restored` from `LocalWorkflowHost.start`, translated to HTTP 503. Migration
  and startup had completed before the submit call. `host.py` and `workflow.py`
  are unchanged from foundation `61d44ed`; this observation alone does not
  establish why restoration mismatched or whether either original failure
  had that same cause.
- **Bounds and decision:** A separate instrumented in-process run completed
  108 cases, and 80 isolated subprocesses with checkpoint/request tracing
  completed without reproducing the mismatch. These do not erase the failures
  or establish a cause. No migration-related defect was identified and no
  checkpoint logic was changed. The evidence-run failure is an unresolved
  pre-PR blocker; capture checkpoint identity, request IDs and ordering on a
  further reproduction and fix the established cause without weakening
  restore checks. A successful rerun alone is not resolution.
- **Lesson:** Record privacy-safe subprocess failure diagnostics and preserve
  failed results; an HTTP 503 or later passing run cannot establish root cause.
- **Later foundation fix:** The independently reproduced equal-timestamp
  selection defect described above was fixed in foundation `9efeef0`, with
  deterministic regression tests. GitHub Actions
  [run 44936094798](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936094798)
  passed all five jobs on that exact foundation SHA. The original two failures'
  exact causes remain unproven; those failures are not reclassified.

### PostgreSQL 16 compatibility observation

- **Evidence:** On migration branch `031fdb4`, an independent local run on
  PostgreSQL 16.15 passed all 12 migration tests without skips, including
  adoption, later revision, drift and rollback. Its first auxiliary readiness
  probe failed before tests; a corrected probe was used for the successful
  run. This is local evidence only, not Azure, Entra, hosted identity or
  live restore verification.
- **Next:** Recheck the reconciled branch on PostgreSQL 16 and 17 and verify
  actual PR CI on its exact head before approval.
- **Reconciled source evidence:** On rebased code `9f1f802`, `python -B -m
  unittest discover -s tests -v` in `backend` passed 48 tests without skips
  against each of isolated PostgreSQL 16.15 and 17.12. This covers migration,
  security and recovery tests but does not replace generated-app or hosted CI.
- **Reconciled generated evidence:** At `7cd99ac`, the same backend command
  passed 48 tests without skips in both source and independently generated
  copies on each PostgreSQL version. Generated verifier tests passed 44;
  generator/copy checks passed two. The generated real evidence producer
  returned approval and recovery passed, explanation and hint unverified;
  the independent validator returned an unverified gate (exit 1) because
  the synthetic trust store is unsigned. This does not erase the earlier
  failed runs or verify Azure, hosted identities or live restoration.

### Migration review - versioned schema and least privilege

- **Issue:** Comparing every live database to the original baseline rejected
  later legitimate revisions, and creating a reference schema on every API
  startup required unnecessary database CREATE privilege.
- **Fix:** Reviewed manifests validate the current revision and migration
  head; an explicit owner job performs upgrades, while runtime startup
  validates without DDL. Unversioned drift and unknown revisions fail.
- **Pre-rebase evidence:** Source and generated backend suites passed 44
  tests each on isolated PostgreSQL 17, including a modularity test removed by
  the clean foundation. The 12 migration tests exercised a test-only second
  revision, fresh and existing upgrades, preserved business/decision/audit/ledger
  rows, rollback, concurrent startup and a role without database/schema CREATE
  privileges. Two generator tests passed. Local Compose migration, preparation,
  startup and generated image build passed using a locally selected package proxy.
- **Failed attempts and fixes:** The first Compose preparation failed because
  its executable module imported `os` too late. The import was corrected and
  a subprocess regression added before the successful rerun. The first rebased
  generated verifier run failed for missing `jsonschema`; after installing its
  declared requirements, the 44-test rerun passed without skips.
- **Rebased evidence:** On foundation `61d44ed`, source and generated backend
  suites passed 43 tests each and the generator passed two tests. Source and
  generated Compose smokes returned UI 200, health 204 and protected API 401
  after explicit migration and example preparation. Results are local and
  synthetic, not release approval.
- **Lesson and limits:** Test upgrades against a later head, not just
  baseline adoption. Coordinate backup and checkpoint recovery; no automatic
  downgrade, live restore or hosted identity is established. Catalog formatting
  on PostgreSQL versions other than 17 is unverified. Reconcile parallel
  dependencies and run actual credential-free PR CI against the integrated head.

### PR #6 - Native MAF workflow and local recovery core

- **Change:** Added a native MAF approval workflow, local checkpoint host,
  PostgreSQL business/decision/audit/action records, and worker-kill recovery
  tests. CI used isolated PostgreSQL and exposed no application endpoints in
  that increment.
- **Evidence:** The PR description records 13 passing core tests, including
  both worker-kill windows, and 43 source tests passed with the later
  application acceptance adapter intentionally skipped.
- **Reusable lesson:** Checkpoint state and PostgreSQL state are separate;
  test the crash windows explicitly. Database transaction idempotency does
  not guarantee idempotency for arbitrary external effects.
- **References:** [PR #6](https://github.com/ppenumatsa1/agent-blueprints/pull/6);
  `backend/app/workflows/host.py`, `backend/app/infrastructure/store.py`, and
  `backend/tests/test_core.py`.

### PR #8 - Authenticated local MAF application

- **Change:** Added Entra-protected FastAPI operations, case authorization,
  optional server-side OBO, React/MSAL, a synthetic application, and a
  loopback-only Compose stack.
- **Evidence:** The PR description records 26 backend tests and 8 frontend
  tests passing, build/CSP checks passing, and a local Compose smoke with UI
  200, health 204, protected API 401, non-root API, and private checkpoint
  permissions. It explicitly leaves live Entra/OBO and production controls
  unverified.
- **Reusable lesson:** A synthetic identity is a test fixture, not interactive
  authentication. Keep the public browser on the UI origin and do not expose
  database/API ports or service secrets.
- **Known warning:** The PR reported an approximately 505 kB minified UI chunk
  and an HTTPX test-client deprecation warning; no evidence here establishes
  that either was subsequently fixed.
- **References:** [PR #8](https://github.com/ppenumatsa1/agent-blueprints/pull/8);
  `backend/app/infrastructure/identity.py`, `backend/app/domain/policy.py`,
  `compose.yaml`, and `frontend/src/api.ts`.

### PR #10 - Independent blueprint instantiation and evidence

- **Change:** Added generation outside the source checkout and an independent
  verifier, exact contract copies, synthetic golden adapter, crash evidence,
  and generated-project CI.
- **Evidence:** The PR description records byte-identical contracts,
  isolated imports/build contexts, generated backend 31 tests, verifier 44,
  frontend 8, and Compose smoke. Approval/recovery observations passed while
  explanation/hint remained unverified and the unsigned readiness result
  remained unverified. GitHub Actions run 44917564338 passed five jobs.
- **Reusable lesson:** Generated copies need their own tests and runtime
  contexts; a fixture that formats its own explanation/hint is not agent
  evaluation or browser end-to-end evidence. Passing observations do not make
  unsigned data a release authorization.
- **References:** [PR #10](https://github.com/ppenumatsa1/agent-blueprints/pull/10);
  `scripts/instantiate_maf.py`, `tests/test_instantiation.py`, and
  `.github/workflows/ci.yml`.

### PR #11 - Modularity foundation

- **Change:** Split backend/frontend build contexts and organized backend
  responsibilities while retaining previous extension imports.
- **Evidence:** The PR description records source/generated backend 32 tests
  each, generated verifier 44, and frontend 8 with build/CSP passing. It
  records package-host TLS failure followed by a successful retry through
  approved package proxies. At the time of this entry, PR #11 is open and its
  hosted verification status must be refreshed before approval.
- **Decision / follow-up:** The greenfield quality gate rejects backward
  compatibility shims and forwarding modules. This revision removes them
  and updates internal imports; tests and CI must be rerun on its exact head.
- **References:** [PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11);
  `backend/app/`, `frontend/`, `backend/Dockerfile`, and
  `tests/test_instantiation.py`.

### PR #13 - Locked developer tooling proposal

- **Status and revision:** Open, based on `modularity-foundation`; head
  `e1d953662e615e547fa641ad0831907c363318e3`. It is a parallel workstream and
  is not included in this branch's baseline commit `57d404c`.
- **Proposed changes:** Python 3.12, uv 0.9.26, public-PyPI `uv.lock` and
  hash-pinned backend/image installs, Ruff 0.14.13, Node 22 with `npm ci`,
  and VS Code task/debug configurations.
- **Evidence:** Hosted run
  [44928260607](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44928260607)
  passed `contracts`, `maf-core`, `maf-frontend`, `maf-compose`, and
  `maf-independent` for that exact tooling head only. The workstream reports
  Windows and Linux Compose checks using an approved mirror after public TLS
  failures. Those results do not transfer to this branch or other revisions.
- **Unverified:** macOS Compose and interactive debugger operation.
- **References:** [PR #13](https://github.com/ppenumatsa1/agent-blueprints/pull/13);
  `uv.lock`, backend image install, and developer task/debug configuration
  are proposed in that PR, not present in the baseline documented here.

## Current acceptance queue

| Item | Status | Evidence needed / next action |
| --- | --- | --- |
| Eight design documents and generated inclusion | In progress | Run the focused instantiation tests and verify copied Markdown links. |
| Canonical imports and legacy-shim removal | Open in foundation workstream | Inspect final diff across imports, tests, Docker, CI, docs, and generator; do not approve while forwarding paths remain. |
| Locked developer tooling | Open in parallel PR #13 | Reconcile only after review/merge; verify any resulting revision and platform matrix independently. |
| Current dependent PR CI | Pending on updated revision | Confirm all required checks correspond to the pushed PR head. |
| Foundry host caller binding and lost-response recovery | Blocked | Establish supported identity and reconciliation guarantees before implementing a hosted bridge. |
| Live Entra/OBO, cloud telemetry, Azure deployment | Unverified | Separate scoped implementation, authorization where required, and live evidence. |

Future entries should use this form: date and scope; observed issue and
evidence-backed cause; attempted approaches (including failures); accepted
change or decision; focused tests and exact revision/CI evidence; remaining
limitations and reusable lesson. Do not invent historical root causes when the
available PR or test record does not establish one.
