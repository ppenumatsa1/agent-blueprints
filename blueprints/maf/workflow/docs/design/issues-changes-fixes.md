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
- **Investigation:** Earlier SDK inspection found that, in
  `azure-ai-agentserver-responses==2.4.0`, resilient execution can serialize
  forwarded `x-client-*` headers even for foreground `store=true` requests
  when resilient or steering features are enabled. Offline middleware tests
  rejected unauthorized requests and stripped a header before SDK context
  creation for `store=false`; gateway retention for stored requests remains
  unknown. The
  [hosted-agent contract](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-contract)
  documents trusted but opaque platform identities and drops caller headers
  outside its allowlist.
- **Documented pattern, not implemented:** The PR #15 workstream owner reports
  that current Microsoft Agent Framework guidance supports a native Python
  `Workflow` in the Responses host with
  `ResponsesServerOptions(resilient_background=True)` and Requests
  `store=true, background=true`. The host owns durable workflow checkpoints;
  do not pass a separate checkpoint store to the Workflow. For caller binding,
  the backend must first authenticate and authorize the user, then send the
  Foundry workload Authorization and `x-ms-user-identity` populated from the
  trusted user OID. Current azd protocol-adapter documentation explicitly
  declares protocol 2.0.0 in `azure.yaml`; the Foundry hosted-agent sample
  uses `host: azure.ai.agent` with version 2.0.0. The
  hosted container receives platform-injected `x-agent-user-id`; the backend
  sets the distinct `x-ms-user-identity` when calling Foundry, and
  `get_request_context().user_id` exposes the trusted identity. Use requires
  the Foundry Agent Consumer role and custom
  `UserIdentityImpersonation/action`. If the hosted workflow does not call a
  downstream API as the user, no end-user bearer/OBO token needs to be
  forwarded or persisted. The wire mechanism and protocol declaration are
  documented, but these are not evidence that this blueprint implements
  them.
- **Credential boundary:** The OID header conveys identity, not a credential.
  Never persist an end-user bearer/OBO token in business state, workflow
  checkpoints, or logs. The current local OBO option reads its secret from
  the backend environment; hosted secret delivery/rotation, workload identity
  configuration, and delegated-token lifecycle are not implemented. If a
  hosted workflow must call a downstream API as the user, design and verify
  token acquisition, renewal, and credential handling separately.
