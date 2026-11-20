# Phased implementation plan

## Phase 0: foundation

This pull request proposes the architecture, reference analysis, catalog,
engineering standards, readiness contracts, schema examples, and GitHub-hosted
validation. The repository uses the MIT License. Specification Studio has not
yet produced an artifact, so the proposed handoff is not an end-to-end
compatibility claim. Phase 0 does not implement the validator or an agent
template, integrate Specification Studio, deploy Azure resources, or establish
production/customer approval.

## Phase 1: MAF workflow golden path

**Goal:** an independently runnable synthetic application with a native MAF
workflow, durable human approval and recovery, and an executable
Verification/Readiness Validator. Start locally with FastAPI, React,
PostgreSQL, Docker Compose, tests, and evaluations. Foundry Hosted Agents are
the preferred later deployment target, subject to compatibility verification;
Azure Container Apps (ACA) is the explicit fallback.

### Execution sequence and work packages

The packages are future implementation work, not completed functionality.
Inputs and interfaces can be agreed in parallel; integrations wait on the
dependencies listed.

| ID | Bounded work package | Dependencies | Independently verifiable outcome |
| --- | --- | --- | --- |
| P1-01 | Define a synthetic, non-destructive scenario and approve requirement/check IDs, criteria, evidence types, freshness limits, and maturity gates. | None | Reviewed contract and an authorized approval record bind the exact contract digest; fixtures cover success, failure, approval, rejection, and recovery without customer data. |
| P1-02 | Define normalized test-result and evidence-manifest inputs, including contract/version, requirement/check IDs, outcome, revision, environment, timestamps, artifact references, and digests. Map local test/evaluation output explicitly. | P1-01 | Synthetic input fixtures cover multiple checks and evidence types; unknown or unmappable results cannot be silently ignored. |
| P1-03 | Implement the validator's contract, traceability, evidence-integrity, freshness, and gate logic as a small local Python component. | P1-02 | Focused tests reject missing, failed, stale, future-dated, mismatched, duplicate, inaccessible, or tampered inputs, including non-blocking requirements. |
| P1-04 | Expose the validator as a CLI that consumes the approved contract, test results, and supporting evidence and writes a schema-valid readiness report. | P1-03 | Automated CLI tests verify success, nonzero failure, actionable diagnostics, report contents, and no fabricated approval. |
| P1-05 | Create the local Docker Compose development stack and documented setup for React, FastAPI, PostgreSQL, and the selected local workflow mode. | P1-01 interfaces | A clean-machine setup starts and stops the stack with synthetic configuration; no Azure credentials are needed. |
| P1-06 | Implement PostgreSQL business records, approval/audit state, and an idempotent action ledger. | P1-01, P1-05 interfaces | Transaction, uniqueness, concurrency, restart, and duplicate-action tests pass; business records are separate from workflow checkpoints. |
| P1-07 | Implement typed FastAPI operations, authenticated identity, per-record authorization, approvals, and explicit error responses. | P1-01, P1-06 interfaces | Positive and negative tests cover anonymous, unauthorized, malformed, replayed, and cross-user requests. Local mock identity is explicit and cannot become production security. |
| P1-08 | Implement an accessible React client for sign-in, scenario submission, status, approval/rejection, and failure states. | P1-01, P1-07 API contract | UI tests cover visible states and safe retries; browser code contains no service secrets. |
| P1-09 | Implement the framework-native MAF workflow with bounded executors, request isolation, pause, resume, rejection, and safe recovery. | P1-01, P1-06 interfaces | Local tests cover repeated decisions, concurrent requests, and recovery without a universal orchestration wrapper. |
| P1-10 | Add integration/E2E tests and synthetic agent evaluations; connect their actual results and artifacts to the validator. | P1-04 through P1-09 | A local run produces a report from real test/evaluation artifacts; negative runs cannot pass, and rubric/threshold decisions are recorded. |
| P1-11 | Add privacy-safe logs, traces, correlation, and operational signals across API, workflow, approvals, and side effects. | P1-07, P1-09 interfaces | Tests verify redaction and correlation; actual export remains environment-specific. |
| P1-12 | Validate Foundry Hosted Agent compatibility for the selected MAF version, Responses protocol, request-aware workflow factory, identity, and host-managed checkpoints. | P1-09, P1-10 | Record versions and evidence for the compatibility assessment; local checks alone are not a hosted deployment. No Azure resources are provisioned. |
| P1-13 | Prepare the explicitly selected ACA fallback and a framework-compatible checkpoint strategy. | P1-09, P1-10 | Separate local/container recovery and idempotency checks pass; no claim that ACA shares Foundry checkpoint ownership or silently replaces a failed model call. |
| P1-14 | Prepare Bicep, least-privilege identities, authenticated public endpoints, GitHub-hosted CI, and deployment/handoff instructions. Deploy only after separate Azure authorization. | P1-10, P1-11, P1-12; P1-13 if selected | Static checks work without Azure credentials; an authorized deployment later records its revision, versions, identity, network, evidence, cost, and teardown owner. |

### Validator acceptance contract

The validator consumes the approved, versioned verification contract; actual
normalized test/evaluation results; and supporting evidence artifacts. Its
assessment context supplies the target maturity, source revision, environment,
and assessment time. The first implementation reads bounded local artifacts,
not arbitrary remote URLs, and verifies their bytes and SHA-256 digests. It runs
locally or in CI with the generated project, not as a shared factory runtime.

It must verify the contract's exact byte digest against an authorized approval,
then match contract/version, unique requirement and check IDs, expected evidence
types, results, revision, environment, and each check's explicit freshness
policy. A failed check is **failed**; missing, stale, future-dated, inaccessible,
or mismatched evidence is **unverified**. Either prevents an overall pass for
every applicable requirement, including `non_blocking`. Verify contract approval,
applicability, and customer decisions through an authorized human decision
mechanism, including scope, validity, and revocation where applicable; a name
or approval string alone is not authority. If approval cannot be verified,
report unverified rather than inventing it.

For a valid contract and assessment context, write a machine-readable
readiness report even when checks fail or evidence is unverified. Exit zero
only for a passing report and nonzero otherwise. If the contract or assessment
context cannot be parsed or identified, emit a machine-readable diagnostic
and a nonzero exit rather than fabricating a schema-valid report. Tests must
cover missing or invalid contract approval, freshness boundaries,
revision/environment and digest mismatches,
missing or duplicate IDs and checks, failed tests, non-blocking failures,
unreviewed applicability, and missing or rejected customer approval.

**Hosting constraint:** the Python Foundry hosting integration is documented as
prerelease. Establish package/protocol compatibility and the approval/resume
path before promising it. Foundry-managed checkpoints do not replace PostgreSQL
business state; ACA recovery requires separate evidence. Select a fallback
explicitly and never provision Azure resources without approval.

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
