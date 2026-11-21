# Testing and evidence

Install dependencies as described in [setup](setup.md). Set
`MAF_TEST_DATABASE_URL` to a disposable, isolated PostgreSQL database. From
`backend`, run:

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest -v tests.test_core tests.test_security tests.test_evidence_runner tests.test_telemetry tests.test_migrations
```

Tests create and drop isolated schemas and roles; the test identity requires
`CREATEROLE`. They fail if the database is unavailable; do not point them at
production data. They use synthetic
identities and no Azure credentials or model. They exercise authorization,
native workflow and actual worker termination after decision persistence and
after a database action commits. They do not prove live Entra/OBO, external
effect exactly-once delivery, or hosted recovery.

From `frontend`:

```text
npm ci
npm test
npm run build
npm run check-csp
```

The automated accessibility check does not assess color contrast. The CSP
check compares the inline theme script against the reverse-proxy policy.

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
