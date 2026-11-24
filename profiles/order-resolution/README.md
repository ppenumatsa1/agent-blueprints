# Order Resolution generation overlay

This explicit profile is copied over the independently owned MAF workflow
blueprint by `scripts/instantiate_maf.py --profile order-resolution`.
It is application source, not a registry, plugin system, specification
compiler, or shared runtime dependency.

The overlay adds deterministic Order Resolution validation and proposal rules,
database-owned action records, a native `WorkflowBuilder` workflow that
auto-completes low-risk proposals and pauses approval-required proposals, and a
profile-specific React renderer. It reuses the copied FastAPI, PostgreSQL,
Compose, authentication, authorization, checkpoint, and lock-file
infrastructure.

The canonical nine-case fixture is intentionally not duplicated here. The
generator copies `scenarios/order-resolution/acceptance-contract.json` and
`scenarios/order-resolution/golden-cases.json` from merged PR #42, together
with `tests/test_order_resolution_contract.py`. Explicit
`--order-resolution-contract`, `--order-resolution-cases`, and
`--order-resolution-test` paths remain available for isolated generator tests.

The generated integration tests exercise the real FastAPI boundary, native MAF
workflow/checkpoint host, and PostgreSQL state. The runtime adapter executes
canonical `ORS-001` through `ORS-009` from the generated verification assets
and derives separate business and technical results from API, checkpoint, and
database observations rather than fixture expectations.

The profile-root backend adds an explicit PostgreSQL migration, request and
proposal stores, atomic decision persistence, an effect ledger, authorization
audit records, and a synthetic downstream destination. Consequential effect
identity binds case, proposal version, action, and destination. Native MAF
continues to own workflow checkpoints.

Hosted generation adds a protected FastAPI service boundary at
`/api/internal/hosted/v1`. The hosted runtime authenticates with its managed
identity for the API audience and the fixed `Hosted.Workflow.Invoke` app role,
then uses case-bound start/resume, read/proposal, approval/decision,
effect-projection, and completion routes. Opaque hosted
caller/session/conversation values are bound to authoritative case principals,
and every mutation requires a durable case-bound idempotency key. The API UAMI
is the sole PostgreSQL runtime principal; the hosted runtime receives no
database URL, TLS setting, credential, or role. Foundry owns hosted
conversation/checkpoint state, so hosted case checkpoint columns remain null.

The profile-root evaluation layer consumes the copied canonical golden cases;
it does not duplicate them. It runs deterministic business and technical
comparisons through MAF's native `Evaluator`, `LocalEvaluator`, `@evaluator`,
and `evaluate_agent()` APIs, then passes native results to the merged #39
readiness mapper. The generated evidence runner executes all nine scenarios,
writes revision-bound local artifacts, and invokes the independent readiness
validator. Deterministic results may pass locally while model quality, browser
evidence, and trusted producer provenance remain unverified.

The generated `hosted-agent` package is a separate Foundry Responses entry
point. It hosts a fresh native MAF workflow per request, uses the public
Foundry hosting checkpoint provider, and never attaches the API's local
`FileCheckpointStorage`. `HttpHostedBusinessStore` calls the protected API with
the hosted platform identity to verify a conversation binding that an
authenticated application command already established. The hosted platform
user is the API workload, not the human actor, and opaque Foundry correlation
cannot create owner/reviewer authority. Missing or mismatched owner/reviewer
bindings fail before any business read or write. The narrow
`HostedBusinessStore` lifecycle provides stable opaque hosted request
correlation, hosted decision claim, idempotent action, and business completion.
Normal hosted API composition loads
`order_resolution_hosted.bridge:build_workflow_host`, passing settings, the
application store, its authenticated-human authority binding adapter, and the
durable operation journal. That bridge creates/reconciles the server-selected
conversation, prebinds the authenticated owner or reviewer before Responses
dispatch, omits caller-supplied `agent_session_id` so Foundry owns the stable
session associated with the conversation, and exposes only async
`start(case_id, actor)` and `resume(case_id, actor, decision_command)`. There is
no generic `/runs` fallback. An identical authorized terminal resume reuses the
acknowledged operation without another Responses dispatch; conflicting intent
or an unauthorized actor fails closed.
The generator copies only the API bridge/client into
`backend/order_resolution_hosted` with a non-eager initializer and adds that
directory to the existing backend Docker context. The API does not import the
sibling hosted-agent source or install the hosting SDK; parity tests require
the backend and hosted copies to remain byte-identical.
Foundry still owns native checkpoint state; the HTTP contract carries no
checkpoint bytes or fabricated local checkpoint IDs. The copied
`scripts/foundry/publish_order_resolution_hosted.py` packages the generated
backend and hosted package for source-code deployment; it does not provision
resources or assign RBAC. Publishing requires an explicit Foundry project
endpoint and resource ID plus the model deployment and protected internal API
endpoint, app scope, and timeout. The publisher injects only that allowlist;
the hosted container receives no database URL, PostgreSQL credential, TLS
root, or database identity setting.
The endpoint includes the frozen `/api/internal/hosted/v1` prefix, the scope is
the configured API application ID URI plus `/.default`, and the hosted version
identity receives only the `Hosted.Workflow.Invoke` application role.
The hosted requirements retain pinned `psycopg` only for the shared domain
model's runtime type import; hosted execution receives no DSN and opens no
database connection.
Its journal identity binds the target, agent name, archive, runtime, protocol,
entry point, model deployment, API target/scope/timeout, and hosted
configuration; a different reuse fails before create. Responses journals must
atomically distinguish a newly acquired claim from an existing pending record,
which is never replayed after restart or concurrency. After create, the
publisher uses the public version GET to return the hosted identity principal
and client IDs plus agent version identity before active readiness. External
authorization must grant that hosted identity only the protected API access it
needs, then rerun the same operation with `--require-active` without creating
another version. The API remains the sole PostgreSQL owner and performs the
idempotent prepare/decision/action/completion operations.

## Independent local verification

From the generated `backend`, use a disposable PostgreSQL database and select
the generated Agent A source explicitly so the loopback test does not skip:

```sh
export MAF_TEST_DATABASE_URL="<isolated-local-test-database-url>"
export ORDER_RESOLUTION_AGENT_A_SOURCE="$(cd ../hosted-agent/src && pwd)"
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests -v
```

Only the real-provider evaluation is intentionally skipped when
`MAF_REAL_EVALUATION_ENABLED` is unset. Do not enable it without separately
verified authorization, target isolation, credentials, and provenance. Local
loopback tests use synthetic tokens and local HTTP, not Azure.

Then install the generated `hosted-agent/requirements.txt` in the test
environment and run the complete Agent A suite, as CI does:

```sh
cd ../hosted-agent
uv pip install --python ../backend/.venv/bin/python -r requirements.txt
PYTHONPATH="$PWD/src:$(cd ../backend && pwd)" \
  ../backend/.venv/bin/python -m unittest discover -s tests -v
```

These are local SDK and fixture checks, not live model or Foundry validation.
From each generated frontend, run `npm test`, `npm run build`, and
`npm run check-csp` and, with Chromium installed, `npm run e2e:local`.
The base generated frontend additionally runs `npm run e2e:history` and
`npm run e2e:studio`. The optional-adapters browser tests retain evidence
display, failure isolation, and ordinary approval coverage; callback execution
remains disabled as an interim control, not completed isolated manual testing.
