# Issues, Fixes, and Changes

This log records significant implementation and deployment corrections together
with their evidence and remaining validation gaps. An entry does not change a
plan or release status unless the corresponding validation is complete.

## 2026-11-27 - Approved observability and studio follow-up

| Time (US Central) | Status | Task | Completed details | PR |
| --- | --- | --- | --- | --- |
| 06:00 CST | Complete | Trace ingestion | A fresh synthetic run produced connected API, Foundry, MAF, and database spans. | #62 |
| 06:40 CST | In progress | Telemetry and studio | Infrastructure checks passed; the root suite ran 114 tests with two optional adapters skipped. Telemetry is underway; partial UI work is paused until telemetry verification. | #62 |
| 06:54 CST | Complete | Noise baseline | The original trace had 119 dependency rows, 26 token requests, and 200 log rows, 81 of which were credential noise. Successful request metrics were present. | #62 |
| 06:59 CST | In progress | Telemetry review | Focused API and hosted tests passed, but exception privacy and sampled-flag correlation issues require correction before UI work resumes. | #62 |
| 07:38 CST | In progress | Telemetry review | Focused API and hosted tests pass; review identified a fail-open redaction path and polling-root retention that need resolution before rollout. | #62 |
| 08:12 CST | Blocked | Telemetry review | Redaction failure now fails closed in local tests. Sampled polling roots are still retained to preserve returned trace parentage; broader HTTP telemetry privacy and useful failure diagnostics need review. No follow-up rollout has occurred. | #62 |
| 08:42 CST | Blocked | Telemetry privacy | Local probes identified additional Azure SDK path/exception exposure and inbound baggage exposure in AgentServer logs; these remain unresolved. Telemetry is not deployment-ready. | #62 |
| 08:58 CST | Blocked | Telemetry privacy | Synthetic local probes reproduced URL path and allowed query values in Azure Monitor dependency envelopes, exception text in OTLP spans, and untrusted baggage in Azure Monitor log envelopes. The deployed export paths remain unverified. Disabling SDK instrumentation alone loses dependency spans and propagation. | #62 |
| 09:11 CST | In progress | Parallel implementation | User authorized separate telemetry and studio worktrees. Prior uncommitted candidates are preserved; integration and deployment await both workstreams and their checks. | #62 |
| 09:17 CST | Blocked | Authenticated UI preflight | Browser access to the existing POC tab was not approved; authenticated browser verification remains unverified. Local work and CI preparation continue without bypassing browser approval. | #62 |
| 09:18 CST | Complete | Integration baseline | The isolated integration worktree passed 18 infrastructure tests, 18 hosted publisher tests, and 114 root tests with two optional adapter skips. Both implementation workstreams remain in progress. | #62 |
| 09:20 CST | In progress | Telemetry | A separate worktree produced a locally tested partial backend change that suppresses fast successful polling operation logs. Hosted privacy and polling-span reduction remain unresolved; the candidate has not been integrated or deployed. | #62 |
| 09:22 CST | In progress | Workflow Studio | A local candidate passed frontend, generated-profile, accessibility, and proxy-configuration checks. Search, editable use-case inputs, and approval-state wording need follow-up before final integration. | #62 |
| 09:24 CST | In progress | Local integration | Initial telemetry and studio commits are integrated in an isolated worktree. Focused telemetry (30), generator (10), and frontend (62) tests passed; the frontend build and CSP check passed. Further privacy and UX work remains. | #62 |
| 09:26 CST | In progress | Generated UI and telemetry | The independently generated UI passed 70 tests, build, CSP, and responsive browser checks. Hosted probes still expose synthetic exception text and downstream baggage in OTLP; mitigation is under investigation. | #62 |
| 09:31 CST | Complete | Local studio checks | History search, editable inputs, and approval-state wording are integrated. Source and generated UI tests passed (63 and 72), as did builds, CSP, and responsive browser checks. Azure UI verification remains pending. | #62 |
| 09:32 CST | Complete | Local history checks | Generated-project history browser tests passed (5); the production-built studio signed-out smoke passed (1). These checks do not replace authenticated Azure UI verification. | #62 |
| 09:33 CST | Blocked | Hosted telemetry | A local test of the pinned AgentServer bootstrap and loopback OTLP collector reproduced synthetic downstream baggage in logs and exception text in traces. Supported exporter injection was not found; the partial mitigation is not a complete privacy fix. | #62 |
| 09:36 CST | In progress | Hosted telemetry | Investigating the documented custom observability callback as a possible privacy-safe alternative; equivalent native tracing, exporter behavior, and error visibility still need proof. | #62 |
| 09:40 CST | Blocked | Hosted telemetry | An experimental application-owned callback sanitized synthetic Azure Monitor and OTLP export envelopes while retaining tested parentage and error status. It did not establish native Foundry enrichment, identity, metrics, or all destinations, and conflicts with the approved AgentServer-owned initialization requirement; it is not implemented. | #62 |
| 09:44 CST | Blocked | Hosted telemetry | The documented AgentServer configuration exposes no confirmed ordered sanitizer for all managed exporters. Actual A365, OTLP, and platform-injected settings remain unknown; the existing connected Azure trace does not verify export privacy. Obtain a supported privacy boundary and verify the enabled destinations before rollout. | #62 |
| 09:48 CST | In progress | Deployed telemetry and UI | The user directed an evidence-first investigation of actual configuration and authorized synthetic exposures while independently tested UI work continues. Local canaries alone are not proof of a deployed leak. | #62 |
| 09:52 CST | Complete | Local authenticated UI flow | A generated-profile test exercised loading, editing, scoped submission, history, activity, and server-gated decisions using mocked identity and services. The generated UI suite passed 73 tests. Real authenticated Azure browser behavior remains unverified. | #62 |

