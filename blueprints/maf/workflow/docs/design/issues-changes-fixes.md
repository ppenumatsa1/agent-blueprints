# Engineering issues, changes, and fixes

## Evidence rule

This journal records engineering decisions and evidence that can be tied to a
source revision, test, or PR. A merged PR or passing local test is not a
deployment claim. Keep **implemented**, **verified**, **planned**, and
**unverified** separate. Add entries as work lands; do not rewrite earlier
entries to hide failed attempts or gaps.

## 2026-11-21 - Generated-project design baseline

- **Issue / cause:** Blueprint implementation and operator guides existed,
  but generated projects had no single set of product requirements, stack,
  implementation mapping, project structure, user journey, deployment flow,
  or cumulative journal.
- **Change / decision:** Add eight `docs/design` files, keep the six existing
  adopter/operator guides, link both sets from the generated README, and make
  the complete blueprint documentation part of the independent copy check.
- **Evidence:** `tests/test_instantiation.py` compares copied documentation
  bytes and checks relative Markdown links. After adding this design set to
  the working tree based on `57d404c`, both focused instantiation tests passed
  locally. This is not yet hosted verification for the updated PR revision.
- **Limit:** This is documentation and test coverage; it does not implement
  migrations, telemetry export, Foundry hosting, cloud deployment, or live
  identity verification.

## 2026-11-21 - Instrumentation failure isolation

- **Finding:** Span entry, annotation, context reads and closure could raise
  into application execution, and a pre-yield startup failure bypassed
  telemetry shutdown.
- **Decision:** Isolate SDK operations individually, emit fixed failure
  signals, never rerun the business action or replace its exception, and
  clean up initialized telemetry on construction or startup failure.
- **Evidence:** Focused injected-failure tests exercise synchronous and
  asynchronous actions, HTTP status and propagation, exporter/provider
  cleanup, and original exception identity. On implementation revision
  `fe4550a`, source and generated backend suites passed 50 tests each, the
  generated verifier passed 44, instantiation passed two, and changed Python
  files passed the tooling branch's Ruff checks. Exact PR CI remains pending.
- **Limit / lesson:** Public hosted configuration and cloud ingestion remain
  unverified. A fixed signal is diagnostic, not delivery evidence; failures
  can lose spans. Failure isolation must cover instrumentation
  setup and teardown as well as export, without catching business errors.

## 2026-11-21 - Privacy-safe observability

- **Issue:** Trace-only export omitted required metrics, and silently accepting
  missing Azure configuration obscured a nonfunctional hosted exporter.
- **Decision:** Add manual allowlisted spans, JSON logs, counter and histogram,
  explicit Azure trace and metric exporters, no metric exemplars, static
  non-identifying exporter resource fields, fail-fast configuration and fixed
  failure signals. Local mode has no exporter or collector.
- **Evidence:** `backend/tests/test_telemetry.py` exercises in-memory signals,
  redaction canaries, converted Azure envelopes and failure handling;
  `frontend/src/test/api.test.ts` exercises browser trace context. Earlier
  reconciled source and generated backend suites passed 45 tests each;
  generated independent verification passed 44, instantiation passed two,
  and both frontend suites passed nine with build and CSP checks. Earlier
  revisions passed 46 backend tests each. Check exact PR CI before approval.
- **Limits / lesson:** Export initialization is not ingestion evidence.
  Hosted trace/metric delivery, outgoing and Foundry propagation, and Azure
  operations remain unverified. A privacy review must cover exporter-generated
  metadata and failure logs as well as application attributes.
- **Coordination:** The independent tooling branch moves requirements into
  `pyproject.toml` and `uv.lock`; its reported pins are SDK `1.45.2` and Azure
  exporter `1.0.0b59`. Reconcile manifests and the public lock on integration.

## Prior implementation evidence

### PR #6 - Native MAF workflow and local recovery core

- **Change:** Added a native MAF approval workflow, local checkpoint host,
  PostgreSQL business/decision/audit/action records, and worker-kill recovery
  tests. CI used isolated PostgreSQL and exposed no application endpoints in
  that increment.
- **Evidence:** The PR description records 13 passing core tests, including
  both worker-kill windows, and 43 source tests passed with the later
  application acceptance adapter intentionally skipped.
- **Reusable lesson:** Checkpoint state and PostgreSQL state are separate;
  test the crash windows explicitly. Database transaction idempotency does
  not guarantee idempotency for arbitrary external effects.
