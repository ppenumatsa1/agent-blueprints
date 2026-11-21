# Verification and readiness contract

This is a proposed contract for future projects. A local validator and
synthetic fixtures exist, but they are not a verification service, release
authorization system, or evidence that any agent has passed these gates. The
goal is a verified customer prototype in 2–3 hours when feasible, without
concealing risk or claiming production readiness.

## Profiles and maturity

| Target | Required outcome |
| --- | --- |
| Prototype | Every applicable critical or blocking requirement passes. Failed or unverified non-blocking requirements remain visible with reasons but do not prevent prototype readiness. Record assumptions, incomplete integrations, and limitations; this is not a production or customer-acceptance claim. |
| Production candidate | All applicable blocking requirements pass. Appropriate security, integration, operations, and evaluation controls have verified evidence or an authorized, documented applicability decision. A non-blocking failure or unknown requires explicit, independently reviewed risk acceptance; its actual result remains failed or unverified. |
| Customer validated | The production-candidate policy applies, and an authorized customer representative explicitly approves the evidenced acceptance criteria for the specific scope and revision. |

For each requirement, the owner specifies measurable success and failure
criteria, `critical` and `security_critical` classifications, domains, checks,
expected evidence types, a positive maximum evidence age for each check, and
one gate per target. A security-critical requirement is also critical, must
include the security domain, and may not be marked non-blocking at any target.
Other critical requirements may not be non-blocking either. `not_applicable`
is allowed only for a genuinely inapplicable scope, with the authorized human
review described below; it is not a waiver.

The approved contract and its security classifications must not be silently
weakened. The local validator compares an updated contract against the
previously approved baseline and requires a separately signed decision from
an independently administered trust store for any critical or security-critical
downgrade, removal, or change to `not_applicable`. The organization must
authenticate the human and protect that trust. The decision must include a
rationale. Initial classifications also require human contract review. A new
approval must bind the changed contract bytes;
an extension or a changed flag alone cannot authorize a downgrade.

`production_controls` declares whether security, integration, operations, and
evaluation are required. It may be omitted for a prototype-only contract, but
the validator must require it for production-candidate and customer-validated
assessments. Security is always required. Each required domain needs at least
one applicable, blocking requirement tagged with that domain and backed by
appropriate checks and evidence. The other domains may be `not_applicable`
only with a rationale and an authorized review reference; the validator must
verify that review. Missing coverage or an unverifiable decision cannot
support a production pass.

## Results and gates

Each requirement retains one distinct outcome:

- **Passed:** all required checks passed and their expected evidence is
  available, attributable, current, and applicable to the assessed revision
  and environment.
- **Failed:** an applicable required check failed or a defined failure
  criterion occurred. Record the reason and supporting evidence.
- **Unverified:** a required check or evidence is missing, incomplete, stale,
  inaccessible, mismatched, or not yet assessed. Missing evidence is never a
  pass.
- **Not applicable:** an authorized human has reviewed and documented why the
  requirement does not apply to this scope. Record the reviewer, rationale,
  and decision reference.

The validator computes results from the approved contract and actual
inputs; it does not trust a submitted gate or relabel a failed check. Invalid,
missing, stale, failed, or mismatched evidence cannot establish a passing
check. For every profile, a failed blocking requirement makes the gate
**failed**; an unverified blocking requirement, unverified applicability or
contract approval, or a contract with no applicable blocking requirements
makes it **unverified**. A pass requires at least one passing blocking
requirement and a verified contract approval.

For a prototype, non-blocking failures and unknowns do not change that gate,
but their separate outcomes, reasons, and applicable disclosures remain in the
report. For production-candidate and customer-validated assessments, each
non-blocking failure or unknown additionally needs valid risk acceptance:
without it the gate is failed for a failure or unverified for an unknown.
Accepted risk permits an overall pass only for that non-blocking result; it
does not turn a failed or unverified requirement or check into a pass. Risk
acceptance never overrides a blocking or critical requirement.

The report records an acceptance decision, reviewer, evidence reference,
decision time, expiration, rationale, compensating controls, and scope:
requirement ID, affected check IDs, actual requirement status, contract
SHA-256, target maturity, source revision, and environment. An empty controls
list explicitly means none. The validator must verify that the referenced
human decision covers the exact adverse check outcomes and supporting evidence,
the reviewer's authority, scope, decision time, expiry, and revocation as of
assessment time. New or changed findings require a new decision. Missing,
expired, mismatched, or unverifiable acceptance cannot support a production
pass. Approvals and exceptions are decisions, not evidence that the underlying
check passed.

