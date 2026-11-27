# Azure/Foundry Deployment Plan

## Status

Plan status: **Approved / Not Validated**

Deployment status: **Development POC Deployed / Validation Partial**

Current follow-up: source `3bddba6` passed
[exact-head CI 8/8](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/46034973494)
and was deployed to the existing development POC. Hosted version 12 is fixed
at 100%; API and web revisions are ready with protected configuration,
identities and secrets preserved and self-approval disabled. ORS-001
completed; ORS-006/007 and three ORS-008 variants failed as expected without
effects. ORS-004 remains unverified because its nonterminal replay boundary
was not observed. In the new ORS-001 trace, five hosted API callbacks had
origin-only dependency URLs and no case ID; parent links connected API,
Foundry, hosted and callback API spans. Database span correlation was not
established by that query. The live baggage marker was not found, but its
arrival at hosted instrumentation is unverified; live exception exposure is
unverified. Browser approval was denied, so authenticated UI behavior remains
unverified. Next: obtain browser access and verify replay, baggage and
exception exposure separately. The seven Azure Policy audit findings remain
unresolved.

Change authorization: **The user approved the observability and frontend
changes below, including deployment and verification on the existing
development POC resources.** The broader plan remains **Approved / Not
Validated**; approval does not establish that validation has passed.

## Approved PR #62 observability and operator UI correction

This proposal adds two bounded follow-up workstreams to the existing
development POC. It does not change the overall **Approved / Not Validated**
plan status or convert partial POC evidence into production validation.

### Workflow Studio UI candidate - local evidence only

The approved UI changes are implemented in the shared blueprint and copied
into a fresh, independently generated Order Resolution project. The shared
frontend passed 64 unit tests, production build, CSP check, and Chromium E2E
checks for local rendering (1), history (5), and studio shell (1). The
generated frontend passed 74 unit tests, production build, CSP check, the same
Chromium checks (1/5/1), and its responsive accessibility check (1). The final
copy distinguishes an empty activity timeline from empty workflow history;
semantic status text colors are defined for both themes.

These are local results, not exact-head CI or authenticated Azure UI evidence.
The UI candidate has not yet been deployed. No automatic PR run appeared after
the candidate push, so a non-privileged manual dispatch was added to the
existing readiness workflow without changing its eight jobs. Run it at the
exact PR head and require 8/8 before rollout; live history, timeline, approval
visibility, and end-to-end behavior remain unverified. The seven Azure Policy
audit findings remain unresolved.

The implementation may use `ppenumatsa1/maf-monorepo` at indexed revision
`45430753c5f3e75716ea3822d2b2b52fbb4f1c34` as read-only design and supported
SDK-pattern evidence. Do not copy its source implementation. Preserve the
blueprint's framework-native, independently generated structure and use
supported AgentServer, Microsoft Agent Framework, OpenTelemetry, Azure Monitor,
React, Vite, and CopilotKit capabilities before adding custom code.

### Verified baseline

- The POC uses its existing Application Insights component and Log Analytics
  workspace. The initially named component from a different application is
  unrelated. Environment-specific resource identifiers stay outside this
  public repository.
- The Foundry project Application Insights connection now uses
  `ProjectManagedIdentity`, keeps the full connection string under metadata,
  contains no credentials, and is not shared to all projects. The Foundry
  project identity and hosted-agent identity have the narrowly scoped
  `Monitoring Metrics Publisher` role at the exact Application Insights
  component.
- A fresh synthetic ORS-001 produced an Application Insights trace with the
  connected API `http.request` -> Foundry platform `agentsv2/invoke_agent` ->
  hosted `order-resolution/invoke_agent` -> native MAF workflow/business stages
  -> API/database hierarchy. This is real telemetry evidence, not an
  application-log inference. Environment-specific trace and case identifiers
  are retained outside this public repository.
- The active ORS-001 path is deterministic and did not invoke a model. The
  absence of a model/chat span is therefore not a failed telemetry check unless
  a future path actually performs a model call.
- The same run produced approximately 123 dependency rows and at least 200
  trace-log rows. Repeated successful polling, managed-identity token traffic,
  Azure Identity initialization messages, and low-level state-store transport
  diagnostics obscure the useful transaction.
- The current React UI supports authenticated submission, history, case
  opening, activity, and server-authorized approval/rejection, but presents
  them as dense independent cards. It has no safe curated use-case loader,
  limited run-at-a-glance hierarchy, and weak responsive operator flow.

### Workstream A - interpretable Foundry and Application Insights telemetry

Objective: retain one privacy-safe distributed business transaction and
existing metrics while removing redundant, fast successful polling and
credential noise. Do not hide slow requests, errors, failed authentication,
failed exports, business failures, or unresolved parentage.

Inspect the deployed telemetry configuration and use authorized synthetic
tests to classify suspected exposures as confirmed, not reproduced, or
unverified. A local probe alone does not establish exposure in the deployed
POC. Address confirmed sources with the smallest supported change and retain
AgentServer ownership unless a demonstrated need for a change is approved.
Continue independently verified UI work alongside this investigation.
Verify that the pinned SDKs support `ENABLE_TELEMETRY`,
`ENABLE_INSTRUMENTATION`, and `OTEL_RECORD_CONTENT` before relying on them;
enable telemetry and instrumentation while keeping content capture disabled.
Reduce Azure SDK informational logging without hiding warnings or errors.

1. Preserve the supported telemetry foundation:
   - AgentServer owns hosted provider/exporter initialization.
   - Native MAF instrumentation remains enabled with message and sensitive
     content capture disabled.
   - W3C propagation remains the API-to-Foundry correlation mechanism.
   - The hosted `invoke_agent` hook remains a privacy-safe application anchor;
     do not recreate native MAF spans.
   - The API keeps one global provider and its existing allowlisted business
     attributes.
