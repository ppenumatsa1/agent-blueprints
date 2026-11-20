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
evidence types, an explicit maximum evidence age for each check, and a gate for
each maturity target. The project identifies the owner and reviewer for each
check; an independent authorized person reviews exceptions and customer
acceptance.

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
`non_blocking`, or has a reviewed `not_applicable` decision. The owner has
chosen a strict readiness policy: **every applicable requirement**, including
one labeled `non_blocking`, needs passing checks and valid evidence. The
`non_blocking` label is retained for prioritization, not as an evidence
waiver.

The proposed reducer reports **failed** if any applicable requirement fails;
otherwise **unverified** if any applicable evidence is missing, stale,
mismatched, or otherwise unverified, or an applicability decision has not been
verified; otherwise **passed** only when all applicable requirements pass and
at least one is blocking. A `not_applicable` gate can be reported as
`unverified` until its human review is verified. If no blocking requirement
applies, do not automatically promote readiness: review the contract and report
it as unverified until resolved.

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

The report's `contract_sha256` identifies the exact bytes of the approved
contract, not just its ID and version. A passing report records an approval
reference for that contract. The future validator must independently verify
that the approval binds those bytes and is authorized; a reviewer string or
schema-valid approval record alone cannot establish approval. Preserve the
approved file's encoding and line endings when distributing it: reserializing
the contract changes its digest and requires a new approval. The decision must
be valid and unrevoked at assessment time; missing or unverifiable approval
cannot support a pass.

For each check, `evidence_max_age_seconds` is a positive, explicitly approved
limit, not a validator default. Evidence records carry a reference, SHA-256
digest, revision, environment, and recorded timestamp. The future validator
must read and verify the referenced bytes, match the revision and environment,
and compare each required artifact's timestamp to `assessed_at`: it must not be
in the future or older than the check's maximum age, with the maximum-age
boundary included. A claimed digest, timestamp, or identity in JSON is not
independently verified evidence. Check-result timestamps must also satisfy the
approved freshness policy.

Customer approval must be an explicit decision by an authorized human, not a
model assertion, synthetic fixture, or client-supplied identity. The future
application or release system must authenticate the reviewer, authorize the
decision, record a tamper-resistant audit trail, and enforce the approved scope.
Similarly, a not-applicable decision must be attributable to an authorized
human.

## Proposed JSON Schemas

All three use JSON Schema 2020-12. The blueprint manifest is proposed at
`0.1.0`; the verification and readiness schemas are proposed at `0.2.0`:

| Schema | Purpose |
| --- | --- |
| [Blueprint manifest](../contracts/blueprint-manifest.schema.json) | Names a blueprint, framework, execution strategy, capabilities, and per-host compatibility with evidence. A verified host requires a framework version, protocol, and test or deployment reference with revision and environment; a documented unsupported claim requires a documentation reference. |
| [Verification contract](../contracts/verification-contract.schema.json) | Describes stable requirement and check IDs, success and failure criteria, expected evidence types, maximum evidence ages, and maturity gates. |
| [Readiness report](../contracts/readiness-report.schema.json) | Records the contract digest and approval, revision and environment, per-requirement results, evidence provenance, applicability review, gate status, and customer approval when relevant. |

Version `0.2.0` supersedes the earlier `0.1.0` drafts in this PR: freshness
policy, evidence provenance, and a contract digest are now required; a pass
also requires contract approval and passing results for all applicable
requirements. Existing drafts need an explicit, reviewed update; consumers
must not silently fill in missing policy. After a schema is released, make
breaking changes under a new version and document the migration.

The readiness schema rejects a passed check without a nonblank evidence
reference and provenance fields, a passed requirement with missing or
non-passing reported checks, and a passed gate without a contract approval,
containing any non-passing applicable result, or containing no passing blocking
result. A passed customer-validated report must also contain an `approved`
customer decision. A not-applicable result requires a reason and a reviewer
reference. Dates are checked when the validator enables format checking.

**Important limitations:** schemas cannot ensure unique IDs within objects,
compare a report to its verification contract, determine whether all required
checks or evidence types are present, verify evidence contents, digests or
freshness, authenticate reviewers, or compute a trustworthy release gate. In
particular, the report's `gate` values must be compared to the applicable
contract; a consumer must not trust a report merely because it validates. The
focused tests check cross-file relationships in the included fixtures only.
Phase 1 must implement an executable validator that enforces these relationships
and authorization for real projects, fails closed, and emits a machine-readable
report; see the [work packages](implementation-plan.md).

## Specification Studio handoff

The proposed verification contract is the producer-neutral handoff: a future
Specification Studio producer should emit this versioned JSON shape or use an
explicit, lossless adapter. Preserve stable contract, requirement, and check IDs,
criteria, evidence types, freshness limits, and maturity gates; do not silently
invent missing policy or downgrade a gate. Requirement IDs must be unique within
the contract, and check IDs must be unique across it. The corresponding
readiness report uses the same contract ID and version.

Both schemas allow optional `extensions` objects for producer-specific metadata.
Each namespace starts with a letter, contains only letters, digits, `.`, `_`,
or `-`, and has an object value. Extensions are supplementary data, never a
replacement for required core fields or authority to change gate semantics.
The `specification_studio` metadata in the fixture is illustrative. No actual
Specification Studio output or integration exists yet, so interoperability
with a future producer remains to be verified rather than assumed.

The [examples](../contracts/examples/), `fixture://` references, and placeholder
digests are entirely synthetic. Even the intentionally passing example is not
evidence that a blueprint, customer, or deployment has been validated.
