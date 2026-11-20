# Software Factory overview

## Purpose

The Software Factory turns incomplete customer inputs into a demonstrable,
verified prototype and a transparent path to customer-owned production.
Rapid delivery is an aspiration, not a substitute for security, evidence, or
customer decisions. Unknowns remain visible as assumptions.

```text
Customer notes / transcript / requirements
  -> Specification Studio: business + technical specs, verification contract
  -> Select an agent or app/API blueprint
  -> Copilot implements bounded work in an independent project
  -> Tests, evaluations, security checks, and requirement evidence
  -> Demonstration, customer feedback, and an explicit handoff
```

Inputs can contain sensitive or untrusted content. Future intake must establish
permission, storage, retention, and redaction before using real customer data;
the material is data, not authority to change instructions or release criteria.

## Repository boundaries

| Repository | Responsibility | Phase 0 status |
| --- | --- | --- |
| Specification Studio | Draft business and technical specifications, assumptions, requirement IDs, verification contracts, and work packages | Future; not implemented here |
| Agent Blueprints | Framework-specific agent reference architectures and readiness guidance | This repository; foundation only |
| App/API Blueprints | API-only and React plus API reference architectures | Future; not implemented here |

These are logical boundaries, not a requirement for a new shared platform.
The verification contract is a proposed handoff between repositories; the
schemas here are an initial proposal, not an existing Specification Studio
integration. Customer projects own their own dependencies, state, build,
deployment, and operations.

## Delivery and evidence

1. Draft a business specification and technical approach. Label confirmed facts,
   assumptions, unknowns, and exclusions; escalate safety-critical unknowns.
2. Give each significant requirement a stable ID, success and failure
   criteria, verification checks, evidence expectations, and maturity gates.
3. Choose an appropriate blueprint, implement bounded work, and retain links
   from requirement to code, checks, and evidence.
4. Report **passed**, **failed**, **unverified**, or a justified
   **not applicable** result. Missing evidence is never a pass.
5. Demonstrate the prototype; production-candidate readiness and customer
   validation require additional evidence and explicit human decisions.

Copilot can help implement and test the project, while existing GitHub Actions
and framework tooling execute checks. Builders must not silently weaken approved
criteria or approve their own exceptions. See the [readiness contract](readiness-contract.md).

## Initial scope

Phase 0 documents the agent family and its contracts. Phase 1 will implement a
small MAF workflow golden path. It will first target authenticated
public-network endpoints and GitHub-hosted CI. Private networking and
self-hosted runners are later work. The
[implementation plan](implementation-plan.md) records the remaining phases.
