# Phased implementation plan

## Phase 0: foundation

This pull request proposes the architecture, reference analysis, catalog,
engineering standards, readiness contracts, schema examples, and GitHub-hosted
validation. It does not create an agent template, integrate Specification
Studio, deploy Azure resources, or establish production/customer approval.

## Phase 1: MAF workflow golden path

**Goal:** an independently runnable synthetic application that demonstrates a
framework-native MAF workflow, a durable human approval and safe recovery, and
evidence-driven verification. Foundry Hosted Agents are the preferred
public-network deployment; Azure Container Apps (ACA) is an explicitly
selected fallback. Both require their own verification.

Use the following bounded work packages as separate implementation units.
Parallel work can start after its stated inputs are agreed. Acceptance criteria
are future requirements, not completed functionality.

| ID | Work package and dependencies | Acceptance evidence |
| --- | --- | --- |
| P1-A | **Contract and scenario:** review Phase 0 schemas; define a synthetic, non-destructive business scenario and stable requirement IDs, safety boundaries, expected behavior, test data, and maturity gates. No dependencies. | Reviewed contract covers normal, failure, approval, rejection, and recovery paths; no real customer data or implied release approval. |
| P1-B | **Business state and action ledger:** design PostgreSQL records for the scenario, approvals, audit, and idempotency. Depends on P1-A. | Transactions and uniqueness constraints prevent duplicate or conflicting actions, including concurrent submissions and restart; business records remain distinct from workflow checkpoints. |
| P1-C | **Native MAF workflow:** implement bounded executors, explicit pause, resume, rejection, and request isolation. Depends on P1-A and the P1-B interfaces. | Deterministic local tests cover success, failure, repeated decision, concurrent requests, and recovery; no universal orchestration wrapper or invented business approval. |
| P1-D | **FastAPI boundary:** define typed operations, input validation, authenticated identity, per-record authorization, approval endpoints, and error mapping. Depends on P1-A and P1-B interfaces; integrate P1-C. | Positive and negative tests reject anonymous, unauthorized, malformed, replayed, and cross-user requests; the server derives the actor from validated identity. Local mock identity is explicitly selected and cannot be deployed as production security. |
| P1-E | **React application:** implement accessible sign-in, scenario submission, status, approval/rejection, and error states against the documented API. Depends on P1-A and P1-D's API contract. | UI and end-to-end tests exercise user-visible states, authorization failures, refresh, and safe retry; browser code holds no service secrets. |
| P1-F | **Foundry hosted adapter:** use the documented Responses integration and request-aware MAF workflow factory with stable identities and host-managed checkpoints; pin the prerelease integration. Depends on P1-C and the hosting contract. | Version/protocol and identity constraints are recorded; request isolation and pause/resume are checked. Local tests do not claim a hosted deployment. Do not configure a separate workflow checkpoint store for host-managed recovery. |
| P1-G | **ACA fallback:** build a separate, explicitly selected MAF runtime/hosting path and choose a tested framework-compatible checkpoint strategy. Depends on P1-C and P1-B. | Independent checkpoint, restart, approval, and idempotency tests pass; no claim that ACA and Foundry share checkpoint ownership or that a model failure silently switches hosts. |
| P1-H | **Local development:** compose API, UI, PostgreSQL, and a selected local agent mode with synthetic settings. Depends on P1-B, P1-C, P1-D, and P1-E interfaces. | A clean-machine setup has documented prerequisites and reproducible commands. Explicit scripted/offline mode is visibly distinct from real model execution and does not mask failed calls. |
| P1-I | **Verification and evaluations:** implement requirement-to-code/check/evidence traceability and an actual gate evaluator; define synthetic evaluation data, rubric, thresholds, negative tests, and evidence retention. Depends on P1-A; integrate P1-B through P1-H. | Automated checks cover missing or stale evidence, unique IDs, contract/report gate matching, failed blocking checks, human approval, and evaluation regressions. Real reviewer authorization is enforced outside JSON Schema. |
| P1-J | **Telemetry and operations:** add privacy-safe structured logs, traces and correlation across API, workflow, approvals, and side effects; define latency, usage, cost, retention, and alerts. Depends on P1-D and P1-C interfaces. | Tests verify redaction and correlation; an authorized environment demonstrates actual telemetry export and operational ownership. |
| P1-K | **Public-network infrastructure and CI:** prepare parameterized Bicep, managed identities, least-privilege role assignments, secret handling, budgets/quotas, and GitHub-hosted build/test checks. Depends on P1-D, P1-F, P1-G, and P1-J interfaces. | Static validation and security review pass without credentials. Deployment uses authenticated endpoints and explicit origins; no resources are provisioned or paid features enabled without separate authorization. |
| P1-L | **Deployment and handoff:** after explicit Azure authorization, select Foundry or ACA, deploy to an approved environment, execute smoke/recovery tests, and record revision, versions, region, identity, network mode, evidence, cost, and teardown ownership. Depends on P1-I, P1-J, and P1-K. | Reproducible, environment-specific evidence supports only the demonstrated maturity; customer acceptance remains an authorized human decision. |

**Critical integration decisions:** Foundry's Python hosted-workflow integration
is documented as prerelease, so establish compatible package versions and the
approval/resume protocol before promising this path. Foundry-managed
checkpoints do not replace PostgreSQL business state. ACA recovery must be
tested separately. If the preferred hosting path cannot satisfy the contract,
record the limitation and select the fallback explicitly rather than
misrepresenting the result.

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
