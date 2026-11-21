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

## 2026-11-21 - Local tooling and observability integration

- **Decision:** Preserve both open PR histories and merge observability locally
  into the locked tooling/documentation baseline. Keep the public lock and
  hash-checked installs, canonical imports, all backend CI selectors, and both
  workstreams' prior evidence. The two telemetry pins and public lock additions
  match tooling workstream revision `8a5b3b3`.
- **Local evidence:** The combined tree passed offline lock validation, full
  Ruff checks, 50 source and 50 generated backend tests, 44 generated verifier
  tests, two generation tests, and nine frontend tests per copy with builds
  and CSP checks. Source and generated backend images built and imported
  telemetry with an approved mirror and hash-checked dependencies.
- **Evidence boundary:** Direct public Python downloads failed locally with
  TLS errors; the public-only lock contains no mirror URLs. Passing CI on the
  separate PR heads is not evidence for this combined revision. Hosted CI,
  public hosted configuration and cloud ingestion remain unverified.
- **Next:** Reconcile independently developed migration and infrastructure
  changes only after review; no PR is merged and no Azure resource is created.

## 2026-11-21 - Instrumentation failure isolation

- **Finding:** Span entry, annotation, context reads and closure could raise
  into application execution, and a pre-yield startup failure bypassed
  telemetry shutdown.
- **Decision:** Isolate SDK operations individually, emit fixed failure
  signals, never rerun the business action or replace its exception, and
  clean up initialized telemetry on construction or startup failure.
- **Evidence:** Focused injected-failure tests exercise synchronous and
  asynchronous actions, HTTP status and propagation, exporter/provider
  cleanup, and original exception identity. On implementation revision
  `fe4550a`, source and generated backend suites passed 50 tests each, the
  generated verifier passed 44, instantiation passed two, and changed Python
  files passed the tooling branch's Ruff checks. Exact PR CI remains pending.
- **Limit / lesson:** Public hosted configuration and cloud ingestion remain
  unverified. A fixed signal is diagnostic, not delivery evidence; failures
  can lose spans. Failure isolation must cover instrumentation
  setup and teardown as well as export, without catching business errors.

## 2026-11-21 - Privacy-safe observability

- **Issue:** Trace-only export omitted required metrics, and silently accepting
  missing Azure configuration obscured a nonfunctional hosted exporter.
- **Decision:** Add manual allowlisted spans, JSON logs, counter and histogram,
  explicit Azure trace and metric exporters, no metric exemplars, static
  non-identifying exporter resource fields, fail-fast configuration and fixed
  failure signals. Local mode has no exporter or collector.
- **Evidence:** `backend/tests/test_telemetry.py` exercises in-memory signals,
  redaction canaries, converted Azure envelopes and failure handling;
  `frontend/src/test/api.test.ts` exercises browser trace context. Earlier
  reconciled source and generated backend suites passed 45 tests each;
  generated independent verification passed 44, instantiation passed two,
  and both frontend suites passed nine with build and CSP checks. Earlier
  revisions passed 46 backend tests each. Check exact PR CI before approval.
- **Limits / lesson:** Export initialization is not ingestion evidence.
  Hosted trace/metric delivery, outgoing and Foundry propagation, and Azure
  operations remain unverified. A privacy review must cover exporter-generated
  metadata and failure logs as well as application attributes.
- **Coordination:** The independent tooling branch moves requirements into
  `pyproject.toml` and `uv.lock`; its reported pins are SDK `1.45.2` and Azure
  exporter `1.0.0b59`. Reconcile manifests and the public lock on integration.

## Prior implementation evidence

### 2026-11-21 - Reconcile developer tooling with canonical imports

- **Issue / cause:** The tooling branch and the foundation independently
  changed CI, generation tests, and setup guidance. The foundation removed
  forwarding modules and `tests.test_modularity`, while the tooling branch
  replaced requirements files with a locked environment.
- **Fix / decision:** Retain canonical imports, remove references to deleted
  tests and requirements files, copy the design docs in generated projects,
  and run evidence-normalization tests in both source and generated CI.
- **Evidence:** On the reconciled tree, source and generated backend suites
  each passed 31 tests, generated independent verification passed 44 without
  skips, and generated frontend tests/build/CSP passed using an approved npm
  mirror. Ruff passed in both backend copies. The root suite ran 46 tests
  with one unselected-adapter skip. Hosted
  [run 44931241591](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44931241591)
  passed all five jobs for head `ad6a78aa989189871ae521a05100ade36cbe7eb1`;
  confirm CI separately for any subsequent PR revision.
- **Lesson / limit:** Integrate environment instructions with the canonical
  source layout; a successful earlier CI run cannot establish the result of a
  rebased revision. Public-only local downloads, macOS, and interactive
  debugging remain unverified.

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
- **Next action:** Foundation
  [run 44936094798](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936094798)
  passed all five jobs for `9efeef01101b176a1a10627c654eff0ca5150b6b`.
  Reconcile dependent branches and verify the combined revision. Earlier
  migration evidence failures remain recorded; a later pass does not establish
  their original cause.
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

### 2026-11-21 - Reconcile developer tooling with canonical imports

- **Issue / cause:** The tooling branch and the foundation independently
  changed CI, generation tests, and setup guidance. The foundation removed
  forwarding modules and `tests.test_modularity`, while the tooling branch
  replaced requirements files with a locked environment.
