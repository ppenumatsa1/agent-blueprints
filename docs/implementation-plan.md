# Phased implementation plan

## Phase 0: foundation

The [foundation PR](https://github.com/ppenumatsa1/agent-blueprints/pull/1)
established the architecture, reference analysis, catalog, engineering
standards, initial contracts, and GitHub-hosted validation under the MIT
License. The [follow-up](https://github.com/ppenumatsa1/agent-blueprints/pull/2)
added profile-aware contracts, the supplied architecture source, and the
[living checklist](master-checklist.md).

The [cross-framework Order Resolution specification
proposal](order-resolution-specification-proposal.md) adds a documentation-only
business contract for triage, policy retrieval, deterministic resolution,
authorized approval/rejection, idempotency, crash/restart recovery, and
evaluations. Its versioned synthetic set covers automatic completion, approval,
rejection, duplicate commands, worker recovery, policy-evidence failures, and
authorization denial. It requires framework-native workflow/checkpoint
providers and keeps PostgreSQL application persistence separate; it does not
add a runtime, custom checkpointer, compatibility shim, or Azure resource.

Merged [PR #42](https://github.com/ppenumatsa1/agent-blueprints/pull/42)
adds the [executable acceptance fixture](../scenarios/order-resolution/README.md),
versions that contract as `order-resolution-spec/0.1.0`, and encodes exactly
`ORS-001` through `ORS-009`. Root tests enforce the exact synthetic policies,
decimal USD round-half-up refund amounts, approval/action/outcome expectations,
and explicit policy-evidence failures. Normalized `business_outcome`
assertions remain separate from framework-specific `technical_execution`
assertions. This is contract encoding, not implementation or readiness
evidence. Parallel workstreams B, C, and D depend on this contract and must not
redefine its normalized facts or outcomes.

Merged [PR #44](https://github.com/ppenumatsa1/agent-blueprints/pull/44)
adds one explicit `order-resolution` generation profile to the existing safe
copy generator. Default generation remains unchanged. The generated project
owns its FastAPI/React/PostgreSQL/Compose application, deterministic policy
rules, database-only synthetic action, native MAF `Executor` and
`WorkflowBuilder`, host-selected file checkpoints, tests, locks, and copied
acceptance assets. A fresh external generation passed 117 inherited and
profile backend tests on PostgreSQL 17; those tests executed `ORS-001` as one
automatic `USD 7.90` action, `ORS-002` as a native pause followed by one
authorized `USD 18.50` action, and `ORS-006` as a persisted fail-closed case
with no checkpoint, decision, action claim, or effect. Generated frontend
tests/build/CSP checks and a standalone Compose root/health/auth boundary also
passed locally. These results are implementation evidence, not full nine-case,
hosted, remote-effect, evaluation, or production-readiness evidence.

Merged [PR #41](https://github.com/ppenumatsa1/agent-blueprints/pull/41)
integrates application-owned PostgreSQL requests, proposals, atomic decisions,
effects, audit records, synthetic downstream reconciliation, and an explicit
profile migration into that generated application. Effect identity includes
case, proposal version, action, and destination. Process tests cover termination
around decision persistence and effect send; timeout-after-send remains unknown
until authoritative observation. The generated runtime adapter executes
`ORS-001` through `ORS-009` while keeping normalized business outcomes separate
from API, native-checkpoint, and PostgreSQL execution evidence. Native MAF
continues to own checkpoint bytes. Real downstream guarantees remain unverified
and blocked by #32.
A fresh external generation passed 136 backend tests, 10 frontend tests plus
build/CSP, all nine canonical scenarios without skips, 20 repeated concurrent
duplicate-request runs, source-independence checks, and Compose root
`200`/health `204`/protected API `401`. Exact-head CI and independent review
remain required before merge consideration.

Draft [PR #43](https://github.com/ppenumatsa1/agent-blueprints/pull/43)
integrates the versioned evaluation dataset, native MAF local deterministic
checks, merged #39 result normalization, and a generated evidence producer.
A fresh external generation passed 147 backend tests, all nine canonical
scenarios without skips, 10 frontend tests plus production build/CSP, and
Compose root `200`/health `204`/protected API `401`. The evidence producer
reported every scenario plus deterministic technical and business evaluation
as `passed`; the independent validator correctly retained an `unverified`
gate because no trusted producer attestation exists. Real provider/model
quality, actual browser evidence, and trusted provenance remain unverified,
and release/deployment remains blocked.

**Milestone decision:** READY for the local MAF software-factory milestone;
NOT READY for production, release, or deployment.

## Azure/Foundry Workstream C

Workstream C composes the generated FastAPI application with either the
existing native local host or Agent A's API-only native Responses bridge copied
into the generated backend. The API image does not import the sibling hosted
runtime or hosting SDK, and hosted composition fails closed when the bridge is
absent. The
application owns end-user authentication/authorization and PostgreSQL
business state; Agent A owns hosted execution identity and checkpoint/session
state. The API UAMI is the sole PostgreSQL runtime principal and is never
treated as the user. The hosted identity calls only the protected internal API
with the fixed `Hosted.Workflow.Invoke` app role and receives no database
configuration. PostgreSQL-only synthetic effects use a distinct application
tool identity and retain proposal/action/destination/digest binding.

Implementation acceptance criteria:

- explicit host selection with no local fallback from hosted errors;
- validated end-user tenant, issuer, audience, subject, scopes/roles,
  ownership, reviewer authorization, and stale/conflicting decisions;
- claim-before-send and authoritative status reconciliation for ambiguous
  hosted acknowledgments, without replay;
- app-only tenant/issuer/audience/principal/role validation on
  `/api/internal/hosted/v1`, case-bound conversation/channel checks,
  and durable idempotency-key conflict detection;
- authenticated-human start/resume prebinding before Responses dispatch,
  verification-only service-MI binding routes, and a hashed expiring decision
  intent that the hosted callback must match before recording a decision;
- opaque platform user/session/call correlation that cannot grant human
  authority, with current durable binding reauthorization on every
  verification request and platform call IDs excluded from business-operation
  digests;
- exact post-terminal human decision retries that reauthorize the reviewer,
  conversation, channel, intent, and command, then return Agent A's recorded
  Responses result without redispatch or another effect;
- explicit migrations, startup schema validation, runtime/admin identity
  separation, TLS verification, bounded pools, and managed-identity or secret
  authentication;
- unchanged frontend/API and ORS-001..009 contracts, atomic stores and effect
  ledger, and no duplicate synthetic effects; and
- local PostgreSQL/native Responses-wire tests plus generated-project and
  frontend checks.

The Agent A integration additionally uses `HttpHostedBusinessStore` for
case-bound prepare/claim/effect/finish calls and C's
`PostgresOperationJournal` beside `ResponsesClient`. These seams persist
business approval state and opaque correlation only; they never fabricate
local checkpoint IDs, expose PostgreSQL to the hosted runtime, or store
Foundry checkpoint bytes. The API-side `PostgresHostedAuthorityBindings`
adapter never derives user authority from opaque hosted correlation or case
fields.

Current local evidence satisfies those implementation criteria and is detailed
in [application security](azure-foundry/application-security.md) and draft PR
[#48](https://github.com/ppenumatsa1/agent-blueprints/pull/48). OBO is not
required because no verified user-delegated downstream operation exists.
Remaining work is integration review, exact-head CI, Agent A contract
confirmation, Agent B output binding, and live Azure/Foundry/PostgreSQL
verification. This workstream does not provision, deploy, merge, or close
production-readiness issues.

## Azure/Foundry Workstream B

Workstream B prepares, but does not execute, the Azure deployment path. Its
source of truth is [`.azure/deployment-plan.md`](../.azure/deployment-plan.md),
with the detailed inventory, regional evidence, cost assumptions, role matrix,
operations, and cross-workstream outputs in
[`docs/azure-foundry/infrastructure.md`](azure-foundry/infrastructure.md).

The selected single region is East US 2. The model contract is
`gpt-4.1-mini` version `2025-04-14`, `GlobalStandard`, capacity 10. The
subscription and platform checks found sufficient capacity, but Standard
`gpt-4.1-mini` quota is exhausted and is rejected. East US and Central US are
reviewed fallbacks only; failure in East US 2 stops the deployment and
requires a complete fallback-region recheck rather than silent resource
splitting.

The implementation provides modular Foundry/model, identity/RBAC,
observability, ACR, Container Apps, Key Vault, and PostgreSQL Bicep; root azd
orchestration; guarded preflight, what-if, deploy, database configuration,
migration, health, rollback, and teardown scripts; and non-deploying contract
tests. Hosted agent code deployment remains owned by Agent A and intentionally
has no ACR dependency. The API/frontend ACR is retained for Container Apps
remote builds.

Deployment-time Entra automation idempotently creates or reuses the authorized
single-tenant API/SPA registrations, exposes only the three workflow scopes,
defines user/approver roles, and creates no secret or test user. Live app
deployment remains fail-closed until Agents A/C implement renewable
managed-identity PostgreSQL authentication, hosted workflow selection, and the
deployed frontend proxy target.

**Acceptance evidence:** exact base verified; read-only Azure discovery
completed; Bicep build/lint and 8 infrastructure contracts pass; 68 root tests
pass with two expected adapter-selection skips; script syntax checks pass.
The current Azure CLI identity matches the authorized target, but azd is a
different account and tenant. All mutation paths fail closed until both
identities match. No Azure mutation or deployment has occurred.

**Next action:** independent validation on the draft PR, then an approved
what-if after azd reauthentication. Deployment remains outside this PR.

Specification Studio has not yet produced an artifact, so the proposed
handoff is not an end-to-end compatibility claim. Phase 0 does not implement
the validator or an agent template, integrate Specification Studio, deploy
Azure resources, or establish production/customer approval.

## Phase 1: MAF workflow golden path

**Goal:** a reusable, independently runnable MAF workflow blueprint and an
independently buildable generated project, with durable human approval and
recovery and an independent Verification/Readiness Validator. Start locally
with FastAPI, React, PostgreSQL, Docker Compose, tests, and evaluations.
Business logic is supplied by the generated application; order adjustment is
only a synthetic test fixture. The primary deployment targets a Foundry
Hosted Agent for the native workflow, with separate Azure Container Apps
(ACA) for the UI and API. Hosting the workflow itself in ACA is a deferred
alternative, not a verified fallback.

The local workflow uses MAF-native file checkpoints on a persistent single-host
volume, separate from PostgreSQL business state and approval records. A future
Foundry host owns its managed checkpoint provider; the adapter and hosted
pause/resume validation are P1-12, not local durability evidence. Interactive
sign-in uses Entra ID and existing registrations, while isolated automated
tests may use synthetic identities. Azure provisioning requires explicit
approval of the resource inventory, estimated cost, and deployment plan.

### Reconciled gaps and sequencing

The engineering foundation and [integrated review #17](https://github.com/ppenumatsa1/agent-blueprints/pull/17)
are not proof of completed hosted or deployment capabilities. Track the
remaining acceptance criteria, dependencies and evidence in these issues:

- Hosted security and durability: [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22),
  [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19),
  [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20), and
  [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32).
- Reusable MAF extension contracts (P1): [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35)
  covers typed model, agent, prompt, tool/authorization, and executor/workflow
  patterns, demonstrated in a generated synthetic application.
- Independent trust and evaluation: [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21)
  and [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25).
- Azure, data, telemetry and identity: [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18),
  [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24),
  [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26),
  [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27), and
  [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28).
- Developer experience and demonstration: [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23)
  and [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29).
- P1 permanent standalone reference application: [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30)
  is required but requires separate repository authorization.
- Reusable MAF extensions and PostgreSQL readiness: [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35)
  and [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38).
- Separately scoped/future work: [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31),
  [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33), and
  [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34).

Merged PR [#40](https://github.com/ppenumatsa1/agent-blueprints/pull/40)
adds the standardized Order Resolution specification. Its focused executable
fixture remains separate from the current blueprint runtime and from the
legacy order-adjustment scenario. A framework mapping must consume the
normalized fixture and add native checkpoint/execution evidence rather than
redefining the business contract.

Hosted recovery remains explicitly deferred, not waived. Azure deployment
requires the implemented and independently verified offline prerequisites,
separately approved subscription access, and approval of the concrete
deployment plan. Read-only subscription and resource-group listing succeeded;
this is not evidence of deployment write access or application/service
connectivity. Its live checks provide evidence to close the related hosted and
operational issues.
Do not merge overlapping workstream histories blindly or treat a green
engineering check as release authorization.
The dated [issue and fix journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---issue-and-fix-status)
summarizes open PR evidence, unresolved issues and the review sequence. Its
draft work is not represented as merged functionality on this branch.

The #35 extension workstream keeps only seams that add application-owned
configuration or policy beyond MAF's native APIs. `ModelSelection` is a small
validated provider/model configuration value; the application constructs the
selected `SupportsChatGetResponse` client and passes it directly to MAF
`Agent`. `PromptAsset` supplies an explicit file version and source-byte digest
because MAF accepts instructions but does not manage versioned prompt files.
The example uses MAF's native `Agent` and `@tool` APIs directly; only the
request-scoped `ToolAuthorization` protocol remains application-owned, since
MAF tool registration is not business authorization. No generic
`ModelClientFactory`, `AgentDefinition`, `build_chat_agent`, or `ToolRegistry`
is needed. The workflow continues to use the host's `WorkflowFactory`,
framework-native `Executor`/`WorkflowBuilder`, and host-provided
`FileCheckpointStorage`.

The pinned `foundry-public` source at
[`4543075`](https://github.com/ppenumatsa1/maf-monorepo/tree/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/underwriting/foundry-public/backend)
likewise constructs its provider client in application code and builds
concrete MAF executors with `WorkflowBuilder`. Its client fallback is not
copied: unavailable model calls must not silently produce synthetic output.
The evaluation extension does not duplicate MAF's native `Evaluator`,
`LocalEvaluator`, `@evaluator`, or `evaluate_agent()` APIs. Applications use
the standard framework path and may pass its results to app-owned readiness
normalization.

The generated synthetic fixture tests provider selection, explicit versioned
prompt loading, native agent/tool composition, affirmative authorization,
approval/rejection and restart/crash recovery without invoking a real model.
The fixture tool is read-only. Arbitrary trusted Python callbacks remain
unsandboxed, so the absolute extension non-bypass criterion is unverified.
Consequential remote effects remain blocked by #32; hosted identity,
checkpoints and recovery (#19/#20/#22) and trusted readiness evidence (#21)
remain unverified. Do not mark #35 or hosted capabilities complete beyond the
evidence on the current draft PR.

The #25 follow-on retains only typed application-owned evaluation datasets,
rubric criteria with explicit thresholds, readiness-check identity validation,
and normalization of standard MAF evaluation results. Applications invoke
native MAF evaluation APIs directly; this extension adds no evaluator protocol
or orchestration wrapper. Callers supply unique IDs from the selected
readiness contract to validation and mapping; these are a consistency input,
not trusted authorization. Matching but unknown dataset/rubric IDs reject
before native evaluator invocation. Oversized integer thresholds reject and
oversized observation scores fail closed. Missing observations and unavailable
native results remain unverified; failed, malformed, unknown, or duplicate
observations cannot pass. Provider/tool errors propagate through the standard
framework path. Source and generated tests exercise MAF's native local
evaluator with explicitly synthetic responses, not live model quality. No
actual model or browser evidence, independent trust/provenance, or hosted
validation is claimed.
The stacked #37 base `0772af8c9ee0e5f765040f4d20ceab9962948c0d` passed all six
exact-head CI jobs in run [45031304964](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45031304964).
This only verifies #37's extension foundation; it does not establish real
evaluation, browser evidence, trust, or hosted readiness. PR #39's previous
head-specific CI is historical and does not validate this integration. On the
local integration tree, source and independently generated backends each passed
93 tests, both Ruff checks passed, the generated verifier passed 44 tests
without skips, and the root verifier passed 56 tests with one expected
`adapter-not-selected` skip. The pinned `agent-framework-core==1.26.0` wheel
matched the approved SHA-256 `175b75f07e15d1bb7b6cea9cb35b965ac2528cd96e3eae8f791c85c48c7232b3`.
These results correspond to implementation commit
`1724f3ef9bfdb7af07c575697cc1d0cd7b5d5af2`, whose exact-head Actions run
[45033947068](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45033947068)
passed all six jobs. This validates the evaluation implementation, not live
evaluation, browser evidence, trust, or hosted readiness. Subsequent
documentation-only commits require their own exact-head CI.

### Execution sequence and work packages

The modularity foundation reorganizes the local blueprint and generated
copies into sibling backend/frontend contexts and separates backend
responsibilities using canonical imports and no compatibility aliases. Acceptance
requires source and generated security/recovery tests, both crash windows,
independent golden verification and exact contract bytes, credential-free
CI and Compose smoke checks. Local evidence is recorded in the
[checklist](master-checklist.md). [PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11)
merged into `main` as `de1cbe4`; its security-hardened head is
`587e6cc1abc23a67845c8193d486cc65c8b52854`. Foundation commit `9efeef0`
removes compatibility aliases and corrects checkpoint selection. Its
[hosted run 44936094798](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936094798)
passed all five checks on that exact commit. An intermittent local restore
failure occurred during migration testing; a deterministic equal-timestamp
reproduction showed a real selection defect but does not prove the
unretained original failure had the same cause. The foundation selects
MAF-native persisted checkpoints and rejects incomplete terminal state on
completion and replay. Local source/generated backend suites passed 36 tests
each; the selected-adapter root suite passed 46 and the generated verifier
passed 44 without skips. Reconcile dependent PRs and verify the combined
revision separately. Hosted checks do not prove live hosting.
An independent CI regression exposed that the generated-verifier command's
failure could be masked by `tee`. The workflow now propagates pipeline
failures and the [regression test](../tests/test_ci_workflow.py) exercises
failure, skip and success behavior. Prior CI job status alone is not proof
that the verifier passed; logs for the prior PR heads recorded 44 tests and
`OK`. [Run 44939172266](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44939172266)
passed all five jobs for foundation head `d0e1727`. The dependent PRs had
separate successful head-specific runs, which are not evidence for the
reconciled tree.
PR #17 is merged into `main` at
`0c1297cc8e93c62f69d61d0eb3bdabf3c27c683d`; exact-main
[run 45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271)
passed all six jobs for that baseline. PRs #36, #37 and #40 are now merged
into current `main` at `49932ee0cd61ee653a5f86be0f43873cec197ff9`; exact-main
run [45041465032](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45041465032)
passed all six jobs. PR #39 is being reconciled directly onto this main
revision without replaying #37. Earlier PR #17 commit and merge-ref results
below are historical snapshots and do not replace current-base validation. Local
validation and network/harness caveats are recorded in the
[integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---main-reconciliation-and-local-validation).
The [targeted MAF supply-chain audit](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---targeted-maf-supply-chain-audit)
distinguishes the approved `agent-framework-core==1.26.0` dependency from the
compromised `agent-framework` umbrella releases. Source and generated installs
must reject the umbrella distribution and verify the approved core wheel hash
against the canonical `uv.lock` before locked installation.
The copied evidence producer observed approval and recovery passing while
explanation and browser hint remained unverified; the independent unsigned
readiness report remained unverified. The first local container build could
not reach the public Python package host; a retry using the operator-approved
package proxies built and passed the generated Compose smoke checks.
Independent workstreams cover locked tooling, migrations, observability,
Foundry hosting, infrastructure and integration evidence. Do not merge PRs
without approval. Azure deployment is a deliverable but requires prior
approval of its resource inventory, estimated cost and deployment plan;
permanent reference repository creation requires separate approval. As of
2026-11-21, locked tooling is proposed in open
[PR #13](https://github.com/ppenumatsa1/agent-blueprints/pull/13), currently
at `7325765cbbfb809e2064ec0e78a5567b465e3621`. Actions run
[44947297321](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44947297321)
passed all five jobs on that exact head. The owner reports a headless
generated-project debugpy/DAP smoke using `.vscode/launch.json`'s
`Backend: FastAPI` configuration: execution stopped at `health.py:9`, the
stack was inspected, and continuing returned HTTP 204 with exit code 0;
temporary resources were cleaned. The report did not identify an immutable
revision. It does not verify the interactive VS Code UI, Restricted Mode, or
macOS.

Earlier, the owner reported Windows/Linux Compose verification using an
approved mirror after public TLS failures and could not run uv in a separate
validation environment. PR #13's previous reported head was
`b78634b3b746c7adbf5f8500e4b7023c96c67963`; its
[run 44928260607](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44928260607)
passed five checks for prior exact revision
`e1d953662e615e547fa641ad0831907c363318e3` only. The integrated tooling
revision is `543b137a432ca054920d629b943fc42a729df676`; its
[run 44937692067](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44937692067)
passed five checks for that exact head, not the combined PR #17 tree. None of
these results establishes that tooling is merged or validates this branch,
interactive debugging, Restricted Mode, or macOS.

For PR #16, the owner reports guarded Alembic adoption only after exact
baseline-manifest validation and checking that no later-revision-owned tables
exist; fresh databases run revision `0001`, and validation never stamps.
Source/generated suites each passed 48 tests on PostgreSQL 16.15 and 17.12;
the root suite passed 47 with one expected adapter-not-selected skip. Run
44944613749 passed five jobs for `897aae8` against `d0e1727`, but is stale
relative to foundation head `8144918`; reconcile and rerun before relying
on this evidence. Follow-up commit `ce86252324dca041fd5430602a3fc2c28a355274`
was reported to pass 12 focused migration regressions on isolated PostgreSQL
17 and Ruff 0.14.13 checks. It is local integration evidence, not final
combined CI; reconcile ancestry and validate the combined revision.
The owner later reported merge commit
`d1251352835c2d02e91690104b4dcabf465f5f05` with parents `897aae8` and
foundation `8144918`; its generated instantiation/link check, root suite
(47 passed, one expected skip), and all five Actions jobs in run 44947337144
passed. This is PR #16-specific and does not verify PR #17's combined tree.

Each PR must remove obsolete compatibility layers, use direct imports,
update affected `docs/design` specifications and the cumulative engineering
journal, and record actual regression, security, durability, independent
verification and CI outcomes for its final revision. PR #12 is deepening the
six generated-project guides and eight documents under
`blueprints/maf/workflow/docs/design/`; these documents must evolve alongside
implementation, remain in generated applications, and use actual
source/configuration references, meaningful Mermaid diagrams, and accurate
implemented/planned labels. An earlier documentation working tree passed three focused
instantiation and generated-verifier pipeline tests. PR #11 is now pushed at
`44ee18b886d409b0b59cf6df6b4893917370307d`. Its canonical source separates
`composition.py`, `api/app.py`, route handlers, schemas, dependencies,
errors, middleware, and `lifecycle.py`; the current PR #12 source-map links
now point to these exact paths. The owner reports 37 backend tests passed.
Actions run 44944929394 completed with four jobs passing and `contracts`
failing on the stale `specs.md` API link; the root suite had 47 tests, one
failure from that link, and one expected adapter-not-selected skip. Rebase
onto the new head and rerun root/contracts before final PR validation. The
coordinator reports the minimal link correction was then pushed at
`814491811eac457826108b70fc213fdc564af0e5`; root tests passed 47/47 and
Actions run
[44945419570](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44945419570)
passed all five jobs on that exact head, including generated checks without
skips. PR #12 is rebased onto that tip; its isolated root suite passed 47
tests with one expected adapter-not-selected skip, including generated
copy/link and verifier-pipeline tests, and `git diff --check` passed. Actual
head run
[44946550709](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44946550709)
passed all five jobs on exact head
`c247bf737acabe47e7af0023eaebf69c0b393fdf`. Hosted checks for this combined
PR #17 revision remain to be run.
Maintain the
engineering journal without inventing historical findings. For each meaningful PR update
this plan, `docs/master-checklist.md`, and relevant architecture documentation
with acceptance criteria, evidence, status, and next action.

### Cross-cutting PR acceptance gates

Before any PR is ready for approval, keep one canonical implementation and
use direct imports. Remove compatibility shims, forwarding modules, legacy
import aliases, obsolete directories, duplicate code, unused dependencies,
and stale configuration; backward compatibility with prior internal
implementations is not required for this greenfield blueprint. Update
dependent call sites, tests, Dockerfiles/build contexts, CI, documentation,
and instantiation scripts in the same coherent change while preserving
functional behavior and verification contracts.

Before requesting approval, run applicable regression, security, durability,
and independent verification tests; do not weaken or relabel failed or
unverified checks. Confirm GitHub Actions for the actual PR head revision.
Live Entra/OBO, Foundry-hosted recovery, cloud telemetry, and Azure deployment
remain unverified until separately implemented and evidenced. Azure
provisioning and permanent repository creation still require separate
authorization; never merge automatically.

The dependent developer-tooling branch adds `backend/pyproject.toml` and a
public-registry `uv.lock`, locked development and container installs, Ruff,
portable development commands and VS Code configurations. Acceptance requires
source and generated lint/tests and locked builds without Azure credentials,
then passing hosted CI on the actual reviewed head. Local Windows source and
generated backend tests, Ruff, generated UI tests/build and Linux Compose
204/401 smoke passed using an approved temporary mirror after public artifact
downloads failed locally with a TLS handshake error. On foundation `9efeef0`,
source and generated backend suites passed 36 tests each, independent
verification passed 44 without skips, generated frontend passed 8 tests/build/
CSP, and Ruff passed in both backends. Hosted run
[44940616666](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44940616666)
passed all five jobs for PR head `b78634b`, not for any combined revision.
macOS, interactive debugging and a clean public-only local installation
remain unverified. Next verify integrated work and review the separate PRs.

The migration workstream, based on `modularity-foundation`, adds Alembic
baseline `0001`, per-revision catalog manifests, an explicit schema-owner
upgrade and read-only startup validation. Local PostgreSQL 17 evidence:
12 migration tests including a test-only second revision, 43 source and 43
generated backend tests, 44 generated verifier tests, and two generator tests
after rebasing; source and generated Compose smokes each returned UI 200,
health 204 and protected API 401. The
[migration tests](../blueprints/maf/workflow/backend/tests/test_migrations.py),
[operations guide](../blueprints/maf/workflow/README.md#business-database-migrations)
and [journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md) record
the acceptance evidence and limitations. Two later local evidence runs failed;
their subprocess stderr was not retained. An independently reproduced native
checkpoint timestamp-tie defect was fixed in foundation `9efeef0`, whose
[CI run](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936094798)
passed all five jobs. The original failures' causes remain unproven. Local
PostgreSQL 16.15 migration tests passed at `031fdb4`, after an initial
auxiliary readiness probe failed before tests.
At `7cd99ac`, local source and independently generated backend suites passed
48 tests each on both PostgreSQL 16.15 and 17.12; the generated verifier
passed 44 and generator tests passed two. The generated evidence producer
passed approval/recovery observations but left explanation/hint unverified;
the independent unsigned readiness report remained unverified.
[PR #16](https://github.com/ppenumatsa1/agent-blueprints/pull/16) remains open;
[run 44940559106](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44940559106)
passed all five jobs for head `eb898f6`, not on the combined
revision. Next verify the integrated revision; live backup/restore remains
unverified.

P1-14 now has a staged, independently copied
[Foundry-first resource graph](../blueprints/maf/workflow/infra/README.md)
and offline compiler/configuration tests. Optional model, project-wide API
agent-consumer grant, registry and API/UI services default off; the remaining
resources would still incur cost. Foundry and monitoring private connectivity,
PostgreSQL Entra token use, API/UI binding and the hosted-agent contract are
not implemented or verified. Source and independent generated static checks
and nine infrastructure security/configuration tests per copy passed locally
on the rebased working tree; two instantiation tests also passed.
[PR #15](https://github.com/ppenumatsa1/agent-blueprints/pull/15)
[run 44939817209](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44939817209)
passed all six jobs for head `2023e16`. Follow with separately authorized
network, identity, cost and deployment review; no cloud mutation has occurred.

The staged PostgreSQL server selects 16 while Compose uses 17. The pinned
API's documented enum and examples
conflict, and the compiler accepts arbitrary version strings; neither resolves
17 support for that API. The [version-gap review](../blueprints/maf/workflow/infra/README.md#open-postgresql-version-gap)
records a newer API as an unverified candidate. Separately, migration revision
`031fdb440908092cf09801232fe7f5d15048f065` passed 12 migration tests on local
PostgreSQL 16.15 after an initial auxiliary locale probe failed and was
corrected. The integration worktree combines the migrations and infrastructure,
but that result belongs to the separate migration revision. Resolve the target
major before deployment; local evidence does not prove Azure compatibility or
safe downgrade.

The local combined code revision `af3955a85036d3a6a01465648437a184a790309c`
passed 68 source and 68 generated backend tests on each of PostgreSQL 16.15
and 17.12, 47 selected-adapter root tests, 44 generated verification tests
without skips, Ruff, frontend tests/build/CSP, offline IaC checks, and source
and generated Compose smoke. Its unsigned readiness report remained
unverified. The [integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---combined-engineering-layer-integration)
records failed attempts and limitations. Exact final combined-revision CI
and review are still required; none of these open PRs has been merged.

P1-01 through P1-04 have an initial local foundation and a test-only
application adapter, but the scenario has no authorized contract approval.
Trusted result production and repository protection remain unverified. The
blueprint work follows the foundation in smaller reviewable changes. See the
[checklist](master-checklist.md) for status and evidence.

The [first blueprint increment](https://github.com/ppenumatsa1/agent-blueprints/pull/6)
contains a native MAF approval workflow, an explicit local host, PostgreSQL
decision/audit/action records, and integration tests including both
process-kill recovery windows. [Draft PR #8](https://github.com/ppenumatsa1/agent-blueprints/pull/8)
adds an Entra-secured API, MSAL UI, explicit synthetic application, and locally
smoke-tested Compose stack. A separate stacked increment adds a generator,
test-only golden adapter, fixture-specific evidence producer, and generated
project CI. It does not establish independently trusted result provenance,
live Entra/OBO, agent-generated explanation evaluation, browser hint
end-to-end behavior, or hosted recovery. A temporary generated copy passed
31 backend, 44 verification, and 8 frontend tests; its Compose stack passed
the local HTTP smoke check. Its unsigned readiness report is unverified.

| ID | Bounded work package | Dependencies | Independently verifiable outcome |
| --- | --- | --- | --- |
| P1-01 | Define the synthetic scenario, golden acceptance tests, and contract; obtain authorized approval. | None | [Scenario, golden cases, and test-only adapter](../scenarios/order-adjustment/README.md) exist; independent authorized approval remains outstanding. |
| P1-02 | Define normalized result, evidence, baseline, and signed-decision inputs; map actual runner output. | P1-01 | The [synthetic runner](../blueprints/maf/workflow/backend/tests/evidence_runner.py) records actual observations; independent result attestation remains outstanding. |
| P1-03 | Implement local traceability, evidence integrity, freshness, decisions, and profile gates. | P1-02 | [Validator](../readiness/validator.py) and [acceptance tests](../tests/test_readiness.py) exercise the policy; actual trust and provenance require independent administration. |
| P1-04 | Expose the validator as a local CLI with a machine-readable report. | P1-03 | [CLI](../readiness/__main__.py) and [usage](readiness-validator.md) preserve outcomes and disclose unapproved inputs. |
| P1-05 | Create a self-contained blueprint with the local React, FastAPI, PostgreSQL, and Docker Compose stack. | P1-01 interfaces | The stack starts; one temporary generated project builds, runs, tests, and verifies independently. Automated tests need no Azure credentials; interactive sign-in requires existing Entra configuration. |
| P1-05 readiness | Avoid the transient socket-only initialization race in source/generated CI and Compose. | P1-05 | [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38) records socket-ready/TCP-unready observations on PostgreSQL 16.15 and 17, an initial `createdb` failure, and a 72/72 source/generated retry on historical head `8b3c357`. Both CI waits and the Compose health check use bounded loopback TCP readiness. Verify the resulting exact head and generated Compose; managed PostgreSQL remains unverified. |
| P1-06 | Implement PostgreSQL business records, approval/audit state, and an idempotent action ledger for effects inside the same transaction. | P1-01, P1-05 interfaces | Real restart tests cover crashes after decision persistence and after action commit, with no unauthorized or duplicate database actions. Consequential remote effects are separately P0-blocked by [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32). |
| P1-07 | Implement typed FastAPI operations with Entra token validation, authorization, approvals, and optional OBO. | P1-01, P1-06 interfaces | Positive and negative tests cover scopes, roles, identity isolation, malformed and replayed requests; synthetic identities exist only in isolated tests. |
| P1-08 | Implement an accessible MSAL React client for sign-in, submission, status, approval/rejection, and failure states. | P1-01, P1-07 API contract | UI tests cover visible states and safe retries; browser code contains no service secrets. |
| P1-09 | Implement a native MAF workflow with local file checkpoints, isolated pause/resume, rejection, and recovery. | P1-01, P1-06 interfaces | Local tests cover repeated decisions, concurrent requests, and recovery without a universal orchestration wrapper; Foundry hosting is deferred to P1-12. |
| P1-10 | Add integration/E2E tests, synthetic agent evaluations, and GitHub Actions; connect actual results and artifacts to the validator. | P1-04 through P1-09 | Draft #43 generates revision-bound Order Resolution case, evaluation, matrix, input, and validator artifacts from the real generated adapter. All nine deterministic cases and separate business/technical checks pass locally; the independent report remains unverified without producer attestation. Real model and browser evidence remain outstanding. |
| P1-11 | Add privacy-safe logs, traces, correlation, and operational signals across API, workflow, approvals, and side effects. | P1-07, P1-09 interfaces | Manual telemetry tests cover redaction and correlation; owner-reported native global auto-instrumentation leaked a query canary and emitted duplicate FastAPI spans. Do not enable that path until exact-revision negative tests cover prompt/tool/identity and failure paths; hosted export remains environment-specific. |
| P1-15 | Demonstrate the local prototype from a synthetic specification through approval, evaluation, and its readiness report. | P1-10, P1-11 | Record the scenario, evidence, limitations, and observed elapsed time; the 2–3 hour objective is a target until a representative run demonstrates it. |
| P1-12 | Validate Foundry Hosted Agent compatibility for the selected MAF version, Responses protocol, request-aware workflow factory, identity, per-user session isolation, and host-managed checkpoints. | P1-09, P1-15 | Microsoft warns delegated users are not fenced from one another within a shared session. A trusted app must authorize each principal's session, verify mapping from the validated principal, map each authenticated caller to a distinct session, and reject unchecked client IDs; an opaque app-supplied `x-ms-user-identity` scoping value derived from that principal is not authorization. Platform-generated `x-agent-user-id` is a different header; do not assume their values match. Equivalence and binding to the validated principal are unsupported and unverified; this bridge and mapping are not implemented or tested. Local AgentServer Core 2.3.0/Responses 2.4.0 one-shot task IDs reran fresh after terminal completion and are not persistent deduplication; hosted semantics remain unknown. The exact `agent-framework-foundry-hosting==1.0.0b261112` source exposes `response_id` in the request-aware factory before checkpoint preparation/parsing/run claim, but this hook alone does not establish a safe owner-bound CAS claim, a reservation per continuation, pending-reply/action ordering, idempotent side effects, or same-response recovery. The scoping value is not a credential; hosted secret delivery/rotation and downstream OBO token lifecycle are not implemented, and end-user bearer/OBO tokens must not be persisted. Lost `response.id` recovery remains blocked; see the [investigation journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---hosted-caller-binding-and-lost-responses) and [session-isolation clarification](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---delegated-session-isolation-and-debugger-evidence). Local checks alone are not a hosted deployment. No Azure resources are provisioned. |
| P1-13 | Prepare the explicitly selected ACA fallback and a framework-compatible checkpoint strategy. | P1-09, P1-15 | Separate local/container recovery and idempotency checks pass; no claim that ACA shares Foundry checkpoint ownership or silently replaces a failed model call. |
| P1-14 | Prepare Bicep, least-privilege identities, authenticated public endpoints, GitHub-hosted CI, and deployment/handoff instructions. Deploy only after separate Azure authorization. | Offline: P1-10, P1-11, P1-12 design decisions; P1-13 only if selected. Live deployment supplies evidence for hosted/cloud issues and must not wait for all live-verification issues to be closed. | Exact PR #17 head `8b3c357` passed `maf-infrastructure` and generated infrastructure checks in run [44960731511](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44960731511); the staged graph is not wired or deployed. Track IaC wiring [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), managed PostgreSQL operations [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), and separately authorized live deployment [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28). |

### Current integrated review baseline and issue-linked backlog

The latest verified integrated snapshot is head
`8b3c3578f36c30f32f4539ef1d181e1ff3984ab4`, based on
`1e99e038dc31c0ae25e5ea7712030d204ee35bc0`. Run
[44960731511](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44960731511)
passed all six jobs. Merge ref
`2ab8f3c92ebde95aa5c0bfb2cd33b0e5ab558c52` had exact base/head parents and a
tree identical to the head (`304b2b02432bc8bf9a63b641c853e7f07467e860`).
Generated acceptance passed 44 tests without skips or expected failures.
Synthetic producer evidence remains limited: approval/recovery passed,
explanation/hint remain unverified, and the unsigned validator exited 1.
Any later tree or base change requires exact-head revalidation. Neither result
makes the blueprint, readiness report, or deployment complete. See the
[journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---integrated-gap-reconciliation-and-backlog).

| Work package | Open issue(s) and acceptance boundary |
| --- | --- |
| P1-01–03: authorized exact contract and independent trust/provenance | [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21); synthetic schemas and validator tests do not establish authorized approval or trust administration. |
| P0: consequential external side effects | [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32); the action ledger covers only effects in the same PostgreSQL transaction. Block consequential remote actions until service-specific authorization, downstream idempotency and authoritative reconciliation are independently verified; otherwise fail closed and use manual resolution. An outbox only persists intent; it cannot deduplicate an external effect after a lost acknowledgment. The opt-in [pattern](../blueprints/maf/workflow/backend/examples/external_effect_boundary.py) and [synthetic tests](../blueprints/maf/workflow/backend/tests/test_external_effect.py) cover exact-request authorization, a five-second downstream budget, conflicts, concurrency, timeouts, reconciliation and process death, not real services or hosted guarantees. Its case-level key represents one immutable action only; future proposal-version/action/target identity must follow merged #40. Independently verify generated revision and each integration's authorization, retention, timeout and reconciliation; keep #32 open. |
| P1-07–08: real identity and browser experience | [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27); interactive Entra/OBO, generated UI and accessibility remain unverified. |
| P1-09/P1-12: hosted MAF packaging and checkpoint integration | [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19); caller/session binding [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22); lost-response/effect recovery [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20). Hosted recovery was explicitly deferred; this is not a security waiver. |
| Typed MAF extensions | [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35), [merged PR #37](https://github.com/ppenumatsa1/agent-blueprints/pull/37); use validated model-selection configuration, explicitly versioned prompt assets, direct native MAF `Agent`, `@tool`, `Executor` and `WorkflowBuilder` composition, and request-scoped application authorization. The current #37 implementation was reconciled with merged #36/#40 behavior on main `49932ee0cd61ee653a5f86be0f43873cec197ff9`; exact-head CI and implementation evidence remain in its PR and merged records. The example requires affirmative `True` authorization. Arbitrary trusted Python callbacks remain unsandboxed, so absolute non-bypass is unverified. External effects remain blocked by [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32); hosted identity/recovery, trusted readiness and a live model response are not claimed. |
| P1-10: agent evaluation and browser-hint evidence | [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25); current synthetic producer leaves explanation and hint unverified. Applications invoke native MAF `Evaluator`, `LocalEvaluator`, `@evaluator`, and `evaluate_agent()` APIs. PR #39 adds only app-owned versioned datasets/rubrics, thresholds and readiness-check mapping/normalization; its synthetic local evaluation tests are not model-quality or browser evidence. Keep #25 open until actual evaluation evidence and independent provenance are available. |
| P1-11: privacy-safe cloud telemetry | [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26); native auto-instrumentation remains disabled after the query-canary leak and duplicate spans. |
| Developer experience | [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23); macOS, interactive debugging and Restricted Mode remain unverified. |
| P1-13: optional ACA workflow runtime | [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31); alternative remains unselected, not a silent fallback. |
| P1-14: Azure graph wiring, managed database operations, deployment | [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28); no Azure resource was provisioned. |
| P1-15: measured local demonstration | [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29); the 2–3 hour objective has not been measured. |
| Phase 0 Specification Studio handoff | [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33); no producer artifact or lossless adapter exists, and this does not authorize implementation. |
| P1 permanent standalone reference application | [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30); required as an independent deliverable, but repository creation still requires separate explicit authorization. |
| Later separate App/API blueprint roadmap | [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34); remains out of phase and requires separate authorization. |

### Azure/Foundry Workstream A

Agent A adds only the native hosted-runtime and lifecycle source boundary for
the independently generated Order Resolution application. Acceptance requires:

- exact public SDK pins and drift tests for the Responses host and
  `create_version_from_code`;
- a request-aware native workflow factory using Foundry-managed hosted
  checkpoints, never the API's local file store or a PostgreSQL workflow
  serializer;
- structured approval resume with application authorization, exact
  conversation/channel binding, and platform-managed session scope that never
  treats the API workload user as the human actor;
- an application-owned hosted business lifecycle that persists only opaque
  request correlation, decision, and completion while Foundry retains native
  checkpoint ownership;
- at-most-once-biased Responses and publish creates that preserve `unknown`
  after a lost acknowledgment, never resend a preexisting pending claim, bind
  the complete publication target/configuration identity, and require
  authoritative reconciliation;
- independent generator output plus focused hosted, local workflow and
  repository contract tests.

Implementation and current local evidence are recorded in the
  [hosting report](azure-foundry/hosting.md). On 2026-11-22, 40 generated hosted
  tests, 16 publisher/generator tests, Ruff, 39 focused generated PostgreSQL
  tests, ORS-001..009, and the 68-test repository contract suite (2 documented
  adapter skips) passed. Workstream C revision
  `60fd83fc05acc290aab3ed96f8f8c255e493d28d` passed a composed
  real-PostgreSQL protected-API business lifecycle and native
  `/conversations` plus `/responses` wire proof, including restart duplicate
  acknowledgment with zero replay, one decision/action, exact
  `OperationClaim(record, acquired)`, and null business checkpoint fields, but
  security review rejected that revision's creation of owner/reviewer bindings
  from opaque hosted caller input. A now binds human authority only to the
  authenticated case/conversation/channel command, treats platform user/session
  as separate opaque workload correlation, and omits caller-supplied
  `agent_session_id` so Foundry owns the stable conversation session. A exports
  the explicit `order_resolution_hosted.bridge:build_workflow_host`
  API-to-Responses factory; no generic `/runs` host is permitted. Final A/C
  compatibility remains blocked until a new C revision and composed
  absent/mismatched-binding plus normal API bridge tests pass. Agents B and D
  consume the explicit API-only runtime
  allowlist, atomic operation claim contract, and two-phase
  identity-then-active publication fields documented in the hosting report.
  Public hosted runtime never receives PostgreSQL connectivity; the protected
  API owns business persistence and database networking.
  This workstream does not provision Azure, assign roles, publish an agent, merge
  a pull request, or convert an unverified hosted capability to passing readiness.

### Validator acceptance contract

The validator consumes the approved, versioned verification contract; actual
normalized test/evaluation results; and supporting evidence artifacts. Its
assessment context supplies the target maturity, source revision, environment,
and assessment time. The first implementation reads bounded local artifacts,
not arbitrary remote URLs, and verifies their bytes and SHA-256 digests. It runs
locally or in CI with the generated project, not as a shared factory runtime.

It must verify the contract's exact byte digest against an authorized approval,
then account for every requirement and required check, matching reported IDs,
expected evidence types, results, revision, environment, and each check's
explicit freshness policy. Reject unknown or duplicate IDs, report missing
checks as unverified, and corroborate test outcomes with their actual result
artifacts. A failed check is **failed**; missing, stale, future-dated,
inaccessible, or mismatched evidence is **unverified**, never a passing check.
All blocking requirements must pass. Prototype readiness may still pass with
disclosed non-blocking failures or unknowns; production readiness additionally requires
verified, scoped, unexpired human risk acceptance for each such result.
Neither profile relabels failed or unverified outcomes.

Verify contract approval, applicability, classification changes, risk
acceptance, and customer decisions through an authorized human decision
mechanism, including scope, validity, and revocation; a name or approval
string alone is not authority. Compare changed critical/security-critical
classifications, removals, and applicability against the approved baseline and
require an explicit authorized decision for any downgrade. For production
and customer validation, enforce the declared security, integration,
operations, and evaluation domain coverage or a verified applicable
not-applicable decision. Missing production controls or unverifiable approval
cannot support a pass. Signed decisions and result attestations use an
independently administered, baseline-pinned trust store. Signatures establish
key possession, not human identity or actual execution; trust administration
and protected result production remain operator responsibilities.

For a valid contract and assessment context, write a machine-readable
readiness report even when checks fail or evidence is unverified. Exit zero
only for a passing report and nonzero otherwise. If the contract or assessment
context cannot be parsed or identified, emit a machine-readable diagnostic
and a nonzero exit rather than fabricating a schema-valid report. Tests must
cover missing or invalid contract approval, freshness boundaries,
revision/environment and digest mismatches, missing or duplicate IDs and
checks, critical downgrade attempts, failed tests, disclosed prototype
non-blocking failures, production risk acceptance with invalid scope or
expiry, missing production controls, unreviewed applicability, and missing or
rejected customer approval.

**Hosting constraint:** the Python Foundry hosting integration is documented as
prerelease. Establish package/protocol compatibility and the approval/resume
path before promising it. Foundry-managed checkpoints do not replace PostgreSQL
business state; ACA recovery requires separate evidence. Select a fallback
explicitly and never provision Azure resources without approval.

### P1-11 observability increment

The MAF backend now has manually instrumented request, workflow, database
operations and OBO boundaries, allowlisted JSON operational logs and optional
Azure Monitor trace and metric export. Missing or invalid hosted configuration
fails startup; subsequent export failures are signaled without changing workflow
outcomes. Metric dimensions are limited to operation/outcome and exemplars are
disabled. Span creation, metadata, context and closure failures are isolated
without retrying work or masking application exceptions; startup failures clean
up telemetry resources. Logger failures produce a fixed stderr-only failure
signal without payloads; a stderr write failure cannot change the workflow
result. Acceptance requires canary, correlation, injected SDK, logger and
export failure tests, credential-free generated-project CI, and no workflow
changes.
Evidence: [tests](../blueprints/maf/workflow/backend/tests/test_telemetry.py)
and [operational guidance](../blueprints/maf/workflow/README.md#operational-telemetry).
After reconciliation onto the checkpoint foundation, the source backend suite
passed 51 tests and the independent generated backend suite passed 56 tests
(including evidence-runner tests); the generated standalone verifier passed
44 tests and two instantiation tests passed. Recovery coverage includes tied
checkpoint selection, pending and terminal validation, and completed replay
rejection. Earlier Compose returned UI 200, health 204 and protected API 401
after an initial failed startup attempt. [PR #14](https://github.com/ppenumatsa1/agent-blueprints/pull/14)
head `8c643df` passed all five jobs in
[run 44938368000](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44938368000);
these checks do not prove cloud export or the combined revision.
This increment remains in progress pending review and real hosted
verification. Outbound/Foundry propagation, sampling,
retention, regional placement and access policy require separate validation.
The common design suite and engineering journal record the implementation and
limitations. The local integration tree combines the public locked telemetry
dependencies with tooling. Its source and generated backend suites passed 50
tests each, its generated verifier 44, and generation tests two; full Ruff
checks passed. Both backend images built with an approved mirror after public
Python TLS failures.
Revision `fe4550a` passed 50 source and 50 generated backend tests, the
44-test generated verifier, and two instantiation tests; changed Python files
passed Ruff with the tooling workstream's configuration. These historical
results are not combined-revision evidence. Hosted configuration and cloud
ingestion remain unverified. No Azure provisioning or ingestion is implied.

## API-boundary integration follow-up

The final PR #14 code from `3aa389f` is reconciled with migrations and the
canonical dependency lock. All 23 focused privacy regressions passed locally;
native automatic instrumentation remains disabled following the measured
query-canary leak. Complete source/generated and final-revision CI checks
before review; hosted caller binding and lost-response recovery remain blocked.

The PR #11 API split and source-map fix are being reconciled with integrated
telemetry rather than replaying earlier workstream history. The
[integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---reconcile-api-boundaries-with-integration-telemetry)
records focused local evidence and limitations. Acceptance still requires the
remaining workstream changes and source/generated checks on the final combined
revision; earlier runs do not establish that result.

The exact PR #16 delta `897aae8` adopts a validated existing baseline through
Alembic `stamp` inside the existing transaction; fresh schemas still execute
the baseline revision. Its 12 migration regressions passed locally on isolated
PostgreSQL 17 after restoring cached HTTP test dependencies, and locked-version
Ruff checks passed. This focused result is not final combined verification.
The design-document owner will consolidate the engineering journal.

## Later phases

| Phase | Scope and dependency |
| --- | --- |
| 2 | MAF harness and a Foundry Project SDK agent; choose prompt versus application-owned runtime explicitly and preserve application-controlled authority. Builds on Phase 1 contracts and evidence. |
| 3 | LangGraph workflow with native graph state, interrupt/resume, framework-specific checkpointing, and the same independent project/security expectations. |
| 4 | Deep Agents harness, with its own supported tools, hosting protocol, state boundaries, and evidence. |
| 5 | GitHub Copilot SDK harness, retaining the SDK-managed loop, explicit permissions, and independently verified hosting compatibility. |
| 6 | Specification Studio contract handoff and project generation, after the schemas and selected blueprints have been validated; generated applications remain independently deployable. |

App/API Blueprints and Specification Studio are separate future repositories.
Private networking and self-hosted runners are deferred work, not assumed
prerequisites for Phase 1. Each phase requires its own approval, implementation,
and evidence; this plan does not authorize deployment or create those
repositories.