2. Commit the already proven infrastructure contract:
   - Foundry connection `authType: ProjectManagedIdentity`.
   - no connection credentials;
   - project managed identity telemetry role at the exact component;
   - focused contract coverage for those invariants.
3. Use supported configuration before custom filtering:
   - configure AgentServer/runtime log verbosity so Azure Identity, Azure Core,
     HTTP client, and successful credential initialization diagnostics do not
     export at information level;
   - retain warning, error, exporter, authentication, and authorization logs;
   - disable or narrow redundant low-level Azure SDK/urllib transport
     instrumentation only after a trace comparison proves the platform,
     hosted invocation, MAF workflow, meaningful tool/API calls, and database
     spans remain connected.
4. Add the smallest application-owned request exclusions required by the
   blueprint's manual privacy-safe API middleware:
   - reduce successful, fast health, SSE opening, history/activity refresh,
     and case-status polling `http.request` telemetry;
   - always retain submission, decision, internal hosted callback, and
     consequential workflow requests;
   - always retain 4xx/5xx results, exceptions, and slow requests, including
     on normally quiet routes. Use an existing documented slow-request
     threshold if present; otherwise start with a documented, testable
     one-second elapsed-time threshold. Expected stream lifetime alone is not
     a slow request;
   - preserve request-count, duration, and failure metrics regardless of span
     reduction, and avoid orphaning retained child spans;
   - do not record route parameters, query strings, tokens, payloads, customer
     text, or raw model/tool content.
5. Keep correlation usable:
   - retain trace ID, request/correlation ID, case ID, conversation ID, hosted
     version, and privacy-safe stage/outcome dimensions where supported;
   - do not use case ID as a replacement for distributed parentage;
   - disclose browser polling as separate traces when it is intentionally not
     part of the business transaction.

Acceptance criteria:

- A new ORS-001 produces one connected API -> Foundry platform -> hosted agent
  -> MAF workflow/business stage -> database transaction in the POC's existing
  Application Insights component.
- The trace contains the real operation/trace ID, request ID, and case ID, with
  no raw request, response, prompt, token, credential, or policy-evidence
  content.
- Fast successful health/poll/SSE transport is reduced. Slow requests, failure
  traces, request metrics, warnings, and errors remain visible. Measure the
  before/after low-value credential and transport rows; disclose limitations
  rather than treating an arbitrary reduction percentage as a release gate.
- Local synthetic canary tests cover URL path and query attributes, exception
  text, and untrusted baggage in actual export envelopes, while verifying
  retained error visibility and W3C parentage through native agent spans.
- Foundry trace visibility is verified where the current identity has access.
  A portal or data-plane `403` remains an explicit access gap; Application
  Insights rows alone must not be represented as proof of Foundry portal
  visibility.

### Workstream B - simple Order Resolution operator workspace

Objective: use the existing MAF Workflow Studio reference project and supplied
screenshot as the design baseline, not invent a separate design. Preserve its
three-panel organization in a simpler, responsive operator workspace without
copying its code or weakening existing authorization and side-effect boundaries.

Frontend baseline:

- Keep the existing React, React DOM, Vite, TypeScript, Playwright, and
  lockfile versions when they already support the work. Do not upgrade or add
  React, Vite, TypeScript, CopilotKit, Zod, or lint tooling merely to match
  reference-project version numbers.
- Add or change a dependency only when a requested implemented capability
  actually requires it; document and verify compatibility. Use the configured
  Microsoft npm proxy if package downloads require it.
- Preserve MSAL, same-origin `/api` proxying, CSP, no browser secrets, and the
  existing generated-project independence contract.

Planned information architecture:

1. A compact header with the application identity, environment/runtime
   context, refresh/new-case actions, and sign-out.
2. A left-hand searchable, status-filtered workflow history rail with concise status
   badges, browser-local timestamps with an explicit time-zone label, selected
   state, and accessible loading/empty/error states.
3. A central workflow and timeline workspace with:
   - a plain-language new issue composer;
   - curated ORS use-case templates that only populate reviewed form data;
   - a normal authenticated submit action with generated idempotency key;
   - a chronological event timeline that emphasizes business stages and
     expands technical details on demand.
4. A right-hand approvals and evidence rail with status, latest outcome, request
   summary, correlation identifiers, approval state/actions,
   evidence/capability indicators, and raw details behind an explicit disclosure.
5. Responsive behavior that becomes one logical column on narrow screens,
   preserves keyboard order, and does not rely on color alone.

Functional and security boundaries:

- "Load use case" loads only versioned, static, schema-checked synthetic ORS
  examples. It does not execute profile callbacks, arbitrary JavaScript,
  browser-side test runners, or hidden Azure actions.
- "Run case" uses the existing authenticated API and server-side authorization.
  Approval/rejection is offered only for a valid pending decision; the server
  remains responsible for enforcing reviewer assignment and authorization.
- CopilotKit is limited to the existing capability-gated, read-only
  selected-case assistant/projection. It cannot start, approve, reject, retry,
  or alter a workflow. If no supported AG-UI/CopilotKit endpoint is present,
  the core workspace ships with that capability disabled and the gap remains
  documented.
- The UI does not fabricate evidence, infer successful effects from status
  text, or expose tenant IDs, access tokens, secret values, raw policy
  evidence, model content, or internal exception details.
- Existing API contracts are reused. Additive backend projection changes are
  allowed only when the current API cannot safely provide a required display
  field.

Acceptance criteria:

- An operator can sign in, load a reviewed ORS example, submit it, follow its
  activity, reopen it from history, and approve or reject a valid pending case
  without editing raw JSON.
- Failed, pending, recovering, rejected, and completed states remain visually
  distinct and accurately mapped to server data.
