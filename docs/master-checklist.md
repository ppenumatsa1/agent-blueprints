# Software Factory master checklist

This is the living tracker for the three-repository Software Factory. Update
it, the [implementation plan](implementation-plan.md), and relevant
architecture documentation with each meaningful PR. Use **Planned**,
**In Progress**, **Completed**, or **Blocked**; mark work completed only
when it is implemented and supported by evidence. A plan link is a design
reference, not proof that functionality exists.

The original [interactive architecture](software-factory.html) is a preserved
historical source; this checklist records current status. The 2–3 hour
prototype objective has not yet been measured.

PR #17 merged into `main` at
`0c1297cc8e93c62f69d61d0eb3bdabf3c27c683d`, with parents
`de1cbe4cc3a93f2473a6f8f5f9e063d1ae278fa3` and final #17 head
`1a3e7c75f2ff5ffa8ef055e474a7ea5fb6d2a397`. The merge tree
`f4623d919f75ec4f6d5bf2d9f4e365a1bdcaa124` matches the PR #17 head tree.
Exact-main run
[45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271)
passed all six jobs for that historical baseline. PRs #36, #37 and #40 are
merged into current `main` at
`49932ee0cd61ee653a5f86be0f43873cec197ff9`; that exact main revision is the
base for the #39 evaluation follow-on. Green CI is not blueprint completion,
release readiness, or Azure deployment approval.

## Local Azure/Foundry integration acceptance

