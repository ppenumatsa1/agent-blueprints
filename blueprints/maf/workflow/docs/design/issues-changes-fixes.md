# Engineering issues, changes, and fixes

## Evidence rule

This journal records engineering decisions and evidence that can be tied to a
source revision, test, or PR. A merged PR or passing local test is not a
deployment claim. Keep **implemented**, **verified**, **planned**, and
**unverified** separate. Add entries as work lands; do not rewrite earlier
entries to hide failed attempts or gaps.

## 2026-11-22 - Issue and fix status

This is a point-in-time review summary, not a claim that the open PRs have
merged into `main`. The local blueprint and generated copy provide synthetic
evidence; they do not establish authorized readiness or a cloud deployment.
All issues in the table remain open. Check the linked PRs and issues for
subsequent updates and rerun checks after any head or base changes.

### Completed engineering work and evidence

- The local MAF blueprint separates native file checkpoints from PostgreSQL
  business state and decisions. FastAPI, React, Compose, independent project
  generation and the copied readiness validator have local synthetic tests,
  including approval, rejection, restart and two worker-kill recovery windows.
  Order adjustment is a test fixture, not a customer application.
- [PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11) is the
  open modularity foundation; its exact-head
  [run 44954168348](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44954168348)
  passed five jobs. The open integrated work in
  [PR #17](https://github.com/ppenumatsa1/agent-blueprints/pull/17) combines
  reviewed portions of the tooling, telemetry, infrastructure, migration
  and design workstreams; its exact-head
  [run 44964201508](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44964201508)
  passed six jobs. This is not a complete semantic audit of every workstream
  difference; PRs #12-#16 remain open for review.
- The PostgreSQL socket-ready/TCP-not-ready race is addressed in #17 by TCP
  probes in CI and Compose, with regression tests ([#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38)).
  Earlier fixes also preserve verifier pipeline failures and select native
  checkpoints by lineage rather than relying on timestamp ties.
- Draft [PR #36](https://github.com/ppenumatsa1/agent-blueprints/pull/36)
  demonstrates an opt-in synthetic external-effect boundary; its
  [run 44967323320](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44967323320)
  passed six jobs. It does not prove a real downstream service's guarantees.
  Draft [PR #37](https://github.com/ppenumatsa1/agent-blueprints/pull/37)
  adds application-owned typed MAF extensions; its
  [run 44964330392](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44964330392)
  passed six jobs. Arbitrary Python callbacks are not sandboxed.
  Draft [PR #39](https://github.com/ppenumatsa1/agent-blueprints/pull/39),
  stacked on #37, adds synthetic evaluation contracts and rejects unknown
  configured checks and oversized thresholds, while oversized scores fail
  closed; its
  [run 44966632801](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44966632801)
  passed six jobs. These are separate PR runs, not combined-tree CI.
- An uncommitted #36 + #39 candidate tree `20ba59d01fff7429550c5034d2d6ec055f5d640f`
  passed 110 source and 110 generated backend tests and 44 generated
  verification tests on local PostgreSQL 16.15. Its generated Compose stack
  also passed local health, unauthenticated API, CSP and checkpoint-permission
  smoke checks. These are local results for a tree, not a commit, merged PR,
  fresh-install proof, managed database validation or combined GitHub CI.
  See [#24 evidence](https://github.com/ppenumatsa1/agent-blueprints/issues/24#issuecomment-7071728692)
  and [#35 evidence](https://github.com/ppenumatsa1/agent-blueprints/issues/35#issuecomment-7071755307).

### Open issues, fixes and next actions

| Issue | Status, fix or decision | Remaining action |
| --- | --- | --- |
| [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18) | Staged Foundry-first infrastructure and offline checks exist in #17; they are not an end-to-end deployment. | Complete and verify identity, network, service and browser connectivity. |
| [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19) | Foundry Responses adapter and managed checkpoints are explicitly deferred to P1-12. | Implement and verify the host-owned storage boundary after caller binding is established. |
| [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20) | Local crash recovery is tested; hosted lost-response and continuation semantics remain unknown. | Verify hosted reconciliation, recovery and side-effect ordering; do not blindly retry ambiguous effects. |
| [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21) | The independent validator retains failed and unverified outcomes, but synthetic data is not authorized evidence. A read-only check on 2026-11-22 found `main` unprotected with no effective rules. | Independently administer and verify contract approval, evidence provenance, trust, branch protection and bypass controls. |
| [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22) | Hosted identity guidance was corrected: opaque application scoping and platform identity headers are not verified authorization or a principal mapping. | Establish authenticated caller-to-session binding and enforce ownership; do not persist bearer credentials. |
| [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23) | Locked tooling and mirror-based restores are represented in #17; public-registry TLS failures and a canceled editor trust prompt were recorded. | Verify clean supported-platform installation, macOS and interactive debugging without bypassing user trust decisions. |
| [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24) | Versioned migrations and local PostgreSQL 16/17 tests exist; local candidate evidence is linked above. | Test the final integrated revision and managed service, least-privilege principals, backup and restore. |
| [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25) | Draft #39 adds application-owned evaluation mapping and failure handling, not actual model or browser evidence. | Run provider-backed and browser-hint evaluations and retain independently trusted evidence. |
| [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26) | Manual privacy-conscious telemetry is in #17; native global auto-instrumentation remains disabled after a query-canary leak and duplicate spans. | Verify redaction, propagation and ingestion in the actual hosted environment. |
| [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27) | Synthetic API security and UI checks exist. | Verify live Entra/OBO, interactive browser flows and accessibility. |
| [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28) | No Azure resources were provisioned; staged infrastructure is not a deployment. | Complete prerequisites and obtain approval of the concrete inventory, cost and deployment plan before provisioning. |
| [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29) | A partial synthetic generated-project run recorded approval/recovery observations and an unverified independent report; it excluded a clean install, UI and real evaluation. | Measure a representative complete run on a named revision; do not claim the setup objective from the partial timing. |
| [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30) | Temporary generated projects demonstrate isolation; no permanent application repository was created. | Obtain separate authorization before creating a permanent reference repository. |
| [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31) | ACA workflow hosting is a deferred alternative, not a verified fallback. | Assess it only after separate authorization. |
| [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32) | Draft #36 tests a synthetic downstream; an outbox alone cannot deduplicate an effect after a lost acknowledgment. | Block consequential effects until effect-specific authorization, downstream idempotency and authoritative reconciliation are independently verified; otherwise fail closed and use manual resolution. |
| [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33) | Specification Studio implementation and an actual producer are outside this phase. | Validate interoperability when that separate work is authorized and available. |
| [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34) | Other framework blueprints and a separate App/API repository are deferred. | Scope and authorize those later efforts separately. |
| [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35) | Draft #37 supplies native MAF extension patterns and generated synthetic tests; arbitrary trusted callbacks can bypass conventions. | Review integrations and verify security, approval and recovery boundaries; absolute non-bypass remains unproven. |
| [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38) | #17 contains the TCP-readiness correction and regression tests; its CI passed at the cited head. | Review and integrate the fix, then rerun checks against the actual resulting revision. |

### Review sequence

1. Review #11 separately; merge only after explicit approval.
2. Audit the feature-only incorporation of #12-#16 into #17, retarget #17
   after #11 is merged, and rerun checks on its actual base and head. Keep
   #12-#16 open until incorporation and their closure are separately approved.
3. Review #36, #37 and #39 separately. Their overlapping CI and documentation
   require reconciliation and fresh checks on the actual resulting tree;
   green sibling PRs and the uncommitted candidate do not establish combined CI.
4. Keep hosted identity/recovery, independent trust, real evaluation and
   consequential external effects blocked or unverified until their stated
   evidence exists. No merge or Azure provisioning is authorized by this journal.

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

### 2026-11-21 - Generated verifier pipeline exit status

- **Issue / reproduction:** GitHub Actions used `bash -e` for the generated
  verifier step. A failing `python -m unittest` piped through `tee` returned
  the successful `tee` status; a focused reproduction returned zero after a
  simulated verifier exit of 37. The separate skip check did not detect it.
- **Fix / decision:** Enable Bash `pipefail` in that step. A regression test
  executes the actual workflow step with a simulated failing verifier,
  skipped and expected-failure outputs, and a clean success.
- **Evidence / limit:** The test failed against the earlier workflow and
  passed after the fix. CI logs for prior heads of PRs #11 through #16 each
  explicitly recorded 44 passing verifier tests, rather than relying solely
  on the CI job status.
  Verify the revised foundation and dependent PRs on their actual heads;
  earlier green job status alone cannot prove verifier success.
- **Lesson:** Preserving evidence output with `tee` must not mask the
  producer's nonzero exit status.

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
| Design documentation and generated inclusion | Local evidence exists | Review the updated journal and verify copied documentation and links at the resulting revision. |
| Foundation and workstream integration | Open in #11 and #17 | Review diffs and feature-only retention; rerun CI whenever head or base changes. |
| Locked developer tooling | In #17 and open PR #13 | Review reconciliation and verify the final revision and platform matrix independently. |
| Dependent PR CI | Separate exact-head runs passed | Reconcile #36/#37/#39 and verify the actual combined tree and CI before integration. |
| Foundry host caller binding and lost-response recovery | Blocked | Establish supported identity and reconciliation guarantees before implementing a hosted bridge. |
| Live Entra/OBO, cloud telemetry, Azure deployment | Unverified | Separate scoped implementation, authorization where required, and live evidence. |

Future entries should use this form: date and scope; observed issue and
evidence-backed cause; attempted approaches (including failures); accepted
change or decision; focused tests and exact revision/CI evidence; remaining
limitations and reusable lesson. Do not invent historical root causes when the
available PR or test record does not establish one.
