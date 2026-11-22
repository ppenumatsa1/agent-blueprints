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
Evaluation/readiness work remains separate in draft PR #43.
