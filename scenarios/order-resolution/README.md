# Order Resolution executable acceptance contract

This versioned synthetic fixture makes the normalized cases from the
[Order Resolution specification](../../docs/order-resolution-specification-proposal.md)
executable without adding a framework runtime. The contract identity is
`order-resolution-spec/0.1.0`, and the golden set contains exactly `ORS-001`
through `ORS-009`.

The [acceptance contract](acceptance-contract.json) defines the exact synthetic
orders, policies, reviewer authority, evidence rule, idempotency key, currency,
and rounding rule. The [golden cases](golden-cases.json) keep normalized
`business_outcome` assertions separate from `technical_execution` assertions.
Framework implementations must preserve the business outcomes while adding
their native checkpoint identifiers and implementation-specific evidence.

Amounts are decimal USD strings. `partial_refund_10` is calculated once as
10% of the order amount and rounded once to two decimal places using
round-half-up, producing exactly `7.90` for `ORDER-LOW` and `18.50` for
`ORDER-HIGH`. The damaged-item proposal is exactly one
`replacement_shipment`. Missing, conflicting, and invalid evidence fail
explicitly with `policy_evidence_missing`, `policy_evidence_conflict`, and
`policy_evidence_invalid`.

Run the static contract checks with:

```text
python -m unittest discover -s tests -p test_order_resolution_contract.py -v
```

The application acceptance test is skipped unless
`ORDER_RESOLUTION_ADAPTER` selects an executable. The adapter must read one
JSON object from stdin containing `scenario_set` and `case`, then emit JSON
with separate `business_outcome` and `technical_execution` objects. Expected
fixture fields are matched recursively; implementations may add native
checkpoint identity, trace, and evidence fields. Each invocation must execute
the commands rather than echoing fixture expectations. A skipped adapter test
is not framework conformance evidence.

This fixture is synthetic and non-authoritative. It does not authenticate a
person, approve the contract, implement a blueprint, execute a real refund or
shipment, prove native checkpoint behavior, or authorize deployment.