- History search/filter, refresh, selected-case state, approval controls,
  local-time display, and responsive navigation are keyboard accessible and
  covered by unit and Playwright checks.
- Source and independently generated profile frontends pass their existing
  typecheck, unit/axe tests, production build, CSP checks, and Chromium
  workflows at desktop and mobile widths.
- The deployed web revision is verified against the existing API with a real
  authenticated browser session when the required user state is available.
  Missing authenticated-browser access remains unverified, not passed.

### Approved execution order and verification

1. Implement telemetry and the reference-aligned three-panel UI in parallel
   in separate worktrees. Locally verify telemetry privacy, correlation, fast,
   slow, failed, and consequential requests and metrics; verify source and
   generated-profile UI behavior and accessibility independently.
2. Integrate both reviewed workstreams without overwriting existing work.
3. Update `docs/issues-fixes-changes.md`, `docs/master-checklist.md`,
   `docs/implementation-plan.md`, and the relevant Foundry/frontend
   architecture documentation with acceptance criteria, evidence, and
   remaining gaps.
4. Run targeted backend/hosted/frontend checks, then
   `python -m unittest discover -s tests -v`, generated-project tests, frontend
   existing frontend typecheck/unit/build/CSP checks, and Playwright.
5. Commit and push the reviewed change to draft PR #62. Run exact-head CI and
   require 8/8 before any application rollout.
6. After green exact-head CI, use `.github/skills/azure-poc-deploy/SKILL.md`
   for the authorized existing-resource rollout. Publish immutable API, web,
   and hosted images only where their code changed. Preserve all existing
   secrets, identities, networking, firewall, policy, and revision settings.
7. Verify both telemetry and the UI in Azure before testing remaining
   scenarios. Use one fresh ORS-001 as needed for verification, capture real
   trace/case/request identifiers and telemetry queries, and collect browser
   screenshots or links where access permits. Any subsequent scenarios remain
   subject to the repository skill's explicit authorization and safety limits;
   ORS-002, ORS-003, ORS-005, and ORS-009 remain pending without a compatible
   procedure and the required distinct reviewer and recovery evidence.
8. Keep PR #62 draft, self-approval disabled, the seven Azure Policy audit
   findings unresolved, deployment evidence development-only, and the plan
   **Approved / Not Validated** until all broader validation requirements are
   independently satisfied.

Out of scope: infrastructure provisioning; firewall, networking, Entra, secret,
identity, or Azure Policy changes; production rollout; UI-triggered manual test
code; arbitrary prompt execution; fabricated model spans; and retrospective
alteration of historical deployment or telemetry records.

## Current POC rollout scope

The approved objective is one synthetic Order Resolution cycle on the
CI-validated candidate, starting with ORS-001. If it succeeds, the remaining
authorized exception-OFF cases are ORS-004 and ORS-006 through ORS-008.
Self-approval remains off. Old Foundry sessions remain unchanged, issue #56
stays open, and the stacked pull requests stay draft and unmerged.

Use only the existing POC resources. The intended changes are the required
database migrations, immutable API and web images, and a new hosted-agent
version. Do not provision infrastructure, create a resource group or network,
modify PostgreSQL firewall rules, or use the broader deployment and migration
scripts below. Preserve authentication, authorization, managed identities,
and existing safety gates. Tenant-specific identifiers remain outside this
public repository.

The planned recipe is Azure CLI against the existing resources, with the
generated independent project and native migration and hosted-agent publisher.
Before any Azure write, prepare and validate the exact execution path, confirm
the candidate commit and CI, identify existing resource and image identities,
and establish a bounded forward-recovery procedure for the separately
committed base and profile migrations. Verify that the previous API can safely
operate against the migrated schema before relying on image rollback. Capture
each case's real observations and errors separately; missing evidence is not a
pass.

### Prepared existing-resource procedure

The following is preparation for validation, not authorization to execute
Azure writes before validation:

1. Generate a fresh independent project with
   `python .\scripts\instantiate_maf.py <new-directory> --profile order-resolution`.
   Build its backend and frontend and use the generated hosted publisher with
   `--archive <local-zip> --container-context <new-local-directory>` to prepare
   the hosted image context. The deployment web build must use the existing
   API's TLS upstream and approved client configuration. Resolve build inputs
   without committing tenant values and retain immutable image digests once
   images are pushed.
2. Connect to the existing PostgreSQL server using an Entra token and
   `sslmode=verify-full` over its already permitted path. After validation,
   run `python -m app.order_resolution.migrations upgrade` from the generated
   backend with the migration connection in the process environment. Do not
   call the firewall-mutating migration wrapper. The base and profile
   transactions can commit separately; on failure stop, preserve the error,
   and diagnose the actual schema before a forward retry.
3. Before publishing, preserve endpoint settings and use the native Foundry
   agent endpoint merge-patch to change only the version-selection rules from
   `@latest` to the currently serving concrete version at 100%. Re-read the
   route and stop on a mismatch. Existing sessions are not queried or changed.
4. Publish one hosted version with the generated publisher's `--publish`,
   `--agent-name <name>`,
   `--image-reference <registry/repository@sha256:digest>`,
   `--expected-route-version <current-version>`, `--operation-id`, and
   `--journal` options. Retain the journal and do not replay an ambiguous
   create. Verify the resulting version, identity, required narrowly scoped
   access, and configured digest before transition. Leave the POC
   self-decision flag off and do not create a POC self-decision grant.
5. After validating the precise API and web changes, update the existing
   Container Apps with `az containerapp update --image` and the required API
   environment changes. Preserve existing authentication and secret
   configuration. Verify the active revisions, images, version, and health,
   then run ORS-001 before the other authorized cases.

### Current validation checklist

