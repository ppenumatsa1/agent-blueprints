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

AgentServer configures the supported Azure Monitor exporter and HTTP
instrumentation on one global provider before native MAF instrumentation is
enabled. The backend reuses its process-global provider, emits manual
allowlisted operational spans and metrics, and explicitly propagates W3C
context into the Foundry invocation. Sensitive-data and message-content
capture are forced off in both runtimes.

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
hosted failure run. For hosted start/resume phases it also requires one
connected span tree per OperationId, a real `invoke_agent` root, native
workflow/executor/message spans, application workflow-stage spans, API and
hosted service roles, durable conversation continuity, and an explicit
start-span link on resume. A separately captured Foundry trajectory artifact
must contain the same trace IDs. The verifier rejects raw message/content
properties, uses a bounded ingestion retry, and does not treat row presence as
correlation.

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
requires successful CI and deployment runs whose run metadata both name the
requested exact source commit. The CI run must be the repository's Readiness
validation workflow. The deployment run must also come from the exact trusted
workflow path configured in repository variable
`MAF_HOSTED_DEPLOYMENT_WORKFLOW_PATH`; an unset or mismatched path fails before
artifact download. The artifact is then checked against the requested
deployment/environment and active backend, frontend, and hosted agent
revisions.

The current checkout has no workflow that produces
`azure-foundry-deployment-evidence`, so the trusted deployment producer path
and artifact remain unverified. Do not populate the path variable until an
authorized producer exists and is reviewed.

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

Failure injection is a separate, destructive opt-in and defaults to `false`.
Only when the protected synthetic target is ready, add
`-f run_failure_injection=true` and
`-f failure_target_id=<exact-container-app-resource-id>` to the dispatch
command.

Repository variable `MAF_HOSTED_DEPLOYMENT_WORKFLOW_PATH` must be the exact
`.github/workflows/<file>.yml` or `.yaml` path of the reviewed artifact
producer. It is intentionally not guessed in this repository.

The `azure-foundry-validation` GitHub environment must provide:

- secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
  `AZURE_SUBSCRIPTION_ID`, `E2E_OWNER_STORAGE_STATE_JSON`,
  `E2E_OWNER_SESSION_STORAGE_JSON`, `E2E_REVIEWER_STORAGE_STATE_JSON`, and
  `E2E_REVIEWER_SESSION_STORAGE_JSON`; and a short-lived, narrowly scoped
  `MAF_REAL_PROVIDER_AUTH_JSON`;
- variables `AZURE_LOG_ANALYTICS_WORKSPACE_ID`, `E2E_OWNER_ID`, `E2E_REVIEWER_ID`,
  a synthetic `E2E_PAYLOAD_JSON`, `E2E_ENTRA_TENANT_ID`,
  `E2E_ENTRA_SPA_CLIENT_ID`, and `E2E_ENTRA_API_APP_ID_URI`;
- `MAF_LIVE_AUTHORIZED_ORIGIN`, independently configured by an authorized
  operator as the exact HTTPS origin of the trusted deployed frontend/API;
- variables `MAF_REAL_EVALUATION_PROVIDER`,
  `MAF_REAL_EVALUATION_MODEL`, `MAF_REAL_EVALUATOR_FACTORY`,
  `MAF_REAL_RESULT_FACTORY`, and
  `MAF_REAL_EVALUATION_MINIMUM_SCORE`.

The dispatch `base_url` must be that origin, without a path, query, user info
or fragment. The Python acceptance client rejects all redirects, including
same-origin redirects. The browser injects session storage only at the
authorized origin, including in frames; supplied browser storage state must
contain no cookies and no other origin. Cookies cannot be restricted to a
port, so even secure cookies are rejected. Curate state accordingly; do not
disable these checks to make a run pass. Direct local use must separately
set `MAF_LIVE_AUTHORIZED_ORIGIN` for the Python client and
`E2E_AUTHORIZED_ORIGIN` for the browser. The configured origin and endpoint
must be trusted; these checks do not attest the deployment, protect against
a compromised authorized origin or trusted proxy, or verify Entra login.

