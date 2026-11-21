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

## 2026-11-21 - Staged Foundry-first infrastructure

- **Issue / decision:** The local blueprint lacked independently copied IaC
  and offline infrastructure checks. Add local Bicep modules and azd API/UI
  descriptors, but do not guess an unimplemented Foundry hosted-service
  contract or deploy resources. Keep the optional model, project-wide API
  agent-consumer grant, registry and Container Apps disabled by default.
- **Security boundary:** The graph configures private PostgreSQL with
  Entra-only auth; Foundry and monitoring public access are disabled. The
  optional API/UI are internal-only, while the optional authenticated registry
  remains publicly network-reachable. Application authentication and
  authorization remain required even if separately applied ACA platform auth
  fails. An agent-scoped grant alone would not exclude inherited roles; caller
  restrictions are unverified. No private Foundry/monitor endpoint or
  database token flow is present.
- **Attempt and evidence:** Bicep 0.37.4 lacked the selected Container Apps
  type schema and the strict static check failed on its diagnostics. After
  confirming the missing compiler capability, Bicep 0.49.2 was obtained and
  verified. Source and independent
  generated-copy compilation, lint, parameter examples and eight focused
  compiled-resource/configuration tests each passed without Azure credentials.
  The source repository suite passed 46 tests with the synthetic adapter
  selected. Foundry's required local dependency preflight passed. Actual
  PR-head CI is pending.
- **Test-environment interruption:** An extended backend test run failed to
  import `agent_framework` and `jwt` after its shared virtual environment
  disappeared during execution. A task-owned isolated environment was then
  created and dependencies restored. The subsequent isolated PostgreSQL run
  passed 31 source backend, 31 independently generated backend, and 44
  independently generated verification tests with the synthetic adapter
  selected. The initial failure is not treated as a pass.
- **Remaining gaps:** No hosted entrypoint, authenticated caller binding,
  checkpoint/response recovery contract, Foundry private path, telemetry
  private path, API database token acquisition, ACA proxy, or SPA cloud build
  is verified. Forwarded workload-token retention, stripping, replay and
  background recovery also require review. Static success is not a live
  deployment, authorization, cost, telemetry-delivery, or recovery claim.
- **Reusable lesson:** Compile a self-contained generated copy and preserve
  separate application authorization even when platform authentication is
  configured. Treat restrictive but unreachable services as blocked
  integrations, not as evidence of a working secure deployment.

## 2026-11-21 - PostgreSQL major-version alignment review

- **Issue:** The staged server selects PostgreSQL 16, but Compose and the
  parallel migration workstream's catalog tests use 17. Passing tests on 17
  do not prove clean migration, upgrade, catalog-drift or application behavior
  on 16. The migration workstream also reports separate unresolved local
  checkpoint-evidence failures on its `031fdb4` revision; this review does
  not resolve them.