- **Issues:** Useful Foundry/Application Insights transaction spans are
  obscured by credential and polling noise; the current operator UI does not
  match the usable three-panel MAF Workflow Studio reference.
- **Approved sequence:** Implement telemetry and the reference-aligned UI in
  parallel in separate worktrees; integrate, validate, and deploy both together
  on the existing development POC before remaining scenario testing.
- **Requirements:** Preserve errors, slow requests, metrics, correlation,
  authentication, authorization, and self-approval controls. Avoid unnecessary
  framework and CopilotKit upgrades.
- **Foundry ingestion cause and correction:** The POC Application Insights
  component disables local authentication, but the project connection used
  API-key authentication and the project identity lacked the component-scoped
  telemetry role. The existing connection now uses project managed identity
  and the project identity has the narrowly scoped publisher role. A fresh
  synthetic ORS-001 produced a connected API, Foundry platform, hosted MAF,
  and database trace in Application Insights. Environment-specific identifiers
  and raw evidence are retained outside this public repository.
- **Noise baseline:** A bounded query for that trace returned 119 dependency
  rows, including 26 managed-identity token requests, and 200 hosted-agent log
  rows, including 81 credential initialization or successful-token messages.
  Two initial Windows CLI queries failed with `BadArgumentError`; the same
  read-only query succeeded with single-quoted KQL string literals.
- **Metric baseline:** The API exported `blueprint.operations` and
  `blueprint.operation.duration` for successful `http.request` operations.
  The baseline window contained no failed-request metric sample, so failure
  metric preservation still requires a focused check.
- **Local contract checks:** The Foundry connection and scoped-role changes
  passed all 18 infrastructure tests, and the Bicep template compiled. The
  role's deterministic assignment seed matches the existing scoped deployment.
  The isolated root suite ran 114 tests: 112 passed and two optional
  application-adapter tests were skipped because no adapters were selected.
  These checks do not replace exact-head CI or Azure rollout verification.