- [ ] Prepare a recipe and validation inputs that represent only the intended
  existing-resource updates and no infrastructure provisioning.
- [ ] Run the Azure CLI recipe's core CLI, authentication, template build,
  provider validation, and what-if checks against those exact inputs.
- [x] Build the three generated containers locally and verify their offline
  imports or build output. The web build used synthetic configuration.
- [x] Check the frontend build uses supported Node.js 22 LTS and the existing
  API and web identities have registry pull roles.
- [ ] Verify applicable Azure policies, the remaining required roles, and the
  actual deployed build inputs.
- [ ] Record commands, timestamps, results, and remaining unknowns in a new
  current-scope validation proof before setting status to `Validated`.
- [ ] Complete the required deployment preflight without violating this scope.

Provisioning a new resource group, network, database, or other infrastructure
is outside this scope, so their creation and capacity checks are not
applicable; this does not waive the validation recipe's mandatory checks. The
existing infrastructure template and its historical what-if are not proof for
the proposed image and agent updates. The repository's POC-specific deployment
procedure is `.github/skills/azure-poc-deploy/SKILL.md`; it defines the
existing-resource-only path and prohibits infrastructure provisioning. Its
presence resolves the earlier workflow conflict with generic deployment
guidance, but it does not validate the current rollout or authorize Azure
writes. The seven existing Azure Policy audit findings remain unresolved and
deferred. Do not assume a required check can be skipped, weaken the existing
security requirements, or widen the approved scope.

### Current-scope evidence and limitations

- Authorized candidate
  `3cfdbd942dc7daf37e4f8f136b26645b83471978` passed exact-head CI 8/8 in
  run `45980935647`. The earlier head
  `0e3b2397cc1989a3198a04ef7a29c06693d7b079` passed 8/8 in run
  `45977781842`.
- The existing-resource-only development deployment completed without
  provisioning infrastructure or changing networking, firewall, Entra,
  managed identities, or Azure Policy. The seven Azure Policy audit findings
  remain unresolved and deferred.
- Final deployed components use API revision suffix `pr62-3cfdbd9-v11`, web
  revision suffix `pr62-3cfdbd9-v3`, and fixed hosted-agent version 11 at
  100%. Immutable digests are API
  `sha256:561214d1792d055b07f0543ca4c9671448303e88047feafab96cc2af05fb6b75`,
  web
  `sha256:2d05f2375fa09bbc81913720664e2e45967273bef3dbcf3d7a7ff349611889e3`,
  and hosted
  `sha256:278843a486038c230c78bd658bd1e1a9a59a8c3c40f05dcdbafbd9a27b07223c`.
  The API and web remain on their existing identities, registry,
  networking, scale, and secret references; secret-value equality was not
  exposed or claimed. Self-decision remains `false`.
- Final live Azure evidence on the final API revision passed ORS-001 and
  ORS-004 with one claim, one effect, and one terminal event each. ORS-006 and
  ORS-007 failed explicitly with their required failure codes, zero effects,
  and one terminal event. All three ORS-008 invalid-evidence variants failed
  explicitly with zero effects and one terminal event each. ORS-002,
  ORS-003, ORS-005, and ORS-009 remain pending.
- Foundry version 10 exposed an image startup defect after the image was
  successfully pulled: Foundry set `HOME=/home/session`, and AgentServer could
  not write its default state directory. Version 11 sets
  `AGENTSERVER_STATE_ROOT=/home/hosted/.agentserver`. Two final version-11
  hosted sessions were observed for ORS-001 and ORS-004. The earlier ambiguous
  version-10 case remains historical and was not rewritten or replayed.
- The image publisher now omits Foundry platform-reserved environment
  variables from image-container definitions while retaining them in the
  journaled publication identity. The deployed web proxy also required an
  Azure-specific HTTPS upstream, SNI, and upstream host header; that
  deployment-portability correction is not yet represented in the generated
  generic nginx configuration.
- These results validate only the explicitly authorized development POC
  matrix. They do not validate the broader plan, production readiness,
  reviewer-dependent flows, provider evaluation, browser acceptance, or the
  unresolved policy findings. Plan status therefore remains **Approved / Not
  Validated**.

The following bullets preserve historical pre-deployment evidence. Where they
describe an unstarted rollout, absent live migration, `@latest` routing, or
unverified pushed artifacts, the completed current-scope evidence above
supersedes those observations without erasing their audit history.

- Exact-head CI passed 8/8 for
  `0e3b2397cc1989a3198a04ef7a29c06693d7b079` in run `45977781842`.
  Earlier exact-head runs also passed for
  `260d9cbb47390f2fb866bf1e620c9741845484e8` in run `45667244691` and
  `4c069e10af7d440d47c431ac495988a6ae1d2ae5` in run `45668742499`; a later
  candidate must have its own passing CI.
- The generated migration command upgraded a disposable legacy PostgreSQL
  fixture twice while preserving existing operation and binding states.
  Live read-only checks found migrations 0004 and 0005 absent; no live
  migration or POC case was run.
- A fresh independent project at `4c069e1` matched the local build contexts
  byte-for-byte, and the native hosted archive matched the earlier generated
  archive. API, web, and hosted images built locally. The first offline API
  import failed because `WORKFLOW_HOST` was unset; it succeeded with synthetic
  hosted configuration. These builds do not prove pushed artifact identity.
- The existing API and web use one registry with visible `AcrPull` assignments
  for both managed identities; their current images are digest-pinned. The
  current hosted endpoint is `@latest`, so the publisher's fixed-route guard
  requires a route update before publication. A locally serialized SDK
  merge-patch input passed the publisher's fixed-route check, and `@latest`
  was rejected; the patch was not sent to Azure.
