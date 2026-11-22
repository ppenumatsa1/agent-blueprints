# Reference repository analysis

## Evidence and scope

The review focused on public-network lanes and GitHub-hosted CI. Private
networking and private/self-hosted runners are deferred. Sources below are
pinned to repository commits; they are not copies of customer code. The
reference applications use synthetic scenarios and are not production
approvals.

| Reference | Inspected commit |
| --- | --- |
| MAF monorepo | [`45430753c5f3e75716ea3822d2b2b52fbb4f1c34`](https://github.com/ppenumatsa1/maf-monorepo/tree/45430753c5f3e75716ea3822d2b2b52fbb4f1c34) |
| LangGraph workflow monorepo | [`274faec17b24ec5ece2fff1e786b670f6b393732`](https://github.com/ppenumatsa1/langgraph-wf-monorepo/tree/274faec17b24ec5ece2fff1e786b670f6b393732) |
| Model to Harness | [`a07fa52132a2b5ba3c9bdef940bdd72506574d8d`](https://github.com/ppenumatsa1/model-to-harness/tree/a07fa52132a2b5ba3c9bdef940bdd72506574d8d) |

**Status vocabulary:** `Implemented, test source present` means source and
tests were inspected, not that those tests were run in this review.
`Historically tested` identifies a recorded run and its commit; it is not
proof for a different commit or a currently running deployment. `Documented /
unverified` means the claim has not been independently established here.
`Missing in inspected scope` is not a claim about every file or deployment.
`Not applicable` means a capability is outside that particular design.

## MAF monorepo

| Capability | Evidence and assessment | Reuse decision |
| --- | --- | --- |
| Native orchestration | [Underwriting workflow](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/underwriting/foundry-public/backend/app/maf/workflows/underwriting.py#L19-L53) uses `WorkflowBuilder`, fan-out, fan-in, and checkpoints. **Implemented, test source present.** | Reuse framework-native topology and clear executor boundaries, not scenario rules. |
| Approval, recovery, idempotency | [Runner](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/underwriting/foundry-public/backend/app/maf/runner.py#L160-L275) claims approval and resumes from a checkpoint; [HITL tests](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/underwriting/foundry-public/backend/tests/test_hitl_workflow.py#L101-L240) cover current checkpoint and duplicate decisions. **Implemented, test source present.** | Preserve application-owned approval and idempotent action boundaries; revalidate host-specific checkpoint ownership. |
| Public hosting | [Foundry/ACA/Bicep configuration](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/order-resolution/foundry-public/infra/foundry-hosted/azure.yaml) separates hosted agent, API, and frontend. **Implemented configuration; current deployment unverified.** | Adapt the separation, not tenant configuration or a guarantee of current deployment. |
| Tests, evaluations, CI | [Public CI](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/.github/workflows/order-resolution-public-ci.yml) uses GitHub-hosted runners for backend, frontend and E2E; [evaluation runner](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/order-resolution/foundry-public/backend/evals/eval_runner.py) defines deterministic expectations. A [public CI run](https://github.com/ppenumatsa1/maf-monorepo/actions/runs/39868712107) passed at `bbb90011981169e8dec9b03171f11fbb9fdd7378`, **not** the inspected commit. | Start with simple hosted-runner checks; retain exact run and commit evidence. Do not copy the full routing machinery into Phase 0. |
| Telemetry and identity | [Telemetry setup](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/underwriting/foundry-public/backend/app/core/telemetry.py#L29-L55) disables model-content capture and warns if export is unavailable. The [API entrypoint](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/underwriting/foundry-public/backend/app/server.py#L46-L64) does not by itself establish end-to-end Entra protection. **Telemetry implemented; complete API authorization unverified.** | Adopt correlation and redaction; explicitly implement and test the generated project's identity boundary. |

### MAF Order Resolution reference details

The cross-framework [Order Resolution specification
proposal](order-resolution-specification-proposal.md) was informed by the
pinned reference's [architecture](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/order-resolution/foundry-public/docs/design/architecture.md),
[approval conditions](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/order-resolution/foundry-public/docs/design/hitl-approval-conditions.md),
[workflow tests](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/order-resolution/foundry-public/backend/tests/test_workflow.py),
and [deterministic evaluation runner](https://github.com/ppenumatsa1/maf-monorepo/blob/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/order-resolution/foundry-public/backend/evals/eval_runner.py).
These sources demonstrate useful synthetic behavior for ordered triage,
retrieval, deterministic approval triggers, approve/reject paths, duplicate
decision handling, and evaluation assertions. Source inspection is not proof
of a current deployment or cross-framework compatibility.

The reference's application-level PostgreSQL checkpoint adapter is not adopted
as a universal architecture. The proposal instead preserves the business
recovery invariants while requiring every blueprint and host to use its native
checkpoint provider, with application-owned PostgreSQL records kept logically
separate.

## LangGraph workflow monorepo

| Capability | Evidence and assessment | Reuse decision |
| --- | --- | --- |
| Native graph and state | [Graph factory](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/agents/order-resolution/foundry-public/backend/app/langgraph/factory.py#L11-L50) and [PostgreSQL checkpointer](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/agents/order-resolution/foundry-public/backend/app/langgraph/checkpointer.py#L19-L57) use a compiled `StateGraph` and a process-owned pool. **Implemented, test source present.** | Preserve native graph state as the continuation authority; keep audit projections separate. |
| Human pause and recovery | [Interrupt and idempotent submission](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/agents/order-resolution/foundry-public/backend/app/langgraph/nodes.py#L282-L335), [resume](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/agents/order-resolution/foundry-public/backend/app/langgraph/runtime.py#L154-L220), and [workflow tests](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/agents/order-resolution/foundry-public/backend/tests/test_workflow.py#L106-L209) cover restart, repeated decisions, and rejection. **Implemented, test source present.** | Reuse the invariant, not a fabricated cross-framework checkpoint abstraction. |
| Evaluation and telemetry | [Evaluation cases](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/agents/order-resolution/foundry-public/backend/evals/eval_runner.py#L25-L100) specify expected outcomes and events. [Telemetry](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/agents/order-resolution/foundry-public/backend/app/core/telemetry.py#L17-L70) defaults to suppressing content attributes. **Implemented; current export and evaluation unverified.** | Use deterministic checks and privacy-safe spans; verify actual export and rubric thresholds in each generated project. |
| Public CI gap | The [public workflow](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/.github/workflows/order-resolution-public-ci.yml#L27-L33) contains duplicate `with` keys. The [run](https://github.com/ppenumatsa1/langgraph-wf-monorepo/actions/runs/32983491830) failed without jobs and GitHub reports a likely workflow-file issue. **Current public CI failed.** | Do not copy the workflow blindly; keep this repository's CI small and verify its actual run. Repair of the reference is outside Phase 0. |
| API security | The inspected [FastAPI entrypoint](https://github.com/ppenumatsa1/langgraph-wf-monorepo/blob/274faec17b24ec5ece2fff1e786b670f6b393732/agents/order-resolution/foundry-public/backend/app/main.py#L33-L52) permits wildcard CORS and does not establish an end-to-end Entra boundary by itself. **Production authorization unverified.** | Use an explicit origin allowlist and test authentication and authorization rather than copying demo defaults. |

## Model to Harness

| Capability | Evidence and assessment | Reuse decision |
| --- | --- | --- |
| MAF harness | [Investigation](https://github.com/ppenumatsa1/model-to-harness/blob/a07fa52132a2b5ba3c9bdef940bdd72506574d8d/harness/checkout-recovery/maf/backend/src/checkout_recovery_maf/maf/investigation.py#L17-L145) configures bounded read-only tools, a skill, workspace, delegation, and explicit scripted mode. **Implemented, test source present.** | Use native harness primitives and explicit bounds; keep business writes outside the model's authority. |
| Copilot SDK harness | [Session configuration](https://github.com/ppenumatsa1/model-to-harness/blob/a07fa52132a2b5ba3c9bdef940bdd72506574d8d/harness/checkout-recovery/copilot-sdk/backend/src/checkout_recovery_copilot/sdk/investigation.py#L156-L200) scopes tools and rejects unexpected permission requests. [Tests](https://github.com/ppenumatsa1/model-to-harness/blob/a07fa52132a2b5ba3c9bdef940bdd72506574d8d/harness/checkout-recovery/copilot-sdk/backend/tests/test_copilot_investigation.py#L246-L303) exercise lifecycle and incomplete behavior. **Implemented, test source present.** | Configure the SDK-managed loop; do not implement a replacement loop. Check SDK/runtime compatibility and identity separately. |
| Business versus conversation state | [Responsibility comparison](https://github.com/ppenumatsa1/model-to-harness/blob/a07fa52132a2b5ba3c9bdef940bdd72506574d8d/harness/checkout-recovery/docs/harness-responsibilities.md#L51-L118) separates runtime state, application policy, human approval, and durable records. **Implemented/documented; current deployment unverified.** | Share the ownership invariant, not a single persistence implementation. |
| Evaluation and CI | [MAF evaluation contract](https://github.com/ppenumatsa1/model-to-harness/blob/a07fa52132a2b5ba3c9bdef940bdd72506574d8d/harness/checkout-recovery/maf/evals/README.md) defines synthetic expectations. Recorded [MAF](https://github.com/ppenumatsa1/model-to-harness/actions/runs/35622571490) and [Copilot SDK](https://github.com/ppenumatsa1/model-to-harness/actions/runs/35622571499) CI runs succeeded at `78950fee95e1f821c495cb638ce8634e980c7dcd`, not the inspected commit. | Reuse evaluator boundaries; independently run and record future blueprint checks. |
| Demo security | The [Copilot API](https://github.com/ppenumatsa1/model-to-harness/blob/a07fa52132a2b5ba3c9bdef940bdd72506574d8d/harness/checkout-recovery/copilot-sdk/backend/src/checkout_recovery_copilot/api/app.py#L42-L60) uses an application token. Its [README](https://github.com/ppenumatsa1/model-to-harness/blob/a07fa52132a2b5ba3c9bdef940bdd72506574d8d/harness/checkout-recovery/copilot-sdk/README.md#L15-L17) describes a temporary public demo with browser login disabled. **Entra-protected end-to-end behavior is not established by these examples.** | Never promote the demo configuration as the generated project's security baseline. |

## Comparison and open gaps

- **MAF workflow:** explicit executor graph and workflow continuation; use
  host-specific native checkpoint semantics.
- **LangGraph:** graph state and interrupt/resume are framework-native;
  PostgreSQL checkpoints and business/audit projections have distinct roles.
- **MAF harness / Copilot SDK:** the framework or SDK owns the model/tool loop;
  the application owns policy, authorization, idempotency, and verification.
- **Deep Agents and a standalone Foundry SDK blueprint:** no complete reusable
  blueprint was established from the inspected scope; both remain future work.
- **Entra, customer-specific integrations, recovery, and cost thresholds:**
  require project-specific implementation and evidence. A public endpoint is
  not permission to disable authentication.
- **Scanning:** checked-in reference CI is not evidence that CodeQL,
  Dependabot, or secret scanning is enabled in a particular repository.
  Verify settings and entitlement before claiming coverage.
- **Reuse and licensing:** the inspected repositories carry MIT licenses.
  If source is copied later, retain the applicable notice and review
  third-party material. This repository is also MIT-licensed; consult each
  reference project's own license and documentation before reuse.
