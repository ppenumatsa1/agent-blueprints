# Azure/Foundry Workstream D readiness

This workstream defines observability, evaluation, browser automation, hosted
failure injection, and independent release-evidence validation for the
generated MAF Order Resolution application. It does not provision or deploy
Azure resources, change RBAC, perform consequential business transactions, or
turn credential-free CI into Azure evidence.

The authorized source baseline is
`886b628fdea02f9089c385b4ed0fc46d90f375e8`. Its before-state CI
[run 45069723947](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45069723947)
passed the six existing jobs. Workstream D preserves those jobs and adds a
seventh generated-project Chromium job. Any changed head needs a new exact-head
run; the baseline run does not validate this workstream.

## Correlation and privacy contract

Automatic MAF content instrumentation remains disabled. The backend creates
manual allowlisted spans and metrics across the API, Foundry invocation,
native workflow, model, tool, and PostgreSQL boundaries.

| Field | Contract |
| --- | --- |
| `blueprint.request.id` | Application-generated UUID for one request attempt. |
| `blueprint.case.id` | Application-owned case UUID when a case is known. |
| W3C trace/span IDs | Correlate technical execution without becoming business authority. |
| `blueprint.agent.version` | Safe configured agent package/version identifier. |
| `blueprint.deployment.revision` | Exact immutable deployment revision under test. |
| technical status | `succeeded`, `failed`, `interrupted`, `retrying`, or `unknown`. |
| business outcome | Separate `created`, `pending`, `approved`, `rejected`, `completed`, `failed`, or `unknown`. |

Model provider/name, token counts, latency, errors, retries, and allowlisted
tool names are operational attributes. Metrics use bounded low-cardinality
labels. The contract excludes prompts, completions, authorization headers,
tokens, SQL, exception messages, arbitrary baggage, and raw tool or business
payloads. `contracts/telemetry-event.schema.json` rejects unknown fields, and
the examples demonstrate valid and invalid records.

Application Insights verification queries only exact
request/case/trace/agent-version/deployment-revision tuples emitted by the
hosted failure run. It uses a bounded explicit ingestion retry and does not
inspect content fields.

## Evidence and readiness contract

`contracts/release-evidence.schema.json` and `readiness/release.py` define
three independent dimensions with `passed`, `failed`, `blocked`, and
`unverified` states. This manifest is explicitly
`diagnostic_non_authorizing`: it preserves exact artifact state and binding,
but it cannot authorize production.

| Dimension | Pass boundary |
| --- | --- |
| Implementation | Exact-source local tests plus independently hashed evaluation artifacts. |
| Azure runtime | Exact source, environment, and deployment revision with active revision, hosted execution, real-provider evaluation, live browser, failure injection, and telemetry-query evidence. |
| Production | Always blocked in this diagnostic manifest; authorization belongs to the independently administered readiness validator. |

Schema validation checks shape only. The validator also reads each local
artifact, verifies SHA-256, revision/environment binding, timestamps, required
check IDs, and required evidence kinds. Azure runtime cannot pass without an
exact deployment revision. Production cannot pass from this release manifest. Production authorization
must run `python -m readiness` with the approved verification contract,
baseline-pinned trust store, signed result attestations, and any scoped,
unexpired risk decisions. Critical and security-critical blocking checks are
not waivable through the release manifest or a self-authored `human_review`
artifact.

The pre-cloud state is deliberately:

| Dimension | State | Reason |
| --- | --- | --- |
| Implementation | `unverified` | Becomes passed only from a successful exact-head CI artifact set. |
| Azure runtime | `unverified` | No deployed revision or real hosted evidence exists in this workstream. |
| Production | `blocked` | Runtime, security, cost, and scoped human review evidence are absent. |

## Credential-free local and CI checks

Run root contract and evidence validation in an isolated Python environment:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Run the backend checks with the locked environment:

```powershell
python -m pip install uv==0.9.26
uv sync --locked --project .\blueprints\maf\workflow\backend
uv run --locked --project .\blueprints\maf\workflow\backend `
  python -m unittest -v `
  tests.test_telemetry `
  tests.test_evaluation `
  tests.test_hosted_failure_runner
uv run --locked --project .\blueprints\maf\workflow\backend `
  ruff check .\blueprints\maf\workflow\backend
uv run --locked --project .\blueprints\maf\workflow\backend `
  ruff format --check .\blueprints\maf\workflow\backend
```

Instantiate the profile outside the source checkout and run its copied tests:

```powershell
$generated = Join-Path $env:TEMP "maf-order-resolution-generated"
python .\scripts\instantiate_maf.py $generated --profile order-resolution
uv sync --locked --project "$generated\backend"
uv run --locked --project "$generated\backend" `
  python -m unittest discover -s "$generated\backend\tests" -v
