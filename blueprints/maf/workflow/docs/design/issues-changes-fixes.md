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

## 2026-11-21 - Combined engineering-layer integration

- **Decision:** Integrate the independently reviewed tooling, documentation,
  observability, migration, infrastructure, and foundation changes in an
  isolated worktree without merging their PRs. Retain the verifier pipeline
  failure fix, the native checkpoint and hosted caller-binding investigations,
  exact copied contracts, and each workstream's evidence and limitations.
  The tooling reconciliation additionally makes the pipeline regression
  assert the generated backend's `uv run --locked --project` selector.
- **Local evidence:** At combined code revision `af3955a85036d3a6a01465648437a184a790309c`,
  source and independently generated backends each passed 68 tests without
  skips against both PostgreSQL 16.15 and 17.12, including authorization,
  telemetry, migration, approval, rejection, and both worker-kill recovery
  windows. The selected-adapter root suite passed 47 tests, and generated
  independent verification passed 44 without skips. Both copies passed Ruff,
  nine frontend tests, build and CSP checks, and offline Bicep/configuration
  validation plus nine infrastructure tests. Source and generated Compose
  ran explicit migrations and synthetic preparation, then returned UI 200,
  health 204 and protected API 401. The generated Compose contexts stayed in
  the copy, with no bind mounts; its API ran non-root with private checkpoints.
  Focused instantiation and pipeline tests also passed after adding generated
  infrastructure-document link coverage and the locked selector assertion.
- **Readiness evidence:** The generated producer observed synthetic approval
  and recovery passing, while explanation and browser hint remained unverified.
  The independent unsigned validator returned exit 1 and `unverified`; none
  of these observations is human release approval or trusted attestation.
- **Failed attempts retained:** An offline generated `uv sync` failed because
  the locked Ruff artifact was not cached. A hash-checked lock export was
  installed through an approved temporary mirror; a subsequent offline locked
  sync passed, and no mirror URL was committed. PR #13's reconciled local
  public-only Compose build separately failed on a TLS download; its hosted
  Compose check passed. The first combined generated Compose smoke reached
  healthy services but our PowerShell asset check falsely reported a missing
  script because it applied `-notmatch` to a multiline array. The built image
  contained the script; a corrected string-based check and full retry passed.
- **PR evidence:** Against foundation `d0e1727`, current open heads and
  successful PR runs are #12 `58369ad` / 44939850338, #13 `b78634b` /
  44940616666, #14 `cb4ff78` / 44940364995, #15 `2023e16` / 44939817209,
  and #16 `eb898f6` / 44940559106. These individual runs are not combined
  CI evidence.
- **Next / limits:** Confirm CI for the final combined revision and review
  the open PRs. Local results do not prove Azure PostgreSQL compatibility,
  live identity, telemetry ingestion, Foundry caller binding or hosted
  checkpoint recovery. Earlier intermittent evidence failures remain of
  unproven cause; macOS, interactive debugging, and public-only local package
  downloads remain unverified. No Azure resource or permanent application
  repository was created.

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
  changes; no PR is merged and no Azure resource is created.

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

## 2026-11-21 - Observability reconciliation and logger fallback

- **Reconciliation:** Rebased observability onto checkpoint foundation
  `9efeef01101b176a1a10627c654eff0ca5150b6b`. Retained native checkpoint
  selection, pending restoration/validation, terminal checkpoint validation,
  timestamp-tie recovery, and completed replay rejection; instrumentation
  remains outside those decisions.
- **Change:** The testing guide now lists telemetry in the source backend
  command and describes the generated evidence-runner suite separately. If
  operational logging fails, emit only a fixed failure event to stderr; a
  stderr write error cannot replace workflow output or an original exception.
- **Evidence:** Source backend 51 tests, generated backend 56 tests (including
  evidence-runner), generated verifier 44 tests, and two instantiation tests
  passed in an isolated local test environment. Focused telemetry coverage
  checks logger failure, exact payload-free fallback bytes, preserved business
  results/original exceptions, and stderr failure. Actual-head CI is required
  after publishing this reconciliation. [Run 44938368000](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44938368000)
  subsequently passed all five jobs for head `8c643df`, not the combined tree.
