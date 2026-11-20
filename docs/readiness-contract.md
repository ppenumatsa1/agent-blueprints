# Verification and readiness contract

This is a proposed contract for future projects. Phase 0 provides document
schemas and synthetic fixtures, not a verification service, a release
authorization system, or evidence that any agent has passed these gates.

## Maturity

| Target | Required outcome |
| --- | --- |
| Prototype | A demonstrable synthetic scenario with its agreed blocking requirements, basic security, privacy, and failure behavior verified. It is not a production or customer-acceptance claim. |
| Production candidate | The project's blocking functionality, identity, authorization, security, reliability, operations, evaluation, deployment, and recovery requirements have appropriate evidence for the intended environment. A human release authority reviews remaining risk. |
| Customer validated | The agreed customer acceptance criteria are evidenced and an authorized customer representative explicitly approves the specific scope and revision. This is not a substitute for ongoing operational assurance. |

The requirement owner defines measurable success and failure criteria, checks,
evidence types, and a gate for each maturity target. Security-critical or
business-critical controls must not be made non-blocking merely to obtain a
pass. The project identifies the owner and reviewer for each check; an
independent authorized person reviews exceptions and customer acceptance.

## Result and gate semantics

Each requirement has one of these outcomes:

- **Passed:** every required check passed and its expected evidence is
  available, attributable, and applicable to the assessed revision and
  environment.
- **Failed:** an applicable required check failed or a defined failure
  criterion occurred. Record the reason and supporting evidence.
- **Unverified:** a required check or evidence is missing, incomplete, stale,
  inaccessible, or not yet assessed. Missing evidence is never a pass.
- **Not applicable:** an authorized human has reviewed and documented why the
  requirement does not apply to this scope. Record the reviewer, rationale,
  and decision reference; do not use this as a silent waiver.

For a maturity target, an applicable requirement is `blocking` or
`non_blocking`, or has a reviewed `not_applicable` decision. A proposed gate
reducer reports **failed** for a blocking failure; otherwise **unverified**
when blocking evidence is missing; otherwise **passed** only when at least
one blocking requirement is evidenced and every blocking requirement passed.
Non-blocking failures and unknowns remain visible even if that gate passes.
If no blocking requirement applies, do not automatically promote readiness:
review the contract and report it as unverified until resolved.

Document exceptions, their scope, owner, rationale, risk, compensating
controls, expiration, and approval in the project's decision system. An
exception is not an implicit passing test or authority to rewrite an approved
contract; any change to criteria or applicability requires a reviewed contract
version and an explicit decision.

## Traceability and human authority

The intended chain is **requirement -> check -> implementation -> result ->
evidence -> decision**, tied to a contract version, source revision,
environment, and assessment time. Evidence should be retained under
appropriate access and retention controls; a reference is not proof that its
target exists, is current, or is trustworthy.

Customer approval must be an explicit decision by an authorized human, not a
model assertion, synthetic fixture, or client-supplied identity. The future
application or release system must authenticate the reviewer, authorize the
decision, record a tamper-resistant audit trail, and enforce the approved scope.
Similarly, a not-applicable decision must be attributable to an authorized
human.

## Proposed JSON Schemas

All three use JSON Schema 2020-12 and identify the initial schema version as
`0.1.0`. Versions are proposed and may change through review:

| Schema | Purpose |
| --- | --- |
| [Blueprint manifest](../contracts/blueprint-manifest.schema.json) | Names a blueprint, framework, execution strategy, capabilities, and per-host compatibility with evidence. A verified host requires a framework version, protocol, and test or deployment reference with revision and environment; a documented unsupported claim requires a documentation reference. |
| [Verification contract](../contracts/verification-contract.schema.json) | Describes stable requirement and check IDs, success and failure criteria, expected evidence types, and maturity gates. |
| [Readiness report](../contracts/readiness-report.schema.json) | Records the assessed contract and revision, per-requirement results, check evidence, applicability review, gate status, and customer approval when relevant. |

The readiness schema rejects a passed check without a nonblank evidence
reference, a passed requirement with missing or non-passing reported checks,
and a passed gate containing a non-passing blocking result or no passing
blocking result. A passed customer-validated report must contain an `approved`
decision. A not-applicable result requires a reason and a reviewer reference.
Dates are checked when the validator enables format checking.

**Important limitations:** schemas cannot ensure unique IDs within objects,
compare a report to its verification contract, determine whether all required
checks or evidence types are present, verify evidence contents or freshness,
authenticate reviewers, or compute a trustworthy release gate. In particular,
the report's `gate` values must be compared to the applicable contract; a
consumer must not trust a report merely because it validates. The focused
tests check cross-file relationships in the included fixtures only. A future
verification/release implementation must enforce these relationships and
authorization for real projects, fail closed, and preserve the decision trail.

The [examples](../contracts/examples/) and `fixture://` references are entirely
synthetic. Even the intentionally passing example is not evidence that a
blueprint, customer, or deployment has been validated.