- Source-to-immutable-artifact provenance, independently observed runtime
  identity, and historical hosted response outcomes remain unverified. These
  unknowns are disclosed rather than represented as passes or used as an
  exhaustive historical reconciliation prerequisite.
- The validation evidence below is historical infrastructure-only evidence,
  not validation or authorization of this current POC rollout.

## Historical infrastructure scope and guardrails

Prepare deployment-ready Azure Developer CLI and Bicep infrastructure for
Azure/Foundry Workstream B. This branch may perform read-only Azure discovery
and local validation only. It must not provision, deploy, change RBAC, modify
Azure resources, or run teardown.

The target is a public-networking milestone. Do not add a virtual network,
private endpoint, private DNS zone, or private runner. Public endpoints remain
authenticated and authorized, local/key authentication is disabled where the
service supports it, PostgreSQL is Entra-only, and TLS is mandatory.

Tenant, subscription, and user identifiers are supplied at execution time and
are intentionally not committed to this public repository.

## Workload classification

- Mode: modify an existing repository and add a root deployment surface.
- Deployment path: Azure Developer CLI with modular Bicep.
- Application services: public Azure Container Apps for API and frontend.
- Agent service: Foundry Hosted Agent code deployment owned by the runtime
  workstream; this infrastructure provides the account, project, model, roles,
  telemetry, runtime connection contract, and integration outputs.
- Persistence: PostgreSQL Flexible Server with Entra authentication only.
- Networking: public endpoints with TLS, platform/application authentication,
  least-privilege RBAC, and explicit PostgreSQL firewall configuration.

## Region and model decision

Region order is `eastus2`, `eastus`, then `centralus`. Read-only checks selected
`eastus2` because it supports Foundry projects, Responses API, Agent Service,
Container Apps, PostgreSQL Flexible Server, Log Analytics, and Application
Insights. No split-region topology is selected. If deployment-time capacity or
service checks fail in East US 2, stop and review the next region rather than
silently splitting resources.

The planned model deployment is:

- model: `gpt-4.1-mini`
- version: `2025-04-14`
- format: `OpenAI`
- SKU: `GlobalStandard`
- capacity: `10`

The model/version/SKU and subscription quota were verified read-only in East
US 2. Standard `gpt-4.1-mini` is rejected because its current subscription
quota is exhausted. The deployment remains an explicit parameter so a future
review can change it without a SKU/name swap.

The catalog reports `agentsV2=true` and `responses=true` for the selected
version. It also reports lifecycle status `Legacy` and inference deprecation
on 2027-04-14. Deployment validation must recheck this and the owning team
must plan a supported replacement before production use approaches that date.

## Resource topology

| Component | Planned resource | Key controls |
| --- | --- | --- |
| Resource boundary | One tagged resource group | Deterministic names; environment and owner tags |
| Foundry | AI Services account and project | Managed identity, local auth disabled, public access enabled |
| Model | One explicit account deployment | Reviewed version/SKU/capacity; no embedding deployment |
| Hosted runtime | Generated source published through Agent A's public SDK fallback | One journaled create; identity grants occur while pending; active polling never replays create |
| API/frontend | Container Apps environment and two apps | TLS-only ingress, API Entra auth, single revision, bounded scale |
| Registry | Basic ACR for API/frontend images only | Admin and anonymous access disabled; managed-identity pull |
| Database | PostgreSQL Flexible Server and application database | Entra-only auth, TLS, no password parameter, bounded storage/backup |
| Secrets/config | Key Vault plus passwordless configuration | RBAC authorization, no secret outputs or committed secret values |
| Telemetry | Log Analytics and workspace-based Application Insights | 30-day retention, 1 GB/day cap, Entra telemetry role |

Azure Verified Modules are used for stable common resources where their
interfaces fit. Raw Bicep is used for Foundry projects/connections, Container
Apps auth configuration, and tightly controlled PostgreSQL/public-firewall
behavior where no suitable stable AVM contract exists.

## Identity and RBAC

- API and frontend use separate user-assigned managed identities.
- API receives Foundry Agent Consumer only at the documented exact agent scope,
  derived from the validated project resource ID and the same fixed agent name
  passed to the journaled publisher. It receives Monitoring Metrics Publisher
  at Application Insights scope.
- API and frontend receive AcrPull at registry scope.
- API receives Key Vault Secrets User at vault scope.
- The Foundry project identity receives Cognitive Services OpenAI User at
  account scope.
- PostgreSQL database-role creation is a separate, explicit configuration step;
  Azure RBAC does not create database principals.
- Hosted-agent principal assignments are applied after the journaled version
  exposes its authoritative principal ID and before active readiness polling.

## Operations

Scripts under `scripts/azure/` provide:

1. read-only identity, provider, region, model quota/capacity, Container Apps,
   and PostgreSQL preflight;
2. local Bicep build/lint and infrastructure contract checks;
3. independent Order Resolution generation plus guarded Azure CLI what-if and
   deployment orchestration;
4. PostgreSQL firewall and managed-identity database-principal configuration;
5. staged hosted publication: capture pending identity, grant/migrate, then
   poll the same journaled version active without another create;
6. schema migration;
7. exact revision and health verification;
8. scoped Container Apps rollback; and
9. destructive teardown requiring explicit confirmation.

Azure CLI mode validates the active Azure CLI subscription, tenant, and user
without changing them. An azd mismatch is reported but does not block this
mode. Explicit azd mode still requires matching identities and refuses
application deployment because root `azure.yaml` is infrastructure-only.

Before any mutation, deployment generates a new independent Order Resolution
project and requires its backend, frontend, hosted source, and publisher. The
cloud API is configured only for hosted workflow execution and managed-identity
PostgreSQL. `BLUEPRINT_APPLICATION`, `CHECKPOINT_ROOT`, the source blueprint
backend/frontend, and `WORKFLOW_HOST=local` are prohibited.

