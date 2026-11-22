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

The action is deliberately database-only: it records the synthetic resolution
in `order_resolution_actions` in the same PostgreSQL transaction as the action
ledger. It does not call a fulfillment or payment service and is not evidence
for a consequential external effect.

## Verification assets and current integration limits

`verification/scenarios/order-resolution/acceptance-contract.json` and
`verification/scenarios/order-resolution/golden-cases.json` are copied into
this project at generation time with
`verification/tests/test_order_resolution_contract.py`; they are not read by
the runtime. The canonical nine-case fixture and its acceptance test remain
owned by draft PR #42 and are not duplicated in the profile.

The baseline application initializes its profile table at startup. Versioned
migrations, effect-ledger integration, and crash-window durability are
downstream dependencies from draft PR #41. Evaluation adapters and full
nine-case verification are downstream dependencies from draft PR #43. The
source generator merges those profile-root backend and verification assets
after this overlay. Their absence must remain visible; they are not replaced
with synthetic success.
