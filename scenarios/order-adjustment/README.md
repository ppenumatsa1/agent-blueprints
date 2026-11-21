# Synthetic order adjustment: acceptance contract

This is a fictional, non-destructive order adjustment. No payment, customer
system, model, or Azure resource is used. A request over 100 units must pause
for an authorized, case-scoped decision. Approval permits one simulated action;
rejection or an unauthorized decision permits none. A restart or replay must
not lose the decision or duplicate the action. Operators must be able to
explain the outcome using the case, amount, policy, decision, and correlation
ID without exposing the secret canary or private reasoning.

The [verification contract](verification-contract.json) defines the stable
requirements, checks, evidence types, freshness, and maturity gates. The
[golden cases](golden-cases.json) specify pending, approved, rejected,
unauthorized, wrong-case, duplicate, restart, action-failure, and optional-hint
outcomes **before an
application exists**. The optional hint is explicitly non-blocking; its failure
or absence must remain visible. All amounts and identities are synthetic.

The application acceptance test is deliberately skipped until a real adapter is
provided. Set `SCENARIO_ADAPTER` to an executable that reads one case's `input`
JSON from stdin and emits JSON with `state`, integer `action_count`, `decision`,
`explanation`, nonempty `correlation_id`, and any additional fields specified
by the case (such as `hint`). Each invocation must exercise the
named steps, including real restart and simulated failure, against isolated
state; it must not simply return the expected fixture. Run
`python -m unittest discover -s tests -p test_golden_scenario.py -v`.
The fixture's fact matching is a minimum deterministic rubric, not proof that
an explanation has no unsupported claims; later evaluation must check that
against the recorded facts.

The scenario contract is a proposal awaiting an authorized human review of its
exact bytes. The checked-in `example-trust.json` has no keys, and
`example-input.json` has neither results nor decisions; they intentionally
produce **unverified**, not an approval or readiness claim.
