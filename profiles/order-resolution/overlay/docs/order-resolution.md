# Order Resolution profile

This generated application owns an explicit Order Resolution implementation on
the copied MAF workflow blueprint. It has no import, mount, symlink, or runtime
read back to the blueprint repository.

## Runtime selection

Compose selects
`app.order_resolution.application:build_application` by default. The profile
retains the copied FastAPI authentication and authorization boundary, React
client, PostgreSQL business store, local MAF checkpoint host, and canonical
backend and frontend lock files.

## Request shape

Submit an `order` object and exactly one `policy_evidence` item. The synthetic
profile accepts `late_delivery` with an integer `delay_days` greater than 3, or
`damaged_item`. Amounts are decimal USD strings. Evidence must name the
applicable `POLICY-LATE@1` or `POLICY-DAMAGED@1` policy and explicitly mark
`current`, `applicable`, and `digest_valid` as `true`.

The application calculates and persists a versioned proposal before workflow
execution. Low-risk late-delivery refunds complete through the native MAF
workflow without a human pause. High-value refunds and replacement shipments
create a native approval request and use the existing authenticated,
server-authorized decision endpoint.

Missing, conflicting, or invalid policy evidence creates a persisted terminal
failed case with its explicit failure code. It creates no proposal, native
pause/checkpoint, decision, action claim, or effect. Other malformed or
unsupported request data remains an HTTP validation failure.

The action targets a synthetic PostgreSQL destination and records the verified
resolution projection in `order_resolution_actions`. Its effect key binds the
case, proposal version, action, and destination; conflicting reuse fails
closed. One bounded deadline is shared by authoritative observation and send.
A timeout or process exit after send is an unknown outcome, so recovery
observes the destination before retrying. This proves only the generated
synthetic adapter and is not evidence for a real refund or shipment service.

Local regression coverage exercises a lost hosted acknowledgment across a
new PostgreSQL store, a concurrent first-use journal claim, legacy-unbound
hosted and local approvals, and local crash/resume recovery. A stored
self-approval is also rejected at the effect boundary. These tests use
synthetic identities and a disposable database; they do not prove downstream
transport or cloud isolation.

## Verification assets and current integration limits

`verification/scenarios/order-resolution/acceptance-contract.json` and
`verification/scenarios/order-resolution/golden-cases.json` are copied into
this project at generation time with
`verification/tests/test_order_resolution_contract.py`; they are not read by
the runtime. The canonical nine-case fixture and its acceptance test remain
owned by merged PR #42 and are not duplicated in the profile.

Run `python -m app.order_resolution.migrations upgrade` with the schema-owner
database identity before application startup. Runtime startup validates the
profile schema and does not create it. PostgreSQL owns requests, proposals,
decisions, effect state, audit records, and the synthetic downstream; native
MAF checkpoint files remain separate and unmodified.

The generated runtime adapter executes all nine canonical scenarios without
reading expectations into runtime output. Focused process tests terminate
before and after decision persistence and synthetic send, then recover with a
new application lifecycle. Real downstream idempotency, authoritative
reconciliation, and transport deadline enforcement remain unverified and
blocked by [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32).

The generated project also owns
`backend/evaluations/order-resolution-0.1.0.json`, native MAF deterministic
evaluators, and `tests/order_resolution_evidence_runner.py`. The dataset groups
the nine canonical scenario IDs without copying their expected outcomes. The
runner reads the copied golden cases, executes the real generated adapter,
evaluates separate `business_outcome` and `technical_execution` payloads
through `LocalEvaluator` and `evaluate_agent()`, and normalizes results with
the application-owned #39 readiness mapper.

Run the local evidence path after starting an isolated PostgreSQL database:

```text
python -m tests.order_resolution_evidence_runner \
  --verification-root ../verification \
  --output ../verification/evidence/order-resolution \
  --revision <git-sha> \
  --environment <environment>

python -m readiness \
  --contract scenarios/order-resolution/verification-contract.json \
  --baseline scenarios/order-resolution/verification-contract.json \
  --input evidence/order-resolution/readiness-input.json \
  --trust scenarios/order-resolution/example-trust.json \
  --evidence-root evidence/order-resolution \
  --output evidence/order-resolution/readiness-report.json
```

Use a new empty output directory for each run so evidence from different
revisions or environments cannot be combined.

The empty example trust root intentionally leaves the independent report
`unverified`: local digests are not producer attestation. Real provider/model
quality, actual browser evidence, trusted provenance, hosted execution, and
real consequential downstream effects are not established by this path.
