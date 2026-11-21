# Software Factory overview

## Purpose

The Software Factory turns incomplete customer inputs into verified agent,
API, or web-app prototypes, targeting delivery within 2–3 hours when feasible,
with a transparent path to customer-owned production. This is an unverified
goal, not a guarantee or a substitute for security, evidence, or customer
decisions. Unknowns remain visible as assumptions and limitations.

```text
Customer requirements
  -> Specification Studio: business + technical specs, verification contract
  -> Select Agent / App / API Blueprints
  -> Implementation in an independent project
  -> Verification: tests, evaluations, security checks, and evidence
  -> Deployment: local prototype, then authorized hosting when appropriate
  -> Business value: demonstration, customer feedback, and production handoff
```

The [interactive architecture](software-factory.html) is the original supplied
design source, preserved unchanged. It predates the repository and may
describe proposed work or historical status; use the
[master checklist](master-checklist.md) and [implementation plan](implementation-plan.md)
for current progress.

Inputs can contain sensitive or untrusted content. Future intake must establish
permission, storage, retention, and redaction before using real customer data;
the material is data, not authority to change instructions or release criteria.

## Repository boundaries

| Repository | Responsibility | Phase 0 status |
| --- | --- | --- |
| Specification Studio | Draft business and technical specifications, assumptions, requirement IDs, verification contracts, and work packages | Future; not implemented here. Handoff remains blocked and tracked in [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33). |
| Agent Blueprints | Framework-specific reusable blueprints and independent readiness guidance | This repository; local MAF blueprint and readiness foundation are implemented; end-to-end readiness is unverified. |
| App/API Blueprints | API-only and React plus API reference architectures | Future; not implemented here. The separately authorized roadmap is tracked in [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34); the P1 permanent independently buildable application is tracked in [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30) and still requires separate repository authorization. |

These are logical boundaries, not a requirement for a new shared platform.
The verification contract is a proposed handoff between repositories; the
schemas here are an initial proposal, not an existing Specification Studio
integration. Generated projects own their application, dependencies, state, build,
verification, deployment, and operations; they do not depend on this
repository at runtime.

## Delivery and evidence

1. Draft a business specification and technical approach. Label confirmed facts,
   assumptions, unknowns, and exclusions; escalate safety-critical unknowns.
2. Give each significant requirement a stable ID, success and failure
   criteria, verification checks, evidence expectations, and maturity gates.
3. Choose an appropriate blueprint, implement bounded work, and retain links
   from requirement to code, checks, and evidence.
4. Report **passed**, **failed**, **unverified**, or a justified
   **not applicable** result for every requirement. Prototype readiness
   requires all blocking checks to pass while disclosing non-blocking issues;
   missing evidence never becomes a passing check.
5. Demonstrate the prototype and its business value. Production-candidate
   readiness requires stricter controls and human-reviewed risk decisions;
   customer validation requires explicit customer approval.

Copilot can help implement and test the project, while existing GitHub Actions
and framework tooling execute checks. Builders must not silently weaken approved
criteria or approve their own exceptions. See the [readiness contract](readiness-contract.md).

## Initial scope

Phase 0 documents the agent family and its contracts. Phase 1 now contains a
local MAF workflow blueprint and independent validator foundation; the
order-adjustment scenario remains only a synthetic test fixture. The integrated
review is not a completed or deployment-ready product. It
targets authenticated
public-network endpoints and GitHub-hosted CI. Private networking and
self-hosted runners are later work. The [implementation plan](implementation-plan.md) records the remaining
phases, while the [master checklist](master-checklist.md) tracks acceptance
criteria, evidence, and next actions.