## Cost controls

- Container Apps consumption with `minReplicas: 0`, `maxReplicas: 2`.
- PostgreSQL Burstable `Standard_B2s`, 32 GiB storage, 7-day backup, no HA or
  geo-redundant backup by default.
- ACR Basic.
- Log Analytics 30-day retention and 1 GB/day ingestion cap.
- One `GlobalStandard` model deployment at capacity 10.
- Hosted-agent compute and model/tool usage remain variable and must be reviewed
  before deployment.

## Validation and evidence

- [x] Exact repository base verified.
- [x] Existing infrastructure and authorized reference patterns reviewed.
- [x] Azure CLI identity, tenant, subscription, permissions, and providers
  checked without changing active subscription.
- [x] Region order, Agent Service support, selected model catalog entry,
  platform capacity, subscription quota, Container Apps quota, and PostgreSQL
  SKU checked read-only.
- [x] Modular Bicep, Azure CLI orchestration, and optional infrastructure-only
  azd configuration generated.
- [x] Operations automation and documentation generated.
- [x] Bicep build/lint and 17 non-deploying contract tests pass.
- [x] Root unit suite passes: 68 tests with two expected adapter-selection
  skips.
- [x] PowerShell and Python syntax validation passes.
- [x] Local build, contract, and syntax validation passed.
- [x] Live Azure CLI identity, permission, provider, region, quota, and capacity
  preflight passed in East US 2.
- [x] Subscription policies were reviewed and provider-backed deployment
  validation and what-if passed.
- [x] Status changed to `Validated`.

## Section 7: Validation proof

| Command or check | Result |
| --- | --- |
| `pwsh ./scripts/azure/validate.ps1` | Bicep build/lint succeeded; 17 infrastructure contracts passed |
| Isolated `python -m unittest discover -s tests -v` with `requirements-dev.txt` | 68 passed; 2 expected adapter-selection skips |
| PowerShell parser over `scripts/azure/*.ps1` | Passed |
| `python -m compileall -q ./scripts/azure ./infra/tests` | Passed |
| `git diff --check` | Passed |
| Azure CLI identity preflight with mismatched azd | Passed the authorized Azure CLI context, preserved the active subscription/tenant/user exactly, and reported the unrelated azd mismatch |
| Azure CLI negative identity contracts | Wrong subscription fails before azd inspection; explicit azd mode blocks mismatch |
| Generated hosted-composition deployment gate | Current unintegrated source generation stopped before preflight/mutation on missing `backend/app/api/routes/hosted_service.py` and cleaned temporary artifacts |
| Exact immutable A/C API image composition | Final A `708a4185abe149526c606477de02cd57c5d90a9c` plus final C `722fc4e32937df4bd94678ec12380cac2a7c84df` (TLS code parent `509fb0b20c80fa8e436de4ac782f618c47f38bd3`) generated byte-identical API bridge/client and C composition files, required the image-owned system CA setting, built the canonical backend with `--no-dev`, verified the Agent Framework wheel digest, imported the bridge, and selected `ResponsesWorkflowHost`. |
| Cross-workstream application composition | Integration coordinator independently reports exact A+C default Docker CMD/app lifespan passed against isolated PostgreSQL 17 with inherited `SSL_CERT_FILE`, `verify-full`, `sslrootcert=system`, `pg_stat_ssl.ssl=true`, health `204`, and protected API `401`. Trusted-CA/wrong-hostname and untrusted-CA/correct-hostname negatives both failed closed. B did not rerun that PostgreSQL suite; its own evidence is the nonconnecting canonical image guard above. |
| Credentialless package mirrors | Direct PyPI failed on this laptop with a TLS handshake error; `https://packagefeedproxy.microsoft.io/pypi/simple` passed while retaining TLS, lockfile hashes, and Agent Framework wheel-digest verification. The exact generated web target also built with `NPM_REGISTRY=https://packagefeedproxy.microsoft.io/npm/`; `npm ci`, TypeScript/Vite production build, CSP verification, and nginx image export passed without integrity/TLS weakening. |
| `pwsh ./scripts/azure/preflight.ps1 ...` (`2026-11-23T00:49:53Z`) | Passed with the authorized Azure CLI user, tenant, and subscription; Owner and Foundry User roles found; all required providers registered; East US 2 eligible; PostgreSQL SKU, Container Apps quota, `gpt-4.1-mini` Responses/agentsV2 capabilities, GlobalStandard quota, and capacity available. The unrelated azd identity mismatch remained disclosed and Azure CLI mode performed no mutation. |
| Subscription policy review (`2026-11-23T00:49:53Z`) | Reviewed nine inherited/subscription assignments. The explicit resource-creation deny applies only to listed classic resource types; the planned modern resource types passed provider validation. |
| `az deployment sub validate --validation-level ProviderNoRbac ...` (`2026-11-23T00:49:53Z`) | Succeeded for the exact target subscription, East US 2, resource group, current Entra PostgreSQL administrator object, and validated parameter shape. |
| `pwsh ./scripts/azure/what-if.ps1 ...` (`2026-11-23T00:49:53Z`) | Succeeded with 21 creates, zero modifies, and zero deletes. Four role-assignment previews were reported as unsupported under `ProviderNoRbac`; static contracts verified their exact principals, data-plane roles, and least-privilege scopes. |
| PostgreSQL ordering repair revalidation | `scripts/azure/validate.ps1` passed Bicep build/lint and all 17 infrastructure contracts. Live Azure CLI preflight passed again. Provider-backed what-if against the partially provisioned resource group succeeded with five remaining creates, 12 provider-normalization modifies, no resource deletes, and the same four unsupported deterministic RBAC previews. |
| Draft integration PR exact-head CI | Draft PR #49 at `007f9bc0136c0d0e42bb22c4d45fd9a7f799cfb4`; run `45090269313` passed contracts, browser, Compose, core, frontend, independent generation, and infrastructure. |
| Immutable image and observability guard revalidation | `scripts/azure/validate.ps1` passed Bicep build/lint and all 17 infrastructure contracts after making both application images explicit and preserving existing digest pins. Pinned hosted compatibility tests passed for AgentServer, Azure Monitor, HTTP instrumentation, native MAF, and Foundry SDK surfaces; focused privacy, HITL-link, and strict correlation-verifier tests passed. No Azure mutation was performed by these checks. |