The distinct `azure-foundry-failure-injection-nonproduction` GitHub
environment must be configured with required reviewers and an OIDC federated
credential restricted to this repository/environment. Its secrets are
`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, and
`MAF_HOSTED_FAILURE_AUTH_JSON`. Its variables are
`MAF_HOSTED_FAILURE_TARGET_KIND` (exactly `synthetic-nonproduction`),
`MAF_HOSTED_FAILURE_TARGET_ID` (the exact API Container App ARM resource ID),
`MAF_HOSTED_FAILURE_BASE_URL`, `MAF_HOSTED_FAILURE_EVIDENCE_ENVIRONMENT`
(exactly `synthetic-nonproduction`), `MAF_HOSTED_FAILURE_RESOURCE_GROUP`,
`MAF_HOSTED_FAILURE_API_CONTAINER_APP_NAME`,
`MAF_HOSTED_FAILURE_AZD_ENVIRONMENT`,
`MAF_LIVE_AUTHORIZED_ORIGIN` (the separately authorized HTTPS origin),
`MAF_HOSTED_FAILURE_HOSTED_AGENT_NAME`,
`MAF_HOSTED_FAILURE_HOSTED_AGENT_VERSION`,
`MAF_HOSTED_FAILURE_API_REVISION`, `MAF_HOSTED_FAILURE_HOSTED_ROOT`, and
`MAF_HOSTED_FAILURE_ADAPTER`.

The job compares the dispatch target and URL to those protected settings and
checks the exact active-revision artifact before the provenance hard stop. It
uses the GitHub-hosted `ubuntu-24.04` Azure CLI and installs Azure Developer
CLI 1.39.1 using the action pinned to commit
`413f112a14d9b57e38ed09d704c451124cd4ff08`. Locked backend dependencies and
the target check run with the OIDC request-token variables blanked; `azure/login`
and target-verification steps are staged after the hard stop but are currently
unreachable. Adapter auth material restoration and execution are also
unreachable. Once independently verified provenance exists, the identity must
have only target-specific permissions needed to restart the configured
Container App and stop the synthetic session; the workflow cannot verify Azure
role-assignment scope.

The active-revision verifier checks health, traffic, digest shape, and
revision fields in supplied JSON; it does not independently attest that the
image digest was built from the requested source or that the hosted inspection
is authentic. The [advisory build-attestation preflight](../../blueprints/maf/workflow/docs/build-attestations.md)
can verify exact signed OCI subjects against an externally supplied policy, but
does not prove independent policy or builder control, actual checkout, or live
deployment identity. No trusted deployment-provenance verifier or observer is
present. Therefore the failure-injection job contains a deliberate hard stop
before `azure/login` and before loading/running the adapter. Setting dispatch
inputs or environment markers cannot bypass that stop.

These settings and marker checks are necessary gates, not proof of isolation.
The adapter is trusted executable code, and the repository does not contain a
reviewed Azure implementation for the hosted-failure adapter. Until a trusted
source-to-image/hosted provenance verifier exists and the environment
reviewers, federated credential, resource-scoped role assignments, target
ownership/isolation, auth material, and adapter implementation are
independently verified, leave failure injection disabled. No live dispatch or
fault injection is claimed. Replacing the hard stop requires a separately
reviewed code change that verifies provenance, not a workflow variable or
operator assertion. The cloud workflow does not modify existing
PostgreSQL firewall rules; issue #56 remains open.

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
source/deployment revisions plus `target_kind` and `target_id` matching the
protected synthetic-nonproduction target, and support only bounded synthetic
faults. The runner does not serialize the target resource ID into evidence. A
missing capability is `blocked`; a failed observation is `failed`; neither is
converted to success.

The hosted-interruption scenario is blocked before creating or interrupting a
case: its existing adapter cannot verify native continuation after a stopped
session. The live adapter also refuses direct interruption and reconciliation;
it retains unknown/interrupted flags rather than treating an ordinary database
read as recovery. Consequently its timeout/reconciliation scenarios cannot
pass until an authoritative reconciliation mechanism exists. A future
implementation must independently verify native continuation and durable
outcome evidence before restoring these scenarios. The synthetic fixture tests
are not evidence of live Foundry recovery.

The browser gate restores explicit Playwright cookie/local-storage state and
an explicit MSAL session-storage snapshot only after npm and browser
installation. The snapshot must match the configured tenant, SPA client, and
API application URI. Live traces, screenshots, and videos are disabled so
authenticated state is not uploaded. If an authenticated state is unavailable
or the protected request/approval flow fails, browser authentication remains
`unverified`.

Browser/provider dependency installation runs without their secrets. For
failure injection, the step-level OIDC request-token environment is blanked
while locked dependencies, Azure tools, and exact target/revision checks run;
`id-token: write` is limited to the failure-injection and telemetry-query jobs.
The telemetry-query job installs no application dependencies.

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

## Hosted trace failure and code correction — 2026-11-23

The first live trace against `order-resolution:2` failed the correlation gate
without weakening it. Synthetic case
`c22d740f-0983-4d1f-b2c1-e7470aafe9f1`, request
`26e9a217-bdb4-45c3-b110-a132c690babb`, conversation
`conv_02f50f07ef1fd40b00wQ49AZRhYG1nBMtu2muc75uEXWXflRBJ`, and trace
`125933bf44624f04af77bb285814b53a` reached pending HITL with no effect.
The full trace had 37 rows: five API request spans and 32 dependencies. All
rows used the API role. The five hosted-to-API callbacks preserved the original
OperationId but named ParentIds that were absent from ingestion. No hosted
role, `invoke_agent`, native workflow span, or business-stage span existed.
The observed rows contained no raw message-content fields.

The evidence distinguishes the failure modes:

| Candidate | Result |
| --- | --- |
| Missing exporter/provider | Rejected by pinned-runtime provider inspection: one global provider had Azure Monitor batch export and native MAF instrumentation. |
| Wrong App Insights target or runtime environment | Rejected by active version inspection: hosted version 2 used the shared connection and privacy flags false. |
| Sampling | Rejected: AgentServer uses full sampling when no alternate sampler is configured. |
| W3C propagation | Rejected: API callbacks retained the hosted start OperationId. |
| Query/indexing only | Rejected: corrected read-only KQL parsed successfully and still returned zero hosted roots. |
| Request flush | Confirmed: AgentServer Responses defaults to background flush, and its supported documentation warns final spans can be lost when no post-response drain window exists. |

The code correction is built-ins-first. Publication forces supported
`AGENTSERVER_FLUSH_MODE=async`, which awaits `force_flush` off the event loop
before request completion. Existing AgentServer setup still owns the single
global provider, Azure Monitor exporter/resource, Azure SDK/HTTPX/urllib
instrumentation, W3C propagation, and sampling. Native MAF instrumentation
remains enabled on that provider with sensitive and message capture false.
No parallel exporter, manual MAF span recreation, or artificial model call was
added. Application-owned business anchors and the explicit HITL restart link
remain the only custom telemetry because no built-in can infer business stages
or preserve an active parent across a serialized approval wait.

The official references checked for this correction are the
[AgentServer Responses telemetry-flushing contract](https://learn.microsoft.com/python/api/overview/azure/ai-agentserver-responses-readme?view=azure-python),
[MAF observability guidance](https://learn.microsoft.com/agent-framework/agents/observability),
[Azure Monitor OpenTelemetry initialization guidance](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable?tabs=python),
and [OpenTelemetry Python W3C propagation guidance](https://opentelemetry.io/docs/languages/python/propagation/).
The pinned compatibility test additionally verifies that Responses `2.4.0`
dispatches `async` mode through its awaited `flush_spans_async` path and does
not schedule background flushing.

The Foundry trajectory helper separately changed its trace-ID KQL literals from
JSON double quotes to KQL single quotes. A Windows `az.cmd` read-only query now
exits zero and returns the expected zero pre-fix hosted roots instead of
`SYN0002`. Local validation passes 103 root tests with two disclosed adapter
selection skips, 47 generated hosted tests, and Ruff. Live correlation remains
`failed` for version 2 and post-fix ingestion remains `unverified` until a new
immutable hosted version is published and one safe synthetic trace passes in
both Application Insights and Foundry.

The version-3 trace kept the gate failed and isolated the next defect. Foundry
session metadata proved the transaction targeted `order-resolution:3`, while
the unchanged API revision correctly continued to report its locally configured
version `2`. After the ingestion window, Application Insights still contained
37 API-only rows and no hosted root. Hosted runtime logs then recorded repeated
`azure.monitor.opentelemetry.exporter.export._base` `Unauthorized` responses.
This proves provider setup and export/flush execution; it rejects sampling,
query indexing, and sandbox suspension as the remaining cause. The component
has local authentication disabled, hosted version 3 lacked
`APPLICATIONINSIGHTS_AUTH_MODE=entra`, and its managed identity lacked
component-scoped `Monitoring Metrics Publisher`.

The next code correction uses only the pinned supported path:
AgentServer maps Entra mode to `ManagedIdentityCredential()` and the Microsoft
OpenTelemetry distro's Azure Monitor credential argument. Publication keeps
all raw-content flags false. The deployment path grants the hosted identity the
publisher role only at the exact Application Insights component resource ID,
records that assignment in normalized evidence, and binds
`HOSTED_AGENT_VERSION` into the API so `blueprint.agent.version` names the
active hosted version after the coordinated rollout. Deployment and a new
synthetic trace remain unverified in this code-only phase.
Local evidence for the correction passes 103 root tests with two disclosed
adapter-selection skips, 126 source-backend tests and 179 independently
generated backend tests against isolated PostgreSQL 17 instances, 48 generated
hosted-agent tests, Ruff check/format, PowerShell parsing, and Bicep
compilation. These checks do not establish Azure role propagation or telemetry
ingestion.

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

## Observability remediation validation

The first exact-head remediation run, `45183371725`, failed the generated
PostgreSQL Order Resolution API suite before any cloud deployment. The workflow
correctly added deterministic conversation metadata to its durable approval
request, but the local host still compared that request with the historical
case-only shape. The resulting fail-closed `CheckpointError` surfaced as HTTP
`503 Workflow recovery is unavailable` for approval-required starts.

The correction preserves the new metadata and security boundary: the host now
requires the exact case ID and deterministic local conversation ID both when
the request is emitted and when its checkpoint is restored. The complete
generated PostgreSQL API module, Ruff check, and source instantiation tests pass
locally. Run `45183593755` also exposed a separate contracts-only probe that
imported the hosted bridge without installing its runtime dependencies. The
probe now verifies the generated module location through import metadata;
runtime import remains covered in the locked generated-project job. The full
103-test contracts suite passes in an isolated `requirements-dev.txt`
environment. These are implementation results only; exact-head CI, immutable
Azure deployment, one accepted App Insights/Foundry trace tree, restart-link
evidence, and the remaining hosted acceptance gates are still required.

The next authorized rollout built its immutable API image but failed before
the API revision update because Windows `az.cmd` treated the
`&sslrootcert=system` database URL suffix as shell syntax. Deployment now uses
Azure CLI's packaged Python entry point for the two API updates on Windows,
while preserving the `verify-full` URL and normal CLI behavior on other
platforms. The direct entry point reports Azure CLI `2.93.0`, and all 17
infrastructure validation tests pass. Live deployment and correlation proof
remain unverified until exact-head CI passes and the rollout is rerun.

The later full ARM replay demonstrated that the prior optional Container Apps
image defaults were unsafe for an existing environment: ARM created
placeholder latest revisions and single-revision routing followed them. Bicep
now requires explicit API and web images. The deployment orchestrator carries
forward existing immutable digests, allows a placeholder only before immutable
history exists, and fails closed when placeholder state conflicts with an
existing immutable revision. This guard has local Bicep and contract evidence
only; provider what-if and deployment proof remain required.

Pinned hosted dependencies also confirm the built-in observability surfaces:
AgentServer accepts the App Insights connection, privacy flag, and HTTP
instrumentation options; native MAF accepts sensitive-data/message-event
disablement and forced registration. Runtime loading is deferred until that
global provider is initialized. HITL restart links and the strict
App Insights/Foundry verifier remain privacy-safe and do not invent model/token
spans for deterministic paths.

The next deployment reconciliation identified a packaging failure rather than
a startup-prewarm or identity failure. The failed immutable API image contained
`order_resolution_hosted.bridge` and `client` but omitted the new local sibling
`credentials`; importing normal `app.main` therefore raised
`ModuleNotFoundError` before lifespan startup. The independent-project
generator now validates an explicit typed API-bridge manifest against the
transitive relative-import graph and copies exactly `bridge.py`, `client.py`,
and `credentials.py`. Focused source contracts pass 17 tests, the generated
PostgreSQL 17 selection passes 164 tests, and the normal generated image imports
all three modules from one package and composes `ResponsesWorkflowHost`.
These results repair local readiness evidence only. Bind the correction to a
green exact-head run before a later immutable deployment; no workflow,
firewall, or cloud acceptance state changed in this correction.

## Hosted durability correction

The source branch now makes hosted pending persistence atomic: case state,
hosted binding, audit evidence, and the native decision-handle binding commit
or roll back together. The replay branch uses the same typed
connection-scoped helper to verify or repair the exact handle/channel, avoiding
a permanently unbound pending proposal after the former two-transaction crash
window.

The hosted Responses client now acquires authorization before claiming a fresh
durable operation. A token acquisition failure sends no POST and leaves no
journal row; a later retry claims and posts exactly once. Existing ambiguity
after a request may have been sent remains non-replayable without
reconciliation.

Local evidence passed: two focused PostgreSQL crash-window/journal regressions,
63 source hosted tests, 166 independently generated PostgreSQL/backend tests
with one explicit provider-opt-in skip, 63 generated hosted tests, nine
canonical ORS contract tests without skips, 105 repository tests with two
documented adapter-selection skips, and source/generated Ruff checks. This
checkpoint did not deploy or invoke a workflow and changed no cloud, database,
RBAC, firewall, or network state. A green exact-head CI run and separate
authorization are required before an immutable rollout and focused live
recovery verification.

## Immutable deployment and bounded signal comparison

Exact source `a302e939810283bce47867b8fa088374f3d204ad` passed all seven
PR #49 jobs in
[run 45275635199](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45275635199).
The authorized deployment verification then passed 32/32 checks:

- active hosted agent `order-resolution:9`, archive SHA-256
  `84a18cc7a233e252b06fcd869ac53a6c881e7355ab82a0957ec6c43b2992c595`,
  and publication digest
  `781e882933dc02a0edce61356a6502d430ce20e80ed0b39e60e17e5029f025e7`;
- API revision `aborsfoundpv2n45-api--a302e939`, 100 percent traffic, image
  `sha256:6991536d9cf23efd9bdf1b21a94d1c9bddaa245a151d4b709a13235905eebf79`;
- unchanged web revision `aborsfoundpv2n45-web--0000002`, image
  `sha256:f8a43d68c38707a61ab60b673401427d0c7266d1ebb3dde04a602c07bf3a9ce7`;
- API health `204`, protected unauthenticated request `401`, web root `200`,
  and web health `204`; and
- API managed-identity PostgreSQL login as `aborsfoundpv2n45-api-id` to
  `workflow` with `sslmode=verify-full`, system trust, and TLS 1.3.

The bounded signal phase submitted exactly two synthetic requests and did not
approve, reject, resume, replay, or execute a consequential business action.

| Path | Correlation | Durable result |
| --- | --- | --- |
| Automatic | Case `169a5177-543c-4d06-ac61-314252a2c39f`; trace `d4d3af124c8d4aee8b240bad2af0a78f`; conversation `conv_0cb297e218b263c400UeoYAKXKCW0TATnyGh76BkynLJm4rb5u`; request `7b2c0ebe-acd2-4b12-b0b1-83abb7078a93` | Completed with one PostgreSQL synthetic effect and zero real or external effects. |
| Pending HITL | Case `4b368d22-7335-4ac0-8917-9ee4f7cd63a1`; trace `2c64659b9cbc467488d53e67e972b7fc`; conversation `conv_098da7ddb17139e3008wVAOWPvXojs08YCNLcZ78fY9DCAocn4`; request `d4a44261-4fd9-4fc2-86e0-f89e5e3d5f6c` | Remains pending with zero decisions, claims, effects, terminal events, or resume attempts. |

The comparison passed 16/16 checks:

| Signal | Version 7 | Version 9 | Result |
| --- | ---: | ---: | --- |
| Total spans | 276 | 243 | 33 fewer while retaining required dependencies |
| API spans | 74 | 26 | 48 fewer |
| Hosted spans | 202 | 217 | 15 additional deterministic business stages |
| Pooled-borrow `database.connect` | 52 | 0 | Target met; physical open/create visibility retained |
| MSI token spans | 54 | 52 | Warm reduction without hiding refresh/failure dependencies |
| Foundry data-plane dependencies | 128 | 128 | Unchanged |
| Optional A365/OpenAI Agents startup exceptions | 2 | 0 | Target met |

Both graphs have only the expected external caller and non-exported
AgentServer platform-parent boundaries. All correlated HTTP requests had
successful result semantics. Exact hosted version and deployment revision
binding passed. Exporter failures, raw-content rows, payload markers, and
optional startup exceptions were zero. Privacy-safe deterministic stages
include `workflow.run`, authorization, policy, proposal, approval, effect,
persistence, `workflow.resolution_submit`, and `workflow.hitl_waiting` as
applicable to each path.

Machine-readable evidence is retained as
`deployment-observability-signal-a302e939/deployment-verification-summary.json`,
`signal-comparison-a302e939-v9-20261123T222235Z/signal-comparison.json`, and
`signal-comparison-a302e939-v9-20261123T222235Z/signal-comparison-summary.json`.

Two blockers remain explicit:

1. A distinct delegated reviewer is still required for HITL resume and the
   durable start-to-resume trace-link proof. Workload identity or single-user
   substitution is prohibited.
2. PostgreSQL firewall hardening is deferred. Retained read-only evidence
   records public network access, the broad
   `temporary-e2e-public-remove-after-e2e` rule, five narrow Container Apps
   rules, 407 advertised outbound addresses, and a temporary exact-IP
   `deployment-operator` migration path. The broad rule must remain until both
   API and operator/migration connectivity are validated without it.

No runtime code, cloud resource, RBAC, workflow, firewall, or network state was
changed by this documentation reconciliation. PR #49 remains draft, open, and
unmerged. Production authorization remains blocked and cannot be inferred
from these diagnostic artifacts.