- **Remaining blocker:** `response.id` is required for polling. Creating a
  conversation first does not provide a documented idempotency key or
  unambiguous lookup for the case where response creation succeeds but its
  result is lost. The
  [list responses API](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/list-responses)
  documents filters for limit/order/after/before/agent/conversation, but not
  response metadata. The
  [list conversations API](https://learn.microsoft.com/rest/api/microsoft-foundry/aiproject#conversations)
  does not document a conversation-metadata query filter, and no
  Responses-create idempotency key is documented.   Thus, if no conversation
  or response ID was persisted before transport loss, metadata cannot yet
  provide an unambiguous lookup. Dedicated per-operation conversations and
  response metadata can be used as best-effort correlation: a matching
  response visible in a paged `GET /responses?conversation_id=...` can yield
  its ID. An empty list has no documented read-after-write/linearizable
  visibility or bounded consistency, so it cannot prove that create failed
  and is not safe grounds to retry. `POST /conversations` has the same
  lost-ack ambiguity; conversation listing has no metadata filter or
  visibility guarantee. Per-operation locks do not make a remote create
  atomic with the application database across crashes, and retention is
  setup-dependent. The reference
  project's `ResponsesWorkflowClient` creates a conversation before
  invoking, but does not persist/reconcile response IDs or bind user identity.
  Its package pins (`azure-ai-agentserver-responses==2.3.0`,
  `agent-framework-core==1.22.0`, `agent-framework-foundry==1.15.0`) are
  reference evidence only; they do not solve the blocker or establish
  compatibility with this blueprint. Local business idempotency protects
  database effects; it cannot recover hosted response identity. Keep recovery
  blocked until the provider offers a usable consistency/idempotency guarantee
  or the application has a separate durable, idempotent reconciliation
  contract.
- **Decision / next action:** No Responses adapter, hosted identity bridge,
  custom permission, private route, dependency compatibility, tests, or
  hosted checkpoint integration exists in the current blueprint. Verify
  package/API compatibility, workload networking, application lifecycle,
  caller role binding, and actual service behavior with separate
  authorization. Resolve response-ID recovery before safely retrying
  ambiguous requests. Do not persist end-user bearer credentials or silently
  repeat side effects.
- **References:** [Responses protocol hosting guidance](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent#responses-protocol);
  [hosted-agent contract](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-contract);
  [on-behalf-of flow](https://learn.microsoft.com/azure/foundry/agents/how-to/use-on-behalf-of-flow);
  [Responses and conversations REST operations](https://learn.microsoft.com/rest/api/microsoft-foundry/aiproject#responses).

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
  Hosted checks for this dependent PR must still be confirmed on its pushed
  final head.
- **Limit:** This is documentation reconciliation and regression evidence; it
  does not verify Azure hosting, interactive debugging on macOS, live
  Entra/OBO, or hosted checkpoint recovery.

### 2026-11-21 - Reconcile documentation with generated-verifier CI fix

- **Issue / cause:** The generated verifier test command was piped through
  `tee`, which could hide the command's nonzero exit status without `pipefail`.
  The resulting green job could not establish that the generated verifier
  passed.
- **Change / decision:** Rebase the documentation work onto foundation
  `d0e172751a39bc6e3a072d80482b3581b7007413`, preserving its workflow fix,
  the new `tests/test_ci_workflow.py` regression coverage, the checkpoint
  selection correction, and the hosted caller-binding blocker. Update the
  generated deployment guide, implementation plan, checklist, and architecture
  overview to state the exact behavior and revision-scoped evidence.
- **Evidence:** `tests/test_ci_workflow.py` exercises command failure, skipped
  tests, expected failures, and success against the actual workflow step.
  `python -m unittest tests.test_instantiation tests.test_ci_workflow -v`
  verifies generated documentation copying/local links and the pipeline
  regression. Foundation PR #11 run
  [44939172266](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44939172266)
  passed all five jobs for the exact foundation revision. This dependent PR's
  hosted CI must be checked on its final pushed head.
- **Limit:** CI validates the generated test step, not Azure hosting, live
  identity, or hosted checkpoint recovery.

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

- **Status and revision:** Open, based on `modularity-foundation`; head
  `b78634b3b746c7adbf5f8500e4b7023c96c67963`, as reported by its owner. It is
  a parallel workstream and is not included in cleaned foundation commit
  `d0e1727`.
- **Proposed changes:** Python 3.12, uv 0.9.26, public-PyPI `uv.lock` and
  hash-pinned backend/image installs, Ruff 0.14.13, Node 22 with `npm ci`,
  and VS Code task/debug configurations.
- **Evidence:** Hosted run
  [44928260607](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44928260607)
  passed `contracts`, `maf-core`, `maf-frontend`, `maf-compose`, and
  `maf-independent` for the earlier exact head
  `e1d953662e615e547fa641ad0831907c363318e3` only. The workstream reports
  Windows and Linux Compose checks using an approved mirror after public TLS
  failures. Those results do not transfer to its newer head, this branch, or
  other revisions. The current reported head retains uv/lock-based tooling
  but has no Foundry Responses hosting dependency; adding the prerelease
  hosting package requires separate MAF version/lock coordination.
- **Unverified:** macOS Compose and interactive debugger operation.
- **Additional local verification limit:** In a later owner-reported check,
  VS Code opened the tooling checkout in Restricted Mode. The owner did not
  bypass the trust decision, so actual breakpoints/debugging were not tested.
  That environment also lacked an installed `uv` executable; locked-tool
  execution was not verified there. These are environment limitations, not a
  claim that the proposed tooling failed its hosted checks.
- **References:** [PR #13](https://github.com/ppenumatsa1/agent-blueprints/pull/13);
  `uv.lock`, backend image install, and developer task/debug configuration
  are proposed in that PR, not present in the baseline documented here.

### PR #16 - Versioned database migration proposal

- **Status and revision:** The owner reports final commit
  `897aae853a4381177407ab8aaf5518c6f6149b4b`. It is not part of this
  documentation branch's local-only baseline.
- **Decision / behavior:** Adopt an existing database only after verifying
  the exact baseline schema manifest and confirming no later-revision-owned
  tables exist; only then stamp Alembic at `0001` and apply upgrades in the
  same transaction. A fresh database runs revision `0001`; validation does
  not stamp. This preserves application data while rejecting unrecognized
  schema histories.
- **Evidence:** The workstream owner reports source and generated test suites
  each passed 48 tests with no skips on PostgreSQL 16.15 and 17.12. Its root
  suite passed 47 tests with one expected adapter-not-selected skip.
  [Actions run 44944613749](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44944613749)
  passed five jobs for exact head `897aae8` when the PR used foundation base
  `d0e1727`.
- **Revision limitation:** That hosted run is stale relative to foundation
  PR #11's newer head
  `814491811eac457826108b70fc213fdc564af0e5`. The
  migration change must be reconciled and validated against its current base;
  this entry is owner-reported evidence, not proof for this branch or a
  production database.
- **Follow-up owner report:** The owner applied the `897aae8` delta locally
  and committed it as `ce86252324dca041fd5430602a3fc2c28a355274` atop PR #11
  ancestry `51a0666`. Twelve focused migration regressions passed on isolated
  PostgreSQL 17, and Ruff 0.14.13 lint/format checks passed. The README change
  was retained and shared design docs/journal were left unchanged. This is
  focused local evidence only; the commit is being held for remaining settled
  deltas, its exact foundation ancestry needs reconciliation, and no combined
  or hosted verification was reported.
- **References:** [PR #16](https://github.com/ppenumatsa1/agent-blueprints/pull/16);
  the verified baseline manifest, Alembic revision `0001`, and source/generated
  migration tests are in that workstream.

## 2026-11-21 - Deepen generated-project design documentation

- **Issue / cause:** The initial generated design baseline named requirements,
  components, and deployment boundaries, but needed more actionable identity,
  runtime, configuration, interaction, and failure-path detail to guide
  implementation and review. General documentation patterns alone would not
  establish that those paths exist in this blueprint.
- **Change / decision:** Refine the PRD, technology stack, technical
  specifications, architecture, project structure, user flow, and deployment
  flow with concrete local source/configuration references, API authority
  rules, startup and recovery order, error/retry behavior, and meaningful
  Mermaid diagrams. Follow the public reference project's separated
  documentation viewpoints and evidence traceability without copying its
  order-resolution behavior or business examples:
  [reference design docs](https://github.com/ppenumatsa1/maf-monorepo/tree/main/agents/order-resolution/foundry-public/docs/design).
  Update the source map for the canonical API composition, assembly, routes,
  schemas, dependencies, middleware/errors, and lifecycle modules. Clearly
  label Foundry hosting, cloud deployment, live identity, telemetry, and
  migration capabilities that remain unimplemented or unverified.
- **Evidence:** On the working tree descended from `58369ad`, the focused
  command `python -m unittest tests.test_instantiation tests.test_ci_workflow
  -v` passed all three tests. This verifies generated documentation byte-copy
  and local Markdown links, plus the workflow-step regression for failed,
  skipped, expected-failure, and successful verifier outcomes.
  `git diff --check` passed. This working-tree evidence is not hosted CI for
  the final PR revision; check that revision before approval.
- **Foundation reconciliation:** PR #11's latest reported head is
  `814491811eac457826108b70fc213fdc564af0e5`, parent
  `44ee18b886d409b0b59cf6df6b4893917370307d`. Its canonical layout separates
  `composition.py`, `api/app.py`, route handlers, schemas, dependencies,
  errors, middleware, and `lifecycle.py`; no `app.api` compatibility shim
  remains. The owner reports 37 backend tests passed with no skips. Before
  PR #12's source-map fix, Actions run
  [44944929394](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44944929394)
  had four jobs pass and `contracts` fail on the stale
  `../../backend/app/api.py` link. The root suite reported 47 tests, one
  failure from that link, and one expected adapter-not-selected skip. The
  PR #12 docs now map routes/auth to `api/routes/cases.py` and
  `api/dependencies.py`, wiring to `composition.py`, API assembly to
  `api/app.py`, and startup/recovery to `lifecycle.py`. Rebase onto this
  exact foundation and rerun root/contracts before relying on the correction.
  The coordinator reports that after a one-reference parent-branch correction,
  root `python -m unittest discover -s tests -v` passed 47/47 with the
  synthetic adapter selected. This verifies the root suite on the new base,
  not this dependent PR's post-rebase checks. The owner reports PR #11 run
  [44945419570](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44945419570)
  passed all five jobs, including generated checks without skips, on exact
  head `814491811eac457826108b70fc213fdc564af0e5`. PR #12 was rebased onto
  that exact tip. After rebase, the local working tree passed
  `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` in an isolated
  environment with root `requirements-dev.txt` installed (47 tests, one
  expected adapter-not-selected skip) and `git diff --check`. The
  instantiation tests verified generated documentation copying and local
  links, and the workflow regression passed. Hosted CI for the final dependent
  head remains pending.
- **Lesson:** Documentation structure may use a reference project's
  viewpoints, but implementation claims must be grounded in this repository
  and tied to evidence at the revision being reviewed.

## 2026-11-21 - Delegated session isolation and debugger evidence

- **Security clarification:** Microsoft's
  [per-user isolation guidance](https://learn.microsoft.com/azure/foundry/agents/how-to/isolate-sessions-per-user)
  warns that the platform does not fence one delegated end user from another
  within delegated access. If an application routes two users to the same
  session, they can see each other's data. The trusted application must
  authenticate each caller, maintain a server-side caller-to-session
  mapping, issue distinct session IDs, and reject unchecked client-supplied
  session IDs. `x-ms-user-identity` is an opaque identity-scoping value, not
  authorization. This hosted bridge and mapping are not implemented or tested.
- **PR #13 debugger report:** The workstream owner reports a headless
  generated-project debugpy/DAP smoke using `.vscode/launch.json`'s
  `Backend: FastAPI` configuration: execution stopped at `health.py:9`, the
  stack was inspected, and continuing returned HTTP 204 with exit code 0.
  Temporary resources were cleaned. This is owner-reported evidence; the
  report did not identify an immutable revision. It does not verify the
  interactive VS Code UI, Restricted Mode, or macOS.
- **Separate hosted CI evidence:** PR #13 is open at head
  `7325765cbbfb809e2064ec0e78a5567b465e3621`. Actions run
  [44947297321](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44947297321)
  completed successfully for that exact head with all five jobs passing.
  This verifies that PR's CI revision, not the debugger smoke or this
  documentation branch.
- **Next action / limit:** Keep the Foundry workstream blocked until the
  caller-to-session mapping, authorization boundary, and live behavior are
  implemented and tested. Keep debugger UI, Restricted Mode, and macOS
  checks explicitly unverified.

## 2026-11-21 - Hosted recovery and telemetry evidence updates

- **One-shot task negative evidence (PR #15 owner report):** In a disposable
  environment, the owner installed AgentServer Core 2.3.0 and Responses 2.4.0;
  Core 2.4.0 was unavailable. With the SDK's real local filesystem
  TaskManager, concurrent calls using the same task ID raised
  `TaskConflictError`. After terminal completion, that ID ran fresh for both
  same and different inputs, including after manager restart; a different
  session also ran fresh. The inspected one-shot `@task` is always ephemeral,
  is deleted at terminal completion, and rejects `ephemeral=False`; local
  storage partitions by agent/session/task. This is scoped to the tested
  local SDK/version and does not establish hosted behavior. Native one-shot
  task identity is not persistent completed-result deduplication.
- **Exact hosted source correction:** Inspection of the public
  `agent-framework-foundry-hosting==1.0.0b261112` wheel (SHA-256
  `9609ca758dd7f9e45542e2407b473acb7514ec6c0fd4dad3189068fd4ee2e55c`) found
  that `HostedResponseRequest.response_id` is exposed in `_request.py:150-164`;
  `_workflow_responses.py:425-434` resolves the request-aware factory before
  checkpoint preparation, parsing, and run claim. The parser is skipped on
  recovery, but the factory still runs. This corrects the earlier docs-only
  uncertainty about hook availability in that exact source version. It does
  not prove safe identity binding, a durable reservation per continuation,
  pending-reply/action ordering, idempotent side effects, same-response
  recovery, authorization, or hosted runtime behavior. A Postgres
  owner/digest-bound compare-and-set reservation remains only a candidate:
  the host's public docs do not establish that the hook can safely control
  every action and pending-reply consumption, and every continuation creates
  a new outer response requiring a separately linked reservation. Lost claim
  visibility, user/session mapping, duplicate side-effect/checkpoint windows,
  and expiry remain unproven.
- **Native telemetry failure (PR #14 owner report):** Opt-in native-global
  instrumentation on the pinned stack emitted duplicate FastAPI spans
  (`fastapi.dependencies`, `fastapi.endpoint`, `fastapi.serialization`, and
  `GET /secret`) alongside manual HTTP telemetry and leaked a synthetic
  query canary into exported span JSON. The owner is removing that opt-in or
  explicitly disabling auto-instrumentation until prompt/tool/identity and
  failure-path privacy are proven. The exact fix revision and regression
  results are pending; this is a concrete failure, not evidence that native
  MAF instrumentation is safe. It is separate from the local workflow's
  unverified telemetry plan.
- **Next actions / limits:** Keep hosted recovery blocked until the
  request-aware hook is exercised against an explicit authorization and
  durable-reconciliation design, including each continuation and external
  effect failure window. Keep telemetry safety unverified until the PR #14
  fix is tied to an exact revision and privacy regression evidence. Do not
  treat the local task probe, candidate reservation, or source-level hook
  finding as hosted acceptance.

## Current acceptance queue

| Item | Status | Evidence needed / next action |
| --- | --- | --- |
| Eight design documents and generated inclusion | In progress | After rebasing onto foundation `814491811eac457826108b70fc213fdc564af0e5`, the local root suite passed 47 tests with one expected adapter-not-selected skip; generated docs/link and pipeline regression tests passed; `git diff --check` passed. Confirm hosted CI on the pushed final PR head. |
| Canonical imports, API module boundaries and legacy-shim removal | Implemented in foundation head `8144918` | PR #11 run 44945419570 passed all five checks; root suite passed 47/47. Preserve direct imports and canonical route/composition/lifecycle boundaries. |
| Generated-verifier pipeline failure propagation | Implemented in foundation commit `d0e1727` | `tests/test_ci_workflow.py` covers failed, skipped, expected-failure, and successful outputs; PR #11 run 44945419570 passed all five checks at head `8144918`. |
| Versioned database migrations | Proposed in parallel PR #16 | Owner-reported tests passed on PostgreSQL 16/17; run 44944613749 is stale against foundation head `8144918`; reconcile and rerun. |
| Locked developer tooling | Open in parallel PR #13 at `7325765cbbfb809e2064ec0e78a5567b465e3621` | Actions run 44947297321 passed all five jobs on this exact head. Owner-reported headless debugpy/DAP smoke stopped at `health.py:9`, inspected the stack, then returned HTTP 204/exit 0; its report does not name a revision. Verify interactive VS Code UI, Restricted Mode, and macOS independently. |
| Current dependent PR CI | Pending on updated revision | Confirm all required checks correspond to the pushed PR head. |
| Foundry host identity, per-user session isolation, credential lifecycle and lost-response recovery | Blocked | The platform does not fence delegated users sharing a session: the trusted application must map authenticated callers to distinct sessions and reject unchecked client IDs; opaque `x-ms-user-identity` is not authorization. No bridge or mapping tests exist. Host-managed checkpoints have a documented pattern but no integration or live verification. Hosted credential delivery/rotation and downstream OBO lifecycle are unimplemented; never persist end-user bearer/OBO tokens. Visible response metadata is best-effort only; obtain bounded visibility/idempotency or a separate durable reconciliation contract before retrying ambiguous creates. |
| Live Entra/OBO, cloud telemetry, Azure deployment | Unverified | Separate scoped implementation, authorization where required, and live evidence. |

Future entries should use this form: date and scope; observed issue and
evidence-backed cause; attempted approaches (including failures); accepted
change or decision; focused tests and exact revision/CI evidence; remaining
limitations and reusable lesson. Do not invent historical root causes when the
available PR or test record does not establish one.