- **Fix / decision:** Retain canonical imports, remove references to deleted
  tests and requirements files, copy the design docs in generated projects,
  and run evidence-normalization tests in both source and generated CI.
- **Evidence:** After rebasing onto checkpoint-fix foundation
  `9efeef0`, source and generated backend suites each passed 36 tests with
  isolated PostgreSQL, including timestamp ties, checkpoint selection,
  terminal replay, security and worker recovery. Generated independent
  verification passed 44 without skips; generated frontend passed 8 tests,
  build and CSP check. Ruff passed in source and generated backends. The root
  suite passed 46 with one intentional unselected-adapter skip. Generated
  npm installation used the approved mirror. Public package downloads still
  fail locally with TLS errors. Check hosted CI for the actual PR head before
  approval.
- **Hosted evidence:** Run
  [44937433206](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44937433206)
  passed all five jobs for code head `2a8fafdbcf5574d2a4e6cba59e8621bf1b3c0cd7`,
  including the checkpoint regressions and generated Compose build. Check the
  actual PR-head run after this documentation update before approval.
- **Lesson / limit:** Integrate environment instructions with the canonical
  source layout; a successful earlier CI run cannot establish the result of a
  rebased revision. Public-only local downloads, macOS, and interactive
  debugging remain unverified.

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

### 2026-11-21 - Reconcile documentation with checkpoint foundation

- **Change / decision:** Rebase the documentation work onto foundation
  `9efeef0`, preserving its checkpoint timestamp-tie and hosted caller-binding
  investigations, canonical imports, and the documentation and copy/link
  checks. The foundation also rejects incomplete terminal checkpoint state
  during completion and replay.
- **Evidence:** Foundation PR #11 run
  [44936094798](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936094798)
  passed all five checks for exact commit
  `9efeef01101b176a1a10627c654eff0ca5150b6b`. The two
  `tests.test_instantiation` tests pass locally after rebasing this branch.
  Documentation PR #12 run
  [44936739123](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936739123)
  passed all five checks for exact head `60458d9951bec3066dd92dc779714539007f7fd5`.
- **Limit:** This is documentation reconciliation and regression evidence; it
  does not verify Azure hosting, interactive debugging on macOS, live
  Entra/OBO, or hosted checkpoint recovery.

## 2026-11-21 - Reconcile dependent documentation with cleaned foundation

- **Change / decision:** Rebase the documentation work onto foundation
  `61d44ed`, retain its canonical imports and remove stale `test_modularity`
  command references. Preserve the six generated-project guides, their README
  navigation, the eight design documents, and copy/link verification.
- **Evidence:** Both focused `tests.test_instantiation` tests passed after
  rebasing onto `61d44ed`. Foundation PR #11 run
  [44930591252](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44930591252)
  passed all five checks on the exact foundation commit. Hosted checks for
  this dependent PR remain pending until its rebased head is published.
- **Limit:** This reconciliation does not verify Azure hosting, interactive
  debugging on macOS, live Entra/OBO, or hosted checkpoint recovery.

### PR #13 - Locked developer tooling proposal

- **Historical status and revision:** At this entry, the parallel PR was open,
  based on `modularity-foundation`, at head
  `e1d953662e615e547fa641ad0831907c363318e3`. Tooling is not included in
  cleaned foundation commit `9efeef0`.
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
  were proposed in that PR, not present in the foundation baseline.

## 2026-11-21 - Combine documentation and tooling for integration

- **Issue / cause:** Both dependent PRs updated the technology summary,
  journal acceptance queue, and master checklist independently.
- **Decision:** Preserve both changes in an isolated integration worktree;
  retain revision-specific evidence and avoid describing either open PR as
  merged. Keep the individual PRs unchanged.
- **Evidence:** On the combined working tree, both
  `python -m unittest tests.test_instantiation -v` tests passed, including
  documentation copy and relative-link checks.
- **Limit:** This focused result is not a full integration, security,
  durability, Compose, generated-runtime, or hosted-CI result.

## Current acceptance queue

| Item | Status | Evidence needed / next action |
| --- | --- | --- |
| Eight design documents and generated inclusion | Open in PR #12 | Focused instantiation tests and run 44936739123 passed on head `60458d9`; verify the combined revision separately. |
| Canonical imports and legacy-shim removal | Implemented in open PR #11 | Foundation run 44936094798 passed all five checks on `9efeef0`; preserve direct imports in later changes. |
| Locked developer tooling | Open in PR #13 | Run 44937692067 passed all five checks on head `543b137`; verify the combined revision separately. macOS, interactive debugging and public-only local downloads remain unverified. |
| Combined revision CI | Not run | Passing checks on individual PRs do not establish checks for their combined revision. |
| Foundry host caller binding and lost-response recovery | Blocked | Establish supported identity and reconciliation guarantees before implementing a hosted bridge. |
| Live Entra/OBO, cloud telemetry, Azure deployment | Unverified | Separate scoped implementation, authorization where required, and live evidence. |

Future entries should use this form: date and scope; observed issue and
evidence-backed cause; attempted approaches (including failures); accepted
change or decision; focused tests and exact revision/CI evidence; remaining
limitations and reusable lesson. Do not invent historical root causes when the
available PR or test record does not establish one.