## Traceability and human authority

The intended chain is **requirement -> check -> implementation -> result ->
evidence -> decision**, tied to a contract version, source revision,
environment, and assessment time. Evidence should be retained under
appropriate access and retention controls; a reference is not proof that its
target exists, is current, or is trustworthy.

The report's `contract_sha256` identifies the exact bytes of the approved
contract, not just its ID and version. A passing report records an approval
reference for that contract. The validator verifies that a signed decision
binds those bytes and matches its configured trust store; independently
administering that store and establishing human authority remain necessary. A
reviewer string or schema-valid record alone cannot establish approval. Preserve the
approved file's encoding and line endings when distributing it: reserializing
the contract changes its digest and requires a new approval. The decision must
be valid and unrevoked at assessment time.

Evidence records carry a reference, SHA-256 digest, revision, environment, and
recorded timestamp. The validator must read and verify referenced bytes, match
revision and environment, corroborate each check's outcome against the
referenced result artifact, and compare each required artifact's timestamp to
`assessed_at`: it must not be in the future or older than the check's maximum
age, with the maximum-age boundary included. A claimed digest, timestamp, or
identity in JSON is not independently verified evidence.

Customer approval, applicability review, classification changes, and risk
acceptance must be explicit decisions by authorized humans, not model
assertions, synthetic fixtures, or client-supplied identities. The future
application or release system must authenticate reviewers, authorize their
decisions, retain an audit trail, and enforce approved scope.

## Proposed JSON Schemas

All three use JSON Schema 2020-12. The blueprint manifest remains `0.1.0`;
the verification and readiness schemas are proposed at `0.3.0`:

| Schema | Purpose |
| --- | --- |
| [Blueprint manifest](../contracts/blueprint-manifest.schema.json) | Names a blueprint, framework, execution strategy, capabilities, and per-host compatibility with evidence. |
| [Verification contract](../contracts/verification-contract.schema.json) | Describes requirements, criticality, domains, checks, evidence and freshness policy, maturity gates, and optional production controls. |
| [Readiness report](../contracts/readiness-report.schema.json) | Records disclosures, per-requirement results, evidence, approval, applicable risk acceptance, and the gate outcome. |

Version `0.3.0` is a breaking change from `0.2.0`: classify and tag every
requirement through human review, supply the report disclosure arrays, and
define production controls where required. Reassess gates and reapprove the
new contract bytes; do not silently infer classifications or carry forward a
passing report. The synthetic prototype and production examples demonstrate
different profile policies, not actual readiness.

The schemas enforce document shape and some local invariants: for example, a
blocking result cannot be non-passing in a passed report, a passed production
report needs risk-acceptance records for non-blocking failures and unknowns,
and security-critical requirements cannot be marked non-blocking. The schema
cannot determine whether a risk reviewer is authorized, a decision is valid,
a contract changed classifications, a control has appropriate coverage, or the
report matches its contract.

**Schema validation is not readiness verification.** The local
[validator](readiness-validator.md) checks cross-file relationships, IDs,
evidence bytes and freshness, signed decisions, and profile gates. Its trust
store, producer, assessment time, and human authority must be independently
controlled; synthetic tests do not establish readiness of an application.

## Specification Studio handoff

The proposed verification contract is the producer-neutral handoff: a future
Specification Studio producer should emit this versioned JSON shape or use an
explicit, lossless adapter. Preserve stable contract, requirement, and check
IDs, criteria, classifications, domains, evidence types, freshness limits,
maturity gates, and production controls; do not silently invent policy or
downgrade a gate. Requirement IDs must be unique within the contract, and
check IDs must be unique across it.

Both schemas allow optional namespaced `extensions` objects for supplementary
producer metadata. Extensions never replace required core fields or override
gate semantics. The `specification_studio` metadata in the fixture is
illustrative. No actual Specification Studio output or integration exists yet,
so interoperability remains to be verified rather than assumed.

The [examples](../contracts/examples/), `fixture://` references, and placeholder
digests are entirely synthetic. They are not evidence that a blueprint,
customer, or deployment has been validated.
