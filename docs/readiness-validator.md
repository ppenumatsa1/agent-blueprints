# Local readiness validator

The validator is a local Python CLI, not an orchestration service or CI
platform. It uses JSON Schema, OpenSSL, and bounded local files. It does not
run the application, tests, evaluations, or GitHub Actions. Its assessments
are meaningful only if the independent trust store, clock, source checkout,
result producer, and evidence directory are controlled by an authorized
operator. A valid signature proves possession of a trusted key, not that the
signer is a human or that a test actually ran.

## Try the unapproved scenario

Install `requirements-dev.txt` in a Python 3.12+ virtual environment and make
OpenSSL available on `PATH`. From the repository root:

```sh
python -m readiness \
  --contract scenarios/order-adjustment/verification-contract.json \
  --baseline scenarios/order-adjustment/verification-contract.json \
  --input scenarios/order-adjustment/example-input.json \
  --trust scenarios/order-adjustment/example-trust.json \
  --evidence-root scenarios/order-adjustment \
  --output readiness-report.json
```

This intentionally returns exit 1 and an **unverified** report: no checks or
authorized decisions have been supplied. Exit 0 means the selected profile
passed; exit 1 means a valid assessment did not pass; exit 2 produces a JSON
`error` instead of a report when required inputs cannot be identified or
validated. Without `--output`, JSON is written to stdout. Never use the
checked-in empty trust store for an actual decision.

## Trust and review boundary

An administrator independent of the builder must provision and protect the
[trust store](../contracts/readiness-trust.schema.json), its referenced PEM
public keys, and the approved baseline bytes. `baseline_sha256` pins the exact
baseline file. Key IDs have a reviewer identity, authorized roles, and optional
`revoked_at`; key paths are relative to the trust-store directory. Use distinct
keys for trusted CI result producers, independent contract/exception
reviewers, and customer reviewers. The validator cannot enforce organizational
separation, verify real-world identity, consult an external revocation service,
or protect a trust store that the builder can edit. Update revocations promptly
and protect the trust store outside the assessed project and PR.