- **Limit:** This does not verify Azure configuration, cloud ingestion, or
  hosted trace/metric propagation.

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
  trusted user OID. **Superseded/unverified:** this historical OID and identity
  equivalence claim is not safe current guidance. The later
  [delegated-isolation clarification](#2026-11-21---delegated-session-isolation-and-debugger-evidence)
  treats `x-ms-user-identity` as an opaque app-supplied scoping value and
  `x-agent-user-id` as a different platform-generated header; neither binding
  to the validated principal nor equivalence of their values is established.
  A trusted app must authorize
  each principal's session, map callers to distinct sessions, and reject
  unchecked session IDs. Neither header is authorization, and bearer/OBO tokens
  must not be persisted. The bridge and mapping remain unimplemented and
  unverified. Current azd protocol-adapter documentation explicitly
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

### 2026-11-21 - Reconcile developer tooling with checkpoint foundation

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

- **Historical status and revision:** The earlier hosted run was on head
  `e1d953662e615e547fa641ad0831907c363318e3`; at that point the tooling
  remained a parallel PR, not part of the cleaned foundation.
- **Reported and integrated revisions:** The owner later reported PR head
  `b78634b3b746c7adbf5f8500e4b7023c96c67963`; the #17 integration branch
  records tooling at `543b137a432ca054920d629b943fc42a729df676`. These are
  separate snapshots; evidence for one must not be attributed to the other.
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
- **Integrated revision evidence:** The #17 branch reports run
  [44937692067](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44937692067)
  passed five checks on tooling head `543b137a432ca054920d629b943fc42a729df676`.
  This is not a check of the combined PR #17 revision or evidence for the
  Restricted Mode debugger/uv environment gaps.
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

## 2026-11-21 - Reconcile API boundaries with integration telemetry

- **Issue:** PR #11's API split deleted the monolithic API module, which the
  integration branch had independently extended with privacy-safe telemetry.
- **Decision:** Apply the `44ee18b` refactor and the `8144918` source-map
  correction without replaying earlier workstream history. Move telemetry
  construction, request spans, recovery signals, and shutdown to the new
  composition, middleware, and lifecycle boundaries; preserve direct imports.
- **Evidence:** On the reconciled working tree, 64 core, security, telemetry,
  and migration tests passed against an isolated PostgreSQL 17 container using
  the previously built integration runtime image and cached test dependencies.
  Ruff 0.14.13 lint and format checks passed. This is focused local evidence,
  not a locked-install or final combined CI result.
- **Limit / next action:** Reconcile the remaining workstream deltas and rerun
  source/generated and exact-head CI. Live hosted caller binding and
  lost-response recovery remain unverified. Local locked dependency restoration
  failed offline on an uncached Windows wheel and online on a public TLS error.

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
  PostgreSQL 17, and Ruff 0.14.13 lint/format checks passed. The README delta
  was retained and shared design docs/journal were unchanged in that commit.
  This is focused local evidence only; its ancestry needs reconciliation and
  no final combined or hosted verification was reported.
- **Conflict resolution and newer evidence:** The owner reports merge commit
  `d1251352835c2d02e91690104b4dcabf465f5f05` with parents PR #16 `897aae8`
  and foundation `8144918`. Its `specs.md` retains canonical SPEC-02 API
  links, points SPEC-03/SPEC-05 to `backend/migrations/baseline.sql`, and
  preserves migration SPEC-12 and its diagram. Generated instantiation/link
  validation passed; the root suite passed 47 tests with one expected
  adapter-not-selected skip; Actions run
  [44947337144](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44947337144)
  passed all five jobs on that exact PR #16 revision. This evidence does not
  verify the distinct combined PR #17 revision.
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
  that exact tip. Its isolated root suite passed 47 tests with one expected
  adapter-not-selected skip; generated-copy/link and verifier-pipeline tests
  passed, as did `git diff --check`. Actual-head run
  [44946550709](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44946550709)
  passed all five jobs on exact head
  `c247bf737acabe47e7af0023eaebf69c0b393fdf`. These results do not replace
  final combined PR #17 verification.
- **Integrated-doc conflict and resolution:** Applying the richer PR #12
  documents to the #17 integration branch conflicted in ten shared documents.
  Taking foundation files wholesale would have lost migration SPEC-12 and its
  diagram, observability SPEC-13, staged infrastructure and prior failure
  evidence; the PR16 branch also identified stale `schema.sql` references
  after migration integration. The docs-owner resolution preserves SPEC-02's
  canonical API paths, points SPEC-03/SPEC-05 to
  `backend/migrations/baseline.sql`, reserves SPEC-12 for migrations and
  SPEC-13 for observability, and renumbers colliding API/lifecycle contracts.
  It retains the migration diagram, infrastructure limitations, previous
  failures/evidence, and the richer Mermaid/runtime documentation. Generated
  copy/link and combined tests must pass before this integration is complete.
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
  session IDs. Platform-generated global `x-agent-user-id` and app-supplied
  opaque `x-ms-user-identity` are different headers; do not assume their raw
  values match. The bridge must verify an explicit mapping
  from the validated application principal. `x-ms-user-identity` is an
  identity-scoping assertion, not authorization. This hosted bridge and
  mapping are not implemented or tested.
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
- **PR #15 task-ID research, negative evidence:** The owner reports testing
  the real local filesystem TaskManager with AgentServer Core 2.3.0 and
  Responses 2.4.0; Core 2.4.0 was unavailable. Concurrent calls with the same
  task ID raised `TaskConflictError`, but after terminal completion the same
  one-shot ID ran fresh for both same and different inputs, including after a
  manager restart; a different session also ran fresh. The source documents
  one-shot `@task` as ephemeral/deleted at terminal completion, rejects
  `ephemeral=False`, and partitions local storage by agent/session/task. This
  local evidence means one-shot task identity alone is not persistent
  completed-result deduplication. It does not establish hosted behavior.
- **Separate reconciliation candidate:** The owner is assessing a
  Postgres compare-and-set claim bound to an owner and request digest as a
  possible way to recover the winning outer response ID. Public MAF host docs
  do not define its recovery contract. Inspection of the exact public
  wheel `agent-framework-foundry-hosting==1.0.0b261112`
  (SHA-256 `9609ca758dd7f9e45542e2407b473acb7514ec6c0fd4dad3189068fd4ee2e55c`)
  found `HostedResponseRequest.response_id` exposed in `_request.py:150-164`,
  and `_workflow_responses.py:425-434` resolves the request-aware factory
  before checkpoint preparation, parsing, and run claim. The parser is skipped
  on recovery while the factory still runs. This establishes source-level
  hook availability for that exact version, not a safe reservation contract.
  Each continuation produces a new outer response requiring a separately
  linked reservation; whether the hook supports a claim before every action
  and pending-reply consumption remains unverified. Lost claim visibility,
  user/session mapping, same-response recovery, duplicate side effects and
  checkpoint windows, and expired state remain unproven. Treat Postgres CAS
  as a candidate, not a fix; no implementation or hosted recovery claim
  follows.
  The user explicitly deferred hosted recovery to a separate scoped follow-up;
  this is not a security waiver, and caller binding and the host bridge remain
  unimplemented blockers.
- **Next action / limit:** Keep the Foundry workstream blocked until the
  caller-to-session mapping, authorization boundary, and live behavior are
  implemented and tested. Keep debugger UI, Restricted Mode, and macOS
  checks explicitly unverified.

## PR #14 - Native global instrumentation privacy failure

- **Reported failure:** On the pinned stack, an opt-in native-global
  instrumentation probe emitted duplicate FastAPI spans
  (`fastapi.dependencies`, `fastapi.endpoint`, `fastapi.serialization`, and
  `GET /secret`) alongside manual HTTP telemetry. A synthetic query canary
  appeared in exported span JSON.
- **Implemented fix:** The final PR #14 code at
  `3aa389f21bf027e61a417f3c56fae358358e675a` removes the native opt-in,
  disables automatic instrumentation, uses public metric classes and
  temporality instead of private SDK fields, preserves payload-free recovery
  signals, and restores restricted-origin CORS trace/correlation headers.
- **Focused evidence:** All 23 telemetry tests passed locally in the
  integrated hash-verified locked environment, including the subprocess
  query/prompt/tool/identity/failure canaries, recovery-log redaction, and
  allowed/disallowed-origin CORS checks. The imported unnecessary f-string
  initially failed Ruff; its safe fix and formatting now pass.
- **Limit / next action:** These are focused integrated working-tree results,
  not final combined CI or cloud ingestion evidence. Native auto-instrumentation
  remains disabled and unverified, not approved for privacy-sensitive use.
  Run source/generated and exact-final-revision checks before review.

## 2026-11-21 - Integrated gap reconciliation and backlog

- **Scope:** Read-only reconciliation of integrated PR #17 against the
  documented MAF reference patterns and the current phase-1 target, followed by
  issue-linked documentation updates. The reference analysis in
  `docs/reference-repository-analysis.md` adopts framework-native workflow
  ownership, isolated approval/recovery, independent generated projects,
  accurate evidence, privacy and component boundaries; it does not import the
  reference business scenario or claim its deployment.
- **Historical integrated evidence (not valid for the refreshed base):** Head
  `98091a35976069dafa239ade9bf053b35ee829b7`, run
  [44951264840](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44951264840),
  six of six jobs successful. GitHub checked merge ref
  `b728ed00d92c58cf1e580a68537edc32db543c30`; its parents were the pinned
  base `814491811eac457826108b70fc213fdc564af0e5` and this head, and its tree
  equaled the head tree. Source/generated backends passed 72 tests each;
  generated verifier passed 44 with no skips. Source/generated frontend,
  infrastructure and Compose jobs passed. The unsigned independent validator
  intentionally remained exit 1/unverified: approval and recovery observations
  passed; explanation and hint remained unverified. These results establish
  the integrated code/CI checks only, not readiness or deployment.
- **Open implementation and verification work:** Issues
  [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18) (offline
  infrastructure wiring),
  [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19) (hosted
  MAF/checkpoints),
  [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20)
  (lost-response/effect recovery),
  [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21)
  (authorized contract review and independent trust),
  [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22)
  (caller/session binding),
  [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23)
  (cross-platform developer experience),
  [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24)
  (managed PostgreSQL/migration operations),
  [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25)
  (evaluations/browser hints),
  [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26) (cloud
  telemetry),
  [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27) (live
  Entra/OBO and accessible UI),
  [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28)
  (authorized deployment),
  [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29) (measured
  local demo),
  [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30) (P1
  permanent reference application; requires separate repository
  authorization),
  [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31) (optional
  ACA runtime),
  [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32) (P0
  consequential external-effect authorization and idempotency),
  [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33)
  (Specification Studio handoff), and
  [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34) (separate
  App/API roadmap), and
  [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35) (P1
  reusable model, agent, prompt, tool and executor patterns). Their criteria
  are tracked in the issues and linked from the checklist, plan and relevant
  design documents.
- **Deferral and authorization:** Hosted recovery was explicitly deferred to
  a separate scoped follow-up. This is not a security waiver; caller binding,
  the trusted host bridge and safe lost-response recovery remain
  unimplemented. Static prerequisites and separately authorized deployment
  are distinct: a live deployment should produce evidence for hosted/cloud
  issues and need not wait for all live-verification issues to close. A
  read-only Azure subscription/resource-group listing returned HTTP 200; no
  resource was changed, and this does not verify deployment write access or
  application/service connectivity. No Azure resources or permanent
  repository were created.
- **Merge-order lesson:** PR #11 is the foundation against `main`; dependent
  workstreams target `modularity-foundation`, and #14 had a stale `d0e1727`
  base at reconciliation time. Do not merge dependent PRs into `main` without
  retargeting them after #11, and do not assume aggregate #17 supersedes
  workstream review or has identical trees. Verify each exact head/base,
  feature delta and CI; compare resulting trees before deciding whether #17
  adds unique changes. Never replay complete histories or merge both paths
  blindly. If foundation changes or the target is retargeted, rerun relevant
  checks on the resulting tree.

## Current acceptance queue

| Item | Status | Evidence needed / next action |
| --- | --- | --- |
| Eight design documents and generated inclusion | Passed at exact tested head `b633539` | `maf-independent` passed in run 44955776238 after copying and checking the issue-linked documentation. Earlier run 44955210922 applies to `152743a`, not `b633539`. This documentation correction is newer than `b633539` and requires its own exact-head CI. |
| Canonical imports, API module boundaries and legacy-shim removal | Implemented in foundation head `1e99e03` | PR #11 run [44954168348](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44954168348) passed five checks for that exact head. Preserve direct imports and canonical route/composition/lifecycle boundaries. |
| Generated-verifier pipeline failure propagation | Implemented in foundation commit `d0e1727`, retained at `1e99e03` | `tests/test_ci_workflow.py` covers failed, skipped, expected-failure, and successful outputs; PR #11 run 44954168348 passed all five checks at head `1e99e03`. |
| Locked developer tooling | Passed source/generated installs and Ruff at exact tested head `b633539` | Run 44955776238 passed the locked source/generated jobs. Earlier run 44955210922 applies to `152743a` only. macOS, interactive debugging and Restricted Mode remain unverified; track [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23). |
| Privacy-safe observability | Manual instrumentation fixed; hosted telemetry unverified | 23 focused telemetry regressions passed; `maf-core` and `maf-independent` passed in run 44955776238 on `b633539`. Keep native auto-instrumentation disabled after the recorded privacy failure; track live cloud export in [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26). |
| Versioned database migrations | Integrated; exact-head source/generated CI passed | Run 44955776238 passed `maf-core` and `maf-independent` on `b633539`. Managed PostgreSQL version alignment, backup/restore and operational evidence remain in [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24); historical PG16 tests were on separate revisions. |
| Foundry-first infrastructure staging | Static validation passed; application graph not wired or deployed | Run 44955776238 passed `maf-infrastructure` and generated infrastructure checks on `b633539`. Private paths, database identity, auth/proxy wiring and service contracts remain in [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18); deployment requires separate authorization under [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28). |
| PostgreSQL major-version alignment | Local integrated runtime tested on PostgreSQL 17.12 | Azure template selects 16; earlier 16.15 migration checks were on separate revisions. Resolve target and verify managed behavior under [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24). |
| Combined PR #17 revision CI | Six-check pass on exact head `b63353944372f2b6dcd91546cca3a350250be78b`, base `1e99e038dc31c0ae25e5ea7712030d204ee35bc0` | Run [44955776238](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44955776238) passed all six checks. Merge ref `0a54717118879bab6be56633dc29c313178d9081` had exact base/head parents and identical tree `1e0a7994da25cbf63c9e3f6b7284f1a660260c55`; generated verifier passed 44 tests, `OK`, no skips or expected failures. Synthetic producer reported approval/recovery passed and explanation/hint unverified; the unsigned validator exited 1/unverified. Earlier run 44955210922 applies to `152743a`, not this head. This documentation correction is newer than `b633539` and requires fresh exact-head CI; keep the stacked target and revalidate after any later tree/base change. |
| Foundry host identity, per-user isolation, checkpoints and lost-response recovery | Blocked and explicitly deferred | No trusted host bridge, per-caller session map, managed checkpoint integration or safe ambiguous-create recovery. Preserve distinction between `x-agent-user-id` and opaque `x-ms-user-identity`; never persist end-user bearer/OBO tokens. Track host/checkpoints [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19), recovery [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20), caller binding [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22). Deferral is not a security waiver. |
| Independent readiness trust, evaluations and browser hints | Incomplete/unverified | Synthetic approval/recovery passed; explanation/hint remain unverified and unsigned validator exits 1. Track trust [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21), evaluations/hints [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25). |
| Live Entra/OBO, accessible UI, external effects and local demo | Unverified or not exercised | Track [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27), P0 consequential effects [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32), and [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29). Block consequential remote actions until #32 is verified. |
| Reusable MAF extension contracts | P1, not yet specified or independently demonstrated | Track typed model, agent, prompt, tool/authorization and executor/workflow patterns in [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35); preserve MAF-native semantics and no shared runtime. |
| P1 permanent standalone reference application | Required deliverable, blocked on separate repository authorization | Track [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30); no repository has been authorized or created. |
| Specification handoff and later runtime/App/API roadmap | Deferred/out of this phase | Track [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33), [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31), and [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34); no implementation authorization is implied. |

Future entries should use this form: date and scope; observed issue and
evidence-backed cause; attempted approaches (including failures); accepted
change or decision; focused tests and exact revision/CI evidence; remaining
limitations and reusable lesson. Do not invent historical root causes when the
available PR or test record does not establish one.

## 2026-11-21 - Foundation refresh and retained workstream matrix

- **Foundation reconciliation:** PR #11 head
  `1e99e038dc31c0ae25e5ea7712030d204ee35bc0` is the current
  `modularity-foundation` branch head and is included as a merge parent in
  local integration commit `13cfeb804c75fc450e13786d26ee125477adbc25`.
  The local merge-base is the exact PR #11 head; retain the stacked target.
  Push the refreshed #17 head and confirm GitHub's displayed base/merge ref
  rather than retargeting the PR. PR #17's last combined run
  [44951264840](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44951264840)
  remains historical for head `98091a3` / base `8144918`.
- **Workstream reconciliation:** The integrated tree retains the reviewed
  net changes and engineering learnings below; it does not make the aggregate
  PR a substitute for individual review, and tree identity is not assumed.

| PR | Retained paths and integrated outcome | Evidence/learning preserved |
| --- | --- | --- |
| #12 | `blueprints/maf/workflow/docs/design/{prd,userflow,specs,techstack,projectstructure,architecture,deployment-flow,issues-changes-fixes}.md`, `docs/{master-checklist,implementation-plan,agent-blueprints-architecture}.md`, and the blueprint README. | The eight design documents describe actual component ownership, identity/runtime flows, configuration and deployment boundaries; diagrams and engineering decisions remain in the journal. Individual CI [44950235818](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44950235818) passed exact PR head `fbed3c7`; issue links and known limitations are updated in this revision. |
| #13 | `blueprints/maf/workflow/backend/{pyproject.toml,uv.lock}`, `.vscode/{launch,tasks}.json`, backend Docker/build paths, CI and adopter/debugging documentation. | uv remains canonical and dependencies are consolidated in the lock. Individual CI [44947297321](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44947297321) passed exact PR head `7325765`. Generated headless debugger/DAP behavior is owner-reported; interactive VS Code, Restricted Mode and macOS remain unverified under [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23). |
| #14 | `blueprints/maf/workflow/backend/app/infrastructure/telemetry.py`, `backend/tests/test_telemetry.py`, API middleware/CORS, frontend API trace context and related security/client tests. | Public metric temporality replaces private SDK fields; unsafe native global instrumentation remains disabled after duplicate spans and a query-canary leak. The 23 focused tests cover privacy, recovery logging and CORS. Individual CI [44951057522](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44951057522) passed exact PR head `11fa5af`; hosted ingestion remains unverified under [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26). |
| #15 | `blueprints/maf/workflow/azure.yaml`, `infra/{main.bicep,modules/**,validate.py,tests/test_validation.py}`, generated-project instantiation checks and deployment/operator documentation. | Offline Bicep/azd checks are retained, but the application graph is not fully wired or deployed. Individual CI [44949593122](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44949593122) passed exact PR head `e1cde71`, including `maf-infrastructure`. Read-only Azure subscription/resource-group listing returned HTTP 200; no resources were changed, and this does not prove deployment write access or private service connectivity. Track [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18) and separately authorized deployment [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28). |
| #16 | `blueprints/maf/workflow/backend/app/infrastructure/migrations.py`, `backend/migrations/{baseline.sql,env.py,manifests/**,versions/**}`, migration fixtures/tests, startup validation and runtime-role checks. | Standard Alembic revisions preserve guarded exact-baseline adoption, data integrity, explicit owner upgrades, and runtime least privilege. Individual CI [44947337144](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44947337144) passed exact PR head `d125135`. Local PostgreSQL 16/17 and revision-specific checks are not managed backup/restore or current combined CI evidence; track [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24). |

- **Priority/extension decisions:** Track reusable typed model, agent,
  prompt, tool/authorization and executor/workflow patterns as P1 [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35);
  the permanent independent application is P1 [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30)
  but still requires separate repository authorization. Consequential
  external effects are P0 [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32):
  block them until authorization, downstream idempotency/outbox, reconciliation
  and fault-injection evidence pass.
- **Next verification:** Run focused documentation/instantiation and CI
  workflow tests, push without force, verify the exact #17 head, base and merge
  tree, and inspect every combined Actions check including `maf-infrastructure`
  and generated-verifier no-skip evidence. Keep all workstream issues open;
  no PR merge, PR close, Azure mutation, or permanent repository creation is
  authorized here.
