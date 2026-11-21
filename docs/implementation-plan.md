# Phased implementation plan

## Phase 0: foundation

The [foundation PR](https://github.com/ppenumatsa1/agent-blueprints/pull/1)
established the architecture, reference analysis, catalog, engineering
standards, initial contracts, and GitHub-hosted validation under the MIT
License. The [follow-up](https://github.com/ppenumatsa1/agent-blueprints/pull/2)
added profile-aware contracts, the supplied architecture source, and the
[living checklist](master-checklist.md).
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

### Execution sequence and work packages

The modularity foundation reorganizes the local blueprint and generated
copies into sibling backend/frontend contexts and separates backend
responsibilities using canonical imports and no compatibility aliases. Acceptance
requires source and generated security/recovery tests, both crash windows,
independent golden verification and exact contract bytes, credential-free
CI and Compose smoke checks. Local evidence is recorded in the
[checklist](master-checklist.md). [PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11)
remains open; foundation commit `9efeef0` removes compatibility aliases and
corrects checkpoint selection. Its
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
passed all five jobs for foundation head `d0e1727`; reconcile and verify the
dependent PRs and combined revision separately.
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
[PR #13](https://github.com/ppenumatsa1/agent-blueprints/pull/13), head
`543b137a432ca054920d629b943fc42a729df676`; its
[hosted run](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44937692067)
passed five checks for that exact revision. The proposal's reported
Windows/Linux Compose verification used an approved mirror after public TLS
failures; macOS and interactive debugger verification remain unverified.
These results do not establish that tooling in PR #13 is merged or validate
any combined revision. Documentation [PR #12](https://github.com/ppenumatsa1/agent-blueprints/pull/12)
head `60458d9951bec3066dd92dc779714539007f7fd5` passed all five checks in
[run 44936739123](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936739123);
it also remains open.

Each PR must remove obsolete compatibility layers, use direct imports,
update affected `docs/design` specifications and the cumulative engineering
journal, and record actual regression, security, durability, independent
verification and CI outcomes for its final revision. The design documents
must accompany generated applications and distinguish planned work from
verified behavior. The six generated-project guides and eight documents under
`blueprints/maf/workflow/docs/design/` must evolve alongside implementation,
remain in generated applications, and use actual source/configuration
references, meaningful Mermaid diagrams, and accurate implemented/planned
labels. Maintain the engineering journal without inventing historical
findings. For each meaningful PR update this plan, `docs/master-checklist.md`,
and relevant architecture documentation with acceptance criteria, evidence,
status, and next action.

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
[44937692067](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44937692067)
passed all five jobs for PR head `543b137`, not for any combined revision.
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
[run 44938122124](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44938122124)
passed all five jobs on its final head `0364721`, not on the combined
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
on the rebased working tree; two instantiation tests also passed. Confirm the
exact proposed head and actual PR CI, followed by separately authorized
network, identity, cost and deployment review; no cloud mutation has occurred.

The staged PostgreSQL server selects 16 while Compose and the parallel
migration catalog tests use 17. The pinned API's documented enum and examples
conflict, and the compiler accepts arbitrary version strings; neither resolves
17 support for that API. The [version-gap review](../blueprints/maf/workflow/infra/README.md#open-postgresql-version-gap)
records a newer API as an unverified candidate. Separately, migration revision
`031fdb440908092cf09801232fe7f5d15048f065` passed 12 migration tests on local
PostgreSQL 16.15 after an initial auxiliary locale probe failed and was
corrected. The integration worktree combines the migrations and infrastructure,
but that result belongs to the separate migration revision. Resolve the target
major and rerun clean, upgrade and drift tests on the exact combined revision before
deployment; local evidence does not prove Azure compatibility or safe
downgrade.

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
| P1-06 | Implement PostgreSQL business records, approval/audit state, and an idempotent action ledger. | P1-01, P1-05 interfaces | Real restart tests cover crashes after decision persistence and after action commit, with no unauthorized or duplicate actions. |
| P1-07 | Implement typed FastAPI operations with Entra token validation, authorization, approvals, and optional OBO. | P1-01, P1-06 interfaces | Positive and negative tests cover scopes, roles, identity isolation, malformed and replayed requests; synthetic identities exist only in isolated tests. |
| P1-08 | Implement an accessible MSAL React client for sign-in, submission, status, approval/rejection, and failure states. | P1-01, P1-07 API contract | UI tests cover visible states and safe retries; browser code contains no service secrets. |
| P1-09 | Implement a native MAF workflow with local file checkpoints, isolated pause/resume, rejection, and recovery. | P1-01, P1-06 interfaces | Local tests cover repeated decisions, concurrent requests, and recovery without a universal orchestration wrapper; Foundry hosting is deferred to P1-12. |
| P1-10 | Add integration/E2E tests, synthetic agent evaluations, and GitHub Actions; connect actual results and artifacts to the validator. | P1-04 through P1-09 | A local or CI run produces a report from real artifacts; blocking failures cannot pass, non-blocking outcomes follow the selected profile, and rubric/threshold decisions are recorded. |
| P1-11 | Add privacy-safe logs, traces, correlation, and operational signals across API, workflow, approvals, and side effects. | P1-07, P1-09 interfaces | Tests verify redaction and correlation; actual export remains environment-specific. |
| P1-15 | Demonstrate the local prototype from a synthetic specification through approval, evaluation, and its readiness report. | P1-10, P1-11 | Record the scenario, evidence, limitations, and observed elapsed time; the 2–3 hour objective is a target until a representative run demonstrates it. |
| P1-12 | Validate Foundry Hosted Agent compatibility for the selected MAF version, Responses protocol, request-aware workflow factory, identity, and host-managed checkpoints. | P1-09, P1-15 | Hosted caller binding and lost-response reconciliation are blocked; see the [investigation journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---hosted-caller-binding-and-lost-responses). Local checks alone are not a hosted deployment. No Azure resources are provisioned. |
| P1-13 | Prepare the explicitly selected ACA fallback and a framework-compatible checkpoint strategy. | P1-09, P1-15 | Separate local/container recovery and idempotency checks pass; no claim that ACA shares Foundry checkpoint ownership or silently replaces a failed model call. |
| P1-14 | Prepare Bicep, least-privilege identities, authenticated public endpoints, GitHub-hosted CI, and deployment/handoff instructions. Deploy only after separate Azure authorization. | P1-10, P1-11, P1-12; P1-13 if selected | Source and independently generated Bicep compilation and focused tests passed locally without Azure credentials; PR-head CI must be confirmed. Agent-scoped identity, private connectivity and application integration remain unverified. An authorized deployment later records its revision, versions, identity, network, evidence, cost, and teardown owner. |

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