The historical infrastructure-only validation workflow completed with status
`Validated` for the scope above; it did not validate the current POC rollout.
Provisioning, live generated-source publication, hosted execution, and
application verification described in that scope remained unexecuted and must
preserve the fail-closed deployment and readiness gates below.

The first guarded apply exposed two provider behaviors not represented by the
catalog-only preflight: ACR Basic rejected the AVM module's default deny
network-rule object, and PostgreSQL rejected `Standard_B1ms` despite returning
it in regional capability metadata. The corrected configuration keeps ACR
public but authenticated by setting the network-rule default to `Allow`, with
admin and anonymous access still disabled, and uses the service's regional
default Burstable `Standard_B2s`. The failed apply created no application
deployment evidence and does not change release readiness.

A subsequent guarded apply provisioned the PostgreSQL server but exposed a
provider concurrency constraint: administrator and configuration child
operations cannot safely run in parallel while the server is becoming
accessible. The PostgreSQL module now serializes administrator, TLS
configuration, database, and optional firewall resources. This is deployment
ordering only; it does not change authentication, TLS, firewall, or runtime
ownership.

The serialized retry provisioned the complete resource graph, then the
post-deployment gate rejected ARM's noncanonical output-key casing when the
values file was reread. Deployment output names are now normalized to uppercase
before persistence. No migration, image build, hosted publication, or
application activation ran before this fail-closed stop.

The normalized retry then exposed Azure CLI's current Flexible Server firewall
argument contract: server selection uses `--server-name` and rule selection
uses `--name`. The configuration and temporary operator-rule helpers now use
that contract. The failure occurred before any firewall rule, migration, image
build, hosted publication, or application activation.

The Container Apps environment currently reports 407 exact outbound addresses.
Firewall reconciliation uses stable IP-derived rule names, skips rules whose
single-address range is already correct, and removes only stale rules with the
managed `container-apps-` prefix. This keeps retries bounded and idempotent
without using the broad Azure-services firewall rule.

Live database configuration on 2026-11-23 verified PostgreSQL 17 `Ready`,
Entra authentication enabled, password authentication disabled,
`require_secure_transport=ON`, and a `verify-full` administrator connection
using TLS 1.3. The generated platform migration reached revision `0001`; all
ten Order Resolution tables were present. The API UAMI principal
`aborsfoundpv2n45-api-id` maps to object
`fe78ecef-bd1c-40e8-bfcd-81e48014e2e0` as a non-admin Entra service
principal and has database connect, schema usage, table DML, and sequence
privileges without schema create or elevated role attributes.

The temporary E2E rule `temporary-e2e-public-remove-after-e2e` currently spans
`0.0.0.0` through `255.255.255.255`. It is authorized only for the active E2E
window and must be removed after E2E, then replaced by a controlled egress
path or the reviewed API Container App outbound addresses plus the current
operator machine address if operator access remains necessary. It is currently
the only PostgreSQL firewall rule; deleting it before replacement would break
the public API-to-database path. The sole active generated API revision now
logs a successful managed-identity `database.connect`, returns health `204`,
and rejects unauthenticated protected requests with `401`.

The 2026-11-23 live acceptance attempt passed the immutable API/web runtime
and HTTP boundaries but did not clear the release gate. Delegated workflow
authorization, provider evaluation, ORS-001–009, authenticated Chromium, and
live fault injection were blocked by missing consent/authentication or live
adapters. Exact telemetry correlation failed because the deployed runtime
reported agent `0.1.0` and deployment `local-unversioned`; the retained
normalized values also omitted final hosted fields. These defects must be
corrected and independently rerun before merge or Azure runtime readiness.

The live migration also exposed two Windows operator defects: PowerShell
treated `$database?sslmode` as one variable name, and bundled psycopg could not
use a Windows `system` CA path. The migration helper now delimits
`${database}` and resolves the locked generated backend's `certifi` bundle on
Windows while retaining `verify-full`; Linux runtime configuration remains
bound to the system CA store.

## Deployment gate

The current Azure CLI identity matches the authorized context. Azure CLI mode
uses that verified context for preflight, what-if, Bicep deployment, outputs,
generated image deployment, and scoped operations; it never calls
`az account set`. The current azd identity is a different tenant/account, is
reported in evidence, and blocks only explicitly selected azd mode.

Deployment also fails before mutation unless it can instantiate an independent
Order Resolution project and find the generated backend, frontend,
`hosted-agent`, and Agent A publisher. The hosted adapter endpoint, stable
publish operation, durable journal, PostgreSQL
administrator, and output path are mandatory explicit inputs.

No RBAC scope input is accepted. Deployment derives
`<project-resource-id>/agents/<agent-name>` from validated Bicep output and the
same safe agent-name segment passed to the publisher, following the documented
Foundry agent-scope contract. Project, account, resource-group, subscription,
agent-version, role-assignment, and another-agent scopes are rejected by
offline contracts.