Each decision is a signed payload and base64 signature in the
[input](../contracts/readiness-input.schema.json). The signature is
RSA/ECDSA-SHA256 as verified by `openssl dgst -sha256 -verify`. Sign the
UTF-8 bytes of the payload serialized as
`json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
with no trailing newline. For example, after preparing those canonical bytes:

```sh
openssl dgst -sha256 -sign reviewer-private.pem -out decision.sig canonical-payload.json
```

Base64-encode `decision.sig` into the envelope's `signature`. Keep private
keys outside the project, CI logs, and artifacts. A payload includes `key_id`,
`kind`, `decision`, `reference`, `decided_at`, `expires_at`, and `scope`.
Decisions must be signed by a currently authorized role, unrevoked at
`assessed_at`, and satisfy `decided_at <= assessed_at < expires_at`. Multiple
valid decisions for the same kind and scope are ambiguous and fail closed.
The assessment timestamp is an **as-of input**, not a trusted clock: an
operator must supply a trustworthy current time for release decisions and
prevent backdating. Historical assessments do not establish current readiness.

Scopes are exact objects, not partial matches:

| Kind / role | Decision | Scope |
| --- | --- | --- |
| `contract` | `approved` | `contract_sha256` of exact approved bytes. |
| `result` | `attested` | `contract_sha256`, `target_maturity`, `source_revision`, `environment`, `check_id`, `result_sha256`. |
| `classification` | `approved` | `baseline_sha256`, `contract_sha256`, `requirement_id`, `changes`; production-control changes instead use `production_controls: true`. Requires `rationale`. |
| `applicability` | `approved` | `contract_sha256`, `target_maturity`, `source_revision`, `environment`, and `requirement_id`; domain exceptions instead use `domain`, `reason`, `reference`, and `reviewer` from the contract. Requires `rationale`. |
| `risk` | `accepted` | `requirement_id`, sorted adverse `check_ids`, `requirement_status`, `contract_sha256`, `target_maturity`, `source_revision`, `environment`, `finding_sha256`. Requires `rationale` and `compensating_controls` (possibly empty). |
| `customer` | `approved` | `contract_sha256`, `target_maturity`, `source_revision`, `environment`, `results_sha256`. Requires `rationale`. |

`result_sha256` hashes the canonical complete normalized result object.
`finding_sha256` hashes the canonical `check_results` array for the adverse
requirement in an initial report. `results_sha256` hashes the canonical
`results` array, including any risk decisions. Review the initial report and
its evidence before signing; rerun with the decision. Any changed finding or
scope requires another decision. The report's `extensions.validator` records
diagnostics and verified decision references/scopes for human review.

The classification `changes` array is sorted. It includes removed requirements
or checks, relaxed blocking gates or evidence policies, changes to any
previously critical requirement, criticality downgrades, changes to
not-applicable, and changes to baseline production controls. The initial
contract must itself have independent signed approval; the baseline is
independently pinned, not supplied by an untrusted builder.

## Normalized results and evidence

Every `results` entry names one contract `check_id`, its actual `outcome`
(`passed`, `failed`, or `unverified`), optional `reason` and
`implementation_refs`, and an `evidence` array. The producer maps each
specific local test/evaluation to a contract check; unknown or duplicate IDs
make the gate unverified. Do not map a whole passing test run to checks it did
not actually exercise. A trusted producer must sign each complete result using
the `result` scope above; an unsigned or modified passing result is unverified.

Evidence entries have `kind`, relative `reference`, `revision`, `environment`,
`recorded_at`, and SHA-256. Paths must resolve beneath `--evidence-root`; URLs,
absolute paths, and escapes are rejected. Each expected evidence type must be
present, and **every** supplied artifact must be readable, digest-matched,
scope-matched and fresh. Age zero through the contract's maximum age is
accepted; future timestamps are not. Files are limited to 5 MiB. At least one
`test_report`, `evaluation_result`, or `security_report` is required. Each
artifact with one of those kinds must be a JSON object whose fields corroborate
the normalized result:

```json
{"check_id":"CHECK-APPROVAL","outcome":"passed","source_revision":"the-commit",
 "environment":"local-test","recorded_at":"2026-01-02T00:00:00Z"}
```

The normalizer must derive that object and the outcome from the actual
per-check runner output; this repository does not yet include a JUnit or
evaluation adapter. Other artifact types are checked for bytes, scope and
freshness, not semantically interpreted. An `approval_record` artifact is not
a signed human authorization. Digests and signatures bind what the producer
reported; they do not prove that the claimed time, revision, environment, test
execution, or contents are truthful. Protect the producer and retain underlying
runner logs, trace IDs, errors, and privacy-safe supporting artifacts for
debugging. Do not use a builder-controlled key to attest its own unreviewed
claims. These integration and operational controls remain future work.

An explicit failed result stays failed even if its evidence is invalid; a
purported pass with missing, invalid, stale, or mismatched evidence becomes
unverified. Prototype may pass with disclosed non-blocking gaps. Production
requires appropriate blocking security, integration, operations and evaluation
checks or verified applicability decisions, plus scoped risk acceptance for
every non-blocking adverse result. Customer validation additionally requires
an approval binding the final results. No critical or blocking failure is
waived. Explain gaps in the report's disclosure arrays; preserve per-check
reasons and evidence.

## Repository protection

`.github/CODEOWNERS` identifies protected paths but does not enforce anything
by itself. Configure GitHub branch rules/rulesets to require pull requests,
independent code-owner review, and the `contracts` job as a required check;
protect the workflow, contracts, golden cases, tests, validator, CODEOWNERS,
trust configuration, and branch-rule administration from builders. Limit
bypass and verify the actual settings and check names. Repository rules and
CI status must be inspected independently; merely committing a workflow or
CODEOWNERS is not evidence that protections are active.