```

Run frontend unit, build, CSP, and actual local Chromium checks:

```powershell
Set-Location .\blueprints\maf\workflow\frontend
npm ci --registry=https://packagefeedproxy.microsoft.io/npm/ --no-audit --no-fund
npx playwright install chromium
npm test
npm run build
npm run check-csp
npm run e2e:local
```

These commands produce implementation evidence only. They do not authenticate
to Azure, call a real model, validate a hosted revision, or prove cloud
ingestion.

## Explicit live validation workflow

`.github/workflows/cloud-validation.yml` is manual and non-deploying. It
requires an already successful exact-head CI run and an immutable deployment
evidence artifact produced by the deployment workstreams.

The `maf-independent` producer explicitly checks out the pull-request head
SHA (or `github.sha` on `main`) before recording `SOURCE_REVISION`. The default
pull-request merge checkout is not accepted as exact-source evidence: its
artifact revision would differ from the deployment source and the release
evidence builder must reject it.

The deployment health verifier requires the public health endpoint to return
exactly `204` and an unauthenticated protected API request to return exactly
`401`; `200` health or `403` unauthenticated responses do not pass.

The corrected exact-head producer and health-verifier contracts passed all
seven PR #49 jobs at
`d516410f3c63472152b13f28f65081d4006ec04b` in run `45152016819`.
Independent download inspection confirmed all 12 revision-bound implementation
evidence documents use that exact source revision.

Example:

```powershell
gh workflow run cloud-validation.yml `
  -f source_revision=<exact-commit> `
  -f deployment_revision=<immutable-release-id> `
  -f agent_version=<exact-agent-package-version> `
  -f evidence_environment=<environment-id> `
  -f ci_run_id=<successful-exact-head-ci-run> `
  -f deployment_run_id=<successful-deployment-run> `
  -f expected_backend_revision=<aca-revision> `
  -f expected_frontend_revision=<aca-revision> `
  -f expected_hosted_version=<hosted-agent-version> `
  -f base_url=https://<generated-frontend-host>