- **Remaining gaps:** Noise reduction and UI changes are in progress and not
  yet deployed or verified. The initial frontend test could not start because
  Vitest was absent; dependencies were restored from the existing lockfile and
  the test has not yet been rerun. Foundry portal trace visibility remains
  unverified after a `403`; the seven Azure Policy audit findings remain
  unresolved. The deployment plan remains **Approved / Not Validated**.

## 2026-11-27 - PR #62 development POC deployment

Status: **Development POC deployed; validation partial**. The deployment plan
remains **Approved / Not Validated**, PR #62 remains draft, and production
readiness is not claimed.

### Hosted-agent startup failure

- **Issue:** Foundry hosted-agent version 10 failed before application
  initialization. Its session log reported
  `PermissionError: [Errno 13] Permission denied:
  '/home/session/.agentserver'`.
- **Cause:** Foundry set `HOME=/home/session`, while the non-root image user
  owned `/home/hosted`. AgentServer derived its default file-backed state root
  from `HOME` and could not create the required directories.
- **Impact:** The first ORS-001 case was created, but the API did not receive an
  acknowledged Foundry start within the bounded timeout and recorded
  `AmbiguousCreate`. That case was not replayed.
- **Fix:** Set
  `AGENTSERVER_STATE_ROOT=/home/hosted/.agentserver` in a permission-only image
  layer based on the verified version-10 image digest. Local construction with
  Foundry's `HOME=/home/session` override completed without filesystem errors.
  The corrected immutable image was pushed as
  `sha256:278843a486038c230c78bd658bd1e1a9a59a8c3c40f05dcdbafbd9a27b07223c`.
- **Evidence:** The image was journal-published as hosted-agent version 11,
  reached `active`, and was promoted to the fixed 100% route. Final version-11
  sessions executed ORS-001 and ORS-004 successfully.
- **Historical record:** The original ambiguous version-10 case remains
  unchanged. A new authorized case was used rather than replaying its unknown
  start operation.

### Image publisher correction

- **Issue:** Foundry rejects platform-reserved variables in image-container
  definitions, including `FOUNDRY_PROJECT_ENDPOINT`,
  `APPLICATIONINSIGHTS_CONNECTION_STRING`, and
  `APPLICATIONINSIGHTS_AUTH_MODE`.
- **Fix:** Image publication filters those variables from the submitted
  container definition while retaining the complete target configuration in
  the journaled publication identity.
- **Evidence:** All 18 focused publisher tests passed. Operation
  `pr62-3cfdbd9-image-v3-homefix-20261127t1114z` acknowledged active version 11
  on the expected immutable digest while the route remained fixed to version
  10.

### Web proxy corrections

- **Issue:** The generated web proxy first targeted the Docker Compose hostname
  `api:8000`; the initial Azure HTTPS correction then forwarded the public web
  hostname to the API upstream and returned HTTP 502.
- **Fix:** The deployed web revision uses the API HTTPS FQDN, TLS SNI, and the
  upstream host header.
- **Evidence:** Revision `aborsfoundpv2n45-web--pr62-3cfdbd9-v3` is healthy at
  100% traffic; the root, health endpoint, and authenticated proxied API path
  returned their expected responses.
- **Remaining gap:** The deployment-portable nginx correction is not yet
  represented in the repository-generated web configuration.

### Final authorized scenario results

- **ORS-001:** completed; one claim, one effect, one terminal event.
- **ORS-004:** completed idempotently; original outcome returned, one effect,
  and no duplicate terminal event.
- **ORS-006:** failed explicitly with `policy_evidence_missing`; zero effects
  and one terminal event.
- **ORS-007:** failed explicitly with `policy_evidence_conflict`; zero effects
  and one terminal event.
- **ORS-008:** the digest-invalid, expired, and non-applicable variants all
  failed explicitly with `policy_evidence_invalid`; each had zero effects and
  one terminal event.
- **Remaining gaps:** ORS-002, ORS-003, ORS-005, and ORS-009 were not run.
  Seven Azure Policy audit findings remain unresolved. The evidence is for a
  development POC only.