- **Investigation:** The
  [Azure service](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-supported-versions)
  lists PostgreSQL 17, while the pinned
  [2024-08-01 resource schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/2024-08-01/flexibleservers#serverproperties)
  lists 11–16. The corresponding
  [REST reference](https://learn.microsoft.com/en-us/rest/api/postgresql/servers/create?view=rest-postgresql-2024-08-01)
  has the same enum but an example requesting 18. Bicep 0.49.2 emitted 17
  without diagnostics; it also accepted a deliberately invalid version
  string, so the compiler probe is not proof of API support. An Azure API
  contributor [described 17 in later preview APIs](https://github.com/Azure/azure-rest-api-specs/issues/36451#issuecomment-3308512467)
  in 2025, not a current guarantee for the pinned API.
- **Decision:** Retain 16 under the pinned API and disclose the mismatch.
  The stable 2025-08-01 API lists 17 and compiled in an isolated probe, but
  its other semantics and live deployment are not verified; it is a candidate
  for later review, not an implemented upgrade.
- **Verification / next action:** The compiler prerequisite initially failed
  because the required version was absent; the official 0.49.2 binary was
  obtained in task-owned storage and SHA-256 verified. For this revision,
  source and independently generated compilation, lint, parameter checks and
  nine infrastructure tests each passed, including a new regression check
  tying the disclosed majors to the compiled template and Compose. Both focused
  generated-documentation tests passed. A deliberately stale disclosure in
  the generated copy produced the expected assertion failure; the copy was
  restored and the focused test passed. Actual PR-head CI is pending; rerun
  checks after any rebase. Before deployment, choose and review a supported
  target, then run clean, upgrade and drift tests on that major version;
  separately authorize any live Azure test. Do not assume safe downgrade or
  cross-major data compatibility.
- **Reusable lesson:** An extensible API enum and permissive compiler can
  accept a value syntactically even when version-specific support remains
  ambiguous. Compare service, API-schema and migration-test evidence.

## 2026-11-21 - Local PostgreSQL 16 migration and foundation reconciliation

- **Separate migration evidence:** At migration workstream revision
  `031fdb440908092cf09801232fe7f5d15048f065`, an isolated local
  `postgres:16-alpine` server reported PostgreSQL 16.15. From that worktree's
  backend, `python -B -m unittest -v tests.test_migrations` passed 12 tests
  with no failures, errors or skips, covering fresh initialization, adoption,
  upgrades, drift, rollback and downgrade refusal.
- **Initial attempt:** An auxiliary `current_setting('lc_collate')` probe
  failed with `UndefinedObject` before tests ran. A retry used database
  catalog metadata and completed the suite; the failed attempt remains part
  of the evidence. The test container and its task-owned volume were removed.
- **Scope / next action:** That migration revision is separate from this
  infrastructure branch. Its local result neither resolves the separately
  reported checkpoint-evidence failures nor proves Azure Flexible Server,
  Entra database authentication, network access, deployment or cross-major
  data compatibility. After integration, rerun target-version migrations and
  drift checks on the exact combined revision; live checks require separate
  authorization.
- **Reconciliation:** The infrastructure branch was rebased onto foundation
  `9efeef01101b176a1a10627c654eff0ca5150b6b`. Its
  [GitHub Actions run 44936094798](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936094798)
  passed five jobs for that foundation head, not for the rebased branch.
  The checkpoint timestamp and hosted caller-binding entries below remain
  unchanged. Recheck the final infrastructure revision and its own PR CI.
- **Offline checks / prerequisite:** On the rebased working tree, source and
  independent generated-project Bicep compilation, lint and configuration
  checks passed, as did nine infrastructure security/configuration tests in
  each copy and two instantiation tests. The compiler prerequisite initially
  failed because no compatible Bicep executable was available; the official
  0.49.2 release was then obtained and its SHA-256 verified before rerunning.
  These checks used no Azure credentials or resources and do not replace
  exact-head PR CI.
- **Local recovery / security regression:** Source and generated
  `tests.test_core`, `tests.test_security` and `tests.test_evidence_runner`
  each passed 36 tests without skips on isolated local PostgreSQL 17.12 after
  the rebase. These exercise the local workflow, not hosted recovery or live
  identity.
- **Reusable lesson:** Local engine-version evidence is useful but remains
  scoped to the tested code and runtime; a passing retry does not erase the
  earlier failed probe or establish cloud compatibility.

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
| Eight design documents and generated inclusion | In progress | Run the focused instantiation tests and verify copied Markdown links. |
| Canonical imports and legacy-shim removal | Open in foundation workstream | Inspect final diff across imports, tests, Docker, CI, docs, and generator; do not approve while forwarding paths remain. |
| Locked developer tooling | Open in parallel PR #13 | Reconcile only after review/merge; verify any resulting revision and platform matrix independently. |
| Foundry-first infrastructure | In progress | Source and generated offline checks passed locally; confirm final-revision checks and actual PR-head CI, then coordinate live host, networking, identity and cost review. |
| PostgreSQL major-version alignment | Open | Separate migration revision `031fdb4` passed 12 local PostgreSQL 16.15 tests; the 16/17 mismatch, integrated revision, live API and Azure compatibility remain unverified. |
| Current dependent PR CI | Pending on updated revision | Confirm all required checks correspond to the pushed PR head. |
| Foundry host caller binding and lost-response recovery | Blocked | Establish supported identity and reconciliation guarantees before implementing a hosted bridge. |
| Live Entra/OBO, cloud telemetry, Azure deployment | Unverified | Separate scoped implementation, authorization where required, and live evidence. |

Future entries should use this form: date and scope; observed issue and
evidence-backed cause; attempted approaches (including failures); accepted
change or decision; focused tests and exact revision/CI evidence; remaining
limitations and reusable lesson. Do not invent historical root causes when the
available PR or test record does not establish one.