```

The `azure-foundry-validation` GitHub environment must provide:

- secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
  `AZURE_SUBSCRIPTION_ID`, `E2E_STORAGE_STATE_JSON`, and
  `E2E_SESSION_STORAGE_JSON`; and a short-lived, narrowly scoped
  `MAF_REAL_PROVIDER_AUTH_JSON`;
- variables `AZURE_LOG_ANALYTICS_WORKSPACE_ID`, `E2E_REVIEWER_ID`,
  a synthetic `E2E_PAYLOAD_JSON`, `E2E_ENTRA_TENANT_ID`,
  `E2E_ENTRA_SPA_CLIENT_ID`, and `E2E_ENTRA_API_APP_ID_URI`;
- variables `MAF_REAL_EVALUATION_PROVIDER`,
  `MAF_REAL_EVALUATION_MODEL`, `MAF_REAL_EVALUATOR_FACTORY`,
  `MAF_REAL_RESULT_FACTORY`, and
  `MAF_REAL_EVALUATION_MINIMUM_SCORE`;
- variable `MAF_HOSTED_FAILURE_ADAPTER`.

`AZURE_LOG_ANALYTICS_WORKSPACE_ID` may be the workspace ARM resource ID emitted
by deployment or the Log Analytics customer/workspace GUID. The correlation
verifier resolves an ARM resource ID to the query GUID before issuing KQL.

The provider evaluator, live-result producer, and failure adapter use explicit
`module:callable` factories. The result producer must call the exact deployed
hosted application/provider and return all nine revision-bound ORS outcomes;
canonical expected outputs are never substituted as actual output. The
real-provider gate has no synthetic fallback. The hosted adapter must implement
the protocol in
`blueprints/maf/workflow/backend/tests/hosted_failure_runner.py`, expose exact
source/deployment revisions, and support only bounded synthetic faults. A
missing capability is `blocked`; a failed observation is `failed`; neither is
converted to success.

The browser gate restores explicit Playwright cookie/local-storage state and
an explicit MSAL session-storage snapshot only after npm and browser
installation. The snapshot must match the configured tenant, SPA client, and
API application URI. Live traces, screenshots, and videos are disabled so
authenticated state is not uploaded. If an authenticated state is unavailable
or the protected request/approval flow fails, browser authentication remains
`unverified`.

Dependency installation runs without browser/provider secrets and without
Azure OIDC permission. The workflow restores short-lived authentication files
only after locked dependencies are installed, removes those files on every
outcome, and scopes `id-token: write` to the telemetry-query job, which installs
no application dependencies.

The workflow expects Agent B's `azure-foundry-deployment-evidence` artifact to
contain `backend-revisions.json`, `frontend-revisions.json`, and
`hosted-agent.json`. Container images must be digest pinned, exactly one
healthy revision must receive 100 percent traffic, and the hosted version must
be active and revision bound. The workflow never changes traffic or activates
a revision.

The official Foundry region capability reference is
[limits, quotas, and regions](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions).
East US 2 is the current selection input for Responses API, Agents, Browser
Automation, Function, MCP, OpenAPI, and an Agent Service-compatible
`gpt-4.1-mini`; live subscription quota, capacity, and deployment support
remain unverified until Agent B records exact read-only and deployment
evidence.

The confirmed East US 2 `gpt-4.1-mini` GlobalStandard meter inputs are
$0.0004 per 1,000 input tokens and $0.0016 per 1,000 output tokens. They are
pricing inputs, not production cost evidence by themselves. Agent B must attach
the timestamped exact Azure Retail Prices API meter response and bind it to the
deployed model SKU, region, token usage, and source/deployment revisions before
the required `cost_report` can pass.

## Hosted failure scenarios

The failure run records all scenarios independently and performs no hidden
retry:

1. API restart with persisted identity.
2. Hosted interruption with host-managed resume/reconciliation.
3. PostgreSQL transient read failure and recovery.
4. Tool timeout after an effect, retained as unknown until reconciliation.
5. Duplicate approval.
6. Stale approval.
7. Unauthorized approval.
8. Lost create acknowledgment, retained as unknown without blind replay.
9. Unknown-outcome retry refusal followed by authoritative reconciliation.

All effects remain synthetic. The harness requires distinct technical and
business outcomes and verifies no duplicate effect.

## Dependencies on Agents A-C

| Workstream | Required output for Workstream D |
| --- | --- |
| Agent A - native Foundry host | Published hosted version/image evidence; native host-managed pause/resume; Responses conversation binding; lost-ack reconciliation; an adapter-compatible hosted test surface; no custom whole-workflow checkpointing. |
| Agent B - infrastructure/operations | Exact deployment revision, digest-pinned active ACA revisions, hosted-agent inspection, frontend URL, Log Analytics workspace, workload-identity login inputs, and the immutable deployment evidence artifact. Region/quota/capacity evidence must match the deployed region. |
| Agent C - application security/data | Authenticated reviewer browser flow, strict caller/case/conversation authorization, explicit hosted-client mode, Azure PostgreSQL TLS/auth/pools/migrations, restart behavior, synthetic effect ledger, and bounded fault-injection hooks that preserve unknown outcomes and idempotency. |

Until those outputs are integrated and a live manual workflow completes,
Azure runtime remains `unverified`. Production remains `blocked` until
independent security, cost, and scoped human risk-acceptance evidence is
attached to the same source and deployment revisions.

## Live acceptance attempt — 2026-11-23

Exact source `c63b48afa4179a3d92c286aeb6ae339e16ece275` passed all seven CI
jobs in run `45158642321`; all 12 downloaded revision-bound implementation
documents name that exact source. Read-only runtime checks passed for API
revision `aborsfoundpv2n45-api--final-2ef5161` and web revision
`aborsfoundpv2n45-web--final-9d5a663`, each healthy, running, digest pinned,
and receiving 100 percent traffic. The API returned `/healthz` `204`, rejected
unauthenticated reads and submissions with `401`, and logged a successful
managed-identity `database.connect`. The web returned root `200` and proxied
health `204`. Hosted version `order-resolution:1` remained active with the
documented agent-scoped consumer assignment and `Hosted.Workflow.Invoke`.

The remaining live suite did not pass and was not replaced with fixtures:

- positive synthetic workflow and ORS-001–009 were `blocked` because the
  operator could not obtain a delegated API token (`consent_required`);
- direct hosted invocation was `blocked` because the operator identity lacked
  the agent session-create action;
- authenticated Chromium was `blocked` because no short-lived Playwright state
  existed and browser access to the deployed origin was denied;
- failure injection was `blocked` because no reviewed live adapter or bounded
  cloud fault-control surface exists;
- provider evaluation was `blocked` because no reviewed live result/evaluator
  factories or authentication were configured;
- exact telemetry correlation `failed`: 13 recent request/dependency rows had
  zero request/case-correlated rows and reported agent `0.1.0` with deployment
  `local-unversioned`, not hosted version `1` and an immutable deployment
  revision; and
- the normalized deployment-evidence gate `failed` because the retained values
  file omitted final hosted fields and no deployment-run artifact was
  available.

No refund, shipment, or other consequential effect was executed. Production
and merge authorization remain blocked.