The publisher contract requires `agent_version`, `agent_version_id`,
`agent_guid`, `identity_principal_id`, `identity_client_id`, and an `active`
`provisioning_status` in the second phase. The first phase may return
`creating` after the same fields are authoritative. The generated API and its
internal hosted-state boundary are deployed first in hosted mode using the
credentialless API resource service principal as the temporary identity. That
principal has no `Hosted.Workflow.Invoke` assignment, so the boundary fails
closed without local workflow mode or file checkpoints. The authoritative
hosted principal then receives only the dedicated API app role. After active
readiness, the final API revision binds the returned principal.
`--require-active` must reuse the same operation/journal and perform no create.
The data-plane version ID is not represented as an ARM resource ID.

Foundry hosted code receives no PostgreSQL URL, credential, database role, or
firewall rule because public hosted egress has no stable source-IP contract.
Only API Container App outbound IPs are allowlisted; the API UAMI is the sole
runtime database principal. API PostgreSQL clients use `verify-full` with
`sslrootcert=system`, and generated API image builds fail if the system CA
bundle is absent. The canonical image owns the bundled libpq/OpenSSL
`SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` setting; Bicep and deployment
updates must not override or clear it.

The generated application interface is frozen at Agent C draft PR #48 head
`722fc4e32937df4bd94678ec12380cac2a7c84df`; all six C CI jobs passed in run
`45087843018`. Its TLS code parent is
`509fb0b20c80fa8e436de4ac782f618c47f38bd3`, whose all-six C CI run
`45087411666` passed. Agent A's immutable replacement head is
`708a4185abe149526c606477de02cd57c5d90a9c`; all six A CI jobs passed in
run `45085543517`, and its exact `git archive`
tar SHA-256 is
`96E4F3ECEECE65A686ED6F941AD56E1B111CA29EC03879010E00D1766A341BC0`,
with explicit bridge factory
`order_resolution_hosted.bridge:build_workflow_host`. Exact immutable A/C
generation and API image import/composition are verified locally; live Azure
compatibility remains unverified and deployment remains outside this plan.
Agent A owns generator production of byte-identical
API-only `client.py` and `bridge.py` modules, a side-effect-free backend package
initializer, and the canonical backend Dockerfile copy. The API-only client
uses the Python standard library plus existing runtime `azure-identity`; test-only
`httpx` remains outside the production dependency set. B validates those
outputs without copying or replacing them, then builds that canonical backend context.
Hosted-agent source remains a separate publishable context. The API image
neither relies on a sibling `PYTHONPATH` nor imports the full hosted runtime.
The non-deploying
`test-generated-api-image.ps1` regression must build the composed generated
project with production dependencies only and prove import/composition/wire
parity before live validation. Exact file hashes were A client
`4D40A8951409226C0A19637365DE16234117B90028779C7638EEB4C8EA0809DC`,
A bridge
`893F4E6C72ED1E714E8932A83393A00601F0D45B39DC650C5014C3F5426130B4`,
and C composition
`8C095B37A098F2298D17DC6684BC1B8F07A9081BA469F113C6C3D7B9C4A0C911`.
The resulting content image-manifest digest was
`sha256:fd0f7c76f26d152789006aace213cd436e21be31567ddde8b0d7cfeb7a84496b`.
The local manifest-list digest is omitted because BuildKit provenance
attestation metadata changes it without changing the image content.
The generated Dockerfile SHA-256 was
`7066B0036EF77B525EBDD8A40CE568720844B4AE6563464D43970964F414C228`.
The integration coordinator independently reports normal default Docker
CMD/app lifespan passed against isolated PostgreSQL 17 with inherited
`SSL_CERT_FILE`, `verify-full`, `sslrootcert=system`, and
`pg_stat_ssl.ssl=true`; health returned `204` and protected API access returned
`401`. Wrong-hostname and untrusted-CA negatives failed closed. B did not rerun
that PostgreSQL suite. Canonical packaging evidence is complete. Live image, health,
authentication, and managed-identity database startup are verified;
human-authorized hosted workflow, recovery, evaluation, browser, and exact
telemetry evidence remain blocked or failed as recorded above.
The exact generated web target was separately built with the credentialless
HTTPS npm proxy `https://packagefeedproxy.microsoft.io/npm/`; it retained
`npm ci` and produced content image-manifest digest
`sha256:935b7688791961f8168de26c07519b30074877869bbac4652446c298d4c7bb86`.

## Directory application contract

`scripts/azure/configure-entra.ps1` provides non-interactive read-only
validation and an explicit `-Apply` mode for two uniquely named single-tenant
registrations. It exposes the three delegated workflow scopes, defines
`Workflow.User`, `Workflow.Approver`, and the application-only
`Hosted.Workflow.Invoke` role, configures localhost and exact deployed SPA
origins, and preauthorizes only the SPA client. The hosted version's dedicated
principal receives only `Hosted.Workflow.Invoke`. Azure CLI mode
returns tenant/client/app-ID-URI values directly to the deployment orchestrator;
optional azd mode may persist the same nonsecret identifiers. It creates no
credentials or users.

The hosted app role authenticates only the platform service identity; it never
mints or substitutes human authority. Before any Responses dispatch, the
application must pre-establish exact human principal/case authority bound to
the server-selected conversation and channel. Foundry platform user, session,
and call identifiers are opaque workload correlation and continuity values,
not human authority; the API bridge sends neither caller-selected
`agent_session_id` nor actor-subject metadata to Foundry. Hosted binding calls
verify the server-owned authority record and fail closed on absence or
mismatch. This infrastructure workstream does not implement or weaken that
business authorization boundary.

Directory permissions are independent of subscription `Owner`. The operator
must be allowed to create/update the two app registrations, create the API
service principal, inspect the hosted version service principal, and assign an
application role through Microsoft Graph. Subscription roles do not imply
those directory permissions. Entra deletion is a separately confirmed
`teardown-entra.ps1` operation and is not part of resource-group teardown.