- **References:** [PR #6](https://github.com/ppenumatsa1/agent-blueprints/pull/6);
  `backend/app/workflows/host.py`, `backend/app/infrastructure/store.py`, and
  `backend/tests/test_core.py`.

### PR #8 - Authenticated local MAF application

- **Change:** Added Entra-protected FastAPI operations, case authorization,
  optional server-side OBO, React/MSAL, a synthetic application, and a
  loopback-only Compose stack.
- **Evidence:** The PR description records 26 backend tests and 8 frontend
  tests passing, build/CSP checks passing, and a local Compose smoke with UI
  200, health 204, protected API 401, non-root API, and private checkpoint
  permissions. It explicitly leaves live Entra/OBO and production controls
  unverified.
- **Reusable lesson:** A synthetic identity is a test fixture, not interactive
  authentication. Keep the public browser on the UI origin and do not expose
  database/API ports or service secrets.
- **Known warning:** The PR reported an approximately 505 kB minified UI chunk
  and an HTTPX test-client deprecation warning; no evidence here establishes
  that either was subsequently fixed.
- **References:** [PR #8](https://github.com/ppenumatsa1/agent-blueprints/pull/8);
  `backend/app/infrastructure/identity.py`, `backend/app/domain/policy.py`,
  `compose.yaml`, and `frontend/src/api.ts`.

### PR #10 - Independent blueprint instantiation and evidence

- **Change:** Added generation outside the source checkout and an independent
  verifier, exact contract copies, synthetic golden adapter, crash evidence,
  and generated-project CI.
- **Evidence:** The PR description records byte-identical contracts,
  isolated imports/build contexts, generated backend 31 tests, verifier 44,
  frontend 8, and Compose smoke. Approval/recovery observations passed while
  explanation/hint remained unverified and the unsigned readiness result
  remained unverified. GitHub Actions run 44917564338 passed five jobs.
- **Reusable lesson:** Generated copies need their own tests and runtime
  contexts; a fixture that formats its own explanation/hint is not agent
  evaluation or browser end-to-end evidence. Passing observations do not make
  unsigned data a release authorization.
- **References:** [PR #10](https://github.com/ppenumatsa1/agent-blueprints/pull/10);
  `scripts/instantiate_maf.py`, `tests/test_instantiation.py`, and
  `.github/workflows/ci.yml`.

### PR #11 - Modularity foundation

- **Change:** Split backend/frontend build contexts and organized backend
  responsibilities while retaining previous extension imports.
- **Evidence:** The PR description records source/generated backend 32 tests
  each, generated verifier 44, and frontend 8 with build/CSP passing. It
  records package-host TLS failure followed by a successful retry through
  approved package proxies. At the time of this entry, PR #11 is open and its
  hosted verification status must be refreshed before approval.
- **Decision / follow-up:** The greenfield quality gate rejects backward
  compatibility shims and forwarding modules. This revision removes them
  and updates internal imports; tests and CI must be rerun on its exact head.
- **References:** [PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11);
  `backend/app/`, `frontend/`, `backend/Dockerfile`, and
  `tests/test_instantiation.py`.

### PR #13 - Locked developer tooling proposal

- **Status and revision:** Open, based on `modularity-foundation`; head
  `e1d953662e615e547fa641ad0831907c363318e3`. It is a parallel workstream and
  is not included in this branch's baseline commit `57d404c`.
- **Proposed changes:** Python 3.12, uv 0.9.26, public-PyPI `uv.lock` and
  hash-pinned backend/image installs, Ruff 0.14.13, Node 22 with `npm ci`,
  and VS Code task/debug configurations.
- **Evidence:** Hosted run
  [44928260607](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44928260607)
  passed `contracts`, `maf-core`, `maf-frontend`, `maf-compose`, and
  `maf-independent` for that exact tooling head only. The workstream reports
  Windows and Linux Compose checks using an approved mirror after public TLS
  failures. Those results do not transfer to this branch or other revisions.
- **Unverified:** macOS Compose and interactive debugger operation.
- **References:** [PR #13](https://github.com/ppenumatsa1/agent-blueprints/pull/13);
  `uv.lock`, backend image install, and developer task/debug configuration
  are proposed in that PR, not present in the baseline documented here.

## Current acceptance queue

| Item | Status | Evidence needed / next action |
| --- | --- | --- |
| Eight design documents and generated inclusion | In progress | Run the focused instantiation tests and verify copied Markdown links. |
| Canonical imports and legacy-shim removal | Implemented in foundation | Reverify the integrated diff and generated copy; do not approve while forwarding paths remain. |
| Locked developer tooling | Open in parallel PR #13 | Reconcile only after review/merge; verify any resulting revision and platform matrix independently. |
| Current dependent PR CI | Pending on updated revision | Confirm all required checks correspond to the pushed PR head. |
| Live Entra/OBO, Foundry host/recovery, cloud telemetry, Azure deployment | Unverified | Separate scoped implementation, authorization where required, and live evidence. |

Future entries should use this form: date and scope; observed issue and
evidence-backed cause; attempted approaches (including failures); accepted
change or decision; focused tests and exact revision/CI evidence; remaining
limitations and reusable lesson. Do not invent historical root causes when the
available PR or test record does not establish one.
