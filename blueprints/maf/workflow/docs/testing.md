# Testing and evidence

Install dependencies as described in [setup](setup.md). Set
`MAF_TEST_DATABASE_URL` to a disposable, isolated PostgreSQL database. From
`backend`, run:

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest -v tests.test_core tests.test_external_effect tests.test_security tests.test_evidence_runner tests.test_telemetry tests.test_migrations tests.test_extensions tests.test_evaluation
```

Tests create and drop isolated schemas and roles; the test identity requires
`CREATEROLE`. They fail if the database is unavailable; do not point them at
production data. They use synthetic identities and no Azure credentials or
model. Source and generated CI run the same suite: authorization, native
checkpoint recovery, privacy-safe telemetry, migrations, evidence
normalization, and actual worker termination after decision persistence and
after a database action commits. They do not prove live Entra/OBO, external
effect exactly-once delivery, or hosted recovery.

The external-effect tests use a separate durable SQLite database as a
synthetic downstream that independently hashes and atomically stores both a
key-bound request and a representative effect. Its authorizer applies a
fixed synthetic policy to the exact request, not a real human authorization.
The tests exercise authorization,
rejection, concurrent sends and retries, conflicting bindings, ambiguous
reconciliation, bounded SQLite lock waits, failures before the effect and a
timeout after the effect but before acknowledgment, and worker termination
before the local ledger commits. A timeout does not imply absence; retries
require request-bound downstream reconciliation. Conflicting database
decisions race in synchronized threads; each crash barrier verifies the exact
downstream effect before and after recovery. They do not prove any
real service's durability, retention, authorization, or reconciliation
guarantees; the fixture's policy is not a production authorizer.

The official PostgreSQL container's initialization server can accept Unix
socket connections before its final TCP server starts. Source/generated CI
waits and the Compose health check probe loopback TCP with bounded failure.
Issue [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38)
records the transient socket-ready/TCP-unready observation on disposable
PostgreSQL 16.15 and 17 and an initial failed `createdb`; a TCP-gated retry
passed 72 source and 72 generated backend tests on historical head `8b3c357`.
These local checks do not establish managed PostgreSQL readiness.

From `frontend`:

```text
npm ci
npm test
npm run build
npm run check-csp
```

The automated accessibility check does not assess color contrast. The CSP
check compares the inline theme script against the reverse-proxy policy.

From the blueprint or generated project root, run offline infrastructure
checks with Python 3.12 and Bicep 0.49.2 or newer:

```text
python infra/validate.py
python -m unittest discover -s infra/tests -v
```

These compile and lint local modules and inspect committed examples and
security configuration without Azure credentials. They do not prove role
propagation, endpoint behavior, connectivity, or a successful deployment.
See the [infrastructure guide](../infra/README.md).

In an independently generated project, the copied `verification` directory
contains the verifier, contracts, synthetic fixture, and its own
requirements. Set `SCENARIO_ADAPTER` to the absolute path of
`backend/tests/order_adjustment_adapter.py`, then from `verification` run:

```text
uv run --locked --project ../backend python -m unittest discover -s tests -v
```

The readiness validator guide at `verification/docs/readiness-validator.md`
exists in generated projects, not the source blueprint alone. The fixture
runner and its command are described in the [project README](../README.md).
The empty trust store yields **unverified**, not authorization. Synthetic
approval is not human approval; fixture explanation and hint comparisons do
not prove agent-generated explanations or browser end-to-end behavior.
Schema validity alone is not a release gate. Retain failed and unverified
results as such.

## Evaluation extension tests

`tests.test_evaluation` exercises explicit versioned synthetic dataset and
rubric configuration through MAF's native `@evaluator`, `LocalEvaluator`, and
`evaluate_agent()` path, then checks inclusive configured-threshold edges,
multiple criteria per readiness check, trace mapping, missing and unavailable
results, failed/canceled/unknown native run statuses, malformed and oversized
thresholds/scores, unknown and duplicate
configured check IDs, unknown evaluator criteria, unknown and duplicate
observations, out-of-case scores, and propagated evaluator failures. Native
aggregate item failure is mapped to the evaluator score that failed when
available, without marking unrelated passing criteria as failed.
The source test derives the complete known-check tuple from the repository's
selected verification contract; the generated-copy test derives it from that
copy's `verification/scenarios/order-adjustment/verification-contract.json`.
The clearly synthetic fixture's check IDs must be in that derived tuple, and a
matching but unknown dataset/rubric ID is rejected before evaluator invocation.
This tuple is not trusted authorization. Native evaluation uses explicit
synthetic responses and does not invoke a live model or establish evaluation
quality. Source and generated CI run the same tests; the synthetic results do
not produce or attest readiness evidence or browser behavior.