**Status: Completed for local integration; Azure API/web runtime and database
connectivity verified; hosted business execution and production unverified.**
The integration starts at exact main
`886b628fdea02f9089c385b4ed0fc46d90f375e8`. Accepted sources are
A `708a4185abe149526c606477de02cd57c5d90a9c` (#45),
C `722fc4e32937df4bd94678ec12380cac2a7c84df` (#48; runtime TLS fix
`509fb0b20c80fa8e436de4ac782f618c47f38bd3`),
B `b09877c219d3b9ec813614d879f5e1897729b254` (#47), and
D `9336176459cf38c367c8956849ceac32ffa98cbc` (#46).
Their exact-head owner CI is green. Runtime integration revision
`920a339777e23be85c34402afb7fb4322ca26e02` supplies the following
local evidence. Later owner follow-ups record TLS/provenance evidence and
enforce image-owned CA configuration in the generated-image guard; application
runtime bytes are unchanged.

| Acceptance criterion | Scoped local evidence |
| --- | --- |
| Native MAF and separate hosted/business persistence | Source backend 124 pass; fresh generated backend 169 pass, one explicit real-provider opt-in skip; hosted 41 and publisher 9 pass |
| Authenticated human prebinding, terminal replay, one effect, null hosted checkpoint columns | Isolated PostgreSQL 17 authority/composed-wire suite 13 pass; terminal retries do not redispatch Responses |
| Exact business contract and generated independence | Generated verification 61 pass without skips, including both actual adapters and all ORS-001..009; root 87 pass with two disclosed adapter-not-selected skips |
| Canonical protected API image and system trust | Backend-only production image/import/composition guard passes; normal hosted `app.main` Docker command/lifespan reaches health `204` and protected `401`; actual PostgreSQL TLS confirmed; wrong hostname and untrusted CA rejected |
| Local stack, frontend, infrastructure, and evidence boundaries | Compose API/web/PostgreSQL healthy; source/generated UI 9/10 pass, builds/CSP pass, Chromium render passes; infrastructure 17 plus base 9 pass and Bicep compilation/lint pass; generated Ruff 87 files pass; evidence keeps cloud/production unverified and release blocked |

Builds use supported credentialless HTTPS `PYTHON_PACKAGE_INDEX` and
`NPM_REGISTRY` overrides without disabling TLS, hashes, or lockfile integrity.
Synthetic certificate trust is confined to disposable test containers;
deployment must not override image-owned `SSL_CERT_FILE`. Existing test
connection ResourceWarnings and the Vite chunk-size warning remain disclosed,
not waived production checks. Harness import-path/database setup failures were
corrected before the final complete suites passed; no tests were removed.

**Next action:** draft PR #49 now includes the generated startup correction at
`2ef516107b47f57ea266021b2651ca13b235bd3e` and the frontend upstream-TLS SNI
correction at `9d5a66315f223cb424b70a20679cd6d950f47ffb`. ACR runs `ch5` and
`cha` produced immutable API and web digests. The sole active revisions
`aborsfoundpv2n45-api--final-2ef5161` and
`aborsfoundpv2n45-web--final-9d5a663` are healthy. Live checks returned API
`/healthz` `204`, unauthenticated `/api/cases` `401`, web root `200`, and
proxied web `/healthz` `204`; API startup logs record successful
managed-identity `database.connect`. The final API binds the active hosted
identity and `Hosted.Workflow.Invoke`, while prohibited local runtime settings
remain absent. No business action was invoked. Preserve this exact revision,
image, endpoint, configuration, and log evidence; then complete only the
separately authorized hosted/browser/evaluation checks. Remove the temporary
broad E2E firewall rule after E2E and replace it with actual API outbound
addresses plus the operator address only if still needed. Production
authorization remains unverified. The original architecture HTML remains
unchanged.

## Azure/Foundry Workstream C

**Status: In Progress.** The cloud application increment adds an SDK-free
hosted-workflow port, explicit `local` versus `hosted` composition, API-UAMI
caller tokens, Azure PostgreSQL managed-identity/password configuration,
verified TLS requirements, bounded connections, explicit runtime/migration
identity separation, and restart reconciliation for ambiguous hosted outcomes.
The API UAMI is the sole PostgreSQL runtime principal. The hosted identity
calls the protected `/api/internal/hosted/v1` boundary with the fixed
`Hosted.Workflow.Invoke` app role and receives no database configuration.
Durable case/conversation/channel binding, case-bound idempotency, exact
Agent A operation-journal conversion, and business-only hosted
pending/decision/effect/completion state leave local checkpoint columns null.

Acceptance evidence is local only: 117 source-backend tests, 117 tests in a
fresh generated generic backend, 159 tests in a fresh generated Order
Resolution backend, the ORS-001..009 adapter contract (9/9), 68 root tests
with two expected unselected-adapter skips, and source/generated frontend
suites with 9/9 or 10/10 tests plus build/CSP passed. A PostgreSQL 17 and
loopback HTTP test composes Agent A's live `HttpHostedBusinessStore` and
`ResponsesClient` with C's exact journal types, covers restart/duplicate
no-replay with changing opaque platform call IDs, revocation and changed-intent
negatives, post-terminal approved/rejected command replay through Agent A's
acknowledged journal without a second Responses dispatch, and one
decision/effect with null checkpoint fields.
Fresh generated Compose built through approved package proxies, ran explicit
migrations, became healthy, and returned root `200`, health `204`, and
protected API `401`. The canonical backend image also exports
`SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` so bundled libpq/OpenSSL
discovers the same readable system bundle selected by
`PGSSLROOTCERT=system`; `verify-full` remains mandatory. An isolated
PostgreSQL 17 image proof passed normal `app.main` startup and reported TLS in
`pg_stat_ssl`; a trusted certificate for the wrong hostname and an untrusted
CA both failed certificate verification. The
[application security contract](azure-foundry/application-security.md)
records the identity matrix, Agent A interface, Agent B outputs, OBO decision,
and recovery behavior. Draft PR [#48](https://github.com/ppenumatsa1/agent-blueprints/pull/48)
contains the Workstream C implementation. Next action: obtain draft-PR review
and exact-head CI,
then run the listed live-only checks after integration and authorized
deployment. No Azure resource or live RBAC/configuration was changed here.

The TCP-readiness correction from [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38)
and current MAF-native patterns are in merged #37. PR #39 is being reconciled
directly onto current `main` without replaying #37. Its new exact-head
validation is required; earlier stacked-branch CI does not validate this
baseline.

## Azure/Foundry Workstream B

**Status: In Progress - ready for independent validation, not deployed.**

Starting from exact main
`886b628fdea02f9089c385b4ed0fc46d90f375e8`, Workstream B adds the
[deployment plan](../.azure/deployment-plan.md), infrastructure-only azd
descriptor, modular public-network Bicep, Azure CLI deployment orchestration,
infrastructure contract
tests, and the [operator evidence](azure-foundry/infrastructure.md). East US 2
is selected without a split-region design for `gpt-4.1-mini`
`2025-04-14` on `GlobalStandard` capacity 10. Read-only evidence found enough
model quota/capacity and dependent-service quota. Azure CLI mode validates the
authorized active context and reports the unrelated azd mismatch without
blocking; explicit azd mode still fails closed.

Acceptance evidence: Bicep build/lint and 17 infrastructure contracts pass; the
root suite passes 68 tests with two expected adapter-selection skips; all new
PowerShell/Python files parse. No Azure resource, RBAC assignment, database
principal, migration, deployment, rollback, or teardown was executed.
Deployment generates an independent Order Resolution project, requires the
Agent A/C hosted and managed-identity interfaces, patches only the generated
nginx upstream to the exact API FQDN, and prohibits the source blueprint,
synthetic application selector, local workflow host, and file checkpoints.
The protected API state boundary and API-only PostgreSQL access are established
before publication. The pending hosted identity receives only a dedicated API
application role before the same journaled version is required active; hosted
code receives no direct database access. Agent Consumer assignment additionally
uses only the official exact agent scope derived from validated project output
and the fixed publisher agent name; wider or another-agent scopes fail closed.
The hosted app role authenticates service identity only; API-owned exact
human principal/case authority bound to the server-selected conversation and
channel must exist before Responses dispatch and cannot be inferred from the
hosted token. Foundry user/session/call values are opaque platform correlation,
not human authority; no caller-selected session or actor metadata is sent.
Exact final A `708a4185` plus final C `722fc4e3` (all-six CI run
`45087843018`) generation produced
byte-identical owned files, built/imported the canonical no-dev backend, and
passed nonconnecting wire composition. The integration coordinator
independently reports default Docker CMD/app lifespan passed against isolated
PostgreSQL 17 with inherited image CA setting, verified TLS, health `204`, and
protected `401`; hostname and trust negatives failed closed. B did not rerun
that suite. The exact generated web target also passed unchanged `npm ci`,
production Vite build, and CSP verification through the credentialless HTTPS
npm proxy. C's TLS code parent `509fb0b2` owns the canonical image
`SSL_CERT_FILE`; B deploy contracts
prohibit overriding the image default. Canonical packaging evidence is
complete.

**Next action:** independently validate the exact PR revision, supply the
deployment-specific hosted endpoint/agent-name/administrator/journal values,
review Azure CLI provider what-if, and approve resource
inventory, cost, identity, and public-network controls before deployment.

## Reconciled engineering backlog

The foundation and the integrated review do not establish blueprint
completion or deployment readiness. The issues below retain their own
acceptance criteria, dependencies and required independent evidence.
Deferred work remains deferred; critical security checks are not waived.
The [issue and fix journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---issue-and-fix-status)
records the current review snapshot, scoped evidence, and next actions. Its
open PR references do not imply those changes have merged into this branch.

| Area | Open tracking issues | Next action |
| --- | --- | --- |
| Hosted identity, execution and recovery | [Caller binding #22](https://github.com/ppenumatsa1/agent-blueprints/issues/22), [host and checkpoints #19](https://github.com/ppenumatsa1/agent-blueprints/issues/19), [lost-response recovery #20](https://github.com/ppenumatsa1/agent-blueprints/issues/20), [external effects #32](https://github.com/ppenumatsa1/agent-blueprints/issues/32) | Implement and independently verify the security and durability boundaries. |
| MAF adopter extension patterns | [Reusable model, agent, prompt, tool and executor patterns #35](https://github.com/ppenumatsa1/agent-blueprints/issues/35) | Specify typed framework-native extension contracts and prove each in an independent synthetic generated application. |
| Independent readiness | [Trust and contract approval #21](https://github.com/ppenumatsa1/agent-blueprints/issues/21), [evaluations and browser hints #25](https://github.com/ppenumatsa1/agent-blueprints/issues/25) | Obtain authorized trust and produce actual evidence; retain unverified outcomes. |
| Azure and operations | [Infrastructure #18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), [managed PostgreSQL #24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), [telemetry #26](https://github.com/ppenumatsa1/agent-blueprints/issues/26), [live identity and accessibility #27](https://github.com/ppenumatsa1/agent-blueprints/issues/27), [deployment #28](https://github.com/ppenumatsa1/agent-blueprints/issues/28) | Close offline prerequisites, validate access and obtain approval of the concrete deployment plan before live validation. |
| Developer experience and demonstration | [Cross-platform tooling #23](https://github.com/ppenumatsa1/agent-blueprints/issues/23), [measured local demo #29](https://github.com/ppenumatsa1/agent-blueprints/issues/29) | Verify supported environments and record a representative end-to-end run. |
| P1 reference application and later work | [Permanent standalone reference #30](https://github.com/ppenumatsa1/agent-blueprints/issues/30) is P1 and still requires separate repository authorization; [ACA runtime #31](https://github.com/ppenumatsa1/agent-blueprints/issues/31), [Specification Studio #33](https://github.com/ppenumatsa1/agent-blueprints/issues/33), and [later blueprints #34](https://github.com/ppenumatsa1/agent-blueprints/issues/34) remain separately scoped. | Track the P1 deliverable without creating a repository absent authorization; preserve out-of-phase boundaries for the remaining items. |

The #17 row-level acceptance evidence below remains more detailed. In
particular, #28's offline prerequisites are distinct from authorized live
deployment; deployment is expected to produce evidence for hosted/cloud
issues and need not wait for all live verification to close.

| Requirement or capability | Phase | Status | Acceptance criteria | Evidence or PR | Next action |
| --- | --- | --- | --- | --- | --- |
| Three-repository architecture and boundaries | 0 | Completed | Document Specification Studio, Agent Blueprints, and App/API Blueprints and their handoff. | [Overview](software-factory-overview.md); [PR #1](https://github.com/ppenumatsa1/agent-blueprints/pull/1) | Update architecture when decisions change. |
| Reference analysis, catalog, and engineering standards | 0 | Completed | Document reference evidence, framework-native blueprints, and engineering boundaries without claiming unverified deployments. | [Analysis](reference-repository-analysis.md); [catalog](blueprint-catalog.md); [standards](engineering-standards.md); [PR #1](https://github.com/ppenumatsa1/agent-blueprints/pull/1) | Reassess compatibility as blueprints are implemented. |
| Repository licensing | 0 | Completed | Select and include a license for the public repository. | [MIT License](../LICENSE); [PR #1](https://github.com/ppenumatsa1/agent-blueprints/pull/1) | Retain third-party notices when code is reused. |
| Supplied interactive architecture source | 0 | Completed | Include the original HTML without fabricating a replacement; retain its source bytes and identify it as a historical baseline. | [Original HTML](software-factory.html); [PR #2](https://github.com/ppenumatsa1/agent-blueprints/pull/2) | Preserve the supplied source. |
| Prototype and production readiness contracts | 0 | Completed | Schemas and fixtures preserve per-requirement results, protect critical gates, disclose prototype limitations, and represent reviewed production risk acceptance. | [Policy](readiness-contract.md); [PR #2](https://github.com/ppenumatsa1/agent-blueprints/pull/2) | Independently review scenario contract and trust setup. |
| Living tracker and Phase 1 plan | 0 | Completed | Track status, acceptance criteria, evidence, and next actions; keep work packages independently verifiable. | [Plan](implementation-plan.md); [PR #2](https://github.com/ppenumatsa1/agent-blueprints/pull/2) | Update with each meaningful PR. |
| Cross-framework Order Resolution specification | 0 | Completed | Define a versioned framework-neutral scenario set for triage, policy retrieval, deterministic resolution, authorized human decisions, idempotency, restart recovery, and evaluations while requiring native framework checkpoints and separate application persistence. | [Proposal](order-resolution-specification-proposal.md); merged PR [#40](https://github.com/ppenumatsa1/agent-blueprints/pull/40) is included in current `main`. | Obtain a human readiness decision on the specification, then map it independently to each future framework blueprint with implementation-specific evidence. |
| Executable Order Resolution acceptance contract | 0 | Completed | Encode exactly `order-resolution-spec/0.1.0` and `ORS-001` through `ORS-009`; preserve decimal USD round-half-up refunds, approval/action/outcome rules, explicit evidence failures, and separate business versus technical assertions without adding a runtime. | [Fixture](../scenarios/order-resolution/README.md), [root contract tests](../tests/test_order_resolution_contract.py), and merged [PR #42](https://github.com/ppenumatsa1/agent-blueprints/pull/42). | Framework mappings must preserve its normalized outcomes while adding implementation-specific evidence. |
| Generated MAF Order Resolution application | 1 | In Progress | Preserve default generation; add one explicit independently owned profile using FastAPI, React, PostgreSQL, Compose, native MAF workflow/checkpoints, deterministic proposals, authorized decisions, fail-closed policy evidence, durable synthetic effects, native evaluation, and no source runtime dependency. | Merged [PR #44](https://github.com/ppenumatsa1/agent-blueprints/pull/44) supplies the application and merged [PR #41](https://github.com/ppenumatsa1/agent-blueprints/pull/41) supplies durability/effect safety. Draft [PR #43](https://github.com/ppenumatsa1/agent-blueprints/pull/43) integrates evaluation/readiness. A fresh external generation passed 147 backend tests, 10 frontend tests plus build/CSP, `ORS-001` through `ORS-009` with no skips, native deterministic technical/business evaluations, an unverified independent readiness report, source-independence checks, and Compose root `200`/health `204`/protected API `401`. Native MAF retains checkpoint ownership. | Obtain exact-head six-job CI and independent review. Keep real downstream guarantees unverified/#32-blocked; real model quality, browser evidence, trusted provenance, deployment, and production readiness remain incomplete. |
| MAF modularity foundation and supply-chain guard | 1 | In Progress | Separate sibling backend/frontend contexts and API/lifecycle responsibilities, use canonical imports without compatibility shims, preserve native recovery, reject the compromised `agent-framework` umbrella distribution, verify the approved core wheel against the canonical `uv.lock`, and ensure generated-verifier failures and skips fail CI. | PR #11 merged to `main` as `587e6cc1abc23a67845c8193d486cc65c8b52854`; PR #17 and the approved-wheel guard are included in `main`. The then-current exact-main run [45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271) passed all six jobs, including source/generated locked installs and rejection tests. Current #37 integration evidence is tracked separately below. | Preserve the canonical lock and hash verification; keep runtime and hosted claims scoped to evidence. |
| Versioned database migrations | 1 | In Progress | Preserve fresh-database creation and safely adopt only an exactly recognized legacy baseline; never stamp unrecognized or later-owned schemas. | Integrated `SPEC-12`, `backend/migrations/baseline.sql`, migration-aware startup and runtime least privilege passed in #17 `maf-core` and `maf-independent` jobs on `b633539` / run 44955776238. Historical PR #16 run and PostgreSQL 16 tests are separate; managed restore/version operations tracked in [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24). | Verify against the selected managed PostgreSQL target and backup/restore operations; do not infer Azure support from local tests. |
| Generated-project documentation | 1 | In Progress | Copy adopter/operator guides and all eight design documents; map requirements to implementation/tests, maintain the evidence journal, distinguish current/planned capability, and verify links/copy inclusion. | Exact-main run [45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271) passed the generated documentation and link checks after #17 merged. | Keep copied documentation synchronized and preserve the no-readiness boundary. |
| Cross-platform developer experience | 1 | In Progress | Maintain uv-based portable lock, Ruff/format, locked source/generated installs/builds, and usable editor tasks without shared runtime dependencies. | Run [44955776238](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44955776238) passed locked source/generated jobs on `b633539`. Headless generated debugpy/DAP was owner-reported; macOS, Restricted Mode and interactive UI remain unverified. Track [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23). | Verify remaining platform/debugger evidence against a named revision; any tree/base change requires exact-head CI. |
| Privacy-safe observability | 1 | In Progress | Use one supported global provider per runtime, enable native MAF instrumentation only with sensitive/message capture disabled, and verify connected hosted traces rather than row presence. | PR #49 remediation validates the pinned AgentServer/MAF/Azure Monitor APIs, uses supported HTTP propagation, preserves explicit durable restart links, and passes focused privacy/global-provider and hosted compatibility tests locally. Earlier unsafe native-global behavior remains historical evidence; the remediated cloud path is not passed until exact-head CI and live App Insights plus Foundry trajectory validation succeed. | Run exact-head CI, deploy immutable API/hosted revisions, and require one privacy-safe connected start/resume trace with a valid restart link in both views. |
| Reusable MAF extension patterns (#35) | 1 | In Progress | Demonstrate independently needed application config and authorization around direct MAF `Agent`, `@tool`, `Executor` and `WorkflowBuilder`; retain explicitly versioned prompts and an independent generated fixture. | Merged PR #37 removes redundant `ModelClientFactory`, `AgentDefinition`, `build_chat_agent`, and `ToolRegistry`; direct MAF composition, `ModelSelection`, `PromptAsset`, and request-scoped `ToolAuthorization` remain. Current merged state includes #36's external-effect boundary and #40's Order Resolution proposal. Exact combined-head evidence is recorded in merged PRs and current-main Actions. Arbitrary trusted callbacks remain unsandboxed; absolute non-bypass is unverified. Consequential effects remain restricted by #32. | Keep #35 and hosted capabilities in progress/unverified. |
| MAF evaluation extension (#25) | 1 | In Progress | Define app-owned datasets, rubrics, deterministic checks and thresholds; map native MAF results strictly to selected-contract readiness checks; preserve failed/unverified semantics and source/generated independence without making unsupported quality claims. | Merged PR #39 supplies the mapper without an evaluator framework. Draft [PR #43](https://github.com/ppenumatsa1/agent-blueprints/pull/43) uses native MAF `Evaluator`, `LocalEvaluator`, `@evaluator`, and `evaluate_agent()` in the generated Order Resolution profile. Local deterministic business and technical results pass; the independent validator remains unverified without trusted attestation. | Obtain exact-head CI and human review. Keep #25 open until actual model and browser evaluation evidence and independent provenance exist. |
| Foundry-first infrastructure staging | 1 | In Progress | Stage restrictive Bicep/azd paths without provisioning resources or claiming live connectivity. | Exact #17 run [44960731511](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44960731511) passed `maf-infrastructure` and generated infrastructure checks on `8b3c357`. Network, identity, cost and Azure behavior remain unverified. | Preserve no-provisioning boundary; infrastructure checks do not establish deployment or live connectivity. |
| Locked developer tooling dependency integration | 1 | In Progress | Keep one canonical uv lock, install source/generated environments reproducibly, lint/format and build independent generated projects. | Integrated lock includes dependencies from #13 and #14; exact #17 `maf-core`/`maf-independent` jobs passed at `b633539` in run 44955776238. Workstream #13 remains independently reviewable; no PR is superseded by aggregate evidence. | Compare feature delta/tree when sequencing merges; see [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23); rerun exact-head CI for later changes. |
| Cross-cutting implementation quality | 1 | In Progress | Before approval, remove shims/forwarders/obsolete paths, duplicate code, unused dependencies and stale config; preserve behavior and update dependent tests, Dockerfiles, CI, docs and generator. | [Acceptance gates](implementation-plan.md#cross-cutting-pr-acceptance-gates); [canonical structure](../blueprints/maf/workflow/docs/design/projectstructure.md); [engineering journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md). | Review remaining cleanup and rerun focused regressions plus exact-revision CI for any resulting tree change. |
| Versioned business database baseline | 1 | In Progress | Explicit schema-owner migration, per-revision drift checks, restricted runtime startup, data preservation, future upgrades and recovery/rollback limits. | [PR #16](https://github.com/ppenumatsa1/agent-blueprints/pull/16), [run 44940559106](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44940559106) passed five jobs for `eb898f6`. Combined source/generated backends passed 68 tests each locally on PG 16.15 and 17.12 at `af3955a`; exact #17 `maf-core` and `maf-independent` checks also passed at `b633539` / run 44955776238. Earlier failures and unverified outcomes remain in the [journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md). | Live restore and hosted identities remain unverified. |
| Combined engineering integration | 1 | In Progress | Run source/generated security, durability, migrations, telemetry, independent acceptance, Compose, UI, and offline IaC together; preserve exact contracts and failed/unverified outcomes. | PR #17 merged into `main` at `0c1297c`; exact-main run [45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271) passed all six jobs for that historical baseline. The current #37 integration commit `245cbe2` passed all six jobs in exact-head run [45040560075](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45040560075), with GitHub merge-ref/tree verification recorded in the #35 row. | Human review; green CI is not readiness or Azure deployment approval. |
| Synthetic business scenario and approved contract (P1-01) | 1 | In Progress | Approve a non-destructive scenario and exact contract digest, with explicit criticality and profile gates. | [Scenario and golden cases](../scenarios/order-adjustment/README.md); [test-only API adapter](../blueprints/maf/workflow/backend/tests/order_adjustment_adapter.py); independent authorized exact-contract review tracked in [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21). | Obtain and independently administer approval of the exact contract bytes. |
| Normalized evidence and decision inputs (P1-02) | 1 | In Progress | Map test results, artifacts, baseline contracts, and human decisions to explicit IDs and scope. | [Synthetic runner](../blueprints/maf/workflow/backend/tests/evidence_runner.py); [input and trust schemas](../contracts/); [validator tests](../tests/test_readiness.py); independent result provenance in [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21). | Independently administer and protect result attestation and human decisions. |
| Executable readiness validator (P1-03) | 1 | In Progress | Verify traceability, evidence bytes and freshness, criticality, decisions, and profile gates; reject invalid evidence as proof of passing. | [Validator](../readiness/validator.py); [acceptance tests](../tests/test_readiness.py) | Verify trusted provenance, human authority, and repository protection. |
| Readiness CLI and machine-readable report (P1-04) | 1 | Completed | Consume approved inputs, preserve outcomes and disclosures, emit a report, and use profile-appropriate exit codes. | [CLI](../readiness/__main__.py); [tests](../tests/test_readiness.py); unsigned synthetic results produce an unverified report. | Independently administer trust and result provenance. |
| Local development stack (P1-05) | 1 | In Progress | Start React, FastAPI, PostgreSQL, and Docker Compose; automated tests need no Azure credentials, while interactive sign-in uses existing Entra configuration. | [Blueprint](../blueprints/maf/workflow/README.md); source/generated Compose checks passed in exact-head run 44955776238 (UI 200, health 204, protected API 401, private checkpoint volume). | Verify interactive Entra and accessibility under [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27). |
| PostgreSQL startup readiness | 1 | In Progress | Gate source/generated CI and Compose startup on final loopback TCP readiness, with bounded failure; never treat the temporary initialization socket as service readiness. | [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38) records socket-ready/TCP-unready observations on disposable PostgreSQL 16.15 and 17 and a failed initial 16.15 `createdb`; the retry passed 72 source and 72 generated tests on historical head `8b3c357`. The correction's working-tree checks reproduced the socket/TCP transition on 16/17, passed 72 source/generated tests each on 17 and source/generated Compose HTTP checks using cached images; fresh local image builds hit dependency-download failures. The new probe and regression require exact-head CI evidence. | Verify source/generated CI and Compose on the resulting head; this is not managed PostgreSQL evidence. |
| Independent blueprint instantiation | 1 | In Progress | Generate a self-contained project that builds, runs and tests without this repository; keep its synthetic readiness report distinct from trusted evidence. | [Generator](../scripts/instantiate_maf.py); `maf-independent` passed at exact #17 head `b633539` in run 44955776238. Synthetic report remains unverified (approval/recovery passed; explanation/hint unverified; unsigned validator exit 1). Independent trust/provenance tracked in [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21). | Continue independent trust administration; schema validation is not a release gate. |
| Business state, approvals, and idempotency (P1-06) | 1 | In Progress | Persist isolated business and approval state and prevent duplicate or unauthorized database actions across both specified crash windows. | [Core tests](../blueprints/maf/workflow/backend/tests/test_core.py), including both worker-kill windows; exact #17 `maf-core` and `maf-independent` jobs passed at `b633539` in run 44955776238. External effects remain outside this guarantee. | Preserve tested local guarantees; do not claim universal exactly-once behavior. |
| Consequential external side-effect authorization and idempotency (P0) | 1 | Blocked | Before consequential remote effects, require service-specific authorization, verified downstream idempotency and authoritative reconciliation; otherwise fail closed and use manual resolution rather than retrying an ambiguous effect. An outbox only persists intent; it cannot deduplicate an external effect after a lost acknowledgment. | The opt-in local pattern and separate durable synthetic downstream are exercised by `backend/tests/test_external_effect.py`; it passes a shared five-second budget, treats timeout as unknown, and reconciles before retry. Its `case:{id}:action` key covers one immutable action per case; future proposal-version/action/target identity follows merged #40. See [architecture](../blueprints/maf/workflow/docs/architecture.md). This is not evidence for a real service or a Python sandbox. Track [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32), #20 and #22. | Independently verify real adapter enforcement of deadlines, authorization, retention and reconciliation before consequential effects; keep #32 open. |
| Authenticated FastAPI service (P1-07) | 1 | In Progress | Validate Entra tokens, scopes, roles, and record access; support optional delegated OBO and explicit errors. | [API security tests](../blueprints/maf/workflow/backend/tests/test_security.py); exact #17 `maf-core` and `maf-independent` jobs passed at `b633539` / run 44955776238. Synthetic principals do not establish live Entra/OBO; track [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27). | Verify live Entra/OBO with separately authorized configuration; rerun exact-head CI for later tree/base changes. |
| Accessible React client (P1-08) | 1 | In Progress | Use MSAL and show submission, status, approval, rejection, and error states without service secrets. | Source/generated frontend tests, build and CSP passed in #17 run 44955776238 on `b633539`; live sign-in and accessibility assessment remain outstanding under [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27). | Verify interactive sign-in, accessibility, and the generated application. |
| Framework-native durable MAF workflow (P1-09) | 1 | In Progress | Use native local file checkpoints for isolated pause, resume, rejection, and recovery; keep hosted storage separate. | [Local host](../blueprints/maf/workflow/backend/app/workflows/host.py); exact #17 `maf-core` and `maf-independent` jobs passed at `b633539` / run 44955776238. Hosted MAF/checkpoints [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19), caller binding [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22), lost response [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20). | Keep hosted recovery deferred until these security-critical contracts are implemented and independently verified; deferral is not a waiver. |
| Tests, evaluations, and GitHub Actions (P1-10) | 1 | In Progress | Produce real local/CI artifacts and profile-correct readiness results, including negative cases. | Exact-tree CI [44955776238](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44955776238) passed at `b633539`; generated verifier passed 44 tests with no skips or expected failures. Producer observed approval/recovery passed, explanation/hint unverified; unsigned validator exit 1. Track evaluations/hints [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25) and trust [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21). | Add agent evaluation and browser evidence; maintain independently controlled attestations. |
| Privacy-safe observability (P1-11) | 1 | In Progress | Correlate request and workflow signals with allowlisted attributes, privacy canaries, one supported provider, native spans with raw capture off, and failure-isolated export. | The historical `3aa389f` leak/fix evidence remains in the [journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#pr-14---native-global-instrumentation-privacy-failure). PR #49 adds pinned API compatibility checks, global-provider reuse, supported HTTP propagation, content-free native MAF instrumentation, processor deduplication, and explicit durable trace links. Focused local tests pass; live post-remediation ingestion is unverified. | Require exact-head CI and one connected App Insights/Foundry start-resume trace before closing [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26). |
| Local prototype demonstration (P1-15) | 1 | Planned | Demonstrate the complete synthetic workflow and readiness report; record actual elapsed time and limitations. | [Phase 1 plan](implementation-plan.md#phase-1-maf-workflow-golden-path); 2–3 hour objective not measured. Track [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29). | Run and document a representative synthetic demo; this issue does not authorize cloud deployment. |
| Foundry Hosted Agents compatibility (P1-12) | 1 | Blocked | Record framework, protocol, identity, per-user session isolation, checkpoint, credential-lifecycle, and approval/resume compatibility evidence; local checks are not a hosted deployment. | [Hosted pattern and lost-response investigation](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---hosted-caller-binding-and-lost-responses) and [delegated session isolation clarification](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---delegated-session-isolation-and-debugger-evidence). The platform does not fence delegated users sharing a session; a trusted app must authorize each principal's session, map authenticated callers to distinct sessions and reject unchecked client IDs. Platform-generated `x-agent-user-id` is a different header from the opaque app-supplied `x-ms-user-identity` scoping value derived from the validated principal; do not assume their values match. Equivalence and binding to that principal are unsupported and unverified, and the scoping value is not authorization. No bridge or mapping tests, host integration, hosted secret delivery/rotation, or host-managed checkpoint integration is implemented/live verified. Local one-shot AgentServer task IDs reran fresh after terminal completion and are not persistent deduplication; hosted semantics remain unknown. Exact wheel source exposes `response_id` in the request-aware factory before checkpoint preparation/parsing/run claim, but safe caller-bound claims, per-continuation reservations, pending-reply/action ordering, idempotent side effects, and same-response recovery remain unproven. PostgreSQL CAS is only a candidate, not a fix. The scoping value is not a credential and end-user bearer/OBO tokens must not be persisted. Lost `response.id` recovery remains unresolved. | Implement and test caller-to-session authorization before hosted use; validate any task/CAS recovery scheme, then coordinate package/API compatibility, workload networking, credential lifecycle and app lifecycle; establish unambiguous lost-response reconciliation before safely retrying ambiguous creates. |
| ACA fallback compatibility (P1-13) | 1 | Planned | Verify a separately selected container recovery strategy without assuming Foundry checkpoint ownership. | [Phase 1 plan](implementation-plan.md#phase-1-maf-workflow-golden-path) | Prepare fallback only if selected. |
| Azure deployment preparation (P1-14) | 1 | In Progress | Independently copied Bicep/azd compiles and tests without Azure credentials; default configuration avoids public unauthenticated API exposure, documents scoped roles and explicit network gaps, and requires separate approval before provisioning. | Exact #17 run 44955776238 passed `maf-infrastructure` and generated infrastructure checks on `b633539`; read-only Azure subscription/resource-group listing previously returned HTTP 200, but no resource was changed and service connectivity/write access remain unverified. Staged graph is not wired or deployed. Track IaC wiring [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), managed DB operations [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), and separately authorized deployment [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28). | Finish offline prerequisites and obtain explicit authorization. Live deployment should produce hosted/cloud evidence and need not wait for all live-verification issues to close. |
| Specification Studio interoperability | 6 | Blocked | Validate the versioned handoff with an actual producer or a reviewed lossless adapter. | [Handoff contract](readiness-contract.md#specification-studio-handoff); issue [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33). | Obtain a real producer artifact when available; this remains outside Phase 1 and does not authorize implementation. |
| Permanent standalone reference application (P1) | 1 | Blocked pending authorization | Deliver a synthetic, independently owned application with no source-repository runtime dependency and documented extension/operational boundaries. | Required P1 deliverable tracked in [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30); no permanent repository has been authorized or created. | Obtain separate explicit repository authorization, then verify clean clone/build/run/test and independent contracts. |
| App/API Blueprints roadmap | Later | Planned | Establish separately authorized API/web-app paths and repositories. | Roadmap [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34); [Repository boundaries](software-factory-overview.md#repository-boundaries). | Keep out of phase and obtain separate authorization before implementation. |

### Azure/Foundry Workstream A

| Acceptance criterion | Status | Evidence | Next action |
| --- | --- | --- | --- |
| Generate an independently owned native MAF Responses host without a custom orchestrator/checkpointer | Implemented; locally verified 2026-11-22 | [Hosting report](azure-foundry/hosting.md); 41 generated hosted tests, 16 publisher/generator tests, and generated Ruff check/format passed. The explicit API bridge uses only `/conversations` and `/responses`, omits caller-supplied `agent_session_id`, and prebinds authenticated human authority to the server-selected conversation before dispatch. Exact C `2a04d5be3013e782a7c1222b2a16a7047cbb15cd` passed normal API composition and all six PR checks. | Keep live hosting, managed identity, RBAC, network, and checkpoint behavior unverified until separately authorized deployment. |
| Preserve application-owned PostgreSQL business state and local filesystem checkpoint behavior | Implemented; locally verified 2026-11-22 | Eight generated workflow tests, 39 focused generated backend tests on PostgreSQL 17, and ORS-001..009 passed. Exact C `2a04d5be3013e782a7c1222b2a16a7047cbb15cd` proved one decision/action, null checkpoint fields, and no hosted PostgreSQL connectivity through the protected API. | Keep direct hosted-to-PostgreSQL removed and preserve authenticated application prebinding before hosted start/resume. |
| Reject unauthorized/cross-channel resume and avoid ambiguous POST replay | Implemented; locally verified 2026-11-22 | Generated tests cover platform-session conflict rejection, conversation/channel refusal, API-workload versus human identity separation, missing pre-established owner/reviewer binding refusal, Responses pending/malformed acknowledgments, managed-identity internal API authorization, exact schemas, stable idempotency and ambiguous-write no replay. Exact C `2a04d5be3013e782a7c1222b2a16a7047cbb15cd` adds terminal exact-intent bridge replay with zero new Responses dispatch plus conflicting-intent and unauthorized-actor refusal. | Verify deployed identities and authoritative reconciliation behavior before any live invocation. |
| Pin current public SDK/source-publish compatibility without private patches | Implemented; locally verified 2026-11-22 | [Compatibility matrix](azure-foundry/hosting.md), SDK-drift tests, deterministic source archive test, two-phase identity/readiness no-replay test, and 68-test repository contract run (2 documented adapter skips) | Recheck pins at deployment time; do not publish on failed drift tests. |

## Issue-linked open backlog

The following links attach concrete acceptance work to the matching rows
above; none marks Phase 1 or deployment complete.

| Checklist capability | Tracked work |
| --- | --- |
| P1-01–03: contract approval, evidence provenance, independent trust | [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21) |
| P0: consequential external effects require explicit authorization and idempotency | [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32) |
| P1-07–08: live Entra/OBO, interactive authentication and accessibility | [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27) |
| P1-09/P1-12: hosted MAF packaging and host-managed checkpoints | [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19); caller/session authority [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22); lost-response and side-effect recovery [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20) |
| P1-10: real agent evaluation and browser-hint evidence | [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25); independent attestation [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21) |
| P1-11: verified cloud telemetry and trace propagation | [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26) |
| Developer tooling: cross-platform and interactive debugger verification | [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23) |
| P1-13: explicitly selected ACA workflow alternative | [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31) |
| P1-14: staged IaC wiring, managed database operations, deployment | [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28) |
| P1: reusable model, agent, prompt, tool and executor extension patterns | [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35); typed contracts and generated synthetic fixture are under review on the stacked workstream branch; actual provider calls and hosted semantics remain unverified. |
| P1-15: measured local synthetic demonstration | [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29) |
| Phase 0 Specification Studio handoff | [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33); separate producer contract in [readiness-contract.md](readiness-contract.md#specification-studio-handoff) |
| P1 permanent standalone reference application | [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30); separate explicit repository authorization is required |
| Later App/API blueprint roadmap | [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34); out of phase and requires separate authorization |

## Azure/Foundry Workstream D

| Capability | Status | Acceptance criteria | Evidence | Next action |
| --- | --- | --- | --- | --- |
| Privacy-safe end-to-end correlation | Remediation implemented; live gate failed/unverified | Correlate API, Foundry, native MAF workflow, and deterministic business stages with request/case/trace/conversation/agent/deployment identifiers; require model/token spans only when the real path invokes a model; exclude content and secrets. | PR #49 configures AgentServer's supported Azure Monitor exporter and HTTP instrumentation against the supplied App Insights connection, then enables native MAF instrumentation with sensitive data and message events disabled. Runtime construction now defers the application/MAF graph until after AgentServer initializes the one global provider. Durable HITL resume uses an explicit trace link, and the verifier requires connected W3C trees, conversation/deployment continuity, native/business spans, Foundry visibility, and no raw content without requiring model/token spans for deterministic execution. Pinned API compatibility and focused local tests pass; no post-fix cloud trace is yet claimed. | Obtain green exact-head CI, deploy immutable API/hosted revisions, execute one synthetic start/resume/restart transaction, and validate the same trace IDs in App Insights and Foundry. |
| Real-provider evaluation and browser E2E | Implemented locally; externally blocked live | Run real-provider evaluation only when explicitly configured, never synthesize provider success, and run actual local/live Chromium automation with revision-bound evidence. | The live runner enforces distinct delegated owner and reviewer object IDs. Only the owner/operator identity is currently available; no provider or authenticated dual-user Chromium pass is claimed. | Supply a second delegated Entra user with `workflow.read workflow.approve` and `Workflow.Approver`, consented for the API, plus an authenticated browser state. |
| Hosted failure injection and ORS | Partially passed; remaining cases blocked | Observe ORS-001–009 and all bounded synthetic failure/recovery cases without hidden retry or duplicate effects; preserve unknown outcomes until authoritative reconciliation. | Live Azure passed ORS-001, ORS-004, ORS-006, ORS-007, every ORS-008 variant, and the ORS-009 owner authorization negative (HTTP 403, pending, one denial, no effect). Successful hosted cases exposed a normalization defect because `hosted_workflow_finished` was not counted as terminal; the corrected query and hosted idempotency regression require one terminal event. ORS-002, ORS-003, ORS-005, approval/rejection, and decision/restart crash windows remain blocked by the missing distinct reviewer. | Deploy the exact fix, rerun ORS-001/004 terminal checks, then execute the reviewer-dependent matrix when the delegated prerequisite exists. |
| Independent release readiness | Blocked | Preserve immutable implementation/Azure runtime evidence as `passed`, `failed`, `blocked`, or `unverified`; bind cloud evidence to exact source/deployment revisions; keep the release manifest diagnostic and non-authorizing. | A full infrastructure replay exposed that optional Bicep image defaults could create placeholder latest revisions and move single-revision traffic away from healthy immutable applications. Image parameters are now required; the deployment script preserves existing digest-pinned images, permits placeholders only before any immutable revision exists, and fails closed if a placeholder template coexists with immutable history. Bicep and all 17 infrastructure contracts pass locally. No deployment of this guard is yet claimed. | Obtain green exact-head CI, run a provider what-if proving the immutable images remain unchanged, then use the bounded app/hosted deployment path; retain the PostgreSQL public rule until replacement egress is validated and do not merge PR #49. |
